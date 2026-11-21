"""The Tasks agent: the shared shopping list, tasks assigned to people, the day plan, and how it is reached in conversation."""

import pytest

from app import impact, orchestrator
from app.agents import BY_NAME
from app.agents.tasks import TasksAgent
from app.state import FamilyState
from app.toolkit import ToolError, run_tool


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)


@pytest.fixture
def state():
    return FamilyState()  # the demo family: Priya, Rahul, Aarav and Dadi, on Friday 2026-11-20


@pytest.fixture
def agent():
    return TasksAgent()


def tool(agent, state, name, **args):
    return agent.tool(name).fn(state, **args)


def talk(agent, state, member_id, text):
    state.persona = member_id
    return agent.handle(state, member_id, text)


def notes(state, kind="task"):
    return [n for n in state.notifications if n["kind"] == kind]


# ---- tasks ----


def test_a_task_given_to_someone_else_notifies_them(agent, state):
    state.persona = "priya"
    out = tool(agent, state, "add_task", title="Renew the car insurance", assignee="rahul", due="saturday", priority="high")
    assert out["task"]["assignee"] == "rahul" and out["task"]["due"] == "2026-11-21" and out["task"]["created_by"] == "priya"
    assert out["notified"] == ["rahul"]
    assert notes(state)[-1]["to"] == ["rahul"] and "Renew the car insurance" in notes(state)[-1]["text"]


def test_a_task_for_yourself_or_nobody_notifies_nobody(agent, state):
    state.persona = "priya"
    before = len(state.notifications)
    mine = tool(agent, state, "add_task", title="Water the plants", assignee="priya")
    nobody = tool(agent, state, "add_task", title="Sort the garage")
    assert mine["notified"] == [] and nobody["task"]["assignee"] is None and len(state.notifications) == before


def test_assignees_can_be_named_and_unknown_people_are_refused(agent, state):
    assert tool(agent, state, "add_task", title="A", assignee="Rahul")["task"]["assignee"] == "rahul"
    assert tool(agent, state, "add_task", title="B", assignee="everyone")["task"]["assignee"] == "family"
    with pytest.raises(ToolError, match="not in this family"):
        tool(agent, state, "add_task", title="C", assignee="Zed")
    with pytest.raises(ToolError, match="priority"):
        tool(agent, state, "add_task", title="D", priority="urgent")
    with pytest.raises(ToolError, match="read"):
        tool(agent, state, "add_task", title="E", due="whenever")


def test_the_same_open_task_is_not_added_twice(agent, state):
    first = tool(agent, state, "add_task", title="Pay the electricity bill", assignee="rahul")
    assert first["already_there"] is True and first["task"]["id"] == "t1"


def test_a_task_can_go_into_the_assignees_calendar(agent, state):
    out = tool(agent, state, "add_task", title="Call the school", assignee="priya", due="saturday", time="10:30", add_to_calendar=True)
    event = out["calendar_event"]
    assert event["member_ids"] == ["priya"] and (event["date"], event["start"], event["end"]) == ("2026-11-21", "10:30", "11:00")
    assert any(e["id"] == event["id"] for e in state.calendar)
    with pytest.raises(ToolError, match="needs a day"):
        tool(agent, state, "add_task", title="No day", assignee="priya", add_to_calendar=True)
    with pytest.raises(ToolError, match="one person"):
        tool(agent, state, "add_task", title="No one", due="saturday", add_to_calendar=True)


def test_pending_tasks_come_overdue_first_with_counts(agent, state):
    out = tool(agent, state, "list_tasks")
    assert [t["id"] for t in out["tasks"]][:3] == ["t1", "t2", "t3"] and out["tasks"][0]["overdue"] and out["overdue"] == 1
    assert out["unassigned"] == 1 and out["open_per_person"] == {"Rahul": 2, "Priya": 1, "Nobody yet": 1}
    rahul = tool(agent, state, "list_tasks", assignee="rahul")
    assert [t["id"] for t in rahul["tasks"]] == ["t1", "t3"]
    assert [t["id"] for t in tool(agent, state, "list_tasks", due="saturday")["tasks"]] == ["t1", "t2"]  # due on or before


