"""The room planner: cost summary maths, the places / restaurants / scheduling tools, household needs, flight choice
and the proactive first draft. Offline: the model is scripted, live flight search is faked or off."""

import json
import sys
import warnings
from types import SimpleNamespace

import pytest

from app import planner, rooms
from app.state import STATE

warnings.filterwarnings("ignore")
REAL_LIVE_SEARCH = planner._live_search  # the wrapper itself, before the autouse fixture replaces it


# ---- scripted model helpers (same chunk shapes the gateway sends) ----


def delta(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=calls))])


def tool_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def calls_round(*calls):
    chunks = []
    for i, (name, args) in enumerate(calls):
        raw = json.dumps(args)
        half = len(raw) // 2
        chunks.append(delta(calls=[tool_delta(i, id=f"c{i}", name=name, arguments=raw[:half])]))
        chunks.append(delta(calls=[tool_delta(i, arguments=raw[half:])]))
    return chunks


class StreamClient:
    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        return iter(self.rounds.pop(0) if len(self.rounds) > 1 else self.rounds[0])


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    STATE.reset(demo=True)
    rooms._PLAN_LOCKS.clear()
    monkeypatch.setattr(planner, "_live_search", lambda *a, **k: [])
    monkeypatch.setattr(rooms, "spawn", lambda fn, *a, **k: fn(*a, **k))


def make_room(member="priya"):
    return rooms.create_room(STATE, "Goa trip", member)["id"]


def tools_for(rid):
    turn = planner.Turn()
    return planner.Tools(STATE, rid, turn), turn


def run(tools, tool, **args):
    return planner.run_tool(tools, tool, args)


def plan_of(rid):
    return rooms.snapshot(STATE, rid)["plan"]


def set_trip(tools, travellers=4, budget=None):
    run(tools, "set_origin", name="Bengaluru")
    run(tools, "set_destination", name="Goa")
    run(tools, "set_dates", start="2026-12-26", end="2026-12-30")
    run(tools, "set_travelers", participant_ids=["p-1"], count=travellers)
    if budget:
        run(tools, "set_budget", total=budget)


def offer(number, price, stops=0, frm="BLR", to="GOI", date="2026-12-26", source="sample", airline="IndiGo"):
    return {"airline": airline, "number": number, "from": frm, "to": to, "date": date, "dep": "07:10", "arr": "08:30", "price": price,
            "stops": stops, "source": source, "link": None}


# ---- the derived cost summary ----


