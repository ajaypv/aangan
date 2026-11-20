"""Care agent: senior wellbeing. Medicine reminders and confirmation, daily check-ins, missed-check-in escalation,
doctor appointments, refills.

Domain data (state.domains["care"]): seniors{member_id: {...}}, checkins, appointments, orders. Extend, don't rename fields.
Fields this agent adds: care["chaos_fired"] (bool, set once the simulated pharmacy failure has fired),
checkins[] items {id, member_id, date, at, mood, note}, orders[] items {id, member_id, med, dose, days_supply,
pharmacy, eta, status}, appointments[] items {id, member_id, doctor, clinic, date, time, end, escort, cab, event_id}.
A dose is keyed in med["taken"] as "YYYY-MM-DD HH:MM" (the scheduled slot) -> the HH:MM it was logged.
"""

import re
from datetime import date as _date, timedelta

from .. import calendar_core as cal
from ..toolkit import Tool, ToolError
from .base import Specialist, Trigger

DEFAULT_PHARMACY = "MedPlus Jayanagar"
BACKUP_PHARMACY = "Apollo Pharmacy Jayanagar"

STRONG_TERMS = (
    "medicine", "medication", "dawai", "dawa", "tablet", "pill", "refill", "doctor", "appointment", "check-in",
    "checkin", "check in", "checkup", "check-up", "clinic", "bp", "blood pressure", "sugar", "pharmacy", "chakkar",
    "tabiyat", "tabiat", "tabeeyat", "health", "dizzy", "unwell", "not feeling well", "feel weak", "chest pain",
    "fever", "bukhar", "dard", "kamzori", "metformin", "amlodipine",
    "feel well", "feel sick", "feeling sick", "feel ill", "feeling ill", "not well", "headache", "feel bad", "feeling bad",
    "stomach", "nausea", "vomit", "feel weak", "hurt", "ache", "aching",
)
NOT_MINE = re.compile(r"remember|yaad rakh|what do you know|who is")
CONCERN = re.compile(
    r"chakkar|tabiyat|tabiat|tabeeyat|\bdard\b|\bpain\b|dizz|not feeling well|unwell|feel(?:ing)? weak|kamzori|"
    r"bukhar|fever|saans|breath|\bchest\b|behosh|faint|ghabrahat|\bsick\b|nausea|ulti|"
    r"(?:don't|do not|dont|not) (?:feel|feeling) (?:well|good|right)|feel(?:ing)? (?:ill|bad|off)|\bnot well\b|headache|stomach|vomit|"
    r"\bhurts?\b|\bhurting\b|\bache\b|\baching\b"
)
URGENT = re.compile(r"\bchest\b|breath|saans|faint|behosh|stroke|unconscious|\bfell\b|gir gayi|gir gaye")
TAKEN = re.compile(r"\b(le li|le liya|le lee|kha li|kha liya|khali|li hai|liya hai|khayi|took|taken|had my)\b")
QUESTION = re.compile(r"\?|\bdid\b|\bkya\b|\bhas\b")
REFILL = re.compile(
    r"khatam|finish|running (?:low|out|short)|ran out|run out|refill|re-?order|order|stock|low on|bachi|baaki kam|\bend\b|"
    r"almost (?:over|done|finished|out|empty|gone)|nearly (?:over|finished|empty|out|gone)|about to run out|need more|need a refill|"
    r"(?:is|are) over\b"
)
NOT_TAKEN = re.compile(
    r"\b(?:haven't|have not|hasn't|has not|didn't|did not|not yet|forgot|forgotten|yet to|missed|skipped|couldn't|could not)\b"
)
APPT = re.compile(r"appointment|doctor|check-?up|clinic|\bdr\b")
BOOK = re.compile(r"book|schedule|fix|set up|arrange|take her|le jao|le jana|dikhana|dikhane|lena hai|jaana hai|jana hai|chahiye|karwa|kar do|karo")
CANCEL = re.compile(r"\b(cancel|nahi|nahin|no|rehne do|chhodo|never mind)\b")
BASE_QUERY = re.compile(r"how('s| is)|kaisi|kaise|status|did |took|taken|today|aaj|update|report|summary")


def _care(state) -> dict:
    return state.domains["care"]


def _senior(state, member_id: str) -> dict:
    senior = _care(state)["seniors"].get(member_id)
    if senior is None:
        raise ToolError(f"{member_id} is not set up for care")
    return senior


