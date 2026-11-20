"""The planning brain of a Family Room.

After a human message it reads the recent discussion and the current plan, and updates the plan through tools (set the
destination, search flights, schedule a place on a day, ...). It speaks in the room only when it is addressed;
otherwise it just updates the plan and leaves at most one short system note ("Aangan added 2 flight options").
The voice agent reaches the same brain through `stream_turn`, so what is said aloud and what is typed end up in
one plan.

Rules that hold everywhere in this file:
  * Aangan never books. `propose_booking` only asks the host (rooms.propose_booking); `rooms.decide` is the human tap.
  * Flights, hotels, places and restaurants come from tools and carry an honest `source`: "live" only for a real
    search result (live_flights), "sample" for built-in sample data.
  * With no AI key the planner still shows something, through a few plain rules, and says so in the room.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date, timedelta

from . import ground, languages, rooms, travel_data, travel_places
from .config import settings
from .gateway import open_stream

log = logging.getLogger("aangan.planner")

MAX_ROUNDS = 8
MAX_TOKENS = 3000
NONSTOP_PREMIUM = 1500  # a non-stop flight beats the cheapest connection when it costs less than this much more per person
INDIC = ("hi", "te", "kn")
ADDRESSED = re.compile(r"aangan|आँगन|आंगन|ఆంగన్|ಆಂಗನ್", re.I)
DONE = {
    "en": "Done, the plan is updated.", "hi": "हो गया, प्लान अपडेट हो गया।", "te": "అయింది, ప్లాన్ అప్‌డేట్ అయింది.",
    "kn": "ಆಯಿತು, ಪ್ಲಾನ್ ಅಪ್‌ಡೇಟ್ ಆಯಿತು.",
}
NO_AI_NOTICE = (
    "Aangan has no AI key configured here, so it can only pick up simple things from the chat: a destination, dates, "
    "a budget and where you start from."
)

RULES = """You are Aangan, the planner for a family room where several people talk through a plan together, usually a trip. You read the discussion and keep one shared plan up to date with your tools; everyone sees the plan board change as you work.

