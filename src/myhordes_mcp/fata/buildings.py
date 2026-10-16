"""Building formatters: today's builds, history, available constructions."""

from ..utils.clock import data_updated


# Fata returns rarityCurrent=0 for private-town buildings — rarity filter won't catch them.
# Hardcoded exclusion list is the only reliable approach.
PRIVATE_TOWN_BUILDINGS = {"Holy Raincloud", "Spirit Mirage", "Sword of Bokor", "XXL Voodoo Doll"}

_RARITY_LABEL = {0: None, 1: "bp:common", 2: "bp:uncommon", 3: "bp:rare", 4: "bp:very rare"}


def _building_line(b: dict, show_day: bool = False) -> str:
    name = b["name"]
    if b.get("level") is not None:
        name += f" [Lv.{b['level']}]"
    parts = [f"  {name}"]
    details = []
    if show_day and b.get("built_day"):
        details.append(f"Day {b['built_day']}")
    if b["defense"]:
        details.append(f"+{b['defense']} def")
    if b["temporary"]:
        details.append("temporary")
    if details:
        parts.append(", ".join(details))
    return " — ".join(parts) if len(parts) > 1 else parts[0]


def _available_line(b: dict, locked: bool = False, include_resources: bool = False) -> str:
    parts = [f"  {b['name']}"]
    details = []
    if b["ap_cost"]:
        details.append(f"{b['ap_cost']} AP")
    if b["defense"]:
        details.append(f"+{b['defense']} def")
    if b["temporary"]:
        details.append("temporary")
    rarity_tag = _RARITY_LABEL.get(b.get("rarity", 0))
    if rarity_tag:
        details.append(f"[{rarity_tag}]")
    if locked and b.get("parent_name"):
        details.append(f"[needs: {b['parent_name']}]")
    if include_resources and b.get("resources"):
        res_str = ", ".join(f"{r['name']} ×{r['amount']}" for r in b["resources"])
        details.append(f"[{res_str}]")
    if details:
        parts.append(", ".join(details))
    return " — ".join(parts) if len(parts) > 1 else parts[0]


def _build_history_lines(built: list) -> list[str]:
    """Return lines for the full day-by-day construction history."""
    has_history = any(b.get("built_day") is not None for b in built)
    total_def = sum(b["defense"] for b in built)

    if not has_history:
        built_sorted = sorted(built, key=lambda b: b["name"].lower())
        lines = [f"### Built ({len(built)}, total defense: {total_def})"]
        for b in built_sorted:
            lines.append(_building_line(b))
        return lines

    day_builds: dict[int, list] = {}
    day_upgrades: dict[int, list] = {}

    for b in built:
        bd = b.get("built_day")
        if bd is not None:
            try:
                key = int(bd)
            except (ValueError, TypeError):
                key = 0
            day_builds.setdefault(key, []).append(b)

        udays = b.get("upgrade_days")
        if udays:
            for day_str, new_level in udays.items():
                try:
                    uday = int(day_str)
                    nlevel = int(new_level)
                except (ValueError, TypeError):
                    continue
                day_upgrades.setdefault(uday, []).append((b["name"], nlevel - 1, nlevel))

    all_days = sorted(set(day_builds.keys()) | set(day_upgrades.keys()))
    lines = [f"### Built — construction history (total defense from buildings: {total_def})"]
    for day_key in all_days:
        label = f"**Day {day_key}**" if day_key > 0 else "**Day ? (unknown)**"
        lines.append(label)
        for name, old_lv, new_lv in sorted(day_upgrades.get(day_key, []), key=lambda x: x[0].lower()):
            lines.append(f"  *(free vote)* {name}: Lv.{old_lv} → Lv.{new_lv}")
        for b in sorted(day_builds.get(day_key, []), key=lambda x: x["name"].lower()):
            lines.append(_building_line(b))
        lines.append("")
    return lines


