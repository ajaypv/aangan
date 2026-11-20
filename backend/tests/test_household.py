import pytest

from app import orchestrator, seed
from app.agents import REGISTRY
from app.agents.household import HouseholdAgent
from app.state import FamilyState

agent = HouseholdAgent()


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")


@pytest.fixture
def state():
    return FamilyState()


def test_add_member_from_one_sentence(state):
    reply = agent.handle(state, "priya", "Meet my daughter Anaya, she is 6, loves drawing and is allergic to eggs")
    anaya = state.member("anaya")
    assert "Anaya" in reply and "allergy" in reply and len(state.members) == 5
    assert anaya["relation"] == "Daughter" and anaya["age"] == 6 and anaya["kind"] == "child"
    assert anaya["language"] == "Hinglish" and anaya["voice_id"] is None
    assert set(seed.MEMBERS[0]) <= set(anaya)
    assert anaya["color"] not in [m["color"] for m in state.members if m["id"] != "anaya"]
    facts = {f["fact"]: f["tags"] for f in state.facts_about("anaya")}
    assert "allergy" in facts["Allergic to eggs"] and "interest" in facts["Loves drawing"]
    assert anaya["about"] == "Loves drawing"
    assert state.domains["school"]["kids"]["anaya"]["grade"] == "1-A"
    assert state.domains["school"]["kids"]["anaya"]["marks"] == []
    assert "anaya" not in state.domains["care"]["seniors"]
    note = state.notifications[-1]
    assert note["kind"] == "household" and "anaya" not in note["to"] and set(note["to"]) == {"priya", "rahul", "aarav", "dadi"}
    assert [e["tool"] for e in state.events] == ["add_member", "remember_fact", "remember_fact"]


def test_add_member_asks_for_missing_details(state):
    reply = agent.handle(state, "rahul", "Please add a new member to the family")
    assert "name" in reply.lower() and state.pending["agent"] == "household"
    reply = agent.handle(state, "rahul", "Her name is Meera, my sister")
    assert "old" in reply.lower() and state.pending["step"] == "age"
    reply = agent.handle(state, "rahul", "34")
    assert state.pending is None and state.member("meera")["kind"] == "adult" and state.member("meera")["age"] == 34
    assert "Meera is now part of the family" in reply


def test_add_member_pending_can_be_cancelled(state):
    agent.handle(state, "rahul", "Meet my son Kabir")
    assert state.pending["step"] == "age"
    assert "won't add" in agent.handle(state, "rahul", "never mind")
    assert state.pending is None and len(state.members) == 4


def test_add_senior_gets_care_entry_and_hindi(state):
    agent.handle(state, "priya", "Meet our grandfather Mohan, he is 75")
    mohan = state.member("mohan")
    assert mohan["kind"] == "senior" and mohan["language"] == "Hindi" and mohan["locale"] == "hi-IN"
    assert state.domains["care"]["seniors"]["mohan"]["meds"] == []
    assert "mohan" not in state.domains["school"]["kids"]


def test_add_member_hinglish_and_duplicate(state):
    reply = agent.handle(state, "dadi", "Yeh meri beti Riya hai, 8 saal ki, drawing pasand hai")
    assert state.member("riya")["relation"] == "Daughter" and "ab parivaar ka hissa" in reply
    assert any(f["fact"] == "Loves drawing" for f in state.facts_about("riya"))
    again = agent.handle(state, "priya", "Meet my daughter Riya, she is 8")
    assert "already in the family" in again and len(state.members) == 5


def test_remember_english_and_hinglish(state):
    reply = agent.handle(state, "priya", "Remember Rahul doesn't like mushrooms")
    assert "Doesn't like mushrooms" in reply
    fact = state.facts_about("rahul")[-1]
    assert fact["fact"] == "Doesn't like mushrooms" and "food" in fact["tags"] and fact["id"] == "m10"
    reply = agent.handle(state, "rahul", "Yaad rakhna ki Dadi ko subah jaldi uthna pasand hai")
    assert "Dadi ko subah jaldi uthna pasand hai" in reply
    assert "routine" in state.facts_about("dadi")[-1]["tags"]
    assert "already knew" in agent.handle(state, "rahul", "Yaad rakhna ki Dadi ko subah jaldi uthna pasand hai")
    assert "pehle se" in agent.handle(state, "priya", "Yaad rakhna ki Dadi ko subah jaldi uthna pasand hai")


