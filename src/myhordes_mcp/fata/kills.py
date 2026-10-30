"""Kill runs: how many zombies a route has to kill, pairs and singles, with which weapons
from the bank, and what to carry to get there and back. Plan: docs/kill-route-plan.md.

Rules from the game source (myhordes-docker v5.0.6: MapMaker::zombieSpawnGovernorMH and
spreadCycleMH, ProcessZoneEffect, ActionDataService fixtures); player-facing version in
knowledge/tactics/weapons.md and opti-town-meta.md (Zombie Zoo).

- Killing is total clean-up. Each night: respawn check, one spread cycle, then Despair
  (floor((killed today in the zone - 1) / 2) more die, applied AFTER the spread, which reads
  the counts before it). A zombie left alive infects the clean zones around it. The planner
  always counts EVERY zombie of every zone on the route.
- A weapon kills min(zombies in the zone, its kills) (ProcessZoneEffect): a 2-kill weapon on
  a zone of 1 wastes the second kill. A zone with n zombies = n // 2 pairs + n % 2 single.
- Nightly growth (risk.zombie_growth): +1 on average, +2 at most per night per zone with
  zombies; an empty zone next to a zone with more grows 1-2 (or 0).
- Weapons (WEAPONS below): using one costs 0 AP, reloading too (also outside). Burning Laser
  Pointer: 2 kills per charge, a Battery loads 4 (50%), 3 (25%) or 2 (25%) charges
  (load_lpointer). Machete: 2 kills, breaks 25% per use (throw_b_cutcut, g_break_25).
  Battery Launcher Mk. II: 1 kill, always empties, 80% to get the Battery back
  (fire_pilegun2). Serrated Knife: 1 kill, breaks 33% (throw_b_knife). Aqua-Splash: 5 shots
  per Water Ration (fill_asplash*); Water Pistol: 3. Repair Kit / Kwik-fix repair a broken
  Machete or Knife for 1 AP (repair_1, repair_2). Melee weapons need AP left and healthy hands.
- Entering a zone with more zombies than the group's CP blocks the group until they are
  killed: out of weapons = stuck.
- A zone never visited holds zombies only by spread from the zones next to it (the day-1
  spawn puts them on ruins and a few free zones, then spreadCycleMH): it is estimated from
  its infected neighbours. A zoo side is cleaned up to the map edge (edge_gap warns).
"""

import math
import re
from dataclasses import dataclass

from .pathing import loop_return
from .geo import MAX_PATH_AP, NEIGHBOURS8, Cell, fmt_xy, in_bounds, map_bounds, xy, zone_map
from .risk import (CP_PER_CITIZEN, DANGER_TOP, GROWTH_AVG, GROWTH_MAX, danger_band, never_visited,
                   respawn_check, respawn_totals, zombie_growth, zone_is_today)
from .towndata import expand_route
from . import supplies
from ..utils.fmt import header
from ..utils.clock import data_updated



# ---------------------------------------------------------------------------
# Zombie counts per zone
# ---------------------------------------------------------------------------

def _est(lo: float, avg: float, hi: float, source: str, **extra) -> dict:
    return {"min": lo, "avg": avg, "max": hi, "source": source, **extra}


def zone_estimate(zone: dict | None, day, zmap: dict[Cell, dict], *, final: bool = False) -> dict:
    """{min, avg, max, source[, killed_today]} zombies in a zone.

    Counted today: exact. Counted on an earlier day: grown by risk.zombie_growth for the
    nights since (an empty zone only if a neighbour had zombies at its last count).
    Only a danger band: its bounds, grown the same way if not today's. Never visited
    (zone None): source "unknown". final: the data is a finished day, so the day's maximum
    (before the kills) is what the zone held."""
    if zone is None:
        return _est(0, 0, 0, "unknown")
    z, zmax = zone.get("zombies", -1), zone.get("zombies_max")
    upd, danger = zone.get("updated_day"), zone.get("danger", 0)
    nights = day - upd if isinstance(day, int) and upd is not None else 0
    if zone.get("danger_today"):
        lo, hi = danger_band(danger, DANGER_TOP)
        return _est(lo, (lo + hi) / 2, hi, f"danger {danger} today" if danger else "clear today")
    if z >= 0 and zone_is_today(zone, day):
        if zmax and zmax > z:
            if final:
                return _est(zmax, zmax, zmax, f"day {day} (max, before kills)")
            return _est(z, z, z, "today", killed_today=zmax - z)
        return _est(z, z, z, "today")
    if z >= 0 and upd is not None and nights > 0:
        src = f"day {upd} (+{nights} night{'s' if nights > 1 else ''})"
        if z > 0:
            return _est(*zombie_growth(z, nights), src)
        x, y = xy(zone)
        near = any(zmap.get((x + dx, y + dy), {}).get("zombies", 0) > 0 for dx, dy in NEIGHBOURS8)
        return _est(0, GROWTH_AVG * nights if near else 0, GROWTH_MAX * nights if near else 0, src)
    if z >= 0:
        return _est(z, z, z, f"day {upd}" if upd is not None else "counted")
    lo, hi = danger_band(danger, DANGER_TOP)
    if danger and nights > 0:
        return _est(lo, (lo + hi) / 2 + GROWTH_AVG * nights, hi + GROWTH_MAX * nights,
                    f"danger {danger} (+{nights} night{'s' if nights > 1 else ''})")
    return _est(lo, (lo + hi) / 2, hi, f"danger {danger}" if danger else "clear (danger 0)")


