"""Travel agent: flights and cabs for any member or the whole family, plus delay rebooking.

Domain data (state.domains["travel"]): trips, bookings, cabs, catalog (+ chaos_consumed, seq). Extend, don't rename.
A trip: id, member_ids, route, date, flight, airline, dep, arr, seats{member: seat}, status
(ON_TIME | DELAYED | BOOKED | REBOOKED), delay_min, pnr, cab{booking, pickup_date, pickup, status},
fare_total, calendar_event_id, optional must_arrive_by / meeting{title, place, start, transit_min, buffer_min}.

Tools: search_flights, book_flight, rebook_flight, book_cab, update_cab_pickup, add_trip_to_calendar,
notify_family (stage "after"), get_trip, flight_status_webhook.
Trigger: flight_delay (Rahul's Monday flight is delayed 3h; the agent proposes an alternative and waits for yes/no).
"""

import re
from datetime import date as _date, timedelta

from .. import calendar_core as cal
from ..toolkit import Tool, ToolError, run_parallel
from .base import Specialist, Trigger

CITIES = {"goa": "GOI", "new delhi": "DEL", "delhi": "DEL", "bangalore": "BLR", "bengaluru": "BLR", "bangaluru": "BLR"}
_CITY_ALT = "|".join(re.escape(c) for c in sorted(CITIES, key=len, reverse=True))
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

CONFIRM = {"yes", "yeah", "yep", "ok", "okay", "confirm", "book", "haan", "han", "theek", "thik", "sure", "done", "karo", "kardo"}
REJECT = {"no", "nope", "nahi", "nahin", "cancel", "stop", "ruko", "wait"}

FLIGHT_RE = re.compile(r"\b(flights?|fly|flying|airport|tickets?|rebook|pnr|airline)\b")
CAB_RE = re.compile(r"\b(cab|taxi)\b")
AIRPORT_RE = re.compile(r"\b(airport|flight|trip)\b")
OTHER_DOMAIN_RE = re.compile(r"\b(doctor|clinic|hospital|restaurant|lunch|dinner|breakfast|table|school|dawai|medicine)\b")
OUTING_RE = re.compile(r"\b(outing|picnic|movie|mall|temple|park|beach|shopping|party|visit)\b")  # a cab to somewhere other than the airport
DELAY_RE = re.compile(r"\b(delay|delayed|late|rebook|alternative|alternate|another|postponed|cancelled|dusri|doosri|dusra)\b")
BOOK_RE = re.compile(r"\b(book|reserve|buy)\b|kar do|kardo|\bkaro\b")
STATUS_RE = re.compile(r"\b(when|kab|status|pnr|what time|kitne baje|details|where|on time)\b")
STATUS_QUESTION_RE = re.compile(
    r"^\s*(?:is|are|was|has|did|does|will)\b.*\b(?:on time|delayed|late|cancelled|canceled|running late|landed|taken off)\b|"
    r"\b(?:any update|update on|still on time|on time)\b"
)
DELAY_LEN_RE = re.compile(
    r"(?:delayed|delay|late)\s+(?:by\s+)?(?:about\s+|around\s+|almost\s+)?(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b|"
    r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s+(?:late|delayed|delay)\b"
)
WANTS_CHANGE_RE = re.compile(r"\b(find|another|alternative|alternate|rebook|book|change|instead|something else)\b")
BUDGET_RE = re.compile(r"(?:\b(?:under|below|budget|max|within|rs\.?|rupees)|₹)\s*(\d[\d,]*)\s*(k)?")
BY_RE = re.compile(
    r"\b(?:by|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b(?!\s*(?:" + MONTHS + r"|hours?|hrs?|minutes?|mins?|days?))"
)  # "by 10" is a deadline; "by 2 hours" (a delay length) and "by 5 december" are not
SELF_RE = re.compile(r"\b(me|myself|mera|meri|mujhe|mere)\b")


# ---------------------------------------------------------------- helpers

def _data(state) -> dict:
    return state.domains["travel"]


def _find_trip(state, trip_id: str) -> dict:
    trip = next((t for t in _data(state)["trips"] if t["id"] == trip_id), None)
    if trip is None:
        raise ToolError(f"no trip {trip_id}")
    return trip


def _catalog_flight(state, flight_id: str) -> dict:
    flight = next((f for f in _data(state)["catalog"] if f["id"] == flight_id), None)
    if flight is None:
        raise ToolError(f"unknown flight {flight_id}")
    return flight


def _seat_pref(state, member_id: str) -> str | None:
    for fact in state.facts_about(member_id):
        low = fact["fact"].lower()
        if "aisle" in low:
            return "aisle"
        if "window" in low:
            return "window"
    return None


def _budget_pref(state, member_id: str) -> int | None:
    for fact in state.facts_about(member_id):
        m = re.search(r"under rs\.?\s*([\d,]+)", fact["fact"].lower())
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _prefers_morning(state, member_ids: list[str]) -> bool:
    return any("morning" in f["fact"].lower() for mid in member_ids for f in state.facts_about(mid))


def _money(n: int) -> str:
    return f"Rs {n:,}"


def _maybe_chaos(state, flight_id: str) -> None:
    """With the supplier-failure toggle on, the first seat hold fails once; the agent falls back."""
    data = _data(state)
    if not state.chaos:
        data["chaos_consumed"] = False
        return
    if not data.get("chaos_consumed"):
        data["chaos_consumed"] = True
        raise ToolError(f"Seat hold on {flight_id} expired at supplier (HTTP 409)")


