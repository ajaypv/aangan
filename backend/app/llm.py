"""LLM brain: one tool-calling loop over every specialist agent's tools. Three providers, first key found wins:
Vercel AI Gateway (Chat Completions, any "provider/model"), OpenAI (Responses API), Anthropic (Messages API).

orchestrator.converse calls converse() when either key is set. Tool names are namespaced
"<agent>__<tool>" so they stay unique across agents.
"""

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import anthropic

from . import languages
from .agents import REGISTRY
from .config import settings
from .toolkit import Tool, ToolError, run_parallel, run_tool

MAX_ITERATIONS = 6
HISTORY_TURNS = 8
MAX_TOKENS = 4096
EFFORT = "medium"  # multistep tool use; drop to "low" if voice latency matters more than planning quality
SEP = "__"

_clients: dict = {}

RULES = """You are Aangan, the voice assistant for one family. Everything you write is spoken aloud.
Style: reply in 1-2 short spoken sentences, in the speaker's language. No markdown, lists, emojis or symbols.
Behaviour:
- Act with your tools instead of describing what you could do.
- Check the calendar before proposing times, and use what the family remembers (allergies, diet, access needs, budgets) without being asked.
- Ask for confirmation only before spending money or booking for several people; otherwise just do it.
- After tools succeed, say exactly what was done. When others are affected, make sure the family is notified.
- Tools take member ids (the [id: ...] after each name below), never names.
- If a tool fails, say so honestly and try the fallback.
- A general question (what a medicine is, why something happens) gets a plain one-sentence answer, then tie it to the family if it helps. For medical advice, say to ask the doctor.
- Prefer a sensible default to a question: a family cab starts at home, a lunch is at midday. Ask only for what you truly cannot assume, such as a time.
- Keep spoken replies short. Give numbers once, in words a person would say.
- Shopping and chores: "we need milk" or "add eggs to the list" goes on the shopping list; "remind Rahul to pay the bill" or "ask Priya to book the plumber" is a task assigned to that person (they are notified); "who is shopping" is assign_shopping. A task is done only when someone says it has ALREADY been done ("I paid the bill"); "Rahul should collect the prescription" or "remind him to" is add_task or assign_task, never complete_task, and when a task like it exists, assign it or move its day instead of adding another. Leave out who did or added something: it defaults to the person speaking. For "plan my day", "what are my priorities" or "what is pending", read get_day_plan or list_tasks first, then say the two or three things that matter most, using what the family remembers."""


def _client_for(api_key: str) -> anthropic.Anthropic:
    if api_key not in _clients:
        _clients[api_key] = anthropic.Anthropic(api_key=api_key)
    return _clients[api_key]


def _tool_index() -> dict[str, tuple]:
    return {f"{agent.name}{SEP}{tool.name}": (agent, tool) for agent in REGISTRY for tool in agent.tools}


def _tool_defs(index: dict[str, tuple]) -> list[dict]:
    return [{"name": key, "description": tool.description, "input_schema": tool.parameters} for key, (_, tool) in index.items()]


def _guarded(tool: Tool) -> Tool:
    """Turn any unexpected exception (bad arguments from the model, bugs) into a ToolError so it is logged and reported."""

    def fn(state, **args):
        try:
            return tool.fn(state, **args)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    return dataclasses.replace(tool, fn=fn)


def build_system(state, member_id: str, lang: str | None = None) -> list[dict]:
    names = {m["id"]: m["name"] for m in state.members}
    roster = "\n".join(
        f"- {m['name']} ({m['relation']}, {m['age']}, speaks {state.reply_language(m['id'])}) [id: {m['id']}]" for m in state.members
    )
    grouped: dict[str, list[str]] = {}
    for fact in state.memory:
        grouped.setdefault(names.get(fact["about"], "Whole family"), []).append(fact["fact"])
    memory = "\n".join(f"- {who}: " + "; ".join(facts) for who, facts in grouped.items())

    speaker = state.member(member_id)
    language = {
        "English": "English",
        "Hindi": "Hindi written in Latin script",
        "Hinglish": "Hinglish (Hindi and English mixed, Latin script)",
    }.get(state.reply_language(member_id), state.reply_language(member_id))  # english mode: English for everyone
    weekday = date.fromisoformat(state.now["date"]).strftime("%A")
    if lang:  # multi-language mode: the language of this message, found from its script, decides the reply
        chosen = languages.LANGUAGES[lang]
        language = (
            f"{chosen.name}. The user's latest message is in {chosen.name}: answer only in {chosen.name}, written in {chosen.script}, "
            f"even if earlier messages used another language, and write numbers, amounts and times as words in {chosen.name}. "
            "Names of people and places may stay as they are"
        )

    return [
        {
            "type": "text",
            "text": f"{RULES}\n\nThe family:\n{roster}\n\nWhat the family remembers:\n{memory}",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"Speaker now: {speaker['name']} ({speaker['relation']}). Reply in {language}.\n"
                f"Now: {weekday} {state.now['date']} {state.now['time']}."
            ),
        },
    ]