def test_cost_summary_adds_up_what_is_chosen_and_explicit_lines():
    rid = make_room()
    tools, _ = tools_for(rid)
    set_trip(tools, travellers=4, budget=80000)
    rooms.add_flights(STATE, rid, [offer("6E-512", 4200), offer("QP-1127", 3900)])
    assert plan_of(rid)["cost_summary"]["by_category"]["flights"] == 3900 * 4  # nothing chosen: the cheapest proposed one
    assert plan_of(rid)["cost_summary"]["estimate"] is True
    rooms.choose(STATE, rid, "f-1")
    rooms.add_hotels(STATE, rid, [{"name": "Cheap Inn", "area": "Baga", "price_per_night": 5000, "rating": 4.0, "lat": 15.5, "lon": 73.7, "step_free": False},
                                  {"name": "Grove", "area": "Candolim", "price_per_night": 6500, "rating": 4.4, "lat": 15.5, "lon": 73.7, "step_free": True}])
    assert plan_of(rid)["cost_summary"]["by_category"]["stay"] == 5000 * 4  # cheapest proposed until one is chosen
    rooms.choose(STATE, rid, "h-2")
    rooms.add_places(STATE, rid, [{"name": "Fort", "area": "Candolim", "category": "sight", "lat": 15.4, "lon": 73.7, "duration_min": 60, "price": 100,
                                   "per": "person", "day": None, "notes": "", "source": "sample", "status": "proposed"},
                                  {"name": "Beach", "area": "Baga", "category": "beach", "lat": 15.5, "lon": 73.7, "duration_min": 60, "price": 0,
                                   "per": "person", "day": None, "notes": "", "source": "sample", "status": "proposed"}])
    rooms.schedule_item(STATE, rid, "pl-1", 2)
    rooms.add_restaurants(STATE, rid, [{"name": "Thali House", "cuisine": "Thali", "area": "Candolim", "meal": "lunch", "day": None, "date": None, "time": None,
                                        "price_for_two": 900, "veg_only": True, "veg_options": True, "lat": 15.5, "lon": 73.7, "notes": "", "source": "sample",
                                        "status": "proposed"}])
    rooms.schedule_item(STATE, rid, "r-1", 2)
    rooms.add_cost(STATE, rid, "Local transport", 5000, category="local", day=3)
    rooms.add_cost(STATE, rid, "Souvenirs", 2000, category="nonsense")
    s = plan_of(rid)["cost_summary"]
    assert s["by_category"] == {"flights": 16800, "stay": 26000, "food": 1800, "activities": 400, "local": 5000, "other": 2000}
    assert s["total"] == 52000 and s["travellers"] == 4 and s["per_person"] == 13000 and s["currency"] == "INR"
    assert s["budget"] == 80000 and s["remaining"] == 28000 and s["over_budget"] is False
    days = {d["day"]: d for d in s["by_day"]}
    assert sorted(days) == [1, 2, 3, 4, 5] and days[1]["date"] == "2026-12-26" and days[5]["date"] == "2026-12-30"
    assert days[1]["amount"] == 16800 + 6500  # the flight and the first night
    assert days[2]["amount"] == 6500 + 400 + 1800  # a night, the fort for four, lunch for four (price for two x 4 / 2)
    assert days[3]["amount"] == 6500 + 5000 and days[4]["amount"] == 6500 and days[5]["amount"] == 0
    assert {l["label"] for l in s["lines"]} >= {"IndiGo 6E-512 x 4", "Grove x 4 nights", "Thali House", "Fort", "Local transport"}
    rooms.set_budget(STATE, rid, 50000)
    over = plan_of(rid)["cost_summary"]
    assert over["over_budget"] is True and over["remaining"] == -2000


def test_cost_summary_follows_the_group_size_and_rooms_and_is_never_stored():
    rid = make_room()
    tools, _ = tools_for(rid)
    set_trip(tools, travellers=2)
    rooms.add_flights(STATE, rid, [offer("6E-512", 4000)])
    rooms.add_hotels(STATE, rid, [{"name": "Grove", "area": "x", "price_per_night": 1000, "rating": 4.0, "lat": 1, "lon": 1, "step_free": True}])
    assert plan_of(rid)["cost_summary"]["total"] == 8000 + 4000
    run(tools, "set_travelers", count=6, hotel_rooms=2)
    s = plan_of(rid)["cost_summary"]
    assert s["travellers"] == 6 and s["by_category"]["flights"] == 24000 and s["by_category"]["stay"] == 8000 and s["per_person"] == 5333
    assert "cost_summary" not in STATE.rooms[rid]["plan"]  # derived on every read, never written
    empty = plan_of(make_room())["cost_summary"]
    assert empty["total"] == 0 and empty["budget"] is None and empty["remaining"] is None and empty["over_budget"] is False and empty["travellers"] == 1


def test_a_booked_flight_is_no_longer_an_estimate():
    rid = make_room()
    tools, _ = tools_for(rid)
    set_trip(tools, travellers=2)
    rooms.add_flights(STATE, rid, [offer("6E-512", 4000)])
    rooms.propose_booking(STATE, rid, flight_id="f-1")
    rooms.decide(STATE, rid, "p-1", True)
    s = plan_of(rid)["cost_summary"]
    assert s["by_category"]["flights"] == 8000 and s["estimate"] is False and s["lines"][0]["estimate"] is False


# ---- places, restaurants, household needs ----


