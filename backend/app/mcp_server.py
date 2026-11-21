"""Aangan as an MCP server, so other agents (Claude, Cursor, an Agora or LangGraph agent...) can use the family's tools.

Transport: MCP "Streamable HTTP", answered as plain JSON (no streaming, no sessions), at POST /mcp. Every specialist agent's tool
is exposed as `<agent>_<tool>` (for example `tasks_add_task`, `travel_search_flights`), plus two helpers:
`ask_aangan` (say something to Aangan in plain language, exactly as a family member would) and `family_members`.
The tools run against the same shared household as the app, and are logged in the same activity feed under their agent.

Auth: `Authorization: Bearer <MCP_API_KEY>` (falls back to LLM_API_KEY). With neither set the endpoint is open, which is only
sensible on localhost. A browser page on another origin is refused either way.
"""

from __future__ import annotations

import hmac
import json
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from . import orchestrator, persistence
from .agents import REGISTRY
from .config import settings
from .state import STATE
from .toolkit import run_tool

log = logging.getLogger("aangan.mcp")

router = APIRouter()

SERVER_INFO = {"name": "aangan", "title": "Aangan family assistant", "version": "1.0.0"}
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "Aangan is one family's shared assistant: travel, calendar, dining, school, senior care, household memory, money, tasks and "
    "shopping, and a virtual smart home. Use `ask_aangan` for anything you would say to a person in plain language; use the "
    "`<agent>_<tool>` tools when you know exactly what to do. Tools that book, add or change things act on the real shared household."
)

# Names that only read; clients can run these without asking the user.
_READ_ONLY_PREFIXES = ("get_", "list_", "search_", "find_", "check_", "show_", "read_", "lookup_", "estimate_", "compare_")


def _tool_name(agent: str, tool: str) -> str:
    return f"{agent}_{tool}"


def _read_only(tool: str) -> bool:
    return tool.startswith(_READ_ONLY_PREFIXES)


def _catalogue() -> dict[str, tuple[str, Any]]:
    """MCP tool name -> (agent name, Tool). Built per request so a newly registered agent shows up without a restart."""
    return {_tool_name(a.name, t.name): (a.name, t) for a in REGISTRY for t in a.tools}


def _object_schema(schema: dict | None) -> dict:
    schema = dict(schema or {})
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return schema


