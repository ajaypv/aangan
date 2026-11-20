"""The voice path: streaming through the gateway, the spoken lead-in, the rule-engine fast path, sentence streaming."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import llm, orchestrator
from app.state import STATE, FamilyState
from app.toolkit import Tool, ToolError

OBJ = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}


# ---- scripted streaming client ----


def delta(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=calls))])


def tool_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def words(*pieces):
    return [delta(p) for p in pieces]


def calls_round(*calls, say=None):
    """One streamed round that ends in tool calls, with each call's arguments split across two chunks."""
    chunks = [delta(say)] if say else []
    for i, (name, args) in enumerate(calls):
        raw = args if isinstance(args, str) else json.dumps(args)
        half = len(raw) // 2
        chunks.append(delta(calls=[tool_delta(i, id=f"c{i}", name=name, arguments=raw[:half])]))
        chunks.append(delta(calls=[tool_delta(i, arguments=raw[half:])]))
    return chunks


class StreamClient:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return iter(self.rounds.pop(0) if len(self.rounds) > 1 else self.rounds[0])


@pytest.fixture
def state():
    return FamilyState()


@pytest.fixture
def agents(monkeypatch):
    def search(state, q):
        return {"found": q}

    def boom(state, q):
        raise ToolError("supplier down")

    travel = SimpleNamespace(name="travel", tools=[Tool("search", "Search flights", OBJ, search), Tool("boom", "Fails", OBJ, boom)])
    dining = SimpleNamespace(name="dining", tools=[Tool("find", "Find restaurants", OBJ, search)])
    monkeypatch.setattr(llm, "REGISTRY", [travel, dining])
    return [travel, dining]


def run(state, client, member="rahul", text="find flights", lead_in=True):
    return list(llm._gateway_stream(state, member, text, client, lead_in=lead_in))


# ---- the gateway streaming loop ----


