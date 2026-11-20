import json
from types import SimpleNamespace

import pytest

from app import llm
from app.state import FamilyState
from app.toolkit import Tool, ToolError

OBJ = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic; records every messages.create call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        return item


def text(t, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=t)], stop_reason=stop)


def tool_use(*calls):
    blocks = [SimpleNamespace(type="tool_use", id=f"tu{i}", name=name, input=args) for i, (name, args) in enumerate(calls)]
    return SimpleNamespace(content=blocks, stop_reason="tool_use")


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agents(monkeypatch):
    def search(state, q):
        return {"found": q}

    def boom(state, q):
        raise ToolError("supplier down")

    def strict(state, q):
        return {"ok": True}

    travel = SimpleNamespace(name="travel", tools=[Tool("search", "Search flights", OBJ, search), Tool("boom", "Always fails", OBJ, boom)])
    dining = SimpleNamespace(name="dining", tools=[Tool("find", "Find restaurants", OBJ, strict)])
    monkeypatch.setattr(llm, "REGISTRY", [travel, dining])
    return [travel, dining]


def test_plain_reply_without_tools(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    client = FakeClient([text("Namaste! How can I help?")])
    reply = llm.converse(state, "priya", "hello", client=client)
    assert reply == "Namaste! How can I help?"
    call = client.calls[0]
    assert "tools" not in call
    assert call["model"] == "claude-sonnet-5-5" and call["output_config"] == {"effort": llm.EFFORT}
    assert call["messages"] == [{"role": "user", "content": "hello"}]


def test_tool_turn_runs_tool_and_logs_under_agent(state, agents):
    client = FakeClient([tool_use(("travel__search", {"q": "goa"})), text("Found flights to Goa.")])
    reply = llm.converse(state, "rahul", "find flights", client=client)
    assert reply == "Found flights to Goa."

    assert [(e["agent"], e["tool"], e["status"]) for e in state.events] == [("travel", "search", "ok")]
    assert state.events[0]["result"] == {"found": "goa"}
    names = [t["name"] for t in client.calls[0]["tools"]]
    assert names == ["travel__search", "travel__boom", "dining__find"]
    second = client.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-1]["role"] == "user"
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu0" and "is_error" not in result
    assert '"found": "goa"' in result["content"]


def test_failing_bad_and_unknown_tools_produce_is_error(state, agents):
    client = FakeClient(
        [
            tool_use(("travel__boom", {"q": "x"}), ("dining__find", {}), ("nope__tool", {"q": "x"})),
            text("Something failed; I tried the fallback."),
        ]
    )
    reply = llm.converse(state, "priya", "go", client=client)
    assert "fallback" in reply
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu0", "tu1", "tu2"]  # order preserved, one user message
    assert all(r["is_error"] for r in results)
    assert "supplier down" in results[0]["content"]
    assert "TypeError" in results[1]["content"]  # missing argument turned into a tool error, not a crash
    assert "unknown tool" in results[2]["content"]
    statuses = {(e["agent"], e["tool"]): e["status"] for e in state.events}
    assert statuses == {("travel", "boom"): "error", ("dining", "find"): "error", ("aangan", "nope__tool"): "error"}


def test_parallel_calls_across_agents_return_in_order(state, agents):
    client = FakeClient([tool_use(("travel__search", {"q": "a"}), ("dining__find", {"q": "b"})), text("Both done.")])
    assert llm.converse(state, "priya", "do both", client=client) == "Both done."
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu0", "tu1"]
    assert {e["agent"] for e in state.events} == {"travel", "dining"}


def test_iteration_cap(state, agents):
    client = FakeClient([tool_use(("travel__search", {"q": "again"}))])
    reply = llm.converse(state, "rahul", "loop forever", client=client)
    assert len(client.calls) == llm.MAX_ITERATIONS == 6
    assert len(state.events) == 6
    assert "couldn't finish" in reply


