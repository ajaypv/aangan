"""School agent: kids' arrival check-ins, marks, homework, and parent summaries.

Domain data (state.domains["school"]): school, kids{member_id: {...}}, arrivals, notes. Extend, don't rename fields.
Triggers drive the demo: the school-arrival ping (simulated location) notifies both parents.

Tools (all JSON-schema'd): record_arrival, log_marks, get_child_summary, add_homework, complete_homework,
notify_parents (stage "after", parents only).
"""

import re
from datetime import date, timedelta

from ..calendar_core import parse_date, to_min
from ..toolkit import Tool, ToolError
from .base import Specialist, Trigger

SUBJECTS = {
    "maths": "Maths", "math": "Maths", "mathematics": "Maths", "ganit": "Maths",
    "science": "Science", "vigyan": "Science", "english": "English", "hindi": "Hindi",
    "social": "Social Studies", "sst": "Social Studies", "evs": "EVS", "computer": "Computer",
    "kannada": "Kannada", "gk": "General Knowledge",
}
SUBJECT_RE = re.compile(r"\b(" + "|".join(SUBJECTS) + r")\b")
RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|out of|outof|mein se|me se)\s*(\d+(?:\.\d+)?)")
SCORED_RE = re.compile(r"\b(?:got|scored|score|mila|mile|mil gaya|aaye|aaya)\b\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:marks\b|mila|mile)")
MARKER_RE = re.compile(r"\b(marks|mila|mile|got|scored|score|result|test|exam|aaj)\b")
REACHED_RE = re.compile(r"pahunch|pahuch|pohoch|pohch|\breach(?:ed|ing)?\b|school (?:aa|a) gay[aei]")
AT_SCHOOL_RE = re.compile(r"\b(?:at|in) school\b|school (?:me|mein) (?:hoon|hu)\b")
HOMEWORK_RE = re.compile(r"\bhome\s?work\b|\bhw\b")
HOMEWORK_DONE_RE = re.compile(r"ho gaya|ho gya|\bdone\b|complete|finish|kar liya|kar li\b|khatam|\b(?:i|we)\s+(?:just\s+|already\s+)?(?:did|had done)\b")
HOMEWORK_ADD_RE = re.compile(r"\b(?:add|new|naya)\s+(?:\w+\s+)?home\s?work\b|\bhome\s?work\s+add\b")
SUMMARY_RE = re.compile(r"\b(how(?:'s| is| are| has| was| did| do| does)|kaisa|kaisi|kaise|result|marks|report|progress|performance|doing|padhai|studies|grades?)\b")
HOMEWORK_LIST_RE = re.compile(r"\b(what|which|any|how much|how many|pending|due|left|remaining|show|tell|list|read)\b")
GOT_TO_SCHOOL_RE = re.compile(
    r"\b(?:got|gotten|get|gets|getting|arrive[ds]?|arriving|came|come|made it|make it|safely)\s+(?:to|at|in)\s+school\b|"
    r"\bmade it\b.*\bschool\b"
)
OTHER_PLACE_RE = re.compile(r"flight|airport|delhi|goa|train|\bcab\b|taxi")


def _n(x) -> str:
    return str(int(x)) if float(x) == int(x) else str(x)


def _pct(score, mx) -> int:
    return round(100 * float(score) / float(mx))


def _norm_subject(subject: str) -> str:
    return SUBJECTS.get(subject.strip().lower(), subject.strip().title())


def _find_subject(low: str) -> str | None:
    m = SUBJECT_RE.search(low)
    return SUBJECTS[m.group(1)] if m else None


def _child(state, member_id: str) -> dict:
    member = next((m for m in state.members if m["id"] == member_id), None)
    if member is None or member["kind"] != "child":
        raise ToolError(f"{member_id} is not a child in this family")
    return member