def unvisited_estimate(cell: Cell, day, zmap: dict[Cell, dict], *, final: bool = False) -> dict:
    """A zone never visited. Zombies only spread to the zones next to them (spreadCycleMH),
    so it is estimated from its known neighbours (8): min 0, avg the mean of the infected
    ones, max the highest of them. No infected neighbour known: source "unknown" (0)."""
    x, y = cell
    near = [zone_estimate(zmap[n], day, zmap, final=final) for dx, dy in NEIGHBOURS8
            if (n := (x + dx, y + dy)) in zmap and n != (0, 0)]
    infected = [e for e in near if e["avg"] > 0]
    if not infected:
        return _est(0, 0, 0, "unknown")
    return _est(0, sum(e["avg"] for e in infected) / len(infected), max(e["max"] for e in infected),
                f"never visited, from {_n(len(infected), 'neighbour')}")


def buckets(n: float) -> tuple[int, int]:
    """(pairs, singles) for n zombies in one zone (n rounded half up)."""
    n = int(n + 0.5)
    return n // 2, n % 2


def _fmt(n: float) -> str:
    return f"{n:.1f}".rstrip("0").rstrip(".")


def _n(n: float, word: str) -> str:
    """'1 pair', '2 pairs'."""
    return f"{_fmt(n)} {word}{'' if n == 1 else 's'}"


def _range(e: dict) -> str:
    if e["min"] == e["max"]:
        return _fmt(e["avg"])
    return f"{_fmt(e['min'])}–{_fmt(e['max'])} (avg {_fmt(e['avg'])})"


def analyse_route(data: dict, path: list[Cell]) -> dict:
    """The zones of `path` (town excluded, each counted once on its first step) that hold
    zombies, the ones never visited with no infected neighbour, and totals (zombies, pairs,
    singles) by min/avg/max. A never-visited zone next to infected ones is a row, estimated
    from them (unvisited_estimate)."""
    day = data["meta"].get("day")
    final = data["meta"].get("live") is False
    zmap = zone_map(data)
    rows, unknown, banded, seen = [], [], [], set()
    for step, cell in enumerate(path, 1):
        if cell == (0, 0) or cell in seen:
            continue
        seen.add(cell)
        est = zone_estimate(zmap[cell], day, zmap, final=final) if cell in zmap \
            else unvisited_estimate(cell, day, zmap, final=final)
        if est["source"] == "unknown":
            unknown.append((step, cell))
        elif final and est["source"].startswith("danger") and est["max"] > 0:
            banded.append((step, cell, est))   # a past day's totals are counts, not bands
        elif est["max"] > 0:
            rows.append({"step": step, "zone": cell, "est": est,
                         "pairs": buckets(est["avg"])[0], "singles": buckets(est["avg"])[1]})
    totals = {}
    for k in ("min", "avg", "max"):
        pb = [buckets(r["est"][k]) for r in rows]
        totals[k] = {"zombies": sum(int(r["est"][k] + 0.5) for r in rows),
                     "pairs": sum(p for p, _ in pb), "singles": sum(s for _, s in pb)}
    return {"rows": rows, "unknown": unknown, "banded": banded, "totals": totals, "zones": len(seen)}


def edge_gap(data: dict, path: list[Cell]) -> str | None:
    """A warning when a strip stops short of the map edge with zombies (or never-visited
    zones) left between its far end and the edge. The strip runs along the longer side of
    the route's box (both on a square), away from town; only the box's width is checked."""
    bounds = map_bounds(data)
    cells = [c for c in path if c != (0, 0)]
    if not bounds or not cells:
        return None
    day = data["meta"].get("day")
    zmap = zone_map(data)
    x0, x1 = min(c[0] for c in cells), max(c[0] for c in cells)
    y0, y1 = min(c[1] for c in cells), max(c[1] for c in cells)
    gaps = []
    for axis, (lo, hi), (blo, bhi), (olo, ohi) in ((1, (y0, y1), (bounds.ymin, bounds.ymax), (x0, x1)),
                                                    (0, (x0, x1), (bounds.xmin, bounds.xmax), (y0, y1))):
        if hi - lo < ohi - olo:
            continue
        for far, edge, step in ((hi, bhi, 1), (lo, blo, -1)):
            if far * step <= 0 or far == edge:   # toward town, or already on the edge
                continue
            zones = [(o, a) if axis == 1 else (a, o)
                     for a in range(far + step, edge + step, step) for o in range(olo, ohi + 1)]
            est = {c: zone_estimate(zmap[c], day, zmap) if c in zmap else unvisited_estimate(c, day, zmap)
                   for c in zones}
            bad = [c for c in zones if est[c]["max"] > 0 or c not in zmap]
            if bad:
                gaps.append((("y" if axis == 1 else "x"), far, edge, bad, est))
    if not gaps:
        return None
    parts = []
    for name, far, edge, bad, est in gaps:
        unseen = [c for c in bad if c not in zmap]
        lo, avg, hi = (sum(est[c][k] for c in bad) for k in ("min", "avg", "max"))
        parts.append(f"from {name}={far} to the edge {name}={edge}: {_n(len(bad), 'zone')} with zombies or "
                     f"never visited, ~{_fmt(avg)} zombies ({_fmt(lo)}–{_fmt(hi)})"
                     + (f", {len(unseen)} never visited" if unseen else "") + f": {_zones_text(bad)}")
    return ("**Stops short of the map edge** " + "; ".join(parts) + ". A zoo side or strip is cleaned "
            "up to the edge (zombies left there spread back tonight): extend the waypoints to the edge; "
            "if AP or slots do not fit, split it into trips that each reach the edge.")


