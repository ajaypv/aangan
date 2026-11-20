"""Specialist agent base class. Each specialist owns a slice of the family's world.

A specialist has:
  - seed():   its initial data, stored at state.domains[self.name]
  - tools:    Tool objects (JSON-schema params) used by both the rule engine and the LLM brain
  - handle(): the rule-based (mock-mode) conversation handler; returns the spoken reply, or None if the
              message is not for this agent
  - triggers: proactive scenario buttons ("school arrival", "missed check-in") that run tools and notify family
Use self.call(state, tool_name, **args) to run a tool so it is logged under this agent's name.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from ..toolkit import Tool, run_tool


def _empty_like(value: Any) -> Any:
    if isinstance(value, dict):
        return {}
    if isinstance(value, list):
        return []
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, str):
        return ""
    return None


@dataclass
class Trigger:
    name: str
    label: str
    fn: Callable  # fn(state) -> str  (the agent's proactive spoken/written message)


class Specialist:
    name: str = ""
    title: str = ""
    keywords: tuple[str, ...] = ()
    tools: list[Tool] = []
    triggers: list[Trigger] = []
    # keys of seed() that hold a family's own records (not service catalogues); emptied for a real household
    family_keys: tuple[str, ...] = ()

    def seed(self) -> dict:
        return {}

    def blank(self) -> dict:
        """Domain data for a household that has not entered anything yet: seed() with the family records emptied."""
        data = deepcopy(self.seed())
        for key in self.family_keys:
            if key in data:
                data[key] = _empty_like(data[key])
        return data

    def score(self, state, text: str) -> int:
        low = text.lower()
        return sum(1 for k in self.keywords if k in low)

    def handle(self, state, member_id: str, text: str) -> str | None:
        return None

    # --- helpers for subclasses
    def data(self, state) -> dict:
        return state.domains[self.name]

    def tool(self, name: str) -> Tool:
        return next(t for t in self.tools if t.name == name)

    def call(self, state, tool_name: str, **args) -> tuple[str, dict]:
        return run_tool(state, self.name, self.tool(tool_name), args)

    def say(self, state, member_id: str, en: str, hi: str) -> str:
        """Pick the reply language for this member: Hinglish/Hindi speakers get the Hinglish text."""
        return hi if state.speaks_hindi(member_id) else en

    def run_trigger(self, state, name: str) -> str:
        trigger = next(t for t in self.triggers if t.name == name)
        return trigger.fn(state)
