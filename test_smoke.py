"""Smoke test: python test_smoke.py  (uses a throwaway database)"""
import os
import tempfile

os.environ["DND_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import db  # noqa: E402
import engine  # noqa: E402
import server  # noqa: E402

# engine invariants
for cls in engine.CLASSES:
    for lvl in (1, 5, 11, 20):
        c = engine.make_character(character_class=cls, level=lvl)
        assert c["hp"] >= lvl and 1 <= c["ac"] <= 25, (cls, lvl, c["hp"], c["ac"])
        assert all(8 <= a["score"] <= 20 for a in c["abilities"].values())
for lvl in (1, 5, 10, 20):
    for diff in engine.DIFFS:
        for theme in engine.THEMES:
            e = engine.make_encounter(lvl, 4, diff, theme)
            assert e["monsters"] and e["adjusted_xp"] <= e["thresholds"]["deadly"] * 1.6, (lvl, diff, theme, e["adjusted_xp"])
# 2014 PHB details
mk = engine.make_character
assert mk(character_class="Fighter", level=1)["ac"] == 18  # chain mail + shield
cl = mk(character_class="Cleric", level=1)
assert cl["ac"] == 16 + min(cl["abilities"]["dex"]["mod"], 2)  # scale mail + shield
he = mk(race="Half-Elf", character_class="Wizard", level=1)["abilities"]
assert (he["int"]["score"], he["con"]["score"], he["cha"]["score"]) == (16, 15, 12)  # +1/+1 follow the class, +2 Cha
assert sum(sk["prof"] for sk in mk(race="Half-Elf", character_class="Wizard", level=1)["skills"]) == 6  # bg 2 + class 2 + versatility 2
for lvl, n in ((1, 2), (5, 2), (6, 4)):
    rg = mk(character_class="Rogue", level=lvl)
    ex = [sk for sk in rg["skills"] if sk["expertise"]]
    assert len(ex) == n and all(sk["prof"] for sk in ex)
    ab = engine.SKILLS
    assert all(sk["bonus"] == rg["abilities"][ab[sk["name"]]]["mod"] + 2 * rg["proficiency"] for sk in ex)
assert [sum(sk["expertise"] for sk in mk(character_class="Bard", level=l)["skills"]) for l in (1, 3, 10)] == [0, 2, 4]
bd = mk(character_class="Bard", level=2)  # Jack of All Trades
assert all(sk["bonus"] == bd["abilities"][engine.SKILLS[sk["name"]]]["mod"] + 1 for sk in bd["skills"] if not sk["prof"])
assert bd["initiative"] == bd["abilities"]["dex"]["mod"] + 1  # Jack of All Trades applies to initiative
b1 = mk(character_class="Bard", level=1)
assert b1["initiative"] == b1["abilities"]["dex"]["mod"]
assert mk(race="Human", character_class="Monk", level=2)["speed"] == 40
assert mk(race="Human", character_class="Barbarian", level=5)["speed"] == 40
tot = lambda cls, lvl: sum(a["score"] for a in mk(race="Human", character_class=cls, level=lvl)["abilities"].values())  # noqa: E731
assert tot("Fighter", 6) - tot("Fighter", 5) == 2 and tot("Rogue", 10) - tot("Rogue", 9) == 2 and tot("Wizard", 6) == tot("Wizard", 5)
r = engine.roll("4d6kh3")
assert len(r["kept"]) == 3 and r["total"] == sum(r["kept"])
a = engine.roll("1d20", "advantage")
assert a["discarded"] is not None and a["kept"][0] >= a["discarded"][0]
d = engine.roll("1d20", "disadvantage")
assert d["kept"][0] <= d["discarded"][0]

with TestClient(server.app) as client:
    assert client.get("/").status_code == 200
    st = client.get("/api/status").json()
    assert st["mode"] == "offline" and "dice" in st["agents"]
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["event"] == "presence"
        chat = lambda m: client.post("/api/chat", json={"cid": "t", "message": m, "who": "Tester"}).json()  # noqa: E731
        hero = chat("character level 3 tiefling warlock")["cards"][0]
        assert hero["type"] == "character" and hero["class"] == "Warlock" and hero["race"] == "Tiefling" and hero["id"]
        enc = chat("encounter level 3 party of 4 hard undead")["cards"][0]
        assert enc["type"] == "encounter" and enc["id"]
        assert chat("npc innkeeper")["cards"][0]["role"] == "innkeeper"
        loot = chat("loot level 6 hoard")["cards"][0]
        assert loot["type"] == "loot" and loot["id"]
        assert chat("roll 2d6+3")["cards"][0]["type"] == "roll"
        assert chat("note: Crypt hook - the bell tolls thrice")["cards"][0]["type"] == "note"
        # party is separate from the Archive: an unrecruited hero must not join combat
        assert chat("character level 2 human fighter")["cards"][0]["in_party"] is False
        assert chat("party")["cards"][0]["members"] == []
        solo = chat("start combat")["cards"][0]
        assert solo["active"] and not any(c["side"] == "party" for c in solo["combatants"])
        chat("end combat")
        assert chat(f"add {hero['name']} to the party")["cards"][0]["members"][0]["id"] == hero["id"]
        assert [m["id"] for m in client.get("/api/party").json()] == [hero["id"]]
        combat = chat("start combat")["cards"][0]
        assert combat["active"] and [c["name"] for c in combat["combatants"] if c["side"] == "party"] == [hero["name"]]
        foe = next(c for c in combat["combatants"] if c["side"] == "foe")
        hit = client.post("/api/tool/combat_hp", json={"args": {"target": foe["name"], "delta": -5}}).json()
        assert hit["type"] == "combat"
        assert client.post("/api/tool/next_turn", json={}).json()["type"] == "combat"
        job = client.post("/api/tool/queue_print", json={"args": {"item_name": "Goblin x3"}}).json()
        assert job["status"] == "queued"
        assert client.post("/api/tool/set_print_status", json={"args": {"id": job["id"], "status": "printing"}}).json()["status"] == "printing"
        assert client.post("/api/tool/combat_hp", json={"args": {"target": "nobody", "delta": 1}}).json()["type"] == "error"
        assert chat("end combat")["cards"][0]["active"] is False
        assert chat(f"remove {hero['name']} from the party")["cards"][0]["members"] == []
        state = chat("what do we have")["cards"][0]
        assert state["type"] == "state" and state["character"] and state["encounter"] and state["party"] == []
        assert "offline" in chat("gibberish")["reply"].lower()
        seen = set()
        for _ in range(60):
            ev = ws.receive_json()
            seen.add(ev["event"])
            if {"tool", "tool_start", "thinking"} <= seen:
                break
        assert {"tool", "tool_start", "thinking"} <= seen, seen
    items = client.get("/api/items?kind=character").json()
    assert len(items) == 2 and not any(i["in_party"] for i in items)
    for i in items:
        assert client.delete(f"/api/items/{i['id']}").json()["ok"]

# party: concurrent adds are not lost, and campaign_state lists members beyond its 30-hero summary window
import threading  # noqa: E402
import tools  # noqa: E402

heroes = [tools.create_character(character_class="Fighter")["id"] for _ in range(35)]
ts = [threading.Thread(target=tools.party_add, args=(h,)) for h in heroes]
[t.start() for t in ts]
[t.join() for t in ts]
assert sorted(m["id"] for m in tools.party_members()) == sorted(heroes)
assert {m["id"] for m in tools.campaign_state()["party"]} == set(heroes)
for h in heroes:
    db.delete_item(h)

# offline router: whole-word matching, longest race wins
import agent  # noqa: E402

route = lambda m: agent.offline_agent("t", m, "Tester", None)[1]  # noqa: E731
assert route("character level 3 half-elf bard")[0]["race"] == "Half-Elf"
assert route("character level 3 half orc fighter")[0]["race"] == "Half-Orc"
assert route("send the party a message") == []
assert route("my stranger friend") == []
assert route("a house on the estate") == []
assert route("two heroes please")[0]["type"] == "character"
assert route("npc sage")[0]["role"] == "sage"

# Claude loop with a scripted fake client (no network)
from types import SimpleNamespace as NS  # noqa: E402


def fake_client(script, seen):
    def create(**kw):
        seen.append({"msgs": [(m["role"], m["content"] if isinstance(m["content"], str) else
                               [x["tool_use_id"] if isinstance(x, dict) else x.type for x in m["content"]]) for m in kw["messages"]],
                     "cached": kw["tools"][-1].get("cache_control")})
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step
    return NS(messages=NS(create=create))


tool_turn = lambda stop: NS(stop_reason=stop, content=[NS(type="text", text="Rolling."),  # noqa: E731
                                                       NS(type="tool_use", id="tu1", name="roll_dice", input={"expression": "1d20"})])
done = NS(stop_reason="end_turn", content=[NS(type="text", text="Nat what?")])

# a max_tokens stop that still contains a tool_use must still get its tool_result
seen = []
agent._client = lambda: fake_client([tool_turn("max_tokens"), done], seen)
reply, cards = agent.claude_agent("c1", "roll me a d20", "DM", None)
assert reply == "Nat what?" and cards[0]["type"] == "roll"
assert seen[1]["msgs"][-1] == ("user", ["tu1"]) and seen[0]["cached"] == {"type": "ephemeral"}
assert [m["role"] for m in agent.HISTORY["c1"]] == ["user", "assistant", "user", "assistant"]

# an API failure mid-turn must not leave an unanswered tool_use in the history
before = len(agent.HISTORY["c1"])
agent._client = lambda: fake_client([tool_turn("tool_use"), RuntimeError("boom")], [])
try:
    agent.claude_agent("c1", "again", "DM", None)
    raise AssertionError("expected failure")
except RuntimeError:
    pass
assert len(agent.HISTORY["c1"]) == before
seen = []
agent._client = lambda: fake_client([done], seen)
agent.claude_agent("c1", "and again", "DM", None)
assert [r for r, _ in seen[0]["msgs"]] == ["user", "assistant", "user", "assistant", "user"]

# conversations are bounded
for i in range(agent.MAX_CONVERSATIONS + 5):
    agent._history(f"x{i}")
assert len(agent.HISTORY) <= agent.MAX_CONVERSATIONS
# a conversation whose turn is in flight keeps its history and lock when others push it past the cap
agent.HISTORY.clear()
agent._locks.clear()
busy = agent._history("busy")
agent._locks["busy"] = threading.Lock()
agent._locks["busy"].acquire()
for i in range(agent.MAX_CONVERSATIONS + 5):
    agent._history(f"y{i}")
assert agent.HISTORY["busy"] is busy and agent._locks["busy"].locked()
agent._locks["busy"].release()

# Print Forge webhook fires on queue and on each status change, and Claude can set status
import json  # noqa: E402
import db  # noqa: E402
import tools  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402

posts = []


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):
        posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Hook)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["PRINT_WEBHOOK_URL"] = f"http://127.0.0.1:{srv.server_port}/hook"
assert tools.call_tool("queue_print", {"item_name": "Goblin x3", "scale_mm": "28<img>"})["type"] == "error"
job = tools.call_tool("queue_print", {"item_name": "Ogre", "scale_mm": "32"})
assert job["scale_mm"] == 32
tools.call_tool("set_print_status", {"id": job["id"], "status": "done"})
import time  # noqa: E402

for _ in range(50):
    if len(posts) >= 2:
        break
    time.sleep(0.1)
assert set(posts[0]) == set(tools.PRINT_KEYS)
ogre = [p["status"] for p in posts if p["name"] == "Ogre"]
assert ogre == ["queued", "done"], ogre  # delivered in order
note = tools.save_note("n", "t")
assert tools.call_tool("set_print_status", {"id": note["id"], "status": "done"})["type"] == "error"
assert "status" not in db.get_item(note["id"])
assert any(t["name"] == "set_print_status" for t in tools.TOOL_SCHEMAS)
os.environ.pop("PRINT_WEBHOOK_URL")
print("ALL SMOKE TESTS PASSED")
