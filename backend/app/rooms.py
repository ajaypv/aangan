"""Family Rooms: several people plan something together (usually a trip) around one shared, live plan.

A room is a plain dict kept in `state.rooms` and saved in household.json with everything else (see ROOM_CONTRACT.md for
the exact shape the app reads). Keys that start with an underscore are the backend's own bookkeeping (id counters, the
voice session, presence); they are saved but never sent to the app.

Every change goes through a function here, under one lock, and bumps `version`. The app polls `GET /rooms/{id}?since=N`
and only gets the room back when the version has moved. The planner (planner.py) is the only thing that edits the plan
on its own, through the functions below; money is never moved except by `decide`, which a human taps.
"""

import copy
import logging
import math
import re
import secrets
import threading
import time
from datetime import date as _date, datetime, timedelta

from . import languages, travel_data
from .state import _zone

log = logging.getLogger("aangan.rooms")

LOCK = threading.RLock()
ONLINE_FOR_S = 20
MAX_MESSAGES_KEPT = 600
HOLDS = ("proposed", "selected", "booked", "rejected")
COST_CATEGORIES = ("flights", "stay", "food", "activities", "local", "other")
MEAL_TIMES = {"breakfast": "08:30", "lunch": "13:00", "dinner": "19:30", "snack": "17:00"}
PLACE_SLOTS = ("10:00", "15:00", "17:30", "11:30", "09:00")
DEMO_REF_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: a reference is read out loud


class RoomError(Exception):
    """A request the room cannot honour. `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ---------------------------------------------------------------- small helpers


def _time() -> float:
    return time.time()


def _hhmm(epoch: float | None = None) -> str:
    return datetime.fromtimestamp(epoch if epoch is not None else _time(), _zone()).strftime("%H:%M")


def _stamp() -> str:
    return datetime.fromtimestamp(_time(), _zone()).strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return datetime.fromtimestamp(_time(), _zone()).strftime("%Y-%m-%d")


def _next(room: dict, prefix: str) -> str:
    seq = room.setdefault("_seq", {})
    seq[prefix] = seq.get(prefix, 0) + 1
    return f"{prefix}-{seq[prefix]}"


def _next_int(room: dict, key: str) -> int:
    seq = room.setdefault("_seq", {})
    seq[key] = seq.get(key, 0) + 1
    return seq[key]


def _clean(text, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _money(n) -> str:
    return f"{int(round(n)):,}"


def _parse_date(value) -> _date:
    try:
        return _date.fromisoformat(str(value))
    except ValueError as exc:
        raise RoomError(400, f"dates must be YYYY-MM-DD, got {value!r}") from exc


def _nice_date(iso: str) -> str:
    try:
        d = _date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%b')}"


def empty_plan() -> dict:
    return {
        "goal": "", "destination": None, "origin": None, "dates": None, "travelers": [], "budget": None, "preferences": [],
        "traveler_count": None, "rooms": None,
        "flights": [], "hotels": [], "places": [], "restaurants": [], "itinerary": [], "costs": [], "decisions": [],
        "open_questions": [], "checklist": [],
    }


# ---------------------------------------------------------------- lookups


def _room(state, room_id: str) -> dict:
    room = state.rooms.get(room_id)
    if room is None:
        raise RoomError(404, "unknown room")
    return room


def _participant(room: dict, participant_id: str | None) -> dict:
    found = next((p for p in room["participants"] if p["id"] == participant_id), None)
    if found is None:
        raise RoomError(404, "unknown participant")
    return found


def _name_of(room: dict, participant_id: str | None) -> str:
    p = next((p for p in room["participants"] if p["id"] == participant_id), None)
    return p["name"] if p else ""


def _resolve_people(room: dict, people) -> tuple[list[str], list[str]]:
    """Participant ids from ids or names ('p-2', 'Meera'). Returns (ids, the ones that matched nobody)."""
    ids, unknown = [], []
    for raw in people or []:
        text = _clean(raw, 60).lower()
        match = next(
            (p for p in room["participants"] if p["id"].lower() == text or p["name"].lower() == text or p["name"].lower().split(" (")[0] == text),
            None,
        )
        if match is None:
            unknown.append(str(raw))
        elif match["id"] not in ids:
            ids.append(match["id"])
    return ids, unknown


def _new_uid(room: dict) -> int:
    """A random RTC uid, unique in the room and never the agent's own (the voice agent joins as 123456)."""
    from .agora import AGENT_UID

    used = {p["rtc_uid"] for p in room["participants"]} | {AGENT_UID}
    while True:
        uid = secrets.randbelow(9_999_000) + 1000
        if uid not in used:
            return uid


# ---------------------------------------------------------------- travellers, nights, costs


def travellers(room: dict) -> int:
    """How many people are going: the count the planner was told, else the named travellers, else everyone in the room."""
    plan = room["plan"]
    return int(plan.get("traveler_count") or len(plan["travelers"]) or len(room["participants"]) or 1)


def nights(plan: dict) -> int | None:
    dates = plan.get("dates")
    if not dates:
        return None
    return max((_parse_date(dates["end"]) - _parse_date(dates["start"])).days, 0)


def trip_days(plan: dict) -> int | None:
    n = nights(plan)
    return None if n is None else n + 1


def _day_to_date(plan: dict, day: int) -> str | None:
    dates = plan.get("dates")
    return (_parse_date(dates["start"]) + timedelta(days=day - 1)).isoformat() if dates else None


def _date_to_day(plan: dict, iso: str) -> int | None:
    dates = plan.get("dates")
    if not dates:
        return None
    try:
        return (_parse_date(iso) - _parse_date(dates["start"])).days + 1
    except RoomError:
        return None


def _item_cost(room: dict, kind: str, item: dict) -> int:
    """What one chosen thing costs the whole group, in rupees."""
    n = travellers(room)
    if kind == "flight":
        return int(item["price"] * n)
    if kind == "hotel":
        stay = nights(room["plan"])
        return int(item["price_per_night"] * (1 if stay is None else stay) * (room["plan"].get("rooms") or 1))
    if kind == "restaurant":
        return int(round(item["price_for_two"] * n / 2))
    return int(item.get("price", 0) * n)  # place


