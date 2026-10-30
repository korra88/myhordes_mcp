"""Per-citizen Control Points log, built from the zone CP Fata reports.

/towndata gives CP per zone (`human`, game-sourced, recorded at the zone
update), never per citizen. A citizen's CP is read from it when:

  solo     they are the only citizen on the zone and were already there when
           the zone was updated (their last position update is not newer);
  derived  the zone holds a group whose other members all have a solo reading
           the same day: their CP is subtracted from the zone total.

Limit: Fata does not say who stood on the zone at the update. A citizen who
left afterwards still counts in the zone's CP, so a reading can be too high.

CP changes with status (knowledge/tactics/game-mechanics.md, "Losing CP bonus"),
so the log keeps both the best value seen (max) and the most recent one (last).

Stored per town in towns/{town}/citizens-cp.json, updated on every fetch.
"""

import json
import re
import time

from . import archive
from .risk import CP_PER_CITIZEN, MAX_CP_PER_CITIZEN, zone_cp

CP_FILE = "citizens-cp.json"
MAX_READINGS = 30   # per citizen
MAX_GROUPS = 200


def _load(town_id: int) -> dict:
    tdir = archive.town_dir(town_id)
    if tdir is None:
        return {"town_id": town_id, "citizens": {}, "groups": []}
    try:
        log = json.loads((tdir / CP_FILE).read_text(encoding="utf-8"))
        log.setdefault("citizens", {})
        log.setdefault("groups", [])
        return log
    except (OSError, json.JSONDecodeError):
        return {"town_id": town_id, "citizens": {}, "groups": []}


def load_cp_log(town_id: int) -> dict:
    return _load(town_id)


def zone_readings(data: dict) -> tuple[list[dict], list[dict]]:
    """(solo readings, group readings) from a parsed /towndata result."""
    zones = {z["coords"]: z for z in data.get("zones", [])}
    per_zone: dict[str, list[dict]] = {}
    for c in data.get("citizens", []):
        if not c["inside_town"]:
            per_zone.setdefault(c["coords"], []).append(c)

    solos, groups = [], []
    for coords, people in per_zone.items():
        zone = zones.get(coords)
        cp = zone_cp(zone, people) if zone else None
        if cp is None:
            continue
        base = {"cp": cp, "day": zone.get("updated_day"), "time": zone["updated_on"], "coords": coords}
        if len(people) == 1:
            solos.append({**base, "id": people[0]["id"], "name": people[0]["name"], "job": people[0]["job"]})
        else:
            groups.append({**base, "members": [c["id"] for c in people],
                           "names": [c["name"] for c in people]})
    return solos, groups


def _add(entry: dict, reading: dict) -> None:
    readings = entry.setdefault("readings", [])
    if any(r["time"] == reading["time"] and r["coords"] == reading["coords"] for r in readings):
        return
    readings.append(reading)
    readings.sort(key=lambda r: r["time"])
    del readings[:-MAX_READINGS]
    entry["last"] = readings[-1]
    best = entry.get("max")
    if best is None or reading["cp"] > best["cp"] or (reading["cp"] == best["cp"] and reading["time"] > best["time"]):
        entry["max"] = reading


def update_cp_log(town_id: int, data: dict) -> None:
    """Add the readings of a parsed /towndata result to the town's CP log."""
    if data.get("error") or data.get("source") != "towndata":
        return
    tdir = archive.town_dir(town_id)
    if tdir is None:
        return
    solos, groups = zone_readings(data)
    if not solos and not groups:
        return
    log = _load(town_id)
    cits = log["citizens"]

    for s in solos:
        e = cits.setdefault(str(s["id"]), {})
        e["name"], e["job"] = s["name"], s["job"]
        _add(e, {k: s[k] for k in ("cp", "day", "time", "coords")} | {"source": "solo"})

    seen = {(g["time"], g["coords"]) for g in log["groups"]}
    for g in groups:
        if (g["time"], g["coords"]) not in seen:
            log["groups"].append(g)
    log["groups"] = sorted(log["groups"], key=lambda g: g["time"])[-MAX_GROUPS:]

    # Derive a member's CP when every other member has a solo reading that day.
    for g in log["groups"]:
        same_day = {}
        for mid in g["members"]:
            e = cits.get(str(mid)) or {}
            day_solos = [r for r in e.get("readings", []) if r["source"] == "solo" and r["day"] == g["day"]]
            if day_solos:
                same_day[mid] = min(day_solos, key=lambda r: abs(r["time"] - g["time"]))["cp"]
        unknown = [m for m in g["members"] if m not in same_day]
        if len(unknown) != 1:
            continue
        cp = g["cp"] - sum(same_day.values())
        if not 0 <= cp <= MAX_CP_PER_CITIZEN:
            continue
        mid = unknown[0]
        e = cits.setdefault(str(mid), {})
        e.setdefault("name", g["names"][g["members"].index(mid)])
        _add(e, {"cp": cp, "day": g["day"], "time": g["time"], "coords": g["coords"], "source": "derived"})

    log["town_id"] = town_id
    log["updated"] = int(time.time())
    path = tdir / CP_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def citizen_cp(log: dict, citizen_id: int) -> dict | None:
    """{'last': reading, 'max': reading} or None if never read."""
    e = log.get("citizens", {}).get(str(citizen_id))
    if not e or "last" not in e:
        return None
    return {"last": e["last"], "max": e["max"]}


