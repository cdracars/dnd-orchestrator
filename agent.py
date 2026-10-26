"""The Orchestrator brain.

With ANTHROPIC_API_KEY set, Claude plans and chains the Guild's tools.
Without it, a keyword router drives the same tools so the whole table still works offline.
"""
import json
import os
import re
import threading

import db
import engine
import tools

MODEL = os.environ.get("DND_MODEL", "claude-sonnet-5-5")
HISTORY = {}
MAX_TURNS = 12
MAX_CONVERSATIONS = 50
_locks = {}
_locks_guard = threading.Lock()

SYSTEM = """You are the Orchestrator: the Dungeon Master's assistant, living on the DM's home network.
You command a Guild of specialist tools (dice, rules, encounters, NPCs, loot, notes, combat, 3D print queue).

Rules of the table:
- ALWAYS use tools for dice, stat blocks, encounter math and loot. Never invent numbers.
- The UI automatically shows full result cards for every tool call, so do NOT restate stats. Reply with 2-5 punchy sentences
  that add value: tactics, story hooks, how the pieces connect, what to do next.
- Things you create are saved to the Archive by default.
- For big asks ("prep tonight's session") chain several tools: encounter, NPC, loot, a note.
- Use 5e (2014 SRD-style) rules. Warm, playful tabletop energy. Short and vivid.

Current party in the Archive: {party}"""


def _party():
    heroes = db.list_items("character")
    return ", ".join(f"{h['name']} (L{h['level']} {h['race']} {h['class']}, id {h['id']})" for h in heroes) or "none yet"


def _trim(msgs):
    idx = [i for i, m in enumerate(msgs) if m["role"] == "user" and isinstance(m["content"], str)]
    if len(idx) > MAX_TURNS:
        del msgs[: idx[-MAX_TURNS]]


def _client():
    import anthropic

    return anthropic.Anthropic()


def _history(cid):
    """Per-conversation message list. Past MAX_CONVERSATIONS the least-recently-used idle conversation is dropped;
    one whose turn is still running (its lock is held) is never evicted."""
    with _locks_guard:
        msgs = HISTORY.pop(cid, [])
        HISTORY[cid] = msgs
        for old in list(HISTORY):
            if len(HISTORY) <= MAX_CONVERSATIONS:
                break
            lock = _locks.get(old)
            if old != cid and not (lock and lock.locked()):
                HISTORY.pop(old)
                _locks.pop(old, None)
        return msgs


def _tool_payload(out):
    text = json.dumps(out, default=str)
    return text if len(text) <= 7000 else text[:7000] + "...[truncated]"


# Tool schemas are the biggest static part of the prompt; mark them cacheable (the system prompt changes with the party).
_CACHED_TOOLS = [*tools.TOOL_SCHEMAS[:-1], {**tools.TOOL_SCHEMAS[-1], "cache_control": {"type": "ephemeral"}}]


def claude_agent(cid, text, who, emit):
    with _locks_guard:
        lock = _locks.setdefault(cid, threading.Lock())
    with lock:  # two devices sharing a conversation id must not interleave tool_use / tool_result pairs
        client = _client()
        msgs = _history(cid)
        msgs.append({"role": "user", "content": text if who == "DM" else f"[{who}] {text}"})
        _trim(msgs)
        mark = len(msgs) - 1
        cards, reply = [], ""
        try:
            for _ in range(8):
                resp = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM.format(party=_party()),
                                              tools=_CACHED_TOOLS, messages=msgs)
                msgs.append({"role": "assistant", "content": resp.content})
                reply = "".join(b.text for b in resp.content if b.type == "text") or reply
                # Answer every tool_use block, whatever the stop_reason (e.g. max_tokens), or the history becomes
                # invalid and every later request in this conversation fails.
                uses = [b for b in resp.content if b.type == "tool_use"]
                if not uses:
                    break
                results = []
                for b in uses:
                    out = tools.call_tool(b.name, b.input, cid, who, emit)
                    cards.append(out)
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": _tool_payload(out),
                                    "is_error": out.get("type") == "error"})
                msgs.append({"role": "user", "content": results})
        except Exception:
            del msgs[mark:]  # drop this turn entirely so the stored history stays valid
            raise
        return reply.strip(), cards


