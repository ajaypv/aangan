"""Routes each utterance to the right specialist agent (rule engine), or to the LLM brain when configured."""

import queue
import re
import threading
import time

from . import languages
from .agents import BY_NAME, REGISTRY
from .config import settings
from .normalize import normalize
from .speech import clean_input, speakable

FALLBACK_EN = "I can help with flights and cabs, calendars, restaurant bookings, school updates, care for the older members, family memory, and the linked virtual house's lights and doors. What do you need?"
FALLBACK_HI = "Main flight aur cab, calendar, restaurant booking, school updates, bade-bujurgon ki dekhbhal aur family ki baatein sambhal sakta hoon. Bataiye kya karna hai?"


_THANKS = re.compile(r"\b(thank(?:s| you)|cheers|appreciate it)\b", re.I)
_BYE = re.compile(r"\b(bye|goodbye|see you|talk (?:to you )?later|good night)\b", re.I)
_GREETING = re.compile(r"^\W*(hello|hi|hey|good (morning|afternoon|evening)|namaste)\b", re.I)
_HELP = re.compile(r"\b(what can you do|what do you do|how do you work|help)\b", re.I)
_BARE_ANSWER = re.compile(r"^\W*(yes|yeah|yep|yup|no|nope|ok|okay|sure|please)\W*$", re.I)


def small_talk(state, member_id: str, text: str) -> str:
    """English replies for greetings, thanks and answers with nothing pending; anything else gets the capabilities list."""
    name = state.member(member_id)["name"]
    if _THANKS.search(text):
        return "You're welcome. Anything else for the family?"
    if _BYE.search(text):
        return f"Goodbye, {name}. I'm here whenever you need me."
    if _HELP.search(text):
        return FALLBACK_EN
    greeting = _GREETING.search(text)
    if greeting:
        opener = greeting.group(2) and f"Good {greeting.group(2).lower()}" or "Hello"
        return f"{opener}, {name}. How can I help the family today?"
    if _BARE_ANSWER.search(text):
        return "Sorry, I'm not sure what that answers. What would you like me to do?"
    return FALLBACK_EN


def load_context(state, member_id: str) -> dict:
    """Before stage: retrieve who is speaking and what the family remembers about them."""
    member = state.member(member_id)
    ctx = {
        "speaker": member["name"], "language": member["language"], "family_size": len(state.members),
        "facts": [f["fact"] for f in state.facts_about(member_id)],
        "family_facts": [f["fact"] for f in state.facts_about("family")],
    }
    start = time.perf_counter()
    state.stage = "before"
    state.log("orchestrator", "load_member_context", {"member": member_id}, "ok", ctx, int((time.perf_counter() - start) * 1000))
    return ctx


def route(state, text: str):
    scored = sorted(((a.score(state, text), i, a) for i, a in enumerate(REGISTRY)), key=lambda t: (-t[0], t[1]))
    return scored[0][2] if scored[0][0] > 0 else None


# A request goes to the rule engine first when it is plain and unambiguous: that answer takes milliseconds, the LLM
# takes seconds. Anything unclear, merged ("book it and tell Meera") or without a clear owner goes to the LLM.
FAST_SCORE = 3
_COMPOUND = re.compile(
    r"\b(?:and|then|also|plus|after that)\s+(?:then\s+)?(?:please\s+)?"
    r"(?:book|move|add|cancel|remind|tell|text|message|send|find|schedule|order|log|set|call|reschedule|check|ask|notify|let|put|assign|give|make|buy|pick|collect|pay)\b",
    re.I,
)
# "What is metformin?", "why is the stock low", "no, I'm asking what that is": questions about meaning need a model, not a status report
_EXPLAIN = re.compile(
    r"\b(what(?:'s| is| are| does)\b(?!.*\b(?:schedule|calendar|plan|planned|today|tomorrow|tonight|doing|happening|free|booked|due|left|spent|spend|budget|balance|cost|on|pending|overdue|tasks?|to-?do|list|priorities|chores)\b)"
    r"|who is|why|how (?:does|do|come)|explain|i'?m asking|i am asking|do you mean|what do you mean|meaning of|what does .* mean)",
    re.I,
)
_SMALL_TALK = (_THANKS, _BYE, _GREETING)
FILLER = "One moment."
FILLER_AFTER_S = 3.0  # silence this long before the first word and the voice gets a short filler


