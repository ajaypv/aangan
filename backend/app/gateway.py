"""Vercel AI Gateway: streaming text generation with the OpenAI SDK pointed at the gateway.

The gateway speaks the OpenAI API at https://ai-gateway.vercel.sh/v1, authenticated with AI_GATEWAY_API_KEY,
and addresses every model as "provider/model" (see https://ai-gateway.vercel.sh/v1/models).

Run it:  uv run python -m app.gateway "write a haiku about ai"
"""

import sys
from collections.abc import Iterator

from openai import OpenAI

from .config import settings

BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_MODEL = "openai/gpt-6-astra"


class GatewayNotConfigured(RuntimeError):
    pass


def gateway_client(api_key: str | None = None) -> OpenAI:
    key = api_key or settings().ai_gateway_api_key
    if not key:
        raise GatewayNotConfigured("AI_GATEWAY_API_KEY is not set")
    return OpenAI(api_key=key, base_url=BASE_URL)


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
