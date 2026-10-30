"""Expedition supplies: when to drink, eat and take drugs along a route, and what to carry.

Rules from the game source (myhordes-docker v5.0.6: ActionDataService, ActionEffectProvider,
ActionRequirementProvider, BeyondController, CitizenHandler, ProcessStatusEffect); the
player-facing version is in knowledge/tactics/expedition-planning.md.

- A move costs 1 point. Leaving a zone at 3+ km (geo.km) pays EP first, else AP only.
- Thirst counter: +1 per move (AP or EP). Above 10 the thirst level goes up and the counter
  restarts: thirsty at move 11, dehydrated at 22, dead at 33. Only water (and midnight) resets it
  (not food, not Hydratone, not entering town).
- Water: not thirsty → only if not drunk today and AP < max; AP to max. Thirsty → clears
  thirst; AP to max only if not drunk today. Dehydrated → becomes thirsty, no AP, so a
  second ration is needed. A second drink while not thirsty is refused by the game.
- Food: once a day, only with AP < max. 6 AP food → max AP, 7 AP food → max + 1.
- Anabolic Steroids → max AP, Twinoid → max + 2. Both are drugs: a second drug the same
  day makes the citizen an addict, so the planner uses at most one.
- Alcohol → max AP; not when already drunk or hungover (hungover the next day).
- Bloody Hot Coffee: +4 AP up to max, +1 EP up to max EP, no daily limit.
- Second Wind (hero skill, HeroSkillDataService 'super_enduring_N' + effect 'just_ap_sw'):
  adds AP up to max (never above) and EP even above max; skill levels 0-3 (what players call
  Enduring 1-4, Master = 4) give +3/+1, +3/+3, +4/+4, +4/+6. It is the day's one heroic action (status tg_hero, cleared at night),
  shared with Heroic Return and the other hero actions. Not an item: no slot.
- AP items raise AP to a level, they never add: AP left when using one is wasted.
- They also refill EP up to the shoes (1) + bike (2) part, never the scout's 2;
  Twinoid one more. Max AP is 6, 5 when wounded.
- Observation Platform level 3/4: teleport home from 1/2 km (gate open), no move.
- Labyrinth: entering town from [0|0] costs 1 AP.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

from .geo import EP_MIN_KM, MAX_PATH_AP, TOWN, fmt_xy, km
from .risk import CP_PER_CITIZEN, platform_level, teleport_range

THIRST_STEP = 10  # the counter goes up a level when it passes this


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    kind: str   # water | food | drug | alcohol | coffee
    level: int  # AP level relative to max (food/drug/alcohol), or AP added (coffee)


ITEMS = {
    "water": Item("water", "Water Ration", "water", 0),
    "food7": Item("food7", "7 AP food", "food", 1),
    "food6": Item("food6", "6 AP food", "food", 0),
    "alcohol": Item("alcohol", "alcohol", "alcohol", 0),
    "steroid": Item("steroid", "Anabolic Steroids", "drug", 0),
    "twinoid": Item("twinoid", "Twinoid 500mg", "drug", 2),
    "coffee": Item("coffee", "Bloody Hot Coffee", "coffee", 4),
    "secondwind": Item("secondwind", "Second Wind (hero action)", "hero", 0),
}
SECOND_WIND = {0: (3, 1), 1: (3, 3), 2: (4, 4), 3: (4, 6)}  # skill level 0-3 (Enduring 1-4) → (AP, EP)
ORDER = tuple(ITEMS)

# When the player doesn't say what they have: water and one 7 AP food are assumed; drugs and
# alcohol are "extras", used only if needed and then reported as an extra to find.
DEFAULT_AVAILABLE = {"water": 3, "food7": 1, "alcohol": 1, "steroid": 1, "twinoid": 1}
EXTRAS = ("steroid", "alcohol", "twinoid")

ALIASES = {
    "water": "water", "ration": "water", "waters": "water",
    "food": "food6", "food6": "food6", "food7": "food7", "meal": "food6",
    "alcohol": "alcohol", "vodka": "alcohol", "beer": "alcohol", "rhum": "alcohol",
    "steroid": "steroid", "steroids": "steroid", "anabolic": "steroid",
    "twinoid": "twinoid", "coffee": "coffee",
}


def parse_available(text: str) -> dict[str, int] | str:
    """'water=2, food7=1, twinoid' → counts; an "Error: ..." text (str) if a name is unknown."""
    if not text.strip():
        return dict(DEFAULT_AVAILABLE)
    out: dict[str, int] = {}
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, n = part.replace(":", "=").partition("=")
        key = ALIASES.get(name.strip().lower())
        if key is None:
            return f"Error: Unknown item '{name.strip()}'. Use: {', '.join(ORDER)}."
        try:
            out[key] = out.get(key, 0) + (int(n) if n.strip() else 1)
        except ValueError:
            return f"Error: Bad count in '{part}'."
    return out


@dataclass(frozen=True)
class Start:
    ap: int = 6
    ep: int | None = None        # None = full (scout 2 + shoes 1 + bike 2)
    counter: int = 0
    thirst: int = 0              # 0 ok, 1 thirsty, 2 dehydrated
    drank: bool = False          # already drank today
    ate: bool = False            # already ate today
    drugged: bool = False        # already took a drug today
    no_alcohol: bool = False     # drunk or hungover
    wounded: bool = False
    scout: bool = False
    shoes: bool = False
    bike: bool = False
    sw_ap: int = 0               # Second Wind, when the player has it (see SECOND_WIND)
    sw_ep: int = 0

    @property
    def max_ap(self) -> int:
        return 5 if self.wounded else 6

    @property
    def ext(self) -> int:
        return (2 if self.bike else 0) + (1 if self.shoes else 0)

    @property
    def max_ep(self) -> int:
        return (2 if self.scout else 0) + self.ext


# Cost, compared lexicographically (lower is better):
# dead, moves short, dehydrated at the end, times dehydrated, thirsty at the end,
# items, alcohol, drugs (alcohol is the last resort, after one drug), premium items
# (7 AP food, Twinoid: kept for when they are needed), AP wasted (only a tiebreak between
# feasible plans: keeping a Twinoid beats an AP lost while arriving with AP to spare),
# AP left at arrival, negated (EP are worth nothing in town: Second Wind or coffee goes
# where its EP still pay for moves)
ZERO = (0,) * 11
THIRST_KEY = slice(0, 5)   # the part of a cost that is the thirst outcome (death, moves short, dehydration)
SUPPLY_KEY = slice(0, 6)   # ... and the items carried
WASTE = 9                  # index of the AP wasted
PREMIUM = {"food7": 1, "twinoid": 2}  # a Twinoid is rarer than a 7 AP food


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def feasible(result: dict) -> bool:
    """The plan reaches the end: nobody dies, no move short."""
    cost = result["cost"]
    return not (cost[0] or cost[1])


class State(NamedTuple):
    """A point of the search: next move index, AP, EP, thirst counter and level, what was
    done today, and how many of each item (ORDER) were used."""
    i: int
    ap: int
    ep: int
    cnt: int
    th: int
    drank: bool
    ate: bool
    drugged: bool
    drunk: bool
    used: tuple


def carried(used: dict[str, int]) -> int:
    """Rucksack slots the used supplies take (Second Wind is an action, not an item)."""
    return sum(n for k, n in used.items() if k != "secondwind")


def plan(route: list[tuple[int, int]], start: Start, available: dict[str, int],
         *, end_ap: int = 0, slots: int = 0) -> dict:
    """Best use of `available` along `route` (zones walked, start included).

    end_ap: AP needed after the last move (1 to enter through the Labyrinth).
    slots: max items carried (0 = no limit).
    Returns {'cost', 'steps': [...], 'used': {key: n}, 'final': state}.
    """
    last = len(route) - 1
    max_ap, ext = start.max_ap, start.ext
    max_ep = start.max_ep
    avail = tuple(available.get(k, 0) for k in ORDER)
    ep0 = max_ep if start.ep is None else start.ep

    def refill(ep, plus=0):
        return max(ep, ext + plus) if ext > 0 else ep

    def use(state, k):
        """State after using item k, or None if the game (or the policy) refuses it."""
        i, ap, ep, cnt, th, drank, ate, drugged, drunk, used = state
        if used[ORDER.index(k)] >= avail[ORDER.index(k)]:
            return None
        it = ITEMS[k]
        if slots and it.kind != "hero" and sum(used) - used[ORDER.index("secondwind")] >= slots:
            return None
        waste = 0
        if it.kind == "hero":
            new = max(ap, min(ap + start.sw_ap, max_ap))
            waste = start.sw_ap - (new - ap)
            ap, ep = new, min(ep + start.sw_ep, max_ep + start.sw_ep)
        elif it.kind == "water":
            if th == 0:
                if drank or ap >= max_ap:
                    return None
                waste = min(ap, max_ap)
                ap, ep, drank, cnt = max(ap, max_ap), refill(ep), True, 0
            elif th == 1:
                if not drank:
                    waste = min(ap, max_ap)
                    ap, ep, drank = max(ap, max_ap), refill(ep), True
                th, cnt = 0, 0
            else:
                th, cnt = 1, 0
        elif it.kind == "food":
            if ate or ap >= max_ap or ap > 0:
                return None
            ap, ep, ate = max(ap, max_ap + it.level), refill(ep), True
        elif it.kind == "drug":
            if drugged or ap > 0:
                return None
            ap, ep, drugged = max(ap, max_ap + it.level), refill(ep, 1 if k == "twinoid" else 0), True
        elif it.kind == "alcohol":
            if drunk or ap > 0:
                return None
            ap, ep, drunk = max(ap, max_ap), refill(ep), True
        else:  # coffee
            if ap >= max_ap:
                return None
            new = min(max(max_ap, ap), ap + it.level)
            waste = it.level - (new - ap)
            ap, ep = new, max(ep, min(ep + 1, max_ep))
        used = tuple(n + (1 if o == k else 0) for o, n in zip(ORDER, used))
        # Second Wind costs less than an item (no slot) but is kept when not needed: it is
        # the day's heroic action (Heroic Return, ...).
        cost = (0, 0, 0, 0, 0, 0.5 if it.kind == "hero" else 1, it.kind == "alcohol", it.kind == "drug",
                PREMIUM.get(k, 0), waste, 0)
        return State(i, ap, ep, cnt, th, drank, ate, drugged, drunk, used), cost

    def move(state):
        i, ap, ep, cnt, th, drank, ate, drugged, drunk, used = state
        x, y = route[i]
        if ep > 0 and km(x, y) >= EP_MIN_KM:
            ep -= 1
        elif ap > 0:
            ap -= 1
        else:
            return None
        cnt += 1
        dehyd = 0
        if cnt > THIRST_STEP:
            th, cnt = th + 1, 0
            dehyd = th == 2
        return State(i + 1, ap, ep, cnt, th, drank, ate, drugged, drunk, used), dehyd

    @lru_cache(maxsize=None)
    def best(state):
        """(cost, choice) for the rest of the route; choice = ('move'|item key|'end'|'stuck')."""
        i, ap, ep, cnt, th = state[:5]
        options = []
        if i == last:
            if ap >= end_ap:
                options.append(((0, 0, th == 2, 0, th == 1, 0, 0, 0, 0, 0, -ap), "end"))
            else:
                options.append(((0, end_ap - ap, th == 2, 0, th == 1, 0, 0, 0, 0, 0, 0), "stuck"))
        else:
            m = move(state)
            if m is not None:
                nxt, dehyd = m
                if nxt.th >= 3:
                    options.append(((1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "move"))
                else:
                    options.append((_add(best(nxt)[0], (0, 0, 0, dehyd, 0, 0, 0, 0, 0, 0, 0)), "move"))
            else:
                options.append(((0, last - i + end_ap, th == 2, 0, th == 1, 0, 0, 0, 0, 0, 0), "stuck"))
        for k in ORDER:
            r = use(state, k)
            if r is not None:
                nxt, c = r
                options.append((_add(best(nxt)[0], c), k))
        return min(options, key=lambda o: o[0])

    state = State(0, start.ap, ep0, start.counter, start.thirst, start.drank, start.ate,
                  start.drugged, start.no_alcohol, (0,) * len(ORDER))
    cost = best(state)[0]

    # Replay the best choices into rows.
    steps = []
    while True:
        _, choice = best(state)
        i = state.i
        if choice in ("end", "stuck"):
            break
        if choice == "move":
            nxt, _ = move(state)
            if nxt.th >= 3:
                steps.append({"kind": "dead", "zone": route[i + 1]})
                break
            paid = "EP" if nxt.ep < state.ep else "AP"
            steps.append({"kind": "move", "zone": route[i + 1], "paid": paid, "ap": nxt.ap,
                          "ep": nxt.ep, "counter": nxt.cnt, "thirst": nxt.th, "move": i + 1})
            state = nxt
        else:
            nxt, c = use(state, choice)
            steps.append({"kind": "use", "item": choice, "zone": route[i], "ap_before": state.ap,
                          "ap": nxt.ap, "ep": nxt.ep, "counter": nxt.cnt, "thirst": nxt.th,
                          "waste": c[WASTE], "move": i})
            state = nxt
    best.cache_clear()
    used = {k: n for k, n in zip(ORDER, state.used) if n}
    return {"cost": cost, "steps": steps, "used": used, "final": state, "stuck_at": state.i}


EXTRA_SETS = (("steroid",), ("alcohol",), ("twinoid",), ("steroid", "alcohol"), ("alcohol", "twinoid"))
STOCK_LABEL = {"steroid": "Steroids", "alcohol": "alcohol", "twinoid": "Twinoid"}


def extra_options(route: list[tuple[int, int]], start: Start, available: dict[str, int], *,
                  end_ap: int = 0, slots: int = 0, stock: dict[str, int] | None = None) -> list[str]:
    """One line per way to cover the extras that works (one drug, alcohol, or both), with
    the slots, water and arrival it implies and the bank stock: the planner picks by slots
    and thirst, the player may prefer to keep a Twinoid."""
    out = []
    for keys in EXTRA_SETS:
        avail = {k: n for k, n in available.items() if k not in EXTRAS}
        avail.update({k: 1 for k in keys})
        r = plan(route, start, avail, end_ap=end_ap, slots=slots)
        if not feasible(r):
            continue
        final, used = r["final"], r["used"]
        name = " + ".join(ITEMS[k].label for k in keys)
        bank = ", ".join(f"{STOCK_LABEL[k]} {stock.get(k, 0)}" for k in keys) if stock is not None else ""
        out.append(f"{name}: {carried(used)} slots ({used.get('water', 0)} water), arrives "
                   f"{THIRST[final.th]} with {final.ap} AP" + (f" (bank: {bank})" if bank else ""))
    return out


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

THIRST = {0: "OK", 1: "Thirsty", 2: "Dehydrated"}


def thirst_state(counter: int) -> str:
    """State after `counter` moves without water (the counter never resets in a step table):
    a level every THIRST_STEP + 1 moves, dead at the third."""
    level = counter // (THIRST_STEP + 1)
    return THIRST[level] if level in THIRST else "DEAD"


def end_requirements(data: dict, route: list[tuple[int, int]], end: tuple[int, int]) -> tuple[list, int, str]:
    """Shorten a route home by the Observation Platform teleport; AP needed to enter.

    Returns (route, end_ap, note)."""
    if end != (0, 0) or len(route) < 2:
        return route, 0, ""
    level = platform_level(data)
    reach = teleport_range(level)
    if reach:
        # Last leg only: from the last zone farther than the teleport range.
        cut = len(route) - 1
        while cut > 0 and km(*route[cut - 1]) <= reach:
            cut -= 1
        if cut < len(route) - 1:
            z = route[cut]
            return (route[:cut + 1], 0,
                    f"Observation Platform level {level}: teleport home from "
                    f"{fmt_xy(z)} ({len(route) - 1 - cut} moves saved; needs the gate open).")
    if any(b["name"].lower() == "labyrinth" for b in data.get("buildings", []) if b.get("built")):
        return route, 1, f"Labyrinth built: entering town from {fmt_xy(TOWN)} costs 1 AP."
    return route, 0, ""


def labels(used: dict[str, int], generic: bool) -> dict[str, str]:
    """Item names for the output. With generic extras, a single 6 AP extra is reported as
    'steroid or alcohol' (either works); two extras or a Twinoid are named."""
    out = {k: it.label for k, it in ITEMS.items()}
    if generic:
        six = [k for k in ("steroid", "alcohol") if used.get(k)]
        # "either" only when no other drug is used: with a Twinoid, steroids would be a
        # second drug (addict).
        if len(six) == 1 and not used.get("twinoid"):
            out[six[0]] = "6 AP extra (Anabolic Steroids or alcohol)"
        else:
            out["steroid"], out["alcohol"] = "Anabolic Steroids (extra)", "alcohol (extra)"
        out["twinoid"] = "Twinoid 500mg (8 AP extra)"
    return out


def _ranges(moves: list[int]) -> str:
    """[16, 17, 18, 24] → '16-18, 24'."""
    out, start, prev = [], None, None
    for m in sorted(moves):
        if start is None:
            start = prev = m
        elif m == prev + 1:
            prev = m
        else:
            out.append(f"{start}-{prev}" if prev > start else str(start))
            start = prev = m
    if start is not None:
        out.append(f"{start}-{prev}" if prev > start else str(start))
    return ", ".join(out)


def _zones_label(r: dict) -> str:
    zs = r.get("zones") or [r["zone"]]
    if len(zs) == 1:
        return fmt_xy(zs[0])
    return f"{fmt_xy(zs[0])} to {fmt_xy(zs[-1])} ({len(zs)} zones)"


def _risk_what(r: dict, cp: int) -> str:
    if r["tag"] == "UNKNOWN":
        n = len(r.get("zones") or [1])
        return "never scouted, zombies unknown" if n == 1 else f"{n} zones never scouted, zombies unknown"
    if r["tag"] == "TRAPPED":
        return f"{r['zombies']} zombies seen today vs {cp} CP: blocked"
    old = f", data {r['age']} day(s) old" if r.get("age", -1) > 0 else ""
    return f"~{r['zombies']} zombies estimated{old} vs {cp} CP: may block"


def format_risks(risks: list[dict], cp: int, items: int, slots: int, cp_label: str | None = None) -> list[str]:
    """'Route risks' section: each risky zone, the way around it, or the weapons needed."""
    if not risks:
        return []
    free = (f"{max(0, slots - items)}/{slots} slots free after supplies" if slots
            else f"supplies already take {items} slot(s)")
    blocking = [r for r in risks if r["tag"] != "UNKNOWN"]
    lines = ["", f"**Route risks** ({cp_label or f'{cp} CP'})"
             + (" — cannot pass safely unless you re-route or carry weapons" if blocking else "")]
    for r in risks:
        z = _zones_label(r)
        moves = ("moves " if len(r["moves"]) > 1 else "move ") + _ranges(r["moves"])
        if r.get("waypoint"):
            around = "it is a waypoint of the trip"
        elif r["detour_ap"] is None:
            around = f"no way around within {MAX_PATH_AP} AP"
        elif r["detour_ap"] <= 0:
            around = "a way around costs no extra AP but is riskier elsewhere"
        else:
            around = f"re-route around it: +{r['detour_ap']} AP"
        if r["kills"]:
            weapons = f"carry weapons to kill {r['kills']} zombie(s) ({free})"
        elif r["tag"] == "UNKNOWN":
            weapons = f"carry a weapon or two just in case ({free})"
        else:
            weapons = ""
        lines.append(f"- ⚠ {z}, {moves}: {_risk_what(r, r.get('cp', cp))} → {around}" + (f"; or {weapons}" if weapons else ""))
    return lines


def _use_label(s: dict, names: dict[str, str]) -> str:
    """Item name; water that gives no AP (already drunk for AP today, or Dehydrated) is
    there for the thirst only."""
    label = names[s["item"]]
    if s["item"] == "water" and s["ap"] == s["ap_before"]:
        label += " (thirst only, no AP)"
    return label


def waypoint_moves(steps: list[dict], waypoints: list[tuple[int, int]]) -> set[int]:
    """Moves that reach each waypoint, in order (the last one is the arrival)."""
    hits, pending = set(), list(waypoints)
    for s in steps:
        if s["kind"] == "move" and pending and s["zone"] == pending[0]:
            hits.add(s["move"])
            pending.pop(0)
    return hits


def _turns(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The zones where a walk changes direction, plus its last zone."""
    out = []
    for a, b, c in zip(path, path[1:], path[2:]):
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            out.append(b)
    return out + path[-1:]


