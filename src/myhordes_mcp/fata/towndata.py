"""Parse the Fata Morgana `/towndata` JSON into the standard result dict.

`GET https://beta.fatamorgana.md26.eu/towndata?town={id}[&day={n}]` — public,
read-only, OK'd by the Fata developer for this MCP (2026-10-15). No day = the
latest day; `day=n` = that day as it was at its end. Not affected by the
nightly attack or game downtime.

Shape (town 8212, day 7: 814 KB raw, 128 KB gzipped):

    version       "1.0" (added 2026-10-16; absent in earlier archived days)
    town_info     town, day, name, tx/ty (town position on the map), door,
                  chaos/devast/hard, season, lang, map_type, roles {guide, shaman},
                  defense {total, base, buildings, upgrades, items, itemsMul,
                           citizenHomes, citizenGuardians, watchmen, temp},
                  estimation_today {days, min, max, maxed}, estimation_tomorrow,
                  well_water, newspaper {day: {z, def}} (attack that ended day-1),
                  bank [{id, count, broken}] (broken stacks are separate rows),
                  constructions {bid: {paCurrent, rarityCurrent, resourcesCurrent,
                                       constructionLog [{constructedDay, destructionDay?}],
                                       votingLog [{voteLevel, day}]}}  # = unlocked blueprints
                  last_game_update (ISO, UTC)
    town_maps     one row per zone (absolute x/y), see _parse_zones
    town_citizens citizen_id, name, job, x/y, out, dead, survival_day, death_type,
                  last_update {day, time}
    item_data, construction_data, building_data   catalogues (names, costs)
    town_routes   routes drawn on the Fata map, see _parse_routes
    town_souls    unused

Field meanings checked against the game with players in town 8212:
  human              CP of the citizens in the zone at the last zone update,
                     game-sourced (items and status included). Per zone only.
  building_camped    the ruin's blueprint was taken (camping takes it)
  exc/exc_timestamp  a Scavenger excavated the zone (once per zone; refreshes it)
  scav_zone_level    3 abundant, 2 half empty, 1 almost exhausted, 0 unknown
  scav_radar_reading {zone: 0 replenished | 1 depleted}
  nyv                never visited
  nvt                not seen today. Seen today = zombie state on the map is today's:
                     a citizen passed, or at night the zone held a citizen or lay in
                     the Observation Platform radius (level 0/1/2+ → 3/6/10 km,
                     NightlyHandler + BuildingQueryListener NightlyZoneDiscoveryRadius).
                     Town 8212 day 8, platform level 4: all 474 zones ≤ 10 km seen.
  dried              zone depleted (sent on every zone since 2026-10-16; archived
                     days before that lack it: the scavenger radar stands in)
  building_dried     the ruin is depleted
  town_routes[]      {name, route_day, ap, mode, color, creator (citizen id), editor,
                     source, route [{x, y}, ...] (absolute corners; the first one is
                     the town, straight segments between them), instructions
                     null | {"<step>": text}} (step 1 = first zone after the town)
  km                 rounded Euclidean distance to town, matches geo.km()
                     (676/676 zones, town 8212, 2026-10-16)
"""

from datetime import datetime

from ..utils.clock import GAME_TZ
from .parse import DEATH_TYPES, JOB_NAMES

# /towndata job keys (icon names) → display name; legacy keys stay in JOB_NAMES.
TOWNDATA_JOBS = {
    "shield": "Guardian",
    "dig": "Scavenger",
    "vest": "Scout",
    "book": "Survivalist",
    "tamer": "Tamer",
    "tech": "Technician",
    "shaman": "Shaman",
    "basic": "Resident",
    "none": "Resident",
}

# /towndata item categories → the legacy names bank.py groups by.
ITEM_CATEGORIES = {
    "Miscellaneous": "Misc",
    "Armoury": "Weapon",
    "Food": "Food",
    "Furniture": "Furniture",
    "Containers and boxes": "Box",
    "Resources": "Rsc",
    "Pharmacy": "Drug",
    "Defences": "Armor",
}

SCAV_LEVELS = {1: "almost exhausted", 2: "half empty", 3: "abundant"}


def _name(entry: dict | None, fallback: str) -> str:
    if not entry:
        return fallback
    return entry.get("name_en") or entry.get("name_fr") or fallback


