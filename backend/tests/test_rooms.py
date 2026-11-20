"""Family Rooms: the API contract, presence, approvals, persistence, the voice path and the Agora session start.
Everything is offline: the model is a scripted fake and Agora and live flight search are patched out."""

import json
import threading
import warnings
from types import SimpleNamespace

import pytest
from agora_agent.agents.client import AgentsClient
from fastapi.testclient import TestClient

from app import agora, persistence, planner, rooms
from app.config import settings
from app.main import STATE, app
from app.state import FamilyState

warnings.filterwarnings("ignore")
client = TestClient(app)

LIVE_ENV = {
    "AGORA_APP_ID": "a" * 32, "AGORA_APP_CERTIFICATE": "b" * 32, "MURF_API_KEY": "murf-key",
    "PUBLIC_BASE_URL": "https://abc.trycloudflare.com", "LLM_API_KEY": "llm-secret",
}


# ---- scripted streaming model (same chunk shapes the gateway sends) ----


def delta(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=calls))])


def tool_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def words(*pieces):
    return [delta(p) for p in pieces]


def calls_round(*calls, say=None):
    chunks = [delta(say)] if say else []
    for i, (name, args) in enumerate(calls):
        raw = args if isinstance(args, str) else json.dumps(args)
        half = len(raw) // 2
        chunks.append(delta(calls=[tool_delta(i, id=f"c{i}", name=name, arguments=raw[:half])]))
        chunks.append(delta(calls=[tool_delta(i, arguments=raw[half:])]))
    return chunks


class StreamClient:
    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return iter(self.rounds.pop(0) if len(self.rounds) > 1 else self.rounds[0])


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    STATE.reset(demo=True)
    agora.SESSION.clear()
    rooms._PLAN_LOCKS.clear()
    # nothing in this file may reach the network: live flight search finds nothing unless a test says otherwise
    monkeypatch.setattr(planner, "_live_search", lambda *a, **k: [])


@pytest.fixture
def inline(monkeypatch):
    """Background work runs where it is called, so a test sees its result straight away."""
    monkeypatch.setattr(rooms, "spawn", lambda fn, *a, **k: fn(*a, **k))


@pytest.fixture
def model(monkeypatch, inline):
    """An AI key is 'set' and each planning turn gets the next scripted client."""
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    queue: list = []
    monkeypatch.setattr(planner, "_client", lambda: queue.pop(0) if len(queue) > 1 else queue[0])
    return queue


@pytest.fixture
def live_env(monkeypatch):
    for key, value in LIVE_ENV.items():
        monkeypatch.setenv(key, value)


def new_room(member="priya", title="Goa trip"):
    resp = client.post("/api/rooms", json={"title": title, "member_id": member})
    assert resp.status_code == 200, resp.text
    return resp.json()