def test_assigning_a_task_to_someone_notifies_the_new_owner(agent, state):
    state.persona = "priya"
    out = tool(agent, state, "assign_task", task="plumber", assignee="rahul")
    assert out["task"]["assignee"] == "rahul" and out["was"] is None and out["notified"] == ["rahul"]
    again = tool(agent, state, "assign_task", task="t4", assignee="rahul")
    assert again["notified"] == []  # already his
    with pytest.raises(ToolError, match="who"):
        tool(agent, state, "assign_task", task="t4", assignee="")


def test_finishing_a_task_tells_whoever_asked_for_it(agent, state):
    state.persona = "rahul"
    out = tool(agent, state, "complete_task", task="electricity bill")
    assert out["task"]["done"] and out["notified"] == ["priya"] and out["open_tasks_left"] == 3
    assert "Rahul finished" in notes(state)[-1]["text"]
    assert tool(agent, state, "complete_task", task="t1")["already_done"] is True
    assert "t1" not in [t["id"] for t in tool(agent, state, "list_tasks")["tasks"]]
    assert tool(agent, state, "list_tasks", status="done")["count"] == 1


def test_a_vague_task_reference_asks_which_one(agent, state):
    tool(agent, state, "add_task", title="Call the electrician", assignee="rahul")
    with pytest.raises(ToolError, match="more than one task"):
        tool(agent, state, "complete_task", task="call the")
    with pytest.raises(ToolError, match="no task matches"):
        tool(agent, state, "complete_task", task="learn the violin")


# ---- shopping ----


def test_items_go_on_the_list_with_quantities_and_duplicates_are_noticed(agent, state):
    out = tool(agent, state, "add_shopping_items", items=["2 kg rice", "milk", "Bananas"])
    assert out["added"] == ["Rice (2 kg)"] and sorted(out["already_on_the_list"]) == ["Bananas", "Milk"] and out["list"]["open"] == 6
    split = tool(agent, state, "add_shopping_items", items="curd, salt and 1 dozen eggs")
    assert split["added"] == ["Curd", "Salt", "Eggs (1 dozen)"]


def test_a_remembered_diet_or_allergy_is_set_against_what_is_added(agent, state):
    out = tool(agent, state, "add_shopping_items", items=["chicken", "peanut butter", "oats"])
    assert any("Dadi is vegetarian" in w and "chicken" in w for w in out["warnings"])
    assert any("Aarav has a peanut allergy" in w for w in out["warnings"])
    assert not any("oats" in w for w in out["warnings"])
    assert len(out["added"]) == 3  # a warning, not a refusal: someone else in the family may eat it


def test_buying_things_ticks_them_off_and_a_finished_list_says_so(agent, state):
    out = tool(agent, state, "mark_bought", items=["milk", "atta"])
    assert out["bought"] == ["Milk", "Atta"] and out["left"] == ["Paneer", "Bananas", "Tomatoes"] and not out["list_complete"]
    assert tool(agent, state, "mark_bought", items=["saffron"])["not_on_the_list"] == ["saffron"]
    done = tool(agent, state, "mark_bought", items=["paneer", "bananas", "tomatoes"])
    assert done["list_complete"] is True
    assert tool(agent, state, "get_shopping_list")["lists"][0]["open"] == 0
    back = tool(agent, state, "add_shopping_items", items=["milk"])  # needed again: it comes back
    assert back["added"] == ["Milk (2 L)"] and tool(agent, state, "get_shopping_list")["lists"][0]["open"] == 1


def test_items_can_come_off_the_list_unbought(agent, state):
    out = tool(agent, state, "remove_shopping_items", items=["paneer"])
    assert out["removed"] == ["Paneer"] and "Paneer" not in out["left"]


def test_putting_someone_on_the_shopping_makes_an_errand_and_tells_them(agent, state):
    state.persona = "priya"
    out = tool(agent, state, "assign_shopping", assignee="rahul", due="saturday")
    assert out["list"]["assignee"] == "rahul" and out["task"]["title"] == "Shop for Groceries (5 items)" and out["task"]["due"] == "2026-11-21"
    assert out["notified"] == ["rahul"] and "Shop for Groceries" in notes(state)[-1]["text"]
    tool(agent, state, "add_shopping_items", items=["curd"])
    again = tool(agent, state, "assign_shopping", assignee="priya")  # reassigned: still one errand, now with six items
    errands = [t for t in tool(agent, state, "list_tasks")["tasks"] if t["list"]]
    assert len(errands) == 1 and errands[0]["assignee"] == "priya" and errands[0]["title"] == "Shop for Groceries (6 items)" and again["notified"] == []


