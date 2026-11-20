import pytest

from app import toolkit
from app.agents.dining import DiningAgent, derive_constraints, search_restaurants
from app.state import FamilyState

LUNCH = "Sunday ko sab saath bahar jaana hai"
EVERYONE = ["priya", "rahul", "aarav", "dadi"]


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr(toolkit.time, "sleep", lambda s: None)


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agent():
    return DiningAgent()


def tools_used(state):
    return [(e["agent"], e["tool"], e["status"]) for e in state.events if e["agent"] == "dining"]


def test_constraints_come_from_memory(state):
    c = derive_constraints(state, EVERYONE)
    assert c["nut_free"] == ["aarav"] and c["veg_only"] == ["dadi"] and c["step_free"] == ["dadi"]
    assert c["mild_spice"] == ["dadi"] and c["kid_friendly"] == ["aarav"]
    assert c["max_total"] == 3000 and c["dinner_cutoff"] == "20:00"
    assert derive_constraints(state, ["priya", "rahul"])["nut_free"] == []


def test_hinglish_request_proposes_udupi_with_reasons(state, agent):
    reply = agent.handle(state, "priya", LUNCH)
    assert "Udupi Garden" in reply and "13:00" in reply
    assert "Aarav ke liye nut-free" in reply and "Dadi ke liye pure veg, step-free" in reply
    assert "4" in reply and "book kar doon" in reply
    assert state.pending["agent"] == "dining" and state.pending["proposal"]["restaurant_id"] == "r1"
    assert ("dining", "search_restaurants", "ok") in tools_used(state)


def test_english_request_proposes_with_cost_and_day(state, agent):
    reply = agent.handle(state, "rahul", "Let's all go out for lunch on Sunday")
    assert reply.startswith("Udupi Garden on Sunday 22 Nov at 13:00")
    assert "nut-free and kid-friendly for Aarav" in reply and "pure veg, step-free and mild spice for Dadi" in reply
    assert "all 4 of you are free" in reply and "Rs 1,800" in reply and "assuming" not in reply


def test_date_assumed_when_missing(state, agent):
    reply = agent.handle(state, "rahul", "book a table for the family")
    assert "assuming Sunday" in reply and "Udupi Garden" in reply


def test_confirm_books_calendar_pickup_and_notifies(state, agent):
    agent.handle(state, "priya", LUNCH)
    reply = agent.handle(state, "priya", "haan book kar do")
    assert "Ho gaya" in reply and "Udupi Garden" in reply and "12:15" in reply
    assert state.pending is None

    res = state.domains["dining"]["reservations"]
    assert len(res) == 1 and res[0]["status"] == "CONFIRMED" and res[0]["time"] == "13:00" and res[0]["end"] == "14:30"
    event = next(e for e in state.calendar if e["source"] == "dining")
    assert event["kind"] == "dining" and event["member_ids"] == EVERYONE and (event["start"], event["end"]) == ("13:00", "14:30")
    assert res[0]["event_id"] == event["id"]
    pickup = state.domains["dining"]["pickups"][0]
    assert pickup["member_id"] == "dadi" and pickup["pickup"] == "12:15" and pickup["status"] == "CONFIRMED"
    note = state.notifications[-1]
    assert note["kind"] == "dining" and note["to"] == EVERYONE and "Udupi Garden" in note["text"]
    used = {t for _, t, _ in tools_used(state)}
    assert {"search_restaurants", "book_table", "add_calendar_event", "arrange_pickup", "notify_family"} <= used
    assert state.stage == "after"


def test_english_confirm(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "yes please book it")
    assert reply.startswith("Done: table for 4 at Udupi Garden") and "Agora Chat" in reply


def test_chaos_falls_back_to_next_slot_and_says_so(state, agent):
    state.chaos = True
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "yes")
    assert ("dining", "book_table", "error") in tools_used(state) and ("dining", "book_table", "ok") in tools_used(state)
    assert "was just taken" in reply and "instead" in reply
    res = state.domains["dining"]["reservations"]
    assert len(res) == 1 and res[0]["time"] != "13:00"


def test_dinner_has_no_pure_veg_match_so_offers_closest_with_issues(state, agent):
    reply = agent.handle(state, "rahul", "dinner on Sunday for everyone")
    assert "Olive Courtyard" in reply and "19:30" in reply
    assert "isn't a pure-veg kitchen" in reply and "over your Rs 3,000 budget" in reply
    assert state.pending["proposal"]["violations"] == ["veg_only", "budget"]
    assert "Coastal Spice" not in reply  # 20:00 start is past Dadi's 8 pm dinner cutoff


def test_cheaper_keeps_access_over_price_and_says_so(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "something cheaper")
    assert "already the cheapest" in reply and "step-free" in reply
    assert state.pending["proposal"]["restaurant_id"] == "r1"


def test_naming_a_cheaper_place_with_stairs_is_allowed_with_caveat(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "what about Green Leaf Thali House")
    assert "Green Leaf Thali House" in reply and "has stairs" in reply
    assert state.pending["proposal"]["restaurant_id"] == "r4"