def join(room_id, **body):
    resp = client.post(f"/api/rooms/{room_id}/join", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def say(room_id, pid, text, **extra):
    resp = client.post(f"/api/rooms/{room_id}/message", json={"participant_id": pid, "text": text, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def get(room_id, since=None):
    return client.get(f"/api/rooms/{room_id}" + (f"?since={since}" if since is not None else "")).json()


# ---- create, join, errors ----


def test_create_room_makes_the_creator_host_and_participant():
    room = new_room()
    assert room["id"].startswith("r-") and room["title"] == "Goa trip" and room["version"] >= 1
    host = room["participants"][0]
    assert room["host_participant_id"] == host["id"] == "p-1"
    assert host["name"] == "Priya" and host["member_id"] == "priya" and host["guest"] is False and host["online"] is True
    assert isinstance(host["rtc_uid"], int) and host["rtc_uid"] != 123456
    assert room["plan"]["destination"] is None and room["plan"]["flights"] == [] and room["pending_approval"] is None
    assert room["bookings"] == [] and room["agent"] == {"live": False, "voice_session": None}
    assert not [k for k in room if k.startswith("_")] and not [k for p in room["participants"] for k in p if k.startswith("_")]


def test_creating_needs_a_household_and_a_known_member():
    STATE.reset(demo=False)
    assert client.post("/api/rooms", json={"title": "x", "member_id": "priya"}).status_code == 409
    STATE.reset(demo=True)
    assert client.post("/api/rooms", json={"title": "x", "member_id": "nobody"}).status_code == 404


def test_join_member_guest_and_idempotent_join():
    room = new_room()
    rid = room["id"]
    first = join(rid, member_id="rahul")
    again = join(rid, member_id="rahul")
    assert first["participant"]["id"] == again["participant"]["id"] == "p-2"
    assert len(again["room"]["participants"]) == 2
    guest = join(rid, guest_name="Meera")["participant"]
    assert guest["name"] == "Meera (guest)" and guest["guest"] is True and guest["member_id"] is None
    assert join(rid, guest_name="meera")["participant"]["id"] == guest["id"]
    uids = [p["rtc_uid"] for p in get(rid)["participants"]]
    assert len(set(uids)) == 3 and 123456 not in uids


def test_unknown_room_participant_and_bad_bodies():
    rid = new_room()["id"]
    assert client.get("/api/rooms/r-nope").json() == {"detail": "unknown room"}
    assert client.post("/api/rooms/r-nope/join", json={"guest_name": "x"}).status_code == 404
    assert client.post(f"/api/rooms/{rid}/join", json={}).status_code == 400
    assert client.post(f"/api/rooms/{rid}/join", json={"member_id": "ghost"}).status_code == 404
    unknown = client.post(f"/api/rooms/{rid}/message", json={"participant_id": "p-9", "text": "hi"})
    assert unknown.status_code == 404 and unknown.json() == {"detail": "unknown participant"}
    assert client.post(f"/api/rooms/{rid}/message", json={"participant_id": "p-1", "text": "  "}).status_code == 400
    assert client.post(f"/api/rooms/{rid}/heartbeat", json={"participant_id": "p-9"}).status_code == 404


def test_version_goes_up_and_since_returns_unchanged():
    room = new_room()
    rid, v0 = room["id"], room["version"]
    assert get(rid, since=v0) == {"id": rid, "version": v0, "unchanged": True}
    joined = join(rid, guest_name="Meera")["room"]
    assert joined["version"] > v0
    assert get(rid, since=v0)["version"] == joined["version"] and "plan" in get(rid, since=v0)
    assert get(rid, since=joined["version"])["unchanged"] is True


# ---- messages and presence ----


def test_message_is_saved_and_returned_at_once(monkeypatch):
    monkeypatch.setattr(rooms, "spawn", lambda fn, *a, **k: None)  # planning is not what this tests
    rid = new_room()["id"]
    room = say(rid, "p-1", "Let's do Goa over Christmas, five days.")
    msg = room["messages"][-1]
    assert msg == {**msg, "id": 1, "kind": "user", "participant_id": "p-1", "name": "Priya", "lang": "en",
                   "text": "Let's do Goa over Christmas, five days."}
    assert len(msg["ts"]) == 5 and msg["ts"][2] == ":"


def test_heartbeat_presence_and_version(monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(rooms, "_time", lambda: clock["t"])
    room = new_room()
    rid = room["id"]
    guest = join(rid, guest_name="Meera")["participant"]
    assert {p["id"]: p["online"] for p in get(rid)["participants"]} == {"p-1": True, guest["id"]: True}
    v = get(rid)["version"]
    clock["t"] += 10
    assert client.post(f"/api/rooms/{rid}/heartbeat", json={"participant_id": guest["id"]}).json() == {"ok": True}
    assert get(rid)["version"] == v  # nobody went online or offline: nothing changed
    clock["t"] += 15  # p-1 is now 25 s quiet, Meera 15 s
    after = get(rid)
    assert {p["id"]: p["online"] for p in after["participants"]} == {"p-1": False, guest["id"]: True} and after["version"] > v
    client.post(f"/api/rooms/{rid}/heartbeat", json={"participant_id": "p-1"})
    assert get(rid)["participants"][0]["online"] is True


# ---- the planner in the background ----


def test_the_planner_updates_the_plan_through_tools_and_stays_silent(model):
    model.append(StreamClient(
        calls_round(
            ("set_destination", {"name": "Goa"}), ("set_origin", {"name": "Bengaluru"}),
            ("set_dates", {"start": "2026-12-26", "nights": 4}), ("set_budget", {"total": 80000}),
            ("add_preference", {"text": "Dadi needs step-free access"}),
        ),
        words("I would like to keep quiet."),  # not addressed: any words are dropped
    ))
    rid = new_room()["id"]
    room = say(rid, "p-1", "Let's do Goa over Christmas, five days, budget 80000")
    assert room["plan"]["destination"] is None  # the reply did not wait for the planner
    room = get(rid)
    plan = room["plan"]
    assert plan["destination"] == {"name": "Goa", "lat": 15.2993, "lon": 74.124}
    assert plan["origin"]["name"] == "Bengaluru" and plan["dates"] == {"start": "2026-12-26", "end": "2026-12-30"}
    assert plan["budget"] == {"total": 80000, "currency": "INR"} and "Dadi needs step-free access" in plan["preferences"]
    kinds = [m["kind"] for m in room["messages"]]
    assert "agent" not in kinds and kinds[-1] == "system"
    assert room["messages"][-1]["text"].startswith("Aangan updated")
    assert "I would like to keep quiet" not in json.dumps(room)


def test_addressed_message_gets_a_spoken_reply_in_the_messages_language(model):
    fake = StreamClient(calls_round(("set_goal", {"goal": "Family trip to Goa"})), words("Noted, ", "a trip to Goa."))
    model.append(fake)
    rid = new_room()["id"]
    say(rid, "p-1", "Aangan, let's plan a Goa trip")
    msgs = get(rid)["messages"]
    assert msgs[-1]["kind"] == "agent" and msgs[-1]["name"] == "Aangan" and msgs[-1]["text"] == "Noted, a trip to Goa."
    assert get(rid)["plan"]["goal"] == "Family trip to Goa"
    assert fake.calls[0]["model"] == "openai/gpt-5-nano" and fake.calls[0]["stream"] is True
    assert "IS addressed" in fake.calls[0]["messages"][1]["content"]


def test_hindi_message_uses_the_indic_model_and_asks_for_that_script(model):
    fake = StreamClient(words("ठीक है।"))
    model.append(fake)
    rid = new_room()["id"]
    say(rid, "p-1", "आँगन, गोवा चलते हैं")
    assert fake.calls[0]["model"] == "google/gemini-2.5-flash"
    assert "Hindi, written in Devanagari script" in fake.calls[0]["messages"][0]["content"]
    assert get(rid)["messages"][-1] == {**get(rid)["messages"][-1], "kind": "agent", "text": "ठीक है।", "lang": "hi"}


def test_ask_flag_makes_aangan_answer_and_unaddressed_messages_do_not(model):
    model.append(StreamClient(words("Sure.")))
    rid = new_room()["id"]
    say(rid, "p-1", "what do you think about the weather")
    assert get(rid)["messages"][-1]["kind"] == "user"
    say(rid, "p-1", "what do you think about the weather", ask=True)
    assert get(rid)["messages"][-1] == {**get(rid)["messages"][-1], "kind": "agent", "text": "Sure."}
    say(rid, "p-1", "@Aangan hello")
    assert get(rid)["messages"][-1]["kind"] == "agent"


def test_a_failing_model_never_breaks_the_reply_and_apologises_when_addressed(model):
    class Broken:
        chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("402 insufficient_funds"))))

    model.append(Broken())
    rid = new_room()["id"]
    say(rid, "p-1", "we should go to Goa")
    assert get(rid)["messages"][-1]["kind"] == "user"  # silent and nothing broke
    say(rid, "p-1", "Aangan, are you there")
    assert "couldn't finish" in get(rid)["messages"][-1]["text"]


def test_the_planner_does_not_block_the_http_reply(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    gate, threads = threading.Event(), []

    def slow_create(**kwargs):
        gate.wait(5)
        return iter(calls_round(("set_goal", {"goal": "Goa"})) if len(kwargs["messages"]) < 3 else [])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=slow_create)))
    monkeypatch.setattr(planner, "_client", lambda: fake)
    monkeypatch.setattr(rooms, "spawn", lambda fn, *a, **k: threads.append(threading.Thread(target=fn, args=a, kwargs=k)) or threads[-1].start())
    rid = new_room()["id"]
    room = say(rid, "p-1", "Goa please")
    assert room["plan"]["goal"] == "" and get(rid)["plan"]["goal"] == ""  # the model is still thinking
    gate.set()
    for t in threads:
        t.join(5)
    assert get(rid)["plan"]["goal"] == "Goa"


