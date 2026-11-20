"""Offline MCP server for the bot evaluation: `main.py`'s 28 tools over stdio, on one frozen
fixture of towns/_eval/fixtures/<id>/ (tests/offline.py does the patching). No network.

Started by `claude -p --mcp-config <file from mcp_config.py>`; configured by the environment:
  BOT_EVAL_FIXTURE    fixture id (required), e.g. 7365-d22
  BOT_EVAL_CLOCK      empty = data time + 10 min; "HH:MM" = that game time (Paris) on the data
                      day; "+5h" / "+30m" = offset from the data time
  LISTENER_USER_ID    the Discord id the listener would pass down (optional)
  LISTENER_CONTEXT    thread | dm (optional)
  BOT_EVAL_FILES      path of a JSON {relative path under towns/: text}, written into the
                      temporary towns/ before the first call, e.g. "_user_towns/<id>": "7365",
                      "_bot/memory/<id>.md": "..."  (the scenario's `memory` / `user_town`)
  BOT_EVAL_MANIFEST   on exit, the temporary towns/ manifest is written there (check D13)
`server.py --now` (same environment) prints the frozen time (UTC ISO) and exits.
stdout carries only the MCP protocol: everything this file prints goes to stderr.
The patches are process-wide: one fixture per process.
"""

import json
import os
import re
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from offline import frozen_now, manifest, offline   # noqa: E402

FIXTURES = ROOT / "towns" / "_eval" / "fixtures"
SYNTH_USER = "100000000000000001"   # the synthetic Discord id scenarios run as


def fixture_towns(fixture: Path) -> list[tuple[str, int]]:
    """[(folder, town id)] of the towns in a fixture, from their cache/_meta.json."""
    return [(d.name, json.loads((d / "cache" / "_meta.json").read_text())["town_id"])
            for d in sorted((fixture / "towns").iterdir()) if (d / "cache" / "_meta.json").exists()]


def clock_spec(spec: str, data_time: datetime) -> datetime:
    """The frozen time for BOT_EVAL_CLOCK (see the module docstring)."""
    spec = spec.strip()
    if not spec:
        return data_time + timedelta(minutes=10)
    if m := re.fullmatch(r"\+(\d+)([hm])", spec):
        n = int(m[1])
        return data_time + (timedelta(hours=n) if m[2] == "h" else timedelta(minutes=n))
    if m := re.fullmatch(r"(\d{1,2}):(\d{2})", spec):
        return data_time.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
    sys.exit(f"BOT_EVAL_CLOCK: '{spec}' is not empty, HH:MM or +Nh / +Nm")


def prepare(run, town: int, clock: str, user: str | None, context: str | None, files: dict) -> None:
    """Inside offline(): the scenario's clock, listener identity and files in the temporary towns/."""
    if user:
        os.environ["LISTENER_USER_ID"] = user
    if context:
        os.environ["LISTENER_CONTEXT"] = context
    else:
        os.environ.pop("LISTENER_CONTEXT", None)
    run.now["t"] = clock_spec(clock, run.now["t"] - timedelta(minutes=10))
    (run.towns_dir / "_current_town").write_text(str(town))
    for rel, text in files.items():
        target = (run.towns_dir / rel).resolve()
        if run.towns_dir.resolve() not in target.parents:
            sys.exit(f"files: {rel} is outside towns/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def scenario_files(s: dict, user: str = "") -> dict:
    """{path under towns/: text} a scenario needs: its memory (DM) and its user town,
    named by the synthetic Discord id the scenario runs as."""
    user = user or SYNTH_USER
    files = {}
    if s.get("memory"):
        files[f"_bot/memory/{user}.md"] = s["memory"]
    if s.get("user_town"):
        files[f"_user_towns/{user}"] = str(s["user_town"])
    return files


def main() -> None:
    fid = os.environ.get("BOT_EVAL_FIXTURE", "")
    fixture = FIXTURES / fid
    if not fid or not (fixture / "towns").is_dir():
        sys.exit(f"BOT_EVAL_FIXTURE '{fid}': no such fixture in {FIXTURES}")
    towns = fixture_towns(fixture)
    town = towns[0][1]
    user, context = os.environ.get("LISTENER_USER_ID"), os.environ.get("LISTENER_CONTEXT")
    manifest_path = os.environ.get("BOT_EVAL_MANIFEST")

    real_stdout = sys.stdout
    sys.stdout = sys.stderr            # offline() and the tools must not touch the protocol stream
    with offline(fixture, towns, town, prefix="bot-eval-") as run:
        # offline() clears LISTENER_USER_ID and sets the clock to data time + 10 min.
        files = {}
        if path := os.environ.get("BOT_EVAL_FILES"):
            files = json.loads(Path(path).read_text(encoding="utf-8"))
        prepare(run, town, os.environ.get("BOT_EVAL_CLOCK", ""), user, context, files)
        print(f"bot-eval server: fixture {fid} town {town}, now {run.now['t']:%Y-%m-%d %H:%M}", file=sys.stderr)
        sys.stdout = real_stdout
        if "--now" in sys.argv[1:]:
            # The frozen time as UTC ISO text, for run.py's chat timestamp; no protocol.
            print(run.now["t"].astimezone(timezone.utc).isoformat(timespec="seconds"))
            return
        # `claude` stops its servers with SIGTERM: turn it into a normal exit so `finally` runs.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        try:
            run.main.mcp.run()
        finally:
            if manifest_path:
                Path(manifest_path).write_text(manifest(run.towns_dir) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