# -------------------------------------------------------------- offline
HELP = (
    "I'm running in **offline Rules Engine mode** (no API key), so I understand direct commands:\n"
    "- `roll 2d6+3`, `roll d20 with advantage`\n"
    "- `encounter level 5 party of 4 hard undead`\n"
    "- `character level 3 tiefling warlock`\n"
    "- `npc innkeeper`, `loot level 6 hoard`\n"
    "- `start combat`, `next turn`, `end combat`, `note: title - text`, `what do we have`\n"
    "Add an `ANTHROPIC_API_KEY` to unlock full natural-language orchestration."
)
THEME_WORDS = {"undead": "undead", "goblin": "goblinoid", "beast": "beast", "animal": "beast", "giant": "giant", "dragon": "dragon",
               "fiend": "fiend", "demon": "fiend", "devil": "fiend", "aberration": "aberration", "dungeon": "dungeon",
               "forest": "forest", "mountain": "mountain", "swamp": "swamp", "bandit": "bandit", "cult": "cult",
               "humanoid": "humanoid"}


def _num(pattern, t, default):
    m = re.search(pattern, t)
    return int(next(g for g in m.groups() if g)) if m else default


def offline_agent(cid, text, who, emit):
    t = text.lower().strip()
    cards = []

    def call(name, **args):
        out = tools.call_tool(name, args, cid, who, emit)
        cards.append(out)
        return out

    level = _num(r"(?:level|lvl|lv)\s*(\d+)|(\d+)(?:st|nd|rd|th)[- ]level", t, None)
    if t.startswith("note:"):
        title, _, body = text[5:].partition("-")
        call("save_note", title=title.strip() or "Note", text=(body or title).strip())
        return "Inked into the Archive. 🪶", cards
    dice = re.search(r"\b(\d*d\d+(?:k[hl]\d+)?(?:[+-]\d+)*)\b", t)
    if dice and ("roll" in t or re.fullmatch(r"\s*" + re.escape(dice.group(1)) + r"\s*", t)):
        adv = "advantage" if "advantage" in t and "dis" not in t else "disadvantage" if "disadvantage" in t else "none"
        r = call("roll_dice", expression=dice.group(1), advantage=adv)
        return ("🌟 NATURAL 20!" if r.get("crit") else "💀 Natural 1..." if r.get("fumble") else "The dice have spoken."), cards
    if re.search(r"end combat|stop combat", t):
        call("end_combat")
        return "Swords sheathed. For now.", cards
    if re.search(r"next turn|next up|\bnext\b", t) and (db.get_state("combat") or {}).get("active"):
        call("next_turn")
        return "Onward!", cards
    if re.search(r"start combat|roll initiative|begin combat|initiative", t):
        enc = (db.list_items("encounter") or [None])[0]
        call("start_combat", encounter_id=enc["id"] if enc else None, include_party=True)
        return "Initiative rolled. Check the War Table! 🛡️", cards
    if "encounter" in t or "ambush" in t:
        size = _num(r"party of (\d+)|(\d+)\s*(?:players|pcs|heroes|adventurers)", t, 4)
        diff = next((d for d in engine.DIFFS if d in t), "medium")
        theme = next((v for k, v in THEME_WORDS.items() if k in t), "any")
        call("generate_encounter", party_level=level or 3, party_size=size, difficulty=diff, theme=theme)
        return "The Forge glows. Say `start combat` when the party is ready.", cards
    if "loot" in t or "treasure" in t or "hoard" in t:
        call("generate_loot", party_level=level or 3, hoard="hoard" in t)
        return "Shiny things acquired. 💰", cards
    race = next((r for r in engine.RACES if r.lower().replace("-", " ") in t.replace("-", " ")), None)
    cls = next((c for c in engine.CLASSES if c.lower() in t), None)
    if "character" in t or "hero" in t or re.search(r"\bpc\b", t) or "build" in t or (race and cls):
        call("create_character", race=race, character_class=cls, level=level or 1)
        return "A new hero steps into the torchlight. Saved to the Archive. 📜", cards
    if "npc" in t or any(r in t for r in engine.ROLES):
        role = next((r for r in engine.ROLES if r in t), None)
        call("generate_npc", role=role)
        return "Someone new is behind the bar. Handle with secrets. 🍺", cards
    if re.search(r"what do we have|state|archive|campaign", t):
        call("campaign_state")
        return "Here's the whole campaign at a glance.", cards
    return HELP, cards


def handle(cid, text, who, emit):
    emit({"event": "thinking", "on": True, "cid": cid})
    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                reply, cards = claude_agent(cid, text, who, emit)
                return {"reply": reply, "cards": cards, "mode": "claude"}
            except Exception as e:  # noqa: BLE001
                reply, cards = offline_agent(cid, text, who, emit)
                return {"reply": f"⚠️ Claude API hiccup ({type(e).__name__}); the Rules Engine answered instead.\n{reply}",
                        "cards": cards, "mode": "offline"}
        reply, cards = offline_agent(cid, text, who, emit)
        return {"reply": reply, "cards": cards, "mode": "offline"}
    finally:
        emit({"event": "thinking", "on": False, "cid": cid})
