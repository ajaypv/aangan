"""English, Hindi, Telugu and Kannada: detection, the voice, the model's language, and the voice endpoint's first chunk."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import agora, config, languages, llm, orchestrator, persistence, voices
from app.state import STATE, FamilyState

TELUGU = "రేపు నాకు ఏం ఉంది? ఆదివారం అందరం భోజనానికి వెళ్దామా?"
KANNADA = "ನಾಳೆ ನನಗೆ ಏನಿದೆ? ಭಾನುವಾರ ಎಲ್ಲರೂ ಊಟಕ್ಕೆ ಹೋಗೋಣವೇ?"
HINDI = "कल मेरा क्या प्लान है? रविवार को सब मिलकर लंच पर चलें?"


@pytest.fixture
def multi(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "multi")


@pytest.fixture
def demo():
    state = FamilyState()
    state.reset(demo=True)
    return state


# ---- detecting the language ----


@pytest.mark.parametrize(
    "text,expected",
    [
        (TELUGU, "te"), (KANNADA, "kn"), (HINDI, "hi"),
        ("Is everyone free on Sunday?", "en"), ("I spent 450 on groceries", "en"), ("kal kya plan hai", "en"),
        ("", "en"), ("450", "en"), ("book a table for Aarav 7 pm తెలుగు", "en"),  # a word of Telugu in English stays English
        ("Priya ఆదివారం మధ్యాహ్నం భోజనానికి వెళ్దాం", "te"),  # a name in Latin letters does not hide a Telugu sentence
    ],
)
def test_detect_reads_the_script(text, expected):
    assert languages.detect(text) == expected


def test_a_member_s_language_maps_to_one_of_the_four():
    assert languages.for_member("Telugu").code == "te" and languages.for_member("Kannada").code == "kn"
    assert languages.for_member("Hindi").code == "hi" and languages.for_member("Hinglish").code == "hi"
    assert languages.for_member("English").code == "en" and languages.for_member(None).code == "en"


def test_every_language_has_every_phrase():
    for table in (languages.HOLD, languages.LOOKING, languages.SORRY, languages.GREETING, languages.FAILURE):
        assert set(table) == set(languages.LANGUAGES)
    assert "{name}" in languages.GREETING["te"] and languages.tts_params("kn", "male") == {"voiceId": "hi-IN-pranav", "locale": "kn-IN"}


# ---- the call and the voice ----


def test_multi_mode_listens_for_all_four_and_uses_one_multi_native_voice(multi, demo):
    dadi, priya = demo.member("dadi"), demo.member("priya")
    assert voices.asr_language(dadi) == "multi"
    v = voices.voice_for(dadi)
    assert v["voice_id"] == "hi-IN-rachna" and v["locale"] == "hi-IN"  # the call opens in her own language
    telugu = dict(priya, language="Telugu")
    assert voices.voice_for(telugu)["locale"] == "te-IN" and voices.voice_for(dict(priya, language="Kannada"))["locale"] == "kn-IN"
    assert voices.voice_for(dict(demo.member("rahul"), gender="male"))["voice_id"] == "hi-IN-pranav"


def test_the_call_opens_with_a_greeting_in_the_members_language(multi, demo):
    demo.member("priya")["language"] = "Telugu"
    assert "నమస్కారం Priya" in agora.greeting_for(demo, "priya")
    assert agora.failure_message_for(demo, "priya") == languages.FAILURE["te"]
    demo.member("dadi")["language"] = "Kannada"
    assert "ನಮಸ್ಕಾರ Dadi" in agora.greeting_for(demo, "dadi")


def test_other_modes_are_unchanged(monkeypatch, demo):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    assert voices.asr_language(demo.member("dadi")) == "en-IN" and voices.voice_for(demo.member("dadi"))["locale"] == "en-IN"
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    assert voices.asr_language(demo.member("dadi")) == "hi"


def test_a_garbage_mode_means_multi(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "klingon")
    assert config.settings().language_mode == "multi"
    monkeypatch.delenv("AANGAN_LANGUAGE_MODE")
    assert config.settings().language_mode == "multi"  # the default


# ---- what the model is told, and which model ----


def test_the_system_prompt_names_the_language_to_answer_in(multi, demo):
    system = llm.build_system(demo, "priya", "te")
    dynamic = system[1]["text"]
    assert "Telugu" in dynamic and "Telugu script" in dynamic and "even if earlier messages used another language" in dynamic
    assert "Telugu" not in system[0]["text"]  # the cached part stays the same for every language
    assert "Reply in English." in llm.build_system(demo, "priya")[1]["text"]


def delta(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


class Recorder:
    def __init__(self, pieces):
        self.pieces, self.calls = pieces, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter([delta(p) for p in self.pieces])


def test_indic_turns_use_the_indic_model_and_english_keeps_its_own(multi, demo, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("OPENAI_REASONING", "low")
    for lang, model, reasoning in [("te", "google/gemini-2.5-flash", False), ("hi", "google/gemini-2.5-flash", False), ("en", "openai/gpt-4o-mini", True)]:
        rec = Recorder(["ok."])
        list(llm._gateway_stream(demo, "priya", "x", rec, lang=lang))
        assert rec.calls[0]["model"] == model, lang
        assert ("reasoning_effort" in rec.calls[0]) is reasoning, lang
    monkeypatch.setenv("AI_GATEWAY_MODEL_INDIC", "google/gemini-2.5-flash-lite")
    rec = Recorder(["ok."])
    list(llm._gateway_stream(demo, "priya", "x", rec, lang="kn"))
    assert rec.calls[0]["model"] == "google/gemini-2.5-flash-lite"


def test_a_silent_indic_model_gets_an_apology_in_that_language(multi, demo):
    assert "".join(llm._gateway_stream(demo, "priya", "x", Recorder([]), lang="te")) == languages.SORRY["te"]


def test_tool_calls_without_an_index_are_still_collected(multi, demo, monkeypatch):
    def call(id=None, name=None, args=None):
        tc = SimpleNamespace(index=None, id=id, function=SimpleNamespace(name=name, arguments=args))
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))])

    seen = []
    from app.toolkit import Tool

    tool = SimpleNamespace(name="search", tools=[Tool("find", "d", {"type": "object", "properties": {}}, lambda state, **a: seen.append(a) or {"ok": 1})])
    monkeypatch.setattr(llm, "REGISTRY", [tool])

    class Client:
        def __init__(self):
            self.n = 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._c))

        def _c(self, **kw):
            self.n += 1
            if self.n == 1:
                return iter([call("c1", "search__find", '{"q": "a"}'), call("c2", "search__find", '{"q": "b"}')])
            return iter([delta("Done.")])

    out = "".join(llm._gateway_stream(demo, "priya", "x", Client(), lang="hi"))
    assert out.endswith("Done.") and out.startswith(languages.LOOKING["hi"]) and len(seen) == 2


# ---- the orchestrator ----


@pytest.fixture
def llm_spy(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    calls = []

    def stream(state, member_id, text, lang=None):
        calls.append(lang)
        yield "Reply. "
        yield "More."

    monkeypatch.setattr(llm, "stream", stream)
    monkeypatch.setattr(llm, "converse", lambda state, member_id, text, lang=None, **k: calls.append(lang) or "Reply. More.")
    return calls


def test_non_english_turns_skip_the_rule_engine_and_carry_their_language(multi, demo, llm_spy):
    for text, lang in [(TELUGU, "te"), (KANNADA, "kn"), (HINDI, "hi")]:
        assert list(orchestrator.converse_stream(demo, "priya", text)) == ["Reply.", "More."]
        assert llm_spy[-1] == lang
    assert orchestrator.converse(demo, "priya", TELUGU) == "Reply. More." and llm_spy[-1] == "te"
    n = len(llm_spy)
    assert "four hundred fifty" in " ".join(orchestrator.converse_stream(demo, "priya", "I spent 450 on groceries"))
    assert len(llm_spy) == n  # English keeps the instant rule-engine path


def test_non_english_replies_are_not_run_through_the_english_speech_rewrite(multi, demo, monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setattr(llm, "stream", lambda *a, **k: iter(["రేపు 3 గంటలకు సమావేశం ఉంది."]))
    assert list(orchestrator.converse_stream(demo, "priya", TELUGU)) == ["రేపు 3 గంటలకు సమావేశం ఉంది."]
    assert demo.transcript[-1]["text"] == "రేపు 3 గంటలకు సమావేశం ఉంది."


def test_the_hindi_full_stop_ends_a_sentence():
    assert list(orchestrator._sentences(["नमस्ते। आज क्या करें? ठीक है"])) == ["नमस्ते।", "आज क्या करें?", "ठीक है"]


def test_a_hold_phrase_in_the_right_language_and_not_kept_in_the_transcript(multi, demo, monkeypatch):
    import time

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setattr(orchestrator, "FILLER_AFTER_S", 0.05)

    def slow(*a, **k):
        time.sleep(0.3)
        yield "ఇదిగో సమాధానం."

    monkeypatch.setattr(llm, "stream", slow)
    out = list(orchestrator.converse_stream(demo, "priya", TELUGU))
    assert out == [languages.HOLD["te"], "ఇదిగో సమాధానం."]
    assert demo.transcript[-1]["text"] == "ఇదిగో సమాధానం."


def test_without_a_model_a_non_english_message_gets_the_english_rule_reply(multi, demo, monkeypatch):
    reply = orchestrator.converse(demo, "priya", TELUGU)
    assert reply and all(ord(c) < 0x0900 for c in reply)  # plain English, not Hinglish


# ---- the voice endpoint ----


def parse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]


def test_voice_endpoint_sends_the_voice_settings_first_in_multi_mode(multi, monkeypatch):
    from app.main import app

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    monkeypatch.setattr(llm, "stream", lambda *a, **k: iter(["రేపు సమావేశం ఉంది."]))
    STATE.reset(demo=True)
    client = TestClient(app)
    body = lambda text: {"model": "x", "stream": True, "messages": [{"role": "user", "content": text}]}
    chunks = parse(client.post("/v1/chat/completions?member=priya", json=body(TELUGU)))
    first = chunks[0]
    assert first["object"] == "chat.completion.custom_metadata" and first["choices"] == []
    assert first["metadata"]["tts_params"]["params"] == {"voiceId": "hi-IN-rachna", "locale": "te-IN"}
    assert chunks[1]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks[1:]).strip() == "రేపు సమావేశం ఉంది."
    assert any(e["tool"] == "reply_language" and e["args"]["detected"] == "te" for e in STATE.events)
    english = parse(client.post("/v1/chat/completions?member=priya", json=body("thanks")))
    assert english[0]["metadata"]["tts_params"]["params"]["locale"] == "en-IN"  # back to English when the speaker is


def test_voice_endpoint_sends_no_voice_settings_outside_multi_mode(monkeypatch):
    from app.main import app

    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    STATE.reset(demo=True)
    chunks = parse(TestClient(app).post("/v1/chat/completions?member=priya", json={"model": "x", "stream": True, "messages": [{"role": "user", "content": "thanks"}]}))
    assert chunks[0]["object"] == "chat.completion.chunk"


# ---- the household's choice ----


def test_settings_can_switch_between_multi_and_english_and_it_is_saved(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setenv("AANGAN_DATA_FILE", str(tmp_path / "h.json"))
    client = TestClient(app)
    STATE.reset(demo=True)
    cfg = client.get("/api/config").json()
    assert cfg["language_mode"] == "native"  # the suites run in native mode; the real default is multi
    assert {l["code"] for l in cfg["languages"]} == {"en", "hi", "te", "kn"}
    assert client.post("/api/language", json={"mode": "english"}).json()["language_mode"] == "english"
    assert json.loads((tmp_path / "h.json").read_text())["language_mode"] == "english"
    assert client.post("/api/language", json={"mode": "multi"}).json()["language_mode"] == "multi"
    assert client.post("/api/language", json={"mode": "klingon"}).status_code == 400
    # a restart reads the choice back
    config.set_language_override(None)
    persistence.load(STATE)
    assert config.settings().language_mode == "multi"


def test_member_languages_include_telugu_and_kannada():
    from app.agents import household

    assert {"Telugu", "Kannada"} <= set(household.LANGUAGES)
    state = FamilyState()
    state.reset(demo=True)
    out = household._add_member(state, "Lakshmi", "Grandmother", 70, language="Telugu")
    assert out["member"]["language"] == "Telugu" and out["member"]["locale"] == "te-IN"
