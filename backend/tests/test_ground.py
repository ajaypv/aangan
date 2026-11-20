"""Getting there by train, bus or car, and getting around: estimates from distance, clearly marked, replacing flights per journey."""

import pytest

from app import ground, planner, rooms
from app.main import STATE


@pytest.fixture(autouse=True)
def fresh():
    STATE.reset(demo=True)
    rooms._PLAN_LOCKS.clear()


def trip(origin="Bengaluru", dest="Goa", start="2026-12-26", end="2026-12-28", people=4):
    room = rooms.create_room(STATE, "Trip", "priya")
    rid = room["id"]
    rooms.set_origin(STATE, rid, origin)
    rooms.set_destination(STATE, rid, dest)
    rooms.set_dates(STATE, rid, start, end)
    rooms.set_travelers(STATE, rid, ["p-1"], people)
    return rid


def plan_of(rid):
    return rooms.snapshot(STATE, rid)["plan"]


# ---- the estimates ----


def test_every_mode_is_offered_and_marked_as_an_estimate():
    found = ground.options("Bengaluru", "Goa", "2026-12-26", "outbound")
    assert {o["mode"] for o in found} == {"train", "bus", "car", "cab"}
    assert all(o["source"] == "estimate" and o["price"] > 0 and o["duration_min"] > 0 for o in found)
    assert not any(k in o for o in found for k in ("number", "train_no", "dep", "arr"))  # no invented timetable


def test_prices_follow_the_distance_and_the_class():
    short = {o["label"]: o["price"] for o in ground.options("Bengaluru", "Chennai", "2026-12-26", "outbound", "train")}
    long = {o["label"]: o["price"] for o in ground.options("Bengaluru", "Delhi", "2026-12-26", "outbound", "train")}
    assert short["Sleeper class"] < short["3AC"] < short["2AC"]
    assert all(long[k] > short[k] for k in short)


def test_a_car_is_priced_per_vehicle_and_a_train_per_person():
    car = ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "car")[0]
    assert car["per"] == "vehicle" and ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "train")[0]["per"] == "person"
    assert [ground.cars_needed(n) for n in (1, 4, 5, 9)] == [1, 1, 2, 3]


def test_the_same_city_or_an_unknown_one_has_no_options():
    assert ground.options("Bengaluru", "Bengaluru", "2026-12-26", "outbound") == []
    assert ground.options("Bengaluru", "Atlantis", "2026-12-26", "outbound") == []


def test_a_very_long_way_is_not_offered_by_road():
    modes = {o["mode"] for o in ground.options("Thiruvananthapuram", "Delhi", "2026-12-26", "outbound")}
    assert modes == {"train"}


def test_the_group_preference_is_read_from_the_notes():
    assert ground.preferred_mode(["Using public transport or train."]) == "train"
    assert ground.preferred_mode(["We would rather drive"]) == "car"
    assert ground.preferred_mode(["Dadi needs step-free access", "cabs to get around"]) is None
    assert ground.local_mode(["Using public transport for the journey."]) == "public"
    assert ground.local_mode(["we will use our own car"]) == "own_car"
    assert ground.local_mode([]) == "cab"


# ---- in the room ----


def test_choosing_a_train_replaces_the_flight_for_that_journey_and_is_costed():
    rid = trip()
    out, back = rooms.add_flights(STATE, rid, [
        {"airline": "IndiGo", "number": "6E-1", "from": "BLR", "to": "GOI", "date": "2026-12-26", "dep": "07:00", "arr": "08:20", "price": 5000, "stops": 0},
        {"airline": "IndiGo", "number": "6E-2", "from": "GOI", "to": "BLR", "date": "2026-12-28", "dep": "18:00", "arr": "19:20", "price": 5200, "stops": 0}])
    rooms.schedule_item(STATE, rid, out["id"])
    rooms.schedule_item(STATE, rid, back["id"])
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "train"))
    train = next(t for t in plan_of(rid)["transport"] if t["label"] == "3AC")
    rooms.schedule_item(STATE, rid, train["id"])
    plan = plan_of(rid)
    assert {f["id"]: f["status"] for f in plan["flights"]} == {out["id"]: "proposed", back["id"]: "selected"}  # only the outbound flight made way
    assert [e["title"] for e in plan["itinerary"] if e["kind"] == "travel" and e["day"] == 1] == ["3AC, Bengaluru to Goa"]
    assert plan["cost_summary"]["by_category"]["transport"] == train["price"] * 4 and plan["cost_summary"]["by_category"]["flights"] == 5200 * 4
    # and choosing the flight again puts the train back
    rooms.choose(STATE, rid, out["id"])
    assert {t["id"]: t["status"] for t in plan_of(rid)["transport"]}[train["id"]] == "proposed"