def _kid(state, member_id: str) -> dict:
    """Per-child school record, created on first use so children added later work too."""
    kids = state.domains["school"].setdefault("kids", {})
    if member_id not in kids:
        kids[member_id] = {
            "grade": "", "status": "at_home", "arrived_at": None, "last_location": "home",
            "marks": [], "homework": [], "mood_log": [],
        }
    return kids[member_id]


def _school(state) -> dict:
    return state.domains["school"].setdefault("school", {"name": "School", "start": "08:00", "bus_pickup": "07:15"})


def _ordered_marks(kid: dict, subject: str | None = None) -> list[dict]:
    indexed = [(m["date"], i, m) for i, m in enumerate(kid["marks"]) if subject is None or m["subject"] == subject]
    return [m for _, _, m in sorted(indexed, key=lambda t: (t[0], t[1]))]


# --- tools


def record_arrival(state, member_id: str, via: str = "voice", at: str | None = None) -> dict:
    member = _child(state, member_id)
    kid = _kid(state, member_id)
    school = _school(state)
    if at:
        state.now["time"] = at
    today = state.now["date"]
    arrivals = state.domains["school"].setdefault("arrivals", [])
    if kid["status"] == "at_school" and any(a["member_id"] == member_id and a["date"] == today for a in arrivals):
        return {"member_id": member_id, "name": member["name"], "already_recorded": True, "arrived_at": kid["arrived_at"],
                "on_time": to_min(kid["arrived_at"]) <= to_min(school["start"]), "school_start": school["start"]}
    arrived = state.now["time"]
    on_time = to_min(arrived) <= to_min(school["start"])
    kid.update({"status": "at_school", "arrived_at": arrived, "last_location": "school"})
    arrivals.append({"member_id": member_id, "date": today, "time": arrived, "via": via, "on_time": on_time})
    return {"member_id": member_id, "name": member["name"], "arrived_at": arrived, "via": via, "on_time": on_time,
            "school": school["name"], "school_start": school["start"]}


def log_marks(state, member_id: str, subject: str, score: float, max: float = 50, exam: str = "Class test") -> dict:
    member = _child(state, member_id)
    kid = _kid(state, member_id)
    if max <= 0 or score < 0 or score > max:
        raise ToolError(f"{_n(score)} out of {_n(max)} is not a valid mark")
    subject = _norm_subject(subject)
    previous = (_ordered_marks(kid, subject) or [None])[-1]
    number = 1 + sum(len(k["marks"]) for k in state.domains["school"]["kids"].values())
    mark = {"id": f"mk{number}", "subject": subject, "score": score, "max": max, "date": state.now["date"], "exam": exam}
    kid["marks"].append(mark)
    percent = _pct(score, max)
    delta = percent - _pct(previous["score"], previous["max"]) if previous else None
    return {"member_id": member_id, "name": member["name"], "mark": mark, "percent": percent, "previous": previous,
            "delta_pct": delta, "trend": "new" if delta is None else "up" if delta > 0 else "down" if delta < 0 else "flat"}


def get_child_summary(state, member_id: str) -> dict:
    member = _child(state, member_id)
    kid = _kid(state, member_id)
    subjects = []
    for subject in sorted({m["subject"] for m in kid["marks"]}):
        marks = _ordered_marks(kid, subject)
        latest, previous = marks[-1], marks[-2] if len(marks) > 1 else None
        delta = _pct(latest["score"], latest["max"]) - _pct(previous["score"], previous["max"]) if previous else None
        subjects.append({
            "subject": subject, "latest": {**latest, "percent": _pct(latest["score"], latest["max"])}, "previous": previous,
            "delta_pct": delta, "trend": "new" if delta is None else "up" if delta > 0 else "down" if delta < 0 else "flat",
        })
    ranked = sorted(subjects, key=lambda s: s["latest"]["percent"])
    improving = [s for s in subjects if (s["delta_pct"] or 0) > 0]
    pending = sorted((h for h in kid["homework"] if not h["done"]), key=lambda h: h["due"])
    return {
        "member_id": member_id, "name": member["name"], "grade": kid["grade"], "status": kid["status"],
        "arrived_at": kid["arrived_at"], "subjects": subjects,
        "average_pct": round(sum(s["latest"]["percent"] for s in subjects) / len(subjects)) if subjects else None,
        "strongest": ranked[-1]["subject"] if ranked else None,
        "weakest": ranked[0]["subject"] if len(ranked) > 1 else None,
        "most_improved": max(improving, key=lambda s: s["delta_pct"])["subject"] if improving else None,
        "homework_due": pending,
    }


