"""Town changes over the day, computed from intraday snapshots.

Every live fetch of the current day stores a compact snapshot (archive.py) when
something changed. get_town_changes compares two of them — movements, bank,
defense, gate — and walks all of today's snapshots to estimate the AP each
citizen spent moving. Replaces the arithmetic inspect-town used to do by hand.
"""

from datetime import datetime

from ..utils.clock import GAME_TZ, data_updated, fmt_epoch
from ..utils.config import PLAYER_NAME
from . import archive
from .client import fetch_town_data
from .risk import _parse_coords, format_trapped, night_alerts, trapped_citizens

# Items inspect-town tracks for deposits and withdrawals.
CRITICAL_ITEMS = [
    "Handful of nuts and bolts", "Wire Reel", "Electronic component", "Laser Diode",
    "Compact detonator", "Copper Pipe", "Semtex", "Anabolic Steroids",
    "Vodka Marinostov", "Construction Blueprint (rare)", "Construction Blueprint (very rare!)",
    "Iron Chest",
]
OTHER_BANK_LINES = 8


def _xy(coords: str) -> tuple[int, int]:
    return _parse_coords({"coords": coords}) or (0, 0)


def platform_discount(level: int | None) -> int:
    """AP saved on the way home by the Observation Platform teleport
    (knowledge/tactics/game-mechanics.md, "Return to town")."""
    if level is None:
        return 0
    return 3 if level >= 4 else 2 if level >= 3 else 0


def _move_cost(a: dict, b: dict, discount: int) -> int:
    """AP of moving between two observed positions (lower bound: straight line)."""
    if a["inside"] and b["inside"]:
        return 0
    if a["inside"]:
        x, y = _xy(b["coords"])
        return abs(x) + abs(y)
    x1, y1 = _xy(a["coords"])
    if b["inside"]:
        return max(0, abs(x1) + abs(y1) - discount)
    x2, y2 = _xy(b["coords"])
    return abs(x2 - x1) + abs(y2 - y1)


def day_movement(snaps: list[dict]) -> dict[str, dict]:
    """Per citizen: AP spent moving today across consecutive snapshots."""
    out: dict[str, dict] = {}
    for prev, cur in zip(snaps, snaps[1:]):
        discount = platform_discount(cur.get("platform_level"))
        for cid, b in cur["citizens"].items():
            a = prev["citizens"].get(cid)
            if a is None:
                continue
            ap = _move_cost(a, b, discount)
            if ap or cid in out:
                entry = out.setdefault(cid, {"name": b["name"], "ap": 0, "trips": 0})
                entry["ap"] += ap
                if a["inside"] and not b["inside"]:
                    entry["trips"] += 1
    return out