def test_household_memory_steers_places_and_restaurants():
    rid = make_room()
    rooms.join(STATE, rid, member_id="dadi")
    rooms.add_user_message(STATE, rid, "p-1", "Aarav is coming too")  # a household member named in the chat counts
    tools, turn = tools_for(rid)
    needs = rooms.family_needs(STATE, rid)
    assert needs["step_free"] == ["Dadi"] and needs["veg"] == ["Dadi"] and needs["allergies"] == [("Aarav", "Severe peanut allergy")]
    rooms.sync_family_needs(STATE, rid)  # the planner does this at the start of every turn
    assert {"Dadi: Pure vegetarian", "Dadi: Bad knees: needs step-free access, no stairs", "Aarav: Severe peanut allergy"} <= set(plan_of(rid)["preferences"])
    out = run(tools, "search_places", city="Goa")
    assert out["places"][0]["notes"].startswith("Step-free.") and out["note"].startswith("SAMPLE")
    assert any("Steps or uneven ground, tricky for Dadi." in p["notes"] for p in out["places"])
    stepfree = [p for p in out["places"] if p["notes"].startswith("Step-free.")]
    assert out["places"][: len(stepfree)] == stepfree  # step-free places lead
    foods = run(tools, "search_restaurants", city="Goa", meal="lunch")["restaurants"]
    assert foods and all(r["notes"].startswith(("Pure veg", "Vegetarian options")) for r in foods)
    assert all("Tell the staff about Aarav: severe peanut allergy" in r["notes"] for r in foods)
    assert foods[0]["veg_only"] is True  # pure vegetarian places first
    assert turn.changes["places"] and turn.changes["restaurants"]
    assert all(p["source"] == "sample" for p in plan_of(rid)["places"] + plan_of(rid)["restaurants"])


def test_without_household_needs_notes_stay_plain_and_filters_work():
    rid = make_room("rahul")
    tools, _ = tools_for(rid)
    beach = run(tools, "search_places", city="Goa", interests=["beach"])["places"]
    assert beach[0]["category"] == "beach" and not beach[0]["notes"].startswith("Step-free")
    veg = run(tools, "search_restaurants", city="Delhi", meal="dinner", veg_only=True)["restaurants"]
    assert veg and all("Mughlai" != r["cuisine"] or r["veg_only"] is False for r in veg)
    cheap = run(tools, "search_restaurants", city="Goa", budget_for_two=800)["restaurants"]
    assert cheap and all(r["price_for_two"] <= 800 for r in cheap)
    assert "no place data" in run(tools, "search_places", city="Atlantis")["note"]
    assert "error" in run(tools, "search_places")  # no city and no destination yet
    run(tools, "set_destination", name="Jaipur")
    assert run(tools, "search_places")["places"][0]["area"]  # defaults to the destination


def test_select_and_schedule_build_the_itinerary_with_costs():
    rid = make_room()
    tools, turn = tools_for(rid)
    set_trip(tools, travellers=4)
    places = run(tools, "search_places", city="Goa")["places"]
    foods = run(tools, "search_restaurants", city="Goa", meal="dinner")["restaurants"]
    paid = next(p for p in places if p["price"] > 0)
    out = run(tools, "select_place", place_id=paid["id"], day=2, time="10:30")
    assert out["day"] == 2 and out["time"] == "10:30"
    run(tools, "select_restaurant", restaurant_id=foods[0]["id"], day=2)
    flight = rooms.add_flights(STATE, rid, [offer("6E-512", 4200)])[0]
    run(tools, "schedule_item", ref=flight["id"])  # a flight's day comes from its date
    hotel = rooms.add_hotels(STATE, rid, [{"name": "Grove", "area": "Candolim", "price_per_night": 6500, "rating": 4.4, "lat": 15.5, "lon": 73.7, "step_free": True}])[0]
    run(tools, "schedule_item", ref=hotel["id"], day=1)
    plan = plan_of(rid)
    by_ref = {e["ref"]: e for e in plan["itinerary"]}
    assert by_ref[paid["id"]]["kind"] == "place" and by_ref[paid["id"]]["cost"] == paid["price"] * 4 and by_ref[paid["id"]]["date"] == "2026-12-27"
    food = by_ref[foods[0]["id"]]
    assert food["kind"] == "food" and food["time"] == "19:30" and food["title"].startswith("Dinner at") and food["cost"] == round(foods[0]["price_for_two"] * 4 / 2)
    assert by_ref[flight["id"]]["kind"] == "travel" and by_ref[flight["id"]]["day"] == 1 and by_ref[flight["id"]]["cost"] == 4200 * 4
    assert by_ref[hotel["id"]]["kind"] == "stay" and by_ref[hotel["id"]]["title"] == "Check in at Grove" and by_ref[hotel["id"]]["cost"] is None
    assert [e["day"] for e in plan["itinerary"]] == sorted(e["day"] for e in plan["itinerary"])
    assert next(p for p in plan["places"] if p["id"] == paid["id"])["status"] == "selected" and next(p for p in plan["places"] if p["id"] == paid["id"])["day"] == 2
    # the group size changes: itinerary prices follow
    run(tools, "set_travelers", count=2)
    assert {e["ref"]: e for e in plan_of(rid)["itinerary"]}[paid["id"]]["cost"] == paid["price"] * 2
    # rejecting takes it off the day again
    run(tools, "select_place", place_id=paid["id"], reject=True)
    assert paid["id"] not in {e["ref"] for e in plan_of(rid)["itinerary"]}
    assert "error" in run(tools, "schedule_item", ref=paid["id"], day=2)  # rejected: it must be selected again first
    assert "error" in run(tools, "schedule_item", ref="pl-999", day=1) and "error" in run(tools, "schedule_item", ref=foods[1]["id"])


