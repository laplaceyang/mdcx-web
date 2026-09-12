"""演员管理页的演员列表缓存：userdata 下的 actor_cache.db（SQLite）。

跟随 /app/data 挂载卷持久化，多浏览器共享同一份缓存；
页面上只有点「刷新列表」才会重新请求 Emby 并更新此处。
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from mdcx.config.resources import resources

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actors (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    updated_at REAL NOT NULL,
    value TEXT NOT NULL
)
"""


def _db_path() -> Path:
    return Path(resources.u("actor_cache.db"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(_SCHEMA)
    return conn


def get_actors() -> tuple[float, list[dict[str, Any]]] | None:
    """返回 (updated_at epoch 秒, 演员列表)；无缓存返回 None。"""
    conn = _connect()
    try:
        row = conn.execute("SELECT updated_at, value FROM actors WHERE id = 1").fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row[0], json.loads(row[1])


def set_actors(actors: list[dict[str, Any]]) -> float:
    """写入演员列表，返回 updated_at epoch 秒。"""
    updated_at = time.time()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO actors (id, updated_at, value) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, value = excluded.value",
                (updated_at, json.dumps(actors, ensure_ascii=False)),
            )
    finally:
        conn.close()
    return updated_at
