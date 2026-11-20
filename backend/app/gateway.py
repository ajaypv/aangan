"""Vercel AI Gateway: streaming text generation with the OpenAI SDK pointed at the gateway.

The gateway speaks the OpenAI API at https://ai-gateway.vercel.sh/v1, authenticated with AI_GATEWAY_API_KEY,
and addresses every model as "provider/model" (see https://ai-gateway.vercel.sh/v1/models).

Run it:  uv run python -m app.gateway "write a haiku about ai"
"""

import logging
import sys
import threading
import time
from collections.abc import Iterator

import openai
from openai import OpenAI

from .config import settings

log = logging.getLogger("aangan.gateway")

BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_MODEL = "openai/gpt-6-astra"


class GatewayNotConfigured(RuntimeError):
    pass


def gateway_client(api_key: str | None = None) -> OpenAI:
    key = api_key or settings().ai_gateway_api_key
    if not key:
        raise GatewayNotConfigured("AI_GATEWAY_API_KEY is not set")
    # No automatic retries: the SDK sleeps for the whole "retry after" of a rate limit (30 to 50 seconds), which is a
    # silent voice call. open_stream() moves to another model instead.
    return OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=30)


_COOLING: dict[str, float] = {}  # model -> time until which it is rate limited or refused
_LOCK = threading.Lock()
DEFAULT_COOLDOWN_S = 30.0


def model_chain(primary: str) -> list[str]:
    """The model to use first, then the fallbacks, without repeats. A model that is cooling down goes to the back."""
    names = [primary] + [m.strip() for m in settings().ai_gateway_fallbacks.split(",") if m.strip()]
    chain = list(dict.fromkeys(names))
    now = time.time()
    with _LOCK:
        ready = [m for m in chain if _COOLING.get(m, 0) <= now]
        cooling = sorted((m for m in chain if m not in ready), key=lambda m: _COOLING[m])
    return ready + cooling


def cool_down(model: str, seconds: float) -> None:
    with _LOCK:
        _COOLING[model] = max(_COOLING.get(model, 0), time.time() + seconds)


def _retry_after(exc) -> float:
    try:
        return float(exc.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_COOLDOWN_S


def open_stream(client, kwargs: dict):
    """Start a streamed completion on the first model that will take it. A rate limit (the free tier allows only a few
    requests a minute per model) or a refused or failing model moves on to the next one at once, instead of waiting."""
    last: Exception | None = None
    for model in model_chain(kwargs["model"]):
        try:
            stream = client.chat.completions.create(**{**kwargs, "model": model})
        except openai.RateLimitError as exc:
            wait = _retry_after(exc)
            log.warning("gateway: %s rate limited for %.0fs, trying the next model", model, wait)
            cool_down(model, wait)
            last = exc
        except (openai.PermissionDeniedError, openai.NotFoundError) as exc:  # not allowed on this key, or no such model
            log.warning("gateway: %s refused the request (%s), trying the next model", model, type(exc).__name__)
            cool_down(model, 600)
            last = exc
        except openai.BadRequestError as exc:  # this model could not take this request (it may suit another); do not bench it
            log.warning("gateway: %s rejected the request: %s", model, str(exc)[:120])
            last = exc
        except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as exc:
            log.warning("gateway: %s failed (%s), trying the next model", model, type(exc).__name__)
            cool_down(model, 10)
            last = exc
        else:
            return stream
    raise last or RuntimeError("no model available")


def stream_text(prompt: str, model: str | None = None, system: str | None = None, client: OpenAI | None = None) -> Iterator[str]:
    """Yield the generated text piece by piece as the model produces it."""
    client = client or gateway_client()
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    stream = client.chat.completions.create(
        model=model or settings().ai_gateway_model or DEFAULT_MODEL,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def main(argv: list[str]) -> int:
    prompt = " ".join(argv) or "Write a haiku about AI."
    try:
        for piece in stream_text(prompt):
            print(piece, end="", flush=True)
    except GatewayNotConfigured as exc:
        print(f"Not configured: {exc}", file=sys.stderr)
        return 2
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
