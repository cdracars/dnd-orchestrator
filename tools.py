"""Tool layer: every capability the orchestrator can call, plus the schemas Claude sees."""
import inspect

import db
import engine

AGENTS = {
    "orchestrator": {"name": "Orchestrator", "icon": "🧠", "desc": "Routes your wishes to the Guild"},
    "dice": {"name": "Dice Goblin", "icon": "🎲", "desc": "Rolls, advantage, fate"},
    "rules": {"name": "Rules Sage", "icon": "📜", "desc": "Rules-legal heroes"},
    "forge": {"name": "Encounter Forge", "icon": "⚔️", "desc": "CR math & monsters"},
    "tavern": {"name": "Tavern Keeper", "icon": "🍺", "desc": "NPCs, secrets, hooks"},
    "hoard": {"name": "Hoard Keeper", "icon": "💰", "desc": "Loot & treasure"},
    "scribe": {"name": "The Scribe", "icon": "🪶", "desc": "Notes & campaign memory"},
    "war": {"name": "War Table", "icon": "🛡️", "desc": "Initiative & combat"},
}


# ------------------------------------------------------------------ tools
def roll_dice(expression="1d20", advantage="none", who="DM", reason=""):
    r = engine.roll(expression, advantage)
    r["who"], r["reason"] = who, reason
    return r


def create_character(name=None, race=None, character_class=None, level=1, background=None, concept="", save=True):
    c = engine.make_character(name, race, character_class, level, background, concept)
    if save:
        c["id"] = db.save_item("character", c["name"], c)
    return c


def generate_encounter(party_level=3, party_size=4, difficulty="medium", theme="any", save=True):
    e = engine.make_encounter(party_level, party_size, difficulty, theme)
    if save:
        e["id"] = db.save_item("encounter", e["title"], e)
    return e


def generate_npc(role=None, race=None, save=True):
    n = engine.make_npc(role, race)
    if save:
        n["id"] = db.save_item("npc", n["name"], n)
    return n


def generate_loot(party_level=3, hoard=False):
    return engine.make_loot(party_level, hoard)


def save_note(title, text):
    n = {"type": "note", "name": title, "text": text}
    n["id"] = db.save_item("note", title, n)
    return n


def campaign_state():
    out = {"type": "state"}
    for kind in ("character", "npc", "encounter", "note"):
        out[kind] = [{"id": i["id"], "name": i["name"],
                      "summary": (f"L{i.get('level')} {i.get('race')} {i.get('class')}" if kind == "character" else
                                  f"{i.get('race')} {i.get('role')}" if kind == "npc" else
                                  f"{i.get('difficulty')} ({sum(m['count'] for m in i.get('monsters', []))} foes)" if kind == "encounter" else
                                  i.get("text", "")[:60])}
                     for i in db.list_items(kind, 30)]
    out["combat_active"] = bool((db.get_state("combat") or {}).get("active"))
    return out


def get_item(id):
    i = db.get_item(id)
    if not i:
        raise ValueError(f"No item with id {id}")
    return i


# ---- combat
def _combat():
    return db.get_state("combat") or {"active": False}


def _add_combatant(lst, name, hp, ac, bonus, side):
    init = engine.roll("1d20")["total"] + int(bonus or 0)
    lst.append({"name": name, "init": init, "bonus": int(bonus or 0), "hp": int(hp), "max_hp": int(hp), "ac": int(ac),
                "side": side, "conditions": []})


def start_combat(encounter_id=None, include_party=True, extra=None):
    cs = []
    if encounter_id:
        enc = db.get_item(encounter_id)
        if not enc or enc.get("type") != "encounter":
            raise ValueError(f"Encounter {encounter_id} not found")
        for m in enc["monsters"]:
            for i in range(m["count"]):
                _add_combatant(cs, f"{m['name']} {i + 1}" if m["count"] > 1 else m["name"], m["hp"], m["ac"], 0, "foe")
    if include_party:
        for c in db.list_items("character"):
            _add_combatant(cs, c["name"], c["hp"], c["ac"], c.get("initiative", 0), "party")
    for e in extra or []:
        _add_combatant(cs, e["name"], e.get("hp", 10), e.get("ac", 10), e.get("init_bonus", 0), e.get("side", "foe"))
    if not cs:
        raise ValueError("Nobody to fight. Create heroes or an encounter first.")
    cs.sort(key=lambda c: (-c["init"], -c["bonus"]))
    state = {"active": True, "round": 1, "turn": 0, "combatants": cs, "event": "Roll for initiative!"}
    db.set_state("combat", state)
    return {"type": "combat", **state}