# ---------------------------------------------------------------------------
# Weapons and the kit
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Weapon:
    key: str
    label: str            # Fata name_en, before the " (state)" suffix
    bucket: str           # pair: 2 kills per use; single: 1 kill per use
    kind: str             # counted (N charges / shots, Empty), loaded (loaded / empty), plain
    ready: tuple[float, float] = (0, 0)       # (average, worst) uses of a plain / loaded weapon
    reload: str | None = None                 # item that refills it: battery | water
    reload_cap: tuple[float, float] = (0, 0)  # (average, worst) uses per reload item
    repairable: bool = False


WEAPONS = {w.key: w for w in (
    Weapon("laser", "Burning Laser Pointer", "pair", "counted", reload="battery", reload_cap=(3.25, 2)),
    Weapon("machete", "Machete", "pair", "plain", ready=(4, 1), repairable=True),
    Weapon("launcher", "Battery Launcher Mk. II", "single", "loaded", ready=(5, 1),
           reload="battery", reload_cap=(5, 1)),
    Weapon("knife", "Serrated Knife", "single", "plain", ready=(3, 1), repairable=True),
    Weapon("splash", "Aqua-Splash", "single", "counted", reload="water", reload_cap=(5, 5)),
    Weapon("pistol", "Water Pistol", "single", "counted", reload="water", reload_cap=(3, 3)),
)}
RELOADS = {"battery": "Battery", "water": "Water Ration (as ammunition, not for drinking)",
           "repair": "Repair Kit / Kwik-fix"}
BROKEN = -1   # a repairable weapon in the bank marked broken: repair it in town first


def _state(w: Weapon, name: str, broken: bool) -> int | None:
    """State of a bank item of weapon w: charges / shots, 1 = ready, 0 = empty, BROKEN."""
    if name == w.label:
        suffix = None
    elif name.startswith(w.label + " ("):
        suffix = name[len(w.label) + 2:-1]
    else:
        return None
    if w.kind == "plain":
        return BROKEN if broken else 1
    if broken or suffix is None:
        return None
    low = suffix.lower()
    if low == "empty":
        return 0
    if w.kind == "loaded":
        return 1 if low == "loaded" else None
    m = re.match(r"(\d+) (?:charges?|shots?)$", low)
    return int(m.group(1)) if m else None


def state_cap(w: Weapon, state: int) -> tuple[float, float]:
    """(average, worst) uses a weapon in this state gives, before any reload or repair."""
    if w.kind == "counted":
        return state, state
    if state == 0:
        return 0, 0
    return w.ready


def stock_from_bank(bank: list[dict]) -> dict[str, int]:
    """Usable weapons and reload items in the bank, by kit key ('laser:3', 'machete:-1',
    'battery', 'water', 'repair')."""
    stock: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        stock[key] = stock.get(key, 0) + n

    for it in bank:
        name, n, broken = it["name"], it["count"], bool(it.get("broken"))
        for w in WEAPONS.values():
            st = _state(w, name, broken)
            if st is not None:
                add(f"{w.key}:{st}", n)
        if broken:
            continue
        if name == "Battery":
            add("battery", n)
        elif name == "Water Ration":
            add("water", n)
        elif name in ("Repair Kit", "Kwik-fix"):
            add("repair", n)
    return stock


def kit_label(key: str) -> str:
    if ":" not in key:
        return RELOADS.get(key, key)
    wk, st = key.split(":")
    w, st = WEAPONS[wk], int(st)
    if st == BROKEN:
        return f"{w.label} (broken: repair in town)"
    if w.kind == "plain":
        return w.label
    if w.kind == "loaded":
        return f"{w.label} ({'loaded' if st else 'empty'})"
    unit = "charge" if wk == "laser" else "shot"
    return f"{w.label} ({'Empty' if wk == 'laser' else 'empty'})" if st == 0 else \
        f"{w.label} ({st} {unit}{'s' if st > 1 else ''})"


KIT_NAMES = {
    "laser": "laser:0", "machete": "machete:1", "launcher": "launcher:0", "launcher_loaded": "launcher:1",
    "knife": "knife:1", "aqua": "splash:0", "pistol": "pistol:0", "battery": "battery",
    "water": "water", "repair": "repair",
}
for _i in range(1, 5):
    KIT_NAMES[f"laser{_i}"] = f"laser:{_i}"
for _i in range(1, 6):
    KIT_NAMES[f"aqua{_i}"] = f"splash:{_i}"
for _i in range(1, 4):
    KIT_NAMES[f"pistol{_i}"] = f"pistol:{_i}"