def itinerary(steps: list[dict], route: list[tuple[int, int]], ending: str,
              names: dict[str, str] | None = None, risky: dict | None = None,
              waypoints: list[tuple[int, int]] | None = None,
              pick_notes: dict[int, str] | None = None) -> list[str]:
    """One numbered list in walking order: each walk (turning points only, moves, what is
    left) and, between walks, what to use where. A walk ends where something happens:
    an item is used, a waypoint is reached, thirst changes, a risky zone starts.
    pick_notes: {route move: text}, one line after the walk that reaches a pickup."""
    names = names or {k: it.label for k, it in ITEMS.items()}
    risky = risky or {}
    reached = waypoint_moves(steps, waypoints or [])
    pick_notes = pick_notes or {}
    out: list[str] = []
    walk: list[dict] = []
    pos = route[0]
    prev_th, prev_risk = None, None

    def fmt(z):
        return f"[{z[0]}/{z[1]}]"

    def flush(events: list[str]):
        nonlocal walk, pos
        if not walk:
            return
        path = [pos] + [w["zone"] for w in walk]
        last = walk[-1]
        n = len(walk)
        text = (f"Walk {fmt(pos)} → " + " → ".join(fmt(z) for z in _turns(path))
                + f" ({n} move{'s' if n > 1 else ''}) — {last['ap']} AP, {last['ep']} EP left")
        out.append(text + "".join(f"; {e}" for e in events))
        pos, walk = last["zone"], []

    for s in steps:
        if s["kind"] == "use":
            flush([])
            when = f" (at {s['ap_before']} AP, exception)" if s["ap_before"] else ""
            out.append(f"At {fmt(s['zone'])}{when}: **{_use_label(s, names)}** → {s['ap']} AP, "
                       f"{s['ep']} EP, {THIRST[s['thirst']]}")
            pos = s["zone"]
            prev_th = s["thirst"]
        elif s["kind"] == "move":
            walk.append(s)
            events = []
            gid, what = risky.get(s["zone"], (None, None))
            if gid is not None and gid != prev_risk:
                events.append(f"⚠ {fmt(s['zone'])}: {what}")
            prev_risk = gid
            if prev_th is not None and s["thirst"] > prev_th:
                events.append(f"becomes **{THIRST[s['thirst']]}** at {fmt(s['zone'])}")
            prev_th = s["thirst"]
            if s["move"] in reached:
                events.append(f"**waypoint {fmt(s['zone'])} reached**")
            if events or s["move"] in pick_notes:
                flush(events)
            if s["move"] in pick_notes:
                out.append(pick_notes[s["move"]])
        else:
            flush([])
            out.append(f"At {fmt(s['zone'])}: **dies of dehydration**")
    moves = [s for s in steps if s["kind"] == "move"]
    if walk:
        flush([ending])
    elif moves and out:
        out[-1] += f"; {ending}"
    return [f"{i}. {line}" for i, line in enumerate(out, 1)]


