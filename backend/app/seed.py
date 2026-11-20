"""Seed world for the Aangan demo: one family, one week (Fri 20 Nov to Tue 24 Nov 2026).

Only used when the demo family is loaded explicitly; a real household starts empty.
Member colours are Redwood data-visualisation colours."""

# member colours in the order new members receive them
PALETTE = ["#245D63", "#D7790F", "#31A09C", "#4E4137", "#699E61", "#B47282", "#83401E", "#9E7FCC", "#A88E00", "#58316E", "#5999B5", "#317A45"]

TODAY = "2026-11-20"  # Friday
SUNDAY = "2026-11-22"
MONDAY = "2026-11-23"

MEMBERS = [
    {
        "id": "priya", "name": "Priya", "relation": "Mom", "age": 38, "kind": "adult",
        "language": "Hinglish", "locale": "en-IN", "gender": "female", "voice_id": "Pooja", "color": "#245D63",
        "about": "Product manager, in office Tue to Thu",
    },
    {
        "id": "rahul", "name": "Rahul", "relation": "Dad", "age": 41, "kind": "adult",
        "language": "English", "locale": "en-IN", "gender": "male", "voice_id": "Abhinav", "color": "#D7790F",
        "about": "Consultant, travels to Delhi often",
    },
    {
        "id": "aarav", "name": "Aarav", "relation": "Son", "age": 10, "kind": "child",
        "language": "Hinglish", "locale": "en-IN", "gender": "male", "voice_id": "Nikhil", "color": "#31A09C",
        "about": "Class 5-B at Greenwood Public School, loves cricket",
    },
    {
        "id": "dadi", "name": "Dadi", "relation": "Grandmother", "age": 72, "kind": "senior",
        "language": "Hindi", "locale": "hi-IN", "gender": "female", "voice_id": "Rachna", "color": "#4E4137",
        "about": "Diabetes and blood pressure medicines, early dinner, bad knees",
    },
]

# "about" is a member id, or "family"
MEMORY = [
    {"id": "m1", "about": "aarav", "fact": "Severe peanut allergy", "tags": ["allergy", "food"]},
    {"id": "m2", "about": "dadi", "fact": "Pure vegetarian", "tags": ["food", "veg"]},
    {"id": "m3", "about": "dadi", "fact": "Avoids spicy food and eats dinner by 8 pm", "tags": ["food"]},
    {"id": "m4", "about": "dadi", "fact": "Bad knees: needs step-free access, no stairs", "tags": ["access"]},
    {"id": "m5", "about": "rahul", "fact": "Prefers aisle seats and morning flights, domestic budget under Rs 8,000", "tags": ["travel"]},
    {"id": "m6", "about": "priya", "fact": "Loves South Indian food", "tags": ["food"]},
    {"id": "m7", "about": "aarav", "fact": "School bus pickup 07:15, school starts 08:00", "tags": ["school"]},
    {"id": "m8", "about": "family", "fact": "Sunday is family day; outings are lunch, not late dinner", "tags": ["routine"]},
    {"id": "m9", "about": "family", "fact": "Family eating-out budget is up to Rs 3,000 for the whole family", "tags": ["budget"]},
]


def _e(eid, title, members, date, start, end, location="", kind="event"):
    return {"id": eid, "title": title, "member_ids": members, "date": date, "start": start, "end": end,
            "location": location, "kind": kind, "source": "seed"}


def _calendar():
    cal = []
    for d in ("2026-11-20", "2026-11-23", "2026-11-24"):
        cal.append(_e(f"school-{d}", "School", ["aarav"], d, "08:00", "14:30", "Greenwood Public School", "school"))
    cal += [
        _e("work-fri", "Product review", ["priya"], "2026-11-20", "11:00", "12:30", "Office", "work"),
        _e("cricket-sat", "Cricket practice", ["aarav"], "2026-11-21", "10:00", "12:00", "Sports ground", "activity"),
        _e("swim-sun", "Swimming class", ["aarav"], SUNDAY, "08:30", "09:30", "Aqua Club", "activity"),
        _e("call-sun", "Client prep call", ["rahul"], SUNDAY, "15:00", "17:00", "Home office", "work"),
        _e("satsang-sun", "Satsang", ["dadi"], SUNDAY, "17:00", "18:30", "Community hall", "event"),
        _e("flight-mon", "Flight 6E-2045 BLR to DEL", ["rahul"], MONDAY, "05:30", "08:20", "Kempegowda Airport T1", "travel"),
        _e("standup-mon", "Team standup", ["priya"], MONDAY, "10:00", "10:30", "Office", "work"),
        _e("ptm-tue", "Parent-teacher meeting", ["priya", "rahul"], "2026-11-24", "16:00", "16:30", "Greenwood Public School", "school"),
    ]
    return cal


CALENDAR = _calendar()