def format_town_changes(data: dict, snaps: list[dict], ref: dict | None, ref_label: str) -> str:
    meta = data["meta"]
    if not snaps:
        return "No snapshot available yet for today."
    cur = snaps[-1]
    lines = [
        f"## Town changes — {meta.get('town_name')} Day {meta.get('day')}",
        data_updated(meta) + f" · {len(snaps)} snapshot(s) today, "
        f"first {fmt_epoch(snaps[0]['taken_at'])}",
    ]
    if ref is None or ref is cur:
        lines.append(f"Compared against: {ref_label} — no earlier snapshot today, nothing to compare.")
    else:
        lines.append(f"Compared: {fmt_epoch(ref['taken_at'])} ({ref_label}) → {fmt_epoch(cur['taken_at'])}")

    alive = len(cur["citizens"])
    inside = sum(c["inside"] for c in cur["citizens"].values())
    state = f"State: {alive} alive of {alive + (cur.get('deaths') or 0)} citizens — {inside} inside, {alive - inside} outside · Defense {cur['defense']} · Gate {cur['gate']}"
    if ref is not None and ref is not cur:
        d_alive = alive - len(ref["citizens"])
        d_def = (cur["defense"] or 0) - (ref["defense"] or 0)
        state += f" · Δ alive {d_alive:+d}, Δ defense {d_def:+d}"
        if ref["gate"] != cur["gate"]:
            state += f" · gate {ref['gate']}→{cur['gate']}"
    est = data["estimations"].get("today", {})
    if est.get("min") is not None:
        state += f" · Tonight {est['min']}–{est['max']}z"
    lines += [state, ""]

    if ref is not None and ref is not cur:
        discount = platform_discount(cur.get("platform_level"))
        moves = []
        for cid, b in sorted(cur["citizens"].items(), key=lambda kv: kv[1]["name"].lower()):
            a = ref["citizens"].get(cid)
            if a is None:
                moves.append(f"  {b['name']} — new in data at {'IN TOWN' if b['inside'] else b['coords']}")
                continue
            if a["inside"] == b["inside"] and a["coords"] == b["coords"]:
                continue
            ap = _move_cost(a, b, discount)
            if b["inside"]:
                moves.append(f"  {b['name']} returned from {a['coords']} (~{ap} AP net)")
            elif a["inside"]:
                moves.append(f"  {b['name']} went out to {b['coords']} (~{ap} AP)")
            else:
                moves.append(f"  {b['name']} {a['coords']} → {b['coords']} (+{ap} AP)")
        gone = [a["name"] for cid, a in ref["citizens"].items() if cid not in cur["citizens"]]
        if gone:
            moves.append(f"  No longer listed (dead?): {', '.join(gone)}")
        if moves:
            lines.append(f"### Movements ({len(moves)})")
            lines += moves + [""]

        changed = {k for k in set(ref["bank"]) | set(cur["bank"]) if ref["bank"].get(k, 0) != cur["bank"].get(k, 0)}
        crit = [k for k in CRITICAL_ITEMS if k in changed]
        other = sorted(changed - set(crit), key=lambda k: -abs(cur["bank"].get(k, 0) - ref["bank"].get(k, 0)))
        if crit or other:
            lines.append("### Bank")
            for k in crit:
                o, n = ref["bank"].get(k, 0), cur["bank"].get(k, 0)
                lines.append(f"  {k}: {o} → {n} ({'+' if n > o else '−'}{abs(n - o)} {'deposited' if n > o else 'PULLED'})")
            if other:
                shown = ", ".join(f"{k} {cur['bank'].get(k, 0) - ref['bank'].get(k, 0):+d}" for k in other[:OTHER_BANK_LINES])
                more = f" (+{len(other) - OTHER_BANK_LINES} more)" if len(other) > OTHER_BANK_LINES else ""
                lines.append(f"  Other: {shown}{more}")
            lines.append("")

        new_builds = [n for n in cur["built"] if n not in ref["built"]]
        upgrades = [f"{n} Lv.{ref['built'][n]}→{lv}" for n, lv in cur["built"].items()
                    if n in ref["built"] and lv != ref["built"][n]]
        if new_builds or upgrades:
            lines.append("### Constructions: " + " · ".join(new_builds + upgrades))
            lines.append("")

        if not moves and not (crit or other) and not (new_builds or upgrades):
            lines += ["No changes since the reference snapshot.", ""]

    walk = day_movement(snaps)
    if walk:
        lines.append(f"### AP spent moving today (lower bound from {len(snaps)} snapshots; "
                     f"platform return discount {platform_discount(cur.get('platform_level'))} AP)")
        for cid, w in sorted(walk.items(), key=lambda kv: -kv[1]["ap"]):
            where = cur["citizens"].get(cid)
            pos = "in town" if where and where["inside"] else (where["coords"] if where else "gone")
            lines.append(f"  {w['name']} ~{w['ap']} AP ({pos})")
        lines.append("")

    warnings = format_trapped(trapped_citizens(data), fmt_epoch)
    warnings += night_alerts(data)
    zones = {z["coords"]: z for z in data["zones"]}
    dried = sorted(c["name"] for c in data["citizens"]
                   if not c["inside_town"] and zones.get(c["coords"], {}).get("dried"))
    if dried:
        mine = f" — including you ({PLAYER_NAME})" if PLAYER_NAME and PLAYER_NAME in dried else ""
        warnings.append(f"Outside on depleted zones ({len(dried)}){mine}: {', '.join(dried)}")
    lines += warnings
    return "\n".join(lines).rstrip()


def _parse_since(since: str, snaps: list[dict]) -> dict | None:
    """'HH:MM' → latest snapshot taken at or before that game time today."""
    try:
        hh, mm = (int(x) for x in since.split(":"))
    except ValueError:
        return None
    ref = None
    for s in snaps:
        t = datetime.fromtimestamp(s["taken_at"], GAME_TZ)
        if (t.hour, t.minute) <= (hh, mm):
            ref = s
    return ref or (snaps[0] if snaps else None)


async def get_town_changes(town_id: int, since: str = "") -> str:
    """Fetch live data (which stores a snapshot), then compare.

    since: "" → previous get_town_changes call today (then advance that marker),
    "day" → first snapshot of today, "HH:MM" → snapshot at or before that time.
    """
    data = await fetch_town_data(town_id)
    if data.get("error"):
        return f"Error: {data['error']}"
    day = data["meta"].get("day")
    snaps = archive.load_snapshots(town_id, day)
    if not snaps:
        return "No snapshot stored for today — archive not writable?"
    if since == "day":
        ref, label = snaps[0], "start of today's snapshots"
    elif since:
        ref, label = _parse_since(since, snaps), f"at or before {since}"
    else:
        marker = archive.get_changes_marker(town_id)
        if marker and marker.get("day") == day:
            ref = next((s for s in reversed(snaps) if s["taken_at"] <= marker["taken_at"]), snaps[0])
            label = "previous check"
        else:
            ref, label = snaps[0], "first snapshot today (no previous check)"
        archive.set_changes_marker(town_id, day, snaps[-1]["taken_at"])
    return format_town_changes(data, snaps, ref, label)