def format_buildings(data: dict, mode: str = "summary", include_private: bool = False, include_resources: bool = False) -> str:
    """Format building list.

    mode:
      "summary"   — buildings constructed today only + running defense total
      "history"   — all built buildings grouped by construction day
      "available" — unbuilt buildings with AP cost, defense, blueprint requirement
    include_private: if False, exclude the 4 private/custom-town-only buildings (hardcoded list).
    include_resources: if True, append resource requirements to each available building line.
    """
    if data.get("error"):
        return f"Error: {data['error']}"

    buildings = data["buildings"]
    meta = data["meta"]

    if not buildings:
        return "No building data available."

    if not include_private:
        buildings = [b for b in buildings if b["name"] not in PRIVATE_TOWN_BUILDINGS]

    current_day = meta.get("day")
    built = [b for b in buildings if b["built"]]
    available = [b for b in buildings if not b["built"]]
    total_def = sum(b["defense"] for b in built)

    header = f"## Buildings — {meta.get('town_name', '?')} Day {current_day}\n{data_updated(meta)}"

    if mode == "summary":
        today = [b for b in built if b.get("built_day") == current_day]
        # Also collect upgrades that happened today
        today_upgrades: list[tuple[str, int, int]] = []
        for b in built:
            udays = b.get("upgrade_days") or {}
            for day_key, new_level in udays.items():
                if int(day_key) == current_day:
                    today_upgrades.append((b["name"], new_level - 1, new_level))

        lines = [header, f"{len(built)} built total — defense from buildings: {total_def}", ""]
        if not today and not today_upgrades:
            lines.append("No constructions today yet.")
        else:
            lines.append(f"### Built today (Day {current_day})")
            for name, old_lv, new_lv in sorted(today_upgrades, key=lambda x: x[0].lower()):
                lines.append(f"  *(free vote)* {name}: Lv.{old_lv} → Lv.{new_lv}")
            for b in sorted(today, key=lambda x: x["name"].lower()):
                lines.append(_building_line(b))
        return "\n".join(lines)

    if mode == "history":
        lines = [header, f"{len(built)} built, {len(available)} not yet built", ""]
        lines.extend(_build_history_lines(built))
        return "\n".join(lines)

    if mode == "available":
        available_sorted = sorted(available, key=lambda b: b["ap_cost"])
        # Split by prerequisite first
        prereq_ok = [b for b in available_sorted if b.get("parent_built", True)]
        prereq_locked = [b for b in available_sorted if not b.get("parent_built", True)]
        # Among prerequisite-ok: split by blueprint status
        # no_bp: rarity==0 (no blueprint needed at all)
        # bp_found: rarity>0 but blueprint already submitted → buildable
        # bp_blocked: rarity>0 and blueprint not yet found → NOT buildable
        no_bp = [b for b in prereq_ok if b.get("rarity", 0) == 0]
        bp_found = [b for b in prereq_ok if b.get("rarity", 0) > 0 and b.get("blueprint_found", False)]
        unlocked_count = len(no_bp) + len(bp_found)
        lines = [header, f"{len(built)} built — {unlocked_count} unlocked, {len(prereq_locked)} locked (prereq) — defense from buildings: {total_def}", ""]
        lines.append(f"### Unlocked — no blueprint needed ({len(no_bp)})")
        for b in no_bp:
            lines.append(_available_line(b, include_resources=include_resources))
        if bp_found:
            lines.append("")
            lines.append(f"### Unlocked — blueprint found ({len(bp_found)})")
            for b in bp_found:
                lines.append(_available_line(b, include_resources=include_resources))
        if prereq_locked:
            lines.append("")
            lines.append(f"### Locked — prerequisite not built ({len(prereq_locked)})")
            for b in prereq_locked:
                lines.append(_available_line(b, locked=True, include_resources=include_resources))
        return "\n".join(lines)

    return f"Unknown mode '{mode}'. Use: summary, history, available."
