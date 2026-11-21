import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


LANGUAGE_MODES = ("multi", "english", "native")
_language_override: str | None = None


def set_language_override(mode: str | None) -> None:
    """The household's own choice (Settings), which beats AANGAN_LANGUAGE_MODE. None goes back to the environment's default."""
    global _language_override
    _language_override = mode if mode in LANGUAGE_MODES else None


def language_override() -> str | None:
    return _language_override


MODEL_KINDS = ("main", "indic")  # main: English and everything else; indic: Hindi, Telugu and Kannada turns
_model_override: dict[str, str] = {}


def set_model_override(kind: str, model: str | None) -> None:
    """The household's model choice (Settings), which beats AI_GATEWAY_MODEL and AI_GATEWAY_MODEL_INDIC. None goes back to the default."""
    if kind not in MODEL_KINDS:
        return
    if model:
        _model_override[kind] = model
    else:
        _model_override.pop(kind, None)


def model_overrides() -> dict[str, str]:
    return dict(_model_override)


def default_models() -> dict[str, str]:
    """What each kind uses when the household has made no choice (the environment, else the built-in default)."""
    return {"main": _env("AI_GATEWAY_MODEL") or "openai/gpt-5-nano", "indic": _env("AI_GATEWAY_MODEL_INDIC", "google/gemini-2.5-flash")}


def load_model_overrides(saved) -> None:
    """From a saved household file; anything that is not a known kind with a text model is ignored."""
    _model_override.clear()
    if isinstance(saved, dict):
        for kind, model in saved.items():
            if kind in MODEL_KINDS and isinstance(model, str) and model.strip():
                _model_override[kind] = model.strip()


def _language_mode() -> str:
    """multi (default): English, Hindi, Telugu and Kannada, following what is said. english: English only.
    native: each member's own language, as before."""
    mode = (_language_override or _env("AANGAN_LANGUAGE_MODE", "multi")).lower()
    return mode if mode in LANGUAGE_MODES else "multi"


@dataclass(frozen=True)
class Settings:
    agora_app_id: str
    agora_app_certificate: str
    murf_api_key: str
    murf_model: str
    public_base_url: str
    llm_api_key: str
    mcp_api_key: str  # bearer token for the MCP endpoint (/mcp); falls back to llm_api_key when empty
    anthropic_api_key: str
    llm_model: str
    openai_api_key: str
    openai_model: str
    ai_gateway_api_key: str
    ai_gateway_model: str
    ai_gateway_model_indic: str  # the model for Hindi, Telugu and Kannada turns: it writes those languages far better
    ai_gateway_fallbacks: str  # comma-separated models tried, in order, when the main one is rate limited (the free tier allows 5 requests a minute per model)
    openai_reasoning: str  # optional reasoning effort for the OpenAI brain ("low", "medium", ...); empty leaves the model default
    cloudflare_api_token: str  # Cloudflare AI Gateway, tried before the Vercel gateway when it is set up
    cloudflare_account_id: str
    cloudflare_gateway_id: str
    cloudflare_model: str  # English and everything else; a Workers AI model needs no credits, an openai/... one needs unified billing credits
    cloudflare_model_indic: str  # for Hindi, Telugu and Kannada; empty sends those turns straight to the Vercel gateway's model, which writes them better
    language_mode: str  # "english": everything in English; "native": Hindi/Hinglish for members who speak it
    chat_host: str
    chat_app_id: str
    chat_app_token: str
    chat_from: str
    chat_to: str

    def _missing(self, pairs: dict[str, str]) -> list[str]:
        return [env for env, value in pairs.items() if not value]

    def missing_agora(self) -> list[str]:
        return self._missing({"AGORA_APP_ID": self.agora_app_id, "AGORA_APP_CERTIFICATE": self.agora_app_certificate})

    def missing_murf(self) -> list[str]:
        return self._missing({"MURF_API_KEY": self.murf_api_key})

    def missing_voice(self) -> list[str]:
        """Everything a live voice session needs: Agora, Murf, and a public URL Agora can call as the agent's LLM."""
        return (
            self.missing_agora() + self.missing_murf()
            + self._missing({"PUBLIC_BASE_URL": self.public_base_url, "LLM_API_KEY": self.llm_api_key})
        )

    def missing_chat(self) -> list[str]:
        return self._missing({"AGORA_CHAT_HOST": self.chat_host, "AGORA_CHAT_APP_ID": self.chat_app_id, "AGORA_CHAT_APP_TOKEN": self.chat_app_token})

    @property
    def voice_ready(self) -> bool:
        return not self.missing_voice()

    @property
    def chat_ready(self) -> bool:
        return not self.missing_chat()

    @property
    def cloudflare_ready(self) -> bool:
        return bool(self.cloudflare_api_token and self.cloudflare_account_id)

    @property
    def gateway_ready(self) -> bool:
        """Either AI gateway is set up: Cloudflare (tried first) or Vercel (the backup)."""
        return bool(self.ai_gateway_api_key or self.cloudflare_ready)

    @property
    def llm_ready(self) -> bool:
        return bool(self.gateway_ready or self.openai_api_key or self.anthropic_api_key)

    @property
    def llm_provider(self) -> str:
        """The AI gateways first (Cloudflare, then Vercel as its backup), then OpenAI, then Anthropic. Empty when no key is set."""
        if self.gateway_ready:
            return "gateway"
        return "openai" if self.openai_api_key else "anthropic" if self.anthropic_api_key else ""

    @property
    def ai_gateway_model_name(self) -> str:
        return _model_override.get("main") or self.ai_gateway_model or "openai/gpt-5-nano"

    @property
    def llm_model_name(self) -> str:
        return {"gateway": self.ai_gateway_model_name, "openai": self.openai_model}.get(self.llm_provider, self.llm_model)

    def services(self) -> dict:
        def svc(missing: list[str]) -> dict:
            return {"configured": not missing, "missing": missing}

        return {
            "agora": svc(self.missing_agora()),
            "murf": svc(self.missing_murf()),
            "voice": svc(self.missing_voice()),
            "chat": svc(self.missing_chat()),
            "llm": svc([] if self.llm_ready else ["AI_GATEWAY_API_KEY"]),
        }


