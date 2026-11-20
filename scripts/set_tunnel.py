"""Record a new public tunnel URL after restarting cloudflared.

Usage (from hackton/backend):  uv run python ../scripts/set_tunnel.py https://<words>.trycloudflare.com
Updates backend/.env (PUBLIC_BASE_URL) and, if present, agora-baseline/.env.local (NEXT_LLM_URL).
Restart the backend afterwards so it reads the new value.
"""

import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1]
public = sys.argv[1].rstrip("/")


def upsert(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=", text, re.M):
        return re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


backend_env = root / "backend" / ".env"
text = backend_env.read_text()
backend_env.write_text(upsert(text, "PUBLIC_BASE_URL", public))

baseline_env = root / "agora-baseline" / ".env.local"
if baseline_env.exists():
    btext = baseline_env.read_text()
    baseline_env.write_text(upsert(btext, "NEXT_LLM_URL", public + "/v1/chat/completions"))

print("tunnel recorded:", public)
