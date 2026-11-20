import pytest

from app.agents.school import SchoolAgent
from app.state import FamilyState


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agent():
    return SchoolAgent()


def talk(agent, state, member_id, text):
    state.persona = member_id
    return agent.handle(state, member_id, text)


def tool_names(state):
    return [e["tool"] for e in state.events if e["agent"] == "school"]


def test_child_arrival_notifies_both_parents(agent, state):
    reply = talk(agent, state, "aarav", "main school pahunch gaya")
    kid = state.domains["school"]["kids"]["aarav"]
    assert kid["status"] == "at_school" and kid["arrived_at"] == "07:52" and state.now["time"] == "07:52"
    assert "Priya aur Rahul" in reply and "Shabaash" in reply
    [note] = state.notifications
    assert note["to"] == ["priya", "rahul"] and note["kind"] == "school" and "07:52" in note["text"]
    assert tool_names(state) == ["record_arrival", "notify_parents"]
    assert state.stage == "after"


def test_arrival_in_english_and_idempotent(agent, state):
    assert "bilkul time pe" in talk(agent, state, "aarav", "I reached school")
    again = talk(agent, state, "aarav", "I reached school")
    assert "hi pahunch gaye the" in again
    assert len(state.notifications) == 1 and len(state.domains["school"]["arrivals"]) == 1


def test_late_arrival_is_flagged(agent, state):
    state.now["time"] = "08:10"
    reply = talk(agent, state, "aarav", "I reached school")
    assert "bell ke thodi der baad" in reply
    assert "after the 08:00 bell" in state.notifications[0]["text"]
    assert state.domains["school"]["arrivals"][0]["on_time"] is False


def test_marks_celebrate_improvement_and_notify(agent, state):
    reply = talk(agent, state, "aarav", "aaj science mein 48 out of 50 mila")
    mark = state.domains["school"]["kids"]["aarav"]["marks"][-1]
    assert (mark["subject"], mark["score"], mark["max"], mark["date"]) == ("Science", 48.0, 50.0, "2026-11-20")
    assert "Wah Aarav" in reply and "14 point" in reply  # 82% -> 96%
    assert state.notifications[0]["to"] == ["priya", "rahul"] and "48/50" in state.notifications[0]["text"]


def test_marks_drop_is_encouraging(agent, state):
    reply = talk(agent, state, "aarav", "aaj maths mein 42 out of 50 mila")
    assert "42/50" in reply and "kam" in reply and "Koi baat nahi" in reply
    assert "4 points lower" in state.notifications[0]["text"]  # 88% -> 84%


def test_marks_single_number_and_exam_name(agent, state):
    talk(agent, state, "priya", "Aarav got 45 in English unit test 3")
    mark = state.domains["school"]["kids"]["aarav"]["marks"][-1]
    assert (mark["subject"], mark["score"], mark["max"], mark["exam"]) == ("English", 45.0, 50.0, "Unit Test 3")


def test_marks_missing_subject_asks_then_logs(agent, state):
    ask = talk(agent, state, "aarav", "mujhe 40 out of 50 mile")
    assert "subject" in ask and state.pending["kind"] == "marks_subject"
    reply = talk(agent, state, "aarav", "hindi ka tha")
    assert state.pending is None
    assert state.domains["school"]["kids"]["aarav"]["marks"][-1]["subject"] == "Hindi" and "40/50" in reply


def test_marks_over_max_rejected(agent, state):
    before = len(state.domains["school"]["kids"]["aarav"]["marks"])
    reply = talk(agent, state, "aarav", "science mein 60 out of 50 mila")
    assert "theek nahi" in reply
    assert len(state.domains["school"]["kids"]["aarav"]["marks"]) == before and not state.notifications
    assert state.events[-1]["status"] == "error"


def test_homework_done_completes_nearest_due(agent, state):
    reply = talk(agent, state, "aarav", "homework ho gaya")
    hw = {h["id"]: h for h in state.domains["school"]["kids"]["aarav"]["homework"]}
    assert hw["hw1"]["done"] and not hw["hw2"]["done"]  # Science (due 21st) before Maths (due 23rd)
    assert "Science" in reply and "1 aur baaki" in reply


def test_homework_done_by_subject_and_none_left(agent, state):
    talk(agent, state, "aarav", "maths homework done")
    hw = {h["id"]: h for h in state.domains["school"]["kids"]["aarav"]["homework"]}
    assert hw["hw2"]["done"] and not hw["hw1"]["done"]
    talk(agent, state, "aarav", "science homework done")
    reply = talk(agent, state, "aarav", "homework done")
    assert "Koi homework baaki nahi" in reply


