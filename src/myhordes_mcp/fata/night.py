"""Night report: what the attack at the end of a game day did.

Deterministic facts for the close-day skill: deaths with cause and last
position, defense vs the attack, alive before/after.
"""

from ..gesthordes.format import at_day, atk_series
from ..utils.clock import data_updated
from ..utils.fmt import town_name
from .geo import TOWN, fmt_xy
from .planning import alive_by_day

TOWN_COORDS = fmt_xy(TOWN)


def _gh_deaths(gh: dict | None, day: int) -> int | None:
    """Gest'Hordes death count for the night of `day`, to cross-check Fata's cadavers."""
    # morts_reels puts day N at index N-1 (checked against Fata cadavers on towns 8212 and 7493).
    return at_day(atk_series(gh), "morts_reels", day, -1)


def night_report(data: dict, day: int, gh: dict | None = None, day_data: dict | None = None) -> dict:
    """Facts about the night at the end of `day`. day_data: Fata page of that day
    (defense and estimate as they stood then), optional."""
    current = data["meta"].get("day") or 0
    alive = alive_by_day(data)
    deaths = [d for d in data["deaths"] if d["day"] == day]
    paper = (data.get("attacks") or {}).get(day) or {}
    defense = paper.get("defense")
    if defense is None and day_data and not day_data.get("error"):
        defense = day_data["defense"].get("total")
    estimate = None
    if day_data and not day_data.get("error"):
        est = day_data["estimations"].get("today", {})
        if est.get("min") is not None:
            estimate = (est["min"], est["max"], bool(est.get("maxed")))
    return {
        "day": day,
        "closed": day < current,
        "deaths": [{**d, "outside": d["last_coords"] != TOWN_COORDS} for d in deaths],
        "alive_before": alive.get(day),
        "alive_after": alive.get(day + 1),
        "defense": defense,
        "attack": paper.get("zombies"),
        "estimate": estimate,
        "gh_deaths": _gh_deaths(gh, day),
    }


def format_night_report(data: dict, day: int, gh: dict | None = None, day_data: dict | None = None) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    r = night_report(data, day, gh, day_data)
    meta = data["meta"]
    if not r["closed"]:
        return (f"Day {day} has not ended yet (town is on day {meta.get('day')}). "
                "Night reports cover days whose attack already happened.")
    lines = [f"## Night report — {town_name(meta)}, night of Day {day} → Day {day + 1}", data_updated(meta)]
    town_alive = (r["alive_after"] or 0) > 0
    lines.append(f"Result: {'SURVIVED' if town_alive else 'FAILED (no citizens left)' if r['alive_after'] == 0 else 'unknown'}")
    d, a = r["defense"], r["attack"]
    vs = f"Defense {d if d is not None else '?'} vs attack {a if a is not None else '?'}"
    if d is not None and a is not None:
        vs += f" (margin {d - a:+d})"
    if r["estimate"]:
        lo, hi, conf = r["estimate"]
        vs += f" · estimate was {lo}–{hi}{' (confirmed)' if conf else ''}"
    lines.append(vs)
    before, after = r["alive_before"], r["alive_after"]
    if before is not None and after is not None:
        lines.append(f"Alive: {before} at day start → {after} next morning ({len(r['deaths'])} died on day {day})")
    lines.append("")
    if r["deaths"]:
        lines.append(f"### Deaths ({len(r['deaths'])})")
        for x in r["deaths"]:
            where = "IN TOWN" if not x["outside"] else f"{x['last_coords']} (outside — camping or stranded)"
            lines.append(f"  {x['name']} — {x['cause']} — last at {where}")
    else:
        lines.append("No deaths recorded by Fata for this day.")
    if r["gh_deaths"] is not None and r["gh_deaths"] != len(r["deaths"]):
        lines.append(f"Note: Gest'Hordes counts {r['gh_deaths']} death(s) for this night — check with players.")
    lines.append("")
    lines.append("Sources: Fata only (deaths from cadavers, attack and defense from the town newspaper, else the Fata page of that day); Gest'Hordes only cross-checks the death count.")
    return "\n".join(lines)