def test_own_itinerary_items_and_cost_lines():
    rid = make_room()
    tools, _ = tools_for(rid)
    set_trip(tools)
    item = run(tools, "add_itinerary_item", title="Sunset at Chapora", day=3, time="17:45", place="Vagator", lat=15.6063, lon=73.7358, notes="Bring jackets")
    assert item["date"] == "2026-12-28" and item["kind"] == "other" and item["ref"] is None and item["time"] == "17:45"
    by_date = run(tools, "add_itinerary_item", title="Check ferry times", date="2026-12-27")
    assert by_date["day"] == 2 and "error" in run(tools, "add_itinerary_item", title="Nowhere")
    run(tools, "add_cost", label="Cabs", amount=3000, category="local")
    run(tools, "add_cost", label="Cabs", amount=3500, category="local")  # the same label updates the line
    assert [(c["label"], c["amount"], c["category"]) for c in plan_of(rid)["costs"]] == [("Cabs", 3500, "local")]
    run(tools, "set_dates", start="2027-01-02", end="2027-01-04")  # same days, new calendar dates
    assert next(e for e in plan_of(rid)["itinerary"] if e["title"] == "Sunset at Chapora")["date"] == "2027-01-04"


def test_changing_the_destination_drops_the_old_one_but_keeps_bookings():
    rid = make_room()
    tools, _ = tools_for(rid)
    set_trip(tools, travellers=2)
    rooms.add_flights(STATE, rid, [offer("6E-512", 4200), offer("QP-1127", 3900)])
    rooms.propose_booking(STATE, rid, flight_id="f-1")
    rooms.decide(STATE, rid, "p-1", True)
    run(tools, "search_places", city="Goa")
    run(tools, "set_destination", name="Manali")
    plan = plan_of(rid)
    assert plan["destination"]["name"] == "Manali" and plan["places"] == [] and [f["status"] for f in plan["flights"]] == ["booked"]
    assert rooms.drafted_for(STATE, rid) is None


# ---- flights: live, sample, non-stop preference ----


def test_nonstop_wins_when_the_price_gap_is_small_and_loses_when_it_is_big():
    small = [offer("A-1", 3000, stops=1), offer("A-2", 4200, stops=0), offer("A-3", 3500, stops=1)]
    assert planner.rank_flights(small)[0]["number"] == "A-2"  # 1,200 more, under the 1,500 premium
    assert [f["number"] for f in planner.rank_flights(small)] == ["A-2", "A-1", "A-3"]
    big = [offer("B-1", 3000, stops=1), offer("B-2", 5000, stops=0)]
    assert planner.rank_flights(big)[0]["number"] == "B-1"
    edge = [offer("C-1", 3000, stops=1), offer("C-2", 4500, stops=0)]
    assert planner.rank_flights(edge)[0]["number"] == "C-1"  # exactly 1,500 more is no longer "small"
    assert planner.rank_flights([]) == []


def live_offers(frm, to, date, passengers, limit):
    return [
        {"airline": "Akasa Air", "number": "QP-9", "from": frm, "to": to, "date": date, "dep": "06:00", "arr": "10:30", "price": 3100, "per": "person",
         "stops": 1, "source": "live", "link": "https://example.test/book", "route": f"{frm}-HYD-{to}", "duration_min": 270},
        {"airline": "IndiGo", "number": "6E-77", "from": frm, "to": to, "date": date, "dep": "07:00", "arr": "08:25", "price": 4300, "per": "person",
         "stops": 0, "source": "live", "link": None},
    ]