def add_homework(state, member_id: str, subject: str, task: str, due: str | None = None) -> dict:
    member = _child(state, member_id)
    kid = _kid(state, member_id)
    due = due or (date.fromisoformat(state.now["date"]) + timedelta(days=1)).isoformat()
    number = 1 + sum(len(k["homework"]) for k in state.domains["school"]["kids"].values())
    item = {"id": f"hw{number}", "subject": _norm_subject(subject), "task": task.strip(), "due": due, "done": False}
    kid["homework"].append(item)
    return {"member_id": member_id, "name": member["name"], "homework": item}


def complete_homework(state, member_id: str, homework_id: str | None = None, subject: str | None = None) -> dict:
    member = _child(state, member_id)
    kid = _kid(state, member_id)
    pending = sorted((h for h in kid["homework"] if not h["done"]), key=lambda h: h["due"])
    if homework_id:
        item = next((h for h in kid["homework"] if h["id"] == homework_id), None)
    elif subject:
        item = next((h for h in pending if h["subject"] == _norm_subject(subject)), None)
    else:
        item = pending[0] if pending else None
    if item is None:
        raise ToolError("no pending homework found")
    item["done"] = True
    remaining = [h for h in kid["homework"] if not h["done"]]
    return {"member_id": member_id, "name": member["name"], "homework": item, "remaining": len(remaining)}


def notify_parents(state, message: str, kind: str = "school", to: list[str] | None = None) -> dict:
    parents = state.parents()
    recipients = [p for p in (to or parents) if p in parents]
    if not recipients:
        raise ToolError("school updates go to parents only")
    note = state.notify(recipients, message, kind, "school")
    return {"notification_id": note["id"], "to": recipients, "mode": note["mode"], "status": note["status"]}