def test_finishing_the_shopping_errand_marks_the_list_bought(agent, state):
    state.persona = "priya"
    errand = tool(agent, state, "assign_shopping", assignee="rahul")["task"]["id"]
    state.persona = "rahul"
    tool(agent, state, "complete_task", task=errand)
    assert tool(agent, state, "get_shopping_list")["lists"][0]["open"] == 0


def test_an_empty_list_cannot_be_assigned(agent):
    blank = FamilyState(demo=False)
    blank.members = [{"id": "a", "name": "Asha", "relation": "Mom", "age": 40, "kind": "adult", "language": "English"}]
    with pytest.raises(ToolError, match="empty"):
        tool(agent, blank, "assign_shopping", assignee="a")
    assert tool(agent, blank, "get_shopping_list")["lists"][0]["items"] == []


# ---- the day plan ----


def test_the_day_plan_puts_what_matters_first(agent, state):
    tool(agent, state, "add_task", title="Pick up the cake", assignee="rahul", due="today", time="17:00")
    state.persona = "priya"
    tool(agent, state, "assign_shopping", assignee="rahul")
    plan = tool(agent, state, "get_day_plan", member_id="rahul")
    assert plan["name"] == "Rahul" and plan["date"] == "2026-11-20"
    assert plan["priorities"][0] == "Overdue: Pay the electricity bill (overdue since Thu 19 Nov)"
    assert "Today: Pick up the cake at 17:00" in plan["priorities"]
    assert any(p.startswith("Shopping: 5 items") for p in plan["priorities"])
    assert [t["id"] for t in plan["tasks"]["overdue"]] == ["t1"] and plan["shopping"][0]["list"] == "Groceries"
    assert any("aisle seats" in fact for fact in plan["remembered"])  # what the family remembers about him comes along
    assert plan["events"] == sorted(plan["events"], key=lambda e: e["start"])


def test_a_childs_day_plan_includes_homework(agent, state):
    plan = tool(agent, state, "get_day_plan", member_id="aarav")
    assert any(p.startswith("Homework: Science") for p in plan["priorities"])
    assert any("peanut allergy" in fact for fact in plan["remembered"])


def test_the_day_plan_needs_a_real_person(agent, state):
    with pytest.raises(ToolError, match="whose day"):
        tool(agent, state, "get_day_plan", member_id="family")
    with pytest.raises(ToolError, match="not in this family"):
        tool(agent, state, "get_day_plan", member_id="nobody")


# ---- conversation ----


def test_adding_to_the_list_by_voice_warns_about_the_diet(agent, state):
    reply = talk(agent, state, "priya", "add milk and eggs to the shopping list")
    assert "Added eggs to the groceries list" in reply and "Milk was already on it" in reply and "Dadi is vegetarian" in reply and "6 items to buy" in reply


def test_we_need_something_goes_on_the_list_but_a_cab_does_not(agent, state):
    assert talk(agent, state, "priya", "we need curd and onions") == "Added curd and onions to the groceries list. 7 items to buy now."
    assert agent.handle(state, "priya", "we need a cab to the airport") is None


def test_reading_the_list_by_voice(agent, state):
    reply = talk(agent, state, "priya", "what's on the shopping list")
    assert reply == "5 items on the groceries list: 2 L milk, 5 kg atta, paneer, 1 dozen bananas and 1 kg tomatoes. Nobody is assigned to shop yet."


def test_buying_by_voice(agent, state):
    reply = talk(agent, state, "rahul", "bought the milk")
    assert reply == "Ticked off milk. Still to buy: atta, paneer, bananas and tomatoes."
    assert agent.handle(state, "rahul", "bought a new car") is None


