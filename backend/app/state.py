import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import chat, seed
from .config import language_override, set_language_override, settings

DEMO_ENV = "AANGAN_DEMO_ON_START"
MAX_EVENTS_SAVED = 200
MAX_TRANSCRIPT_SAVED = 100


def _zone():
    """The household's timezone: India by default (a host such as Render runs on UTC), AANGAN_TIMEZONE to change it."""
    try:
        return ZoneInfo(os.getenv("AANGAN_TIMEZONE", "").strip() or "Asia/Kolkata")
    except Exception:  # no tz database on this machine: fall back to India's fixed offset
        return timezone(timedelta(hours=5, minutes=30))


def _real_now() -> dict:
    now = datetime.now(_zone())
    return {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M")}


def _scripted_clock() -> bool:
    """AANGAN_CLOCK=scripted pins the demo family to its scripted morning (Friday 07:30). Otherwise every household,
    the demo included, follows the real clock."""
    return os.getenv("AANGAN_CLOCK", "real").strip().lower() == "scripted"


class FamilyState:
    def __init__(self, demo: bool = True) -> None:
        self.lock = threading.Lock()
        self.demo = demo
        self.reset()

    def reset(self, demo: bool | None = None) -> None:
        """Back to the starting point of the current mode (the demo family or an empty household).
        Passing demo=True/False switches the mode first."""
        from .agents import REGISTRY

        if demo is not None:
            self.demo = demo
        if self.demo:
            self.members = deepcopy(seed.MEMBERS)
            self.memory = deepcopy(seed.MEMORY)
            self.calendar = deepcopy(seed.CALENDAR)
            self.now = {"date": seed.TODAY, "time": "07:30"} if _scripted_clock() else _real_now()
            self.persona = "priya"
        else:
            self.members, self.memory, self.calendar = [], [], []
            self.now = _real_now()
            self.persona = ""
        self.stage = "before"  # before | during | action | after
        self.pending: dict | None = None  # {"agent": name, ...} awaiting a yes/no from the user
        self.chaos = False
        self.events: list[dict] = []
        self.transcript: list[dict] = []
        self.notifications: list[dict] = []
        self.domains: dict = {}
        for agent in REGISTRY:
            self.domains[agent.name] = agent.seed() if self.demo else agent.blank()

    def load_demo(self) -> None:
        self.reset(demo=True)

    def refresh_clock(self) -> None:
        """Every household follows the real clock, except the demo when AANGAN_CLOCK=scripted."""
        if not (self.demo and _scripted_clock()):
            self.now.update(_real_now())

    # --- family lookups
    def member(self, member_id: str) -> dict:
        return next(m for m in self.members if m["id"] == member_id)

    def find_member(self, text: str) -> dict | None:
        low = text.lower()
        for m in self.members:
            for key in (m["name"], m["relation"], m["id"]):
                if re.search(rf"\b{re.escape(key.lower())}\b", low):
                    return m
        return None

    def mentioned_members(self, text: str) -> list[dict]:
        """Members named in the text; 'everyone', 'all of us', 'sab' or 'family' means all of them."""
        low = text.lower()
        if re.search(r"\b(everyone|everybody|all of us|sab|sabhi|family|hum sab|saath mein)\b", low):
            return list(self.members)
        found = []
        for m in self.members:
            for key in (m["name"], m["relation"], m["id"]):
                if re.search(r"\b" + re.escape(key.lower()) + r"\b", low):
                    found.append(m)
                    break
        return found

    def facts_about(self, member_id: str) -> list[dict]:
        return [f for f in self.memory if f["about"] == member_id]

    def reply_language(self, member_id: str) -> str:
        """Language Aangan answers this member in: always English in english mode, else the member's own."""
        if settings().language_mode in ("english", "multi"):
            return "English"  # multi-language mode reads the language from each message instead (see languages.detect)
        return self.member(member_id)["language"]

    def speaks_hindi(self, member_id: str) -> bool:
        return self.reply_language(member_id) in ("Hindi", "Hinglish")

    def parents(self) -> list[str]:
        return [m["id"] for m in self.members if m["kind"] == "adult"]

    # --- logging
    def log(self, agent: str, tool: str, args: dict, status: str, result: dict, ms: int) -> dict:
        with self.lock:
            event = {
                "id": len(self.events) + 1, "stage": self.stage, "agent": agent, "tool": tool, "args": args,
                "status": status, "result": result, "ms": ms, "ts": datetime.now(_zone()).strftime("%H:%M:%S"),
            }
            self.events.append(event)
        return event

    def say(self, role: str, text: str, member_id: str, agent: str | None = None) -> None:
        self.transcript.append(
            {"role": role, "member_id": member_id, "agent": agent, "text": text, "ts": datetime.now(_zone()).strftime("%H:%M:%S")}
        )

    def notify(self, to: list[str], text: str, kind: str, agent: str) -> dict:
        """Record a family notification and deliver it over Agora Chat when Chat is configured.

        mode/status: live+sent (delivered), live+failed (Chat error), in_app+in_app (Chat not configured)."""
        cfg = settings()
        chat_status, chat_mode = "in_app", "in_app"
        if cfg.chat_ready:
            chat_mode = "live"
            try:
                chat.send_text(cfg, f"[{kind}] {text}")
                chat_status = "sent"
            except httpx.HTTPError:
                chat_status = "failed"
        note = {
            "id": len(self.notifications) + 1, "to": list(to), "kind": kind, "agent": agent, "text": text,
            "channel": "agora_chat", "mode": chat_mode, "status": chat_status, "at": self.now["time"],
            "date": self.now["date"],
        }
        self.notifications.append(note)
        return note

    # --- persistence (see persistence.py)
    def to_dict(self) -> dict:
        """The household's own data. Never includes settings or secrets."""
        return {
            "version": 1,
            "demo": self.demo,
            "members": self.members,
            "memory": self.memory,
            "calendar": self.calendar,
            "domains": self.domains,
            "notifications": self.notifications,
            "events": self.events[-MAX_EVENTS_SAVED:],
            "transcript": self.transcript[-MAX_TRANSCRIPT_SAVED:],
            "persona": self.persona,
            "now": self.now if self.demo else None,
            "language_mode": language_override(),  # the household's own choice in Settings, if it made one
        }

    def apply_dict(self, data: dict) -> None:
        """Replace this household with saved data. Raises on malformed input before changing anything."""
        from .agents import REGISTRY

        members, memory, calendar = list(data["members"]), list(data["memory"]), list(data["calendar"])
        domains, notifications = dict(data["domains"]), list(data["notifications"])
        events, transcript = list(data["events"]), list(data["transcript"])
        for m in members:
            m["id"], m["name"], m["kind"]  # noqa: B018  (KeyError on a malformed member)
        self.demo = bool(data.get("demo", False))
        self.members, self.memory, self.calendar = members, memory, calendar
        self.notifications, self.events, self.transcript = notifications, events, transcript
        for agent in REGISTRY:  # an agent added since the file was written still gets its blank domain
            domains.setdefault(agent.name, agent.seed() if self.demo else agent.blank())
        self.domains = domains
        ids = {m["id"] for m in members}
        saved_persona = data.get("persona") or ""
        self.persona = saved_persona if saved_persona in ids else (members[0]["id"] if members else "")
        saved_now = data.get("now")
        self.now = dict(saved_now) if self.demo and _scripted_clock() and isinstance(saved_now, dict) else _real_now()
        self.pending, self.stage, self.chaos = None, "before", False
        set_language_override(data.get("language_mode"))

    def snapshot(self) -> dict:
        from .agents import REGISTRY

        self.refresh_clock()
        return {
            "now": self.now, "persona": self.persona, "stage": self.stage, "chaos": self.chaos,
            "household": {"exists": bool(self.members), "demo": self.demo},
            "members": self.members, "memory": self.memory, "calendar": self.calendar,
            "domains": self.domains, "pending": self.pending, "events": self.events,
            "notifications": self.notifications, "transcript": self.transcript,
            "agents": [
                {
                    "name": a.name, "title": a.title,
                    # triggers are scripted scenarios built around the demo family, so only the demo lists them
                    "triggers": [{"name": t.name, "label": t.label} for t in a.triggers] if self.demo else [],
                }
                for a in REGISTRY
            ],
        }


STATE = FamilyState(demo=os.getenv(DEMO_ENV, "") == "1")
