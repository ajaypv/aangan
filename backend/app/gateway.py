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
        if settings().cloudflare_ready:  # only Cloudflare is set up: it is the one gateway there is
            return cloudflare_client()
        raise GatewayNotConfigured("AI_GATEWAY_API_KEY is not set")
    # No automatic retries: the SDK sleeps for the whole "retry after" of a rate limit (30 to 50 seconds), which is a
    # silent voice call. open_stream() moves to another model instead.
    return OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=30)


def cloudflare_client() -> OpenAI:
    """Cloudflare AI Gateway's OpenAI-compatible endpoint for this account's gateway. The token goes both as the key and in the
    gateway's own authentication header, so it works whether or not the gateway has authentication switched on."""
    cfg = settings()
    if not cfg.cloudflare_ready:
        raise GatewayNotConfigured("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are not both set")
    return OpenAI(
        api_key=cfg.cloudflare_api_token,
        base_url=f"https://gateway.ai.cloudflare.com/v1/{cfg.cloudflare_account_id}/{cfg.cloudflare_gateway_id}/compat",
        default_headers={"cf-aig-authorization": f"Bearer {cfg.cloudflare_api_token}"},
        max_retries=0, timeout=30,
    )


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


def _try_cloudflare(kwargs: dict, indic: bool):
    """The stream from Cloudflare's gateway, or None when it is not set up, is resting, or just failed (the caller carries on
    with the Vercel gateway). A refusal for credits (402) or a rate limit rests it for a while so the next request does not
    wait for it again."""
    cfg = settings()
    model = cfg.cloudflare_model_indic if indic else cfg.cloudflare_model
    key = f"cloudflare/{model}"
    if not (cfg.cloudflare_ready and model) or _COOLING.get(key, 0) > time.time():
        return None
    params = {**kwargs, "model": model}
    if not model.startswith("openai/"):
        params.pop("reasoning_effort", None)  # an OpenAI setting: the other models behind the gateway do not take it
    try:
        return cloudflare_client().chat.completions.create(**params)
    except openai.RateLimitError as exc:
        wait = _retry_after(exc)
        log.warning("cloudflare: %s rate limited for %.0fs, using the Vercel gateway", model, wait)
        cool_down(key, wait)
    except openai.APIStatusError as exc:
        if exc.status_code == 402:  # unified billing credits used up: OpenAI and other providers' models need them
            log.warning("cloudflare: %s needs credits (402), using the Vercel gateway for the next 5 minutes", model)
            cool_down(key, 300)
        elif exc.status_code in (401, 403, 404, 410):  # a token, gateway or model problem: it will not fix itself soon
            log.warning("cloudflare: %s refused (%s), using the Vercel gateway for the next 5 minutes", model, exc.status_code)
            cool_down(key, 300)
        elif exc.status_code == 400:
            log.warning("cloudflare: %s rejected the request: %s", model, str(exc)[:120])
        else:
            log.warning("cloudflare: %s failed (%s), using the Vercel gateway", model, exc.status_code)
            cool_down(key, 10)
    except Exception as exc:  # no connection, a timeout, or anything unexpected: the backup is there for exactly this
        log.warning("cloudflare: %s failed (%s), using the Vercel gateway", model, type(exc).__name__)
        cool_down(key, 10)
    return None


def open_stream(client, kwargs: dict, indic: bool = False):
    """Start a streamed completion on the first model that will take it: Cloudflare's gateway first when it is set up, then
    the Vercel gateway's models. A rate limit (the free tiers allow only a few requests a minute per model) or a refused or
    failing model moves on to the next one at once, instead of waiting. `indic`: a Hindi, Telugu or Kannada turn."""
    first = _try_cloudflare(kwargs, indic)
    if first is not None:
        return first
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
