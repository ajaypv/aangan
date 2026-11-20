"""Found by driving a real Goa conversation through the room: broken words, a one-leg booking, a missing headline."""

import pytest

from app import planner, rooms
from app.main import STATE


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    STATE.reset(demo=True)
    rooms._PLAN_LOCKS.clear()


def offer(frm, to, date, number, price, stops=0):
    return {"airline": "IndiGo", "number": number, "from": frm, "to": to, "date": date, "dep": "07:10", "arr": "08:30", "price": price,
            "per": "person", "stops": stops, "source": "sample", "link": None}


def room_with_trip():
    room = rooms.create_room(STATE, "Goa trip", "priya")
    rid = room["id"]
    rooms.set_destination(STATE, rid, "Goa")
    rooms.set_dates(STATE, rid, "2026-12-26", "2026-12-30")
    out, back = rooms.add_flights(STATE, rid, [offer("BLR", "GOI", "2026-12-26", "6E-512", 4200), offer("GOI", "BLR", "2026-12-30", "6E-513", 4400)])
    hotel = rooms.add_hotels(STATE, rid, [{"name": "Coconut Grove", "area": "Candolim", "price_per_night": 6500, "rating": 4.4, "lat": 15.5, "lon": 73.7,
                                           "step_free": True, "source": "sample"}])[0]
    return rid, out["id"], back["id"], hotel["id"]


def plan_of(rid):
    return rooms.snapshot(STATE, rid)["plan"]


# ---- streamed words join exactly, with a space only between stretches ----


def test_streamed_tokens_join_without_inserted_spaces():
    turn = planner.Turn()
    for piece in ["I ", "have ", "selected ", "the ", "non", "-stop", " flight", " for ", "four", " of you", "."]:
        turn.say(piece)
    assert turn.reply == "I have selected the non-stop flight for four of you."


def test_a_new_round_and_a_hold_phrase_get_one_space_each():
    turn = planner.Turn()
    turn.say("One moment.", answer=False)
    turn.say("Found")
    turn.say(" two")
    turn.new_round()
    turn.say("Pick one.")
    assert turn.reply == "One moment. Found two Pick one."
    assert turn.answered


# ---- "book the flight" means the whole journey ----


def test_proposing_one_flight_includes_the_other_selected_leg():
    rid, out_id, back_id, hotel_id = room_with_trip()
    rooms.choose(STATE, rid, out_id)
    rooms.choose(STATE, rid, back_id)
    pending = rooms.propose_booking(STATE, rid, flight_id=back_id)
    assert pending["items"] == [back_id, out_id]
    assert pending["title"] == "Book 2 flights"  # one traveller in this room, so no head count in the title
    assert pending["amount"] == (4200 + 4400) * rooms.travellers(rooms._room(STATE, rid))
    assert hotel_id not in pending["items"]  # a flight proposal does not drag the hotel in


def test_proposing_with_no_ids_books_everything_selected():
    rid, out_id, back_id, hotel_id = room_with_trip()
    for ref in (out_id, back_id, hotel_id):
        rooms.choose(STATE, rid, ref)
    pending = rooms.propose_booking(STATE, rid)
    assert set(pending["items"]) == {out_id, back_id, hotel_id} and pending["items"][-1] == hotel_id
    done = rooms.decide(STATE, rid, rooms.snapshot(STATE, rid)["host_participant_id"], True)
    assert {b["kind"] for b in done["bookings"]} == {"flight", "hotel"} and len(done["bookings"]) == 3
    assert all(f["status"] == "booked" for f in done["plan"]["flights"])


def test_proposing_with_nothing_selected_is_a_clear_error():
    rid, *_ = room_with_trip()
    with pytest.raises(rooms.RoomError) as err:
        rooms.propose_booking(STATE, rid)
    assert err.value.status == 400 and "nothing is selected" in str(err.value)


def test_a_hotel_alone_is_still_just_the_hotel():
    rid, out_id, back_id, hotel_id = room_with_trip()
    rooms.choose(STATE, rid, out_id)
    pending = rooms.propose_booking(STATE, rid, hotel_id=hotel_id)
    assert pending["items"] == [out_id, hotel_id] or pending["items"] == [hotel_id]


# ---- the board always has a headline ----


def test_setting_the_destination_gives_the_plan_a_goal():
    room = rooms.create_room(STATE, "Trip", "priya")
    assert plan_of(room["id"])["goal"] == ""
    rooms.set_destination(STATE, room["id"], "Goa")
    assert plan_of(room["id"])["goal"] == "Family trip to Goa"
    rooms.set_goal(STATE, room["id"], "Christmas in Goa")
    rooms.set_destination(STATE, room["id"], "Goa")
    assert plan_of(room["id"])["goal"] == "Christmas in Goa"  # the group's own words are never overwritten


# ---- the planner never claims a booking ----