def cost_summary(room: dict) -> dict:
    """The derived money picture of the plan. Never stored and never written by the model: it is recomputed from what is
    chosen (selected or booked flights, hotel, restaurants and places, or the cheapest proposed flight and hotel when
    nothing is chosen yet) plus the explicit cost lines for things like local transport."""
    plan, n = room["plan"], travellers(room)
    lines: list[dict] = []
    by_day: dict[int, int] = {}

    def add(label: str, amount: int, category: str, estimate: bool, day: int | None = None) -> None:
        lines.append({"label": label, "amount": int(amount), "category": category, "estimate": estimate})
        if day:
            by_day[day] = by_day.get(day, 0) + int(amount)

    chosen = [f for f in plan["flights"] if f["status"] in ("selected", "booked")]
    defaulted = False
    if not chosen and plan["flights"]:
        proposed = [f for f in plan["flights"] if f["status"] == "proposed"]
        chosen, defaulted = ([min(proposed, key=lambda f: f["price"])] if proposed else []), True
    for f in chosen:
        add(f"{f['airline']} {f['number']} x {n}", _item_cost(room, "flight", f), "flights", defaulted or f["status"] != "booked",
            _date_to_day(plan, f["date"]))

    hotels = [h for h in plan["hotels"] if h["status"] in ("selected", "booked")]
    defaulted = False
    if not hotels and plan["hotels"]:
        proposed = [h for h in plan["hotels"] if h["status"] == "proposed"]
        hotels, defaulted = ([min(proposed, key=lambda h: h["price_per_night"])] if proposed else []), True
    for h in hotels:
        nn, rooms_n = nights(plan), plan.get("rooms") or 1
        add(f"{h['name']} x {nn if nn is not None else 1} nights", _item_cost(room, "hotel", h), "stay",
            defaulted or nn is None or h["status"] != "booked")
        for d in range(1, (nn or 0) + 1):
            by_day[d] = by_day.get(d, 0) + int(h["price_per_night"] * rooms_n)

    for r in plan["restaurants"]:
        if r["status"] in ("selected", "booked"):
            add(r["name"], _item_cost(room, "restaurant", r), "food", True, r.get("day"))
    for p in plan["places"]:
        if p["status"] in ("selected", "booked") and p.get("price"):
            add(p["name"], _item_cost(room, "place", p), "activities", True, p.get("day"))
    for c in plan["costs"]:
        category = c.get("category") if c.get("category") in COST_CATEGORIES else "other"
        add(c["label"], c["amount"], category, c.get("status", "estimate") == "estimate", c.get("day"))

    by_category = {k: 0 for k in COST_CATEGORIES}
    for line in lines:
        by_category[line["category"]] += line["amount"]
    total = sum(by_category.values())
    days = trip_days(plan)
    day_numbers = list(range(1, days + 1)) if days else sorted(by_day)
    budget = (plan.get("budget") or {}).get("total")
    return {
        "total": total, "per_person": int(round(total / n)), "travellers": n,
        "currency": (plan.get("budget") or {}).get("currency", "INR"),
        "by_category": by_category,
        "by_day": [{"day": d, "date": _day_to_date(plan, d), "amount": by_day.get(d, 0)} for d in day_numbers],
        "budget": budget, "remaining": (budget - total) if budget else None, "over_budget": bool(budget and total > budget),
        "estimate": any(line["estimate"] for line in lines), "lines": lines,
    }


def _sync_itinerary(room: dict) -> None:
    """Keep each itinerary line that comes from a flight, place or meal priced for the current group size, and in order."""
    plan = room["plan"]
    for entry in plan["itinerary"]:
        ref = entry.get("ref")
        if not ref:
            continue
        try:
            kind, item = _find(room, ref)
        except RoomError:
            continue
        entry["cost"] = None if kind == "hotel" else _item_cost(room, kind, item)
        if plan.get("dates") and entry.get("day"):
            entry["date"] = _day_to_date(plan, entry["day"])
    plan["itinerary"].sort(key=lambda e: (e.get("day") or 99, e.get("time") or "99:99"))


def _bump(room: dict) -> None:
    room["version"] += 1
    _sync_itinerary(room)


# ---------------------------------------------------------------- presentation


def _online_ids(room: dict) -> list[str]:
    now = _time()
    return sorted(p["id"] for p in room["participants"] if now - p.get("_seen", 0) < ONLINE_FOR_S)


def _refresh_presence(room: dict) -> None:
    """Going online or offline is a change the app should see, so it bumps the version; a heartbeat that changes nothing
    does not (otherwise every poll of every participant would defeat `since`)."""
    online = _online_ids(room)
    if online != room.get("_online"):
        room["_online"] = online
        _bump(room)


def _public(room: dict) -> dict:
    """The room as the app sees it: no bookkeeping, `online` worked out now, the derived cost summary on the plan."""
    online = set(_online_ids(room))
    voice = room.get("_voice") or {}
    pending = room.get("pending_approval")
    out = {
        "id": room["id"], "version": room["version"], "title": room["title"], "host_participant_id": room["host_participant_id"],
        "created_at": room["created_at"],
        "participants": [
            {**{k: v for k, v in p.items() if not k.startswith("_")}, "last_seen": _hhmm(p["_seen"]) if p.get("_seen") else p.get("joined_at", ""),
             "online": p["id"] in online}
            for p in room["participants"]
        ],
        "messages": copy.deepcopy(room["messages"]),
        "plan": copy.deepcopy(room["plan"]),
        "pending_approval": {k: copy.deepcopy(v) for k, v in pending.items() if not k.startswith("_")} if pending else None,
        "bookings": copy.deepcopy(room["bookings"]),
        "agent": {"live": bool(voice), "voice_session": voice.get("agent_id")},
    }
    out["plan"]["cost_summary"] = cost_summary(room)
    return out


def snapshot(state, room_id: str, since: int | None = None) -> dict:
    """The room state, or `{"id", "version", "unchanged": true}` when `since` is already the current version."""
    with LOCK:
        room = _room(state, room_id)
        _refresh_presence(room)
        if since is not None and since == room["version"]:
            return {"id": room["id"], "version": room["version"], "unchanged": True}
        return _public(room)


# ---------------------------------------------------------------- persistence


def export(rooms: dict, max_messages: int) -> dict:
    """The rooms for household.json: a private copy, each room keeping only its newest messages."""
    with LOCK:
        saved = copy.deepcopy(rooms)
    for room in saved.values():
        room["messages"] = room["messages"][-max_messages:]
    return saved