How you work:
- Update the plan from what people say. Never claim a change you did not make with a tool.
- Everyone in the room is coming unless told otherwise: call set_travelers with their ids, and give the head count when more people are going than are in the room (for example a grandmother who has not joined).
- As soon as the destination, the dates and the travellers are known, call draft_plan once. It searches flights and a hotel and fills each day with places and a lunch and dinner. After that, refine the plan as people talk, with the other tools.
- Flights and hotels come only from search_flights and search_hotels, places and restaurants only from search_places, search_restaurants or draft_plan. Never invent a flight, hotel, restaurant, price, opening time or booking reference. Results marked sample are sample data: say so if asked.
- Prefer a non-stop flight over the cheapest connection when it costs under about 1,500 rupees more per person.
- People may prefer to go by train, bus or car instead of flying, and to get around the destination by public transport, a cab or their own car. When the group decides how to travel, call travel_by with the mode: it chooses that train, bus or car for the way there and back and replaces the flights. To only look at or compare options call search_transport, which never changes what is chosen. Searching only shows options and never changes what is chosen: when someone asks to see or compare options, search and describe them, and call select_option only when the group has chosen one. For getting around the destination call set_local_transport and never add a local transport cost line yourself. Train, bus and car options are estimates from distance: never invent a train name, number, platform or departure time, and say they are estimates. They cannot be booked here, the group books them (IRCTC for trains).
- Respect what the household remembers about the people going (allergies, diet, step-free access): it is listed below and is already in the preferences. Choose places and restaurants that suit it.
- Never book. When the group wants to book, call propose_booking: the host approves with a button, so tell them the host needs to approve.
- Never say anything is booked, confirmed or reserved. Choosing an option only SELECTS it ("I've selected", "I've put ... in the plan"). Only the host's approval books, and bookings here are demo bookings.
- When the plan is over budget, say so plainly and offer one concrete way to bring it down (a cheaper flight time, a cheaper hotel, fewer paid activities).
- When something essential is missing (where people start from, the dates, the budget), add one open question. Do not ask twice, and resolve a question once it is answered.
- Dates are YYYY-MM-DD and a date without a year is the next one coming. "N days" means the end date is the start date plus N minus 1 (two days from the 21st is the 21st to the 22nd); "N nights" means start plus N. When the dates change, the backend drops the flights and days that no longer fit and drafts the missing ones itself, so do not search again. Money is whole rupees. Always give approximate latitude and longitude for a place you add yourself.
- When the group clearly agrees on something, record it as a decision. Never record a decision that is already in the plan.
- When the group changes its mind about where to go: if they name a new city, call set_destination with it (the old destination's unbooked options are cleared for you), then draft_plan once dates and travellers are known. If they drop the destination and name no new one, call drop_destination. If they name only a region (such as North India), do not set a destination: suggest two or three cities in one short sentence and add one open question. Do not record "the trip is no longer planned" as a decision.
- When someone asks you to suggest or choose something, make the suggestion and put it in the plan with your tools; do not ask a question back unless something essential is missing.
- Speech is transcribed and often wrong or messy ("daily" for Delhi, filler words, half sentences). Use the context of the conversation to work out the most likely meaning, and if you truly cannot, ask one short question instead of guessing.
- Flights, the hotel, chosen restaurants and chosen places are priced by the backend; add cost lines only for other things such as local transport, tips or shopping."""


class Turn:
    """What one planning turn changed and said. Tools note their changes here; the caller turns them into a message."""

    def __init__(self) -> None:
        self.changes: dict[str, int] = {}
        self.reply = ""
        self.answered = False  # the model wrote real words (a spoken hold phrase while a tool runs does not count)
        self.drafted: str | None = None
        self.apart = False  # the next piece starts a new stretch of words (after a tool round or a hold phrase)

    def note(self, key: str, n: int = 1) -> None:
        if n:
            self.changes[key] = self.changes.get(key, 0) + n

    def new_round(self) -> None:
        self.apart = True

    def say(self, piece: str, answer: bool = True) -> str:
        """Streamed pieces are tokens, so they join exactly as they come ("non", "-stop"); a space goes in only between stretches."""
        self.answered = self.answered or (answer and bool(piece.strip()))
        glue = " " if self.apart and self.reply and not self.reply[-1].isspace() and not piece[:1].isspace() else ""
        self.apart = not answer  # a hold phrase is followed by a fresh stretch of words
        if not answer and not piece[-1:].isspace():
            # a hold phrase ends with a space: the speech grouper releases a sentence only once whitespace follows it, so
            # without one "One moment." would sit unspoken until the tools finished
            piece += " "
        self.reply += glue + piece
        return glue + piece


_ADDED = (
    ("flights", "flight option"), ("transport", "train, bus or car option"), ("hotels", "hotel option"), ("places", "place to visit", "places to visit"), ("restaurants", "restaurant option"),
    ("scheduled", "item on the itinerary", "items on the itinerary"), ("decisions", "decision"), ("questions", "open question"),
    ("checklist", "checklist item"), ("costs", "cost line"),
)
# The planner never books, so it must never say it did. A model sometimes writes "I've booked the hotel" after only selecting it:
# a first-person claim of booking, confirming or reserving is rewritten to what actually happened.
_CLAIM = re.compile(r"\b(?P<lead>I've|I have|I|we've|we have|we|and|then)\s+(?P<mid>(?:also\s+|now\s+|already\s+)?)(?:booked|confirmed|reserved)\b", re.I)


def honest(text: str) -> str:
    # no markdown in a spoken or one-line reply: a model sometimes bolds headings anyway
    return _CLAIM.sub(lambda m: f"{m.group('lead')} {m.group('mid')}selected", text.replace("**", ""))


_SET = (("destination", "the destination"), ("origin", "the starting city"), ("dates", "the dates"), ("budget", "the budget"),
        ("travelers", "who is travelling"), ("goal", "the goal"), ("preferences", "the preferences"))


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def summarise(changes: dict[str, int]) -> str:
    """One short sentence for the room about what changed, or "" when nothing visible did."""
    added = []
    for key, one, *many in _ADDED:
        n = changes.get(key, 0)
        if n:
            added.append(f"{n} {one if n == 1 else (many[0] if many else one + 's')}")
    sets = [label for key, label in _SET if changes.get(key)]
    clauses = (["added " + _and(added)] if added else []) + (["updated " + _and(sets)] if sets else [])
    if changes.get("approval"):
        clauses.append("asked the host to approve a booking")
    return ("Aangan " + ", ".join(clauses)) if clauses else ""


# ---------------------------------------------------------------- flights and hotels


def _live_search(origin: str, destination: str, date: str, passengers: int, limit: int) -> list[dict]:
    """Real flight offers from live_flights, or [] when that module is missing, fails or finds nothing. Never raises."""
    try:
        from . import live_flights
    except ImportError:
        return []
    try:
        return list(live_flights.search(origin, destination, date, passengers, limit) or [])
    except Exception as exc:  # live data is a bonus: any failure means "no live data"
        log.warning("live flight search failed: %s", exc)
        return []


def _offer(raw, source: str, fallback: dict | None = None) -> dict | None:
    """One flight offer in the plan's shape, or None when it lacks what a flight needs."""
    if not isinstance(raw, dict):
        return None
    fb = fallback or {}
    try:
        offer = {
            "airline": str(raw.get("airline") or "").strip(), "number": str(raw.get("number") or raw.get("flight") or raw.get("id") or "").strip(),
            "from": str(raw.get("from") or raw.get("origin") or fb.get("from") or "").upper(),
            "to": str(raw.get("to") or raw.get("destination") or fb.get("to") or "").upper(),
            "date": str(raw.get("date") or fb.get("date") or ""), "dep": str(raw.get("dep") or raw.get("departure") or ""),
            "arr": str(raw.get("arr") or raw.get("arrival") or ""), "price": int(round(float(raw.get("price") or 0))),
            "stops": int(raw.get("stops") or 0), "source": source, "link": raw.get("link") or None,
        }
    except (TypeError, ValueError):
        return None
    return offer if offer["airline"] and offer["number"] and offer["price"] > 0 and offer["from"] and offer["to"] and offer["date"] else None


def _catalogue_flights(origin: dict, destination: dict, date: str) -> list[dict]:
    """The family catalogue's sample flights for this route and day (see agents/travel.py), when it has any."""
    from .agents import BY_NAME

    route = f"{origin['code']} -> {destination['code']}"
    out = []
    for f in BY_NAME["travel"].seed().get("catalog", []):
        if f["route"] == route and f["date"] == date:
            out.append({"airline": f["airline"], "number": f["id"], "from": origin["code"], "to": destination["code"], "date": date,
                        "dep": f["dep"], "arr": f["arr"], "price": f["price"], "stops": 0, "source": "sample", "link": None})
    return out


def rank_flights(offers: list[dict]) -> list[dict]:
    """Best first: the cheapest non-stop flight when it costs less than NONSTOP_PREMIUM more than the cheapest of all,
    else the cheapest; then the rest by price."""
    if not offers:
        return []
    by_price = sorted(offers, key=lambda f: (f["price"], f["stops"], f["dep"]))
    best = by_price[0]
    nonstop = next((f for f in by_price if f["stops"] == 0), None)
    if nonstop is not None and nonstop["price"] - best["price"] < NONSTOP_PREMIUM:
        best = nonstop
    return [best] + [f for f in by_price if f is not best]


def find_flights(origin: str, destination: str, date: str, passengers: int, limit: int = 5) -> tuple[list[dict], str]:
    """Flight offers (best first) and their source. Live first; else the catalogue and a built-in sample set."""
    o, d = travel_data.city(origin), travel_data.city(destination)
    live = [x for x in (_offer(r, "live", {"date": date}) for r in _live_search(o["code"] if o else origin, d["code"] if d else destination, date, passengers, limit)) if x]
    if live:
        return rank_flights(live)[:limit], "live"
    if not (o and d):
        return [], "none"
    sample = _catalogue_flights(o, d, date) or travel_data.sample_flights(o, d, date)
    return rank_flights([x for x in (_offer(s, "sample") for s in sample) if x])[:limit], "sample"


def _transport_view(t: dict) -> dict:
    keys = ("id", "mode", "label", "from", "to", "date", "distance_km", "price", "per", "source", "status")
    hours, minutes = divmod(t["duration_min"], 60)
    # the journey time as words, so a reply says "about 14 hours" and not "855 minutes"
    return {**{k: t[k] for k in keys}, "journey_time": f"about {hours} hours" + (f" {minutes} minutes" if minutes else "")}


def _flight_view(f: dict) -> dict:
    return {"id": f["id"], "airline": f["airline"], "number": f["number"], "from": f["from"], "to": f["to"], "date": f["date"], "dep": f["dep"],
            "arr": f["arr"], "price_per_person": f["price"], "stops": f["stops"], "source": f["source"], "status": f["status"]}


# ---------------------------------------------------------------- the tools the model can use


_DROPPING = re.compile(
    r"not going|no longer|n't want|don't want|do not want|not (?:go|travel)|cancel|forget (?:it|about)|drop (?:it|the)|scrap|call (?:it|the trip) off|"
    r"not anymore|any ?more|instead of|rather than|change (?:of )?(?:plan|mind|the destination)|somewhere else|another place|different (?:place|city|destination)",
    re.I)


_ONE_WAY = re.compile(r"one[- ]way|only (?:the )?(?:way (?:there|back)|outbound|return|going|coming)|fly (?:back|there|home|one)|flight (?:back|there|home)|but fly", re.I)
_MODE_WORDS = {"train": "train", "bus": "bus", "car": "own car", "cab": "outstation cab"}


class Tools:
    """The plan tools for one room and one turn. Each public method is one tool; its docstring is for readers, the schema
    the model sees is in TOOL_SPECS. A tool returns a small JSON-able dict, or raises, which the model reads as an error."""

    def __init__(self, state, room_id: str, turn: Turn, participant_id: str | None = None, said: str | None = None):
        self.state, self.room_id, self.turn, self.participant_id = state, room_id, turn, participant_id
        self.said = said  # the message being answered, so a destructive tool can check the group really asked for it

    # --- helpers
    def _plan(self) -> dict:
        return rooms.plan_snapshot(self.state, self.room_id)["plan"]

    def _needs(self) -> dict:
        return rooms.family_needs(self.state, self.room_id)

    def _city_arg(self, city: str | None) -> str:
        name = city or (self._plan().get("destination") or {}).get("name")
        if not name:
            raise ValueError("no city given and no destination set yet")
        return name

    def _place_notes(self, needs: dict):
        names = ", ".join(sorted(set(needs["step_free"])))

        def notes(p: dict) -> str:
            if not needs["step_free"]:
                return p.get("notes", "")
            lead = "Step-free." if p.get("step_free") else f"Steps or uneven ground, tricky for {names}."
            return f"{lead} {p.get('notes', '')}".strip()

        return notes

    def _food_notes(self, needs: dict):
        def notes(r: dict) -> str:
            parts = []
            if needs["veg"]:
                parts.append("Pure veg" if r.get("veg_only") else "Vegetarian options" if r.get("veg_options") else "No vegetarian menu")
            parts += [f"Tell the staff about {who}: {fact.lower()}" for who, fact in needs["allergies"]]
            if r.get("notes"):
                parts.append(r["notes"])
            return ". ".join(parts)

        return notes

    # --- simple plan fields
    def set_goal(self, goal: str) -> dict:
        self.turn.note("goal")
        return rooms.set_goal(self.state, self.room_id, goal)

    def set_destination(self, name: str, lat=None, lon=None) -> dict:
        self.turn.note("destination")
        return rooms.set_destination(self.state, self.room_id, name, lat, lon)

    def drop_destination(self) -> dict:
        # this wipes the flights, stay, places and meals, so it needs the group's own words: a model once called it when
        # people only said they would drive instead of taking a train
        if self.said is not None and not _DROPPING.search(self.said):
            return {"error": "The latest message does not say the group is giving up the destination, so nothing was cleared. "
                             "Changing how they travel, the dates or the budget never clears the destination. Do not call this tool for that."}
        self.turn.note("destination")
        return rooms.clear_destination(self.state, self.room_id)

    def set_origin(self, name: str, lat=None, lon=None) -> dict:
        self.turn.note("origin")
        return rooms.set_origin(self.state, self.room_id, name, lat, lon)

    def set_dates(self, start: str, end: str | None = None, nights: int | None = None) -> dict:
        self.turn.note("dates")
        return rooms.set_dates(self.state, self.room_id, start, end, nights)

    def set_budget(self, total, currency: str = "INR") -> dict:
        self.turn.note("budget")
        return rooms.set_budget(self.state, self.room_id, total, currency)

    def set_travelers(self, participant_ids=None, count: int | None = None, hotel_rooms: int | None = None) -> dict:
        self.turn.note("travelers")
        return rooms.set_travelers(self.state, self.room_id, participant_ids, count, hotel_rooms)

    def add_preference(self, text: str) -> dict:
        out = rooms.add_preference(self.state, self.room_id, text)
        self.turn.note("preferences", 1 if out["added"] else 0)
        return out

    def record_decision(self, text: str, by=None) -> dict:
        self.turn.note("decisions")
        return rooms.record_decision(self.state, self.room_id, text, by)

    def add_open_question(self, text: str) -> dict:
        out = rooms.add_open_question(self.state, self.room_id, text)
        self.turn.note("questions", 1 if out["added"] else 0)
        return out

    def resolve_question(self, question_id: str | None = None, text: str | None = None) -> dict:
        return rooms.resolve_question(self.state, self.room_id, question_id, text)

    def add_checklist_item(self, text: str, owner: str | None = None) -> dict:
        out = rooms.add_checklist_item(self.state, self.room_id, text, owner)
        self.turn.note("checklist", 1 if out["added"] else 0)
        return out

    def add_cost(self, label: str, amount, status: str = "estimate", category: str = "other", day: int | None = None) -> dict:
        if category in ("transport", "flights"):  # these are priced from the chosen options: a line here would count the fare twice
            return {"error": "Flights, trains, buses and cars are priced by the backend from what is chosen. Choose them (travel_by or select_option); do not add a cost line."}
        self.turn.note("costs")
        return rooms.add_cost(self.state, self.room_id, label, amount, status, category, day)

    # --- searching
    def search_flights(self, origin: str | None = None, destination: str | None = None, date: str | None = None, passengers: int | None = None) -> dict:
        plan = self._plan()
        origin = origin or (plan.get("origin") or {}).get("name")
        destination = destination or (plan.get("destination") or {}).get("name")
        date = date or (plan.get("dates") or {}).get("start")
        if not (origin and destination and date):
            raise ValueError("need an origin, a destination and a date (set them first or pass them)")
        n = int(passengers) if passengers else rooms.travellers(self._room_dict())
        offers, source = find_flights(origin, destination, date, n)
        if not offers:
            return {"flights": [], "note": f"No flights found from {origin} to {destination} on {date}, live or sample."}
        added = rooms.add_flights(self.state, self.room_id, offers)
        self.turn.note("flights", len(added))
        listed = [f for f in self._plan()["flights"] if (f["from"], f["to"], f["date"]) == (offers[0]["from"], offers[0]["to"], offers[0]["date"])]
        best_key = (offers[0]["airline"], offers[0]["number"])
        best = next((f for f in listed if (f["airline"], f["number"]) == best_key), None)
        return {
            "flights": [_flight_view(f) for f in listed], "recommended": best["id"] if best else None,
            "source": source, "passengers": n,
            "note": "These are live prices." if source == "live" else "Live search found nothing, so these are SAMPLE flights, not real prices.",
        }

    def search_transport(self, mode: str | None = None, origin: str | None = None, destination: str | None = None, date: str | None = None) -> dict:
        """Train, bus and car options between the two cities, for the journey there and (when the trip has an end date) the way back."""
        plan = self._plan()
        origin = origin or (plan.get("origin") or {}).get("name")
        destination = destination or (plan.get("destination") or {}).get("name")
        dates = plan.get("dates") or {}
        if not (origin and destination and (date or dates)):
            raise ValueError("need an origin, a destination and dates (set them first or pass them)")
        legs = [(origin, destination, date, "outbound")] if date else [(origin, destination, dates["start"], "outbound")]
        if not date and dates["end"] != dates["start"]:
            legs.append((destination, origin, dates["end"], "return"))
        found = [o for leg in legs for o in ground.options(leg[0], leg[1], leg[2], leg[3], mode)]
        if not found:
            return {"options": [], "note": f"I cannot estimate ground travel between {origin} and {destination}: they are the same place, too close to need a ticket, or not a city I know."}
        added = rooms.add_transport(self.state, self.room_id, found)
        self.turn.note("transport", len(added))
        wanted = {(o["date"], o["mode"]) for o in found}
        listed = [t for t in self._plan()["transport"] if (t["date"], t["mode"]) in wanted]
        picks = {}
        for leg_date in {t["date"] for t in listed}:
            best = ground.recommended([t for t in listed if t["date"] == leg_date], mode)
            picks[leg_date] = best["id"] if best else None
        return {
            "options": [_transport_view(t) for t in listed], "recommended_by_date": picks,
            "note": "These are ESTIMATES from the distance between the cities, not timetables: no train names, numbers or departure times. "
                    "This search has NOT chosen anything: call select_option only for the one the group picks, which replaces the flight "
                    "(or the earlier choice) for that journey. The group books it themselves (IRCTC for trains).",
        }

    def travel_by(self, mode: str, label: str | None = None) -> dict:
        """The group has decided how to get between the cities: choose that train, bus or car for the way there AND the way back
        in one step (replacing any flights or earlier choice), and remember it as their preference."""
        if mode not in ground.MODES:
            raise ValueError("mode must be train, bus, car or cab (to fly, use search_flights and select_option)")
        plan = self._plan()
        origin, destination, dates = (plan.get("origin") or {}).get("name"), (plan.get("destination") or {}).get("name"), plan.get("dates")
        if not (origin and destination and dates):
            raise ValueError("set the starting city, the destination and the dates first")
        legs = [(origin, destination, dates["start"], "outbound")]
        if dates["end"] != dates["start"]:
            legs.append((destination, origin, dates["end"], "return"))
        chosen = []
        for leg_from, leg_to, leg_date, leg in legs:
            found = ground.options(leg_from, leg_to, leg_date, leg, mode)
            if not found:
                return {"error": f"I cannot estimate {mode} travel between {leg_from} and {leg_to}: they are too close, or not cities I know."}
            rooms.add_transport(self.state, self.room_id, found)
            self.turn.note("transport", len(found))
            wanted = next((o for o in found if label and o["label"].lower() == label.lower()), None) or ground.recommended(found, mode)
            saved = next((t for t in self._plan()["transport"] if (t["mode"], t["label"], t["date"]) == (wanted["mode"], wanted["label"], wanted["date"])), None)
            if saved:
                rooms.choose(self.state, self.room_id, saved["id"])
                try:
                    rooms.schedule_item(self.state, self.room_id, saved["id"])
                    self.turn.note("scheduled")
                except rooms.RoomError:
                    pass
                chosen.append(_transport_view(next(t for t in self._plan()["transport"] if t["id"] == saved["id"])))
        if not ground.preferred_mode(plan["preferences"]) or ground.preferred_mode(plan["preferences"]) != mode:
            rooms.add_preference(self.state, self.room_id, f"Travel between cities by {_MODE_WORDS[mode]}.")
        return {"chosen": chosen, "note": "Chosen for both journeys. These are ESTIMATES from distance, not timetables; the group books them themselves."}

    def set_local_transport(self, mode: str) -> dict:
        """How the group gets around at the destination: cab, public (metro, buses, autos) or own_car."""
        self.turn.note("costs")
        return rooms.set_local_transport(self.state, self.room_id, mode)

    def _room_dict(self) -> dict:
        """The room's own plan as a lightweight dict for counting travellers (no copy of the messages)."""
        snap = rooms.plan_snapshot(self.state, self.room_id)
        return {"plan": snap["plan"], "participants": snap["participants"]}

    def search_hotels(self, city: str | None = None, nights: int | None = None, budget: int | None = None, step_free_only: bool | None = None) -> dict:
        city = self._city_arg(city)
        plan = self._plan()
        stay = int(nights) if nights else (rooms.nights(plan) or 1)
        needs = self._needs()
        step = bool(step_free_only) if step_free_only is not None else bool(needs["step_free"])
        found = travel_data.sample_hotels(city, int(budget) if budget else None, step_free_only=step)
        if not found:
            return {"hotels": [], "note": f"I have no hotel data for {city}. Hotels I know: {', '.join(travel_data.HOTEL_CITIES)}."}
        rooms.add_hotels(self.state, self.room_id, found)
        self.turn.note("hotels", len(found))
        names = {h["name"] for h in found}
        listed = [h for h in self._plan()["hotels"] if h["name"] in names]
        return {
            "hotels": [{**{k: h[k] for k in ("id", "name", "area", "price_per_night", "rating", "step_free", "source", "status")},
                        "total_for_stay": h["price_per_night"] * stay} for h in listed],
            "nights": stay, "note": "SAMPLE hotels, not live availability or prices.",
        }

    def search_places(self, city: str | None = None, interests=None) -> dict:
        city = self._city_arg(city)
        needs = self._needs()
        found = travel_places.sample_places(city, interests, step_free_first=bool(needs["step_free"]))
        if not found:
            return {"places": [], "note": f"I have no place data for {city}. Cities I know: {', '.join(travel_places.COVERED_CITIES)}."}
        added = rooms.add_places(self.state, self.room_id, found, notes_for=self._place_notes(needs))
        self.turn.note("places", len(added))
        names = {p["name"] for p in found}
        return {"places": [{k: p[k] for k in ("id", "name", "area", "category", "price", "duration_min", "notes", "status", "day")}
                           for p in self._plan()["places"] if p["name"] in names], "note": "SAMPLE places and rounded entry prices."}

    def search_restaurants(self, city: str | None = None, meal: str | None = None, budget_for_two: int | None = None, veg_only: bool | None = None) -> dict:
        city = self._city_arg(city)
        needs = self._needs()
        veg = bool(veg_only) if veg_only is not None else bool(needs["veg"])
        found = travel_places.sample_restaurants(city, meal, int(budget_for_two) if budget_for_two else None, veg_only=veg)
        if not found:
            return {"restaurants": [], "note": f"No restaurants matched for {city}. Cities I know: {', '.join(travel_places.COVERED_CITIES)}."}
        added = rooms.add_restaurants(self.state, self.room_id, found, meal=meal, notes_for=self._food_notes(needs))
        self.turn.note("restaurants", len(added))
        keys = {(r["name"], r["meal"]) for r in found}
        return {"restaurants": [{k: r[k] for k in ("id", "name", "cuisine", "area", "meal", "price_for_two", "veg_only", "notes", "status", "day")}
                                for r in self._plan()["restaurants"] if (r["name"], r["meal"]) in keys], "note": "SAMPLE restaurants and typical prices."}

    # --- choosing and scheduling
    def select_place(self, place_id: str, day: int | None = None, time: str | None = None, reject: bool = False) -> dict:
        out = rooms.choose(self.state, self.room_id, place_id, reject)
        if day and not reject:
            out = rooms.schedule_item(self.state, self.room_id, place_id, day, time)
            self.turn.note("scheduled")
        return out

    def select_restaurant(self, restaurant_id: str, day: int | None = None, time: str | None = None, reject: bool = False) -> dict:
        out = rooms.choose(self.state, self.room_id, restaurant_id, reject)
        if day and not reject:
            out = rooms.schedule_item(self.state, self.room_id, restaurant_id, day, time)
            self.turn.note("scheduled")
        return out

    def select_option(self, ref: str, reject: bool = False) -> dict:
        out = rooms.choose(self.state, self.room_id, ref, reject)
        if not reject and out["kind"] in ("flight", "transport"):
            try:  # the way there and back belongs on the itinerary on its day, not only in the options list
                rooms.schedule_item(self.state, self.room_id, ref)
                self.turn.note("scheduled")
            except rooms.RoomError:
                pass  # a date outside the trip: it stays selected, there is just no day to show it on
        if not reject and out["kind"] == "transport":
            self._same_way_back(ref)
        return out

    def _same_way_back(self, ref: str) -> None:
        """A round trip goes by the same means both ways: choosing the train, bus or car for one journey chooses it for the other,
        unless the group said only one way (or to fly the other). It replaces whatever was chosen for that journey."""
        if self.said and _ONE_WAY.search(self.said):
            return
        plan = self._plan()
        item = next((t for t in plan["transport"] if t["id"] == ref), None)
        dates = plan.get("dates")
        if not item or not dates or dates["start"] == dates["end"]:
            return
        other_date = dates["end"] if item["date"] == dates["start"] else dates["start"] if item["date"] == dates["end"] else None
        if other_date is None:
            return
        if any(t["date"] == other_date and t["status"] in ("selected", "booked") and t["mode"] == item["mode"] for t in plan["transport"]):
            return  # that journey already goes this way
        pick = next((t for t in plan["transport"] if (t["mode"], t["label"], t["date"]) == (item["mode"], item["label"], other_date)), None)
        if pick is None:
            made = [o for o in ground.options(item["to"], item["from"], other_date, "return" if other_date == dates["end"] else "outbound", item["mode"])
                    if o["label"] == item["label"]]
            rooms.add_transport(self.state, self.room_id, made)
            self.turn.note("transport", len(made))
            pick = next((t for t in self._plan()["transport"] if (t["mode"], t["label"], t["date"]) == (item["mode"], item["label"], other_date)), None)
        if pick:
            rooms.choose(self.state, self.room_id, pick["id"])
            try:
                rooms.schedule_item(self.state, self.room_id, pick["id"])
                self.turn.note("scheduled")
            except rooms.RoomError:
                pass

    def schedule_item(self, ref: str, day: int | None = None, time: str | None = None) -> dict:
        out = rooms.schedule_item(self.state, self.room_id, ref, day, time)
        self.turn.note("scheduled")
        return out

    def add_itinerary_item(self, title: str, day: int | None = None, date: str | None = None, time: str | None = None, place: str = "",
                           lat=None, lon=None, notes: str = "") -> dict:
        self.turn.note("scheduled")
        return rooms.add_itinerary_item(self.state, self.room_id, title, day, date, time, place, lat, lon, notes)

    # --- money
    def propose_booking(self, flight_id: str | None = None, hotel_id: str | None = None, travellers: int | None = None, nights: int | None = None) -> dict:
        out = rooms.propose_booking(self.state, self.room_id, flight_id, hotel_id, travellers, nights)
        self.turn.note("approval")
        return {**out, "note": "Nothing is booked. The host must approve with the Approve button."}

    def draft_plan(self) -> dict:
        self._note_travel_wishes()
        return _draft(self.state, self.room_id, self.turn)

    def _note_travel_wishes(self) -> None:
        """"We prefer the train" said in the same breath as the plan must shape the first draft, whatever order the model works in:
        note it as a preference before drafting (the draft reads the preferences)."""
        if not self.said:
            return
        known = self._plan()["preferences"]
        mode = ground.preferred_mode([self.said])
        if mode and not ground.preferred_mode(known):
            rooms.add_preference(self.state, self.room_id, f"Travel between cities by {_MODE_WORDS[mode]}.")
            self.turn.note("preferences")
        if ground.local_mode([self.said]) != "cab" and ground.local_mode(known) == "cab":
            rooms.add_preference(self.state, self.room_id,
                                 "Get around the destination in our own car." if ground.local_mode([self.said]) == "own_car" else "Use public transport at the destination.")
            self.turn.note("preferences")


def _spec(name: str, description: str, props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


_S, _I, _N, _B = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}
_PEOPLE = {"type": "array", "items": _S, "description": "participant ids such as p-1, or names"}

TOOL_SPECS = [
    _spec("set_goal", "Set the one-line goal of the plan.", {"goal": _S}, ["goal"]),
    _spec("set_destination", "Set where the group is going. lat and lon may be left out for well-known Indian cities.",
          {"name": _S, "lat": _N, "lon": _N}, ["name"]),
    _spec("drop_destination", "ONLY when the group says in plain words that they no longer want to go to the current destination and have not named another: clears it and ALL its flights, hotels, places and meals from the board. Never for a change of transport, dates, budget or people."),
    _spec("set_origin", "Set the city the group starts from.", {"name": _S, "lat": _N, "lon": _N}, ["name"]),
    _spec("set_dates", "Set the trip dates (YYYY-MM-DD). Give end, or the number of nights.", {"start": _S, "end": _S, "nights": _I}, ["start"]),
    _spec("set_budget", "Set the total budget in whole rupees.", {"total": _N, "currency": _S}, ["total"]),
    _spec("set_travelers", "Set who is travelling (participant ids or names), the head count if it is more than the people in the room, and the number of hotel rooms.",
          {"participant_ids": _PEOPLE, "count": _I, "hotel_rooms": _I}),
    _spec("add_preference", "Note a preference or need of the group (diet, access, a wish).", {"text": _S}, ["text"]),
    _spec("search_transport", "Find train, bus or car options for the journey there and back (estimates from the distance between the cities, not timetables). Results are added to the plan; choose one with select_option, which replaces the flight for that journey. mode is train, bus, car (self-drive) or cab; leave it out to get all.",
          {"mode": {"type": "string", "enum": ["train", "bus", "car", "cab"]}, "origin": _S, "destination": _S, "date": _S}),
    _spec("travel_by", "The group has DECIDED to go by train, bus, car (their own, self-drive) or cab: chooses it for the way there and the way back in one step, replacing any flight, and remembers the preference. label is optional (for a train 3AC, 2AC or Sleeper class). To fly instead, use search_flights and select_option.",
          {"mode": {"type": "string", "enum": ["train", "bus", "car", "cab"]}, "label": _S}, ["mode"]),
    _spec("set_local_transport", "Set how the group gets around at the destination: cab, public (metro, buses and autos) or own_car. Replaces the local travel cost.",
          {"mode": {"type": "string", "enum": ["cab", "public", "own_car"]}}, ["mode"]),
    _spec("search_flights", "Search flights. Live results when available, otherwise sample data (the result says which). Results are added to the plan. Origin, destination and date default to the plan's.",
          {"origin": _S, "destination": _S, "date": _S, "passengers": _I}),
    _spec("search_hotels", "Search sample hotels for a city; results are added to the plan. budget is the most per night.",
          {"city": _S, "nights": _I, "budget": _I, "step_free_only": _B}),
    _spec("search_places", "Search places to visit in a city (sample data); results are added to the plan. interests such as beach, temple, market, food, nature, kids.",
          {"city": _S, "interests": {"type": "array", "items": _S}}),
    _spec("search_restaurants", "Search restaurants in a city (sample data); results are added to the plan. meal is breakfast, lunch, dinner or snack.",
          {"city": _S, "meal": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]}, "budget_for_two": _I, "veg_only": _B}),
    _spec("select_place", "Choose a place from the plan (or reject it), optionally putting it on a day of the trip.",
          {"place_id": _S, "day": _I, "time": _S, "reject": _B}, ["place_id"]),
    _spec("select_restaurant", "Choose a restaurant from the plan (or reject it), optionally putting it on a day and time.",
          {"restaurant_id": _S, "day": _I, "time": _S, "reject": _B}, ["restaurant_id"]),
    _spec("select_option", "Choose (or reject) a flight or hotel from the plan. This is not a booking.", {"ref": _S, "reject": _B}, ["ref"]),
    _spec("schedule_item", "Put a flight, hotel, place or restaurant on a day (1 is the first day) and time (HH:MM) of the itinerary.",
          {"ref": _S, "day": _I, "time": _S}, ["ref"]),
    _spec("add_itinerary_item", "Add your own itinerary item (day or date, HH:MM time). Give lat and lon for a place.",
          {"title": _S, "day": _I, "date": _S, "time": _S, "place": _S, "lat": _N, "lon": _N, "notes": _S}, ["title"]),
    _spec("add_cost", "Add a cost line for something the backend does not price itself (local transport, tips, shopping).",
          {"label": _S, "amount": _N, "status": {"type": "string", "enum": ["estimate", "quoted", "booked"]},
           "category": {"type": "string", "enum": [c for c in rooms.COST_CATEGORIES if c not in ("flights", "transport")]}, "day": _I}, ["label", "amount"]),
    _spec("record_decision", "Record something the group agreed on.", {"text": _S, "by": _PEOPLE}, ["text"]),
    _spec("add_open_question", "Add a question the group still has to answer.", {"text": _S}, ["text"]),
    _spec("resolve_question", "Mark an open question answered, by id or by matching text.", {"question_id": _S, "text": _S}),
    _spec("add_checklist_item", "Add something to do before the trip.", {"text": _S, "owner": _S}, ["text"]),
    _spec("propose_booking", "Ask the host to approve a booking of a flight and/or a hotel. This NEVER books anything.",
          {"flight_id": _S, "hotel_id": _S, "travellers": _I, "nights": _I}),
    _spec("draft_plan", "Draft a first full plan once destination, dates and travellers are known: flights, a hotel, places and meals for every day, and local transport. Safe to call once."),
]
TOOL_NAMES = {s["name"] for s in TOOL_SPECS}


