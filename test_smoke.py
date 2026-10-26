"""Smoke test: python test_smoke.py  (uses a throwaway database)"""
import os
import tempfile

os.environ["DND_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

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
        assert chat("loot level 6 hoard")["cards"][0]["type"] == "loot"
        assert chat("roll 2d6+3")["cards"][0]["type"] == "roll"
        assert chat("note: Crypt hook - the bell tolls thrice")["cards"][0]["type"] == "note"
        combat = chat("start combat")["cards"][0]
        assert combat["active"] and any(c["side"] == "party" for c in combat["combatants"])
        foe = next(c for c in combat["combatants"] if c["side"] == "foe")
        hit = client.post("/api/tool/combat_hp", json={"args": {"target": foe["name"], "delta": -5}}).json()
        assert hit["type"] == "combat"
        assert client.post("/api/tool/next_turn", json={}).json()["type"] == "combat"
        job = client.post("/api/tool/queue_print", json={"args": {"item_name": "Goblin x3"}}).json()
        assert job["status"] == "queued"
        assert client.post("/api/tool/set_print_status", json={"args": {"id": job["id"], "status": "printing"}}).json()["status"] == "printing"
        assert client.post("/api/tool/combat_hp", json={"args": {"target": "nobody", "delta": 1}}).json()["type"] == "error"
        assert chat("end combat")["cards"][0]["active"] is False
        state = chat("what do we have")["cards"][0]
        assert state["type"] == "state" and state["character"] and state["encounter"]
        assert "offline" in chat("gibberish")["reply"].lower()
        seen = set()
        for _ in range(60):
            ev = ws.receive_json()
            seen.add(ev["event"])
            if {"tool", "tool_start", "thinking"} <= seen:
                break
        assert {"tool", "tool_start", "thinking"} <= seen, seen
    items = client.get("/api/items?kind=character").json()
    assert len(items) == 1
    assert client.delete(f"/api/items/{items[0]['id']}").json()["ok"]
print("ALL SMOKE TESTS PASSED")