def _history(state, member_id: str, text: str) -> list[dict]:
    entries = [t for t in state.transcript if t.get("member_id") == member_id]
    if entries and entries[-1]["role"] == "user" and entries[-1]["text"] == text:
        entries = entries[:-1]  # the orchestrator already logged the current message; we append it ourselves
    messages = [
        {"role": "user" if t["role"] == "user" else "assistant", "content": t["text"]}
        for t in entries[-HISTORY_TURNS:]
    ]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def _text(response) -> str:
    return " ".join(b.text for b in response.content if b.type == "text" and b.text).strip()


def _apology(state, member_id: str, lang: str | None = None) -> str:
    if lang and lang != "en":
        return languages.SORRY[lang]
    if state.speaks_hindi(member_id):
        return "Maaf kijiye, main yeh poora nahi kar paaya. Kripya dobara bolein."
    return "Sorry, I couldn't finish that. Please try again."


def _execute(state, calls: list[tuple]) -> list[tuple[str, dict]]:
    """calls: (agent, tool, args). Single call runs inline, same-agent batches via run_parallel, mixed batches in threads."""
    guarded = [(agent, _guarded(tool), args) for agent, tool, args in calls]
    if len(guarded) == 1:
        agent, tool, args = guarded[0]
        return [run_tool(state, agent.name, tool, args)]
    if len({agent.name for agent, _, _ in guarded}) == 1:
        return run_parallel(state, guarded[0][0].name, [(tool, args) for _, tool, args in guarded])
    with ThreadPoolExecutor(max_workers=len(guarded)) as pool:
        futures = [pool.submit(run_tool, state, agent.name, tool, args) for agent, tool, args in guarded]
        return [f.result() for f in futures]


def _run_tool_blocks(state, index: dict[str, tuple], blocks: list) -> list[dict]:
    results: list[tuple[str, dict] | None] = [None] * len(blocks)
    runnable = []
    for i, block in enumerate(blocks):
        args = dict(block.input or {})
        if block.name in index:
            agent, tool = index[block.name]
            runnable.append((i, agent, tool, args))
        else:
            err = {"error": f"unknown tool {block.name}"}
            state.log("aangan", block.name, args, "error", err, 0)
            results[i] = ("error", err)
    if runnable:
        done = _execute(state, [(agent, tool, args) for _, agent, tool, args in runnable])
        for (i, *_), outcome in zip(runnable, done):
            results[i] = outcome

    out = []
    for block, (status, result) in zip(blocks, results):
        item = {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, ensure_ascii=False, default=str)}
        if status == "error":
            item["is_error"] = True
        out.append(item)
    return out


def _system_text(system: list[dict]) -> str:
    return "\n\n".join(block["text"] for block in system)


def _openai_client(api_key: str):
    if ("openai", api_key) not in _clients:
        from openai import OpenAI

        _clients[("openai", api_key)] = OpenAI(api_key=api_key)
    return _clients[("openai", api_key)]


def _openai_tool_defs(index: dict[str, tuple]) -> list[dict]:
    # strict is off: our JSON schemas are not the strict-mode subset (optional fields, free-form objects)
    return [
        {"type": "function", "name": key, "description": tool.description, "parameters": tool.parameters, "strict": False}
        for key, (_, tool) in index.items()
    ]


