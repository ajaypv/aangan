from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import orchestrator
from app.agents import BY_NAME
from app.agents.smart_home import HOUSE_ID, control_door, control_lights, control_tv, link_house, youtube_video_id
from app.main import app
from app.state import FamilyState
from app.toolkit import ToolError


@pytest.fixture
def house(monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    state = FamilyState()
    link_house(state, HOUSE_ID, True)
    return state


@pytest.mark.parametrize(("text", "room", "on"), [
    ("Turn off the kitchen lights", "kitchen", False),
    ("off the light", "all", False),
    ("Switch all lights off", "all", False),
    ("Please turn off the lights in the bedroom", "bedroom", False),
    ("Can you turn on the living room light?", "living", True),
])
def test_agent_controls_only_the_requested_room(house, text, room, on):
    control_lights(house, "all", on=not on)
    reply = orchestrator.converse(house, "priya", text)
    lights = house.domains["smart_home"]["lights"]
    for key, value in lights.items():
        assert value["on"] is (on if room in ("all", key) else not on)
    assert "virtual house" in reply
    assert house.events[-1]["tool"] == "control_lights"
    assert house.events[-1]["status"] == "ok"


def test_dimming_and_streamed_voice_backend_share_the_same_tools(house):
    reply = "".join(orchestrator.converse_stream(house, "priya", "Set bedroom lights to 30 percent"))
    assert "30" in reply or "thirty" in reply
    assert house.domains["smart_home"]["lights"]["bedroom"]["brightness"] == 30
    reply = "".join(orchestrator.converse_stream(house, "priya", "Open the front door"))
    assert "opened" in reply
    assert house.domains["smart_home"]["doors"]["front"]["open"] is True
    orchestrator.converse(house, "priya", "Close the front door")
    assert house.domains["smart_home"]["doors"]["front"]["open"] is False


@pytest.mark.parametrize("text", [
    "Don't turn off the lights",
    "Turn off the garage lights",
    "Turn off the kitchen lights and open the front door",
    "Open the door",
    "Set bedroom lights to 101 percent",
])
def test_unclear_or_invalid_commands_do_not_change_the_house(house, text):
    before = deepcopy(house.domains["smart_home"])
    orchestrator.converse(house, "priya", text)
    assert house.domains["smart_home"] == before


def test_unlink_revokes_tools_and_relink_preserves_device_state(house):
    control_lights(house, "kitchen", on=False)
    link_house(house, HOUSE_ID, False)
    for tool, args in [("control_lights", {"room": "all", "on": True}), ("control_door", {"door": "front", "open": True})]:
        status, result = BY_NAME["smart_home"].call(house, tool, **args)
        assert status == "error" and "Settings" in result["error"]
    link_house(house, HOUSE_ID, True)
    assert house.domains["smart_home"]["lights"]["kitchen"]["on"] is False
    assert house.domains["smart_home"]["doors"]["front"]["open"] is False


@pytest.mark.parametrize("kwargs", [
    {"room": "garage", "on": False},
    {"room": "all", "on": "false"},
    {"room": "all", "brightness": True},
    {"room": "all", "brightness": -1},
    {"room": "all", "brightness": 12.5},
    {"room": "all", "on": True, "brightness": 0},
    {"room": "all"},
])
def test_tool_validation_is_atomic(house, kwargs):
    before = deepcopy(house.domains["smart_home"])
    with pytest.raises(ToolError):
        control_lights(house, **kwargs)
    assert house.domains["smart_home"] == before


def test_zero_brightness_can_be_turned_back_on_and_snapshots_are_independent(house):
    result = control_lights(house, "bedroom", brightness=0)
    assert result["house"]["lights"]["bedroom"]["on"] is False
    control_lights(house, "bedroom", on=True)
    assert house.domains["smart_home"]["lights"]["bedroom"]["brightness"] == 80
    assert result["house"]["lights"]["bedroom"]["on"] is False


def test_house_survives_reload_and_older_households_start_unlinked(house):
    control_lights(house, "kitchen", on=False)
    control_door(house, "bedroom", open=True)
    saved = deepcopy(house.to_dict())
    restored = FamilyState(demo=False)
    restored.apply_dict(saved)
    assert restored.domains["smart_home"] == house.domains["smart_home"]
    del saved["domains"]["smart_home"]
    restored.apply_dict(saved)
    assert restored.domains["smart_home"]["linked"] is False
    assert len(restored.domains["smart_home"]["lights"]) == 4


def test_settings_api_link_to_ai_to_viewer_and_disk(monkeypatch):
    from app import house_api, main, persistence

    state = FamilyState()
    monkeypatch.setattr(main, "STATE", state)
    monkeypatch.setattr(house_api, "STATE", state)
    client = TestClient(app)
    assert client.get("/api/house").json()["linked"] is False
    assert client.post("/api/house/link", json={"house_id": "external-house", "linked": True}).status_code == 422
    assert client.post("/api/house/link", json={"house_id": HOUSE_ID, "linked": "false"}).status_code == 422
    assert client.post("/api/house/link", json={"house_id": HOUSE_ID, "linked": True}).json()["linked"] is True
    response = client.post("/api/converse", json={"member_id": "priya", "message": "Turn off the kitchen lights"})
    assert response.status_code == 200 and "off" in response.json()["reply"]
    assert client.get("/api/house").json()["lights"]["kitchen"]["on"] is False
    restored = FamilyState(demo=False)
    assert persistence.load(restored)
    assert restored.domains["smart_home"] == state.domains["smart_home"]
    client.post("/api/house/link", json={"house_id": HOUSE_ID, "linked": False})
    blocked = client.post("/api/tool/smart_home/control_door", json={"args": {"door": "front", "open": True}})
    assert blocked.json()["status"] == "error"


def test_no_household_cannot_link():
    with pytest.raises(ToolError, match="Set up your family"):
        link_house(FamilyState(demo=False), HOUSE_ID, True)


def test_flexible_requests_can_reach_the_llm_instead_of_being_consumed_by_rules(house):
    assert orchestrator._fast_rule_reply(house, "priya", "Could you make the bedroom lights a little dimmer for reading?", True) is None
    assert orchestrator._fast_rule_reply(house, "priya", "Turn off the kitchen lights and open the front door", True) is None


def test_tv_commands_and_streaming_preserve_video_case_and_other_devices(house):
    before = deepcopy(house.domains["smart_home"])
    reply = orchestrator.converse(house, "priya", "Play https://youtu.be/M7lc1UVf-VE on the TV")
    assert "TV turned on" in reply
    assert house.domains["smart_home"]["tv"] == {"on": True, "video_id": "M7lc1UVf-VE"}
    reply = "".join(orchestrator.converse_stream(house, "priya", "Turn off the television"))
    assert "TV turned off" in reply
    assert house.domains["smart_home"]["tv"]["on"] is False
    orchestrator.converse(house, "priya", "Switch the TV on")
    assert house.domains["smart_home"]["tv"]["on"] is True
    assert house.domains["smart_home"]["lights"] == before["lights"]
    assert house.domains["smart_home"]["doors"] == before["doors"]
    assert house.events[-1]["tool"] == "control_tv" and house.events[-1]["status"] == "ok"


@pytest.mark.parametrize("link", [
    "M7lc1UVf-VE", "https://youtu.be/M7lc1UVf-VE?t=5",
    "https://www.youtube.com/watch?v=M7lc1UVf-VE&list=ignored",
    "https://www.youtube.com/shorts/M7lc1UVf-VE",
    "https://www.youtube-nocookie.com/embed/M7lc1UVf-VE",
])
def test_youtube_links_are_normalized_to_video_ids(link):
    assert youtube_video_id(link) == "M7lc1UVf-VE"


@pytest.mark.parametrize("kwargs", [
    {"on": "false"}, {"on": True, "video_url": "https://example.com/watch?v=M7lc1UVf-VE"},
    {"on": True, "video_url": "https://youtube.com.evil.test/watch?v=M7lc1UVf-VE"},
    {"on": True, "video_url": "javascript:alert(1)"},
    {"on": True, "video_url": "https://www.youtube.com/playlist?list=123"},
    {"on": True, "video_url": "https://user@youtube.com/watch?v=M7lc1UVf-VE"},
    {"on": True, "video_url": "https://youtube.com:invalid/watch?v=M7lc1UVf-VE"},
])
def test_bad_tv_commands_leave_state_unchanged(house, kwargs):
    before = deepcopy(house.domains["smart_home"])
    with pytest.raises(ToolError):
        control_tv(house, **kwargs)
    assert house.domains["smart_home"] == before


def test_tv_state_migrates_persists_and_requires_link(house):
    saved = deepcopy(house.to_dict())
    del saved["domains"]["smart_home"]["tv"]
    restored = FamilyState(demo=False)
    restored.apply_dict(saved)
    assert restored.domains["smart_home"]["tv"]["on"] is False
    assert restored.domains["smart_home"]["linked"] is True
    control_tv(restored, on=True, video_url="M7lc1UVf-VE")
    reloaded = FamilyState(demo=False)
    reloaded.apply_dict(deepcopy(restored.to_dict()))
    assert reloaded.domains["smart_home"]["tv"] == restored.domains["smart_home"]["tv"]
    link_house(reloaded, HOUSE_ID, False)
    status, result = BY_NAME["smart_home"].call(reloaded, "control_tv", on=False)
    assert status == "error" and "Settings" in result["error"]
    assert reloaded.domains["smart_home"]["tv"]["on"] is True