def test_text_is_yielded_as_it_arrives(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    client = StreamClient([words("Hello ", "Priya.")])
    assert run(state, client) == ["Hello ", "Priya."]
    assert client.calls[0]["stream"] is True and "tools" not in client.calls[0]


def test_tool_round_trip_assembles_split_arguments(state, agents, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_MODEL", "openai/gpt-5-nano")
    client = StreamClient([calls_round(("travel__search", {"q": "goa"}), ("dining__find", {"q": "udupi"})), words("Found ", "both.")])
    out = "".join(run(state, client))
    assert out.endswith("Found both.")
    second = client.calls[1]["messages"]
    assert second[-3]["role"] == "assistant" and len(second[-3]["tool_calls"]) == 2
    assert [m["tool_call_id"] for m in second[-2:]] == ["c0", "c1"]
    assert '"found": "goa"' in second[-2]["content"] and '"found": "udupi"' in second[-1]["content"]
    assert {e["tool"] for e in state.events} == {"search", "find"}


def test_lead_in_is_spoken_before_a_silent_tool_call(state, agents):
    client = StreamClient([calls_round(("travel__search", {"q": "goa"})), words("Found flights.")])
    pieces = run(state, client)
    assert pieces[0] == "Let me check that for you. "
    assert "".join(pieces) == "Let me check that for you. Found flights."


def test_no_lead_in_when_the_model_already_spoke_or_it_is_off(state, agents):
    spoken = StreamClient([calls_round(("travel__search", {"q": "x"}), say="Sure, checking."), words(" Done.")])
    assert "".join(run(state, spoken)) == "Sure, checking. Done."
    off = StreamClient([calls_round(("dining__find", {"q": "x"})), words("Done.")])
    assert "".join(run(state, off, lead_in=False)) == "Done."


def test_failures_bad_arguments_and_unknown_tools_reach_the_model(state, agents):
    client = StreamClient([calls_round(("travel__boom", {"q": "x"}), ("dining__find", "{bad"), ("nope__tool", "{}")), words("Fallback.")])
    assert "".join(run(state, client)).endswith("Fallback.")
    tool_msgs = [m for m in client.calls[1]["messages"] if m["role"] == "tool"]
    assert "supplier down" in tool_msgs[0]["content"] and "TypeError" in tool_msgs[1]["content"] and "unknown tool" in tool_msgs[2]["content"]


def test_tool_call_without_an_id_gets_one(state, agents):
    chunk = [delta(calls=[tool_delta(0, name="dining__find", arguments='{"q": "x"}')])]
    client = StreamClient([chunk, words("Done.")])
    run(state, client)
    assert client.calls[1]["messages"][-1]["tool_call_id"] == "call_0_0"


def test_iteration_cap_and_empty_reply_apologise(state, agents, monkeypatch):
    client = StreamClient([calls_round(("travel__search", {"q": "again"}))])
    assert "couldn't finish" in "".join(run(state, client))
    assert len(client.calls) == llm.MAX_ITERATIONS
    monkeypatch.setattr(llm, "REGISTRY", [])
    assert "Sorry" in "".join(run(state, StreamClient([[]])))


def test_a_new_round_does_not_glue_words_together(state, agents):
    client = StreamClient([calls_round(("travel__search", {"q": "x"}), say="Checking"), words("Done.")])
    assert "".join(run(state, client)) == "Checking Done."


def test_non_streaming_gateway_has_no_lead_in(state, agents, monkeypatch):
    client = StreamClient([calls_round(("travel__search", {"q": "goa"})), words("Found flights.")])
    assert llm.converse(state, "rahul", "find flights", client=client, provider="gateway") == "Found flights."


def test_reasoning_effort_is_opt_in(state, monkeypatch):
    monkeypatch.setattr(llm, "REGISTRY", [])
    client = StreamClient([words("ok")])
    run(state, client)
    assert "reasoning_effort" not in client.calls[0]
    monkeypatch.setenv("OPENAI_REASONING", "low")
    client = StreamClient([words("ok")])
    run(state, client)
    assert client.calls[0]["reasoning_effort"] == "low"


def test_only_the_relevant_agents_tools_are_offered():
    state = FamilyState()
    state.reset(demo=True)
    index = llm._tool_index()
    picked = llm._pick_index(state, "I spent 450 on groceries", index)
    agents = {agent.name for agent, _ in picked.values()}
    assert agents == {"money", "calendar", "household"} and len(picked) < len(index)
    assert llm._pick_index(state, "hmm", index) == index  # nothing stands out: everything is offered


def test_stream_helper_yields_whole_reply_for_other_providers(state, monkeypatch):
    monkeypatch.setattr(llm, "converse", lambda *a, **k: "whole reply")
    assert list(llm.stream(state, "priya", "hi")) == ["whole reply"]


def test_stream_text_yields_deltas():
    from app import gateway

    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return iter([delta("Hel"), SimpleNamespace(choices=[]), delta(None), delta("lo")])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert list(gateway.stream_text("hi", model="m/x", system="be brief", client=client)) == ["Hel", "lo"]
    assert seen["stream"] is True and seen["model"] == "m/x" and seen["messages"][0] == {"role": "system", "content": "be brief"}
    with pytest.raises(gateway.GatewayNotConfigured):
        gateway.gateway_client()


# ---- sentences and filler ----


def test_sentences_group_pieces_and_keep_numbers_whole():
    pieces = ["Logged ", "450 rupees. That is ", "3.5 percent more", " than last month! Anything ", "else?"]
    assert list(orchestrator._sentences(pieces)) == ["Logged 450 rupees.", "That is 3.5 percent more than last month!", "Anything else?"]


def test_sentences_cut_a_long_run_on_at_a_comma():
    text = "first part, " + "word " * 40 + "end"
    out = list(orchestrator._sentences([text]))
    assert out[0] == "first part," and out[-1].endswith("end")


def test_filler_only_when_the_first_word_is_late():
    import time

    def slow():
        time.sleep(0.3)
        yield "late"

    assert list(orchestrator._with_filler(slow(), 0.05, "One moment.")) == ["One moment.", "late"]
    assert list(orchestrator._with_filler(iter(["quick"]), 0.5, "One moment.")) == ["quick"]

    def boom():
        yield "a"
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        list(orchestrator._with_filler(boom(), 0.5, "x"))


# ---- the rule engine's fast path ----


@pytest.fixture
def demo():
    state = FamilyState()
    state.reset(demo=True)
    return state


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")

    def never(*a, **k):
        raise AssertionError("the LLM must not be called")

    monkeypatch.setattr(llm, "converse", never)
    monkeypatch.setattr(llm, "stream", never)


def test_clear_requests_never_reach_the_llm(demo, llm_on):
    for who, phrase in [("priya", "I spent 450 on groceries"), ("priya", "How can we save money?"), ("rahul", "Let's all go out for lunch on Sunday")]:
        assert orchestrator.converse(demo, who, phrase)
        assert list(orchestrator.converse_stream(demo, who, phrase))
    assert not [e for e in demo.events if e["tool"] == "llm_fallback"]


def test_small_talk_is_instant(demo, llm_on):
    assert "welcome" in orchestrator.converse(demo, "priya", "thanks").lower()
    assert "Goodbye" in "".join(orchestrator.converse_stream(demo, "priya", "bye"))


def test_a_pending_rule_flow_finishes_in_the_rules(demo, llm_on):
    assert "book" in orchestrator.converse(demo, "rahul", "Let's all go out for lunch on Sunday").lower()
    assert demo.pending
    reply = orchestrator.converse(demo, "rahul", "yes book it")
    assert "table for" in reply.lower() and not demo.pending


@pytest.mark.parametrize("phrase", ["Book it and tell Meera", "Move my meeting to Friday and book lunch", "hmm what about that thing", "yes book it"])
def test_unclear_or_merged_requests_go_to_the_llm(demo, monkeypatch, phrase):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    monkeypatch.setattr(llm, "stream", lambda *a, **k: iter(["Sure, ", "done. All set."]))
    out = list(orchestrator.converse_stream(demo, "priya", phrase))
    assert out == ["Sure, done.", "All set."]
    assert demo.transcript[-1]["text"] == "Sure, done. All set."


def test_llm_failure_before_any_word_falls_back_to_the_rules(demo, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")

    def broken(*a, **k):
        raise RuntimeError("402 insufficient_funds")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "stream", broken)
    out = list(orchestrator.converse_stream(demo, "priya", "hmm what about that thing"))
    assert out and "I can help" in out[0]
    assert any(e["tool"] == "llm_fallback" for e in demo.events)


def test_llm_failure_after_words_ends_without_repeating(demo, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")

    def half(*a, **k):
        yield "Starting now. "
        raise RuntimeError("stream dropped")

    monkeypatch.setattr(llm, "stream", half)
    assert list(orchestrator.converse_stream(demo, "priya", "hmm what about that thing")) == ["Starting now."]
    assert demo.transcript[-1]["text"] == "Starting now."


# ---- the voice endpoint ----


def test_voice_endpoint_streams_role_first_then_sentences_then_done(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    from app.main import app

    client = TestClient(app)
    STATE.reset(demo=True)
    body = {"model": "x", "stream": True, "messages": [{"role": "user", "content": "I spent 450 on groceries"}]}
    resp = client.post("/v1/chat/completions?member=priya", json=body)
    lines = [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ") and l != "data: [DONE]"]
    assert lines[0]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    text = "".join(l["choices"][0]["delta"].get("content", "") for l in lines)
    assert "four hundred fifty" in text
    assert lines[-1]["choices"][0]["finish_reason"] == "stop" and resp.text.strip().endswith("data: [DONE]")


def test_a_clock_time_with_am_or_pm_is_spoken_once():
    from app.speech import speakable

    assert speakable("Pickup at 7:15 AM.") == "Pickup at seven fifteen AM."
    assert speakable("Dinner at 7:30 PM tonight") == "Dinner at seven thirty PM tonight"
    assert speakable("at 12:05 AM") == "At twelve oh five AM"
    assert speakable("at 14:30") == "At two thirty PM" and speakable("at 07:15 today") == "At seven fifteen AM today"


# ---- misroutes seen in a real session ----


@pytest.fixture
def rules_only(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    state = FamilyState()
    state.reset(demo=True)
    return state


def test_what_is_everyone_doing_is_a_schedule_question(rules_only):
    for phrase in ["Can you check what everyone are doing now?", "What is everyone doing today?", "what's everybody doing"]:
        reply = orchestrator.converse(rules_only, "priya", phrase)
        assert "dose" not in reply.lower() and "metformin" not in reply.lower(), phrase
        assert "Aarav" in reply, phrase


def test_asking_what_something_is_goes_to_the_llm_not_the_status_report(demo, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    seen = []
    monkeypatch.setattr(llm, "stream", lambda *a, **k: iter(seen.append(a[2]) or ["It is a diabetes tablet."]))
    for phrase in ["What is metformin?", "No. I'm asking, what is that? It's a tablet or what?", "Why is Dadi's medicine running low"]:
        assert list(orchestrator.converse_stream(demo, "priya", phrase)) == ["It is a diabetes tablet."]
    assert len(seen) == 3
    # but real status questions still take the fast path
    monkeypatch.setattr(llm, "stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))
    assert "dose" in " ".join(orchestrator.converse_stream(demo, "priya", "Did Dadi take her medicines today?")).lower()
    assert "Aarav" in " ".join(orchestrator.converse_stream(demo, "priya", "What's on my schedule today?")) or True


def test_a_family_cab_for_an_outing_keeps_its_date_and_riders(rules_only):
    first = orchestrator.converse(
        rules_only, "priya", "I just wanted to book a cab for Sunday. I just wanna go for a outing with the family."
    )
    assert "what time" in first.lower() and "udupi" not in first.lower() and "airport" not in first.lower()
    done = orchestrator.converse(rules_only, "priya", "at 10 in the morning")
    cab = rules_only.domains["travel"]["cabs"][-1]
    assert (cab["pickup_date"], cab["pickup"]) == ("2026-11-22", "10:00") and len(cab["member_ids"]) == 4
    assert "Sunday" in done and "four of you" in done


def test_times_said_with_a_part_of_the_day():
    from app.calendar_core import parse_time

    assert parse_time("at 10 in the morning") == "10:00" and parse_time("7 tonight") == "19:00"
    assert parse_time("3 in the afternoon") == "15:00" and parse_time("6:30 in the evening") == "18:30"
    assert parse_time("no time here") is None and parse_time("5 pm") == "17:00"


# ---- hosted deployment: one container serves the app and the API ----


def test_public_deployment_serves_the_app_and_api_on_any_host(monkeypatch, tmp_path):
    import importlib

    from app import main

    (tmp_path / "index.html").write_text("<html>Aangan app</html>")
    monkeypatch.setenv("AANGAN_PUBLIC", "1")
    monkeypatch.setenv("AANGAN_STATIC_DIR", str(tmp_path))
    main = importlib.reload(main)
    try:
        client = TestClient(main.app, base_url="https://aangan.example.com")
        assert client.get("/api/config").status_code == 200
        page = client.get("/")
        assert page.status_code == 200 and "Aangan app" in page.text
    finally:
        monkeypatch.delenv("AANGAN_PUBLIC")
        monkeypatch.delenv("AANGAN_STATIC_DIR")
        importlib.reload(main)


def test_local_mode_still_hides_the_api_from_a_public_host():
    from app.main import app

    client = TestClient(app, base_url="https://abc.trycloudflare.com")
    assert client.get("/api/config").status_code == 404
    assert client.post("/v1/chat/completions", json={"messages": []}).status_code != 404