def _name(state, member_id: str) -> str:
    return state.member(member_id)["name"]


def _contacts(state, member_id: str, hi: bool = False) -> str:
    """Names of the people who get called about this senior: 'Rahul and Priya', or 'the family' when nobody is set up."""
    senior = _care(state)["seniors"].get(member_id) or {}
    ids = [c for c in senior.get("emergency_contacts", []) if any(m["id"] == c for m in state.members)] or state.parents()
    names = [_name(state, i) for i in ids]
    if not names:
        return "ghar walon" if hi else "the family"
    return (" aur " if hi else " and ").join(names)


def _doses(state, member_id: str) -> list[dict]:
    senior, today, now = _senior(state, member_id), state.now["date"], cal.to_min(state.now["time"])
    out = []
    for med in senior["meds"]:
        for slot in med["times"]:
            key, sm = f"{today} {slot}", cal.to_min(slot)
            if key in med["taken"]:
                status = "taken"
            elif sm <= now - 60:
                status = "missed"
            elif sm <= now:
                status = "due"
            else:
                status = "upcoming"
            out.append({"med": med["name"], "dose": med["dose"], "slot": slot, "status": status, "taken_at": med["taken"].get(key)})
    return sorted(out, key=lambda d: d["slot"])


def _find_med(senior: dict, med_name: str | None) -> dict | None:
    if not med_name:
        return None
    return next((m for m in senior["meds"] if med_name.lower() in m["name"].lower()), None)


def _fmt_date(date: str) -> str:
    return _date.fromisoformat(date).strftime("%A %d %b")


def _time_from(text: str) -> str | None:
    found = cal.parse_time(text)
    if found:
        return found
    low = text.lower()
    m = re.search(r"\bat\s+(\d{1,2})\b(?!\s*(?:st|nd|rd|th|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))", low) or re.search(r"\b(\d{1,2})\s+baje\b", low)
    if not m:
        return None
    hour = int(m.group(1))
    if 1 <= hour <= 6:
        hour += 12
    return f"{hour:02d}:00" if 7 <= hour <= 23 else None


# --- tools


def log_medicine_taken(state, member_id: str, med_name: str | None = None) -> dict:
    senior, today, now = _senior(state, member_id), state.now["date"], cal.to_min(state.now["time"])
    logged, nothing_due, matched = [], [], False
    for med in senior["meds"]:
        if med_name and med_name.lower() not in med["name"].lower():
            continue
        matched = True
        open_slots = [s for s in med["times"] if f"{today} {s}" not in med["taken"] and cal.to_min(s) <= now + 120]
        if open_slots:
            slot = max(open_slots, key=cal.to_min)
            med["taken"][f"{today} {slot}"] = state.now["time"]
            logged.append({"med": med["name"], "dose": med["dose"], "slot": slot})
        else:
            nothing_due.append(med["name"])
    if med_name and not matched:
        raise ToolError(f"no medicine called {med_name}")
    return {"member_id": member_id, "logged": logged, "nothing_due": nothing_due, "at": state.now["time"]}


def record_checkin(state, member_id: str, mood: str, note: str = "") -> dict:
    senior = _senior(state, member_id)
    if mood not in ("good", "okay", "unwell", "no_response"):
        raise ToolError(f"unknown mood {mood}")
    care = _care(state)
    entry = {"id": f"ci-{len(care['checkins']) + 1}", "member_id": member_id, "date": state.now["date"],
             "at": state.now["time"], "mood": mood, "note": note}
    care["checkins"].append(entry)
    if mood != "no_response":
        senior["last_checkin"] = {"date": entry["date"], "at": entry["at"], "mood": mood}
    notified: list[str] = []
    if mood == "unwell":
        urgent = bool(URGENT.search(note.lower()))
        text = f"{'URGENT: ' if urgent else ''}{_name(state, member_id)} says she is not feeling well ('{note.strip()[:80]}'). Please call her."
        notified = state.parents()
        state.notify(notified, text, "care", "care")
    return {"checkin": entry, "notified": notified}