def test_asking_someone_to_do_the_shopping(agent, state):
    reply = talk(agent, state, "priya", "ask Rahul to do the groceries")
    assert reply == "Rahul is doing the shopping: 5 items. I have let them know."
    assert talk(agent, state, "priya", "assign the shopping to Priya by saturday").startswith("Priya is doing the shopping: 5 items, due tomorrow")


def test_reminding_someone_makes_an_assigned_task(agent, state):
    reply = talk(agent, state, "priya", "remind Rahul to pay the water bill tomorrow")
    assert reply == "Added the task for Rahul: Pay the water bill, due tomorrow. Rahul has been notified."
    assert notes(state)[-1]["to"] == ["rahul"]
    named = talk(agent, state, "priya", "add a task for Priya: renew the car insurance by saturday")
    assert named == "Added the task: Renew the car insurance, due tomorrow."


def test_asking_what_is_pending(agent, state):
    mine = talk(agent, state, "priya", "what are my tasks")
    assert mine == "You have 1 pending task: Buy chart paper for Aarav's science project, tomorrow."
    his = talk(agent, state, "priya", "what is pending for Rahul")
    assert his.startswith("Rahul has 2 pending tasks: Pay the electricity bill, overdue since Thu 19 Nov") and "1 is overdue" in his
    family = talk(agent, state, "priya", "what are the family's pending tasks")
    assert "(Rahul)" in family and "(nobody yet)" in family


def test_finishing_a_task_by_voice(agent, state):
    reply = talk(agent, state, "rahul", "I finished the electricity bill")
    assert reply == "Done: Pay the electricity bill. 3 tasks left. I have let them know."
    assert agent.handle(state, "rahul", "I finished my homework") is None  # nothing like that on the list


def test_planning_the_day_by_voice(agent, state):
    reply = talk(agent, state, "rahul", "plan my day")
    assert reply.startswith("Today for Rahul: Overdue: Pay the electricity bill")


def test_a_clear_day_is_said_plainly(agent):
    blank = FamilyState(demo=False)
    blank.members = [{"id": "a", "name": "Asha", "relation": "Mom", "age": 40, "kind": "adult", "language": "English"}]
    assert talk(agent, blank, "a", "plan my day") == "You have a clear day: nothing scheduled and nothing pending."


def test_other_agents_keep_what_is_theirs(state):
    for text in ("book a cab for Dadi on Sunday", "spent 500 on groceries", "what is the schedule today", "remind me about the meeting at 5"):
        assert BY_NAME["tasks"].score(state, text) < 3, text  # at most a weak score: it never takes the quick path from the owner
    for text in ("add milk to the shopping list", "plan my day", "remind Rahul to pay the bill"):
        assert BY_NAME["calendar"].score(state, text) == 0, text


def test_the_whole_conversation_reaches_the_agent_through_the_orchestrator(state):
    reply = orchestrator.converse(state, "priya", "put curd and onions on the shopping list")
    assert reply.startswith("Added curd and onions")
    assert [e["tool"] for e in state.events if e["agent"] == "tasks"] == ["add_shopping_items"]
    assert {"Curd", "Onions"} <= {i["name"] for i in state.domains["tasks"]["lists"]["groceries"]["items"]}


# ---- the scenario, the impact numbers and saving ----


def test_the_morning_brief_tells_each_adult_what_today_holds(agent, state):
    note = agent.run_trigger(state, "morning_tasks")
    briefs = notes(state)
    assert note.startswith("Sent a morning brief to") and {n["to"][0] for n in briefs} >= {"rahul", "priya"}
    assert "aarav" not in {n["to"][0] for n in briefs}  # children are not briefed on chores
    assert any("Overdue: Pay the electricity bill" in n["text"] for n in briefs)


def test_tasks_count_towards_the_impact_numbers(agent, state):
    run_tool(state, "tasks", agent.tool("add_task"), {"title": "Fix the gate", "assignee": "rahul"})
    run_tool(state, "tasks", agent.tool("get_day_plan"), {"member_id": "rahul"})
    result = impact.compute(state)
    kinds = {k["key"]: k for k in result["by_kind"]}
    assert kinds["tasks"]["count"] == 2 and kinds["tasks"]["minutes_saved"] == 8


