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
    fata_plan_upgrades, is_panda, lighthouse_built, odds_cap, plan_upgrade_text, resolve_camp_level,
    resolve_night, ruin_term, skill_label, typed_plan, zone_reading,
)
from .risk import _zone_freshness, _zone_threat, fmt_items
from .cp import citizen_key
from .geo import fmt_xy, km, xy
from .towndata import plans_for_citizen, plans_for_zone

MAX_CAMPERS = 6
MAX_NIGHTS = 6
BASE_AP = 6      # AP each citizen has in a day before drinking / eating / drugs
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


@dataclass
class NightPlan:
    """One night of the chain: the zone level it starts from, the Fata plan's upgrades counted in
    it, the campers' values and the solution."""
    target: int
    night: dict
    zombies: int
    zombie_note: str
    start: int                      # zone level the solver starts from (Fata plan upgrades included)
    plan_up: dict | None            # fata_plan_upgrades() counted in `start`
    campers: list
    infos: list
    pos: list
    sol: Solution | None
    plan_ap: int = 0                # AP of the Fata plan's upgrades

    @property
    def future(self) -> bool:
        return self.night["future"]

    @property
    def ap_total(self) -> int:
        """AP the night needs: the plan's upgrades (when counted) + improves, installs, paid graves."""
        return (self.sol.ap if self.sol else 0) + self.plan_ap


def _make_camper(info: dict, k: int, ctx: dict, zombies: int) -> Camper:
    """The camper of night k of the chain (k = nights after the first): one more camping night
    each, no grave carried over (tg_tomb is reset every night), everything else unchanged."""
    nights = info["nights"] + k
    tomb = info["tomb"] and k == 0
    terms = camping_terms(nights=nights, skill=info["skill"], panda=ctx["panda"], tomb=tomb, level=0, ruin=None,
                          hidden_before=0, lighthouse=ctx["lighthouse"], camp_items=0, zombies=zombies,
                          vest=info["vest"], night=True, distance=ctx["km"], devastated=ctx["devastated"])
    base = sum(terms.values()) - terms["campers"] - terms["zoneBuilding"]
    cap = round(odds_cap(info["job"], info["skill"]) * 100)
    return Camper(info["name"], base, cap, tomb, info["tamer"], info["carried"], info["hint"])


def _plan_night(data: dict, cell: tuple, tgt: int, k: int, *, infos: list, ctx: dict, start: int,
                plan_up: dict | None, ruin: dict | None, hidden_before: int, ap: int | None,
                defense_items: int, pool: int, steaks: int, slots: int, objective: str) -> NightPlan:
    """The per-night solve: the campers of night k on the zone at level `start`, with the
    defensive items and steaks still left. `ap` is the group budget (None = unlimited); the Fata
    plan's upgrades of a future night come out of it (they are counted as done that night)."""
    night = resolve_night(data, tgt)
    _, _, zombies, zombie_note = zone_reading(data, cell, night)
    campers = [_make_camper(inf, k, ctx, zombies) for inf in infos]
    plan_ap = plan_up["improves"] if plan_up else 0
    budget = ap if ap is None or not night["future"] else max(0, ap - plan_ap)
    sol = solve(campers, level=start, ruin=ruin, hidden_before=hidden_before, ap=budget,
                defense_items=defense_items, pool=pool, steaks=steaks, slots=slots, objective=objective)
    pos = position_terms(len(campers), ruin, hidden_before)
    shown = [{**inf, "nights": inf["nights"] + k, "tomb": inf["tomb"] and k == 0} for inf in infos]
    return NightPlan(tgt, night, zombies, zombie_note, start, plan_up, campers, shown, pos, sol, plan_ap)


def _plan_pieces(sol: Solution) -> tuple[str, str]:
    """('2× improve (2 AP), ...' or 'no upgrade', 'N graves dug at 1 AP each, ...' or 'no grave to dig')."""
    pieces = []
    if sol.improves:
        pieces.append(f"{sol.improves}× improve ({sol.improves} AP)")
    if sol.installs:
        pieces.append(f"{sol.installs}× install ({sol.installs} AP + {plural(sol.installs, 'defensive item')})")
    if sol.boosts:
        pieces.append(f"{sol.boosts}× steak-fed dog (+5%, {plural(sol.boosts, 'steak')}, 0 AP)")
    graves = []
    if sol.paid:
        graves.append(f"{plural(sol.paid, 'grave')} dug at 1 AP each")
    if sum(1 for g in sol.grave if g == "dog"):
        graves.append(f"{plural(sum(1 for g in sol.grave if g == 'dog'), 'grave')} dug by the Tamer's dog (0 AP)")
    if sol.boosts:
        graves.append(f"{plural(sol.boosts, 'grave')} dug by a steak-fed dog")
    return ", ".join(pieces) if pieces else "no upgrade", ", ".join(graves) if graves else "no grave to dig"