def test_empty_text_and_refusal_fall_back_to_apology(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    empty = SimpleNamespace(content=[], stop_reason="end_turn")
    assert "Sorry" in llm.converse(state, "rahul", "hi", client=FakeClient([empty]))
    refused = SimpleNamespace(content=[], stop_reason="refusal")
    assert "Maaf" in llm.converse(state, "dadi", "hi", client=FakeClient([refused]))


def test_system_prompt_and_history(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    for i in range(6):
        state.say("user", f"priya question {i}", "priya")
        state.say("agent", f"priya answer {i}", "priya", agent="dining")
    state.say("user", "aarav secret chatter", "aarav")
    state.say("user", "book lunch", "priya")  # the current message, already logged by the orchestrator

    client = FakeClient([text("ok")])
    llm.converse(state, "priya", "book lunch", client=client)
    call = client.calls[0]

    static, dynamic = call["system"]
    assert static["cache_control"] == {"type": "ephemeral"} and "cache_control" not in dynamic
    for name in ("Priya", "Rahul", "Aarav", "Dadi"):
        assert name in static["text"]
    assert "Severe peanut allergy" in static["text"] and "Pure vegetarian" in static["text"]
    assert "Whole family" in static["text"] and "Sunday is family day" in static["text"]
    assert "Priya (Mom)" in dynamic["text"] and "Hinglish" in dynamic["text"] and "Friday 2026-11-20 07:30" in dynamic["text"]

    msgs = call["messages"]
    assert msgs[-1] == {"role": "user", "content": "book lunch"}
    history = msgs[:-1]
    assert len(history) == llm.HISTORY_TURNS == 8
    assert history[0]["role"] == "user" and history[-1] == {"role": "assistant", "content": "priya answer 5"}
    assert not any("aarav" in m["content"] for m in msgs)
    assert sum(1 for m in msgs if m["content"] == "book lunch") == 1


def test_english_mode_makes_every_speaker_english(state, monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    monkeypatch.setattr(llm, "REGISTRY", [])
    for member in ("dadi", "aarav", "priya", "rahul"):
        client = FakeClient([text("ok")])
        llm.converse(state, member, "hello", client=client)
        system = client.calls[0]["system"]
        assert "Reply in English." in system[1]["text"]
        assert "Hindi" not in system[1]["text"] and "Hinglish" not in system[1]["text"]
        assert "speaks Hindi" not in system[0]["text"] and "speaks Hinglish" not in system[0]["text"]
        assert "Dadi (Grandmother, 72, speaks English)" in system[0]["text"]


def test_speaker_language_in_system_prompt(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    client = FakeClient([text("ok")])
    llm.converse(state, "dadi", "namaste", client=client)
    assert "Hindi written in Latin script" in client.calls[0]["system"][1]["text"]
    client = FakeClient([text("ok")])
    llm.converse(state, "rahul", "hello", client=client)
    assert "Reply in English" in client.calls[0]["system"][1]["text"]


# ---- OpenAI Responses brain ----


class FakeResponses:
    """Scripted stand-in for openai.OpenAI().responses; records every create call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


class Item(SimpleNamespace):
    def model_dump(self, exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def message(t):
    return SimpleNamespace(output=[Item(type="message", content=[SimpleNamespace(type="output_text", text=t)])], output_text=t)


def fn_calls(*calls):
    out = [
        Item(type="function_call", call_id=f"call{i}", name=name, arguments=args if isinstance(args, str) else json.dumps(args))
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(output=out, output_text="")


def test_openai_plain_reply_settings_and_history(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    state.say("user", "earlier", "priya")
    state.say("agent", "earlier answer", "priya", agent="dining")
    client = FakeResponses([message("Hello Priya.")])
    assert llm.converse(state, "priya", "hello", client=client, provider="openai") == "Hello Priya."
    call = client.calls[0]
    assert call["model"] == "gpt-6-luna" and call["store"] is False and "tools" not in call and "reasoning" not in call
    assert call["include"] == ["reasoning.encrypted_content"]
    assert "You are Aangan" in call["instructions"] and "Severe peanut allergy" in call["instructions"] and "Speaker now: Priya" in call["instructions"]
    assert call["input"][-1] == {"role": "user", "content": "hello"} and call["input"][0]["role"] == "user"


def test_openai_tool_round_trip(state, agents):
    client = FakeResponses([fn_calls(("travel__search", {"q": "goa"})), message("Found flights to Goa.")])
    assert llm.converse(state, "rahul", "find flights", client=client, provider="openai") == "Found flights to Goa."
    tools = client.calls[0]["tools"]
    assert [t["name"] for t in tools] == ["travel__search", "travel__boom", "dining__find"]
    assert all(t["type"] == "function" and t["strict"] is False and t["parameters"] == OBJ for t in tools)
    second = client.calls[1]["input"]
    assert second[-2]["type"] == "function_call" and second[-2]["call_id"] == "call0"
    assert second[-1]["type"] == "function_call_output" and second[-1]["call_id"] == "call0"
    assert '"found": "goa"' in second[-1]["output"]
    assert [(e["agent"], e["tool"], e["status"]) for e in state.events] == [("travel", "search", "ok")]


def test_openai_failures_and_bad_arguments_reach_the_model(state, agents):
    client = FakeResponses([fn_calls(("travel__boom", {"q": "x"}), ("dining__find", "{not json"), ("nope__tool", {})), message("Fallback.")])
    assert llm.converse(state, "priya", "go", client=client, provider="openai") == "Fallback."
    outputs = [i for i in client.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert [o["call_id"] for o in outputs] == ["call0", "call1", "call2"]
    assert "supplier down" in outputs[0]["output"] and "TypeError" in outputs[1]["output"] and "unknown tool" in outputs[2]["output"]


def test_openai_iteration_cap_and_empty_reply(state, agents, monkeypatch):
    client = FakeResponses([fn_calls(("travel__search", {"q": "again"}))])
    assert "couldn't finish" in llm.converse(state, "rahul", "loop", client=client, provider="openai")
    assert len(client.calls) == llm.MAX_ITERATIONS
    monkeypatch.setattr(llm, "REGISTRY", [])
    empty = SimpleNamespace(output=[], output_text="")
    assert "Sorry" in llm.converse(state, "rahul", "hi", client=FakeResponses([empty]), provider="openai")


def test_openai_reasoning_effort_is_opt_in(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    monkeypatch.setenv("OPENAI_REASONING", "low")
    client = FakeResponses([message("ok")])
    llm.converse(state, "rahul", "hi", client=client, provider="openai")
    assert client.calls[0]["reasoning"] == {"effort": "low"}


def test_provider_follows_the_configured_key(monkeypatch):
    from app.config import settings

    assert settings().llm_provider == "" and not settings().llm_ready
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert settings().llm_provider == "anthropic"
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert settings().llm_provider == "openai" and settings().llm_model_name == "gpt-6-luna"
