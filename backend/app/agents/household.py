"""Household agent: the family's shared memory and membership.

Add a new member by voice ("meet my daughter Anaya, she is 6"), remember or forget preferences and facts,
recall what the family knows about a person, and summarise the family. Works directly on state.members and
state.memory; domain data (state.domains["household"]) is free-form extras.

Tools: add_member, remember_fact, forget_fact, recall, family_summary.
Trigger: add_member_demo (adds Anaya, 6, allergic to eggs, loves drawing).
"""

import re

from ..seed import PALETTE
from ..toolkit import Tool, ToolError
from ..voices import infer_gender
from .base import Specialist, Trigger

RELATIONS = {
    "daughter": "Daughter", "beti": "Daughter", "son": "Son", "beta": "Son", "wife": "Wife", "biwi": "Wife",
    "husband": "Husband", "pati": "Husband", "baby": "Baby", "mother": "Mom", "mom": "Mom", "maa": "Mom",
    "father": "Dad", "dad": "Dad", "papa": "Dad", "grandmother": "Grandmother", "nani": "Grandmother",
    "dadi": "Grandmother", "grandfather": "Grandfather", "nana": "Grandfather", "dada": "Grandfather",
    "brother": "Brother", "bhai": "Brother", "sister": "Sister", "behen": "Sister", "uncle": "Uncle",
    "aunt": "Aunt", "cousin": "Cousin",
}
_REL_ALT = "|".join(sorted(RELATIONS, key=len, reverse=True))
KINDS = ["adult", "child", "senior"]
GENDERS = ["female", "male"]
LANGUAGES = ["English", "Hindi", "Hinglish", "Telugu", "Kannada"]
_LOCALES = {"Hindi": "hi-IN", "Telugu": "te-IN", "Kannada": "kn-IN"}  # everything else speaks en-IN

_ADD = re.compile(
    r"\b(meet|add|welcome|introduce|joining|joins|this is|here is|here's|say hello to|yeh|ye|milo|miliye)\b[^.?!]*"
    r"\b(my|our|new|meri|mera|humare|hamare|naya|naye)\b[^.?!]*"
    r"\b(" + _REL_ALT + r"|member|sadasya)\b(?!['’]s\b)",
    re.I,
)
_ADD_NEW = re.compile(
    r"\b(?:we have|we've got|we got|there is|there's) (?:a |one )?new (?:family )?(?:member|addition|baby|daughter|son|grandchild)\b", re.I
)
_ROSTER = re.compile(
    r"\b(who(?:'s| is| are| all are| all is)(?: all)? (?:in|part of) (?:the |my |our )?family|how many (?:of us|people|members|are we)"
    r"|family members|kitne (?:log|members?|sadasya)|family (?:mein|me) kaun)\b",
    re.I,
)
_REMEMBER = re.compile(
    r"\b(remember(?:\s+(?:that|this))?|yaad rakh\w*|(?:make a )?note(?: down)?(?:\s+that)?|keep in mind(?:\s+that)?|"
    r"don't forget\s+that|do not forget\s+that)\b",
    re.I,
)
_FORGET = re.compile(
    r"(?<!don't )(?<!dont )(?<!do not )\b(forget (?:that|about)|bhool (?:jao|jana)|remove (?:the )?(?:fact|memory))\b", re.I
)
_RECALL = re.compile(
    r"\b(what do you know about|what (?:all )?do you remember about|tell me about|know about|ke baare mein|ke bare mein|"
    r"what(?:'s| is| are) \w+(?:'s)? (?:allerg\w*|preferences|likes|dislikes|restrictions)|what (?:does|do) \w+ (?:like|prefer|eat)|"
    r"(?:does|do) \w+ have any allerg\w*|(?:is|are) \w+ allergic)\b",
    re.I,
)
_OTHER = re.compile(
    r"\b(marks?|score|school|homework|exam|medicines?|dawai|tablets?|doctor|appointment|flights?|calendar|schedule|"
    r"lunch|dinner|breakfast|restaurant|table|booking|cab|free|busy|slot)\b",
    re.I,
)
_FAMILY_WORDS = re.compile(r"\b(we|us|our|everyone|everybody|family|sab|hum sab|humare|hamare)\b", re.I)
_CANCEL = re.compile(r"\b(cancel|never ?mind|stop|rehne do|nahi|no)\b", re.I)
_CONNECTORS = {"is", "named", "called", "name", "naam", "ka", "hai"}
_NOT_NAMES = {
    "the", "a", "an", "and", "she", "he", "her", "his", "ki", "ke", "who", "this", "yeh", "ye", "meet", "my", "our",
    "new", "member", "of", "family", "please", "loves", "likes", "is", "was", "age", "aged", "years",
}


