"""Town-level formatters: overview, citizens, defense."""

from ..utils.fmt import est_status, estimate, header, town_name
from ..utils.clock import data_updated
from .cp import cp_label
from .risk import (
    _staleness_tag,
    defense_alert,
    defense_status,
    gate_line,
    night_alerts,
    outside_alert,
    trapped_lines,
)


def _who(c: dict) -> str:
    shaman = " [Shaman]" if c["is_shaman"] else ""
    return f"{c['name']} ({c['job']}{shaman})"


def _stale(c: dict, meta: dict) -> str:
    """Position age tag; citizen positions are auto-synced unless the town is in
    chaos/devastated mode."""
    if not (meta.get("chaos") or meta.get("devastated")):
        return ""
    return _staleness_tag(c.get("last_update_day"), meta.get("day"))


TOWN_SIZE = 40  # citizens a standard town needs before its first attack


def roster_line(data: dict) -> str:
    """'40 citizens (34 alive, 6 dead) — town started: attacks every night'.

    Alive alone misleads: "34" reads as an unfilled town. A town only starts
    (first attack, day 2) once 40 have joined; the dead still count, and past
    day 1 it has started for good."""
    alive, dead = len(data["citizens"]), len(data["deaths"])
    joined, day = alive + dead, data["meta"].get("day") or 0
    head = f"{joined} citizens ({alive} alive, {dead} dead)"
    if day > 1:
        return f"{head} — town started on day 1: attacks every night"
    if joined >= TOWN_SIZE:
        return f"{head} — town full: first attack tonight"
    return f"{head} — town NOT full ({joined}/{TOWN_SIZE}): no attack until it fills"


def _format_estimate(est: dict) -> str:
    """Format a single attack estimate with confirmed/partial indicator."""
    if est.get("min") is None:
        return "not estimated yet"
    return estimate(est["min"], est["max"], est_status(est.get("maxed")))


def format_town_overview(data: dict, season_points: int | None = None, detail: str = "compact") -> str:
    """Format a complete town overview.

    Args:
        data: Fata Morgana town data dict.
        season_points: Optional season point total from Gest'Hordes, shown in header.
        detail: 'compact' (default) — outside citizens one per line, inside
                citizens as one comma-joined roster, deaths as a count line,
                bank as a size line. 'full' — every citizen on its own line
                plus the complete bank item list and death log.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    meta = data["meta"]
    defense = data["defense"]
    water = data["water"]
    est = data["estimations"]
    citizens = data["citizens"]
    deaths = data["deaths"]
    bank = data["bank"]

    alive = len(citizens)
    inside = sum(1 for c in citizens if c["inside_town"])
    outside = alive - inside

    today_est = est.get("today", {})
    tonight = _format_estimate(today_est)
    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    season_pts_str = f" | Season pts: {season_points}" if season_points is not None else ""
    lines = [
        f"# {town_name(meta)} — Day {meta.get('day', '?')}",
        f"Season {meta.get('season', '?')} | Type: {meta.get('game_type', '?')} | Region: {meta.get('region', '?')}"
        + season_pts_str
        + (" | CHAOS MODE" if meta.get("chaos") else "")
        + (" | DEVASTATED" if meta.get("devastated") else ""),
        data_updated(meta),
        *night_alerts(data, gate=False),
        "",
        f"## {gate_line(data)}",
        "",
        "## Defense",
        f"  Total: {defense.get('total', '?')}",
        f"  Wall: {defense.get('base', '?')} | Buildings: {defense.get('buildings', '?')} | Items: {defense.get('items', '?')}",
        f"  Guardians: {defense.get('guardians', '?')} | Homes: {defense.get('homes', '?')} | Other: {defense.get('other', '?')}",
        f"  Multiplier: x{defense.get('multiplier', '?')}",
        "",
        "## Attack Estimation",
        f"  Tonight: {tonight}",
        f"  Tomorrow: {tomorrow}",
        "",
        "## Water",
        f"  Well: {water.get('well', '?')} | Bank rations: {water.get('bank', '?')}",
        "",
        f"## Citizens: {roster_line(data)}",
        f"  {alive} alive — {inside} inside, {outside} outside",
    ]
    if detail == "compact":
        # Outside citizens keep individual lines (coordinates matter);
        # inside citizens collapse to one comma-joined roster line.
        for c in citizens:
            if c["inside_town"]:
                continue
            lines.append(f"  {_who(c)} — {c['coords']}{_stale(c, meta)}")
        inside_c = [c for c in citizens if c["inside_town"]]
        if inside_c:
            roster = ", ".join(
                c["name"] + (" [Shaman]" if c["is_shaman"] else "")
                for c in inside_c
            )
            lines.append(f"  In town: {roster}")
        lines.append("")
        trapped = trapped_lines(data)
        if trapped:
            lines.extend(trapped + [""])
        if deaths:
            d = deaths[0]
            lines.append(
                f"## Deaths: {len(deaths)} total — most recent Day {d['day']}: "
                f"{d['name']} ({d['cause']}). Full list: get_citizen_positions."
            )
        lines.append(f"## Bank: {len(bank)} item types — contents: get_bank_inventory.")
        return "\n".join(lines)

    for c in citizens:
        loc = "IN TOWN" if c["inside_town"] else c["coords"]
        lines.append(f"  {_who(c)} — {loc}{_stale(c, meta)}")

    trapped = trapped_lines(data)
    if trapped:
        lines.append("")
        lines.extend(trapped)

    if deaths:
        lines.append("")
        lines.append(f"## Deaths ({len(deaths)})")
        for d in deaths:
            lines.append(f"  Day {d['day']}: {d['name']} — {d['cause']} (last at {d['last_coords']})")

    lines.append("")
    lines.append(f"## Bank ({len(bank)} items)")
    for item in bank:
        broken = " [BROKEN]" if item["broken"] else ""
        lines.append(f"  {item['name']}: {item['count']}{broken}")

    return "\n".join(lines)


def format_citizens(data: dict, cp_log: dict | None = None) -> str:
    """Format citizen positions and deaths. cp_log (cp.load_cp_log) adds each
    citizen's last known CP."""
    if data.get("error"):
        return f"Error: {data['error']}"

    citizens = data["citizens"]
    deaths = data["deaths"]
    meta = data["meta"]

    inside = [c for c in citizens if c["inside_town"]]
    outside = [c for c in citizens if not c["inside_town"]]

    lines = [
        header("Citizens", meta),
        gate_line(data),
        roster_line(data),
        f"{len(citizens)} alive — {len(inside)} inside, {len(outside)} outside",
        *([a] if (a := outside_alert(data)) else []),
        "",
    ]

    if outside:
        lines.append("### Outside the town:")
        for c in outside:
            cp = cp_label(cp_log, c["id"]) if cp_log else ""
            lines.append(f"  {_who(c)} at {c['coords']}{_stale(c, meta)}{cp}")
    else:
        lines.append("Everyone is inside the town.")

    if inside:
        lines.append("")
        lines.append("### Inside the town:")
        for c in inside:
            cp = cp_label(cp_log, c["id"]) if cp_log else ""
            lines.append(f"  {_who(c)}{cp}")

    if deaths:
        lines.append("")
        lines.append(f"### Dead citizens ({len(deaths)}):")
        death_day = None
        for d in deaths:
            if d["day"] != death_day:
                death_day = d["day"]
                lines.append(f"  Day {death_day}:")
            lines.append(f"    {d['name']} — {d['cause']} (last at {d['last_coords']})")

    return "\n".join(lines)


