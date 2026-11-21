"""Tasks agent: the family's shopping lists and task list, with who is responsible for each, and the day's priorities.

Domain data (state.domains["tasks"]): tasks [...], lists {list_id: {...}}. Extend, don't rename fields.
  task: {id, title, assignee (member id | "family" | None), created_by, created, due (YYYY-MM-DD | None), time, priority
         (high | normal | low), note, done, done_at, done_by, list (id of a shopping list it is the errand for), event_id}
  list: {id, name, assignee, items: [{id, name, qty, added_by, bought, bought_by}]}

Tools: add_task, list_tasks, assign_task, complete_task, remove_task, add_shopping_items, get_shopping_list, mark_bought,
remove_shopping_items, assign_shopping, get_day_plan. Assigning something to another person notifies them.
Trigger (demo): morning_tasks, a task brief for each person who has something to do.
"""

import re
from datetime import date, timedelta

from .. import calendar_core as cc
from ..toolkit import Tool, ToolError
from .base import Specialist, Trigger

PRIORITIES = ("high", "normal", "low")
DEFAULT_LIST = "groceries"
LIST_NAMES = {"groceries": "Groceries", "grocery": "Groceries", "shopping": "Groceries", "pharmacy": "Pharmacy", "medicine": "Pharmacy", "medicines": "Pharmacy"}

# What a remembered preference means for what goes on a list: a pure vegetarian is not shopped for meat, an allergy not for its trigger.
_NON_VEG = {"chicken", "mutton", "fish", "egg", "eggs", "prawn", "prawns", "meat", "beef", "pork", "lamb", "bacon", "ham", "salami", "crab"}
_NUTS = {"peanut", "peanuts", "groundnut", "groundnuts", "peanut butter"}
_GROCERY_WORDS = {
    "milk", "curd", "yogurt", "yoghurt", "paneer", "butter", "ghee", "cheese", "bread", "eggs", "egg", "rice", "atta", "flour", "dal", "daal", "sugar", "salt",
    "oil", "tea", "coffee", "biscuits", "biscuit", "vegetables", "veggies", "tomato", "tomatoes", "onion", "onions", "potato", "potatoes", "fruit", "fruits",
    "banana", "bananas", "apple", "apples", "soap", "shampoo", "detergent", "toothpaste", "chicken", "fish", "masala", "spices", "juice", "water", "noodles",
    "pasta", "cereal", "oats", "honey", "jam", "chips", "snacks", "diapers", "tissues", "coriander", "lemon", "garlic", "ginger",
}


# --------------------------------------------------------------------------- helpers


def _data(state) -> dict:
    d = state.domains.setdefault("tasks", {})
    if not isinstance(d.get("tasks"), list):
        d["tasks"] = []
    if not isinstance(d.get("lists"), dict):
        d["lists"] = {}
    return d


def _names(state) -> dict[str, str]:
    return {m["id"]: m["name"] for m in state.members}


def _who_label(state, who: str | None) -> str:
    if who == "family":
        return "the family"
    return _names(state).get(who or "", who or "nobody")


def _member(state, who) -> str | None:
    """A member id from an id, a name or a relation. None for nobody; 'family' for everyone or anyone."""
    if who is None or not str(who).strip():
        return None
    text = str(who).strip().lower()
    if text in ("family", "everyone", "everybody", "anyone", "anybody", "all", "all of us", "whoever", "sab", "sabhi"):
        return "family"
    for m in state.members:
        if text in (m["id"].lower(), m["name"].lower(), m["relation"].lower()):
            return m["id"]
    for m in state.members:  # "rahul's", "Rahul ji"
        if re.search(rf"\b{re.escape(m['name'].lower())}\b", text):
            return m["id"]
    raise ToolError(f"{who} is not in this family. Members: " + ", ".join(f"{m['name']} ({m['id']})" for m in state.members))


def _speaker(state) -> str | None:
    return state.persona if state.persona in {m["id"] for m in state.members} else None


def _day(state, text) -> str | None:
    """YYYY-MM-DD from a date or a day word ('today', 'friday'), None when nothing is given."""
    if text is None or not str(text).strip():
        return None
    found = cc.parse_date(str(text), state.now["date"])
    if not found:
        raise ToolError(f"I could not read {text!r} as a day. Use a date like 2026-12-26 or a word like tomorrow or friday.")
    return found


def _clock(text) -> str | None:
    if text is None or not str(text).strip():
        return None
    found = cc.parse_time(str(text))
    if not found:
        raise ToolError(f"I could not read {text!r} as a time. Use HH:MM, like 18:30.")
    return found


