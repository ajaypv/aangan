"""Agora Conversational AI Engine: start/stop a per-member voice agent.

The pipeline mirrors the official Agora Next.js quickstart that was proven live (see agora-baseline/):
Agora-managed Deepgram nova-3 speech recognition, our backend as the LLM (CustomLLM, called through a public URL),
and Murf Falcon TTS (bring-your-own-key). Uses the official `agora-agents` SDK in App Credentials mode.
There is no mock path: without the required keys, start_agent raises ServiceNotConfigured.
"""

import secrets

from agora_agent import Agent, Agora, Area
from agora_agent.agentkit import CustomLLM, DeepgramSTT, MurfTTS, expires_in_hours, generate_client_token

from . import languages, voices
from .config import Settings
from .state import FamilyState

AGENT_UID = 123456  # same agent uid the official quickstart uses (DEFAULT_AGENT_UID)
TOKEN_TTL_S = 3600
IDLE_TIMEOUT_S = 30

SYSTEM_PROMPT = (
    "You are Aangan, a warm voice assistant for one family. Keep replies to one or two short spoken sentences. "
    "Reply in the language the user speaks."
)

# mirrors the quickstart's turnDetection (VAD) settings
TURN_DETECTION = {
    "config": {
        "speech_threshold": 0.5,
        "start_of_speech": {"mode": "vad", "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300}},
        "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}},
    }
}
ADVANCED_FEATURES = {"enable_rtm": True, "enable_tools": True}
PARAMETERS = {
    "audio_scenario": "chorus",  # web client: ultra-low-latency profile
    "data_channel": "rtm",
    "enable_error_message": True,
    "enable_metrics": True,
}

SESSION: dict = {}


class ServiceNotConfigured(Exception):
    def __init__(self, missing: list[str]):
        super().__init__("not configured: " + ", ".join(missing))
        self.missing = missing


def _client(cfg: Settings) -> Agora:
    # Area.US is what the proven quickstart uses
    return Agora(area=Area.US, app_id=cfg.agora_app_id, app_certificate=cfg.agora_app_certificate)


def _opening_language(state: FamilyState, member_id: str):
    """In multi-language mode the call opens in the member's own language; after that it follows what is said."""
    if voices.language_mode() != "multi":
        return None
    return languages.for_member(state.member(member_id).get("language"))


def greeting_for(state: FamilyState, member_id: str) -> str:
    member = state.member(member_id)
    opening = _opening_language(state, member_id)
    if opening:
        return languages.GREETING[opening.code].format(name=member["name"])
    if state.speaks_hindi(member_id):
        return f"Namaste {member['name']}, Aangan yahan hai. Bataiye, aaj main kya karun?"
    return f"Hello {member['name']}, Aangan here. What can I do for the family today?"


def failure_message_for(state: FamilyState, member_id: str) -> str:
    opening = _opening_language(state, member_id)
    if opening:
        return languages.FAILURE[opening.code]
    return "Ek second, dobara bolenge?" if state.speaks_hindi(member_id) else "One moment, could you say that again?"


def build_agent(cfg: Settings, client: Agora, state: FamilyState, member_id: str) -> Agent:
    member = state.member(member_id)
    voice = voices.voice_for(member)
    greeting = greeting_for(state, member_id)
    failure = failure_message_for(state, member_id)
    return (
        Agent(
            client=client,
            instructions=SYSTEM_PROMPT,
            greeting=greeting,
            failure_message=failure,
            max_history=50,
            turn_detection=TURN_DETECTION,
            advanced_features=ADVANCED_FEATURES,
            parameters=PARAMETERS,
        )
        # Agora-managed nova-3 (no key): the SDK infers the reseller preset when the session starts
        .with_stt(DeepgramSTT(model="nova-3", language=voices.asr_language(member)))
        .with_llm(
            CustomLLM(
                api_key=cfg.llm_api_key,
                model="aangan-agent",
                base_url=f"{cfg.public_base_url}/v1/chat/completions?member={member_id}",
                greeting_message=greeting,
                failure_message=failure,
                max_history=15,
            )
        )
        # Murf is not an Agora-managed vendor, so it uses our own key
        .with_tts(
            MurfTTS(
                key=cfg.murf_api_key, voice_id=voice["voice_id"], locale=voice["locale"],
                model=cfg.murf_model, sample_rate=24000,
            )
        )
    )


def _start_session(agent: Agent, channel: str, user_uid: int) -> str:
    session = agent.create_session(
        channel=channel,
        agent_uid=str(AGENT_UID),
        remote_uids=[str(user_uid)],
        idle_timeout=IDLE_TIMEOUT_S,
        expires_in=expires_in_hours(1),
    )
    return session.start()


def _already_gone(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    body = str(getattr(exc, "body", "") or exc).lower()
    return status == 404 or "already in the process of shutting down" in body


def _stop_agent_id(cfg: Settings, agent_id: str) -> None:
    try:
        _client(cfg).stop_agent(agent_id)
    except Exception as exc:
        if not _already_gone(exc):  # stopping is idempotent: an agent that is gone or stopping counts as stopped
            raise


def start_agent(cfg: Settings, state: FamilyState, member_id: str) -> dict:
    missing = cfg.missing_voice()
    if missing:
        raise ServiceNotConfigured(missing)
    if SESSION:  # one live session at a time
        try:
            stop_agent(cfg)
        except Exception:
            SESSION.clear()

    state.member(member_id)  # unknown member -> StopIteration surfaces as a 404 in main
    user_uid = secrets.randbelow(9_999_000) + 1000
    while user_uid == AGENT_UID:
        user_uid = secrets.randbelow(9_999_000) + 1000
    channel = f"aangan-{secrets.token_hex(3)}"

    agent = build_agent(cfg, _client(cfg), state, member_id)
    agent_id = _start_session(agent, channel, user_uid)

    # RTC + RTM token for the browser, minted like the quickstart: one token for both, account = String(uid).
    # The RTM login identity must equal rtm_user_id.
    client_token = generate_client_token(
        cfg.agora_app_id, cfg.agora_app_certificate, channel, user_uid, token_expire=TOKEN_TTL_S
    )
    info = {
        "app_id": cfg.agora_app_id,
        "channel": channel,
        "token": client_token,
        "uid": user_uid,
        "rtm_token": client_token,
        "rtm_user_id": str(user_uid),
        "agent_id": agent_id,
        "agent_uid": str(AGENT_UID),
        "greeting": greeting_for(state, member_id),
        "member_id": member_id,
        "voice": voices.voice_for(state.member(member_id)),
        "language_mode": cfg.language_mode,
    }
    SESSION.clear()
    SESSION.update(info)
    return info


def stop_agent(cfg: Settings) -> dict:
    if not SESSION:
        return {"stopped": False}
    agent_id = SESSION["agent_id"]
    _stop_agent_id(cfg, agent_id)
    SESSION.clear()
    return {"stopped": True, "agent_id": agent_id}