_HELPERS = [
    {
        "name": "ask_aangan",
        "title": "Ask Aangan",
        "description": (
            "Say something to Aangan in plain language and get its reply, as a family member would: 'plan my day', 'add milk to the "
            "shopping list', 'remind Rahul to pay the electricity bill tomorrow', 'book a table for four on Saturday'. Aangan picks the "
            "right specialist and uses its tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to say to Aangan."},
                "member": {"type": "string", "description": "Who is speaking: a family member's name or id. Defaults to the household's current person."},
            },
            "required": ["message"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "family_members",
        "title": "Family members",
        "description": "List the people in this household (id, name, role, languages), to use as the `member` of ask_aangan or in tool arguments.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


def list_mcp_tools() -> list[dict]:
    tools = list(_HELPERS)
    for name, (agent, tool) in _catalogue().items():
        tools.append(
            {
                "name": name,
                "title": f"{agent.replace('_', ' ').title()}: {tool.name.replace('_', ' ')}",
                "description": tool.description,
                "inputSchema": _object_schema(tool.parameters),
                "annotations": {"readOnlyHint": _read_only(tool.name), "destructiveHint": False, "openWorldHint": False},
            }
        )
    return tools


def _text(payload: Any, *, error: bool = False) -> dict:
    result: dict[str, Any] = {"content": [{"type": "text", "text": payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)}]}
    if isinstance(payload, dict):
        result["structuredContent"] = payload
    if error:
        result["isError"] = True
    return result


def _find_member(who: str) -> str | None:
    if not STATE.members:
        return None
    if not who:
        return STATE.persona or STATE.members[0]["id"]
    low = who.strip().lower()
    for m in STATE.members:
        if low in (m["id"].lower(), str(m.get("name", "")).lower()):
            return m["id"]
    for m in STATE.members:  # "rahul" for "Rahul Sharma"
        if str(m.get("name", "")).lower().split(" ")[0] == low:
            return m["id"]
    return None


def call_mcp_tool(name: str, args: dict) -> dict:
    """Run one tool. Failures the caller can fix (bad arguments, a refused action) come back as isError results, not protocol errors."""
    if name == "family_members":
        return _text({"members": [{k: m.get(k) for k in ("id", "name", "role", "language") if k in m} for m in STATE.members]})
    if name == "ask_aangan":
        message = str(args.get("message", "")).strip()
        if not message:
            return _text("Say something: `message` is empty.", error=True)
        member_id = _find_member(str(args.get("member", "")))
        if member_id is None:
            known = ", ".join(m["name"] for m in STATE.members) or "nobody yet: set up the family first"
            return _text(f"No family member matches '{args.get('member', '')}'. Known: {known}.", error=True)
        reply = orchestrator.converse(STATE, member_id, message)
        _save()
        return _text({"reply": reply, "member": member_id})

    entry = _catalogue().get(name)
    if entry is None:
        raise KeyError(name)
    agent, tool = entry
    try:
        status, result = run_tool(STATE, agent, tool, args)
    except TypeError as exc:
        return _text(f"Bad arguments for {name}: {exc}", error=True)
    if not _read_only(tool.name):
        _save()
    return _text(result, error=(status != "ok"))


def _save() -> None:
    try:
        persistence.save(STATE)
    except Exception as exc:  # the household is still changed in memory
        log.warning("could not save the household: %s", exc)


# --- JSON-RPC

def _error(rid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle_message(msg: Any) -> dict | None:
    """One JSON-RPC message in, the response out (None for a notification, which gets none)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid request")
    method, rid = msg.get("method"), msg.get("id")
    params = msg.get("params") or {}
    if method is None:  # a response to something we never asked
        return None
    if "id" not in msg:  # notification: notifications/initialized, notifications/cancelled...
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS},
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": list_mcp_tools()}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(args, dict):
            return _error(rid, -32602, "tools/call needs a tool `name` and an `arguments` object")
        try:
            return {"jsonrpc": "2.0", "id": rid, "result": call_mcp_tool(name, args)}
        except KeyError:
            return _error(rid, -32602, f"Unknown tool: {name}")
        except Exception as exc:  # a tool bug must not take the endpoint down
            log.exception("tool %s failed", name)
            return {"jsonrpc": "2.0", "id": rid, "result": _text(f"{name} failed: {exc}", error=True)}
    if method in ("resources/list", "prompts/list"):  # not offered, but clients that probe get an empty list rather than an error
        return {"jsonrpc": "2.0", "id": rid, "result": {method.split("/")[0]: []}}
    return _error(rid, -32601, f"Method not found: {method}")


# --- HTTP

def _expected_key() -> str:
    cfg = settings()
    return cfg.mcp_api_key or cfg.llm_api_key


def _origin_ok(request: Request) -> bool:
    """A page on another site must not drive this endpoint from a visitor's browser (DNS rebinding). Non-browser clients send no Origin."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return (urlparse(origin).netloc or "").lower() == (request.headers.get("host") or "").lower()


def _authorised(request: Request) -> bool:
    key = _expected_key()
    if not key:
        return True
    supplied = request.headers.get("authorization", "")
    return hmac.compare_digest(supplied.encode(), f"Bearer {key}".encode())


@router.post("/mcp")
async def mcp_post(request: Request):
    if not _origin_ok(request):
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    if not _authorised(request):
        return JSONResponse({"error": "invalid or missing bearer token"}, status_code=401, headers={"WWW-Authenticate": 'Bearer realm="aangan"'})
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)

    from starlette.concurrency import run_in_threadpool

    if isinstance(body, list):  # a batch
        if not body:
            return JSONResponse(_error(None, -32600, "Invalid request: empty batch"), status_code=400)
        replies = [r for r in [await run_in_threadpool(handle_message, m) for m in body] if r is not None]
        if not replies:
            return Response(status_code=202)
        return JSONResponse(replies)
    reply = await run_in_threadpool(handle_message, body)
    if reply is None:
        return Response(status_code=202)
    return JSONResponse(reply)


@router.get("/mcp")
@router.delete("/mcp")
async def mcp_other():
    """This server keeps no sessions and sends no server-initiated messages, so there is no stream to open or session to end."""
    return Response(status_code=405, headers={"Allow": "POST"})
