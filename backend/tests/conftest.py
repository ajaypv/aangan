import pytest

SERVICE_KEYS = [
    "AGORA_APP_ID", "AGORA_APP_CERTIFICATE", "MURF_API_KEY", "PUBLIC_BASE_URL", "LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AI_GATEWAY_API_KEY", "AI_GATEWAY_MODEL",
    "AGORA_CHAT_HOST", "AGORA_CHAT_APP_ID", "AGORA_CHAT_APP_TOKEN",
]


@pytest.fixture(autouse=True)
def no_service_keys(monkeypatch):
    """Tests never talk to Agora, Murf, Chat or an LLM, whatever is in a local .env."""
    for key in SERVICE_KEYS:
        monkeypatch.setenv(key, "")
    for key in ("OPENAI_MODEL", "OPENAI_REASONING"):  # tuning knobs from a local .env: tests expect the defaults
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def native_language_mode(monkeypatch):
    """The agent suites assert Hindi/Hinglish replies for Hindi speakers, so they run in native mode.
    The app's real default is english; tests of english mode set AANGAN_LANGUAGE_MODE themselves."""
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "native")


@pytest.fixture(autouse=True)
def isolated_household_file(monkeypatch, tmp_path):
    """Requests save the household after each change; tests write to a temp file, never backend/data."""
    monkeypatch.setenv("AANGAN_DATA_FILE", str(tmp_path / "household.json"))
    monkeypatch.delenv("AANGAN_DEMO_ON_START", raising=False)


@pytest.fixture(autouse=True)
def scripted_clock(monkeypatch):
    """The suites assert the demo's scripted morning (Friday 2026-11-20 07:30). The real default follows the clock;
    tests of that set AANGAN_CLOCK=real themselves."""
    monkeypatch.setenv("AANGAN_CLOCK", "scripted")


@pytest.fixture(autouse=True)
def no_language_override():
    """A household's language choice (Settings) is global state: every test starts without one."""
    from app import config

    config.set_language_override(None)
    yield
    config.set_language_override(None)