def _place_seats(state, member_ids: list[str], flight: dict, forced: str | None) -> dict:
    pools = {"aisle": ["C", "D"], "window": ["A", "F"], None: ["B", "E"]}
    row = 10 + sum(ord(c) for c in flight["id"]) % 15
    taken: set[tuple[int, str]] = set()
    seats = {}
    for mid in member_ids:
        pref = forced or _seat_pref(state, mid)
        if pref and not flight["seats"].get(pref, False):
            pref = next((k for k, open_ in flight["seats"].items() if open_), None)
        letters = pools.get(pref, pools[None])
        for r in range(row, row + 10):
            free = next((letter for letter in letters if (r, letter) not in taken), None)
            if free:
                taken.add((r, free))
                seats[mid] = f"{r}{free}"
                break
    return seats


def _pickup_for(trip: dict) -> tuple[str, str]:
    """Airport cab pickup is two hours before departure; returns (date, HH:MM)."""
    minutes = cal.to_min(trip["dep"]) - 120
    day = _date.fromisoformat(trip["date"])
    if minutes < 0:
        day -= timedelta(days=1)
        minutes += 24 * 60
    return day.isoformat(), cal.to_hhmm(minutes)


def _trip_summary(trip: dict) -> dict:
    return {k: trip.get(k) for k in ("id", "member_ids", "route", "date", "flight", "airline", "dep", "arr", "seats", "status",
                                     "delay_min", "pnr", "cab", "fare_total")}


def _next_pnr(state, flight_id: str, prefix: str) -> str:
    data = _data(state)
    data["seq"] = data.get("seq", 0) + 1
    return f"{prefix}{data['seq']:02d}{re.sub('[^A-Z0-9]', '', flight_id.upper())[-3:]}"


# ---------------------------------------------------------------- tools

def search_flights(state, route: str, date: str, max_budget: int | None = None, seat: str | None = None,
                   arrive_by: str | None = None, earliest_dep: str | None = None, passengers: int = 1,
                   prefer_morning: bool = False) -> dict:
    catalog = [f for f in _data(state)["catalog"] if f["route"] == route and f["date"] == date]
    if not catalog:
        return {"options": [], "fallbacks": [], "blocked": {}, "cheapest_on_time": None, "note": "no flights on that route and date"}
    relaxed = []
    if earliest_dep and not any(cal.to_min(f["dep"]) >= cal.to_min(earliest_dep) for f in catalog):
        earliest_dep = None
        relaxed.append("earliest_dep")
    blocked = {"late": 0, "early": 0, "budget": 0, "seat": 0}
    hard, options = [], []
    for f in sorted(catalog, key=lambda f: (f["price"], f["dep"])):
        if arrive_by and cal.to_min(f["arr"]) > cal.to_min(arrive_by):
            blocked["late"] += 1
        elif earliest_dep and cal.to_min(f["dep"]) < cal.to_min(earliest_dep):
            blocked["early"] += 1
        else:
            hard.append(f)
            if max_budget and f["price"] > max_budget:
                blocked["budget"] += 1
            elif seat and not f["seats"].get(seat, False):
                blocked["seat"] += 1
            else:
                options.append(f)

    def rank(f):
        if arrive_by:
            return (-cal.to_min(f["arr"]), f["price"])
        late_dep = 1 if prefer_morning and cal.to_min(f["dep"]) >= 12 * 60 else 0
        return (late_dep, f["price"], f["dep"])

    options.sort(key=rank)
    fallbacks = sorted((f for f in hard if f not in options), key=rank)
    cheapest = min(hard, key=lambda f: f["price"]) if hard else None
    with_total = lambda f: {**f, "total_price": f["price"] * max(1, passengers)}  # noqa: E731
    return {
        "options": [with_total(f) for f in options], "fallbacks": [f["id"] for f in fallbacks], "blocked": blocked,
        "cheapest_on_time": with_total(cheapest) if cheapest else None, "relaxed": relaxed,
    }


def book_flight(state, flight_id: str, member_ids: list[str], seat_pref: str | None = None) -> dict:
    if not member_ids:
        raise ToolError("no passengers given")
    _maybe_chaos(state, flight_id)
    flight = _catalog_flight(state, flight_id)
    data = _data(state)
    trip = {
        "id": f"trip-{len(data['trips']) + 1}", "member_ids": list(member_ids), "route": flight["route"],
        "date": flight["date"], "flight": flight["id"], "airline": flight["airline"], "dep": flight["dep"],
        "arr": flight["arr"], "seats": _place_seats(state, member_ids, flight, seat_pref), "status": "BOOKED",
        "delay_min": 0, "pnr": _next_pnr(state, flight["id"], "A"), "cab": None,
        "fare_total": flight["price"] * len(member_ids), "per_person": flight["price"], "calendar_event_id": None,
    }
    data["trips"].append(trip)
    data["bookings"].append({"trip_id": trip["id"], "pnr": trip["pnr"], "flight": flight["id"], "fare_total": trip["fare_total"]})
    return _trip_summary(trip)


def rebook_flight(state, trip_id: str, flight_id: str, seat_pref: str | None = None) -> dict:
    trip = _find_trip(state, trip_id)
    _maybe_chaos(state, flight_id)
    flight = _catalog_flight(state, flight_id)
    trip.setdefault("history", []).append({"flight": trip["flight"], "dep": trip["dep"], "arr": trip["arr"], "pnr": trip["pnr"]})
    trip.update({
        "route": flight["route"], "date": flight["date"], "flight": flight["id"], "airline": flight["airline"],
        "dep": flight["dep"], "arr": flight["arr"], "seats": _place_seats(state, trip["member_ids"], flight, seat_pref),
        "status": "REBOOKED", "pnr": _next_pnr(state, flight["id"], "R"),
        "fare_total": flight["price"] * len(trip["member_ids"]), "per_person": flight["price"],
    })
    _data(state)["bookings"].append({"trip_id": trip_id, "pnr": trip["pnr"], "flight": flight["id"], "fare_total": trip["fare_total"], "rebook": True})
    return _trip_summary(trip)