def escalate_missed_checkin(state, member_id: str) -> dict:
    senior = _senior(state, member_id)
    contacts = [c for c in senior["emergency_contacts"] if any(m["id"] == c for m in state.members)] or state.parents()
    unconfirmed = [d for d in _doses(state, member_id) if d["status"] in ("missed", "due")]
    tries = sum(1 for c in _care(state)["checkins"] if c["member_id"] == member_id and c["date"] == state.now["date"] and c["mood"] == "no_response")
    text = f"URGENT: {_name(state, member_id)} has not answered her check-in ({tries} tries by {state.now['time']})."
    if unconfirmed:
        text += f" {len(unconfirmed)} medicine dose(s) today are unconfirmed."
    text += " Please call her now."
    state.notify(contacts, text, "care", "care")
    return {"member_id": member_id, "notified": contacts, "tries": tries, "unconfirmed_doses": len(unconfirmed), "message": text}


def order_refill(state, member_id: str, med_name: str, pharmacy: str = DEFAULT_PHARMACY, notify_to: list[str] | None = None) -> dict:
    senior = _senior(state, member_id)
    med = _find_med(senior, med_name)
    if med is None:
        raise ToolError(f"no medicine called {med_name}")
    care = _care(state)
    if state.chaos and not care.get("chaos_fired") and pharmacy == DEFAULT_PHARMACY:
        care["chaos_fired"] = True
        raise ToolError(f"{pharmacy} could not fulfil {med['name']} (supplier timeout)")
    days_before = med["stock_days"]
    med["stock_days"] += 30
    eta = f"{(_date.fromisoformat(state.now['date']) + timedelta(days=1)).isoformat()} 11:00-13:00"
    order = {"id": f"ord-{len(care['orders']) + 1}", "member_id": member_id, "med": med["name"], "dose": med["dose"],
             "days_supply": 30, "pharmacy": pharmacy, "eta": eta, "status": "ORDERED"}
    care["orders"].append(order)
    recipients = [r for r in (notify_to or state.parents()) if any(m["id"] == r for m in state.members)] or state.parents()
    state.notify(recipients, f"{_name(state, member_id)}'s {med['name']} was down to {days_before} days. Refill ordered from {pharmacy}, arriving tomorrow 11:00-13:00.", "care", "care")
    return {**order, "stock_days_before": days_before, "notified": recipients}


def book_appointment(state, member_id: str, date: str, time: str, doctor: str | None = None) -> dict:
    senior = _senior(state, member_id)
    care = _care(state)
    doctor = doctor or senior["doctor"]["name"] or "the doctor"
    clinic = senior["doctor"]["clinic"]
    end = cal.to_hhmm(cal.to_min(time) + 45)
    clash = cal.conflicts(state, [member_id], date, time, end)
    if clash:
        raise ToolError(f"{_name(state, member_id)} already has '{clash[0]['title']}' {clash[0]['start']}-{clash[0]['end']} that day")
    pickup = cal.to_hhmm(cal.to_min(time) - 45)
    back_by = cal.to_hhmm(cal.to_min(end) + 30)
    escort = next((p for p in state.parents() if not cal.conflicts(state, [p], date, pickup, back_by)), None)
    cab = {"booking": f"CAB-{9001 + len(care['appointments'])}", "pickup": pickup, "status": "CONFIRMED"}
    people = [member_id] + ([escort] if escort else [])
    event = cal.add_event(state, people, f"Doctor: {doctor}", date, time, end, clinic, "health", "care")
    appt = {"id": f"appt-{len(care['appointments']) + 1}", "member_id": member_id, "doctor": doctor, "clinic": clinic,
            "date": date, "time": time, "end": end, "escort": escort, "cab": cab, "event_id": event["id"]}
    care["appointments"].append(appt)
    senior["doctor"]["next_appointment"] = {"date": date, "time": time}
    who = f"{_name(state, escort)} will take her" if escort else "neither of you is free, so please arrange someone to go with her"
    state.notify(state.parents(), f"{_name(state, member_id)}'s appointment with {doctor} is booked for {_fmt_date(date)} at {time}; {who}. Cab {cab['booking']} picks her up at {pickup}.", "care", "care")
    return {**appt, "escort_available": escort is not None, "notified": state.parents()}


