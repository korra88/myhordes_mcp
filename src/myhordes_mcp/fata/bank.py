"""Bank formatters: full item list and strategic summary."""

from ..utils.clock import data_updated


def format_bank(data: dict) -> str:
    """Format bank inventory grouped by category."""
    if data.get("error"):
        return f"Error: {data['error']}"

    bank = data["bank"]
    meta = data["meta"]

    if not bank:
        return "The bank is empty."

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for item in bank:
        by_cat.setdefault(item["category"], []).append(item)

    lines = [
        f"## Bank Inventory — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        data_updated(meta),
        f"{len(bank)} item types in the bank",
        "",
    ]
    for cat in sorted(by_cat.keys()):
        lines.append(f"### {cat}")
        for item in by_cat[cat]:
            broken = " [BROKEN]" if item["broken"] else ""
            lines.append(f"  {item['name']}: {item['count']}{broken}")
        lines.append("")

    return "\n".join(lines)


# Items classified by strategic role.  Keys are English item names (as they
# come from Fata Morgana).  An item can appear in multiple buckets — that's
# fine, the summary sections are independent.
#
# Source: knowledge_base/processed/entities.json (wiki data).
# Damage tiers from killmin/killmax properties.

_FOOD_7AP = {
    # Max + 1 (7 AP) — wiki-verified
    "Apple", "Burnt Marshmallows", "Crawling crumble", "Egg",
    "Handful of Sweets", "Impressive Pumpkin", "Intestine Melon",
    "Sawdust Steak", "Spicy Chinese Noodles",
    "Tasty Homemade Dish", "Tasty-looking Steak",
    # Max + 2 (8 AP)
    "Christmas candy", "Overly tempting apple",
}


_FOOD_6AP = {
    # Max (6 AP) — wiki-verified
    "Chinese Noodles", "Chocolate log", "Dodgy Homemade Dish",
    "Dried Chewing Gum", "Fleshroom Puree", "Fleshroom Puree (infected)",
    "Half-eaten Chicken Wings", "Human Flesh", "Meaty Bone",
    "Mouldy Ham Sandwich", "Mouldy Twinkies",
    "Open Can", "Open Can (infected)",  # also counted as clean water
    "Out-of-Date Jaffa Cakes", "Packet of Soft Crisps",
    "Rancid Shortbread Pack", "Sandy Pretzel",
    "Seasonned fistful of insects",
    "Stale Tart", "Suspicious-looking Vegetable",
    "Suspicious-looking Vegetable (infected)",
    "Unspecified Meat",
}


_ALCOHOL = {
    # 6 AP + morale boost — can be drunk in ADDITION to eating food
    "Vodka Marinostov", "Stale Beer", "Sticky Pint",
    "Ergot Homebrew", "Mug of lukewarm liquid",
    "\u201cWake The Dead\u201d", '"Wake The Dead"',
}


def expedition_extras(bank: list[dict]) -> dict[str, int]:
    """Bank stock of the expedition extras the supplies planner knows (steroid, alcohol,
    Twinoid), intact items only."""
    def count(match) -> int:
        return sum(i["count"] for i in bank if match(i["name"]) and not i.get("broken"))
    return {"steroid": count(lambda n: n.startswith("Anabolic Steroids")),
            "alcohol": count(_ALCOHOL.__contains__),
            "twinoid": count(lambda n: n.startswith("Twinoid"))}


_CLEAN_WATER = {
    # Items that provide clean water rations
    "Water Ration", "Purified Stagnant Water",
    "Open Can", "Open Can (infected)",
    "Water Cooler Bottle (1 ration)", "Water Cooler Bottle (2 rations)",
    "Water Cooler Bottle (3 rations)",
}


# Stagnant Water Can only counts as clean water when a Water Filter or
# Water Purifier building is present — handled dynamically in the formatter.
_CONDITIONAL_WATER = {"Stagnant Water Can"}


_FOOD_CONTAINERS = {
    # Openable containers that yield food (not food themselves)
    "Doggy Bag", "Food Parcel",
}


