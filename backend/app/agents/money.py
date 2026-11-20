"""Money agent: the family's expense tracker and saving coach.

Domain data (state.domains["money"]): expenses[{id, member_id, amount, category, note, date, source}],
budgets{"total": n|None, "<category>": n}, currency "INR". Extend, don't rename fields.
Categories: groceries, eating out, transport, bills, health, education, shopping, entertainment, travel, other.
`family_keys` lists what a fresh household clears; seed() is demo content (about 45 expenses, eating out over budget).
`overview(state)` and `classify(text)` are module-level so the Home screen, the impact endpoint and other agents can use them.
"""

import re
from collections import defaultdict
from datetime import date as _date, timedelta

from .. import calendar_core as cal
from ..toolkit import Tool, ToolError
from .base import Specialist, Trigger

CATEGORIES = ["groceries", "eating out", "transport", "bills", "health", "education", "shopping", "entertainment", "travel", "other"]
LABEL = {
    "groceries": "groceries", "eating out": "eating out", "transport": "transport and fuel", "bills": "bills and utilities",
    "health": "health and pharmacy", "education": "education", "shopping": "shopping", "entertainment": "entertainment",
    "travel": "travel", "other": "other",
}
SYNONYMS = {
    "groceries": ["groceries", "grocery", "vegetables", "veggies", "fruits", "fruit", "milk", "kirana", "supermarket", "bigbasket",
                  "blinkit", "zepto", "provisions", "ration", "kitchen"],
    "eating out": ["eating out", "eat out", "dining out", "dining", "restaurant", "restaurants", "cafe", "coffee", "zomato", "swiggy",
                   "takeaway", "takeout", "food delivery", "ordering food", "order food", "lunch", "dinner", "breakfast", "snacks",
                   "pizza", "biryani", "ice cream", "takeaways", "dine out", "meal", "meals", "food"],
    "transport": ["transport", "fuel", "petrol", "diesel", "cab", "cabs", "uber", "ola", "auto", "metro", "bus", "parking", "toll",
                  "taxi", "commute", "rickshaw", "fastag", "travel card"],
    "bills": ["bills", "bill", "electricity", "water bill", "gas", "internet", "wifi", "broadband", "phone", "recharge", "mobile",
              "rent", "utilities", "utility", "dth", "maintenance", "emi"],
    "health": ["health", "medicine", "medicines", "medical", "pharmacy", "doctor", "hospital", "clinic", "dentist", "tablets",
               "checkup", "check-up", "lab test", "tests"],
    "education": ["education", "school", "fees", "fee", "tuition", "tuitions", "books", "stationery", "coaching", "course", "exam"],
    "shopping": ["shopping", "clothes", "clothing", "shoes", "amazon", "flipkart", "myntra", "gadget", "gadgets", "electronics",
                 "furniture", "gift", "gifts", "dress", "toys"],
    "entertainment": ["entertainment", "movie", "movies", "netflix", "prime", "subscription", "subscriptions", "concert", "games",
                      "game", "cricket", "swimming", "football", "hobby", "sports", "park", "fun"],
    "travel": ["travel", "flight", "flights", "hotel", "trip", "holiday", "vacation", "train", "airfare", "resort"],
    "other": ["other", "misc", "miscellaneous", "donation", "charity", "temple"],
}
_SYN_RE = {c: re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(ws, key=len, reverse=True)) + r")\b") for c, ws in SYNONYMS.items()}

LARGE_CHILD_SPEND = 500
SMALL_PURCHASE = 500


# ------------------------------------------------------------------ parsing

# "2 lakh" reaches the agents as "2 100000" and "60 thousand" as "60 1000" (the speech cleaner converts the scale word alone)
_AMOUNT = re.compile(
    r"(?:(?:rs\.?|inr|₹)\s*)?(\d[\d,]*(?:\.\d+)?)(?:\s+(100000|1000)\b)?\s*(k\b|thousand\b|lakhs?\b)?\s*(?:(?:rs|rupees?|inr|bucks)\b)?", re.I
)
_NOT_AMOUNT_AFTER = re.compile(
    r"\s*(?:hours?|hrs?|minutes?|mins?|days?|weeks?|months?|years?|am\b|pm\b|a\.m|p\.m|%|percent|st\b|nd\b|rd\b|th\b|people|persons|"
    r"members|kids|times|km|kms|kg|litres?|liters?|mg\b|items?|o'?clock|of the family)",
    re.I,
)


def parse_amount(text: str) -> tuple[float, tuple[int, int]] | None:
    """First money amount in the text: '450', '1,200', '1.2k', 'rs 300', '60 thousand', '2 lakh'. Skips times, dates, counts."""
    for m in _AMOUNT.finditer(text):
        before = text[m.start() - 1] if m.start() else ""
        after_char = text[m.end(1)] if m.end(1) < len(text) else ""
        if before == ":" or after_char == ":" or _NOT_AMOUNT_AFTER.match(text, m.end()):
            continue
        value = float(m.group(1).replace(",", "")) * (int(m.group(2)) if m.group(2) else 1)
        scale = (m.group(3) or "").lower()
        if scale in ("k", "thousand"):
            value *= 1000
        elif scale.startswith("lakh"):
            value *= 100000
        if value <= 0:
            continue
        return (int(value) if value == int(value) else round(value, 2)), m.span()
    return None


def normalize_category(text: str, after: int = 0) -> str | None:
    """Canonical category named in the text. Prefers a match after `after` (the amount), else the earliest."""
    low = text.lower()
    for c in CATEGORIES:  # an exact canonical name always wins ("eating out", "groceries")
        if re.search(r"\b" + re.escape(c) + r"\b", low):
            return c
    best: tuple[int, int, str] | None = None
    for c, rx in _SYN_RE.items():
        m = rx.search(low, after) or rx.search(low)
        if m:
            key = (0 if m.start() >= after else 1, m.start(), c)
            if best is None or key < best:
                best = key
    return best[2] if best else None