def _openai_args(raw) -> dict:
    try:
        value = json.loads(raw) if isinstance(raw, str) and raw.strip() else raw or {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _openai_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()
    parts = [
        c.text
        for item in response.output
        if item.type == "message"
        for c in item.content
        if getattr(c, "type", "") == "output_text" and c.text
    ]
    return " ".join(parts).strip()


def _replay(item) -> dict:
    """An output item as an input item for the next request (the conversation is stateless: store=False)."""
    return item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else dict(item)


def _converse_openai(state, member_id: str, text: str, client=None) -> str:
    cfg = settings()
    client = client or _openai_client(cfg.openai_api_key)
    index = _tool_index()
    tools = _openai_tool_defs(index)
    instructions = _system_text(build_system(state, member_id))
    items: list[dict] = _history(state, member_id, text) + [{"role": "user", "content": text}]

    for _ in range(MAX_ITERATIONS):
        state.stage = "during"
        kwargs = {
            "model": cfg.openai_model,
            "instructions": instructions,
            "input": list(items),
            "max_output_tokens": MAX_TOKENS,
            "store": False,  # family data is not kept at the provider
            "include": ["reasoning.encrypted_content"],  # lets reasoning items be replayed statelessly between tool rounds
        }
        if cfg.openai_reasoning:
            kwargs["reasoning"] = {"effort": cfg.openai_reasoning}
        if tools:
            kwargs["tools"] = tools
        response = client.responses.create(**kwargs)

        calls = [o for o in response.output if o.type == "function_call"]
        if not calls:
            return _openai_text(response) or _apology(state, member_id)

        items.extend(_replay(o) for o in response.output)
        blocks = [SimpleNamespace(id=c.call_id, name=c.name, input=_openai_args(c.arguments)) for c in calls]
        for result in _run_tool_blocks(state, index, blocks):
            # a failed tool's content is already {"error": ...}, which is how the model learns it failed
            items.append({"type": "function_call_output", "call_id": result["tool_use_id"], "output": result["content"]})

    return _apology(state, member_id)


def _chat_args(raw) -> dict:
    return _openai_args(raw)


# What the voice says while the first tool runs, when the model went straight to the tool without a word.
LEAD_INS = {
    "calendar": "Let me check the calendar.",
    "dining": "Let me look at the options.",
    "travel": "Let me check that for you.",
    "money": "Let me check the numbers.",
    "school": "Let me check on that.",
    "care": "Let me check on that.",
    "household": "Let me look that up.",
}
DEFAULT_LEAD_IN = "One moment."
CORE_AGENTS = ("calendar", "household")  # always offered: most requests touch the schedule or what the family remembers


def _pick_index(state, text: str, index: dict[str, tuple]) -> dict[str, tuple]:
    """Offer the model the tools of the agents the request is about (plus the core ones), not all 50: a shorter
    request is faster and the model chooses better. When nothing stands out, every tool is offered."""
    agents = {agent.name: agent for agent, _ in index.values()}
    if not all(hasattr(a, "score") for a in agents.values()):
        return index
    from .normalize import normalize
    from .speech import clean_input

    cleaned = clean_input(normalize(text), state.members)
    scored = sorted(((a.score(state, cleaned), name) for name, a in agents.items()), reverse=True)
    top = [name for score, name in scored[:3] if score > 0]
    if not top:
        return index
    keep = set(top) | set(CORE_AGENTS)
    return {key: value for key, value in index.items() if value[0].name in keep}


def _gateway_stream(state, member_id: str, text: str, client=None, lead_in: bool = True, lang: str | None = None):
    """Chat Completions through Vercel AI Gateway, streamed: text is yielded the moment the model produces it, tool
    calls are collected and run, and the loop continues until the model answers in words.

    With `lead_in`, a model that goes straight to a tool without saying anything gets a short spoken sentence, so
    the voice is never silent while the tool runs."""
    from .gateway import gateway_client, open_stream

    cfg = settings()
    client = client or gateway_client(cfg.ai_gateway_api_key)
    full_index = _tool_index()
    index = _pick_index(state, text, full_index)
    tools = [
        {"type": "function", "function": {"name": key, "description": tool.description, "parameters": tool.parameters}}
        for key, (_, tool) in index.items()
    ]
    messages: list[dict] = [{"role": "system", "content": _system_text(build_system(state, member_id, lang))}]
    messages += _history(state, member_id, text) + [{"role": "user", "content": text}]
    spoke, tail, led = False, "", False
    indic = bool(lang and lang != "en")
    model = cfg.ai_gateway_model_indic if indic else cfg.ai_gateway_model_name  # Hindi, Telugu, Kannada: the model that writes them well
    reasoning = cfg.openai_reasoning if not indic else ""  # reasoning effort is an OpenAI setting; the Indic model does not take it

    for round_no in range(MAX_ITERATIONS):
        state.stage = "during"
        kwargs = {"model": model, "messages": list(messages), "max_tokens": MAX_TOKENS, "stream": True}
        if reasoning:
            kwargs["reasoning_effort"] = reasoning
        if tools:
            kwargs["tools"] = tools

        content = ""
        calls: dict[int, dict] = {}
        for chunk in open_stream(client, kwargs, indic=indic):
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                piece = delta.content
                if round_no and not content and spoke:  # a new round continues the same spoken answer
                    piece = piece.lstrip() if tail.endswith(" ") else (piece if piece.startswith(" ") else " " + piece)
                content += delta.content
                spoke = True
                tail = piece or tail
                yield piece
            for tc in delta.tool_calls or []:
                # some models (Gemini) send no index: a chunk with a new id starts a call, one without continues the last
                key = tc.index if tc.index is not None else (len(calls) - 1 if calls and not tc.id else len(calls))
                slot = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
                slot["id"] = tc.id or slot["id"]
                if tc.function:
                    slot["name"] += tc.function.name or ""
                    slot["arguments"] += tc.function.arguments or ""
                if lead_in and not led and not content.strip() and not round_no and slot["name"]:
                    # the model chose a tool: speak now, while it is still writing the arguments and the tool runs
                    led = True
                    tail = (languages.LOOKING[lang] if indic else LEAD_INS.get(slot["name"].split(SEP)[0], DEFAULT_LEAD_IN)) + " "
                    spoke = True
                    yield tail

        if not calls:
            if not content.strip():  # nothing said in words (a lead-in does not count): never leave the caller in silence
                yield (" " if spoke else "") + _apology(state, member_id, lang)
            return

        ordered = [calls[i] for i in sorted(calls)]
        for n, call in enumerate(ordered):
            call["id"] = call["id"] or f"call_{round_no}_{n}"
        messages.append(
            {
                "role": "assistant",
                "content": content or "",  # an empty string, never null: Cloudflare's Workers AI rejects a null content
                "tool_calls": [
                    {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in ordered
                ],
            }
        )
        blocks = [SimpleNamespace(id=c["id"], name=c["name"], input=_chat_args(c["arguments"])) for c in ordered]
        for result in _run_tool_blocks(state, full_index, blocks):
            messages.append({"role": "tool", "tool_call_id": result["tool_use_id"], "content": result["content"]})

    yield ("" if not spoke else " ") + _apology(state, member_id, lang)


def _converse_gateway(state, member_id: str, text: str, client=None, lang: str | None = None) -> str:
    return "".join(_gateway_stream(state, member_id, text, client, lead_in=False, lang=lang)).strip()


def stream(state, member_id: str, text: str, lang: str | None = None):
    """The reply as text pieces, as they are produced. Only the gateway provider streams; the others yield the whole reply."""
    if settings().llm_provider == "gateway":
        yield from _gateway_stream(state, member_id, text, lang=lang)
    else:
        yield converse(state, member_id, text, lang=lang)


def converse(state, member_id: str, text: str, client=None, provider: str | None = None, lang: str | None = None) -> str:
    cfg = settings()
    provider = provider or cfg.llm_provider or "anthropic"
    if provider == "gateway":
        return _converse_gateway(state, member_id, text, client, lang)
    if provider == "openai":
        return _converse_openai(state, member_id, text, client)
    return _converse_anthropic(state, member_id, text, client)


def _converse_anthropic(state, member_id: str, text: str, client=None) -> str:
    cfg = settings()
    client = client or _client_for(cfg.anthropic_api_key)
    index = _tool_index()
    tools = _tool_defs(index)
    system = build_system(state, member_id)
    messages = _history(state, member_id, text) + [{"role": "user", "content": text}]

    for _ in range(MAX_ITERATIONS):
        state.stage = "during"
        kwargs = {
            "model": cfg.llm_model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": messages,
            "output_config": {"effort": EFFORT},
        }
        if tools:
            kwargs["tools"] = tools
        response = client.messages.create(**kwargs)

        if response.stop_reason == "refusal":
            return _apology(state, member_id)
        blocks = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not blocks:
            return _text(response) or _apology(state, member_id)

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": _run_tool_blocks(state, index, blocks)})

    return _apology(state, member_id)
