"""Plain-assert checks of usage stats (no pytest):  .venv/bin/python tests/usage_stats_checks.py

Everything runs on a temp db (USAGE_STATS_DB / --db): the real ~/.myhordes_mcp is never touched.
Covers utils/usage_stats.py (writer, origin, off switch), the fata/client.py recording (fake
httpx, one row per real request, none for archive hits) and scripts/usage_stats.py (windows,
categories, length cap, empty db).
"""

import asyncio
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

TMP = Path(tempfile.mkdtemp(prefix="usage-stats-"))
os.environ["USAGE_STATS_DB"] = str(TMP / "w" / "s.sqlite")   # set before anything imports
os.environ.pop("LISTENER_USER_ID", None)
os.environ.pop("USAGE_STATS_ORIGIN", None)

import httpx   # noqa: E402
import usage_stats as report_mod   # noqa: E402  scripts/usage_stats.py
from myhordes_mcp.fata import client   # noqa: E402
from myhordes_mcp.utils import usage_stats as writer   # noqa: E402

DB = Path(os.environ["USAGE_STATS_DB"])


def rows(sql, db=DB):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# --- writer -----------------------------------------------------------------
assert writer.db_path() == DB
writer.record_fata_call(8299, None, "ok", 200, 120)         # the directory is created
assert rows("SELECT town, day, origin, outcome, status, ms FROM fata_calls") == [(8299, None, "local", "ok", 200, 120)]
os.environ["LISTENER_USER_ID"] = "123"
assert writer.origin() == "bot"
os.environ["USAGE_STATS_ORIGIN"] = "timer"
assert writer.origin() == "timer"                           # the refresh timer wins over the bot
os.environ.pop("LISTENER_USER_ID"), os.environ.pop("USAGE_STATS_ORIGIN")
assert writer.origin() == "local"

# off switch writes nothing; an unwritable path does not raise
os.environ["USAGE_STATS_DB"] = "off"
assert writer.db_path() is None
writer.record_fata_call(1, None, "ok", 200, 1)
(TMP / "blocker").write_text("x")
os.environ["USAGE_STATS_DB"] = str(TMP / "blocker" / "s.sqlite")
writer.record_fata_call(1, None, "ok", 200, 1)
os.environ["USAGE_STATS_DB"] = str(DB)
assert len(rows("SELECT * FROM fata_calls")) == 1

# --- fata/client.py: one row per real HTTP attempt --------------------------
RAW_OK = {"town_info": {"day": 3}}


class Resp:
    def __init__(self, status, body=None, bad_json=False):
        self.status_code, self.body, self.bad_json = status, body, bad_json
        self.request = httpx.Request("GET", "https://x")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=self.request, response=self)

    def json(self):
        if self.bad_json:
            raise ValueError("no json")
        return self.body


def run_load(resp, day=None, raises=None):
    async def fake_get(self, url, params=None, **kw):
        if raises:
            raise raises
        return resp
    real_get, real_result = httpx.AsyncClient.get, client._result
    httpx.AsyncClient.get = fake_get
    client._result = lambda town, raw: {"meta": {}}   # parsing is not under test here
    try:
        return asyncio.run(client._load(8299, day))
    finally:
        httpx.AsyncClient.get, client._result = real_get, real_result


def last():
    return rows("SELECT outcome, status FROM fata_calls ORDER BY rowid DESC LIMIT 1")[0]


# a payload without `town_info.day` is "ok" but nothing to archive: keeps the real towns/ untouched
assert not run_load(Resp(200, {"town_info": {}})).get("error") and last() == ("ok", 200)
assert "rate limit" in run_load(Resp(429)).get("error") and last() == ("rate_limited", 429)
assert "HTTP 500" in run_load(Resp(500)).get("error") and last() == ("http_error", 500)
assert "Could not reach" in run_load(None, raises=httpx.ConnectError("down")).get("error") and last() == ("network_error", None)
assert "not JSON" in run_load(Resp(200, bad_json=True)).get("error") and last() == ("bad_data", 200)
assert run_load(Resp(200, {"nope": 1})).get("error") and last() == ("bad_data", 200)   # parser refuses
n = len(rows("SELECT * FROM fata_calls"))
assert n == 7, n
# a past day already final in the archive is served without HTTP: no row
real_arch, real_cur = client._from_archive, client.archive.get_current_day
client._from_archive = lambda town, day, final_only: {"meta": {}}
client.archive.get_current_day = lambda town: 10
try:
    assert run_load(Resp(200, RAW_OK), day=2) == {"meta": {}}
finally:
    client._from_archive, client.archive.get_current_day = real_arch, real_cur
assert len(rows("SELECT * FROM fata_calls")) == n

# --- the report -------------------------------------------------------------
NOW = 1_800_000_000
H = 3600
R = TMP / "r.sqlite"


