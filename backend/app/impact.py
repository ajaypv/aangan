"""How much value Aangan has delivered: actions taken and time saved, from the tool-call log.

Every successful tool call that matches the table below counts once (failed calls and lookups do not).
The minutes are rough, stated estimates of how long a person would take to do the same thing by hand; the table is
returned as `assumptions` so the UI can show exactly what the numbers rest on.
"""

import re

KINDS = [
    ("bookings", "Bookings and reservations"),
    ("calendar", "Calendar coordination"),
    ("family", "Family updates"),
    ("care", "School and care"),
    ("money", "Money"),
]
KIND_LABEL = dict(KINDS)

# "agent.tool": (minutes saved, kind, what it is in plain words)
TABLE: dict[str, tuple[int, str, str]] = {
    "dining.book_table": (15, "bookings", "Booking a restaurant table"),
    "dining.arrange_pickup": (8, "bookings", "Booking a cab"),
    "dining.cancel_reservation": (5, "bookings", "Cancelling a reservation"),
    "travel.book_flight": (25, "bookings", "Booking a flight"),
    "travel.rebook_flight": (25, "bookings", "Rebooking a flight"),
    "travel.book_cab": (8, "bookings", "Booking a cab"),
    "travel.update_cab_pickup": (5, "bookings", "Moving a cab pickup"),
    "calendar.find_family_slots": (10, "calendar", "Finding a time everyone is free"),
    "calendar.scan_clashes": (8, "calendar", "Checking the week for clashes"),
    "calendar.check_conflicts": (3, "calendar", "Checking an event for conflicts"),
    "calendar.create_event": (5, "calendar", "Adding a calendar event"),
    "calendar.move_event": (5, "calendar", "Moving a calendar event"),
    "calendar.cancel_event": (3, "calendar", "Cancelling a calendar event"),
    "calendar.send_digest": (10, "calendar", "Writing the weekly family digest"),
    "dining.add_calendar_event": (5, "calendar", "Adding a calendar event"),
    "travel.add_trip_to_calendar": (5, "calendar", "Adding a trip to calendars"),
    "dining.notify_family": (2, "family", "Sending a family notification"),
    "travel.notify_family": (2, "family", "Sending a family notification"),
    "school.notify_parents": (2, "family", "Sending a family notification"),
    "household.add_member": (3, "family", "Adding a family member"),
    "household.update_member": (2, "family", "Updating a family member"),
    "household.remember_fact": (1, "family", "Remembering a preference or allergy"),
    "school.record_arrival": (3, "care", "Logging a school arrival"),
    "school.log_marks": (3, "care", "Logging marks"),
    "school.add_homework": (2, "care", "Adding homework"),
    "school.complete_homework": (1, "care", "Ticking off homework"),
    "school.get_child_summary": (5, "care", "Summarising a child's school progress"),
    "care.log_medicine_taken": (2, "care", "Logging medicine taken"),
    "care.record_checkin": (3, "care", "Logging a wellbeing check-in"),
    "care.escalate_missed_checkin": (5, "care", "Alerting the family about a missed check-in"),
    "care.order_refill": (12, "care", "Ordering a medicine refill"),
    "care.book_appointment": (20, "care", "Booking a doctor appointment"),
    "care.get_care_summary": (5, "care", "Summarising a senior's day"),
    "money.log_expense": (2, "money", "Logging an expense"),
    "money.get_spending_summary": (5, "money", "Summarising spending"),
    "money.suggest_savings": (5, "money", "Giving savings advice"),
    "money.get_budget_status": (3, "money", "Checking budgets"),
    "money.set_budget": (3, "money", "Setting a budget"),
    "money.list_expenses": (2, "money", "Looking up expenses"),
    "money.delete_expense": (1, "money", "Removing an expense"),
}

# the money agent's tool names are matched by what they do, so a rename there does not zero the numbers
MONEY_RULES = [
    (re.compile(r"expense|spend_log|log_spend|add_spend|record_spend"), 2, "Logging an expense"),
    (re.compile(r"saving|advice|tip|budget_advice"), 5, "Giving savings advice"),
    (re.compile(r"summary|overview|report|spending"), 5, "Summarising spending"),
]
ALERT_KINDS = {"urgent", "alert", "budget", "care_alert"}
ALERT_TEXT = re.compile(
    r"urgent|did not answer|missed|running low|low stock|over budget|overspen|over the budget|please call|call (?:her|him|them) now|unwell|alerted",
    re.I,
)


def _lookup(agent: str, tool: str) -> tuple[int, str, str] | None:
    entry = TABLE.get(f"{agent}.{tool}")
    if entry:
        return entry
    if agent == "money":
        for pattern, minutes, label in MONEY_RULES:
            if pattern.search(tool):
                return minutes, "money", label
        return 3, "money", "Money help"
    return None


def is_alert(note: dict) -> bool:
    return note.get("kind") in ALERT_KINDS or bool(ALERT_TEXT.search(note.get("text", "")))


def _money(state) -> dict | None:
    try:
        from .agents.money import overview
    except ImportError:
        return None
    try:
        data = overview(state)
    except Exception:  # the impact page must not fail because of the money agent
        return None
    if not isinstance(data, dict):
        return None
    return {
        "currency": data.get("currency", "INR"),
        "month_total": data.get("month_total", 0),
        "budget_total": data.get("budget_total", 0),
        "budget_left": data.get("budget_left", 0),
        "potential_savings": data.get("potential_savings", 0),
        "top_tip": data.get("top_tip"),
    }


def assumptions() -> list[str]:
    seen: dict[str, int] = {}
    for minutes, _, label in TABLE.values():
        seen.setdefault(label, minutes)
    for _, minutes, label in MONEY_RULES:
        seen.setdefault(label, minutes)
    return [f"{label}: about {minutes} min saved" for label, minutes in seen.items()]


def compute(state) -> dict:
    counted: set[int] = set()
    kinds = {key: {"key": key, "label": label, "count": 0, "minutes_saved": 0} for key, label in KINDS}
    for event in state.events:
        if event.get("status") != "ok" or event.get("id") in counted:
            continue
        entry = _lookup(event.get("agent", ""), event.get("tool", ""))
        if entry is None:
            continue
        counted.add(event["id"])
        minutes, kind, _ = entry
        kinds[kind]["count"] += 1
        kinds[kind]["minutes_saved"] += minutes
    by_kind = [k for k in kinds.values() if k["count"]]
    return {
        "actions": sum(k["count"] for k in by_kind),
        "minutes_saved": sum(k["minutes_saved"] for k in by_kind),
        "by_kind": by_kind,
        "alerts": sum(1 for n in state.notifications if is_alert(n)),
        "notifications": len(state.notifications),
        "money": _money(state),
        "assumptions": assumptions(),
    }