@pytest.mark.parametrize(
    "said,expected",
    [
        ("I've booked the Coconut Grove Resort for your stay.", "I've selected the Coconut Grove Resort for your stay."),
        ("I selected the flight and booked the hotel.", "I selected the flight and selected the hotel."),
        ("We have confirmed the stay.", "We have selected the stay."),
        ("I also reserved a table.", "I also selected a table."),
        ("Nothing is booked yet, the host must approve.", "Nothing is booked yet, the host must approve."),
        ("The host can approve the booking.", "The host can approve the booking."),
    ],
)
def test_a_claim_of_booking_becomes_a_selection(said, expected):
    assert planner.honest(said) == expected


# ---- no duplicate itinerary rows ----


def test_a_hand_added_visit_does_not_duplicate_a_drafted_place():
    rid, *_ = room_with_trip()
    drafted = rooms.add_itinerary_item(STATE, rid, "Basilica of Bom Jesus", day=1, time="16:00", place="Old Goa", kind="place", ref="pl-1")
    again = rooms.add_itinerary_item(STATE, rid, "Visit Basilica of Bom Jesus", day=1, time="16:00", place="Basilica of Bom Jesus")
    assert again["id"] == drafted["id"]
    assert len(plan_of(rid)["itinerary"]) == 1
    other_day = rooms.add_itinerary_item(STATE, rid, "Visit Basilica of Bom Jesus", day=2, time="10:00", place="Old Goa")
    assert other_day["id"] != drafted["id"] and len(plan_of(rid)["itinerary"]) == 2


# ---- found in a real room: the group dropped Goa and the board kept it ----


def test_the_same_decision_said_again_is_recorded_once():
    room = rooms.create_room(STATE, "Trip", "priya")
    first = rooms.record_decision(STATE, room["id"], "We will fly nonstop.")
    again = rooms.record_decision(STATE, room["id"], "we will fly nonstop")
    assert again["id"] == first["id"] and len(plan_of(room["id"])["decisions"]) == 1


def test_dropping_the_destination_clears_it_and_its_unbooked_options():
    rid, out_id, back_id, hotel_id = room_with_trip()
    rooms.choose(STATE, rid, out_id)
    out = rooms.clear_destination(STATE, rid)
    plan = plan_of(rid)
    assert out["cleared"] == "Goa" and plan["destination"] is None and plan["goal"] == ""
    assert plan["flights"] == [] and plan["hotels"] == []


def test_the_planner_can_drop_a_destination_with_a_tool():
    rid, *_ = room_with_trip()
    result = planner.run_tool(planner.Tools(STATE, rid, planner.Turn()), "drop_destination", {})
    assert result == {"cleared": "Goa"} and plan_of(rid)["destination"] is None


def test_a_speaker_talking_over_the_agent_does_not_repeat_their_earlier_words():
    room = rooms.create_room(STATE, "Trip", "priya")
    rid, host = room["id"], room["host_participant_id"]
    first = rooms._voice_message(STATE, rid, host, "I'm not sure about Goa")
    second = rooms._voice_message(STATE, rid, host, "I'm not sure about Goa. We go to Delhi.")
    assert second["text"] == "We go to Delhi." and second["id"] != first["id"]
    other = rooms._voice_message(STATE, rid, host, "Something else entirely")
    assert other["text"] == "Something else entirely"


def test_words_resent_in_front_of_several_earlier_messages_are_still_recognised():
    room = rooms.create_room(STATE, "Trip", "priya")
    rid, host = room["id"], room["host_participant_id"]
    a = rooms._voice_message(STATE, rid, host, "We are three people. Starting from Marathahalli.")
    b = rooms._voice_message(STATE, rid, host, "The budget is under ten k.")
    merged = rooms._voice_message(STATE, rid, host, "We are three people. Starting from Marathahalli. The budget is under ten k.")
    assert merged["id"] == b["id"]  # nothing new: the last message is answered again, no duplicate bubble
    tail = rooms._voice_message(STATE, rid, host, "We are three people, starting from Marathahalli! The budget is under ten k. And why so slow?")
    assert tail["text"] == "And why so slow?" and tail["id"] not in (a["id"], b["id"])
    texts = [m["text"] for m in rooms.snapshot(STATE, rid)["messages"] if m["kind"] == "user"]
    assert len(texts) == 3



def test_changing_the_destination_drops_booked_items_from_the_plan_but_not_from_bookings():
    rid, out_id, back_id, hotel_id = room_with_trip()
    for ref in (out_id, back_id, hotel_id):
        rooms.choose(STATE, rid, ref)
    rooms.propose_booking(STATE, rid)
    done = rooms.decide(STATE, rid, rooms.snapshot(STATE, rid)["host_participant_id"], True)
    assert len(done["bookings"]) == 3
    rooms.add_itinerary_item(STATE, rid, "Relax at Baga Beach", day=2, time="10:00", place="Baga Beach")
    rooms.set_destination(STATE, rid, "Jaipur")
    plan = plan_of(rid)
    assert plan["flights"] == [] and plan["hotels"] == [] and plan["itinerary"] == []
    assert plan["cost_summary"]["by_category"]["flights"] == 0 and plan["cost_summary"]["by_category"]["stay"] == 0
    assert len(rooms.snapshot(STATE, rid)["bookings"]) == 3  # the record of what was booked stays