def parse_kit(text: str) -> dict[str, int] | str:
    """'laser, machete, battery=2' → kit {'laser:0': 1, 'machete:1': 1, 'battery': 2}, or an
    "Error: ..." text. A bare laser / launcher / aqua / pistol is empty (needs its battery / water);
    laser3, aqua4, pistol2 and launcher_loaded say what it holds."""
    kit: dict[str, int] = {}
    for part in text.replace(";", ",").split(","):
        part = part.strip().lower()
        if not part:
            continue
        name, _, count = part.partition("=")
        name = name.strip().replace(" ", "_").replace("-", "")
        key = KIT_NAMES.get(name)
        if key is None:
            return (f"Error: unknown kit item '{part}' (use: laser, laser3, machete, knife, launcher, "
                    "launcher_loaded, aqua, aqua4, pistol, pistol2, battery, water, repair).")
        try:
            n = int(count) if count.strip() else 1
        except ValueError:
            return f"Error: bad count in '{part}'."
        kit[key] = kit.get(key, 0) + n
    return kit


def kit_slots(kit: dict[str, int]) -> int:
    """Rucksack slots: every weapon, Battery, ammunition Water Ration and repair item is one;
    a broken weapon repaired in town before leaving still takes one."""
    return sum(n for k, n in kit.items() if k != "repair_town")


def capacity(kit: dict[str, int], need: tuple[float, float] = (0, 0)) -> dict:
    """What a kit kills: {'pair': [avg, worst], 'single': [avg, worst], 'unused': [...]}, in
    uses (a pair use = 2 kills). Battery / water / repair items go where `need` (pairs,
    singles) is short, the laser first on a tie."""
    cap = {"pair": [0.0, 0.0], "single": [0.0, 0.0]}
    devices: dict[str, int] = {}
    for k, n in kit.items():
        if ":" not in k:
            continue
        w = WEAPONS[k.split(":")[0]]
        avg, worst = state_cap(w, int(k.split(":")[1]))
        cap[w.bucket][0] += n * avg
        cap[w.bucket][1] += n * worst
        devices[w.key] = devices.get(w.key, 0) + n

    def short(w: Weapon) -> float:
        """Kills still missing in w's bucket."""
        i = 0 if w.bucket == "pair" else 1
        mult = 2 if w.bucket == "pair" else 1
        return mult * (need[i] - cap[w.bucket][0])

    def give(options: list[str], n: int, unused: list[str], label: str) -> None:
        for _ in range(n):
            have = [WEAPONS[o] for o in options if devices.get(o)]
            if not have:
                unused.append(label)
                continue
            w = max(have, key=short)
            cap[w.bucket][0] += w.reload_cap[0]
            cap[w.bucket][1] += w.reload_cap[1]

    unused: list[str] = []
    give(["laser", "launcher"], kit.get("battery", 0), unused, "Battery")
    give(["splash", "pistol"], kit.get("water", 0), unused, "Water Ration")
    for _ in range(kit.get("repair", 0)):
        w = WEAPONS["machete"] if devices.get("machete") else WEAPONS["knife"] if devices.get("knife") else None
        if w is None:
            unused.append("Repair item")
        else:
            cap[w.bucket][0] += w.ready[0]
            cap[w.bucket][1] += w.ready[1]
    return {**cap, "unused": unused}


def cross_use(cap: dict, pairs: float, singles: float) -> tuple[int, int]:
    """(pairs covered by spare single uses, singles covered by spare pair uses): a spare pair
    use kills one single (one kill wasted), two spare single uses kill a pair."""
    dp = max(0.0, pairs - cap["pair"][0])
    ds = max(0.0, singles - cap["single"][0])
    by_pair = int(min(ds, math.floor(max(0.0, cap["pair"][0] - pairs)))) if ds > 0 else 0
    by_single = int(min(dp, math.floor(max(0.0, cap["single"][0] - singles) / 2))) if dp > 0 else 0
    return by_single, by_pair


def unmet(cap: dict, pairs: float, singles: float) -> tuple[float, float]:
    """(pairs, singles) not covered, after the cross use of spare uses (cross_use)."""
    by_single, by_pair = cross_use(cap, pairs, singles)
    return (max(0.0, pairs - cap["pair"][0]) - by_single,
            max(0.0, singles - cap["single"][0]) - by_pair)


def _candidates(kit: dict[str, int], stock: dict[str, int]) -> list[tuple[dict[str, int], int]]:
    """(items to add, slots) steps to try, from what the bank still has."""
    rem = {k: stock[k] - kit.get(k, 0) for k in stock}
    rem["repair"] = rem.get("repair", 0) - kit.get("repair_town", 0)
    has = {k.split(":")[0] for k in kit if ":" in k}
    out: list[tuple[dict[str, int], int]] = []
    for w in WEAPONS.values():          # WEAPONS order = preference on ties (laser first)
        for key in sorted((k for k in stock if k.startswith(w.key + ":")),
                          key=lambda k: (int(k.split(":")[1]) == BROKEN, k)):   # whole ones first
            if rem[key] <= 0:
                continue
            st = int(key.split(":")[1])
            if st == BROKEN:
                if rem.get("repair", 0) > 0:
                    out.append(({key: 1, "repair_town": 1}, 1))
            elif st == 0:
                if w.reload and rem.get(w.reload, 0) > 0:
                    out.append(({key: 1, w.reload: 1}, 2))
            else:
                out.append(({key: 1}, 1))
    for item, devs in (("battery", ("laser", "launcher")), ("water", ("splash", "pistol"))):
        if rem.get(item, 0) > 0 and has & set(devs):
            out.append(({item: 1}, 1))
    if rem.get("repair", 0) > 0 and has & {"machete", "knife"}:
        out.append(({"repair": 1}, 1))
    return out


