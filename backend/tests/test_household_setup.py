import json
import re

import pytest
from fastapi.testclient import TestClient

from app import orchestrator
from app.agents import BY_NAME
from app.agents.household import HouseholdAgent
from app.main import STATE, app
from app.state import FamilyState

DEMO_NAMES = re.compile(r"\b(priya|rahul|aarav|dadi)\b", re.I)
REDWOOD_ORDER = ["#245D63", "#D7790F", "#31A09C", "#4E4137", "#699E61"]


@pytest.fixture
def blank(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")  # the app's real default
    state = FamilyState(demo=False)
    state.now = {"date": "2026-11-20", "time": "09:00"}
    monkeypatch.setattr(state, "refresh_clock", lambda: None)  # keep the clock still so doses and dates are predictable
    return state


@pytest.fixture
def family(blank):
    """A real household: Maya (mom), Arjun (dad), Kabir (child, 9), Nani (grandmother, 70)."""
    h = HouseholdAgent()
    h.call(blank, "add_member", name="Maya", relation="Mom", age=36, gender="female", diet=["vegetarian"], notes="Loves South Indian food")
    h.call(blank, "add_member", name="Arjun", relation="Dad", age=39, gender="male")
    h.call(blank, "add_member", name="Kabir", relation="Son", age=9, allergies=["peanuts"], notes="Plays cricket")
    h.call(blank, "add_member", name="Nani", relation="Grandmother", age=70, language="Hindi", notes="Bad knees: needs step-free access")
    return blank


@pytest.fixture
def client():
    STATE.reset(demo=False)
    yield TestClient(app)
    STATE.reset(demo=False)


def everything_said(state) -> str:
    """Every word the app showed or sent: replies, notifications and tool results."""
    parts = [t["text"] for t in state.transcript] + [n["text"] for n in state.notifications]
    parts += [json.dumps(e["result"], default=str) for e in state.events if e["agent"] != "orchestrator"]
    return "\n".join(parts)


# ---------------------------------------------------------------- the empty household

def test_a_new_household_is_empty(blank):
    assert blank.members == [] and blank.memory == [] and blank.calendar == []
    assert blank.persona == "" and not blank.demo
    d = blank.domains
    assert d["school"]["kids"] == {} and d["school"]["arrivals"] == []
    assert d["care"]["seniors"] == {} and d["care"]["orders"] == []
    assert d["travel"]["trips"] == [] and d["travel"]["bookings"] == []
    assert d["dining"]["reservations"] == [] and d["dining"]["pickups"] == []
    assert d["money"]["expenses"] == []


def test_service_catalogues_are_kept_for_a_new_household(blank):
    assert len(blank.domains["travel"]["catalog"]) > 0
    assert len(blank.domains["dining"]["restaurants"]) > 0
    assert blank.domains["school"]["school"]["name"] == "School"  # no invented school


def test_blank_snapshot_reports_no_household_and_hides_demo_scenarios(blank):
    snap = blank.snapshot()
    assert snap["household"] == {"exists": False, "demo": False}
    assert all(a["triggers"] == [] for a in snap["agents"])


def test_demo_state_is_unchanged_and_lists_scenarios():
    demo = FamilyState()
    assert demo.demo and [m["name"] for m in demo.members] == ["Priya", "Rahul", "Aarav", "Dadi"]
    assert demo.snapshot()["household"] == {"exists": True, "demo": True}
    assert any(a["triggers"] for a in demo.snapshot()["agents"])
    assert demo.now == {"date": "2026-11-20", "time": "07:30"}


def test_reset_keeps_the_current_mode_and_load_demo_switches():
    state = FamilyState(demo=False)
    state.reset()
    assert state.members == []
    state.load_demo()
    assert state.demo and len(state.members) == 4
    state.reset()
    assert state.demo and len(state.members) == 4
    state.reset(demo=False)
    assert not state.demo and state.members == []


def test_real_household_follows_the_real_clock():
    state = FamilyState(demo=False)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", state.now["date"]) and re.fullmatch(r"\d{2}:\d{2}", state.now["time"])
    state.now = {"date": "1999-01-01", "time": "00:00"}
    state.refresh_clock()
    assert state.now["date"] != "1999-01-01"


# ---------------------------------------------------------------- members

def test_members_get_redwood_colours_in_order_and_derived_kind(family):
    assert [m["color"] for m in family.members] == REDWOOD_ORDER[:4]
    assert [m["kind"] for m in family.members] == ["adult", "adult", "child", "senior"]
    assert family.persona == "maya"


def test_allergies_diet_and_notes_become_tagged_memory(family):
    facts = {f["fact"]: f["tags"] for f in family.memory}
    assert facts["Vegetarian"] == ["food", "veg"]
    assert facts["Allergic to peanuts"] == ["allergy", "food"]
    assert "interest" in facts["Loves South Indian food"]
    assert "access" in facts["Bad knees: needs step-free access"]
    assert {f["about"] for f in family.memory} == {"maya", "kabir", "nani"}


def test_dining_uses_the_facts_a_new_family_entered(family):
    from app.agents.dining import derive_constraints

    cons = derive_constraints(family, [m["id"] for m in family.members])
    assert cons["nut_free"] == ["kabir"] and cons["veg_only"] == ["maya"] and cons["step_free"] == ["nani"]


def test_first_member_creates_no_notification_later_ones_do(blank):
    h = HouseholdAgent()
    h.call(blank, "add_member", name="Maya", relation="Mom", age=36)
    assert blank.notifications == []
    h.call(blank, "add_member", name="Arjun", relation="Dad", age=39)
    assert len(blank.notifications) == 1 and blank.notifications[0]["to"] == ["maya"]


def test_add_member_validation(blank):
    h = HouseholdAgent()
    assert h.call(blank, "add_member", name="Maya", relation="Mom", age=200)[0] == "error"
    assert h.call(blank, "add_member", name="Maya", relation="Mom", age=30, gender="robot")[0] == "error"
    assert h.call(blank, "add_member", name="", relation="Mom", age=30)[0] == "error"
    assert h.call(blank, "add_member", name="Maya", relation="Mom", age=30)[0] == "ok"
    assert h.call(blank, "add_member", name="maya", relation="Aunt", age=30)[0] == "error"


def test_update_member_recomputes_kind_from_age(family):
    h = HouseholdAgent()
    status, res = h.call(family, "update_member", member_id="kabir", name="Kabir Rao", age=19, gender="male", language="English")
    assert status == "ok" and res["member"]["kind"] == "adult" and res["member"]["name"] == "Kabir Rao"
    assert family.member("kabir")["language"] == "English" and family.member("kabir")["id"] == "kabir"
    assert h.call(family, "update_member", member_id="kabir", name="Maya")[0] == "error"
    assert h.call(family, "update_member", member_id="nobody")[0] == "error"


def test_update_to_senior_creates_care_record(family):
    HouseholdAgent().call(family, "update_member", member_id="arjun", age=64)
    assert family.member("arjun")["kind"] == "senior" and "arjun" in family.domains["care"]["seniors"]


def test_remove_member_needs_confirmation_and_cleans_up(family):
    h = HouseholdAgent()
    family.calendar.append({"id": "e1", "title": "School", "member_ids": ["kabir"], "date": "2026-11-21", "start": "08:00", "end": "14:00", "location": "", "kind": "school", "source": "t"})
    family.calendar.append({"id": "e2", "title": "Movie", "member_ids": ["kabir", "maya"], "date": "2026-11-21", "start": "16:00", "end": "18:00", "location": "", "kind": "event", "source": "t"})
    assert h.call(family, "remove_member", member_id="kabir")[0] == "error"
    assert h.call(family, "remove_member", member_id="kabir", confirm=False)[0] == "error"
    assert len(family.members) == 4
    status, res = h.call(family, "remove_member", member_id="kabir", confirm=True)
    assert status == "ok" and res["family_size"] == 3
    assert all(m["id"] != "kabir" for m in family.members)
    assert all(f["about"] != "kabir" for f in family.memory)
    assert [e["id"] for e in family.calendar] == ["e2"] and family.calendar[0]["member_ids"] == ["maya"]
    assert "kabir" not in family.domains["school"]["kids"]


def test_removing_the_speaker_moves_persona_on(family):
    family.persona = "maya"
    HouseholdAgent().call(family, "remove_member", member_id="maya", confirm=True)
    assert family.persona == "arjun"


# ---------------------------------------------------------------- every agent works for a new family

def test_school_works_for_an_added_child(family):
    orchestrator.converse(family, "kabir", "I reached school")
    assert family.domains["school"]["kids"]["kabir"]["status"] == "at_school"
    orchestrator.converse(family, "kabir", "I got 42 out of 50 in maths")
    assert family.domains["school"]["kids"]["kabir"]["marks"][-1]["score"] == 42
    reply = orchestrator.converse(family, "maya", "How is Kabir doing in school?")
    assert "Kabir" in reply and family.transcript[-1]["agent"] == "school"


def test_care_without_medicines_is_graceful_then_works_after_adding_one(family):
    reply = orchestrator.converse(family, "nani", "I took my medicine")
    assert "no medicines" in reply.lower() or "nothing to log" in reply.lower()
    care = BY_NAME["care"]
    status, res = care.call(family, "add_medicine", member_id="nani", name="Metformin", dose="500 mg", times=["08:30"], stock_days=2)
    assert status == "ok" and res["count"] == 1
    assert care.call(family, "add_medicine", member_id="nani", name="metformin")[0] == "error"
    assert care.call(family, "add_medicine", member_id="nani", name="Tablet", times=["8am"])[0] == "error"
    orchestrator.converse(family, "nani", "I took my medicine")
    assert family.domains["care"]["seniors"]["nani"]["meds"][0]["taken"]
    reply = orchestrator.converse(family, "nani", "my medicine is running out")
    assert family.domains["care"]["orders"] and family.domains["care"]["orders"][0]["med"] == "Metformin"


def test_care_with_nobody_to_care_for_says_so(blank):
    HouseholdAgent().call(blank, "add_member", name="Maya", relation="Mom", age=36)
    reply = orchestrator.converse(blank, "maya", "did anyone take their medicines")
    assert "Family" in reply and not blank.domains["care"]["seniors"]


def test_senior_alerts_go_to_the_real_parents(family):
    orchestrator.converse(family, "nani", "I feel dizzy")
    notes = [n for n in family.notifications if n["kind"] == "care"]
    assert notes and set(notes[-1]["to"]) == {"maya", "arjun"}
    assert "Maya and Arjun" in family.transcript[-1]["text"]


def test_travel_with_no_trips_is_graceful(family):
    reply = orchestrator.converse(family, "arjun", "when is my flight")
    assert reply and family.transcript[-1]["role"] == "agent"
    reply = orchestrator.converse(family, "arjun", "when is my cab coming")
    assert reply


def test_calendar_and_dining_work_for_a_new_family(family):
    reply = orchestrator.converse(family, "maya", "When is everyone free on Sunday?")
    assert "free" in reply.lower()
    reply = orchestrator.converse(family, "maya", "Let's all go out for lunch on Sunday")
    assert family.pending and family.pending["agent"] == "dining"
    assert "Kabir" in reply and "Nani" in reply  # the reasons name the people who have the needs
    orchestrator.converse(family, "maya", "yes book it")
    assert family.domains["dining"]["reservations"]
    assert any(e["member_ids"] == ["maya", "arjun", "kabir", "nani"] and e["kind"] == "dining" for e in family.calendar)


def test_household_agent_roster_and_memory_for_a_new_family(family):
    reply = orchestrator.converse(family, "maya", "Who is in the family?")
    assert "Maya" in reply and "Nani" in reply
    orchestrator.converse(family, "arjun", "Remember that I don't like mushrooms")
    assert any(f["about"] == "arjun" and "mushrooms" in f["fact"] for f in family.memory)


def test_nothing_names_the_demo_family_in_a_real_household(family):
    for who, text in [
        ("kabir", "I reached school"), ("maya", "How is Kabir doing in school?"), ("nani", "I took my medicine"),
        ("nani", "I feel unwell"), ("arjun", "when is my flight"), ("maya", "When is everyone free on Sunday?"),
        ("maya", "Let's all go out for lunch on Sunday"), ("maya", "yes book it"), ("maya", "Who is in the family?"),
        ("maya", "hello"), ("maya", "what can you do"), ("nani", "my medicine is running out"),
        ("arjun", "book Nani's doctor appointment for Thursday at 11"),
    ]:
        orchestrator.converse(family, who, text)
    assert not DEMO_NAMES.search(everything_said(family)), DEMO_NAMES.search(everything_said(family))


# ---------------------------------------------------------------- endpoints

def test_endpoints_refuse_to_talk_without_a_household(client):
    assert client.get("/api/state").json()["household"] == {"exists": False, "demo": False}
    res = client.post("/api/converse", json={"member_id": "anyone", "message": "hello"})
    assert res.status_code == 409 and res.json()["detail"]["error"] == "no_household"
    res = client.post("/api/agent/start", json={"member_id": "anyone"})
    assert res.status_code == 409 and res.json()["detail"]["error"] == "no_household"
    res = client.post("/v1/chat/completions", json={"stream": False, "messages": [{"role": "user", "content": "hi"}]})
    assert res.status_code == 409
    res = client.post("/api/trigger/school/arrival")
    assert res.status_code == 409 and res.json()["detail"]["error"] == "demo_only"


def test_setup_through_the_tool_endpoint_then_talk(client):
    res = client.post("/api/tool/household/add_member", json={"args": {"name": "Maya", "relation": "Mom", "age": 36, "gender": "female"}}).json()
    assert res["status"] == "ok" and res["state"]["household"]["exists"] and res["state"]["persona"] == "maya"
    out = client.post("/api/converse", json={"member_id": "maya", "message": "hello"})
    assert out.status_code == 200 and out.json()["reply"]
    assert client.post("/api/converse", json={"member_id": "nobody", "message": "hello"}).status_code == 404


def test_demo_and_reset_endpoints(client):
    snap = client.post("/api/household/demo").json()
    assert snap["household"] == {"exists": True, "demo": True} and len(snap["members"]) == 4
    assert any(a["triggers"] for a in snap["agents"])
    client.post("/api/tool/household/add_member", json={"args": {"name": "Anaya", "relation": "Daughter", "age": 6}})
    assert len(client.get("/api/state").json()["members"]) == 5
    snap = client.post("/api/reset").json()  # back to the demo starting point, not to empty
    assert snap["household"]["demo"] and len(snap["members"]) == 4
    snap = client.post("/api/household/reset").json()
    assert snap["household"] == {"exists": False, "demo": False} and snap["members"] == [] and snap["calendar"] == []
    assert client.post("/api/reset").json()["members"] == []


def test_config_has_no_demo_voices_for_an_empty_household(client):
    assert client.get("/api/config").json()["voices"] == {}