def restore(raw) -> dict:
    """Rooms from a saved file. A room that is not usable is skipped (with a log line); it never stops the household loading."""
    rooms: dict = {}
    for key, room in (raw.items() if isinstance(raw, dict) else []):
        try:
            if not isinstance(room, dict) or not isinstance(room["participants"], list) or not isinstance(room["messages"], list):
                raise ValueError("not a room")
            plan = {**empty_plan(), **room["plan"]}
            room.update({"plan": plan, "version": int(room["version"]), "id": str(room["id"]), "bookings": list(room.get("bookings") or [])})
            room.setdefault("pending_approval", None)
            for needed in ("title", "host_participant_id", "created_at"):
                room[needed]
            rooms[key] = room
        except Exception as exc:
            log.warning("skipping a saved room that could not be read (%s): %s", key, exc)
    return rooms


# ---------------------------------------------------------------- creating, joining, presence


def _new_participant(room: dict, name: str, member_id: str | None) -> dict:
    now = _time()
    p = {
        "id": _next(room, "p"), "name": name, "member_id": member_id, "guest": member_id is None, "rtc_uid": _new_uid(room),
        "joined_at": _hhmm(now), "last_seen": _hhmm(now), "_seen": now,
    }
    room["participants"].append(p)
    return p


def create_room(state, title: str, member_id: str) -> dict:
    if not state.members:
        raise RoomError(409, "Set up your family first.")
    member = next((m for m in state.members if m["id"] == member_id), None)
    if member is None:
        raise RoomError(404, f"unknown family member {member_id}")
    with LOCK:
        room_id = f"r-{secrets.token_hex(3)}"
        while room_id in state.rooms:
            room_id = f"r-{secrets.token_hex(3)}"
        room = {
            "id": room_id, "version": 0, "title": _clean(title, 80) or "Family plan", "host_participant_id": "", "created_at": _stamp(),
            "participants": [], "messages": [], "plan": empty_plan(), "pending_approval": None, "bookings": [],
        }
        room["host_participant_id"] = _new_participant(room, member["name"], member_id)["id"]
        room["_online"] = _online_ids(room)
        state.rooms[room_id] = room
        sync_family_needs(state, room_id)
        _bump(room)
        return _public(room)


def join(state, room_id: str, member_id: str | None = None, guest_name: str | None = None) -> tuple[dict, dict]:
    """Add someone to the room. A household member joining again is the same participant; so is a guest with the same name."""
    with LOCK:
        room = _room(state, room_id)
        if member_id:
            member = next((m for m in state.members if m["id"] == member_id), None)
            if member is None:
                raise RoomError(404, f"unknown family member {member_id}")
            existing = next((p for p in room["participants"] if p["member_id"] == member_id), None)
            name = member["name"]
        else:
            base = _clean(guest_name, 30)
            if not base:
                raise RoomError(400, "member_id or guest_name is required")
            name = base if base.lower().endswith("(guest)") else f"{base} (guest)"
            existing = next((p for p in room["participants"] if p["guest"] and p["name"].lower() == name.lower()), None)
        if existing is None:
            existing = _new_participant(room, name, member_id)
            _bump(room)
            sync_family_needs(state, room_id)
        existing["_seen"] = _time()
        _refresh_presence(room)
        public = _public(room)
        return next(p for p in public["participants"] if p["id"] == existing["id"]), public


def heartbeat(state, room_id: str, participant_id: str) -> None:
    with LOCK:
        room = _room(state, room_id)
        _participant(room, participant_id)["_seen"] = _time()
        _refresh_presence(room)


# ---------------------------------------------------------------- messages


def _append(room: dict, kind: str, participant_id: str | None, name: str, text: str) -> dict:
    msg = {
        "id": _next_int(room, "m"), "kind": kind, "participant_id": participant_id, "name": name, "text": text, "ts": _hhmm(),
        "lang": languages.detect(text),
    }
    room["messages"].append(msg)
    del room["messages"][:-MAX_MESSAGES_KEPT]
    _bump(room)
    return copy.deepcopy(msg)


def add_user_message(state, room_id: str, participant_id: str, text: str) -> dict:
    text = _clean(text, 2000)
    if not text:
        raise RoomError(400, "text is required")
    with LOCK:
        room = _room(state, room_id)
        who = _participant(room, participant_id)
        who["_seen"] = _time()
        return _append(room, "user", who["id"], who["name"], text)


def add_system_message(state, room_id: str, text: str) -> dict:
    with LOCK:
        return _append(_room(state, room_id), "system", None, "", _clean(text, 500))


def add_agent_message(state, room_id: str, text: str) -> dict:
    with LOCK:
        return _append(_room(state, room_id), "agent", None, "Aangan", _clean(text, 2000))


def get_message(state, room_id: str, message_id: int) -> dict | None:
    with LOCK:
        room = _room(state, room_id)
        return copy.deepcopy(next((m for m in room["messages"] if m["id"] == message_id), None))


def recent_messages(state, room_id: str, limit: int = 20) -> list[dict]:
    with LOCK:
        return copy.deepcopy(_room(state, room_id)["messages"][-limit:])


def plan_snapshot(state, room_id: str) -> dict:
    """The room's plan, bookings and pending approval as the planner reads them (with the derived costs)."""
    with LOCK:
        pub = _public(_room(state, room_id))
        return {"plan": pub["plan"], "pending_approval": pub["pending_approval"], "bookings": pub["bookings"], "participants": pub["participants"],
                "title": pub["title"], "host_participant_id": pub["host_participant_id"]}


# ---------------------------------------------------------------- what the household remembers about the people going


_NEED_TAGS = {"allergy", "veg", "access"}


