"""Cloudflare AI Gateway first, the Vercel gateway as the backup."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app import config, gateway
from app.main import app

WORKERS = "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    gateway._COOLING.clear()
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "vck_test")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "openai/gpt-4o-mini")
    yield
    gateway._COOLING.clear()


@pytest.fixture
def cloudflare(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cfut_test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_GATEWAY_ID", "hack")
    monkeypatch.setenv("CLOUDFLARE_MODEL", WORKERS)
    monkeypatch.setenv("CLOUDFLARE_MODEL_INDIC", "")


class Recorder:
    """A fake client that records the models it was asked for and either streams or raises."""

    def __init__(self, name, error=None):
        self.name, self.error, self.asked = name, error, []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        self.asked.append(kwargs)
        if self.error:
            raise self.error
        return iter([f"{self.name} stream"])


def status_error(code, retry_after=None):
    request = httpx.Request("POST", "https://gateway.ai.cloudflare.com/x")
    headers = {"retry-after": str(retry_after)} if retry_after else {}
    response = httpx.Response(code, request=request, headers=headers)
    cls = {429: openai.RateLimitError, 400: openai.BadRequestError, 401: openai.AuthenticationError, 403: openai.PermissionDeniedError, 404: openai.NotFoundError}.get(code)
    if cls:
        return cls("failed", response=response, body=None)
    return openai.APIStatusError("failed", response=response, body=None)


def use(monkeypatch, cf):
    monkeypatch.setattr(gateway, "cloudflare_client", lambda: cf)


def kwargs(**extra):
    return {"model": "openai/gpt-4o-mini", "messages": [], "stream": True, **extra}


# ---- setup ----


def test_cloudflare_needs_both_the_token_and_the_account(monkeypatch):
    assert config.settings().cloudflare_ready is False
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cfut_test")
    assert config.settings().cloudflare_ready is False
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    assert config.settings().cloudflare_ready is True


def test_cloudflare_alone_is_enough_to_have_an_ai_brain(monkeypatch, cloudflare):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "")
    s = config.settings()
    assert s.gateway_ready and s.llm_ready and s.llm_provider == "gateway"
    assert gateway.gateway_client().base_url.host == "gateway.ai.cloudflare.com"  # the one gateway there is


def test_the_client_points_at_this_accounts_gateway_and_sends_the_gateway_header(cloudflare):
    client = gateway.cloudflare_client()
    assert str(client.base_url).rstrip("/") == "https://gateway.ai.cloudflare.com/v1/acct123/hack/compat"
    assert client.api_key == "cfut_test" and client.default_headers["cf-aig-authorization"] == "Bearer cfut_test"
    assert client.max_retries == 0  # a rate limit must move us on, not make the call sleep
    with pytest.raises(gateway.GatewayNotConfigured):
        config_off = pytest.MonkeyPatch()
        config_off.setenv("CLOUDFLARE_API_TOKEN", "")
        try:
            gateway.cloudflare_client()
        finally:
            config_off.undo()


# ---- first choice and backup ----


def test_cloudflare_is_tried_first_and_the_backup_is_not_touched(monkeypatch, cloudflare):
    cf, vercel = Recorder("cloudflare"), Recorder("vercel")
    use(monkeypatch, cf)
    assert list(gateway.open_stream(vercel, kwargs())) == ["cloudflare stream"]
    assert cf.asked[0]["model"] == WORKERS and vercel.asked == []


def test_without_cloudflare_nothing_changes(monkeypatch):
    vercel = Recorder("vercel")
    monkeypatch.setattr(gateway, "cloudflare_client", lambda: pytest.fail("Cloudflare is not set up: it must not be called"))
    assert list(gateway.open_stream(vercel, kwargs())) == ["vercel stream"] and vercel.asked[0]["model"] == "openai/gpt-4o-mini"


@pytest.mark.parametrize("code", [402, 401, 403, 404, 500])
def test_a_refusal_or_failure_falls_back_at_once_and_rests_cloudflare(monkeypatch, cloudflare, code):
    cf, vercel = Recorder("cloudflare", status_error(code)), Recorder("vercel")
    use(monkeypatch, cf)
    assert list(gateway.open_stream(vercel, kwargs())) == ["vercel stream"]
    assert len(cf.asked) == 1 and len(vercel.asked) == 1
    list(gateway.open_stream(vercel, kwargs()))
    assert len(cf.asked) == 1  # still resting: the second request goes straight to the backup, without waiting on it again


def test_a_credit_refusal_rests_cloudflare_for_five_minutes(monkeypatch, cloudflare):
    use(monkeypatch, Recorder("cloudflare", status_error(402)))
    list(gateway.open_stream(Recorder("vercel"), kwargs()))
    rest = gateway._COOLING[f"cloudflare/{WORKERS}"] - __import__("time").time()
    assert 290 < rest <= 300


def test_a_rate_limit_rests_cloudflare_for_as_long_as_it_asks(monkeypatch, cloudflare):
    use(monkeypatch, Recorder("cloudflare", status_error(429, retry_after=45)))
    assert list(gateway.open_stream(Recorder("vercel"), kwargs())) == ["vercel stream"]
    assert 40 < gateway._COOLING[f"cloudflare/{WORKERS}"] - __import__("time").time() <= 45


def test_no_connection_falls_back_too(monkeypatch, cloudflare):
    use(monkeypatch, Recorder("cloudflare", openai.APIConnectionError(request=httpx.Request("POST", "https://x"))))
    assert list(gateway.open_stream(Recorder("vercel"), kwargs())) == ["vercel stream"]


def test_a_request_cloudflare_rejects_is_tried_on_the_backup_without_resting_it(monkeypatch, cloudflare):
    cf, vercel = Recorder("cloudflare", status_error(400)), Recorder("vercel")
    use(monkeypatch, cf)
    assert list(gateway.open_stream(vercel, kwargs())) == ["vercel stream"]
    list(gateway.open_stream(vercel, kwargs()))
    assert len(cf.asked) == 2  # this one request did not suit it; the next may


def test_hindi_telugu_and_kannada_skip_cloudflare_unless_it_has_a_model_for_them(monkeypatch, cloudflare):
    cf, vercel = Recorder("cloudflare"), Recorder("vercel")
    use(monkeypatch, cf)
    assert list(gateway.open_stream(vercel, kwargs(model="google/gemini-2.5-flash"), indic=True)) == ["vercel stream"] and cf.asked == []
    monkeypatch.setenv("CLOUDFLARE_MODEL_INDIC", "workers-ai/@cf/openai/gpt-oss-120b")
    assert list(gateway.open_stream(vercel, kwargs(model="google/gemini-2.5-flash"), indic=True)) == ["cloudflare stream"]
    assert cf.asked[0]["model"] == "workers-ai/@cf/openai/gpt-oss-120b"


def test_an_openai_only_setting_is_not_sent_to_other_models(monkeypatch, cloudflare):
    cf = Recorder("cloudflare")
    use(monkeypatch, cf)
    list(gateway.open_stream(Recorder("vercel"), kwargs(reasoning_effort="low")))
    assert "reasoning_effort" not in cf.asked[0]
    monkeypatch.setenv("CLOUDFLARE_MODEL", "openai/gpt-4.1")
    list(gateway.open_stream(Recorder("vercel"), kwargs(reasoning_effort="low")))
    assert cf.asked[1]["reasoning_effort"] == "low" and cf.asked[1]["model"] == "openai/gpt-4.1"


def test_tools_and_streaming_are_passed_through_untouched(monkeypatch, cloudflare):
    cf = Recorder("cloudflare")
    use(monkeypatch, cf)
    tools = [{"type": "function", "function": {"name": "add_task", "parameters": {"type": "object"}}}]
    list(gateway.open_stream(Recorder("vercel"), kwargs(tools=tools, max_tokens=300)))
    assert cf.asked[0]["tools"] == tools and cf.asked[0]["stream"] is True and cf.asked[0]["max_tokens"] == 300


# ---- what the app says about it ----


def test_the_config_says_cloudflare_is_first_when_it_is(cloudflare):
    llm = TestClient(app).get("/api/config").json()["llm"]
    assert llm["cloudflare"] == {"model": WORKERS, "indic_model": None, "gateway": "hack"}
    assert llm["model"] == "openai/gpt-4o-mini"  # the backup


def test_the_config_has_no_cloudflare_entry_without_it():
    assert TestClient(app).get("/api/config").json()["llm"]["cloudflare"] is None
