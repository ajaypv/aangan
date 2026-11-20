"""Getting there by train, bus or car: estimates from the distance between two known cities.

There is no free live source for Indian train, bus or cab fares, so none of this pretends to be a timetable. Every option is
marked as an estimate, carries no train name, number or departure time, and says how it was worked out. Distances are the
straight line between the cities, stretched to a road or rail distance, and fares use typical rates per kilometre.
"""

import math
import re

from . import travel_data

SEATS_PER_CAR = 4
ROAD_FACTOR = 1.25  # winding roads and detours over the straight line
RAIL_FACTOR = 1.35
MAX_ROAD_KM = 2500  # beyond this nobody drives or takes a bus, so none is offered
MIN_KM = 40  # inside one city there is nothing to book

# mode, label, rate in rupees per km (per person for train and bus, per car for car and cab), average km/h, fixed extra, what the rate means
_RAIL = [("Sleeper class", 0.55, 0), ("3AC", 1.35, 60), ("2AC", 1.95, 60)]
_BUS = [("AC sleeper bus", 2.2, 0), ("Seater bus", 1.2, 0)]
_CAR = ("car", "Self-drive car", 9.0, 0)  # fuel and tolls only, for the whole car
_CAB = ("cab", "Outstation cab with driver", 13.0, 400)  # per km plus a driver allowance, for the whole cab

MODES = ("train", "bus", "car", "cab")

_PREFERENCE = (
    ("train", re.compile(r"\b(train|trains|rail|railway|irctc)\b", re.I)),
    ("bus", re.compile(r"\b(bus|buses|volvo)\b", re.I)),
    ("cab", re.compile(r"\boutstation\b", re.I)),  # "cabs" alone usually means getting around town, which is the local setting
    ("car", re.compile(r"\b(drive|driving|road ?trip|self[- ]drive|by car|own car|our car)\b", re.I)),
)
_LOCAL_PUBLIC = re.compile(r"public transport|public transit|metro|local bus|local train|autos?\b", re.I)
_LOCAL_OWN_CAR = re.compile(r"\b(own car|our car|drive ourselves|self[- ]drive)\b", re.I)


def cars_needed(travellers: int) -> int:
    return max(1, math.ceil(max(1, travellers) / SEATS_PER_CAR))


def _round10(value: float) -> int:
    return int(round(value / 10.0) * 10)


def _duration(km: float, kmh: float, stop_minutes_per_4h: int = 30) -> int:
    drive = km / kmh * 60  # minutes of travelling
    with_stops = drive + (drive / 240) * stop_minutes_per_4h  # plus a break for every four hours
    return int(round(with_stops / 5) * 5)  # to the nearest five minutes


def distances(origin: dict, destination: dict) -> tuple[int, int, int]:
    """(straight line, road, rail) kilometres between two cities of the table."""
    line = travel_data.km_between(origin, destination)
    return int(round(line)), int(round(line * ROAD_FACTOR)), int(round(line * RAIL_FACTOR))


def options(origin: str, destination: str, date: str, leg: str, mode: str | None = None) -> list[dict]:
    """Estimated ways to get from one city to another on a date, cheapest first within each mode. `leg` is outbound or return.
    Empty when a city is unknown or the two are the same place."""
    a, b = travel_data.city(origin), travel_data.city(destination)
    if not a or not b or a["name"] == b["name"]:
        return []
    line, road, rail = distances(a, b)
    if line < MIN_KM:
        return []
    wanted = [mode] if mode in MODES else list(MODES)
    out: list[dict] = []

    def add(kind: str, label: str, minutes: int, km: int, price: int, per: str, notes: str) -> None:
        out.append({
            "mode": kind, "label": label, "from": a["name"], "to": b["name"], "date": date, "leg": leg, "duration_min": minutes,
            "distance_km": km, "price": price, "per": per, "source": "estimate", "notes": notes,
        })

    if "train" in wanted:
        for name, rate, extra in _RAIL:
            add("train", name, _duration(rail, 52, 20), rail, _round10(max(150, rail * rate + extra)), "person",
                "Estimated fare and time for an express train. Pick the train and book on IRCTC.")
    if "bus" in wanted and road <= MAX_ROAD_KM:
        for name, rate, extra in _BUS:
            add("bus", name, _duration(road, 45), road, _round10(max(150, road * rate + extra)), "person",
                "Estimated fare and time for an overnight or day coach. Check operators for the real fare.")
    if "car" in wanted and road <= MAX_ROAD_KM:
        _, name, rate, extra = _CAR
        add("car", name, _duration(road, 55), road, _round10(road * rate + extra), "vehicle",
            f"Fuel and tolls for one car of up to {SEATS_PER_CAR}, one way. A very long day at the wheel, so plan stops." if road > 700
            else f"Fuel and tolls for one car of up to {SEATS_PER_CAR}, one way.")
    if "cab" in wanted and road <= MAX_ROAD_KM:
        _, name, rate, extra = _CAB
        add("cab", name, _duration(road, 55), road, _round10(road * rate + extra), "vehicle",
            f"Estimated fare for one cab of up to {SEATS_PER_CAR}, one way, with a driver.")
    return out


def recommended(found: list[dict], mode: str | None = None) -> dict | None:
    """The sensible default: for a train 3AC, for a bus the AC sleeper, otherwise the only or cheapest of the mode (or overall)."""
    pool = [o for o in found if not mode or o["mode"] == mode]
    if not pool:
        return None
    for preferred in ("3AC", "AC sleeper bus"):
        hit = next((o for o in pool if o["label"] == preferred), None)
        if hit:
            return hit
    return min(pool, key=lambda o: o["price"])


def preferred_mode(preferences: list[str]) -> str | None:
    """The way of travelling between cities the group has said it prefers, from the preference notes (None when none)."""
    text = " ".join(preferences)
    for mode, pattern in _PREFERENCE:
        if pattern.search(text):
            return mode
    return None


def local_mode(preferences: list[str]) -> str:
    """How the group gets around at the destination: cab (the default), public transport or their own car."""
    text = " ".join(preferences)
    if _LOCAL_OWN_CAR.search(text):
        return "own_car"
    if _LOCAL_PUBLIC.search(text):
        return "public"
    return "cab"


def local_cost(mode: str, days: int, travellers: int) -> tuple[str, int]:
    """(label, rupees for the whole stay) of getting around the destination."""
    days = max(1, days)
    if mode == "public":
        return "Local transport (metro, buses and autos)", 250 * travellers * days
    if mode == "own_car":
        return "Local transport (own car: fuel and parking)", 600 * cars_needed(travellers) * days
    return "Local transport (cabs and autos)", (900 if travellers <= 4 else 1600) * days
