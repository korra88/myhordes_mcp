"""Map the bank onto a coalition Garbage Dump sheet's item rows.

Deterministic part of the update-garbage-dump-list skill: the sheet uses
Gest'Hordes names, the bank Fata names. Rules (confirmed with the sheet owner,
see .claude/commands/update-garbage-dump-list.md):
- broken items count: they dump for full value;
- Plastic Bag counts as Water Bomb (filled for free at the Faucet), Plastic Bag
  and Semtex as Exploding Water Bomb;
- emptied weapons "X (empty)" fold into their loaded row X;
- a sheet name with no exact match takes the unique bank name it prefixes
  (the sheet truncates long names, e.g. "Unshaped Concre").
"""

import re
from ..utils.clock import data_updated

ALIASES = {
    "water bomb": ["Water Bomb", "Plastic Bag"],
    "exploding water bomb": ["Exploding Water Bomb", "Plastic Bag and Semtex"],
}
EMPTY_SUFFIX = " (empty)"
INCOMPLETE = "(incomplete)"
# Weapon state suffixes: "(loaded)", "(unloaded)", "(empty)", "(3 shots)".
_STATE = re.compile(r"\s*\((?:loaded|unloaded|empty|\d+ shots?)\)\s*$", re.I)


def _base(name: str) -> str:
    return _STATE.sub("", name).strip().lower()


def _bank_totals(bank: list[dict]) -> tuple[dict[str, int], dict[str, str]]:
    """Total per bank name (broken included), and each name's category."""
    totals: dict[str, int] = {}
    category: dict[str, str] = {}
    for item in bank:
        totals[item["name"]] = totals.get(item["name"], 0) + item["count"]
        category[item["name"]] = item.get("category") or "?"
    return totals, category


def map_dump_rows(bank: list[dict], sheet_items: list[str]) -> dict:
    totals, category = _bank_totals(bank)
    lower = {n.lower(): n for n in totals}
    used: set[str] = set()
    rows, notes, seen = [], [], {}

    for i, sheet_name in enumerate(sheet_items):
        key = sheet_name.strip().lower()
        if not key:
            rows.append((sheet_name, 0, []))
            continue
        if key in seen:
            notes.append(f"Duplicate sheet row: '{sheet_name}' (rows {seen[key] + 1} and {i + 1}) — "
                         "ask which one owns it; filling both double-counts")
        seen.setdefault(key, i)
        sources = [n for n in ALIASES.get(key, []) if n in totals]
        if not sources and key in lower:
            sources = [lower[key]]
        if not sources:
            prefixed = [n for n in totals if n.lower().startswith(key) and INCOMPLETE not in n.lower()]
            if len(prefixed) == 1:
                sources = prefixed
                notes.append(f"Truncated sheet name '{sheet_name}' → '{prefixed[0]}'")
            elif len(prefixed) > 1:
                notes.append(f"Ambiguous truncated name '{sheet_name}': {', '.join(prefixed)} — left at 0")
        rows.append([sheet_name, sum(totals[s] for s in sources), sources])
        used.update(sources)

    # Emptied weapons fold into the loaded row with the same base name; with
    # several candidate rows (e.g. "Aqua-Splash (1..5 shots)") use the first.
    for name in totals:
        if name in used or not name.lower().endswith(EMPTY_SUFFIX):
            continue
        targets = [r for r in rows if r[0].strip() and _base(r[0]) == _base(name)]
        if not targets:
            continue
        row = targets[0]
        row[1] += totals[name]
        row[2].append(name)
        used.add(name)
        if len(targets) > 1:
            notes.append(f"'{name}' folded into '{row[0].strip()}' (first of {len(targets)} matching rows)")

    unmapped = sorted(((n, totals[n], category[n]) for n in totals if n not in used and totals[n] > 0),
                      key=lambda x: (x[2], x[0]))
    return {"rows": rows, "unmapped": unmapped, "notes": notes}


def format_dump_mapping(data: dict, sheet_items: str) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    items = sheet_items.split("\n")
    while items and not items[-1].strip():
        items.pop()
    if not items:
        return "No sheet item names given. Pass column B of the item rows, one per line, in row order."
    meta = data["meta"]
    m = map_dump_rows(data["bank"], items)
    lines = [f"## Dump sheet mapping — bank of {meta.get('town_name')} Day {meta.get('day')}",
             data_updated(meta, suffix=f" · {len(items)} sheet rows, broken items included"), ""]
    for i, (name, value, sources) in enumerate(m["rows"]):
        src = ""
        if len(sources) > 1 or (sources and sources[0].lower() != name.strip().lower()):
            src = "  ← " + " + ".join(sources)
        lines.append(f"  {i + 1:>3}. {name.strip() or '(blank)'}: {value}{src}")
    lines.append("")
    lines.append("Column values in row order (for the write payload):")
    lines.append("  " + ", ".join(str(v) for _, v, _ in m["rows"]))
    lines.append(f"  Sum: {sum(v for _, v, _ in m['rows'])}")
    if m["notes"]:
        lines.append("")
        lines.append("### Decisions to confirm")
        lines += [f"  {n}" for n in m["notes"]]
    if m["unmapped"]:
        lines.append("")
        lines.append(f"### Bank items with no sheet row ({len(m['unmapped'])}) — most are correctly excluded; "
                     "report dumpable weapons/defences")
        by_cat: dict[str, list] = {}
        for n, c, cat in m["unmapped"]:
            by_cat.setdefault(cat, []).append(f"{n} {c}")
        for cat, entries in sorted(by_cat.items()):
            lines.append(f"  {cat}: {', '.join(entries)}")
    return "\n".join(lines)