# ---- money: propose, approve, decline ----


def add_flight_and_propose(rid, model_queue, travellers=4):
    model_queue.append(StreamClient(
        calls_round(("set_origin", {"name": "Bengaluru"}), ("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "end": "2026-12-30"}),
                    ("search_flights", {})),
        calls_round(("propose_booking", {"flight_id": "f-1", "travellers": travellers})),
        words("I asked the host to approve it."),
    ))
    say(rid, "p-1", "Aangan, find flights and book the cheapest", ask=True)
    return get(rid)


def test_propose_booking_never_books(model):
    rid = new_room()["id"]
    room = add_flight_and_propose(rid, model)
    pending = room["pending_approval"]
    assert pending["status"] == "waiting" and pending["needs"] == "host" and pending["kind"] == "booking" and pending["items"] == ["f-1"]
    assert room["bookings"] == [] and room["plan"]["flights"][0]["status"] == "selected"
    assert "Demo booking" in pending["summary"] and pending["amount"] == room["plan"]["flights"][0]["price"] * 4
    assert pending["title"].endswith("for 4 people")


def test_host_approval_books_a_demo_booking_and_records_it(model):
    rid = new_room()["id"]
    room = add_flight_and_propose(rid, model)
    flight, amount = room["plan"]["flights"][0], room["pending_approval"]["amount"]
    resp = client.post(f"/api/rooms/{rid}/approve", json={"participant_id": "p-1", "approve": True})
    assert resp.status_code == 200
    done = resp.json()
    assert done["pending_approval"] is None
    (booking,) = done["bookings"]
    assert booking["kind"] == "flight" and booking["demo"] is True and booking["amount"] == amount
    assert booking["ref"].startswith("DEMO-") and len(booking["ref"]) == 10 and flight["number"] in booking["title"]
    assert next(f for f in done["plan"]["flights"] if f["id"] == "f-1")["status"] == "booked"
    assert done["messages"][-1]["kind"] == "system" and booking["ref"] in done["messages"][-1]["text"]
    again = client.post(f"/api/rooms/{rid}/approve", json={"participant_id": "p-1", "approve": True}).json()
    assert len(again["bookings"]) == 1  # a double tap books nothing more


def test_only_the_host_may_approve_and_the_message_says_who(model):
    rid = new_room()["id"]
    guest = join(rid, guest_name="Meera")["participant"]["id"]
    add_flight_and_propose(rid, model)
    resp = client.post(f"/api/rooms/{rid}/approve", json={"participant_id": guest, "approve": True})
    assert resp.status_code == 403 and "Only the host (Priya)" in resp.json()["detail"]
    room = get(rid)
    assert room["pending_approval"]["status"] == "waiting" and room["bookings"] == []


def test_declining_clears_the_approval_and_books_nothing(model):
    rid = new_room()["id"]
    add_flight_and_propose(rid, model)
    done = client.post(f"/api/rooms/{rid}/approve", json={"participant_id": "p-1", "approve": False}).json()
    assert done["pending_approval"] is None and done["bookings"] == []
    assert done["plan"]["flights"][0]["status"] == "rejected" and "declined" in done["messages"][-1]["text"]


def test_a_hotel_can_be_proposed_and_booked_with_its_nights(model):
    model.append(StreamClient(
        calls_round(("set_destination", {"name": "Goa"}), ("set_dates", {"start": "2026-12-26", "end": "2026-12-30"}), ("search_hotels", {"city": "Goa"})),
        calls_round(("propose_booking", {"hotel_id": "h-1"})), words("Waiting for the host."),
    ))
    rid = new_room()["id"]
    say(rid, "p-1", "Aangan, get us a hotel", ask=True)
    room = get(rid)
    hotel = room["plan"]["hotels"][0]
    assert room["pending_approval"]["amount"] == hotel["price_per_night"] * 4 and hotel["source"] == "sample"
    done = client.post(f"/api/rooms/{rid}/approve", json={"participant_id": "p-1", "approve": True}).json()
    assert done["bookings"][0]["kind"] == "hotel" and done["bookings"][0]["amount"] == hotel["price_per_night"] * 4


def test_reset_plan_empties_the_plan_for_rehearsal(model):
    rid = new_room()["id"]
    add_flight_and_propose(rid, model)
    done = client.post(f"/api/rooms/{rid}/reset-plan", json={}).json()
    assert done["plan"]["flights"] == [] and done["plan"]["destination"] is None and done["pending_approval"] is None
    assert done["bookings"] == [] and len(done["participants"]) == 1 and done["messages"][-1]["text"] == "The plan was reset."


# ---- persistence ----


def test_rooms_survive_a_save_and_load(model, tmp_path):
    rid = new_room()["id"]
    model.append(StreamClient(calls_round(("set_destination", {"name": "Goa"}), ("set_budget", {"total": 50000})), []))
    say(rid, "p-1", "Goa, budget 50000")
    before = get(rid)
    persistence.save(STATE)
    other = FamilyState()
    assert persistence.load(other)
    assert set(other.rooms) == {rid}
    after = rooms.snapshot(other, rid)
    for key in ("title", "plan", "messages", "bookings", "host_participant_id", "version"):
        assert after[key] == before[key], key
    # the saved room keeps working: ids carry on, nothing is reused
    pid = rooms.join(other, rid, guest_name="Late")[0]["id"]
    assert pid == "p-2" and rooms.add_user_message(other, rid, pid, "hi")["id"] == before["messages"][-1]["id"] + 1


def test_only_the_newest_300_messages_are_saved_and_a_bad_room_is_skipped():
    rid = new_room()["id"]
    for i in range(320):
        rooms.add_user_message(STATE, rid, "p-1", f"message {i}")
    saved = STATE.to_dict()["rooms"][rid]["messages"]
    assert len(saved) == 300 and saved[-1]["text"] == "message 319" and len(STATE.rooms[rid]["messages"]) == 320
    data = STATE.to_dict()
    data["rooms"]["broken"] = {"id": "broken"}
    fresh = FamilyState()
    fresh.apply_dict(data)
    assert set(fresh.rooms) == {rid}
    del data["rooms"]
    fresh.apply_dict(data)  # a household file from before rooms existed
    assert fresh.rooms == {}


def test_household_reset_clears_rooms_and_files_never_hold_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("AGORA_APP_CERTIFICATE", "super-secret-cert")
    new_room()
    assert "super-secret-cert" not in persistence.save(STATE).read_text(encoding="utf-8")
    STATE.reset(demo=True)
    assert STATE.rooms == {}


# ---- Agora: token and the voice agent ----


def test_rtc_needs_agora_keys():
    rid = new_room()["id"]
    resp = client.post(f"/api/rooms/{rid}/rtc", json={"participant_id": "p-1"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == {"error": "not_configured", "missing": ["AGORA_APP_ID", "AGORA_APP_CERTIFICATE"]}
    assert client.post(f"/api/rooms/{rid}/rtc", json={"participant_id": "p-9"}).status_code == 404


def test_rtc_returns_a_token_for_the_participants_own_uid(live_env, monkeypatch):
    seen = {}

    def fake_token(app_id, cert, channel, uid, token_expire):
        seen.update(app_id=app_id, cert=cert, channel=channel, uid=uid, expire=token_expire)
        return "tok-123"

    monkeypatch.setattr(agora, "generate_client_token", fake_token)
    room = new_room()
    rid, uid = room["id"], room["participants"][0]["rtc_uid"]
    body = client.post(f"/api/rooms/{rid}/rtc", json={"participant_id": "p-1"}).json()
    assert body == {"app_id": "a" * 32, "channel": f"room-{rid}", "token": "tok-123", "uid": uid, "rtm_token": "tok-123", "rtm_user_id": str(uid)}
    assert seen["channel"] == f"room-{rid}" and seen["uid"] == uid and seen["expire"] == 3600


@pytest.fixture
def agora_start(monkeypatch):
    """What the SDK would send to Agora; nothing goes over the network. Also records stop calls."""
    sent, stops = {"starts": []}, []

    def fake_start(self, appid, **kwargs):
        sent["starts"].append(kwargs)
        sent.update(kwargs, appid=appid)
        return SimpleNamespace(agent_id=f"agent-{len(sent['starts'])}")

    monkeypatch.setattr(AgentsClient, "start", fake_start)
    monkeypatch.setattr(agora, "_stop_agent_id", lambda cfg, agent_id: stops.append(agent_id))
    sent["stops"] = stops
    return sent


def props_of(sent: dict) -> dict:
    props = sent["properties"]
    return props if isinstance(props, dict) else props.model_dump(exclude_none=True, by_alias=True)


def test_agent_start_needs_keys():
    rid = new_room()["id"]
    resp = client.post(f"/api/rooms/{rid}/agent/start", json={"participant_id": "p-1"})
    assert resp.status_code == 503 and resp.json()["detail"]["error"] == "not_configured"
    assert "AGORA_APP_ID" in resp.json()["detail"]["missing"]


def test_the_room_agent_listens_to_everyone_and_calls_the_room_brain(live_env, agora_start, monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "english")
    agora.SESSION.update({"agent_id": "solo-call"})  # a normal single-user call is running
    rid = new_room()["id"]
    resp = client.post(f"/api/rooms/{rid}/agent/start", json={"participant_id": "p-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] == "agent-1" and body["agent_uid"] == "123456" and "everyone" in body["greeting"]
    props = props_of(agora_start)
    assert props["channel"] == f"room-{rid}" and props["remote_rtc_uids"] == ["*"] and props["agent_rtc_uid"] == "123456"
    llm_url = props["llm"]["url"]
    assert llm_url.endswith(f"/v1/chat/completions?member=priya&room={rid}&participant=p-1")
    assert agora.SESSION == {"agent_id": "solo-call"} and agora_start["stops"] == []  # the single-user session is untouched
    assert get(rid)["agent"] == {"live": True, "voice_session": "agent-1"}
    # one agent per room: starting again replaces it
    second = client.post(f"/api/rooms/{rid}/agent/start", json={"participant_id": "p-1"}).json()
    assert second["agent_id"] == "agent-2" and agora_start["stops"] == ["agent-1"]
    assert client.post(f"/api/rooms/{rid}/agent/stop", json={}).json() == {"stopped": True}
    assert agora_start["stops"] == ["agent-1", "agent-2"] and get(rid)["agent"]["live"] is False
    assert client.post(f"/api/rooms/{rid}/agent/stop", json={}).json() == {"stopped": False}


def test_a_guest_starting_the_agent_uses_the_hosts_voice(live_env, agora_start):
    rid = new_room()["id"]
    guest = join(rid, guest_name="Meera")["participant"]["id"]
    assert client.post(f"/api/rooms/{rid}/agent/start", json={"participant_id": guest}).status_code == 200
    assert f"member=priya&room={rid}&participant={guest}" in props_of(agora_start)["llm"]["url"]


def test_if_agora_refuses_the_wildcard_the_starters_uid_is_used(live_env, monkeypatch):
    attempts = []

    def start(agent, channel, user_uid, remote_uids=None):
        attempts.append(remote_uids)
        if remote_uids == ["*"]:
            raise RuntimeError("remote_rtc_uids invalid")
        return "agent-x"

    monkeypatch.setattr(agora, "_start_session", start)
    room = new_room()
    resp = client.post(f"/api/rooms/{room['id']}/agent/start", json={"participant_id": "p-1"})
    assert resp.status_code == 200 and attempts == [["*"], [str(room["participants"][0]["rtc_uid"])]]
    assert STATE.rooms[room["id"]]["_voice"]["listening_to"] == [str(room["participants"][0]["rtc_uid"])]


def test_the_single_user_agent_still_sends_its_own_url_and_uid(live_env, agora_start):
    agora.start_agent(settings(), STATE, "rahul")
    props = props_of(agora_start)
    assert props["remote_rtc_uids"] != ["*"] and props["llm"]["url"].endswith("/v1/chat/completions?member=rahul")


# ---- the voice path ----


def sse_lines(resp):
    return [json.loads(l[6:]) for l in resp.text.splitlines() if l.startswith("data: ") and l != "data: [DONE]"]


def test_voice_with_room_params_answers_through_the_room_brain(model, monkeypatch):
    monkeypatch.setenv("AANGAN_LANGUAGE_MODE", "multi")
    model.append(StreamClient(calls_round(("set_destination", {"name": "Goa"})), words("Goa it is. ", "Who is coming?")))
    room = new_room()
    rid = room["id"]
    resp = client.post(
        f"/v1/chat/completions?member=priya&room={rid}&participant=p-1",
        json={"model": "x", "stream": True, "messages": [{"role": "user", "content": "let's go to Goa"}]},
    )
    lines = sse_lines(resp)
    assert lines[0]["object"] == "chat.completion.custom_metadata"
    assert lines[0]["metadata"]["tts_params"]["params"] == {"voiceId": "hi-IN-rachna", "locale": "en-IN"}  # the room's one voice (the host's gender)
    assert lines[1]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    text = "".join(l["choices"][0]["delta"].get("content", "") for l in lines[2:])
    assert "Goa it is." in text and "Who is coming?" in text
    assert lines[-1]["choices"][0]["finish_reason"] == "stop" and resp.text.strip().endswith("data: [DONE]")
    done = get(rid)
    assert done["plan"]["destination"]["name"] == "Goa"  # the same plan the typed path edits
    assert [m["kind"] for m in done["messages"]][:2] == ["user", "agent"]
    assert done["messages"][0]["text"] == "let's go to Goa" and "Who is coming?" in done["messages"][1]["text"]


def test_voice_non_streaming_and_unknown_room_or_participant(model):
    model.append(StreamClient(words("Hello everyone.")))
    rid = new_room()["id"]
    body = {"model": "x", "stream": False, "messages": [{"role": "user", "content": "hello"}]}
    resp = client.post(f"/v1/chat/completions?room={rid}&participant=p-1", json=body)
    assert resp.json()["choices"][0]["message"]["content"] == "Hello everyone."
    assert client.post(f"/v1/chat/completions?room={rid}&participant=p-9", json=body).status_code == 404
    assert client.post("/v1/chat/completions?room=r-nope&participant=p-1", json=body).status_code == 404
    host = client.post(f"/v1/chat/completions?room={rid}", json=body)  # no participant: the voice speaks for the host
    assert host.status_code == 200 and get(rid)["messages"][-1]["kind"] == "agent"


def test_room_voice_requires_the_llm_key_like_the_single_user_path(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret")
    rid = new_room()["id"]
    body = {"model": "x", "stream": False, "messages": [{"role": "user", "content": "hi"}]}
    assert client.post(f"/v1/chat/completions?room={rid}&participant=p-1", json=body).status_code == 401
    ok = client.post(f"/v1/chat/completions?room={rid}&participant=p-1", json=body, headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_voice_speaks_even_when_the_model_only_ran_tools(model):
    model.append(StreamClient(calls_round(("set_goal", {"goal": "Goa"})), []))
    rid = new_room()["id"]
    out = rooms.converse_room(STATE, rid, "p-1", "make the goal Goa")
    assert out == "One moment. " + planner.DONE["en"] and get(rid)["plan"]["goal"] == "Goa"
    assert get(rid)["messages"][-1]["text"] == planner.DONE["en"]  # the room keeps the answer, not the hold phrase


def test_voice_says_a_hold_phrase_while_the_first_tool_runs(model):
    model.append(StreamClient(calls_round(("set_goal", {"goal": "Goa"})), words("Done.")))
    rid = new_room()["id"]
    msg = rooms.add_user_message(STATE, rid, "p-1", "goal Goa")
    pieces = list(planner.stream_turn(STATE, rid, "p-1", msg["id"]))
    assert pieces[0] == "One moment." and "".join(pieces) == "One moment. Done."


# ---- no AI key: the plain rules ----


def test_without_an_ai_key_simple_rules_still_fill_the_board_and_say_so(inline):
    rid = new_room()["id"]
    say(rid, "p-1", "Trip to Goa from Bangalore on 26 Dec for five days, budget 80000")
    room = get(rid)
    plan = room["plan"]
    assert plan["destination"]["name"] == "Goa" and plan["origin"]["name"] == "Bengaluru"
    assert plan["dates"] == {"start": "2026-12-26", "end": "2026-12-30"} and plan["budget"]["total"] == 80000
    assert plan["goal"] == "Trip to Goa" and plan["travelers"] == ["p-1"]
    notices = [m for m in room["messages"] if m["kind"] == "system" and "no AI key" in m["text"]]
    assert len(notices) == 1
    assert plan["flights"] and plan["hotels"] and plan["itinerary"]  # the first draft ran on the same facts
    say(rid, "p-1", "also 4 people")
    assert len([m for m in get(rid)["messages"] if "no AI key" in m["text"]]) == 1  # said once
    assert get(rid)["plan"]["cost_summary"]["travellers"] == 4


def test_without_a_key_an_addressed_message_gets_a_plain_reply(inline):
    rid = new_room()["id"]
    say(rid, "p-1", "Aangan, Goa trip please")
    assert get(rid)["messages"][-1]["text"] == "Noted: destination Goa."
    say(rid, "p-1", "Aangan, hello")
    assert "without an AI key" in get(rid)["messages"][-1]["text"]


def test_rule_parsers_read_dates_budgets_and_amounts():
    assert planner._parse_dates("26th to 30th December", "2026-11-20") == ("2026-12-26", "2026-12-30")
    assert planner._parse_dates("Goa over Christmas, five days", "2026-11-20") == ("2026-12-25", "2026-12-29")
    assert planner._parse_dates("go on 2026-12-26 for 3 nights", "2026-11-20") == ("2026-12-26", "2026-12-29")
    assert planner._parse_dates("on 5 Jan", "2026-11-20")[0] == "2027-01-05"  # already past this year: next year
    assert planner._parse_dates("sometime soon", "2026-11-20") is None
    assert planner._amount("2.5", "lakh") == 250000 and planner._amount("80,000", None) == 80000 and planner._amount("80", "k") == 80000


# ---- reference data ----


def test_reference_data_covers_the_cities_the_planner_promises():
    from app import travel_data, travel_places

    for name, code in [("Goa", "GOI"), ("Mumbai", "BOM"), ("Delhi", "DEL"), ("Jaipur", "JAI"), ("Kochi", "COK"), ("Hyderabad", "HYD"),
                       ("Chennai", "MAA"), ("Bengaluru", "BLR"), ("Manali", "KUU"), ("Ooty", "CJB"), ("Udaipur", "UDR"), ("Pune", "PNQ"), ("Kolkata", "CCU")]:
        c = travel_data.city(name)
        assert c["code"] == code and c["lat"] and c["lon"] and travel_data.city(code) is c
    assert travel_data.city("Bangalore")["name"] == "Bengaluru" and travel_data.city("Kerala")["name"] == "Kochi"
    for name in ["Goa", "Mumbai", "Delhi", "Jaipur", "Kochi", "Hyderabad", "Chennai", "Bengaluru"]:
        hotels = travel_data.sample_hotels(name, limit=20)
        assert 5 <= len(hotels) <= 8 and all(h["source"] == "sample" and h["lat"] and h["lon"] and isinstance(h["step_free"], bool) for h in hotels)
    for name in ["Goa", "Mumbai", "Delhi", "Jaipur", "Kochi"]:
        assert len(travel_places.sample_places(name, limit=50)) >= 6 and len(travel_places.sample_restaurants(name, limit=50)) >= 6
    for name in ["Hyderabad", "Chennai", "Bengaluru", "Manali", "Ooty", "Udaipur"]:
        assert travel_places.sample_places(name) and travel_places.sample_restaurants(name)
    assert travel_data.sample_hotels("Atlantis") == [] and travel_places.sample_places("Atlantis") == []
    sample = travel_data.sample_flights(travel_data.city("BLR"), travel_data.city("Goa"), "2026-12-26")
    assert len(sample) == 3 and all(f["source"] == "sample" and f["price"] > 0 and f["stops"] == 0 for f in sample)
    assert sample == travel_data.sample_flights(travel_data.city("BLR"), travel_data.city("Goa"), "2026-12-26")  # stable
    assert [c["name"] for _, c in travel_data.cities_in("flying from Bangalore to Goa")] == ["Bengaluru", "Goa"]
    assert travel_data.cities_in("del the dishes") == []  # a bare three-letter word is not an airport code