def run_tool(tools: Tools, name: str, args: dict) -> dict:
    """Run one tool call and return its result, or {"error": ...} (a bad argument or a refusal is information for the model)."""
    if name not in TOOL_NAMES:
        return {"error": f"unknown tool {name}"}
    try:
        return getattr(tools, name)(**args)
    except rooms.RoomError as exc:
        return {"error": exc.detail}
    except Exception as exc:
        log.info("tool %s failed: %s: %s", name, type(exc).__name__, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------- the first draft of a whole plan


def _km(a: dict, b: dict) -> float:
    return travel_data.km_between(a, b)


def _nearest(pool: list[dict], anchor: dict | None) -> dict:
    return pool[0] if anchor is None else min(pool, key=lambda p: _km(anchor, p))


def _day_counts(days: int) -> list[int]:
    """Places per day: a light arrival day and departure day, three on the days between."""
    if days <= 1:
        return [3]
    if days == 2:
        return [2, 2]
    return [1] + [3] * (days - 2) + [1]


def _fit(counts: list[int], available: int) -> list[int]:
    """Shrink the busiest days first until the plan fits the places there are (so no day is left empty while another has three)."""
    counts = list(counts)
    while sum(counts) > available and max(counts) > 0:
        counts[counts.index(max(counts))] -= 1
    return counts


def _ready(plan: dict) -> list[str]:
    missing = []
    if not plan.get("destination"):
        missing.append("destination")
    if not plan.get("dates"):
        missing.append("dates")
    if not (plan.get("traveler_count") or plan.get("travelers")):
        missing.append("travellers")
    return missing


def _draft(state, room_id: str, turn: Turn) -> dict:
    """Fill in a first full plan from what is known, using the same functions the tools use. Parts that already exist are
    kept: a draft only adds what is missing. Everything it picks is 'selected' (a draft, not a booking)."""
    plan = rooms.plan_snapshot(state, room_id)["plan"]
    missing = _ready(plan)
    if missing:
        return {"drafted": False, "missing": missing}
    tools = Tools(state, room_id, turn)
    rooms.sync_family_needs(state, room_id)
    needs = rooms.family_needs(state, room_id)
    dest = plan["destination"]["name"]
    days = min(rooms.trip_days(plan) or 1, 10)
    nights = rooms.nights(plan) or 0
    made: dict[str, int] = {"flights": 0, "hotel": 0, "places": 0, "meals": 0}
    n = rooms.travellers({"plan": plan, "participants": rooms.plan_snapshot(state, room_id)["participants"]})

    # flights: outbound and return, searched together, the recommended one of each leg chosen
    origin = (plan.get("origin") or {}).get("name")
    legs = [(origin, dest, plan["dates"]["start"])]
    if plan["dates"]["end"] != plan["dates"]["start"]:
        legs.append((dest, origin, plan["dates"]["end"]))
    have_dates = {f["date"] for f in plan["flights"]} | {t["date"] for t in plan["transport"] if t["status"] in ("selected", "booked")}
    legs = [leg for leg in legs if leg[2] not in have_dates]  # a leg is searched only when the plan has no flight or chosen train on its date yet
    by_ground = ground.preferred_mode(plan["preferences"])  # "we'll take the train": the draft travels that way instead of flying
    if origin and legs and by_ground:
        for leg_origin, leg_dest, leg_date in legs:
            options = ground.options(leg_origin, leg_dest, leg_date, "outbound" if leg_date == plan["dates"]["start"] else "return", by_ground)
            if not options:
                continue  # too close or unknown: the flight search below is not tried either, there is nothing sensible to offer
            rooms.add_transport(state, room_id, options)
            turn.note("transport", len(options))
            best = ground.recommended(options, by_ground)
            saved = next((t for t in rooms.plan_snapshot(state, room_id)["plan"]["transport"]
                          if (t["label"], t["date"], t["mode"]) == (best["label"], best["date"], best["mode"])), None)
            if saved:
                rooms.schedule_item(state, room_id, saved["id"])
                made["flights"] += 1
        legs = []
    if origin and legs:
        with ThreadPoolExecutor(max_workers=len(legs)) as pool:
            found = list(pool.map(lambda leg: find_flights(leg[0], leg[1], leg[2], n), legs))
        for offers, _source in found:
            if not offers:
                continue
            added = rooms.add_flights(state, room_id, offers)
            turn.note("flights", len(added))
            best = next((f for f in rooms.plan_snapshot(state, room_id)["plan"]["flights"]
                         if (f["airline"], f["number"], f["date"]) == (offers[0]["airline"], offers[0]["number"], offers[0]["date"])), None)
            if best:
                rooms.schedule_item(state, room_id, best["id"])
                made["flights"] += 1
    elif not origin and not plan["flights"]:
        out = rooms.add_open_question(state, room_id, "Which city are you flying from?")
        turn.note("questions", 1 if out["added"] else 0)

    # hotel: the best rated one that fits the budget (a third of it for the stay), step-free when someone needs it
    if nights > 0 and not plan["hotels"]:
        budget = (plan.get("budget") or {}).get("total")
        per_night = int(budget * 0.35 / nights) if budget else None
        hotels = travel_data.sample_hotels(dest, per_night, step_free_only=bool(needs["step_free"]))
        if hotels:
            added = rooms.add_hotels(state, room_id, hotels)
            turn.note("hotels", len(added))
            chosen = next((h for h in rooms.plan_snapshot(state, room_id)["plan"]["hotels"] if h["name"] == hotels[0]["name"]), None)
            if chosen:
                rooms.schedule_item(state, room_id, chosen["id"], 1)
                if days > 1:
                    rooms.schedule_item(state, room_id, chosen["id"], days)
                made["hotel"] = 1

    # a draft should not blow the budget: when there is one, meals and activities each get a share of it
    budget = (plan.get("budget") or {}).get("total")
    meals_planned = max(1, 2 * days - (1 if days > 1 else 0))
    food_cap_for_two = max(400, int(budget * 0.2 / meals_planned * 2 / n)) if budget else None
    place_cap = int(budget * 0.1 / 3) if budget else None  # no single activity should take more than a third of the activities' share

    # places: nearby places grouped into days, step-free first when someone needs it
    snap_places = rooms.plan_snapshot(state, room_id)["plan"]["places"]
    busy_days = {p["day"] for p in snap_places if p.get("day")}  # days that already have something are left as they are
    if len(busy_days) < days:
        pool = travel_places.sample_places(dest, step_free_first=bool(needs["step_free"]), limit=30)
        added = rooms.add_places(state, room_id, pool, notes_for=tools._place_notes(needs))
        turn.note("places", len(added))
        listed = {p["name"]: p for p in rooms.plan_snapshot(state, room_id)["plan"]["places"]}
        # everything found stays on the board as an option; when someone needs step-free access only step-free places go on a day
        left = [dict(p, ref=listed[p["name"]]["id"]) for p in pool if p["name"] in listed and listed[p["name"]]["status"] == "proposed"
                and not (place_cap and p["price"] * n > place_cap) and (p["step_free"] or not needs["step_free"])]
        for day, count in enumerate(_fit(_day_counts(days), len(left)), start=1):
            if day in busy_days:
                continue
            anchor = None
            for _ in range(count):
                if not left:
                    break
                pick = _nearest(left, anchor)
                left.remove(pick)
                anchor = pick
                at = "16:00" if day == 1 and days > 1 else "09:30" if day == days and days > 1 else None
                rooms.schedule_item(state, room_id, pick["ref"], day, at)
                made["places"] += 1
                turn.note("scheduled")

    # meals: a lunch and a dinner each day (no dinner on the way home), near that day's places
    plan_now = rooms.plan_snapshot(state, room_id)["plan"]
    chosen = [f for f in plan_now["flights"] if f["status"] == "selected"]
    arrives = max((f["arr"] for f in chosen if f["date"] == plan["dates"]["start"] and f["to"] != (plan.get("origin") or {}).get("code", "")), default="00:00")
    leaves = min((f["dep"] for f in chosen if f["date"] == plan["dates"]["end"] and f["date"] != plan["dates"]["start"]), default="23:59")
    planned_meals = {(r["day"], r["meal"]) for r in plan_now["restaurants"] if r.get("day")}  # a meal already on a day stays
    used: set[tuple[str, str]] = {(r["name"], r["meal"]) for r in plan_now["restaurants"] if r.get("day")}  # one plan item per restaurant and meal
    for day in range(1, days + 1):
        same_day = [p for p in plan_now["places"] if p.get("day") == day]
        centre = {"lat": sum(p["lat"] for p in same_day) / len(same_day), "lon": sum(p["lon"] for p in same_day) / len(same_day)} if same_day else None
        for meal in ("lunch", "dinner"):
            if (day, meal) in planned_meals:
                continue
            if meal == "dinner" and day == days and days > 1:
                continue  # the day of going home: no dinner
            if meal == "lunch" and ((day == 1 and arrives > "12:30") or (day == days and days > 1 and leaves < "14:00")):
                continue  # still in the air (or already on the way to the airport) at lunch time
            options = [r for r in travel_places.sample_restaurants(dest, meal, budget_for_two=food_cap_for_two, veg_only=bool(needs["veg"]), limit=12)
                       if (r["name"], meal) not in used]
            if not options:  # nothing cheap enough is left: the budget cap gives way to having a meal
                options = [r for r in travel_places.sample_restaurants(dest, meal, veg_only=bool(needs["veg"]), limit=12)
                           if (r["name"], meal) not in used]
            if not options:
                continue
            names = {name for name, _ in used}
            fresh = [r for r in options if r["name"] not in names] or options  # a new place before a repeat for the other meal
            if needs["veg"] and any(r["veg_only"] for r in fresh):
                fresh = [r for r in fresh if r["veg_only"]]
            pick = _nearest(fresh, centre)
            used.add((pick["name"], meal))
            added = rooms.add_restaurants(state, room_id, [pick], meal=meal, notes_for=tools._food_notes(needs), replace=False)
            turn.note("restaurants", len(added))
            saved = next((r for r in rooms.plan_snapshot(state, room_id)["plan"]["restaurants"]
                          if r["name"] == pick["name"] and r["meal"] == meal), None)
            if saved:
                rooms.schedule_item(state, room_id, saved["id"], day)
                made["meals"] += 1
                turn.note("scheduled")

    # local transport, and a few things to do before leaving
    if not any(c.get("category") == "local" for c in plan_now["costs"]):
        local_label, local_amount = ground.local_cost(plan_now.get("local_mode") or ground.local_mode(plan_now["preferences"]), days, n)
        rooms.add_cost(state, room_id, local_label, local_amount, "estimate", "local")
        turn.note("costs")
    for text in ["Carry a photo ID for every traveller"] + (["Confirm step-free access at the hotel and at each place"] if needs["step_free"] else []):
        out = rooms.add_checklist_item(state, room_id, text)
        turn.note("checklist", 1 if out["added"] else 0)
    if n > 2 and not plan_now.get("rooms"):
        out = rooms.add_open_question(state, room_id, "How many hotel rooms do you need?")
        turn.note("questions", 1 if out["added"] else 0)

    rooms.mark_drafted(state, room_id, dest)
    summary = rooms.cost_summary_for(state, room_id)
    turn.drafted = _draft_text(made, summary)
    return {"drafted": True, **made, "estimated_total": summary["total"], "note": "Everything chosen is a draft, nothing is booked."}


def _draft_text(made: dict, summary: dict) -> str:
    bits = []
    if made["flights"]:
        bits.append(f"{made['flights']} flight{'s' if made['flights'] > 1 else ''}")
    if made["hotel"]:
        bits.append("a hotel")
    if made["places"]:
        bits.append(f"{made['places']} places")
    if made["meals"]:
        bits.append(f"{made['meals']} meals")
    what = ", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else (bits[0] if bits else "the basics")
    return f"Aangan drafted a first plan with {what}. Estimated total {summary['total']:,} rupees, mostly sample data, nothing booked."


def _draft_if_ready(state, room_id: str, turn: Turn) -> bool:
    """Draft once destination, dates and travellers are known and this destination has not been drafted yet."""
    plan = rooms.plan_snapshot(state, room_id)["plan"]
    if _ready(plan) or rooms.drafted_for(state, room_id) == plan["destination"]["name"]:
        return False
    return bool(_draft(state, room_id, turn).get("drafted"))


def draft_if_ready(state, room_id: str) -> None:
    """Background entry (the voice path): a draft can take seconds, so it runs after the spoken reply."""
    try:
        with rooms.plan_lock(room_id):
            turn = Turn()
            if _draft_if_ready(state, room_id, turn) and turn.drafted:
                rooms.add_system_message(state, room_id, turn.drafted)
    except Exception:
        log.exception("drafting the plan failed in room %s", room_id)
    finally:
        save_quietly(state)


def save_quietly(state) -> None:
    """Persist after a background change; a failed save never breaks anything."""
    try:
        from . import persistence

        persistence.save(state)
    except Exception as exc:
        log.warning("could not save the household: %s", exc)


# ---------------------------------------------------------------- the model loop


def is_addressed(text: str, ask: bool = False) -> bool:
    return ask or bool(ADDRESSED.search(text))


def _client():
    from .gateway import gateway_client

    return gateway_client(settings().ai_gateway_api_key)


def _plan_view(plan: dict) -> dict:
    """The plan as the model reads it: ids, names, statuses and money, without coordinates and other bulk."""
    pick = lambda items, keys: [{k: i.get(k) for k in keys if i.get(k) not in (None, "")} for i in items]  # noqa: E731
    summary = plan.get("cost_summary") or {}
    return {
        "goal": plan["goal"], "destination": (plan["destination"] or {}).get("name"), "origin": (plan["origin"] or {}).get("name"),
        "dates": plan["dates"], "travelers": plan["travelers"], "traveler_count": plan.get("traveler_count"), "hotel_rooms": plan.get("rooms"),
        "budget": plan["budget"], "preferences": plan["preferences"],
        "flights": pick(plan["flights"], ("id", "airline", "number", "from", "to", "date", "dep", "price", "stops", "source", "status")),
        "ground_transport": pick(plan["transport"], ("id", "mode", "label", "from", "to", "date", "duration_min", "price", "per", "status")),
        "local_transport": plan.get("local_mode"),
        "hotels": pick(plan["hotels"], ("id", "name", "area", "price_per_night", "rating", "source", "status")),
        "places": pick(plan["places"], ("id", "name", "category", "price", "day", "status")),
        "restaurants": pick(plan["restaurants"], ("id", "name", "meal", "price_for_two", "day", "status")),
        "itinerary": pick(plan["itinerary"], ("id", "day", "time", "title", "kind", "ref")),
        "costs": pick(plan["costs"], ("label", "amount", "category", "status")),
        "decisions": [d["text"] for d in plan["decisions"]],
        "open_questions": [{"id": q["id"], "text": q["text"]} for q in plan["open_questions"] if not q["resolved"]],
        "checklist": [c["text"] for c in plan["checklist"]],
        "cost_summary": {k: summary.get(k) for k in ("total", "per_person", "travellers", "by_category", "budget", "remaining", "over_budget")},
    }


def _context(state, room_id: str, participant_id: str, message: dict, addressed: bool) -> str:
    snap = rooms.plan_snapshot(state, room_id)
    host = snap["host_participant_id"]
    people = "\n".join(f"- {p['id']}: {p['name']}{' (host)' if p['id'] == host else ''}" for p in snap["participants"])
    needs = rooms.family_needs(state, room_id)
    facts = "\n".join(f"- {who}: {fact}" for who, fact in needs["facts"]) or "- nothing noted"
    chat = "\n".join(f"{m['name'] or 'Note'}: {m['text']}" for m in rooms.recent_messages(state, room_id, 20) if m["id"] != message["id"])
    now = _date.fromisoformat(rooms.today()).strftime("%A %Y-%m-%d")
    pending = snap["pending_approval"]
    return (
        f"Room: {snap['title']}. Today is {now} (India time).\n"
        f"People in the room (use these ids in tools):\n{people}\n"
        f"What the household remembers about the people going:\n{facts}\n"
        f"Current plan (JSON):\n{json.dumps(_plan_view(snap['plan']), ensure_ascii=False)}\n"
        f"Waiting for the host: {pending['title'] if pending else 'nothing'}. Bookings so far: {len(snap['bookings'])}.\n"
        f"Recent conversation:\n{chat or '(none yet)'}\n\n"
        f"Latest message, from {message['name']}: {message['text']}\n"
        f"This message {'IS' if addressed else 'is NOT'} addressed to you."
    )


def _reply_rule(addressed: bool, lang: str, spoken: bool) -> str:
    if not addressed:
        return "This message is not addressed to you: write no reply text at all. Only call tools, or do nothing when the plan needs no change."
    chosen = languages.LANGUAGES[lang]
    where = (f"{chosen.name}, written in {chosen.script}; names of people and places may stay as they are" if lang != "en" else "English")
    voice = " Everything you write is spoken aloud: write numbers as a person would say them, with no symbols." if spoken else ""
    return f"This message is addressed to you: after your tool calls, answer in one or two short plain sentences, no markdown or lists or emojis, in {where}.{voice}"


def _stream_round(client, kwargs: dict):
    """One streamed model round: yields ("text", piece) as it arrives, then ("end", content, [calls]) with the tool calls assembled."""
    content, calls = "", {}
    for chunk in open_stream(client, kwargs):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            content += delta.content
            yield ("text", delta.content)
        for tc in delta.tool_calls or []:
            # some models send no index: a chunk with a new id starts a call, one without continues the last
            key = tc.index if tc.index is not None else (len(calls) - 1 if calls and not tc.id else len(calls))
            slot = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
            slot["id"] = tc.id or slot["id"]
            if tc.function:
                slot["name"] += tc.function.name or ""
                slot["arguments"] += tc.function.arguments or ""
        if calls and not content.strip():
            yield ("tool", None)
    yield ("end", content, [calls[i] for i in sorted(calls)])


def _args(raw: str) -> dict:
    try:
        value = json.loads(raw) if raw and raw.strip() else {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _model_turn(state, room_id: str, participant_id: str, message: dict, addressed: bool, spoken: bool, turn: Turn, client=None):
    """The tool-calling loop. Yields the reply text as it is written (only when addressed; otherwise the model's words are dropped)."""
    cfg = settings()
    client = client or _client()
    lang = message.get("lang") or languages.detect(message["text"])
    indic = lang in INDIC
    model = cfg.ai_gateway_model_indic if indic else cfg.ai_gateway_model_name
    system = f"{RULES}\n\n{_reply_rule(addressed, lang, spoken)}"
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": _context(state, room_id, participant_id, message, addressed)},
    ]
    tools = [{"type": "function", "function": spec} for spec in TOOL_SPECS]
    handlers = Tools(state, room_id, turn, participant_id, said=message["text"])
    led = False
    for round_no in range(MAX_ROUNDS):
        if round_no:
            turn.new_round()
        kwargs = {"model": model, "messages": list(messages), "max_tokens": MAX_TOKENS, "stream": True, "tools": tools}
        if cfg.openai_reasoning and not indic:
            kwargs["reasoning_effort"] = cfg.openai_reasoning
        content, calls = "", []
        for event in _stream_round(client, kwargs):
            if event[0] == "text":
                if addressed:
                    yield turn.say(event[1])
            elif event[0] == "tool":
                if spoken and addressed and not led and not turn.reply.strip():
                    led = True  # the voice is never silent while the first tool runs
                    yield turn.say(languages.LOOKING[lang] if indic else "One moment.", answer=False)
            else:
                content, calls = event[1], event[2]
        if not calls:
            return
        for n, call in enumerate(calls):
            call["id"] = call["id"] or f"call_{round_no}_{n}"
        messages.append({
            "role": "assistant", "content": content or None,
            "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls],
        })
        for call in calls:
            result = run_tool(handlers, call["name"], _args(call["arguments"]))
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False, default=str)})
    log.warning("planner hit the round limit in room %s", room_id)