def test_a_chosen_train_for_both_ways_means_no_flight_is_assumed():
    rid = trip()
    rooms.add_flights(STATE, rid, [{"airline": "IndiGo", "number": "6E-1", "from": "BLR", "to": "GOI", "date": "2026-12-26", "dep": "07:00",
                                   "arr": "08:20", "price": 5000, "stops": 0}])
    for leg, (a, b, d) in enumerate([("Bengaluru", "Goa", "2026-12-26"), ("Goa", "Bengaluru", "2026-12-28")]):
        rooms.add_transport(STATE, rid, ground.options(a, b, d, "outbound" if leg == 0 else "return", "train"))
    for t in [t for t in plan_of(rid)["transport"] if t["label"] == "3AC"]:
        rooms.choose(STATE, rid, t["id"])
    by = plan_of(rid)["cost_summary"]["by_category"]
    assert by["flights"] == 0 and by["transport"] > 0


def test_a_car_costs_one_vehicle_per_four_people():
    rid = trip(people=5)
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "car"))
    car = plan_of(rid)["transport"][0]
    rooms.choose(STATE, rid, car["id"])
    assert plan_of(rid)["cost_summary"]["by_category"]["transport"] == car["price"] * 2


def test_changing_the_dates_drops_stale_ground_options_too():
    rid = trip()
    rooms.add_transport(STATE, rid, ground.options("Goa", "Bengaluru", "2026-12-28", "return", "train"))
    rooms.set_dates(STATE, rid, "2026-12-26", "2026-12-27")
    assert plan_of(rid)["transport"] == []


def test_local_transport_replaces_the_local_cost():
    rid = trip(people=4)
    out = rooms.set_local_transport(STATE, rid, "public")
    assert out["amount"] == 250 * 4 * 3
    rooms.set_local_transport(STATE, rid, "cab")
    local = [c for c in plan_of(rid)["costs"] if c["category"] == "local"]
    assert len(local) == 1 and local[0]["amount"] == 900 * 3
    with pytest.raises(rooms.RoomError):
        rooms.set_local_transport(STATE, rid, "helicopter")


# ---- through the planner ----


def test_the_planner_tool_searches_both_journeys_and_recommends_one_per_leg():
    rid = trip()
    tools = planner.Tools(STATE, rid, planner.Turn())
    result = planner.run_tool(tools, "search_transport", {"mode": "train"})
    assert {o["date"] for o in result["options"]} == {"2026-12-26", "2026-12-28"}
    assert set(result["recommended_by_date"]) == {"2026-12-26", "2026-12-28"} and "ESTIMATES" in result["note"]
    assert planner.run_tool(tools, "search_transport", {"origin": "Bengaluru", "destination": "Bengaluru"})["options"] == []


def test_a_train_preference_makes_the_automatic_draft_travel_by_train(monkeypatch):
    rid = trip()
    rooms.add_preference(STATE, rid, "We will take the train.")
    monkeypatch.setattr(planner, "find_flights", lambda *a, **k: pytest.fail("a draft by train must not search flights"))
    planner.draft_if_ready(STATE, rid)
    plan = plan_of(rid)
    assert [t["label"] for t in plan["transport"] if t["status"] == "selected"] == ["3AC", "3AC"]
    assert plan["flights"] == [] and plan["cost_summary"]["by_category"]["transport"] > 0
    assert any(c["category"] == "local" for c in plan["costs"])


def test_a_second_local_cost_line_replaces_the_first_instead_of_adding_to_it():
    rid = trip()
    rooms.set_local_transport(STATE, rid, "public")
    rooms.add_cost(STATE, rid, "Local transport (cabs and autos)", 3750, "estimate", "local")  # what a model sometimes does on its own
    local = [c for c in plan_of(rid)["costs"] if c["category"] == "local"]
    assert [c["label"] for c in local] == ["Local transport (cabs and autos)"]
    assert plan_of(rid)["cost_summary"]["by_category"]["local"] == 3750


