"""Spoken-English corpus: what a speech recogniser hands the rule engine (no LLM key), across all six agents.

Every core phrase is run four ways (plain, with a filler, with the assistant's name, with 'please') so filler
stripping is exercised everywhere. Multi-turn cases cover confirmations, rejections and interruptions.
"""

import re

import pytest

from app import orchestrator
from app.speech import clean_input, num_to_words, numbers_to_digits, speakable
from app.state import FamilyState


@pytest.fixture(autouse=True)
def english_mode(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")


def C(persona, text, agent, tools=(), has=(), check=None):
    return (persona, text, agent, tuple(tools), tuple(has), check)


def last_fact(state, who):
    facts = state.facts_about(who)
    return facts[-1]["fact"] if facts else None


def kid(state, member="aarav"):
    return state.domains["school"]["kids"][member]


def travel(state):
    return state.domains["travel"]


def reservations(state):
    return [r for r in state.domains["dining"]["reservations"] if r["status"] == "CONFIRMED"]


def has_event(state, word):
    return any(word in e["title"].lower() for e in state.calendar)


CORE = [
    # ---- travel
    C("rahul", "my flight is delayed find me another one", "travel", ["travel.search_flights"], ["indigo"]),
    C("rahul", "can you find an alternative flight to delhi", "travel", ["travel.search_flights"], ["shall i book"]),
    C("rahul", "my flight is delayed by two hours find me another flight", "travel",
      ["travel.flight_status_webhook", "travel.search_flights"], ["indigo"], lambda s: travel(s)["trips"][0]["delay_min"] == 120),
    C("priya", "rahul's flight is delayed", "travel", ["travel.search_flights"], ["indigo"]),
    C("rahul", "is my flight on time", "travel", ["travel.get_trip"], ["on time"]),
    C("priya", "is rahul's flight running late", "travel", ["travel.get_trip"], ["rahul's flight"]),
    C("rahul", "what's my flight status", "travel", ["travel.get_trip"], ["your flight"]),
    C("rahul", "when is my cab coming", "travel", [], ["three thirty"]),
    C("rahul", "move my airport cab to four am", "travel", ["travel.update_cab_pickup"], ["four am"],
      lambda s: travel(s)["trips"][0]["cab"]["pickup"] == "04:00"),
    C("rahul", "i need a cab to the airport at five am", "travel", ["travel.update_cab_pickup"], ["five am"]),
    C("priya", "book flights for all of us to goa on december twenty sixth", "travel", ["travel.book_flight"], ["four tickets"],
      lambda s: any(len(t["member_ids"]) == 4 for t in travel(s)["trips"])),
    C("priya", "book tickets to goa for the whole family on the twenty sixth of december", "travel", ["travel.book_flight"], ["four tickets"]),
    C("rahul", "book me a flight to goa on december twenty sixth", "travel", ["travel.book_flight"], ["booked"]),
    # ---- calendar
    C("priya", "when is everyone free on sunday", "calendar", ["calendar.find_family_slots"], ["everyone is free"]),
    C("priya", "is everyone free sunday afternoon", "calendar", ["calendar.find_family_slots"], ["free"]),
    C("rahul", "when are we all free for lunch on sunday", "calendar", ["calendar.find_family_slots"], ["free"]),
    C("rahul", "what's on tomorrow", "calendar", ["calendar.get_schedule"], ["you have nothing"]),
    C("rahul", "what is my schedule for monday", "calendar", ["calendar.get_schedule"], ["flight"]),
    C("priya", "what is rahul doing on monday", "calendar", ["calendar.get_schedule"], ["rahul has"]),
    C("priya", "what does aarav have on saturday", "calendar", ["calendar.get_schedule"], ["cricket"]),
    C("priya", "do we have any clashes this week", "calendar", ["calendar.scan_clashes"], ["double"]),
    C("priya", "any conflicts in the calendar", "calendar", ["calendar.scan_clashes"], ["double"]),
    C("priya", "add a dentist appointment for aarav on saturday at five pm", "calendar", ["calendar.create_event"], ["dentist"],
      lambda s: has_event(s, "dentist")),
    C("priya", "add a family movie night on saturday at seven pm", "calendar", ["calendar.create_event"], ["movie night"],
      lambda s: has_event(s, "movie")),
    C("priya", "move the swimming class to ten", "calendar", ["calendar.move_event"], ["swimming class"]),
    C("priya", "cancel the satsang", "calendar", ["calendar.cancel_event"], ["satsang"],
      lambda s: not has_event(s, "satsang")),
    C("priya", "give me the weekly digest", "calendar", ["calendar.send_digest"], ["your week"]),
    C("priya", "what's the plan for the week", "calendar", ["calendar.send_digest"], ["your week"]),
    # ---- dining
    C("priya", "let's all go out for lunch on sunday", "dining", ["dining.search_restaurants"], ["udupi garden", "one pm"]),
    C("priya", "can we go out for dinner on sunday", "dining", ["dining.search_restaurants"], ["olive courtyard"]),
    C("priya", "i want to book a table for the family", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("priya", "where should we eat on sunday", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("priya", "find us a restaurant for sunday lunch", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("priya", "book a table for four at one pm on sunday", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("rahul", "can you plan a family lunch on sunday", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("priya", "we want to go out and eat on sunday", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    C("priya", "i'm hungry let's eat out", "dining", ["dining.search_restaurants"], ["udupi garden"]),
    # ---- school
    C("aarav", "i reached school", "school", ["school.record_arrival"], ["right on time"],
      lambda s: kid(s)["status"] == "at_school"),
    C("aarav", "i'm at school", "school", ["school.record_arrival"], ["priya and rahul"]),
    C("aarav", "i got forty two out of fifty in maths", "school", ["school.log_marks"], ["forty two out of fifty"],
      lambda s: kid(s)["marks"][-1]["score"] == 42),
    C("aarav", "i scored forty five in english", "school", ["school.log_marks"], ["english"],
      lambda s: kid(s)["marks"][-1]["subject"] == "English"),
    C("aarav", "i got fifty out of fifty in science", "school", ["school.log_marks"], ["science"]),
    C("aarav", "my homework is done", "school", ["school.complete_homework"], ["homework is done"]),
    C("aarav", "i finished my science homework", "school", ["school.complete_homework"], ["science homework"]),
    C("priya", "how is aarav doing in school", "school", ["school.get_child_summary"], ["eighty one percent"]),
    C("priya", "how did aarav do in his exams", "school", ["school.get_child_summary"], ["aarav"]),
    C("priya", "how is arav doing in his studies", "school", ["school.get_child_summary"], ["aarav"]),
    C("priya", "did aarav reach school", "school", [], ["hasn't reached"]),
    C("priya", "has aarav gotten to school yet", "school", [], ["hasn't reached"]),
    C("priya", "has he reached school", "school", [], ["hasn't reached"]),
    C("rahul", "did aarav get to school safely", "school", [], ["aarav"]),
    C("priya", "what homework does aarav have", "school", [], ["two homework items"]),
    C("priya", "add homework science draw a diagram due monday", "school", ["school.add_homework"], ["draw a diagram"]),
    C("aarav", "what homework do i have", "school", [], ["you have two homework items"]),
    C("aarav", "what do i have on monday", "calendar", ["calendar.get_schedule"], ["you have school"]),
    # ---- care
    C("dadi", "i took my medicine", "care", ["care.log_medicine_taken"], ["metformin"]),
    C("dadi", "i've taken my tablets", "care", ["care.log_medicine_taken"], ["metformin"]),
    C("dadi", "my medicine is finished", "care", ["care.order_refill"], ["refill"]),
    C("dadi", "i'm running out of my pills", "care", ["care.order_refill"], ["refill"]),
    C("dadi", "i'm feeling dizzy", "care", ["care.record_checkin"], ["sit down"]),
    C("dadi", "i don't feel well", "care", ["care.record_checkin"], ["asked rahul and priya"]),
    C("rahul", "did dadi take her medicines", "care", ["care.get_care_summary"], ["zero of three"]),
    C("rahul", "has grandma had her tablets today", "care", ["care.get_care_summary"], ["dadi has taken"]),
    C("rahul", "did daddy take her medicines", "care", ["care.get_care_summary"], ["dadi has taken"]),
    C("rahul", "did she take her tablets", "care", ["care.get_care_summary"], ["dadi has taken"]),
    C("priya", "how is dadi today", "care", ["care.get_care_summary"], ["dadi has taken"]),
    C("priya", "book dadi's doctor appointment for thursday at eleven", "care", ["care.book_appointment"], ["eleven"],
      lambda s: has_event(s, "sharma")),
    C("priya", "order a refill for dadi's metformin", "care", ["care.order_refill"], ["metformin"]),
    C("priya", "when is dadi's next doctor appointment", "care", [], ["friday the twenty seventh"]),
    # ---- household
    C("priya", "meet my daughter anaya she is six", "household", ["household.add_member"], ["anaya"],
      lambda s: any(m["name"] == "Anaya" and m["age"] == 6 for m in s.members)),
    C("priya", "add a new member to the family", "household", [], ["name"]),
    C("rahul", "remember that i don't like mushrooms", "household", ["household.remember_fact"], ["rahul doesn't like mushrooms"],
      lambda s: last_fact(s, "rahul") == "Doesn't like mushrooms"),
    C("priya", "remember dadi likes tea in the morning", "household", ["household.remember_fact"], ["dadi likes tea"],
      lambda s: "tea" in (last_fact(s, "dadi") or "").lower()),
    C("rahul", "i'm allergic to prawns remember that", "household", ["household.remember_fact"], ["rahul is allergic to prawns"],
      lambda s: last_fact(s, "rahul") == "Allergic to prawns"),
    C("priya", "my favourite food is dosa please remember", "household", ["household.remember_fact"], ["priya's favourite food is dosa"],
      lambda s: last_fact(s, "priya") == "Favourite food is dosa"),
    C("priya", "i prefer window seats remember that", "household", ["household.remember_fact"], ["priya prefers window seats"],
      lambda s: last_fact(s, "priya") == "Prefers window seats"),
    C("priya", "what do you know about dadi", "household", ["household.recall"], ["pure vegetarian"]),
    C("priya", "what does dadi like to eat", "household", ["household.recall"], ["dadi"]),
    C("priya", "who is in the family", "household", ["household.family_summary"], ["four of you"]),
    C("priya", "how many people are in our family", "household", ["household.family_summary"], ["four of you"]),
]

WRAPPERS = ["{}", "um {}", "hey aangan {}", "{} please"]
CORE_PARAMS = [
    pytest.param(*case, wrap, id=f"{case[0]}-w{i}-{case[1][:48]}")
    for case in CORE
    for i, wrap in enumerate(WRAPPERS)
]


@pytest.mark.parametrize("persona,text,agent,tools,has,check,wrap", CORE_PARAMS)
def test_core_phrasings(persona, text, agent, tools, has, check, wrap):
    state = FamilyState()
    reply = orchestrator.converse(state, persona, wrap.format(text))
    assert state.transcript[-1]["agent"] == agent, reply
    ran = [f"{e['agent']}.{e['tool']}" for e in state.events if e["agent"] != "orchestrator"]
    for tool in tools:
        assert tool in ran, (ran, reply)
    for fragment in has:
        assert fragment in reply.lower(), reply
    if check:
        assert check(state), reply


# ------------------------------------------------------------------ a second, adversarial set (found by probing)

EXTRA = [
    ("rahul", "any update on rahul's flight", "travel"), ("priya", "has rahul's flight been delayed", "travel"),
    ("priya", "i want to travel to goa on december twenty sixth with everyone", "travel"),
    ("rahul", "can you book a flight to delhi for me tomorrow", "travel"), ("rahul", "what time does my flight leave", "travel"),
    ("rahul", "call me a cab to the airport", "travel"), ("rahul", "can you change my cab to five am", "travel"),
    ("priya", "what's happening on sunday", "calendar"), ("priya", "is rahul free on sunday afternoon", "calendar"),
    ("priya", "when is rahul free on monday", "calendar"), ("priya", "are we all free on saturday", "calendar"),
    ("rahul", "what's priya doing tomorrow", "calendar"), ("priya", "anything on for dadi on sunday", "calendar"),
    ("priya", "show me aarav's schedule for monday", "calendar"), ("priya", "tell me what's happening this week", "calendar"),
    ("priya", "put the dentist on saturday at five", "calendar"), ("priya", "reschedule the swimming class to eleven", "calendar"),
    ("priya", "push the satsang to six pm", "calendar"), ("priya", "delete the client prep call", "calendar"),
    ("priya", "schedule a doctor visit for dadi on friday at ten", "care"),
    ("priya", "i'd like to reserve a table for sunday lunch", "dining"), ("priya", "find a place to eat on sunday", "dining"),
    ("priya", "let's have dinner out tomorrow", "dining"), ("priya", "can you recommend a restaurant", "dining"),
    ("priya", "what's a good place for lunch on sunday", "dining"), ("priya", "plan a family dinner for saturday", "dining"),
    ("priya", "book us a table at udupi garden", "dining"), ("priya", "where can we get south indian food on sunday", "dining"),
    ("priya", "did aarav get to school", "school"), ("priya", "is aarav at school", "school"),
    ("priya", "has aarav arrived at school", "school"), ("priya", "what are aarav's marks", "school"),
    ("priya", "how did aarav do in maths", "school"), ("priya", "how's aarav's progress", "school"),
    ("aarav", "i scored forty two out of fifty in the maths test", "school"), ("aarav", "i have finished my maths homework", "school"),
    ("aarav", "i did my homework", "school"), ("aarav", "i am in school", "school"), ("aarav", "i've reached school", "school"),
    ("aarav", "i got to school", "school"), ("priya", "add maths homework page ten due friday", "school"),
    ("dadi", "i've had my tablets", "care"), ("dadi", "i took my pills just now", "care"), ("dadi", "i forgot to take my medicine", "care"),
    ("dadi", "should i take my medicine now", "care"), ("dadi", "i have a headache", "care"), ("dadi", "my knees hurt", "care"),
    ("dadi", "i feel weak", "care"), ("priya", "how's dadi doing", "care"), ("priya", "is dadi okay", "care"),
    ("priya", "has dadi taken her medicine", "care"), ("priya", "did dadi have her tablets this morning", "care"),
    ("priya", "order dadi's medicines", "care"), ("dadi", "my medicine is almost over", "care"),
    ("priya", "schedule a checkup for dadi on friday at ten", "care"),
    ("priya", "this is my daughter anaya she is six", "household"), ("priya", "we have a new family member", "household"),
    ("priya", "add my brother vikram he is thirty five", "household"),
    ("priya", "remember that aarav is allergic to peanuts", "household"), ("priya", "aarav doesn't like broccoli remember that", "household"),
    ("priya", "make a note that dadi goes to bed at nine", "household"), ("priya", "what does aarav like", "household"),
    ("priya", "is aarav allergic to anything", "household"), ("priya", "tell me about rahul", "household"),
    ("priya", "who all are in the family", "household"),
]


@pytest.mark.parametrize("persona,text,agent", [pytest.param(*c, id=f"{c[0]}-{c[1][:60]}") for c in EXTRA])
def test_extra_phrasings(persona, text, agent):
    state = FamilyState()
    reply = orchestrator.converse(state, persona, text)
    assert state.transcript[-1]["agent"] == agent, reply


@pytest.mark.parametrize(
    "text",
    ["i haven't taken my medicine", "i have not taken my tablets yet", "i didn't take my pills", "i forgot to take my medicine", "i missed my medicine"],
)
def test_negated_medicine_is_never_logged_as_taken(text):
    state = FamilyState()
    reply = orchestrator.converse(state, "dadi", text)
    assert not any(e["tool"] == "log_medicine_taken" for e in state.events), reply
    assert "next medicine" in reply.lower() or "metformin" in reply.lower()


def test_status_question_while_a_proposal_is_pending_keeps_the_proposal():
    state = FamilyState()
    orchestrator.converse(state, "rahul", "my flight is delayed by two hours find me another flight")
    reply = orchestrator.converse(state, "rahul", "is my flight on time")
    assert "delayed by two hours" in reply.lower() and "still book" in reply.lower()
    assert state.pending and state.pending["agent"] == "travel"


def test_delay_length_is_not_read_as_an_arrival_deadline():
    state = FamilyState()
    reply = orchestrator.converse(state, "rahul", "my flight is delayed by two hours find me another flight")
    assert "reach by" not in reply.lower() and "indigo" in reply.lower()


# ------------------------------------------------------------------ multi-turn: confirmations and interruptions

LUNCH ="let's all go out for lunch on sunday"
DELAY = "my flight is delayed find me an alternative"
DINNER = "can we go out for dinner on sunday"

MULTI = [
    # dining confirmations in different spoken forms
    C("priya", [LUNCH, "yes"], "dining", ["dining.book_table"], ["table for four", "udupi garden"], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "yeah go ahead"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "sounds good book it"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "that works"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "perfect"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "booked it"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "okay book it"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "yes book it and tell rahul"], "dining", ["dining.book_table", "dining.notify_family"], [],
      lambda s: len(reservations(s)) == 1 and bool(s.notifications)),
    C("priya", [LUNCH, "yes please do"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "go ahead and book it"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    C("priya", [LUNCH, "yes"], "dining", ["dining.add_calendar_event"], [],
      lambda s: any(e["kind"] == "dining" and len(e["member_ids"]) == 4 for e in s.calendar)),
    C("priya", [LUNCH, "no thanks"], "dining", [], [], lambda s: not s.pending and not reservations(s)),
    C("priya", [LUNCH, "cancel that"], "dining", [], [], lambda s: not s.pending and not reservations(s)),
    C("priya", [LUNCH, "never mind"], "dining", [], [], lambda s: not s.pending and not reservations(s)),
    C("priya", [LUNCH, "not now"], "dining", [], [], lambda s: not s.pending and not reservations(s)),
    C("priya", [LUNCH, "forget it"], "dining", [], [], lambda s: not s.pending and not reservations(s)),
    # dining changes mid-proposal
    C("priya", [LUNCH, "something cheaper"], "dining", [], [], lambda s: s.pending and s.pending["agent"] == "dining"),
    C("priya", [LUNCH, "can we do italian instead"], "dining", [], [], lambda s: s.pending is None or s.pending["agent"] == "dining"),
    C("priya", [LUNCH, "somewhere with a play area"], "dining", [], [], lambda s: s.pending is None or s.pending["agent"] == "dining"),
    C("priya", [LUNCH, "how about somewhere else"], "dining", [], [], lambda s: s.pending is None or s.pending["agent"] == "dining"),
    C("priya", [DINNER, "yes"], "dining", ["dining.book_table"], [], lambda s: len(reservations(s)) == 1),
    # travel confirmations and changes
    C("rahul", [DELAY, "yes book it"], "travel", ["travel.rebook_flight"], ["booked"],
      lambda s: travel(s)["trips"][0]["status"] == "REBOOKED" and travel(s)["trips"][0]["flight"] == "6E-6107"),
    C("rahul", [DELAY, "yeah go ahead"], "travel", ["travel.rebook_flight"], [], lambda s: travel(s)["trips"][0]["status"] == "REBOOKED"),
    C("rahul", [DELAY, "sounds good"], "travel", ["travel.rebook_flight"], [], lambda s: travel(s)["trips"][0]["status"] == "REBOOKED"),
    C("rahul", [DELAY, "booked it"], "travel", ["travel.rebook_flight"], [], lambda s: travel(s)["trips"][0]["status"] == "REBOOKED"),
    C("rahul", [DELAY, "actually i want a window seat", "yes book it"], "travel", ["travel.rebook_flight"], [],
      lambda s: travel(s)["trips"][0]["flight"] == "SG-8153"),
    C("rahul", [DELAY, "what about a window seat", "sounds good"], "travel", ["travel.rebook_flight"], [],
      lambda s: travel(s)["trips"][0]["flight"] == "SG-8153"),
    C("rahul", [DELAY, "under seven thousand rupees"], "travel", [], ["cheapest"],
      lambda s: travel(s)["trips"][0]["status"] != "REBOOKED"),
    C("rahul", [DELAY, "no thanks"], "travel", [], [], lambda s: not s.pending and travel(s)["trips"][0]["status"] != "REBOOKED"),
    C("rahul", [DELAY, "forget it"], "travel", [], [], lambda s: not s.pending and travel(s)["trips"][0]["status"] != "REBOOKED"),
    C("rahul", [DELAY, "cancel that"], "travel", [], [], lambda s: not s.pending and travel(s)["trips"][0]["status"] != "REBOOKED"),
    C("rahul", ["my flight is delayed by two hours", "is my flight on time"], "travel", ["travel.flight_status_webhook"], ["delayed by two hours"],
      lambda s: travel(s)["trips"][0]["delay_min"] == 120),
    C("rahul", ["i need a flight to goa on december twenty sixth", "yes"], "travel", ["travel.book_flight"], [],
      lambda s: any(t["route"].endswith("GOI") for t in travel(s)["trips"])),
    C("rahul", ["fly to goa", "december twenty sixth", "yes"], "travel", ["travel.book_flight"], [],
      lambda s: any(t["route"].endswith("GOI") for t in travel(s)["trips"])),
    # topic changes while something is pending
    C("rahul", [DELAY, "did dadi take her medicines"], "care", ["care.get_care_summary"], ["dadi has taken"], lambda s: s.pending is None),
    C("priya", [LUNCH, "how is aarav doing in school"], "school", ["school.get_child_summary"], [],
      lambda s: s.pending is None and not reservations(s)),
    C("priya", [LUNCH, "when is everyone free on monday"], "calendar", ["calendar.find_family_slots"], [], lambda s: s.pending is None),
    C("rahul", [DELAY, "what's on tomorrow"], "calendar", ["calendar.get_schedule"], [], lambda s: s.pending is None),
    C("priya", [LUNCH, "remember dadi likes tea"], "household", ["household.remember_fact"], [], lambda s: s.pending is None),
    C("priya", ["book a doctor appointment for dadi", "never mind"], "care", [], [], lambda s: s.pending is None and not s.domains["care"]["appointments"]),
    # slot filling
    C("priya", ["book a doctor appointment for dadi", "thursday at eleven"], "care", ["care.book_appointment"], [],
      lambda s: len(s.domains["care"]["appointments"]) == 1),
    C("priya", ["add a dentist appointment for aarav", "saturday at five pm"], "calendar", ["calendar.create_event"], [],
      lambda s: has_event(s, "dentist")),
    C("priya", ["add a new member", "Her name is Anaya and she is my daughter", "she is six"], "household", ["household.add_member"], ["anaya"],
      lambda s: any(m["name"] == "Anaya" for m in s.members)),
    C("priya", ["meet my son kabir", "he is eleven"], "household", ["household.add_member"], ["kabir"],
      lambda s: any(m["name"] == "Kabir" and m["age"] == 11 for m in s.members)),
    # memory round trips
    C("priya", ["remember dadi likes tea in the morning", "forget that dadi likes tea"], "household", ["household.forget_fact"], [],
      lambda s: not any("tea" in f["fact"].lower() for f in s.facts_about("dadi"))),
    C("rahul", ["remember that i don't like mushrooms", "forget that i don't like mushrooms"], "household", ["household.forget_fact"], [],
      lambda s: not any("mushroom" in f["fact"].lower() for f in s.facts_about("rahul"))),
    C("rahul", ["i'm allergic to prawns remember that", "what do you know about me"], "household", ["household.recall"], ["prawns"]),
    # school round trips
    C("aarav", ["i got forty two out of fifty in maths", "i got forty five out of fifty in maths"], "school", ["school.log_marks"], ["up"],
      lambda s: [m["score"] for m in kid(s)["marks"] if m["subject"] == "Maths"][-2:] == [42, 45]),
    C("aarav", ["i reached school", "priya did aarav reach school"], "school", [], ["reached"]),
    C("aarav", ["my homework is done", "what homework do i have"], "school", [], ["one homework item"]),
    # care round trips
    C("dadi", ["i took my medicine", "did i take my medicine"], "care", ["care.get_care_summary"], []),
    C("dadi", ["my medicine is finished", "when is my refill coming"], "care", [], []),
]


@pytest.mark.parametrize("persona,turns,agent,tools,has,check", [pytest.param(*c, id=f"{c[0]}-{'|'.join(c[1])[:70]}") for c in MULTI])
def test_multi_turn(persona, turns, agent, tools, has, check):
    state = FamilyState()
    reply = ""
    for turn in turns:
        reply = orchestrator.converse(state, persona, turn)
    assert state.transcript[-1]["agent"] == agent, reply
    ran = [f"{e['agent']}.{e['tool']}" for e in state.events if e["agent"] != "orchestrator"]
    for tool in tools:
        assert tool in ran, (ran, reply)
    for fragment in has:
        assert fragment in reply.lower(), reply
    if check:
        assert check(state), reply


# ------------------------------------------------------------------ nothing a voice reads badly reaches the TTS

def _all_replies():
    scripts = [(c[0], [c[1]]) for c in CORE] + [(c[0], c[1]) for c in MULTI] + [(c[0], [c[1]]) for c in EXTRA]
    for persona, turns in scripts:
        state = FamilyState()
        for turn in turns:
            yield persona, turn, orchestrator.converse(state, persona, turn)


def test_spoken_replies_contain_no_digits_symbols_or_codes(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    offenders = []
    for persona, turn, reply in _all_replies():
        if re.search(r"[\d:;()%&@/*_#\[\]<>=]|\bRs\b|->|\bPNR\b|\bBLR\b|\bDEL\b|\bGOI\b", reply):
            offenders.append((persona, turn, reply))
    assert not offenders, offenders[:5]


def test_spoken_replies_are_short_enough_to_listen_to(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    long_ones = [(t, len(r.split())) for _, t, r in _all_replies() if len(r.split()) > 70]
    assert not long_ones, long_ones[:5]


# ------------------------------------------------------------------ small talk and dead ends

@pytest.mark.parametrize(
    "text,fragment",
    [
        ("hello", "how can i help"), ("hi aangan", "how can i help"), ("good morning", "good morning"),
        ("thank you", "welcome"), ("thanks a lot", "welcome"), ("bye", "goodbye"), ("see you later", "goodbye"),
        ("what can you do", "i can help"), ("help", "i can help"),
        ("yes", "what"), ("no", "what"),
        ("tell me a joke about elephants", "i can help"),
    ],
)
def test_small_talk_and_unknown_requests(text, fragment):
    state = FamilyState()
    reply = orchestrator.converse(state, "rahul", text)
    assert fragment in reply.lower(), reply
    assert state.transcript[-1]["agent"] == "aangan"


def test_english_mode_replies_are_english_for_every_member():
    state = FamilyState()
    for member, text in [("dadi", "i took my medicine"), ("aarav", "i reached school"), ("priya", "let's all go out for lunch on sunday")]:
        reply = orchestrator.converse(state, member, text)
        assert not any(w in reply.lower().split() for w in ("hai", "kar", "baje", "aap", "main", "maine", "shabaash"))


def test_voice_reply_is_clean_but_transcript_keeps_screen_text():
    state = FamilyState()
    spoken = orchestrator.converse(state, "priya", "let's all go out for lunch on sunday")
    shown = state.transcript[-1]["text"]
    assert "13:00" in shown and "Rs " in shown
    assert "13:00" not in spoken and "Rs" not in spoken and ":" not in spoken
    assert "one PM" in spoken and "rupees" in spoken


@pytest.mark.parametrize(
    "text",
    ["Sunday को सब के साथ बाहर जाना है", "मैं स्कूल पहुंच गया", "मेरी दवाई खत्म हो रही है"],
)
def test_devanagari_still_reaches_agents_in_english_mode(text):
    state = FamilyState()
    orchestrator.converse(state, "priya", text)
    assert state.transcript[-1]["agent"] in {"dining", "school", "care"}


def test_speaker_pronouns_resolve_to_the_speaker():
    state = FamilyState()
    orchestrator.converse(state, "dadi", "i took my medicine")
    assert state.domains["care"]["checkins"] is not None
    assert any(e["tool"] == "log_medicine_taken" and e["args"]["member_id"] == "dadi" for e in state.events)
    orchestrator.converse(state, "aarav", "i reached school")
    assert any(e["tool"] == "record_arrival" and e["args"]["member_id"] == "aarav" for e in state.events)


# ------------------------------------------------------------------ speech helpers

@pytest.mark.parametrize(
    "spoken,digits",
    [
        ("forty two", "42"), ("twenty one", "21"), ("seven thousand rupees", "7000 rupees"), ("two hundred and fifty", "250"),
        ("a hundred", "100"), ("one thousand eight hundred", "1800"), ("twenty sixth december", "26th december"),
        ("december twenty sixth", "december 26th"), ("the first of december", "the 1st of december"),
        ("at ten thirty", "at 10:30"), ("five thirty pm", "5:30 pm"), ("by nine fifteen am", "by 9:15 am"),
        ("half past ten", "10:30"), ("quarter past nine", "9:15"), ("quarter to five", "4:45"), ("ten o'clock", "10:00"),
        ("at one", "at 1"), ("one pm", "1 pm"), ("three p m", "3 pm"), ("fifty percent", "50 percent"),
        ("forty two out of fifty in maths", "42 out of 50 in maths"), ("a table for four", "a table for 4"),
        ("no one is home", "no one is home"), ("i have one", "i have one"), ("first thing tomorrow", "first thing tomorrow"),
        ("she is six", "she is 6"), ("under seven thousand", "under 7000"), ("nineteen", "19"), ("ninety nine", "99"),
    ],
)
def test_spoken_numbers_become_digits(spoken, digits):
    assert numbers_to_digits(spoken) == digits


@pytest.mark.parametrize(
    "heard,cleaned",
    [
        ("um hey aangan what's on tomorrow", "what's on tomorrow"),
        ("okay so find us a restaurant please", "find us a restaurant"),
        ("uh could you please book it", "could you book it"),
        ("did daddy take her medicines", "did Dadi take her medicines"),
        ("has grandma had her tablets", "has Dadi had her tablets"),
        ("how is arav doing", "how is Aarav doing"),
        ("booked it", "booked it"),
        ("sounds good", "yes sounds good"),
        ("go ahead", "yes go ahead"),
        ("no thanks", "no thanks"),
        ("forget it", "no forget it"),
        ("never mind", "no never mind"),
        ("okay", "okay"),
        ("hello", "hello"),
        ("hello there my flight is delayed", "there my flight is delayed"),
    ],
)
def test_clean_input(heard, cleaned):
    out = clean_input(heard)
    if heard == "booked it":
        assert out == "book it"
    else:
        assert out == cleaned


@pytest.mark.parametrize(
    "text,spoken",
    [
        ("at 13:00", "at one PM"), ("06:20", "six twenty AM"), ("12:00", "noon"), ("00:00", "midnight"),
        ("12:30", "twelve thirty PM"), ("09:05", "nine oh five AM"), ("08:30-09:30", "eight thirty AM to nine thirty AM"),
        ("Rs 1,800", "eighteen hundred rupees"), ("Rs 7,900.", "seven thousand nine hundred rupees."),
        ("Rs 20,400", "twenty thousand four hundred rupees"), ("Rs 900", "nine hundred rupees"),
        ("Sunday 22 Nov", "Sunday the twenty second"), ("2026-11-23", "Monday the twenty third"),
        ("on 26 Dec", "on the twenty sixth of December"), ("6E-6107", "six E six one zero seven"),
        ("AI-544", "A I five four four"), ("PNR K7QX2M", "booking reference K, seven, Q, X, two, M"),
        ("CAB-8841", "Cab number eight eight four one"), ("your cab CAB-8841", "your cab number eight eight four one"),
        ("42/50", "forty two out of fifty"), ("81%", "eighty one percent"), ("500 mg", "five hundred milligrams"),
        ("BLR to DEL", "Bengaluru to Delhi"), ("BLR -> GOI", "Bengaluru to Goa"), ("4 tickets", "four tickets"),
        ("Priya (Mom, 38)", "Priya, Mom, thirty eight"), ("food: pure veg; mild", "food, pure veg, mild"),
        ("2 days left", "two days left"), ("Airport T1", "Airport terminal one"), ("4.5 hours", "four point five hours"),
        ("1 more to go", "One more to go"), ("2026", "twenty twenty six"), ("a & b", "a and b"),
    ],
)
def test_speakable(text, spoken):
    # a reply's first letter is capitalised, so a lower-case fragment comes back with a capital
    assert speakable(text) == spoken[:1].upper() + spoken[1:]


def test_num_to_words_range():
    assert [num_to_words(n) for n in (0, 7, 13, 20, 21, 99, 100, 101, 999, 1000, 1001, 20400, 100000)] == [
        "zero", "seven", "thirteen", "twenty", "twenty one", "ninety nine", "one hundred", "one hundred one",
        "nine hundred ninety nine", "one thousand", "one thousand one", "twenty thousand four hundred", "one lakh",
    ]
