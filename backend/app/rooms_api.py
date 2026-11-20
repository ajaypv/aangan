"""HTTP endpoints of the Family Room (see docs/ROOM_CONTRACT.md). All logic lives in rooms.py and planner.py."""

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import agora, planner, rooms
from .config import settings
from .state import STATE

log = logging.getLogger("aangan.rooms")
router = APIRouter(prefix="/api/rooms")
TOKEN_TTL_S = agora.TOKEN_TTL_S


class CreateRoom(BaseModel):
    title: str = ""
    member_id: str = ""


class JoinRoom(BaseModel):
    member_id: str | None = None
    guest_name: str | None = None


class WhoBody(BaseModel):
    participant_id: str


class MessageBody(BaseModel):
    participant_id: str
    text: str
    ask: bool = False


class ApproveBody(BaseModel):
    participant_id: str
    approve: bool


def _guard(fn, *args, **kwargs):
    """Room errors become the HTTP errors the contract names (404 unknown room / participant, 403, 409, 400)."""
    try:
        return fn(*args, **kwargs)
    except rooms.RoomError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.post("")
def create_room(body: CreateRoom):
    if not STATE.members:
        raise HTTPException(409, {"error": "no_household", "message": "Set up your family first."})
    return _guard(rooms.create_room, STATE, body.title, body.member_id or STATE.persona or STATE.members[0]["id"])


@router.get("/{room_id}")
def get_room(room_id: str, since: int | None = None):
    return _guard(rooms.snapshot, STATE, room_id, since)


@router.post("/{room_id}/join")
def join_room(room_id: str, body: JoinRoom):
    participant, room = _guard(rooms.join, STATE, room_id, body.member_id, body.guest_name)
    return {"participant": participant, "room": room}


@router.post("/{room_id}/heartbeat")
def heartbeat(room_id: str, body: WhoBody):
    _guard(rooms.heartbeat, STATE, room_id, body.participant_id)
    return {"ok": True}


def _plan_in_background(room_id: str, message_id: int, ask: bool) -> None:
    try:
        planner.plan_after_message(STATE, room_id, message_id, ask=ask)
    finally:
        planner.save_quietly(STATE)


@router.post("/{room_id}/message")
def post_message(room_id: str, body: MessageBody):
    """Save the message and answer at once; planning runs in the background and bumps the version when it is done."""
    message = _guard(rooms.add_user_message, STATE, room_id, body.participant_id, body.text)
    state = rooms.snapshot(STATE, room_id)
    rooms.spawn(_plan_in_background, room_id, message["id"], body.ask)
    return state


@router.post("/{room_id}/approve")
def approve(room_id: str, body: ApproveBody):
    return _guard(rooms.decide, STATE, room_id, body.participant_id, body.approve)


@router.post("/{room_id}/reset-plan")
def reset_plan(room_id: str):
    return _guard(rooms.reset_plan, STATE, room_id)


@router.post("/{room_id}/rtc")
def rtc(room_id: str, body: WhoBody):
    """A token for the browser to join the room's Agora channel (RTC and RTM share one token, like the single-user call)."""
    who = _guard(rooms.participant_info, STATE, room_id, body.participant_id)
    cfg = settings()
    missing = cfg.missing_agora()
    if missing:
        raise HTTPException(503, {"error": "not_configured", "missing": missing})
    channel = agora.room_channel(room_id)
    token = agora.generate_client_token(cfg.agora_app_id, cfg.agora_app_certificate, channel, who["rtc_uid"], token_expire=TOKEN_TTL_S)
    return {"app_id": cfg.agora_app_id, "channel": channel, "token": token, "uid": who["rtc_uid"], "rtm_token": token, "rtm_user_id": str(who["rtc_uid"])}


@router.post("/{room_id}/agent/start")
def agent_start(room_id: str, body: WhoBody):
    """Aangan joins the room's channel as a voice participant. One agent per room: starting again replaces the old one."""
    who = _guard(rooms.participant_info, STATE, room_id, body.participant_id)
    host = _guard(rooms.host_info, STATE, room_id)
    member_id = who["member_id"] or host["member_id"]  # a guest has no profile: the agent uses the host's voice
    cfg = settings()
    missing = cfg.missing_voice()
    if missing:
        raise HTTPException(503, {"error": "not_configured", "missing": missing})
    old = rooms.get_voice(STATE, room_id)
    if old:
        try:
            agora.stop_room_agent(cfg, old["agent_id"])
        except Exception as exc:  # a stale session must not block a new one
            log.warning("could not stop the old room agent: %s", exc)
    try:
        info = agora.start_room_agent(cfg, STATE, room_id, member_id, who["id"], who["rtc_uid"])
    except agora.ServiceNotConfigured as exc:
        raise HTTPException(503, {"error": "not_configured", "missing": exc.missing}) from exc
    except Exception as exc:
        raise HTTPException(502, f"Agora start-agent failed: {exc}") from exc
    rooms.set_voice(STATE, room_id, {"agent_id": info["agent_id"], "agent_uid": info["agent_uid"], "gender": info["gender"],
                                     "listening_to": info["listening_to"], "started_at": time.time()})
    return {"agent_id": info["agent_id"], "agent_uid": info["agent_uid"], "greeting": info["greeting"]}


@router.post("/{room_id}/agent/stop")
def agent_stop(room_id: str):
    voice = _guard(rooms.get_voice, STATE, room_id)
    if not voice:
        return {"stopped": False}
    try:
        agora.stop_room_agent(settings(), voice["agent_id"])
    except Exception as exc:
        raise HTTPException(502, f"Agora stop-agent failed: {exc}") from exc
    rooms.clear_voice(STATE, room_id)
    return {"stopped": True}