def pick_kit(pairs: float, singles: float, stock: dict[str, int]) -> dict:
    """Weapons from the bank stock covering `pairs` and `singles` on the AVERAGE capacities,
    one step at a time: the step that covers the most missing kills per slot (the laser
    wins ties), until covered or the bank has nothing left. First each bucket gets its own
    weapons; only then may spare uses of the other bucket cover what is left (a pair weapon
    on a single wastes a kill). Returns {kit, cap, unmet}."""
    kit: dict[str, int] = {}

    def left(k: dict[str, int], cross: bool) -> float:
        cap = capacity(k, (pairs, singles))
        if cross:
            dp, ds = unmet(cap, pairs, singles)
        else:
            dp, ds = max(0.0, pairs - cap["pair"][0]), max(0.0, singles - cap["single"][0])
        return 2 * dp + ds

    for cross in (False, True):
        for _ in range(40):
            base = left(kit, cross)
            if base <= 1e-9:
                break
            best = None
            for i, (add, slots) in enumerate(_candidates(kit, stock)):
                trial = dict(kit)
                for k, n in add.items():
                    trial[k] = trial.get(k, 0) + n
                gain = base - left(trial, cross)
                if gain > 1e-9:
                    score = (gain / slots, gain, -i)
                    if best is None or score > best[0]:
                        best = (score, trial)
            if best is None:
                break
            kit = best[1]
    cap = capacity(kit, (pairs, singles))
    return {"kit": kit, "cap": cap, "unmet": unmet(cap, pairs, singles)}


def format_kit(kit: dict[str, int]) -> str:
    items = {k: n for k, n in kit.items() if k != "repair_town"}
    bring = ", ".join(f"{n} × {kit_label(k)}" for k, n in items.items()) or "nothing"
    return f"{bring} → **{kit_slots(kit)} slot(s)**"


def kit_lines(analysis: dict, bank: list[dict], given: dict[str, int] | None,
              slots: int) -> tuple[list[str], int, dict[str, int]]:
    """Lines for the kit section, the slots it takes and the kit. given = the player's kit
    (checked, not chosen), else the kit is picked from the bank on average capacities."""
    tot = analysis["totals"]
    P, S = tot["avg"]["pairs"], tot["avg"]["singles"]
    Pm, Sm = tot["max"]["pairs"], tot["max"]["singles"]
    stock = stock_from_bank(bank)
    if given is not None:
        kit = given
        cap = capacity(kit, (P, S))
        un = unmet(cap, P, S)
        head = "**Your kit** (checked against the estimate, nothing chosen):"
    else:
        picked = pick_kit(P, S, stock)
        kit, cap, un = picked["kit"], picked["cap"], picked["unmet"]
        head = "**Kit from the bank** (planned on average capacities):"
    lines = [head, f"  {format_kit(kit)}"]
    if kit.get("repair_town"):
        lines.append(f"  Repair {kit['repair_town']} broken weapon(s) in town first (1 AP each, "
                     f"uses {kit['repair_town']} Repair Kit / Kwik-fix).")
    lines.append(f"  Kills: pairs avg {_fmt(cap['pair'][0])} / worst {_fmt(cap['pair'][1])} (need {P}); "
                 f"singles avg {_fmt(cap['single'][0])} / worst {_fmt(cap['single'][1])} (need {S}).")
    by_single, by_pair = cross_use(cap, P, S)
    if by_single:
        lines.append(f"  {by_single} pair(s) are killed with 2 single-kill uses each (spare uses).")
    if by_pair:
        lines.append(f"  {by_pair} single(s) are killed with a pair weapon: 1 kill wasted each.")
    if kit.get("repair") or kit.get("repair_town"):
        lines.append("  Each repair costs 1 AP (Repair Kit / Kwik-fix) and the weapon must be broken first.")
    if un[0] or un[1]:
        parts = [f"{_fmt(un[0])} pair(s)" if un[0] else "", f"{_fmt(un[1])} single(s)" if un[1] else ""]
        what = "your kit" if given is not None else "the bank"
        lines.append(f"  **Not covered by {what}:** {' + '.join(p for p in parts if p)}.")
    cover = not any(unmet(cap, Pm, Sm))
    lines.append(f"  At the maximum estimate ({Pm} pairs, {Sm} singles) the kit "
                 + ("still covers it." if cover else "falls short: carry spares or scout first."))
    if cap["pair"][1] < P or cap["single"][1] < S:
        lines.append("  Worst case (breaks and short charges) is below the need: keep a spare weapon "
                     "and do not enter a zone you cannot clear.")
    if given is None and S and not any(k.startswith(("launcher", "knife", "splash", "pistol")) for k in stock):
        lines.append("  No single-kill weapon in the bank: a pair weapon covers a single and wastes a kill.")
    for u in cap["unused"]:
        lines.append(f"  Note: {u} has no weapon to reload in this kit.")
    return lines, kit_slots(kit), kit


# ---------------------------------------------------------------------------
# Respawn warning
# ---------------------------------------------------------------------------