_SPEND_WORDS = re.compile(r"\b(spent|spend|spending|paid|pay|bought|expense|expenses|expenditure|cost me|cost us|costs me|costs us)\b")
_LOG_VERB = re.compile(r"\b(spent|paid|bought|cost me|cost us|costs me|costs us)\b|\b(?:add|log|record|enter|note|put|track|save)\b.*\b(?:expense|spend|spending|payment|purchase)\b|\bexpense of\b")
_QUESTION = re.compile(r"\bhow much\b|\bhow many\b|^\W*(?:what|which|where|who|show|list|tell|give)\b|\?|\b(?:did|do|have|has|am|are|is|was)\b.*\b(?:spend|spent|spending)\b")
_LOG_WEAK_VERB = re.compile(r"\b(?:add|log|record|enter|note|track|put)\b")
_DELETE = re.compile(r"\b(?:delete|remove|undo|scrap|cancel)\b.*\b(?:expense|expenses|entry|transaction|payment|spend|one)\b|\b(?:delete|remove|undo)\b\s+(?:the\s+)?(?:last|previous|latest)")
_BUDGET_WORD = re.compile(r"\bbudgets?\b")
_BUDGET_SET = re.compile(
    r"\b(?:set|make|change|update|put|raise|lower|increase|decrease|reduce|keep|fix|create|add)\b.*\bbudget\b|"
    r"\bbudget\b\s+(?:of|to|at|as|is)\b|\b(?:monthly|total|weekly)\s+budget\b.*\d"
)
_BUDGET_STATUS = re.compile(
    r"\b(?:over|under|within|exceed\w*|crossed|beyond|on track|left|remaining|status|limit|stay(?:ing)? in)\b|\bhow\b|\bam i\b|\bare we\b|\bis (?:our|my|the)\b"
)
_SAVINGS = re.compile(
    r"\bsav(?:e|ing|ings)\b.*\b(?:money|more|cost|costs|spend|spending|expenses?|budget|bills|rupees|tips?|ideas?|advice|where|how|ways?)\b|"
    r"\b(?:how|where|ways?|tips?|ideas?|advice)\b.*\bsav(?:e|ing|ings)\b|\bsavings\b|\bsave (?:some |more |up )?money\b|"
    r"\bcut (?:down|back|costs?|expenses|spending)\b|\breduce (?:our |my |the )?(?:spending|expenses|costs?)\b|\bspend less\b|"
    r"\beconomi[sz]e\b|\bcost[- ]cutting\b|\bwhere can (?:we|i) (?:save|cut)\b|\boverspend\w*\b|\bwasting money\b|\bwasteful\b"
)
_BIGGEST = re.compile(r"\b(?:biggest|largest|top|highest|most|main|major)\b.*\b(?:expense|expenses|spend|spending|category|categories|cost|costs)\b|\bwhere (?:did|does|is) (?:the|our|my) money (?:go|going|went)\b|\bwhat (?:do|did) (?:we|i) spend (?:the )?most\b")
_LIST = re.compile(r"\b(?:show|list|read|tell)\b.*\b(?:expenses|transactions|purchases|spending)\b|\b(?:recent|latest|last few)\b.*\b(?:expenses|transactions|purchases)\b|\bwhat did (?:we|i|\w+) (?:spend|pay)\b")
_SUMMARY = re.compile(
    r"\bhow much\b.*\b(?:spend|spent|spending|expenses?|paid|pay)\b|\b(?:total|overall)\s+(?:spend|spending|expenses?)\b|"
    r"\b(?:spending|expenses?)\b.*\b(?:this|last|today|yesterday|so far|week|month|total|breakdown|summary|report)\b|"
    r"\b(?:spending|expense|expenses)\s+(?:summary|report|breakdown|review)\b|\bam i spending too much\b|\bare we spending too much\b|"
    r"\bhow (?:much )?(?:are|am|have|did|do) (?:we|i|\w+) (?:spending|spent|spend)\b"
)
_FAMILY_WORDS = re.compile(r"\b(?:we|our|us|ours|family|everyone|everybody|household|all of us|together|total)\b")
_SELF_WORDS = re.compile(r"\b(?:i|my|me|mine|myself)\b")
_CANCEL = re.compile(r"\b(?:cancel|never ?mind|forget it|skip|stop|no thanks|nope|no)\b")


def classify(text: str) -> str | None:
    """What a message is about for the Money agent (pure text, no state): log | delete | budget_set | budget_status |
    savings | biggest | list | summary, or None when it is not a money request."""
    low = text.lower().strip()
    if not low:
        return None
    amount = parse_amount(low)
    question = bool(_QUESTION.search(low))
    if _DELETE.search(low) and re.search(r"\b(?:expense|expenses|entry|transaction|payment|spend|last|previous|latest)\b", low):
        return "delete"
    if _BUDGET_WORD.search(low):
        booking = re.search(r"\b(?:book|find|search|recommend|suggest|restaurant|restaurants|table|hotel|flight|flights|cab|cheap|cheaper|friendly|place|trip)\b", low)
        if booking:
            return None
        if amount and _BUDGET_SET.search(low) and not re.search(r"\b(?:am i|are we|how much|is it)\b", low):
            return "budget_set"
        if re.search(r"\b(?:am i|are we|is our|is my|is the|how (?:is|are|much)|what(?:'s| is)|status|left|remaining|exceeded|crossed|overshot|used up)\b", low):
            return "budget_status"
        return None
    if _SAVINGS.search(low) and not re.search(r"\b(?:save|saved)\b\s+(?:the\s+)?(?:date|this|that|it|me a seat|a seat|the file)\b", low):
        return "savings"
    if _BIGGEST.search(low) and not re.search(r"\b(?:flight|cab|table|restaurant|appointment)\b.*\b(?:book|find)\b", low):
        return "biggest"
    if _LIST.search(low) and not re.search(r"\b(?:medicines?|appointments?|events?|homework|flights?|restaurants?)\b.*\b(?:list|show)\b", low):
        return "list"
    if _SUMMARY.search(low):
        return "summary"
    if amount and not question:
        if _LOG_VERB.search(low) or (_LOG_WEAK_VERB.search(low) and _money_cue(low, amount)):
            return "log"
    if amount is None and _LOG_VERB.search(low) and re.search(r"\b(?:add|log|record)\b.*\bexpense\b", low) and not question:
        return "log_missing_amount"
    return None


def _money_cue(low: str, amount: tuple[float, tuple[int, int]]) -> bool:
    """'add/log 600 for vegetables' only counts as an expense with a money cue, so 'add a dentist visit at 5' never does."""
    value, span = amount
    return bool(
        re.search(r"\b(?:rs|rupees?|inr|expense|expenses|spending|payment|purchase)\b|₹", low)
        or re.search(r"(?:k|thousand|lakhs?)\b", low[span[0]:span[1]])
        or (value >= 100 and normalize_category(low, span[1]))
    )


