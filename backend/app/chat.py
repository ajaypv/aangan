"""Agora Chat server REST: send a text message to the family's Chat account."""

import httpx

from .config import Settings


def send_text(cfg: Settings, text: str) -> dict:
    """Send via Agora Chat. Raises httpx.HTTPError on failure; callers must check cfg.chat_ready first."""
    res = httpx.post(
        f"https://{cfg.chat_host}/app-id/{cfg.chat_app_id}/messages/users",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {cfg.chat_app_token}",
        },
        json={"from": cfg.chat_from, "to": [cfg.chat_to], "type": "txt", "body": {"msg": text}},
        timeout=15,
    )
    res.raise_for_status()
    ids = res.json().get("data", {})
    return {"message_id": next(iter(ids.values()), ""), "to": cfg.chat_to}
