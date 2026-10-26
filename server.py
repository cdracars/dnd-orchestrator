"""Dungeon Master's Orchestrator: FastAPI server. Run it, open the LAN URL on any device at the table."""
import asyncio
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import agent
import db
import tools

BASE = Path(__file__).parent
PORT = int(os.environ.get("PORT", "8080"))
loop = None


@asynccontextmanager
async def lifespan(_app):
    global loop
    loop = asyncio.get_running_loop()
    yield


app = FastAPI(title="Dungeon Master's Orchestrator", lifespan=lifespan)


class Hub:
    def __init__(self):
        self.clients = set()

    async def connect(self, ws):
        await ws.accept()
        self.clients.add(ws)
        await self.broadcast({"event": "presence", "count": len(self.clients)})

    async def drop(self, ws):
        self.clients.discard(ws)
        await self.broadcast({"event": "presence", "count": len(self.clients)})

    async def broadcast(self, ev):
        for c in list(self.clients):
            try:
                await c.send_json(ev)
            except Exception:  # noqa: BLE001
                self.clients.discard(c)


hub = Hub()


def emit(ev: dict):
    """Thread-safe: tools run in worker threads, websockets live on the event loop."""
    if loop and hub.clients:
        asyncio.run_coroutine_threadsafe(hub.broadcast(ev), loop)


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:  # noqa: BLE001
        pass
    return sorted(ips) or ["127.0.0.1"]


class ChatIn(BaseModel):
    cid: str = "anon"
    message: str
    who: str = "DM"


class ToolIn(BaseModel):
    args: dict = {}
    cid: str = "anon"
    who: str = "DM"


@app.get("/api/status")
def status():
    live = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"mode": "claude" if live else "offline", "model": agent.MODEL if live else None, "agents": tools.AGENTS,
            "ips": lan_ips(), "port": PORT, "print_webhook": bool(os.environ.get("PRINT_WEBHOOK_URL"))}


def _with_party(i):
    if i.get("type") == "character":
        i["in_party"] = i["id"] in (db.get_state("party") or [])
    return i


@app.get("/api/items")
def items(kind: str = None):
    return [_with_party(i) for i in db.list_items(kind)]


@app.get("/api/items/{item_id}")
def item(item_id: int):
    i = db.get_item(item_id)
    if not i:
        raise HTTPException(404, "Not found")
    return _with_party(i)


@app.get("/api/party")
def party():
    return [_with_party(m) for m in tools.party_members()]


@app.delete("/api/items/{item_id}")
def delete_item(item_id: int):
    ok = db.delete_item(item_id)
    emit({"event": "library"})
    return {"ok": ok}


@app.get("/api/combat")
def combat():
    return db.get_state("combat") or {"active": False}


@app.get("/api/log")
def log():
    return db.recent_log()


@app.post("/api/tool/{name}")
def run_tool(name: str, body: ToolIn):
    if name not in tools.TOOLS:
        raise HTTPException(404, f"Unknown tool {name}")
    return tools.call_tool(name, body.args, body.cid, body.who, emit)


@app.post("/api/chat")
async def chat(body: ChatIn):
    msg = body.message.strip()
    if not msg:
        raise HTTPException(400, "Say something, adventurer.")
    return await asyncio.to_thread(agent.handle, body.cid, msg[:4000], body.who or "DM", emit)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.drop(ws)


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


def banner():
    live = os.environ.get("ANTHROPIC_API_KEY")
    print("\n  ⚔️  DUNGEON MASTER'S ORCHESTRATOR  ⚔️")
    print(f"  Mode : {'Claude (' + agent.MODEL + ')' if live else 'Offline Rules Engine (set ANTHROPIC_API_KEY for Claude)'}")
    print(f"  Local: http://localhost:{PORT}")
    for ip in lan_ips():
        print(f"  Table: http://{ip}:{PORT}   <- open this on phones, tablets, laptops\n")


if __name__ == "__main__":
    banner()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