# ---------------------------------------------------------------- no AI key: a few plain rules

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_MONTH = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:(?:-|to|till|until)\s*(\d{1,2})(?:st|nd|rd|th)?)?\s+(?:of\s+)?(" + _MONTH + r")\b", re.I)
_MONTH_DAY = re.compile(r"\b(" + _MONTH + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_DURATION = re.compile(r"\b(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")[\s-]*(days?|nights?)\b", re.I)
_BUDGET = re.compile(r"(?:budget|under|within|upto|up to|max(?:imum)?)\D{0,12}?(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|lacs?)?(?![\w])", re.I)
_BUDGET_SYMBOL = re.compile(r"(?:₹|rs\.?\s*|inr\s*)(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|lacs?)?(?![\w])", re.I)
_PEOPLE_COUNT = re.compile(r"\b(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+(?:people|persons|adults|travell?ers|of us|members)\b|\bfor\s+(\d{1,2})\b(?!\s*(?:days?|nights?))", re.I)
_NEED = re.compile(r"step[- ]free|wheelchair|vegetarian|vegan|allerg|peanut|no stairs", re.I)


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word.lower(), 0)


def _amount(number: str, unit: str | None) -> int:
    value = float(number.replace(",", ""))
    unit = (unit or "").lower()
    return int(value * (1000 if unit == "k" else 100000 if unit.startswith(("l", "lakh", "lac")) else 1))