_AP_DRUGS = {
    "Anabolic Steroids", "Anabolic Steroids (infected)", "Twinoid 500mg",
}


_HEALING = {
    "Bandage", "Paracetoid 7g",
}


_STATUS_DRUGS = {
    "Valium Shot", "Hydratone 100mg",
    "Little Book of Calm", "Unlabelled Drug",
    "Water Purifying Tablets", "Cyanohydric Capsule",
    "Twinoid Capsule", "Iodine Tincture",
}


_METAL = {"Wrought Iron", "Scrap Metal", "Metal Support"}


_WOOD = {"Rotting Log", "Twisted Plank", "Patchwork Beam"}


_KEY_RESOURCES = {
    "Copper Pipe", "Handful of nuts and bolts", "Duct Tape",
    "Semtex", "Compact detonator",
    "Wire Reel", "Convex Lens", "Laser Diode",
    "Battery", "Mechanism", "Electronic component",
    "Broken Electronic Device", "Belt",
    "Bag of Cement", "Sheet of Plywood",
    "Sheet Metal (parts)", "Repair Kit",
    # Not resources, but important consumables to track
    "Flash Grenade", "Full Jerrycan",
    "Ness-Quick Weedkiller", "Pharmaceutical Products",
}


# killmax >= 2 — wiki-verified damage tiers
# Includes unloaded/empty variants: still strong once charged.
_STRONG_WEAPONS = {
    # Melee 2-2
    "Machete", "Lawnmower",
    # Battery 2-2 to 3-3 (loaded + empty)
    "Devastator (loaded)", "Devastator (empty)",
    "Chainsaw (loaded)", "Chainsaw (empty)",
    "Burning Laser Pointer (1 charge)", "Burning Laser Pointer (2 charges)",
    "Burning Laser Pointer (3 charges)", "Burning Laser Pointer (4 charges)",
    # Watergun 3-3 / 5-5 (loaded + empty)
    "Kalashni-Splash", "Kalashni-Splash (empty)",
    "Aqua-Splash (1 shot)", "Aqua-Splash (2 shots)",
    "Aqua-Splash (3 shots)", "Aqua-Splash (4 shots)",
    "Aqua-Splash (5 shots)", "Aqua-Splash (empty)",
    "Jerrycan Gun (ready)", "Jerrycan Gun (empty)",
    # Grenades 1-2 to 6-10
    "Exploding Water Bomb", "Exploding Grapefruit",
    "Water Bomb", "Mobile Phone",
}


# Construction blueprints — grouped by rarity tier
_BP_COMMON = {"Construction Blueprint (common)"}


_BP_UNCOMMON = {"Construction Blueprint (uncommon)"}


_BP_RARE = {"Construction Blueprint (rare)"}


_BP_VERY_RARE = {"Construction Blueprint (very rare!)"}


# Explorable ruin blueprints (read before normal ones: fata/blueprints.py). Fata's
# /towndata names them "Bunker Blueprint (…)", the legacy spy page "Bunker Construction …".
_BP_RUIN = {
    "Bunker Blueprint (uncommon)", "Bunker Blueprint (rare)", "Bunker Blueprint (very rare!)",
    "Hospital Blueprint (uncommon)", "Hospital Blueprint (rare)", "Hospital Blueprint (very rare!)",
    "Hotel Blueprint (uncommon)", "Hotel Blueprint (rare)", "Hotel Blueprint (very rare!)",
    "Bunker Construction Blueprint (uncommon)",
    "Bunker Construction Blueprint (rare)",
    "Bunker Construction Blueprint (very rare!)",
    "Hospital Construction Blueprint (uncommon)",
    "Hospital Construction Blueprint (rare)",
    "Hospital Construction Blueprint (very rare!)",
    "Hotel Construction Blueprint (uncommon)",
    "Hotel Construction Blueprint (rare)",
    "Hotel Construction Blueprint (very rare!)",
}


_ALL_BLUEPRINTS = _BP_COMMON | _BP_UNCOMMON | _BP_RARE | _BP_VERY_RARE | _BP_RUIN


