"""Dining agent: finds restaurants that fit the family's remembered constraints, books tables, adds the outing to calendars.

Domain data (state.domains["dining"]): restaurants, reservations, pickups, chaos_fired. Extend, don't rename fields.
Constraints come from state.memory (allergies, veg, access, budget); the hero demo is a Sunday family lunch.

Tools: search_restaurants, book_table, add_calendar_event, arrange_pickup, cancel_reservation, notify_family.
Flow: request -> common free slots for everyone -> memory-derived constraints -> ranked proposal (state.pending)
      -> yes: book (falls back if the slot was just taken) -> calendar for all + cab for seniors -> notify family.
"""

import re
from collections import Counter
from datetime import date as _date

from .. import calendar_core as cal
from ..toolkit import Tool, ToolError, run_parallel
from .base import Specialist

DURATION_MIN = 90
MEAL_WINDOWS = {"lunch": ("12:00", "15:30", "13:00"), "dinner": ("19:00", "22:00", "19:00")}  # earliest, latest end, preferred
WEIGHTS = {"step_free": 3, "veg_only": 3, "mild_spice": 1, "kid_friendly": 1, "play_area": 5, "budget": 1, "max_price": 2, "cuisine": 5}

STRONG = [
    r"\brestaurants?\b", r"\blunch\b", r"\bdinner\b", r"\bbrunch\b", r"\btables?\b", r"\bouting\b", r"\bdining\b",
    r"\bdine\b", r"\beat(?:ing)? out\b", r"\breservations?\b", r"\bbahar\s+ja", r"\bkhana\b",
    r"\beat\b", r"\bgo(?:ing)? out\b", r"\bhungry\b", r"\bgrab (?:a )?(?:bite|food|something)\b", r"\bsomething to eat\b",
    r"\bwhere (?:can|should|shall|could|do) (?:we|i) (?:get|find|have|go|eat|order)\b", r"\bplace (?:to|for) (?:eat|lunch|dinner)\b",
]
EXCLUDE = [
    r"\bflights?\b", r"\bairport\b", r"\bfly\b", r"\bmedicines?\b", r"\bdawa(?:i)?\b", r"\btablets?\b", r"\bdoctor\b",
    r"\bpills?\b", r"\brefill\b", r"\bhomework\b", r"\bmarks\b", r"\btiffin\b", r"\bschool\b", r"\bremember\b",
    r"\bwhen\b.*\b(?:free|available)\b", r"\bfree (?:time|slot)s?\b",  # "when are we all free" is a calendar question
]
CONFIRM = {"yes", "yeah", "yep", "ok", "okay", "confirm", "book", "haan", "han", "ha", "theek", "thik", "sure", "done", "kardo", "perfect", "great", "good"}
REJECT = {"no", "nahi", "nahin", "nope", "cancel", "stop", "leave", "mat"}
CUISINES = {
    "south indian": "south indian", "dosa": "south indian", "idli": "south indian", "udupi": "south indian",
    "north indian": "north indian", "punjabi": "north indian", "thai": "thai", "gujarati": "gujarati", "thali": "gujarati",
    "seafood": "seafood", "continental": "continental", "italian": "continental", "pasta": "continental", "pizza": "continental",
}


# ----------------------------------------------------------------------------- helpers

def _has(patterns: list[str], low: str) -> bool:
    return any(re.search(p, low) for p in patterns)


def _day_label(date: str) -> str:
    return _date.fromisoformat(date).strftime("%A %d %b")


def _join_and(items: list[str], hi: bool = False) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" aur " if hi else " and ") + items[-1]


def _money(n: int) -> str:
    return f"Rs {n:,}"


def derive_constraints(state, attendee_ids: list[str]) -> dict:
    """Turn remembered facts about the attendees into restaurant constraints, remembering who each is for."""
    cons: dict = {k: [] for k in ("nut_free", "veg_only", "step_free", "mild_spice", "kid_friendly")}
    cons.update({"max_total": None, "dinner_cutoff": None})
    cutoffs = []
    for mid in attendee_ids:
        if state.member(mid)["kind"] == "child":
            cons["kid_friendly"].append(mid)
        for f in state.facts_about(mid):
            t, tags = f["fact"].lower(), f.get("tags", [])
            if ("allergy" in tags or "allerg" in t) and "nut" in t:
                cons["nut_free"].append(mid)
            if ("vegetarian" in t and "non" not in t) or "pure veg" in t:
                cons["veg_only"].append(mid)
            if "step-free" in t or "stairs" in t or "knee" in t:
                cons["step_free"].append(mid)
            if "spicy" in t and "avoid" in t:
                cons["mild_spice"].append(mid)
            m = re.search(r"dinner by (\d{1,2})\s*pm", t)
            if m:
                cutoffs.append(int(m.group(1)) + 12)
    for f in state.facts_about("family"):
        t = f["fact"].lower()
        if "budget" in t:
            m = re.search(r"rs\s*([\d,]+)", t)
            if m:
                cons["max_total"] = int(m.group(1).replace(",", ""))
    if cutoffs:
        cons["dinner_cutoff"] = f"{min(cutoffs):02d}:00"
    for k in ("nut_free", "veg_only", "step_free", "mild_spice", "kid_friendly"):
        cons[k] = list(dict.fromkeys(cons[k]))
    return cons