def _parse_dates(text: str, today: str) -> tuple[str, str] | None:
    now = _date.fromisoformat(today)
    low = text.lower()
    isos = _ISO.findall(text)
    duration = _DURATION.search(low)
    length = _count(duration.group(1)) if duration else 0
    is_nights = bool(duration and duration.group(2).startswith("n"))
    start = end = None
    if isos:
        start = _date.fromisoformat(isos[0])
        end = _date.fromisoformat(isos[1]) if len(isos) > 1 else None
    else:
        m = _DAY_MONTH.search(text)
        month_day = _MONTH_DAY.search(text)
        pick = None
        if m:
            pick = (int(m.group(1)), int(m.group(2)) if m.group(2) else None, _MONTHS[m.group(3)[:3].lower()])
        elif month_day:
            pick = (int(month_day.group(2)), None, _MONTHS[month_day.group(1)[:3].lower()])
        elif "christmas" in low:
            pick = (25, None, 12)
        if pick:
            day, end_day, month = pick
            year = now.year
            try:
                start = _date(year, month, day)
                if start < now:
                    start = _date(year + 1, month, day)
                end = _date(start.year, month, end_day) if end_day and end_day >= day else None
            except ValueError:
                return None
    if start is None:
        return None
    if end is None:
        end = start + timedelta(days=length if is_nights else max(length - 1, 0)) if length else start
    return start.isoformat(), end.isoformat()


