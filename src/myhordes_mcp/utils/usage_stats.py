"""Usage stats of the bot: Fata requests, in the SQLite file shared with the Discord listener.

The listener (../discord_mcp, `[stats]`) writes `turns` and `tool_calls` to the same file;
this module writes `fata_calls`, one row per REAL HTTP request to Fata (never an archive or
cache hit), called from `fata/client.py:_load`. `scripts/usage_stats.py` reads all three.

File: `~/.myhordes_mcp/usage_stats.sqlite`, outside every repo; env `USAGE_STATS_DB`
overrides the path, `USAGE_STATS_DB=off` disables (tests, the golden harness). Several
processes write at once (listener, the MCP servers of concurrent turns, the refresh timer):
one connection per write, WAL, 5 s busy timeout. A stats failure never breaks a request:
one warning line, then return. Only town ids, numbers and outcomes are stored.
"""

import logging
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = "~/.myhordes_mcp/usage_stats.sqlite"

# outcome: ok | rate_limited | http_error | network_error | bad_data
_SCHEMA = """
CREATE TABLE IF NOT EXISTS fata_calls (
    ts INTEGER NOT NULL, town INTEGER, day INTEGER, origin TEXT, outcome TEXT,
    status INTEGER, ms INTEGER
);
CREATE INDEX IF NOT EXISTS fata_calls_ts ON fata_calls (ts);
"""


def db_path() -> Path | None:
    """The stats file, or None when disabled (`USAGE_STATS_DB=off`)."""
    raw = os.getenv("USAGE_STATS_DB") or DEFAULT_DB
    return None if raw.strip().lower() == "off" else Path(raw).expanduser()


def origin() -> str:
    """Who asks: `bot` inside a listener turn (the listener sets LISTENER_USER_ID), `timer`
    when fata/refresh.py set USAGE_STATS_ORIGIN, else `local` (Claude Code, scripts)."""
    if os.getenv("USAGE_STATS_ORIGIN"):
        return os.environ["USAGE_STATS_ORIGIN"]
    return "bot" if os.getenv("LISTENER_USER_ID") else "local"


def record_fata_call(town: int, day: int | None, outcome: str, status: int | None, ms: int) -> None:
    """Add one row to `fata_calls`. Never raises."""
    try:
        path = db_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            with conn:
                conn.execute(
                    "INSERT INTO fata_calls (ts, town, day, origin, outcome, status, ms) VALUES (?,?,?,?,?,?,?)",
                    (int(time.time()), town, day, origin(), outcome, status, ms))
        finally:
            conn.close()
    except Exception as e:  # stats must never break a Fata request
        logging.getLogger(__name__).warning("usage stats write failed: %s", e)