def _prepare(state, member_id: str, text: str) -> None:
    state.refresh_clock()
    state.persona = member_id
    state.say("user", text, member_id)
    load_context(state, member_id)
    state.stage = "during"


def _is_small_talk(text: str) -> bool:
    return len(text.split()) <= 6 and any(p.search(text) for p in _SMALL_TALK)


def _rule_reply(state, member_id: str, text: str, heard: str, english: bool):
    """The rule engine's whole pipeline: pending flow, routing, small talk, capabilities. Returns (agent_name, reply)."""
    agent, reply = None, None
    pending_agent = BY_NAME.get(state.pending.get("agent")) if state.pending else None
    if pending_agent:
        other = route(state, text)
        if other is not None and other is not pending_agent and other.score(state, text) >= 3 and pending_agent.score(state, text) == 0:
            state.pending = None  # a different agent clearly owns this message: the user moved on
            pending_agent = None
    if pending_agent:
        agent = pending_agent
        reply = agent.handle(state, member_id, text)
        if reply is None:
            state.pending = None
    if reply is None:
        agent = route(state, text)
        reply = agent.handle(state, member_id, text) if agent else None
    if reply is None:
        reply = small_talk(state, member_id, heard) if english else FALLBACK_HI
    return (agent.name if agent else "aangan"), reply


def _fast_rule_reply(state, member_id: str, heard: str, english: bool):
    """The rule engine's answer when it is sure, as (agent_name, reply), else None (the LLM takes over)."""
    text = clean_input(normalize(heard), state.members)
    if _COMPOUND.search(text):
        return None
    pending_flow = bool(state.pending and BY_NAME.get(state.pending.get("agent")))
    if _EXPLAIN.search(heard) and not pending_flow:
        return None
    if state.pending and BY_NAME.get(state.pending.get("agent")):
        return _rule_reply(state, member_id, text, heard, english)  # a booking or question the rules asked is theirs to finish
    if english and _is_small_talk(heard):
        return "aangan", small_talk(state, member_id, heard)
    scored = sorted(((a.score(state, text), i, a) for i, a in enumerate(REGISTRY)), key=lambda t: (-t[0], t[1]))
    if scored[0][0] < FAST_SCORE or scored[1][0] >= FAST_SCORE:
        return None  # nothing clearly owns it, or two agents compete
    reply = scored[0][2].handle(state, member_id, text)
    return (scored[0][2].name, reply) if reply is not None else None


def _finish(state, member_id: str, agent_name: str, reply: str, english: bool) -> str:
    # the transcript keeps the on-screen wording; the returned reply is what a voice reads aloud
    state.say("agent", reply, member_id, agent=agent_name)
    return speakable(reply) if english else reply


def _turn_language(text: str) -> str | None:
    """In multi-language mode, the language this message is in (en, hi, te or kn) from its script; otherwise None."""
    return languages.detect(text) if settings().language_mode == "multi" else None