def format_plan(route: list[tuple[int, int]], start: Start, result: dict, *,
                title: str, notes: list[str], slots: int = 0, end_ap: int = 0,
                step_table: bool = False, teleport: bool = False, generic_extras: bool = False,
                risks: list[dict] | None = None, cp: int = CP_PER_CITIZEN,
                waypoints: list[tuple[int, int]] | None = None, options: list[str] | None = None,
                pick_verdict: str = "", pick_notes: dict[int, str] | None = None,
                extra_warn: list[str] | None = None, cp_label: str | None = None) -> str:
    """generic_extras: the player didn't list their items, so drugs/alcohol are extras to find.
    waypoints: zones to flag when reached. options: other ways to cover the extras.
    pick_verdict / pick_notes / extra_warn: the pickups' feasibility line, their rucksack
    lines by route move, and their warnings. cp_label: CP text for the risks header."""
    cost, steps, used = result["cost"], result["steps"], result["used"]
    names = labels(used, generic_extras)
    dead, short, end_dehyd, n_dehyd, end_thirsty, _, n_alc, n_drugs, _, waste, _ = cost
    n_items = carried(used)
    hero = used.get("secondwind")
    used = {k: n for k, n in used.items() if k != "secondwind"}
    moves = len(route) - 1
    final = result["final"]

    lines = [f"## {title}",
             f"{moves} moves · start {start.ap} AP, "
             f"{start.max_ep if start.ep is None else start.ep} EP, thirst counter {start.counter}, "
             f"{THIRST[start.thirst]} · max AP {start.max_ap}, max EP {start.max_ep}"]
    lines += [f"{n}" for n in notes if n]
    lines.append("")

    extras = {k: n for k, n in used.items() if generic_extras and k in EXTRAS}
    base = {k: n for k, n in used.items() if k not in extras}
    if used and (short or dead):
        carry = ", ".join(f"{n} × {names[k]}" for k, n in used.items())
        lines.append(f"**Uses (partial plan):** {carry}")
    elif used:
        carry = ", ".join(f"{n} × {names[k]}" for k, n in base.items()) or "nothing else"
        lines.append(f"**Bring:** {carry} → **{sum(base.values())} slot(s)**"
                     + (f" of {slots} free" if slots and not extras else ""))
        if extras:
            more = ", ".join(f"{n} × {names[k]}" for k, n in extras.items())
            lines.append(f"**Extra needed:** {more} → **{sum(used.values())} slot(s) in total**"
                         + (f" of {slots} free" if slots else ""))
        if used.get("water", 0) >= 2:
            lines.append("  (a Water Cooler Bottle holds up to 3 rations in one slot)")
    elif not (short or dead):
        lines.append("**Bring:** nothing — the route fits in the starting AP/EP.")
    if hero:
        lines.append(f"**Hero action:** Second Wind (+{start.sw_ap} AP up to max, +{start.sw_ep} EP), no slot.")
    if options:
        lines.append("**Ways to cover the extra** (bank stock in brackets; pick by what the bank can spare):")
        lines += [f"  - {o}" for o in options]

    if dead:
        verdict = "**DIES of dehydration on the way** — the route is too long for the water available."
    elif short:
        verdict = (f"**NOT FEASIBLE:** {short} more point(s) needed from move {result['stuck_at']}"
                   f" ({fmt_xy(route[result['stuck_at']])}) — "
                   "carry more AP items, or plan a shorter route.")
    else:
        th = final.th
        verdict = (f"Arrives **{THIRST[th]}** with {final.ap} AP, {final.ep} EP left"
                   f" · {waste} AP wasted")
    lines.append(verdict)
    if pick_verdict:
        lines.append(pick_verdict)

    warn = list(extra_warn or [])
    ok = not (short or dead)
    if ok and end_dehyd:
        warn.append("Arrives DEHYDRATED: needs 2 rations at arrival, or dies tonight.")
    elif ok and end_thirsty:
        warn.append("Arrives Thirsty: needs a ration at arrival (not enough water, or no way to avoid it).")
    if n_dehyd and not end_dehyd and ok:
        warn.append("Gets Dehydrated on the way: drink as soon as possible (one ration only makes Thirsty).")
    for s in steps:
        if s["kind"] == "use" and s["item"] == "water" and s["ap_before"] > 0 and s["waste"]:
            warn.append(f"Drinks at {s['ap_before']} AP before move {s['move'] + 1} (exception: "
                        "waiting for 0 AP would mean more thirst).")
    if generic_extras and len([k for k in ("steroid", "alcohol") if used.get(k)]) == 1 and not used.get("twinoid"):
        warn.append("The 6 AP extra: Anabolic Steroids (a drug: never a second drug the same day) "
                    "or alcohol (Drunk today, hungover tomorrow).")
    else:
        if n_drugs:
            warn.append("Uses a drug: a second drug today makes you an addict (permanent; must take a drug every day).")
        if n_alc:
            warn.append("Uses alcohol: Drunk today (-20% finding items when digging), hungover tomorrow (no alcohol).")
    if hero:
        warn.append("Second Wind is today's heroic action: no Heroic Return or other hero action "
                    "today (it resets at night).")
    drank_today = start.drank or any(s["kind"] == "use" and s["item"] == "water" for s in steps)
    if not drank_today and not dead:
        warn.append("No water today so far: without a ration before the attack, thirst goes up tonight.")
    if slots and n_items >= slots:
        warn.append(f"Uses every free slot ({slots}): nothing can be brought back unless items are consumed first.")
    if warn:
        lines.append("")
        lines.append("**Warnings**")
        lines += [f"- {w}" for w in warn]
    risks = risks or []
    lines += format_risks(risks, cp, n_items, slots, cp_label)
    risky = {z: (i, _risk_what(r, r.get("cp", cp))) for i, r in enumerate(risks) for z in (r.get("zones") or [r["zone"]])}

    if not step_table:
        lines += ["", "**Itinerary** (in walking order; every move: step_table=True)"]
        ending = ("**stuck, out of points**" if short else "**dead**" if dead
                  else "then **teleport home**" if teleport else "**arrival**")
        lines += itinerary(steps, route, ending, names, risky, waypoints, pick_notes)
        return "\n".join(lines)
    reached = waypoint_moves(steps, waypoints or [])

    lines += ["", "| # | Zone | km | Action | AP | EP | Counter | Thirst |", "|---|---|---|---|---|---|---|---|"]
    for s in steps:
        z = f"[{s['zone'][0]}/{s['zone'][1]}]"
        if s["kind"] == "move":
            flag = " ⚠" if s["zone"] in risky else ""
            flag += " · waypoint" if s["move"] in reached else ""
            flag += " · pickup" if s["move"] in (pick_notes or {}) else ""
            lines.append(f"| {s['move']} | {z} | {km(*s['zone'])} | move ({s['paid']}){flag} | {s['ap']} | {s['ep']} "
                         f"| {s['counter']} | {THIRST[s['thirst']]} |")
        elif s["kind"] == "use":
            lines.append(f"| | {z} | | **{_use_label(s, names)}**"
                         + (f" (at {s['ap_before']} AP)" if s["ap_before"] else "")
                         + f" | {s['ap']} | {s['ep']} | {s['counter']} | {THIRST[s['thirst']]} |")
        else:
            lines.append(f"| | {z} | | **dies (dehydration)** | | | | |")
    return "\n".join(lines)
