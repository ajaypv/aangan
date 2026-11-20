"""Built-in travel reference data for the Family Room planner: a city table and a few curated sample hotels, plus
sample flights for routes the family catalogue does not cover.

Everything here is *sample* data, and the planner labels it that way (`source: "sample"`). It exists so the demo
works offline and for places no live service covers. Live flight results come from `live_flights`, never from here.
"""

import hashlib
import math
import re

# name, IATA code, lat, lon, aliases. Ooty has no airport of its own: its code is Coimbatore (CJB), the usual gateway.
CITIES: list[dict] = [
    {"name": "Goa", "code": "GOI", "lat": 15.2993, "lon": 74.124, "aliases": ["panaji", "panjim", "north goa", "south goa"]},
    {"name": "Mumbai", "code": "BOM", "lat": 19.076, "lon": 72.8777, "aliases": ["bombay"]},
    {"name": "Delhi", "code": "DEL", "lat": 28.6139, "lon": 77.209, "aliases": ["new delhi"]},
    {"name": "Jaipur", "code": "JAI", "lat": 26.9124, "lon": 75.7873, "aliases": []},
    {"name": "Kochi", "code": "COK", "lat": 9.9312, "lon": 76.2673, "aliases": ["cochin", "kerala", "ernakulam", "munnar", "alleppey", "alappuzha"]},
    {"name": "Hyderabad", "code": "HYD", "lat": 17.385, "lon": 78.4867, "aliases": ["secunderabad"]},
    {"name": "Chennai", "code": "MAA", "lat": 13.0827, "lon": 80.2707, "aliases": ["madras"]},
    {"name": "Bengaluru", "code": "BLR", "lat": 12.9716, "lon": 77.5946, "aliases": ["bangalore", "bangaluru"]},
    {"name": "Manali", "code": "KUU", "lat": 32.2432, "lon": 77.1892, "aliases": ["kullu"]},
    {"name": "Ooty", "code": "CJB", "lat": 11.4102, "lon": 76.695, "aliases": ["udhagamandalam", "coimbatore"]},
    {"name": "Udaipur", "code": "UDR", "lat": 24.5854, "lon": 73.7125, "aliases": []},
    {"name": "Pune", "code": "PNQ", "lat": 18.5204, "lon": 73.8567, "aliases": ["poona"]},
    {"name": "Kolkata", "code": "CCU", "lat": 22.5726, "lon": 88.3639, "aliases": ["calcutta"]},
    {"name": "Ahmedabad", "code": "AMD", "lat": 23.0225, "lon": 72.5714, "aliases": []},
    {"name": "Thiruvananthapuram", "code": "TRV", "lat": 8.5241, "lon": 76.9366, "aliases": ["trivandrum"]},
    {"name": "Varanasi", "code": "VNS", "lat": 25.3176, "lon": 82.9739, "aliases": ["benares", "banaras"]},
]
_BY_KEY: dict[str, dict] = {}
for _c in CITIES:
    for _key in [_c["name"], _c["code"], *_c["aliases"]]:
        _BY_KEY[_key.lower()] = _c


def city(name: str | None) -> dict | None:
    """A city from its name, a nickname or its airport code ('bangalore', 'BLR', 'Cochin'); None when unknown."""
    return _BY_KEY.get(re.sub(r"\s+", " ", (name or "").strip().lower()))


def cities_in(text: str) -> list[tuple[int, dict]]:
    """Cities named in free text, in the order they appear: [(position, city)]. Longer names win over their parts."""
    low = text.lower()
    found: list[tuple[int, dict]] = []
    taken: list[tuple[int, int]] = []
    for key in sorted(_BY_KEY, key=len, reverse=True):
        for m in re.finditer(rf"(?<![a-z]){re.escape(key)}(?![a-z])", low):
            if len(key) == 3 and key == _BY_KEY[key]["code"].lower() and not re.search(r"\b" + key.upper() + r"\b", text):
                continue  # a three-letter code only counts when written in capitals ("del" is also a word)
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), _BY_KEY[key]))
    found.sort(key=lambda t: t[0])
    unique: list[tuple[int, dict]] = []
    for pos, c in found:
        if all(c is not other for _, other in unique):
            unique.append((pos, c))
    return unique