def _rule_turn(state, room_id: str, message: dict, addressed: bool, turn: Turn) -> None:
    """A tiny stand-in for the model: picks a destination, a starting city, dates, a budget and a head count out of the
    chat with regexes, so the board still shows something. It says so in the room, once."""
    text = message["text"]
    plan = rooms.plan_snapshot(state, room_id)["plan"]
    found: list[str] = []
    cities = travel_data.cities_in(text)
    origin = dest = None
    m = re.search(r"\bfrom\s+([A-Za-z ]{3,25}?)(?=\s+(?:to|on|for|in|by|with)\b|[,.;!?]|$)", text)
    if m:
        c = travel_data.city(m.group(1))
        origin = c["name"] if c else None
    for _, c in cities:
        if c["name"] != origin:
            dest = dest or c["name"]
    if dest:
        rooms.set_destination(state, room_id, dest)
        turn.note("destination")
        found.append(f"destination {dest}")
        if not plan["goal"]:
            rooms.set_goal(state, room_id, f"Trip to {dest}")
            turn.note("goal")
    if origin:
        rooms.set_origin(state, room_id, origin)
        turn.note("origin")
        found.append(f"starting from {origin}")
    dates = _parse_dates(text, rooms.today())
    if dates:
        rooms.set_dates(state, room_id, dates[0], dates[1])
        turn.note("dates")
        found.append(f"dates {dates[0]} to {dates[1]}")
    b = _BUDGET.search(text) or _BUDGET_SYMBOL.search(text)
    if b:
        amount = _amount(b.group(1), b.group(2))
        if amount >= 1000:
            rooms.set_budget(state, room_id, amount)
            turn.note("budget")
            found.append(f"budget {amount:,} rupees")
    pc = _PEOPLE_COUNT.search(text)
    count = _count(pc.group(1) or pc.group(2)) if pc else 0
    if _NEED.search(text):
        out = rooms.add_preference(state, room_id, text[:160])
        turn.note("preferences", 1 if out["added"] else 0)
    now_plan = rooms.plan_snapshot(state, room_id)["plan"]
    if count or (dest and not now_plan["travelers"]):  # everyone in the room is going unless told how many
        everyone = [p["id"] for p in rooms.plan_snapshot(state, room_id)["participants"]]
        rooms.set_travelers(state, room_id, everyone, count or None)
        turn.note("travelers")
    if addressed:
        turn.answered = True
        turn.reply = ("Noted: " + ", ".join(found) + ".") if found else (
            "I am running without an AI key, so I can only pick up a destination, dates, a budget and where you start from.")