def _dm(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return d.strftime("%a ") + str(d.day) + d.strftime(" %b")


def _when(state, iso: str | None) -> str:
    """'today', 'tomorrow', 'overdue' or 'Sat 28 Nov'."""
    if not iso:
        return "no date"
    delta = (date.fromisoformat(iso) - date.fromisoformat(state.now["date"])).days
    return "today" if delta == 0 else "tomorrow" if delta == 1 else f"overdue since {_dm(iso)}" if delta < 0 else _dm(iso)


def _task_view(state, t: dict) -> dict:
    overdue = bool(t["due"] and not t["done"] and t["due"] < state.now["date"])
    return {**{k: t[k] for k in ("id", "title", "assignee", "created_by", "due", "time", "priority", "note", "done", "list")},
            "assignee_name": _who_label(state, t["assignee"]) if t["assignee"] else None, "overdue": overdue, "when": _when(state, t["due"])}


def _find_task(state, ref: str) -> dict:
    tasks = _data(state)["tasks"]
    ref = str(ref).strip()
    exact = next((t for t in tasks if t["id"].lower() == ref.lower()), None)
    if exact:
        return exact
    words = [w for w in re.findall(r"[a-z0-9]+", ref.lower()) if w not in {"the", "a", "an", "to", "my", "our", "task", "todo", "that", "it", "of", "for"}]
    if not words:
        raise ToolError("which task? Give its id or a few words from its title.")
    hits = [t for t in tasks if all(w in t["title"].lower() for w in words)]
    if not hits:
        hits = [t for t in tasks if any(w in t["title"].lower() for w in words if len(w) > 3)]
    pool = [t for t in hits if not t["done"]] or hits  # an open task is what people mean; a finished one only when nothing is open
    if len(pool) == 1:
        return pool[0]
    if pool:
        raise ToolError("more than one task fits: " + "; ".join(f"{t['id']} {t['title']}" for t in pool[:5]) + ". Say which one.")
    raise ToolError(f"no task matches {ref!r}. Open tasks: " + ("; ".join(f"{t['id']} {t['title']}" for t in tasks if not t["done"]) or "none"))


_FILLER = {"the", "and", "for", "from", "with", "to", "a", "an", "of", "on", "at", "in", "my", "our", "please", "that", "this"}


def _same_task(a: str, b: str) -> bool:
    """Two titles for one chore: equal, or one holds all the meaningful words of the other ("Collect Dadi's prescription" and
    "Collect Dadi's prescription from the pharmacy"), with at least two words in common."""
    wa, wb = ({w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in _FILLER} for s in (a, b))
    return a.strip().lower() == b.strip().lower() or (len(wa & wb) >= 2 and (wa <= wb or wb <= wa))


def _next_id(prefix: str, items: list[dict]) -> str:
    used = [int(m.group(1)) for i in items if (m := re.fullmatch(prefix + r"(\d+)", i["id"]))]
    return f"{prefix}{max(used, default=0) + 1}"


def _list(state, name: str | None = None, create: bool = True) -> dict:
    key = LIST_NAMES.get((name or DEFAULT_LIST).strip().lower(), re.sub(r"[^a-z0-9]+", "-", (name or DEFAULT_LIST).strip().lower()).strip("-")) or DEFAULT_LIST
    key = key.lower()
    lists = _data(state)["lists"]
    if key not in lists:
        if not create:
            raise ToolError(f"there is no {name} list. Lists: " + (", ".join(l["name"] for l in lists.values()) or "none yet"))
        pretty = LIST_NAMES.get((name or DEFAULT_LIST).strip().lower()) or (name or "Groceries").strip().title()
        lists[key] = {"id": key, "name": pretty, "assignee": None, "items": []}
    return lists[key]


def _open_items(lst: dict) -> list[dict]:
    return [i for i in lst["items"] if not i["bought"]]


def _list_view(state, lst: dict, include_bought: bool = False) -> dict:
    items = lst["items"] if include_bought else _open_items(lst)
    return {"id": lst["id"], "name": lst["name"], "assignee": lst["assignee"], "assignee_name": _who_label(state, lst["assignee"]) if lst["assignee"] else None,
            "open": len(_open_items(lst)), "bought": sum(1 for i in lst["items"] if i["bought"]), "items": items}


def _notify_assignee(state, task: dict, by: str | None, verb: str = "gave you") -> None:
    who = task["assignee"]
    if not who or who == "family" or who == by:
        return
    giver = _who_label(state, by) if by else "Aangan"
    due = f", due {_when(state, task['due'])}" if task["due"] else ""
    state.notify([who], f"{giver} {verb} a task: {task['title']}{due}.", "task", "tasks")


def _diet_warnings(state, names: list[str]) -> list[str]:
    """What the family remembers (a diet, an allergy) set against what is being added to a list."""
    notes = []
    for m in state.members:
        facts = " ".join(f["fact"].lower() for f in state.facts_about(m["id"]))
        for raw in names:
            words = set(re.findall(r"[a-z]+", raw.lower())) | {raw.lower()}
            if ("vegetarian" in facts or "vegan" in facts) and words & _NON_VEG:
                notes.append(f"{m['name']} is vegetarian and does not eat {raw.lower()}.")
            if "peanut" in facts and words & _NUTS:
                notes.append(f"{m['name']} has a peanut allergy: keep {raw.lower()} out of the house.")
    return list(dict.fromkeys(notes))


def _split_items(items) -> list[str]:
    if isinstance(items, str):
        items = re.split(r"\s*(?:,|;|\band\b|\bplus\b|&)\s*", items)
    return [re.sub(r"\s+", " ", str(i)).strip(" .") for i in items or [] if str(i).strip(" .")]


def _qty_name(raw: str) -> tuple[str, str]:
    """'2 kg rice' -> ('Rice', '2 kg'); 'milk' -> ('Milk', '')."""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(kg|g|gm|l|ltr|litre|litres|liter|liters|ml|dozen|packs?|packets?|bottles?|boxes|box|pcs|pieces|x)?\s+(?:of\s+)?(.+)$", raw.strip(), re.I)
    if m:
        qty = f"{m.group(1)} {m.group(2)}".strip() if m.group(2) else m.group(1)
        return m.group(3).strip().capitalize(), qty
    return raw.strip().capitalize(), ""


# --------------------------------------------------------------------------- tools


def add_task(state, title: str, assignee: str | None = None, due: str | None = None, time: str | None = None, priority: str = "normal",
             note: str = "", add_to_calendar: bool = False, created_by: str | None = None) -> dict:
    title = re.sub(r"\s+", " ", (title or "").strip()).strip(" .")
    if not title:
        raise ToolError("a task needs a title")
    if priority not in PRIORITIES:
        raise ToolError("priority must be high, normal or low")
    who, day, at, by = _member(state, assignee), _day(state, due), _clock(time), _member(state, created_by) or _speaker(state)
    data = _data(state)
    same = next((t for t in data["tasks"] if not t["done"] and t["assignee"] == who and _same_task(t["title"], title)), None)
    if same:  # the same chore said again, perhaps in other words: keep one, and take a new day if one was given
        moved = bool(day and day != same["due"])
        if moved:
            same["due"] = day
        return {"task": _task_view(state, same), "already_there": True, "due_updated": moved, "notified": []}
    task = {"id": _next_id("t", data["tasks"]), "title": title, "assignee": who, "created_by": by if by != "family" else None, "created": state.now["date"], "due": day, "time": at,
            "priority": priority, "note": (note or "").strip(), "done": False, "done_at": None, "done_by": None, "list": None, "event_id": None}
    data["tasks"].append(task)
    event = None
    if add_to_calendar:
        if not day:
            raise ToolError("to put a task in the calendar it needs a day")
        if not who or who == "family":
            raise ToolError("to put a task in the calendar it needs one person")
        start = at or "09:00"
        end = cc.to_hhmm(cc.to_min(start) + 30)
        event = cc.add_event(state, [who], title, day, start, end, "", "event", "tasks")
        task["event_id"] = event["id"]
    _notify_assignee(state, task, by)
    notified = [who] if who and who != "family" and who != by else []
    return {"task": _task_view(state, task), "calendar_event": event, "notified": notified}


def list_tasks(state, assignee: str | None = None, status: str = "open", due: str | None = None) -> dict:
    if status not in ("open", "done", "all"):
        raise ToolError("status must be open, done or all")
    who, day = _member(state, assignee), _day(state, due)
    tasks = _data(state)["tasks"]
    if status != "all":
        tasks = [t for t in tasks if t["done"] == (status == "done")]
    if assignee is not None and str(assignee).strip():
        tasks = [t for t in tasks if t["assignee"] == who or (who != "family" and t["assignee"] == "family")]
    if day:
        tasks = [t for t in tasks if t["due"] and t["due"] <= day]
    rank = {"high": 0, "normal": 1, "low": 2}
    tasks = sorted(tasks, key=lambda t: (t["done"], t["due"] or "9999-12-31", rank[t["priority"]], t["id"]))
    views = [_task_view(state, t) for t in tasks]
    per_person: dict[str, int] = {}
    for t in tasks:
        if not t["done"]:
            per_person[_who_label(state, t["assignee"]) if t["assignee"] else "Nobody yet"] = per_person.get(_who_label(state, t["assignee"]) if t["assignee"] else "Nobody yet", 0) + 1
    return {"tasks": views, "count": len(views), "overdue": sum(1 for v in views if v["overdue"]), "unassigned": sum(1 for v in views if not v["assignee"] and not v["done"]), "open_per_person": per_person}


def assign_task(state, task: str, assignee: str, notify: bool = True) -> dict:
    who = _member(state, assignee)
    if not who:
        raise ToolError("who should do it? Give a family member.")
    t = _find_task(state, task)
    if t["done"]:
        raise ToolError(f"{t['title']} is already done")
    before = t["assignee"]
    t["assignee"] = who
    by = _speaker(state)
    if notify and who != before:
        _notify_assignee(state, t, by, "passed you")
    return {"task": _task_view(state, t), "was": _who_label(state, before) if before else None, "notified": [who] if notify and who not in ("family", by) and who != before else []}


def complete_task(state, task: str, done_by: str | None = None) -> dict:
    t = _find_task(state, task)
    if t["done"]:
        return {"task": _task_view(state, t), "already_done": True, "notified": []}
    by = _member(state, done_by) or _speaker(state)
    t["done"], t["done_at"], t["done_by"] = True, state.now["date"], by if by != "family" else None
    asked = t["created_by"]
    notified = []
    if asked and by and asked != by:  # whoever asked for it hears that it is done
        state.notify([asked], f"{_who_label(state, by)} finished: {t['title']}.", "task", "tasks")
        notified = [asked]
    if t["list"]:  # the shopping errand is done: everything on that list counts as bought
        lst = _data(state)["lists"].get(t["list"])
        if lst:
            for item in _open_items(lst):
                item["bought"], item["bought_by"] = True, by
    remaining = sum(1 for x in _data(state)["tasks"] if not x["done"])
    return {"task": _task_view(state, t), "notified": notified, "open_tasks_left": remaining}


def remove_task(state, task: str) -> dict:
    t = _find_task(state, task)
    _data(state)["tasks"].remove(t)
    return {"removed": t["title"], "id": t["id"]}


def add_shopping_items(state, items, list_name: str = DEFAULT_LIST, added_by: str | None = None) -> dict:
    raws = _split_items(items)
    if not raws:
        raise ToolError("what should go on the list?")
    lst = _list(state, list_name)
    by = _member(state, added_by) or _speaker(state)
    added, existing = [], []
    for raw in raws:
        name, qty = _qty_name(raw)
        same = next((i for i in lst["items"] if i["name"].lower() == name.lower()), None)
        if same and not same["bought"]:
            existing.append(same["name"])
            continue
        if same:  # bought before: it is needed again
            same.update(bought=False, bought_by=None, qty=qty or same["qty"], added_by=by if by != "family" else None)
            added.append(same)
            continue
        item = {"id": _next_id("i", [i for l in _data(state)["lists"].values() for i in l["items"]]), "name": name, "qty": qty, "added_by": by if by != "family" else None, "bought": False, "bought_by": None}
        lst["items"].append(item)
        added.append(item)
    return {"list": _list_view(state, lst), "added": [i["name"] + (f" ({i['qty']})" if i["qty"] else "") for i in added], "already_on_the_list": existing,
            "warnings": _diet_warnings(state, [i["name"] for i in added])}


def get_shopping_list(state, list_name: str | None = None, include_bought: bool = False) -> dict:
    lists = _data(state)["lists"]
    if list_name:
        return {"lists": [_list_view(state, _list(state, list_name, create=False), include_bought)]}
    shown = [_list_view(state, l, include_bought) for l in lists.values()]
    return {"lists": shown or [{"id": DEFAULT_LIST, "name": "Groceries", "assignee": None, "assignee_name": None, "open": 0, "bought": 0, "items": []}]}


def _match_items(lst: dict, names: list[str]) -> tuple[list[dict], list[str]]:
    found, missing = [], []
    for raw in names:
        key = _qty_name(raw)[0].lower()
        hit = next((i for i in lst["items"] if i["name"].lower() == key), None) or next((i for i in lst["items"] if key in i["name"].lower() or i["name"].lower() in key), None)
        (found if hit else missing).append(hit or raw)
    return found, missing


def mark_bought(state, items, list_name: str = DEFAULT_LIST, bought_by: str | None = None) -> dict:
    lst = _list(state, list_name, create=False)
    names = _split_items(items)
    if not names:
        raise ToolError("which items were bought?")
    found, missing = _match_items(lst, names)
    by = _member(state, bought_by) or _speaker(state)
    for i in found:
        i["bought"], i["bought_by"] = True, by if by != "family" else None
    done = bool(lst["items"]) and not _open_items(lst)
    if done:  # the whole list is bought: the errand task for it is finished too
        for t in _data(state)["tasks"]:
            if t["list"] == lst["id"] and not t["done"]:
                t["done"], t["done_at"], t["done_by"] = True, state.now["date"], by if by != "family" else None
    return {"bought": [i["name"] for i in found], "not_on_the_list": missing, "left": [i["name"] for i in _open_items(lst)], "list_complete": done}


def remove_shopping_items(state, items, list_name: str = DEFAULT_LIST) -> dict:
    lst = _list(state, list_name, create=False)
    found, missing = _match_items(lst, _split_items(items))
    for i in found:
        lst["items"].remove(i)
    return {"removed": [i["name"] for i in found], "not_on_the_list": missing, "left": [i["name"] for i in _open_items(lst)]}


def assign_shopping(state, assignee: str, list_name: str = DEFAULT_LIST, due: str | None = None, created_by: str | None = None) -> dict:
    who = _member(state, assignee)
    if not who:
        raise ToolError("who should do the shopping? Give a family member.")
    lst = _list(state, list_name)
    if not _open_items(lst):
        raise ToolError(f"the {lst['name']} list is empty: add what is needed first")
    day, by = _day(state, due), _member(state, created_by) or _speaker(state)
    lst["assignee"] = who
    data = _data(state)
    n = len(_open_items(lst))
    title = f"Shop for {lst['name']} ({n} {'item' if n == 1 else 'items'})"
    errand = next((t for t in data["tasks"] if t["list"] == lst["id"] and not t["done"]), None)
    changed = errand is None or errand["assignee"] != who or bool(day and errand["due"] != day)  # tell them only when something is new to them
    if errand:
        errand.update(title=title, assignee=who, due=day or errand["due"])
    else:
        errand = {"id": _next_id("t", data["tasks"]), "title": title, "assignee": who, "created_by": by if by != "family" else None, "created": state.now["date"], "due": day, "time": None,
                  "priority": "normal", "note": "", "done": False, "done_at": None, "done_by": None, "list": lst["id"], "event_id": None}
        data["tasks"].append(errand)
    if changed:
        _notify_assignee(state, errand, by)
    return {"list": _list_view(state, lst), "task": _task_view(state, errand), "notified": [who] if changed and who not in ("family", by) else []}


def get_day_plan(state, member_id: str, date: str | None = None) -> dict:
    """Today at a glance for one person: the schedule, what they owe (overdue first), the shopping they are on, school homework, what the family remembers."""
    who = _member(state, member_id)
    if not who or who == "family":
        raise ToolError("whose day? Give a family member.")
    day = _day(state, date) or state.now["date"]
    events = [{k: e[k] for k in ("id", "title", "start", "end", "location", "kind")} for e in cc.events_for(state, who, day)]
    mine = [t for t in _data(state)["tasks"] if not t["done"] and t["assignee"] in (who, "family")]
    overdue = [t for t in mine if t["due"] and t["due"] < day]
    today = [t for t in mine if t["due"] == day]
    soon = [t for t in mine if t["due"] and t["due"] > day and t["due"] <= (date_from(day) + timedelta(days=2)).isoformat()]
    undated = [t for t in mine if not t["due"]]
    errands = [{"list": l["name"], "open": len(_open_items(l)), "items": [i["name"] for i in _open_items(l)][:8]} for l in _data(state)["lists"].values() if l["assignee"] == who and _open_items(l)]
    homework = []
    kid = state.domains.get("school", {}).get("kids", {}).get(who)
    if kid:
        homework = [{"subject": h["subject"], "task": h["task"], "due": h["due"]} for h in kid.get("homework", []) if not h["done"] and h["due"] <= (date_from(day) + timedelta(days=1)).isoformat()]
    remembered = [f["fact"] for f in state.facts_about(who)][:6] + [f["fact"] for f in state.facts_about("family")][:2]

    priorities = []
    for t in sorted(overdue, key=lambda t: t["due"]):
        priorities.append(f"Overdue: {t['title']} ({_when(state, t['due'])})")
    for t in sorted(today, key=lambda t: (t["priority"] != "high", t["time"] or "99:99")):
        priorities.append(f"Today: {t['title']}" + (f" at {t['time']}" if t["time"] else ""))
    for e in events[:2]:
        priorities.append(f"{e['start']} {e['title']}")
    for er in errands:
        priorities.append(f"Shopping: {er['open']} {'item' if er['open'] == 1 else 'items'} on the {er['list']} list")
    for h in homework[:1]:
        priorities.append(f"Homework: {h['subject']} {h['task']}")
    return {"member_id": who, "name": _who_label(state, who), "date": day, "events": events,
            "tasks": {"overdue": [_task_view(state, t) for t in overdue], "today": [_task_view(state, t) for t in today], "soon": [_task_view(state, t) for t in soon],
                      "anytime": [_task_view(state, t) for t in undated]},
            "shopping": errands, "homework": homework, "remembered": remembered, "priorities": priorities[:6]}


def date_from(iso: str) -> date:
    return date.fromisoformat(iso)


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


_WHO = {"type": "string", "description": "a family member id (as listed in the family), or 'family' for anyone"}
_LIST = {"type": "string", "description": "list name, default groceries (also: pharmacy, or any name)"}

TOOLS = [
    Tool("add_task", "Add a task to the family task list, optionally assigned to a person (they are notified), with a day, a time and a priority. Use it for 'remind Rahul to pay the bill' too.",
         _obj({"title": {"type": "string"}, "assignee": _WHO, "due": {"type": "string", "description": "a day: YYYY-MM-DD or a word like today, tomorrow, friday"},
               "time": {"type": "string", "description": "HH:MM"}, "priority": {"type": "string", "enum": list(PRIORITIES)}, "note": {"type": "string"},
               "add_to_calendar": {"type": "boolean", "description": "also put it in the assignee's calendar (needs a day and one person)"}}, ["title"]),
         add_task),
    Tool("list_tasks", "Pending tasks, optionally for one person or due by a day. Overdue first, then by day and priority.",
         _obj({"assignee": _WHO, "status": {"type": "string", "enum": ["open", "done", "all"]}, "due": {"type": "string", "description": "only tasks due on or before this day"}}),
         list_tasks),
    Tool("assign_task", "Give an existing task to a person (or pass it to someone else); the new person is notified. The task is an id or a few words of its title.",
         _obj({"task": {"type": "string"}, "assignee": _WHO, "notify": {"type": "boolean"}}, ["task", "assignee"]), assign_task),
    Tool("complete_task", "Mark a task DONE, only when the speaker says it has ALREADY been done ('I paid the bill', 'Rahul collected it'). Never for an instruction like 'Rahul should collect X' or 'remind him to': that is add_task or assign_task. Whoever asked for it is told. Finishing a shopping errand marks its list bought.",
         _obj({"task": {"type": "string"}, "done_by": {"type": "string", "description": "who did it; leave out when the speaker did it (the default)"}}, ["task"]), complete_task),
    Tool("remove_task", "Delete a task that is no longer needed.", _obj({"task": {"type": "string"}}, ["task"]), remove_task),
    Tool("add_shopping_items", "Add items to the shared shopping list (groceries by default). Quantities can be part of the text, like '2 kg rice'. Warns when an item clashes with someone's diet or allergy.",
         _obj({"items": {"type": "array", "items": {"type": "string"}}, "list_name": _LIST, "added_by": {"type": "string", "description": "leave out: defaults to the person speaking"}}, ["items"]), add_shopping_items),
    Tool("get_shopping_list", "Read the shopping list(s): what is still needed, who is shopping, what was bought.",
         _obj({"list_name": _LIST, "include_bought": {"type": "boolean"}}), get_shopping_list),
    Tool("mark_bought", "Tick items off the shopping list as bought. When the whole list is bought its errand task is done too.",
         _obj({"items": {"type": "array", "items": {"type": "string"}}, "list_name": _LIST, "bought_by": {"type": "string", "description": "leave out: defaults to the person speaking"}}, ["items"]), mark_bought),
    Tool("remove_shopping_items", "Take items off the shopping list without buying them.",
         _obj({"items": {"type": "array", "items": {"type": "string"}}, "list_name": _LIST}, ["items"]), remove_shopping_items),
    Tool("assign_shopping", "Make one person responsible for the shopping: sets the list's shopper, creates their errand task and tells them.",
         _obj({"assignee": _WHO, "list_name": _LIST, "due": {"type": "string", "description": "a day: YYYY-MM-DD or a word like today, saturday"}}, ["assignee"]), assign_shopping),
    Tool("get_day_plan", "One person's day at a glance: schedule, tasks they owe (overdue first), the shopping they are on, school homework due and what the family remembers about them. Use it for 'plan my day' or 'what are my priorities'.",
         _obj({"member_id": {"type": "string", "description": "a family member id"}, "date": {"type": "string", "description": "default today"}}, ["member_id"]), get_day_plan),
]


# --------------------------------------------------------------------------- conversation (the rule engine)

_LISTWORD = r"(?:shopping|grocery|groceries|kirana|pharmacy|medicine)"
_SHOP_ADD = re.compile(rf"\b(?:add|put|write|note)\s+(?P<items>.+?)\s+(?:to|on|in|into)\s+(?:the\s+|our\s+|my\s+)?(?:{_LISTWORD}\s+)?list\b", re.I)
_SHOP_NEED = re.compile(r"\b(?:we|i)\s+(?:need|are out of|ran out of|are running out of|have run out of|are low on|need to buy|should buy)\s+(?P<items>.+)", re.I)
_SHOP_SHOW = re.compile(rf"\b(?:{_LISTWORD}\s+list|list\s+of\s+{_LISTWORD}|what(?:'s| is)? on the list|what do we need to buy|what(?:'s| is) left to buy)\b", re.I)
_SHOP_BOUGHT = re.compile(r"^\W*(?:i\s+|we\s+)?(?:have\s+|'ve\s+)?(?:just\s+|already\s+)?(?:bought|got|picked up|purchased|ordered)\s+(?P<items>.+)", re.I)
_SHOP_REMOVE = re.compile(rf"\b(?:remove|delete|take off|cross off|cancel)\s+(?P<items>.+?)\s+(?:from|off)\s+(?:the\s+|our\s+)?(?:{_LISTWORD}\s+)?list\b", re.I)
_SHOP_ASSIGN = re.compile(
    rf"\b(?:assign|give|ask|tell|let)\s+\w+\s+(?:to\s+)?(?:do\s+|get\s+|buy\s+|handle\s+|go\s+for\s+)?(?:the\s+)?(?:{_LISTWORD})\b|"
    rf"\b(?:assign|give)\s+(?:the\s+)?(?:{_LISTWORD})(?:\s+(?:list|shopping|run))?\s+to\s+\w+\b|"
    rf"\b\w+\s+(?:will|can|should|is going to|to)\s+(?:do|get|buy|handle|go for)\s+(?:the\s+)?(?:{_LISTWORD})\b", re.I)
_TASK_ADD = re.compile(
    r"\b(?:remind|ask|tell|get|have|make)\s+(?P<who>\w+)\s+to\s+(?P<what>.+)|"
    r"\b(?:add|create|make|new)\s+(?:a\s+|an\s+)?(?:task|to-?do|todo|chore|reminder)(?:\s+for\s+(?P<who2>\w+))?\s*(?:to|:|-)?\s*(?P<what2>.+)?|"
    r"\b(?:assign|give)\s+(?P<what3>.+?)\s+to\s+(?P<who3>\w+)\b", re.I)
_TASK_NEW = re.compile(r"\b(?:add|create|make|new|set up)\s+(?:a\s+|an\s+)?(?:task|to-?do|todo|chore|reminder)\b", re.I)
_TWO_ACTIONS = re.compile(r"\b(?:and|then|also|plus)\s+(?:then\s+)?(?:please\s+)?(?:put|assign|ask|remind|tell|add|give|get|have|make|book|order|buy|call)\b", re.I)
_DAYWORD = r"(?:today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_TASK_LIST = re.compile(
    r"\b(?:(?:my|our|the|everyone's|family)\s+(?:pending\s+|open\s+)?(?:tasks?|to-?do(?:s| list)?|todo(?:s| list)?|chores)|(?:tasks?|chores)\s+(?:for|of)\s+\w+|"
    r"what(?:'s| is| are)?\s+(?:pending|left to do|overdue)|what\s+(?:do|does)\s+(?:i|we|\w+)\s+(?:still\s+)?(?:have|need) to do|who(?:'s| is)? (?:doing|has) what|"
    r"\w+'s\s+(?:tasks?|to-?do(?:s)?|chores)|pending tasks?|open tasks?|overdue tasks?)\b", re.I)