# ---------------------------------------------------------------- tools

def _tags_for(fact: str) -> list[str]:
    low = fact.lower()
    rules = [
        ("allergy", r"allerg"),
        ("food", r"\b(eat|food|veg|vegetarian|spicy|mushroom|khana|dinner|lunch|breakfast|sweet|meal)"),
        ("health", r"medic|sugar|\bbp\b|knee|diabet|pressure|doctor|health"),
        ("routine", r"morning|subah|wake|uthna|sleep|bed\b|early|jaldi|evening|routine|night"),
        ("interest", r"\b(love|loves|like|likes|enjoy|enjoys|pasand|hobby|favou?rite)"),
        ("travel", r"flight|seat|aisle|travel"),
        ("school", r"school|class\b|homework"),
        ("access", r"stairs|step-free|wheelchair|access"),
    ]
    return [tag for tag, pat in rules if re.search(pat, low)] or ["general"]


def _group_of(tags: list[str]) -> str:
    if {"allergy", "health", "access"} & set(tags):
        return "health"
    if "food" in tags:
        return "food"
    if {"routine", "school", "travel"} & set(tags):
        return "routine"
    return "other"


def _next_fact_id(state) -> str:
    nums = [int(m.group(1)) for f in state.memory if (m := re.fullmatch(r"m(\d+)", f["id"]))]
    return f"m{max(nums, default=0) + 1}"


def _grade_for(age: int) -> str:
    return "Preschool" if age < 5 else f"{max(1, age - 5)}-A"


def _init_domains(state, member: dict) -> None:
    school = state.domains.get("school")
    if member["kind"] == "child" and isinstance(school, dict) and isinstance(school.get("kids"), dict):
        school["kids"].setdefault(member["id"], {
            "grade": _grade_for(member["age"]), "status": "at_home", "arrived_at": None, "last_location": "home",
            "marks": [], "homework": [], "mood_log": [],
        })
    care = state.domains.get("care")
    if member["kind"] == "senior" and isinstance(care, dict) and isinstance(care.get("seniors"), dict):
        care["seniors"].setdefault(member["id"], {
            "meds": [], "checkin_times": ["09:00", "18:00"], "last_checkin": None,
            "doctor": {"name": "", "clinic": "", "next_appointment": None},
            "emergency_contacts": [p for p in state.parents() if p != member["id"]],
        })


def _kind_from_age(age: int) -> str:
    return "child" if age < 18 else "senior" if age >= 60 else "adult"


def _check_age(age) -> int:
    if isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 120:
        raise ToolError("age must be a whole number between 0 and 120")
    return age


def _diet_fact(diet: str) -> tuple[str, list[str]] | None:
    d = (diet or "").strip().lower()
    if not d:
        return None
    if d in ("vegetarian", "veg", "pure veg", "pure vegetarian"):
        return "Vegetarian", ["food", "veg"]
    if d == "vegan":
        return "Vegan: vegetarian, no dairy or eggs", ["food", "veg"]
    if d == "jain":
        return "Jain diet: vegetarian, no onion or garlic", ["food", "veg"]
    return f"Follows a {d} diet", ["food"]