def family_needs(state, room_id: str) -> dict:
    """Household memory that should steer the plan, for the people in the room that are household members and for any
    household member named in the discussion: {"step_free": [names], "veg": [names], "allergies": [(name, fact)], "facts": [(name, fact)]}."""
    with LOCK:
        room = _room(state, room_id)
        ids = [p["member_id"] for p in room["participants"] if p["member_id"]]
        said = " ".join(m["text"] for m in room["messages"] if m["kind"] == "user")
        for member in state.mentioned_members(said) if said else []:
            if member["id"] not in ids:
                ids.append(member["id"])
    needs: dict = {"step_free": [], "veg": [], "allergies": [], "facts": []}
    for member_id in ids:
        member = next((m for m in state.members if m["id"] == member_id), None)
        if member is None:
            continue
        for fact in state.facts_about(member_id):
            tags = set(fact.get("tags", []))
            text = fact["fact"]
            low = text.lower()
            if "access" in tags or re.search(r"step[- ]free|wheelchair|no stairs|bad knees|mobility", low):
                needs["step_free"].append(member["name"])
                needs["facts"].append((member["name"], text))
            elif "veg" in tags or re.search(r"vegetarian|vegan|\bjain\b|pure veg", low):
                needs["veg"].append(member["name"])
                needs["facts"].append((member["name"], text))
            elif "allergy" in tags or "allerg" in low:
                needs["allergies"].append((member["name"], text))
                needs["facts"].append((member["name"], text))
    return needs


def sync_family_needs(state, room_id: str) -> int:
    """Put what the household remembers (allergies, diet, step-free access) into `plan.preferences`. Returns how many were added."""
    needs = family_needs(state, room_id)
    added = 0
    with LOCK:
        room = _room(state, room_id)
        known = {p.lower() for p in room["plan"]["preferences"]}
        for name, fact in needs["facts"]:
            line = f"{name}: {fact}"
            if line.lower() not in known:
                room["plan"]["preferences"].append(line)
                known.add(line.lower())
                added += 1
        if added:
            _bump(room)
    return added


# ---------------------------------------------------------------- the plan: simple fields


def set_goal(state, room_id: str, goal: str) -> dict:
    with LOCK:
        room = _room(state, room_id)
        room["plan"]["goal"] = _clean(goal, 160)
        _bump(room)
        return {"goal": room["plan"]["goal"]}


def _clear_destination_items(room: dict) -> None:
    """A new destination makes the old one's flights, hotels, places and meals irrelevant (anything booked stays)."""
    plan = room["plan"]
    for key in ("flights", "hotels", "places", "restaurants"):
        plan[key] = [i for i in plan[key] if i["status"] == "booked"]
    keep = {i["id"] for key in ("flights", "hotels", "places", "restaurants") for i in plan[key]}
    plan["itinerary"] = [e for e in plan["itinerary"] if not e.get("ref") or e["ref"] in keep]
    plan["costs"] = [c for c in plan["costs"] if c.get("category") not in ("local",)]
    room.pop("_drafted_for", None)


def _place_ref(name, lat, lon) -> dict:
    found = travel_data.city(name)
    if lat is None or lon is None:
        if found is None:
            raise RoomError(400, f"I do not know the coordinates of {name!r}; pass lat and lon")
        lat, lon = found["lat"], found["lon"]
    return {"name": found["name"] if found else _clean(name, 80), "lat": round(float(lat), 4), "lon": round(float(lon), 4)}


def set_destination(state, room_id: str, name: str, lat=None, lon=None) -> dict:
    dest = _place_ref(name, lat, lon)
    with LOCK:
        room = _room(state, room_id)
        old = room["plan"]["destination"]
        if old and old["name"].lower() != dest["name"].lower():
            _clear_destination_items(room)
        room["plan"]["destination"] = dest
        if not room["plan"]["goal"]:
            room["plan"]["goal"] = f"Family trip to {dest['name']}"  # the board's headline, until the group words it better
        _bump(room)
        return {"destination": dest}


def set_origin(state, room_id: str, name: str, lat=None, lon=None) -> dict:
    origin = _place_ref(name, lat, lon)
    with LOCK:
        room = _room(state, room_id)
        room["plan"]["origin"] = origin
        _bump(room)
        return {"origin": origin}


def set_dates(state, room_id: str, start: str, end: str | None = None, nights_count: int | None = None) -> dict:
    first = _parse_date(start)
    if end:
        last = _parse_date(end)
    elif nights_count:
        last = first + timedelta(days=int(nights_count))
    else:
        last = first
    if last < first:
        raise RoomError(400, "the end date is before the start date")
    with LOCK:
        room = _room(state, room_id)
        room["plan"]["dates"] = {"start": first.isoformat(), "end": last.isoformat()}
        for entry in room["plan"]["itinerary"]:  # the same days, on the new calendar dates
            if entry.get("day"):
                entry["date"] = _day_to_date(room["plan"], entry["day"])
        _bump(room)
        return {"dates": room["plan"]["dates"], "nights": (last - first).days}


def set_budget(state, room_id: str, total, currency: str = "INR") -> dict:
    amount = int(round(float(total)))
    if amount <= 0:
        raise RoomError(400, "the budget must be more than zero")
    with LOCK:
        room = _room(state, room_id)
        room["plan"]["budget"] = {"total": amount, "currency": _clean(currency, 5).upper() or "INR"}
        _bump(room)
        return {"budget": room["plan"]["budget"]}


def set_travelers(state, room_id: str, people=None, count: int | None = None, rooms_count: int | None = None) -> dict:
    """Who is going. `people` are participant ids or names; `count` is the head count when it is bigger than the people
    in the room (a grandmother who has not joined); `rooms_count` is how many hotel rooms."""
    with LOCK:
        room = _room(state, room_id)
        ids, unknown = _resolve_people(room, people)
        plan = room["plan"]
        if people is not None:
            plan["travelers"] = ids
        if count is not None:
            plan["traveler_count"] = max(1, min(int(count), 40))
        elif people is not None and plan.get("traveler_count") and plan["traveler_count"] < len(ids):
            plan["traveler_count"] = len(ids)
        if rooms_count is not None:
            plan["rooms"] = max(1, min(int(rooms_count), 20))
        _bump(room)
        return {"travelers": plan["travelers"], "traveler_count": travellers(room), "rooms": plan.get("rooms"), "not_in_room": unknown}


def add_preference(state, room_id: str, text: str) -> dict:
    line = _clean(text, 200)
    if not line:
        raise RoomError(400, "text is required")
    with LOCK:
        room = _room(state, room_id)
        added = line.lower() not in {p.lower() for p in room["plan"]["preferences"]}
        if added:
            room["plan"]["preferences"].append(line)
            _bump(room)
        return {"added": added}


