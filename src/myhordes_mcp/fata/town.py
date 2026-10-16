"""Town-level formatters: overview, citizens, defense."""

from ..utils.clock import data_updated, fmt_epoch
from .cp import cp_label
from .risk import _staleness_tag, format_trapped, trapped_citizens


def _format_estimate(est: dict) -> str:
    """Format a single attack estimate with confirmed/partial indicator."""
    if est.get("min") is None:
        return "???"
    label = "(confirmed)" if est.get("maxed") else "(partial)"
    return f"{est['min']}-{est['max']} {label}"


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
        return f"Error fetching town data: {data['error']}"

    meta = data["meta"]
    defense = data["defense"]
    water = data["water"]
    gate = data["gate"]
    est = data["estimations"]
    citizens = data["citizens"]
    deaths = data["deaths"]
    bank = data["bank"]
    current_day = meta.get("day")

    alive = len(citizens)
    inside = sum(1 for c in citizens if c["inside_town"])
    outside = alive - inside

    today_est = est.get("today", {})
    tonight = _format_estimate(today_est)
    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    season_pts_str = f" | Season pts: {season_points}" if season_points is not None else ""
    lines = [
        f"# {meta.get('town_name', 'Unknown Town')} — Day {meta.get('day', '?')}",
        f"Season {meta.get('season', '?')} | Type: {meta.get('game_type', '?')} | Region: {meta.get('region', '?')}"
        + season_pts_str
        + (" | CHAOS MODE" if meta.get("chaos") else "")
        + (" | DEVASTATED" if meta.get("devastated") else ""),
        data_updated(meta),
        "",
        f"## Gate: {gate.upper()}",
        "",
        "## Defense",
        f"  Total: {defense.get('total', '?')}",
        f"  Wall: {defense.get('base', '?')} | Buildings: {defense.get('buildings', '?')} | Items: {defense.get('items', '?')}",
        f"  Guardians: {defense.get('guardians', '?')} | Homes: {defense.get('homes', '?')} | Other: {defense.get('other', '?')}",
        f"  Multiplier: x{defense.get('multiplier', '?')}",
        "",
        "## Attack Estimation",
        f"  Tonight: {tonight} zombies",
        f"  Tomorrow: {tomorrow} zombies",
        "",
        "## Water",
        f"  Well: {water.get('well', '?')} | Bank rations: {water.get('bank', '?')}",
        "",
        f"## Citizens ({alive} alive — {inside} inside, {outside} outside)",
    ]
    # Citizen positions are auto-synced unless town is in chaos/devastated mode
    show_citizen_stale = meta.get("chaos") or meta.get("devastated")

    if detail == "compact":
        # Outside citizens keep individual lines (coordinates matter);
        # inside citizens collapse to one comma-joined roster line.
        for c in citizens:
            if c["inside_town"]:
                continue
            shaman = " [Shaman]" if c["is_shaman"] else ""
            stale = _staleness_tag(c.get("last_update_day"), current_day) if show_citizen_stale else ""
            lines.append(f"  {c['name']} ({c['job']}{shaman}) — {c['coords']}{stale}")
        inside_c = [c for c in citizens if c["inside_town"]]
        if inside_c:
            roster = ", ".join(
                c["name"] + (" [Shaman]" if c["is_shaman"] else "")
                for c in inside_c
            )
            lines.append(f"  In town: {roster}")
        lines.append("")
        trapped = format_trapped(trapped_citizens(data), fmt_epoch)
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
        shaman = " [Shaman]" if c["is_shaman"] else ""
        stale = _staleness_tag(c.get("last_update_day"), current_day) if show_citizen_stale else ""
        lines.append(f"  {c['name']} ({c['job']}{shaman}) — {loc}{stale}")

    trapped = format_trapped(trapped_citizens(data), fmt_epoch)
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
    gate = data["gate"]
    meta = data["meta"]
    current_day = meta.get("day")
    show_citizen_stale = meta.get("chaos") or meta.get("devastated")

    inside = [c for c in citizens if c["inside_town"]]
    outside = [c for c in citizens if not c["inside_town"]]

    lines = [
        f"Gate: {gate.upper()}",
        f"{len(citizens)} citizens alive — {len(inside)} inside, {len(outside)} outside",
        "",
    ]

    if outside:
        lines.append("### Outside the town:")
        for c in outside:
            shaman = " [Shaman]" if c["is_shaman"] else ""
            stale = _staleness_tag(c.get("last_update_day"), current_day) if show_citizen_stale else ""
            cp = cp_label(cp_log, c["id"]) if cp_log else ""
            lines.append(f"  {c['name']} ({c['job']}{shaman}) at {c['coords']}{stale}{cp}")
    else:
        lines.append("Everyone is inside the town.")

    if inside:
        lines.append("")
        lines.append("### Inside the town:")
        for c in inside:
            shaman = " [Shaman]" if c["is_shaman"] else ""
            cp = cp_label(cp_log, c["id"]) if cp_log else ""
            lines.append(f"  {c['name']} ({c['job']}{shaman}){cp}")

    if deaths:
        lines.append("")
        lines.append(f"### Dead citizens ({len(deaths)}):")
        current_day = None
        for d in deaths:
            if d["day"] != current_day:
                current_day = d["day"]
                lines.append(f"  Day {current_day}:")
            lines.append(f"    {d['name']} — {d['cause']} (last at {d['last_coords']})")

    return "\n".join(lines)