def add_medicine(state, member_id: str, name: str, dose: str = "", times: list[str] | None = None, stock_days: int = 30) -> dict:
    senior = _senior(state, member_id)
    name = (name or "").strip()
    if not name:
        raise ToolError("a medicine name is required")
    slots = times or ["08:30"]
    for slot in slots:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(slot)):
            raise ToolError(f"bad time {slot!r}, expected HH:MM")
    if any(m["name"].lower() == name.lower() for m in senior["meds"]):
        raise ToolError(f"{name} is already on the list")
    med = {"id": f"med{len(senior['meds']) + 1}", "name": name, "dose": dose.strip(), "times": sorted(slots),
           "stock_days": max(0, int(stock_days)), "taken": {}}
    senior["meds"].append(med)
    return {"member_id": member_id, "medicine": med, "count": len(senior["meds"])}


def get_care_summary(state, member_id: str) -> dict:
    senior = _senior(state, member_id)
    doses = _doses(state, member_id)
    care = _care(state)
    return {
        "member_id": member_id, "name": _name(state, member_id), "date": state.now["date"], "time": state.now["time"],
        "doses": doses,
        "taken": sum(1 for d in doses if d["status"] == "taken"),
        "total": len(doses),
        "missed": sum(1 for d in doses if d["status"] == "missed"),
        "stock_warnings": [{"med": m["name"], "stock_days": m["stock_days"]} for m in senior["meds"] if m["stock_days"] <= 3],
        "last_checkin": senior["last_checkin"],
        "next_appointment": senior["doctor"]["next_appointment"],
        "open_concerns": sum(1 for c in care["checkins"] if c["member_id"] == member_id and c["date"] == state.now["date"] and c["mood"] == "unwell"),
    }


_MEMBER = {"type": "string", "description": "Family member id of the senior, as listed in the family"}

TOOLS = [
    Tool(
        "log_medicine_taken",
        "Record that a senior took the medicine dose that is due now (or about to be due). Optionally limit to one medicine.",
        {"type": "object", "properties": {"member_id": _MEMBER, "med_name": {"type": "string", "description": "Medicine name, e.g. Metformin. Omit for all medicines due."}}, "required": ["member_id"]},
        log_medicine_taken,
    ),
    Tool(
        "record_checkin",
        "Log a wellbeing check-in. mood 'unwell' also alerts both parents to call her; 'no_response' records an unanswered attempt.",
        {"type": "object", "properties": {"member_id": _MEMBER, "mood": {"type": "string", "enum": ["good", "okay", "unwell", "no_response"]}, "note": {"type": "string", "description": "What she said or why it was logged"}}, "required": ["member_id", "mood"]},
        record_checkin,
    ),
    Tool(
        "escalate_missed_checkin",
        "Urgently notify the emergency contacts (parents) that a senior has not answered her check-in, including unconfirmed medicine doses.",
        {"type": "object", "properties": {"member_id": _MEMBER}, "required": ["member_id"]},
        escalate_missed_checkin,
        stage="after",
    ),
    Tool(
        "order_refill",
        "Order a 30-day refill of a medicine from the pharmacy for next-day delivery and notify the family. Pass a different pharmacy if the first fails.",
        {"type": "object", "properties": {"member_id": _MEMBER, "med_name": {"type": "string"}, "pharmacy": {"type": "string", "description": f"Defaults to {DEFAULT_PHARMACY}; backup is {BACKUP_PHARMACY}"}, "notify_to": {"type": "array", "items": {"type": "string"}, "description": "Member ids to notify; defaults to both parents"}}, "required": ["member_id", "med_name"]},
        order_refill,
    ),
    Tool(
        "book_appointment",
        "Book a doctor appointment for a senior: adds it to the calendar, arranges a cab, picks a free parent as escort and notifies the family. Fails if the senior is busy then.",
        {"type": "object", "properties": {"member_id": _MEMBER, "date": {"type": "string", "description": "YYYY-MM-DD"}, "time": {"type": "string", "description": "HH:MM, 24-hour"}, "doctor": {"type": "string", "description": "Defaults to her usual doctor"}}, "required": ["member_id", "date", "time"]},
        book_appointment,
    ),
    Tool(
        "add_medicine",
        "Add a medicine to a senior's daily list so Aangan can remind, track doses and warn when stock is low.",
        {"type": "object", "properties": {"member_id": _MEMBER, "name": {"type": "string"}, "dose": {"type": "string", "description": "e.g. 500 mg"}, "times": {"type": "array", "items": {"type": "string"}, "description": "Daily dose times as HH:MM, 24-hour. Defaults to 08:30."}, "stock_days": {"type": "integer", "description": "Days of supply left. Defaults to 30."}}, "required": ["member_id", "name"]},
        add_medicine,
    ),
    Tool(
        "get_care_summary",
        "Today's medicine doses (taken, missed, due, upcoming), low stock warnings, last check-in, next appointment and open health concerns for a senior.",
        {"type": "object", "properties": {"member_id": _MEMBER}, "required": ["member_id"]},
        get_care_summary,
    ),
]