def settings() -> Settings:
    return Settings(
        agora_app_id=_env("AGORA_APP_ID"),
        agora_app_certificate=_env("AGORA_APP_CERTIFICATE"),
        murf_api_key=_env("MURF_API_KEY"),
        murf_model=_env("MURF_MODEL", "FALCON"),
        # Render sets RENDER_EXTERNAL_URL to the service's own https address, so a deployment needs no manual URL
        public_base_url=(_env("PUBLIC_BASE_URL") or _env("RENDER_EXTERNAL_URL")).rstrip("/"),
        llm_api_key=_env("LLM_API_KEY"),
        mcp_api_key=_env("MCP_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        llm_model=_env("LLM_MODEL", "claude-sonnet-5-5"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-6-luna"),
        openai_reasoning=_env("OPENAI_REASONING"),
        cloudflare_api_token=_env("CLOUDFLARE_API_TOKEN"),
        cloudflare_account_id=_env("CLOUDFLARE_ACCOUNT_ID"),
        cloudflare_gateway_id=_env("CLOUDFLARE_GATEWAY_ID", "default"),
        cloudflare_model=_env("CLOUDFLARE_MODEL", "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
        cloudflare_model_indic=_env("CLOUDFLARE_MODEL_INDIC"),
        ai_gateway_api_key=_env("AI_GATEWAY_API_KEY"),
        ai_gateway_model=_env("AI_GATEWAY_MODEL"),
        ai_gateway_model_indic=_model_override.get("indic") or _env("AI_GATEWAY_MODEL_INDIC", "google/gemini-2.5-flash"),
        ai_gateway_fallbacks=_env("AI_GATEWAY_FALLBACKS", "openai/gpt-4.1-mini,google/gemini-2.5-flash,openai/gpt-4.1-nano,openai/gpt-4o-mini"),
        language_mode=_language_mode(),
        chat_host=_env("AGORA_CHAT_HOST"),
        chat_app_id=_env("AGORA_CHAT_APP_ID"),
        chat_app_token=_env("AGORA_CHAT_APP_TOKEN"),
        chat_from=_env("AGORA_CHAT_FROM", "aangan"),
        chat_to=_env("AGORA_CHAT_TO", "ajay"),
    )
