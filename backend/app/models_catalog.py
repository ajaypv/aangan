"""The models the AI Gateway offers, for the Settings model picker: fetch, search, and a quick test of one model.

The list comes from the gateway itself (`GET /v1/models`) and is kept for ten minutes. Only chat ("language") models are offered.
A model's `tool-use` tag matters most here: Aangan's agents work through tool calls, so a model without it would answer but never act.
"""

import re
import threading
import time

import httpx
import openai

from .config import settings
from .gateway import BASE_URL, gateway_client

CACHE_SECONDS = 600
_LOCK = threading.Lock()
_cache: dict = {"at": 0.0, "models": []}
_MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+$")


def _per_million(value) -> float | None:
    """The gateway prices a token; people think in rupees or dollars per million tokens."""
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def _shape(raw: dict) -> dict:
    tags = [t for t in raw.get("tags") or [] if isinstance(t, str)]
    pricing = raw.get("pricing") or {}
    return {
        "id": raw["id"], "name": raw.get("name") or raw["id"], "provider": raw.get("owned_by") or raw["id"].split("/")[0],
        "description": (raw.get("description") or "")[:240], "context_window": raw.get("context_window"),
        "tools": "tool-use" in tags, "reasoning": "reasoning" in tags, "fast": "fast" in tags, "vision": "vision" in tags,
        "input_per_million": _per_million(pricing.get("input")), "output_per_million": _per_million(pricing.get("output")),
        "released": raw.get("released"),
    }


def fetch_catalog(force: bool = False, client: httpx.Client | None = None) -> list[dict]:
    """Every chat model the gateway lists, shaped for the app. Cached; on a failed refresh the last good list is kept."""
    with _LOCK:
        fresh = time.time() - _cache["at"] < CACHE_SECONDS
        if fresh and _cache["models"] and not force:
            return list(_cache["models"])
    key = settings().ai_gateway_api_key
    if not key:
        return list(_cache["models"])
    try:
        http = client or httpx.Client(timeout=15)
        data = http.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {key}"}).json()["data"]
        # chat models only; "-batch" variants are for the gateway's batch API (answers come back later), not for a live conversation
        models = [_shape(m) for m in data if m.get("type") == "language" and m.get("id") and not m["id"].endswith("-batch")]
    except Exception:
        return list(_cache["models"])  # offline: whatever we last had (maybe nothing)
    with _LOCK:
        _cache.update(at=time.time(), models=models)
    return list(models)


def clear_cache() -> None:
    with _LOCK:
        _cache.update(at=0.0, models=[])


FEATURED = {"openai", "google", "anthropic", "meta", "mistral", "deepseek", "xai", "alibaba", "cohere"}  # names people expect to see first


def search(models: list[dict], query: str = "", tools_only: bool = False, limit: int = 30) -> list[dict]:
    """Models whose id, name, provider or description contain every word typed, best match first (well-known makers a little
    ahead), then cheapest."""
    words = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    scored = []
    for m in models:
        if tools_only and not m["tools"]:
            continue
        hay = f"{m['id']} {m['name']} {m['provider']}".lower()
        full = f"{hay} {m['description']}".lower()
        if not all(w in full for w in words):
            continue
        score = 0.5 if m["provider"] in FEATURED else 0
        for w in words:
            score += 8 if m["id"].lower() == w else 5 if m["id"].lower().split("/")[-1].startswith(w) else 3 if w in hay else 1
        price = m["input_per_million"] if m["input_per_million"] is not None else 1e9
        scored.append((-score, price, m["id"], m))
    scored.sort(key=lambda t: t[:3])
    return [m for *_, m in scored[:limit]]


def is_valid_id(model: str) -> bool:
    return bool(_MODEL_ID.match(model or ""))


def known(model: str, models: list[dict]) -> bool:
    return any(m["id"] == model for m in models)


_PING_TOOL = [{"type": "function", "function": {
    "name": "ping", "description": "Reply to the user by calling this function.", "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]}}}]


def test_model(model: str, client=None) -> dict:
    """One small request: does the model answer, how fast, and does it call a tool? A failure is a plain sentence, never an exception."""
    started = time.time()
    try:
        client = client or gateway_client()
        reply = client.chat.completions.create(
            model=model, max_tokens=60, tools=_PING_TOOL, tool_choice="auto",
            messages=[{"role": "user", "content": "Call the ping function with the word hello."}],
        )
        message = reply.choices[0].message
        called = bool(message.tool_calls)
        return {"ok": True, "model": model, "ms": int((time.time() - started) * 1000), "tool_calling": called,
                "note": "Answers and calls tools: good for Aangan." if called else "Answers, but did not call a tool: Aangan's agents may not act with it."}
    except openai.RateLimitError:
        return {"ok": False, "model": model, "ms": int((time.time() - started) * 1000), "error": "This model is rate limited right now. Try again in a minute."}
    except (openai.PermissionDeniedError, openai.NotFoundError):
        return {"ok": False, "model": model, "ms": int((time.time() - started) * 1000), "error": "This model is not available on your gateway plan."}
    except openai.BadRequestError as exc:
        return {"ok": False, "model": model, "ms": int((time.time() - started) * 1000), "error": f"The model rejected the test request: {str(exc)[:120]}"}
    except Exception as exc:
        return {"ok": False, "model": model, "ms": int((time.time() - started) * 1000), "error": f"Could not reach the model: {type(exc).__name__}"}
