"""Live flight search for the AI planner, from Kiwi.com's official MCP server (https://mcp.kiwi.com, no API key).

Public interface:
    search(origin, destination, date, passengers=1, limit=5, timeout=15.0) -> list[dict]   (never raises; [] on any failure)
    city_to_iata(name) -> str | None

How the tool behaves (verified against the live server, tools/list + tools/call, Nov 2026):
  * MCP streamable HTTP. `initialize` replies as text/event-stream (`data: {json-rpc}` lines); the server sends no
    Mcp-Session-Id today, but we honour one if it appears (and accept plain application/json replies too).
  * Tool `search-flight`: flyFrom / flyTo accept an IATA code or a city/airport name, departureDate is dd/mm/yyyy,
    `adults`, `currency` (we ask for INR), `sort` ("price").
  * The result carries `structuredContent` = {query, currency, passengers, resultsCount, itineraries[], searchTimeMs, error}.
    `price` on an itinerary is the TOTAL for all passengers (checked: the same flight is 7025 for 1 adult and 14042 for 2),
    so we divide by the passenger count to give a per-person fare. Times are local ISO timestamps.

Each offer: {"airline", "number", "from", "to", "date", "dep", "arr", "price", "per": "person", "stops",
             "source": "live", "link"} plus two extras the planner may ignore: "route" (airport codes incl. layovers) and
             "duration_min". Cheapest first. A non-INR price is never guessed: price 0 and a "price_note" instead.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
import unicodedata
from datetime import datetime
from typing import Any

import httpx

log = logging.getLogger("aangan.live_flights")

MCP_URL = "https://mcp.kiwi.com"
TOOL_NAME = "search-flight"
PROTOCOL_VERSION = "2025-03-26"
CACHE_TTL = 600.0
MAX_ADULTS = 9  # the tool's limit for `adults`
_CLIENT_INFO = {"name": "aangan", "version": "1.0"}


# --------------------------------------------------------------------------------------------------------------------
# City names -> IATA
# --------------------------------------------------------------------------------------------------------------------

_CITY_TABLE: dict[str, tuple[str, ...]] = {
    # India
    "BLR": ("bengaluru", "bangalore", "bengaluru international", "kempegowda"),
    "GOI": ("goa", "goa dabolim", "dabolim", "south goa", "panaji", "panjim", "margao", "vasco", "goa international"),
    "GOX": ("mopa", "north goa", "manohar international", "goa mopa", "goa north"),
    "BOM": ("mumbai", "bombay"),
    "DEL": ("delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida"),
    "HYD": ("hyderabad", "secunderabad"),
    "MAA": ("chennai", "madras"),
    "CCU": ("kolkata", "calcutta"),
    "COK": ("kochi", "cochin", "ernakulam"),
    "PNQ": ("pune", "poona"),
    "JAI": ("jaipur",),
    "AMD": ("ahmedabad",),
    "LKO": ("lucknow",),
    "TRV": ("thiruvananthapuram", "trivandrum"),
    "ATQ": ("amritsar",),
    "BBI": ("bhubaneswar", "bhubaneshwar"),
    "BHO": ("bhopal",),
    "IXC": ("chandigarh", "mohali"),
    "CJB": ("coimbatore",),
    "DED": ("dehradun",),
    "GAU": ("guwahati", "gauhati"),
    "IDR": ("indore",),
    "JDH": ("jodhpur",),
    "CCJ": ("kozhikode", "calicut"),
    "IXM": ("madurai",),
    "IXE": ("mangalore", "mangaluru"),
    "MYQ": ("mysore", "mysuru"),
    "NAG": ("nagpur",),
    "PAT": ("patna",),
    "RPR": ("raipur",),
    "IXR": ("ranchi",),
    "SXR": ("srinagar",),
    "STV": ("surat",),
    "TRZ": ("tiruchirappalli", "trichy", "tiruchirapalli"),
    "UDR": ("udaipur",),
    "VNS": ("varanasi", "banaras", "benares", "kashi"),
    "VGA": ("vijayawada",),
    "VTZ": ("visakhapatnam", "vizag", "vishakhapatnam"),
    "IXZ": ("port blair", "andaman", "andamans"),
    "IXL": ("leh", "ladakh"),
    "AGR": ("agra",),
    "HBX": ("hubli", "hubballi"),
    "IXG": ("belgaum", "belagavi"),
    "PNY": ("pondicherry", "puducherry"),
    "BDQ": ("vadodara", "baroda"),
    "RAJ": ("rajkot",),
    "IXJ": ("jammu",),
    "DIB": ("dibrugarh",),
    "IMF": ("imphal",),
    "IXA": ("agartala",),
    "IXB": ("bagdogra", "siliguri", "darjeeling"),
    "TIR": ("tirupati",),
    "CNN": ("kannur", "cannanore"),
    "IXU": ("aurangabad",),
    "ISK": ("nashik",),
    "GWL": ("gwalior",),
    "JLR": ("jabalpur",),
    "IXD": ("prayagraj", "allahabad"),
    "GOP": ("gorakhpur",),
    "KNU": ("kanpur",),
    "SAG": ("shirdi",),
    "GAY": ("gaya", "bodh gaya"),
    "SXV": ("salem",),
    "BHJ": ("bhuj",),
    "JGA": ("jamnagar",),
    "DMU": ("dimapur",),
    "IXS": ("silchar",),
    # International
    "DXB": ("dubai",),
    "AUH": ("abu dhabi",),
    "SHJ": ("sharjah",),
    "DOH": ("doha",),
    "MCT": ("muscat",),
    "SIN": ("singapore",),
    "BKK": ("bangkok",),
    "HKT": ("phuket",),
    "KBV": ("krabi",),
    "KUL": ("kuala lumpur",),
    "PEN": ("penang",),
    "CMB": ("colombo",),
    "KTM": ("kathmandu",),
    "MLE": ("male", "maldives"),
    "DAC": ("dhaka",),
    "LHR": ("london", "london heathrow", "heathrow"),
    "CDG": ("paris",),
    "FRA": ("frankfurt",),
    "AMS": ("amsterdam",),
    "ZRH": ("zurich",),
    "FCO": ("rome",),
    "MAD": ("madrid",),
    "BCN": ("barcelona",),
    "IST": ("istanbul",),
    "VIE": ("vienna",),
    "MUC": ("munich",),
    "DUB": ("dublin",),
    "MAN": ("manchester",),
    "EDI": ("edinburgh",),
    "JFK": ("new york", "newyork", "nyc"),
    "SFO": ("san francisco",),
    "LAX": ("los angeles",),
    "ORD": ("chicago",),
    "YYZ": ("toronto",),
    "SYD": ("sydney",),
    "MEL": ("melbourne",),
    "AKL": ("auckland",),
    "HND": ("tokyo",),
    "HKG": ("hong kong",),
    "ICN": ("seoul",),
    "DPS": ("bali", "denpasar"),
    "CGK": ("jakarta",),
    "HAN": ("hanoi",),
    "SGN": ("ho chi minh", "ho chi minh city", "saigon"),
    "MNL": ("manila",),
    "PEK": ("beijing",),
    "PVG": ("shanghai",),
    "RUH": ("riyadh",),
    "JED": ("jeddah",),
    "KWI": ("kuwait",),
    "BAH": ("bahrain",),
    "CAI": ("cairo",),
    "NBO": ("nairobi",),
    "JNB": ("johannesburg",),
    "MRU": ("mauritius",),
    "SVO": ("moscow",),
}

_NAME_TO_IATA: dict[str, str] = {}
for _code, _names in _CITY_TABLE.items():
    for _n in _names:
        _NAME_TO_IATA[_n] = _code


def _norm_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    for suffix in (" airport", " international airport", " intl"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def city_to_iata(name: str) -> str | None:
    """'Bengaluru' -> 'BLR', 'Goa' -> 'GOI' (Dabolim; Mopa 'GOX' only when asked for by name), 'dxb' -> 'DXB'.
    Accepts IATA codes unchanged (upper-cased), and 'Bengaluru (BLR)' / 'BLR - Bengaluru' forms. None if unknown."""
    if not name or not isinstance(name, str):
        return None
    cleaned = name.strip()
    if not cleaned:
        return None
    key = _norm_name(cleaned)
    if key in _NAME_TO_IATA:  # before the 3-letter check: "goa" is a city, not an airport code
        return _NAME_TO_IATA[key]
    if re.fullmatch(r"[A-Za-z]{3}", cleaned):
        return cleaned.upper()
    # "Goa, India" / "Bengaluru Karnataka": try the first word group before a comma, then the first word
    head = _norm_name(cleaned.split(",")[0])
    if head in _NAME_TO_IATA:
        return _NAME_TO_IATA[head]
    embedded = re.search(r"[(\[]\s*([A-Za-z]{3})\s*[)\]]", cleaned) or re.match(r"^([A-Za-z]{3})\s*[-:,/]\s*\S", cleaned)
    if embedded:
        return embedded.group(1).upper()
    for n in sorted(_NAME_TO_IATA, key=len, reverse=True):  # longest name first: "new delhi" before "delhi"
        if key.startswith(n + " "):
            return _NAME_TO_IATA[n]
    return None


# --------------------------------------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------------------------------------

_cache: dict[tuple, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: tuple) -> list[dict] | None:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        stamp, offers = hit
        if now - stamp > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return copy.deepcopy(offers)


def _cache_put(key: tuple, offers: list[dict]) -> None:
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) > 256:  # keep it small: drop expired entries, then the oldest
            for k in [k for k, (stamp, _) in _cache.items() if now - stamp > CACHE_TTL]:
                _cache.pop(k, None)
            while len(_cache) > 256:
                _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
        _cache[key] = (now, copy.deepcopy(offers))


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# --------------------------------------------------------------------------------------------------------------------
# MCP streamable-HTTP framing
# --------------------------------------------------------------------------------------------------------------------

class LiveFlightError(Exception):
    """Internal: any reason a live search could not produce a result. search() turns it into a logged []."""


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise LiveFlightError("overall timeout exceeded")
    return left


def _decode_json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LiveFlightError(f"malformed JSON from MCP server: {exc}") from exc


def _read_rpc_response(resp: httpx.Response, request_id: int, deadline: float) -> dict:
    """The JSON-RPC message answering `request_id`, from either an application/json or a text/event-stream body.
    SSE is read line by line and abandoned as soon as the matching message arrives (a server may keep the stream open)."""
    ctype = resp.headers.get("content-type", "").lower()
    if "text/event-stream" in ctype:
        data_lines: list[str] = []
        found: dict | None = None

        def flush() -> dict | None:
            if not data_lines:
                return None
            payload = "\n".join(data_lines)
            data_lines.clear()
            try:
                msg = json.loads(payload)
            except ValueError:
                return None  # keep-alives and non-JSON events are ignored
            if isinstance(msg, dict) and msg.get("id") == request_id and ("result" in msg or "error" in msg):
                return msg
            return None

        for line in resp.iter_lines():
            _remaining(deadline)
            line = line.rstrip("\r")
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
            elif line == "":
                found = flush()
                if found:
                    break
        else:
            found = flush()
        if found is None:
            raise LiveFlightError("no JSON-RPC response in the event stream")
        return found
    resp.read()
    msg = _decode_json(resp.text)
    if isinstance(msg, list):  # a batch reply
        msg = next((m for m in msg if isinstance(m, dict) and m.get("id") == request_id), None)
    if not isinstance(msg, dict):
        raise LiveFlightError("unexpected MCP response shape")
    return msg


def _post(client: httpx.Client, headers: dict, payload: dict, deadline: float, expect_id: int | None) -> tuple[httpx.Headers, dict | None]:
    timeout = httpx.Timeout(_remaining(deadline))
    try:
        with client.stream("POST", MCP_URL, headers=headers, json=payload, timeout=timeout) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise LiveFlightError(f"MCP server returned HTTP {resp.status_code} for {payload.get('method')}")
            if expect_id is None:
                resp.read()  # a notification: 202 with no body
                return resp.headers, None
            return resp.headers, _read_rpc_response(resp, expect_id, deadline)
    except httpx.TimeoutException as exc:
        raise LiveFlightError(f"timeout during {payload.get('method')}: {exc.__class__.__name__}") from exc
    except httpx.HTTPError as exc:
        raise LiveFlightError(f"network error during {payload.get('method')}: {exc.__class__.__name__}: {exc}") from exc


def _call_tool(arguments: dict, timeout: float, transport: httpx.BaseTransport | None = None) -> dict:
    """initialize -> notifications/initialized -> tools/call search-flight. Returns the JSON-RPC `result` of the call."""
    deadline = time.monotonic() + max(0.5, float(timeout))
    base_headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        resp_headers, msg = _post(client, base_headers, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": _CLIENT_INFO},
        }, deadline, expect_id=1)
        if msg is None or "error" in msg:
            raise LiveFlightError(f"initialize failed: {(msg or {}).get('error')}")
        headers = dict(base_headers)
        session_id = resp_headers.get("mcp-session-id")
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        negotiated = (msg.get("result") or {}).get("protocolVersion")
        if isinstance(negotiated, str) and negotiated:
            headers["MCP-Protocol-Version"] = negotiated
        try:
            _post(client, headers, {"jsonrpc": "2.0", "method": "notifications/initialized"}, deadline, expect_id=None)
            _, msg = _post(client, headers, {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": TOOL_NAME, "arguments": arguments},
            }, deadline, expect_id=2)
        finally:
            if session_id:  # politeness: end the session; a failure here changes nothing
                try:
                    client.delete(MCP_URL, headers=headers, timeout=2.0)
                except Exception:  # noqa: BLE001
                    pass
    if msg is None:
        raise LiveFlightError("no response to tools/call")
    if "error" in msg:
        raise LiveFlightError(f"MCP error on tools/call: {msg['error']}")
    result = msg.get("result")
    if not isinstance(result, dict):
        raise LiveFlightError("tools/call had no result")
    return result


# --------------------------------------------------------------------------------------------------------------------
# Result parsing
# --------------------------------------------------------------------------------------------------------------------

def _tool_payload(result: dict) -> dict:
    """The search payload ({query, currency, itineraries...}) out of a tools/call result (or the whole JSON-RPC message)."""
    if isinstance(result.get("result"), dict):  # accept the full JSON-RPC message too (as recorded in fixtures)
        result = result["result"]
    if result.get("isError"):
        text = " ".join(str(c.get("text", "")) for c in result.get("content") or [] if isinstance(c, dict))
        raise LiveFlightError(f"tool reported an error: {text[:300] or 'unknown'}")
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                payload = _decode_json(item["text"])
                break
    if not isinstance(payload, dict):
        raise LiveFlightError("tool result carried no structured payload")
    if payload.get("error"):
        raise LiveFlightError(f"search error: {str(payload['error'])[:300]}")
    return payload


_AIRLINE_NOISE = re.compile(r"\s+(limited|ltd\.?|airlines?|airways)$", re.I)


def _airline_name(segment: dict) -> str:
    name = str(segment.get("carrierName") or "").strip()
    cleaned = _AIRLINE_NOISE.sub("", name).strip()
    return cleaned or name or str(segment.get("carrier") or "").strip()


def _flight_number(segment: dict) -> str:
    """'6E512' + carrier '6E' -> '6E-512'. '' when unknown."""
    raw = str(segment.get("flightNumber") or "").replace(" ", "").replace("-", "")
    carrier = str(segment.get("carrier") or "").strip()
    if not raw:
        return ""
    if carrier and raw.upper().startswith(carrier.upper()) and len(raw) > len(carrier):
        return f"{carrier.upper()}-{raw[len(carrier):]}"
    match = re.match(r"^([A-Za-z0-9]{2})(\d{1,4}[A-Za-z]?)$", raw)
    return f"{match.group(1).upper()}-{match.group(2)}" if match else raw


def _hhmm(iso: Any) -> str:
    text = str(iso or "")
    match = re.search(r"[T ](\d{2}):(\d{2})", text)
    return f"{match.group(1)}:{match.group(2)}" if match else ""


def _date_of(iso: Any, fallback: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(iso or ""))
    return match.group(1) if match else fallback


def parse_result(result: dict, passengers: int = 1, fallback_date: str = "") -> list[dict]:
    """Normalise a `tools/call` result (or full JSON-RPC message) into offers, cheapest first. Raises LiveFlightError on a
    tool/search error; returns [] when the search simply found nothing."""
    payload = _tool_payload(result)
    currency = str(payload.get("currency") or "").upper()
    pax = max(1, int(passengers or 1))
    offers: list[dict] = []
    for itin in payload.get("itineraries") or []:
        try:
            out = itin.get("outbound") or {}
            segments = out.get("segments") or []
            first = segments[0] if segments else {}
            route = [str(c) for c in out.get("route") or [] if c]
            origin = str(out.get("from") or first.get("from") or (route[0] if route else "")).upper()
            dest = str(out.get("to") or (segments[-1].get("to") if segments else "") or (route[-1] if route else "")).upper()
            dep_iso = out.get("departureTime") or first.get("departureTime")
            arr_iso = out.get("arrivalTime") or (segments[-1].get("arrivalTime") if segments else None)
            if not (origin and dest and _hhmm(dep_iso)):
                continue
            total = itin.get("price")
            offer: dict[str, Any] = {
                "airline": _airline_name(first),
                "number": _flight_number(first),
                "from": origin,
                "to": dest,
                "date": _date_of(dep_iso, fallback_date),
                "dep": _hhmm(dep_iso),
                "arr": _hhmm(arr_iso),
                "price": 0,
                "per": "person",
                "stops": int(out.get("stops") if out.get("stops") is not None else max(0, len(segments) - 1)),
                "source": "live",
                "link": itin.get("bookingUrl") or None,
                "route": route or [origin, dest],
            }
            seconds = out.get("durationSeconds") or itin.get("totalDurationSeconds")
            if isinstance(seconds, (int, float)) and seconds > 0:
                offer["duration_min"] = int(round(seconds / 60))
            if isinstance(total, (int, float)) and total > 0:
                if currency == "INR":
                    offer["price"] = int(round(float(total) / pax))  # the tool's price is the total for all passengers
                else:
                    offer["price_note"] = f"fare returned in {currency or 'an unknown currency'}, no INR rate provided: {itin.get('priceFormatted') or total} total"
            else:
                offer["price_note"] = "no fare returned"
            offers.append(offer)
        except (TypeError, ValueError, AttributeError):
            continue
    # cheapest first; offers whose fare is unknown (0) go last
    offers.sort(key=lambda o: (o["price"] == 0, o["price"], o["date"], o["dep"]))
    return offers


# --------------------------------------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------------------------------------

def _resolve(place: str) -> str:
    """IATA code if we know one, else the cleaned name (the tool resolves city names itself)."""
    return city_to_iata(place) or str(place).strip()


def _search(origin: str, destination: str, date: str, passengers: int, limit: int, timeout: float,
            transport: httpx.BaseTransport | None) -> list[dict]:
    if not origin or not str(origin).strip() or not destination or not str(destination).strip():
        log.info("live flights: empty origin or destination")
        return []
    try:
        day = datetime.strptime(str(date).strip(), "%Y-%m-%d")
    except ValueError:
        log.info("live flights: date %r is not YYYY-MM-DD", date)
        return []
    pax = min(MAX_ADULTS, max(1, int(passengers or 1)))
    limit = max(1, int(limit or 5))
    src, dst = _resolve(origin), _resolve(destination)
    if src.upper() == dst.upper():
        log.info("live flights: origin and destination are the same (%s)", src)
        return []
    iso_date = day.strftime("%Y-%m-%d")
    key = (src.lower(), dst.lower(), iso_date, pax)
    cached = _cache_get(key)
    if cached is not None:
        return cached[:limit]
    arguments = {
        "flyFrom": src, "flyTo": dst, "departureDate": day.strftime("%d/%m/%Y"),
        "adults": pax, "currency": "INR", "sort": "price",
    }
    started = time.monotonic()
    result = _call_tool(arguments, timeout, transport)
    offers = parse_result(result, pax, iso_date)
    log.info("live flights: %s->%s %s x%d gave %d offers in %.1fs", src, dst, iso_date, pax, len(offers), time.monotonic() - started)
    if not offers:
        log.info("live flights: no itineraries for %s->%s on %s", src, dst, iso_date)
        return []
    _cache_put(key, offers)
    return copy.deepcopy(offers[:limit])


def search(origin: str, destination: str, date: str, passengers: int = 1, limit: int = 5, timeout: float = 15.0) -> list[dict]:
    """origin/destination: IATA code (BLR) or a city name (Bengaluru, Goa). date: YYYY-MM-DD.
    Returns [] on ANY failure (network, parse, empty). Never raises. Prices are INR for ONE passenger, cheapest first."""
    return _search_with(origin, destination, date, passengers, limit, timeout, None)


def _search_with(origin: Any, destination: Any, date: Any, passengers: Any, limit: Any, timeout: Any,
                 transport: httpx.BaseTransport | None) -> list[dict]:
    try:
        return _search(origin, destination, date, passengers, limit, float(timeout), transport)
    except LiveFlightError as exc:
        log.warning("live flights unavailable (%s -> %s, %s): %s", origin, destination, date, exc)
    except Exception as exc:  # noqa: BLE001 - search() must never raise
        log.warning("live flights failed unexpectedly (%s -> %s, %s): %s: %s", origin, destination, date, exc.__class__.__name__, exc)
    return []
