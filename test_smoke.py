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
