"""Zone camp level record: what the tool last knew about a zone's camp upgrade level.

Fata does not expose the level (docs/camping-plan.md, 1.1). The odds tool therefore keeps
its own record in towns/{town}/camp-zones.json: per zone "[x|y]" {day, level, source}:

  reported  a player gave the level to the tool;
  planned   the level the tool's own plan was assumed to reach that day.

The level drops 15 every night (floor 0), so the default for a later day is
level - 15 * (day - recorded day). A newer entry replaces an older one.

Fata v1.3 now sends a camp-level estimate per zone (`zone["camp_level"]`) and the players'
camp plans: the odds tool prefers that estimate over this record (docs/camping-plan.md,
"Fata camp plans (v1.3)"); the record stays the fallback for zones Fata has no estimate for
and for older data.

Local file only, like the bot memory: no game action. Written only where TOWN_LOG_AUTO is on
(the Pi; camplog.AUTO), like the camping log: one writer for the shared towns/ repo.
"""

import json
import os

from . import archive
from .game import level_after_nights

ZONES_FILE = "camp-zones.json"


def load_zones(town_id: int) -> dict:
    tdir = archive.town_dir(town_id)
    if tdir is None:
        return {}
    try:
        data = json.loads((tdir / ZONES_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def record_zone(town_id: int, zone: str, day: int, level: int, source: str) -> bool:
    """Store the level of `zone` ("[x|y]") on `day`, replacing the older entry. False when the
    town has no folder yet or the write failed (a record failure never breaks a tool call)."""
    from . import camplog
    if not camplog.AUTO:   # same single writer as the camping log (the Pi)
        return False
    tdir = archive.town_dir(town_id)
    if tdir is None or source not in ("reported", "planned"):
        return False
    zones = load_zones(town_id)
    old = zones.get(zone)
    if old and old.get("day", 0) > day:
        return False
    zones[zone] = {"day": day, "level": int(level), "source": source}
    path = tdir / ZONES_FILE
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        tmp.write_text(json.dumps(zones, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


def estimate_level(entry: dict | None, today: int) -> tuple[int, str, int] | None:
    """(level today, note, day of the entry) from a recorded entry, None if there is none."""
    if not entry:
        return None
    d = entry["day"]
    level = level_after_nights(entry["level"], max(0, today - d))
    if entry["source"] == "planned":
        return level, f"estimate from the plan of day {d}, not verified", d
    return level, f"reported on day {d}", d