def _taken(state, restaurant_id: str, date: str, time: str) -> bool:
    return any(
        r["restaurant_id"] == restaurant_id and r["date"] == date and r["time"] == time and r["status"] == "CONFIRMED"
        for r in state.domains["dining"]["reservations"]
    )


def _find_restaurant(state, restaurant_id: str) -> dict:
    r = next((r for r in state.domains["dining"]["restaurants"] if r["id"] == restaurant_id), None)
    if r is None:
        raise ToolError(f"unknown restaurant {restaurant_id}")
    return r


# ----------------------------------------------------------------------------- tools

def search_restaurants(state, date: str, party_size: int, free_starts: list[str], preferred_time: str = "13:00",
                       nut_free: bool = False, veg_only: bool = False, step_free: bool = False, kid_friendly: bool = False,
                       mild_spice: bool = False, play_area: bool = False, max_total_cost: int | None = None,
                       max_price_for_two: int | None = None, cuisine: str | None = None,
                       restaurant_ids: list[str] | None = None, exclude_ids: list[str] | None = None) -> dict:
    free, pref = set(free_starts), cal.to_min(preferred_time)
    matches, partial, rejected = [], [], Counter()
    for r in state.domains["dining"]["restaurants"]:
        if restaurant_ids and r["id"] not in restaurant_ids:
            continue
        if exclude_ids and r["id"] in exclude_ids:
            continue
        times = [t for t in r["slots"].get(date, []) if t in free and not _taken(state, r["id"], date, t)]
        if not times:
            rejected["no_common_time"] += 1
            continue
        if nut_free and not r["nut_free"]:
            rejected["nut_free"] += 1  # an allergy is never relaxed
            continue
        est = round(r["price_for_two"] / 2 * party_size)
        viol = []
        if veg_only and not r["veg_only"]:
            viol.append("veg_only")
        if step_free and not r["step_free"]:
            viol.append("step_free")
        if kid_friendly and not r["kid_friendly"]:
            viol.append("kid_friendly")
        if mild_spice and r["spice"] != "mild":
            viol.append("mild_spice")
        if play_area and not r.get("play_area"):
            viol.append("play_area")
        if max_total_cost and est > max_total_cost:
            viol.append("budget")
        if max_price_for_two and r["price_for_two"] > max_price_for_two:
            viol.append("max_price")
        if cuisine and cuisine.lower() not in r["cuisine"].lower():
            viol.append("cuisine")
        times.sort(key=lambda t: (abs(cal.to_min(t) - pref), cal.to_min(t)))
        entry = {
            "id": r["id"], "name": r["name"], "cuisine": r["cuisine"], "area": r["area"], "time": times[0], "times": times,
            "price_for_two": r["price_for_two"], "est_cost": est, "rating": r["rating"], "spice": r["spice"],
            "veg_only": r["veg_only"], "nut_free": r["nut_free"], "step_free": r["step_free"],
            "kid_friendly": r["kid_friendly"], "play_area": bool(r.get("play_area")), "violations": viol,
        }
        (partial if viol else matches).append(entry)
    gap = lambda e: abs(cal.to_min(e["time"]) - pref)  # noqa: E731
    matches.sort(key=lambda e: (gap(e), -e["rating"], e["name"]))
    partial.sort(key=lambda e: (sum(WEIGHTS[v] for v in e["violations"]), gap(e), -e["rating"], e["name"]))
    blocked = Counter(v for e in partial for v in e["violations"])
    return {
        "matches": matches[:3], "closest": [] if matches else partial[:3],
        "blocked_by": [name for name, _ in blocked.most_common()], "considered": len(matches) + len(partial),
        "rejected": dict(rejected),
    }


def book_table(state, restaurant_id: str, date: str, time: str, party_size: int, member_ids: list[str]) -> dict:
    d = state.domains["dining"]
    r = _find_restaurant(state, restaurant_id)
    if state.chaos and not d["chaos_fired"]:
        d["chaos_fired"] = True
        raise ToolError(f"{r['name']} at {time} was just taken by another booking")
    if time not in r["slots"].get(date, []) or _taken(state, restaurant_id, date, time):
        raise ToolError(f"{r['name']} has no table at {time} on {date}")
    n = len(d["reservations"]) + 1
    res = {
        "id": f"res-{n}", "restaurant_id": restaurant_id, "restaurant": r["name"], "date": date, "time": time,
        "end": cal.to_hhmm(cal.to_min(time) + DURATION_MIN), "party_size": party_size, "member_ids": list(member_ids),
        "status": "CONFIRMED", "code": f"TBL{1000 + n * 37}", "event_id": None,
    }
    d["reservations"].append(res)
    return {"reservation_id": res["id"], "restaurant": r["name"], "date": date, "time": time, "end": res["end"],
            "party_size": party_size, "status": "CONFIRMED", "confirmation": res["code"]}