def _sum_items(bank: list[dict], names: set[str], *, include_broken: bool = False) -> tuple[int, list[tuple[str, int, int]]]:
    """Return (total_count, [(name, count, broken), ...]) for items matching *names*.

    Merges multiple stacks of the same item (e.g. intact + broken Machete).
    """
    merged: dict[str, list[int]] = {}  # name -> [count, broken]
    for item in bank:
        if item["name"] in names:
            entry = merged.setdefault(item["name"], [0, 0])
            entry[0] += item["count"]
            entry[1] += item["broken"]
    matches: list[tuple[str, int, int]] = []
    total = 0
    for name, (count, broken) in merged.items():
        if not include_broken and count == 0:
            matches.append((name, 0, broken))
            continue
        matches.append((name, count, broken))
        total += count
    matches.sort(key=lambda t: (-t[1], t[0]))
    return total, matches


def _fmt_bucket(label: str, total: int, items: list[tuple[str, int, int]], *, show_items: bool = True) -> list[str]:
    """Format one summary bucket."""
    lines = [f"**{label}:** {total}"]
    if show_items and items:
        parts = []
        for name, count, broken in items:
            s = f"{name} ×{count}" if count else f"{name} (broken)"
            if broken and count:
                s += f" (+{broken} broken)"
            parts.append(s)
        lines.append("  " + ", ".join(parts))
    return lines


def format_bank_summary(data: dict) -> str:
    """Format a context-efficient bank summary with strategic groupings."""
    if data.get("error"):
        return f"Error: {data['error']}"

    bank = data["bank"]
    meta = data["meta"]

    if not bank:
        return "The bank is empty."

    lines = [
        f"## Bank Summary — {meta.get('town_name', '?')} Day {meta.get('day', '?')}",
        data_updated(meta),
        f"{len(bank)} item types, {sum(i['count'] for i in bank)} total items",
        "",
    ]
    lines += summary_lines(bank, data.get("buildings", []), bp_hint=" — reading order: get_blueprint_order")
    lines.append("")
    lines.append("_Use get_bank_inventory(detail='full') for the complete item list._")
    return "\n".join(lines)