def km_between(a: dict, b: dict) -> float:
    """Great-circle distance in km between two cities of the table."""
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi, dlam = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# (name, area, price per night in rupees, rating, lat, lon, step-free access)
_HOTELS: dict[str, list[tuple]] = {
    "Goa": [
        ("Coconut Grove Resort", "Candolim", 6500, 4.4, 15.5183, 73.7620, True),
        ("Baga Breeze Inn", "Baga", 3200, 3.9, 15.5553, 73.7517, False),
        ("Palolem Palms Beach Huts", "Palolem", 4200, 4.2, 15.0100, 74.0232, False),
        ("Fontainhas Heritage Stay", "Panaji", 5200, 4.3, 15.4989, 73.8333, True),
        ("Vagator Cliff Villas", "Vagator", 9800, 4.6, 15.6030, 73.7390, True),
        ("Varca White Sands Resort", "Varca", 11500, 4.7, 15.2260, 73.9420, True),
        ("Calangute Courtyard", "Calangute", 4800, 4.1, 15.5440, 73.7550, True),
    ],
    "Mumbai": [
        ("Marine Lines Grand", "Churchgate", 8800, 4.4, 18.9430, 72.8230, True),
        ("Bandra Linking Road Suites", "Bandra West", 7400, 4.2, 19.0596, 72.8295, True),
        ("Juhu Seaview Hotel", "Juhu", 9600, 4.3, 19.1075, 72.8263, True),
        ("Colaba Causeway Lodge", "Colaba", 3900, 3.8, 18.9220, 72.8330, False),
        ("Powai Lakeside Inn", "Powai", 5600, 4.1, 19.1176, 72.9060, True),
        ("Airport Transit Rooms", "Andheri East", 4300, 3.9, 19.1136, 72.8697, True),
    ],
    "Delhi": [
        ("Connaught Place Residency", "Connaught Place", 7200, 4.3, 28.6315, 77.2167, True),
        ("Hauz Khas Village Stay", "Hauz Khas", 5100, 4.1, 28.5494, 77.2001, False),
        ("Aerocity Business Hotel", "Aerocity", 8900, 4.4, 28.5562, 77.1000, True),
        ("Paharganj Backpacker House", "Paharganj", 1800, 3.6, 28.6430, 77.2130, False),
        ("Lodhi Garden Boutique", "Lodhi Colony", 12500, 4.7, 28.5918, 77.2273, True),
        ("Karol Bagh Family Inn", "Karol Bagh", 3600, 3.9, 28.6519, 77.1909, True),
    ],
    "Jaipur": [
        ("Pink City Haveli", "Old City", 5400, 4.5, 26.9239, 75.8267, False),
        ("Amer Road Palace Stay", "Amer Road", 8200, 4.4, 26.9855, 75.8513, True),
        ("C-Scheme Comfort Hotel", "C-Scheme", 4100, 4.0, 26.9124, 75.7960, True),
        ("Bani Park Courtyard", "Bani Park", 3300, 4.1, 26.9330, 75.7900, False),
        ("Rambagh Garden Resort", "Rambagh", 14500, 4.8, 26.8987, 75.8095, True),
        ("Vaishali Nagar Suites", "Vaishali Nagar", 3900, 3.9, 26.9100, 75.7430, True),
    ],
    "Kochi": [
        ("Fort Kochi Heritage Inn", "Fort Kochi", 5800, 4.4, 9.9658, 76.2421, False),
        ("Marine Drive Waterfront", "Marine Drive", 6900, 4.3, 9.9816, 76.2756, True),
        ("Backwater Retreat Alleppey", "Alappuzha", 7800, 4.5, 9.4981, 76.3388, False),
        ("Munnar Tea Hills Lodge", "Munnar", 6200, 4.4, 10.0889, 77.0595, False),
        ("Edappally Business Hotel", "Edappally", 3400, 3.9, 10.0261, 76.3080, True),
        ("Willingdon Island Resort", "Willingdon Island", 9400, 4.6, 9.9585, 76.2690, True),
    ],
    "Hyderabad": [
        ("Banjara Hills Residency", "Banjara Hills", 6800, 4.3, 17.4126, 78.4482, True),
        ("Hitech City Executive", "Hitech City", 5900, 4.2, 17.4435, 78.3772, True),
        ("Charminar Heritage Stay", "Old City", 3100, 3.9, 17.3616, 78.4747, False),
        ("Necklace Road Lakeview", "Necklace Road", 5200, 4.1, 17.4239, 78.4738, True),
        ("Shamshabad Airport Inn", "Shamshabad", 4400, 4.0, 17.2403, 78.4294, True),
        ("Jubilee Hills Boutique", "Jubilee Hills", 9900, 4.6, 17.4326, 78.4071, True),
    ],
    "Chennai": [
        ("Marina Beach Hotel", "Marina", 6100, 4.2, 13.0500, 80.2824, True),
        ("T Nagar Family Suites", "T Nagar", 4200, 4.0, 13.0418, 80.2341, True),
        ("Mylapore Temple Lodge", "Mylapore", 3300, 4.1, 13.0339, 80.2693, False),
        ("Adyar Garden Residency", "Adyar", 5800, 4.3, 13.0067, 80.2570, True),
        ("ECR Seaside Resort", "East Coast Road", 8600, 4.5, 12.8220, 80.2400, True),
        ("Egmore Central Inn", "Egmore", 2900, 3.8, 13.0732, 80.2609, False),
    ],
    "Bengaluru": [
        ("MG Road Grand", "MG Road", 7000, 4.3, 12.9756, 77.6068, True),
        ("Indiranagar Garden Hotel", "Indiranagar", 6200, 4.2, 12.9784, 77.6408, True),
        ("Koramangala Studio Stay", "Koramangala", 4300, 4.0, 12.9352, 77.6245, True),
        ("Whitefield Tech Park Inn", "Whitefield", 4800, 4.1, 12.9698, 77.7500, True),
        ("Malleswaram Heritage Lodge", "Malleswaram", 2800, 3.9, 13.0035, 77.5700, False),
        ("Airport Road Residency", "Devanahalli", 5400, 4.0, 13.1986, 77.7066, True),
    ],
}
HOTEL_CITIES = tuple(_HOTELS)


