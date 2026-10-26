"""Tiny SQLite campaign store shared by every tool and every connected device."""
import json
import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get("DND_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "campaign.db"))
_lock = threading.RLock()
_c = sqlite3.connect(DB_PATH, check_same_thread=False)
_c.row_factory = sqlite3.Row
with _lock:
    _c.executescript(
        """
        CREATE TABLE IF NOT EXISTS items(
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL,
            data TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, agent TEXT, tool TEXT, summary TEXT);
        """
    )
    _c.commit()


def _row(r):
    d = json.loads(r["data"])
    d.update({"id": r["id"], "kind": r["kind"], "created": r["created"]})
    d.setdefault("name", r["name"])
    return d


def save_item(kind: str, name: str, data: dict) -> int:
    with _lock:
        cur = _c.execute("INSERT INTO items(kind,name,data,created) VALUES(?,?,?,?)",
                         (kind, name, json.dumps(data), time.time()))
        _c.commit()
        return cur.lastrowid


def list_items(kind: str = None, limit: int = 200):
    with _lock:
        if kind:
            rows = _c.execute("SELECT * FROM items WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit)).fetchall()
        else:
            rows = _c.execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def get_item(item_id: int):
    with _lock:
        r = _c.execute("SELECT * FROM items WHERE id=?", (int(item_id),)).fetchone()
    return _row(r) if r else None


def update_item(item_id: int, patch: dict):
    with _lock:
        r = _c.execute("SELECT * FROM items WHERE id=?", (int(item_id),)).fetchone()
        if not r:
            return None
        data = json.loads(r["data"])
        data.update(patch)
        _c.execute("UPDATE items SET data=? WHERE id=?", (json.dumps(data), int(item_id)))
        _c.commit()
    return get_item(item_id)


def delete_item(item_id: int) -> bool:
    with _lock:
        cur = _c.execute("DELETE FROM items WHERE id=?", (int(item_id),))
        _c.commit()
        return cur.rowcount > 0


def get_state(key: str, default=None):
    with _lock:
        r = _c.execute("SELECT data FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(r["data"]) if r else default


def set_state(key: str, data) -> None:
    with _lock:
        _c.execute("INSERT INTO state(key,data) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data",
                   (key, json.dumps(data)))
        _c.commit()


def log_event(agent: str, tool: str, summary: str) -> None:
    with _lock:
        _c.execute("INSERT INTO log(ts,agent,tool,summary) VALUES(?,?,?,?)", (time.time(), agent, tool, summary[:300]))
        _c.commit()


def recent_log(n: int = 30):
    with _lock:
        rows = _c.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]