def book_cab(state, trip_id: str | None = None, member_ids: list[str] | None = None, pickup_time: str | None = None,
             pickup_date: str | None = None, from_place: str = "Home", to_place: str | None = None) -> dict:
    data = _data(state)
    trip = _find_trip(state, trip_id) if trip_id else None
    if trip:
        member_ids = member_ids or trip["member_ids"]
        default_date, default_time = _pickup_for(trip)
        pickup_date, pickup_time = pickup_date or default_date, pickup_time or default_time
        to_place = to_place or "Kempegowda Airport T1"
    if not member_ids or not pickup_time:
        raise ToolError("need a pickup time and who is travelling")
    pickup_date = pickup_date or state.now["date"]
    booking = f"CAB-{8841 + len(data['cabs']) + 1}"
    cab = {
        "booking": booking, "trip_id": trip_id, "member_ids": list(member_ids), "pickup_date": pickup_date,
        "pickup": pickup_time, "from": from_place, "to": to_place or "Destination",
        "vehicle": "SUV (6-seater)" if len(member_ids) >= 4 else "Sedan", "status": "CONFIRMED",
    }
    data["cabs"].append(cab)
    if trip:
        trip["cab"] = {"booking": booking, "pickup_date": pickup_date, "pickup": pickup_time, "status": "CONFIRMED"}
    return cab


def update_cab_pickup(state, trip_id: str, pickup_time: str | None = None, pickup_date: str | None = None) -> dict:
    trip = _find_trip(state, trip_id)
    default_date, default_time = _pickup_for(trip)
    pickup_time, pickup_date = pickup_time or default_time, pickup_date or default_date
    if not trip.get("cab"):
        cab = book_cab(state, trip_id, None, pickup_time, pickup_date)
        return {"booking": cab["booking"], "old_pickup": None, "new_pickup": pickup_time, "pickup_date": pickup_date, "status": "CONFIRMED"}
    old = trip["cab"]["pickup"]
    trip["cab"].update({"pickup": pickup_time, "pickup_date": pickup_date, "status": "RESCHEDULED"})
    record = next((c for c in _data(state)["cabs"] if c["booking"] == trip["cab"]["booking"]), None)
    if record is None:
        record = {"booking": trip["cab"]["booking"], "trip_id": trip_id, "member_ids": trip["member_ids"], "from": "Home",
                  "to": "Kempegowda Airport T1", "vehicle": "Sedan", "driver": "Manjunath K"}
        _data(state)["cabs"].append(record)
    record.update({"pickup": pickup_time, "pickup_date": pickup_date, "status": "RESCHEDULED"})
    return {"booking": record["booking"], "old_pickup": old, "new_pickup": pickup_time, "pickup_date": pickup_date, "status": "RESCHEDULED"}


def add_trip_to_calendar(state, trip_id: str) -> dict:
    trip = _find_trip(state, trip_id)
    route = trip["route"].replace("->", "to")
    title = f"Family trip {route} ({trip['flight']})" if len(trip["member_ids"]) > 1 else f"Flight {trip['flight']} {route}"
    event = next((e for e in state.calendar if e["id"] == trip.get("calendar_event_id")), None)
    if event:
        cal.move_event(state, event["id"], date=trip["date"], start=trip["dep"], end=trip["arr"])
        event["title"] = title
    else:
        event = cal.add_event(state, trip["member_ids"], title, trip["date"], trip["dep"], trip["arr"],
                              f"{trip['route'].split(' -> ')[0]} airport", "travel", "travel")
        trip["calendar_event_id"] = event["id"]
    out = {"event_id": event["id"], "title": title, "date": trip["date"], "start": trip["dep"], "end": trip["arr"]}
    meeting = trip.get("meeting")
    if meeting:
        eta = cal.to_min(trip["arr"]) + meeting["transit_min"]
        out.update({"venue_eta": cal.to_hhmm(eta), "slack_min": cal.to_min(meeting["start"]) - eta})
    return out


def notify_family(state, member_ids: list[str], message: str) -> dict:
    note = state.notify(member_ids, message, "travel", "travel")
    return {"notified": member_ids, "channel": note["channel"], "mode": note["mode"], "status": note["status"]}


def get_trip(state, trip_id: str | None = None, member_id: str | None = None) -> dict:
    trips = [t for t in _data(state)["trips"] if (not trip_id or t["id"] == trip_id) and (not member_id or member_id in t["member_ids"])]
    return {"trips": [_trip_summary(t) for t in trips]}


def flight_status_webhook(state, trip_id: str, delay_min: int) -> dict:
    trip = _find_trip(state, trip_id)
    trip.setdefault("orig_dep", trip["dep"])
    trip.setdefault("orig_arr", trip["arr"])
    trip.update({
        "status": "DELAYED", "delay_min": delay_min,
        "dep": cal.to_hhmm(cal.to_min(trip["dep"]) + delay_min), "arr": cal.to_hhmm(cal.to_min(trip["arr"]) + delay_min),
    })
    return {"trip_id": trip_id, "flight": trip["flight"], "delay_min": delay_min, "new_dep": trip["dep"], "new_arr": trip["arr"]}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


_STR, _INT = {"type": "string"}, {"type": "integer"}
_IDS = {"type": "array", "items": {"type": "string"}, "description": "family member ids"}

