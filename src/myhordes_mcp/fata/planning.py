"""Construction planning: build options ranked by efficiency, and build history.

Deterministic numbers for the build-plan and building-report skills, so the
model reasons over a ranked list instead of doing arithmetic.
"""

from .bank import _CLEAN_WATER, _sum_items
from .buildings import PRIVATE_TOWN_BUILDINGS
from ..utils.clock import data_updated

# Daily AP of one citizen used for town budgets (6 AP base + food/water/drugs).
AP_PER_CITIZEN = 18
# Share of the town's daily AP that usually goes to construction.
CONSTRUCTION_SHARE = 0.20
AP_SOFT_CAP = 240
AP_HARD_CAP = 300

WATER_RATIO_CRITICAL = 2.0
DEFENSIVE_FOCUS = "Defensive Focus"
DEFENSE_ITEM_THRESHOLD = 40  # Armor-category items in bank that make the multiplier worth it

# Buildings that add water to the well (knowledge/tactics/buildings-cheatsheet.md).
WATER_PRODUCERS = {
    "Pump", "Drilling Rig", "Eden Project", "Divining Rocket",
    "Mechanical Pump", "Divining Rods", "No Holes Barred",
}
WATER_FILTERS = {"Water Purifier", "Water Filter"}
JERRYCAN = "Full Jerrycan"
JERRYCANS_FOR_FILTER = 10

WATER_RATION = "Water Ration"
NUTS_AND_BOLTS = "Handful of nuts and bolts"


def _bank_counts(bank: list[dict]) -> dict[str, int]:
    """Usable count per item name. Broken items cannot be used as resources."""
    counts: dict[str, int] = {}
    for item in bank:
        if not item.get("broken"):
            counts[item["name"]] = counts.get(item["name"], 0) + item["count"]
    return counts


def _ratio(defense: int, cost: int) -> float | None:
    return round(defense / cost, 2) if defense and cost else None


def _option(b: dict, have: dict[str, int]) -> dict:
    """Score one unbuilt building against the bank."""
    res = b.get("resources") or []
    short = [(r["name"], have.get(r["name"], 0), r["amount"]) for r in res
             if have.get(r["name"], 0) < r["amount"]]
    need = {r["name"]: r["amount"] for r in res}
    # Heaviest draw on the bank: the resource this build uses the biggest share of.
    draw = None
    for name, amount in need.items():
        stock = have.get(name, 0)
        if stock:
            share = amount / stock
            if draw is None or share > draw[3]:
                draw = (name, amount, stock, share)
    return {
        "name": b["name"],
        "ap": b["ap_cost"],
        "defense": b["defense"],
        "temporary": bool(b["temporary"]),
        "resources": res,
        "short": short,
        "ready": not short,
        "def_per_ap": _ratio(b["defense"], b["ap_cost"]),
        "def_per_water": _ratio(b["defense"], need.get(WATER_RATION, 0)),
        "def_per_hnb": _ratio(b["defense"], need.get(NUTS_AND_BOLTS, 0)),
        "heaviest_draw": draw,
        "water_producer": b["name"] in WATER_PRODUCERS,
    }


