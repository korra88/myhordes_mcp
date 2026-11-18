"""Group camping planner: who hides in which order, who digs a grave, who carries which camp item.

Plan and rules: docs/group-camping-plan.md. The odds are `camping.camping_terms` (verified in the
game source); this module only chooses the decisions:

  - the hiding order (crowd malus and the ruin room depend on how many are hidden before);
  - how many improves (+5, 1 AP), installs (+9, 1 AP + a defensive item) and boosted dog uses
    (+5 for a steak, no AP) raise the zone level, which the whole group shares;
  - which campers dig a grave (+8 to that camper, 1 AP; a Tamer's dog digs it for free);
  - how the camp items (+5 each, in the rucksack, not consumed) are spread over the campers.

`solve` is exact. For each (installs j, boosted dog uses s, improves i) the zone level is fixed,
and a DP over (set of campers already placed, items left, paid graves, boosted dogs used)
chooses the order, graves and items. The campers' value is composed by sum and minimum, both
monotone, so the DP is exact; the lexicographic tie-breakers are then settled in a second DP
restricted to the best minimum. Objective (lexicographic, smaller is better after the first):
survival, defensive items, paid graves, AP, steaks, dog uses, camp items used, items moved,
distance from the Fata plan's order.

`format_group_camping` reads a parsed Fata town and prints the answer.
"""

import difflib
import itertools
import math
from dataclasses import dataclass, field

from ..utils.fmt import header, plural, ruin_label
from . import camplog
from .camping import (
    CROWD, IMPROVE_LEVEL, INSTALL_LEVEL, MAX_LEVEL_TO_ACT, NIGHTLY_DROP, _find_citizen, camping_terms,
    is_panda, lighthouse_built, odds_cap, resolve_camp_level, resolve_night, ruin_term, skill_label,
    zone_reading,
)
from .cp import citizen_key
from .geo import fmt_xy, km, xy
from .towndata import plans_for_citizen, plans_for_zone

MAX_CAMPERS = 6
GRAVE_BONUS, ITEM_BONUS = 8, 5
ORD = ["1st", "2nd", "3rd", "4th", "5th", "6th"]


@dataclass
class Camper:
    name: str
    base: int            # every odds term but the zone level, the crowd, the ruin room, grave, items
    cap: int = 90        # cap in points (90, 99, 100)
    tomb: bool = False   # grave already dug (its +8 is counted in `base`)
    tamer: bool = False
    carried: int = 0     # camp items in the rucksack now
    hint: int = 0        # position in the Fata plan (tie-breaker)
    info: dict = field(default_factory=dict)


@dataclass
class Solution:
    level: int
    improves: int
    installs: int
    boosts: int
    order: list          # camper indexes in hiding order
    grave: list          # per camper: "dug" | "paid" | "dog" | "boost" | ""
    items: list          # camp items each camper carries (per camper, not per position)
    odds: list           # capped points per camper
    paid: int
    dogs: int
    ap: int
    survival: tuple = ()

    @property
    def total(self) -> int:
        return sum(self.odds)


def position_terms(n: int, ruin: dict | None, hidden_before: int) -> list[int]:
    """Crowd + ruin-room points for the camper hiding at each position (0 = first of the group)."""
    return [CROWD[min(len(CROWD) - 1, hidden_before + p)] + ruin_term(ruin, hidden_before + p)
            for p in range(n)]


def level_ok(level0: int, n5: int, n9: int) -> bool:
    """Whether n5 steps of +5 and n9 of +9 can all start below 50 (biggest step last)."""
    if not (n5 or n9):
        return True
    return level0 + IMPROVE_LEVEL * n5 + INSTALL_LEVEL * n9 - (INSTALL_LEVEL if n9 else IMPROVE_LEVEL) < MAX_LEVEL_TO_ACT