class CareAgent(Specialist):
    name = "care"
    title = "Care agent"
    family_keys = ("seniors", "checkins", "appointments", "orders", "chaos_fired")
    keywords = STRONG_TERMS
    tools = TOOLS

    def __init__(self) -> None:
        self.triggers = [
            Trigger("morning_checkin", "Dadi morning check-in", self._morning_checkin),
            Trigger("missed_checkin", "Dadi misses check-in", self._missed_checkin),
            Trigger("low_stock", "Medicine running low", self._low_stock),
        ]

    def seed(self) -> dict:
        return {
            "seniors": {
                "dadi": {
                    "meds": [
                        {"id": "med1", "name": "Metformin", "dose": "500 mg", "times": ["08:30", "20:30"], "stock_days": 2, "taken": {}},
                        {"id": "med2", "name": "Amlodipine", "dose": "5 mg", "times": ["08:30"], "stock_days": 9, "taken": {}},
                    ],
                    "checkin_times": ["09:00", "18:00"],
                    "last_checkin": None,
                    "doctor": {"name": "Dr. Sharma", "clinic": "Sunrise Clinic, Jayanagar", "next_appointment": {"date": "2026-11-27", "time": "11:00"}},
                    "emergency_contacts": ["rahul", "priya"],
                }
            },
            "checkins": [],
            "appointments": [],
            "orders": [],
        }

    # --- routing

    def score(self, state, text: str) -> int:
        from .money import is_money

        low = text.lower()
        if NOT_MINE.search(low) or is_money(low):  # spending talk belongs to the Money agent
            return 0
        hits = sum(1 for t in STRONG_TERMS if re.search(r"\b" + re.escape(t), low))
        if not hits:
            return 4 if self._asks_about_senior(state, low) else 0
        return 3 * min(hits, 3) + (1 if "dadi" in low else 0)

    def _asks_about_senior(self, state, low: str) -> bool:
        """'how is Dadi today', 'Dadi kaisi hai': a wellbeing question naming a senior (the name alone never counts)."""
        if re.search(r"\b(everyone|everybody|everyone's|all of us|whole family|the family)\b", low):
            return False  # a question about the whole family is a schedule question
        seniors = _care(state)["seniors"]
        names_senior = any(m["id"] in seniors for m in state.mentioned_members(low))
        return names_senior and bool(
            re.search(r"how('s| is| are| was| did)|kaisi|kaise|kya haal|\bhaal\b|\bdoing\b|\bstatus\b|\bupdate\b", low)
            or re.search(r"\b(?:is|are|was)\b.*\b(?:okay|ok|alright|all right|fine|well|safe|healthy|better)\b", low)
        )

    def handle(self, state, member_id: str, text: str) -> str | None:
        low = text.lower()
        pending = state.pending if state.pending and state.pending.get("agent") == self.name else None
        if pending:
            return self._continue(state, member_id, text, pending)
        if self.score(state, text) == 0:
            return None
        if not _care(state)["seniors"]:
            return self.say(
                state, member_id,
                "I'm not looking after anyone's medicines yet. Add an older family member in the Family section and I'll track their medicines, check-ins and doctor visits.",
                "Abhi main kisi ki dawai nahi dekh raha. Family mein bade-bujurg ko add kijiye, phir main unki dawai, check-in aur doctor ka dhyaan rakhunga.",
            )
        sid = self._target(state, member_id, text)
        if CONCERN.search(low):
            return self._concern(state, member_id, sid, text)
        if REFILL.search(low) and not APPT.search(low):
            return self._refill(state, member_id, sid, low)
        if NOT_TAKEN.search(low) and re.search(r"medicine|medication|tablet|pill|dawai|dose|metformin|amlodipine", low):
            # "I haven't taken my medicine" must never be logged as taken: remind instead
            reminder = self._summary(state, member_id, sid)
            return ("No problem. " + reminder) if member_id == sid else reminder
        if TAKEN.search(low) and not QUESTION.search(low):
            return self._taken(state, member_id, sid)
        if APPT.search(low):
            if BOOK.search(low):
                return self._start_booking(state, member_id, sid, text)
            if re.search(r"when|kab|next|which day|what time", low):
                return self._next_appointment(state, member_id, sid)
        return self._summary(state, member_id, sid)

    def _target(self, state, member_id: str, text: str) -> str:
        seniors = _care(state)["seniors"]
        if member_id in seniors:
            return member_id
        for m in state.mentioned_members(text):
            if m["id"] in seniors:
                return m["id"]
        return next(iter(seniors))

    # --- intents

    def _concern(self, state, member_id: str, sid: str, text: str) -> str:
        urgent = bool(URGENT.search(text.lower()))
        self.call(state, "record_checkin", member_id=sid, mood="unwell", note=text.strip())
        name = _name(state, sid)
        if member_id == sid:
            who_en, who_hi = _contacts(state, sid), _contacts(state, sid, hi=True)
            en = f"I'm sorry you feel unwell, {name}. Please sit down and sip some water; have you eaten today? I've asked {who_en} to call you."
            hi = f"{name}, aap baith jaiye aur paani pijiye, maine {who_hi} ko phone karne ko bol diya hai. Kya aapne aaj khana khaya?"
            if urgent:
                en = f"{name}, please sit down and stay calm; I've alerted {who_en}. If it is severe, call 112 right away."
                hi = f"{name}, aap baith jaiye, maine {who_hi} ko bata diya hai. Agar zyada takleef ho to turant 112 par phone karein."
        else:
            en = f"Noted. I've logged it and alerted both of you; please call {name} now." + (" If it is severe, call 112." if urgent else "")
            hi = f"Likh liya, aap dono ko bata diya hai; {name} ko abhi phone kijiye." + (" Zyada takleef ho to 112 par phone karein." if urgent else "")
        return self.say(state, member_id, en, hi)

    def _refill(self, state, member_id: str, sid: str, low: str) -> str:
        senior = _senior(state, sid)
        if not senior["meds"]:
            return self.say(
                state, member_id,
                f"I don't have any medicines on file for {_name(state, sid)} yet. Add one in the Family section first, then I can order refills.",
                f"{_name(state, sid)} ki koi dawai abhi list mein nahi hai. Pehle Family mein dawai jodiye, phir main order kar dunga.",
            )
        med = next((m for m in senior["meds"] if m["name"].lower() in low), None) or min(senior["meds"], key=lambda m: m["stock_days"])
        status, result = self.call(state, "order_refill", member_id=sid, med_name=med["name"])
        used_backup = False
        if status == "error":
            status, result = self.call(state, "order_refill", member_id=sid, med_name=med["name"], pharmacy=BACKUP_PHARMACY)
            used_backup = status == "ok"
        name = _name(state, sid)
        if status != "ok":
            return self.say(state, member_id, f"I couldn't place the {med['name']} order with either pharmacy; I'll tell the family.", f"{med['name']} ka order nahi ho paaya, main ghar walon ko bata deta hoon.")
        en = f"Done: {med['name']} refill ordered from {result['pharmacy']} for tomorrow between 11 and 1, and the family is informed."
        hi = f"Theek hai {name}, {med['name']} ka order ho gaya, kal dopahar tak aa jayegi. Maine {_contacts(state, sid, hi=True)} ko bhi bata diya hai."
        if used_backup:
            en += " The first pharmacy had no stock, so I used the backup."
        return self.say(state, member_id, en, hi)

    def _taken(self, state, member_id: str, sid: str) -> str:
        name = _name(state, sid)
        if not _senior(state, sid)["meds"]:
            return self.say(state, member_id, f"There are no medicines on file for {name} yet, so there is nothing to log.", f"{name} ki koi dawai list mein nahi hai, isliye likhne ko kuch nahi.")
        status, result = self.call(state, "log_medicine_taken", member_id=sid)
        meds = ", ".join(f"{d['med']} {d['dose']}" for d in result["logged"])
        if not result["logged"]:
            return self.say(state, member_id, f"All of {name}'s medicines due so far are already logged.", f"{name}, aapki abhi tak ki saari dawai pehle se likhi hui hai.")
        return self.say(state, member_id, f"Thank you, I've logged {meds}.", f"Shukriya {name}, maine {meds} likh li hai.")

    def _summary(self, state, member_id: str, sid: str) -> str:
        status, s = self.call(state, "get_care_summary", member_id=sid)
        name = s["name"]
        if not s["total"]:
            return self.say(state, member_id, f"I don't have any medicines on file for {name} yet. You can add them in the Family section.", f"{name} ki koi dawai abhi list mein nahi hai. Family mein jodi ja sakti hai.")
        upcoming = next((d for d in s["doses"] if d["status"] in ("due", "upcoming")), None)
        if member_id == sid:
            if upcoming:
                en = f"{name}, your next medicine is {upcoming['med']} {upcoming['dose']} at {upcoming['slot']}."
                hi = f"{name}, aapki agli dawai {upcoming['med']} {upcoming['dose']} hai, {upcoming['slot']} baje."
            else:
                en, hi = f"{name}, you've taken everything for today.", f"{name}, aaj ki saari dawai ho gayi hai."
            return self.say(state, member_id, en, hi)
        en = f"{name} has taken {s['taken']} of {s['total']} doses today" + (f", {s['missed']} missed" if s["missed"] else "")
        hi = f"{name} ne aaj {s['total']} mein se {s['taken']} dawai li hain" + (f", {s['missed']} chhoot gayi" if s["missed"] else "")
        if upcoming:
            en += f"; next is {upcoming['med']} at {upcoming['slot']}."
            hi += f"; agli {upcoming['med']} {upcoming['slot']} baje."
        else:
            en, hi = en + ".", hi + "."
        if s["stock_warnings"]:
            w = s["stock_warnings"][0]
            en += f" {w['med']} is down to {w['stock_days']} days; shall I reorder?"
            hi += f" {w['med']} sirf {w['stock_days']} din ki bachi hai, order kar doon?"
        elif s["last_checkin"]:
            en += f" Last check-in {s['last_checkin']['at']}: {s['last_checkin']['mood']}."
            hi += f" Aakhri check-in {s['last_checkin']['at']} baje, {s['last_checkin']['mood']}."
        else:
            en += " No check-in yet today."
            hi += " Aaj abhi tak check-in nahi hua."
        return self.say(state, member_id, en, hi)

    def _next_appointment(self, state, member_id: str, sid: str) -> str:
        appt = _senior(state, sid)["doctor"]["next_appointment"]
        doctor = _senior(state, sid)["doctor"]["name"] or "the doctor"
        if not appt:
            return self.say(state, member_id, f"{_name(state, sid)} has no doctor visit booked yet. Tell me a day and time and I'll book one.", f"{_name(state, sid)} ki abhi koi appointment nahi hai. Din aur samay bataiye, main book kar dunga.")
        when = f"{_fmt_date(appt['date'])} at {appt['time']}"
        return self.say(state, member_id, f"{_name(state, sid)}'s next visit with {doctor} is {when}.", f"{_name(state, sid)} ki agli appointment {doctor} ke saath {_fmt_date(appt['date'])} ko {appt['time']} baje hai.")

    def _start_booking(self, state, member_id: str, sid: str, text: str) -> str:
        doctor = re.search(r"\bDr\.?\s*([A-Z][a-z]+)", text)
        return self._book_or_ask(state, member_id, {
            "sid": sid, "date": cal.parse_date(text, state.now["date"]), "time": _time_from(text),
            "doctor": f"Dr. {doctor.group(1)}" if doctor else None,
        })

    def _book_or_ask(self, state, member_id: str, plan: dict) -> str:
        if not plan["date"]:
            state.pending = {"agent": self.name, "step": "appointment", **plan}
            return self.say(state, member_id, "Which day should I book the appointment?", "Kaun se din ke liye appointment book karni hai?")
        if not plan["time"]:
            state.pending = {"agent": self.name, "step": "appointment", **plan}
            return self.say(state, member_id, "What time works for the appointment?", "Kis samay ki appointment rakhein?")
        state.pending = None
        sid = plan["sid"]
        status, result = self.call(state, "book_appointment", member_id=sid, date=plan["date"], time=plan["time"], doctor=plan["doctor"])
        if status == "error":
            state.pending = {"agent": self.name, "step": "appointment", **{**plan, "time": None}}
            return self.say(state, member_id, f"{result['error']}. Which other time should I try?", f"{result['error']}. Kaun sa doosra samay dekhein?")
        doctor, fmt = result["doctor"], _fmt_date(result["date"])
        if result["escort"]:
            escort = _name(state, result["escort"])
            en = f"Booked {doctor} on {fmt} at {result['time']}; {escort} will take her and the cab comes at {result['cab']['pickup']}."
            hi = f"{fmt} ko {result['time']} baje {doctor} ki appointment book ho gayi; {escort} saath jayenge aur cab {result['cab']['pickup']} baje aayegi."
        else:
            en = f"Booked {doctor} on {fmt} at {result['time']} with a cab at {result['cab']['pickup']}, but neither of you is free to go along. Can one of you confirm?"
            hi = f"{fmt} ko {result['time']} baje {doctor} ki appointment book ho gayi, cab {result['cab']['pickup']} baje hai, par aap dono khaali nahi hain. Koi ek saath ja sakta hai?"
        return self.say(state, member_id, en, hi)

    def _continue(self, state, member_id: str, text: str, pending: dict) -> str:
        if CANCEL.search(text.lower()):
            state.pending = None
            return self.say(state, member_id, "Okay, I'll leave the appointment for now.", "Theek hai, appointment abhi rehne dete hain.")
        plan = {k: pending.get(k) for k in ("sid", "date", "time", "doctor")}
        plan["date"] = cal.parse_date(text, state.now["date"]) or plan["date"]
        plan["time"] = _time_from(text) or plan["time"]
        return self._book_or_ask(state, member_id, plan)

    # --- triggers (scenario buttons)

    def _first_senior(self, state) -> str:
        return next(iter(_care(state)["seniors"]))

    def _morning_checkin(self, state) -> str:
        sid = self._first_senior(state)
        state.now["time"] = "09:00"
        state.say("agent", "Namaste Dadi, subah ke nau baje hain. Aapne subah ki dawai li? Raat ko neend kaisi aayi?", sid, agent=self.name)
        state.say("user", "Haan beta, dawai le li. Neend achhi aayi.", sid)
        self.call(state, "log_medicine_taken", member_id=sid)
        self.call(state, "record_checkin", member_id=sid, mood="good", note="Morning check-in: took her medicines, slept well")
        reply = "Bahut accha Dadi, maine dawai aur check-in likh liya hai. Shaam ko 6 baje phir baat karenge."
        state.say("agent", reply, sid, agent=self.name)
        return reply

    def _missed_checkin(self, state) -> str:
        sid = self._first_senior(state)
        for attempt, clock in enumerate(("18:00", "18:05"), start=1):
            state.now["time"] = clock
            state.say("agent", "Dadi, namaste, aap theek hain? Shaam ke check-in ka time ho gaya hai." if attempt == 1 else "Dadi, kya aap sun rahi hain? Kripya ek baar jawab dijiye.", sid, agent=self.name)
            self.call(state, "record_checkin", member_id=sid, mood="no_response", note=f"Check-in attempt {attempt} unanswered")
        state.now["time"] = "18:10"
        status, result = self.call(state, "escalate_missed_checkin", member_id=sid)
        return f"{_name(state, sid)} did not answer two check-in calls. I've alerted {_contacts(state, sid)} to call her now."

    def _low_stock(self, state) -> str:
        sid = self._first_senior(state)
        senior = _senior(state, sid)
        med = min(senior["meds"], key=lambda m: m["stock_days"])
        recipient = "priya" if any(m["id"] == "priya" for m in state.members) else state.parents()[0]
        status, result = self.call(state, "order_refill", member_id=sid, med_name=med["name"], notify_to=[recipient])
        if status == "error":
            status, result = self.call(state, "order_refill", member_id=sid, med_name=med["name"], pharmacy=BACKUP_PHARMACY, notify_to=[recipient])
        if status != "ok":
            reply = f"{_name(state, sid)}'s {med['name']} is running low and both pharmacies failed. Please order it today."
        else:
            reply = f"{_name(state, recipient)}, {_name(state, sid)}'s {med['name']} was down to {result['stock_days_before']} days, so I ordered a refill from {result['pharmacy']}; it arrives tomorrow between 11 and 1."
        state.say("agent", reply, recipient, agent=self.name)
        return reply