def _add_member(
    state, name: str, relation: str, age: int, kind: str | None = None, language: str = "Hinglish", about: str = "",
    gender: str | None = None, diet: list[str] | None = None, allergies: list[str] | None = None, notes: str = "",
) -> dict:
    name = (name or "").strip().title()
    if not name:
        raise ToolError("a name is required")
    age = _check_age(age)
    kind = kind or _kind_from_age(age)
    if kind not in KINDS:
        raise ToolError(f"kind must be one of {KINDS}")
    if language not in LANGUAGES:
        raise ToolError(f"language must be one of {LANGUAGES}")
    if gender is not None and gender not in GENDERS:
        raise ToolError(f"gender must be one of {GENDERS}")
    if any(m["name"].lower() == name.lower() for m in state.members):
        raise ToolError(f"{name} is already in the family")
    base = re.sub(r"[^a-z0-9]+", "", name.lower()) or "member"
    taken = {m["id"] for m in state.members}
    member_id, n = base, 2
    while member_id in taken:
        member_id, n = f"{base}{n}", n + 1
    used = {m["color"].lower() for m in state.members}
    color = next((c for c in PALETTE if c.lower() not in used), PALETTE[len(state.members) % len(PALETTE)])
    relation = (relation or "").strip().title() or "Family"
    member = {
        "id": member_id, "name": name, "relation": relation, "age": age, "kind": kind,
        "language": language, "locale": _LOCALES.get(language, "en-IN"),
        "gender": gender or infer_gender({"relation": relation}), "voice_id": None,
        "color": color, "about": about or "New to the family",
    }
    others = [m["id"] for m in state.members]
    state.members.append(member)
    if not state.persona:
        state.persona = member_id
    _init_domains(state, member)
    facts = []
    for allergy in allergies or []:
        if str(allergy).strip():
            facts.append(_remember_fact(state, member_id, f"Allergic to {str(allergy).strip().lower()}", ["allergy", "food"])["fact"])
    for item in diet or []:
        parsed = _diet_fact(str(item))
        if parsed:
            facts.append(_remember_fact(state, member_id, parsed[0], parsed[1])["fact"])
    if (notes or "").strip():
        facts.append(_remember_fact(state, member_id, notes.strip()[:200])["fact"])
    if others:
        state.notify(
            others, f"{name} ({relation}, {age}) is now part of the family on Aangan.", "household", "household",
        )
    return {"member": member, "family_size": len(state.members), "facts": facts}


def _update_member(
    state, member_id: str, name: str | None = None, relation: str | None = None, age: int | None = None,
    kind: str | None = None, language: str | None = None, gender: str | None = None,
) -> dict:
    member = next((m for m in state.members if m["id"] == member_id), None)
    if member is None:
        raise ToolError(f"unknown family member {member_id}")
    if name is not None:
        name = name.strip().title()
        if not name:
            raise ToolError("a name is required")
        if any(m["name"].lower() == name.lower() and m["id"] != member_id for m in state.members):
            raise ToolError(f"{name} is already in the family")
    if age is not None:
        _check_age(age)
    if kind is not None and kind not in KINDS:
        raise ToolError(f"kind must be one of {KINDS}")
    if language is not None and language not in LANGUAGES:
        raise ToolError(f"language must be one of {LANGUAGES}")
    if gender is not None and gender not in GENDERS:
        raise ToolError(f"gender must be one of {GENDERS}")
    if name is not None:
        member["name"] = name
    if relation is not None and relation.strip():
        member["relation"] = relation.strip().title()
    if age is not None:
        member["age"] = age
        if kind is None:
            member["kind"] = _kind_from_age(age)
    if kind is not None:
        member["kind"] = kind
    if language is not None:
        member["language"] = language
        member["locale"] = _LOCALES.get(language, "en-IN")
    if gender is not None:
        member["gender"] = gender
    _init_domains(state, member)
    return {"member": member}


def _scrub_domain(domain: dict, member_id: str) -> None:
    """Drop a removed member's records from one agent's domain data."""
    for value in domain.values():
        if isinstance(value, dict):
            value.pop(member_id, None)  # per-member maps such as school kids and care seniors
        elif isinstance(value, list):
            kept = []
            for item in value:
                if isinstance(item, dict):
                    if item.get("member_id") == member_id:
                        continue
                    if isinstance(item.get("member_ids"), list):
                        item["member_ids"] = [m for m in item["member_ids"] if m != member_id]
                        if not item["member_ids"]:
                            continue
                kept.append(item)
            value[:] = kept


