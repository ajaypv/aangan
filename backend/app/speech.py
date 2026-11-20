"""Spoken-English helpers shared by the rule engine.

clean_input(text): make a speech recogniser's output look like what the agents expect (fillers, mis-heard names,
                   spoken numbers such as "forty two" or "ten thirty").
speakable(text):   make an English reply sound natural when a TTS voice reads it (times, money, dates, codes).
"""

import re
from datetime import date as _date

ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000}
ORD_ONES = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
    "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
}
ORD_TENS = {"twentieth": 20, "thirtieth": 30}
CARDINAL = {**ONES, **TENS, **SCALES}
ORDINAL = {**ORD_ONES, **ORD_TENS}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MONTH_WORDS = set(MONTHS) | {m[:3] for m in MONTHS} | {"sept"}
TIME_PREPS = {"at", "by", "around", "till", "until", "before", "after", "to", "from", "about"}

_WORD = re.compile(r"[A-Za-z']+")


# ------------------------------------------------------------------ number words <-> digits

def _parse_run(words: list[str]) -> list[tuple[int, bool]]:
    """Turn a run of number words into [(value, is_ordinal)]; 'ten thirty' becomes two numbers."""
    out: list[tuple[int, bool]] = []
    total = current = 0
    have = False

    def flush(ordinal: bool = False) -> None:
        nonlocal total, current, have
        if have:
            out.append((total + current, ordinal))
        total = current = 0
        have = False

    for w in words:
        if w == "and":
            continue
        ordinal = w in ORDINAL
        base = ORD_ONES.get(w) if w in ORD_ONES else ORD_TENS.get(w) if w in ORD_TENS else None
        if w in ONES or w in ORD_ONES:
            v = ONES[w] if w in ONES else base
            after_tens = current % 100 in (20, 30, 40, 50, 60, 70, 80, 90) and 1 <= v <= 9
            after_hundred = (current % 100 == 0 and current >= 100) or (current == 0 and total > 0)
            if not have or after_tens or after_hundred:
                current += v
                have = True
            else:
                flush()
                current, have = v, True
        elif w in TENS or w in ORD_TENS:
            v = TENS[w] if w in TENS else base
            if not have or (current % 100 == 0 and current >= 100) or (current == 0 and total > 0):
                current += v
                have = True
            else:
                flush()
                current, have = v, True
        elif w in SCALES:
            scale = SCALES[w]
            if scale == 100:
                current = (current or 1) * 100 if current < 100 else current
            else:
                total += (current or 1) * scale
                current = 0
            have = True
        if ordinal:
            flush(True)
    flush()
    return out