def test_italian_instead_closest_is_continental(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "no, Italian instead")
    assert "Olive Courtyard" in reply and "isn't a pure-veg kitchen" in reply
    assert state.pending["proposal"]["restaurant_id"] == "r6"


def test_play_area_request(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "somewhere with a play area")
    assert "Olive Courtyard" in reply and "isn't a pure-veg kitchen" in reply


def test_earlier_then_earliest_note(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    first = agent.handle(state, "rahul", "can we go earlier")
    assert "12:30" in first and state.pending["proposal"]["time"] == "12:30"
    second = agent.handle(state, "rahul", "even earlier")
    assert "earliest slot" in second


def test_another_place_excludes_current(state, agent):
    agent.handle(state, "priya", "lunch on Sunday for everyone")
    reply = agent.handle(state, "priya", "somewhere else")
    assert "Udupi Garden" not in reply.split(":")[0] and state.pending["proposal"]["restaurant_id"] != "r1"


def test_reject_clears_pending(state, agent):
    agent.handle(state, "priya", LUNCH)
    reply = agent.handle(state, "priya", "nahi rehne do")
    assert state.pending is None and "kuch book nahi" in reply
    assert state.domains["dining"]["reservations"] == []


def test_unclear_reply_re_asks(state, agent):
    agent.handle(state, "rahul", "lunch on Sunday for everyone")
    reply = agent.handle(state, "rahul", "hmm")
    assert "Shall I book Udupi Garden" in reply and state.pending is not None


def test_named_restaurant_gets_proposed_with_caveats(state, agent):
    reply = agent.handle(state, "rahul", "book Olive Courtyard on Sunday for lunch")
    assert "Olive Courtyard" in reply and "isn't a pure-veg kitchen" in reply


def test_subset_party_includes_speaker_and_mentioned(state, agent):
    agent.handle(state, "priya", "lunch on Sunday with Dadi")
    assert state.pending["filters"]["attendees"] == ["priya", "dadi"]
    assert state.pending["filters"]["party_size"] == 2


def test_explicit_party_size(state, agent):
    agent.handle(state, "priya", "table for 6 on Sunday lunch")
    assert state.pending["filters"]["party_size"] == 6


def test_no_common_time_suggests_another_day(state, agent):
    state.calendar.append({"id": "x", "title": "Busy", "member_ids": ["aarav"], "date": "2026-11-22", "start": "12:00",
                           "end": "15:30", "location": "", "kind": "event", "source": "test"})
    reply = agent.handle(state, "rahul", "lunch on Sunday for everyone")
    assert "no lunch window" in reply and "Wednesday 25 Nov works" in reply  # Mon/Tue are school days
    assert state.pending is None


def test_no_tables_on_other_dates(state, agent):
    reply = agent.handle(state, "rahul", "lunch on Saturday for everyone")
    assert "don't see any open tables" in reply and state.pending is None


def test_cancel_reservation_clears_calendar_and_pickup(state, agent):
    agent.handle(state, "priya", LUNCH)
    agent.handle(state, "priya", "haan book kar do")
    reply = agent.handle(state, "priya", "cancel the lunch reservation")
    assert "Udupi Garden ki table cancel" in reply
    assert state.domains["dining"]["reservations"][0]["status"] == "CANCELLED"
    assert not [e for e in state.calendar if e["source"] == "dining"]
    assert state.domains["dining"]["pickups"][0]["status"] == "CANCELLED"
    assert agent.handle(state, "priya", "cancel the lunch reservation").startswith("Cancel karne ke liye")


def test_a_booked_outing_blocks_the_same_window(state, agent):
    agent.handle(state, "priya", LUNCH)
    agent.handle(state, "priya", "haan")
    reply = agent.handle(state, "rahul", "lunch on Sunday for everyone")
    assert "no lunch window" in reply and state.pending is None


def test_search_tool_never_offers_a_non_nut_free_place(state):
    res = search_restaurants(state, "2026-11-22", 4, ["13:00", "13:30", "19:30"], nut_free=True, veg_only=True, step_free=True)
    names = [e["name"] for e in res["matches"] + res["closest"]]
    assert "Bangkok Wok" not in names and "Punjabi Tadka" not in names
    assert res["rejected"]["nut_free"] >= 1


def test_score_ownership(state, agent):
    for text in ("lunch on Sunday", "Sunday ko sab saath bahar jaana hai", "book a table for the family", "any good restaurant?"):
        assert agent.score(state, text) >= 3, text
    for text in ("when is everyone free on Sunday", "my flight is delayed", "Dadi ki dawai khatam ho gayi",
                 "Aarav got 42 out of 50", "check the timetable", "remember Dadi likes lunch early", "hello"):
        assert agent.score(state, text) == 0, text


def test_unrelated_text_returns_none(state, agent):
    assert agent.handle(state, "priya", "what is on my calendar tomorrow") is None
    assert state.pending is None


def test_tools_have_full_schemas(agent):
    names = {t.name for t in agent.tools}
    assert names == {"search_restaurants", "book_table", "add_calendar_event", "arrange_pickup", "cancel_reservation", "notify_family"}
    for t in agent.tools:
        assert t.parameters["type"] == "object" and t.parameters["properties"] and t.description
    assert agent.tool("notify_family").stage == "after"