def test_live_flights_are_used_and_labelled_live_with_nonstop_preferred(monkeypatch):
    seen = []
    monkeypatch.setattr(planner, "_live_search", lambda o, d, date, n, limit: seen.append((o, d, date, n)) or live_offers(o, d, date, n, limit))
    rid = make_room()
    tools, turn = tools_for(rid)
    set_trip(tools, travellers=3)
    out = run(tools, "search_flights")
    assert seen == [("BLR", "GOI", "2026-12-26", 3)] and out["source"] == "live" and out["note"] == "These are live prices."
    assert [f["number"] for f in out["flights"]] == ["6E-77", "QP-9"] and out["recommended"] == out["flights"][0]["id"]
    flights = plan_of(rid)["flights"]
    assert {f["source"] for f in flights} == {"live"} and flights[0]["link"] is None and flights[1]["link"] == "https://example.test/book"
    assert all(f["status"] == "proposed" and f["per"] == "person" for f in flights) and turn.changes["flights"] == 2
    run(tools, "search_flights")  # the same search again does not list anything twice
    assert len(plan_of(rid)["flights"]) == 2


def test_without_live_data_the_family_catalogue_then_a_built_in_set_are_used_as_sample():
    rid = make_room()
    tools, _ = tools_for(rid)
    out = run(tools, "search_flights", origin="Bangalore", destination="Goa", date="2026-12-26", passengers=2)
    assert out["source"] == "sample" and "SAMPLE" in out["note"]
    assert {f["number"] for f in out["flights"]} == {"6E-512", "AI-544", "QP-1127"} and all(f["source"] == "sample" for f in out["flights"])  # the catalogue
    other = run(tools, "search_flights", origin="Mumbai", destination="Jaipur", date="2026-12-27")
    assert len(other["flights"]) == 3 and all(f["source"] == "sample" and f["from"] == "BOM" and f["to"] == "JAI" for f in other["flights"])
    assert run(tools, "search_flights", origin="Atlantis", destination="Goa", date="2026-12-26")["flights"] == []
    assert "error" in run(tools, "search_flights")  # nothing known yet