def next_turn():
    s = _combat()
    if not s.get("active"):
        raise ValueError("No active combat.")
    n = len(s["combatants"])
    for _ in range(n):
        s["turn"] += 1
        if s["turn"] >= n:
            s["turn"], s["round"] = 0, s["round"] + 1
        c = s["combatants"][s["turn"]]
        if not (c["side"] != "party" and c["hp"] <= 0):
            break
    s["event"] = f"{s['combatants'][s['turn']]['name']}'s turn (round {s['round']})"
    db.set_state("combat", s)
    return {"type": "combat", **s}


def _find(s, target):
    t = str(target).lower()
    for c in s["combatants"]:
        if c["name"].lower() == t:
            return c
    for c in s["combatants"]:
        if t in c["name"].lower():
            return c
    raise ValueError(f"No combatant matching '{target}'.")


def combat_hp(target, delta):
    s = _combat()
    if not s.get("active"):
        raise ValueError("No active combat.")
    c = _find(s, target)
    delta = int(delta)
    c["hp"] = max(0, min(c["max_hp"], c["hp"] + delta))
    s["event"] = f"{c['name']} {'takes ' + str(-delta) + ' damage' if delta < 0 else 'heals ' + str(delta)}" + \
                 (" and is DOWN!" if c["hp"] == 0 else f" ({c['hp']}/{c['max_hp']})")
    db.set_state("combat", s)
    return {"type": "combat", **s}


def combat_condition(target, condition, active=True):
    s = _combat()
    if not s.get("active"):
        raise ValueError("No active combat.")
    c = _find(s, target)
    if active and condition not in c["conditions"]:
        c["conditions"].append(condition)
    if not active and condition in c["conditions"]:
        c["conditions"].remove(condition)
    s["event"] = f"{c['name']} {'is now' if active else 'is no longer'} {condition}"
    db.set_state("combat", s)
    return {"type": "combat", **s}


def end_combat():
    s = _combat()
    s.update({"active": False, "event": "Combat ended."})
    db.set_state("combat", s)
    return {"type": "combat", **s}


TOOLS = {f.__name__: f for f in [
    roll_dice, create_character, generate_encounter, generate_npc, generate_loot, save_note, campaign_state, get_item,
    start_combat, next_turn, combat_hp, combat_condition, end_combat]}

TOOL_AGENT = {
    "roll_dice": "dice", "create_character": "rules", "generate_encounter": "forge", "generate_npc": "tavern",
    "generate_loot": "hoard", "save_note": "scribe", "campaign_state": "scribe", "get_item": "scribe",
    "start_combat": "war", "next_turn": "war", "combat_hp": "war", "combat_condition": "war", "end_combat": "war",
}
COMBAT_TOOLS = {"start_combat", "next_turn", "combat_hp", "combat_condition", "end_combat"}


