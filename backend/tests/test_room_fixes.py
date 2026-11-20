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
