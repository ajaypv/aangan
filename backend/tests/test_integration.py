import json
import warnings

import pytest
from fastapi.testclient import TestClient

from app import agora, voices
from app.config import settings
from app.main import STATE, app

warnings.filterwarnings("ignore")
client = TestClient(app)

LIVE_ENV = {
    "AGORA_APP_ID": "app123", "AGORA_APP_CERTIFICATE": "a" * 32, "MURF_API_KEY": "murf-key",
    "PUBLIC_BASE_URL": "https://abc.ngrok.app", "LLM_API_KEY": "llm-secret",
}


@pytest.fixture(autouse=True)
def fresh():
    STATE.reset(demo=True)  # the app starts empty; these tests exercise the demo family
    agora.SESSION.clear()


@pytest.fixture
def live_env(monkeypatch):
    for k, v in LIVE_ENV.items():
        monkeypatch.setenv(k, v)


def test_config_reports_missing_keys():
    cfg = client.get("/api/config").json()
    assert cfg["brain"] == "rules" and cfg["language_mode"] == "native"  # conftest runs the legacy suites in native mode
    assert cfg["services"]["voice"] == {
        "configured": False,
        "missing": ["AGORA_APP_ID", "AGORA_APP_CERTIFICATE", "MURF_API_KEY", "PUBLIC_BASE_URL", "LLM_API_KEY"],
    }
    assert cfg["services"]["llm"]["missing"] == ["AI_GATEWAY_API_KEY"]
    assert cfg["voices"]["dadi"] == {
        "name": "Rachna", "voice_id": "hi-IN-rachna", "locale": "hi-IN", "gender": "female", "language": "Hindi",
    }


def test_config_flips_to_configured(live_env):
    cfg = client.get("/api/config").json()
    assert cfg["services"]["voice"]["configured"] and cfg["services"]["chat"]["configured"] is False
    assert cfg["llm_url"] == "https://abc.ngrok.app/v1/chat/completions"


def test_voices_follow_the_murf_recommended_list():
    by_id = {m["id"]: voices.voice_for(m) for m in STATE.members}
    assert by_id["priya"]["voice_id"] == "en-IN-pooja" and by_id["priya"]["locale"] == "hi-LATN"
    assert by_id["aarav"]["voice_id"] == "en-IN-nikhil" and by_id["rahul"]["voice_id"] == "en-IN-abhinav"
    assert by_id["rahul"]["locale"] == "en-IN"
    assert voices.voice_for({"language": "Hinglish", "relation": "Daughter"})["name"] == "Pooja"
    assert voices.asr_language({"language": "Hinglish"}) == "hi-Latn"


def test_agent_start_returns_503_when_voice_not_configured():
    res = client.post("/api/agent/start", json={"member_id": "dadi"})
    assert res.status_code == 503
    assert res.json()["detail"]["error"] == "not_configured" and "MURF_API_KEY" in res.json()["detail"]["missing"]
    assert client.post("/api/agent/start", json={"member_id": "nobody"}).status_code == 404
    assert client.post("/api/agent/stop").json() == {"stopped": False}


def test_tool_endpoint_runs_a_tool_and_logs_it():
    res = client.post("/api/tool/household/remember_fact", json={"args": {"about": "rahul", "fact": "Dislikes mushrooms"}}).json()
    assert res["status"] == "ok" and res["result"]["fact"]["fact"] == "Dislikes mushrooms"
    assert any(e["agent"] == "household" and e["tool"] == "remember_fact" for e in res["state"]["events"])
    bad = client.post("/api/tool/household/remember_fact", json={"args": {"about": "nobody", "fact": "x"}}).json()
    assert bad["status"] == "error"
    assert client.post("/api/tool/household/nope", json={"args": {}}).status_code == 404
    assert client.post("/api/tool/household/remember_fact", json={"args": {"bogus": 1}}).status_code == 422
    assert {t["agent"] for t in client.get("/api/tools").json()} == {"travel", "calendar", "dining", "school", "care", "household", "money"}


def test_tunnel_host_can_only_reach_the_llm_endpoint():
    public = {"Host": "random-words.trycloudflare.com"}
    assert client.get("/api/state", headers=public).status_code == 404
    assert client.post("/api/reset", headers=public).status_code == 404
    assert client.get("/api/state").status_code == 200
    body = {"messages": [{"role": "user", "content": "hello there"}], "stream": False}
    assert client.post("/v1/chat/completions?member=dadi", json=body, headers=public).status_code == 200


def test_snapshot_shape():
    s = client.get("/api/state").json()
    assert [m["id"] for m in s["members"]] == ["priya", "rahul", "aarav", "dadi"]
    assert set(s["domains"]) == {"travel", "calendar", "dining", "school", "care", "household", "money"}


def test_converse_records_context_and_transcript():
    res = client.post("/api/converse", json={"member_id": "priya", "message": "hello there"}).json()
    assert res["reply"]
    assert ("orchestrator", "load_member_context") in [(e["agent"], e["tool"]) for e in res["state"]["events"]]
    assert [t["role"] for t in res["state"]["transcript"]] == ["user", "agent"]


def test_stale_pending_proposal_is_dropped_when_user_moves_on():
    client.post("/api/trigger/travel/flight_delay")
    assert STATE.pending and STATE.pending["agent"] == "travel"
    res = client.post("/api/converse", json={"member_id": "dadi", "message": "dawai le li"}).json()
    assert STATE.pending is None
    assert res["state"]["transcript"][-1]["agent"] == "care"


def test_trigger_reply_lands_in_transcript_once():
    res = client.post("/api/trigger/school/arrival").json()
    texts = [t["text"] for t in res["state"]["transcript"] if t["role"] == "agent"]
    assert texts.count(res["reply"]) == 1


def test_chaos_toggle_rearms_supplier_failure():
    client.post("/api/chaos", json={"enabled": True})
    STATE.domains["travel"]["chaos_consumed"] = True
    STATE.domains["dining"]["chaos_fired"] = True
    client.post("/api/chaos", json={"enabled": True})
    assert STATE.domains["travel"]["chaos_consumed"] is False and STATE.domains["dining"]["chaos_fired"] is False


def test_chat_completions_streams_sse_for_member():
    body = {"model": "x", "stream": True, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hello there"}]}
    res = client.post("/v1/chat/completions?member=dadi", json=body)
    assert res.headers["content-type"].startswith("text/event-stream")
    lines = [line for line in res.text.splitlines() if line.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line[6:]) for line in lines[:-1]]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert STATE.transcript[0]["member_id"] == "dadi"


def test_chat_completions_non_stream_and_list_content():
    body = {"stream": False, "messages": [{"role": "user", "content": [{"type": "text", "text": "hello there"}]}]}
    msg = client.post("/v1/chat/completions", json=body).json()["choices"][0]["message"]
    assert msg["role"] == "assistant" and msg["content"]


def test_chat_completions_checks_bearer(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sekret")
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/v1/chat/completions", json=body).status_code == 401
    ok = client.post("/v1/chat/completions", json=body, headers={"Authorization": "Bearer sekret"})
    assert ok.status_code == 200