class _Solver:
    def __init__(self, campers, pos, *, level, ap, defense_items, pool, steaks, slots, objective):
        self.c, self.pos, self.n = campers, pos, len(campers)
        self.level0, self.ap, self.defense, self.pool = level, ap, defense_items, pool
        self.steaks, self.slots, self.objective = steaks, slots, objective
        self.tamers = sum(1 for c in campers if c.tamer and not c.tomb)
        self._opts: dict = {}
        self._bounds: dict = {}

    def options(self, level: int):
        """opts[k][p]: (kind, paid, boost, items, odds, dog, moved, place) of camper k at position p."""
        if level in self._opts:
            return self._opts[level]
        out = []
        for k, c in enumerate(self.c):
            row = []
            for p in range(self.n):
                base = c.base + self.pos[p] + level
                kinds = [("dug" if c.tomb else "", 0, 0, 0, 0)]
                if not c.tomb:
                    if c.tamer:   # the dog's grave is free: it always beats paying 1 AP
                        kinds.append(("dog", 0, 0, GRAVE_BONUS, 1))
                        kinds.append(("boost", 0, 1, GRAVE_BONUS, 1))
                    else:
                        kinds.append(("paid", 1, 0, GRAVE_BONUS, 0))
                opts = []
                for kind, paid, boost, bonus, dog in kinds:
                    need = max(0, c.cap - base - bonus)
                    top = min(self.slots, self.pool, -(-need // ITEM_BONUS))
                    for m in range(top + 1):
                        o = max(0, min(base + bonus + ITEM_BONUS * m, c.cap))
                        opts.append((kind, paid, boost, m, o, dog, abs(m - c.carried), abs(p - c.hint)))
                row.append(opts)
            out.append(row)
        self._opts[level] = out
        return out

    def _bound(self, level):
        """(rem, kbest): rem[mask] = the most odds (points) the campers outside `mask` can have
        in the positions left, with every resource they could want (resources ignored: an upper
        bound); kbest[k] = camper k's best odds anywhere."""
        cache = self._bounds.get(level)
        if cache is None:
            n, opts = self.n, self.options(level)
            best = [[max(o[4] for o in opts[k][p]) for p in range(n)] for k in range(n)]
            full = (1 << n) - 1
            rem = [0] * (full + 1)
            for mask in range(full - 1, -1, -1):
                p = bin(mask).count("1")
                rem[mask] = max(best[k][p] + rem[mask | 1 << k] for k in range(n) if not mask >> k & 1)
            cache = self._bounds[level] = (rem, [max(row) for row in best])
        return cache

    def _dp(self, level, gmax, s, phase, mstar=0, target=None):
        """Best final states of one DP. phase 1: value by the objective's survival (exact m*),
        states dominated in (items left, paid graves, value) dropped; phase 2: only odds >= m*,
        value = (sum, -dogs, -moved, -distance), no dominance (items used and paid graves are
        tie-breakers there). `target` (phase 1): a survival that must be reached, a state whose
        best possible completion falls below it is dropped."""
        n, P = self.n, self.pool
        opts = self.options(level)
        exp = self.objective == "expected"
        if phase == 1:
            init = (0, math.inf) if exp else (math.inf,)
        elif phase == 3:
            init = (0,)
        else:
            init = (0, 0, 0, 0)
        layers = [{(0, P, 0, 0): (init, None)}]
        full = (1 << n) - 1
        rem, kbest = self._bound(level)
        floor = None if target is None or phase != 1 else target[0]
        for p in range(n):
            nxt: dict = {}
            for key, (val, _) in layers[-1].items():
                mask, il, g, b = key
                for k in range(n):
                    if mask >> k & 1:
                        continue
                    for opt in opts[k][p]:
                        kind, paid, boost, m, o, dog, mv, dist = opt
                        if m > il or g + paid > gmax or b + boost > s:
                            continue
                        if phase == 1:
                            nv = (val[0] + o, min(val[1], o)) if exp else (min(val[0], o),)
                            if floor is not None and (nv[0] + rem[mask | 1 << k] if exp else nv[0]) < floor:
                                continue
                        elif phase == 3:
                            if o < mstar:
                                continue
                            nv = (val[0] + o,)
                        else:
                            if o < mstar:
                                continue
                            nv = (val[0] + o, val[1] - dog, val[2] - mv, val[3] - dist)
                        nk = (mask | 1 << k, il - m, g + paid, b + boost)
                        cur = nxt.get(nk)
                        if cur is None or nv > cur[0]:
                            nxt[nk] = (nv, (key, k, opt))
            if phase != 2 and p < n - 1:
                nxt = self._prune(nxt)
            layers.append(nxt)
            if not nxt:
                return None, layers
        return layers[-1], layers

    @staticmethod
    def _prune(states: dict) -> dict:
        """Drop a state when another one of the same (mask, boosts) has at least as many items
        left, at most as many paid graves and at least the value (survival-only phase)."""
        groups: dict = {}
        for key, v in states.items():
            groups.setdefault((key[0], key[3]), []).append((key[2], -key[1], key, v))
        out = {}
        for lst in groups.values():
            lst.sort(key=lambda t: (t[0], t[1]))   # fewer paid graves, then more items left
            kept: list = []
            for g, nil, key, v in lst:
                if any(kil <= nil and kv >= v for kg, kil, kv in kept):   # (kg <= g by order)
                    continue
                kept.append((g, nil, v))
                out[key] = v
        return out

    def _pick(self, final, s, phase):
        best = None
        for key, (val, _) in final.items():
            if key[3] != s:
                continue
            if phase in (1, 3):
                cand = (val, -key[2])    # survival, then fewest paid graves
            else:   # sum high, then paid graves, dogs, items used, moved, distance low
                cand = (val[0], -key[2], val[1], -(self.pool - key[1]), val[2], val[3])
            if best is None or cand > best[0]:
                best = (cand, key, val)
        return best

    def _trace(self, layers, key):
        out = []
        for p in range(self.n, 0, -1):
            _, back = layers[p][key]
            key, k, opt = back
            out.append((k, opt))
        return out[::-1]

    def survival_of(self, odds):
        return (sum(odds), min(odds)) if self.objective == "expected" else (min(odds), sum(odds))

    def screen(self, i, j, s, target=None, relaxed=False):
        """Phase 1 of a combo: (survival, fewest paid graves at that survival, m*), cheap.
        `relaxed`: graves are not limited by AP (an upper bound of the combo's survival)."""
        level = self.level0 + IMPROVE_LEVEL * (i + s) + INSTALL_LEVEL * j
        gmax = self.n if self.ap is None or relaxed else self.ap - i - j
        if gmax < 0:
            return None
        gmax = min(gmax, self.n)
        if target is not None:   # cannot reach the target even with every resource: no DP
            rem, kbest = self._bound(level)
            if (rem[0] if self.objective == "expected" else min(kbest)) < target[0]:
                return None
        final, _ = self._dp(level, gmax, s, 1, target=target)
        best = self._pick(final, s, 1) if final else None
        if best is None:
            return None
        v = best[2]
        if self.objective == "expected":
            return v, -best[0][1], v[1]
        # weakest: the best lowest odds first (phase 1), then the best sum with every camper
        # at that lowest or more (phase 3), whose fewest paid graves count
        mstar = v[0]
        final, _ = self._dp(level, gmax, s, 3, mstar)
        best = self._pick(final, s, 3) if final else None
        return (mstar, best[2][0]), -best[0][1], mstar

    def build(self, i, j, s, mstar, paid):
        """Phase 2 of the winning combo: the tie-breakers, with exactly `paid` paid graves."""
        level = self.level0 + IMPROVE_LEVEL * (i + s) + INSTALL_LEVEL * j
        final, layers = self._dp(level, paid, s, 2, mstar)
        best = self._pick(final, s, 2) if final else None
        trace = self._trace(layers, best[1])
        order = [k for k, _ in trace]
        grave, items, odds = [""] * self.n, [0] * self.n, [0] * self.n
        for k, (kind, pd, boost, m, o, dog, mv, dist) in trace:
            grave[k], items[k], odds[k] = kind, m, o
        paid_n = sum(1 for g in grave if g == "paid")
        dogs = sum(1 for g in grave if g in ("dog", "boost"))
        sol = Solution(level, i, j, s, order, grave, items, odds, paid_n, dogs, i + j + paid_n)
        sol.survival = self.survival_of(odds)
        return sol


def solve(campers: list[Camper], *, level: int, ruin: dict | None, hidden_before: int = 0,
          ap: int | None = None, defense_items: int = 0, pool: int = 0, steaks: int = 0,
          slots: int = 5, objective: str = "expected") -> Solution | None:
    """The best plan for the group (see the module docstring). `ap` None = unlimited."""
    n = len(campers)
    sv = _Solver(campers, position_terms(n, ruin, hidden_before), level=level, ap=ap,
                 defense_items=defense_items, pool=pool, steaks=steaks, slots=slots, objective=objective)
    smax = min(steaks, sv.tamers)
    jmax = defense_items if ap is None else min(defense_items, ap)
    combos = []     # every (i, j, s) the AP, the items, the steaks and the level rule allow
    for j in range(jmax + 1):
        for s in range(smax + 1):
            i = 0
            while (ap is None or i + j <= ap) and level_ok(level, i + s, j):
                combos.append((j, i + j, s, i))
                i += 1
    if not combos:
        return None
    top = max(combos, key=lambda c: (level + IMPROVE_LEVEL * (c[3] + c[2]) + INSTALL_LEVEL * c[0], -c[0], -c[1]))
    j, _, s, i = top
    # Upper bound of the survival: the highest level with graves not limited by AP.
    bound = sv.screen(i, j, s, relaxed=True)
    best = None     # (key, (i, j, s, m*, paid))

    def consider(i, j, s):
        nonlocal best
        res = sv.screen(i, j, s, target=best[2] if best else None)
        if res is None:
            return
        surv, paid, mstar = res
        if best is not None and surv < best[2]:
            return
        key = (tuple(-v for v in surv), j, paid, i + j + paid, s)
        if best is None or key < best[0]:
            best = (key, (i, j, s, mstar, paid), surv)

    consider(i, j, s)
    for j, ij, s, i in sorted(combos):
        if best is not None and bound is not None and best[2] == bound[0] and (j, 0, ij, s) >= best[0][1:]:
            continue    # survival cannot improve; no fewer installs / graves / AP possible
        consider(i, j, s)
    if best is None:
        return None
    i, j, s, mstar, paid = best[1]
    return sv.build(i, j, s, mstar, paid)


# ---------------------------------------------------------------------------
# Order matters?
# ---------------------------------------------------------------------------

def order_matters(campers, sol: Solution, pos: list[int], level: int) -> bool:
    """Whether another hiding order (same graves, same items per camper) changes anyone's odds."""
    n = len(campers)

    def odds_by_camper(perm):
        out = {}
        for p, k in enumerate(perm):
            c = campers[k]
            bonus = (GRAVE_BONUS if sol.grave[k] in ("paid", "dog", "boost") else 0) + ITEM_BONUS * sol.items[k]
            out[k] = max(0, min(c.base + pos[p] + level + bonus, c.cap))
        return out
    ref = odds_by_camper(sol.order)
    return any(odds_by_camper(perm) != ref for perm in itertools.permutations(range(n)))


# ---------------------------------------------------------------------------
# Group parsing and the formatter
# ---------------------------------------------------------------------------

_SKILL_TOKENS = {"r1": "reclusive1", "r2": "reclusive2", "r3": "reclusive3", "r4": "reclusive4",
                 "pro": "procamp", "none": "none"}
ITEM_UIDS = {"sheet": "Groundsheet", "smelly_meat": "Festering Flesh"}
STEAK_UID = "meat"


def parse_group(text: str) -> list[dict] | str:
    """'Korra:R2:n2, Ammonia:R4:tomb:items=1' -> [{name, skill?, nights?, tomb?, items?, vest?,
    tamer?, surv?}], or an error text."""
    out = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        parts = [t.strip() for t in raw.split(":")]
        name = parts[0]
        rest = parts[1:]
        if rest and rest[0].isdigit():   # "@Name:12345" handle
            name += ":" + rest.pop(0)
        ov = {"name": name}
        for t in rest:
            tl = t.lower()
            if tl in _SKILL_TOKENS:
                ov["skill"] = _SKILL_TOKENS[tl]
            elif tl.startswith("n") and tl[1:].isdigit():
                ov["nights"] = int(tl[1:])
            elif tl == "tomb":
                ov["tomb"] = True
            elif tl == "notomb":
                ov["tomb"] = False
            elif tl.startswith("items=") and tl[6:].isdigit():
                ov["items"] = int(tl[6:])
            elif tl in ("vest", "tamer", "surv"):
                ov[tl] = True
            else:
                return (f"Error: cannot read '{t}' after {name}: use R1-R4, pro, none, nN (nights survived), "
                        "tomb (grave already dug) / notomb, items=K, vest, tamer, surv.")
        out.append(ov)
    return out


def _ord(i: int) -> str:
    return ORD[i] if i < len(ORD) else f"{i + 1}th"


def _zone_item_count(z: dict | None, uid: str) -> int:
    return sum(i.get("count", 0) for i in (z or {}).get("items", []) if i.get("uid") == uid)


def format_group_camping(data: dict, *, x: int | None, y: int | None, group: str = "", day_arg: int = 0,
                         ap: int = -1, defense_items: int = 0, camp_items: int = 0, steaks: int = -1,
                         slots: int = 5, camp_level: int = -1, hidden_before: int = 0,
                         objective: str = "expected", town_id: int | None = None) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    night = resolve_night(data, day_arg)
    if isinstance(night, str):
        return night
    day, target, future = night["day"], night["target"], night["future"]
    ref = night["ref"]
    objective = (objective or "expected").strip().lower()
    if objective not in ("expected", "weakest"):
        return "Error: objective must be 'expected' (most expected survivors) or 'weakest' (best lowest odds)."
    for label, v in (("defense_items", defense_items), ("camp_items", camp_items),
                     ("hidden_before", hidden_before)):
        if v < 0:
            return f"Error: {label} cannot be negative."
    if slots < 1:
        return "Error: slots must be at least 1."
    if not isinstance(day, int):
        return "Error: the town's current day is unknown."
    alive = {c["id"] for c in data.get("citizens", [])}
    assumed: list[str] = []

    # --- the campers asked for -------------------------------------------------------
    overrides = parse_group(group)
    if isinstance(overrides, str):
        return overrides
    named = bool(overrides)
    if len(overrides) > MAX_CAMPERS:
        return f"Error: {len(overrides)} campers: the planner handles at most {MAX_CAMPERS}. Split the group."
    cits = []
    for ov in overrides:
        cit = _find_citizen(data, ov["name"])
        if cit is None:
            names = [c["name"] for c in data.get("citizens", [])]
            close = difflib.get_close_matches(citizen_key(ov["name"]), [citizen_key(n) for n in names], n=4, cutoff=0.4)
            sug = [n for n in names if citizen_key(n) in close]
            return (f"Error: '{ov['name']}' is not a living citizen of this town."
                    + (f" Closest living citizens: {', '.join(sug)}." if sug else ""))
        cits.append(cit)

    def latest_earlier(cid):
        for d in range(target - 1, day - 1, -1):
            p = max(plans_for_citizen(data, cid, d), key=lambda p: len(p["players"]), default=None)
            if p:
                return p
        return None

    # --- the zone --------------------------------------------------------------------
    cell = (x, y) if x is not None and y is not None else None
    plan_src = None   # the plan group="" uses
    if cell is None:
        zones = set()
        if named:
            for cit in cits:
                p = max(plans_for_citizen(data, cit["id"], target), key=lambda p: len(p["players"]), default=None) \
                    or (latest_earlier(cit["id"]) if future else None)
                if p:
                    zones.add(p["coords"])
            if not zones:
                pos = {xy(c) for c in cits if xy(c) is not None and not c.get("inside_town")}
                if len(pos) == 1:
                    zones = {fmt_xy(next(iter(pos)))}
                    assumed.append(f"zone {next(iter(zones))}: where the group stands now")
        else:
            ps = [p for p in data.get("camp_plans") or [] if p["target_day"] == target]
            if not ps and future:
                for d in range(target - 1, day - 1, -1):
                    ps = [p for p in data.get("camp_plans") or [] if p["target_day"] == d]
                    if ps:
                        break
            zones = {p["coords"] for p in ps}
        if not zones:
            return ("Error: give the zone (x, y)" + ("" if named else " or a group name list: no Fata camp plan "
                    f"for {ref}") + ".")
        if len(zones) > 1:
            return f"Error: the group's plans are on several zones ({', '.join(sorted(zones))}): give the zone (x, y)."
        cell = xy(next(iter(zones)))
        if not any("zone " in a for a in assumed):
            assumed.append(f"zone {fmt_xy(cell)}: from the Fata camp plan")
    if cell == (0, 0):
        return "Error: nobody camps in town: give a zone outside."
    coords = fmt_xy(cell)
    z, ruin, zombies, zombie_note = zone_reading(data, cell, night)
    zone_plans = plans_for_zone(data, coords, target)

    # group "" = the campers of the plan(s) of the night on the zone (an earlier plan for a future night)
    base_plan = None
    if not named:
        pool_plans = zone_plans
        if not pool_plans and future:
            for d in range(target - 1, day - 1, -1):
                pool_plans = plans_for_zone(data, coords, d)
                if pool_plans:
                    break
            if pool_plans:
                base_plan = max(pool_plans, key=lambda p: len(p["players"]))
        if not pool_plans:
            return f"Error: no Fata camp plan {ref} on {coords}: give the group (names)."
        seen = []
        for p in sorted(pool_plans, key=lambda p: -len(p["players"])):
            for q in p["players"]:
                if q["citizen_id"] in alive and all(q["citizen_id"] != r["citizen_id"] for r in seen):
                    seen.append(q)
        if len(pool_plans) > 1:
            assumed.append(f"{len(pool_plans)} Fata plans on this zone: their campers are merged ({len(seen)} different)")
        for q in seen:
            cit = next(c for c in data["citizens"] if c["id"] == q["citizen_id"])
            overrides.append({"name": cit["name"]})
            cits.append(cit)
        dead = sum(1 for p in pool_plans for q in p["players"] if q["citizen_id"] not in alive)
        if dead:
            assumed.append(f"{dead} camper(s) of the plan(s) are dead: left out")
        if len(overrides) > MAX_CAMPERS:
            return (f"Error: the Fata plan has {len(overrides)} campers: the planner handles at most "
                    f"{MAX_CAMPERS}. Give a list of at most {MAX_CAMPERS} names in `group`.")
    if not overrides:
        return "Error: no camper: give `group` or a zone with a Fata camp plan."
    names = [c["id"] for c in cits]
    if len(set(names)) != len(names):
        return "Error: a camper is listed twice."

    mine = max(zone_plans, key=lambda p: sum(any(q["citizen_id"] == c["id"] for q in p["players"]) for c in cits),
               default=None) if zone_plans else None
    camp_level = resolve_camp_level(data, coords=coords, z=z, night=night, camp_level=camp_level,
                                    zone_plans=zone_plans, mine=mine,
                                    assumed=assumed, town_id=town_id, can_record=False)   # read-only: nothing recorded
    km_ = km(*cell)
    panda, lighthouse = is_panda(meta), lighthouse_built(data)
    devastated = bool(meta.get("devastated"))
    log = camplog.load_log(town_id) if town_id is not None else {}

    # --- per camper values: override > plan of the night > earlier plan > log > job > none ----
    campers, infos = [], []
    for idx, (ov, cit) in enumerate(zip(overrides, cits)):
        entry, src = None, ""
        for p in zone_plans:
            e = next((q for q in p["players"] if q["citizen_id"] == cit["id"]), None)
            if e:
                entry, src, hint = e, f"{p['creator'] or 'a player'}'s Fata plan", p["players"].index(e)
                break
        else:
            hint = 100 + idx
        shift = 0
        if entry is None and future:
            ep = latest_earlier(cit["id"])
            if ep:
                entry = next(q for q in ep["players"] if q["citizen_id"] == cit["id"])
                shift = target - ep["target_day"]
                src = f"{ep['creator'] or 'a player'}'s Fata plan for day {ep['target_day']}"
        if base_plan is not None:
            hint = next((i for i, q in enumerate(base_plan["players"]) if q["citizen_id"] == cit["id"]), 100 + idx)
        job = "Survivalist" if ov.get("surv") else cit["job"]
        skill = ov.get("skill") or (entry["skill"] if entry else "none")
        if "nights" in ov:
            nights = ov["nights"]
        elif entry:
            nights = entry["nights"] + shift
            if shift:
                assumed.append(f"{cit['name']}: {nights} camping nights = {entry['nights']} in {src} + {shift}, "
                               "assuming every night until then is camped as planned (ask the player)")
        else:
            sure, prob, plnd = camplog.counts(log, cit["id"]) if town_id is not None else (0, 0, 0)
            nights = sure + prob + plnd
            assumed.append(f"{cit['name']}: {nights} camping nights from the camping log ({sure} sure + {prob} "
                           f"probable + {plnd} planned, pessimistic)" if nights else
                           f"{cit['name']}: camping nights assumed 0 (no plan, nothing in the log), ask the player")
        # A grave lasts one night: the game clears it every night (tg_tomb is a volatile status,
        # NightlyHandler), so an earlier night's plan never gives one.
        tomb = ov.get("tomb", bool(entry and entry["tomb"] and not shift))
        carried = ov.get("items", entry["camp_items"] if entry else 0)
        if entry and entry["tomb"] and "tomb" not in ov:
            assumed.append(f"{cit['name']}: grave in {src} " + (
                "not carried over: a grave lasts one night, a new one is planned only if needed"
                if shift else "counted as already dug (notomb if not dug yet)"))
        if shift and carried and "items" not in ov:
            assumed.append(f"{cit['name']}: {plural(carried, 'camp item')} carried, taken from {src}: "
                           "assumed still carried that night (items=K corrects it)")
        vest = ov.get("vest", entry["vest"] if entry else job == "Scout")
        tamer = bool(ov.get("tamer")) or cit["job"] == "Tamer"
        if skill == "none" and entry is None and "skill" not in ov:
            assumed.append(f"{cit['name']}: hero skill unknown, taken as none (give R1-R4 / pro if they have one)")
        terms = camping_terms(nights=nights, skill=skill, panda=panda, tomb=tomb, level=0, ruin=None,
                              hidden_before=0, lighthouse=lighthouse, camp_items=0, zombies=zombies, vest=vest,
                              night=True, distance=km_, devastated=devastated)
        base = sum(terms.values()) - terms["campers"] - terms["zoneBuilding"]
        cap = round(odds_cap(job, skill) * 100)
        campers.append(Camper(cit["name"], base, cap, tomb, tamer, carried, hint))
        shown_job = f"{job}, declared Tamer" if tamer and job != "Tamer" else job
        infos.append({"job": shown_job, "skill": skill, "nights": nights, "tomb": tomb, "vest": vest, "tamer": tamer})

    # --- resources -------------------------------------------------------------------
    floor_ok = bool(z) and not future and z.get("seen_today", False)
    floor_items = sum(_zone_item_count(z, u) for u in ITEM_UIDS) if floor_ok else 0
    floor_steaks = _zone_item_count(z, STEAK_UID) if floor_ok else 0
    carried_total = sum(c.carried for c in campers)
    pool = carried_total + camp_items + floor_items
    if floor_items:
        assumed.append(f"{floor_items} Groundsheet / Festering Flesh lie on the zone's floor (Fata items "
                       "of today): counted as available, someone must pick them up")
    steaks_given = steaks >= 0
    has_tamer = any(i["tamer"] for i in infos)
    if steaks < 0:
        steaks = floor_steaks if has_tamer else 0   # a steak matters only with a Tamer's dog
        if steaks:
            assumed.append(f"{plural(steaks, 'steak')} on the zone's floor (Fata items of today): counted, someone "
                           "must pick them up")
    n_tamers = sum(1 for c, i in zip(campers, infos) if i["tamer"] and not c.tomb)
    for c, i in zip(campers, infos):
        c.tamer = i["tamer"]
    if n_tamers:
        assumed.append("Tamer's dog: assumed not used yet today; the dog digs the Tamer's grave for free"
                       + (f", or with a steak also improves the zone +5 ({plural(steaks, 'steak')} available)"
                          if steaks else ""))
    elif steaks and steaks_given:
        assumed.append(f"{plural(steaks, 'steak')}: no Tamer in the group, unused")
    ap_arg = None if ap < 0 else ap

    sol = solve(campers, level=camp_level, ruin=ruin, hidden_before=hidden_before, ap=ap_arg,
                defense_items=defense_items, pool=pool, steaks=steaks, slots=slots, objective=objective)
    pos = position_terms(len(campers), ruin, hidden_before)

    # --- output ----------------------------------------------------------------------
    n = len(campers)
    lines = [header("Group camping", meta)]
    lines.append(f"Night of day {target} ({ref})" + (": a projection from today's data." if future else "."))
    where = coords + (f", {ruin_label(ruin)}" if ruin else "")
    slots_txt = ""
    if ruin and ruin.get("camp_slots") is not None and ruin["camp_slots"] >= 0:
        slots_txt = f" ({plural(ruin['camp_slots'], 'place')})"
    lines.append(f"Zone {where}{slots_txt}, {km_} km. Camp bonus now +{camp_level}%. "
                 f"{plural(zombies, 'zombie')}" + (" (today)" if not future else "") + ".")
    if sol is None:
        lines.append("No feasible plan: the AP given do not allow the zone level or the graves needed.")
        return "\n".join(lines)
    pieces = []
    if sol.improves:
        pieces.append(f"{sol.improves}× improve ({sol.improves} AP)")
    if sol.installs:
        pieces.append(f"{sol.installs}× install ({sol.installs} AP + {plural(sol.installs, 'defensive item')})")
    if sol.boosts:
        pieces.append(f"{sol.boosts}× steak-fed dog (+5%, {plural(sol.boosts, 'steak')}, 0 AP)")
    plan = ", ".join(pieces) if pieces else "no upgrade"
    graves = []
    if sol.paid:
        graves.append(f"{plural(sol.paid, 'grave')} dug at 1 AP each")
    if sum(1 for g in sol.grave if g == "dog"):
        graves.append(f"{plural(sum(1 for g in sol.grave if g == 'dog'), 'grave')} dug by the Tamer's dog (0 AP)")
    if sol.boosts:
        graves.append(f"{plural(sol.boosts, 'grave')} dug by a steak-fed dog")
    gtxt = ", ".join(graves) if graves else "no grave to dig"
    lvl = f"camp bonus +{camp_level}% -> +{sol.level}%" if sol.level != camp_level else f"camp bonus stays +{camp_level}%"
    ap_txt = f"AP used {sol.ap} of {ap}" if ap_arg is not None else f"{sol.ap} AP needed"
    allcap = all(o >= c.cap for o, c in zip(sol.odds, campers))
    lines.append("")
    lines.append(f"Plan: {plan}; {gtxt}; {lvl}; {ap_txt}."
                 + (" Everyone at their cap." if allcap else " Not everyone can reach the cap with these resources."))
    matters = n > 1 and order_matters(campers, sol, pos, sol.level)
    lines.append("Hiding order (after the upgrades, after 19:00):" if matters else
                 "Hiding order: any order (nobody's odds change), after the upgrades and after 19:00:")
    moved = []
    for p, k in enumerate(sol.order):
        c, inf = campers[k], infos[k]
        desc = [inf["job"]]
        if inf["skill"] != "none":
            desc.append(skill_label(inf["skill"]))
        desc.append(plural(inf["nights"], "night"))
        g = sol.grave[k]
        desc.append({"dug": "grave already dug", "paid": "digs a grave (1 AP)", "dog": "grave by the dog",
                     "boost": "grave by the dog + steak", "": ""}[g])
        if sol.items[k]:
            desc.append(plural(sol.items[k], "camp item"))
        desc = [d for d in desc if d]
        extra = []
        if pos[p] < 0 and sol.odds[k] >= c.cap:
            extra.append(f"{pos[p]:+d} crowd/ruin absorbed")
        elif pos[p]:
            extra.append(f"{pos[p]:+d} crowd/ruin")
        cap_txt = f"cap {c.cap}" + ("".join(", " + e for e in extra))
        prefix = f"  {_ord(p)} " if matters else "  - "
        lines.append(f"{prefix}{c.name} ({', '.join(desc)})  {sol.odds[k]}% ({cap_txt})")
        if sol.items[k] != c.carried:
            moved.append((k, sol.items[k] - c.carried))
    lines.append(f"Expected survivors {sol.total / 100:.2f} / {n}." + ("" if objective == "expected" else
                                                                      f" Lowest {min(sol.odds)}%."))
    if moved:
        gives = [[campers[k].name, -d] for k, d in moved if d < 0]
        takes = [[campers[k].name, d] for k, d in moved if d > 0]
        steps = []
        for t in takes:
            for g in gives:
                n_ = min(t[1], g[1])
                if n_:
                    steps.append(f"{g[0]} gives {plural(n_, 'camp item')} to {t[0]}")
                    t[1] -= n_
                    g[1] -= n_
            if t[1]:
                src = " / ".join(x for x in ((f"the {camp_items} extra" if camp_items else ""),
                                              ("the zone's floor" if floor_items else "")) if x) or "the pool"
                steps.append(f"{t[0]} takes {plural(t[1], 'camp item')} from {src}")
        for g in gives:
            if g[1]:
                steps.append(f"{g[0]} leaves {plural(g[1], 'camp item')} unused")
        lines.append("Camp items: " + "; ".join(steps) + ".")
    # --- carry-over: AP beyond the plan --------------------------------------------------
    if ap_arg is not None and ap_arg > sol.ap:
        spare = ap_arg - sol.ap
        best = None
        for i in range(spare + 1):
            for j in range(min(defense_items - sol.installs, spare - i) + 1):
                ti, tj = sol.improves + i, sol.installs + j
                if not level_ok(camp_level, ti + sol.boosts, tj):
                    continue
                tot = camp_level + IMPROVE_LEVEL * (ti + sol.boosts) + INSTALL_LEVEL * tj
                k = (-tot, i + j, j)
                if best is None or k < best[0]:
                    best = (k, i, j, tot)
        if best:
            _, i, j, tot = best
            keep = lambda lv: max(0, lv - NIGHTLY_DROP)
            if keep(tot) > keep(sol.level):
                ex = ", ".join(([f"{i}× improve"] if i else []) + ([f"{j}× install"] if j else []))
                nxt = "the next night" if future else "tomorrow"
                lines.append(f"Optional, for later nights only (no effect on these odds): {ex} ({i + j} AP) -> "
                             f"+{tot}% that night, +{keep(tot)}% left {nxt} (only the bonus above +{NIGHTLY_DROP}% "
                             f"survives the night; now +{keep(sol.level)}% would be left).")
    # --- assumptions ---------------------------------------------------------------------
    lines.append("")
    lines.append("Assumptions:")
    lines.append(f"- Zombies: {zombie_note}.")
    lines += [f"- {a}" for a in assumed]
    if hidden_before:
        lines.append(f"- {plural(hidden_before, 'citizen')} outside the group already hidden on the zone: counted.")
    lines.append(f"- Objective: {'most expected survivors (sum of the odds), then the best lowest odds' if objective == 'expected' else 'best lowest odds, then the most expected survivors'}; "
                 "then fewest defensive items, paid graves, AP, steaks, dog uses.")
    lines.append(f"- Camp items (Groundsheet, Festering Flesh: +5% each, kept, in the rucksack): at most {slots} "
                 "per camper, handed over before hiding. A grave helps its digger only. Tired campers "
                 "(no AP) and dog uses already spent today are not modelled; zombies count at hide time.")
    return "\n".join(lines)