def _remove_member(state, member_id: str, confirm: bool = False) -> dict:
    if confirm is not True:
        raise ToolError("Removing someone deletes their records. Ask the user to confirm, then call again with confirm=true.")
    member = next((m for m in state.members if m["id"] == member_id), None)
    if member is None:
        raise ToolError(f"unknown family member {member_id}")
    state.members.remove(member)
    state.memory[:] = [f for f in state.memory if f["about"] != member_id]
    for event in list(state.calendar):
        event["member_ids"] = [m for m in event["member_ids"] if m != member_id]
        if not event["member_ids"]:
            state.calendar.remove(event)
    for domain in state.domains.values():
        if isinstance(domain, dict):
            _scrub_domain(domain, member_id)
    if state.persona == member_id:
        state.persona = state.members[0]["id"] if state.members else ""
    state.pending = None
    return {"removed": {"id": member["id"], "name": member["name"]}, "family_size": len(state.members)}


def _remember_fact(state, about: str, fact: str, tags: list[str] | None = None) -> dict:
    if about != "family" and not any(m["id"] == about for m in state.members):
        raise ToolError(f"unknown family member {about}")
    fact = (fact or "").strip()
    if not fact:
        raise ToolError("nothing to remember")
    for existing in state.memory:
        if existing["about"] == about and existing["fact"].lower() == fact.lower():
            return {"fact": existing, "duplicate": True}
    entry = {"id": _next_fact_id(state), "about": about, "fact": fact, "tags": tags or _tags_for(fact)}
    state.memory.append(entry)
    return {"fact": entry, "duplicate": False}


def _forget_fact(state, fact_id: str) -> dict:
    entry = next((f for f in state.memory if f["id"] == fact_id), None)
    if entry is None:
        raise ToolError(f"no remembered fact {fact_id}")
    state.memory.remove(entry)
    return {"forgotten": entry}


def _recall(state, about: str) -> dict:
    if about == "family":
        name = "the family"
    else:
        name = next((m["name"] for m in state.members if m["id"] == about), None)
        if name is None:
            raise ToolError(f"unknown family member {about}")
    facts = state.facts_about(about)
    groups: dict[str, list[str]] = {"food": [], "health": [], "routine": [], "other": []}
    for f in facts:
        groups[_group_of(f["tags"])].append(f["fact"])
    return {"about": about, "name": name, "facts": facts, "groups": groups}


def _family_summary(state) -> dict:
    return {
        "count": len(state.members),
        "members": [
            {"id": m["id"], "name": m["name"], "relation": m["relation"], "age": m["age"], "kind": m["kind"], "language": m["language"]}
            for m in state.members
        ],
        "fact_count": len(state.memory),
    }


_OBJ = "object"
TOOLS = [
    Tool(
        "add_member", "Add a new person to the family so Aangan remembers and helps them too.",
        {"type": _OBJ, "properties": {
            "name": {"type": "string"}, "relation": {"type": "string", "description": "e.g. Daughter, Grandfather, Wife"},
            "age": {"type": "integer"},
            "kind": {"type": "string", "enum": KINDS, "description": "Derived from age when omitted: under 18 child, 60 and over senior"},
            "language": {"type": "string", "enum": LANGUAGES},
            "gender": {"type": "string", "enum": GENDERS},
            "diet": {"type": "array", "items": {"type": "string"}, "description": "e.g. vegetarian, vegan, jain"},
            "allergies": {"type": "array", "items": {"type": "string"}, "description": "e.g. peanuts, eggs"},
            "notes": {"type": "string", "description": "anything else worth remembering, e.g. bad knees, loves cricket"},
            "about": {"type": "string", "description": "one-line description"}},
         "required": ["name", "relation", "age"]},
        _add_member,
    ),
    Tool(
        "update_member", "Edit a family member's profile: name, relation, age, kind, language or gender.",
        {"type": _OBJ, "properties": {
            "member_id": {"type": "string"}, "name": {"type": "string"}, "relation": {"type": "string"},
            "age": {"type": "integer"}, "kind": {"type": "string", "enum": KINDS},
            "language": {"type": "string", "enum": LANGUAGES}, "gender": {"type": "string", "enum": GENDERS}},
         "required": ["member_id"]},
        _update_member,
    ),
    Tool(
        "remove_member", "Remove a person and all of their records from the family. Only call with confirm=true after the user has confirmed.",
        {"type": _OBJ, "properties": {"member_id": {"type": "string"}, "confirm": {"type": "boolean"}},
         "required": ["member_id", "confirm"]},
        _remove_member,
    ),
    Tool(
        "remember_fact", "Store a preference, allergy, routine or other fact about a family member (or 'family').",
        {"type": _OBJ, "properties": {
            "about": {"type": "string", "description": "member id, or 'family'"}, "fact": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}}},
         "required": ["about", "fact"]},
        _remember_fact,
    ),
    Tool(
        "forget_fact", "Remove a remembered fact by its id.",
        {"type": _OBJ, "properties": {"fact_id": {"type": "string"}}, "required": ["fact_id"]},
        _forget_fact,
    ),
    Tool(
        "recall", "Read back what the family knows about a member (or 'family'), grouped into food, health, routine, other.",
        {"type": _OBJ, "properties": {"about": {"type": "string", "description": "member id, or 'family'"}}, "required": ["about"]},
        _recall,
    ),
    Tool(
        "family_summary", "List every family member with relation, age and language.",
        {"type": _OBJ, "properties": {}},
        _family_summary,
    ),
]