_TASK_DONE = re.compile(r"\b(?:(?:i|we|\w+)\s+)?(?:(?:have\s+|has\s+|'ve\s+)?(?:just\s+|already\s+)?(?:finished|completed|done with|did)|mark(?:ed)?)\s+(?:the\s+|my\s+)?(?P<what>.+?)(?:\s+(?:as\s+)?done)?\W*$|(?P<what2>.+?)\s+(?:is|are)\s+(?:done|finished|complete)\b", re.I)
_DAY_PLAN = re.compile(r"\b(?:plan my day|my priorities|my day look|what(?:'s| is| are) (?:my )?(?:priorities|on my plate)|daily (?:brief|briefing|plan)|brief me|what do i need to do today|what should i do today|prioriti[sz]e)\b", re.I)
_OTHER_OWNER = re.compile(r"\b(?:flight|cab|taxi|restaurant|table|appointment|doctor|medicine|tablet|homework|marks|expense|spent|rupees|rs\.?\s?\d|₹)\b", re.I)


def owns(state, text: str) -> bool:
    """True when the Tasks agent owns this message (a list, a chore, a day plan). Other agents stand down on it."""
    return TasksAgent()._intent(state, text) is not None


def _clean_items(text: str) -> str:
    return re.sub(r"\b(?:please|too|also|as well|for us|today|tomorrow)\b", "", text, flags=re.I).strip(" .,!?")