def record_decision(state, room_id: str, text: str, by=None) -> dict:
    with LOCK:
        room = _room(state, room_id)
        ids, _ = _resolve_people(room, by)
        d = {"id": _next(room, "d"), "text": _clean(text, 200), "by": ids, "ts": _hhmm()}
        room["plan"]["decisions"].append(d)
        _bump(room)
        return d


def add_open_question(state, room_id: str, text: str, asked_by: str = "Aangan") -> dict:
    line = _clean(text, 200)
    with LOCK:
        room = _room(state, room_id)
        same = next((q for q in room["plan"]["open_questions"] if not q["resolved"] and q["text"].lower() == line.lower()), None)
        if same:
            return {**same, "added": False}
        q = {"id": _next(room, "q"), "text": line, "asked_by": _clean(asked_by, 40) or "Aangan", "ts": _hhmm(), "resolved": False}
        room["plan"]["open_questions"].append(q)
        _bump(room)
        return {**q, "added": True}


def resolve_question(state, room_id: str, question_id: str | None = None, text: str | None = None) -> dict:
    with LOCK:
        room = _room(state, room_id)
        open_ones = [q for q in room["plan"]["open_questions"] if not q["resolved"]]
        found = next((q for q in open_ones if question_id and q["id"] == question_id), None)
        if found is None and text:
            low = text.lower()
            found = next((q for q in open_ones if low in q["text"].lower() or q["text"].lower() in low), None)
        if found is None:
            raise RoomError(404, "no open question matches")
        found["resolved"] = True
        _bump(room)
        return {"resolved": found["id"], "text": found["text"]}


def add_checklist_item(state, room_id: str, text: str, owner: str | None = None) -> dict:
    line = _clean(text, 200)
    with LOCK:
        room = _room(state, room_id)
        same = next((c for c in room["plan"]["checklist"] if c["text"].lower() == line.lower()), None)
        if same:
            return {**same, "added": False}
        ids, _ = _resolve_people(room, [owner] if owner else [])
        c = {"id": _next(room, "c"), "text": line, "done": False, "owner": ids[0] if ids else None}
        room["plan"]["checklist"].append(c)
        _bump(room)
        return {**c, "added": True}


def add_cost(state, room_id: str, label: str, amount, status: str = "estimate", category: str = "other", day: int | None = None) -> dict:
    """An explicit cost line (local transport, shopping, tips). Flights, the hotel, chosen meals and chosen places are
    priced by the backend from the plan itself, so they do not need a line here."""
    value = int(round(float(amount)))
    if value < 0:
        raise RoomError(400, "an amount cannot be negative")
    with LOCK:
        room = _room(state, room_id)
        line = {
            "label": _clean(label, 80), "amount": value, "status": status if status in ("estimate", "quoted", "booked") else "estimate",
            "category": category if category in COST_CATEGORIES else "other",
        }
        if day:
            line["day"] = int(day)
        same = next((c for c in room["plan"]["costs"] if c["label"].lower() == line["label"].lower()), None)
        if same:
            same.update(line)
        else:
            room["plan"]["costs"].append(line)
        _bump(room)
        return line


# ---------------------------------------------------------------- the plan: flights, hotels, places, restaurants


def _find(room: dict, ref: str) -> tuple[str, dict]:
    """(kind, item) for an id such as f-1, h-2, pl-3 or r-4. Kinds: flight, hotel, place, restaurant."""
    table = (("pl-", "place", "places"), ("f-", "flight", "flights"), ("h-", "hotel", "hotels"), ("r-", "restaurant", "restaurants"))
    for prefix, kind, key in table:
        if str(ref).startswith(prefix):
            item = next((i for i in room["plan"][key] if i["id"] == ref), None)
            if item:
                return kind, item
    raise RoomError(404, f"nothing in the plan has the id {ref}")


def _drop_items(room: dict, key: str, keep) -> None:
    plan = room["plan"]
    gone = {i["id"] for i in plan[key] if not keep(i)}
    plan[key] = [i for i in plan[key] if i["id"] not in gone]
    plan["itinerary"] = [e for e in plan["itinerary"] if e.get("ref") not in gone]


def _flight_key(f: dict) -> tuple:
    return (f["airline"].lower(), str(f["number"]).lower(), f["from"], f["to"], f["date"])


def add_flights(state, room_id: str, offers: list[dict]) -> list[dict]:
    """Add flight options to the plan. The same flight is never listed twice; a new search for a route and date replaces
    the options still only 'proposed' for it (chosen, booked and rejected ones stay)."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        legs = {(o["from"], o["to"], o["date"]) for o in offers}
        _drop_items(room, "flights", lambda f: f["status"] != "proposed" or (f["from"], f["to"], f["date"]) not in legs)
        have = {_flight_key(f) for f in plan["flights"]}
        added = []
        for o in offers:
            flight = {
                "id": "", "airline": str(o["airline"]), "number": str(o["number"]), "from": str(o["from"]), "to": str(o["to"]),
                "date": str(o["date"]), "dep": str(o.get("dep", "")), "arr": str(o.get("arr", "")), "price": int(o["price"]),
                "per": "person", "stops": int(o.get("stops") or 0), "source": "live" if o.get("source") == "live" else "sample",
                "link": o.get("link"), "status": "proposed",
            }
            if _flight_key(flight) in have:
                continue
            flight["id"] = _next(room, "f")
            plan["flights"].append(flight)
            have.add(_flight_key(flight))
            added.append(copy.deepcopy(flight))
        if added:
            _bump(room)
        return added


def add_hotels(state, room_id: str, hotels: list[dict]) -> list[dict]:
    """Add hotel options; a new search replaces the hotels still only 'proposed'."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        names = {h["name"].lower() for h in hotels}
        _drop_items(room, "hotels", lambda h: h["status"] != "proposed" or h["name"].lower() in names)
        have = {h["name"].lower() for h in plan["hotels"]}
        added = []
        for h in hotels:
            if h["name"].lower() in have:
                continue
            item = {
                "id": _next(room, "h"), "name": h["name"], "area": h.get("area", ""), "price_per_night": int(h["price_per_night"]),
                "rating": h.get("rating"), "lat": h.get("lat"), "lon": h.get("lon"), "step_free": bool(h.get("step_free")),
                "source": "live" if h.get("source") == "live" else "sample", "status": "proposed",
            }
            plan["hotels"].append(item)
            added.append(copy.deepcopy(item))
        if added:
            _bump(room)
        return added