def build_options(data: dict, include_private: bool = False) -> dict:
    """Compute the situation and every buildable option. See format_build_options."""
    meta = data["meta"]
    bank = data["bank"]
    have = _bank_counts(bank)
    buildings = data["buildings"]
    if not include_private:
        buildings = [b for b in buildings if b["name"] not in PRIVATE_TOWN_BUILDINGS]
    by_id = {b["id"]: b for b in buildings}

    def buildable(b: dict) -> bool:
        return (not b["built"] and b.get("parent_built", True)
                and (b.get("rarity", 0) == 0 or b.get("blueprint_found")))

    options = [_option(b, have) for b in buildings if buildable(b)]
    buildable_ids = {b["id"] for b in buildings if buildable(b)}

    # One step of prerequisite chaining: locked buildings whose parent is buildable now.
    chains = []
    for b in buildings:
        if b["built"] or b.get("parent_built", True):
            continue
        if b.get("rarity", 0) > 0 and not b.get("blueprint_found"):
            continue
        parent = by_id.get(b.get("parent_id"))
        if parent is None or parent["id"] not in buildable_ids:
            continue
        # Only chains worth planning around: defense, water, or the multiplier.
        if not (b["defense"] or b["name"] in WATER_PRODUCERS or b["name"] == DEFENSIVE_FOCUS):
            continue
        opt = _option(b, have)
        opt["after"] = parent["name"]
        opt["chain_ap"] = b["ap_cost"] + parent["ap_cost"]
        opt["chain_def"] = b["defense"] + parent["defense"]
        chains.append(opt)

    alive = len(data["citizens"])
    water, _ = _sum_items(bank, _CLEAN_WATER)
    armor = sum(i["count"] for i in bank if i.get("category") == "Armor")
    focus = next((b for b in data["buildings"] if b["name"] == DEFENSIVE_FOCUS), None)
    est = data["estimations"].get("today", {})
    total_def = data["defense"].get("total")
    est_max = est.get("max")

    return {
        "town": meta.get("town_name"),
        "day": meta.get("day"),
        "data_time": meta.get("data_time"),
        "alive": alive,
        "defense": total_def,
        "estimate": est,
        "buffer": (total_def - est_max) if (total_def is not None and est_max is not None) else None,
        "water_bank": water,
        "water_well": data["water"].get("well"),
        "water_ratio": round(water / alive, 2) if alive else None,
        "town_ap": alive * AP_PER_CITIZEN,
        "construction_ap": round(alive * AP_PER_CITIZEN * CONSTRUCTION_SHARE),
        "armor_items": armor,
        "focus_built": bool(focus and focus["built"]),
        "focus_buildable": bool(focus and buildable(focus)),
        "focus_parent": focus.get("parent_name") if focus else None,
        "jerrycans": have.get(JERRYCAN, 0),
        "options": options,
        "chains": chains,
    }


def _res_text(o: dict) -> str:
    if not o["resources"]:
        return "no resources"
    return ", ".join(f"{r['name']} {r['amount']}" for r in o["resources"])


def _option_line(o: dict) -> str:
    bits = [f"{o['ap']} AP"]
    if o["defense"]:
        bits.append(f"+{o['defense']} def")
    ratios = []
    for key, label in (("def_per_ap", "def/AP"), ("def_per_water", "def/water"), ("def_per_hnb", "def/HNB")):
        if o[key] is not None:
            ratios.append(f"{label} {o[key]:g}")
    if ratios:
        bits.append(" · ".join(ratios))
    if o["ready"]:
        status = "✓ ready"
        if o["heaviest_draw"] and o["heaviest_draw"][3] >= 0.5:
            name, need, stock, share = o["heaviest_draw"]
            status += f" (uses {need}/{stock} {name}, {share:.0%})"
    else:
        status = "⚠ short: " + ", ".join(f"{n} {h}/{need}" for n, h, need in o["short"])
    line = f"  {o['name']} — " + ", ".join(bits) + f" — {status}"
    if "after" in o:
        line += f" — after {o['after']} (chain {o['chain_ap']} AP, +{o['chain_def']} def)"
    return line


TOP_PER_GROUP = 8  # options shown per group unless include_all
# Always shown: the Situation block points at them (multipliers, water filters).
ALWAYS_SHOWN = {DEFENSIVE_FOCUS, "Defensive Adjustment", "Garbage Dump"} | WATER_FILTERS  # Dump: S19 meta