def add_calendar_event(state, member_ids: list[str], title: str, date: str, start: str, end: str,
                       location: str = "", reservation_id: str | None = None) -> dict:
    clashes = cal.conflicts(state, member_ids, date, start, end)
    event = cal.add_event(state, member_ids, title, date, start, end, location, kind="dining", source="dining")
    if reservation_id:
        for res in state.domains["dining"]["reservations"]:
            if res["id"] == reservation_id:
                res["event_id"] = event["id"]
    return {"event_id": event["id"], "title": title, "date": date, "start": start, "end": end,
            "attendees": list(member_ids), "clashes": [c["title"] for c in clashes]}


def arrange_pickup(state, member_id: str, date: str, pickup_time: str, destination: str,
                   reservation_id: str | None = None) -> dict:
    d = state.domains["dining"]
    pickup = {
        "id": f"cab-d{len(d['pickups']) + 1}", "booking": f"CAB-D{4200 + len(d['pickups']) + 1}", "member_id": member_id,
        "date": date, "pickup": pickup_time, "destination": destination, "status": "CONFIRMED", "reservation_id": reservation_id,
    }
    d["pickups"].append(pickup)
    return {"booking": pickup["booking"], "for": state.member(member_id)["name"], "pickup": pickup_time,
            "destination": destination, "status": "CONFIRMED"}


def cancel_reservation(state, reservation_id: str) -> dict:
    d = state.domains["dining"]
    res = next((r for r in d["reservations"] if r["id"] == reservation_id), None)
    if res is None or res["status"] != "CONFIRMED":
        raise ToolError(f"no active reservation {reservation_id}")
    res["status"] = "CANCELLED"
    if res.get("event_id"):
        try:
            cal.remove_event(state, res["event_id"])
        except ToolError:
            pass
    for p in d["pickups"]:
        if p.get("reservation_id") == reservation_id:
            p["status"] = "CANCELLED"
    return {"cancelled": reservation_id, "restaurant": res["restaurant"], "date": res["date"], "time": res["time"]}


def notify_family(state, member_ids: list[str], text: str) -> dict:
    note = state.notify(member_ids, text, "dining", "dining")
    return {"notification_id": note["id"], "to": note["to"], "channel": note["channel"], "mode": note["mode"], "status": note["status"]}


_OBJ = "object"
TOOLS = [
    Tool(
        "search_restaurants",
        "Search restaurants with a table free at a time when every attendee is free, ranked against dietary, access, "
        "budget and cuisine constraints. Allergy (nut_free) is never relaxed; other constraints show up as violations.",
        {"type": _OBJ, "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "party_size": {"type": "integer"},
            "free_starts": {"type": "array", "items": {"type": "string"}, "description": "HH:MM start times when all attendees are free"},
            "preferred_time": {"type": "string", "description": "HH:MM, default 13:00"},
            "nut_free": {"type": "boolean"}, "veg_only": {"type": "boolean"}, "step_free": {"type": "boolean"},
            "kid_friendly": {"type": "boolean"}, "mild_spice": {"type": "boolean"}, "play_area": {"type": "boolean"},
            "max_total_cost": {"type": "integer", "description": "Whole-party budget in rupees"},
            "max_price_for_two": {"type": "integer"},
            "cuisine": {"type": "string", "description": "Substring of the cuisine, e.g. 'south indian'"},
            "restaurant_ids": {"type": "array", "items": {"type": "string"}},
            "exclude_ids": {"type": "array", "items": {"type": "string"}},
        }, "required": ["date", "party_size", "free_starts"]},
        search_restaurants,
    ),
    Tool(
        "book_table", "Book a table. Fails if the slot was just taken; try another slot or restaurant.",
        {"type": _OBJ, "properties": {
            "restaurant_id": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
            "party_size": {"type": "integer"}, "member_ids": {"type": "array", "items": {"type": "string"}},
        }, "required": ["restaurant_id", "date", "time", "party_size", "member_ids"]},
        book_table,
    ),
    Tool(
        "add_calendar_event", "Add the outing to the calendars of the attendees.",
        {"type": _OBJ, "properties": {
            "member_ids": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"},
            "date": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"},
            "location": {"type": "string"}, "reservation_id": {"type": "string"},
        }, "required": ["member_ids", "title", "date", "start", "end"]},
        add_calendar_event,
    ),
    Tool(
        "arrange_pickup", "Book a cab to take a family member (for example a grandparent) to the restaurant.",
        {"type": _OBJ, "properties": {
            "member_id": {"type": "string"}, "date": {"type": "string"}, "pickup_time": {"type": "string"},
            "destination": {"type": "string"}, "reservation_id": {"type": "string"},
        }, "required": ["member_id", "date", "pickup_time", "destination"]},
        arrange_pickup,
    ),
    Tool(
        "cancel_reservation", "Cancel a confirmed reservation; removes the calendar event and cancels pickups.",
        {"type": _OBJ, "properties": {"reservation_id": {"type": "string"}}, "required": ["reservation_id"]},
        cancel_reservation,
    ),
    Tool(
        "notify_family", "Tell family members about a dining plan over Agora Chat.",
        {"type": _OBJ, "properties": {
            "member_ids": {"type": "array", "items": {"type": "string"}}, "text": {"type": "string"},
        }, "required": ["member_ids", "text"]},
        notify_family, stage="after",
    ),
]


