"""Things picked up on an expedition: rucksack slots and heavy items along the route.

Rules from the game source (InventoryHandler::getSize, getHeavyItemSize; shield_off status),
player-facing version in knowledge/tactics/expedition-planning.md:

- The rucksack holds `slots` items; a picked item takes a slot, heavy or not. A used
  supply frees its slot. Supplies and pickups are checked at each pickup: supplies still
  to be used (a use at the pickup zone counts as already made) + items picked so far
  must fit; supplies are never dropped to make room, the plan is redone with fewer slots
  at departure instead.
- A citizen carries one heavy item (a bike or trolley counts as that item). A Guardian
  with the shield lowered carries two but the group loses the shield's 2 CP from the
  moment the 2nd one is carried.
"""

import re
from dataclasses import dataclass, field

from . import supplies
from .pathing import reach_indices
from .geo import fmt_xy, zone_map
from .risk import is_defense

GUARDIAN_CP_LOSS = 2
DEFENSE_WORDS = {"defense", "defence", "defenses", "defences", "defensive"}


@dataclass
class Pickup:
    zone: tuple[int, int]
    spec: str                    # what the player asked for ("blueprint", "defense", "old door")
    count: int                   # items to pick up
    heavy: int = 0               # how many of them are heavy
    names: list[str] = field(default_factory=list)  # what Fata saw there that matches
    warning: str = ""
    wp: int = 0                  # index of the zone in the route points (set by the caller)


def parse(text: str) -> list[tuple[str, str, int]] | str:
    """'14,2: blueprint; -3,8: 2 defense' → [(zone text, what, count)], or an error text."""
    out = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        zone, sep, spec = part.rpartition(":")
        if not sep or not zone.strip() or not spec.strip():
            return f"Error: can't read the pickup '{part}' (use 'x,y: item', e.g. '14,2: blueprint')."
        spec, count = spec.strip(), 1
        m = re.match(r"^(\d+)\s*[x×]?\s+(.+)$", spec) or re.match(r"^(.+?)\s*[x×]\s*(\d+)$", spec)
        if m:
            a, b = m.groups()
            spec, count = (b, int(a)) if a.isdigit() else (a, int(b))
        if count < 1:
            return f"Error: pickup '{part}': the count must be at least 1."
        out.append((zone.strip(), spec.strip(), count))
    return out


def resolve(data: dict, entries: list[tuple[tuple[int, int], str, int]]) -> list[Pickup]:
    """Match each (zone, what, count) against the zone's ground items. `what` is `defense`
    (defensive object or part), `heavy`, or part of an item name. Heavy-first when the
    zone has several matches (worst case for carrying). What Fata did not see is kept:
    light (heavy for the word `heavy`), with a warning."""
    zones = zone_map(data)
    day = data["meta"].get("day")
    seen_day = f" (data from day {day})" if day is not None else ""
    out = []
    for zone, spec, count in entries:
        z = zones.get(zone) or {}
        key = spec.lower()
        if key in DEFENSE_WORDS:
            pred = is_defense
        elif key == "heavy":
            pred = lambda i: bool(i.get("heavy"))  # noqa: E731
        else:
            pred = lambda i, k=key: k in i["name"].lower()  # noqa: E731
        found: list[dict] = []
        for it in z.get("items") or []:
            if pred(it):
                found += [it] * it["count"]
        found.sort(key=lambda i: not i.get("heavy"))  # stable: heavy first
        taken = found[:count]
        p = Pickup(zone, spec, count, heavy=sum(1 for i in taken if i.get("heavy")),
                   names=[i["name"] for i in taken])
        short = count - len(taken)
        if short:
            # Not on the ground per Fata: assume light (the word `heavy` means heavy).
            if key == "heavy":
                p.heavy += short
            blueprint = "blueprint" in key and z.get("ruin")
            if not blueprint:
                if taken:
                    p.warning = (f"Pickup {spec} at {fmt_xy(zone)}: Fata saw only {len(taken)} of "
                                 f"{count} there{seen_day}; the other {short} assumed "
                                 f"{'heavy' if key == 'heavy' else 'light'}.")
                else:
                    p.warning = (f"Pickup {spec} at {fmt_xy(zone)}: not seen there by Fata{seen_day}; "
                                 f"assumed {'heavy' if key == 'heavy' else 'light'}.")
        out.append(p)
    return out


def heavy_check(picks: list[Pickup], *, bike: bool, trolley: bool, guardian: bool) -> dict | str:
    """Heavy items carried along the trip. Returns an error text when more than one heavy
    item is carried without a Guardian (or more than two with one), else
    {'drop_from': points index from which the group CP is 2 lower (None = never),
     'at_pickup': Pickup that causes it (None = from departure), 'max': heavy items at most}."""
    held = [n for n, f in (("bike", bike), ("trolley", trolley)) if f]
    cap = 2 if guardian else 1
    drop, cause = (0, None) if len(held) >= 2 else (None, None)
    most = len(held)

    def too_many() -> str:
        text = f"Error: that is {len(held)} heavy items ({', '.join(held)}): "
        if guardian:
            return text + "even a Guardian with the shield lowered carries only 2."
        return (text + "a citizen carries only 1 (a bike and a trolley count). A Guardian can carry 2 "
                f"(guardian=True), at -{GUARDIAN_CP_LOSS} CP for the group. A Tamer can send one home with "
                "the dog first: plan two trips, split at the send zone.")

    if len(held) > cap:
        return too_many()
    for p in sorted(picks, key=lambda p: p.wp):
        if not p.heavy:
            continue
        held += [f"{(p.names or [p.spec])[min(i, len(p.names) - 1)] if p.names else p.spec} "
                 f"at {fmt_xy(p.zone)}" for i in range(p.heavy)]
        most = max(most, len(held))
        if len(held) > cap:
            return too_many()
        if len(held) >= 2 and drop is None:
            drop, cause = p.wp, p
    return {"drop_from": drop, "at_pickup": cause, "max": most}