def sample_hotels(city_name: str, budget: int | None = None, step_free_only: bool = False, limit: int = 4) -> list[dict]:
    """Curated sample hotels for a city (empty for a city without a list). With a nightly budget the ones under it
    come first, best rated first; with none, best rated overall."""
    found = city(city_name)
    rows = _HOTELS.get(found["name"], []) if found else []
    hotels = [
        {"name": n, "area": a, "price_per_night": p, "rating": r, "lat": la, "lon": lo, "step_free": sf, "source": "sample"}
        for n, a, p, r, la, lo, sf in rows
        if not step_free_only or sf
    ]
    if budget:
        within = sorted((h for h in hotels if h["price_per_night"] <= budget), key=lambda h: (-h["rating"], h["price_per_night"]))
        # nothing fits the budget: show the two cheapest so the family sees how far off it is, rather than an empty list
        return within[:limit] if within else sorted(hotels, key=lambda h: h["price_per_night"])[:2]
    return sorted(hotels, key=lambda h: (-h["rating"], h["price_per_night"]))[:limit]


# Sample flights for a route the family catalogue does not have: three departures a day, priced by distance.
_AIRLINES = [("IndiGo", "6E", "06:40", 1.00), ("Air India", "AI", "11:15", 1.25), ("Akasa Air", "QP", "18:30", 0.92)]


def _hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sample_flights(origin: dict, destination: dict, date: str) -> list[dict]:
    """Three believable, clearly-sample flights between two cities of the table, stable for the same route and date."""
    if origin["code"] == destination["code"]:
        return []
    km = km_between(origin, destination)
    duration = int(55 + km / 11)
    out = []
    for airline, code, dep, factor in _AIRLINES:
        digest = int(hashlib.sha1(f"{origin['code']}{destination['code']}{date}{code}".encode()).hexdigest()[:6], 16)
        dep_min = int(dep[:2]) * 60 + int(dep[3:]) + digest % 25
        price = int(round((2300 + km * 2.9) * factor / 50.0)) * 50
        out.append(
            {
                "airline": airline, "number": f"{code}-{200 + digest % 780}", "from": origin["code"], "to": destination["code"],
                "date": date, "dep": _hhmm(dep_min), "arr": _hhmm(dep_min + duration), "price": price, "per": "person",
                "stops": 0, "source": "sample", "link": None,
            }
        )
    return sorted(out, key=lambda f: f["price"])