# ----------------------------------------------------------------------------- agent

class DiningAgent(Specialist):
    name = "dining"
    title = "Dining agent"
    family_keys = ("reservations", "pickups", "chaos_fired")
    keywords = ("restaurant", "lunch", "dinner", "table", "book a table", "eat", "food", "reservation", "outing", "bahar", "khana", "breakfast", "hungry")
    tools = TOOLS

    def seed(self) -> dict:
        d = "2026-11-22"
        return {
            "restaurants": [
                {"id": "r1", "name": "Udupi Garden", "cuisine": "South Indian", "veg_only": True, "nut_free": True, "kid_friendly": True, "step_free": True, "play_area": False, "spice": "mild", "price_for_two": 900, "rating": 4.4, "area": "Indiranagar", "slots": {d: ["12:30", "13:00", "13:30", "14:00"]}},
                {"id": "r2", "name": "Bangkok Wok", "cuisine": "Thai", "veg_only": False, "nut_free": False, "kid_friendly": True, "step_free": True, "play_area": True, "spice": "hot", "price_for_two": 1600, "rating": 4.5, "area": "Koramangala", "slots": {d: ["13:00", "13:30", "19:30"]}},
                {"id": "r3", "name": "Punjabi Tadka", "cuisine": "North Indian", "veg_only": False, "nut_free": False, "kid_friendly": True, "step_free": False, "play_area": False, "spice": "medium", "price_for_two": 1400, "rating": 4.2, "area": "HSR Layout", "slots": {d: ["13:00", "14:00", "20:00"]}},
                {"id": "r4", "name": "Green Leaf Thali House", "cuisine": "Gujarati thali", "veg_only": True, "nut_free": True, "kid_friendly": True, "step_free": False, "play_area": False, "spice": "mild", "price_for_two": 800, "rating": 4.3, "area": "Jayanagar", "slots": {d: ["12:30", "13:00", "13:30"]}},
                {"id": "r5", "name": "Coastal Spice", "cuisine": "Seafood", "veg_only": False, "nut_free": True, "kid_friendly": True, "step_free": True, "play_area": False, "spice": "hot", "price_for_two": 1800, "rating": 4.6, "area": "Whitefield", "slots": {d: ["20:00", "20:30"]}},
                {"id": "r6", "name": "Olive Courtyard", "cuisine": "Continental", "veg_only": False, "nut_free": True, "kid_friendly": True, "step_free": True, "play_area": True, "spice": "mild", "price_for_two": 2200, "rating": 4.6, "area": "Indiranagar", "slots": {d: ["12:30", "13:00", "19:30"]}},
            ],
            "reservations": [],
            "pickups": [],
            "chaos_fired": False,
        }

    def score(self, state, text: str) -> int:
        from .money import is_money

        low = text.lower()
        if _has(EXCLUDE, low) or is_money(low):  # spending talk belongs to the Money agent
            return 0
        if re.search(r"\b(cab|taxi)\b", low) and not re.search(
            r"\b(restaurants?|lunch|dinner|brunch|breakfast|tables?|eat|food|dine|dining|khana|hungry)\b", low
        ):
            return 0  # "a cab for the family outing" is the travel agent's
        hits = sum(1 for p in STRONG if re.search(p, low))
        return 3 + hits if hits else 0

    # --- parsing
    def _parse(self, state, text: str) -> dict:
        low, today = text.lower(), state.now["date"]
        out: dict = {"date": cal.parse_date(text, today), "time": cal.parse_time(text)}
        out["meal"] = "dinner" if re.search(r"\b(dinner|raat)\b", low) else "lunch" if re.search(r"\b(lunch|brunch|dopahar)\b", low) else None
        for word in sorted(CUISINES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(word) + r"\b", low):
                out["cuisine"], out["cuisine_word"] = CUISINES[word], word
                break
        out["cheaper"] = bool(re.search(r"\b(cheaper|cheap|sasta|sasti|less expensive|affordable)\b", low))
        out["earlier"] = bool(re.search(r"\b(earlier|pehle|jaldi)\b", low))
        out["later"] = bool(re.search(r"\b(later|baad mein)\b", low))
        out["other"] = bool(re.search(r"\b(another|different|something else|somewhere else|koi aur|dusra|dusri|other place)\b", low))
        out["play_area"] = bool(re.search(r"\b(play ?area|play ?ground|kids area)\b", low))
        for r in state.domains["dining"]["restaurants"]:
            if r["name"].lower() in low:
                out["only_id"] = r["id"]
        return out

    def _attendees(self, state, member_id: str, text: str) -> list[str]:
        mentioned = [m["id"] for m in state.mentioned_members(text)]
        if not mentioned or len(mentioned) == len(state.members):
            return [m["id"] for m in state.members]
        ids = set(mentioned) | {member_id}
        return [m["id"] for m in state.members if m["id"] in ids]

    # --- entry point
    def handle(self, state, member_id: str, text: str) -> str | None:
        if state.pending and state.pending.get("agent") == self.name:
            return self._handle_pending(state, member_id, text)
        if self.score(state, text) == 0:
            return None
        low = text.lower()
        if re.search(r"\bcancel\b", low):
            return self._cancel(state, member_id)
        return self._start(state, member_id, text)

    def _start(self, state, member_id: str, text: str) -> str:
        ch = self._parse(state, text)
        attendees = self._attendees(state, member_id, text)
        explicit = re.search(r"\b(?:for|party of)\s+(\d{1,2})\b(?!:)", text.lower()) or re.search(r"\b(\d{1,2})\s+(?:people|persons|log|guests)\b", text.lower())
        party = int(explicit.group(1)) if explicit else len(attendees)
        default_date = cal.parse_date("sunday", state.now["date"])
        filters = {
            "date": ch["date"] or default_date, "assumed_date": ch["date"] is None, "meal": ch["meal"] or "lunch",
            "preferred": ch["time"], "attendees": attendees, "party_size": party, "cuisine": ch.get("cuisine"),
            "cuisine_word": ch.get("cuisine_word"), "play_area": ch["play_area"], "only_id": ch.get("only_id"),
            "exclude": [], "max_price": None,
        }
        return self._propose(state, member_id, filters)

    # --- propose
    def _propose(self, state, member_id: str, filters: dict, prefix_en: str = "", prefix_hi: str = "") -> str:
        ids, date, meal = filters["attendees"], filters["date"], filters["meal"]
        n, day = filters["party_size"], _day_label(filters["date"])
        cons = derive_constraints(state, ids)
        earliest, latest, default_pref = MEAL_WINDOWS[meal]
        starts = [s["start"] for s in cal.find_common_slots(state, ids, date, DURATION_MIN, earliest, latest)]
        if meal == "dinner" and cons["dinner_cutoff"]:
            starts = [s for s in starts if cal.to_min(s) <= cal.to_min(cons["dinner_cutoff"]) - 30]
        if filters.get("assumed_date"):
            prefix_en += "I'm assuming Sunday, family day. "
            prefix_hi += "Sunday maan raha hoon, family day hai na. "
            filters["assumed_date"] = False
        if not starts:
            state.pending = None
            return self._no_time(state, member_id, filters, prefix_en, prefix_hi)

        args = {
            "date": date, "party_size": n, "free_starts": starts, "preferred_time": filters.get("preferred") or default_pref,
            "nut_free": bool(cons["nut_free"]), "veg_only": bool(cons["veg_only"]), "step_free": bool(cons["step_free"]),
            "kid_friendly": bool(cons["kid_friendly"]), "mild_spice": bool(cons["mild_spice"]),
            "play_area": bool(filters.get("play_area")),
        }
        if cons["max_total"]:
            args["max_total_cost"] = cons["max_total"]
        if filters.get("max_price"):
            args["max_price_for_two"] = filters["max_price"]
        if filters.get("cuisine"):
            args["cuisine"] = filters["cuisine"]
        if filters.get("only_id"):
            args["restaurant_ids"] = [filters["only_id"]]
        if filters.get("exclude"):
            args["exclude_ids"] = filters["exclude"]
        _, res = self.call(state, "search_restaurants", **args)

        pool = res["matches"] or res["closest"]
        if not pool:
            state.pending = None
            return self.say(
                state, member_id,
                prefix_en + f"I don't see any open tables on {day} that fit everyone. Want to try another day or time?",
                prefix_hi + f"{day} ko aisi koi table khaali nahi dikh rahi. Koi aur din ya time try karein?",
            )
        entry = pool[0]
        cands = [{"restaurant_id": entry["id"], "name": entry["name"], "time": t} for t in entry["times"]]
        cands += [{"restaurant_id": e["id"], "name": e["name"], "time": e["time"]} for e in pool[1:]]
        state.pending = {
            "agent": self.name, "step": "confirm", "filters": filters, "candidates": cands,
            "proposal": {"restaurant_id": entry["id"], "name": entry["name"], "time": entry["time"],
                         "price_for_two": entry["price_for_two"], "violations": entry["violations"]},
        }
        if res["matches"]:
            return self._reply_match(state, member_id, entry, cons, filters, prefix_en, prefix_hi)
        return self._reply_closest(state, member_id, entry, res, cons, filters, prefix_en, prefix_hi)

    def _reasons(self, state, cons: dict, entry: dict, ids: list[str], hi: bool) -> str:
        labels = {"nut_free": "nut-free", "veg_only": "pure veg", "step_free": "step-free", "mild_spice": "mild spice", "kid_friendly": "kid-friendly"}
        per: dict[str, list[str]] = {}
        for key, label in labels.items():
            if key in entry["violations"]:
                continue
            for mid in cons[key]:
                per.setdefault(mid, []).append(label)
        parts = []
        for mid in ids:
            if mid in per:
                name = state.member(mid)["name"]
                parts.append(f"{name} ke liye {_join_and(per[mid], True)}" if hi else f"{_join_and(per[mid])} for {name}")
        return ", ".join(parts)

    def _reply_match(self, state, member_id, entry, cons, filters, pen, phi) -> str:
        ids, n, day = filters["attendees"], filters["party_size"], _day_label(filters["date"])
        why_en, why_hi = self._reasons(state, cons, entry, ids, False), self._reasons(state, cons, entry, ids, True)
        who_en = f"all {n} of you are free" if n == len(ids) else f"{n} of you are free"
        who_hi = f"aap sab {n} log free ho" if n == len(ids) else f"{n} log free ho"
        en = (f"{entry['name']} on {day} at {entry['time']}: {why_en + ', and ' if why_en else ''}{who_en}. "
              f"About {_money(entry['est_cost'])} in total, shall I book it?")
        hi = (f"{entry['name']} mein {day} ko {entry['time']} baje: {why_hi + ', aur ' if why_hi else ''}{who_hi}. "
              f"Lagbhag {_money(entry['est_cost'])} lagenge, book kar doon?")
        return self.say(state, member_id, pen + en, phi + hi)

    def _issue(self, v: str, entry: dict, cons: dict, filters: dict, hi: bool) -> str:
        word = filters.get("cuisine_word") or "that cuisine"
        budget = _money(cons["max_total"]) if cons.get("max_total") else ""
        en = {
            "veg_only": "isn't a pure-veg kitchen", "step_free": "has stairs", "mild_spice": "can be spicy",
            "kid_friendly": "isn't kid-friendly", "play_area": "has no play area",
            "budget": f"would cost about {_money(entry['est_cost'])}, over your {budget} budget",
            "max_price": "isn't any cheaper", "cuisine": f"isn't {word}",
        }
        hin = {
            "veg_only": "pure-veg kitchen nahi hai", "step_free": "mein seedhiyan hain", "mild_spice": "thoda teekha ho sakta hai",
            "kid_friendly": "bacchon ke liye theek nahi hai", "play_area": "mein play area nahi hai",
            "budget": f"lagbhag {_money(entry['est_cost'])} lagenge, jo aapke {budget} budget se zyada hai",
            "max_price": "sasta nahi hai", "cuisine": f"{word} nahi hai",
        }
        return (hin if hi else en)[v]

    def _reply_closest(self, state, member_id, entry, res, cons, filters, pen, phi) -> str:
        n = filters["party_size"]
        word = filters.get("cuisine_word") or "that cuisine"
        block_en = {"veg_only": "pure veg", "step_free": "step-free", "mild_spice": "mild", "kid_friendly": "kid-friendly",
                    "play_area": "play-area friendly", "budget": "within budget", "max_price": "cheaper", "cuisine": word}
        block_hi = {"veg_only": "pure veg", "step_free": "step-free", "mild_spice": "kam teekha", "kid_friendly": "bacchon ke liye theek",
                    "play_area": "play area wali", "budget": "budget mein", "max_price": "sasti", "cuisine": word}
        top = [block_en[b] for b in res["blocked_by"][:2]]
        top_hi = [block_hi[b] for b in res["blocked_by"][:2]]
        issues_en = _join_and([self._issue(v, entry, cons, filters, False) for v in entry["violations"]])
        issues_hi = _join_and([self._issue(v, entry, cons, filters, True) for v in entry["violations"]], True)
        en = (f"Nothing is {_join_and(top)} and free for all {n} of you then. The closest is {entry['name']} at {entry['time']}, "
              f"but it {issues_en}. Want it, or shall I change something?")
        hi = (f"Aisi koi jagah nahi jo {_join_and(top_hi, True)} ho aur aap sab {n} ke liye free ho. Sabse nazdeek {entry['name']} hai, {entry['time']} baje, "
              f"lekin yeh {issues_hi}. Isse book karoon ya kuch badlun?")
        return self.say(state, member_id, pen + en, phi + hi)

    def _no_time(self, state, member_id: str, filters: dict, pen: str, phi: str) -> str:
        ids, meal = filters["attendees"], filters["meal"]
        earliest, latest, _ = MEAL_WINDOWS[meal]
        day = _day_label(filters["date"])
        base = _date.fromisoformat(filters["date"])
        for add in range(1, 7):
            d = _date.fromordinal(base.toordinal() + add).isoformat()
            if cal.find_common_slots(state, ids, d, DURATION_MIN, earliest, latest):
                alt = _day_label(d)
                return self.say(
                    state, member_id,
                    pen + f"There's no {meal} window on {day} when all {len(ids)} of you are free. {alt} works, want that instead?",
                    phi + f"{day} ko {meal} ke liye aap sab {len(ids)} log ek saath free nahi ho. {alt} theek rahega, wahi dekhun?",
                )
        return self.say(state, member_id, pen + f"There's no {meal} window on {day} when everyone is free.",
                        phi + f"{day} ko {meal} ke liye sab ek saath free nahi hain.")

    # --- mid-proposal replies
    def _handle_pending(self, state, member_id: str, text: str) -> str:
        pend = state.pending
        filters, prop = pend["filters"], pend["proposal"]
        low, tokens = text.lower(), set(re.findall(r"[a-z']+", text.lower()))
        ch = self._parse(state, text)

        changes: dict = {}
        if ch.get("cuisine"):
            changes["cuisine"] = ch["cuisine"]
        for key in ("cheaper", "earlier", "later", "other", "play_area"):
            if ch[key]:
                changes[key] = True
        if ch["time"] and ch["time"] != prop["time"]:
            changes["time"] = ch["time"]
        if ch["date"] and ch["date"] != filters["date"]:
            changes["date"] = ch["date"]
        if ch["meal"] and ch["meal"] != filters["meal"]:
            changes["meal"] = ch["meal"]
        if ch.get("only_id") and ch["only_id"] != prop["restaurant_id"]:
            changes["only_id"] = ch["only_id"]

        if changes:
            return self._research(state, member_id, filters, prop, changes, ch)
        if tokens & REJECT or "kar mat" in low:
            state.pending = None
            return self.say(state, member_id, "Okay, I won't book anything. Tell me what you'd like instead.",
                            "Theek hai, kuch book nahi kar raha. Batayein aap kya chahte hain.")
        if tokens & CONFIRM or "kar do" in low or "go ahead" in low:
            return self._execute(state, member_id, pend)
        return self.say(
            state, member_id,
            f"Shall I book {prop['name']} at {prop['time']}? Say yes, or tell me what to change.",
            f"{prop['name']} mein {prop['time']} baje book kar doon? Haan bolein, ya batayein kya badalna hai.",
        )

    def _research(self, state, member_id: str, filters: dict, prop: dict, changes: dict, ch: dict) -> str:
        f = dict(filters)
        f["exclude"] = list(f.get("exclude", []))
        note_en = note_hi = ""
        if "cuisine" in changes:
            f["cuisine"], f["cuisine_word"] = changes["cuisine"], ch.get("cuisine_word")
        if changes.get("cheaper"):
            f["max_price"] = prop["price_for_two"] - 1
        if changes.get("other"):
            f["exclude"].append(prop["restaurant_id"])
        if changes.get("play_area"):
            f["play_area"] = True
        if "only_id" in changes:
            f["only_id"], f["exclude"] = changes["only_id"], []
        if "date" in changes:
            f["date"], f["preferred"] = changes["date"], None
        if "meal" in changes:
            f["meal"], f["preferred"] = changes["meal"], None
        if "time" in changes:
            f["preferred"] = changes["time"]
        if changes.get("earlier"):
            f["preferred"] = cal.to_hhmm(cal.to_min(prop["time"]) - 60)
        if changes.get("later"):
            f["preferred"] = cal.to_hhmm(cal.to_min(prop["time"]) + 60)
        reply = self._propose(state, member_id, f, note_en, note_hi)
        new = state.pending["proposal"] if state.pending else None
        if new and changes.get("cheaper") and new["restaurant_id"] == prop["restaurant_id"] and "max_price" in new["violations"]:
            cons = derive_constraints(state, f["attendees"])
            fits_en = _join_and([lbl for key, lbl in (("nut_free", "nut-free"), ("veg_only", "pure veg"), ("step_free", "step-free")) if cons[key]])
            fits_hi = _join_and([lbl for key, lbl in (("nut_free", "nut-free"), ("veg_only", "pure veg"), ("step_free", "step-free")) if cons[key]], True)
            return self.say(
                state, member_id,
                f"{prop['name']} is already the cheapest place that works for everyone ({fits_en}). Shall I book it, or name another restaurant?",
                f"{prop['name']} hi sabse sasta hai jo sabke liye theek hai ({fits_hi}). Book kar doon, ya koi aur restaurant bolein?",
            )
        if new and new["restaurant_id"] == prop["restaurant_id"] and new["time"] == prop["time"] and (changes.get("earlier") or changes.get("later")):
            which = "earliest" if changes.get("earlier") else "latest"
            reply = self.say(state, member_id, f"That's the {which} slot that works for everyone. ",
                             f"Sabke liye sabse {'jaldi' if which == 'earliest' else 'der'} ka yahi slot hai. ") + reply
        return reply

    # --- execute
    def _execute(self, state, member_id: str, pend: dict) -> str:
        f = pend["filters"]
        ids, n, date = f["attendees"], f["party_size"], f["date"]
        first_failed, booked, chosen = None, None, None
        for cand in pend["candidates"]:
            status, res = self.call(state, "book_table", restaurant_id=cand["restaurant_id"], date=date, time=cand["time"],
                                    party_size=n, member_ids=ids)
            if status == "ok":
                booked, chosen = res, cand
                break
            first_failed = first_failed or cand
        state.pending = None
        if not booked:
            return self.say(state, member_id, "I couldn't get a table at any of those. Want me to look again?",
                            "Kisi bhi jagah table nahi mil payi. Dobara dekhun?")

        title = f"{f['meal'].capitalize()} at {booked['restaurant']}"
        calls = [(self.tool("add_calendar_event"), {
            "member_ids": ids, "title": title, "date": date, "start": booked["time"], "end": booked["end"],
            "location": booked["restaurant"], "reservation_id": booked["reservation_id"]})]
        seniors = [m for m in ids if state.member(m)["kind"] == "senior"]
        pickup_time = cal.to_hhmm(cal.to_min(booked["time"]) - 45)
        for s in seniors:
            calls.append((self.tool("arrange_pickup"), {
                "member_id": s, "date": date, "pickup_time": pickup_time, "destination": booked["restaurant"],
                "reservation_id": booked["reservation_id"]}))
        run_parallel(state, self.name, calls)

        day = _day_label(date)
        note = f"Table for {n} at {booked['restaurant']}, {day} {booked['time']}."
        if seniors:
            note += f" Cab for {state.member(seniors[0])['name']} at {pickup_time}."
        self.call(state, "notify_family", member_ids=ids, text=note + f" Confirmation {booked['confirmation']}.")

        moved_en = moved_hi = ""
        if first_failed:
            moved_en = f"{first_failed['name']} at {first_failed['time']} was just taken, so I booked {booked['restaurant']} at {booked['time']} instead. "
            moved_hi = f"{first_failed['name']} mein {first_failed['time']} wali table abhi kisi ne le li, isliye {booked['restaurant']} mein {booked['time']} baje book ki. "
        cab_en = f" a cab picks {state.member(seniors[0])['name']} up at {pickup_time}," if seniors else ""
        cab_hi = f" {state.member(seniors[0])['name']} ke liye cab {pickup_time} baje aayegi," if seniors else ""
        en = (f"{moved_en}Done: table for {n} at {booked['restaurant']}, {day} at {booked['time']}. It's on everyone's calendar,"
              f"{cab_en} and the family has been told on Agora Chat.")
        hi = (f"{moved_hi}Ho gaya! {booked['restaurant']} mein {day} ko {booked['time']} baje {n} logon ki table book hai. Sabke calendar mein add hai,"
              f"{cab_hi} aur family ko Agora Chat pe bata diya.")
        return self.say(state, member_id, en, hi)

    def _cancel(self, state, member_id: str) -> str:
        active = [r for r in state.domains["dining"]["reservations"] if r["status"] == "CONFIRMED"]
        if not active:
            return self.say(state, member_id, "There's no dining booking to cancel.", "Cancel karne ke liye koi booking nahi hai.")
        res = active[-1]
        self.call(state, "cancel_reservation", reservation_id=res["id"])
        self.call(state, "notify_family", member_ids=res["member_ids"],
                  text=f"Cancelled: table at {res['restaurant']}, {_day_label(res['date'])} {res['time']}.")
        return self.say(
            state, member_id,
            f"Cancelled the table at {res['restaurant']} and cleared it from everyone's calendar. The family has been told.",
            f"{res['restaurant']} ki table cancel kar di aur sabke calendar se hata di. Family ko bata diya.",
        )
