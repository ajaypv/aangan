import pytest

from app.agents.calendar import CalendarAgent
from app.state import FamilyState
from app.toolkit import run_tool


@pytest.fixture(autouse=True)
def fast_mock(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agent():
    return CalendarAgent()


def tools_used(state):
    return [(e["tool"], e["status"]) for e in state.events if e["agent"] == "calendar"]


def test_free_slots_names_blockers_and_windows(state, agent):
    reply = agent.handle(state, "rahul", "When is everyone free on Sunday?")
    assert "09:30 to 15:00" in reply and "18:30 to 21:00" in reply
    assert "Rahul's Client prep call 15:00-17:00" in reply
    assert ("find_family_slots", "ok") in tools_used(state)


def test_free_slots_for_lunch_suggests_best_time(state, agent):
    reply = agent.handle(state, "rahul", "when are we all free for lunch on Sunday")
    assert "Best for lunch: 13:00 to 14:30" in reply


def test_free_slots_without_a_date_prefers_family_day(state, agent):
    reply = agent.handle(state, "rahul", "when is everyone free for 2 hours")
    assert reply.startswith("Sunday,")


def test_free_slots_hinglish(state, agent):
    reply = agent.handle(state, "aarav", "sab kab free hain Sunday ko")
    assert "free hain" in reply and "se" in reply and "tak" in reply


def test_schedule_for_named_member_and_for_speaker(state, agent):
    reply = agent.handle(state, "rahul", "What is Rahul doing on Monday?")
    assert "flight 6E-2045 BLR to DEL at 05:30" in reply  # schedule items read mid-sentence, so the title is lower-cased
    reply = agent.handle(state, "rahul", "what's on tomorrow")
    assert "you have nothing" in reply
    reply = agent.handle(state, "aarav", "aaj mera schedule kya hai")
    assert "School 08:00 baje" in reply


def test_clashes_report_double_booking_and_logistics_headsup(state, agent):
    reply = agent.handle(state, "rahul", "any clashes this week?")
    assert "No double-bookings" in reply and "only Priya can see Aarav off for school on Monday" in reply  # lower-cased after "watch:"
    assert "Rahul has Flight 6E-2045 BLR to DEL at 05:30" in reply
    state.calendar.append({"id": "x1", "title": "Dentist", "member_ids": ["priya"], "date": "2026-11-20", "start": "11:30",
                           "end": "12:00", "location": "", "kind": "event", "source": "test"})
    reply = agent.handle(state, "rahul", "any conflicts?")
    assert "double-booked on Friday" in reply and "Product review" in reply


def test_no_parent_free_is_a_clash(state, agent):
    state.calendar.append({"id": "x2", "title": "Offsite", "member_ids": ["priya"], "date": "2026-11-23", "start": "07:00",
                           "end": "09:00", "location": "", "kind": "work", "source": "test"})
    reply = agent.handle(state, "rahul", "do we have any clashes")
    assert "No parent is free to see Aarav off for school on Monday" in reply


def test_move_event_notifies_and_keeps_length(state, agent):
    reply = agent.handle(state, "rahul", "move the swimming class to 10")
    ev = next(e for e in state.calendar if e["id"] == "swim-sun")
    assert (ev["start"], ev["end"]) == ("10:00", "11:00")
    assert "Moved the swimming class to Sunday at 10:00" in reply  # natural article and casing for a spoken reply
    assert [t for t, _ in tools_used(state)] == ["check_conflicts", "move_event"]
    note = state.notifications[-1]
    assert note["kind"] == "calendar" and note["to"] == ["aarav"] and "10:00" in note["text"]


def test_move_to_a_clash_warns(state, agent):
    state.calendar.append({"id": "piano", "title": "Piano lesson", "member_ids": ["aarav"], "date": "2026-11-22", "start": "10:00",
                           "end": "11:00", "location": "", "kind": "activity", "source": "test"})
    reply = agent.handle(state, "rahul", "move the swimming class to 10")
    assert "Heads up, it now clashes with Piano lesson at 10:00" in reply
    reply = agent.handle(state, "rahul", "move the satsang to 3 pm")
    assert "Heads up" not in reply  # satsang is Dadi's only: no overlap with Rahul's call


def test_move_asks_when_time_is_missing(state, agent):
    reply = agent.handle(state, "rahul", "reschedule the swimming class")
    assert "which time or day" in reply and state.pending["agent"] == "calendar"
    assert agent.score(state, "whatever") == 3
    reply = agent.handle(state, "rahul", "at 11")
    assert "11:00" in reply and state.pending is None
    assert next(e for e in state.calendar if e["id"] == "swim-sun")["start"] == "11:00"


def test_add_event(state, agent):
    reply = agent.handle(state, "rahul", "add a dentist appointment for Aarav on Saturday at 5 pm")
    ev = next(e for e in state.calendar if e["title"] == "Dentist appointment")
    assert (ev["date"], ev["start"], ev["end"], ev["member_ids"]) == ("2026-11-21", "17:00", "18:00", ["aarav"])
    assert "Added a dentist appointment for Aarav tomorrow at 17:00" in reply  # Saturday is tomorrow (today is Fri 20 Nov)
    assert state.notifications[-1]["kind"] == "calendar"


def test_add_event_slot_filling_and_overlap_warning(state, agent):
    reply = agent.handle(state, "rahul", "add a meeting for Rahul on Sunday")
    assert "What time" in reply and state.pending["action"] == "add"
    reply = agent.handle(state, "rahul", "3:30 pm")
    assert "Heads up, it overlaps Client prep call at 15:00" in reply and state.pending is None


def test_add_event_hinglish(state, agent):
    reply = agent.handle(state, "aarav", "kal 5 baje dentist appointment add karo")
    assert "add kar diya" in reply
    ev = next(e for e in state.calendar if e["title"] == "Dentist appointment")
    assert (ev["date"], ev["start"], ev["member_ids"]) == ("2026-11-21", "17:00", ["aarav"])


def test_pending_can_be_dropped(state, agent):
    agent.handle(state, "rahul", "add a meeting for Rahul on Sunday")
    reply = agent.handle(state, "rahul", "never mind")
    assert reply == "Okay, dropped it." and state.pending is None


def test_cancel_event(state, agent):
    reply = agent.handle(state, "rahul", "cancel the satsang")
    assert "Cancelled the satsang on Sunday" in reply
    assert not any(e["id"] == "satsang-sun" for e in state.calendar)
    assert state.notifications[-1]["to"] == ["dadi"]


def test_score_claims_own_intents_only(state, agent):
    for text in ["when is everyone free on Sunday", "what's on tomorrow", "any clashes this week",
                 "move the swimming class to 10", "add a dentist appointment for Aarav on Saturday at 5 pm"]:
        assert agent.score(state, text) >= 3, text
    for text in ["book a table for Sunday lunch", "my flight is delayed", "Dadi ne dawai le li", "Sunday ko sab saath lunch pe jaana hai",
                 "how is Aarav doing in school", "Main school pahunch gaya", "meet my daughter Anaya", "book Dadi's doctor appointment Thursday",
                 "hello there", "remember Rahul doesn't like mushrooms"]:
        assert agent.score(state, text) == 0, text
        assert agent.handle(state, "rahul", text) is None, text


def test_week_digest_trigger(state, agent):
    state.persona = "rahul"
    reply = agent.run_trigger(state, "week_digest")
    assert "Busiest day is Sunday with 3 events" in reply and "Best family window: Sunday 09:30 to 15:00" in reply
    assert "only Priya can see Aarav off" in reply
    note = state.notifications[-1]
    assert note["kind"] == "calendar" and note["to"] == ["priya", "rahul", "aarav", "dadi"]
    assert "Week ahead (Fri 20 Nov to Tue 24 Nov)" in note["text"] and "Rahul: Client prep call Sun 15:00" in note["text"]
    send = next(e for e in state.events if e["tool"] == "send_digest")
    assert send["stage"] == "after" and send["agent"] == "calendar"
    assert state.transcript[-1]["role"] == "agent" and state.transcript[-1]["agent"] == "calendar"
    assert agent.triggers[0].name == "week_digest" and agent.triggers[0].label == "Weekly family digest"


def test_tool_schemas_are_complete_and_errors_are_recoverable(state, agent):
    assert [t.name for t in agent.tools] == [
        "get_schedule", "find_family_slots", "check_conflicts", "scan_clashes", "create_event", "move_event", "cancel_event", "send_digest",
    ]
    for t in agent.tools:
        assert t.parameters["type"] == "object" and t.description and "required" in t.parameters
        assert all(k in t.parameters["properties"] for k in t.parameters["required"])
    assert run_tool(state, "calendar", agent.tool("get_schedule"), {"member_ids": ["ghost"], "date": "2026-11-22"}, 0)[0] == "error"
    assert run_tool(state, "calendar", agent.tool("get_schedule"), {"member_ids": ["priya"], "date": "soon"}, 0)[0] == "error"
    assert run_tool(state, "calendar", agent.tool("move_event"), {"event_id": "nope", "start": "10:00"}, 0)[0] == "error"
    assert run_tool(state, "calendar", agent.tool("create_event"),
                    {"member_ids": ["priya"], "title": "x", "date": "2026-11-22", "start": "10:00", "end": "09:00"}, 0)[0] == "error"


def test_created_event_ids_stay_unique_after_removals(state, agent):
    run_tool(state, "calendar", agent.tool("cancel_event"), {"event_id": "satsang-sun"}, 0)
    for title in ("One", "Two"):
        run_tool(state, "calendar", agent.tool("create_event"),
                 {"member_ids": ["priya"], "title": title, "date": "2026-11-22", "start": "10:00", "end": "11:00"}, 0)
    ids = [e["id"] for e in state.calendar]
    assert len(ids) == len(set(ids))
