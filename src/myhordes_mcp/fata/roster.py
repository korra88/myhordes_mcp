"""Expedition roster: who is outside, grouped by tile, reconciled with a list.

Deterministic part of the expedition-report skill: distances, scrappers,
tile groups with ruin names, class icons, and the accounting equation
listed + scrappers + unaccounted = outside.
"""

import re

from .risk import _parse_coords

# Forum icons per Fata job display name (parse.JOB_NAMES values).
CLASS_ICONS = {
    "Guardian": ":guard:", "Tamer": ":tamer:", "Scavenger": ":scav:",
    "Technician": ":tech:", "Survivalist": ":surv:", "Scout": ":scout:",
}
SHAMAN_ICON = ":sham:"
UNKNOWN_ICON = ":human:"
SCRAPPER_DISTANCE = 1


def icon(c: dict) -> str:
    if c.get("is_shaman"):
        return SHAMAN_ICON
    return CLASS_ICONS.get(c["job"], UNKNOWN_ICON)


def _norm(name: str) -> str:
    # "@PlayerName:12345" → "playername"
    return re.sub(r"^@", "", name.strip()).split(":")[0].strip().lower()


def parse_listed(listed: str) -> list[str]:
    return [n for n in (x.strip() for x in re.split(r"[,\n;]+", listed)) if n]


def roster(data: dict, listed: list[str] | None = None) -> dict:
    zones = {z["coords"]: z for z in data["zones"]}
    outside = []
    for c in data["citizens"]:
        if c["inside_town"]:
            continue
        x, y = _parse_coords({"coords": c["coords"]}) or (0, 0)
        outside.append({**c, "distance": abs(x) + abs(y), "icon": icon(c)})

    listed = listed or []
    wanted = {_norm(n): n for n in listed}
    on_list = [c for c in outside if _norm(c["name"]) in wanted]
    off_list = [c for c in outside if _norm(c["name"]) not in wanted]
    scrappers = [c for c in off_list if c["distance"] <= SCRAPPER_DISTANCE]
    unaccounted = [c for c in off_list if c["distance"] > SCRAPPER_DISTANCE]

    by_name = {_norm(c["name"]): c for c in data["citizens"]}
    dead = {_norm(d["name"]): d for d in data["deaths"]}
    outside_names = {_norm(c["name"]) for c in outside}
    ghosts = []
    for key, original in wanted.items():
        if key in outside_names:
            continue
        if key in by_name:
            ghosts.append((original, "in town"))
        elif key in dead:
            ghosts.append((original, f"dead (day {dead[key]['day']}, {dead[key]['cause']})"))
        else:
            ghosts.append((original, "not a citizen of this town — check spelling"))

    tiles: dict[str, list] = {}
    for c in outside:
        if c["distance"] > SCRAPPER_DISTANCE:
            tiles.setdefault(c["coords"], []).append(c)
    groups = []
    for coords, people in tiles.items():
        ruin = (zones.get(coords, {}).get("ruin") or {}).get("name")
        groups.append({"coords": coords, "distance": people[0]["distance"], "ruin": ruin,
                       "members": sorted(people, key=lambda c: c["name"].lower())})
    groups.sort(key=lambda g: (-len(g["members"]), g["distance"]))

    return {"outside": outside, "on_list": on_list, "scrappers": scrappers,
            "unaccounted": unaccounted, "ghosts": ghosts, "groups": groups, "has_list": bool(listed)}


def format_roster(data: dict, listed: str = "") -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    r = roster(data, parse_listed(listed))
    lines = [f"## Expedition roster — {meta.get('town_name')} Day {meta.get('day')}",
             f"Data updated: {meta.get('data_time')} · distance = Manhattan (AP from town)", ""]
    n_out = len(r["outside"])
    if r["has_list"]:
        lines.append(f"Accounting: {len(r['on_list'])} listed + {len(r['scrappers'])} scrappers + "
                     f"{len(r['unaccounted'])} unaccounted = {n_out} outside")
        lines.append("")
        if r["unaccounted"]:
            lines.append(f"### Unaccounted — outside, distance ≥2, on no list ({len(r['unaccounted'])})")
            for c in sorted(r["unaccounted"], key=lambda c: -c["distance"]):
                lines.append(f"  {c['icon']} {c['name']} ({c['job']}) {c['coords']} — {c['distance']} AP")
            lines.append("")
        if r["ghosts"]:
            lines.append(f"### Listed but not outside ({len(r['ghosts'])}) — keep their slots unless dead")
            for name, why in r["ghosts"]:
                lines.append(f"  {name} — {why}")
            lines.append("")
    else:
        lines.append(f"{n_out} outside: {len(r['scrappers'])} scrappers (distance 1), "
                     f"{n_out - len(r['scrappers'])} at distance ≥2")
        lines.append("")
    if r["groups"]:
        lines.append("### Outside at distance ≥2, by exact tile")
        for g in r["groups"]:
            ruin = f" — {g['ruin']}" if g["ruin"] else ""
            members = ", ".join(f"{c['icon']} {c['name']}" for c in g["members"])
            lines.append(f"  {g['coords']} ({g['distance']} AP){ruin}: {members}")
        lines.append("")
    if r["scrappers"]:
        tiles = sorted({c["coords"] for c in r["scrappers"]})
        lines.append(f"Scrappers (distance 1, not on list): {len(r['scrappers'])} on {', '.join(tiles)}")
    lines.append("Class icons from live job data; :sham: = elected shaman. Items (bikes, kits) are not visible here.")
    return "\n".join(lines)