def respawn_after_kills(data: dict, planned_avg: float) -> list[str]:
    """One warning line when the planned kills may take the map below tonight's global-respawn
    threshold, or when Fata's count is too incomplete to say. Warning only: it never
    reduces the kills."""
    t = respawn_totals(data)
    if t is None:
        return []
    left = t["known"] - planned_avg
    if left < t["threshold"]:
        return [f"**Respawn risk:** Fata counts {t['known']} zombies, {_fmt(planned_avg)} are planned "
                f"to die → {_fmt(left)} < the tonight threshold {t['threshold']} "
                f"({t['per_day']} × day {t['day'] + 1}); {t['missing']} are not counted, so a global "
                "respawn is possible (it regrows clean zones). Warning only: check the total with the zookeepers."]
    if t["never"] or t["uncounted"]:
        return [f"Respawn check: Fata counts {t['known']}, {_fmt(planned_avg)} planned → {_fmt(left)} ≥ "
                f"{t['threshold']} (threshold tonight), but {t['missing']} are not counted."]
    return []


# ---------------------------------------------------------------------------
# Zoo clusters and sides
# ---------------------------------------------------------------------------

DIRS4 = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}   # N = y growing (town-relative)
MAX_LISTED = 12


def _zones_text(zones: list[Cell]) -> str:
    zs = sorted(zones, key=lambda c: (c[1], c[0]))
    shown = " ".join(fmt_xy(c) for c in zs[:MAX_LISTED])
    return shown + (f" +{len(zs) - MAX_LISTED}" if len(zs) > MAX_LISTED else "")


def zoo_clusters(data: dict) -> list[dict]:
    """Connected groups (8 neighbours) of infected zones (estimate avg > 0 or danger > 0),
    biggest first. Each: zones, zombies (min/avg/max), bbox, unseen (never-visited zones
    next to it, inside the map), edge (touches the map border), sides {N,S,E,W: zones next
    to a visited clean zone in that direction}, zoo (the likely zoo)."""
    day = data["meta"].get("day")
    final = data["meta"].get("live") is False
    zmap = zone_map(data)
    est = {c: zone_estimate(z, day, zmap, final=final) for c, z in zmap.items() if c != (0, 0)}
    infected = {c for c, e in est.items() if e["avg"] > 0 or zmap[c].get("danger", 0) > 0}
    bounds = map_bounds(data)
    inside = (lambda c: in_bounds(bounds, c)) if bounds else (lambda c: False)

    def clean(c: Cell) -> bool:
        return c in zmap and c not in infected and (c == (0, 0) or est[c]["avg"] == 0)

    clusters, todo = [], set(infected)
    while todo:
        seed = todo.pop()
        comp, stack = {seed}, [seed]
        while stack:
            x, y = stack.pop()
            for dx, dy in NEIGHBOURS8:
                n = (x + dx, y + dy)
                if n in todo:
                    todo.discard(n)
                    comp.add(n)
                    stack.append(n)
        unseen = {(x + dx, y + dy) for x, y in comp for dx, dy in NEIGHBOURS8
                  if (x + dx, y + dy) not in zmap and inside((x + dx, y + dy))}
        edge = bool(bounds) and any(x in (bounds.xmin, bounds.xmax) or y in (bounds.ymin, bounds.ymax) for x, y in comp)
        sides = {}
        for d, (dx, dy) in DIRS4.items():
            zs = [c for c in comp if clean((c[0] + dx, c[1] + dy))]
            if zs:
                sides[d] = zs
        tot = {k: sum(est[c][k] for c in comp) for k in ("min", "avg", "max")}
        xs, ys = [c[0] for c in comp], [c[1] for c in comp]
        clusters.append({"zones": sorted(comp), "zombies": tot, "unseen": sorted(unseen), "edge": edge,
                         "bbox": (min(xs), max(xs), min(ys), max(ys)), "sides": sides, "est": est,
                         "zoo": False})
    clusters.sort(key=lambda c: -c["zombies"]["avg"])
    likely = next((c for c in clusters if c["edge"] or c["unseen"]), None)
    if likely:
        likely["zoo"] = True
    return clusters


def _side_line(d: str, zones: list[Cell], est: dict) -> str:
    z = sum(int(est[c]["avg"] + 0.5) for c in zones)
    p = sum(buckets(est[c]["avg"])[0] for c in zones)
    s = sum(buckets(est[c]["avg"])[1] for c in zones)
    return f"    {d}: {_n(len(zones), 'zone')}, ~{z} zombies ({_n(p, 'pair')} + {_n(s, 'single')}): {_zones_text(zones)}"


