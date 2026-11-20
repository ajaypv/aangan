"""Calendar agent: cross-member schedule view, conflicts, finding family-free slots, creating and moving events.

Uses app.calendar_core helpers over state.calendar. Domain data (state.domains["calendar"]): free-form extras.

Tools: get_schedule, find_family_slots, check_conflicts, scan_clashes, create_event, move_event, cancel_event,
send_digest (stage "after"). Trigger: week_digest. create/move/cancel notify the affected members (kind "calendar").
"""

import re
import secrets
from datetime import date as _date, timedelta
from itertools import combinations

from .. import calendar_core as cc
from ..toolkit import Tool, ToolError
from .base import Specialist, Trigger

# utterances owned by other agents; calendar never claims them
BLOCK = re.compile(
    r"\b(doctor|medicine|medicines|dawai|dawa|tablet|refill|flight|flights|fly|cab|taxi|restaurant|table|reservation|marks|score|homework)\b"
)
CLASH = re.compile(r"\b(clash|clashes|conflict|conflicts|overlap|overlaps|double.?book\w*|takrav)\b")
FREE = re.compile(r"\b(free|available|availability|khali|find (?:a )?(?:time|slot)|common (?:time|slot))\b")
SCHEDULE = re.compile(
    r"\b(what'?s on|whats on|what is on|what do (?:i|we|you|\w+) have|what does \w+ have|what'?s (?:\w+ )?doing|what is (?:\w+ )?doing"
    r"|what (?:is|are) (?:everyone|everybody|all|they|we)(?:'s)?\b[^?.]*\bdoing|what everyone(?:'s| is| are)? doing|who(?:'s| is) doing what"
    r"|what (?:is|are) \w+ up to|what'?s (?:planned|happening|going on)|anything (?:on|planned)|what have (?:i|we) got"
    r"|schedule|agenda|calendar|kya (?:hai|plan)|plans? for)\b"
)
DIGEST = re.compile(
    r"\b(digest|week ahead|weekly (?:summary|update|overview|plan|schedule|rundown)"
    r"|(?:plan|schedule|summary|overview|rundown|look|picture)\b.*\bweek\b"
    r"|what'?s on (?:this|the|next) week|(?:this|the|coming|next) week\b.*\b(?:look like|going on|happening|busy|planned)"
    r"|\b(?:happening|going on|planned|coming up)\b.*\b(?:this|the|coming|next) week)\b"
)
MOVE = re.compile(r"\b(move|reschedule|shift|postpone|push|bring forward|put off|badal|badlo)\b")
CANCEL = re.compile(r"\b(cancel|delete|remove|hata)\b")
ADD_VERB = re.compile(r"\b(add|put|create|set up|fix|block|schedule|note|jodo)\b")
ADD_NOUN = re.compile(
    r"\b(appointment|meeting|class|event|reminder|practice|call|dentist|visit|party|birthday|match|session|lesson)\b"
)
REJECT = re.compile(r"\b(no|nope|nahi|nahin|cancel|never ?mind|forget it|rehne do|chhodo|stop)\b")
GENERIC = {"the", "a", "an", "my", "our", "this", "that", "class", "meeting", "event", "call", "appointment", "practice", "session"}
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"


# ---------------------------------------------------------------- helpers

def _lc(title: str) -> str:
    """Lower-case a title's first letter for mid-sentence use, keeping acronyms and codes intact."""
    return title[:1].lower() + title[1:] if title[1:2].islower() else title


def _view(e: dict) -> dict:
    return {k: e[k] for k in ("id", "title", "member_ids", "date", "start", "end", "location", "kind")}


def _ids(state, member_ids) -> list[str]:
    if not member_ids:
        raise ToolError("member_ids is empty")
    known = {m["id"] for m in state.members}
    bad = [m for m in member_ids if m not in known]
    if bad:
        raise ToolError(f"unknown family member: {', '.join(bad)}")
    return list(member_ids)


def _valid_date(d: str) -> None:
    try:
        _date.fromisoformat(d)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"bad date {d!r}, expected YYYY-MM-DD") from exc