def _suffix(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def numbers_to_digits(text: str) -> str:
    """'forty two out of fifty' -> '42 out of 50'; 'ten thirty' after 'at' -> '10:30'; 'twenty sixth december' -> '26th december'."""
    text = re.sub(r"\ba\s+(hundred|thousand|lakh)\b", r"one \1", text, flags=re.I)
    tokens = re.findall(r"[A-Za-z']+|\d+(?:[.,]\d+)*|\s+|[^\sA-Za-z\d]", text)
    out: list[str] = []
    i = 0

    def prev_word() -> str:
        for tok in reversed(out):
            if tok.strip():
                return tok.lower()
        return ""

    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if not (_WORD.fullmatch(tok) and (low in CARDINAL or low in ORDINAL)):
            out.append(tok)
            i += 1
            continue
        # gather a run: number words joined by spaces or hyphens ('and' only between scales and units)
        run, j, last = [low], i + 1, i
        while j < len(tokens):
            sep = tokens[j]
            if sep.strip() in ("", "-") and j + 1 < len(tokens) and sep.strip() != "" or (sep.isspace() and j + 1 < len(tokens)):
                nxt = tokens[j + 1].lower()
                if nxt in CARDINAL or nxt in ORDINAL:
                    run.append(nxt)
                    last = j + 1
                    j += 2
                    continue
                if nxt == "and" and run[-1] in SCALES and j + 3 < len(tokens) and tokens[j + 3].lower() in CARDINAL:
                    run.append("and")
                    j += 2
                    continue
            break
        after, after2 = "", ""
        for tok2 in tokens[last + 1:]:
            if tok2.strip():
                if not after:
                    after = tok2.lower()
                else:
                    after2 = tok2.lower()
                    break
        before = prev_word()
        items = _parse_run(run)
        pieces: list[str] = []
        k = 0
        while k < len(items):
            val, is_ord = items[k]
            if is_ord:
                around_month = before in MONTH_WORDS or after in MONTH_WORDS or (after == "of" and after2 in MONTH_WORDS)
                if around_month or len(run) > 1:
                    pieces.append(f"{val}{_suffix(val)}")
                else:
                    pieces.append(run[0])
                k += 1
                continue
            if (
                k + 1 < len(items) and not items[k + 1][1] and 1 <= val <= 12 and 0 <= items[k + 1][0] <= 59
                and (before in TIME_PREPS or re.match(r"[ap]\.?m", after))
            ):
                pieces.append(f"{val}:{items[k + 1][0]:02d}")
                k += 2
                continue
            if len(run) == 1 and run[0] == "one" and not (
                after in {"pm", "am", "o'clock", "oclock", "hundred", "thousand", "percent", "out"} or before in TIME_PREPS
            ):
                pieces.append("one")
            elif len(run) == 1 and run[0] == "zero":
                pieces.append("zero")
            else:
                pieces.append(str(val))
            k += 1
        out.append(" ".join(pieces))
        i = last + 1
    result = "".join(out)
    result = re.sub(r"\bhalf past (\d{1,2})\b", lambda m: f"{int(m.group(1))}:30", result, flags=re.I)
    result = re.sub(r"\bquarter past (\d{1,2})\b", lambda m: f"{int(m.group(1))}:15", result, flags=re.I)
    result = re.sub(r"\bquarter to (\d{1,2})\b", lambda m: f"{(int(m.group(1)) - 2) % 12 + 1}:45", result, flags=re.I)
    result = re.sub(r"\b(\d{1,2}) o'?clock\b", lambda m: f"{int(m.group(1))}:00", result, flags=re.I)
    result = re.sub(r"(\d)\s*([ap])\.\s*m\.?|(\d)\s+([ap])\s+m\b", lambda m: f"{m.group(1) or m.group(3)} {(m.group(2) or m.group(4)).lower()}m", result, flags=re.I)
    return result


_SMALL = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
    "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS_WORDS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def num_to_words(n: int) -> str:
    if n < 0:
        return "minus " + num_to_words(-n)
    if n < 20:
        return _SMALL[n]
    if n < 100:
        return _TENS_WORDS[n // 10] + (f" {_SMALL[n % 10]}" if n % 10 else "")
    if n < 1000:
        return f"{_SMALL[n // 100]} hundred" + (f" {num_to_words(n % 100)}" if n % 100 else "")
    if n < 100000:
        return f"{num_to_words(n // 1000)} thousand" + (f" {num_to_words(n % 1000)}" if n % 1000 else "")
    if n < 10000000:
        return f"{num_to_words(n // 100000)} lakh" + (f" {num_to_words(n % 100000)}" if n % 100000 else "")
    return str(n)


def ordinal_words(n: int) -> str:
    special = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth"}
    if n in special:
        return special[n]
    if n < 20:
        return num_to_words(n) + "th"
    if n % 10 == 0:
        return num_to_words(n).replace("y", "ieth") if n < 100 else num_to_words(n) + "th"
    head = num_to_words(n - n % 10)
    return f"{head} {ordinal_words(n % 10)}"


# ------------------------------------------------------------------ input cleaning

_LEAD = re.compile(
    r"^(?:\s*(?:um+|uh+|uhh+|erm+|er+|ah+|hmm+|mm+|well|so|okay|ok|alright|all right|hey|hi|hello|aangan|angan|anghan|aangaan|ongan)\b[\s,.!?-]*)+",
    re.I,
)
_INLINE_FILLER = re.compile(r"\b(?:um+|uh+|uhh+|erm|hmm+)\b[\s,]*", re.I)
_PLEASE = re.compile(r"\b(?:please|pls|kindly)\b[\s,]*", re.I)

_MISHEARD = [
    (r"\b(?:arav|aaraav|aarov|arrav|aaruv|aarva|aaarav)\b", "Aarav"),
    (r"\b(?:dhadhi|dadhi|daadi|dadee|dadie|dhaadi|dhadi|dady)\b", "Dadi"),
    (r"\b(?:grandma|granny|grannie|grandmom|gran|nani)\b", "Dadi"),
    (r"\b(?:pria|preeya|priyah|prea)\b", "Priya"),
    (r"\b(?:rahool|rahull|raul|rahol)\b", "Rahul"),
    (r"\b(?:mummy|mum|mama|mommy)\b", "mom"),
    (r"\b(?:papa|father)\b", "dad"),
    (r"\bbooked it\b|\bbooking it\b", "book it"),
    (r"\bdoctors\b", "doctor's"),
]
_CARE_CONTEXT = re.compile(r"\b(her|she|hers|medicines?|medication|tablets?|pills?|doctor|knees?|dadi|grand\w*)\b", re.I)

_AFFIRM = re.compile(
    r"\b(go ahead|do it|sounds (?:good|great|perfect)|that works|that's fine|that is fine|let's do it|lets do it|works for me|"
    r"yes please|absolutely|definitely|of course|sure thing|perfect|that sounds (?:good|great)|please do|go for it)\b",
    re.I,
)
_NEGATE = re.compile(
    r"\b(no thanks|no thank you|not now|never ?mind|forget it|skip it|leave it|cancel that|i changed my mind|don't|do not|not really)\b",
    re.I,
)
_YES_WORDS = re.compile(r"\b(yes|yeah|yep|yup|ok|okay|sure|confirm|book)\b", re.I)
_NO_WORDS = re.compile(r"\b(no|nope|cancel|stop|nahi)\b", re.I)


_GRANDMOTHER_RELATIONS = {"grandmother", "grandma", "dadi", "nani"}


def _name_fixes(members: list[dict] | None) -> list[tuple[str, str]]:
    """Mishearing fixes for names. With no member list (legacy callers) the demo family's names are assumed;
    otherwise a fix only applies to a person who actually exists, so 'Arav' is never forced into 'Aarav'."""
    if members is None:
        return [(p, r) for p, r in _MISHEARD if r in {"Aarav", "Dadi", "Priya", "Rahul"} or r not in _NAME_TARGETS]
    names = {m["name"].lower(): m["name"] for m in members}
    grandmother = next((m["name"] for m in members if m.get("relation", "").lower() in _GRANDMOTHER_RELATIONS), None)
    fixes = []
    for pattern, replacement in _MISHEARD:
        if replacement in _NAME_TARGETS:
            if replacement == "Dadi" and pattern.startswith(r"\b(?:grandma"):
                if grandmother:
                    fixes.append((pattern, grandmother))
            elif replacement.lower() in names:
                fixes.append((pattern, names[replacement.lower()]))
        else:
            fixes.append((pattern, replacement))
    return fixes


_NAME_TARGETS = {"Aarav", "Dadi", "Priya", "Rahul"}


def clean_input(text: str, members: list[dict] | None = None) -> str:
    """Normalise what a speech recogniser produced into the text the agents were written for."""
    original = text
    text = text.strip()
    stripped = _LEAD.sub("", text)
    if len(stripped.strip()) >= 2:
        text = stripped
    text = _INLINE_FILLER.sub("", text)
    text = _PLEASE.sub("", text)
    if re.search(r"\bdaddy\b", text, re.I):
        dadi = "Dadi" if members is None else next((m["name"] for m in members if m["name"].lower() == "dadi"), None)
        text = re.sub(r"\bdaddy\b", dadi if dadi and _CARE_CONTEXT.search(text) else "dad", text, flags=re.I)
    for pattern, replacement in _name_fixes(members):
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = numbers_to_digits(text)
    text = re.sub(r"(\d(?:st|nd|rd|th))\s+of\s+(" + "|".join(sorted(MONTH_WORDS, key=len, reverse=True)) + r")\b", r"\1 \2", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if not text:
        return original.strip()
    if len(text.split()) <= 6:
        if _AFFIRM.search(text) and not _YES_WORDS.search(text) and not _NO_WORDS.search(text):
            text = "yes " + text
        elif _NEGATE.search(text) and not _NO_WORDS.search(text):
            text = "no " + text
    return text


# ------------------------------------------------------------------ output for TTS

_AIRPORTS = {"BLR": "Bengaluru", "DEL": "Delhi", "GOI": "Goa", "BOM": "Mumbai", "HYD": "Hyderabad", "MAA": "Chennai"}
_DIGIT_WORDS = _SMALL[:10]
_MONTH_NAMES = {m[:3]: m.capitalize() for m in MONTHS}
_WEEKDAYS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


def _hour_words(h: int, m: int) -> str:
    if h == 0 and m == 0:
        return "midnight"
    if h == 12 and m == 0:
        return "noon"
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    if m == 0:
        return f"{num_to_words(h12)} {suffix}"
    minutes = f"oh {num_to_words(m)}" if m < 10 else num_to_words(m)
    return f"{num_to_words(h12)} {minutes} {suffix}"


def _spell(chars: str, sep: str = " ") -> str:
    return sep.join(_DIGIT_WORDS[int(c)] if c.isdigit() else c.upper() for c in chars if c.isalnum())


def _money(n: int) -> str:
    if 1100 <= n <= 1900 and n % 100 == 0:
        return f"{num_to_words(n // 100)} hundred rupees"
    return f"{num_to_words(n)} rupees"


def _int(m: re.Match) -> str:
    n = int(m.group(0).replace(",", ""))
    if 1900 <= n <= 2099:
        return f"twenty {num_to_words(n % 100)}" if n % 100 >= 10 else (f"twenty twenty" if n == 2020 else f"twenty oh {num_to_words(n % 100)}")
    return num_to_words(n)


def speakable(text: str) -> str:
    """Rewrite an English reply so a TTS voice reads it naturally: no clock digits, 'Rs', codes or symbols."""
    t = text
    # codes first (they contain digits)
    t = re.sub(
        r"\b(?:PNR|booking reference)(\s+is)?\s+(?=[A-Z0-9]{5,8}\b)(?=[A-Z0-9]*\d)([A-Z0-9]{5,8})\b",
        lambda m: "booking reference" + (m.group(1) or "") + " " + _spell(m.group(2), ", "), t,
    )
    t = re.sub(
        r"\b(?:cab\s+)?CAB-(\d{3,6})\b",
        lambda m: ("Cab" if m.group(0)[0] == "C" else "cab") + " number " + _spell(m.group(1)), t, flags=re.I,
    )
    t = re.sub(r"\b(\d[A-Z]|[A-Z]\d|[A-Z]{2})-(\d{2,5})\b", lambda m: _spell(m.group(1)) + " " + _spell(m.group(2)), t)
    t = re.sub(r"\bT(\d)\b", lambda m: f"terminal {num_to_words(int(m.group(1)))}", t)
    for code, name in _AIRPORTS.items():
        t = re.sub(rf"\b{code}\b", name, t)
    t = re.sub(r"\s*(?:->|→)\s*", " to ", t)
    # dates
    def iso(m: re.Match) -> str:
        d = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return f"{d.strftime('%A')} the {ordinal_words(d.day)}"

    t = re.sub(r"\b(20\d{2})-(\d{2})-(\d{2})\b", iso, t)
    mon_alt = "|".join(m[:3] for m in MONTHS)
    t = re.sub(
        rf"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:{mon_alt})[a-z]*\b",
        lambda m: f"{_WEEKDAYS[m.group(1).lower()]} the {ordinal_words(int(m.group(2)))}", t, flags=re.I,
    )
    t = re.sub(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({mon_alt})[a-z]*\b",
        lambda m: f"the {ordinal_words(int(m.group(1)))} of {_MONTH_NAMES[m.group(2).lower()]}", t, flags=re.I,
    )
    # times and ranges
    t = re.sub(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", r"\1 to \2", t)
    def _clock(m):
        hour, minute, marker = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if marker.startswith("p") and hour < 12:
            hour += 12  # "7:15 PM" already says which half of the day: use it, and swallow the marker so it is not spoken twice
        elif marker.startswith("a") and hour == 12:
            hour = 0
        return _hour_words(hour, minute)

    t = re.sub(r"\b(\d{1,2}):(\d{2})\b(?:\s*([AaPp])\.?[Mm]\b)?", _clock, t)
    # money, percent, fractions, units
    t = re.sub(r"(?:Rs\.?|₹|INR)\s*(\d{1,3}(?:,\d{3})+|\d+)", lambda m: _money(int(m.group(1).replace(",", ""))), t)
    t = re.sub(r"(\d+)\s*%", lambda m: f"{num_to_words(int(m.group(1)))} percent", t)
    t = re.sub(r"\b(\d+)/(\d+)\b", lambda m: f"{num_to_words(int(m.group(1)))} out of {num_to_words(int(m.group(2)))}", t)
    t = re.sub(r"(\d+)\s*mg\b", lambda m: f"{num_to_words(int(m.group(1)))} milligrams", t)
    t = re.sub(r"\b(\d+)\.(\d+)\b", lambda m: f"{num_to_words(int(m.group(1)))} point {_spell(m.group(2))}", t)
    t = re.sub(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b", _int, t)
    # symbols
    t = t.replace("&", " and ").replace("—", ", ").replace("–", ", ")
    t = re.sub(r"\s*[:;]\s+", ", ", t)
    t = re.sub(r"\s*\(([^)]*)\)", r", \1,", t)
    t = re.sub(r"[*_#]", "", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,+", ",", t)
    t = re.sub(r",\s*([.?!])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    # a number spelled out at the start of a sentence still starts with a capital
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