def _obj(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


TOOLS = [
    Tool("record_arrival", "Record that a child reached school (by voice or a location ping) and mark them at school.",
         _obj({"member_id": {"type": "string", "description": "child's member id, as listed in the family"},
               "via": {"type": "string", "enum": ["voice", "location_ping", "manual"]},
               "at": {"type": "string", "description": "arrival time HH:MM; defaults to the current time"}}, ["member_id"]),
         record_arrival),
    Tool("log_marks", "Log a test or exam mark for a child; returns the change versus their previous mark in that subject.",
         _obj({"member_id": {"type": "string"}, "subject": {"type": "string"}, "score": {"type": "number"},
               "max": {"type": "number", "description": "maximum marks, default 50"},
               "exam": {"type": "string", "description": "e.g. Unit Test 3"}}, ["member_id", "subject", "score"]),
         log_marks),
    Tool("get_child_summary", "Summarise a child's school status: latest marks per subject, trend, strongest and weakest subject, homework due.",
         _obj({"member_id": {"type": "string"}}, ["member_id"]), get_child_summary),
    Tool("add_homework", "Add a homework item for a child.",
         _obj({"member_id": {"type": "string"}, "subject": {"type": "string"}, "task": {"type": "string"},
               "due": {"type": "string", "description": "due date YYYY-MM-DD, default tomorrow"}}, ["member_id", "subject", "task"]),
         add_homework),
    Tool("complete_homework", "Mark a child's homework done: by id, by subject, or the item due soonest.",
         _obj({"member_id": {"type": "string"}, "homework_id": {"type": "string"}, "subject": {"type": "string"}}, ["member_id"]),
         complete_homework),
    Tool("notify_parents", "Send a school update to the parents over Agora Chat. Parents only; never other members.",
         _obj({"message": {"type": "string"}, "kind": {"type": "string"},
               "to": {"type": "array", "items": {"type": "string"}, "description": "parent member ids; default all parents"}}, ["message"]),
         notify_parents, stage="after"),
]


class SchoolAgent(Specialist):
    name = "school"
    title = "School agent"
    family_keys = ("kids", "arrivals", "notes")
    keywords = ("school", "reached", "pahunch", "marks", "score", "exam", "test", "homework", "class", "teacher", "grade", "padhai", "bus", "ptm")
    tools = TOOLS

    def blank(self) -> dict:
        data = super().blank()
        data["school"] = {"name": "School", "start": "08:00", "bus_pickup": "", "address": ""}  # no invented school
        return data

    def __init__(self) -> None:
        self.triggers = [
            Trigger("arrival", "Aarav reaches school", self._arrival_trigger),
            Trigger("homework_nudge", "Homework reminder", self._homework_trigger),
        ]

    def seed(self) -> dict:
        return {
            "school": {"name": "Greenwood Public School", "start": "08:00", "bus_pickup": "07:15", "address": "Greenwood Road, Bengaluru"},
            "kids": {
                "aarav": {
                    "grade": "5-B", "status": "at_home", "arrived_at": None, "last_location": "home",
                    "marks": [
                        {"id": "mk1", "subject": "Maths", "score": 38, "max": 50, "date": "2026-09-18", "exam": "Unit Test 1"},
                        {"id": "mk2", "subject": "Science", "score": 41, "max": 50, "date": "2026-09-25", "exam": "Unit Test 1"},
                        {"id": "mk3", "subject": "English", "score": 36, "max": 50, "date": "2026-10-02", "exam": "Unit Test 1"},
                        {"id": "mk4", "subject": "Maths", "score": 44, "max": 50, "date": "2026-11-06", "exam": "Unit Test 2"},
                    ],
                    "homework": [
                        {"id": "hw1", "subject": "Science", "task": "Draw the water cycle", "due": "2026-11-21", "done": False},
                        {"id": "hw2", "subject": "Maths", "task": "Practice sheet on fractions", "due": "2026-11-23", "done": False},
                    ],
                    "mood_log": [],
                }
            },
            "arrivals": [],
            "notes": [],
        }

    # --- language and member helpers

    def _children(self, state) -> list[dict]:
        return [m for m in state.members if m["kind"] == "child"]

    def _named_children(self, state, text: str) -> list[dict]:
        low = text.lower()
        return [m for m in self._children(state) if re.search(r"\b" + re.escape(m["name"].lower()) + r"\b", low)]

    def _speaker_kind(self, state, member_id: str) -> str:
        member = next((m for m in state.members if m["id"] == member_id), None)
        return member["kind"] if member else "adult"

    def _parent_names(self, state, hi: bool) -> str:
        names = [state.member(p)["name"] for p in state.parents()]
        return (" aur " if hi else " and ").join(names) if names else ("mummy-papa" if hi else "your parents")

    def _due_label(self, state, due: str, hi: bool) -> str:
        tomorrow = (date.fromisoformat(state.now["date"]) + timedelta(days=1)).isoformat()
        if due == state.now["date"]:
            return "aaj" if hi else "today"
        if due == tomorrow:
            return "kal tak" if hi else "tomorrow"
        return (due if not hi else f"{due} tak") if hi else f"by {due}"

    # --- intent detection (no side effects; also drives score())

    def _parse_marks(self, low: str) -> dict | None:
        ratio = RATIO_RE.search(low)
        subject = _find_subject(low)
        if ratio:
            score, mx = float(ratio.group(1)), float(ratio.group(2))
        else:
            single = SCORED_RE.search(low)
            if not (single and subject):
                return None
            score, mx = float(single.group(1) or single.group(2)), 50.0
        if not (subject or MARKER_RE.search(low)):
            return None
        exam = "Class test"
        unit = re.search(r"unit test\s*(\d+)?", low)
        if unit:
            exam = "Unit Test" + (f" {unit.group(1)}" if unit.group(1) else "")
        elif "exam" in low:
            exam = "Exam"
        return {"score": score, "max": mx, "subject": subject, "exam": exam}

    def _intent(self, state, member_id: str, text: str) -> str | None:
        low = text.lower()
        kind = self._speaker_kind(state, member_id)
        named = self._named_children(state, text)
        if self._parse_marks(low):
            return "marks"
        if HOMEWORK_ADD_RE.search(low):
            return "homework_add"
        if HOMEWORK_RE.search(low) and HOMEWORK_DONE_RE.search(low):
            return "homework_done"
        if HOMEWORK_RE.search(low) and HOMEWORK_LIST_RE.search(low) and (named or kind == "child" or "school" in low):
            return "homework_list"
        if REACHED_RE.search(low) or GOT_TO_SCHOOL_RE.search(low) or (AT_SCHOOL_RE.search(low) and not SUMMARY_RE.search(low)):
            if kind == "child":
                return "arrival_report"
            if (named or "school" in low or re.search(r"\b(kids|children|bachche|bacche)\b", low)) and not (
                OTHER_PLACE_RE.search(low) and "school" not in low
            ):
                return "arrival_query"
        if "bus" in low and named:
            return "arrival_query"
        if SUMMARY_RE.search(low):
            schoolish = re.search(r"\bschool\b|padhai|result|marks|report|grades?|exam|test|homework|class|teacher", low)
            if not schoolish and re.search(r"\bwhat(?:'s| is| are| does)\b.*\b(doing|have|got)\b", low):
                return None  # "what is Aarav doing on Monday" is a schedule question for the calendar agent
            if named or re.search(r"\bschool\b|padhai|result|marks|report card", low):
                return "summary"
        return None

    def score(self, state, text: str) -> int:
        from .money import is_money

        return 4 if not is_money(text) and self._intent(state, state.persona, text) else 0

    # --- conversation

    def _resolve_child(self, state, member_id: str, text: str, intent_text: str) -> str | None:
        """Which child the message is about; asks (via pending) when several children and none is named."""
        if self._speaker_kind(state, member_id) == "child":
            return member_id
        named = self._named_children(state, text)
        if len(named) == 1:
            return named[0]["id"]
        kids = self._children(state)
        if not named and len(kids) == 1:
            return kids[0]["id"]
        state.pending = {"agent": self.name, "kind": "which_child", "text": intent_text}
        return None

    def handle(self, state, member_id: str, text: str) -> str | None:
        low = text.lower()
        pending = state.pending
        if pending and pending.get("agent") == self.name:
            state.pending = None
            if pending["kind"] == "marks_subject":
                subject = _find_subject(low)
                if subject:
                    return self._marks(state, member_id, pending["member_id"], pending["score"], pending["max"], subject, pending["exam"])
            elif pending["kind"] == "which_child":
                named = self._named_children(state, text)
                if named:
                    return self.handle(state, member_id, f"{pending['text']} {named[0]['name']}")

        intent = self._intent(state, member_id, text)
        if intent is None:
            return None
        if intent == "arrival_query":
            return self._arrival_query(state, member_id, text)
        ask = self.say(state, member_id, "Which child do you mean?", "Kis bachche ke baare mein? Naam bata dijiye.")
        kid_id = self._resolve_child(state, member_id, text, text)
        if kid_id is None:
            return ask

        if intent == "marks":
            m = self._parse_marks(low)
            if m["subject"] is None:
                state.pending = {"agent": self.name, "kind": "marks_subject", "member_id": kid_id, **{k: m[k] for k in ("score", "max", "exam")}}
                return self.say(state, member_id, "Which subject was that for?", "Yeh kis subject ka tha?")
            return self._marks(state, member_id, kid_id, m["score"], m["max"], m["subject"], m["exam"])
        if intent == "homework_done":
            return self._homework_done(state, member_id, kid_id, _find_subject(low))
        if intent == "homework_add":
            return self._homework_add(state, member_id, kid_id, text)
        if intent == "homework_list":
            return self._homework_list(state, member_id, kid_id)
        if intent == "arrival_report":
            return self._arrival_report(state, member_id, kid_id)
        return self._summary(state, member_id, kid_id)

    def _arrival_report(self, state, member_id: str, kid_id: str) -> str:
        at = None if to_min(state.now["time"]) >= to_min("07:40") else "07:52"
        status, res = self.call(state, "record_arrival", member_id=kid_id, via="voice", at=at)
        if status != "ok":
            return self.say(state, member_id, "I couldn't record that. Please try again.", "Yeh note nahi ho paya, dobara bolo.")
        name, parents_hi, parents_en = res["name"], self._parent_names(state, True), self._parent_names(state, False)
        if res.get("already_recorded"):
            return self.say(
                state, member_id,
                f"You reached at {res['arrived_at']} already, {name}. {parents_en} know.",
                f"Tum {res['arrived_at']} baje hi pahunch gaye the {name}, {parents_hi} ko pata hai.",
            )
        school = res["school"]
        msg = f"{name} reached {school} at {res['arrived_at']}" + (", on time." if res["on_time"] else f", a little after the {res['school_start']} bell.")
        self.call(state, "notify_parents", message=msg, kind="school")
        t = res["arrived_at"]
        if res["on_time"]:
            return self.say(
                state, member_id,
                f"Great, {name}! You reached school at {t}, right on time. I've let {parents_en} know.",
                f"Shabaash {name}! Tum {t} baje school pahunch gaye, bilkul time pe. Maine {parents_hi} ko bata diya.",
            )
        return self.say(
            state, member_id,
            f"You reached at {t}, a little after the bell. That's okay, {name}. I've let {parents_en} know.",
            f"Tum {t} baje pahunche, bell ke thodi der baad. Koi baat nahi {name}. Maine {parents_hi} ko bata diya.",
        )

    def _marks(self, state, member_id: str, kid_id: str, score: float, mx: float, subject: str, exam: str) -> str:
        status, res = self.call(state, "log_marks", member_id=kid_id, subject=subject, score=score, max=mx, exam=exam)
        if status != "ok":
            return self.say(
                state, member_id, f"{_n(score)} out of {_n(mx)} doesn't look right. Can you say it again?",
                f"{_n(score)}/{_n(mx)} theek nahi lag raha. Dobara bolo?",
            )
        name, subj, pct, delta, prev = res["name"], res["mark"]["subject"], res["percent"], res["delta_pct"], res["previous"]
        got = f"{_n(score)}/{_n(mx)}"
        parents_hi, parents_en = self._parent_names(state, True), self._parent_names(state, False)
        if res["trend"] == "up":
            note = f"up {delta} points from last time ({_n(prev['score'])}/{_n(prev['max'])})"
            self.call(state, "notify_parents", message=f"{name} scored {got} in {subj} ({pct}%), {note}.", kind="school")
            return self.say(
                state, member_id,
                f"Well done, {name}! {subj} {got}, {note}. I've told {parents_en}.",
                f"Wah {name}! {subj} mein {got}, pichhli baar se {delta} point zyada. Maine {parents_hi} ko bata diya.",
            )
        if res["trend"] == "down":
            note = f"{-delta} points lower than last time ({_n(prev['score'])}/{_n(prev['max'])})"
            self.call(state, "notify_parents", message=f"{name} scored {got} in {subj} ({pct}%), {note}.", kind="school")
            return self.say(
                state, member_id,
                f"{subj} {got}, a little lower than last time. No worries, {name}, we'll aim higher next test. I've told {parents_en}.",
                f"{subj} mein {got} mila, pichhli baar se thoda kam. Koi baat nahi {name}, agle test mein aur achha karenge. Maine {parents_hi} ko bata diya.",
            )
        extra = " Same as last time, steady." if res["trend"] == "flat" else " That's your first one here, nice start."
        extra_hi = " Pichhli baar jitna hi, steady." if res["trend"] == "flat" else " Yeh pehla score hai, achhi shuruaat."
        self.call(state, "notify_parents", message=f"{name} scored {got} in {subj} ({pct}%).", kind="school")
        return self.say(
            state, member_id, f"Logged {subj} {got}.{extra} I've told {parents_en}.",
            f"{subj} {got} likh liya.{extra_hi} Maine {parents_hi} ko bata diya.",
        )

    def _homework_done(self, state, member_id: str, kid_id: str, subject: str | None) -> str:
        args = {"member_id": kid_id}
        if subject:
            args["subject"] = subject
        status, res = self.call(state, "complete_homework", **args)
        if status != "ok":
            return self.say(state, member_id, "I don't see any pending homework. Nice and clear!", "Koi homework baaki nahi dikh raha. Badhiya!")
        h, left = res["homework"], res["remaining"]
        more_en = f" {left} more to go." if left else " That's all of it!"
        more_hi = f" {left} aur baaki hai." if left else " Sab khatam!"
        return self.say(
            state, member_id, f"Great, {h['subject']} homework is done.{more_en}", f"Shabaash! {h['subject']} ka homework ho gaya.{more_hi}"
        )

    def _homework_add(self, state, member_id: str, kid_id: str, text: str) -> str:
        low = text.lower()
        subject = _find_subject(low) or "General"
        task = re.sub(r"\b(?:add|new|naya)\s+(?:\w+\s+)?home\s?work\b|\bhome\s?work\s+add\b|\bdue\b.*$", "", text, flags=re.I)
        task = SUBJECT_RE.sub("", task.lower()).strip(" ,.:-") or "Homework"
        due = parse_date(text, state.now["date"])
        status, res = self.call(state, "add_homework", member_id=kid_id, subject=subject, task=task.capitalize(), due=due)
        h = res["homework"]
        return self.say(
            state, member_id, f"Added {h['subject']} homework: {h['task']}, due {self._due_label(state, h['due'], False)}.",
            f"{h['subject']} ka homework add kar diya: {h['task']}, {self._due_label(state, h['due'], True)}.",
        )

    def _homework_list(self, state, member_id: str, kid_id: str) -> str:
        name = state.member(kid_id)["name"]
        pending = sorted((h for h in _kid(state, kid_id)["homework"] if not h["done"]), key=lambda h: h["due"])
        who_en = "You have" if member_id == kid_id else f"{name} has"
        if not pending:
            return self.say(
                state, member_id,
                "You have no homework pending. All clear!" if member_id == kid_id else f"{name} has no homework pending. All clear!",
                f"{name} ka koi homework baaki nahi hai. Sab clear!",
            )
        items_en = "; ".join(
            f"{h['subject']}, {h['task'][:1].lower() + h['task'][1:]}, due {self._due_label(state, h['due'], False)}" for h in pending[:3]
        )
        items_hi = "; ".join(f"{h['subject']}: {h['task']}, {self._due_label(state, h['due'], True)}" for h in pending[:3])
        count = len(pending)
        return self.say(
            state, member_id,
            f"{who_en} {count} homework item{'s' if count > 1 else ''} pending: {items_en}.",
            f"{name} ke {count} homework baaki hain: {items_hi}.",
        )

    def _arrival_query(self, state, member_id: str, text: str) -> str:
        named = self._named_children(state, text)
        kids = named or self._children(state)
        school = _school(state)
        en, hi = [], []
        for kid in kids:
            rec = _kid(state, kid["id"])
            if rec["status"] == "at_school":
                en.append(f"{kid['name']} reached at {rec['arrived_at']}.")
                hi.append(f"{kid['name']} {rec['arrived_at']} baje pahunch gaya.")
            else:
                en.append(f"{kid['name']} hasn't reached yet; the bus was due at {school['bus_pickup']} and school starts at {school['start']}.")
                hi.append(f"{kid['name']} abhi nahi pahuncha; bus {school['bus_pickup']} pe aani thi aur school {school['start']} pe shuru hota hai.")
        return self.say(state, member_id, " ".join(en), " ".join(hi))

    def _summary(self, state, member_id: str, kid_id: str) -> str:
        status, s = self.call(state, "get_child_summary", member_id=kid_id)
        name = s["name"]
        if not s["subjects"]:
            return self.say(state, member_id, f"No marks logged for {name} yet.", f"{name} ke abhi koi marks nahi hain.")
        by_subject = {x["subject"]: x for x in s["subjects"]}
        lead_en, lead_hi = f"{name} is averaging {s['average_pct']}%", f"{name} ka average {s['average_pct']}% hai"
        if s["most_improved"]:
            imp = by_subject[s["most_improved"]]
            lead_en += f", and {imp['subject']} is up {imp['delta_pct']} points to {_n(imp['latest']['score'])}/{_n(imp['latest']['max'])}."
            lead_hi += f", aur {imp['subject']} mein {imp['delta_pct']} point badhe hain ({_n(imp['latest']['score'])}/{_n(imp['latest']['max'])})."
        else:
            lead_en, lead_hi = lead_en + ".", lead_hi + "."
        tail_en, tail_hi = [], []
        if s["weakest"]:
            w = by_subject[s["weakest"]]["latest"]["percent"]
            tail_en.append(f"{s['weakest']} needs a little push at {w}%.")
            tail_hi.append(f"{s['weakest']} par thoda dhyan dena hoga ({w}%).")
        if s["homework_due"]:
            h = s["homework_due"][0]
            tail_en.append(f"{h['subject']} homework is due {self._due_label(state, h['due'], False)}.")
            tail_hi.append(f"{h['subject']} ka homework {self._due_label(state, h['due'], True)} dena hai.")
        return self.say(state, member_id, " ".join([lead_en] + tail_en), " ".join([lead_hi] + tail_hi))

    # --- proactive triggers

    def _demo_child(self, state) -> dict | None:
        kids = self._children(state)
        return next((k for k in kids if k["id"] == "aarav"), kids[0] if kids else None)

    def _arrival_trigger(self, state) -> str:
        kid = self._demo_child(state)
        if kid is None:
            return "There are no children in the family yet."
        status, res = self.call(state, "record_arrival", member_id=kid["id"], via="location_ping", at="07:52")
        if res.get("already_recorded"):
            return f"{kid['name']} already reached school at {res['arrived_at']}."
        msg = f"{kid['name']} reached {res['school']} at {res['arrived_at']}" + (", on time." if res["on_time"] else f", after the {res['school_start']} bell.")
        self.call(state, "notify_parents", message=msg, kind="school")
        names = self._parent_names(state, False)
        return f"{msg} I've let {names} know."

    def _homework_trigger(self, state) -> str:
        kid = self._demo_child(state)
        if kid is None:
            return "There are no children in the family yet."
        rec = _kid(state, kid["id"])
        pending = sorted((h for h in rec["homework"] if not h["done"]), key=lambda h: h["due"])
        if not pending:
            return f"{kid['name']} has no homework pending."
        h = pending[0]
        hi = state.speaks_hindi(kid["id"])
        nudge = (
            f"{kid['name']}, {h['subject']} ka homework '{h['task']}' {self._due_label(state, h['due'], True)} dena hai. Aaj shaam ko kar loge?"
            if hi else
            f"{kid['name']}, your {h['subject']} homework '{h['task']}' is due {self._due_label(state, h['due'], False)}. Shall we do it this evening?"
        )
        to = ["priya"] if "priya" in state.parents() else None
        self.call(state, "notify_parents",
                  message=f"I reminded {kid['name']} about {h['subject']} homework ('{h['task']}') due {self._due_label(state, h['due'], False)}.",
                  kind="school", **({"to": to} if to else {}))
        return nudge
