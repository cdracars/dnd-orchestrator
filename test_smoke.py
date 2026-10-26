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

import threading  # noqa: E402

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
