"""The Settings model picker: searching the gateway's models, choosing one for the household, testing one."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app import config, models_catalog
from app.main import STATE, app

RAW = [
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o mini", "owned_by": "openai", "type": "language", "context_window": 128000, "tags": ["tool-use", "fast"],
     "pricing": {"input": "0.00000015", "output": "0.0000006"}, "description": "Small and quick"},
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "owned_by": "google", "type": "language", "context_window": 1000000,
     "tags": ["tool-use", "reasoning"], "pricing": {"input": "0.0000003", "output": "0.0000025"}, "description": "Strong in Indian languages"},
    {"id": "meta/llama-chat-only", "name": "Llama Chat", "owned_by": "meta", "type": "language", "context_window": 8000, "tags": [],
     "pricing": {"input": "0.0000001", "output": "0.0000001"}, "description": "No tools"},
    {"id": "openai/text-embedding-3", "name": "Embedding", "owned_by": "openai", "type": "embedding", "tags": [], "pricing": {}},
    {"id": "google/gemini-2.5-flash-batch", "name": "Gemini 2.5 Flash (Batch)", "owned_by": "google", "type": "language", "tags": ["tool-use"], "pricing": {}},
]


class FakeHttp:
    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.calls = data if data is not None else RAW, fail, 0

    def get(self, url, headers=None):
        self.calls += 1
        if self.fail:
            raise OSError("offline")
        return type("R", (), {"json": lambda s: {"data": self.data}})()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    models_catalog.clear_cache()
    config._model_override.clear()
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "vck_test")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "openai/gpt-4o-mini")
    yield
    models_catalog.clear_cache()
    config._model_override.clear()


@pytest.fixture
def catalog(monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr(models_catalog.httpx, "Client", lambda **k: fake)
    return fake


def test_the_catalog_keeps_chat_models_only_and_shapes_them(catalog):
    models = models_catalog.fetch_catalog()
    assert [m["id"] for m in models] == ["openai/gpt-4o-mini", "google/gemini-2.5-flash", "meta/llama-chat-only"]
    mini = models[0]
    assert mini["tools"] and mini["fast"] and mini["input_per_million"] == 0.15 and mini["output_per_million"] == 0.6 and mini["provider"] == "openai"


def test_the_catalog_is_cached_and_survives_a_failed_refresh(catalog, monkeypatch):
    models_catalog.fetch_catalog()
    models_catalog.fetch_catalog()
    assert catalog.calls == 1
    models_catalog._cache["at"] = 0  # stale
    monkeypatch.setattr(models_catalog.httpx, "Client", lambda **k: FakeHttp(fail=True))
    assert len(models_catalog.fetch_catalog()) == 3  # the last good list


def test_search_matches_every_word_ranks_and_can_require_tools(catalog):
    models = models_catalog.fetch_catalog()
    assert [m["id"] for m in models_catalog.search(models, "gemini flash")] == ["google/gemini-2.5-flash"]
    assert [m["id"] for m in models_catalog.search(models, "indian languages")] == ["google/gemini-2.5-flash"]  # the description counts
    assert models_catalog.search(models, "nothing like this") == []
    everything = models_catalog.search(models, "")
    assert [m["id"] for m in everything][0] == "meta/llama-chat-only"  # no query: cheapest first
    assert "meta/llama-chat-only" not in [m["id"] for m in models_catalog.search(models, "", tools_only=True)]
    assert models_catalog.search(models, "openai")[0]["id"] == "openai/gpt-4o-mini"


def test_a_chosen_model_beats_the_environment_and_can_be_reset():
    assert config.settings().ai_gateway_model_name == "openai/gpt-4o-mini"
    config.set_model_override("main", "google/gemini-2.5-flash")
    assert config.settings().ai_gateway_model_name == "google/gemini-2.5-flash" and config.settings().llm_model_name == "google/gemini-2.5-flash"
    config.set_model_override("indic", "openai/gpt-4o-mini")
    assert config.settings().ai_gateway_model_indic == "openai/gpt-4o-mini"
    config.set_model_override("main", None)
    assert config.settings().ai_gateway_model_name == "openai/gpt-4o-mini" and config.model_overrides() == {"indic": "openai/gpt-4o-mini"}
    config.set_model_override("nonsense", "x/y")
    assert "nonsense" not in config.model_overrides()


def test_the_choice_is_saved_with_the_household_and_loaded_back():
    config.set_model_override("main", "google/gemini-2.5-flash")
    saved = STATE.to_dict()
    assert saved["llm_models"] == {"main": "google/gemini-2.5-flash"}
    config._model_override.clear()
    STATE.apply_dict(saved)
    assert config.settings().ai_gateway_model_name == "google/gemini-2.5-flash"
    config.load_model_overrides({"main": 5, "bogus": "a/b", "indic": " google/gemini-2.5-flash "})
    assert config.model_overrides() == {"indic": "google/gemini-2.5-flash"}


def test_the_api_searches_selects_and_resets(catalog):
    client = TestClient(app)
    found = client.get("/api/llm/models", params={"q": "gemini"}).json()
    assert found["matches"] == 1 and found["models"][0]["id"] == "google/gemini-2.5-flash" and found["total"] == 3
    chosen = client.post("/api/llm/model", json={"model": "google/gemini-2.5-flash"}).json()
    assert chosen["llm"]["model"] == "google/gemini-2.5-flash" and chosen["llm"]["overrides"] == {"main": "google/gemini-2.5-flash"}
    assert chosen["llm"]["defaults"]["main"] == "openai/gpt-4o-mini" and chosen["llm"]["choosable"] is True
    indic = client.post("/api/llm/model", json={"model": "openai/gpt-4o-mini", "kind": "indic"}).json()
    assert indic["llm"]["indic_model"] == "openai/gpt-4o-mini"
    back = client.post("/api/llm/model", json={"model": None}).json()
    assert back["llm"]["model"] == "openai/gpt-4o-mini" and back["llm"]["overrides"] == {"indic": "openai/gpt-4o-mini"}


def test_the_api_refuses_a_model_the_gateway_does_not_list_or_a_malformed_one(catalog):
    client = TestClient(app)
    assert client.post("/api/llm/model", json={"model": "made/up-model"}).status_code == 404
    assert client.post("/api/llm/model", json={"model": "no slash here"}).status_code == 400
    assert client.post("/api/llm/model", json={"model": "openai/gpt-4o-mini", "kind": "huge"}).status_code == 400
    assert client.post("/api/llm/test", json={"model": "drop table"}).status_code == 400
    assert config.model_overrides() == {}


def test_without_the_gateway_the_picker_says_why(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)
    assert client.get("/api/llm/models").status_code == 409
    assert client.post("/api/llm/model", json={"model": "openai/gpt-4o-mini"}).status_code == 409


def test_the_catalog_being_unreachable_is_a_clear_503(monkeypatch):
    monkeypatch.setattr(models_catalog.httpx, "Client", lambda **k: FakeHttp(fail=True))
    assert TestClient(app).get("/api/llm/models").status_code == 503


class Reply:
    def __init__(self, tools):
        self.choices = [type("C", (), {"message": type("M", (), {"tool_calls": tools})()})()]


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        if self.error:
            raise self.error
        return self.result


def test_a_model_test_reports_speed_and_tool_calling():
    good = models_catalog.test_model("openai/gpt-4o-mini", client=FakeClient(Reply([object()])))
    assert good["ok"] and good["tool_calling"] and good["ms"] >= 0 and "good for Aangan" in good["note"]
    no_tools = models_catalog.test_model("meta/llama-chat-only", client=FakeClient(Reply(None)))
    assert no_tools["ok"] and not no_tools["tool_calling"] and "may not act" in no_tools["note"]


def test_a_model_test_turns_failures_into_sentences():
    request = httpx.Request("POST", "https://x")
    limited = openai.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)
    denied = openai.PermissionDeniedError("no", response=httpx.Response(403, request=request), body=None)
    assert "rate limited" in models_catalog.test_model("a/b", client=FakeClient(error=limited))["error"]
    assert "not available on your gateway plan" in models_catalog.test_model("a/b", client=FakeClient(error=denied))["error"]
    assert "Could not reach" in models_catalog.test_model("a/b", client=FakeClient(error=OSError("down")))["error"]