def test_tasks_and_lists_survive_saving_and_loading(agent, state):
    tool(agent, state, "add_shopping_items", items=["curd"])
    tool(agent, state, "add_task", title="Fix the gate", assignee="rahul")
    saved = state.to_dict()
    fresh = FamilyState(demo=False)
    fresh.apply_dict(saved)
    assert {t["title"] for t in fresh.domains["tasks"]["tasks"]} >= {"Fix the gate", "Pay the electricity bill"}
    assert "Curd" in [i["name"] for i in fresh.domains["tasks"]["lists"]["groceries"]["items"]]


def test_a_new_household_starts_with_no_tasks_and_no_invented_list():
    blank = FamilyState(demo=False)
    assert blank.domains["tasks"] == {"tasks": [], "lists": {}}


# ---- found by talking to it for real ----


def test_the_same_chore_in_other_words_is_one_task_and_a_new_day_moves_it(agent, state):
    out = tool(agent, state, "add_task", title="Collect Dadi's prescription", assignee="rahul", due="friday")
    assert out["already_there"] is True and out["task"]["id"] == "t3" and out["due_updated"] is True and out["task"]["due"] == state.now["date"]
    assert len([t for t in tool(agent, state, "list_tasks")["tasks"] if "prescription" in t["title"].lower()]) == 1
    other = tool(agent, state, "add_task", title="Collect Aarav's books", assignee="rahul")  # a different chore with one word in common
    assert "already_there" not in other


def test_putting_the_same_person_on_the_shopping_again_does_not_notify_twice(agent, state):
    state.persona = "priya"
    first = tool(agent, state, "assign_shopping", assignee="rahul")
    second = tool(agent, state, "assign_shopping", assignee="rahul")
    assert first["notified"] == ["rahul"] and second["notified"] == [] and len(notes(state)) == 1
    moved = tool(agent, state, "assign_shopping", assignee="rahul", due="saturday")  # a new day is news to him
    assert moved["notified"] == ["rahul"]


def test_what_is_pending_is_answered_by_the_rules_not_sent_to_the_model(state):
    for text in ("what is pending for Rahul", "what are my tasks", "what is on the shopping list"):
        fast = orchestrator._fast_rule_reply(state, "priya", text, True)
        assert fast is not None and fast[0] == "tasks", text
    assert orchestrator._fast_rule_reply(state, "priya", "what is metformin", True) is None  # a real question still goes to the model


def test_the_model_is_told_that_done_means_already_done(agent):
    from app.llm import RULES

    assert "ALREADY" in agent.tool("complete_task").description and "add_task or assign_task" in agent.tool("complete_task").description
    assert "never complete_task" in RULES
    for name, key in (("complete_task", "done_by"), ("add_shopping_items", "added_by"), ("mark_bought", "bought_by")):
        assert "leave out" in agent.tool(name).parameters["properties"][key]["description"]


def test_two_requests_in_one_sentence_are_left_to_the_model(agent, state):
    both = "ask Aarav to tidy his room by tomorrow evening and put Rahul on the shopping for Saturday"
    assert agent.handle(state, "priya", both) is None and orchestrator._fast_rule_reply(state, "priya", both, True) is None
    assert agent.handle(state, "priya", "ask Aarav to tidy his room by tomorrow evening") is not None


def test_a_task_title_loses_its_day_and_time_words(agent, state):
    reply = talk(agent, state, "priya", "ask Aarav to tidy his room by tomorrow evening")
    assert reply == "Added the task for Aarav: Tidy his room, due tomorrow. Aarav has been notified."
    again = talk(agent, state, "priya", "remind Rahul to call the plumber on saturday at 5 pm")
    assert again.startswith("Added the task for Rahul: Call the plumber, due tomorrow")


def test_a_compound_task_request_still_offers_the_model_the_task_tools(state):
    from app import llm

    text = "Ask Aarav to tidy his room by tomorrow evening and put Rahul on the shopping for Saturday"
    assert BY_NAME["tasks"].score(state, text) in (1, 2)  # weak: offered to the model, never the quick path
    offered = llm._pick_index(state, text, llm._tool_index())
    assert any(key.startswith("tasks__") for key in offered)
    assert orchestrator._fast_rule_reply(state, "priya", text, True) is None