def _game_time(iso: str | None) -> str | None:
    """'2026-10-15T08:57:02+00:00' → '2026-10-15 10:57:02' (game time, like legacy datatime)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(GAME_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso


def is_towndata(raw: dict) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("town_info"), dict)


def build_result(town_id: int, raw: dict, estimation_history: dict | None = None) -> dict:
    """Transform a /towndata response into the standardized result dict.

    estimation_history: {day_str: {min, max, maxed}} for earlier days, from the
    disk archive (this endpoint only carries today's and tomorrow's estimate).
    """
    ti = raw["town_info"]
    day = ti.get("day")
    tx, ty = ti.get("tx", 0), ti.get("ty", 0)
    items = {i["id"]: i for i in raw.get("item_data") or []}
    citizens_raw = raw.get("town_citizens") or []
    names = {c["citizen_id"]: c.get("name") for c in citizens_raw}

    def rel(x, y) -> tuple[int, int]:
        return x - tx, ty - y

    def who(user_id) -> str | None:
        if user_id is None:
            return None
        return names.get(user_id) or f"#{user_id}"

    return {
        "error": None,
        "source": "towndata",
        "meta": {
            "town_name": ti.get("name", "Unknown"),
            "town_id": ti.get("town", town_id),
            "day": day,
            "season": ti.get("season"),
            "region": ti.get("lang"),
            "game_type": ti.get("map_type"),
            "owner": None,
            "data_time": _game_time(ti.get("last_game_update")),
            "chaos": bool(ti.get("chaos")),
            "devastated": bool(ti.get("devast")),
            "hardcore": bool(ti.get("hard")),
            "map_zones": len(raw.get("town_maps") or []),  # town zone included
            "map_bounds": _map_bounds(len(raw.get("town_maps") or []), rel),
        },
        "defense": _parse_defense(ti.get("defense") or {}),
        "water": {"well": ti.get("well_water"), "bank": _bank_water(ti.get("bank") or [])},
        "gate": "open" if ti.get("door") else "closed",
        "estimations": _parse_estimations(ti, estimation_history),
        "attacks": _parse_newspaper(ti.get("newspaper")),
        "citizens": _parse_citizens(citizens_raw, ti.get("roles") or {}, rel),
        "deaths": _parse_deaths(citizens_raw, rel),
        "bank": _parse_bank(ti.get("bank") or [], items),
        "buildings": _parse_buildings(ti.get("constructions") or {}, raw.get("construction_data") or [], items,
                                      hardcore=bool(ti.get("hard"))),
        "scout": _parse_scout(raw.get("town_maps") or [], rel, who),
        "zones": _parse_zones(raw.get("town_maps") or [], items, raw.get("building_data") or [], rel, who, day),
        "routes": _parse_routes(raw.get("town_routes") or [], rel, who),
    }


def _map_bounds(zones: int, rel) -> tuple[int, int, int, int] | None:
    """(xmin, xmax, ymin, ymax), town-relative, of the square map (729 zones = 27 × 27)."""
    size = int(zones ** 0.5 + 0.5)
    if size < 2 or size * size != zones:
        return None
    xa, ya = rel(0, 0)
    xb, yb = rel(size - 1, size - 1)
    return min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)


def _parse_defense(d: dict) -> dict:
    """Map to the legacy keys the formatters use; watchmen/temp are what legacy lumped into 'other'."""
    out = {
        "total": d.get("total", 0),
        "base": d.get("base", 0),
        "buildings": d.get("buildings", 0),
        "upgrades": d.get("upgrades", 0),
        "items": d.get("items", 0),
        "multiplier": d.get("itemsMul", 1),
        "guardians": d.get("citizenGuardians", 0),
        "homes": d.get("citizenHomes", 0),
        "watchmen": d.get("watchmen", 0),
        "temporary": d.get("temp", 0),
    }
    known = sum(out[k] for k in ("base", "buildings", "upgrades", "items", "guardians", "homes"))
    out["other"] = out["total"] - known
    return out


def _bank_water(bank: list[dict]) -> int:
    return sum(b.get("count", 0) for b in bank if b.get("id") == 1 and not b.get("broken"))


def _est(e) -> dict:
    if not isinstance(e, dict) or e.get("min") is None:
        return {}
    return {"min": e.get("min"), "max": e.get("max"), "maxed": int(bool(e.get("maxed")))}


def _parse_estimations(ti: dict, history: dict | None) -> dict:
    today = _est(ti.get("estimation_today"))
    tomorrow = _est(ti.get("estimation_tomorrow"))
    hist = dict(history or {})
    day = ti.get("day")
    if today and day is not None:
        hist[str(day)] = today
    if tomorrow and day is not None:
        hist[str(day + 1)] = tomorrow
    return {"today": today, "tomorrow": tomorrow, "history": hist}


def _parse_newspaper(news) -> dict:
    """{night's day: {zombies, defense}} — newspaper of day d reports the attack that ended day d-1."""
    if not isinstance(news, dict):
        return {}
    out = {}
    for d, v in news.items():
        try:
            if v.get("z") is not None:
                out[int(d) - 1] = {"zombies": v["z"], "defense": v.get("def")}
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def _job(key: str) -> str:
    return TOWNDATA_JOBS.get(key) or JOB_NAMES.get(key) or key or "unknown"


def _parse_citizens(raw: list[dict], roles: dict, rel) -> list[dict]:
    shaman_id = roles.get("shaman")
    guide_id = roles.get("guide")
    citizens = []
    for c in raw:
        if c.get("dead"):
            continue
        rx, ry = rel(c.get("x", 0), c.get("y", 0))
        lu = c.get("last_update") or {}
        citizens.append({
            "id": c["citizen_id"],
            "name": c.get("name", "Unknown"),
            "job": _job(c.get("job", "")),
            "coords": f"[{rx}|{ry}]",
            "inside_town": rx == 0 and ry == 0 and not c.get("out"),
            "is_shaman": c["citizen_id"] == shaman_id,
            "is_guide": c["citizen_id"] == guide_id,
            "last_update_day": lu.get("day"),
            "last_update_time": lu.get("time"),
        })
    citizens.sort(key=lambda c: c["name"].lower())
    return citizens


def _parse_deaths(raw: list[dict], rel) -> list[dict]:
    """survival_day = nights survived, so the death belongs to game day survival_day + 1
    (same as the legacy cadavers[] index + 1)."""
    deaths = []
    for c in raw:
        if not c.get("dead"):
            continue
        rx, ry = rel(c.get("x", 0), c.get("y", 0))
        dtype = c.get("death_type")
        deaths.append({
            "name": c.get("name", "Unknown"),
            "cause": DEATH_TYPES.get(dtype, f"Unknown ({dtype})"),
            "last_coords": f"[{rx}|{ry}]",
            "day": (c.get("survival_day") or 0) + 1,
        })
    deaths.sort(key=lambda d: d["day"], reverse=True)
    return deaths


def _item_fields(item_id: int, items: dict) -> dict:
    d = items.get(item_id) or {}
    return {
        "name": _name(d, f"Item #{item_id}"),
        "uid": d.get("uid"),
        "category": ITEM_CATEGORIES.get(d.get("cat"), d.get("cat") or "Unknown"),
        "heavy": bool(d.get("heavy")),
        "guard": bool(d.get("guard")),
        "deco": bool(d.get("deco")),
    }


def _parse_bank(raw: list[dict], items: dict) -> list[dict]:
    bank = []
    for b in raw:
        if not b.get("count"):
            continue
        bank.append({
            "id": b["id"],
            "count": b["count"],
            "broken": 1 if b.get("broken") else 0,
            **_item_fields(b["id"], items),
        })
    bank.sort(key=lambda i: (i["name"].lower(), i["broken"]))
    return bank


RUINS = ("bunker", "hotel", "hospital")


def _parse_buildings(constructions: dict, catalogue: list[dict], items: dict, *,
                     hardcore: bool = False) -> list[dict]:
    """One entry per catalogue building. A key in `constructions` = blueprint unlocked here.

    ruin_pools: the explorable ruins whose blueprints can unlock it, from the catalogue's
    {bunker,hotel,hospital}_{normal,hardcore} flags (= rules.yml plan_limits lists;
    hardcore towns use other lists). The tier is the building's rarity.

    constructionLog is per day: a building is built when its last entry has no
    destructionDay (temporary buildings get one the night they fall).
    votingLog: one entry per upgrade vote, voteLevel = level reached that day.
    """
    buildings = []
    for c in catalogue:
        bid = str(c["id"])
        con = constructions.get(bid)
        log = (con or {}).get("constructionLog") or []
        built = bool(log) and not log[-1].get("destructionDay")
        votes = (con or {}).get("votingLog")
        upgrade_days = {v["day"]: v["voteLevel"] for v in votes or [] if "day" in v and "voteLevel" in v} or None
        if votes is None:
            level = None
        else:
            level = max(upgrade_days.values()) if upgrade_days else 0

        if con is not None:
            ap_cost = con.get("paCurrent", c.get("ap", 0))
            rarity = con.get("rarityCurrent", c.get("rarity", 0))
            resources = [
                {"name": _name(items.get((r.get("rsc") or {}).get("id")), "?"), "amount": r.get("amount", 1)}
                for r in con.get("resourcesCurrent") or []
            ]
        else:
            ap_cost = c.get("ap", 0)
            rarity = c.get("rarity", 0)
            resources = [{"name": _name(items.get(r.get("id")), "?"), "amount": r.get("amount", 1)}
                         for r in c.get("ressources") or []]

        parent = c.get("parent")
        buildings.append({
            "id": bid,
            "name": _name(c, f"Building {bid}"),
            "defense": c.get("def", 0),
            "ap_cost": ap_cost,
            "temporary": bool(c.get("temporary")),
            "built": built,
            "level": level,
            "built_day": log[-1].get("constructedDay") if log else None,
            "construction_log": log,
            "upgrade_days": upgrade_days,
            "rarity": int(rarity or 0),
            "blueprint_found": con is not None,
            "parent_id": str(parent) if parent else None,
            "ruin_pools": [r for r in RUINS if c.get(f"{r}_{'hardcore' if hardcore else 'normal'}")],
            "resources": resources,
        })

    built_ids = {b["id"] for b in buildings if b["built"]}
    id_to_name = {b["id"]: b["name"] for b in buildings}
    for b in buildings:
        pid = b["parent_id"]
        if pid and pid != "0":
            b["parent_name"] = id_to_name.get(pid)
            b["parent_built"] = pid in built_ids
        else:
            b["parent_name"] = None
            b["parent_built"] = True
    return buildings


def _parse_scout(maps: list[dict], rel, who) -> list[dict]:
    """Scout radar readings (zombie estimates), one per zone that has one."""
    out = []
    for m in maps:
        upd = m.get("scout_last_update")
        if not upd:
            continue
        rx, ry = rel(m["x"], m["y"])
        out.append({
            "coords": f"[{rx}|{ry}]",
            "zombies": int(m.get("scout_zombies") or 0),
            "scouted_by": who(upd.get("user")) or "Unknown",
            "scouted_day": upd.get("day"),
        })
    return out


def expand_route(corners: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Every zone walked between corners (the first one excluded), one move at a time:
    straight segments (Fata's corners are axis-aligned); a diagonal pair walks x first,
    then y, since a move changes one coordinate."""
    path = []
    x, y = corners[0]
    for nx, ny in corners[1:]:
        while x != nx:
            x += (nx > x) - (nx < x)
            path.append((x, y))
        while y != ny:
            y += (ny > y) - (ny < y)
            path.append((x, y))
    return path


def _parse_routes(routes: list[dict], rel, who) -> list[dict]:
    """Routes drawn on Fata's map. Per route: name, day, ap, creator, waypoints (relative
    corners, the town first), path (every zone step by step, relative, the town at the start
    left out) and instructions {step: text} (step 1 = path[0])."""
    out = []
    for r in routes:
        corners = [(p["x"], p["y"]) for p in r.get("route") or [] if "x" in p and "y" in p]
        if len(corners) < 2:
            continue
        ins = {}
        for k, v in (r.get("instructions") or {}).items():
            try:
                ins[int(k)] = v
            except (TypeError, ValueError):
                continue
        out.append({
            "name": r.get("name") or "?",
            "day": r.get("route_day"),
            "ap": r.get("ap"),
            "creator": who(r.get("creator")),
            "waypoints": [rel(x, y) for x, y in corners],
            "path": [rel(x, y) for x, y in expand_route(corners)],
            "instructions": ins,
        })
    return out


def _parse_zones(maps: list[dict], items: dict, ruin_types: list[dict], rel, who,
                 current_day: int | None) -> list[dict]:
    """Visited zones (never-visited ones are skipped, like the legacy map).

    Zombie fields (same rules as the legacy parser):
      zombies      count at the last zone update; -1 = no update (or 0 with
                   danger > 0, which is ambiguous) → fall back to danger
      max_zombies  day's maximum; 0 is also the default, so only trusted when > 0
                   or when the zone was updated today
      danger       0 none, 1 = 1-2, 2 = 3-5, 3 = 6+
    """
    ruins = {r["id"]: r for r in ruin_types}
    zones = []
    for m in maps:
        if m.get("nyv"):
            continue
        rx, ry = rel(m["x"], m["y"])
        upd = m.get("zone_update") or {}

        zone_items = [
            {**_item_fields(i["id"], items), "count": i.get("count", 0),
             "broken": 1 if i.get("broken") else 0}
            for i in m.get("items") or []
        ]

        ruin = None
        btype = m.get("building_type") or 0
        if btype:
            ruin = {
                "name": _name(ruins.get(btype), "Unknown ruin"),
                "type_id": btype,
                "digs_remaining": int(m.get("building_digs") or 0),
                "blueprint_available": btype > 0 and not m.get("building_camped"),
                "dried": int(bool(m.get("building_dried"))),
            }

        danger = int(m.get("danger") or 0)
        observed = bool(upd)
        z = int(m.get("zombies") or 0)
        if not observed or (z == 0 and danger > 0):
            z = -1
        # Seen today but not updated today (earlier, or never): `danger` is today's
        # estimate (the platform radius, see nvt above) and `zombies` is a 0
        # placeholder. Town 8212 day 8: 277 such zones with zombies 0, 14 with
        # danger 1–3; 28 of them never had a zone update at all.
        danger_today = not m.get("nvt") and upd.get("day") != current_day
        zmax = int(m.get("max_zombies") or 0)
        if not (zmax > 0 or (observed and upd.get("day") == current_day)):
            zmax = None

        radar = m.get("scav_radar_reading")
        radar_upd = m.get("scav_radar_last_update") or {}
        radar_state = None
        if isinstance(radar, dict) and "zone" in radar:
            radar_state = "depleted" if radar["zone"] else "replenished"
        exc_ts = m.get("exc_timestamp") or {}
        # Depleted: the latest of three readings wins. `dried` is the zone's state
        # at its last zone update (absent in archived days from before Fata sent
        # it); the scavenger radar reads it later from afar; an excavation
        # replenishes it. Town 8212 (2026-10-16): `dried` marks 155 zones, the
        # radar alone caught 34; 5 zones were dried at their update (days 4–7) and
        # replenished on a radar reading of day 7–8, e.g. [-1|3].
        readings = []
        if "dried" in m:
            readings.append((upd.get("time") or 0, bool(m["dried"])))
        if radar_state:
            readings.append((radar_upd.get("time") or 0, radar_state == "depleted"))
        if m.get("exc"):
            readings.append((exc_ts.get("time") or 0, False))
        dried = max(readings, key=lambda r: r[0])[1] if readings else False

        scav = m.get("scav_zone_level") or 0
        zones.append({
            "coords": f"[{rx}|{ry}]",
            "zombies": z,
            "zombies_max": zmax,
            "danger": danger,
            "dried": int(dried),
            "tag": None,
            "items": zone_items,
            "ruin": ruin,
            "updated_by": who(upd.get("user")),
            "updated_day": upd.get("day"),
            "updated_on": upd.get("time"),
            "cp": int(m.get("human") or 0) if observed else None,
            "seen_today": not m.get("nvt"),
            "danger_today": danger_today,
            "excavated": bool(m.get("exc")),
            "excavated_day": exc_ts.get("day"),
            "scav_level": SCAV_LEVELS.get(scav) if scav else None,
            "scav_radar": radar_state,
            "scav_radar_day": radar_upd.get("day"),
        })
    return zones