# ---------------------------------------------------------------- parsing

def _relation_in(text: str) -> tuple[str, int] | None:
    m = re.search(r"\b(" + _REL_ALT + r")\b", text, re.I)
    return (RELATIONS[m.group(1).lower()], m.end()) if m else None


def _extract_name(text: str, start: int) -> str | None:
    tokens = re.findall(r"[A-Za-z']+", text[start:])
    for tok in tokens:
        if tok.lower() in _CONNECTORS:
            continue
        if tok.lower() in _NOT_NAMES or tok.lower() in RELATIONS:
            return None
        return tok.title()
    return None


def _extract_age(text: str) -> int | None:
    low = text.lower()
    m = re.search(r"\b(\d{1,3})\s*(?:years?|yrs?|saal|sal)\b", low) or re.search(r"\b(?:is|age|aged|umar|she's|he's)\s+(\d{1,3})\b", low)
    if not m:
        return None
    age = int(m.group(1))
    return age if 0 <= age <= 120 else None


def _facts_from(text: str) -> list[tuple[str, list[str]]]:
    low = text.lower()
    out: list[tuple[str, list[str]]] = []

    def add(fact: str, tags: list[str]) -> None:
        if (fact, tags) not in out:
            out.append((fact, tags))

    for m in re.finditer(r"allergic to ([a-z ]+?)(?:[,.;]|\band\b|$)", low):
        add(f"Allergic to {m.group(1).strip()}", ["allergy", "food"])
    for m in re.finditer(r"\b([a-z]+)\s+se\s+allergy", low):
        add(f"Allergic to {m.group(1)}", ["allergy", "food"])
    for m in re.finditer(r"(?:doesn't like|does not like|dislikes?|hates?)\s+([a-z ]+?)(?:[,.;]|\band\b|$)", low):
        add(f"Dislikes {m.group(1).strip()}", ["dislike"])
    for m in re.finditer(r"(?<!n't )(?<!not )\b(?:loves?|likes?|enjoys?)\s+([a-z ]+?)(?:[,.;]|\band\b|\bis\b|$)", low):
        add(f"Loves {m.group(1).strip()}", ["interest"])
    for m in re.finditer(r"\b([a-z]+)\s+pasand\s+hai", low):
        add(f"Loves {m.group(1)}", ["interest"])
    if re.search(r"\b(vegetarian|veg)\b", low):
        add("Vegetarian", ["food", "veg"])
    return out


def _kind_for(age: int) -> str:
    return "child" if age < 18 else "senior" if age >= 60 else "adult"


def _fact_text(text: str, members: list[dict]) -> str:
    m = _REMEMBER.search(text)
    if m:
        after = re.sub(r"^\s*(?:that|this|ki|ke|[:,])\s*", "", text[m.end():], flags=re.I).strip(" .,!?")
        before = text[: m.start()].strip(" .,!?")
        body = after or before  # "remember that X" or "X, remember that"
    else:
        body = text.strip(" .,!?")
    body = re.sub(r"\b(?:please|pls)\b", "", body, flags=re.I).strip(" ,.!?")
    body = re.sub(r"^(?:that|this)\s+", "", body, flags=re.I)
    for mem in members:
        body = re.sub(rf"^{re.escape(mem['name'])}(?:'s)?\s+(?!ko\b|ka\b|ki\b|ke\b|se\b)", "", body, flags=re.I)
    return body[:1].upper() + body[1:]


