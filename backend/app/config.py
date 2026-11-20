import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    agora_app_id: str
    agora_app_certificate: str
    murf_api_key: str
    murf_model: str
    public_base_url: str
    llm_api_key: str
    anthropic_api_key: str
    llm_model: str
    openai_api_key: str
    openai_model: str
    ai_gateway_api_key: str
    ai_gateway_model: str
    openai_reasoning: str  # optional reasoning effort for the OpenAI brain ("low", "medium", ...); empty leaves the model default
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
    def llm_ready(self) -> bool:
        return bool(self.ai_gateway_api_key or self.openai_api_key or self.anthropic_api_key)

    @property
    def llm_provider(self) -> str:
        """Vercel AI Gateway first, then OpenAI, then Anthropic. Empty when no key is set."""
        if self.ai_gateway_api_key:
            return "gateway"
        return "openai" if self.openai_api_key else "anthropic" if self.anthropic_api_key else ""

    @property
    def ai_gateway_model_name(self) -> str:
        return self.ai_gateway_model or "openai/gpt-5-nano"

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
        public_base_url=_env("PUBLIC_BASE_URL").rstrip("/"),
        llm_api_key=_env("LLM_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        llm_model=_env("LLM_MODEL", "claude-sonnet-5-5"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-6-luna"),
        openai_reasoning=_env("OPENAI_REASONING"),
        ai_gateway_api_key=_env("AI_GATEWAY_API_KEY"),
        ai_gateway_model=_env("AI_GATEWAY_MODEL"),
        language_mode="native" if _env("AANGAN_LANGUAGE_MODE", "english").lower() == "native" else "english",
        chat_host=_env("AGORA_CHAT_HOST"),
        chat_app_id=_env("AGORA_CHAT_APP_ID"),
        chat_app_token=_env("AGORA_CHAT_APP_TOKEN"),
        chat_from=_env("AGORA_CHAT_FROM", "aangan"),
        chat_to=_env("AGORA_CHAT_TO", "ajay"),
    )
