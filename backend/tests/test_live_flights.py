"""Offline tests for app.live_flights. Nothing here touches the network: the MCP framing is exercised through a fake httpx
transport, and the parser runs on results recorded from the real Kiwi MCP server (tests/fixtures/kiwi_search_*.json)."""
import copy
import json
import threading
from pathlib import Path

import httpx
import pytest

from app import live_flights as lf

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    """A recorded tools/call JSON-RPC message ({"jsonrpc","id","result":{content,structuredContent,isError}})."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


BLR_GOI = load("kiwi_search_blr_goi.json")  # recorded for 2 adults, currency INR
BLR_DEL = load("kiwi_search_blr_del.json")  # recorded for 1 adult, currency INR


@pytest.fixture(autouse=True)
def fresh_cache():
    lf.clear_cache()
    yield
    lf.clear_cache()


# ---- a fake MCP server ----------------------------------------------------------------------------------------------

class FakeMcp:
    """Answers initialize / notifications/initialized / tools/call like the real server; records what it was sent."""

    def __init__(self, tool_message: dict | None = None, sse: bool = True, session_id: str | None = None,
                 tool_status: int = 200, tool_body: bytes | None = None, init_status: int = 200):
        self.tool_message = tool_message
        self.sse = sse
        self.session_id = session_id
        self.tool_status = tool_status
        self.tool_body = tool_body
        self.init_status = init_status
        self.requests: list[httpx.Request] = []
        self.calls: list[dict] = []

    def reply(self, message: dict, status: int = 200, extra_headers: dict | None = None) -> httpx.Response:
        headers = dict(extra_headers or {})
        if self.sse:
            headers["content-type"] = "text/event-stream"
            body = ("event: message\r\ndata: " + json.dumps(message) + "\r\n\r\n").encode()
        else:
            headers["content-type"] = "application/json"
            body = json.dumps(message).encode()
        return httpx.Response(status, headers=headers, content=body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(200)
        payload = json.loads(request.content)
        method = payload.get("method")
        self.calls.append(payload)
        if method == "initialize":
            if self.init_status != 200:
                return httpx.Response(self.init_status, content=b"boom")
            headers = {"mcp-session-id": self.session_id} if self.session_id else {}
            return self.reply({"jsonrpc": "2.0", "id": payload["id"], "result": {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}}, extra_headers=headers)
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/call":
            if self.tool_status != 200:
                return httpx.Response(self.tool_status, content=b"server error")
            if self.tool_body is not None:
                return httpx.Response(200, headers={"content-type": "application/json"}, content=self.tool_body)
            message = copy.deepcopy(self.tool_message)
            message["id"] = payload["id"]
            return self.reply(message)
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def run(fake: FakeMcp, origin="Bengaluru", dest="Goa", date="2026-12-18", pax=2, limit=5, timeout=5.0):
    return lf._search_with(origin, dest, date, pax, limit, timeout, fake.transport())


# ---- parser, on recorded real results ---------------------------------------------------------------------------------

def test_fixtures_are_real_kiwi_results():
    for message in (BLR_GOI, BLR_DEL):
        result = message["result"]
        assert result["isError"] is False
        payload = result["structuredContent"]
        assert payload["currency"] == "INR" and payload["itineraries"]
        assert payload["itineraries"][0]["bookingUrl"].startswith("https://kiwi.com/")


def test_parse_recorded_blr_goi_two_adults_is_per_person():
    offers = lf.parse_result(BLR_GOI, passengers=2, fallback_date="2026-12-18")
    raw = BLR_GOI["result"]["structuredContent"]["itineraries"]
    assert len(offers) == len(raw) == 15
    first = offers[0]
    # the tool's price is the total for both adults: 14042 INR for the cheapest, so 7021 each
    assert first["price"] == round(min(i["price"] for i in raw) / 2) == 7021
    assert first["per"] == "person" and first["source"] == "live"
    assert first["from"] == "BLR" and first["to"] == "GOI"
    assert first["date"] == "2026-12-18"
    assert first["airline"] == "Air India" and first["number"] == "AI-9563"
    assert (first["dep"], first["arr"]) == ("17:45", "19:10")
    assert first["stops"] == 0
    assert first["link"] == "https://kiwi.com/u/vx76wmbty5"
    assert first["duration_min"] == 85 and first["route"] == ["BLR", "GOI"]


def test_parse_normalises_every_field_for_every_recorded_offer():
    import re
    for message, pax in ((BLR_GOI, 2), (BLR_DEL, 1)):
        for o in lf.parse_result(message, passengers=pax):
            assert set(o) >= {"airline", "number", "from", "to", "date", "dep", "arr", "price", "per", "stops", "source", "link"}
            assert re.fullmatch(r"[A-Z]{3}", o["from"]) and re.fullmatch(r"[A-Z]{3}", o["to"])
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", o["date"])
            assert re.fullmatch(r"\d\d:\d\d", o["dep"]) and re.fullmatch(r"\d\d:\d\d", o["arr"])
            assert re.fullmatch(r"[0-9A-Z]{2}-\d+", o["number"]), o["number"]
            assert isinstance(o["price"], int) and o["price"] > 0
            assert isinstance(o["stops"], int)
            assert o["link"].startswith("https://")
            assert "price_note" not in o


def test_parse_sorted_cheapest_first_and_connections_counted():
    offers = lf.parse_result(BLR_GOI, passengers=2)
    prices = [o["price"] for o in offers]
    assert prices == sorted(prices)
    stops = {o["stops"] for o in offers}
    assert stops == {0, 1}  # the fixture has nonstops and one-stop connections via other airports
    connecting = next(o for o in offers if o["stops"] == 1)
    assert len(connecting["route"]) == 3 and connecting["to"] == "GOI"


def test_parse_recorded_blr_del_one_adult():
    offers = lf.parse_result(BLR_DEL, passengers=1)
    assert len(offers) == 15
    assert offers[0]["price"] == 10722 and offers[0]["number"] == "IX-1040" and offers[0]["airline"] == "Air India Express"
    assert {o["airline"] for o in offers} >= {"IndiGo", "Akasa Air", "Air India"}
    assert all(o["to"] == "DEL" for o in offers)


def synthetic(itineraries, currency="INR", **extra):
    return {"result": {"isError": False, "content": [], "structuredContent": {"currency": currency, "itineraries": itineraries, **extra}}}


def itin(price=5000.0, dep="2026-12-18T09:15:00", arr="2026-12-18T11:00:00", number="6E512", carrier="6E", name="IndiGo Airlines", **kw):
    seg = {"from": "BLR", "to": "GOI", "carrier": carrier, "carrierName": name, "flightNumber": number, "departureTime": dep, "arrivalTime": arr}
    return {"price": price, "priceFormatted": f"{int(price)} INR", "bookingUrl": kw.get("link", "https://kiwi.com/u/x"), "totalDurationSeconds": 6300,
            "outbound": {"from": "BLR", "to": "GOI", "departureTime": dep, "arrivalTime": arr, "stops": kw.get("stops", 0), "route": ["BLR", "GOI"], "segments": [seg]}}


def test_parse_flight_number_format_and_missing_pieces():
    offers = lf.parse_result(synthetic([itin(number="6E512"), itin(price=6000, number="", link=None)]), 1)
    assert offers[0]["number"] == "6E-512" and offers[0]["airline"] == "IndiGo"
    assert offers[1]["number"] == "" and offers[1]["link"] is None


def test_non_inr_currency_never_guessed():
    offers = lf.parse_result(synthetic([itin(price=80.0)], currency="EUR"), 1)
    assert offers[0]["price"] == 0
    assert "EUR" in offers[0]["price_note"]


def test_unknown_fares_sort_last():
    offers = lf.parse_result(synthetic([itin(price=0), itin(price=9000), itin(price=4000)]), 1)
    assert [o["price"] for o in offers] == [4000, 9000, 0]
    assert offers[-1]["price_note"]


def test_garbage_itineraries_are_skipped():
    offers = lf.parse_result(synthetic([None, {}, {"outbound": None}, itin(price=3000), "x"]), 1)
    assert [o["price"] for o in offers] == [3000]


def test_parse_accepts_text_content_when_no_structured_content():
    payload = BLR_GOI["result"]["structuredContent"]
    message = {"result": {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}}
    assert lf.parse_result(message, 2)[0]["price"] == 7021


def test_parse_tool_error_raises_internal_error():
    with pytest.raises(lf.LiveFlightError):
        lf.parse_result({"result": {"isError": True, "content": [{"type": "text", "text": "bad date"}]}}, 1)
    with pytest.raises(lf.LiveFlightError):
        lf.parse_result(synthetic([], error="rate limited"), 1)


# ---- MCP framing through a fake transport -----------------------------------------------------------------------------

def test_sse_response_end_to_end_sends_the_right_arguments():
    fake = FakeMcp(BLR_GOI, sse=True)
    offers = run(fake)
    assert offers and offers[0]["price"] == 7021
    methods = [c["method"] for c in fake.calls]
    assert methods == ["initialize", "notifications/initialized", "tools/call"]
    call = fake.calls[-1]["params"]
    assert call["name"] == "search-flight"
    args = call["arguments"]
    assert args["flyFrom"] == "BLR" and args["flyTo"] == "GOI"  # city names resolved to IATA codes
    assert args["departureDate"] == "18/12/2026"  # dd/mm/yyyy
    assert args["adults"] == 2 and args["currency"] == "INR" and args["sort"] == "price"
    for request in fake.requests:
        assert "text/event-stream" in request.headers["accept"] and "application/json" in request.headers["accept"]


def test_plain_json_response_end_to_end():
    fake = FakeMcp(BLR_DEL, sse=False)
    offers = run(fake, "BLR", "DEL", pax=1)
    assert offers[0]["number"] == "IX-1040"


def test_session_id_header_is_echoed_on_later_requests():
    fake = FakeMcp(BLR_GOI, sse=True, session_id="sess-123")
    assert run(fake)
    posts = [r for r in fake.requests if r.method == "POST"]
    assert "mcp-session-id" not in posts[0].headers
    assert posts[1].headers["mcp-session-id"] == "sess-123"
    assert posts[2].headers["mcp-session-id"] == "sess-123"
    assert posts[2].headers["mcp-protocol-version"] == "2025-03-26"


def test_sse_with_keepalives_and_other_events_before_the_answer():
    message = copy.deepcopy(BLR_DEL)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        method = payload.get("method")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            body = f"data: {json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': '2025-03-26'}})}\n\n"
        else:
            message["id"] = 2
            body = (": keep-alive\n\nevent: ping\ndata: not json\n\n"
                    f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'notifications/message', 'params': {}})}\n\n"
                    f"event: message\ndata: {json.dumps(message)}\n\n")
        return httpx.Response(200, headers={"content-type": "text/event-stream; charset=utf-8"}, content=body.encode())

    offers = lf._search_with("BLR", "DEL", "2026-12-18", 1, 5, 5.0, httpx.MockTransport(handler))
    assert offers and offers[0]["price"] == 10722


def test_sse_data_split_across_lines_is_joined():
    pretty = json.dumps({"jsonrpc": "2.0", "id": 2, "result": BLR_DEL["result"]}, indent=1).splitlines()
    sse_body = "\n".join("data: " + line for line in pretty) + "\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        method = json.loads(request.content).get("method")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode())
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body.encode())

    assert lf._search_with("BLR", "DEL", "2026-12-18", 1, 5, 5.0, httpx.MockTransport(handler))


# ---- failure paths: always [] and a logged reason ---------------------------------------------------------------------

def test_http_500_on_tool_call_returns_empty_and_logs(caplog):
    caplog.set_level("INFO", logger="aangan.live_flights")
    assert run(FakeMcp(BLR_GOI, tool_status=500)) == []
    assert any("HTTP 500" in r.getMessage() for r in caplog.records)


def test_http_500_on_initialize_returns_empty():
    assert run(FakeMcp(BLR_GOI, init_status=500)) == []


def test_timeout_returns_empty_and_logs(caplog):
    caplog.set_level("INFO", logger="aangan.live_flights")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    assert lf._search_with("BLR", "GOI", "2026-12-18", 1, 5, 2.0, httpx.MockTransport(handler)) == []
    assert any("timeout" in r.getMessage().lower() for r in caplog.records)


def test_connection_error_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    assert lf._search_with("BLR", "GOI", "2026-12-18", 1, 5, 2.0, httpx.MockTransport(handler)) == []


def test_overall_deadline_is_enforced_across_steps(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(lf.time, "monotonic", lambda: clock["t"])
    fake = FakeMcp(BLR_GOI)
    original = fake.__call__

    def slow(request):
        clock["t"] += 3.0  # every round trip "takes" 3 s against a 5 s budget
        return original(request)

    assert lf._search_with("BLR", "GOI", "2026-12-18", 1, 5, 5.0, httpx.MockTransport(slow)) == []


def test_malformed_json_returns_empty():
    fake = FakeMcp(BLR_GOI, sse=False, tool_body=b"{not json")
    assert run(fake) == []


def test_malformed_sse_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        method = json.loads(request.content).get("method")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            return httpx.Response(200, headers={"content-type": "application/json"}, content=b'{"jsonrpc":"2.0","id":1,"result":{}}')
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"data: {broken\n\n")

    assert lf._search_with("BLR", "GOI", "2026-12-18", 1, 5, 2.0, httpx.MockTransport(handler)) == []


def test_tool_error_returns_empty(caplog):
    caplog.set_level("INFO", logger="aangan.live_flights")
    message = {"jsonrpc": "2.0", "id": 2, "result": {"isError": True, "content": [{"type": "text", "text": "Invalid departure date"}]}}
    assert run(FakeMcp(message)) == []
    assert any("Invalid departure date" in r.getMessage() for r in caplog.records)


def test_jsonrpc_error_returns_empty():
    message = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "bad params"}}
    assert run(FakeMcp(message)) == []


def test_search_error_field_returns_empty():
    message = {"jsonrpc": "2.0", "id": 2, "result": {"isError": False, "structuredContent": {"currency": "INR", "itineraries": [], "error": "no route"}}}
    assert run(FakeMcp(message)) == []


def test_no_itineraries_returns_empty_and_is_not_cached(caplog):
    caplog.set_level("INFO", logger="aangan.live_flights")
    message = {"jsonrpc": "2.0", "id": 2, "result": {"isError": False, "structuredContent": {"currency": "INR", "itineraries": [], "resultsCount": 0}}}
    fake = FakeMcp(message)
    assert run(fake) == []
    assert any("no itineraries" in r.getMessage() for r in caplog.records)
    assert run(fake) == []
    assert [c["method"] for c in fake.calls].count("tools/call") == 2


def test_search_never_raises_even_on_unexpected_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(lf, "_call_tool", boom)
    assert lf.search("BLR", "GOI", "2026-12-18") == []
    assert lf.search(None, None, None) == []  # type: ignore[arg-type]
    assert lf.search("BLR", "GOI", "2026-12-18", passengers="x") == []  # type: ignore[arg-type]


def test_search_public_function_uses_httpx_and_returns_empty_when_offline(monkeypatch):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    real_client = httpx.Client
    monkeypatch.setattr(lf.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(refuse), **{k: v for k, v in kw.items() if k != "transport"}))
    assert lf.search("BLR", "GOI", "2026-12-18") == []


@pytest.mark.parametrize("origin,dest,date", [
    ("", "GOI", "2026-12-18"), ("BLR", "", "2026-12-18"), ("BLR", "GOI", "18/12/2026"), ("BLR", "GOI", "2026-13-40"),
    ("BLR", "GOI", ""), ("Bengaluru", "BLR", "2026-12-18"),
])
def test_bad_input_returns_empty_without_calling_the_server(origin, dest, date):
    fake = FakeMcp(BLR_GOI)
    assert run(fake, origin, dest, date) == []
    assert fake.requests == []


def test_passenger_count_is_clamped_to_the_tools_limit():
    fake = FakeMcp(BLR_GOI)
    assert lf._search_with("BLR", "GOI", "2026-12-18", 40, 5, 5.0, fake.transport())
    assert fake.calls[-1]["params"]["arguments"]["adults"] == 9
    fake = FakeMcp(BLR_GOI)
    lf._search_with("BLR", "GOI", "2026-12-18", 0, 5, 5.0, fake.transport())
    assert fake.calls[-1]["params"]["arguments"]["adults"] == 1


# ---- ordering / limit ---------------------------------------------------------------------------------------------------

def test_limit_and_cheapest_first():
    fake = FakeMcp(BLR_GOI)
    three = run(fake, limit=3)
    assert len(three) == 3
    assert [o["price"] for o in three] == sorted(o["price"] for o in three)
    assert three[0]["price"] == 7021
    assert len(run(fake, limit=50)) == 15  # all of them, from the cache
    assert len(run(fake, limit=0)) >= 1  # a nonsense limit still behaves


def test_unsorted_server_results_are_sorted_by_price():
    shuffled = copy.deepcopy(BLR_GOI)
    shuffled["result"]["structuredContent"]["itineraries"].reverse()
    offers = run(FakeMcp(shuffled), limit=15)
    prices = [o["price"] for o in offers]
    assert prices == sorted(prices) and prices[0] == 7021


# ---- cache ---------------------------------------------------------------------------------------------------------------

def test_cache_hit_avoids_a_second_call_and_returns_copies():
    fake = FakeMcp(BLR_GOI)
    first = run(fake)
    first[0]["price"] = -1  # callers may mutate what they get
    second = run(fake)
    assert second[0]["price"] == 7021
    assert [c["method"] for c in fake.calls].count("tools/call") == 1


def test_cache_key_is_route_date_and_passengers():
    fake = FakeMcp(BLR_GOI)
    run(fake)
    run(fake, date="2026-12-19")
    run(fake, pax=3)
    run(fake, dest="DEL")
    assert [c["method"] for c in fake.calls].count("tools/call") == 4
    run(fake, origin="BLR", dest="GOI")  # city names and IATA codes resolve to the same key
    assert [c["method"] for c in fake.calls].count("tools/call") == 4


def test_cache_expires_after_ttl(monkeypatch):
    clock = {"t": 5000.0}
    monkeypatch.setattr(lf.time, "monotonic", lambda: clock["t"])
    fake = FakeMcp(BLR_GOI)
    run(fake)
    clock["t"] += lf.CACHE_TTL - 1
    run(fake)
    assert [c["method"] for c in fake.calls].count("tools/call") == 1
    clock["t"] += 2
    run(fake)
    assert [c["method"] for c in fake.calls].count("tools/call") == 2


def test_failures_are_not_cached():
    assert run(FakeMcp(BLR_GOI, tool_status=500)) == []
    good = FakeMcp(BLR_GOI)
    assert run(good)


def test_cache_is_thread_safe():
    fake = FakeMcp(BLR_GOI)
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for j in range(20):
                lf._cache_put(("k", i, j), [{"price": j}])
                lf._cache_get(("k", i, j))
                lf._cache_get(("k", i, j - 1))
            assert run(fake)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors


# ---- city_to_iata ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,code", [
    ("Bengaluru", "BLR"), ("Bangalore", "BLR"), ("bangalore", "BLR"), ("  BENGALURU ", "BLR"),
    ("Goa", "GOI"), ("goa", "GOI"), ("Dabolim", "GOI"), ("Mopa", "GOX"), ("North Goa", "GOX"),
    ("Mumbai", "BOM"), ("Bombay", "BOM"), ("Delhi", "DEL"), ("New Delhi", "DEL"), ("Hyderabad", "HYD"),
    ("Chennai", "MAA"), ("Kolkata", "CCU"), ("Kochi", "COK"), ("Cochin", "COK"), ("Pune", "PNQ"), ("Jaipur", "JAI"),
    ("Ahmedabad", "AMD"), ("Lucknow", "LKO"), ("Thiruvananthapuram", "TRV"), ("Trivandrum", "TRV"),
    ("Dubai", "DXB"), ("Singapore", "SIN"), ("Bangkok", "BKK"), ("London", "LHR"), ("Paris", "CDG"), ("New York", "JFK"),
    ("Visakhapatnam", "VTZ"), ("Mysuru", "MYQ"),
    ("BLR", "BLR"), ("blr", "BLR"), ("GOI", "GOI"), ("GOX", "GOX"), ("dxb", "DXB"), ("XYZ", "XYZ"),
    ("Bengaluru (BLR)", "BLR"), ("BLR - Bengaluru", "BLR"), ("Goa, India", "GOI"), ("Bengaluru Airport", "BLR"),
])
def test_city_to_iata_known(name, code):
    assert lf.city_to_iata(name) == code


@pytest.mark.parametrize("name", ["", "   ", "Atlantis", "Nowhereville", None, 42])
def test_city_to_iata_unknown_is_none(name):
    assert lf.city_to_iata(name) is None  # type: ignore[arg-type]


def test_city_names_with_accents_and_punctuation():
    assert lf.city_to_iata("Zürich") == "ZRH"
    assert lf.city_to_iata("Kuala-Lumpur") == "KUL"


def test_unknown_place_is_passed_to_the_tool_as_given():
    fake = FakeMcp(BLR_GOI)
    lf._search_with("Bengaluru", "Atlantis Reef", "2026-12-18", 1, 5, 5.0, fake.transport())
    args = fake.calls[-1]["params"]["arguments"]
    assert args["flyFrom"] == "BLR" and args["flyTo"] == "Atlantis Reef"
