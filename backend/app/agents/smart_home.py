"""Controls for the linked virtual house. Never sends commands to physical devices."""

import re
from copy import deepcopy
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from ..toolkit import Tool, ToolError
from .base import Specialist

if TYPE_CHECKING:
    from ..state import FamilyState

HOUSE_ID = "cozy-home"
ROOMS = {"living": "Living room", "kitchen": "Kitchen", "bedroom": "Bedroom", "reading": "Reading nook"}
DOORS = {"front": "Front door", "bedroom": "Bedroom door"}
DEFAULT_VIDEO_ID = "M7lc1UVf-VE"
ALIASES = {
    "living": "living", "living room": "living", "lounge": "living",
    "kitchen": "kitchen", "dining": "kitchen", "dining room": "kitchen",
    "bedroom": "bedroom", "upstairs": "bedroom", "reading": "reading", "reading nook": "reading",
    "all": "all", "house": "all", "whole house": "all",
}


def initial_tv() -> dict:
    return {"on": False, "video_id": DEFAULT_VIDEO_ID}


def initial_house() -> dict:
    return {
        "id": HOUSE_ID, "name": "Cozy home", "linked": False, "revision": 0,
        "lights": {key: {"name": name, "on": True, "brightness": 80} for key, name in ROOMS.items()},
        "doors": {key: {"name": name, "open": False} for key, name in DOORS.items()},
        "tv": initial_tv(),
        "last_action": "Link this virtual house in Settings to control it with Aangan.",
    }


def get_house_state(state: "FamilyState") -> dict:
    with state.lock:
        return deepcopy(state.domains["smart_home"])


def link_house(state: "FamilyState", house_id: str, linked: bool) -> dict:
    if house_id != HOUSE_ID:
        raise ToolError("Unknown house. Open the Cozy home link provided in Settings.")
    if not state.members:
        raise ToolError("Set up your family before linking a house.")
    with state.lock:
        house = state.domains["smart_home"]
        house["linked"] = linked
        house["revision"] += 1
        house["last_action"] = "Virtual house linked to Aangan." if linked else "House unlinked. AI controls are disabled."
        return deepcopy(house)


def _linked(state: "FamilyState") -> dict:
    house = state.domains["smart_home"]
    if not house["linked"]:
        raise ToolError("No house is linked. Open Settings, then link the virtual house first.")
    return house


def control_lights(state: "FamilyState", room: str, on: bool | None = None, brightness: int | None = None) -> dict:
    target = ALIASES.get(room.strip().lower()) if isinstance(room, str) else None
    if target is None:
        raise ToolError("Unknown room. Choose living room, kitchen, bedroom, reading nook or all.")
    if on is not None and type(on) is not bool:
        raise ToolError("on must be true or false.")
    if brightness is not None and (type(brightness) is not int or not 0 <= brightness <= 100):
        raise ToolError("Brightness must be a whole number from 0 to 100.")
    if on is None and brightness is None:
        raise ToolError("Specify on, off or a brightness.")
    if on is True and brightness == 0:
        raise ToolError("Zero brightness means off. Choose a positive brightness to turn a light on.")
    with state.lock:
        house = _linked(state)
        targets = list(ROOMS) if target == "all" else [target]
        for key in targets:
            light = house["lights"][key]
            if brightness is not None:
                light["brightness"] = brightness
                light["on"] = brightness > 0
            if on is not None:
                light["on"] = on
                if on and light["brightness"] == 0:
                    light["brightness"] = 80
        label = "All lights" if target == "all" else f"{ROOMS[target]} lights"
        value = f"set to {brightness}%" if brightness is not None and on is not False else ("on" if on else "off")
        house["last_action"] = f"{label} {value} in the virtual house."
        house["revision"] += 1
        return {"message": house["last_action"], "house": deepcopy(house)}


def control_door(state: "FamilyState", door: str, open: bool) -> dict:
    if door not in DOORS:
        raise ToolError("Choose the front door or bedroom door.")
    if type(open) is not bool:
        raise ToolError("open must be true or false.")
    with state.lock:
        house = _linked(state)
        house["doors"][door]["open"] = open
        house["last_action"] = f"{DOORS[door]} {'opened' if open else 'closed'} in the virtual house."
        house["revision"] += 1
        return {"message": house["last_action"], "house": deepcopy(house)}


def youtube_video_id(value: str) -> str:
    if not isinstance(value, str):
        raise ToolError("Use a YouTube video link or an 11-character video ID.")
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    try:
        url = urlsplit(value)
        valid = url.scheme == "https" and not url.username and not url.password and url.port in (None, 443)
        video_id = ""
        if valid and url.hostname in ("youtu.be", "www.youtu.be"):
            video_id = url.path.removeprefix("/")
        elif valid and url.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "www.youtube-nocookie.com"):
            if url.path == "/watch":
                video_id = parse_qs(url.query).get("v", [""])[0]
            elif re.fullmatch(r"/(?:embed|shorts)/[A-Za-z0-9_-]{11}", url.path):
                video_id = url.path.rsplit("/", 1)[1]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return video_id
    except ValueError:
        pass
    raise ToolError("Use a valid HTTPS YouTube video link, not a playlist or another website.")