def _valid_time(t: str) -> None:
    if not isinstance(t, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        raise ToolError(f"bad time {t!r}, expected HH:MM")


def _windows(slots: list[dict], step: int = 30) -> list[dict]:
    wins: list[dict] = []
    prev = None
    for s in slots:
        if prev is not None and cc.to_min(s["start"]) == prev + step:
            wins[-1]["end"] = s["end"]
        else:
            wins.append({"start": s["start"], "end": s["end"]})
        prev = cc.to_min(s["start"])
    return wins


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _wd(d: str) -> str:
    return _date.fromisoformat(d).strftime("%A")


def _dm(d: str) -> str:
    x = _date.fromisoformat(d)
    return x.strftime("%a ") + str(x.day) + x.strftime(" %b")


def _label(state, d: str) -> tuple[str, str]:
    delta = (_date.fromisoformat(d) - _date.fromisoformat(state.now["date"])).days
    if delta == 0:
        return "today", "aaj"
    if delta == 1:
        return "tomorrow", "kal"
    return _wd(d), f"{_wd(d)} ko"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _names(state, ids: list[str]) -> str:
    if set(ids) == {m["id"] for m in state.members}:
        return "everyone"
    return _join([state.member(i)["name"] for i in ids])


def _fmt_win(wins: list[dict], hi: bool) -> str:
    if hi:
        return " aur ".join(f"{w['start']} se {w['end']} tak" for w in wins)
    return " and ".join(f"{w['start']} to {w['end']}" for w in wins)


def _loose_time(text: str, bare: bool = False) -> str | None:
    """Like calendar_core.parse_time but also '5 baje', 'at 10', and (bare=True) a lone number."""
    t = cc.parse_time(text)
    if t:
        return t
    low = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*baje\b", low)
    if not m:
        m = re.search(r"\b(?:to|at|by|ko|tak|till|se)\s+(\d{1,2})(?::(\d{2}))?\b(?!\s*" + MONTHS + ")", low)
    if not m and bare:
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b(?!\s*" + MONTHS + ")", low)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if hour > 23:
        return None
    if 1 <= hour <= 6:
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _duration(text: str, default: int) -> int:
    m = re.search(r"\bfor\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)\b", text.lower())
    if not m:
        return default
    value = float(m.group(1))
    return int(value * 60) if m.group(2).startswith("h") else int(value)


def _find_event(state, text: str) -> dict | None:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    if "ptm" in words:
        words |= {"parent", "teacher"}
    best, best_score = None, 0
    for e in sorted(state.calendar, key=lambda e: (e["date"], e["start"])):
        if e["date"] < state.now["date"] or e["kind"] == "travel":
            continue
        tw = {w for w in re.findall(r"[a-z0-9]+", e["title"].lower()) if len(w) > 2}
        strong = (tw - GENERIC) & words
        if not strong:
            continue
        score = 2 * len(strong) + len((tw & GENERIC) & words)
        if score > best_score:
            best, best_score = e, score
    return best


def _scan(state, start_date: str, days: int) -> dict:
    adults = state.parents()
    kids = {m["id"] for m in state.members if m["kind"] == "child"}
    clashes: list[dict] = []
    heads_up: list[str] = []
    for i in range(days):
        d = (_date.fromisoformat(start_date) + timedelta(days=i)).isoformat()
        evs = sorted((e for e in state.calendar if e["date"] == d), key=lambda e: e["start"])
        for a, b in combinations(evs, 2):
            shared = set(a["member_ids"]) & set(b["member_ids"])
            if shared and _overlap(cc.to_min(a["start"]), cc.to_min(a["end"]), cc.to_min(b["start"]), cc.to_min(b["end"])):
                who = _join([state.member(x)["name"] for x in sorted(shared)])
                clashes.append({
                    "type": "double_booking", "date": d, "members": sorted(shared), "events": [a["id"], b["id"]],
                    "text": f"{who} double-booked on {_wd(d)}: {a['title']} {a['start']} and {b['title']} {b['start']}",
                })
        for e in evs:
            kid_ids = set(e["member_ids"]) & kids
            if e["kind"] not in ("school", "activity") or not kid_ids:
                continue
            kid = state.member(sorted(kid_ids)[0])["name"]
            start = cc.to_min(e["start"])
            windows = [(start - (45 if e["kind"] == "school" else 30), start)]
            if e["kind"] == "activity":
                windows.append((cc.to_min(e["end"]), cc.to_min(e["end"]) + 30))
            action = f"see {kid} off for school" if e["kind"] == "school" else f"take or fetch {kid} for {e['title']}"
            free, busy = [], {}
            for a in adults:
                clash = next(
                    (ev for ev in cc.events_for(state, a, d) if any(_overlap(cc.to_min(ev["start"]), cc.to_min(ev["end"]), w0, w1) for w0, w1 in windows)),
                    None,
                )
                if clash:
                    busy[a] = clash
                else:
                    free.append(a)
            if not free:
                clashes.append({
                    "type": "no_parent_free", "date": d, "members": sorted(kid_ids), "events": [e["id"]],
                    "text": f"No parent is free to {action} on {_wd(d)}",
                })
            elif busy:
                other = next(iter(busy))
                heads_up.append(
                    f"Only {state.member(free[0])['name']} can {action} on {_wd(d)}: "
                    f"{state.member(other)['name']} has {busy[other]['title']} at {busy[other]['start']}"
                )
    return {"start_date": start_date, "days": days, "clashes": clashes, "heads_up": heads_up}


def _build_digest(state, start_date: str, days: int = 5) -> dict:
    dates = [(_date.fromisoformat(start_date) + timedelta(days=i)).isoformat() for i in range(days)]
    per_member: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for m in state.members:
        items = [
            f"{e['title']} {_date.fromisoformat(e['date']).strftime('%a')} {e['start']}"
            for d in dates for e in cc.events_for(state, m["id"], d) if e["kind"] != "school"
        ]
        if items:
            per_member[m["name"]] = items
    for d in dates:
        counts[d] = sum(1 for e in state.calendar if e["date"] == d and e["kind"] != "school")
    busiest = max(dates, key=lambda d: (counts[d], -dates.index(d)))
    everyone = [m["id"] for m in state.members]
    best = None
    family_sunday = any("sunday is family day" in f["fact"].lower() for f in state.facts_about("family"))
    for d in dates:
        wins = _windows(cc.find_common_slots(state, everyone, d, 90))
        if not wins:
            continue
        longest = max(wins, key=lambda w: cc.to_min(w["end"]) - cc.to_min(w["start"]))
        length = cc.to_min(longest["end"]) - cc.to_min(longest["start"])
        rank = (1 if (family_sunday and _date.fromisoformat(d).weekday() == 6) else 0, length)
        if best is None or rank > best[0]:
            best = (rank, d, longest)
    scan = _scan(state, start_date, days)
    heads = scan["clashes"][0]["text"] if scan["clashes"] else (scan["heads_up"][0] if scan["heads_up"] else "")
    lines = [f"Week ahead ({_dm(dates[0])} to {_dm(dates[-1])})."]
    lines += [f"{name}: {', '.join(items[:3])}." for name, items in per_member.items()]
    lines.append(f"Busiest day: {_wd(busiest)} with {counts[busiest]} events.")
    if best:
        lines.append(f"Best family-free window (90 min or more): {_wd(best[1])} {best[2]['start']} to {best[2]['end']}.")
    if heads:
        lines.append(f"Heads-up: {heads}.")
    return {
        "text": " ".join(lines), "busiest": busiest, "busiest_count": counts[busiest],
        "best": {"date": best[1], **best[2]} if best else None, "heads_up": heads,
    }


# ---------------------------------------------------------------- tools

def _members_prop(desc: str = "Family member ids, as listed in the family") -> dict:
    return {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": desc}


def _notify_event(state, ids: list[str], text: str) -> None:
    state.notify(ids, text, "calendar", "calendar")


def get_schedule(state, member_ids, date):
    ids = _ids(state, member_ids)
    _valid_date(date)
    return {"date": date, "schedule": {m: [_view(e) for e in cc.events_for(state, m, date)] for m in ids}}


def find_family_slots(state, member_ids, date, duration_min=90, earliest="08:00", latest="21:00", prefer_time=None):
    ids = _ids(state, member_ids)
    _valid_date(date)
    _valid_time(earliest)
    _valid_time(latest)
    if duration_min <= 0:
        raise ToolError("duration_min must be positive")
    slots = cc.find_common_slots(state, ids, date, duration_min, earliest, latest)
    lo, hi = cc.to_min(earliest), cc.to_min(latest)
    blocking = [
        _view(e) for e in sorted(state.calendar, key=lambda e: e["start"])
        if e["date"] == date and set(e["member_ids"]) & set(ids) and cc.to_min(e["end"]) > lo and cc.to_min(e["start"]) < hi
    ]
    best = None
    if slots:
        if prefer_time:
            _valid_time(prefer_time)
            best = min(slots, key=lambda s: abs(cc.to_min(s["start"]) - cc.to_min(prefer_time)))
        else:
            best = slots[0]
    return {
        "date": date, "member_ids": ids, "duration_min": duration_min, "windows": _windows(slots),
        "best": best, "slot_count": len(slots), "blocking": blocking,
    }


def check_conflicts(state, member_ids, date, start, end, exclude_event_id=None):
    ids = _ids(state, member_ids)
    _valid_date(date)
    _valid_time(start)
    _valid_time(end)
    found = [_view(e) for e in cc.conflicts(state, ids, date, start, end) if e["id"] != exclude_event_id]
    return {"date": date, "start": start, "end": end, "conflicts": found, "has_conflicts": bool(found)}


def scan_clashes(state, start_date=None, days=5):
    start_date = start_date or state.now["date"]
    _valid_date(start_date)
    if not 1 <= days <= 14:
        raise ToolError("days must be between 1 and 14")
    return _scan(state, start_date, days)


def create_event(state, member_ids, title, date, start, end, location="", kind="event"):
    ids = _ids(state, member_ids)
    _valid_date(date)
    _valid_time(start)
    _valid_time(end)
    clashes = [_view(e) for e in cc.conflicts(state, ids, date, start, end)]
    event = cc.add_event(state, ids, title, date, start, end, location, kind, "calendar")
    if sum(1 for e in state.calendar if e["id"] == event["id"]) > 1:
        event["id"] = f"cal-{secrets.token_hex(3)}"
    _notify_event(state, ids, f"{title} added: {_dm(date)} {start}-{end}.")
    return {"event": _view(event), "conflicts": clashes, "notified": ids}


def move_event(state, event_id, date=None, start=None, end=None):
    event = next((e for e in state.calendar if e["id"] == event_id), None)
    if event is None:
        raise ToolError(f"no event {event_id}")
    if date:
        _valid_date(date)
    if start:
        _valid_time(start)
    if end:
        _valid_time(end)
    before = _view(event)
    cc.move_event(state, event_id, date, start, end)
    clashes = [_view(e) for e in cc.conflicts(state, event["member_ids"], event["date"], event["start"], event["end"]) if e["id"] != event_id]
    _notify_event(state, event["member_ids"], f"{event['title']} moved to {_dm(event['date'])} {event['start']}-{event['end']}.")
    return {"event": _view(event), "previous": before, "conflicts": clashes, "notified": event["member_ids"]}


def cancel_event(state, event_id):
    event = cc.remove_event(state, event_id)
    _notify_event(state, event["member_ids"], f"{event['title']} on {_dm(event['date'])} {event['start']} was cancelled.")
    return {"cancelled": _view(event), "notified": event["member_ids"]}


def send_digest(state, text, member_ids):
    ids = _ids(state, member_ids)
    note = state.notify(ids, text, "calendar", "calendar")
    return {"notification_id": note["id"], "notified": ids, "channel": note["channel"], "mode": note["mode"]}


TOOLS = [
    Tool(
        "get_schedule", "List each family member's events on one date.",
        {"type": "object", "properties": {"member_ids": _members_prop(), "date": {"type": "string", "description": "YYYY-MM-DD"}},
         "required": ["member_ids", "date"]},
        get_schedule,
    ),
    Tool(
        "find_family_slots", "Find time windows on a date when all the given members are free for at least duration_min.",
        {"type": "object", "properties": {
            "member_ids": _members_prop(), "date": {"type": "string", "description": "YYYY-MM-DD"},
            "duration_min": {"type": "integer", "description": "Needed length in minutes (default 90)"},
            "earliest": {"type": "string", "description": "HH:MM, default 08:00"},
            "latest": {"type": "string", "description": "HH:MM, default 21:00"},
            "prefer_time": {"type": "string", "description": "HH:MM; pick the slot closest to this as 'best'"}},
         "required": ["member_ids", "date"]},
        find_family_slots,
    ),
    Tool(
        "check_conflicts", "Check whether a proposed time overlaps existing events for the given members.",
        {"type": "object", "properties": {
            "member_ids": _members_prop(), "date": {"type": "string"}, "start": {"type": "string", "description": "HH:MM"},
            "end": {"type": "string", "description": "HH:MM"},
            "exclude_event_id": {"type": "string", "description": "Ignore this event (when moving it)"}},
         "required": ["member_ids", "date", "start", "end"]},
        check_conflicts,
    ),
    Tool(
        "scan_clashes", "Scan the coming days for double-bookings and for school or activity runs where a parent is unavailable.",
        {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
            "days": {"type": "integer", "description": "How many days, 1-14 (default 5)"}},
         "required": []},
        scan_clashes,
    ),
    Tool(
        "create_event", "Add an event to the family calendar and notify the members it involves.",
        {"type": "object", "properties": {
            "member_ids": _members_prop("Members attending"), "title": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD"}, "start": {"type": "string", "description": "HH:MM"},
            "end": {"type": "string", "description": "HH:MM"}, "location": {"type": "string"},
            "kind": {"type": "string", "description": "event | work | school | activity | dining | travel"}},
         "required": ["member_ids", "title", "date", "start", "end"]},
        create_event,
    ),
    Tool(
        "move_event", "Move an existing event to another date or start time (keeps its length) and notify its members.",
        {"type": "object", "properties": {
            "event_id": {"type": "string"}, "date": {"type": "string", "description": "New YYYY-MM-DD"},
            "start": {"type": "string", "description": "New start HH:MM"}, "end": {"type": "string", "description": "New end HH:MM"}},
         "required": ["event_id"]},
        move_event,
    ),
    Tool(
        "cancel_event", "Remove an event from the calendar and notify its members.",
        {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]},
        cancel_event,
    ),
    Tool(
        "send_digest", "Post a family digest message to the given members over Agora Chat.",
        {"type": "object", "properties": {"text": {"type": "string"}, "member_ids": _members_prop("Recipients")},
         "required": ["text", "member_ids"]},
        send_digest, stage="after",
    ),
]