def add_places(state, room_id: str, places: list[dict], notes_for=None) -> list[dict]:
    """Add place options; a new search replaces places still only 'proposed' and not on a day."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        names = {p["name"].lower() for p in places}
        _drop_items(room, "places", lambda p: p["status"] != "proposed" or p.get("day") or p["name"].lower() in names)
        have = {p["name"].lower() for p in plan["places"]}
        added = []
        for p in places:
            if p["name"].lower() in have:
                continue
            item = {k: copy.deepcopy(v) for k, v in p.items() if k != "step_free"}
            item["id"] = _next(room, "pl")
            item["notes"] = notes_for(p) if notes_for else p.get("notes", "")
            plan["places"].append(item)
            added.append(copy.deepcopy(item))
        if added:
            _bump(room)
        return added


def add_restaurants(state, room_id: str, restaurants: list[dict], meal: str | None = None, notes_for=None, replace: bool = True) -> list[dict]:
    """Add restaurant options; with `replace`, a new search replaces the unscheduled 'proposed' ones for that meal."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        names = {r["name"].lower() for r in restaurants}
        if replace:
            _drop_items(room, "restaurants", lambda r: r["status"] != "proposed" or r.get("day") or (meal and r["meal"] != meal)
                        or r["name"].lower() in names)
        have = {(r["name"].lower(), r["meal"]) for r in plan["restaurants"]}
        added = []
        for r in restaurants:
            if (r["name"].lower(), r["meal"]) in have:
                continue
            item = {k: copy.deepcopy(v) for k, v in r.items() if k != "veg_options"}
            item["id"] = _next(room, "r")
            item["notes"] = notes_for(r) if notes_for else r.get("notes", "")
            plan["restaurants"].append(item)
            have.add((r["name"].lower(), r["meal"]))
            added.append(copy.deepcopy(item))
        if added:
            _bump(room)
        return added


def choose(state, room_id: str, ref: str, reject: bool = False) -> dict:
    """Mark a flight, hotel, place or restaurant as selected (or rejected). Booking is a separate, human step."""
    with LOCK:
        room = _room(state, room_id)
        kind, item = _find(room, ref)
        if item["status"] == "booked":
            raise RoomError(409, f"{ref} is already booked")
        item["status"] = "rejected" if reject else "selected"
        if reject:
            if kind in ("place", "restaurant"):
                item["day"] = None
                if kind == "restaurant":
                    item["date"] = item["time"] = None
            room["plan"]["itinerary"] = [e for e in room["plan"]["itinerary"] if e.get("ref") != ref]
        _bump(room)
        return {"id": ref, "kind": kind, "status": item["status"]}


def _free_slot(room: dict, day: int, candidates) -> str:
    used = {e.get("time") for e in room["plan"]["itinerary"] if e.get("day") == day}
    return next((t for t in candidates if t not in used), candidates[-1])


def _valid_time(value) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 else None


def _upsert_entry(room: dict, entry: dict, key: tuple) -> dict:
    plan = room["plan"]
    same = next((e for e in plan["itinerary"] if (e.get("ref"), e["title"]) == key), None)
    if same:
        same.update(entry)
        return same
    entry["id"] = _next(room, "i")
    plan["itinerary"].append(entry)
    return entry


