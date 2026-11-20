import pytest

from app.agents.travel import TravelAgent
from app.state import FamilyState
from app.toolkit import ToolError

agent = TravelAgent()


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)
    return FamilyState()


def trip(state, trip_id="trip-1"):
    return next(t for t in state.domains["travel"]["trips"] if t["id"] == trip_id)


def tools(state):
    return [(e["tool"], e["status"]) for e in state.events if e["agent"] == "travel"]


def test_flight_delay_trigger_proposes_best_alternative(state):
    msg = agent.run_trigger(state, "flight_delay")
    t = trip(state)
    assert (t["status"], t["dep"], t["arr"], t["delay_min"]) == ("DELAYED", "08:30", "11:20", 180)
    assert state.pending["agent"] == "travel" and state.pending["flight_id"] == "6E-6107"
    assert "6E-6107" in msg and "Shall I book it?" in msg
    assert state.transcript[-1]["member_id"] == "rahul" and state.transcript[-1]["agent"] == "travel"
    assert any("delayed by 3 hours" in n["text"] for n in state.notifications)
    assert any("Client meeting" in e["title"] for e in state.calendar)  # meeting added so the clash is visible
    flight_event = next(e for e in state.calendar if e["id"] == "flight-mon")
    assert (flight_event["start"], flight_event["end"]) == ("08:30", "11:20")


def test_confirm_rebooks_moves_cab_updates_calendar_and_notifies(state):
    agent.run_trigger(state, "flight_delay")
    reply = agent.handle(state, "rahul", "yes book it")
    t = trip(state)
    assert (t["status"], t["flight"], t["dep"], t["arr"]) == ("REBOOKED", "6E-6107", "06:20", "09:10")
    assert t["seats"]["rahul"].endswith("C")  # Rahul's remembered aisle preference
    assert t["cab"]["pickup"] == "04:20" and t["cab"]["status"] == "RESCHEDULED"
    flight_event = next(e for e in state.calendar if e["id"] == "flight-mon")
    assert (flight_event["start"], flight_event["end"]) == ("06:20", "09:10")
    assert state.pending is None and "6E-6107" in reply and "04:20" in reply
    names = {name for name, status in tools(state) if status == "ok"}
    assert {"rebook_flight", "update_cab_pickup", "add_trip_to_calendar", "notify_family"} <= names
    assert state.notifications[-1]["to"] == [m["id"] for m in state.members]
    assert state.stage == "after"


def test_constraint_change_replans_mid_proposal(state):
    agent.run_trigger(state, "flight_delay")
    reply = agent.handle(state, "rahul", "actually window seat please")
    assert state.pending["flight_id"] == "SG-8153" and state.pending["constraints"]["seat"] == "window"
    assert reply.startswith("Updated: window seat")


def test_budget_too_low_offers_cheapest_and_keeps_proposal_open(state):
    reply = agent.handle(state, "rahul", "find me another flight under 7000")
    assert "SG-8153" in reply and state.pending["flight_id"] is None
    assert "nothing to book" in agent.handle(state, "rahul", "yes").lower()
    agent.handle(state, "rahul", "ok budget 10000")
    assert state.pending["flight_id"] == "6E-6107"


def test_reject_clears_pending(state):
    agent.run_trigger(state, "flight_delay")
    agent.handle(state, "rahul", "no")
    assert state.pending is None and trip(state)["status"] == "DELAYED"


def test_unrelated_reply_keeps_proposal(state):
    agent.run_trigger(state, "flight_delay")
    reply = agent.handle(state, "rahul", "hmm let me think")
    assert "6E-6107" in reply and state.pending["flight_id"] == "6E-6107"


def test_hinglish_from_priya_about_rahuls_trip(state):
    reply = agent.handle(state, "priya", "Rahul ki flight delay ho gayi, dusri flight dikhao")
    assert "Book kar doon" in reply and state.pending["trip_id"] == "trip-1"
    done = agent.handle(state, "priya", "haan book kar do")
    assert "Ho gaya" in done and trip(state)["flight"] == "6E-6107"


def test_supplier_failure_falls_back_to_next_best_flight(state):
    state.chaos = True
    agent.run_trigger(state, "flight_delay")
    reply = agent.handle(state, "rahul", "yes")
    assert ("rebook_flight", "error") in tools(state)
    assert trip(state)["flight"] == "AI-502" and trip(state)["status"] == "REBOOKED"
    assert "seat hold failed" in reply