def test_remember_family_and_self(state):
    agent.handle(state, "priya", "Remember that we eat dinner together on Sundays")
    assert state.facts_about("family")[-1]["fact"] == "We eat dinner together on Sundays"
    agent.handle(state, "aarav", "Remember I like mango ice cream")
    # first-person facts are stored in the third person about the speaker
    assert state.facts_about("aarav")[-1]["fact"] == "Likes mango ice cream"


def test_recall_groups_facts(state):
    reply = agent.handle(state, "rahul", "What do you know about Dadi?")
    assert reply.startswith("About Dadi")
    assert "On food, pure vegetarian" in reply and "On health, bad knees" in reply  # phrased for a voice, not "label: item"
    assert "dinner by 8 pm" in reply or "Avoids spicy" in reply
    assert "About the family" in agent.handle(state, "rahul", "What do you know about us?")
    assert agent.handle(state, "priya", "What do you know about Dadi?").startswith("Dadi ke baare mein")
    own = agent.handle(state, "aarav", "Tell me about me")
    assert "peanut" in own.lower()


def test_roster(state):
    reply = agent.handle(state, "rahul", "Who is in the family?")
    assert "4 of you" in reply and "Dadi the grandmother, 72" in reply  # read aloud as "Dadi the grandmother, 72"
    hi = agent.handle(state, "aarav", "Family mein kaun kaun hai")
    assert "Aap sab 4 log hain" in hi
    agent.handle(state, "rahul", "Meet my daughter Anaya, she is 6")
    assert "5 of you" in agent.handle(state, "rahul", "How many of us are there")


def test_forget(state):
    agent.handle(state, "rahul", "Remember Rahul doesn't like mushrooms")
    reply = agent.handle(state, "rahul", "Forget that Rahul doesn't like mushrooms")
    assert "Forgotten" in reply
    assert all("mushrooms" not in f["fact"] for f in state.memory)
    assert "couldn't find" in agent.handle(state, "rahul", "Forget that Rahul likes cricket")
    assert "Bhool gaya" in agent.handle(state, "priya", "Bhool jao ki Dadi pure vegetarian hain")


def test_trigger_demo_adds_anaya_once(state):
    state.persona = "priya"
    reply = agent.run_trigger(state, "add_member_demo")
    assert "Anaya" in reply and len(state.members) == 5
    assert state.transcript[-1]["agent"] == "household"
    assert any(f["fact"] == "Allergic to eggs" for f in state.facts_about("anaya"))
    assert "pehle se" in agent.run_trigger(state, "add_member_demo") and len(state.members) == 5
    state.persona = "rahul"
    assert "already" in agent.run_trigger(state, "add_member_demo")


def test_tool_errors_and_schemas(state):
    for tool in agent.tools:
        assert tool.parameters["type"] == "object"
        assert set(tool.parameters.get("required", [])) <= set(tool.parameters["properties"])
    assert agent.call(state, "remember_fact", about="nobody", fact="x")[0] == "error"
    assert agent.call(state, "forget_fact", fact_id="m999")[0] == "error"
    assert agent.call(state, "add_member", name="Sam", relation="Son", age=200, kind="child")[0] == "error"
    assert agent.call(state, "recall", about="nobody")[0] == "error"


def test_score_core_intents_high_and_others_zero(state):
    core = [
        "Meet my daughter Anaya, she is 6", "Remember Rahul doesn't like mushrooms", "What do you know about Dadi",
        "Who is in the family", "Yaad rakhna ki Dadi ko subah jaldi uthna pasand hai", "Forget that Rahul likes mushrooms",
    ]
    others = [
        "Sunday ko sab saath lunch pe jaana hai", "Dadi ki dawai khatam ho rahi hai", "How is Aarav doing in school?",
        "Book flights for all of us to Goa on December 26", "When is everyone free on Sunday?", "Main school pahunch gaya",
        "What do you know about the flight to Delhi", "Don't forget to book a table", "Add my son's cricket match to the calendar",
        "Dawai le li", "Tell me about Aarav's marks",
    ]
    assert all(agent.score(state, t) >= 3 for t in core)
    assert all(agent.score(state, t) == 0 for t in others), [t for t in others if agent.score(state, t)]


def test_router_prefers_household_for_core_utterances(state):
    assert "household" in [a.name for a in REGISTRY]
    assert orchestrator.route(state, "Meet my daughter Anaya, she is 6, loves drawing and is allergic to eggs").name == "household"
    assert orchestrator.route(state, "Who is in the family?").name == "household"
    reply = orchestrator.converse(state, "priya", "Remember Rahul doesn't like mushrooms")
    assert "mushrooms" in reply and state.transcript[-1]["agent"] == "household"
