import pytest

from app import calendar_core as cal
from app.state import FamilyState
from app.toolkit import Tool, ToolError, run_parallel, run_tool


@pytest.fixture
def state():
    return FamilyState()


def test_sunday_common_slot_respects_everyones_calendar(state):
    everyone = [m["id"] for m in state.members]
    slots = cal.find_common_slots(state, everyone, "2026-11-22", 90)
    starts = [s["start"] for s in slots]
    assert "13:00" in starts and "09:30" in starts
    assert "14:00" not in starts  # Rahul's call starts at 15:00 and the lunch would run to 15:30


def test_conflict_detection(state):
    assert cal.conflicts(state, ["rahul"], "2026-11-22", "14:30", "15:30")
    assert not cal.conflicts(state, ["rahul"], "2026-11-22", "12:00", "14:00")


def test_add_move_remove_event(state):
    ev = cal.add_event(state, ["priya", "rahul"], "Lunch", "2026-11-22", "13:00", "14:30", "Udupi Garden", "dining", "dining")
    assert ev in state.calendar
    cal.move_event(state, ev["id"], start="13:30")
    assert (ev["start"], ev["end"]) == ("13:30", "15:00")
    cal.remove_event(state, ev["id"])
    assert ev not in state.calendar
    with pytest.raises(ToolError):
        cal.remove_event(state, "nope")


def test_run_tool_logs_event_with_agent_and_handles_errors(state):
    ok = Tool("ping", "d", {"type": "object", "properties": {}}, lambda s: {"pong": True})
    bad = Tool("boom", "d", {"type": "object", "properties": {}}, lambda s: (_ for _ in ()).throw(ToolError("nope")), stage="after")
    assert run_tool(state, "travel", ok, {}, latency=0) == ("ok", {"pong": True})
    assert run_tool(state, "travel", bad, {}, latency=0)[0] == "error"
    assert [(e["agent"], e["tool"], e["status"]) for e in state.events] == [("travel", "ping", "ok"), ("travel", "boom", "error")]
    assert state.stage == "after"
    results = run_parallel(state, "calendar", [(ok, {}), (ok, {})])
    assert [r[0] for r in results] == ["ok", "ok"]


def test_notify_is_in_app_when_chat_not_configured(state, monkeypatch):
    for key in ("AGORA_CHAT_HOST", "AGORA_CHAT_APP_ID", "AGORA_CHAT_APP_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **k: None)
    note = state.notify(["priya", "rahul"], "Aarav reached school", "school", "school")
    assert note["mode"] == "in_app" and note["status"] == "in_app" and state.notifications == [note]


def test_member_helpers(state):
    assert state.find_member("tell Dadi to rest")["id"] == "dadi"
    assert state.speaks_hindi("dadi") and not state.speaks_hindi("rahul")
    assert state.parents() == ["priya", "rahul"]


def test_parse_date_and_time():
    assert cal.parse_date("lunch on Sunday", "2026-11-20") == "2026-11-22"
    assert cal.parse_date("kal subah", "2026-11-20") == "2026-11-21"
    assert cal.parse_date("fly on 26 Dec", "2026-11-20") == "2026-12-26"
    assert cal.parse_date("hello", "2026-11-20") is None
    assert cal.parse_time("at 1 pm please") == "13:00" and cal.parse_time("by 9:15 am") == "09:15"
    assert cal.parse_time("at 13:30") == "13:30" and cal.parse_time("no time") is None


def test_mentioned_members(state):
    assert [m["id"] for m in state.mentioned_members("tell Dadi and Rahul")] == ["rahul", "dadi"]
    assert len(state.mentioned_members("everyone is free")) == 4
    assert state.mentioned_members("dadi's medicine")[0]["id"] == "dadi"