def test_family_trip_books_four_passengers_on_comfortable_flight(state):
    reply = agent.handle(state, "priya", "book flights for all of us to Goa on 26 Dec")
    t = trip(state, "trip-2")
    assert t["member_ids"] == ["priya", "rahul", "aarav", "dadi"]
    assert t["flight"] == "AI-544" and t["fare_total"] == 20400 and t["status"] == "BOOKED"  # 09:00, not a 07:10 wake-up for Dadi and Aarav
    assert t["seats"]["rahul"].endswith("C") and len(set(t["seats"].values())) == 4
    assert t["cab"]["pickup"] == "07:00" and t["cab"]["pickup_date"] == "2026-12-26"
    event = next(e for e in state.calendar if e["id"] == t["calendar_event_id"])
    assert event["member_ids"] == t["member_ids"] and event["date"] == "2026-12-26" and event["start"] == "09:00"
    assert "20,400" in reply
    assert any(n["kind"] == "travel" for n in state.notifications)
    assert state.domains["travel"]["cabs"][-1]["vehicle"] == "SUV (6-seater)"


def test_family_trip_find_then_confirm(state):
    reply = agent.handle(state, "rahul", "find flights for all of us to Goa on 26 Dec")
    assert "AI-544" in reply and "Aarav and Dadi" in reply and len(state.domains["travel"]["trips"]) == 1
    agent.handle(state, "rahul", "yes")
    assert len(state.domains["travel"]["trips"]) == 2
    hinglish = agent.handle(FamilyState(), "priya", "find flights for all of us to Goa on 26 Dec")
    assert "Aarav aur Dadi" in hinglish and "Book kar doon" in hinglish


def test_family_trip_asks_for_missing_date_then_books(state):
    reply = agent.handle(state, "rahul", "book flights for all of us to Goa")
    assert "date" in reply.lower() and state.pending["kind"] == "await_details"
    agent.handle(state, "rahul", "26 December")
    assert trip(state, "trip-2")["flight"] == "AI-544" and state.pending is None


def test_no_flights_for_that_date(state):
    reply = agent.handle(state, "rahul", "book flights for all of us to Goa on 1 Jan")
    assert "couldn't find" in reply and len(state.domains["travel"]["trips"]) == 1
    assert "nahi mili" in agent.handle(FamilyState(), "priya", "Goa ki flight book karo 1 Jan")
    assert state.pending["kind"] == "flight" and state.pending["flight_id"] is None  # stays open so a new date can be given
    agent.handle(state, "rahul", "make it 26 Dec")
    assert state.pending["flight_id"] == "AI-544"


def test_cab_status_and_reschedule(state):
    assert "03:30" in agent.handle(state, "rahul", "when is my cab coming for the airport")
    reply = agent.handle(state, "rahul", "move my airport cab to 4 am")
    assert trip(state)["cab"]["pickup"] == "04:00" and "04:00" in reply


def test_adhoc_cab_asks_time_then_books(state):
    reply = agent.handle(state, "priya", "book a cab for Dadi to the clinic")
    assert "What time" in reply or "kitne baje" in reply.lower()
    agent.handle(state, "priya", "at 10 am")
    cab = state.domains["travel"]["cabs"][-1]
    assert cab["pickup"] == "10:00" and cab["member_ids"] == ["dadi"]


def test_flight_status(state):
    reply = agent.handle(state, "rahul", "what is my flight status")
    assert "6E-2045" in reply and "K7QX2M" in reply


def test_score_claims_travel_not_other_domains(state):
    assert agent.score(state, "my flight is delayed") >= 3
    assert agent.score(state, "find a cab to the airport") >= 3
    assert agent.score(state, "plan a trip to Goa") >= 3
    for text in ("book a table for Sunday lunch", "Dadi's medicine", "Aarav got 42 out of 50", "when is everyone free", "meet my daughter Anaya"):
        assert agent.score(state, text) == 0, text
    assert agent.score(state, "book a cab for Dadi to the doctor") < 3


def test_tool_schemas_are_complete_json_schema(state):
    assert len({t.name for t in agent.tools}) == len(agent.tools) == 9
    for t in agent.tools:
        assert t.parameters["type"] == "object" and "properties" in t.parameters and t.description
        assert set(t.parameters.get("required", [])) <= set(t.parameters["properties"])
    assert [t.name for t in agent.tools if t.stage == "after"] == ["notify_family"]


def test_tool_errors_are_recoverable(state):
    status, res = agent.call(state, "rebook_flight", trip_id="trip-99", flight_id="6E-6107")
    assert status == "error" and "no trip" in res["error"]
    status, _ = agent.call(state, "book_flight", flight_id="NOPE", member_ids=["rahul"])
    assert status == "error"
    with pytest.raises(ToolError):
        agent.tool("book_cab").fn(state)