def _camp_item_steps(campers: list, sol: Solution, camp_items: int, floor_items: int) -> str:
    """'A gives 1 camp item to B; ...' for the items that change hands, or ''."""
    moved = [(k, sol.items[k] - c.carried) for k, c in enumerate(campers) if sol.items[k] != c.carried]
    if not moved:
        return ""
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
    return "Camp items: " + "; ".join(steps) + "."


def _absorbable(level_after: int) -> int:
    """Improves that can still be done on a night ending at `level_after`: each must start below 50."""
    return max(0, -(-(MAX_LEVEL_TO_ACT - level_after) // IMPROVE_LEVEL))


def _ap_warning(np_: NightPlan, prev: NightPlan | None, n: int) -> str:
    """'' or the warning that the night needs more AP than the group's 6 each, with how many of
    the excess improves the night before could take over (each +5% carries over, -15% overnight)."""
    base = BASE_AP * n
    # tonight the plan's upgrades may be done already: only what is planned on top counts
    need = np_.sol.ap + (np_.plan_ap if np_.future else 0)
    if need <= base:
        return ""
    excess = need - base
    text = (f"Night {np_.target} needs {need} AP, more than the {base} the group has ({BASE_AP} each): "
            "drink/eat for AP")
    if prev is not None and prev.sol is not None:
        spare = max(0, base - prev.ap_total)
        movable = np_.sol.improves + (np_.plan_ap if np_.future else 0)
        k = min(excess, _absorbable(prev.sol.level), spare, movable)
        if k:
            text += (f", or do {k} of these improves the night before (night {prev.target}; each +5% carries over, "
                     f"-{NIGHTLY_DROP}% a night)")
    return text + "."


# ---------------------------------------------------------------------------
# Nearby defensive items
# ---------------------------------------------------------------------------

NEARBY_MAX_D, NEARBY_ZONES = 12, 3
# Items the game lets a camper install on the campsite ('improve' action, ActionDataService).
INSTALLABLE = {"Old Door", "Sheet Metal", "Trestle", "Mattress", "Solid Wooden Board", "Sheet of Plywood",
               "Järpen Table"}
REACH_TIERS = ((3, "the day's 6 AP"), (6, "water or food too (AP back to max once each)"),
               (9, "water and food"), (12, "water, food and a drug (Steroid / alcohol AP to 6, Twinoid 8, Coffee +4)"))


def nearby_installable(data: dict, cell: tuple) -> list[tuple]:
    """(moves, coords, zone, items) of the zones other than the camp's (and the town) holding
    items a camper can install (INSTALLABLE: not pets nor assembly parts), within
    NEARBY_MAX_D moves of `cell`, nearest first."""
    hits = []
    for z in data.get("zones", []):
        zc = xy(z)
        if zc is None or zc == cell or zc == (0, 0):
            continue
        d = abs(zc[0] - cell[0]) + abs(zc[1] - cell[1])
        found = [i for i in z.get("items", []) if i.get("name") in INSTALLABLE and not i.get("broken")]
        if d <= NEARBY_MAX_D and found:
            hits.append((d, z["coords"], z, found))
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def nearby_defense_lines(data: dict, cell: tuple, spare_nights: list[int] | None = None, n: int = 1,
                         multi: bool = False) -> list[str]:
    """A signal, not a plan input: the nearest zones of nearby_installable (3 at most), the
    reach tiers, the nights with AP to spare for the round trip (`spare_nights` = nights whose
    spare AP >= nearest trip + 1) and a pointer to the route tools. Not added to the defensive
    items pool."""
    day = data["meta"].get("day")
    hits = nearby_installable(data, cell)
    if not hits:
        return []
    lines = ["Defensive items near the camp (round trip from the camp; +1 AP to install each; the AP of the trip "
             "are not available for upgrades):",
             "  Reach: " + "; ".join(f"d <= {d} with {w}" for d, w in REACH_TIERS)
             + ". Inventory unknown: not assumed. EP not counted (scouts, bikes go further); zombies on the way are ignored."]
    for d, coords, z, found in hits[:NEARBY_ZONES]:
        lines.append(f"  {coords} {d} away, {2 * d} AP round trip: {fmt_items(found)}"
                     f"{_zone_threat(z, day)}{_zone_freshness(z, day)}")
    if any(i.get("heavy") for _, _, _, f in hits[:NEARBY_ZONES] for i in f):
        lines.append("  Heavy items: one per camper per trip.")
    if len(hits) > NEARBY_ZONES:
        far = hits[NEARBY_ZONES:]
        lines.append(f"  +{plural(len(far), 'more zone')} at {far[0][0]}-{far[-1][0]} away.")
    if spare_nights:
        hint = ("Good nights to fetch (AP to spare for the nearest round trip + 1): "
                if multi else "AP to spare tonight for the nearest round trip + 1: ")
        hint = (hint + ", ".join(str(t) for t in spare_nights) + ".") if multi else hint.rstrip(": ") + "."
        if n >= 3:
            hint += f" With {n} campers, one can fetch while the others upgrade."
        lines.append(hint)
    lines.append("For an exact route: find_expedition_path / plan_expedition_supplies with start = the camp (x,y), round trip.")
    return lines


def _spare_nights(nights: list[NightPlan], n: int, trip: int) -> list[int]:
    """Nights whose spare AP (6 each minus what the night needs) covers `trip` AP."""
    return [np_.target for np_ in nights if np_.sol is not None and BASE_AP * n - np_.ap_total >= trip]


def format_group_camping(data: dict, *, x: int | None, y: int | None, group: str = "", day_arg: int = 0,
                         ap: int = -1, defense_items: int = 0, camp_items: int = 0, steaks: int = -1,
                         slots: int = 5, camp_level: int = -1, hidden_before: int = 0,
                         objective: str = "expected", until_day: int = 0, town_id: int | None = None) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    meta = data["meta"]
    night = resolve_night(data, day_arg)
    if isinstance(night, str):
        return night
    day, target, future = night["day"], night["target"], night["future"]
    ref = night["ref"]
    first = target
    last = until_day if until_day else first
    if last < first:
        return f"Error: until_day {until_day} is before the first night (day {first}): give a day >= {first} or 0."
    if last - first + 1 > MAX_NIGHTS:
        return (f"Error: {last - first + 1} nights asked (day {first} to {last}): at most {MAX_NIGHTS} nights "
                f"in one call. Ask for day {first} to {first + MAX_NIGHTS - 1}, then continue from there.")
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
    plan_info: dict = {}
    camp_level_given = camp_level >= 0
    camp_level = resolve_camp_level(data, coords=coords, z=z, night=night, camp_level=camp_level,
                                    zone_plans=zone_plans, mine=mine, assumed=assumed, town_id=town_id,
                                    can_record=False, info=plan_info)   # read-only: nothing recorded
    plan_up = plan_info.get("plan")
    km_ = km(*cell)
    ctx = {"panda": is_panda(meta), "lighthouse": lighthouse_built(data),
           "devastated": bool(meta.get("devastated")), "km": km_}
    log = camplog.load_log(town_id) if town_id is not None else {}

    # --- per camper values: override > plan of the night > earlier plan > log > job > none ----
    infos = []
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
        if entry and entry["tomb"] and "tomb" not in ov and not shift:
            assumed.append(f"{cit['name']}: grave in {src} counted as already dug (notomb if not dug yet)")
        if shift and carried and "items" not in ov:
            assumed.append(f"{cit['name']}: {plural(carried, 'camp item')} carried, taken from {src}: "
                           "assumed still carried that night (items=K corrects it)")
        vest = ov.get("vest", entry["vest"] if entry else job == "Scout")
        tamer = bool(ov.get("tamer")) or cit["job"] == "Tamer"
        if skill == "none" and entry is None and "skill" not in ov:
            assumed.append(f"{cit['name']}: hero skill unknown, taken as none (give R1-R4 / pro if they have one)")
        shown_job = f"{job}, declared Tamer" if tamer and job != "Tamer" else job
        infos.append({"name": cit["name"], "job": job, "shown_job": shown_job, "skill": skill, "nights": nights,
                      "tomb": tomb, "vest": vest, "tamer": tamer, "carried": carried, "hint": hint})

    # --- resources (finite pools shrink from night to night) -----------------------------
    # Items seen on the zone today count for a later night too (assumed still there): they are free.
    floor_ok = bool(z) and z.get("seen_today", False)
    still = ", assumed still there" if future else ""
    floor_items = sum(_zone_item_count(z, u) for u in ITEM_UIDS) if floor_ok else 0
    floor_steaks = _zone_item_count(z, STEAK_UID) if floor_ok else 0
    floor_def = sum(i.get("count", 0) for i in (z or {}).get("items", [])
                    if floor_ok and i.get("name") in INSTALLABLE and not i.get("broken"))
    pool = sum(i["carried"] for i in infos) + camp_items + floor_items
    if floor_items:
        assumed.append(f"{floor_items} Groundsheet / Festering Flesh lie on the zone's floor (Fata items "
                       f"of today{still}): counted as available, someone must pick them up")
    if floor_def:
        defense_items += floor_def
        assumed.append(f"{plural(floor_def, 'defensive item')} lie on the zone's floor (Fata items of today{still}): added "
                       "to the defensive items available, someone must pick them up")
    steaks_given = steaks >= 0
    has_tamer = any(i["tamer"] for i in infos)
    if steaks < 0:
        steaks = floor_steaks if has_tamer else 0   # a steak matters only with a Tamer's dog
        if steaks:
            assumed.append(f"{plural(steaks, 'steak')} on the zone's floor (Fata items of today{still}): counted, someone "
                           "must pick them up")
    n_tamers = sum(1 for i in infos if i["tamer"] and not i["tomb"])
    if n_tamers:
        assumed.append("Tamer's dog: assumed not used yet today; the dog digs the Tamer's grave for free"
                       + (f", or with a steak also improves the zone +5 ({plural(steaks, 'steak')} available)"
                          if steaks else "") + (", once a night" if last > first else ""))
    elif steaks and steaks_given:
        assumed.append(f"{plural(steaks, 'steak')}: no Tamer in the group, unused")
    ap_arg = None if ap < 0 else ap
    n = len(infos)
    defense_start, steaks_start = defense_items, steaks

    # --- the chain: one solve per night, each starting from the night before ---------------
    nights: list[NightPlan] = []
    defense_left, steaks_left = defense_items, steaks
    zombie_notes: list[str] = []
    for k in range(last - first + 1):
        tgt = first + k
        start, up = camp_level, plan_up
        if k > 0:
            chain = max(0, nights[-1].sol.level - NIGHTLY_DROP)
            zp = plans_for_zone(data, coords, tgt)
            typed = typed_plan(zp, max(zp, key=lambda p: sum(any(q["citizen_id"] == c["id"] for q in p["players"])
                                                              for c in cits), default=None))
            start, up = chain, None
            if typed:
                up = fata_plan_upgrades(typed)
                start = up["after"] if up else typed["level_before"]
                if typed["level_before"] != chain:
                    assumed.append(f"Fata plan for day {tgt} types +{typed['level_before']}%; the chain from night "
                                   f"{tgt - 1} gives +{chain}%: the plan's number is used")
                ids = {q["citizen_id"] for p in zp for q in p["players"] if q["citizen_id"] in alive}
                if ids != {c["id"] for c in cits}:
                    assumed.append(f"the Fata plan for day {tgt} has other campers: the first night's group is kept")
        np_ = _plan_night(data, cell, tgt, k, infos=infos, ctx=ctx, start=start, plan_up=up, ruin=ruin,
                          hidden_before=hidden_before, ap=ap_arg, defense_items=defense_left, pool=pool,
                          steaks=steaks_left, slots=slots, objective=objective)
        if np_.zombie_note not in zombie_notes:
            zombie_notes.append(np_.zombie_note)
        if np_.sol is None:
            nights.append(np_)
            break
        nights.append(np_)
        defense_left -= np_.sol.installs
        steaks_left -= np_.sol.boosts
        for inf, got in zip(infos, np_.sol.items):   # camp items stay in the rucksack for the next night
            inf["carried"] = got

    multi = len(nights) > 1 or last > first
    near = nearby_installable(data, cell)
    nearby = []
    if near:
        trip = 2 * near[0][0] + 1
        nearby = nearby_defense_lines(data, cell, _spare_nights(nights, n, trip), n, multi=multi)
    where = coords + (f", {ruin_label(ruin)}" if ruin else "")
    slots_txt = ""
    if ruin and ruin.get("camp_slots") is not None and ruin["camp_slots"] >= 0:
        slots_txt = f" ({plural(ruin['camp_slots'], 'place')})"

    # --- output ----------------------------------------------------------------------
    lines = [header("Group camping", meta)]
    if not multi:
        np_ = nights[0]
        sol = np_.sol
        lines.append(f"Night of day {target} ({ref})" + (
            ": a projection from today's data, this night alone: the upgrades the plan would make on the "
            "nights before are not counted. For several nights make ONE call with until_day = the last night."
            if future else "."))
        bonus = (f"Camp bonus +{camp_level}% with the Fata plan's upgrades (+{plan_up['before']}% before them)"
                 if plan_up else f"Camp bonus now +{camp_level}%")
        lines.append(f"Zone {where}{slots_txt}, {km_} km. {bonus}. "
                     f"{plural(np_.zombies, 'zombie')}" + (" (today)" if not future else "") + ".")
        if plan_up:
            lines.append(plan_upgrade_text(plan_up, future) + ".")
        if sol is None:
            lines.append("No feasible plan: the AP given do not allow the zone level or the graves needed.")
            return "\n".join(lines + nearby)
        plan, gtxt = _plan_pieces(sol)
        lvl = f"camp bonus +{camp_level}% -> +{sol.level}%" if sol.level != camp_level else f"camp bonus stays +{camp_level}%"
        if ap_arg is not None:
            ap_txt = f"AP used {sol.ap + (np_.plan_ap if future else 0)} of {ap}"
        else:
            ap_txt = f"{sol.ap} AP needed"
        if plan_up and future:
            ap_txt += f" ({np_.plan_ap} of them the Fata plan's upgrades)"
        elif plan_up:
            ap_txt += f" (+{np_.plan_ap} AP if the Fata plan's upgrades are not done yet)"
        allcap = all(o >= c.cap for o, c in zip(sol.odds, np_.campers))
        lines.append("")
        lines.append(f"Plan: {plan}; {gtxt}; {lvl}; {ap_txt}."
                     + (" Everyone at their cap." if allcap else " Not everyone can reach the cap with these resources."))
        matters = n > 1 and order_matters(np_.campers, sol, np_.pos, sol.level)
        lines.append("Hiding order (after the upgrades, after 19:00):" if matters else
                     "Hiding order: any order (nobody's odds change), after the upgrades and after 19:00:")
        for p, k in enumerate(sol.order):
            c, inf = np_.campers[k], np_.infos[k]
            desc = [inf["shown_job"]]
            if inf["skill"] != "none":
                desc.append(skill_label(inf["skill"]))
            desc.append(plural(inf["nights"], "night"))
            desc.append({"dug": "grave already dug", "paid": "digs a grave (1 AP)", "dog": "grave by the dog",
                         "boost": "grave by the dog + steak", "": ""}[sol.grave[k]])
            if sol.items[k]:
                desc.append(plural(sol.items[k], "camp item"))
            desc = [d for d in desc if d]
            extra = []
            if np_.pos[p] < 0 and sol.odds[k] >= c.cap:
                extra.append(f"{np_.pos[p]:+d} crowd/ruin absorbed")
            elif np_.pos[p]:
                extra.append(f"{np_.pos[p]:+d} crowd/ruin")
            cap_txt = f"cap {c.cap}" + ("".join(", " + e for e in extra))
            prefix = f"  {_ord(p)} " if matters else "  - "
            lines.append(f"{prefix}{c.name} ({', '.join(desc)})  {sol.odds[k]}% ({cap_txt})")
        lines.append(f"Expected survivors {sol.total / 100:.2f} / {n}." + ("" if objective == "expected" else
                                                                          f" Lowest {min(sol.odds)}%."))
        steps = _camp_item_steps(np_.campers, sol, camp_items, floor_items)
        if steps:
            lines.append(steps)
        # --- carry-over: AP beyond the plan ---------------------------------------------
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
        if nearby:
            lines.append("")
            lines += nearby
        zlines = [f"- Zombies: {np_.zombie_note}."]
    else:
        names_txt = " and ".join([", ".join(i["name"] for i in infos[:-1]), infos[-1]["name"]]) if n > 1 else infos[0]["name"]
        lines.append(f"Nights {first}-{nights[-1].target}, {names_txt} at {where}{slots_txt}, {km_} km. Each night "
                     f"starts from the previous night's plan (-{NIGHTLY_DROP}% overnight); nights after "
                     f"{'tonight' if not future else 'the first'} are projections.")
        lines.append("")
        for k, np_ in enumerate(nights):
            sol = np_.sol
            head = f"Night {np_.target} ({np_.night['ref'] if np_.night['ref'] in ('tonight', 'tomorrow night') else f'in {np_.target - day} days'}):"
            if sol is None:
                lines.append(f"{head} no feasible plan (the AP given do not allow the zone level or the graves "
                             "needed); the chain stops here.")
                break
            if np_.plan_up:
                up = np_.plan_up
                if k == 0:
                    src = (f"+{up['before']}% now, then {up['creator']}'s Fata plan upgrades for +{up['pct']}% -> "
                           f"+{up['after']}%" + (": check in game whether done; if not, "
                                                 f"{up['improves']} AP first" if not future else
                                                 " counted as done"))
                else:
                    src = (f"+{up['before']}% typed in {up['creator']}'s Fata plan, its upgrades for +{up['pct']}% "
                           f"-> +{up['after']}% counted as done")
                starts = f"starts {src}."
            else:
                starts = f"starts +{np_.start}%" + (" (camp bonus given)." if k == 0 and camp_level_given else ".")
            plan, gtxt = _plan_pieces(sol)
            acts = []
            if sol.improves or sol.installs or sol.boosts:
                acts.append(plan + f" -> +{sol.level}%")
            if sol.paid or sol.boosts or any(g == "dog" for g in sol.grave):
                acts.append(gtxt)
            act = "; ".join(acts) if acts else "Nothing more needed."
            matters = n > 1 and order_matters(np_.campers, sol, np_.pos, sol.level)
            odds = []
            for p, kk in enumerate(sol.order):
                c = np_.campers[kk]
                tag = {"dug": "grave dug", "paid": "grave 1 AP", "dog": "grave by the dog",
                       "boost": "grave by the dog + steak", "": ""}[sol.grave[kk]]
                if sol.items[kk]:
                    tag += (", " if tag else "") + plural(sol.items[kk], "camp item")
                odds.append((f"{_ord(p)} " if matters else "") + f"{c.name} {sol.odds[kk]}%"
                            + (" (cap)" if sol.odds[kk] >= c.cap else f" (cap {c.cap})") + (f" [{tag}]" if tag else ""))
            lines.append(f"{head} {starts} {act}")
            lines.append(f"  {'Hide in this order' if matters else 'Any order'}: {', '.join(odds)}. "
                         f"Survivors {sol.total / 100:.2f}/{n}. Zombies {np_.zombies}.")
            steps = _camp_item_steps(np_.campers, sol, camp_items, floor_items)
            if steps:
                lines.append("  " + steps)
            warn = _ap_warning(np_, nights[k - 1] if k else None, n)
            if warn:
                lines.append("  WARNING " + warn)
        aps = []
        for np_ in nights:
            if np_.sol is None:
                break
            aps.append(f"{np_.ap_total}" + (f" (+{np_.plan_ap} if not done)" if np_.plan_ap and not np_.future else ""))
        lines.append(f"AP per night: {' / '.join(aps)}; the group has {BASE_AP * n} a day ({BASE_AP} each).")
        used_def = sum(np_.sol.installs for np_ in nights if np_.sol)
        used_st = sum(np_.sol.boosts for np_ in nights if np_.sol)
        lines.append(f"Items: defensive {used_def} used ({defense_start} available at the start)"
                     + (f"; steaks {used_st} used ({steaks_start} available)" if steaks_start or used_st else "") + ".")
        if nearby:
            lines += nearby
        zlines = [f"- Zombies: {nt}." for nt in zombie_notes]
        assumed.append("Survival: every camper is assumed to survive each night (one more camping night each "
                       "night after the first). Graves last one night: dug again when needed.")
    # --- assumptions ---------------------------------------------------------------------
    lines.append("")
    lines.append("Assumptions:")
    lines += zlines
    lines += [f"- {a}" for a in dict.fromkeys(assumed)]
    if hidden_before:
        lines.append(f"- {plural(hidden_before, 'citizen')} outside the group already hidden on the zone: counted.")
    lines.append(f"- Objective: {'most expected survivors (sum of the odds), then the best lowest odds' if objective == 'expected' else 'best lowest odds, then the most expected survivors'}; "
                 "then fewest defensive items, paid graves, AP, steaks, dog uses.")
    lines.append(f"- Camp items (Groundsheet, Festering Flesh: +5% each, kept, in the rucksack): at most {slots} "
                 "per camper, handed over before hiding. A grave helps its digger only. Tired campers "
                 "(no AP) and dog uses already spent today are not modelled; zombies count at hide time.")
    return "\n".join(lines)