_THIRD_VERB = {"have": "has", "do": "does", "go": "goes", "be": "is"}
_ADVERBS = {"usually", "always", "never", "often", "only", "sometimes", "mostly"}


def _third(verb: str) -> str:
    v = verb.lower()
    if v in _THIRD_VERB:
        return _THIRD_VERB[v]
    if re.search(r"(s|sh|ch|x|z)$", v):
        return v + "es"
    if re.search(r"[^aeiou]y$", v):
        return v[:-1] + "ies"
    return v + "s"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _third_person(body: str) -> str:
    """'I don't like mushrooms' -> 'Doesn't like mushrooms' (the predicate; the person is stored separately)."""
    b = body.strip().rstrip(".!?")
    rules = [
        (r"^i (?:do not|don't|dont) like (.+)$", lambda m: f"Doesn't like {m.group(1)}"),
        (r"^i (?:do not|don't|dont) (eat|drink|want|enjoy|have|take) (.+)$", lambda m: f"Doesn't {m.group(1)} {m.group(2)}"),
        (r"^i (?:can't|cannot|can not|cant) (eat|drink|have|stand|take) (.+)$", lambda m: f"Can't {m.group(1)} {m.group(2)}"),
        (r"^i(?: am|'m) (?:allergic|allergy prone) to (.+)$", lambda m: f"Allergic to {m.group(1)}"),
        (r"^i(?: am|'m) (?:a )?(vegetarian|vegan|veg)\b.*$", lambda m: "Vegetarian" if m.group(1) != "vegan" else "Vegan"),
        (r"^i(?: am|'m) (.+)$", lambda m: _cap(m.group(1))),
        (r"^my (.+?) (?:is|are) (.+)$", lambda m: f"{_cap(m.group(1))} is {m.group(2)}"),
        (r"^i (" + "|".join(sorted(_ADVERBS)) + r") (\w+)(.*)$", lambda m: f"{_cap(m.group(1))} {_third(m.group(2))}{m.group(3)}"),
        (r"^i (\w+)(.*)$", lambda m: f"{_cap(_third(m.group(1)))}{m.group(2)}"),
    ]
    for pattern, build in rules:
        m = re.match(pattern, b, re.I)
        if m:
            out = build(m)
            return _cap(out[3:]) if out.startswith("Is ") else _cap(out)
    return _cap(re.sub(r"\bmy\b", "their", b, flags=re.I))


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def _sentence(name: str, predicate: str) -> str:
    """'Rahul' + "Doesn't like mushrooms" -> "Rahul doesn't like mushrooms"."""
    low = predicate.lower()
    if re.match(r"(allergic|vegetarian|vegan|afraid|scared)", low):
        return f"{name} is {_lower_first(predicate)}"
    if re.match(r"(favourite|favorite)", low):
        return f"{name}'s {_lower_first(predicate)}"
    return f"{name} {_lower_first(predicate)}"


def _targets(state, member_id: str, text: str) -> list[str]:
    if _FAMILY_WORDS.search(text):
        return ["family"]
    found = [m["id"] for m in state.mentioned_members(text)]
    return found or [member_id]


# ---------------------------------------------------------------- agent