def test_a_new_destination_updates_the_automatic_headline_and_answers_the_where_questions():
    room = rooms.create_room(STATE, "Trip", "priya")
    rid = room["id"]
    rooms.set_destination(STATE, rid, "Goa")
    rooms.add_open_question(STATE, rid, "What specific places in North India are you considering for the trip?")
    rooms.add_open_question(STATE, rid, "How many hotel rooms do you need?")
    rooms.set_destination(STATE, rid, "Delhi")
    plan = plan_of(rid)
    assert plan["goal"] == "Family trip to Delhi"
    assert [q["resolved"] for q in plan["open_questions"]] == [True, False]
    rooms.set_goal(STATE, rid, "Winter in the north")
    rooms.set_destination(STATE, rid, "Jaipur")
    assert plan_of(rid)["goal"] == "Winter in the north"


def test_the_hold_phrase_is_released_to_the_voice_before_the_tools_finish():
    """The speech grouper only releases a sentence once whitespace follows it; the hold phrase must not wait for the answer."""
    from app import orchestrator

    def pieces():
        yield "One moment. "  # what the planner yields when it sees the first tool call
        raise AssertionError("the answer must not be needed to release the hold phrase")

    grouped = orchestrator._sentences(pieces())
    assert next(grouped) == "One moment."


# ---- found in a real room: old choices and old days kept counting ----


def test_choosing_another_hotel_or_flight_puts_the_earlier_choice_back():
    rid, out_id, back_id, hotel_id = room_with_trip()
    rooms.schedule_item(STATE, rid, hotel_id, 1)  # chosen first: a new search replaces options that are only proposed
    rooms.schedule_item(STATE, rid, out_id)
    second_hotel = rooms.add_hotels(STATE, rid, [{"name": "Palolem Palms", "area": "Palolem", "price_per_night": 4200, "rating": 4.2, "lat": 15.0, "lon": 74.0,
                                                  "step_free": False, "source": "sample"}])[0]["id"]
    other_out = rooms.add_flights(STATE, rid, [offer("BLR", "GOI", "2026-12-26", "6E-977", 6200)])[0]["id"]
    rooms.choose(STATE, rid, second_hotel)
    rooms.choose(STATE, rid, other_out)
    plan = plan_of(rid)
    status = {h["id"]: h["status"] for h in plan["hotels"]} | {f["id"]: f["status"] for f in plan["flights"]}
    assert status[second_hotel] == "selected" and status[hotel_id] == "proposed"
    assert status[other_out] == "selected" and status[out_id] == "proposed"
    assert not [e for e in plan["itinerary"] if e.get("ref") in (hotel_id, out_id)]  # the earlier choices left the itinerary
    assert plan["cost_summary"]["by_category"]["stay"] == 4200 * rooms.nights(plan)  # and only one hotel is counted


def test_shortening_the_trip_drops_old_flights_and_days_and_moves_the_checkout():
    rid, out_id, back_id, hotel_id = room_with_trip()
    for ref in (out_id, back_id, hotel_id):
        rooms.choose(STATE, rid, ref)
    rooms.schedule_item(STATE, rid, hotel_id, 1)
    rooms.schedule_item(STATE, rid, hotel_id, 5)
    rooms.add_itinerary_item(STATE, rid, "Beach day", day=4, time="10:00")
    rooms.set_dates(STATE, rid, "2026-12-26", "2026-12-27")
    plan = plan_of(rid)
    assert [f["id"] for f in plan["flights"]] == [out_id]  # the return flight was for the 30th
    assert max(e["day"] for e in plan["itinerary"]) == 2 and not [e for e in plan["itinerary"] if e["title"] == "Beach day"]
    assert [e["day"] for e in plan["itinerary"] if e["title"].startswith("Check out")] == [2]
    assert rooms.drafted_for(STATE, rid) is None  # a fresh draft will search the missing return flight


def test_a_redraft_after_shortening_searches_only_the_missing_leg(monkeypatch):
    rid, out_id, back_id, hotel_id = room_with_trip()
    for ref in (out_id, back_id, hotel_id):
        rooms.choose(STATE, rid, ref)
    rooms.set_origin(STATE, rid, "Bengaluru")
    rooms.set_travelers(STATE, rid, ["p-1"], 2)
    searched = []

    def fake(origin, destination, date, passengers, limit=5):
        searched.append((origin, destination, date))
        return [offer("GOI", "BLR", date, "6E-900", 4000)], "sample"

    monkeypatch.setattr(planner, "find_flights", fake)
    rooms.set_dates(STATE, rid, "2026-12-26", "2026-12-28")  # the return flight (the 30th) is stale, the outbound stays
    planner.draft_if_ready(STATE, rid)
    plan = plan_of(rid)
    assert searched == [("Goa", "Bengaluru", "2026-12-28")]
    assert {f["date"] for f in plan["flights"] if f["status"] == "selected"} == {"2026-12-26", "2026-12-28"}
    assert sorted({e["day"] for e in plan["itinerary"] if e.get("day")}) == [1, 2, 3]
    assert sum(1 for c in plan["costs"] if c["category"] == "local") == 1
