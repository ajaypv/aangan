"""Aangan as an MCP server: the handshake, the tool list, calling tools against the shared household, and who may call."""

import warnings

import pytest
from fastapi.testclient import TestClient

from app.agents import REGISTRY
from app.main import STATE, app

warnings.filterwarnings("ignore")
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("FORCE_MOCK", "1")
    monkeypatch.setattr("app.toolkit.time.sleep", lambda s: None)
    STATE.reset(demo=True)


def rpc(method, params=None, rid=1, headers=None):
    body = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers or {})


def call(name, args=None):
    res = rpc("tools/call", {"name": name, "arguments": args or {}})
    assert res.status_code == 200
    return res.json()["result"]


def test_initialize_negotiates_a_version_and_offers_tools():
    res = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["serverInfo"]["name"] == "aangan" and "tools" in res["capabilities"]
    old = rpc("initialize", {"protocolVersion": "2024-11-05"}).json()["result"]
    assert old["protocolVersion"] == "2024-11-05"
    unknown = rpc("initialize", {"protocolVersion": "1999-01-01"}).json()["result"]
    assert unknown["protocolVersion"] == "2025-06-18"  # we answer with the newest we speak; the client decides


def test_notifications_get_no_body_and_ping_answers():
    res = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert res.status_code == 202 and res.content == b""
    assert rpc("ping").json()["result"] == {}


def test_every_agent_tool_is_listed_once_with_an_object_schema():
    tools = rpc("tools/list").json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names))
    for agent in REGISTRY:
        for t in agent.tools:
            assert f"{agent.name}_{t.name}" in names
    assert {"ask_aangan", "family_members"} <= set(names)
    for t in tools:
        assert t["inputSchema"]["type"] == "object" and t["description"]
        assert all(c.isalnum() or c in "_-" for c in t["name"])  # the characters MCP allows in a tool name


def test_reading_tools_are_marked_read_only():
    tools = {t["name"]: t for t in rpc("tools/list").json()["result"]["tools"]}
    assert tools["tasks_get_shopping_list"]["annotations"]["readOnlyHint"] is True
    assert tools["tasks_add_task"]["annotations"]["readOnlyHint"] is False


def test_a_tool_runs_against_the_shared_household_and_is_logged():
    before = len(STATE.events) if hasattr(STATE, "events") else None
    result = call("tasks_add_shopping_items", {"items": ["oat milk"]})
    assert "isError" not in result
    listed = call("tasks_get_shopping_list")["structuredContent"]
    assert "oat milk" in str(listed).lower()
    assert "oat milk" in str(STATE.domains["tasks"]).lower()  # the app sees what the other agent did
    if before is not None:
        assert len(STATE.events) > before


def test_ask_aangan_answers_in_plain_language_as_a_named_member():
    out = call("ask_aangan", {"message": "add eggs to the shopping list", "member": "rahul"})
    assert "isError" not in out and out["structuredContent"]["member"] == "rahul" and out["structuredContent"]["reply"]
    assert "eggs" in str(STATE.domains["tasks"]).lower()


def test_ask_aangan_without_a_member_uses_the_current_person_and_rejects_strangers():
    assert call("ask_aangan", {"message": "what is pending"})["structuredContent"]["member"] == STATE.persona
    bad = call("ask_aangan", {"message": "hello", "member": "Zorg"})
    assert bad["isError"] is True and "Rahul" in bad["content"][0]["text"]
    assert call("ask_aangan", {"message": "  "})["isError"] is True


def test_family_members_lists_the_household():
    members = call("family_members")["structuredContent"]["members"]
    assert {"priya", "rahul"} <= {m["id"] for m in members}


def test_bad_arguments_are_a_tool_error_the_caller_can_fix_not_a_protocol_error():
    out = call("tasks_add_task", {"nonsense": 1})
    assert out["isError"] is True
    assert "error" not in rpc("tools/call", {"name": "tasks_add_task", "arguments": {"nonsense": 1}}).json()


def test_a_tool_that_refuses_reports_is_error():
    out = call("tasks_complete_task", {"task": "no such task anywhere"})
    assert out["isError"] is True and "error" in out["structuredContent"]


def test_unknown_tool_and_method_are_protocol_errors():
    assert rpc("tools/call", {"name": "nope_nothing", "arguments": {}}).json()["error"]["code"] == -32602
    assert rpc("tools/call", {"arguments": {}}).json()["error"]["code"] == -32602
    assert rpc("does/not/exist").json()["error"]["code"] == -32601
    assert client.post("/mcp", content=b"{not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/mcp", json=[]).status_code == 400  # an empty batch is invalid


def test_a_batch_returns_one_reply_per_request():
    res = client.post("/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    assert [r["id"] for r in res.json()] == [1, 2]


def test_get_and_delete_are_not_allowed():
    assert client.get("/mcp").status_code == 405 and client.delete("/mcp").status_code == 405


def test_open_without_a_key_but_a_key_is_enforced_once_set(monkeypatch):
    assert rpc("ping").status_code == 200
    monkeypatch.setenv("MCP_API_KEY", "s3cret")
    denied = rpc("ping")
    assert denied.status_code == 401 and denied.headers["www-authenticate"].startswith("Bearer")
    assert rpc("ping", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert rpc("ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_the_voice_secret_protects_it_when_no_separate_key_is_set(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "voice-secret")
    assert rpc("ping").status_code == 401
    assert rpc("ping", headers={"Authorization": "Bearer voice-secret"}).status_code == 200
    monkeypatch.setenv("MCP_API_KEY", "own-key")  # a dedicated key wins, and the voice secret stops working here
    assert rpc("ping", headers={"Authorization": "Bearer voice-secret"}).status_code == 401
    assert rpc("ping", headers={"Authorization": "Bearer own-key"}).status_code == 200


def test_a_web_page_on_another_origin_is_refused():
    assert rpc("ping", headers={"Origin": "https://evil.example"}).status_code == 403
    assert rpc("ping", headers={"Origin": "http://testserver"}).status_code == 200  # the page served by this very host