# ---------------------------------------------------------------- agent

class CalendarAgent(Specialist):
    name = "calendar"
    title = "Calendar agent"
    keywords = ("calendar", "schedule", "free", "busy", "slot", "meeting", "reschedule", "move", "when", "available", "clash", "conflict", "plan")
    tools = TOOLS

    def __init__(self) -> None:
        self.triggers = [Trigger("week_digest", "Weekly family digest", self._week_digest)]

    def seed(self) -> dict:
        return {}

    # --- intent detection
    def _intent(self, state, text: str) -> str | None:
        low = text.lower()
        if BLOCK.search(low):
            return None
        if CLASH.search(low):
            return "clash"
        if MOVE.search(low) and _find_event(state, low):
            return "move"
        if CANCEL.search(low) and _find_event(state, low):
            return "cancel"
        if ADD_VERB.search(low) and (ADD_NOUN.search(low) or "calendar" in low):
            return "add"
        # "add a family movie night on saturday at seven": a verb plus a day or time is enough
        if re.search(r"\b(add|put|create|set up|block|note)\b", low) and (cc.parse_date(text, state.now["date"]) or _loose_time(text)):
            return "add"
        if FREE.search(low):
            return "free"
        if DIGEST.search(low):
            return "digest"
        if SCHEDULE.search(low):
            return "schedule"
        return None

    def score(self, state, text: str) -> int:
        from .money import is_money

        if is_money(text):  # spending talk belongs to the Money agent
            return 0
        if state.pending and state.pending.get("agent") == self.name:
            return 3
        return 3 if self._intent(state, text) else 0

    # --- shared reply helpers
    def _fail(self, state, member_id, result: dict) -> str:
        err = result.get("error", "unknown error")
        return self.say(state, member_id, f"Sorry, that didn't work: {err}.", f"Maaf kijiye, nahi ho paaya: {err}.")

    def _targets(self, state, member_id: str, text: str, default_all: bool) -> list[str]:
        mentioned = [m["id"] for m in state.mentioned_members(text)]
        if mentioned:
            return mentioned
        if default_all and not re.search(r"\b(i|me|my|mine|main|mera|meri)\b", text.lower()):
            return [m["id"] for m in state.members]
        return [member_id]

    # --- handle
    def handle(self, state, member_id: str, text: str) -> str | None:
        pending = state.pending if state.pending and state.pending.get("agent") == self.name else None
        if pending:
            reply = self._continue(state, member_id, text, pending)
            if reply is not None:
                return reply
            state.pending = None
        intent = self._intent(state, text)
        if intent is None:
            return None
        return getattr(self, f"_do_{intent}")(state, member_id, text)

    def _continue(self, state, member_id: str, text: str, pending: dict) -> str | None:
        if REJECT.search(text.lower()):
            state.pending = None
            return self.say(state, member_id, "Okay, dropped it.", "Theek hai, chhod diya.")
        if pending["action"] == "add":
            return self._finish_add(state, member_id, pending["draft"], text)
        if pending["action"] == "move":
            return self._finish_move(state, member_id, pending["draft"], text)
        return None

    # --- free slots
    def _do_free(self, state, member_id: str, text: str) -> str:
        hi = state.speaks_hindi(member_id)
        low = text.lower()
        ids = self._targets(state, member_id, text, default_all=True)
        duration = _duration(text, 90)
        earliest, latest, prefer, meal = "08:00", "21:00", None, ""
        if "lunch" in low:
            earliest, latest, prefer, meal = "11:30", "15:00", "13:00", "lunch"
        elif "dinner" in low:
            earliest, latest, prefer, meal = "18:00", "21:30", "19:30", "dinner"
        elif "morning" in low or "subah" in low:
            earliest, latest = "08:00", "12:00"
        elif "afternoon" in low:
            earliest, latest = "12:00", "17:00"
        elif "evening" in low or "shaam" in low:
            earliest, latest = "17:00", "21:00"

        d = cc.parse_date(text, state.now["date"])
        if d is None:
            d = self._best_day(state, ids, duration, earliest, latest)
        status, res = self.call(
            state, "find_family_slots", member_ids=ids, date=d, duration_min=duration, earliest=earliest, latest=latest,
            **({"prefer_time": prefer} if prefer else {}),
        )
        if status != "ok":
            return self._fail(state, member_id, res)
        en_day, hi_day = _label(state, d)
        who = _names(state, ids)
        blockers = [
            f"{state.member(e['member_ids'][0])['name']}'s {e['title']} {e['start']}-{e['end']}" if not hi
            else f"{state.member(e['member_ids'][0])['name']} ka {e['title']} {e['start']}-{e['end']}"
            for e in res["blocking"][:3]
        ]
        if not res["windows"]:
            return self.say(
                state, member_id,
                f"There's no {duration}-minute gap {en_day} for {who}" + (f"; busy with {_join(blockers)}." if blockers else "."),
                f"{hi_day.capitalize()} {who} ke liye {duration} minute ka koi gap nahi hai" + (f"; busy: {', '.join(blockers)}." if blockers else "."),
            )
        wins_en, wins_hi = _fmt_win(res["windows"], False), _fmt_win(res["windows"], True)
        best = res["best"]
        extra_en = extra_hi = ""
        if meal and best:
            extra_en = f" Best for {meal}: {best['start']} to {best['end']}."
            extra_hi = f" {meal} ke liye best: {best['start']} se {best['end']} tak."
        block_en = f" Held up by {_join(blockers)}." if blockers else ""
        block_hi = f" Busy: {', '.join(blockers)}." if blockers else ""
        verb = "is" if who == "everyone" or len(ids) == 1 else "are"
        return self.say(
            state, member_id,
            f"{en_day.capitalize()}, {who} {verb} free {wins_en}.{extra_en}{block_en}",
            f"{hi_day.capitalize()} {who} free hain: {wins_hi}.{extra_hi}{block_hi}",
        )

    def _best_day(self, state, ids, duration: int, earliest: str, latest: str) -> str:
        today = _date.fromisoformat(state.now["date"])
        family_sunday = any("sunday is family day" in f["fact"].lower() for f in state.facts_about("family"))
        best = None
        for i in range(5):
            d = (today + timedelta(days=i)).isoformat()
            wins = _windows(cc.find_common_slots(state, ids, d, duration, earliest, latest))
            if not wins:
                continue
            length = max(cc.to_min(w["end"]) - cc.to_min(w["start"]) for w in wins)
            rank = (1 if (family_sunday and (today + timedelta(days=i)).weekday() == 6) else 0, length)
            if best is None or rank > best[0]:
                best = (rank, d)
        return best[1] if best else today.isoformat()

    # --- read schedule
    def _do_schedule(self, state, member_id: str, text: str) -> str:
        ids = self._targets(state, member_id, text, default_all=False)
        d = cc.parse_date(text, state.now["date"]) or state.now["date"]
        status, res = self.call(state, "get_schedule", member_ids=ids, date=d)
        if status != "ok":
            return self._fail(state, member_id, res)
        en_day, hi_day = _label(state, d)
        lead_en = en_day.capitalize() if en_day in ("today", "tomorrow") else f"On {en_day}"
        en_parts, hi_parts = [], []
        for mid in ids:
            evs = res["schedule"][mid]
            name = state.member(mid)["name"]
            me = mid == member_id
            en_who, hi_who = ("you" if me else name), ("Aap" if me else name)
            verb = "have" if me else "has"
            if not evs:
                en_parts.append(f"{en_who} {verb} nothing planned")
                hi_parts.append(f"{hi_who}: kuch nahi")
                continue
            more_en = f" and {len(evs) - 3} more" if len(evs) > 3 else ""
            more_hi = f" aur {len(evs) - 3}" if len(evs) > 3 else ""
            en_parts.append(f"{en_who} {verb} " + ", ".join(f"{_lc(e['title'])} at {e['start']}" for e in evs[:3]) + more_en)
            hi_parts.append(f"{hi_who}: " + ", ".join(f"{e['title']} {e['start']} baje" for e in evs[:3]) + more_hi)
        return self.say(
            state, member_id,
            f"{lead_en}, " + "; ".join(en_parts) + ".",
            f"{hi_day.capitalize()}, " + "; ".join(hi_parts) + ".",
        )

    def _do_digest(self, state, member_id: str, text: str) -> str:
        return self._digest_reply(state, member_id)

    # --- clashes
    def _do_clash(self, state, member_id: str, text: str) -> str:
        status, res = self.call(state, "scan_clashes", start_date=state.now["date"], days=5)
        if status != "ok":
            return self._fail(state, member_id, res)
        clashes, heads = res["clashes"], res["heads_up"]
        if clashes:
            first = clashes[0]["text"]
            more = f" and {len(clashes) - 1} more" if len(clashes) > 1 else ""
            return self.say(
                state, member_id,
                f"I found {len(clashes)} clash{'es' if len(clashes) > 1 else ''}: {first}{more}.",
                f"{len(clashes)} clash mile: {first}{more}.",
            )
        if heads:
            return self.say(
                state, member_id,
                f"No double-bookings this week. One thing to watch: {_lc(heads[0])}.",
                f"Is hafte koi double-booking nahi hai. Ek baat dhyan rakhiye: {heads[0]}.",
            )
        return self.say(state, member_id, "No clashes this week. Everyone's calendar is clear.", "Is hafte koi clash nahi hai. Sabka calendar saaf hai.")

    # --- add
    def _do_add(self, state, member_id: str, text: str) -> str:
        low = text.lower()
        ids = [m["id"] for m in state.mentioned_members(low)] or [member_id]
        title = self._title(low)
        draft = {
            "member_ids": ids, "title": title, "duration": _duration(low, 60),
            "date": cc.parse_date(text, state.now["date"]), "start": _loose_time(text),
        }
        return self._finish_add(state, member_id, draft, None)

    def _title(self, low: str) -> str:
        m = re.search(r"\b(?:(\w+)\s+)?(appointment|meeting|class|event|reminder|practice|call|visit|party|session|lesson|match)\b", low)
        if m:
            lead = m.group(1)
            if lead and lead not in {"a", "an", "the", "new", "my", "our", "ek", "ka", "ki", "ke", "to", "for", "add", "set", "up"} and not lead.isdigit():
                return f"{lead} {m.group(2)}".capitalize()
            return m.group(2).capitalize()
        m = re.search(r"\b(?:add|put|create|schedule|set up|fix|block|note)\b\s+(?:a|an|the|my|one)?\s*(.+)", low)
        if m:
            head = re.split(r"\s+(?:for|on|at|to|tomorrow|today|kal|aaj|in|by|from|with|ko|pe|par)\b", m.group(1))[0].strip()
            if head:
                return head.capitalize()
        return "Event"

    def _finish_add(self, state, member_id: str, draft: dict, reply_text: str | None) -> str | None:
        if reply_text is not None:
            before = (draft["date"], draft["start"])
            draft["date"] = draft["date"] or cc.parse_date(reply_text, state.now["date"])
            draft["start"] = draft["start"] or _loose_time(reply_text, bare=True)
            if (draft["date"], draft["start"]) == before:
                return None
        missing = [k for k in ("date", "start") if not draft[k]]
        if missing:
            state.pending = {"agent": self.name, "action": "add", "draft": draft}
            need_en = "day and time" if len(missing) == 2 else ("day" if missing[0] == "date" else "time")
            need_hi = "kis din aur kitne baje" if len(missing) == 2 else ("kis din" if missing[0] == "date" else "kitne baje")
            return self.say(
                state, member_id,
                f"What {need_en} for the {draft['title'].lower()}?",
                f"{draft['title']} {need_hi} rakhna hai?",
            )
        state.pending = None
        end = cc.to_hhmm(cc.to_min(draft["start"]) + draft["duration"])
        ids = draft["member_ids"]
        s_chk, chk = self.call(state, "check_conflicts", member_ids=ids, date=draft["date"], start=draft["start"], end=end)
        status, res = self.call(
            state, "create_event", member_ids=ids, title=draft["title"], date=draft["date"], start=draft["start"], end=end,
        )
        if status != "ok":
            return self._fail(state, member_id, res)
        who = _names(state, ids)
        en_day, hi_day = _label(state, draft["date"])
        warn_en = warn_hi = ""
        if res["conflicts"]:
            c = res["conflicts"][0]
            warn_en = f" Heads up, it overlaps {c['title']} at {c['start']}."
            warn_hi = f" Dhyan dijiye, yeh {c['title']} ({c['start']}) se takrata hai."
        title_en = draft["title"].lower()
        article = "an" if title_en[:1] in "aeiou" else "a"
        return self.say(
            state, member_id,
            f"Added {article} {title_en} for {who} {en_day} at {draft['start']}.{warn_en}",
            f"{who} ke liye {draft['title'].lower()} {hi_day} {draft['start']} baje add kar diya.{warn_hi}",
        )

    # --- move
    def _do_move(self, state, member_id: str, text: str) -> str:
        low = text.lower()
        event = _find_event(state, low)
        tail_match = re.search(r"\b(?:to|ko)\b(.*)$", low)
        tail = tail_match.group(1) if tail_match else ""
        draft = {
            "event_id": event["id"], "date": cc.parse_date(tail, state.now["date"]) if tail else None,
            "start": _loose_time(tail, bare=True) if tail else None,
        }
        return self._finish_move(state, member_id, draft, None)

    def _finish_move(self, state, member_id: str, draft: dict, reply_text: str | None) -> str | None:
        if reply_text is not None:
            before = (draft["date"], draft["start"])
            draft["date"] = draft["date"] or cc.parse_date(reply_text, state.now["date"])
            draft["start"] = draft["start"] or _loose_time(reply_text, bare=True)
            if (draft["date"], draft["start"]) == before:
                return None
        event = next((e for e in state.calendar if e["id"] == draft["event_id"]), None)
        if event is None:
            state.pending = None
            return self.say(state, member_id, "I can't find that event any more.", "Woh event ab nahi mil raha.")
        if not draft["date"] and not draft["start"]:
            state.pending = {"agent": self.name, "action": "move", "draft": draft}
            return self.say(
                state, member_id,
                f"Move {event['title']} to which time or day?",
                f"{event['title']} ko kis din ya kitne baje karna hai?",
            )
        state.pending = None
        new_date = draft["date"] or event["date"]
        new_start = draft["start"] or event["start"]
        new_end = cc.to_hhmm(cc.to_min(new_start) + cc.to_min(event["end"]) - cc.to_min(event["start"]))
        self.call(
            state, "check_conflicts", member_ids=event["member_ids"], date=new_date, start=new_start, end=new_end,
            exclude_event_id=event["id"],
        )
        status, res = self.call(state, "move_event", event_id=event["id"], date=new_date, start=new_start, end=new_end)
        if status != "ok":
            return self._fail(state, member_id, res)
        en_day, hi_day = _label(state, new_date)
        warn_en = warn_hi = ""
        if res["conflicts"]:
            c = res["conflicts"][0]
            warn_en = f" Heads up, it now clashes with {c['title']} at {c['start']}."
            warn_hi = f" Dhyan dijiye, ab yeh {c['title']} ({c['start']}) se takrata hai."
        return self.say(
            state, member_id,
            f"Moved the {_lc(event['title'])} to {en_day} at {new_start}.{warn_en}",
            f"{event['title']} ko {hi_day} {new_start} baje kar diya.{warn_hi}",
        )

    # --- cancel
    def _do_cancel(self, state, member_id: str, text: str) -> str:
        event = _find_event(state, text.lower())
        status, res = self.call(state, "cancel_event", event_id=event["id"])
        if status != "ok":
            return self._fail(state, member_id, res)
        return self.say(
            state, member_id,
            f"Cancelled the {_lc(event['title'])} on {_wd(event['date'])} and told the family.",
            f"{event['title']} ({_wd(event['date'])}) cancel kar diya, family ko bata diya.",
        )

    # --- digest (voice request and demo trigger)
    def _week_digest(self, state) -> str:
        reply = self._digest_reply(state, state.persona)
        state.say("agent", reply, state.persona, agent=self.name)
        return reply

    def _digest_reply(self, state, member_id: str) -> str:
        digest = _build_digest(state, state.now["date"], 5)
        everyone = [m["id"] for m in state.members]
        self.call(state, "send_digest", text=digest["text"], member_ids=everyone)
        parts_en = [f"Busiest day is {_wd(digest['busiest'])} with {digest['busiest_count']} events."]
        parts_hi = [f"Sabse busy din {_wd(digest['busiest'])} hai, {digest['busiest_count']} events ke saath."]
        if digest["best"]:
            b = digest["best"]
            parts_en.append(f"Best family window: {_wd(b['date'])} {b['start']} to {b['end']}.")
            parts_hi.append(f"Family ke liye best time: {_wd(b['date'])} {b['start']} se {b['end']} tak.")
        if digest["heads_up"]:
            parts_en.append(f"Heads-up: {_lc(digest['heads_up'])}.")
            parts_hi.append(f"Dhyan dijiye: {digest['heads_up']}.")
        return self.say(
            state, member_id,
            "Here's your week. " + " ".join(parts_en) + " The full digest is in everyone's Agora Chat.",
            "Yeh raha is hafte ka haal. " + " ".join(parts_hi) + " Poora digest sabke Agora Chat mein bhej diya.",
        )
