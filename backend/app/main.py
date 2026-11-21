import json
import logging
import os
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import agora, impact, languages, models_catalog, orchestrator, persistence, rooms, voices
from .agents import BY_NAME, REGISTRY
from .config import MODEL_KINDS, default_models, model_overrides, set_language_override, set_model_override, settings
from .rooms_api import router as rooms_router
from .house_api import router as house_router
from .state import DEMO_ENV, STATE
from .toolkit import run_tool

log = logging.getLogger("aangan")


def _warm_up() -> None:
    """Import the LLM client libraries now: the first spoken turn used to pay several seconds for it."""
    try:
        from . import gateway, llm  # noqa: F401

        if settings().gateway_ready:
            gateway.gateway_client()
    except Exception as exc:
        log.warning("LLM warm-up skipped: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the saved household at startup; with none saved, AANGAN_DEMO_ON_START=1 starts with the demo family."""
    loaded = persistence.load(STATE)
    if not loaded and os.getenv(DEMO_ENV, "") == "1":
        STATE.load_demo()
    await run_in_threadpool(_warm_up)
    yield


app = FastAPI(title="Aangan", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5190", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
PUBLIC_PATHS = ("/v1/chat/completions",)
# AANGAN_PUBLIC=1 on a host such as Render or Fly: the whole app is public, so the local tunnel guard steps aside
PUBLIC_DEPLOYMENT = os.getenv("AANGAN_PUBLIC", "") == "1"


@app.middleware("http")
async def tunnel_guard(request: Request, call_next):
    """Requests arriving through a public tunnel (a non-local Host) may only reach the LLM endpoint Agora calls."""
    if PUBLIC_DEPLOYMENT:  # a hosted deployment is meant to be reached by anyone, the app included
        return await call_next(request)
    host = urlsplit("//" + request.headers.get("host", "")).hostname or ""
    if host not in LOCAL_HOSTS and not request.url.path.startswith(PUBLIC_PATHS):
        return JSONResponse({"detail": "not found"}, status_code=404)
    return await call_next(request)


@app.middleware("http")
async def save_household(request: Request, call_next):
    """After any request that can change the household, write it to disk. A failed save never breaks the response."""
    response = await call_next(request)
    path = request.url.path
    # the voice endpoint saves for itself when its stream ends: the response body is still being produced here
    # a room heartbeat arrives every few seconds from everyone in the room and changes nothing worth saving
    if request.method != "GET" and path.startswith("/api/") and not path.endswith("/heartbeat"):
        try:
            await run_in_threadpool(persistence.save, STATE)
        except Exception as exc:
            log.warning("could not save the household: %s", exc)
    return response


app.include_router(rooms_router)
app.include_router(house_router)


class Utterance(BaseModel):
    member_id: str
    message: str


class MemberRef(BaseModel):
    member_id: str


class Chaos(BaseModel):
    enabled: bool


class ToolCall(BaseModel):
    args: dict[str, Any] = {}


class ChatCompletionRequest(BaseModel):
    model_config = {"extra": "allow"}
    messages: list[dict[str, Any]]
    stream: bool = True


def _member_or_404(member_id: str) -> str:
    if not STATE.members:
        raise HTTPException(409, {"error": "no_household", "message": "Set up your family first."})
    if not any(m["id"] == member_id for m in STATE.members):
        raise HTTPException(404, f"unknown family member {member_id}")
    return member_id


@app.get("/api/config")
def get_config():
    cfg = settings()
    return {
        "services": cfg.services(),
        "brain": "llm" if cfg.llm_ready else "rules",
        "llm": {
            "provider": cfg.llm_provider, "model": cfg.llm_model_name, "indic_model": cfg.ai_gateway_model_indic,
            "choosable": cfg.llm_provider == "gateway", "overrides": model_overrides(), "defaults": default_models(),
            # Cloudflare's gateway is tried first when set up; the models above are then the backup
            "cloudflare": {"model": cfg.cloudflare_model, "indic_model": cfg.cloudflare_model_indic or None, "gateway": cfg.cloudflare_gateway_id} if cfg.cloudflare_ready else None,
        } if cfg.llm_ready else None,
        "language_mode": cfg.language_mode,
        "languages": [{"code": l.code, "name": l.name, "native": l.native} for l in languages.LANGUAGES.values()],
        "voices": {m["id"]: voices.voice_for(m) for m in STATE.members},
        "tts": {"vendor": "murf", "model": cfg.murf_model},
        "llm_url": f"{cfg.public_base_url}/v1/chat/completions" if cfg.public_base_url else None,
    }


class LanguageChoice(BaseModel):
    mode: str


@app.post("/api/language")
def set_language(choice: LanguageChoice):
    """The household's language choice: `multi` (English, Hindi, Telugu, Kannada, following what is said) or `english`.
    A voice call in progress keeps the language it started with; the next call uses the new one."""
    if choice.mode not in ("multi", "english"):
        raise HTTPException(400, "mode must be multi or english")
    set_language_override(choice.mode)
    return get_config()


@app.get("/api/llm/models")
def llm_models(q: str = "", tools_only: bool = True, limit: int = 30):
    """Search the models the AI Gateway offers (id, name, provider, price per million tokens, context, tool use). Chat models only."""
    if settings().llm_provider != "gateway":
        raise HTTPException(409, {"error": "not_gateway", "message": "Choosing a model needs the AI Gateway key (AI_GATEWAY_API_KEY)."})
    catalog = models_catalog.fetch_catalog()
    if not catalog:
        raise HTTPException(503, {"error": "catalog_unavailable", "message": "Could not load the model list from the gateway. Check your connection and try again."})
    found = models_catalog.search(catalog, q, tools_only=tools_only, limit=max(1, min(limit, 100)))
    return {"models": found, "total": len(catalog), "matches": len(found), "query": q}


class ModelChoice(BaseModel):
    model: str | None = None  # None puts the default back
    kind: str = "main"  # main: English and everything else; indic: Hindi, Telugu and Kannada


@app.post("/api/llm/model")
def set_llm_model(choice: ModelChoice):
    """The household's AI model choice. It applies from the next message; a voice call in progress keeps its model for that turn only."""
    if settings().llm_provider != "gateway":
        raise HTTPException(409, {"error": "not_gateway", "message": "Choosing a model needs the AI Gateway key (AI_GATEWAY_API_KEY)."})
    if choice.kind not in MODEL_KINDS:
        raise HTTPException(400, "kind must be main or indic")
    if choice.model:
        if not models_catalog.is_valid_id(choice.model):
            raise HTTPException(400, "a model looks like provider/name, for example openai/gpt-4o-mini")
        catalog = models_catalog.fetch_catalog()
        if catalog and not models_catalog.known(choice.model, catalog):
            raise HTTPException(404, f"the gateway does not list {choice.model}")
    set_model_override(choice.kind, choice.model)
    _save_household()
    return get_config()


class ModelTest(BaseModel):
    model: str


@app.post("/api/llm/test")
def test_llm_model(body: ModelTest):
    """One tiny request to a model: does it answer, how fast, and does it call a tool? Changes nothing."""
    if settings().llm_provider != "gateway":
        raise HTTPException(409, {"error": "not_gateway", "message": "Testing a model needs the AI Gateway key (AI_GATEWAY_API_KEY)."})
    if not models_catalog.is_valid_id(body.model):
        raise HTTPException(400, "a model looks like provider/name, for example openai/gpt-4o-mini")
    return models_catalog.test_model(body.model)


@app.get("/api/state")
def get_state():
    return STATE.snapshot()


@app.get("/api/impact")
def get_impact():
    return impact.compute(STATE)


@app.post("/api/household/demo")
def household_demo():
    STATE.load_demo()
    return STATE.snapshot()


@app.post("/api/household/reset")
def household_reset():
    STATE.reset(demo=False)
    return STATE.snapshot()


@app.get("/api/tools")
def list_tools():
    return [
        {"agent": a.name, "name": t.name, "description": t.description, "parameters": t.parameters}
        for a in REGISTRY
        for t in a.tools
    ]


@app.post("/api/tool/{agent}/{tool}")
def call_tool(agent: str, tool: str, body: ToolCall):
    if agent not in BY_NAME:
        raise HTTPException(404, f"unknown agent {agent}")
    spec = next((t for t in BY_NAME[agent].tools if t.name == tool), None)
    if spec is None:
        raise HTTPException(404, f"unknown tool {agent}/{tool}")
    try:
        status, result = run_tool(STATE, agent, spec, body.args)
    except TypeError as exc:  # wrong or missing arguments
        raise HTTPException(422, f"bad arguments for {agent}/{tool}: {exc}") from exc
    return {"status": status, "result": result, "state": STATE.snapshot()}


@app.post("/api/converse")
def converse(body: Utterance):
    member_id = _member_or_404(body.member_id)
    reply = orchestrator.converse(STATE, member_id, body.message.strip())
    return {"reply": reply, "state": STATE.snapshot()}


@app.post("/api/trigger/{agent}/{name}")
def trigger(agent: str, name: str):
    if agent not in BY_NAME or not any(t.name == name for t in BY_NAME[agent].triggers):
        raise HTTPException(404, f"no trigger {agent}/{name}")
    if not STATE.demo:
        raise HTTPException(409, {"error": "demo_only", "message": "Scenarios run on the demo family only."})
    reply = orchestrator.run_trigger(STATE, agent, name)
    return {"reply": reply, "state": STATE.snapshot()}


@app.post("/api/chaos")
def chaos(body: Chaos):
    STATE.chaos = body.enabled
    for domain in STATE.domains.values():  # re-arm the one-shot supplier failure in every agent
        for key in ("chaos_consumed", "chaos_fired"):
            if key in domain:
                domain[key] = False
    return STATE.snapshot()


@app.post("/api/reset")
def reset():
    STATE.reset()
    return STATE.snapshot()


@app.post("/api/agent/start")
def agent_start(body: MemberRef):
    member_id = _member_or_404(body.member_id)
    try:
        return agora.start_agent(settings(), STATE, member_id)
    except agora.ServiceNotConfigured as exc:
        raise HTTPException(503, {"error": "not_configured", "missing": exc.missing}) from exc
    except Exception as exc:  # Agora rejected the request or was unreachable
        raise HTTPException(502, f"Agora start-agent failed: {exc}") from exc


@app.post("/api/agent/stop")
def agent_stop():
    try:
        return agora.stop_agent(settings())
    except Exception as exc:
        raise HTTPException(502, f"Agora stop-agent failed: {exc}") from exc


def _save_household() -> None:
    try:
        persistence.save(STATE)
    except Exception as exc:  # a failed save never breaks a turn
        log.warning("could not save the household: %s", exc)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _chunks(reply: str):
    words = reply.split(" ")
    return [" ".join(words[i : i + 4]) + (" " if i + 4 < len(words) else "") for i in range(0, len(words), 4)]


@app.post("/v1/chat/completions")
def chat_completions(
    body: ChatCompletionRequest,
    member: str = "",
    room: str = "",
    participant: str = "",
    authorization: str | None = Header(default=None),
):
    """OpenAI-compatible endpoint Agora calls as the agent's LLM; runs the Aangan orchestrator for `member`.
    With `room` (and `participant`) it is the voice of a Family Room, answered by the room brain instead."""
    key = settings().llm_api_key
    if key and authorization != f"Bearer {key}":
        raise HTTPException(401, "invalid LLM api key")
    if room:
        return _room_completion(body, room, participant)
    member_id = _member_or_404(member or STATE.persona or (STATE.members[0]["id"] if STATE.members else ""))

    last_user = next((m for m in reversed(body.messages) if m.get("role") == "user"), None)
    if last_user is None:
        raise HTTPException(400, "no user message")
    content = last_user["content"]
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
    completion_id, created, model = f"chatcmpl-{uuid.uuid4().hex[:12]}", int(time.time()), "aangan-agent"
    if not body.stream:
        reply = orchestrator.converse(STATE, member_id, content.strip())
        _save_household()
        return JSONResponse(
            {
                "id": completion_id, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            }
        )

    def stream():
        """Agora's speech engine starts talking on the first words, so every sentence is sent the moment it is ready."""
        base = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model}
        lang = orchestrator._turn_language(content)
        if lang:
            # Multi-language mode: Agora reads this first chunk and points the Murf voice at the language being spoken to
            # (the same multi-native voice, a different locale), before any text arrives.
            speak = languages.tts_params(lang, voices.infer_gender(STATE.member(member_id)))
            STATE.log("voice", "reply_language", {"detected": lang, **speak}, "ok", {}, 0)
            yield _sse(
                {"id": completion_id, "object": "chat.completion.custom_metadata", "choices": [], "metadata": {"tts_params": {"params": speak}}}
            )
        yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
        try:
            for sentence in orchestrator.converse_stream(STATE, member_id, content.strip()):
                yield _sse({**base, "choices": [{"index": 0, "delta": {"content": sentence + " "}, "finish_reason": None}]})
        except Exception:
            log.exception("voice turn failed")
            yield _sse({**base, "choices": [{"index": 0, "delta": {"content": "Sorry, something went wrong."}, "finish_reason": None}]})
        finally:
            _save_household()
        yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _room_completion(body: ChatCompletionRequest, room_id: str, participant_id: str):
    """The room's voice: what was said is saved in the room, the planner answers and updates the plan, sentence by sentence."""
    last_user = next((m for m in reversed(body.messages) if m.get("role") == "user"), None)
    if last_user is None:
        raise HTTPException(400, "no user message")
    content = last_user["content"]
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
    content = content.strip()
    try:
        # no participant given: the voice speaks for the host (one agent listens to the whole room)
        participant_id = participant_id or rooms.host_info(STATE, room_id)["id"]
        rooms.participant_info(STATE, room_id, participant_id)
    except rooms.RoomError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    completion_id, created, model = f"chatcmpl-{uuid.uuid4().hex[:12]}", int(time.time()), "aangan-agent"
    if not body.stream:
        reply = rooms.converse_room(STATE, room_id, participant_id, content)
        _save_household()
        return JSONResponse(
            {
                "id": completion_id, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            }
        )

    def stream():
        base = {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model}
        lang = orchestrator._turn_language(content)
        if lang:  # same as the single-user call: the Murf voice follows the language being spoken, in Aangan's one room voice
            speak = languages.tts_params(lang, rooms.voice_gender(STATE, room_id))
            yield _sse(
                {"id": completion_id, "object": "chat.completion.custom_metadata", "choices": [], "metadata": {"tts_params": {"params": speak}}}
            )
        yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
        try:
            for sentence in rooms.converse_room_stream(STATE, room_id, participant_id, content):
                yield _sse({**base, "choices": [{"index": 0, "delta": {"content": sentence + " "}, "finish_reason": None}]})
        except Exception:
            log.exception("room voice turn failed")
            yield _sse({**base, "choices": [{"index": 0, "delta": {"content": "Sorry, something went wrong."}, "finish_reason": None}]})
        finally:
            _save_household()
        yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# --- the built web app. One container serves both the API and the PWA, so the browser talks to its own origin
# (no CORS, and the microphone works because hosts give HTTPS). Mounted last so every /api and /v1 route wins.
def _static_dir() -> Path | None:
    configured = os.getenv("AANGAN_STATIC_DIR", "").strip()
    for candidate in ([Path(configured)] if configured else []) + [Path(__file__).resolve().parents[2] / "frontend" / "dist"]:
        if (candidate / "index.html").is_file():
            return candidate
    return None


_STATIC = _static_dir() if os.getenv("AANGAN_SERVE_WEB", "1") == "1" else None
if _STATIC:
    from starlette.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_STATIC, html=True), name="web")