def test_selecting_a_train_puts_it_on_the_itinerary_too():
    rid = trip()
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "train"))
    train = next(t for t in plan_of(rid)["transport"] if t["label"] == "3AC")
    tools = planner.Tools(STATE, rid, planner.Turn(), said="the train there, one way only")
    planner.run_tool(tools, "select_option", {"ref": train["id"]})
    travel = [e for e in plan_of(rid)["itinerary"] if e["kind"] == "travel"]
    assert [(e["day"], e["title"]) for e in travel] == [(1, "3AC, Bengaluru to Goa")]
    assert "no fixed departure time" in travel[0]["notes"]


def test_journey_times_are_realistic():
    by = {o["mode"]: o["duration_min"] for o in ground.options("Bengaluru", "Goa", "2026-12-26", "outbound") if o["label"] in ("3AC", "AC sleeper bus", "Self-drive car")}
    assert 7 * 60 <= by["car"] <= 13 * 60  # Bengaluru to Goa is a day's drive, not three
    assert 8 * 60 <= by["bus"] <= 18 * 60 and 8 * 60 <= by["train"] <= 20 * 60
    assert ground.options("Bengaluru", "Chennai", "2026-12-26", "outbound", "car")[0]["duration_min"] < 8 * 60


def test_dropping_the_destination_needs_the_groups_own_words():
    rid = trip()
    said_travel = planner.Tools(STATE, rid, planner.Turn(), said="Aangan, actually let's drive our own car there and back.")
    assert "error" in planner.run_tool(said_travel, "drop_destination", {})
    assert plan_of(rid)["destination"]["name"] == "Goa"
    said_drop = planner.Tools(STATE, rid, planner.Turn(), said="We are not going to Goa anymore.")
    assert planner.run_tool(said_drop, "drop_destination", {}) == {"cleared": "Goa"}


def _with_flights_both_ways(rid):
    out, back = rooms.add_flights(STATE, rid, [
        {"airline": "IndiGo", "number": "6E-1", "from": "BLR", "to": "GOI", "date": "2026-12-26", "dep": "07:00", "arr": "08:20", "price": 5000, "stops": 0},
        {"airline": "IndiGo", "number": "6E-2", "from": "GOI", "to": "BLR", "date": "2026-12-28", "dep": "18:00", "arr": "19:20", "price": 5200, "stops": 0}])
    for f in (out, back):
        rooms.schedule_item(STATE, rid, f["id"])
    return out["id"], back["id"]


def test_choosing_the_train_one_way_chooses_it_for_the_way_back_too():
    rid = trip()
    out_id, back_id = _with_flights_both_ways(rid)
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "train"))
    train = next(t for t in plan_of(rid)["transport"] if t["label"] == "3AC")
    tools = planner.Tools(STATE, rid, planner.Turn(), said="Aangan, let's take the train")
    planner.run_tool(tools, "select_option", {"ref": train["id"]})
    plan = plan_of(rid)
    assert [(t["label"], t["date"]) for t in plan["transport"] if t["status"] == "selected"] == [("3AC", "2026-12-26"), ("3AC", "2026-12-28")]
    assert all(f["status"] == "proposed" for f in plan["flights"])  # both flights made way
    assert [(e["day"], e["title"]) for e in plan["itinerary"] if e["kind"] == "travel"] == [(1, "3AC, Bengaluru to Goa"), (3, "3AC, Goa to Bengaluru")]


def test_one_way_wishes_are_respected():
    rid = trip()
    out_id, back_id = _with_flights_both_ways(rid)
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "train"))
    train = next(t for t in plan_of(rid)["transport"] if t["label"] == "3AC")
    tools = planner.Tools(STATE, rid, planner.Turn(), said="Train there, but fly back please")
    planner.run_tool(tools, "select_option", {"ref": train["id"]})
    plan = plan_of(rid)
    assert [t["date"] for t in plan["transport"] if t["status"] == "selected"] == ["2026-12-26"]
    assert {f["id"]: f["status"] for f in plan["flights"]}[back_id] == "selected"