def format_defense(data: dict, gh_defense: dict | None = None) -> str:
    """Format defense breakdown and attack estimation.

    Args:
        data: Fata Morgana town data dict.
        gh_defense: Optional Gest'Hordes current-day defence breakdown from
                    gesthordes.extract_current_defense(). Adds watchers,
                    temporary, and dead_bonus lines that Fata lumps into 'other'.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    defense = data["defense"]
    est = data["estimations"]
    gate = data["gate"]

    total = defense.get("total", 0)
    today_est = est.get("today", {})
    low = today_est.get("min")
    high = today_est.get("max")
    tonight = _format_estimate(today_est)

    tomorrow_est = est.get("tomorrow", {})
    tomorrow = _format_estimate(tomorrow_est)

    survival = ""
    if low is not None and high is not None:
        if total >= high:
            survival = " -> SAFE (defense exceeds max estimate)"
        elif total >= low:
            survival = f" -> AT RISK (defense covers min, {high - total} short of max)"
        else:
            survival = f" -> DANGER ({low - total} defense short of minimum estimate)"

    lines = [
        f"## Defense Analysis — Gate: {gate.upper()}{survival}",
        data_updated(data["meta"]),
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
    if gh_defense is not None:
        watchers = gh_defense.get("watchers", 0)
        temporary = gh_defense.get("temporary", 0)
        dead_bonus = gh_defense.get("dead_bonus", 0)
        lines.append(f"  Watchmen: {watchers}")
        lines.append(f"  Temporary bonuses: {temporary}")
        lines.append(f"  Dead-citizen bonus: {dead_bonus}")
        gh_accounted = watchers + temporary + dead_bonus
        remainder = other - gh_accounted
        if remainder != 0:
            lines.append(f"  Other (unaccounted): {remainder}")
        lines.append("  (Gest'Hordes breakdown)")
    elif "watchmen" in defense:
        lines.append(f"  Watchmen: {defense['watchmen']}")
        lines.append(f"  Temporary bonuses: {defense.get('temporary', 0)}")
        if other - defense["watchmen"] - defense.get("temporary", 0):
            lines.append(f"  Other (unaccounted): {other - defense['watchmen'] - defense.get('temporary', 0)}")
    else:
        lines.append(f"  Other sources: {other}")

    lines += [
        "",
        f"Tonight's attack: {tonight} zombies",
        f"Tomorrow's attack: {tomorrow} zombies",
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