def format_defense(data: dict) -> str:
    """Format defense breakdown and attack estimation, from Fata only."""
    if data.get("error"):
        return f"Error: {data['error']}"

    defense = data["defense"]
    est = data["estimations"]

    total = defense.get("total", 0)
    today_est = est.get("today", {})
    tonight = _format_estimate(today_est)

    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    status = defense_status(data)
    survival = {
        None: "",
        "SAFE": " — SAFE (defense exceeds max estimate)",
        "AT RISK": f" — AT RISK (defense covers min, {status[1]} short of max)" if status else "",
        "DANGER": f" — DANGER ({status[1]} defense short of minimum estimate)" if status else "",
    }[status[0] if status else None]
    alert = defense_alert(data)
    if status and status[0] != "SAFE" and not alert and data["meta"].get("live") is not False:
        survival += " — before 23:00: normal while the town still builds"

    lines = [
        f"## Defense Analysis{survival}",
        data_updated(data["meta"]),
        gate_line(data),
        *([alert] if alert else []),
        "",
        f"Total defense: {total}",
        f"  Wall base: {defense.get('base', '?')}",
        f"  Buildings: {defense.get('buildings', '?')}",
        f"  Defense items: {defense.get('items', '?')} (x{defense.get('multiplier', '?')} multiplier)",
        f"  Guardians: {defense.get('guardians', '?')}",
        f"  Homes: {defense.get('homes', '?')}",
        f"  Upgrades: {defense.get('upgrades', '?')}",
    ]

    other = defense.get("other", 0) or 0
    if "watchmen" in defense:
        lines.append(f"  Watchmen: {defense['watchmen']}")
        lines.append(f"  Temporary bonuses: {defense.get('temporary', 0)}")
        if other - defense["watchmen"] - defense.get("temporary", 0):
            lines.append(f"  Other (unaccounted): {other - defense['watchmen'] - defense.get('temporary', 0)}")
    else:
        lines.append(f"  Other sources: {other}")

    lines += [
        "",
        f"Tonight's attack: {tonight}",
        f"Tomorrow's attack: {tomorrow}",
    ]

    # Estimation history, with the actual attack where Fata has it (newspaper)
    history = est.get("history", {})
    attacks = data.get("attacks") or {}
    days = sorted({int(d) for d in history} | set(attacks))
    if days:
        lines.append("")
        lines.append("### Attack history:")
        for day in days:
            e = history.get(str(day))
            line = f"  Day {day}: est. {_format_estimate(e)}" if e else f"  Day {day}: est. unknown"
            a = attacks.get(day)
            if a:
                line += f" → attack {a['zombies']}" + (f" vs defense {a['defense']}" if a.get("defense") is not None else "")
            lines.append(line)

    return "\n".join(lines)