class HouseholdAgent(Specialist):
    name = "household"
    title = "Household agent"
    keywords = ("remember", "add", "new member", "meet", "daughter", "son", "wife", "husband", "preference", "likes", "allergic", "allergy", "who is", "everyone", "family", "yaad", "about")
    tools = TOOLS
    family_keys = ()

    def seed(self) -> dict:
        return {}

    # --- intent detection (shared by score and handle)
    def _intent(self, text: str) -> str | None:
        if _ROSTER.search(text):
            return "roster"
        if _ADD.search(text) or _ADD_NEW.search(text):
            return "add"
        if _FORGET.search(text):
            return "forget"
        if _REMEMBER.search(text):
            return "remember"
        if _RECALL.search(text) and not _OTHER.search(text):
            return "recall"
        return None

    def score(self, state, text: str) -> int:
        from .money import is_money

        return 5 if not is_money(text) and self._intent(text) else 0

    def handle(self, state, member_id: str, text: str) -> str | None:
        pend = state.pending
        if pend and pend.get("agent") == self.name:
            return self._continue(state, member_id, text, pend)
        intent = self._intent(text)
        if intent == "roster":
            return self._roster(state, member_id)
        if intent == "add":
            return self._start_add(state, member_id, text)
        if intent == "forget":
            return self._forget(state, member_id, text)
        if intent == "remember":
            return self._remember(state, member_id, text)
        if intent == "recall":
            return self._recall(state, member_id, text)
        return None

    # --- add member (multi-turn when details are missing)
    def _start_add(self, state, member_id: str, text: str) -> str:
        draft: dict = {"facts": _facts_from(text)}
        rel = _relation_in(text)
        if rel:
            draft["relation"] = rel[0]
            draft["name"] = _extract_name(text, rel[1])
        draft["age"] = _extract_age(text)
        return self._advance(state, member_id, draft)

    def _continue(self, state, member_id: str, text: str, pend: dict) -> str:
        draft = pend["draft"]
        if _CANCEL.search(text) and not re.search(r"\d", text):
            state.pending = None
            return self.say(state, member_id, "Okay, I won't add anyone for now.", "Theek hai, abhi kisi ko add nahi karta.")
        if not draft.get("relation"):
            rel = _relation_in(text)
            if rel:
                draft["relation"] = rel[0]
                draft["name"] = draft.get("name") or _extract_name(text, rel[1])
        if not draft.get("name"):
            caps = [t for t in re.findall(r"[A-Za-z']+", text) if t[0].isupper() and t.lower() not in _NOT_NAMES]
            words = re.findall(r"[A-Za-z']+", text)
            draft["name"] = caps[0] if caps else (words[0].title() if len(words) == 1 else None)
        if draft.get("age") is None:
            bare = re.fullmatch(r"\s*(\d{1,3})\s*", text)
            draft["age"] = int(bare.group(1)) if bare else _extract_age(text)
        draft["facts"] += [f for f in _facts_from(text) if f not in draft["facts"]]
        return self._advance(state, member_id, draft)

    def _advance(self, state, member_id: str, draft: dict) -> str:
        if not draft.get("relation") or not draft.get("name"):
            state.pending = {"agent": self.name, "step": "details", "draft": draft}
            return self.say(
                state, member_id,
                "Happy to add them. What's their name and how are they related to you?",
                "Zaroor. Unka naam kya hai aur woh aapke kya lagte hain?",
            )
        if draft.get("age") is None:
            state.pending = {"agent": self.name, "step": "age", "draft": draft}
            return self.say(state, member_id, f"How old is {draft['name']}?", f"{draft['name']} kitne saal ke hain?")
        state.pending = None
        return self._finish_add(state, member_id, draft)

    def _finish_add(self, state, member_id: str, draft: dict) -> str:
        age = draft["age"]
        kind = _kind_for(age)
        language = "Hindi" if kind == "senior" else "Hinglish"
        interests = [f for f, tags in draft["facts"] if "interest" in tags]
        about = interests[0] if interests else ""
        status, res = self.call(
            state, "add_member", name=draft["name"], relation=draft["relation"], age=age, kind=kind, language=language, about=about
        )
        if status != "ok":
            problem = res["error"]
            return self.say(state, member_id, f"I couldn't add them: {problem}.", f"Add nahi kar paya: {problem}.")
        member = res["member"]
        has_allergy = False
        for fact, tags in draft["facts"]:
            self.call(state, "remember_fact", about=member["id"], fact=fact, tags=tags)
            has_allergy = has_allergy or "allergy" in tags
        name = member["name"]
        en = f"{name} is now part of the family"
        hi = f"{name} ab parivaar ka hissa hain"
        if has_allergy:
            en += "; I'll keep that allergy in mind for bookings"
            hi += "; allergy ka dhyaan booking mein rakhunga"
        return self.say(state, member_id, en + ". I've told everyone.", hi + ". Sabko bata diya.")

    # --- remember / forget / recall / roster
    def _remember(self, state, member_id: str, text: str) -> str:
        targets = _targets(state, member_id, text)
        members = [state.member(t) for t in targets if t != "family"]
        fact = _fact_text(text, members)
        if not fact:
            return self.say(state, member_id, "What should I remember?", "Kya yaad rakhna hai?")
        first_person = bool(re.match(r"^(i\b|i'm\b|my\b)", fact, re.I))
        if first_person:  # "I don't like mushrooms" said by Rahul is stored as a fact about Rahul
            fact = _third_person(fact)
        duplicate = True
        for t in targets:
            _, res = self.call(state, "remember_fact", about=t, fact=fact)
            duplicate = duplicate and res.get("duplicate", False)
        who = "the family" if targets == ["family"] else " and ".join(m["name"] for m in members)
        if fact.lower().startswith("is "):
            fact = _cap(fact[3:])
        if len(members) == 1 and fact.lower().startswith(members[0]["name"].lower()):
            said_en = fact  # the fact already names the person (e.g. Hinglish "Dadi ko subah jaldi uthna pasand hai")
        elif len(members) == 1:
            said_en = _sentence(members[0]["name"], fact)
        else:
            said_en = f"{who} {_lower_first(fact)}"
        if duplicate:
            return self.say(state, member_id, f"I already knew that about {who}.", f"Yeh toh main pehle se jaanta hoon, {who} ke baare mein.")
        return self.say(state, member_id, f"Got it, I'll remember that {said_en}.", f"Theek hai, {who} ke liye yaad rakhunga: {fact}.")

    def _forget(self, state, member_id: str, text: str) -> str:
        targets = _targets(state, member_id, text)
        words = {w for w in re.findall(r"[a-z']+", text.lower()) if len(w) >= 4}
        best, best_score = None, 0
        for f in state.memory:
            if f["about"] not in targets and targets != ["family"]:
                continue
            overlap = len(words & set(re.findall(r"[a-z']+", f["fact"].lower())))
            if overlap > best_score:
                best, best_score = f, overlap
        if best is None:
            return self.say(state, member_id, "I couldn't find that in what I remember.", "Yeh mujhe yaad ki list mein nahi mila.")
        self.call(state, "forget_fact", fact_id=best["id"])
        return self.say(state, member_id, f"Forgotten: {best['fact']}.", f"Bhool gaya: {best['fact']}.")

    def _recall(self, state, member_id: str, text: str) -> str:
        about = _targets(state, member_id, text)[0]
        _, res = self.call(state, "recall", about=about)
        parts = [f"{label}: {'; '.join(items[:2])}" for label, items in res["groups"].items() if items]
        if not parts:
            return self.say(state, member_id, f"I don't know much about {res['name']} yet.", f"{res['name']} ke baare mein abhi zyada nahi pata.")
        body = ". ".join(parts)
        lead = {"food": "On food", "health": "On health", "routine": "On routine", "other": "Also"}
        spoken = ". ".join(
            f"{lead.get(label, label.capitalize())}, " + " and ".join(_lower_first(i) for i in items[:2])
            for label, items in res["groups"].items() if items
        )
        return self.say(state, member_id, f"About {res['name']}. {spoken}.", f"{res['name']} ke baare mein, {body}.")

    def _roster(self, state, member_id: str) -> str:
        _, res = self.call(state, "family_summary")
        people = ", ".join(f"{m['name']} ({m['relation']}, {m['age']})" for m in res["members"])
        spoken = [f"{m['name']} the {m['relation'].lower()}, {m['age']}" for m in res["members"]]
        listed_en = ", ".join(spoken[:-1]) + (f", and {spoken[-1]}" if len(spoken) > 1 else spoken[0] if spoken else "")
        return self.say(state, member_id, f"There are {res['count']} of you: {listed_en}.", f"Aap sab {res['count']} log hain: {people}.")

    # --- demo trigger
    def _demo_add(self, state) -> str:
        speaker = state.persona if any(m["id"] == state.persona for m in state.members) else state.members[0]["id"]
        if any(m["name"] == "Anaya" for m in state.members):
            reply = self.say(state, speaker, "Anaya is already part of the family.", "Anaya pehle se parivaar ka hissa hain.")
        else:
            reply = self._start_add(state, speaker, "Meet my daughter Anaya, she is 6, loves drawing and is allergic to eggs")
        state.say("agent", reply, speaker, agent=self.name)
        return reply

    def __init__(self) -> None:
        self.triggers = [Trigger("add_member_demo", "Add a new family member", self._demo_add)]
