"""
usage_stats.py — Report how the Discord bot is used (24 h, 48 h, 7 days), for `/stats`.

Reads the SQLite file the listener (turns, tool_calls) and the Fata client (fata_calls)
write: ~/.myhordes_mcp/usage_stats.sqlite, env USAGE_STATS_DB or --db to override. Prints
Discord markdown of at most 1900 characters (the listener cuts at 2000). A missing file or
table is "no data yet" for that part. Standard library only, so it runs with the system
python3 started by the listener, like set_town.py. Never opens the db for writing.

Usage:
    python3 scripts/usage_stats.py [--db PATH]
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = "~/.myhordes_mcp/usage_stats.sqlite"
MAX_CHARS = 1900
WINDOWS = (("24h", 24 * 3600), ("48h", 48 * 3600), ("7d", 7 * 24 * 3600))

# Tool category by name without the `mcp__<server>__` prefix; anything else is "other"
# (built-in tools like Read/Grep, the memory tools).
CATEGORIES = {
    "expeditions": ("find_expedition_path", "plan_expedition_supplies", "plan_kill_route",
                    "get_expedition_roster"),
    "camping": ("plan_camping", "get_camping_odds", "plan_group_camping"),   # old names: stats before 2026-11-21
    "construction": ("get_build_options", "get_blueprint_order", "get_buildings",
                     "get_construction_history"),
    "knowledge": ("search_wiki", "list_wiki_categories", "search_knowledge"),
    "town": ("get_town_overview", "get_citizen_positions", "get_citizen_cp", "get_defense_status",
             "get_bank_inventory", "get_scout_map", "get_zone_details", "get_town_changes",
             "get_night_report", "get_attack_distribution", "get_attack_forecast",
             "map_bank_to_dump_sheet"),
}
CATEGORY_OF = {tool: cat for cat, tools in CATEGORIES.items() for tool in tools}
ORDER = [*CATEGORIES, "other"]


def short_name(tool: str) -> str:
    """`mcp__myhordes__get_town_overview` -> `get_town_overview`."""
    if tool.startswith("mcp__"):
        return tool.split("__", 2)[-1]
    return tool


def category(tool: str) -> str:
    return CATEGORY_OF.get(short_name(tool), "other")


def human(n: float) -> str:
    """Compact count: 950, 45k, 1.2M, 11M."""
    n = float(n or 0)
    for limit, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if n >= limit:
            v = n / limit
            return f"{v:.1f}{suffix}" if v < 10 else f"{v:.0f}{suffix}"
    return f"{n:.0f}"


def money(x: float) -> str:
    return f"${x:.2f}" if x < 10 else f"${x:.0f}"


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def one(conn, sql: str, *args):
    return conn.execute(sql, args).fetchone()[0] or 0


def paris(ts: float) -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d %H:%M Paris")
    except Exception:  # no tz database: say UTC rather than guess
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def row(label: str, values: list[str], note: str = "") -> str:
    line = f"{label:<14}" + "".join(f"{v:>7}" for v in values)
    return line + (f"   {note}" if note else "")


def turn_lines(conn, since: list[float]) -> list[str]:
    cols = ("SUM(input_tokens), SUM(cache_read), SUM(cache_created), SUM(output_tokens), SUM(cost_usd)")
    per = []
    for s in since:
        ok = one(conn, "SELECT COUNT(*) FROM turns WHERE ts >= ? AND kind = 'ok'", s)
        failed = one(conn, "SELECT COUNT(*) FROM turns WHERE ts >= ? AND kind != 'ok'", s)
        fresh, read, written, out, cost = (v or 0 for v in conn.execute(
            f"SELECT {cols} FROM turns WHERE ts >= ?", (s,)).fetchone())
        sessions = one(conn, "SELECT COUNT(DISTINCT place) FROM turns WHERE ts >= ?", s)
        # new = a session whose first turn (resumed = 0) falls in the window
        new = one(conn, "SELECT COUNT(DISTINCT place) FROM turns WHERE ts >= ? AND resumed = 0", s)
        users = one(conn, "SELECT COUNT(DISTINCT user) FROM turns WHERE ts >= ?", s)
        tiers = dict(conn.execute(
            "SELECT tier, COUNT(DISTINCT user) FROM turns WHERE ts >= ? GROUP BY tier", (s,)).fetchall())
        per.append(dict(ok=ok, failed=failed, fresh=fresh, read=read, written=written, out=out,
                        cost=cost, sessions=sessions, new=new, users=users, tiers=tiers))
    a = per[0]
    lines = [
        row("turns ok", [human(p["ok"]) for p in per]),
        row("turns failed", [human(p["failed"]) for p in per]),
        row("sessions", [human(p["sessions"]) for p in per],
            f"(new {a['new']} · resumed {max(a['sessions'] - a['new'], 0)} in 24h)"),
        row("users", [human(p["users"]) for p in per],
            f"(trusted {a['tiers'].get('trusted', 0)} · public {a['tiers'].get('public', 0)} in 24h)"),
        row("tokens in", [human(p["fresh"] + p["read"] + p["written"]) for p in per]),
        row("  fresh", [human(p["fresh"]) for p in per]),
        row("  cache read", [human(p["read"]) for p in per]),
        row("  cache writ.", [human(p["written"]) for p in per]),
        row("tokens out", [human(p["out"]) for p in per]),
        row("cost est.", [money(p["cost"]) for p in per]),
    ]
    return lines


def tool_lines(conn, since: list[float]) -> tuple[list[str], list[tuple[str, int]]]:
    totals = [{c: 0 for c in ORDER} for _ in since]
    top: dict[str, int] = {}
    for i, s in enumerate(since):
        for tool, n in conn.execute(
                "SELECT tool, COUNT(*) FROM tool_calls WHERE ts >= ? GROUP BY tool", (s,)):
            totals[i][category(tool)] += n
            if i == len(since) - 1:
                top[short_name(tool)] = top.get(short_name(tool), 0) + n
    lines = [row("tools", [human(sum(t.values())) for t in totals])]
    lines += [row("  " + c, [human(t[c]) for t in totals]) for c in ORDER if any(t[c] for t in totals)]
    return lines, sorted(top.items(), key=lambda kv: (-kv[1], kv[0]))


def fata_lines(conn, since: list[float]) -> list[str]:
    def count(s, where=""):
        return one(conn, f"SELECT COUNT(*) FROM fata_calls WHERE ts >= ? {where}", s)
    a = since[0]
    origins = dict(conn.execute(
        "SELECT origin, COUNT(*) FROM fata_calls WHERE ts >= ? GROUP BY origin", (a,)).fetchall())
    note = " · ".join(f"{o} {origins.get(o, 0)}" for o in ("bot", "timer", "local"))
    limited = count(a, "AND outcome = 'rate_limited'")
    return [
        row("fata HTTP", [human(count(s)) for s in since], f"({note} in 24h)"),
        row("  errors", [human(count(s, "AND outcome != 'ok'")) for s in since],
            f"(429: {limited} in 24h)"),
    ]


def report(db: Path | None, now: float | None = None) -> str:
    """The /stats text. `now` is for tests."""
    now = time.time() if now is None else now
    since = [now - seconds for _, seconds in WINDOWS]
    if db is None or not db.exists():
        return "**Bot usage**: no data yet."
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        first = [conn.execute(f"SELECT MIN(ts) FROM {t}").fetchone()[0]
                 for t in ("turns", "fata_calls") if has_table(conn, t)]
        first = min((f for f in first if f), default=None)
        head = (f"**Bot usage** (since {paris(first)}, now {paris(now)})" if first
                else "**Bot usage**: no data yet.")
        body = [row("", [name for name, _ in WINDOWS])]
        top: list[tuple[str, int]] = []
        for table, part in (("turns", "turns"), ("tool_calls", "tools"), ("fata_calls", "fata")):
            if not has_table(conn, table):
                body.append(f"{part}: no data yet")
            elif part == "turns":
                body += turn_lines(conn, since)
            elif part == "tools":
                lines, top = tool_lines(conn, since)
                body += lines
            else:
                body += fata_lines(conn, since)
    finally:
        conn.close()
    if not first:
        return head
    while True:
        tail = ("\ntop tools 7d: " + ", ".join(f"{n} {c}" for n, c in top)) if top else ""
        text = f"{head}\n```text\n" + "\n".join(body) + "\n```" + tail
        if len(text) <= MAX_CHARS or not top:
            return text[:MAX_CHARS]
        top = top[:-1]   # too long: the top list is what gives way first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", help="stats file (default: $USAGE_STATS_DB or " + DEFAULT_DB + ")")
    args = parser.parse_args()
    raw = args.db or os.getenv("USAGE_STATS_DB") or DEFAULT_DB
    path = None if raw.strip().lower() == "off" else Path(raw).expanduser()
    try:
        print(report(path))
    except sqlite3.Error as e:
        print(f"Bot usage: the stats file could not be read ({type(e).__name__}).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