def converse(state, member_id: str, text: str) -> str:
    _prepare(state, member_id, text)
    cfg = settings()
    lang = _turn_language(text)
    rules_english = not state.speaks_hindi(member_id)  # the rule engine answers in English (or Hinglish in native mode)
    english = rules_english and lang in (None, "en")  # what the model wrote is read as English only when it is

    if cfg.llm_ready:
        # the rule engine's quick answer is for English; Hindi, Telugu and Kannada always go to the model
        fast = None if lang not in (None, "en") else _fast_rule_reply(state, member_id, text, rules_english)
        if fast:
            return _finish(state, member_id, fast[0], fast[1], rules_english)
        try:
            from . import llm

            reply = llm.converse(state, member_id, text, lang=lang)
            state.say("agent", reply, member_id, agent="aangan")
            return speakable(reply) if english else reply
        except Exception as exc:  # LLM unavailable: fall back to the built-in rule engine
            state.log("orchestrator", "llm_fallback", {}, "error", {"error": str(exc)[:200]}, 0)

    # the rule engine matches romanised Hinglish and plain digits; the LLM path reads raw speech itself
    clean = clean_input(normalize(text), state.members)
    agent_name, reply = _rule_reply(state, member_id, clean, text, rules_english)
    return _finish(state, member_id, agent_name, reply, rules_english)


_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")  # the Hindi full stop is the danda


def _sentences(pieces):
    """Group streamed text into whole sentences: speech engines sound right on sentences, and numbers never split."""
    buf = ""
    for piece in pieces:
        buf += piece
        parts = _SENTENCE_END.split(buf)
        for sentence in parts[:-1]:
            if sentence.strip():
                yield sentence.strip()
        buf = parts[-1]
        if len(buf) > 160 and ", " in buf:  # a long run-on: speak up to the last comma
            head, _, tail = buf.rpartition(", ")
            yield head.strip() + ","
            buf = tail
    if buf.strip():
        yield buf.strip()


def _with_filler(gen, after_s: float, filler: str):
    """Pass `gen` through, adding one short filler if nothing has been produced within `after_s` seconds."""
    q: queue.Queue = queue.Queue()

    def pump():
        try:
            for item in gen:
                q.put(("item", item))
            q.put(("end", None))
        except Exception as exc:  # handed to the consumer
            q.put(("error", exc))

    threading.Thread(target=pump, daemon=True).start()
    produced = False
    while True:
        try:
            kind, value = q.get(timeout=None if produced else after_s)
        except queue.Empty:
            produced = True  # one filler at most
            yield filler
            continue
        if kind == "item":
            produced = True
            yield value
        elif kind == "end":
            return
        else:
            raise value


def converse_stream(state, member_id: str, text: str):
    """Yield the reply a sentence at a time, as soon as each sentence is ready (what the voice endpoint streams)."""
    _prepare(state, member_id, text)
    cfg = settings()
    lang = _turn_language(text)
    rules_english = not state.speaks_hindi(member_id)
    english = rules_english and lang in (None, "en")
    holds = set(languages.HOLD.values())

    if cfg.llm_ready:
        fast = None if lang not in (None, "en") else _fast_rule_reply(state, member_id, text, rules_english)
        if fast:
            yield _finish(state, member_id, fast[0], fast[1], rules_english)
            return
        spoken: list[str] = []
        try:
            from . import llm

            filler = languages.HOLD[lang or "en"]
            for sentence in _with_filler(_sentences(llm.stream(state, member_id, text, lang=lang)), FILLER_AFTER_S, filler):
                spoken.append(sentence)
                yield speakable(sentence) if english else sentence
        except Exception as exc:
            state.log("orchestrator", "llm_fallback", {}, "error", {"error": str(exc)[:200]}, 0)
        if spoken:  # the transcript keeps what was said, without the filler
            state.say("agent", " ".join(s for s in spoken if s not in holds), member_id, agent="aangan")
            return  # even after an error: part of the answer is already spoken, so end it rather than repeat

    clean = clean_input(normalize(text), state.members)
    agent_name, reply = _rule_reply(state, member_id, clean, text, rules_english)
    yield _finish(state, member_id, agent_name, reply, rules_english)


def run_trigger(state, agent_name: str, trigger: str) -> str:
    agent = BY_NAME[agent_name]
    state.stage = "before"
    reply = agent.run_trigger(state, trigger)
    last = state.transcript[-1] if state.transcript else None
    if reply and not (last and last["role"] == "agent" and last["text"] == reply):
        state.say("agent", reply, state.persona, agent=agent_name)
    return reply
