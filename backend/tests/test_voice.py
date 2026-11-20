import warnings

import pytest
from agora_agent.agents.client import AgentsClient
from fastapi.testclient import TestClient

from app import agora, orchestrator, voices
from app.config import settings
from app.main import STATE, app
from app.state import FamilyState

warnings.filterwarnings("ignore")
client = TestClient(app)

LIVE_ENV = {
    "AGORA_APP_ID": "a" * 32, "AGORA_APP_CERTIFICATE": "b" * 32, "MURF_API_KEY": "murf-key",
    "PUBLIC_BASE_URL": "https://abc.trycloudflare.com", "LLM_API_KEY": "llm-secret",
}


@pytest.fixture(autouse=True)
def fresh():
    STATE.reset(demo=True)  # the app starts empty; these tests exercise the demo family
    agora.SESSION.clear()


@pytest.fixture
def live_env(monkeypatch):
    for key, value in LIVE_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")


@pytest.fixture
def captured_start(monkeypatch):
    """Capture exactly what the SDK would send to Agora's start-agent API; nothing goes over the network."""
    sent = {}

    def fake_start(self, appid, **kwargs):
        sent.update(kwargs, appid=appid)

        class Response:
            agent_id = "agent-123"

        return Response()

    monkeypatch.setattr(AgentsClient, "start", fake_start)
    return sent


def props_of(sent: dict) -> dict:
    props = sent["properties"]
    return props if isinstance(props, dict) else props.model_dump(exclude_none=True, by_alias=True)


# --- language mode

def test_default_language_mode_is_multi(monkeypatch):
    monkeypatch.delenv("AANGAN_LANGUAGE_MODE", raising=False)
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **k: None)
    assert settings().language_mode == "multi"
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    assert settings().language_mode == "native"
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "klingon")
    assert settings().language_mode == "multi"


def test_english_mode_puts_every_member_on_en_in(english):
    cfg = client.get("/api/config").json()
    assert cfg["language_mode"] == "english"
    for member in STATE.members:
        voice = cfg["voices"][member["id"]]
        assert voice["locale"] == "en-IN" and voice["language"] == "English"
        assert voices.asr_language(member) == "en-IN"
    assert cfg["voices"]["dadi"]["voice_id"] == "hi-IN-rachna"  # same assigned voice, speaking English
    assert cfg["voices"]["rahul"]["voice_id"] == "en-IN-abhinav"