# ---------------------------------------------------------------- entry points


_DECIDING = re.compile(r"\b(let'?s|lets|we'?ll|we will|we want|we would like|we should|take|go by|going by|travel by|switch|back to|instead|prefer|rather|drive|driving|use)\b", re.I)
_BROWSING = re.compile(r"\b(show|compare|options?|what about|how much|price|prices|cost|costs|is there|are there|which|list|check|find|tell me|what are)\b", re.I)
_MODE_WORDS_IN_SPEECH = (
    ("train", re.compile(r"\b(train|trains|rail|railway)\b", re.I)),
    ("bus", re.compile(r"\b(bus|buses)\b", re.I)),
    ("car", re.compile(r"\b(drive|driving|own car|our car|by car|the car|road ?trip)\b", re.I)),
)
_FLYING = re.compile(r"\b(fly|flying|flight|flights|plane|air)\b", re.I)


def decided_travel_mode(said: str) -> str | None:
    """The way of getting between cities the group has clearly DECIDED on in this message (train, bus or car), else None.
    Looking at options ("show me the bus options") and mentions of flying are not decisions."""
    if not said or _BROWSING.search(said) or _FLYING.search(said) or not _DECIDING.search(said):
        return None
    modes = [mode for mode, pattern in _MODE_WORDS_IN_SPEECH if pattern.search(said)]
    return modes[0] if len(modes) == 1 else None


