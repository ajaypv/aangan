"""Shared calendar helpers used by every agent. Dates are YYYY-MM-DD, times are HH:MM."""

from .toolkit import ToolError


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def events_for(state, member_id: str, date: str) -> list[dict]:
    return sorted(
        (e for e in state.calendar if member_id in e["member_ids"] and e["date"] == date),
        key=lambda e: e["start"],
    )


def busy_intervals(state, member_ids: list[str], date: str) -> list[tuple[int, int]]:
    spans = sorted(
        (to_min(e["start"]), to_min(e["end"]))
        for e in state.calendar
        if e["date"] == date and set(e["member_ids"]) & set(member_ids)
    )
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def conflicts(state, member_ids: list[str], date: str, start: str, end: str) -> list[dict]:
    s, e = to_min(start), to_min(end)
    return [
        ev for ev in state.calendar
        if ev["date"] == date and set(ev["member_ids"]) & set(member_ids) and to_min(ev["start"]) < e and s < to_min(ev["end"])
    ]


def find_common_slots(state, member_ids: list[str], date: str, duration_min: int,
                      earliest: str = "08:00", latest: str = "21:00", step: int = 30) -> list[dict]:
    busy = busy_intervals(state, member_ids, date)
    slots = []
    t = to_min(earliest)
    while t + duration_min <= to_min(latest):
        if all(t + duration_min <= bs or t >= be for bs, be in busy):
            slots.append({"start": to_hhmm(t), "end": to_hhmm(t + duration_min)})
        t += step
    return slots


def add_event(state, member_ids: list[str], title: str, date: str, start: str, end: str,
              location: str = "", kind: str = "event", source: str = "") -> dict:
    if to_min(end) <= to_min(start):
        raise ToolError("event must end after it starts")
    used = [int(e["id"][3:]) for e in state.calendar if re.fullmatch(r"ev-\d+", e["id"])]
    event = {
        "id": f"ev-{max(used, default=0) + 1}", "title": title, "member_ids": list(member_ids), "date": date,
        "start": start, "end": end, "location": location, "kind": kind, "source": source,
    }
    state.calendar.append(event)
    return event


def move_event(state, event_id: str, date: str | None = None, start: str | None = None, end: str | None = None) -> dict:
    event = next((e for e in state.calendar if e["id"] == event_id), None)
    if event is None:
        raise ToolError(f"no event {event_id}")
    if start and not end:
        end = to_hhmm(to_min(start) + to_min(event["end"]) - to_min(event["start"]))
    event.update({k: v for k, v in {"date": date, "start": start, "end": end}.items() if v})
    return event


def remove_event(state, event_id: str) -> dict:
    event = next((e for e in state.calendar if e["id"] == event_id), None)
    if event is None:
        raise ToolError(f"no event {event_id}")
    state.calendar.remove(event)
    return event


# --- natural-language helpers shared by all agents

import re
from datetime import date as _date, timedelta

_WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3,
             "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
             "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3, "shukravar": 4, "shanivar": 5, "ravivar": 6, "itwar": 6}


def parse_date(text: str, today: str) -> str | None:
    """'today', 'tomorrow', 'kal', 'sunday', 'on 26 dec', '2026-12-26' -> YYYY-MM-DD relative to `today`; None if absent."""
    low = text.lower()
    base = _date.fromisoformat(today)
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", low)
    if iso:
        return iso.group(1)
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", low) or \
        re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", low)
    if m:
        a, b = m.groups()
        day, mon = (int(a), months[b]) if a.isdigit() else (int(b), months[a])
        year = base.year if (mon, day) >= (base.month, base.day) else base.year + 1
        return _date(year, mon, day).isoformat()
    if re.search(r"\b(today|aaj)\b", low):
        return base.isoformat()
    if re.search(r"\b(yesterday|last night)\b", low):
        return (base - timedelta(days=1)).isoformat()
    if re.search(r"\blast week\b", low):
        return (base - timedelta(days=7)).isoformat()
    if re.search(r"\b(day after tomorrow|parso)\b", low):
        return (base + timedelta(days=2)).isoformat()
    if re.search(r"\b(tomorrow|kal)\b", low):
        return (base + timedelta(days=1)).isoformat()
    for word, idx in _WEEKDAYS.items():
        if re.search(rf"\b{word}\b", low):
            ahead = (idx - base.weekday()) % 7
            return (base + timedelta(days=ahead or 7 if ahead == 0 and "next" in low else ahead)).isoformat()
    return None


def parse_time(text: str) -> str | None:
    """'1 pm', '13:30', '7:15 am', 'noon' -> HH:MM; None if absent."""
    low = text.lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if m:
        hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        hour = hour % 12 + (12 if ap == "pm" else 0)
        return f"{hour:02d}:{minute:02d}"
    m = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(?:o'?clock\s*)?(?:in the |at |this )?(morning|afternoon|evening|night|tonight)\b", low)
    if m:  # "10 in the morning", "7 tonight"
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) == "morning":
            hour = hour % 12 if hour == 12 else hour
        elif hour < 12:
            hour += 12
        return f"{hour:02d}:{minute:02d}"
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", low)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    if re.search(r"\bnoon\b", low):
        return "12:00"
    return None