def _cp(r: dict) -> str:
    return "0 (terrorised)" if r["cp"] == 0 else str(r["cp"])


def cp_label(log: dict, citizen_id: int) -> str:
    """Compact ' · CP 4 (max 6)' tag, or '' if unknown."""
    cp = citizen_cp(log, citizen_id)
    if cp is None:
        return ""
    last, best = cp["last"], cp["max"]
    tag = f" · CP {_cp(last)} (day {last['day']})"
    if best["cp"] != last["cp"]:
        tag = f" · CP {_cp(last)} (day {last['day']}, max {best['cp']})"
    return tag


def citizen_key(name: str) -> str:
    """A citizen name as players type it, for matching: "@PlayerName:12345" (a forum or
    Discord handle) and "playername" both → "playername"."""
    return re.sub(r"^@", "", name.strip()).split(":")[0].strip().lower()


def resolve_group_cp(data: dict, town_id: int, group_cp: int, party: str) -> tuple[int, list[str] | None]:
    """The CP a route tool plans with: `group_cp` if given (>= 0), else the total of the
    comma-separated `party` from the CP log, else the base CP of one citizen.
    Returns (cp, breakdown lines or None)."""
    if group_cp >= 0:
        return group_cp, None
    if party and not data.get("error"):
        return party_cp(load_cp_log(town_id), data["citizens"], party.split(","))
    return CP_PER_CITIZEN, None


def party_cp(log: dict, citizens: list[dict], names: list[str], base: int = CP_PER_CITIZEN) -> tuple[int, list[str]]:
    """Total CP of a party by citizen names, from each one's last reading.

    Unknown citizens count `base` (2, no bonus). Returns (total, breakdown lines)."""
    by_name = {citizen_key(c["name"]): c for c in citizens}
    total, lines = 0, []
    names = [n for n in names if n.strip()]
    if not names:
        return base, []
    for raw in names:
        n = raw.strip()
        if not n:
            continue
        c = by_name.get(citizen_key(n))
        cp = citizen_cp(log, c["id"]) if c else None
        if c is None:
            total += base
            lines.append(f"{n}: not a living citizen of this town — counted {base} CP")
        elif cp is None:
            total += base
            lines.append(f"{c['name']}: no CP reading yet — counted {base} CP")
        else:
            last, best = cp["last"], cp["max"]
            total += last["cp"]
            extra = f", max {best['cp']} on day {best['day']}" if best["cp"] != last["cp"] else ""
            lines.append(f"{c['name']}: {_cp(last)} CP (last seen day {last['day']} at {last['coords']}{extra})")
    return total, lines


def format_cp_log(log: dict, citizens: list[dict]) -> list[str]:
    """One line per living citizen: 'Elprede (Guardian) 7/7 — d7 [0|1]' (last/max CP,
    where and when the last reading was; max day only when it differs). A list, not
    a Markdown table: Discord shows tables raw and `[x|y]` breaks their cells."""
    rows, unread = [], []
    for c in sorted(citizens, key=lambda c: c["name"].lower()):
        cp = citizen_cp(log, c["id"])
        if cp is None:
            unread.append(c["name"])
            continue
        last, best = cp["last"], cp["max"]
        src = ", derived" if last.get("source") == "derived" else ""
        maxday = f", max d{best['day']}" if best["day"] != last["day"] else ""
        terror = " (terrorised)" if last["cp"] == 0 else ""
        rows.append(f"  {c['name']} ({c['job']}) {last['cp']}/{best['cp']}{terror} — d{last['day']} {last['coords']}{src}{maxday}")
    lines = ["Last/Max CP — day and zone of the last reading:"] + rows
    if unread:
        lines.append(f"Never read alone on a zone (assume {CP_PER_CITIZEN}): {', '.join(unread)}")
    return lines