def is_money(text: str) -> bool:
    """True when the Money agent owns this message; other agents use it to stand down on spending phrases."""
    return classify(text) is not None


# ------------------------------------------------------------------ ledger helpers

def _money(state) -> dict:
    d = state.domains["money"]
    d.setdefault("expenses", [])
    d.setdefault("budgets", {})
    d.setdefault("currency", "INR")
    return d


def _today(state) -> _date:
    return _date.fromisoformat(state.now["date"])


def _rs(n: float) -> str:
    return f"Rs {int(round(n)):,}"


def _label(cat: str) -> str:
    return LABEL.get(cat, cat)


def _month_start(d: _date) -> _date:
    return d.replace(day=1)


def _prev_month(d: _date) -> tuple[_date, _date]:
    end = _month_start(d) - timedelta(days=1)
    return _month_start(end), end


def period_range(state, period: str) -> tuple[_date, _date, _date | None, _date | None, str]:
    """(start, end, previous_start, previous_end, label) for a named period; end is inclusive."""
    today = _today(state)
    monday = today - timedelta(days=today.weekday())
    if period == "today":
        return today, today, today - timedelta(days=1), today - timedelta(days=1), "today"
    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, y, y - timedelta(days=1), y - timedelta(days=1), "yesterday"
    if period == "week":
        return monday, today, monday - timedelta(days=7), monday - timedelta(days=1), "this week"
    if period == "last_week":
        start = monday - timedelta(days=7)
        return start, monday - timedelta(days=1), start - timedelta(days=7), start - timedelta(days=1), "last week"
    if period == "last_month":
        start, end = _prev_month(today)
        ps, pe = _prev_month(start)
        return start, end, ps, pe, "last month"
    if period == "all":
        first = min((_date.fromisoformat(e["date"]) for e in _money(state)["expenses"]), default=today)
        return first, today, None, None, "so far"
    start = _month_start(today)
    ps, pe = _prev_month(today)
    return start, today, ps, pe, "this month"


def _in_range(e: dict, start: _date, end: _date) -> bool:
    return start <= _date.fromisoformat(e["date"]) <= end


def _select(state, start: _date, end: _date, category: str | None = None, member_ids: list[str] | None = None) -> list[dict]:
    return [
        e for e in _money(state)["expenses"]
        if _in_range(e, start, end) and (category is None or e["category"] == category) and (not member_ids or e["member_id"] in member_ids)
    ]


def _total(rows: list[dict]) -> float:
    return sum(e["amount"] for e in rows)


