import pytest

from app import orchestrator
from app.agents.care import CareAgent
from app.state import FamilyState


@pytest.fixture(autouse=True)
def fast_mock(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agent():
    return CareAgent()


def care(state):
    return state.domains["care"]


def test_score_is_sharp(state, agent):
    assert agent.score(state, "Dadi's medicine status") >= 3
    assert agent.score(state, "meri dawai khatam ho rahi hai") >= 3
    assert agent.score(state, "book Dadi's doctor appointment for Thursday at 11") >= 6
    assert agent.score(state, "what do you know about Dadi") == 0
    assert agent.score(state, "remember Dadi takes medicine at 8") == 0
    assert agent.score(state, "Dadi") == 0
    assert agent.score(state, "book a table for Sunday lunch") == 0
    assert agent.score(state, "when is everyone free on Sunday") == 0


def test_dadi_took_medicine_logs_due_doses(state, agent):
    reply = agent.handle(state, "dadi", "dawai le li")
    assert "Metformin" in reply and "Amlodipine" in reply and "Shukriya" in reply
    today = state.now["date"]
    for med in care(state)["seniors"]["dadi"]["meds"]:
        assert f"{today} 08:30" in med["taken"]
        assert f"{today} 20:30" not in med["taken"]
    again = agent.handle(state, "dadi", "dawai le li")
    assert "pehle se likhi" in again


def test_parent_summary_after_dose(state, agent):
    agent.handle(state, "dadi", "dawai le li")
    reply = agent.handle(state, "priya", "did Dadi take her medicines?")
    assert "2 of 3 doses" in reply or "3 mein se 2" in reply
    assert "Metformin is down to 2 days" in reply or "Metformin sirf 2 din" in reply


def test_summary_counts_missed_doses(state, agent):
    state.now["time"] = "21:00"
    reply = agent.handle(state, "rahul", "how is Dadi today")
    assert "0 of 3" in reply and "2 missed" in reply


def test_refill_orders_lowest_stock_and_notifies_family(state, agent):
    reply = agent.handle(state, "dadi", "meri dawai khatam ho rahi hai")
    assert "Metformin" in reply and "kal" in reply
    med = care(state)["seniors"]["dadi"]["meds"][0]
    assert med["stock_days"] == 32
    order = care(state)["orders"][0]
    assert order["med"] == "Metformin" and order["pharmacy"] == "MedPlus Jayanagar" and order["status"] == "ORDERED"
    note = state.notifications[-1]
    assert note["kind"] == "care" and set(note["to"]) == {"priya", "rahul"} and "Metformin" in note["text"]


def test_refill_falls_back_to_backup_pharmacy_on_supplier_failure(state, agent):
    state.chaos = True
    reply = agent.handle(state, "rahul", "order Dadi's metformin refill")
    assert "backup" in reply
    statuses = [(e["tool"], e["status"]) for e in state.events]
    assert statuses == [("order_refill", "error"), ("order_refill", "ok")]
    assert care(state)["orders"][0]["pharmacy"] == "Apollo Pharmacy Jayanagar"


def test_unwell_records_concern_and_asks_parents_to_call(state, agent):
    reply = agent.handle(state, "dadi", "mujhe thoda chakkar aa raha hai")
    assert "Rahul aur Priya" in reply and reply.endswith("?")
    checkin = care(state)["checkins"][-1]
    assert checkin["mood"] == "unwell" and care(state)["seniors"]["dadi"]["last_checkin"]["mood"] == "unwell"
    note = state.notifications[-1]
    assert "Please call her" in note["text"] and set(note["to"]) == {"priya", "rahul"}


def test_chest_pain_is_urgent(state, agent):
    reply = agent.handle(state, "dadi", "mere seene mein dard hai, saans nahi aa rahi")
    assert "112" in reply
    assert state.notifications[-1]["text"].startswith("URGENT")


def test_parent_reports_concern(state, agent):
    reply = agent.handle(state, "rahul", "Dadi says she feels dizzy")
    assert "call Dadi now" in reply and care(state)["checkins"][-1]["mood"] == "unwell"


def test_book_appointment_adds_event_cab_escort_and_notifies(state, agent):
    reply = agent.handle(state, "rahul", "book Dadi's doctor appointment for Thursday at 11")
    assert "Thursday 26 Nov" in reply and "11:00" in reply and "Priya will take her" in reply
    appt = care(state)["appointments"][0]
    assert (appt["date"], appt["time"], appt["escort"]) == ("2026-11-26", "11:00", "priya")
    assert appt["cab"]["pickup"] == "10:15"
    event = next(e for e in state.calendar if e["id"] == appt["event_id"])
    assert event["member_ids"] == ["dadi", "priya"] and event["kind"] == "health"
    assert care(state)["seniors"]["dadi"]["doctor"]["next_appointment"] == {"date": "2026-11-26", "time": "11:00"}
    assert "Cab CAB-9001" in state.notifications[-1]["text"]
    assert state.pending is None


def test_escort_skips_parent_with_a_clash(state, agent):
    reply = agent.handle(state, "rahul", "book Dadi's doctor appointment on Monday at 10:00")
    assert "Rahul will take her" in reply
    assert care(state)["appointments"][0]["escort"] == "rahul"


def test_appointment_asks_for_missing_day_then_books(state, agent):
    first = orchestrator.converse(state, "rahul", "book a doctor appointment for Dadi")
    assert "Which day" in first and state.pending["agent"] == "care"
    second = orchestrator.converse(state, "rahul", "Thursday at 11")
    # orchestrator replies for English speakers are TTS-friendly: "Thursday the twenty sixth", not "Thursday 26 Nov"
    assert "Thursday the twenty sixth" in second and state.pending is None
    assert len(care(state)["appointments"]) == 1


def test_appointment_clash_offers_another_time(state, agent):
    reply = agent.handle(state, "rahul", "book Dadi's doctor appointment on Sunday at 17:30")
    assert "Satsang" in reply and "Which other time" in reply
    assert state.pending["time"] is None and state.pending["date"] == "2026-11-22"
    assert care(state)["appointments"] == []
    done = agent.handle(state, "rahul", "make it 3 pm")
    assert "Sunday 22 Nov" in done and care(state)["appointments"][0]["time"] == "15:00"


def test_cancel_pending_appointment(state, agent):
    agent.handle(state, "rahul", "book a doctor appointment for Dadi")
    reply = agent.handle(state, "rahul", "never mind")
    assert "leave the appointment" in reply and state.pending is None


def test_next_appointment_question(state, agent):
    reply = agent.handle(state, "rahul", "when is Dadi's next doctor appointment")
    assert "Friday 27 Nov at 11:00" in reply


def test_trigger_morning_checkin(state, agent):
    reply = agent.run_trigger(state, "morning_checkin")
    assert "check-in" in reply and state.now["time"] == "09:00"
    senior = care(state)["seniors"]["dadi"]
    assert senior["last_checkin"] == {"date": "2026-11-20", "at": "09:00", "mood": "good"}
    assert all(f"{state.now['date']} 08:30" in m["taken"] for m in senior["meds"])
    assert [t["role"] for t in state.transcript] == ["agent", "user", "agent"]
    assert "Namaste Dadi" in state.transcript[0]["text"]


def test_trigger_missed_checkin_escalates_to_both_parents(state, agent):
    state.now["time"] = "09:00"
    reply = agent.run_trigger(state, "missed_checkin")
    assert "did not answer two" in reply and state.now["time"] == "18:10"
    assert [c["mood"] for c in care(state)["checkins"]] == ["no_response", "no_response"]
    note = state.notifications[-1]
    assert note["text"].startswith("URGENT") and set(note["to"]) == {"rahul", "priya"}
    assert "2 medicine dose(s)" in note["text"] and "2 tries" in note["text"]
    assert state.events[-1]["tool"] == "escalate_missed_checkin" and state.stage == "after"


def test_trigger_low_stock_notifies_only_priya(state, agent):
    reply = agent.run_trigger(state, "low_stock")
    assert "Priya" in reply and "down to 2 days" in reply
    assert state.notifications[-1]["to"] == ["priya"]
    assert care(state)["seniors"]["dadi"]["meds"][0]["stock_days"] == 32


def test_triggers_are_registered_with_labels(agent):
    assert {t.name: t.label for t in agent.triggers} == {
        "morning_checkin": "Dadi morning check-in",
        "missed_checkin": "Dadi misses check-in",
        "low_stock": "Medicine running low",
    }


def test_orchestrator_routes_to_care_and_returns_none_for_others(state, agent):
    reply = orchestrator.converse(state, "dadi", "meri dawai le li")
    assert "likh li" in reply
    assert state.transcript[-1]["agent"] == "care"
    assert agent.handle(state, "priya", "book a table for Sunday lunch") is None


def test_tool_schemas_are_complete(agent):
    names = {t.name for t in agent.tools}
    assert names == {"log_medicine_taken", "record_checkin", "escalate_missed_checkin", "order_refill", "book_appointment", "add_medicine", "get_care_summary"}
    for t in agent.tools:
        assert t.parameters["type"] == "object" and t.parameters["required"] and t.description
    assert agent.tool("escalate_missed_checkin").stage == "after"