def make(path, turns=(), tools=(), fata=()):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE turns (id INTEGER PRIMARY KEY, ts, kind, place, user, tier, model, resumed,
            wall_s, input_tokens, output_tokens, cache_read, cache_created, cost_usd, num_turns, context);
        CREATE TABLE tool_calls (turn_id, ts, tool);
        CREATE TABLE fata_calls (ts, town, day, origin, outcome, status, ms);""")
    conn.executemany("INSERT INTO turns (ts,kind,place,user,tier,resumed,input_tokens,output_tokens,"
                     "cache_read,cache_created,cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?)", turns)
    conn.executemany("INSERT INTO tool_calls VALUES (NULL,?,?)", tools)
    conn.executemany("INSERT INTO fata_calls VALUES (?,8299,NULL,?,?,?,1)", fata)
    conn.commit(), conn.close()


make(R,
     turns=[  # ts, kind, place, user, tier, resumed, in, out, read, written, cost
         (NOW - 1 * H, "ok", "t1", "u1", "trusted", 0, 10, 100, 1000, 100, 1.0),      # 24h, new session
         (NOW - 2 * H, "ok", "t1", "u1", "trusted", 1, 10, 100, 1000, 100, 1.0),      # same session
         (NOW - 3 * H, "error", "t2", "u2", "public", 1, 0, 0, 0, 0, 0.0),            # failed, resumed session
         (NOW - 30 * H, "ok", "t3", "u3", "public", 0, 10, 100, 1000, 100, 1.0),      # 48h only
         (NOW - 100 * H, "ok", "t4", "u1", "trusted", 0, 10, 100, 1000, 100, 1.0),    # 7d only
         (NOW - 200 * H, "ok", "t5", "u9", "trusted", 0, 10, 100, 1000, 100, 1.0)],   # outside every window
     tools=[(NOW - 1 * H, "mcp__myhordes__find_expedition_path"), (NOW - 1 * H, "mcp__myhordes__get_camping_odds"),
            (NOW - 1 * H, "mcp__myhordes__get_build_options"), (NOW - 1 * H, "mcp__myhordes__search_wiki"),
            (NOW - 1 * H, "mcp__myhordes__get_town_overview"), (NOW - 1 * H, "Read"),
            (NOW - 30 * H, "mcp__myhordes__get_town_overview"), (NOW - 100 * H, "mcp__myhordes__remember"),
            (NOW - 200 * H, "Read")],
     fata=[(NOW - 1 * H, "bot", "ok", 200), (NOW - 2 * H, "timer", "rate_limited", 429),
           (NOW - 30 * H, "local", "http_error", 500), (NOW - 100 * H, "bot", "ok", 200)])
text = report_mod.report(R, now=NOW)
lines = {l.split("  ")[0].strip(): l for l in text.splitlines()}


def cells(label):
    return lines[label].split("(")[0].split()[len(label.split()):]


assert cells("turns ok") == ["2", "3", "4"], text
assert cells("turns failed") == ["1", "1", "1"]
assert cells("sessions") == ["2", "3", "4"] and "new 1 · resumed 1 in 24h" in lines["sessions"], text
assert lines["users"].split()[1:4] == ["2", "3", "3"] and "trusted 1 · public 1 in 24h" in lines["users"], lines["users"]
assert lines["tools"].split()[1:4] == ["6", "7", "8"], lines["tools"]
assert "  expeditions" in text and "  other" in text and "  construction" in text
assert lines["fata HTTP"].split()[2:5] == ["2", "3", "4"] and "bot 1 · timer 1 · local 0 in 24h" in text
assert "(429: 1 in 24h)" in text
assert "top tools 7d: get_town_overview 2, " in text and "remember 1" in text
assert "$2.00  $3.00  $4.00" in text, text
assert "tokens in" in text and "since" in text and len(text) <= report_mod.MAX_CHARS

# categories: prefix stripped, one dict, unknown -> other
assert report_mod.category("mcp__myhordes__get_camping_odds") == "camping"
assert report_mod.category("mcp__other__plan_kill_route") == "expeditions"
assert report_mod.category("Read") == "other" and report_mod.category("mcp__myhordes__remember") == "other"
assert report_mod.human(950) == "950" and report_mod.human(45_000) == "45k" and report_mod.human(1_234_567) == "1.2M"

# length cap: many distinct tools with long names squeeze the top list, never the table
big = TMP / "big.sqlite"
make(big, turns=[(NOW - H, "ok", "t", "u", "trusted", 0, 1, 1, 1, 1, 1.0)],
     tools=[(NOW - H, f"mcp__myhordes__a_very_long_tool_name_number_{i:03d}") for i in range(300)])
t = report_mod.report(big, now=NOW)
assert len(t) <= report_mod.MAX_CHARS and "tokens out" in t and "```" in t.split("top tools")[0][-4:], len(t)

# empty cases: no file, a file with no tables, tables with no rows
assert report_mod.report(TMP / "missing.sqlite", now=NOW) == "**Bot usage**: no data yet."
sqlite3.connect(TMP / "blank.sqlite").close()
blank = report_mod.report(TMP / "blank.sqlite", now=NOW)
assert blank == "**Bot usage**: no data yet.", blank
make(TMP / "norows.sqlite")
assert report_mod.report(TMP / "norows.sqlite", now=NOW) == "**Bot usage**: no data yet."
# only fata_calls exist (a PC without the listener): the other parts say so
conn = sqlite3.connect(TMP / "fata.sqlite")
conn.execute("CREATE TABLE fata_calls (ts, town, day, origin, outcome, status, ms)")
conn.execute("INSERT INTO fata_calls VALUES (?,1,NULL,'local','ok',200,1)", (NOW - H,))
conn.commit(), conn.close()
t = report_mod.report(TMP / "fata.sqlite", now=NOW)
assert "turns: no data yet" in t and "tools: no data yet" in t and "fata HTTP" in t, t

# the script end to end (what /stats runs), --db and env, read-only
out = subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_stats.py"), "--db", str(R)],
                     capture_output=True, text=True, check=True).stdout
assert out.startswith("**Bot usage** (since") and len(out) <= 1900
mtime = R.stat().st_mtime_ns
subprocess.run([sys.executable, str(ROOT / "scripts" / "usage_stats.py")], env={**os.environ, "USAGE_STATS_DB": str(R)},
               capture_output=True, text=True, check=True)
assert R.stat().st_mtime_ns == mtime

print("usage stats checks: ok")