def schedule_item(state, room_id: str, ref: str, day: int | None = None, time: str | None = None) -> dict:
    """Put a flight, hotel, place or restaurant on a day of the trip: it becomes selected and gets an itinerary line."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        kind, item = _find(room, ref)
        if item["status"] == "rejected":
            raise RoomError(409, f"{ref} was rejected; select it first if the family changed its mind")
        if day is None and kind == "flight":
            day = _date_to_day(plan, item["date"])
        if day is None:
            raise RoomError(400, "day is required (1 is the first day of the trip)")
        day = int(day)
        if day < 1:
            raise RoomError(400, "day starts at 1")
        at = _valid_time(time)
        base = {"day": day, "date": _day_to_date(plan, day), "kind": "other", "ref": ref, "cost": None}
        if kind == "place":
            at = at or _free_slot(room, day, PLACE_SLOTS)
            item.update(day=day, status="selected" if item["status"] == "proposed" else item["status"])
            entry = {**base, "time": at, "title": item["name"], "place": item["area"], "lat": item["lat"], "lon": item["lon"],
                     "notes": item.get("notes", ""), "kind": "place"}
        elif kind == "restaurant":
            at = at or item.get("time") or MEAL_TIMES.get(item["meal"], "13:00")
            item.update(day=day, date=_day_to_date(plan, day), time=at, status="selected" if item["status"] == "proposed" else item["status"])
            entry = {**base, "time": at, "title": f"{item['meal'].title()} at {item['name']}", "place": item["area"], "lat": item["lat"],
                     "lon": item["lon"], "notes": item.get("notes", ""), "kind": "food"}
        elif kind == "flight":
            origin, dest = travel_data.city(item["from"]), travel_data.city(item["to"])
            if item["status"] == "proposed":
                item["status"] = "selected"
            entry = {**base, "time": item["dep"], "title": f"{item['airline']} {item['number']}, {item['from']} to {item['to']}",
                     "place": item["from"], "lat": origin["lat"] if origin else None, "lon": origin["lon"] if origin else None,
                     "notes": f"Lands {item['arr']} at {item['to']}", "kind": "travel"}
        else:  # hotel
            last = trip_days(plan)
            verb = "Check in at" if day == 1 else "Check out of" if last and day == last else "Stay at"
            if item["status"] == "proposed":
                item["status"] = "selected"
            entry = {**base, "time": at or ("14:00" if day == 1 else "11:00"), "title": f"{verb} {item['name']}", "place": item["area"],
                     "lat": item["lat"], "lon": item["lon"], "notes": "Step-free access" if item.get("step_free") else "", "kind": "stay"}
        saved = _upsert_entry(room, entry, (ref, entry["title"]))
        _bump(room)
        return {"ref": ref, "kind": kind, "day": day, "time": saved["time"], "itinerary_id": saved["id"]}


def add_itinerary_item(state, room_id: str, title: str, day: int | None = None, date: str | None = None, time: str | None = None,
                       place: str = "", lat=None, lon=None, notes: str = "", kind: str = "other", ref: str | None = None,
                       cost=None) -> dict:
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        if date and day is None:
            day = _date_to_day(plan, date)
        if day is not None and not date:
            date = _day_to_date(plan, int(day))
        if day is None and date is None:
            raise RoomError(400, "give a day (1 is the first day) or a date")
        entry = {
            "id": "", "day": int(day) if day is not None else None, "date": date, "time": _valid_time(time) or "", "title": _clean(title, 120),
            "place": _clean(place, 80), "lat": round(float(lat), 4) if lat is not None else None,
            "lon": round(float(lon), 4) if lon is not None else None, "notes": _clean(notes, 200),
            "kind": kind if kind in ("travel", "stay", "place", "food", "other") else "other", "ref": ref,
            "cost": int(cost) if cost is not None else None,
        }
        if not ref:
            # "Visit Basilica of Bom Jesus" added by hand, when the drafted day already has that place or meal: not twice
            name = entry["title"].lower()
            twin = next((e for e in plan["itinerary"] if e["day"] == entry["day"] and e["kind"] in ("place", "food")
                         and (e["title"].lower() in name or e["title"].lower() == entry["place"].lower())), None)
            if twin:
                return copy.deepcopy(twin)
        saved = _upsert_entry(room, entry, (ref, entry["title"])) if ref else None
        if saved is None:
            same = next((e for e in plan["itinerary"] if not e.get("ref") and e["day"] == entry["day"] and e["title"].lower() == entry["title"].lower()), None)
            if same:
                same.update({**entry, "id": same["id"]})
                saved = same
            else:
                entry["id"] = _next(room, "i")
                plan["itinerary"].append(entry)
                saved = entry
        _bump(room)
        return copy.deepcopy(saved)


# ---------------------------------------------------------------- approvals and demo bookings


def _make_ref(room: dict) -> str:
    used = {b["ref"] for b in room["bookings"]}
    while True:
        ref = "DEMO-" + "".join(secrets.choice(DEMO_REF_ALPHABET) for _ in range(5))
        if ref not in used:
            return ref


def propose_booking(state, room_id: str, flight_id: str | None = None, hotel_id: str | None = None, travellers_count: int | None = None,
                    nights_count: int | None = None) -> dict:
    """Ask the host to approve a booking. This only sets `pending_approval`: nothing is booked and no money moves."""
    with LOCK:
        room = _room(state, room_id)
        plan = room["plan"]
        n = max(1, min(int(travellers_count), 40)) if travellers_count else travellers(room)
        # "book the flight" means the whole journey: every selected flight (out and back), not one leg. With no ids at all,
        # the proposal is everything selected so far, flights and hotel.
        selected = [f["id"] for f in plan["flights"] if f["status"] == "selected"]
        wanted = [(flight_id, "flight")] if flight_id else []
        if flight_id or not hotel_id:
            wanted += [(ref, "flight") for ref in selected if ref != flight_id]
        if hotel_id:
            wanted.append((hotel_id, "hotel"))
        elif not flight_id:
            chosen = next((h["id"] for h in plan["hotels"] if h["status"] == "selected"), None)
            if chosen:
                wanted.append((chosen, "hotel"))
        if not wanted:
            raise RoomError(400, "nothing is selected yet: give a flight_id or a hotel_id")
        items, parts, amount, bits = [], [], 0, []
        for ref, want in wanted:
            kind, item = _find(room, ref)
            if kind != want:
                raise RoomError(400, f"{ref} is a {kind}, not a {want}")
            if item["status"] == "booked":
                raise RoomError(409, f"{ref} is already booked")
            items.append(ref)
            if kind == "flight":
                cost = int(item["price"] * n)
                parts.append(f"{item['airline']} {item['number']}")
                bits.append(f"{n} seat{'s' if n > 1 else ''} {item['from']} to {item['to']} on {_nice_date(item['date'])} {item['dep']}, {_money(cost)} total")
            else:
                stay = int(nights_count) if nights_count else (nights(plan) if nights(plan) is not None else 1)
                cost = int(item["price_per_night"] * stay * (plan.get("rooms") or 1))
                parts.append(item["name"])
                bits.append(f"{stay} night{'s' if stay != 1 else ''} at {item['name']}, {_money(cost)} total")
            amount += cost
        # a new proposal replaces the waiting one: its items go back to being options
        old = room.get("pending_approval")
        if old and old["status"] == "waiting":
            for ref in old["items"]:
                try:
                    _, it = _find(room, ref)
                    if it["status"] == "selected":
                        it["status"] = "proposed"
                except RoomError:
                    pass
        for ref in items:
            _find(room, ref)[1]["status"] = "selected"
        flown = sum(1 for ref in items if ref.startswith("f-"))
        names = ([f"{flown} flights"] if flown > 1 else parts[:flown]) + parts[flown:] if flown else parts
        title = "Book " + " and ".join(names) + (f" for {n} people" if flown and n > 1 else "")
        room["pending_approval"] = {
            "id": _next(room, "a"), "kind": "booking", "title": title,
            "summary": "; ".join(bits) + ". Demo booking: no real money moves.", "amount": amount, "items": items, "needs": "host",
            "approvals": [], "status": "waiting", "_meta": {"travellers": n, "nights": nights_count},
        }
        _bump(room)
        return {k: v for k, v in room["pending_approval"].items() if not k.startswith("_")}


def _book(room: dict, pending: dict, approver: dict) -> list[dict]:
    plan = room["plan"]
    n = int((pending.get("_meta") or {}).get("travellers") or travellers(room))
    made = []
    for ref in pending["items"]:
        kind, item = _find(room, ref)
        item["status"] = "booked"
        if kind == "flight":
            title = f"{item['airline']} {item['number']}, {_nice_date(item['date'])} {item['dep']}, {n} traveller{'s' if n != 1 else ''}"
            amount = int(item["price"] * n)
        else:
            stay = (pending.get("_meta") or {}).get("nights")
            stay = int(stay) if stay else (nights(plan) if nights(plan) is not None else 1)
            title = f"{item['name']}, {stay} night{'s' if stay != 1 else ''} from {_nice_date((plan.get('dates') or {}).get('start', ''))}"
            amount = int(item["price_per_night"] * stay * (plan.get("rooms") or 1))
        booking = {"id": _next(room, "b"), "kind": kind, "ref": _make_ref(room), "title": title, "amount": amount, "demo": True, "ts": _hhmm()}
        room["bookings"].append(booking)
        made.append(booking)
    return made


def decide(state, room_id: str, participant_id: str, approve: bool) -> dict:
    """The human tap. Approving books (a demo booking) what is waiting; declining clears it. With nothing waiting this is
    a harmless no-op, so a double tap never errors. `needs: host` means only the host participant may decide."""
    with LOCK:
        room = _room(state, room_id)
        who = _participant(room, participant_id)
        pending = room.get("pending_approval")
        if not pending or pending["status"] != "waiting":
            return _public(room)
        if pending["needs"] == "host" and who["id"] != room["host_participant_id"]:
            host = _name_of(room, room["host_participant_id"])
            raise RoomError(403, f"Only the host ({host}) can approve or decline this booking.")
        if approve:
            pending["approvals"].append(who["id"])
            pending["status"] = "approved"
            made = _book(room, pending, who)
            refs = ", ".join(b["ref"] for b in made)
            _append(room, "system", None, "", f"{who['name']} approved: {pending['title']}. Demo booking {refs}, no real money moved.")
        else:
            pending["status"] = "declined"
            for ref in pending["items"]:
                try:
                    _, item = _find(room, ref)
                    if item["status"] == "selected":
                        item["status"] = "rejected"
                except RoomError:
                    pass
            _append(room, "system", None, "", f"{who['name']} declined: {pending['title']}.")
        room["pending_approval"] = None
        _bump(room)
        return _public(room)


def reset_plan(state, room_id: str) -> dict:
    """For rehearsing the demo: an empty plan, nothing waiting, no bookings. People and the conversation stay."""
    with LOCK:
        room = _room(state, room_id)
        room["plan"], room["pending_approval"], room["bookings"] = empty_plan(), None, []
        room.pop("_drafted_for", None)
        _append(room, "system", None, "", "The plan was reset.")
        sync_family_needs(state, room_id)
        return _public(room)


def participant_info(state, room_id: str, participant_id: str) -> dict:
    """A copy of one participant (including its rtc_uid), for the voice and token endpoints."""
    with LOCK:
        return {k: v for k, v in _participant(_room(state, room_id), participant_id).items() if not k.startswith("_")}


def host_info(state, room_id: str) -> dict:
    with LOCK:
        room = _room(state, room_id)
        return {**participant_info(state, room_id, room["host_participant_id"]), "title": room["title"]}


# ---------------------------------------------------------------- bookkeeping the planner needs


def mark_drafted(state, room_id: str, destination: str) -> None:
    with LOCK:
        _room(state, room_id)["_drafted_for"] = destination


def drafted_for(state, room_id: str) -> str | None:
    with LOCK:
        return _room(state, room_id).get("_drafted_for")


def once(state, room_id: str, key: str) -> bool:
    """True the first time it is asked for this key in this room, False after that (to say a thing once)."""
    with LOCK:
        room = _room(state, room_id)
        seen = room.setdefault("_once", [])
        if key in seen:
            return False
        seen.append(key)
        return True


def touch(state, room_id: str) -> None:
    """Bump the version: the planner finished a turn, so the app should look again."""
    with LOCK:
        _bump(_room(state, room_id))


def cost_summary_for(state, room_id: str) -> dict:
    with LOCK:
        return cost_summary(_room(state, room_id))


# ---------------------------------------------------------------- the voice session of a room


def set_voice(state, room_id: str, info: dict) -> None:
    with LOCK:
        room = _room(state, room_id)
        room["_voice"] = info
        _bump(room)


def clear_voice(state, room_id: str) -> dict | None:
    with LOCK:
        room = _room(state, room_id)
        old = room.pop("_voice", None)
        if old:
            _bump(room)
        return old


def get_voice(state, room_id: str) -> dict | None:
    with LOCK:
        return copy.deepcopy(_room(state, room_id).get("_voice"))


def voice_gender(state, room_id: str) -> str:
    """Aangan keeps one voice in a room: the gender chosen when the voice agent started, else the host's."""
    from . import voices

    with LOCK:
        room = _room(state, room_id)
        chosen = (room.get("_voice") or {}).get("gender")
        if chosen:
            return chosen
        host = _participant(room, room["host_participant_id"])
    member = next((m for m in state.members if m["id"] == host["member_id"]), None)
    return voices.infer_gender(member) if member else "female"