def leg_cps(cp: int, legs: int, drop_from: int | None) -> list[int]:
    """CP per leg; legs from index `drop_from` on (the leg that starts at points[drop_from])
    have the Guardian's shield lowered."""
    return [cp if drop_from is None or i < drop_from else max(0, cp - GUARDIAN_CP_LOSS)
            for i in range(legs)]


def timeline(route: list[tuple[int, int]], points: list[tuple[int, int]], picks: list[Pickup],
             result: dict, slots: int) -> list[dict]:
    """Rucksack at each pickup the route reaches: supplies still to be used + items picked so
    far. [{'pickup', 'move', 'supplies', 'picked', 'used', 'over'}] in walking order."""
    reached = reach_indices(route, points)
    uses = [s["move"] for s in result["steps"] if s["kind"] == "use" and s["item"] != "secondwind"]
    rows, picked = [], 0
    for p in sorted(picks, key=lambda p: p.wp):
        picked += p.count
        m = reached[p.wp] if p.wp < len(reached) else None
        if m is None:
            continue
        left = sum(1 for u in uses if u > m)
        rows.append({"pickup": p, "move": m, "supplies": left, "picked": picked,
                     "used": left + picked, "over": max(0, left + picked - slots)})
    return rows


def fit(route: list[tuple[int, int]], points: list[tuple[int, int]], picks: list[Pickup],
        slots: int, plan_fn) -> dict:
    """The supplies plan that leaves room for the pickups. plan_fn(departure_slots) → plan.

    Tries `slots`, then one fewer ... (never more than the pickups need): a plan that
    does worse than the first one (dies, runs out of AP, ends Dehydrated or Thirsty: it
    dropped a supply the trip needs) is never accepted to make room. Returns {'result',
    'rows', 'departure_slots', 'missing'}; missing > 0 = no plan fits (the one with the
    least overflow is returned); rows is empty when there are no pickups or the supplies
    plan itself is not feasible."""
    n = sum(p.count for p in picks)
    best, first = None, None
    for k in range(n + 1):
        s = slots - k
        if s < 1:
            break
        res = plan_fn(s)
        if k == 0:
            first = res["cost"][supplies.THIRST_KEY]
            if not supplies.feasible(res):
                return {"result": res, "rows": [], "departure_slots": s, "missing": 0}
        elif res["cost"][supplies.THIRST_KEY] > first:
            break
        rows = timeline(route, points, picks, res, slots)
        over = max((r["over"] for r in rows), default=0)
        cand = {"result": res, "rows": rows, "departure_slots": s, "missing": over}
        if over == 0:
            return cand
        if best is None or over < best["missing"]:
            best = cand
    return best


def _supplies(n: int) -> str:
    return f"{n} supply" if n == 1 else f"{n} supplies"


def verdict(fitted: dict, slots: int, heavy: dict) -> str:
    """One line: are the pickups feasible, and why not."""
    rows = fitted["rows"]
    if not rows:
        return ""
    peak = max(r["used"] for r in rows)
    if fitted["missing"]:
        worst = max(rows, key=lambda r: r["over"])
        z = worst["pickup"].zone
        return (f"**Pickups NOT FEASIBLE:** at {fmt_xy(z)} the rucksack needs {worst['used']} slots "
                f"({_supplies(worst['supplies'])} left + {worst['picked']} picked) of {slots} free: "
                f"{fitted['missing']} more slot(s) needed (supplies are not dropped to make room).")
    text = (f"**Pickups feasible:** rucksack peaks at {peak}/{slots} slots"
            + (f", {heavy['max']} heavy item(s)" if heavy["max"] else "") + ".")
    if fitted["departure_slots"] < slots:
        text += (f" Supplies planned with {fitted['departure_slots']} slots at departure to leave "
                 f"room for the pickups.")
    return text


def pickup_lines(fitted: dict, slots: int) -> dict[int, str]:
    """{route index: text} for the Itinerary: what is picked up there and the rucksack after it."""
    out: dict[int, list[str]] = {}
    for r in fitted["rows"]:
        p = r["pickup"]
        named = p.names and not (len(p.names) == 1 and p.names[0].lower() == p.spec.lower())
        what = (f"{p.count} × {p.spec}" if p.count > 1 else p.spec) \
            + (f" ({', '.join(p.names)})" if named else "")
        heavy = f", {p.heavy} heavy" if p.heavy else ""
        over = " — OVER" if r["over"] else ""
        out.setdefault(r["move"], []).append(
            f"Pick up {what}{heavy}. Rucksack: {r['used']}/{slots} slots used, "
            f"{max(0, slots - r['used'])} free ({_supplies(r['supplies'])} + {r['picked']} picked){over}")
    return {m: " · ".join(v) for m, v in out.items()}