def _obj(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOL_SCHEMAS = [
    {"name": "roll_dice", "description": "Roll dice. Supports NdM+K and keep-highest like 4d6kh3. Use advantage for a single d20.",
     "input_schema": _obj({"expression": {"type": "string"}, "advantage": {"type": "string", "enum": ["none", "advantage", "disadvantage"]},
                           "reason": {"type": "string"}}, ["expression"])},
    {"name": "create_character", "description": "Build a rules-legal 5e character (SRD-style) and save it to the Archive. Omit fields to randomise.",
     "input_schema": _obj({"name": {"type": "string"}, "race": {"type": "string", "enum": list(engine.RACES)},
                           "character_class": {"type": "string", "enum": list(engine.CLASSES)},
                           "level": {"type": "integer", "minimum": 1, "maximum": 20},
                           "background": {"type": "string", "enum": list(engine.BACKGROUNDS)},
                           "concept": {"type": "string", "description": "One-line character concept for flavour"}})},
    {"name": "generate_encounter", "description": "Build a balanced encounter using DMG XP-budget math and save it.",
     "input_schema": _obj({"party_level": {"type": "integer"}, "party_size": {"type": "integer"},
                           "difficulty": {"type": "string", "enum": engine.DIFFS}, "theme": {"type": "string", "enum": engine.THEMES}},
                          ["party_level", "party_size"])},
    {"name": "generate_npc", "description": "Create an NPC with a secret, a want, a voice and an attitude, and save it.",
     "input_schema": _obj({"role": {"type": "string"}, "race": {"type": "string", "enum": list(engine.RACES)}})},
    {"name": "generate_loot", "description": "Roll treasure for a party level. hoard=true for a big haul.",
     "input_schema": _obj({"party_level": {"type": "integer"}, "hoard": {"type": "boolean"}}, ["party_level"])},
    {"name": "save_note", "description": "Save a campaign note (session recap, plot thread, lore) to the Archive.",
     "input_schema": _obj({"title": {"type": "string"}, "text": {"type": "string"}}, ["title", "text"])},
    {"name": "campaign_state", "description": "List everything in the Archive (heroes, NPCs, encounters, notes) with ids.",
     "input_schema": _obj({})},
    {"name": "get_item", "description": "Fetch the full saved record for an id from the Archive.",
     "input_schema": _obj({"id": {"type": "integer"}}, ["id"])},
    {"name": "start_combat", "description": "Start the initiative tracker from a saved encounter id, optionally adding saved heroes and extra combatants.",
     "input_schema": _obj({"encounter_id": {"type": "integer"}, "include_party": {"type": "boolean"},
                           "extra": {"type": "array", "items": _obj({"name": {"type": "string"}, "hp": {"type": "integer"},
                                                                    "ac": {"type": "integer"}, "init_bonus": {"type": "integer"},
                                                                    "side": {"type": "string", "enum": ["party", "foe"]}}, ["name"])}})},
    {"name": "next_turn", "description": "Advance the initiative tracker to the next combatant.", "input_schema": _obj({})},
    {"name": "combat_hp", "description": "Damage (negative delta) or heal (positive delta) a combatant by name.",
     "input_schema": _obj({"target": {"type": "string"}, "delta": {"type": "integer"}}, ["target", "delta"])},
    {"name": "combat_condition", "description": "Add or remove a condition (e.g. prone, stunned) on a combatant.",
     "input_schema": _obj({"target": {"type": "string"}, "condition": {"type": "string"}, "active": {"type": "boolean"}},
                          ["target", "condition"])},
    {"name": "end_combat", "description": "End the current combat.", "input_schema": _obj({})},
]


def brief(name, r):
    t = r.get("type")
    if t == "roll":
        return f"{r.get('who', '')} rolled {r['expr']} = {r['total']}"
    if t == "character":
        return f"Built {r['name']} (L{r['level']} {r['race']} {r['class']})"
    if t == "encounter":
        return f"{r['title']} ({r['difficulty']})"
    if t == "npc":
        return f"{r['name']}, {r['role']}"
    if t == "loot":
        return f"{r['gp']} gp + {len(r['items'])} items"
    if t == "combat":
        return r.get("event", "combat update")
    if t == "error":
        return r["message"]
    return name


def call_tool(name, args, cid="", who="DM", emit=None):
    agent = TOOL_AGENT.get(name, "scribe")
    if emit:
        emit({"event": "tool_start", "tool": name, "agent": agent, "cid": cid})
    try:
        fn = TOOLS.get(name)
        if not fn:
            raise ValueError(f"Unknown tool '{name}'")
        params = inspect.signature(fn).parameters
        clean = {k: v for k, v in (args or {}).items() if k in params}
        if "who" in params and "who" not in clean:
            clean["who"] = who
        result = fn(**clean)
    except Exception as e:  # noqa: BLE001
        result = {"type": "error", "message": str(e)}
    text = brief(name, result)
    db.log_event(agent, name, text)
    if emit:
        ev = {"event": "tool", "tool": name, "agent": agent, "cid": cid, "who": who, "brief": text,
              "ok": result.get("type") != "error"}
        if result.get("type") == "roll":
            ev["roll"] = result
        emit(ev)
    return result