# ---------------------------------------------------------------- running the planner


_PLAN_LOCKS: dict[str, threading.Lock] = {}


def plan_lock(room_id: str) -> threading.Lock:
    """One planning turn per room at a time: a second message waits for the first, then sees its changes."""
    with LOCK:
        return _PLAN_LOCKS.setdefault(room_id, threading.Lock())


def spawn(fn, *args, **kwargs) -> threading.Thread:
    """Run `fn` in the background (the planner never blocks an HTTP reply). Tests replace this to run inline."""
    thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True, name="room-planner")
    thread.start()
    return thread


_HOLD_PHRASES = {"One moment.", *languages.HOLD.values(), *languages.LOOKING.values()}


def converse_room_stream(state, room_id: str, participant_id: str, text: str):
    """The voice path: what was said is saved as a room message, the planner answers (and updates the plan), and the reply
    is yielded a sentence at a time, ready for the speech engine. The reply is also saved in the room as Aangan's."""
    from . import orchestrator, planner
    from .speech import speakable

    message = add_user_message(state, room_id, participant_id, text)
    english = message["lang"] == "en"
    spoken: list[str] = []
    try:
        for sentence in orchestrator._sentences(planner.stream_turn(state, room_id, participant_id, message["id"], spoken=True)):
            spoken.append(sentence)
            yield speakable(sentence) if english else sentence
    finally:
        said = [x for x in spoken if x not in _HOLD_PHRASES]  # the room keeps the answer, not the "one moment"
        if said:
            add_agent_message(state, room_id, " ".join(said))
        rooms_spawn_draft(state, room_id)


def rooms_spawn_draft(state, room_id: str) -> None:
    """After a spoken turn, fill in a first draft in the background if the plan is ready for one (it can take seconds)."""
    from . import planner

    spawn(planner.draft_if_ready, state, room_id)


def converse_room(state, room_id: str, participant_id: str, text: str) -> str:
    """The whole spoken reply for one utterance in a room (the non-streaming voice path)."""
    return " ".join(converse_room_stream(state, room_id, participant_id, text)).strip()