TOOLS = [
    Tool("search_flights", "Search the flight catalog for a route and date with optional budget, seat, arrival-time and departure-time limits.",
         _obj({"route": {**_STR, "description": "e.g. 'BLR -> GOI'"}, "date": {**_STR, "description": "YYYY-MM-DD"},
               "max_budget": {**_INT, "description": "max fare per person in rupees"}, "seat": {"type": "string", "enum": ["aisle", "window"]},
               "arrive_by": {**_STR, "description": "latest arrival HH:MM"}, "earliest_dep": {**_STR, "description": "earliest departure HH:MM"},
               "passengers": _INT, "prefer_morning": {"type": "boolean"}}, ["route", "date"]), search_flights),
    Tool("book_flight", "Book a flight for one or more family members; seats follow each person's remembered preference.",
         _obj({"flight_id": _STR, "member_ids": _IDS, "seat_pref": {"type": "string", "enum": ["aisle", "window"]}}, ["flight_id", "member_ids"]),
         book_flight),
    Tool("rebook_flight", "Move an existing trip to a different flight (for example after a delay).",
         _obj({"trip_id": _STR, "flight_id": _STR, "seat_pref": {"type": "string", "enum": ["aisle", "window"]}}, ["trip_id", "flight_id"]),
         rebook_flight),
    Tool("book_cab", "Book a cab: for a trip's airport run (pickup defaults to 2 hours before departure) or an ad-hoc ride.",
         _obj({"trip_id": _STR, "member_ids": _IDS, "pickup_time": {**_STR, "description": "HH:MM"}, "pickup_date": {**_STR, "description": "YYYY-MM-DD"},
               "from_place": _STR, "to_place": _STR}, []), book_cab),
    Tool("update_cab_pickup", "Move a trip's cab pickup; with no time it is recomputed as 2 hours before the current departure.",
         _obj({"trip_id": _STR, "pickup_time": {**_STR, "description": "HH:MM"}, "pickup_date": {**_STR, "description": "YYYY-MM-DD"}}, ["trip_id"]),
         update_cab_pickup),
    Tool("add_trip_to_calendar", "Add or update the trip's flight in the calendar of everyone travelling.",
         _obj({"trip_id": _STR}, ["trip_id"]), add_trip_to_calendar),
    Tool("notify_family", "Send a travel update to family members over Agora Chat.",
         _obj({"member_ids": _IDS, "message": _STR}, ["member_ids", "message"]), notify_family, stage="after"),
    Tool("get_trip", "Look up trips by trip id or by traveller.",
         _obj({"trip_id": _STR, "member_id": _STR}, []), get_trip),
    Tool("flight_status_webhook", "Record a flight delay reported by the airline.",
         _obj({"trip_id": _STR, "delay_min": _INT}, ["trip_id", "delay_min"]), flight_status_webhook),
]


# ---------------------------------------------------------------- agent