def _speak_list(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] if words else "nothing"


def _grocery_like(text: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", text.lower())) & _GROCERY_WORDS)


class TasksAgent(Specialist):
    name = "tasks"
    title = "Tasks and shopping agent"
    family_keys = ("tasks", "lists")
    keywords = ("shopping list", "grocery list", "groceries", "task", "tasks", "to-do", "todo", "chore", "chores", "assign", "remind", "pending", "priorities", "shopping")
    tools = TOOLS

    def __init__(self) -> None:
        self.triggers = [Trigger("morning_tasks", "Morning task brief for the family", self._morning)]

    def seed(self) -> dict:
        today = date.fromisoformat("2026-11-20")
        tomorrow, soon = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=3)).isoformat()
        return {
            "tasks": [
                {"id": "t1", "title": "Pay the electricity bill", "assignee": "rahul", "created_by": "priya", "created": "2026-11-18", "due": "2026-11-19", "time": None, "priority": "high",
                 "note": "", "done": False, "done_at": None, "done_by": None, "list": None, "event_id": None},
                {"id": "t2", "title": "Buy chart paper for Aarav's science project", "assignee": "priya", "created_by": "priya", "created": "2026-11-19", "due": tomorrow, "time": None, "priority": "normal",
                 "note": "The water cycle drawing is due tomorrow.", "done": False, "done_at": None, "done_by": None, "list": None, "event_id": None},
                {"id": "t3", "title": "Collect Dadi's prescription from the pharmacy", "assignee": "rahul", "created_by": "priya", "created": "2026-11-19", "due": soon, "time": None, "priority": "normal",
                 "note": "", "done": False, "done_at": None, "done_by": None, "list": None, "event_id": None},
                {"id": "t4", "title": "Call the plumber about the kitchen tap", "assignee": None, "created_by": "rahul", "created": "2026-11-17", "due": None, "time": None, "priority": "low",
                 "note": "", "done": False, "done_at": None, "done_by": None, "list": None, "event_id": None},
            ],
            "lists": {
                DEFAULT_LIST: {"id": DEFAULT_LIST, "name": "Groceries", "assignee": None, "items": [
                    {"id": "i1", "name": "Milk", "qty": "2 L", "added_by": "priya", "bought": False, "bought_by": None},
                    {"id": "i2", "name": "Atta", "qty": "5 kg", "added_by": "priya", "bought": False, "bought_by": None},
                    {"id": "i3", "name": "Paneer", "qty": "", "added_by": "dadi", "bought": False, "bought_by": None},
                    {"id": "i4", "name": "Bananas", "qty": "1 dozen", "added_by": "rahul", "bought": False, "bought_by": None},
                    {"id": "i5", "name": "Tomatoes", "qty": "1 kg", "added_by": "priya", "bought": False, "bought_by": None},
                ]},
            },
        }

    # --- intent detection (shared by score and handle)
    def _intent(self, state, text: str) -> str | None:
        from .money import is_money

        if is_money(text) and not re.search(r"\blist\b", text, re.I):
            return None  # "bought milk for 60 rupees" is a spending entry
        if _SHOP_REMOVE.search(text):
            return "shop_remove"
        if _SHOP_ADD.search(text):  # "add eggs to the shopping list for tomorrow" is an addition, whatever words follow
            return "shop_add"
        if _SHOP_ASSIGN.search(text) and not _SHOP_SHOW.search(text):
            return "shop_assign"
        if _SHOP_SHOW.search(text) and not re.search(r"\b(add|put|remove|delete)\b", text, re.I):
            return "shop_show"
        m = _SHOP_NEED.search(text)
        if m and _grocery_like(m.group("items")) and not _OTHER_OWNER.search(text):
            return "shop_add"
        if _SHOP_BOUGHT.search(text) and self._on_list(state, _SHOP_BOUGHT.search(text).group("items")):
            return "shop_bought"
        if _DAY_PLAN.search(text):
            return "day_plan"
        if _TWO_ACTIONS.search(text) and (_TASK_NEW.search(text) or _TASK_ADD.search(text)):
            return None  # "ask Aarav to tidy up and put Rahul on the shopping" is two requests: the model splits them
        if _TASK_NEW.search(text):  # "add a task for Priya: ..." names the task, it does not ask to see them
            return "task_add"
        if _TASK_DONE.search(text) and self._matching_open_task(state, _TASK_DONE.search(text)):
            return "task_done"
        if _TASK_LIST.search(text):
            return "task_list"
        m = _TASK_ADD.search(text)
        if m and not _OTHER_OWNER.search(text):
            who = m.group("who") or m.group("who2") or m.group("who3")
            if who and not self._is_member(state, who) and who.lower() not in ("me", "us", "everyone", "family"):
                return "task_add" if re.search(r"\b(task|to-?do|todo|chore|reminder)\b", text, re.I) else None
            return "task_add"
        return None

    def score(self, state, text: str) -> int:
        if self._intent(state, text):
            return 4
        # No clear rule applies (a sentence with two requests, say). A weak score still gets these tools offered to the model, and
        # stays under the quick path's bar of 3, so the model does the work instead of the rules guessing.
        from .money import is_money

        return 0 if is_money(text) else min(2, super().score(state, text))  # spending talk ("450 on groceries") is the Money agent's

    @staticmethod
    def _is_member(state, word: str) -> bool:
        w = word.lower()
        return any(w in (m["name"].lower(), m["id"].lower(), m["relation"].lower()) for m in state.members)

    def _on_list(self, state, items_text: str) -> bool:
        lists = _data(state)["lists"].values()
        names = [i["name"].lower() for l in lists for i in _open_items(l)]
        return any(n in items_text.lower() or any(w in n for w in re.findall(r"[a-z]{4,}", items_text.lower())) for n in names)

    def _matching_open_task(self, state, m) -> dict | None:
        what = (m.group("what") or m.group("what2") or "").strip()
        if not what:
            return None
        try:
            t = _find_task(state, what)
        except ToolError:
            return None
        return t if not t["done"] else None

    # --- reply helpers
    def _fail(self, state, member_id, result: dict) -> str:
        err = result.get("error", "unknown error")
        return self.say(state, member_id, f"Sorry, that didn't work: {err}", f"Maaf kijiye, nahi ho paaya: {err}")

    def _who_in(self, state, member_id: str, text: str) -> str | None:
        """Who a message names ('me' is the speaker), else None."""
        if re.search(r"\b(?:me|myself|my|mine|i)\b", text, re.I) and not state.mentioned_members(text):
            return member_id
        named = state.mentioned_members(text)
        if len(named) == len(state.members) and len(named) > 1:
            return "family"
        return named[0]["id"] if named else None

    def handle(self, state, member_id: str, text: str) -> str | None:
        intent = self._intent(state, text)
        if intent is None:
            return None
        return getattr(self, f"_do_{intent}")(state, member_id, text)

    def _do_shop_add(self, state, member_id: str, text: str) -> str:
        m = _SHOP_ADD.search(text) or _SHOP_NEED.search(text)
        items = _clean_items(m.group("items"))
        lname = DEFAULT_LIST
        pm = re.search(r"\bpharmacy|medicine", text, re.I)
        if pm:
            lname = "pharmacy"
        status, out = self.call(state, "add_shopping_items", items=_split_items(items), list_name=lname, added_by=member_id)
        if status != "ok":
            return self._fail(state, member_id, out)
        said = []
        if out["added"]:
            said.append(f"Added {_speak_list([a.lower() for a in out['added']])} to the {out['list']['name'].lower()} list.")
        if out["already_on_the_list"]:
            said.append(f"{_speak_list([a.lower() for a in out['already_on_the_list']]).capitalize()} {'was' if len(out['already_on_the_list']) == 1 else 'were'} already on it.")
        said += out["warnings"]
        said.append(f"{out['list']['open']} {'item' if out['list']['open'] == 1 else 'items'} to buy now.")
        return " ".join(said)

    def _do_shop_show(self, state, member_id: str, text: str) -> str:
        status, out = self.call(state, "get_shopping_list")
        lst = out["lists"][0]
        if not lst["items"]:
            return "The shopping list is empty. Tell me what we need and I will add it."
        names = [(f"{i['qty']} " if i["qty"] else "") + i["name"].lower() for i in lst["items"]]  # "2 L milk", "5 kg atta"
        who = f" {lst['assignee_name']} is doing the shopping." if lst["assignee_name"] else " Nobody is assigned to shop yet."
        return f"{lst['open']} {'item' if lst['open'] == 1 else 'items'} on the {lst['name'].lower()} list: {_speak_list(names)}.{who}"

    def _do_shop_bought(self, state, member_id: str, text: str) -> str:
        items = _clean_items(_SHOP_BOUGHT.search(text).group("items"))
        status, out = self.call(state, "mark_bought", items=_split_items(items), bought_by=member_id)
        if status != "ok":
            return self._fail(state, member_id, out)
        said = [f"Ticked off {_speak_list([b.lower() for b in out['bought']])}."] if out["bought"] else []
        if out["list_complete"]:
            said.append("The whole list is bought.")
        elif out["left"]:
            said.append(f"Still to buy: {_speak_list([x.lower() for x in out['left']])}.")
        if out["not_on_the_list"]:
            said.append(f"{_speak_list(out['not_on_the_list'])} was not on the list.")
        return " ".join(said) or "Nothing on the list matched that."

    def _do_shop_remove(self, state, member_id: str, text: str) -> str:
        items = _clean_items(_SHOP_REMOVE.search(text).group("items"))
        status, out = self.call(state, "remove_shopping_items", items=_split_items(items))
        if status != "ok":
            return self._fail(state, member_id, out)
        if not out["removed"]:
            return f"{_speak_list(out['not_on_the_list'])} is not on the list."
        return f"Took {_speak_list([r.lower() for r in out['removed']])} off the list. {len(out['left'])} left to buy."

    def _do_shop_assign(self, state, member_id: str, text: str) -> str:
        m = _SHOP_ASSIGN.search(text)
        who = self._who_in(state, member_id, text)
        if not who or who == "family":
            return "Who should do the shopping?"
        due = cc.parse_date(text, state.now["date"])
        status, out = self.call(state, "assign_shopping", assignee=who, due=due)
        if status != "ok":
            return self._fail(state, member_id, out)
        n = out["list"]["open"]
        when = f", due {_when(state, out['task']['due'])}" if out["task"]["due"] else ""
        told = " I have let them know." if out["notified"] else ""
        return f"{out['list']['assignee_name']} is doing the shopping: {n} {'item' if n == 1 else 'items'}{when}.{told}"

    def _do_task_add(self, state, member_id: str, text: str) -> str:
        m = _TASK_ADD.search(text)
        what = (m.group("what") or m.group("what2") or m.group("what3") or "").strip()
        who_word = m.group("who") or m.group("who2") or m.group("who3")
        who = None
        if who_word:
            if who_word.lower() in ("me", "myself"):
                who = member_id
            elif who_word.lower() in ("us", "everyone", "family"):
                who = "family"
            elif self._is_member(state, who_word):
                who = next(mm["id"] for mm in state.members if who_word.lower() in (mm["name"].lower(), mm["id"].lower(), mm["relation"].lower()))
        due = cc.parse_date(text, state.now["date"])
        at = cc.parse_time(text)
        title = re.sub(rf"\b(?:by|on|before|due|at|for)?\s*{_DAYWORD}(?:\s+(?:morning|afternoon|evening|night))?\b", "", what, flags=re.I)
        title = re.sub(r"\b(?:by|before|due|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", "", title, flags=re.I)
        title = re.sub(r"\s{2,}", " ", title).strip(" .,!?")
        if not title:
            return "What should the task be?"
        title = title[0].upper() + title[1:]
        priority = "high" if re.search(r"\b(urgent|asap|important|high priority)\b", text, re.I) else "normal"
        status, out = self.call(state, "add_task", title=title, assignee=who, due=due, time=at, priority=priority, created_by=member_id)
        if status != "ok":
            return self._fail(state, member_id, out)
        t = out["task"]
        if out.get("already_there"):
            return f"That task is already on the list: {t['title']}."
        mine = f" for {t['assignee_name']}" if t["assignee_name"] and t["assignee"] != member_id else ""
        when = f", due {t['when']}" if t["due"] else ""
        told = f" {t['assignee_name']} has been notified." if out["notified"] else ""
        return f"Added the task{mine}: {t['title']}{when}.{told}"

    def _do_task_list(self, state, member_id: str, text: str) -> str:
        who = self._who_in(state, member_id, text)
        if who == "family" or (who is None and re.search(r"\b(everyone|everybody|family|who|our|all)\b", text, re.I)):
            who = None  # the whole family's list
        elif who is None:
            who = member_id
        status, out = self.call(state, "list_tasks", assignee=who)
        if status != "ok":
            return self._fail(state, member_id, out)
        tasks = out["tasks"]
        label = "Everyone has" if who is None else "You have" if who == member_id else f"{_who_label(state, who)} has"
        if not tasks:
            return ("Nothing pending for the family." if who is None else "Nothing pending for you." if who == member_id else f"Nothing pending for {_who_label(state, who)}.")
        parts = []
        for t in tasks[:5]:
            owner = "" if who is not None else f" ({t['assignee_name']})" if t["assignee_name"] else " (nobody yet)"
            parts.append(f"{t['title']}{owner}" + (f", {t['when']}" if t["due"] else ""))
        more = f" And {len(tasks) - 5} more." if len(tasks) > 5 else ""
        flag = f" {out['overdue']} {'is' if out['overdue'] == 1 else 'are'} overdue." if out["overdue"] else ""
        return f"{label} {len(tasks)} pending {'task' if len(tasks) == 1 else 'tasks'}: {'; '.join(parts)}.{flag}{more}"

    def _do_task_done(self, state, member_id: str, text: str) -> str:
        m = _TASK_DONE.search(text)
        status, out = self.call(state, "complete_task", task=(m.group("what") or m.group("what2")), done_by=member_id)
        if status != "ok":
            return self._fail(state, member_id, out)
        told = " I have let them know." if out["notified"] else ""
        return f"Done: {out['task']['title']}. {out['open_tasks_left']} {'task' if out['open_tasks_left'] == 1 else 'tasks'} left.{told}"

    def _do_day_plan(self, state, member_id: str, text: str) -> str:
        who = self._who_in(state, member_id, text) or member_id
        who = member_id if who == "family" else who
        status, out = self.call(state, "get_day_plan", member_id=who)
        if status != "ok":
            return self._fail(state, member_id, out)
        name = "You" if who == member_id else out["name"]
        if not out["priorities"]:
            return f"{name} {'have' if who == member_id else 'has'} a clear day: nothing scheduled and nothing pending."
        top = "; ".join(out["priorities"][:4])
        remember = f" Remember: {out['remembered'][0].lower()}." if out["remembered"] and who != member_id else ""
        return f"Today for {out['name']}: {top}.{remember}"

    # --- proactive scenario
    def _morning(self, state) -> str:
        sent = 0
        for m in state.members:
            plan = get_day_plan(state, m["id"])
            if plan["priorities"] and m["kind"] != "child":
                state.notify([m["id"]], f"Good morning {m['name']}. Today: " + "; ".join(plan["priorities"][:3]) + ".", "task", "tasks")
                sent += 1
        state.log("tasks", "morning_brief", {}, "ok", {"people": sent}, 0)
        return f"Sent a morning brief to {sent} {'person' if sent == 1 else 'people'}."