def control_tv(state: "FamilyState", on: bool, video_url: str | None = None) -> dict:
    if type(on) is not bool:
        raise ToolError("on must be true or false.")
    video_id = youtube_video_id(video_url) if video_url is not None else None
    with state.lock:
        house = _linked(state)
        if video_id is not None:
            house["tv"]["video_id"] = video_id
        house["tv"]["on"] = on
        house["last_action"] = "TV turned on in the virtual house. YouTube may need a tap to play." if on else "TV turned off in the virtual house."
        house["revision"] += 1
        return {"message": house["last_action"], "house": deepcopy(house)}


class SmartHomeAgent(Specialist):
    name = "smart_home"
    title = "Virtual house"
    tools = [
        Tool("get_house_state", "Read the virtual house link, room lights, brightness, doors and YouTube TV. These are simulated devices, not a physical home.",
             {"type": "object", "properties": {}, "additionalProperties": False}, get_house_state),
        Tool("control_lights", "Set lights in the linked virtual house. An unspecified light means all lights; never guess an unknown room. Brightness is 0-100.",
             {"type": "object", "properties": {
                 "room": {"type": "string", "enum": [*ROOMS, "all"]},
                 "on": {"type": "boolean"},
                 "brightness": {"type": "integer", "minimum": 0, "maximum": 100},
             }, "required": ["room"], "additionalProperties": False}, control_lights),
        Tool("control_door", "Open or close a door in the linked virtual 3D house only. Ask which door if unspecified. No physical locks are connected.",
             {"type": "object", "properties": {
                 "door": {"type": "string", "enum": list(DOORS)}, "open": {"type": "boolean"},
             }, "required": ["door", "open"], "additionalProperties": False}, control_door),
        Tool("control_tv", "Turn the linked virtual house TV on/off. Optionally set a YouTube video using a user-provided HTTPS link or exact video ID; never invent a video ID. Power off stops the embedded player. Browser policy may require a tap to play or unmute.",
             {"type": "object", "properties": {
                 "on": {"type": "boolean"}, "video_url": {"type": "string"},
             }, "required": ["on"], "additionalProperties": False}, control_tv),
    ]

    def seed(self) -> dict:
        return initial_house()

    def score(self, state: "FamilyState", text: str) -> int:
        return 5 if re.search(r"\b(lights?|lamps?|doors?|tv|television|virtual house|smart home)\b", text, re.I) else 0

    def handle(self, state: "FamilyState", member_id: str, text: str) -> str | None:
        if not self.score(state, text):
            return None
        low = re.sub(r"\b(please|can you|could you|would you)\b", "", text.lower()).strip(" .?!,")
        low = re.sub(r"\s+", " ", low)
        tv = r"(?:the |my |our )?(?:living room )?(?:tv|television)"
        match = re.fullmatch(rf"(?:(?:turn|switch|power)\s+)?(?P<power>on|off)\s+{tv}", low)
        if not match:
            match = re.fullmatch(rf"(?:(?:turn|switch|power)\s+)?{tv}\s+(?P<power>on|off)", low)
        if match:
            status, result = self.call(state, "control_tv", on=match["power"] == "on")
            return result["message"] if status == "ok" else result["error"]
        # Preserve the case-sensitive video ID from the original utterance.
        match = re.fullmatch(rf"(?:please\s+)?play\s+(?P<url>https://\S+)\s+on\s+{tv}[.!?]?", text.strip(), re.I)
        if match:
            status, result = self.call(state, "control_tv", on=True, video_url=match["url"])
            return result["message"] if status == "ok" else result["error"]
        light = r"(?:(?:the|all|all the|my|our)\s+)?(?P<room>[a-z ]*?)(?:\s+)?(?:lights?|lamps?)"
        match = re.fullmatch(rf"(?:(?:turn|switch)\s+)?(?P<power>on|off)\s+{light}", low)
        if not match:
            match = re.fullmatch(rf"(?:(?:turn|switch)\s+)?{light}\s+(?P<power>on|off)", low)
        if not match:
            match = re.fullmatch(rf"(?:(?:turn|switch)\s+)?(?P<power>on|off)\s+(?:the\s+)?(?:lights?|lamps?)\s+in\s+(?:the\s+)?(?P<room>[a-z ]+)", low)
        if match:
            room = match["room"].strip() or "all"
            status, result = self.call(state, "control_lights", room=room, on=match["power"] == "on")
            return result["message"] if status == "ok" else result["error"]
        match = re.fullmatch(rf"(?:dim|set)\s+{light}\s+to\s+(?P<brightness>\d+)\s*(?:%|percent)", low)
        if match:
            status, result = self.call(state, "control_lights", room=match["room"].strip() or "all", brightness=int(match["brightness"]))
            return result["message"] if status == "ok" else result["error"]
        match = re.fullmatch(r"(?P<action>open|close|shut)\s+(?:the\s+)?(?P<door>front|bedroom)\s+door", low)
        if match:
            status, result = self.call(state, "control_door", door=match["door"], open=match["action"] == "open")
            return result["message"] if status == "ok" else result["error"]
        if re.fullmatch(r"(?:show|check)(?: me)? (?:the )?(?:house|virtual house|smart home|lights|doors|tv|television)(?: status)?", low):
            _, house = self.call(state, "get_house_state")
            if not house["linked"]:
                return "No house is linked. Link the virtual house in Settings first."
            return "Virtual house: " + "; ".join(f"{v['name']} lights {'on' if v['on'] else 'off'}" for v in house["lights"].values()) + ". " + "; ".join(f"{v['name']} {'open' if v['open'] else 'closed'}" for v in house["doors"].values()) + f". TV {'on' if house['tv']['on'] else 'off'}."
        return None