def format_zoo(data: dict) -> str:
    clusters = zoo_clusters(data)
    meta = data["meta"]
    lines = [header("Zombie clusters", meta)]
    if not clusters:
        lines.append("No zone with zombies (or danger) in the zones Fata knows.")
    never = never_visited(data)
    if never:
        lines.append(f"{never} zones never visited (not counted).")
    big = [c for c in clusters if len(c["zones"]) >= 3][:4]
    small = [c for c in clusters if c not in big]
    for i, c in enumerate(big, 1):
        z = c["zombies"]
        x0, x1, y0, y1 = c["bbox"]
        flags = ", ".join(f for f in ("touches the map edge" if c["edge"] else "",
                                      f"{len(c['unseen'])} never-visited zones inside/next to it" if c["unseen"] else "") if f)
        lines += ["", f"### Cluster {i}{' — likely zoo' if c['zoo'] else ''}: {_n(len(c['zones']), 'zone')}, "
                      f"{_fmt(z['avg'])} zombies ({_fmt(z['min'])}–{_fmt(z['max'])}), "
                      f"x {x0}..{x1}, y {y0}..{y1}" + (f", {flags}" if flags else "")]
        if c["sides"]:
            lines.append("  Sides (zombie zones next to a visited clean zone; N = y growing):")
            lines += [_side_line(d, zs, c["est"]) for d, zs in c["sides"].items()]
    if small:
        zs = [z for c in small for z in c["zones"]]
        n = sum(c["zombies"]["avg"] for c in small)
        lines += ["", f"Small clusters: {len(small)} groups, {len(zs)} zones, ~{_fmt(n)} zombies: {_zones_text(zs)}"]
    lines += ["", *respawn_check(data), "",
              "Ask the player which side to clean, or which area / corridor (then call this tool with "
              "waypoints= or route=). Kill every zombie of every zone you enter."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

def find_route(data: dict, name: str) -> dict | str:
    """The Fata route called `name` (case-insensitive: exact first, then prefix), or an
    error text (none found, or several: they are listed)."""
    routes = data.get("routes") or []
    if not routes:
        return "No routes in this data (Fata routes exist only in /towndata days)."
    low = name.strip().lower()
    hits = [r for r in routes if r["name"].lower() == low] or \
           [r for r in routes if r["name"].lower().startswith(low)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        sample = ", ".join(r["name"] for r in routes[:12])
        return f"No route named '{name}' on day {data['meta'].get('day')}. Routes: {sample}" \
               + (f" (+{len(routes) - 12} more)" if len(routes) > 12 else "")
    return f"'{name}' matches {len(hits)} routes: " + "; ".join(r["name"] for r in hits[:12]) + ". Use the full name."


def _supplies_block(data: dict, path: list[Cell], *, start_ap: int, slots: int, kit: int, available: str,
                    second_wind: int, group_cp: int, repairs_out: int = 0,
                    repairs_town: int = 0) -> str | list[str]:
    """The supplies plan on the exact route out (town to path[-1]) and the way home. An error
    text (str) on bad input, else the plan lines. Repairs cost 1 AP each: those done in town
    come off the departure AP, those carried are kept as AP to spare along the way."""
    parsed = supplies.parse_supplies(available, second_wind)
    if isinstance(parsed, str):
        return parsed
    items, sw_ap, sw_ep = parsed
    out = [(0, 0)] + path
    notes = []
    back = loop_return(data, out, group_cp) if out[-1] != (0, 0) else None
    if out[-1] != (0, 0) and back is None:
        leg = supplies.HomeLeg(out, 0, f"No way home found from the last zone ({MAX_PATH_AP} AP cap): "
                                       "supplies cover the way out only.", None)
    else:
        leg = supplies.home_leg(data, out, back)
    route, end_ap = leg.route, leg.end_ap
    notes.append(leg.note)
    if repairs_town:
        start_ap -= repairs_town
        notes.append(f"Departure AP {start_ap}: {repairs_town} AP spent repairing in town.")
    if repairs_out:
        end_ap += repairs_out
        notes.append(f"{repairs_out} AP kept to spare for the repair(s) on the way (1 AP each).")
    st = supplies.Start(ap=start_ap, sw_ap=sw_ap, sw_ep=sw_ep)
    free = slots - kit
    # slots=0 means no limit: with no slot left, plan freely and say how many are missing.
    result = supplies.plan(route, st, items, end_ap=end_ap, slots=max(0, free))
    failed = not supplies.feasible(result)
    lead: list[str] = []
    if failed:
        # The goal sets a kill route, not the AP: plan it with every booster it needs
        # (one drug, one alcohol at most), in any number of slots, and check the slots below.
        alt, added, swapped = supplies.with_boosters(route, st, items, end_ap)
        lead.append(supplies.not_feasible_line(route, result, available, added if alt else None, max(0, free), swapped))
        if alt:
            result, failed = alt, False
    need = supplies.carried(result["used"])
    if not failed and need > free:
        notes.append(f"**Does not fit in the rucksack:** kit {kit} + supplies {need} = {kit + need} slots, "
                     f"{slots} free: {kit + need - slots} short. Bring a bag (more slots), take a kit with "
                     "fewer slots (kit=), or split the route into trips.")
    if not available.strip():
        notes.append(supplies.ASSUMED_DEFAULT_NOTE)
    notes.append(f"Slots: {slots} free at departure, minus {kit} for the kit = {free}.")
    options = None
    if supplies.wants_extra_options(available, result) and not failed and free >= need:
        from .bank import expedition_extras
        options = supplies.extra_options(route, st, items, end_ap=end_ap, slots=free,
                                         stock=expedition_extras(data["bank"]))
    text = supplies.format_plan(route, st, result, title="Supplies plan, the route as given",
                                notes=[n for n in notes if n], slots=max(free, 0) if need <= free else 0,
                                end_ap=end_ap,
                                teleport=leg.teleport_from is not None,
                                generic_extras=not available.strip(), cp=group_cp, options=options, lead=lead)
    return text.split("\n")


def plan_kill_route(data: dict, *, route: str = "", waypoints: list[Cell] | None = None, zoo: bool = False,
                    kit: str = "", group_cp: int = CP_PER_CITIZEN, cp_breakdown: list[str] | None = None,
                    start_ap: int = 6, slots: int = 5, available: str = "", second_wind: int = 0) -> str:
    """The whole answer of the plan_kill_route tool, from a parsed /towndata result."""
    if data.get("error"):
        return f"Error: {data['error']}"
    if route.strip() and waypoints:
        return "Error: give a Fata route name or waypoints, not both."
    if zoo or not (route.strip() or waypoints):
        return format_zoo(data)
    if slots < 1:
        return supplies.SLOTS_ERROR
    given = None
    if kit.strip():
        given = parse_kit(kit)
        if isinstance(given, str):
            return given
    meta = data["meta"]
    instructions: dict[int, str] = {}
    if route.strip():
        r = find_route(data, route)
        if isinstance(r, str):
            return r
        path, title = r["path"], r["name"]
        head = f"{len(path)} steps, {r.get('ap')} AP (Fata)" + (f", drawn by {r['creator']}" if r.get("creator") else "")
        instructions = r["instructions"]
        if r.get("day") not in (None, meta.get("day")):
            head += f", route of day {r['day']}"
    else:
        path = expand_route([(0, 0)] + list(waypoints))
        title, head = "own route", f"{len(path)} steps, {len(path)} AP"
    if not path:
        return "Error: the route has no step."
    a = analyse_route(data, path)
    tot = a["totals"]
    lines = [f"## Kill route: {title} (Day {meta.get('day', '?')}) — {head}", data_updated(meta)]
    if a["rows"]:
        lines += ["", "| Step | Zone | Zombies | Source | Pairs | Singles |", "|---|---|---|---|---|---|"]
        for row in a["rows"]:
            e, (x, y) = row["est"], row["zone"]
            src = e["source"] + (f", {e['killed_today']} killed today" if e.get("killed_today") else "")
            lines.append(f"| {row['step']} | {fmt_xy((x, y))} | {_range(e)} | {src} | {row['pairs']} | {row['singles']} |")
    else:
        lines += ["", "No zone with zombies on this route."]
    avg, lo, hi = tot["avg"], tot["min"], tot["max"]
    lines += ["", f"**Total (average): {avg['zombies']} zombies in {_n(len(a['rows']), 'zone')} = "
                  f"{_n(avg['pairs'], 'pair')} + {_n(avg['singles'], 'single')}**"
                  + ("" if lo == hi == avg else
                     f" · range {lo['zombies']}–{hi['zombies']} zombies "
                     f"({min(lo['pairs'], hi['pairs'])}–{max(lo['pairs'], hi['pairs'])} pairs, "
                     f"{min(lo['singles'], hi['singles'])}–{max(lo['singles'], hi['singles'])} singles)"),
              "Kill every zombie of every zone: one left alive infects the clean zones around it tonight."]
    if a["unknown"]:
        lines.append("Never visited, no infected zone known around (counted 0, scout first): "
                     + " ".join(f"{fmt_xy(c)} (step {s})" for s, c in a["unknown"]))
    if a["banded"]:
        lines.append("Danger band only, left out of the totals (past day): "
                     + " ".join(f"{fmt_xy(c)} ~{_fmt(e['min'])}–{_fmt(e['max'])}" for _, c, e in a["banded"]))
    if a["rows"] or given is not None:
        kl, kslots, kit_used = kit_lines(a, data.get("bank", []), given, slots)
        lines += [""] + kl
    else:
        kslots, kit_used = 0, {}
    warns = respawn_after_kills(data, avg["zombies"])
    if gap := edge_gap(data, path):
        warns.insert(0, gap)
    blocked = [r for r in a["rows"] if r["est"]["max"] > group_cp]
    if blocked:
        zs = ", ".join(f"{fmt_xy(r['zone'])} ({_fmt(r['est']['max'])})" for r in blocked[:MAX_LISTED])
        warns.append(f"Zones with more zombies than the group's {group_cp} CP block it there until they are "
                     f"killed: {zs}" + (f" +{len(blocked) - MAX_LISTED}" if len(blocked) > MAX_LISTED else "")
                     + ". Kill everything before leaving the zone; an empty weapon means stuck.")
    for step, text in sorted(instructions.items()):
        c = path[step - 1] if 0 < step <= len(path) else None
        warns.append(f"Route note, step {step}" + (f" {fmt_xy(c)}" if c else "") + f": {text}")
    if any(k.startswith(("machete:", "knife:")) for k in kit_used):
        warns.append("Machete and Serrated Knife need AP left (not Exhausted) and healthy hands: "
                     "kill with them before using your last AP.")
    if cp_breakdown:
        warns.append("Party CP: " + "; ".join(cp_breakdown))
    if group_cp == CP_PER_CITIZEN and not cp_breakdown:
        warns.append(f"Assumed {CP_PER_CITIZEN} CP (solo citizen): pass party= or group_cp= for the group.")
    if warns:
        lines += ["", "**Warnings**"] + [f"- {w}" for w in warns]
    plan = _supplies_block(data, path, start_ap=start_ap, slots=slots, kit=kslots, available=available,
                           second_wind=second_wind, group_cp=group_cp,
                           repairs_out=kit_used.get("repair", 0), repairs_town=kit_used.get("repair_town", 0))
    if isinstance(plan, str):
        return plan
    lines += [""] + [("#" + ln if ln.startswith("## ") else ln) for ln in plan]
    return "\n".join(lines)