def test_add_homework(agent, state):
    reply = talk(agent, state, "priya", "add homework hindi read chapter 4 due monday")
    item = state.domains["school"]["kids"]["aarav"]["homework"][-1]
    assert item["subject"] == "Hindi" and item["due"] == "2026-11-23" and not item["done"]
    assert "Hindi" in reply


def test_parent_summary_hinglish_and_english(agent, state):
    hi = talk(agent, state, "priya", "Aarav ka result kaisa hai")
    assert "average 81%" in hi and "Maths mein 12 point" in hi and "English par thoda dhyan" in hi and "Science ka homework kal tak" in hi
    en = talk(agent, state, "rahul", "How is Aarav doing in school?")
    assert "averaging 81%" in en and "Maths is up 12 points to 44/50" in en and "English needs a little push at 72%" in en
    assert "Science homework is due tomorrow" in en


def test_arrival_query_not_yet_then_yes(agent, state):
    no = talk(agent, state, "rahul", "Did Aarav reach school?")
    assert "hasn't reached yet" in no and "07:15" in no and "08:00" in no
    talk(agent, state, "aarav", "I reached school")
    yes = talk(agent, state, "rahul", "Did Aarav reach school?")
    assert "reached at 07:52" in yes


def test_triggers(agent, state):
    assert [t.name for t in agent.triggers] == ["arrival", "homework_nudge"]
    msg = agent.run_trigger(state, "arrival")
    assert "07:52" in msg and "Priya and Rahul" in msg and state.domains["school"]["kids"]["aarav"]["status"] == "at_school"
    assert state.notifications[-1]["to"] == ["priya", "rahul"]

    nudge = agent.run_trigger(state, "homework_nudge")
    assert "Science ka homework" in nudge and "Draw the water cycle" in nudge
    note = state.notifications[-1]
    assert note["to"] == ["priya"] and "Science homework" in note["text"]


def test_notify_parents_never_reaches_children(agent, state):
    status, res = agent.call(state, "notify_parents", message="hi", to=["aarav"])
    assert status == "error" and "parents only" in res["error"] and not state.notifications
    status, res = agent.call(state, "notify_parents", message="hi", to=["aarav", "rahul"])
    assert status == "ok" and res["to"] == ["rahul"]


def test_new_child_lazily_gets_school_record(agent, state):
    state.members.append({"id": "anaya", "name": "Anaya", "relation": "Daughter", "age": 6, "kind": "child",
                          "language": "Hinglish", "locale": "en-IN", "voice_id": None, "color": "#a073e5", "about": ""})
    reply = talk(agent, state, "priya", "Anaya ne maths mein 20 out of 25 score kiya")
    kid = state.domains["school"]["kids"]["anaya"]
    assert kid["marks"][0]["subject"] == "Maths" and kid["marks"][0]["max"] == 25.0
    assert "20/25" in reply and "pehla score" in reply


def test_two_children_ask_which_child(agent, state):
    state.members.append({"id": "anaya", "name": "Anaya", "relation": "Daughter", "age": 6, "kind": "child",
                          "language": "Hinglish", "locale": "en-IN", "voice_id": None, "color": "#a073e5", "about": ""})
    ask = talk(agent, state, "rahul", "How is school going?")
    assert "Which child" in ask and state.pending["kind"] == "which_child"
    reply = talk(agent, state, "rahul", "Aarav")
    assert state.pending is None and "Aarav" in reply and "averaging" in reply
    both = talk(agent, state, "rahul", "Did the kids reach school?")
    assert "Aarav" in both and "Anaya" in both


def test_score_claims_school_intents_only(agent, state):
    mine = [
        ("aarav", "main school pahunch gaya"), ("aarav", "aaj maths mein 42 out of 50 mila"), ("aarav", "homework ho gaya"),
        ("priya", "How is Aarav doing in school?"), ("priya", "Aarav ka result kaisa hai"),
        ("rahul", "Did Aarav reach school?"), ("priya", "add homework science draw a cell"),
    ]
    for member, text in mine:
        state.persona = member
        assert agent.score(state, text) >= 3, text
    others = [
        ("priya", "Book a table for Sunday lunch"), ("dadi", "Dawai le li"), ("rahul", "My flight is delayed, find an alternative"),
        ("priya", "When is everyone free on Sunday?"), ("priya", "Meet my daughter Anaya, she is 6"),
        ("priya", "How is Dadi doing?"), ("rahul", "Did I reach Delhi?"), ("rahul", "Did Rahul reach the airport?"),
        ("priya", "Remember Rahul doesn't like mushrooms"), ("priya", "Is the table booked for 4 out of 6 people?"),
        ("dadi", "Meri dawai khatam ho rahi hai"), ("priya", "Book Dadi's doctor appointment on Thursday"),
    ]
    for member, text in others:
        state.persona = member
        assert agent.score(state, text) == 0, text
        assert agent.handle(state, member, text) is None, text