def test_a_missing_or_failing_live_module_means_no_live_data(monkeypatch):
    from app import live_flights

    monkeypatch.setattr(live_flights, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert REAL_LIVE_SEARCH("BLR", "GOI", "2026-12-26", 1, 5) == []
    monkeypatch.setattr(live_flights, "search", lambda *a, **k: None)
    assert REAL_LIVE_SEARCH("BLR", "GOI", "2026-12-26", 1, 5) == []
    import app

    monkeypatch.delattr(app, "live_flights", raising=False)
    monkeypatch.setitem(sys.modules, "app.live_flights", None)
    assert REAL_LIVE_SEARCH("BLR", "GOI", "2026-12-26", 1, 5) == []  # ImportError: another engineer's module is not there


def test_malformed_live_offers_are_dropped(monkeypatch):
    monkeypatch.setattr(planner, "_live_search", lambda *a, **k: [{"airline": "X"}, "junk", {**offer("Z-1", 0, source="live")}, offer("Y-2", 3000, source="live")])
    offers, source = planner.find_flights("BLR", "GOI", "2026-12-26", 1)
    assert source == "live" and [f["number"] for f in offers] == ["Y-2"]


# ---- the proactive first draft ----


def full_script(extra=()):
    return StreamClient(
        calls_round(("set_origin", {"name": "Bengaluru"}), ("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "end": "2026-12-30"}),
                    ("set_travelers", {"participant_ids": ["p-1"], "count": 4}), *extra),
        [],
    )


class ModelSlot:
    """The scripted model for the next planning turns: `model.append(client)` replaces the one in use."""

    current = None

    def append(self, client):
        self.current = client


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    slot = ModelSlot()
    monkeypatch.setattr(planner, "_client", lambda: slot.current)
    return slot


def say(rid, text, pid="p-1"):
    msg = rooms.add_user_message(STATE, rid, pid, text)
    planner.plan_after_message(STATE, rid, msg["id"])


def test_once_destination_dates_and_travellers_are_known_aangan_drafts_a_whole_plan(model):
    rid = make_room()
    model.append(full_script())
    say(rid, "Goa from Bengaluru, 26 to 30 December, four of us")
    room = rooms.snapshot(STATE, rid)
    plan = room["plan"]
    legs = {(f["from"], f["to"], f["date"]) for f in plan["flights"]}
    assert {("BLR", "GOI", "2026-12-26"), ("GOI", "BLR", "2026-12-30")} <= legs
    assert sorted(f["date"] for f in plan["flights"] if f["status"] == "selected") == ["2026-12-26", "2026-12-30"]
    assert [h["status"] for h in plan["hotels"]].count("selected") == 1
    entries = plan["itinerary"]
    assert {e["kind"] for e in entries} >= {"travel", "stay", "place", "food"}
    per_day = {d: [e for e in entries if e["day"] == d] for d in range(1, 6)}
    for day in (2, 3, 4):
        kinds = [e["kind"] for e in per_day[day]]
        assert kinds.count("place") >= 2 and kinds.count("food") == 2, (day, kinds)  # places, a lunch and a dinner
    assert [e["kind"] for e in per_day[1]].count("place") >= 1 and not any(e["title"].startswith("Dinner") for e in per_day[5])
    titles = [(e["ref"], e["title"]) for e in entries]
    assert len(titles) == len(set(titles))  # nothing was scheduled twice
    assert all(e["time"] for e in entries) and [e["day"] for e in entries] == sorted(e["day"] for e in entries)
    assert all(p["source"] == "sample" for p in plan["places"] + plan["restaurants"] + plan["hotels"] + plan["flights"])
    assert any(c["category"] == "local" for c in plan["costs"])
    summary = plan["cost_summary"]
    assert summary["total"] > 0 and summary["travellers"] == 4 and summary["by_category"]["flights"] > 0 and summary["by_category"]["stay"] > 0
    assert summary["by_category"]["food"] > 0 and summary["by_category"]["local"] > 0
    assert room["bookings"] == [] and room["pending_approval"] is None  # a draft is not a booking
    assert not [x for x in plan["flights"] + plan["hotels"] if x["status"] == "booked"]
    note = room["messages"][-1]
    assert note["kind"] == "system" and note["text"].startswith("Aangan drafted a first plan") and "nothing booked" in note["text"]
    assert any(q["text"] == "How many hotel rooms do you need?" for q in plan["open_questions"])


def test_a_draft_happens_once_and_later_messages_refine_instead(model):
    rid = make_room()
    model.append(full_script())
    say(rid, "Goa from Bengaluru, 26 to 30 December, four of us")
    count = len(plan_of(rid)["itinerary"])
    model.append(StreamClient(calls_round(("add_checklist_item", {"text": "Book the airport cab"})), []))
    say(rid, "we need a cab to the airport")
    room = rooms.snapshot(STATE, rid)
    assert len(room["plan"]["itinerary"]) == count
    assert len([m for m in room["messages"] if m["text"].startswith("Aangan drafted")]) == 1
    assert "Book the airport cab" in [c["text"] for c in room["plan"]["checklist"]]


def test_no_draft_until_all_three_are_known_and_missing_origin_becomes_a_question(model):
    rid = make_room()
    model.append(StreamClient(calls_round(("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "nights": 4})), []))
    say(rid, "Goa from the 26th")
    assert plan_of(rid)["flights"] == [] and plan_of(rid)["hotels"] == []  # who is going is not known yet
    model.append(StreamClient(calls_round(("set_travelers", {"participant_ids": ["p-1"]})), []))
    say(rid, "just me")
    plan = plan_of(rid)
    assert plan["hotels"] and plan["itinerary"] and plan["flights"] == []  # no origin: no flights, and the planner asks
    assert any(q["text"] == "Which city are you flying from?" for q in plan["open_questions"])


def test_the_draft_prefers_a_nonstop_flight_when_it_costs_little_more(monkeypatch, model):
    def live(o, d, date, n, limit):
        return [offer("CONN-1", 3000, stops=1, frm=o, to=d, date=date, source="live"), offer("NON-1", 4400, stops=0, frm=o, to=d, date=date, source="live")]

    monkeypatch.setattr(planner, "_live_search", live)
    rid = make_room()
    model.append(full_script())
    say(rid, "Goa please")
    chosen = [f for f in plan_of(rid)["flights"] if f["status"] == "selected"]
    assert [f["number"] for f in chosen] == ["NON-1", "NON-1"] and {f["source"] for f in chosen} == {"live"}
    monkeypatch.setattr(planner, "_live_search", lambda o, d, date, n, limit: [offer("CONN-1", 3000, stops=1, frm=o, to=d, date=date, source="live"),
                                                                              offer("NON-1", 5200, stops=0, frm=o, to=d, date=date, source="live")])
    rid2 = make_room()
    model.append(full_script())
    say(rid2, "Goa please")
    assert [f["number"] for f in plan_of(rid2)["flights"] if f["status"] == "selected"] == ["CONN-1", "CONN-1"]


def test_the_draft_stays_near_the_budget_and_uses_step_free_places_for_dadi(model):
    rid = make_room()
    rooms.join(STATE, rid, member_id="dadi")
    model.append(StreamClient(
        calls_round(("set_origin", {"name": "Bengaluru"}), ("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "end": "2026-12-30"}),
                    ("set_travelers", {"participant_ids": ["p-1", "p-2"], "count": 4}), ("set_budget", {"total": 120000})), []))
    say(rid, "Goa, budget 1.2 lakh")
    plan = plan_of(rid)
    assert plan["cost_summary"]["over_budget"] is False and plan["cost_summary"]["budget"] == 120000
    scheduled = [p for p in plan["places"] if p["day"]]
    assert scheduled and all(p["notes"].startswith("Step-free.") for p in scheduled)  # the rest stay on the board as options only
    assert any(not p["day"] and "tricky for Dadi" in p["notes"] for p in plan["places"])
    assert len({p["day"] for p in scheduled}) >= 4  # the few step-free places are spread over the days, not piled on one
    hotel = next(h for h in plan["hotels"] if h["status"] == "selected")
    assert hotel["step_free"] is True
    assert {"Dadi: Pure vegetarian", "Dadi: Bad knees: needs step-free access, no stairs"} <= set(plan["preferences"])
    meals = [r for r in plan["restaurants"] if r["day"]]
    assert meals and all(r["notes"].startswith(("Pure veg", "Vegetarian options")) for r in meals)


def test_the_model_can_call_draft_plan_itself_and_it_is_safe_to_call_twice(model):
    rid = make_room()
    model.append(StreamClient(
        calls_round(("set_origin", {"name": "Bengaluru"}), ("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "end": "2026-12-28"}),
                    ("set_travelers", {"participant_ids": ["p-1"]}), ("draft_plan", {})), []))
    say(rid, "Goa")
    first = len(plan_of(rid)["itinerary"])
    tools, _ = tools_for(rid)
    again = run(tools, "draft_plan")
    assert again["drafted"] is True and len(plan_of(rid)["itinerary"]) == first  # a second draft adds nothing that is already there
    assert run(tools_for(make_room())[0], "draft_plan") == {"drafted": False, "missing": ["destination", "dates", "travellers"]}


def test_draft_on_the_voice_path_runs_after_the_reply(model, monkeypatch):
    rid = make_room()
    model.append(full_script())
    out = rooms.converse_room(STATE, rid, "p-1", "Goa from Bengaluru, 26 to 30 December, four of us")
    assert out == planner.DONE["en"] or out == "One moment. " + planner.DONE["en"]
    plan = plan_of(rid)
    assert plan["itinerary"] and plan["flights"]  # the spawned draft ran (inline here)
    assert any(m["text"].startswith("Aangan drafted") for m in rooms.snapshot(STATE, rid)["messages"])


def test_the_change_summary_reads_naturally():
    assert planner.summarise({}) == ""
    assert planner.summarise({"flights": 2}) == "Aangan added 2 flight options"
    assert planner.summarise({"flights": 1, "places": 3, "dates": 1, "budget": 1}) == "Aangan added 1 flight option and 3 places to visit, updated the dates and the budget"
    assert planner.summarise({"approval": 1}) == "Aangan asked the host to approve a booking"
