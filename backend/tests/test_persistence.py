import json
import os

import pytest
from fastapi.testclient import TestClient

from app import persistence
from app.agents.household import HouseholdAgent
from app.main import STATE, app
from app.state import FamilyState


def household() -> FamilyState:
    state = FamilyState(demo=False)
    h = HouseholdAgent()
    h.call(state, "add_member", name="Maya", relation="Mom", age=36, allergies=["eggs"], notes="Loves chai")
    h.call(state, "add_member", name="Kabir", relation="Son", age=9)
    state.say("user", "hello", "maya")
    return state


def test_round_trip_restores_everything_the_family_entered(tmp_path):
    state = household()
    state.calendar.append({"id": "ev-1", "title": "Dentist", "member_ids": ["kabir"], "date": "2026-12-01", "start": "10:00", "end": "11:00", "location": "", "kind": "health", "source": "t"})
    state.domains["school"]["kids"]["kabir"]["marks"].append({"id": "mk1", "subject": "Maths", "score": 40, "max": 50, "date": "2026-11-20", "exam": "Test"})
    persistence.save(state)

    fresh = FamilyState(demo=False)
    assert persistence.load(fresh) is True
    assert [m["name"] for m in fresh.members] == ["Maya", "Kabir"]
    assert fresh.memory == state.memory
    assert fresh.calendar == state.calendar
    assert fresh.domains["school"]["kids"]["kabir"]["marks"][0]["score"] == 40
    assert fresh.transcript[0]["text"] == "hello"
    assert fresh.demo is False and fresh.persona == "maya"
    assert fresh.pending is None


def test_demo_flag_and_scripted_clock_survive(tmp_path):
    demo = FamilyState()
    demo.now["time"] = "09:10"
    persistence.save(demo)
    fresh = FamilyState(demo=False)
    assert persistence.load(fresh) and fresh.demo and len(fresh.members) == 4
    assert fresh.now == {"date": "2026-11-20", "time": "09:10"}


def test_a_real_household_does_not_restore_a_stale_clock():
    state = household()
    persistence.save(state)
    data = json.loads(persistence.data_path().read_text())
    assert data["now"] is None
    fresh = FamilyState(demo=False)
    persistence.load(fresh)
    assert fresh.now["date"] == FamilyState(demo=False).now["date"]


def test_secrets_are_never_written(monkeypatch):
    monkeypatch.setenv("MURF_API_KEY", "murf-secret-123")
    monkeypatch.setenv("AGORA_APP_CERTIFICATE", "cert-secret-456")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret-789")
    persistence.save(household())
    text = persistence.data_path().read_text()
    assert not any(s in text for s in ("murf-secret-123", "cert-secret-456", "llm-secret-789"))


def test_writes_are_atomic_and_leave_no_temp_file():
    persistence.save(household())
    path = persistence.data_path()
    assert path.exists() and not path.with_name(path.name + ".tmp").exists()
    persistence.save(household())
    assert json.loads(path.read_text())["members"][0]["name"] == "Maya"


def test_only_the_last_200_events_are_saved():
    state = household()
    for i in range(250):
        state.log("household", f"tool{i}", {}, "ok", {}, 1)
    persistence.save(state)
    saved = json.loads(persistence.data_path().read_text())["events"]
    assert len(saved) == 200 and saved[-1]["tool"] == "tool249"


def test_missing_file_means_nothing_to_load():
    state = FamilyState(demo=False)
    assert persistence.load(state) is False and state.members == []


@pytest.mark.parametrize("content", ["{not json", "[]", '{"members": "oops"}', '{"members": [{"id": "a"}], "memory": [], "calendar": [], "domains": {}, "notifications": [], "events": [], "transcript": []}', ""])
def test_corrupt_file_is_kept_aside_and_never_crashes(content):
    path = persistence.data_path()
    path.write_text(content)
    state = FamilyState(demo=False)
    assert persistence.load(state) is False
    assert state.members == [] and state.memory == []
    assert not path.exists() and path.with_name(path.name + ".bad").read_text() == content


def test_a_failed_load_leaves_an_existing_household_untouched():
    state = household()
    persistence.data_path().write_text('{"members": 5}')
    assert persistence.load(state) is False
    assert [m["name"] for m in state.members] == ["Maya", "Kabir"]


def test_agents_added_later_get_a_blank_domain_on_load():
    state = household()
    persistence.save(state)
    data = json.loads(persistence.data_path().read_text())
    data["domains"].pop("money")
    persistence.data_path().write_text(json.dumps(data))
    fresh = FamilyState(demo=False)
    assert persistence.load(fresh) and fresh.domains["money"]["expenses"] == []


# ---------------------------------------------------------------- through the app

@pytest.fixture
def client():
    STATE.reset(demo=False)
    yield TestClient(app)
    STATE.reset(demo=False)


def test_a_change_made_through_the_api_is_saved_but_reads_do_not_write(client):
    path = persistence.data_path()
    client.get("/api/state")
    assert not path.exists()
    client.post("/api/tool/household/add_member", json={"args": {"name": "Maya", "relation": "Mom", "age": 36}})
    assert [m["name"] for m in json.loads(path.read_text())["members"]] == ["Maya"]
    client.post("/api/converse", json={"member_id": "maya", "message": "hello"})
    assert json.loads(path.read_text())["transcript"][-1]["role"] == "agent"
    client.post("/api/household/reset")
    assert json.loads(path.read_text())["members"] == []


def test_the_llm_endpoint_saves_too(client):
    client.post("/api/tool/household/add_member", json={"args": {"name": "Maya", "relation": "Mom", "age": 36}})
    os.remove(persistence.data_path())
    client.post("/v1/chat/completions?member=maya", json={"stream": False, "messages": [{"role": "user", "content": "hello"}]})
    assert persistence.data_path().exists()


def test_startup_loads_the_saved_household(client):
    persistence.save(household())
    STATE.reset(demo=False)
    with TestClient(app) as started:
        snap = started.get("/api/state").json()
    assert [m["name"] for m in snap["members"]] == ["Maya", "Kabir"] and snap["household"]["demo"] is False


def test_startup_with_nothing_saved_is_empty_unless_demo_is_requested(monkeypatch):
    STATE.reset(demo=False)
    with TestClient(app) as started:
        assert started.get("/api/state").json()["members"] == []
    monkeypatch.setenv("AANGAN_DEMO_ON_START", "1")
    STATE.reset(demo=False)
    with TestClient(app) as started:
        snap = started.get("/api/state").json()
    assert snap["household"]["demo"] is True and len(snap["members"]) == 4
    STATE.reset(demo=False)


def test_startup_survives_a_corrupt_file():
    persistence.data_path().write_text("{broken")
    STATE.reset(demo=False)
    with TestClient(app) as started:
        assert started.get("/api/state").status_code == 200
    assert persistence.data_path().with_name("household.json.bad").exists()