def _enforce_travel_choice(state, room_id: str, said: str) -> None:
    """A safety net behind the model: when the group clearly decided how to travel and the plan does not say so afterwards (a
    model sometimes tells the room it switched without calling the tool), apply the decision now."""
    mode = decided_travel_mode(said)
    if not mode:
        return
    plan = rooms.plan_snapshot(state, room_id)["plan"]
    if not (plan.get("origin") and plan.get("destination") and plan.get("dates")):
        return
    dates = {plan["dates"]["start"], plan["dates"]["end"]}
    chosen = [t for t in plan["transport"] if t["status"] in ("selected", "booked")]
    if chosen and all(t["mode"] == mode for t in chosen) and {t["date"] for t in chosen} >= dates:
        return  # already travelling that way, both ways
    result = run_tool(Tools(state, room_id, Turn(), said=said), "travel_by", {"mode": mode})
    log.info("travel mode %s applied by the safety net in room %s: %s", mode, room_id, "error" in result and result["error"] or "ok")


def _stream_brain(state, room_id: str, participant_id: str, message: dict, addressed: bool, spoken: bool, turn: Turn, client=None):
    if not settings().ai_gateway_api_key and client is None:
        if rooms.once(state, room_id, "no_ai"):
            rooms.add_system_message(state, room_id, NO_AI_NOTICE)
        _rule_turn(state, room_id, message, addressed, turn)
        if turn.reply:
            yield turn.reply
        return
    yield from _model_turn(state, room_id, participant_id, message, addressed, spoken, turn, client)
    try:
        _enforce_travel_choice(state, room_id, message["text"])
    except Exception:
        log.exception("could not apply the travel choice in room %s", room_id)


def stream_turn(state, room_id: str, participant_id: str, message_id: int, spoken: bool = True, client=None):
    """The voice path: yields the reply text as it is written. Always addressed (someone is talking to the voice agent)."""
    message = rooms.get_message(state, room_id, message_id)
    if message is None:
        return
    with rooms.plan_lock(room_id):
        rooms.sync_family_needs(state, room_id)
        turn = Turn()
        try:
            yield from _stream_brain(state, room_id, participant_id, message, True, spoken, turn, client)
        except Exception:
            log.exception("voice planning turn failed in room %s", room_id)
            yield languages.SORRY[message.get("lang") or "en"]
            return
        if not turn.answered:  # tools ran but the model said nothing: never leave the voice silent
            yield (" " if turn.reply else "") + DONE[message.get("lang") or "en"]


def plan_after_message(state, room_id: str, message_id: int, ask: bool = False, client=None) -> None:
    """Run in the background after a human message: update the plan, speak only when addressed. Catches every exception."""
    try:
        message = rooms.get_message(state, room_id, message_id)
        if message is None or message["kind"] != "user":
            return
        addressed = is_addressed(message["text"], ask)
        with rooms.plan_lock(room_id):
            rooms.sync_family_needs(state, room_id)
            turn = Turn()
            failed = False
            try:
                for _ in _stream_brain(state, room_id, message["participant_id"], message, addressed, False, turn, client):
                    pass
            except Exception:
                failed = True
                log.exception("planning turn failed in room %s", room_id)
            try:
                _draft_if_ready(state, room_id, turn)
            except Exception:
                log.exception("drafting failed in room %s", room_id)
            lang = message.get("lang") or "en"
            if addressed:
                reply = turn.reply.strip() if turn.answered else (languages.SORRY[lang] if failed else DONE[lang])
                rooms.add_agent_message(state, room_id, honest(reply))
            if turn.drafted:
                rooms.add_system_message(state, room_id, turn.drafted)
            elif not addressed:
                note = summarise(turn.changes)
                if note:
                    rooms.add_system_message(state, room_id, note)
            rooms.touch(state, room_id)
    except Exception:
        log.exception("planner crashed in room %s", room_id)