def test_native_mode_keeps_each_members_own_language(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    by_id = {m["id"]: m for m in STATE.members}
    assert voices.voice_for(by_id["dadi"])["locale"] == "hi-IN" and voices.asr_language(by_id["dadi"]) == "hi"
    assert voices.voice_for(by_id["priya"])["locale"] == "hi-LATN" and voices.asr_language(by_id["priya"]) == "hi-Latn"
    assert voices.voice_for(by_id["rahul"])["locale"] == "en-IN" and voices.asr_language(by_id["rahul"]) == "en-IN"


def test_english_mode_replies_in_english_for_everyone(english):
    state = FamilyState()
    assert not any(state.speaks_hindi(m["id"]) for m in state.members)
    assert state.reply_language("dadi") == "English"
    reply = orchestrator.converse(state, "priya", "Sunday ko sab saath bahar jaana hai")
    assert "Udupi Garden on Sunday" in reply and "baje" not in reply
    dadi = orchestrator.converse(state, "dadi", "dawai le li")
    assert dadi and not {"hai", "mein", "aap", "kar", "doon"} & set(dadi.lower().replace(",", " ").split())


def test_native_mode_replies_in_the_members_language(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    state = FamilyState()
    assert state.speaks_hindi("dadi") and state.speaks_hindi("priya") and not state.speaks_hindi("rahul")
    reply = orchestrator.converse(state, "priya", "Sunday ko sab saath bahar jaana hai")
    assert "baje" in reply


def test_greetings_follow_the_mode(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    assert agora.greeting_for(STATE, "dadi") == "Hello Dadi, Aangan here. What can I do for the family today?"
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    assert agora.greeting_for(STATE, "dadi").startswith("Namaste Dadi")
    assert agora.greeting_for(STATE, "rahul").startswith("Hello Rahul")


# --- the request Agora receives (mirrors the proven quickstart)

def test_start_request_mirrors_the_proven_quickstart(live_env, english, captured_start):
    cfg = settings()
    agent = agora.build_agent(cfg, agora._client(cfg), STATE, "rahul")
    assert agora._start_session(agent, "chan1", 4321) == "agent-123"

    props = props_of(captured_start)
    assert captured_start["appid"] == "a" * 32 and captured_start["preset"] == "deepgram_nova_3"
    assert props["channel"] == "chan1" and props["agent_rtc_uid"] == "123456" and props["remote_rtc_uids"] == ["4321"]
    assert props["idle_timeout"] == 30
    assert props["asr"]["vendor"] == "deepgram" and props["asr"]["params"]["language"] == "en-IN"
    assert "api_key" not in props["asr"]["params"]  # Agora-managed nova-3: no Deepgram key

    llm = props["llm"]
    assert llm["url"] == "https://abc.trycloudflare.com/v1/chat/completions?member=rahul"
    assert llm["api_key"] == "llm-secret" and llm["vendor"] == "custom" and llm["style"] == "openai"
    assert llm["greeting_message"].startswith("Hello Rahul")

    tts = props["tts"]
    assert tts["vendor"] == "murf"
    assert tts["params"]["api_key"] == "murf-key" and tts["params"]["voiceId"] == "en-IN-abhinav"
    assert tts["params"]["locale"] == "en-IN" and tts["params"]["model"] == "FALCON"

    assert props["turn_detection"]["config"] == {
        "speech_threshold": 0.5,
        "start_of_speech": {"mode": "vad", "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300}},
        "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}},
    }
    assert props["advanced_features"] == {"enable_rtm": True, "enable_tools": True}
    assert props["parameters"]["audio_scenario"] == "chorus" and props["parameters"]["data_channel"] == "rtm"
    assert props["parameters"]["enable_error_message"] is True and props["parameters"]["enable_metrics"] is True


def test_native_start_request_uses_the_members_language(live_env, monkeypatch, captured_start):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")
    cfg = settings()
    agora._start_session(agora.build_agent(cfg, agora._client(cfg), STATE, "dadi"), "chan2", 4322)
    props = props_of(captured_start)
    assert props["asr"]["params"]["language"] == "hi"
    assert props["tts"]["params"]["voiceId"] == "hi-IN-rachna" and props["tts"]["params"]["locale"] == "hi-IN"
    assert props["llm"]["greeting_message"].startswith("Namaste Dadi")
    assert props["llm"]["url"].endswith("?member=dadi")


# --- /api/agent/start and /api/agent/stop

def fake_sdk(monkeypatch):
    calls = {"started": [], "stopped": []}

    def start(agent, channel, user_uid):
        calls["started"].append((channel, user_uid))
        return f"agent-{len(calls['started'])}"

    monkeypatch.setattr(agora, "_start_session", start)
    monkeypatch.setattr(agora, "_stop_agent_id", lambda cfg, agent_id: calls["stopped"].append(agent_id))
    return calls


def test_agent_start_response_contract(live_env, english, monkeypatch):
    calls = fake_sdk(monkeypatch)
    res = client.post("/api/agent/start", json={"member_id": "dadi"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "app_id", "channel", "token", "uid", "rtm_token", "rtm_user_id", "agent_id", "agent_uid", "greeting",
        "member_id", "voice", "language_mode",
    }
    assert body["app_id"] == "a" * 32 and body["channel"].startswith("aangan-")
    assert isinstance(body["uid"], int) and 1000 <= body["uid"] < 10_000_000 and body["uid"] != 123456
    assert body["rtm_user_id"] == str(body["uid"]) and body["agent_uid"] == "123456"
    assert body["token"] and body["rtm_token"] == body["token"]  # one combined RTC + RTM token, as in the quickstart
    assert body["agent_id"] == "agent-1" and body["member_id"] == "dadi" and body["language_mode"] == "english"
    assert body["voice"] == {"name": "Rachna", "voice_id": "hi-IN-rachna", "locale": "en-IN", "gender": "female", "language": "English"}
    assert body["greeting"].startswith("Hello Dadi")
    assert calls["started"] == [(body["channel"], body["uid"])] and agora.SESSION["agent_id"] == "agent-1"


def test_second_start_stops_the_first_session(live_env, english, monkeypatch):
    calls = fake_sdk(monkeypatch)
    first = client.post("/api/agent/start", json={"member_id": "rahul"}).json()
    second = client.post("/api/agent/start", json={"member_id": "priya"}).json()
    assert calls["stopped"] == [first["agent_id"]]
    assert second["agent_id"] == "agent-2" and agora.SESSION["member_id"] == "priya"


def test_agent_stop_stops_via_the_sdk_and_is_idempotent(live_env, english, monkeypatch):
    calls = fake_sdk(monkeypatch)
    started = client.post("/api/agent/start", json={"member_id": "rahul"}).json()
    assert client.post("/api/agent/stop").json() == {"stopped": True, "agent_id": started["agent_id"]}
    assert calls["stopped"] == [started["agent_id"]] and not agora.SESSION
    assert client.post("/api/agent/stop").json() == {"stopped": False}


def test_agent_start_503_lists_what_is_missing():
    res = client.post("/api/agent/start", json={"member_id": "rahul"})
    assert res.status_code == 503
    assert res.json()["detail"] == {
        "error": "not_configured",
        "missing": ["AGORA_APP_ID", "AGORA_APP_CERTIFICATE", "MURF_API_KEY", "PUBLIC_BASE_URL", "LLM_API_KEY"],
    }


def test_stop_treats_an_already_gone_agent_as_stopped(live_env, monkeypatch):
    class Gone(Exception):
        status_code = 404

    class Stopping(Exception):
        status_code = 400
        body = {"detail": "Agent is already in the process of shutting down"}

    class Broken(Exception):
        status_code = 500

    class FakeClient:
        def __init__(self, exc):
            self.exc = exc

        def stop_agent(self, agent_id):
            raise self.exc

    cfg = settings()
    for exc in (Gone(), Stopping()):
        monkeypatch.setattr(agora, "_client", lambda cfg, e=exc: FakeClient(e))
        agora._stop_agent_id(cfg, "agent-9")  # no error
    monkeypatch.setattr(agora, "_client", lambda cfg: FakeClient(Broken()))
    with pytest.raises(Broken):
        agora._stop_agent_id(cfg, "agent-9")