def summary_lines(bank: list[dict], buildings: list[dict] | None = None, *,
                  rest_hint: str = "use detail='full' to see all", bp_hint: str = "") -> list[str]:
    """Strategic groupings of a list of items ({name, count, broken, category}):
    the bank, or every item lying in the desert. `rest_hint` says how to see the
    types no group covers."""
    lines: list[str] = []

    # Clean water — check if Water Filter / Water Purifier is built
    buildings = buildings or []
    has_purifier = any(
        b["built"] and b["name"] in ("Water Filter", "Water Purifier")
        for b in buildings
    )
    water_names = _CLEAN_WATER | (_CONDITIONAL_WATER if has_purifier else set())
    twater, itemswater = _sum_items(bank, water_names)
    purifier_note = " (incl. purifiable)" if has_purifier else ""
    lines.extend(_fmt_bucket(f"Clean water{purifier_note}", twater, itemswater))

    # Food
    t7, items7 = _sum_items(bank, _FOOD_7AP)
    t6, items6 = _sum_items(bank, _FOOD_6AP)
    tfc, itemsfc = _sum_items(bank, _FOOD_CONTAINERS)
    lines.extend(_fmt_bucket("Food 7+ AP", t7, items7))
    lines.extend(_fmt_bucket("Food 6 AP", t6, items6))
    if tfc:
        lines.extend(_fmt_bucket("Food containers", tfc, itemsfc))

    # Alcohol — separate category, can be drunk in addition to eating
    talc, itemsalc = _sum_items(bank, _ALCOHOL)
    lines.extend(_fmt_bucket("Alcohol (bonus to food)", talc, itemsalc))

    # Drugs & Meds
    tap, itemsap = _sum_items(bank, _AP_DRUGS)
    theal, itemsheal = _sum_items(bank, _HEALING)
    tstat, itemsstat = _sum_items(bank, _STATUS_DRUGS)
    lines.extend(_fmt_bucket("AP drugs", tap, itemsap))
    lines.extend(_fmt_bucket("Healing", theal, itemsheal))
    lines.extend(_fmt_bucket("Status drugs", tstat, itemsstat))

    # Defense items: the game's Defences category (its `defence` items), as planning.py counts them
    defense_names = {i["name"] for i in bank if i.get("category") == "Armor"}
    tdef, itemsdef = _sum_items(bank, defense_names)
    lines.extend(_fmt_bucket("Defense items", tdef, itemsdef))

    # Construction materials — metal and wood summed, then other key resources
    tmetal, _ = _sum_items(bank, _METAL)
    twood, _ = _sum_items(bank, _WOOD)
    lines.append(f"**Metal:** {tmetal} (Iron + Scrap + Support)")
    lines.append(f"**Wood:** {twood} (Log + Plank + Beam)")
    tres, itemsres = _sum_items(bank, _KEY_RESOURCES)
    top5 = ", ".join(f"{n} ×{c}" for n, c, _ in itemsres[:5])
    lines.append(f"**Other resources:** {tres} ({top5}, …)")

    # Blueprints
    tbp_ruin, itemsbp_ruin = _sum_items(bank, _BP_RUIN)
    tbp_common, _ = _sum_items(bank, _BP_COMMON)
    tbp_uncommon, _ = _sum_items(bank, _BP_UNCOMMON)
    tbp_rare, _ = _sum_items(bank, _BP_RARE)
    tbp_vrare, _ = _sum_items(bank, _BP_VERY_RARE)
    if tbp_ruin or tbp_common or tbp_uncommon or tbp_rare or tbp_vrare:
        ruin_detail = ""
        if tbp_ruin:
            ruin_names = ", ".join(n.replace(" Construction Blueprint", "").replace(" Blueprint", "")
                                   for n, *_ in itemsbp_ruin)
            ruin_detail = f"; ruin: {tbp_ruin} ({ruin_names}){bp_hint}"
        bp_parts = []
        for tier, count in (("common", tbp_common), ("uncommon", tbp_uncommon), ("rare", tbp_rare), ("very rare", tbp_vrare)):
            bp_parts.append(f"{tier} {count}")
        lines.append(f"**Blueprints:** {', '.join(bp_parts)}{ruin_detail}")

    # Weapons
    tweap, itemsweap = _sum_items(bank, _STRONG_WEAPONS, include_broken=True)
    lines.extend(_fmt_bucket("Strong weapons", tweap, itemsweap))
    # Count weak weapons: anything in Weapon category not in strong set
    weak_count = sum(i["count"] for i in bank
                     if i.get("category") == "Weapon" and i["name"] not in _STRONG_WEAPONS)
    lines.append(f"**Weak weapons:** {weak_count}")

    # Furniture — count only (exclude items already shown in named buckets above)
    tfurn = sum(i["count"] for i in bank if i.get("category") == "Furniture" and i["name"] not in defense_names)
    lines.append(f"**Furniture:** {tfurn} items")

    # Boxes / containers — count only
    boxes = [i for i in bank if i.get("category") == "Box"]
    if boxes:
        tbox = sum(i["count"] for i in boxes)
        names = ", ".join(f"{i['name']} ×{i['count']}" for i in boxes)
        lines.append(f"**Containers:** {tbox} ({names})")

    # Uncategorised remainder — items not captured in any bucket above
    accounted = (_CLEAN_WATER | _CONDITIONAL_WATER
                 | _FOOD_7AP | _FOOD_6AP | _ALCOHOL | _FOOD_CONTAINERS
                 | _AP_DRUGS | _HEALING | _STATUS_DRUGS
                 | defense_names | _METAL | _WOOD | _KEY_RESOURCES
                 | _STRONG_WEAPONS | _ALL_BLUEPRINTS)
    remainder = [i for i in bank
                 if i["name"] not in accounted
                 and i.get("category") not in ("Weapon", "Furniture", "Box")]
    if remainder:
        lines.append(f"**Other:** {len(remainder)} types not shown ({rest_hint})")

    return lines