def _by_category(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for e in rows:
        out[e["category"]] += e["amount"]
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _ledger_start(state) -> _date | None:
    dates = [_date.fromisoformat(e["date"]) for e in _money(state)["expenses"]]
    return min(dates) if dates else None


def _reliable(state, prev_start: _date | None) -> bool:
    """A comparison is only fair when the ledger reaches back to the start of the previous period."""
    first = _ledger_start(state)
    return bool(prev_start and first and first <= prev_start)


def _next_id(state) -> str:
    nums = [int(m.group(1)) for e in _money(state)["expenses"] if (m := re.fullmatch(r"exp-(\d+)", e["id"]))]
    return f"exp-{max(nums, default=0) + 1}"


def _name(state, member_id: str) -> str:
    return state.member(member_id)["name"]


def _budget_for(state, category: str) -> float | None:
    b = _money(state)["budgets"].get(category)
    return b if b else None


# ------------------------------------------------------------------ savings engine

def savings_ideas(state) -> list[dict]:
    """Concrete, ledger-grounded saving ideas for the current month, biggest first."""
    today = _today(state)
    start, end, ps, pe, _ = period_range(state, "month")
    rows = _select(state, start, end)
    total = _total(rows)
    if not rows:
        return []
    cats = _by_category(rows)
    prev_rows = _select(state, ps, pe) if ps else []
    prev_cats = _by_category(prev_rows)
    reliable = _reliable(state, ps)
    ideas: list[dict] = []
    for cat, spent in cats.items():
        label = _label(cat)
        share = spent / total * 100 if total else 0
        budget = _budget_for(state, cat)
        candidates: list[tuple[float, str]] = []
        text, saving = None, 0.0
        if budget and spent > budget:
            over = spent - budget
            pct = round(over / budget * 100)
            lead = f"{label.capitalize()} is {_rs(spent)} this month, {pct}% above the {_rs(budget)} budget."
            tip = {
                "eating out": " Getting back to budget would save about " + _rs(over) + ", for example by cooking at home two more dinners a week.",
                "groceries": " Planning one weekly shop and skipping top-up orders would save about " + _rs(over) + ".",
                "shopping": " Pausing non-essential buying until next month would save about " + _rs(over) + ".",
                "entertainment": " Trimming one subscription or outing would save about " + _rs(over) + ".",
                "transport": " Combining trips and sharing rides would save about " + _rs(over) + ".",
            }.get(cat, " Getting back to budget would save about " + _rs(over) + ".")
            candidates.append((over, lead + tip))
        elif not budget and share >= 30:
            trim = spent * 0.15
            candidates.append((trim, f"{label.capitalize()} is {round(share)}% of this month's spending at {_rs(spent)}. Trimming it by 15% would save about {_rs(trim)}."))
        if reliable and cat in prev_cats and prev_cats[cat] > 0:
            prev = prev_cats[cat]
            rise = spent - prev
            if rise / prev >= 0.3 and rise >= 500 and not (budget and spent > budget):
                candidates.append((rise, f"{label.capitalize()} is up {round(rise / prev * 100)}% on last month, from {_rs(prev)} to {_rs(spent)}. Bringing it back would save about {_rs(rise)}."))
        small = [e for e in rows if e["category"] == cat and e["amount"] < SMALL_PURCHASE]
        if len(small) >= 4 and _total(small) >= 1000:
            bundle = _total(small) * 0.2
            candidates.append((bundle, f"There are {len(small)} small {label} purchases adding up to {_rs(_total(small))}. Bundling them could save about {_rs(bundle)}."))
        if candidates:
            saving, text = max(candidates, key=lambda c: c[0])
            ideas.append({"category": cat, "saving": int(round(saving)), "text": text})
    ideas.sort(key=lambda i: -i["saving"])
    return ideas[:4]


def overview(state) -> dict:
    """Month-to-date numbers for the Home screen and the impact endpoint; safe on an empty ledger."""
    start, end, ps, pe, _ = period_range(state, "month")
    rows = _select(state, start, end)
    month_total = _total(rows)
    last_total = _total(_select(state, ps, pe)) if ps else 0
    budgets = _money(state)["budgets"]
    budget_total = budgets.get("total") or None
    ideas = savings_ideas(state)
    return {
        "currency": _money(state).get("currency", "INR"),
        "month_total": int(round(month_total)),
        "last_month_total": int(round(last_total)),
        "last_month_partial": not _reliable(state, ps),
        "by_category": {c: int(round(v)) for c, v in _by_category(rows).items()},
        "budget_total": budget_total,
        "budget_left": int(round(budget_total - month_total)) if budget_total else None,
        "potential_savings": sum(i["saving"] for i in ideas),
        "top_tip": ideas[0]["text"] if ideas else None,
    }


# ------------------------------------------------------------------ tools

def log_expense(state, member_id: str, amount: float, category: str, note: str = "", date: str | None = None) -> dict:
    member = state.member(member_id)
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ToolError("amount must be greater than zero")
    cat = normalize_category(category) or ("other" if category.strip().lower() in ("misc", "other") else None)
    if cat is None:
        raise ToolError(f"unknown category {category!r}; use one of {', '.join(CATEGORIES)}")
    date = date or state.now["date"]
    try:
        when = _date.fromisoformat(date)
    except ValueError as exc:
        raise ToolError(f"bad date {date!r}, expected YYYY-MM-DD") from exc
    if when > _today(state):
        raise ToolError("that date is in the future")
    amount = int(amount) if float(amount) == int(amount) else round(float(amount), 2)
    expense = {"id": _next_id(state), "member_id": member_id, "amount": amount, "category": cat, "note": (note or "").strip(),
               "date": date, "source": "voice"}
    _money(state)["expenses"].append(expense)
    start, end, *_ = period_range(state, "month")
    month_rows = _select(state, start, end)
    cat_total = _total([e for e in month_rows if e["category"] == cat])
    budget = _budget_for(state, cat)
    notified = False
    if member["kind"] == "child" and amount >= LARGE_CHILD_SPEND:
        state.notify(state.parents(), f"{member['name']} logged {_rs(amount)} on {_label(cat)}.", "money", "money")
        notified = True
    return {
        "expense": expense, "month_category_total": cat_total, "category_budget": budget,
        "over_budget": bool(budget and cat_total > budget), "month_total": _total(month_rows), "parents_notified": notified,
    }


def delete_expense(state, expense_id: str) -> dict:
    rows = _money(state)["expenses"]
    if expense_id in ("last", "latest", "previous") and rows:
        target = max(rows, key=lambda e: int(e["id"].split("-")[1]) if re.fullmatch(r"exp-\d+", e["id"]) else 0)
    else:
        target = next((e for e in rows if e["id"] == expense_id), None)
    if target is None:
        raise ToolError("there is no such expense to delete" if rows else "there are no expenses to delete")
    rows.remove(target)
    return {"deleted": target}


def list_expenses(state, limit: int = 10, category: str | None = None, member_id: str | None = None, period: str = "all") -> dict:
    start, end, *_ = period_range(state, period)
    cat = normalize_category(category) if category else None
    rows = _select(state, start, end, cat, [member_id] if member_id else None)
    rows = sorted(rows, key=lambda e: (e["date"], int(e["id"].split("-")[1]) if re.fullmatch(r"exp-\d+", e["id"]) else 0), reverse=True)
    return {"expenses": rows[: max(1, int(limit))], "count": len(rows), "total": _total(rows)}


def get_spending_summary(state, period: str = "month", category: str | None = None, member_id: str | None = None) -> dict:
    if period not in ("today", "yesterday", "week", "last_week", "month", "last_month", "all"):
        raise ToolError("period must be today, yesterday, week, last_week, month, last_month or all")
    cat = normalize_category(category) if category else None
    if category and cat is None:
        raise ToolError(f"unknown category {category!r}")
    start, end, ps, pe, label = period_range(state, period)
    rows = _select(state, start, end, cat, [member_id] if member_id else None)
    total = _total(rows)
    cats = _by_category(rows)
    members = defaultdict(float)
    for e in rows:
        members[e["member_id"]] += e["amount"]
    prev_total, change = None, None
    if ps and pe:
        prev_total = _total(_select(state, ps, pe, cat, [member_id] if member_id else None))
        if _reliable(state, ps) and prev_total > 0:
            change = round((total - prev_total) / prev_total * 100)
    budget = _budget_for(state, cat) if cat else (_money(state)["budgets"].get("total") or None)
    return {
        "period": period, "label": label, "start": start.isoformat(), "end": end.isoformat(), "total": total, "count": len(rows),
        "by_category": [{"category": c, "amount": a, "share_pct": round(a / total * 100) if total else 0} for c, a in cats.items()],
        "by_member": [{"member_id": m, "name": _name(state, m), "amount": a} for m, a in sorted(members.items(), key=lambda kv: -kv[1])],
        "biggest_category": next(iter(cats), None), "previous_total": prev_total, "change_pct": change,
        "comparison_reliable": _reliable(state, ps) if ps else False, "budget": budget,
        "scope": {"category": cat, "member_id": member_id}, "currency": _money(state).get("currency", "INR"),
    }


def set_budget(state, category: str, amount: float) -> dict:
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ToolError("a budget must be greater than zero")
    key = "total" if category.strip().lower() in ("total", "monthly", "overall", "all", "month") else normalize_category(category)
    if key is None:
        raise ToolError(f"unknown category {category!r}")
    budgets = _money(state)["budgets"]
    previous = budgets.get(key)
    budgets[key] = int(amount) if float(amount) == int(amount) else round(float(amount), 2)
    return {"category": key, "amount": budgets[key], "previous": previous}


def get_budget_status(state) -> dict:
    start, end, *_ = period_range(state, "month")
    rows = _select(state, start, end)
    cats = _by_category(rows)
    budgets = _money(state)["budgets"]
    total_budget = budgets.get("total") or None
    month_total = _total(rows)
    lines = []
    for cat, budget in budgets.items():
        if cat == "total" or not budget:
            continue
        spent = cats.get(cat, 0)
        lines.append({"category": cat, "budget": budget, "spent": spent, "left": budget - spent,
                      "over_pct": round((spent - budget) / budget * 100) if spent > budget else 0})
    over = [l["category"] for l in lines if l["spent"] > l["budget"]]
    status = "none" if not total_budget and not lines else "over" if (over or (total_budget and month_total > total_budget)) else "ok"
    return {"month_total": month_total, "total_budget": total_budget, "total_left": (total_budget - month_total) if total_budget else None,
            "status": status, "categories": lines, "over": over}


def suggest_savings(state) -> dict:
    start, end, *_ = period_range(state, "month")
    rows = _select(state, start, end)
    ideas = savings_ideas(state)
    return {
        "enough_data": len(rows) >= 3, "ideas": ideas, "potential_savings": sum(i["saving"] for i in ideas),
        "top_tip": ideas[0]["text"] if ideas else None, "month_total": _total(rows),
    }


_MEMBER = {"type": "string", "description": "Family member id, e.g. priya"}
_PERIOD = {"type": "string", "enum": ["today", "yesterday", "week", "last_week", "month", "last_month", "all"]}
_CATEGORY = {"type": "string", "description": "One of: " + ", ".join(CATEGORIES) + " (natural words like 'petrol' or 'electricity' are mapped)"}

TOOLS = [
    Tool(
        "log_expense",
        "Record something a family member spent. Amount is in rupees; category is mapped from natural words. A large spend by a child notifies the parents.",
        {"type": "object", "properties": {"member_id": _MEMBER, "amount": {"type": "number", "description": "Rupees, greater than zero"},
                                          "category": _CATEGORY, "note": {"type": "string", "description": "What it was for, e.g. electricity bill"},
                                          "date": {"type": "string", "description": "YYYY-MM-DD, defaults to today; never in the future"}},
         "required": ["member_id", "amount", "category"]},
        log_expense,
    ),
    Tool(
        "delete_expense",
        "Delete one expense by id, or pass 'last' to delete the most recently logged one.",
        {"type": "object", "properties": {"expense_id": {"type": "string", "description": "e.g. exp-12, or 'last'"}}, "required": ["expense_id"]},
        delete_expense,
    ),
    Tool(
        "list_expenses",
        "List recent expenses, newest first, optionally filtered by category, member and period.",
        {"type": "object", "properties": {"limit": {"type": "integer"}, "category": _CATEGORY, "member_id": _MEMBER, "period": _PERIOD}},
        list_expenses,
    ),
    Tool(
        "get_spending_summary",
        "Totals for a period: per category with share, per member, and the change versus the previous period (only when the ledger covers it).",
        {"type": "object", "properties": {"period": _PERIOD, "category": _CATEGORY, "member_id": _MEMBER}},
        get_spending_summary,
    ),
    Tool(
        "set_budget",
        "Set a monthly budget for one category, or pass category 'total' for the overall monthly budget.",
        {"type": "object", "properties": {"category": {"type": "string", "description": "'total' or a category"}, "amount": {"type": "number"}},
         "required": ["category", "amount"]},
        set_budget,
    ),
    Tool(
        "get_budget_status",
        "This month's spending against the total budget and each category budget, and which categories are over.",
        {"type": "object", "properties": {}},
        get_budget_status,
    ),
    Tool(
        "suggest_savings",
        "Specific, ledger-grounded ways to save this month (over-budget categories, big shares, spikes versus last month, many small purchases) with estimated monthly savings.",
        {"type": "object", "properties": {}},
        suggest_savings,
    ),
]


# ------------------------------------------------------------------ seed (demo content)

_DEMO = [
    ("2026-10-15", "priya", 3400, "groceries", "weekly shop at the supermarket"),
    ("2026-10-17", "rahul", 2300, "transport", "petrol"),
    ("2026-10-18", "priya", 1650, "eating out", "Sunday lunch"),
    ("2026-10-19", "rahul", 620, "eating out", "Swiggy dinner"),
    ("2026-10-21", "priya", 2750, "bills", "electricity bill"),
    ("2026-10-22", "dadi", 560, "health", "medicines"),
    ("2026-10-24", "priya", 1800, "shopping", "Diwali decorations"),
    ("2026-10-25", "rahul", 2400, "groceries", "monthly grocery run"),
    ("2026-10-26", "priya", 2900, "eating out", "family dinner"),
    ("2026-10-27", "rahul", 850, "entertainment", "movie night"),
    ("2026-10-29", "aarav", 90, "eating out", "ice cream"),
    ("2026-10-30", "priya", 2500, "education", "tuition fees"),
    ("2026-10-30", "priya", 999, "bills", "internet bill"),
    ("2026-10-20", "rahul", 6200, "travel", "train tickets for the Diwali visit"),
    ("2026-10-31", "rahul", 1500, "other", "Diwali gifts"),
    ("2026-11-01", "priya", 2500, "education", "tuition fees"),
    ("2026-11-01", "rahul", 3200, "groceries", "monthly grocery run"),
    ("2026-11-02", "priya", 1450, "eating out", "Sunday lunch at Udupi Garden"),
    ("2026-11-03", "rahul", 2400, "transport", "petrol"),
    ("2026-11-04", "priya", 999, "bills", "internet bill"),
    ("2026-11-05", "priya", 599, "bills", "phone recharge"),
    ("2026-11-05", "rahul", 780, "eating out", "Swiggy dinner"),
    ("2026-11-06", "priya", 2850, "bills", "electricity bill"),
    ("2026-11-07", "dadi", 640, "health", "pharmacy"),
    ("2026-11-08", "priya", 2100, "groceries", "vegetables and fruit"),
    ("2026-11-08", "rahul", 960, "entertainment", "movie tickets"),
    ("2026-11-09", "priya", 2500, "eating out", "family dinner"),
    ("2026-11-10", "rahul", 800, "health", "doctor consultation"),
    ("2026-11-11", "priya", 3200, "shopping", "clothes for the kids"),
    ("2026-11-12", "priya", 640, "eating out", "Zomato lunch"),
    ("2026-11-12", "rahul", 520, "transport", "cab to the office"),
    ("2026-11-13", "aarav", 150, "education", "stationery"),
    ("2026-11-14", "rahul", 2200, "transport", "petrol"),
    ("2026-11-14", "priya", 1850, "groceries", "weekly shop"),
    ("2026-11-15", "priya", 1950, "eating out", "birthday dinner"),
    ("2026-11-15", "priya", 1200, "entertainment", "cricket coaching fee"),
    ("2026-11-16", "rahul", 649, "entertainment", "Netflix and Prime"),
    ("2026-11-17", "rahul", 720, "eating out", "coffee and snacks"),
    ("2026-11-17", "priya", 899, "shopping", "Amazon order"),
    ("2026-11-17", "dadi", 420, "health", "medicines"),
    ("2026-11-18", "rahul", 1400, "shopping", "shoes"),
    ("2026-11-18", "priya", 2600, "groceries", "bulk order"),
    ("2026-11-18", "priya", 300, "transport", "metro card top-up"),
    ("2026-11-19", "rahul", 700, "other", "gift"),
    ("2026-11-19", "aarav", 80, "eating out", "ice cream"),
    ("2026-11-19", "priya", 450, "education", "stationery and books"),
]


# ------------------------------------------------------------------ agent

def _scope(state, member_id: str, text: str) -> tuple[list[str] | None, str, str]:
    """(member ids or None for the whole family, English subject, 'has/have' verb) for a question's wording."""
    low = text.lower()
    named = [m for m in state.mentioned_members(re.sub(r"\b(?:we|our|us|everyone|everybody|all of us|family)\b", " ", low))
             if m["id"] != member_id or re.search(r"\b" + re.escape(m["name"].lower()) + r"\b", low)]
    named = [m for m in named if re.search(r"\b(?:" + "|".join(re.escape(k.lower()) for k in (m["name"], m["relation"], m["id"])) + r")\b", low)]
    if named and not _FAMILY_WORDS.search(low.replace("total", "")):
        ids = [m["id"] for m in named]
        return ids, " and ".join(m["name"] for m in named), "has" if len(ids) == 1 else "have"
    if _SELF_WORDS.search(low) and not _FAMILY_WORDS.search(low):
        return [member_id], "you", "have"
    return None, "the family", "has"


def _period_from(text: str) -> str:
    low = text.lower()
    if re.search(r"\byesterday\b|\blast night\b", low):
        return "yesterday"
    if re.search(r"\btoday\b|\bthis morning\b|\btonight\b", low):
        return "today"
    if re.search(r"\blast week\b|\bprevious week\b", low):
        return "last_week"
    if re.search(r"\bthis week\b|\bthe week\b|\bweekly\b|\bso far this week\b", low):
        return "week"
    if re.search(r"\blast month\b|\bprevious month\b|\bprior month\b", low):
        return "last_month"
    if re.search(r"\ball time\b|\bin total\b|\boverall\b|\bever\b|\bso far\b|\bsince we started\b|\bin all\b", low) and "this month" not in low:
        return "all"
    return "month"


class MoneyAgent(Specialist):
    name = "money"
    title = "Money agent"
    keywords = ("spent", "spend", "spending", "expense", "expenses", "budget", "savings")
    tools = TOOLS
    family_keys = ("expenses", "budgets")

    def __init__(self) -> None:
        self.triggers = [
            Trigger("monthly_review", "Monthly spending review", self._monthly_review),
            Trigger("budget_alert", "Budget alert", self._budget_alert),
        ]

    def seed(self) -> dict:
        return {
            "expenses": [
                {"id": f"exp-{i}", "member_id": m, "amount": a, "category": c, "note": n, "date": d, "source": "seed"}
                for i, (d, m, a, c, n) in enumerate(_DEMO, start=1)
            ],
            "budgets": {"total": 60000, "groceries": 14000, "eating out": 6000, "transport": 6000, "shopping": 6000, "entertainment": 3000},
            "currency": "INR",
        }

    # --- routing

    def _pending(self, state) -> dict | None:
        return state.pending if state.pending and state.pending.get("agent") == self.name else None

    def score(self, state, text: str) -> int:
        if self._pending(state) and (normalize_category(text) or _CANCEL.search(text.lower())):
            return 4
        return 4 if classify(text) else 0

    # --- conversation

    def handle(self, state, member_id: str, text: str) -> str | None:
        pending = self._pending(state)
        if pending:
            return self._continue(state, member_id, text, pending)
        kind = classify(text)
        if kind is None:
            return None
        low = text.lower()
        if kind == "log":
            return self._log(state, member_id, text)
        if kind == "log_missing_amount":
            return self.say(state, member_id, "How much was it, and what was it for?", "Kitna kharch hua, aur kis cheez ke liye?")
        if kind == "delete":
            return self._delete(state, member_id)
        if kind == "budget_set":
            return self._budget_set(state, member_id, low)
        if kind == "budget_status":
            return self._budget_status(state, member_id)
        if kind == "savings":
            return self._savings(state, member_id)
        if kind == "biggest":
            return self._biggest(state, member_id, text)
        if kind == "list":
            return self._list(state, member_id, text)
        return self._summary(state, member_id, text)

    def _continue(self, state, member_id: str, text: str, pending: dict) -> str | None:
        low = text.lower()
        category = normalize_category(text)
        if category:
            state.pending = None
            return self._record(state, pending["payer"], pending["amount"], category, pending.get("note", ""), pending.get("date"), member_id)
        if _CANCEL.search(low):
            state.pending = None
            return self.say(state, member_id, "Okay, I won't record it.", "Theek hai, record nahi karunga.")
        return None  # the user moved on: the orchestrator drops the pending question and routes normally

    def _log(self, state, member_id: str, text: str) -> str:
        low = text.lower()
        parsed = parse_amount(low)
        amount, span = parsed
        category = normalize_category(low, span[1])
        payer = member_id
        for m in state.members:
            if re.search(r"\b" + re.escape(m["name"].lower()) + r"\b(?:'s)?\s+(?:just\s+)?(?:spent|paid|bought)\b", low):
                payer = m["id"]
        date = cal.parse_date(low, state.now["date"]) if re.search(r"\byesterday\b|\bon\s+\d|\b\d{4}-\d{2}-\d{2}\b|\blast week\b|\bon (?:mon|tues|wednes|thurs|fri|satur|sun)day\b", low) else None
        if re.search(r"\blast night\b", low):
            date = (_today(state) - timedelta(days=1)).isoformat()
        note = ""
        m = re.search(r"\b(?:on|for|at|towards)\s+(?:the\s+|a\s+|an\s+|my\s+|our\s+)?([a-z][a-z' -]{2,40}?)(?=\s+(?:yesterday|today|last|this|on|at|for)\b|[.,!?]|$)", low[span[1]:] if span[1] < len(low) else low)
        if m:
            note = m.group(1).strip()
        if category is None:
            state.pending = {"agent": self.name, "kind": "category", "amount": amount, "payer": payer, "note": note, "date": date}
            return self.say(
                state, member_id,
                f"Got it, {_rs(amount)}. Which category should that go under? For example groceries, eating out, bills or shopping.",
                f"Samajh gaya, {_rs(amount)}. Kis category mein daalun? Jaise groceries, eating out, bills ya shopping.",
            )
        return self._record(state, payer, amount, category, note, date, member_id)

    def _record(self, state, payer: str, amount: float, category: str, note: str, date: str | None, speaker: str) -> str:
        args = {"member_id": payer, "amount": amount, "category": category, "note": note}
        if date:
            args["date"] = date
        status, res = self.call(state, "log_expense", **args)
        if status != "ok":
            return self.say(state, speaker, f"I couldn't record that: {res['error']}.", f"Record nahi ho paya: {res['error']}.")
        label = _label(category)
        who = "" if payer == speaker else f" for {_name(state, payer)}"
        when = " yesterday" if date and date == (_today(state) - timedelta(days=1)).isoformat() else ""
        en = f"Logged {_rs(amount)} on {label}{who}{when}."
        hi = f"{_rs(amount)} {label} mein likh diya{when and ' kal'}."
        budget = res["category_budget"]
        if budget:
            total = res["month_category_total"]
            if res["over_budget"]:
                en += f" {label.capitalize()} is now {_rs(total)}, over the {_rs(budget)} budget by {_rs(total - budget)}."
                hi += f" {label} ab {_rs(total)} hai, {_rs(budget)} ke budget se {_rs(total - budget)} upar."
            else:
                en += f" That's {_rs(total)} of the {_rs(budget)} {label} budget this month."
                hi += f" Is mahine {_rs(total)}, budget {_rs(budget)} ka."
        if res["parents_notified"]:
            en += " I've told your parents."
            hi += " Maine mummy papa ko bata diya."
        return self.say(state, speaker, en, hi)

    def _delete(self, state, member_id: str) -> str:
        status, res = self.call(state, "delete_expense", expense_id="last")
        if status != "ok":
            return self.say(state, member_id, "There's nothing to delete yet.", "Abhi delete karne ke liye kuch nahi hai.")
        e = res["deleted"]
        return self.say(
            state, member_id,
            f"Deleted the {_rs(e['amount'])} {_label(e['category'])} expense from {_pretty_date(e['date'])}.",
            f"{_pretty_date(e['date'])} ka {_rs(e['amount'])} {_label(e['category'])} ka kharch hata diya.",
        )

    def _budget_set(self, state, member_id: str, low: str) -> str:
        amount, span = parse_amount(low)
        category = normalize_category(low, span[1])
        if re.search(r"\b(?:monthly|total|overall|household|family|whole)\b", low) and not category:
            category = "total"
        category = category or "total"
        status, res = self.call(state, "set_budget", category=category, amount=amount)
        if status != "ok":
            return self.say(state, member_id, f"I couldn't set that budget: {res['error']}.", f"Budget set nahi hua: {res['error']}.")
        what = "monthly budget" if category == "total" else f"{_label(category)} budget"
        start, end, *_ = period_range(state, "month")
        spent = _total(_select(state, start, end, None if category == "total" else category))
        left = amount - spent
        en = f"Done. The {what} is now {_rs(amount)}."
        hi = f"Ho gaya. {what} ab {_rs(amount)} hai."
        if res["previous"]:
            en = en[:-1] + f", up from {_rs(res['previous'])}." if amount > res["previous"] else en[:-1] + f", down from {_rs(res['previous'])}."
        en += f" You've spent {_rs(spent)} so far this month, so {_rs(left)} is left." if left >= 0 else f" You've already spent {_rs(spent)} this month, {_rs(-left)} over it."
        hi += f" Is mahine {_rs(spent)} kharch hua hai."
        return self.say(state, member_id, en, hi)

    def _budget_status(self, state, member_id: str) -> str:
        status, res = self.call(state, "get_budget_status")
        if res["status"] == "none":
            return self.say(
                state, member_id,
                "You haven't set a budget yet. Say something like 'set a monthly budget of sixty thousand' to start.",
                "Abhi koi budget set nahi hai. Bolo, 'monthly budget sixty thousand set karo'.",
            )
        parts_en, parts_hi = [], []
        if res["total_budget"]:
            if res["total_left"] >= 0:
                parts_en.append(f"You've spent {_rs(res['month_total'])} of the {_rs(res['total_budget'])} monthly budget, so {_rs(res['total_left'])} is left.")
                parts_hi.append(f"{_rs(res['total_budget'])} ke budget mein se {_rs(res['month_total'])} kharch hua, {_rs(res['total_left'])} bacha hai.")
            else:
                parts_en.append(f"You're over the monthly budget: {_rs(res['month_total'])} spent against {_rs(res['total_budget'])}.")
                parts_hi.append(f"Monthly budget paar ho gaya: {_rs(res['month_total'])} kharch, budget {_rs(res['total_budget'])}.")
        over = [l for l in res["categories"] if l["spent"] > l["budget"]]
        if over:
            worst = ", ".join(f"{_label(l['category'])} by {_rs(l['spent'] - l['budget'])}" for l in over[:3])
            parts_en.append(f"Over budget: {worst}.")
            parts_hi.append(f"Budget se upar: {worst}.")
        elif res["total_budget"]:
            parts_en.append("Every category is within its budget.")
            parts_hi.append("Har category budget ke andar hai.")
        return self.say(state, member_id, " ".join(parts_en), " ".join(parts_hi))

    def _savings(self, state, member_id: str) -> str:
        status, res = self.call(state, "suggest_savings")
        if not res["enough_data"]:
            return self.say(
                state, member_id,
                "I don't have enough spending recorded this month to suggest savings yet. Tell me what you spend, like 'I spent 450 on groceries', and I'll find patterns.",
                "Is mahine ka kharch abhi kam hai. Bolo, 'maine 450 groceries pe kharch kiye', main bachat ke tarike dhoondhunga.",
            )
        if not res["ideas"]:
            return self.say(
                state, member_id,
                "Spending looks balanced this month: nothing is over budget or unusually high. Logging more expenses will sharpen the tips.",
                "Is mahine kharch santulit hai: kuch bhi budget se upar nahi. Aur kharch likhoge to behtar tips milenge.",
            )
        ideas = res["ideas"][:2]
        en = " ".join(i["text"] for i in ideas)
        if len(res["ideas"]) > 1:
            en += f" Together the top ideas could save about {_rs(sum(i['saving'] for i in ideas))} a month."
        hi = f"Sabse badi bachat: {_label(ideas[0]['category'])} mein lagbhag {_rs(ideas[0]['saving'])} mahine ki bachat ho sakti hai."
        return self.say(state, member_id, en, hi)

    def _biggest(self, state, member_id: str, text: str) -> str:
        period = _period_from(text)
        ids, subject, verb = _scope(state, member_id, text)
        status, res = self.call(state, "get_spending_summary", period=period, **({"member_id": ids[0]} if ids and len(ids) == 1 else {}))
        if not res["count"]:
            return self._empty(state, member_id, res["label"])
        top = res["by_category"][0]
        start, end, *_ = period_range(state, period)
        rows = _select(state, start, end, None, ids)
        biggest = max(rows, key=lambda e: e["amount"])
        en = (f"The biggest spending category {res['label']} is {_label(top['category'])} at {_rs(top['amount'])}, {top['share_pct']}% of the total. "
              f"The largest single expense was {_rs(biggest['amount'])} on {_label(biggest['category'])}, {_pretty_date(biggest['date'])}.")
        hi = (f"{res['label']} sabse zyada kharch {_label(top['category'])} mein hua: {_rs(top['amount'])}. "
              f"Sabse bada kharch {_rs(biggest['amount'])} {_label(biggest['category'])} ka tha.")
        return self.say(state, member_id, en, hi)

    def _list(self, state, member_id: str, text: str) -> str:
        ids, subject, verb = _scope(state, member_id, text)
        category = normalize_category(text) if re.search(r"\b(?:on|for)\b", text.lower()) else None
        args: dict = {"limit": 5, "period": _period_from(text) if re.search(r"today|yesterday|week|month", text.lower()) else "all"}
        if ids and len(ids) == 1:
            args["member_id"] = ids[0]
        if category:
            args["category"] = category
        status, res = self.call(state, "list_expenses", **args)
        if not res["count"]:
            return self._empty(state, member_id, "")
        items = "; ".join(f"{_rs(e['amount'])} on {_label(e['category'])}, {_pretty_date(e['date'])}" for e in res["expenses"][:4])
        return self.say(state, member_id, f"Your latest expenses: {items}. {res['count']} in total.", f"Taaza kharch: {items}.")

    def _summary(self, state, member_id: str, text: str) -> str:
        low = text.lower()
        period = _period_from(low)
        ids, subject, verb = _scope(state, member_id, low)
        category = normalize_category(low) if re.search(r"\b(?:on|for|in|towards)\b", low) or normalize_category(low) else None
        args: dict = {"period": period}
        if ids and len(ids) == 1:
            args["member_id"] = ids[0]
        if category:
            args["category"] = category
        status, res = self.call(state, "get_spending_summary", **args)
        if status != "ok":
            return self.say(state, member_id, f"I couldn't work that out: {res['error']}.", f"Hisaab nahi nikla: {res['error']}.")
        if not res["count"]:
            return self._empty(state, member_id, res["label"], category)
        label = res["label"]
        about = f" on {_label(category)}" if category else ""
        en =f"{subject.capitalize() if subject != 'you' else 'You'} {verb} spent {_rs(res['total'])}{about} {label}, across {res['count']} expenses."
        hi = f"{label} {_rs(res['total'])}{about} kharch hua, {res['count']} entries mein."
        if not category and len(res["by_category"]) > 1:
            top = res["by_category"][:3]
            en += " The biggest categories are " + ", then ".join(f"{_label(c['category'])} at {_rs(c['amount'])}" for c in top) + "."
            hi += " Sabse zyada: " + ", ".join(f"{_label(c['category'])} {_rs(c['amount'])}" for c in top) + "."
        if not ids and len(res["by_member"]) > 1 and not category:
            lead = res["by_member"][0]
            en += f" {lead['name']} has logged the most at {_rs(lead['amount'])}."
        budget = res["budget"]
        if budget and period == "month":
            left = budget - res["total"]
            en += f" That's {_rs(res['total'])} of the {_rs(budget)} budget, {_rs(left)} left." if left >= 0 else f" That's {_rs(-left)} over the {_rs(budget)} budget."
        if res["change_pct"] is not None and period in ("week", "month", "last_month", "last_week"):
            direction = "up" if res["change_pct"] > 0 else "down"
            if abs(res["change_pct"]) >= 5:
                en += f" It's {direction} {abs(res['change_pct'])}% on the previous period."
        return self.say(state, member_id, en, hi)

    def _empty(self, state, member_id: str, label: str, category: str | None = None) -> str:
        where = f" on {_label(category)}" if category else ""
        when = f" {label}" if label else ""
        return self.say(
            state, member_id,
            f"I haven't recorded any spending{where}{when} yet. Tell me what you spend, like 'I spent 450 on groceries'.",
            f"Abhi koi kharch{where}{when} nahi likha hai. Bolo, 'maine 450 groceries pe kharch kiye'.",
        )

    # --- triggers

    def _monthly_review(self, state) -> str:
        status, res = self.call(state, "get_spending_summary", period="month")
        ov = overview(state)
        if not res["count"]:
            text = "No spending has been recorded this month yet."
        else:
            top = res["by_category"][0]
            text = (f"This month the family has spent {_rs(res['total'])} so far, mostly on {_label(top['category'])} at {_rs(top['amount'])}.")
            if ov["budget_total"]:
                text += f" That leaves {_rs(ov['budget_left'])} of the {_rs(ov['budget_total'])} budget." if ov["budget_left"] >= 0 else f" That is {_rs(-ov['budget_left'])} over the {_rs(ov['budget_total'])} budget."
            if ov["top_tip"]:
                text += " " + ov["top_tip"]
        state.notify([m["id"] for m in state.members], text, "money", "money")
        return text

    def _budget_alert(self, state) -> str:
        status, res = self.call(state, "get_budget_status")
        over = [l for l in res["categories"] if l["spent"] > l["budget"]]
        total_over = res["total_budget"] and res["month_total"] > res["total_budget"]
        if not over and not total_over:
            return "Everything is within budget this month, so no alert is needed."
        parts = [f"{_label(l['category'])} is {_rs(l['spent'] - l['budget'])} over its {_rs(l['budget'])} budget" for l in over]
        if total_over:
            parts.append(f"the monthly budget is exceeded by {_rs(res['month_total'] - res['total_budget'])}")
        text = "Budget alert: " + "; ".join(parts) + "."
        state.notify(state.parents(), text, "money", "money")
        return text


def _pretty_date(iso: str) -> str:
    d = _date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"