def format_build_options(data: dict, include_resources: bool = False, include_all: bool = False) -> str:
    """Ranked construction options for the current town, with the numbers a
    build plan needs: defense buffer, water ratio, AP budget, multiplier gap,
    and per-building efficiency ratios and bank availability."""
    if data.get("error"):
        return f"Error: {data['error']}"
    p = build_options(data)
    est = p["estimate"]
    est_txt = f"{est.get('min')}–{est.get('max')}" if est.get("min") is not None else "unknown"
    est_txt += " (confirmed)" if est.get("maxed") else (" (partial)" if est.get("min") is not None else "")
    lines = [
        f"## Build options — {p['town']} Day {p['day']}",
        data_updated(data["meta"]),
        "",
        "### Situation",
    ]
    buf = p["buffer"]
    lines.append(f"  Defense {p['defense']} vs tonight {est_txt}"
                 + (f" → buffer {buf:+d}" + (" ⚠ NEGATIVE" if buf < 0 else "") if buf is not None else ""))
    ratio = p["water_ratio"]
    wflag = " ⚠ below 2.0 — water builds first" if ratio is not None and ratio < WATER_RATIO_CRITICAL else ""
    lines.append(f"  Water: {p['water_bank']} clean in bank for {p['alive']} alive = {ratio}/citizen{wflag} · well {p['water_well']}")
    lines.append(f"  AP: town ≈ {p['town_ap']}/day ({AP_PER_CITIZEN}×alive); construction share "
                 f"{CONSTRUCTION_SHARE:.0%} ≈ {p['construction_ap']} AP · plan caps: soft {AP_SOFT_CAP}, hard {AP_HARD_CAP}")
    if p["focus_built"]:
        lines.append(f"  {DEFENSIVE_FOCUS}: built")
    else:
        gap = p["armor_items"] >= DEFENSE_ITEM_THRESHOLD
        where = ("buildable now" if p["focus_buildable"]
                 else f"needs {p['focus_parent']} first" if p["focus_parent"] else "not buildable yet")
        lines.append(f"  {DEFENSIVE_FOCUS}: not built, {where} · {p['armor_items']} defense items in bank"
                     + (f" ≥{DEFENSE_ITEM_THRESHOLD} → multiplier gap, highest-leverage build" if gap else ""))
    if p["jerrycans"] >= JERRYCANS_FOR_FILTER:
        lines.append(f"  {p['jerrycans']} {JERRYCAN} in bank → water filter/purifier worth it")
    lines.append("")

    opts = p["options"]
    groups = [
        ("Water producers", [o for o in opts if o["water_producer"]], lambda o: o["ap"]),
        ("Defense — permanent (best def/AP first)",
         [o for o in opts if o["defense"] and not o["temporary"] and not o["water_producer"]],
         lambda o: -(o["def_per_ap"] or 0)),
        ("Defense — temporary (lost after the attack)",
         [o for o in opts if o["defense"] and o["temporary"]], lambda o: -(o["def_per_ap"] or 0)),
        ("Utility — no defense", [o for o in opts if not o["defense"] and not o["water_producer"]],
         lambda o: o["ap"]),
    ]
    for title, items, key in groups:
        if not items:
            continue
        ready = sum(o["ready"] for o in items)
        lines.append(f"### {title} — {len(items)} buildable, {ready} with resources in bank")
        ranked = sorted(items, key=key)
        shown = ranked if include_all else (ranked[:TOP_PER_GROUP]
                                            + [o for o in ranked[TOP_PER_GROUP:] if o["name"] in ALWAYS_SHOWN])
        for o in shown:
            lines.append(_option_line(o))
            if include_resources:
                lines.append(f"      needs: {_res_text(o)}")
        if len(ranked) > len(shown):
            hidden = [o for o in ranked if o not in shown]
            lines.append(f"  +{len(hidden)} more ({sum(o['ready'] for o in hidden)} ready): "
                         + ", ".join(o["name"] for o in hidden) + " — include_all=True for their numbers")
        lines.append("")

    if p["chains"]:
        lines.append("### Next step — defense/water/multiplier unlocked by a buildable prerequisite")
        for o in sorted(p["chains"], key=lambda o: -(o["chain_def"] / o["chain_ap"] if o["chain_ap"] else 0)):
            lines.append(_option_line(o))
            if include_resources:
                lines.append(f"      needs: {_res_text(o)}")
        lines.append("")

    lines.append("Blueprint-locked buildings are omitted. Ratios: defense per AP / per water ration / per "
                 "nuts-and-bolts used. 'uses X/Y' flags builds taking ≥50% of a resource's bank stock.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Construction history
# ---------------------------------------------------------------------------

def _gh_series(gh: dict | None) -> dict:
    """Per-day series from Gest'Hordes stats (lists indexed by day)."""
    if not gh or "error" in gh:
        return {}
    atk = gh.get("data", {}).get("stats", {}).get("atk", {})
    return {
        "attack": atk.get("attaque_jour", []),
        "est_min": atk.get("min_estim", []),
        "est_max": atk.get("max_estim", []),
    }


def _at(lst: list, i: int):
    return lst[i] if 0 <= i < len(lst) else None


def deaths_by_day(data: dict) -> dict[int, int]:
    """Deaths per game day (a death's day is the day whose attack/end it happened on)."""
    out: dict[int, int] = {}
    for d in data["deaths"]:
        out[d["day"]] = out.get(d["day"], 0) + 1
    return out


def alive_by_day(data: dict) -> dict[int, int | None]:
    """Citizens alive at the start of each day, walking back from today's count.
    A finished town has no citizens and no cadavers left in Fata: None then."""
    current = data["meta"].get("day") or 0
    deaths = deaths_by_day(data)
    alive: dict[int, int | None] = {current: len(data["citizens"]) or None}
    for day in range(current - 1, 0, -1):
        nxt = alive[day + 1]
        alive[day] = nxt + deaths.get(day, 0) if nxt is not None else None
    return alive


def construction_history(data: dict, gh: dict | None = None) -> list[dict]:
    """One row per game day: paid builds with AP, free vote upgrades, alive at
    day start, AP budget, share used and the night's attack."""
    meta = data["meta"]
    current = meta.get("day") or 0
    built = [b for b in data["buildings"] if b["built"]]

    builds: dict[int, list] = {}
    upgrades: dict[int, list] = {}
    for b in built:
        if b.get("built_day") is not None:
            builds.setdefault(int(b["built_day"]), []).append(b)
        for day, level in (b.get("upgrade_days") or {}).items():
            upgrades.setdefault(int(day), []).append((b["name"], level - 1, level))

    night_deaths = deaths_by_day(data)
    alive = alive_by_day(data)

    series = _gh_series(gh)
    rows = []
    first = min([*builds, *upgrades, current]) if (builds or upgrades) else current
    for day in range(max(1, first), current + 1):
        paid = sorted(builds.get(day, []), key=lambda b: b["name"].lower())
        ap = sum(b["ap_cost"] for b in paid)
        budget = alive[day] * AP_PER_CITIZEN if alive[day] is not None else None
        attack = _at(series.get("attack", []), day)
        if attack is None:  # Fata's newspaper: the attack that ended this day
            attack = (data.get("attacks") or {}).get(day, {}).get("zombies")
        est = (_at(series.get("est_min", []), day), _at(series.get("est_max", []), day))
        rows.append({
            "day": day,
            "builds": [(b["name"], b["ap_cost"], b["defense"]) for b in paid],
            "upgrades": sorted(upgrades.get(day, [])),
            "ap": ap,
            "alive": alive[day],
            "budget": budget,
            "share": round(100 * ap / budget) if budget else None,
            "attack": attack,
            "estimate": est if est[0] is not None else None,
            "deaths": night_deaths.get(day, 0),
        })
    return rows


def format_construction_history(data: dict, gh: dict | None = None) -> str:
    """Day-by-day construction throughput table."""
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    rows = construction_history(data, gh)
    lines = [
        f"## Construction history — {meta.get('town_name')} Day {meta.get('day')}",
        data_updated(meta) + f" · budget = {AP_PER_CITIZEN} AP × citizens alive at day start",
        "",
        f"{'Day':<4} {'AP':>4} {'Budget':>7} {'%':>4} {'Alive':>5} {'Attack':>11} {'Deaths':>6}  Paid builds",
    ]
    for r in rows:
        if r["attack"] is not None:
            atk = str(r["attack"])
        elif r["estimate"]:
            atk = f"~{r['estimate'][0]}-{r['estimate'][1]}"
        else:
            atk = "—"
        if r["day"] == meta.get("day"):
            atk += "*"
        builds = " · ".join(f"{n} ({ap})" for n, ap, _ in r["builds"]) or "—"
        share = f"{r['share']}%" if r["share"] is not None else "—"
        budget = r["budget"] if r["budget"] is not None else "?"
        alive = r["alive"] if r["alive"] is not None else "?"
        lines.append(f"D{r['day']:<3} {r['ap']:>4} {budget:>7} {share:>4} {alive:>5} {atk:>11} {r['deaths']:>6}  {builds}")
    lines.append("")
    total = sum(r["ap"] for r in rows)
    lines.append(f"Total paid AP: {total} over {len(rows)} days. * = tonight (estimate, attack not happened yet).")
    ups = [(r["day"], u) for r in rows for u in r["upgrades"]]
    if ups:
        lines.append("")
        per_day = []
        for day in sorted({d for d, _ in ups}):
            items = ", ".join(f"{n} Lv.{a}→{b}" for d, (n, a, b) in ups if d == day)
            per_day.append(f"D{day} {items}")
        lines.append("Free vote upgrades (not counted in AP): " + " · ".join(per_day))
    if rows and rows[-1]["alive"] is None:
        lines.append("Alive/budget unknown: Fata has no citizen or death data left for this town (finished?).")
    if (not gh or "error" in (gh or {})) and not data.get("attacks"):
        lines.append("")
        lines.append("Attack column empty: Gest'Hordes data unavailable.")
    return "\n".join(lines)