def test_a_travel_wish_in_the_same_message_shapes_the_first_draft(monkeypatch):
    rid = trip()
    monkeypatch.setattr(planner, "find_flights", lambda *a, **k: pytest.fail("the group said train: no flight search"))
    tools = planner.Tools(STATE, rid, planner.Turn(), said="Plan Goa, we prefer going by train, and public transport once there.")
    result = planner.run_tool(tools, "draft_plan", {})
    plan = plan_of(rid)
    assert result["drafted"] and plan["flights"] == []
    assert [t["label"] for t in plan["transport"] if t["status"] == "selected"] == ["3AC", "3AC"]
    assert plan["costs"] and [c["label"] for c in plan["costs"] if c["category"] == "local"] == ["Local transport (metro, buses and autos)"]


def test_markdown_bold_is_stripped_from_replies():
    assert planner.honest("**Bus options:** AC sleeper bus.") == "Bus options: AC sleeper bus."


def test_travel_by_chooses_the_mode_both_ways_replaces_flights_and_remembers_it():
    rid = trip(people=5)
    out_id, back_id = _with_flights_both_ways(rid)
    tools = planner.Tools(STATE, rid, planner.Turn(), said="Aangan, let's drive our own car there and back.")
    result = planner.run_tool(tools, "travel_by", {"mode": "car"})
    plan = plan_of(rid)
    assert [(c["label"], c["date"]) for c in result["chosen"]] == [("Self-drive car", "2026-12-26"), ("Self-drive car", "2026-12-28")]
    assert all(f["status"] == "proposed" for f in plan["flights"]) and plan["cost_summary"]["by_category"]["flights"] == 0
    assert plan["cost_summary"]["by_category"]["transport"] == 2 * result["chosen"][0]["price"] * 2  # two journeys, two cars for five people
    assert ground.preferred_mode(plan["preferences"]) == "car"
    # switching again replaces the earlier choice
    planner.run_tool(planner.Tools(STATE, rid, planner.Turn()), "travel_by", {"mode": "train", "label": "2AC"})
    assert [t["label"] for t in plan_of(rid)["transport"] if t["status"] == "selected"] == ["2AC", "2AC"]
    assert ground.preferred_mode(plan_of(rid)["preferences"]) in ("train", "car")


def test_travel_by_needs_the_basics_and_a_real_mode():
    room = rooms.create_room(STATE, "Trip", "priya")
    tools = planner.Tools(STATE, room["id"], planner.Turn())
    assert "error" in planner.run_tool(tools, "travel_by", {"mode": "train"})
    rid = trip()
    assert "error" in planner.run_tool(planner.Tools(STATE, rid, planner.Turn()), "travel_by", {"mode": "rocket"})


@pytest.mark.parametrize(
    "said,expected",
    [
        ("Aangan, actually let's drive our own car there and back.", "car"),
        ("hmm, on second thought the train is better. Back to the train.", "train"),
        ("We prefer going by train, and public transport once there.", "train"),
        ("Let's take the bus", "bus"),
        ("Aangan, show me the bus and car options too, but keep the train.", None),  # looking, not deciding
        ("How much is the train?", None),
        ("what about the train", None),
        ("let's fly, the train takes too long", None),  # flying is the model's call
        ("let's take the train or the bus", None),  # two answers: not a decision
        ("Dadi can't climb the train steps easily", None),
    ],
)
def test_a_clear_travel_decision_is_recognised(said, expected):
    assert planner.decided_travel_mode(said) == expected


def test_the_safety_net_applies_a_decision_the_model_forgot_to_make():
    rid = trip()
    rooms.add_transport(STATE, rid, ground.options("Bengaluru", "Goa", "2026-12-26", "outbound", "car"))
    planner._enforce_travel_choice(STATE, rid, "Aangan, let's drive our own car there and back")
    assert [(t["mode"], t["date"]) for t in plan_of(rid)["transport"] if t["status"] == "selected"] == [("car", "2026-12-26"), ("car", "2026-12-28")]
    before = plan_of(rid)["transport"]
    planner._enforce_travel_choice(STATE, rid, "Aangan, let's drive our own car there and back")  # already so: nothing changes
    assert plan_of(rid)["transport"] == before
    planner._enforce_travel_choice(STATE, rid, "show me train options")
    assert [t["mode"] for t in plan_of(rid)["transport"] if t["status"] == "selected"] == ["car", "car"]


def test_a_transport_cost_line_from_the_model_is_refused():
    rid = trip()
    result = planner.run_tool(planner.Tools(STATE, rid, planner.Turn()), "add_cost", {"label": "Self-drive car", "amount": 5120, "category": "transport"})
    assert "error" in result and plan_of(rid)["costs"] == []