class TravelAgent(Specialist):
    name = "travel"
    title = "Travel agent"
    family_keys = ("trips", "bookings", "cabs", "chaos_consumed", "seq")
    keywords = ("flight", "fly", "trip", "travel", "ticket", "airport", "cab", "taxi", "delay", "rebook", "goa", "delhi")
    tools = TOOLS

    def __init__(self) -> None:
        self.triggers = [Trigger("flight_delay", "Rahul's flight delayed", self._flight_delay)]

    def seed(self) -> dict:
        return {
            "trips": [
                {
                    "id": "trip-1", "member_ids": ["rahul"], "route": "BLR -> DEL", "date": "2026-11-23",
                    "flight": "6E-2045", "airline": "IndiGo", "dep": "05:30", "arr": "08:20",
                    "seats": {"rahul": "14C"}, "status": "ON_TIME", "delay_min": 0, "pnr": "K7QX2M",
                    "cab": {"booking": "CAB-8841", "pickup_date": "2026-11-23", "pickup": "03:30", "status": "CONFIRMED"},
                    "calendar_event_id": "flight-mon", "must_arrive_by": "09:15", "fare_total": 6800,
                    "meeting": {"title": "Client meeting - Cyber Hub, Gurugram", "place": "Cyber Hub", "start": "10:30",
                                "transit_min": 60, "buffer_min": 15},
                }
            ],
            "bookings": [],
            "cabs": [],
            "chaos_consumed": False,
            "seq": 0,
            "catalog": [
                {"id": "SG-8153", "airline": "SpiceJet", "route": "BLR -> DEL", "date": "2026-11-23", "dep": "06:00", "arr": "08:50", "price": 7400, "seats": {"aisle": False, "window": True}},
                {"id": "AI-502", "airline": "Air India", "route": "BLR -> DEL", "date": "2026-11-23", "dep": "06:10", "arr": "09:00", "price": 9200, "seats": {"aisle": True, "window": True}},
                {"id": "6E-6107", "airline": "IndiGo", "route": "BLR -> DEL", "date": "2026-11-23", "dep": "06:20", "arr": "09:10", "price": 7900, "seats": {"aisle": True, "window": False}},
                {"id": "QP-1411", "airline": "Akasa Air", "route": "BLR -> DEL", "date": "2026-11-23", "dep": "06:45", "arr": "09:35", "price": 6900, "seats": {"aisle": True, "window": True}},
                {"id": "6E-512", "airline": "IndiGo", "route": "BLR -> GOI", "date": "2026-12-26", "dep": "07:10", "arr": "08:30", "price": 4200, "seats": {"aisle": True, "window": True}},
                {"id": "AI-544", "airline": "Air India", "route": "BLR -> GOI", "date": "2026-12-26", "dep": "09:00", "arr": "10:20", "price": 5100, "seats": {"aisle": True, "window": True}},
                {"id": "QP-1127", "airline": "Akasa Air", "route": "BLR -> GOI", "date": "2026-12-26", "dep": "13:30", "arr": "14:50", "price": 3900, "seats": {"aisle": True, "window": True}},
            ],
        }

    # --- routing

    def score(self, state, text: str) -> int:
        from .money import is_money

        low = text.lower()
        if is_money(low):  # spending talk belongs to the Money agent
            return 0
        score = 0
        if FLIGHT_RE.search(low):
            score += 3
        if CAB_RE.search(low):
            score += 1 if OTHER_DOMAIN_RE.search(low) and not AIRPORT_RE.search(low) else 3
        if re.search(rf"\b(trip|travel)\b", low) and re.search(rf"\b({_CITY_ALT})\b", low):
            score += 3
        if score and re.search(r"\b(trip|travel|delay|delayed|goa|delhi)\b", low):
            score += 1
        return score

    # --- conversation

    def handle(self, state, member_id: str, text: str) -> str | None:
        pending = state.pending if state.pending and state.pending.get("agent") == self.name else None
        if pending:
            return self._handle_pending(state, member_id, text, pending)
        low = text.lower()
        has_flight = bool(FLIGHT_RE.search(low))
        route, dest = self._parse_route(text)
        trip = self._trip_for(state, member_id, text)
        if has_flight and STATUS_QUESTION_RE.search(low) and not WANTS_CHANGE_RE.search(low):
            return self._status(state, member_id, trip)
        if has_flight and DELAY_RE.search(low) and trip and (dest is None or trip["route"].endswith(dest)):
            reported = DELAY_LEN_RE.search(low)
            if reported and trip["status"] == "ON_TIME":  # "delayed by two hours": record it so status questions agree
                amount, unit = float(reported.group(1) or reported.group(3)), reported.group(2) or reported.group(4)
                self.call(state, "flight_status_webhook", trip_id=trip["id"], delay_min=int(amount * 60 if unit.startswith("h") else amount))
            ctx = self._rebook_ctx(state, trip)
            return self._propose(state, member_id, ctx, self._parse_changes(state, text, ctx))
        if CAB_RE.search(low) and not (has_flight and BOOK_RE.search(low) and dest):
            return self._cab(state, member_id, text, trip)
        if has_flight and STATUS_RE.search(low) and not BOOK_RE.search(low) and dest is None:
            return self._status(state, member_id, trip)
        if has_flight or (re.search(r"\b(trip|travel)\b", low) and dest):
            return self._new_trip(state, member_id, text, None)
        return None

    def _handle_pending(self, state, member_id: str, text: str, pending: dict) -> str:
        low, tokens = text.lower(), set(re.findall(r"[a-z]+", text.lower()))
        kind = pending["kind"]
        if kind == "await_details":
            return self._new_trip(state, member_id, text, pending)
        if kind == "await_cab":
            return self._cab(state, member_id, text, None, pending)
        if kind == "flight" and FLIGHT_RE.search(low) and STATUS_QUESTION_RE.search(low) and not WANTS_CHANGE_RE.search(low):
            status = self._status(state, member_id, self._trip_for(state, member_id, text))
            return status + self.say(state, member_id, " Shall I still book the alternative?", " Alternative book kar doon?")
        changed = self._parse_changes(state, text, pending)
        if changed:
            return self._propose(state, member_id, pending, changed)
        if tokens & REJECT:
            state.pending = None
            return self.say(state, member_id, "Okay, I've dropped that. Tell me what to change and I'll search again.",
                            "Theek hai, cancel kar diya. Kuch badalna ho to batao, main dobara dhundta hoon.")
        if tokens & CONFIRM or "kar do" in low:
            return self._execute(state, member_id, pending)
        flight = pending.get("flight_id") or "that flight"
        return self.say(state, member_id, f"I'm still holding {flight} for you. Shall I book it, or change something?",
                        f"{flight} abhi hold pe hai. Book kar doon, ya kuch badalna hai?")

    # --- parsing

    def _parse_route(self, text: str) -> tuple[str | None, str | None]:
        low = text.lower()
        origin = dest = None
        m = re.search(rf"\bfrom\s+({_CITY_ALT})\b", low)
        if m:
            origin = CITIES[m.group(1)]
        m = re.search(rf"\b(?:to|for)\s+({_CITY_ALT})\b", low) or re.search(rf"\b({_CITY_ALT})\s+(?:ki|ke|ka|jaane|chalo)\b", low)
        if m:
            dest = CITIES[m.group(1)]
        if dest is None:
            others = [CITIES[c] for c in CITIES if re.search(rf"\b{re.escape(c)}\b", low) and CITIES[c] != origin]
            dest = others[0] if others else None
        origin = origin or "BLR"
        if dest is None or dest == origin:
            return None, None
        return f"{origin} -> {dest}", dest

    def _trip_for(self, state, member_id: str, text: str) -> dict | None:
        trips = [t for t in _data(state)["trips"] if t["status"] != "CANCELLED"]
        ordered = sorted(trips, key=lambda t: (t["date"], t["dep"]))
        for mid in [m["id"] for m in state.mentioned_members(text)] + [member_id]:
            match = next((t for t in ordered if mid in t["member_ids"] and t["date"] >= state.now["date"]), None)
            if match:
                return match
        return None

    def _parse_changes(self, state, text: str, ctx: dict) -> list[str]:
        low, c, changed = text.lower(), ctx["constraints"], []
        seat = "aisle" if "aisle" in low else "window" if ("window" in low or "khidki" in low) else None
        if seat and seat != c.get("seat"):
            c["seat"] = seat
            changed.append(f"{seat} seat")
        m = BUDGET_RE.search(low)
        if m:
            value = int(m.group(1).replace(",", ""))
            value *= 1000 if (m.group(2) or value < 100) else 1
            if value != c.get("max_budget"):
                c["max_budget"] = value
                changed.append(f"budget {_money(value)}")
        m = BY_RE.search(low)
        if m:
            hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
            if ap == "pm" and hour < 12:
                hour += 12
            deadline = hour * 60 + minute
            trip = next((t for t in _data(state)["trips"] if t["id"] == ctx.get("trip_id")), None)
            meeting = trip.get("meeting") if trip else None
            arrive_by = deadline - (meeting["transit_min"] + meeting["buffer_min"] if meeting else 0)
            if cal.to_hhmm(arrive_by) != c.get("arrive_by"):
                c["arrive_by"] = cal.to_hhmm(arrive_by)
                changed.append(f"reach by {cal.to_hhmm(deadline)}")
        if ctx["mode"] == "new" and ctx.get("date"):
            new_date = cal.parse_date(text, state.now["date"])
            if new_date and new_date != ctx["date"]:
                ctx["date"] = new_date
                changed.append(new_date)
        return changed

    # --- flight flows

    def _rebook_ctx(self, state, trip: dict) -> dict:
        who = trip["member_ids"][0]
        return {
            "agent": self.name, "kind": "flight", "mode": "rebook", "trip_id": trip["id"], "member_ids": list(trip["member_ids"]),
            "route": trip["route"], "date": trip["date"], "flight_id": None, "alternates": [],
            "constraints": {"seat": _seat_pref(state, who), "max_budget": _budget_pref(state, who), "arrive_by": trip.get("must_arrive_by")},
        }

    def _new_trip(self, state, member_id: str, text: str, ctx: dict | None) -> str:
        low = text.lower()
        if ctx is None:
            pax = [m["id"] for m in state.mentioned_members(text)]
            if SELF_RE.search(low) and member_id not in pax:
                pax.append(member_id)
            ctx = {
                "agent": self.name, "kind": "await_details", "mode": "new", "explicit_book": bool(BOOK_RE.search(low)),
                "member_ids": pax or [member_id], "route": None, "date": None, "flight_id": None, "alternates": [],
                "constraints": {},
            }
        route, _ = self._parse_route(text)
        ctx["route"] = ctx["route"] or route
        ctx["date"] = ctx["date"] or cal.parse_date(text, state.now["date"])
        if not ctx["route"] or not ctx["date"]:
            state.pending = ctx
            need_route, need_date = not ctx["route"], not ctx["date"]
            return self.say(
                state, member_id,
                "Where would you like to fly, and on which date?" if need_route and need_date
                else "Which city should I fly to?" if need_route else "Which date should I book it for?",
                "Kahan jaana hai aur kis date ko?" if need_route and need_date
                else "Kis shehar ki flight chahiye?" if need_route else "Kis date ke liye book karun?",
            )
        ids = ctx["member_ids"]
        kinds = {state.member(i)["kind"] for i in ids}
        c = ctx["constraints"]
        if kinds & {"senior", "child"}:
            c["earliest_dep"] = "08:00"
        c["prefer_morning"] = bool(kinds & {"senior", "child"}) or _prefers_morning(state, ids)
        if len(ids) == 1:
            c.setdefault("seat", _seat_pref(state, ids[0]))
            c.setdefault("max_budget", _budget_pref(state, ids[0]))
        ctx["kind"] = "flight"
        changed = self._parse_changes(state, text, ctx)
        if ctx["explicit_book"] and not changed:
            res = self._search_into(state, ctx)
            if res["options"]:
                return self._execute(state, member_id, ctx)
            return self._no_match(state, member_id, ctx, res, changed)
        return self._propose(state, member_id, ctx, changed)

    def _search_into(self, state, ctx: dict) -> dict:
        c = ctx["constraints"]
        _, res = self.call(
            state, "search_flights", route=ctx["route"], date=ctx["date"], max_budget=c.get("max_budget"), seat=c.get("seat"),
            arrive_by=c.get("arrive_by"), earliest_dep=c.get("earliest_dep"), passengers=len(ctx["member_ids"]),
            prefer_morning=c.get("prefer_morning", False),
        )
        options = res["options"]
        ctx["flight_id"] = options[0]["id"] if options else None
        ctx["alternates"] = [f["id"] for f in options[1:]] + res["fallbacks"]
        return res

    def _no_match(self, state, member_id: str, ctx: dict, res: dict, changed: list[str]) -> str:
        state.pending = ctx
        lead = (("Theek hai, " if state.speaks_hindi(member_id) else "Updated: ") + ", ".join(changed) + ". ") if changed else ""
        cheap = res.get("cheapest_on_time")
        if res.get("note"):
            ctx["kind"] = "flight"
            return lead + self.say(state, member_id, "I couldn't find any flights on that route and date. Try another date?",
                                   "Us route aur date pe koi flight nahi mili. Koi aur date try karein?")
        if cheap:
            return lead + self.say(
                state, member_id,
                f"Nothing matches those limits. The cheapest that still works is {cheap['airline']} {cheap['id']} at {_money(cheap['price'])}. Relax the budget or seat?",
                f"Aapki conditions pe koi flight nahi mili. Sabse sasti jo chalegi woh {cheap['airline']} {cheap['id']} hai, {_money(cheap['price'])} mein. Budget ya seat relax karein?",
            )
        return lead + self.say(state, member_id, "No flight fits that deadline.", "Is deadline tak koi flight nahi hai.")

    def _propose(self, state, member_id: str, ctx: dict, changed: list[str]) -> str:
        res = self._search_into(state, ctx)
        if not res["options"]:
            return self._no_match(state, member_id, ctx, res, changed)
        best = res["options"][0]
        c, ids = ctx["constraints"], ctx["member_ids"]
        state.pending = ctx
        hi = state.speaks_hindi(member_id)
        lead = (("Theek hai, " if hi else "Updated: ") + ", ".join(changed) + ". ") if changed else ""
        price_en = f"{_money(best['price'])}" + (f" each, {_money(best['total_price'])} for {len(ids)}" if len(ids) > 1 else "")
        price_hi = f"{_money(best['price'])}" + (f" per person, kul {_money(best['total_price'])}" if len(ids) > 1 else "")
        seat_en = f", {c['seat']} seat" if c.get("seat") and len(ids) == 1 else ""
        trip = next((t for t in _data(state)["trips"] if t["id"] == ctx.get("trip_id")), None)
        meeting = trip.get("meeting") if trip else None
        reach = ""
        if meeting:
            eta = cal.to_hhmm(cal.to_min(best["arr"]) + meeting["transit_min"])
            reach = (f" You would reach {meeting['place']} by {eta}.", f" {meeting['place']} aap {eta} tak pahunch jaoge.")
        elif c.get("earliest_dep"):
            vulnerable = [state.member(i)["name"] for i in ids if state.member(i)["kind"] in ("senior", "child")]
            reach = (f" A {best['dep']} departure keeps it easy for {' and '.join(vulnerable)}.",
                     f" {best['dep']} ki flight {' aur '.join(vulnerable)} ke liye aaram se rahegi.")
        reach_en, reach_hi = reach or ("", "")
        en = f"{lead}Best match: {best['airline']} {best['id']}, departs {best['dep']}, lands {best['arr']}, {price_en}{seat_en}.{reach_en} Shall I book it?"
        hi_text = f"{lead}Sabse best: {best['airline']} {best['id']}, {best['dep']} se {best['arr']}, {price_hi}{seat_en}.{reach_hi} Book kar doon?"
        return self.say(state, member_id, en, hi_text)

    def _execute(self, state, member_id: str, ctx: dict) -> str:
        if not ctx.get("flight_id"):
            return self.say(state, member_id, "There's nothing to book yet. Change a limit and I'll search again.",
                            "Abhi book karne ko kuch nahi hai. Koi limit badlo, main dobara dhundta hoon.")
        state.pending = None
        c = ctx["constraints"]
        booked, fallback_used = None, False
        for i, flight_id in enumerate([ctx["flight_id"], *ctx["alternates"]]):
            if ctx["mode"] == "rebook":
                status, res = self.call(state, "rebook_flight", trip_id=ctx["trip_id"], flight_id=flight_id, seat_pref=c.get("seat"))
            else:
                status, res = self.call(state, "book_flight", flight_id=flight_id, member_ids=ctx["member_ids"], seat_pref=c.get("seat"))
            if status == "ok":
                booked, fallback_used = res, i > 0
                break
        if not booked:
            return self.say(state, member_id, "I couldn't hold any of the options. Want me to try again?",
                            "Koi bhi flight hold nahi ho paayi. Main dobara try karun?")
        trip_id = booked["id"]
        cab_tool = "update_cab_pickup" if ctx["mode"] == "rebook" else "book_cab"
        results = run_parallel(state, self.name, [
            (self.tool(cab_tool), {"trip_id": trip_id}), (self.tool("add_trip_to_calendar"), {"trip_id": trip_id}),
        ])
        cab_res, cal_res = results[0][1], results[1][1]
        trip = _find_trip(state, trip_id)
        names = " and ".join(state.member(i)["name"] for i in trip["member_ids"])
        message = (f"{names}: {booked['flight']} {booked['dep']}-{booked['arr']} on {booked['date']}, PNR {booked['pnr']}, "
                   f"{_money(booked['fare_total'])}. Cab pickup {cab_res.get('new_pickup') or cab_res.get('pickup')}.")
        if "venue_eta" in cal_res:
            message += f" Venue ETA {cal_res['venue_eta']}."
        self.call(state, "notify_family", member_ids=[m["id"] for m in state.members], message=message)

        pickup = cab_res.get("new_pickup") or cab_res.get("pickup")
        swap_en = " The first seat hold failed, so I moved to the next best flight." if fallback_used else ""
        swap_hi = " Pehla seat hold fail ho gaya tha, isliye agla best flight liya." if fallback_used else ""
        if ctx["mode"] == "rebook":
            eta_en = f" You will reach by {cal_res['venue_eta']}." if "venue_eta" in cal_res else ""
            eta_hi = f" Aap {cal_res['venue_eta']} tak pahunch jaoge." if "venue_eta" in cal_res else ""
            return self.say(
                state, member_id,
                f"Done. {booked['flight']} is booked, PNR {booked['pnr']}. The cab now comes at {pickup}, the calendar is updated and the family is told.{eta_en}{swap_en}",
                f"Ho gaya! {booked['flight']} book hai, PNR {booked['pnr']}. Cab ab {pickup} baje aayegi, calendar update ho gaya aur family ko bata diya.{eta_hi}{swap_hi}",
            )
        n = len(trip["member_ids"])
        return self.say(
            state, member_id,
            f"Booked {n} ticket{'s' if n > 1 else ''} on {booked['flight']} for {_money(booked['fare_total'])}, PNR {booked['pnr']}. The cab is set for {pickup} and the trip is on everyone's calendar.{swap_en}",
            f"{n} ticket {booked['flight']} pe book ho gaye, kul {_money(booked['fare_total'])}, PNR {booked['pnr']}. Cab {pickup} baje ki hai aur trip sabke calendar mein hai.{swap_hi}",
        )

    # --- status and cabs

    def _status(self, state, member_id: str, trip: dict | None) -> str:
        if not trip:
            return self.say(state, member_id, "I don't see an upcoming flight. Want me to book one?", "Koi upcoming flight nahi dikh rahi. Book karun?")
        self.call(state, "get_trip", trip_id=trip["id"])
        who = " and ".join(state.member(i)["name"] for i in trip["member_ids"])
        cab = trip.get("cab")
        cab_en = f" The cab picks up at {cab['pickup']}." if cab else ""
        mine = trip["member_ids"] == [member_id]
        delay = trip.get("delay_min") or 0
        state_en = {"ON_TIME": "on time", "DELAYED": f"delayed by {delay // 60} hours" if delay >= 60 else "delayed",
                    "REBOOKED": "rebooked", "BOOKED": "booked"}.get(trip["status"], trip["status"].replace("_", " ").lower())
        return self.say(
            state, member_id,
            f"{'Your' if mine else who + chr(39) + 's'} flight is {trip['airline']} {trip['flight']} on {trip['date']}, "
            f"{trip['dep']} to {trip['arr']}. It is {state_en}. The booking reference is {trip['pnr']}.{cab_en}",
            f"{who}: {trip['airline']} {trip['flight']}, {trip['date']} ko {trip['dep']} se {trip['arr']}, status {trip['status'].replace('_', ' ').lower()}, PNR {trip['pnr']}.{(' Cab ' + cab['pickup'] + ' baje.') if cab else ''}",
        )

    def _cab(self, state, member_id: str, text: str, trip: dict | None, pending: dict | None = None) -> str:
        low = text.lower()
        time_given = cal.parse_time(text)
        date_given = cal.parse_date(text, state.now["date"]) or (pending or {}).get("date")  # "Sunday" said before the time
        airport_run = bool(AIRPORT_RE.search(low)) or (trip is not None and pending is None and not OTHER_DOMAIN_RE.search(low) and not OUTING_RE.search(low))
        if STATUS_RE.search(low) and not time_given and not BOOK_RE.search(low) and trip and trip.get("cab"):
            cab = trip["cab"]
            return self.say(state, member_id, f"Cab {cab['booking']} picks up at {cab['pickup']} on {cab.get('pickup_date', trip['date'])}.",
                            f"Cab {cab['booking']} {cab.get('pickup_date', trip['date'])} ko {cab['pickup']} baje aayegi.")
        if pending:
            state.pending = None
        if trip and airport_run:
            if time_given or not trip.get("cab"):
                _, res = self.call(state, "update_cab_pickup", trip_id=trip["id"], pickup_time=time_given, pickup_date=date_given)
            else:
                res = trip["cab"] | {"new_pickup": trip["cab"]["pickup"]}
            pickup = res.get("new_pickup") or res.get("pickup")
            self.call(state, "notify_family", member_ids=trip["member_ids"], message=f"Airport cab {res['booking']} is set for {pickup} on {res.get('pickup_date', trip['date'])}.")
            return self.say(state, member_id, f"Your airport cab {res['booking']} is set for {pickup}.", f"Airport cab {res['booking']} {pickup} baje ke liye set hai.")
        if time_given:
            mids = (pending or {}).get("member_ids") or self._riders(state, member_id, text)
            place = re.search(r"\bto (?:the )?([a-z ]{3,30}?)(?: at | by |$)", low)
            status, res = self.call(state, "book_cab", member_ids=mids, pickup_time=time_given, pickup_date=date_given or state.now["date"],
                                    to_place=place.group(1).title() if place else None)
            if status == "ok":
                day = res.get("pickup_date") or date_given or state.now["date"]
                who = "" if len(mids) == 1 else f" for {len(mids)} of you"
                return self.say(state, member_id, f"Cab {res['booking']} is booked for {res['pickup']} on {day}{who}.",
                                f"Cab {res['booking']} {day} ko {res['pickup']} baje ke liye book ho gayi.")
        state.pending = {"agent": self.name, "kind": "await_cab", "date": date_given, "member_ids": self._riders(state, member_id, text)}
        return self.say(state, member_id, "What time should the cab pick you up?", "Cab kitne baje bulaun?")

    @staticmethod
    def _riders(state, member_id: str, text: str) -> list[str]:
        """Who the cab is for: the people named, else the whole family when the request says so, else the speaker."""
        named = [m["id"] for m in state.mentioned_members(text)]
        if named:
            return named
        if re.search(r"\b(family|everyone|everybody|all of us|we all|hum sab)\b", text.lower()):
            return [m["id"] for m in state.members]
        return [member_id]

    # --- trigger

    def _flight_delay(self, state) -> str:
        trip = next((t for t in _data(state)["trips"] if t["id"] == "trip-1"), None)
        if trip is None or trip["status"] != "ON_TIME":
            msg = "Rahul's Monday flight has already been handled."
            state.say("agent", msg, "rahul", agent=self.name)
            return msg
        self.call(state, "flight_status_webhook", trip_id="trip-1", delay_min=180)
        meeting = trip["meeting"]
        if not any("Client meeting" in e["title"] and e["date"] == trip["date"] for e in state.calendar):
            cal.add_event(state, ["rahul"], meeting["title"], trip["date"], meeting["start"], cal.to_hhmm(cal.to_min(meeting["start"]) + 60),
                          meeting["place"], "work", "travel")
        self.call(state, "add_trip_to_calendar", trip_id="trip-1")
        late = cal.to_min(trip["arr"]) + meeting["transit_min"] - cal.to_min(meeting["start"])
        self.call(state, "notify_family", member_ids=[m["id"] for m in state.members],
                  message=f"Rahul's flight {trip['flight']} is delayed by 3 hours and now lands at {trip['arr']}; he would reach {meeting['place']} about {late} min after his {meeting['start']} meeting.")
        ctx = self._rebook_ctx(state, trip)
        res = self._search_into(state, ctx)
        intro = (f"Heads up Rahul: {trip['airline']} {trip['flight']} is delayed by 3 hours and now lands at {trip['arr']}. "
                 f"You would reach {meeting['place']} about {late} minutes after your {meeting['start']} meeting starts. ")
        if res["options"]:
            best = res["options"][0]
            state.pending = ctx
            eta = cal.to_hhmm(cal.to_min(best["arr"]) + meeting["transit_min"])
            msg = intro + (f"Best alternative: {best['airline']} {best['id']}, departs {best['dep']}, lands {best['arr']}, {_money(best['price'])}, "
                           f"aisle seat. You would reach {meeting['place']} by {eta}. Shall I book it?")
        else:
            msg = intro + "I couldn't find an alternative within your limits. Want me to relax the budget or seat?"
            state.pending = ctx
        state.say("agent", msg, "rahul", agent=self.name)
        return msg
