import pytest
from fastapi.testclient import TestClient

from app import impact, orchestrator
from app.main import STATE, app
from app.state import FamilyState


def kinds(result) -> dict:
    return {k["key"]: (k["count"], k["minutes_saved"]) for k in result["by_kind"]}


def test_an_empty_household_has_zero_impact_and_still_explains_itself():
    result = impact.compute(FamilyState(demo=False))
    assert result["actions"] == 0 and result["minutes_saved"] == 0 and result["by_kind"] == []
    assert result["alerts"] == 0 and result["notifications"] == 0
    assert isinstance(result["assumptions"], list) and result["assumptions"]
    assert "Booking a restaurant table: about 15 min saved" in result["assumptions"]
    assert result["money"] is not None and result["money"]["month_total"] == 0


def test_a_booked_lunch_is_counted_once_per_real_action():
    state = FamilyState()
    orchestrator.converse(state, "priya", "Sunday ko sab saath bahar jaana hai")
    orchestrator.converse(state, "priya", "haan book kar do")
    result = impact.compute(state)
    # book_table 15 + cab 8 (bookings), calendar event 5, family notification 2; the restaurant search is a lookup
    assert kinds(result) == {"bookings": (2, 23), "calendar": (1, 5), "family": (1, 2)}
    assert result["actions"] == 4 and result["minutes_saved"] == 30


def test_failed_calls_and_unknown_tools_do_not_count():
    state = FamilyState(demo=False)
    state.log("dining", "book_table", {}, "error", {"error": "slot taken"}, 1)
    state.log("dining", "search_restaurants", {}, "ok", {}, 1)
    state.log("orchestrator", "load_member_context", {}, "ok", {}, 1)
    state.log("dining", "book_table", {}, "ok", {}, 1)
    result = impact.compute(state)
    assert result["actions"] == 1 and kinds(result) == {"bookings": (1, 15)}


def test_the_same_event_is_never_counted_twice():
    state = FamilyState(demo=False)
    state.log("travel", "rebook_flight", {}, "ok", {}, 1)
    state.events.append(dict(state.events[0]))  # a duplicated log line with the same id
    assert impact.compute(state)["actions"] == 1
    assert impact.compute(state) == impact.compute(state)


def test_every_documented_estimate_is_applied():
    expected = {
        ("dining", "book_table"): 15, ("travel", "rebook_flight"): 25, ("travel", "book_cab"): 8,
        ("calendar", "find_family_slots"): 10, ("calendar", "create_event"): 5, ("care", "order_refill"): 12,
        ("care", "book_appointment"): 20, ("school", "log_marks"): 3, ("school", "record_arrival"): 3,
        ("dining", "notify_family"): 2, ("money", "log_expense"): 2, ("money", "get_spending_summary"): 5,
        ("money", "suggest_savings"): 5,
    }
    for (agent, tool), minutes in expected.items():
        state = FamilyState(demo=False)
        state.log(agent, tool, {}, "ok", {}, 1)
        assert impact.compute(state)["minutes_saved"] == minutes, (agent, tool)


def test_a_renamed_money_tool_still_counts_by_what_it_does():
    state = FamilyState(demo=False)
    state.log("money", "record_expense_entry", {}, "ok", {}, 1)
    state.log("money", "anything_else", {}, "ok", {}, 1)
    result = impact.compute(state)
    assert kinds(result) == {"money": (2, 5)}


def test_alerts_count_urgent_family_messages():
    state = FamilyState()
    state.notify(["rahul"], "Aarav reached school at 07:52.", "school", "school")
    assert impact.compute(state)["alerts"] == 0
    from app.agents.care import CareAgent

    CareAgent().run_trigger(state, "missed_checkin")
    result = impact.compute(state)
    assert result["alerts"] >= 1 and result["notifications"] == len(state.notifications)
    state.notify(["priya"], "Eating out is over budget this month.", "money", "money")
    assert impact.compute(state)["alerts"] == result["alerts"] + 1


def test_money_comes_from_the_money_agents_overview():
    state = FamilyState()
    money = impact.compute(state)["money"]
    assert set(money) == {"currency", "month_total", "budget_total", "budget_left", "potential_savings", "top_tip"}
    assert money["month_total"] > 0 and money["budget_total"]


def test_a_broken_money_overview_never_breaks_the_impact_page(monkeypatch):
    import app.agents.money as money_module

    monkeypatch.setattr(money_module, "overview", lambda state: 1 / 0)
    assert impact.compute(FamilyState())["money"] is None


def test_the_impact_endpoint_matches_the_calculation():
    STATE.reset(demo=True)
    client = TestClient(app)
    client.post("/api/converse", json={"member_id": "priya", "message": "Sunday ko sab saath bahar jaana hai"})
    client.post("/api/converse", json={"member_id": "priya", "message": "haan book kar do"})
    body = client.get("/api/impact").json()
    assert body == impact.compute(STATE) and body["actions"] == 4 and body["minutes_saved"] == 30
    assert set(body) == {"actions", "minutes_saved", "by_kind", "alerts", "notifications", "money", "assumptions"}
    assert all(set(k) == {"key", "label", "count", "minutes_saved"} for k in body["by_kind"])
    STATE.reset(demo=False)
