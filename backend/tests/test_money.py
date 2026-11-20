"""Money agent: logging, questions, budgets, savings tips, deletion, routing, tools and triggers (english mode)."""

from datetime import date, timedelta

import pytest

from app import orchestrator
from app.agents import BY_NAME
from app.agents import money as M
from app.state import FamilyState
from app.toolkit import ToolError, run_tool


@pytest.fixture(autouse=True)
def english(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")


@pytest.fixture
def state():
    return FamilyState()  # demo ledger, 2026-11-20


@pytest.fixture
def blank():
    s = FamilyState()
    s.domains["money"] = {"expenses": [], "budgets": {}, "currency": "INR"}
    return s


def ask(s, member, text):
    orchestrator.converse(s, member, text)
    last = s.transcript[-1]
    return last["agent"], last["text"]


def ledger(s):
    return s.domains["money"]["expenses"]


def total(s, start="2026-11-01", end="2026-11-20", member=None, category=None):
    return sum(
        e["amount"] for e in ledger(s)
        if start <= e["date"] <= end and (member is None or e["member_id"] == member) and (category is None or e["category"] == category)
    )


# ---------------------------------------------------------------- logging an expense

LOG_CASES = [
    ("priya", "I spent 450 on groceries", 450, "groceries"),
    ("priya", "i spent four hundred and fifty on groceries", 450, "groceries"),
    ("priya", "um I spent 450 rupees on groceries please", 450, "groceries"),
    ("rahul", "add an expense of 1200 for the electricity bill", 1200, "bills"),
    ("rahul", "add an expense of twelve hundred for the electricity bill", 1200, "bills"),
    ("rahul", "paid three hundred for Aarav's cricket yesterday", 300, "entertainment"),
    ("priya", "spent 2000 at the restaurant", 2000, "eating out"),
    ("priya", "we spent 2,500 on dinner last night", 2500, "eating out"),
    ("rahul", "I paid 1.2k for petrol", 1200, "transport"),
    ("rahul", "paid rs 800 for the doctor", 800, "health"),
    ("dadi", "I spent 300 on medicines", 300, "health"),
    ("priya", "log 600 for vegetables", 600, "groceries"),
    ("priya", "record an expense of 5000 for school fees", 5000, "education"),
    ("priya", "paid 1500 for the school fees", 1500, "education"),
    ("priya", "spent 3500 on shoes for Aarav", 3500, "shopping"),
    ("rahul", "I spent 900 on a cab", 900, "transport"),
    ("rahul", "spent 180 on an auto", 180, "transport"),
    ("rahul", "I spent 12000 on flights to Goa", 12000, "travel"),
    ("priya", "paid 650 for the hotel", 650, "travel"),
    ("priya", "I spent 999 on internet", 999, "bills"),
    ("priya", "paid 599 for the phone recharge", 599, "bills"),
    ("rahul", "spent 960 on movie tickets", 960, "entertainment"),
    ("rahul", "I paid 649 for netflix", 649, "entertainment"),
    ("priya", "spent 1400 on clothes", 1400, "shopping"),
    ("priya", "i spent 2 lakh on furniture", 200000, "shopping"),
    ("priya", "spent 1k on snacks", 1000, "eating out"),
    ("priya", "I spent 75 on milk", 75, "groceries"),
    ("rahul", "paid 2200 for fuel", 2200, "transport"),
    ("rahul", "I spent 520 on parking", 520, "transport"),
    ("priya", "paid 3000 for tuition", 3000, "education"),
    ("priya", "spent 200 on stationery", 200, "education"),
    ("rahul", "I spent 700 on a gift", 700, "shopping"),
    ("priya", "spent 800 on coffee", 800, "eating out"),
    ("priya", "I spent 1800 on a pizza", 1800, "eating out"),
    ("priya", "paid 320 for swiggy", 320, "eating out"),
    ("priya", "spent 440 on pharmacy", 440, "health"),
    ("rahul", "paid 1100 for the dentist", 1100, "health"),
    ("priya", "I paid 8000 for the rent", 8000, "bills"),
    ("rahul", "spent 450 at the supermarket", 450, "groceries"),
    ("priya", "add expense 250 for fruits", 250, "groceries"),
    ("priya", "note down 400 spent on groceries", 400, "groceries"),
    ("priya", "I spent rs 150 on ice cream", 150, "eating out"),
    ("rahul", "spent ₹2,750 on electricity", 2750, "bills"),
    ("dadi", "spent 500 on a donation", 500, "other"),
    ("priya", "I spent 60 thousand on a trip", 60000, "travel"),
]


@pytest.mark.parametrize("member, text, amount, category", LOG_CASES)
def test_logging_an_expense(blank, member, text, amount, category):
    agent, reply = ask(blank, member, text)
    assert agent == "money", reply
    assert len(ledger(blank)) == 1
    e = ledger(blank)[0]
    assert e["amount"] == amount and e["category"] == category and e["member_id"] == member
    assert e["date"] in ("2026-11-20", "2026-11-19")
    assert "Logged" in reply


def test_yesterday_and_last_night_set_the_date(blank):
    ask(blank, "rahul", "paid three hundred for Aarav's cricket yesterday")
    ask(blank, "priya", "we spent 2,500 on dinner last night")
    assert [e["date"] for e in ledger(blank)] == ["2026-11-19", "2026-11-19"]


def test_a_named_payer_is_recorded(blank):
    ask(blank, "priya", "Rahul spent 500 on petrol")
    assert ledger(blank)[0]["member_id"] == "rahul"


def test_budget_context_is_added_to_the_confirmation(state):
    _, reply = ask(state, "priya", "I spent 2000 on groceries")
    assert "budget" in reply and "14,000" in reply


def test_over_budget_is_called_out(state):
    _, reply = ask(state, "priya", "spent 2000 at the restaurant")
    assert "over the Rs 6,000 budget" in reply


# ---------------------------------------------------------------- the missing-category follow-up

def test_missing_category_asks_once_then_logs(blank):
    agent, reply = ask(blank, "priya", "I spent 450")
    assert agent == "money" and "Which category" in reply and blank.pending["agent"] == "money"
    agent, reply = ask(blank, "priya", "groceries")
    assert agent == "money" and blank.pending is None
    assert (ledger(blank)[0]["amount"], ledger(blank)[0]["category"]) == (450, "groceries")


def test_missing_category_answer_eating_out_is_not_stolen_by_dining(blank):
    ask(blank, "priya", "I paid 900")
    agent, _ = ask(blank, "priya", "eating out")
    assert agent == "money" and ledger(blank)[0]["category"] == "eating out"


def test_missing_category_can_be_cancelled(blank):
    ask(blank, "priya", "I spent 450")
    _, reply = ask(blank, "priya", "never mind")
    assert blank.pending is None and not ledger(blank) and "won't record" in reply


def test_moving_on_drops_the_question(blank):
    ask(blank, "priya", "I spent 450")
    agent, _ = ask(blank, "priya", "who is in the family")
    assert agent == "household" and blank.pending is None and not ledger(blank)


def test_adding_an_expense_without_an_amount_asks_for_it(blank):
    agent, reply = ask(blank, "priya", "add an expense")
    assert agent == "money" and "How much" in reply


# ---------------------------------------------------------------- questions about spending

def test_month_total(state):
    agent, reply = ask(state, "priya", "how much did we spend this month")
    assert agent == "money" and f"{total(state):,}" in reply and "the family" in reply.lower()


def test_my_spending_uses_the_speaker(state):
    _, reply = ask(state, "priya", "how much did I spend on eating out")
    assert f"{total(state, member='priya', category='eating out'):,}" in reply and reply.startswith("You")


def test_named_member_spending(state):
    _, reply = ask(state, "rahul", "how much did Priya spend this month")
    assert f"{total(state, member='priya'):,}" in reply and "Priya" in reply


def test_category_total_and_budget_context(state):
    _, reply = ask(state, "priya", "how much did we spend on eating out")
    assert f"{total(state, category='eating out'):,}" in reply


def test_last_month_total(state):
    _, reply = ask(state, "priya", "how much did we spend last month")
    assert f"{total(state, '2026-10-01', '2026-10-31'):,}" in reply


def test_this_week_total(state):
    _, reply = ask(state, "priya", "how much did we spend this week")
    assert f"{total(state, '2026-11-16', '2026-11-20'):,}" in reply


def test_last_week_total(state):
    _, reply = ask(state, "priya", "how much did we spend last week")
    assert f"{total(state, '2026-11-09', '2026-11-15'):,}" in reply


def test_today_with_nothing_logged_says_so(state):
    agent, reply = ask(state, "priya", "how much did we spend today")
    assert agent == "money" and "haven't recorded any spending" in reply


def test_so_far_covers_the_whole_ledger(state):
    _, reply = ask(state, "priya", "how much have we spent in total")
    assert f"{total(state, '2000-01-01', '2026-12-31'):,}" in reply


def test_biggest_expense(state):
    agent, reply = ask(state, "priya", "what is our biggest expense")
    assert agent == "money" and "groceries" in reply and "largest single expense" in reply


def test_where_did_the_money_go(state):
    agent, reply = ask(state, "priya", "where did the money go this month")
    assert agent == "money" and "groceries" in reply


def test_list_recent_expenses(state):
    agent, reply = ask(state, "priya", "show me my recent expenses")
    assert agent == "money" and "latest expenses" in reply


def test_comparison_with_a_partial_last_month_is_not_claimed(state):
    _, reply = ask(state, "priya", "how much did we spend this month")
    assert "previous period" not in reply  # October has only half a month of data


SUMMARY_PHRASES = [
    ("priya", "how much did we spend this month"),
    ("rahul", "how much have we spent this month"),
    ("priya", "how much are we spending"),
    ("rahul", "what is our total spending this month"),
    ("priya", "give me a spending summary"),
    ("priya", "are we spending too much"),
    ("rahul", "how much did we spend on groceries"),
    ("rahul", "how much did we spend on medicines"),
    ("priya", "how much did we spend on entertainment this month"),
    ("rahul", "how much did the family spend on petrol"),
    ("priya", "how much did Rahul spend on petrol"),
    ("priya", "how much did Aarav spend"),
    ("rahul", "um could you tell me how much we spent this month"),
    ("priya", "hey Aangan how much have we spent on shopping"),
    ("dadi", "how much did I spend on medicines"),
    ("priya", "how much did we spend on bills"),
    ("priya", "tell me our expenses this month"),
    ("priya", "what was our spending last month"),
]


@pytest.mark.parametrize("member, text", SUMMARY_PHRASES)
def test_spending_questions_reach_money(state, member, text):
    agent, reply = ask(state, member, text)
    assert agent == "money", reply
    assert reply and "I can help with" not in reply


# ---------------------------------------------------------------- budgets

def test_set_total_budget(blank):
    _, reply = ask(blank, "priya", "set a monthly budget of sixty thousand")
    assert blank.domains["money"]["budgets"]["total"] == 60000 and "60,000" in reply


BUDGET_SET_CASES = [
    ("set the grocery budget to eight thousand", "groceries", 8000),
    ("make the monthly budget 50k", "total", 50000),
    ("change the eating out budget to 5000", "eating out", 5000),
    ("update the transport budget to 7000", "transport", 7000),
    ("put a budget of 3000 on entertainment", "entertainment", 3000),
    ("set shopping budget 4500", "shopping", 4500),
    ("set a budget of 45000 for the month", "total", 45000),
    ("I want to set a health budget of 2500", "health", 2500),
    ("raise the groceries budget to 16000", "groceries", 16000),
    ("set our total budget to 70000", "total", 70000),
    ("set the bills budget to nine thousand", "bills", 9000),
    ("lower the monthly budget to fifty five thousand", "total", 55000),
]


@pytest.mark.parametrize("text, key, amount", BUDGET_SET_CASES)
def test_budget_set(blank, text, key, amount):
    agent, reply = ask(blank, "priya", text)
    assert agent == "money", reply
    assert blank.domains["money"]["budgets"][key] == amount


def test_budget_set_reports_what_is_left(state):
    _, reply = ask(state, "priya", "set the monthly budget to 50000")
    assert "left" in reply and "50,000" in reply


BUDGET_STATUS_PHRASES = [
    "am I over budget", "are we over budget", "how is our budget", "how much budget is left",
    "are we within budget", "what is left in the budget", "what's our budget status", "is the eating out budget exceeded",
    "how are we doing against the budget", "have we crossed the budget",
]


@pytest.mark.parametrize("text", BUDGET_STATUS_PHRASES)
def test_budget_status_phrases(state, text):
    agent, reply = ask(state, "priya", text)
    assert agent == "money", reply
    assert "budget" in reply.lower()


def test_budget_status_names_the_over_budget_category(state):
    _, reply = ask(state, "priya", "am I over budget")
    assert "eating out by Rs 2,120" in reply and "Rs 18,294 is left" in reply


def test_budget_status_with_no_budget_explains(blank):
    _, reply = ask(blank, "priya", "am I over budget")
    assert "haven't set a budget" in reply


def test_restaurant_search_within_budget_is_dining_not_money(state):
    agent, _ = ask(state, "priya", "find a restaurant within our budget for sunday lunch")
    assert agent == "dining"


# ---------------------------------------------------------------- saving tips

SAVINGS_PHRASES = [
    "how can we save money", "where can we cut costs", "give me some tips to save money", "how do we reduce spending",
    "can we spend less", "any savings ideas", "how can I save more", "suggest ways to save money", "where are we overspending",
    "how can we cut down on expenses",
]


@pytest.mark.parametrize("text", SAVINGS_PHRASES)
def test_savings_questions_get_grounded_tips(state, text):
    agent, reply = ask(state, "priya", text)
    assert agent == "money", reply
    assert "Eating out" in reply and "8,120" in reply and "6,000" in reply and "2,120" in reply


def test_savings_with_too_little_data_says_so(blank):
    _, reply = ask(blank, "priya", "how can we save money")
    assert "don't have enough spending" in reply


def test_savings_when_everything_is_fine(blank):
    s = blank
    for i, (cat, amt) in enumerate([("groceries", 900), ("bills", 700), ("transport", 500), ("health", 400)]):
        run_tool(s, "money", BY_NAME["money"].tool("log_expense"), {"member_id": "priya", "amount": amt, "category": cat})
    s.domains["money"]["budgets"] = {"groceries": 5000, "bills": 5000}
    _, reply = ask(s, "priya", "how can we save money")
    assert "balanced" in reply


def seed_ledger(s, rows):
    s.domains["money"] = {"expenses": [], "budgets": {}, "currency": "INR"}
    for i, (d, cat, amt) in enumerate(rows, start=1):
        s.domains["money"]["expenses"].append(
            {"id": f"exp-{i}", "member_id": "priya", "amount": amt, "category": cat, "note": "", "date": d, "source": "test"}
        )


def test_a_category_over_30_percent_is_flagged_without_a_budget(blank):
    seed_ledger(blank, [("2026-11-02", "shopping", 6000), ("2026-11-03", "groceries", 2000), ("2026-11-04", "bills", 2000)])
    ideas = M.savings_ideas(blank)
    assert ideas[0]["category"] == "shopping" and "60%" in ideas[0]["text"] and ideas[0]["saving"] == 900


def test_a_jump_versus_a_fully_tracked_last_month_is_flagged(blank):
    rows = [("2026-10-01", "groceries", 100)]
    rows += [("2026-10-10", "transport", 2000), ("2026-10-20", "bills", 3000), ("2026-10-25", "health", 4000)]
    rows += [("2026-11-03", "transport", 3500), ("2026-11-05", "bills", 3000), ("2026-11-07", "health", 4000)]
    seed_ledger(blank, rows)
    ideas = {i["category"]: i for i in M.savings_ideas(blank)}
    assert "up 75% on last month" in ideas["transport"]["text"] and ideas["transport"]["saving"] == 1500


def test_many_small_purchases_are_flagged(blank):
    rows = [(f"2026-11-0{d}", "eating out", 250) for d in range(1, 7)] + [("2026-11-08", "bills", 9000), ("2026-11-09", "groceries", 9000)]
    seed_ledger(blank, rows)
    ideas = {i["category"]: i for i in M.savings_ideas(blank)}
    assert "6 small eating out purchases" in ideas["eating out"]["text"] and ideas["eating out"]["saving"] == 300


def test_comparisons_are_skipped_when_last_month_is_only_partly_tracked(state):
    assert M.overview(state)["last_month_partial"] is True
    assert all("last month" not in i["text"] for i in M.savings_ideas(state))


# ---------------------------------------------------------------- deleting

DELETE_PHRASES = [
    "delete the last expense", "remove the last expense", "undo the last expense", "delete my last entry",
    "remove the previous expense", "undo that expense",
]


@pytest.mark.parametrize("text", DELETE_PHRASES)
def test_delete_the_last_expense(blank, text):
    ask(blank, "priya", "I spent 450 on groceries")
    ask(blank, "priya", "I spent 120 on milk")
    agent, reply = ask(blank, "priya", text)
    assert agent == "money" and "Deleted" in reply
    assert [e["amount"] for e in ledger(blank)] == [450]


def test_delete_with_nothing_logged(blank):
    _, reply = ask(blank, "priya", "delete the last expense")
    assert "nothing to delete" in reply


def test_delete_then_summary_reflects_it(blank):
    ask(blank, "priya", "I spent 450 on groceries")
    ask(blank, "priya", "I spent 120 on milk")
    ask(blank, "priya", "delete the last expense")
    _, reply = ask(blank, "priya", "how much did we spend this month")
    assert "450" in reply and "120" not in reply


# ---------------------------------------------------------------- empty ledger and children

def test_empty_ledger_answers(blank):
    for text in ["how much did we spend this month", "what is our biggest expense", "show my expenses"]:
        agent, reply = ask(blank, "priya", text)
        assert agent == "money" and "haven't recorded any spending" in reply


def test_a_large_child_spend_notifies_the_parents(blank):
    _, reply = ask(blank, "aarav", "I spent 800 on shopping")
    assert reply.endswith("I've told your parents.")
    note = blank.notifications[-1]
    assert note["kind"] == "money" and set(note["to"]) == {"priya", "rahul"} and "Aarav" in note["text"]


def test_a_small_child_spend_does_not_notify(blank):
    ask(blank, "aarav", "I spent 80 on ice cream")
    assert blank.notifications == [] and ledger(blank)[0]["category"] == "eating out"


def test_overview_on_an_empty_ledger_is_safe(blank):
    o = M.overview(blank)
    assert o["month_total"] == 0 and o["by_category"] == {} and o["budget_total"] is None and o["budget_left"] is None
    assert o["potential_savings"] == 0 and o["top_tip"] is None


def test_overview_on_the_demo_ledger(state):
    o = M.overview(state)
    assert o["month_total"] == total(state) and o["budget_total"] == 60000 and o["budget_left"] == 60000 - o["month_total"]
    assert o["by_category"]["eating out"] == 8120 and o["potential_savings"] >= 2120 and "Eating out" in o["top_tip"]


def test_demo_seed_shape(state):
    rows = ledger(state)
    assert 40 <= len(rows) <= 50
    assert min(e["date"] for e in rows) >= "2026-10-15" and max(e["date"] for e in rows) <= "2026-11-19"
    assert {e["category"] for e in rows} == set(M.CATEGORIES)
    assert BY_NAME["money"].family_keys == ("expenses", "budgets")


# ---------------------------------------------------------------- tools

def tool(name):
    return BY_NAME["money"].tool(name)


def test_tool_validation(blank):
    with pytest.raises(ToolError):
        M.log_expense(blank, "priya", 0, "groceries")
    with pytest.raises(ToolError):
        M.log_expense(blank, "priya", -5, "groceries")
    with pytest.raises(ToolError):
        M.log_expense(blank, "priya", 100, "spaceships")
    with pytest.raises(ToolError):
        M.log_expense(blank, "priya", 100, "groceries", date="2026-12-01")
    with pytest.raises(ToolError):
        M.log_expense(blank, "priya", 100, "groceries", date="yesterday")
    with pytest.raises(ToolError):
        M.set_budget(blank, "groceries", 0)
    with pytest.raises(ToolError):
        M.set_budget(blank, "spaceships", 100)
    with pytest.raises(ToolError):
        M.delete_expense(blank, "exp-99")
    with pytest.raises(ToolError):
        M.get_spending_summary(blank, period="decade")


def test_tools_have_schemas_and_log_to_the_money_agent(blank):
    assert {t.name for t in BY_NAME["money"].tools} == {
        "log_expense", "delete_expense", "list_expenses", "get_spending_summary", "set_budget", "get_budget_status", "suggest_savings",
    }
    for t in BY_NAME["money"].tools:
        assert t.parameters["type"] == "object" and t.description
    status, res = run_tool(blank, "money", tool("log_expense"), {"member_id": "rahul", "amount": 300, "category": "petrol"})
    assert status == "ok" and res["expense"]["category"] == "transport"
    assert blank.events[-1]["agent"] == "money" and blank.events[-1]["tool"] == "log_expense"


def test_expense_ids_stay_unique_after_deletes(blank):
    a = M.log_expense(blank, "priya", 100, "groceries")["expense"]["id"]
    b = M.log_expense(blank, "priya", 100, "groceries")["expense"]["id"]
    M.delete_expense(blank, a)
    c = M.log_expense(blank, "priya", 100, "groceries")["expense"]["id"]
    assert len({a, b, c}) == 3


def test_summary_tool_shares_members_and_reliable_comparison(blank):
    seed_ledger(blank, [("2026-10-01", "groceries", 1000), ("2026-10-20", "bills", 1000), ("2026-11-05", "groceries", 1500), ("2026-11-06", "bills", 500)])
    res = M.get_spending_summary(blank, period="month")
    assert res["total"] == 2000 and res["previous_total"] == 2000 and res["comparison_reliable"] and res["change_pct"] == 0
    assert res["by_category"][0] == {"category": "groceries", "amount": 1500, "share_pct": 75}
    assert res["by_member"][0]["member_id"] == "priya"


def test_list_tool_filters_and_orders(state):
    res = M.list_expenses(state, limit=3, category="transport")
    assert len(res["expenses"]) == 3 and res["expenses"][0]["date"] >= res["expenses"][1]["date"]
    assert all(e["category"] == "transport" for e in res["expenses"])


def test_delete_tool_accepts_last(blank):
    M.log_expense(blank, "priya", 100, "groceries")
    M.log_expense(blank, "priya", 200, "bills")
    assert M.delete_expense(blank, "last")["deleted"]["amount"] == 200


# ---------------------------------------------------------------- triggers

def test_monthly_review_trigger_speaks_and_notifies_everyone(state):
    reply = orchestrator.run_trigger(state, "money", "monthly_review")
    assert "41,706" in reply and "groceries" in reply and "Eating out" in reply
    note = state.notifications[-1]
    assert note["kind"] == "money" and set(note["to"]) == {m["id"] for m in state.members}
    assert state.transcript[-1]["agent"] == "money"


def test_budget_alert_trigger_notifies_the_adults_when_over(state):
    reply = orchestrator.run_trigger(state, "money", "budget_alert")
    assert "eating out" in reply and "2,120" in reply
    assert set(state.notifications[-1]["to"]) == {"priya", "rahul"}


def test_budget_alert_is_quiet_when_all_is_well(blank):
    blank.domains["money"]["budgets"] = {"total": 60000}
    reply = orchestrator.run_trigger(blank, "money", "budget_alert")
    assert "within budget" in reply and blank.notifications == []


def test_trigger_labels_are_listed_in_the_snapshot(state):
    money = next(a for a in state.snapshot()["agents"] if a["name"] == "money")
    assert [t["name"] for t in money["triggers"]] == ["monthly_review", "budget_alert"]


# ---------------------------------------------------------------- routing: money must not steal, and must not be stolen from

NOT_MONEY = [
    ("priya", "let's eat out on Sunday", "dining"),
    ("priya", "book a table for lunch on Sunday", "dining"),
    ("priya", "find a restaurant for dinner", "dining"),
    ("priya", "let's all go out for lunch", "dining"),
    ("priya", "plan a family outing for Sunday lunch", "dining"),
    ("priya", "book a table for dinner somewhere cheaper", "dining"),
    ("rahul", "can we eat out on Saturday night", "dining"),
    ("priya", "find a restaurant within our budget for sunday lunch", "dining"),
    ("priya", "refill Dadi's metformin", "care"),
    ("rahul", "did Dadi take her medicines", "care"),
    ("priya", "book Dadi's doctor appointment for Thursday at 11", "care"),
    ("dadi", "my medicine is running low", "care"),
    ("priya", "I need a refill for the BP tablets", "care"),
    ("priya", "how is Aarav doing in school", "school"),
    ("aarav", "I reached school", "school"),
    ("aarav", "I got 42 out of 50 in maths", "school"),
    ("priya", "did Aarav finish his homework", "school"),
    ("rahul", "when is everyone free on Sunday", "calendar"),
    ("rahul", "what is Aarav doing on Monday", "calendar"),
    ("priya", "add a dentist appointment for Aarav on Saturday at 5 pm", "calendar"),
    ("priya", "move the swimming class to 10", "calendar"),
    ("priya", "any clashes this week", "calendar"),
    ("rahul", "my flight is delayed find me an alternative", "travel"),
    ("priya", "book flights for all of us to Goa on 26 December", "travel"),
    ("rahul", "when is my cab coming", "travel"),
    ("rahul", "book a cab to the airport", "travel"),
    ("priya", "who is in the family", "household"),
    ("rahul", "remember that I don't like mushrooms", "household"),
    ("priya", "what do you know about Dadi", "household"),
    ("priya", "meet my daughter Anaya she is 6 and allergic to eggs", "household"),
]


@pytest.mark.parametrize("member, text, expected", NOT_MONEY)
def test_other_agents_keep_their_requests(state, member, text, expected):
    agent, reply = ask(state, member, text)
    assert agent == expected, (agent, reply)


MONEY_BUT_LOOKS_LIKE_ANOTHER_AGENT = [
    ("priya", "I spent 2000 at the restaurant"),
    ("priya", "how much did we spend on eating out"),
    ("priya", "paid 5000 for school fees"),
    ("priya", "I spent 600 at the pharmacy"),
    ("rahul", "how much did we spend on medicines"),
    ("rahul", "paid 900 for a cab"),
    ("rahul", "spent 12000 on flights to Goa"),
    ("priya", "how much did Dadi spend on doctor visits"),
    ("priya", "how much do we spend on dinner"),
    ("priya", "set the eating out budget to 7000"),
    ("priya", "what is our eating out budget"),
    ("priya", "how much did Aarav spend on school things"),
    ("priya", "how much did we spend on flights"),
    ("priya", "how much did the family spend on cabs this month"),
    ("priya", "what did we spend on the restaurant last week"),
    ("priya", "how much have we spent on school fees this month"),
]


@pytest.mark.parametrize("member, text", MONEY_BUT_LOOKS_LIKE_ANOTHER_AGENT)
def test_spending_phrases_with_other_domain_words_reach_money(state, member, text):
    agent, reply = ask(state, member, text)
    assert agent == "money", (agent, reply)


def test_pending_proposal_is_dropped_when_the_user_asks_about_spending(state):
    ask(state, "priya", "let's all go out for lunch on Sunday")
    assert state.pending and state.pending["agent"] == "dining"
    agent, _ = ask(state, "priya", "how much did we spend on eating out this month")
    assert agent == "money" and state.pending is None


def test_confirming_a_lunch_still_books_it(state):
    ask(state, "priya", "let's all go out for lunch on Sunday")
    agent, reply = ask(state, "priya", "yes book it")
    assert agent == "dining" and "Udupi Garden" in reply


def test_replies_read_naturally_aloud(state):
    spoken = orchestrator.converse(state, "priya", "how much did we spend this month")
    assert "Rs" not in spoken and not any(ch.isdigit() for ch in spoken) and "%" not in spoken
    spoken = orchestrator.converse(state, "priya", "how can we save money")
    assert "Rs" not in spoken and not any(ch.isdigit() for ch in spoken)


def test_blank_household_has_no_money_until_logged(blank):
    assert ledger(blank) == []
    ask(blank, "priya", "I spent 450 on groceries")
    assert len(ledger(blank)) == 1
