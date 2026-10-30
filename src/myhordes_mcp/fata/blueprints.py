"""Blueprint reading order: which blueprints in the bank to read first, which to hold.

Rules from the game source (myhordes-docker: ProcessTownEffect, BuildingPrototypeRepository::
findProspectivePrototypes, config/app/rules.yml explorable_ruin_params.plan_limits):

- Reading a blueprint unlocks one building picked uniformly at random among the buildings
  not unlocked yet whose parent is unlocked (or that have no parent).
- A normal Construction Blueprint filters that set by building rarity (1 common, 2 uncommon,
  3 rare, 4 very rare).
- A Bunker / Hotel / Hospital blueprint filters it by that ruin's list for its tier
  (6 uncommon, 10 rare, 5 very rare in normal towns; each list holds buildings of that
  rarity; hardcore towns have other lists). The lists come with Fata's catalogue
  (towndata `ruin_pools`).
- If nothing matches, the blueprint is consumed and unlocks nothing.

So a normal blueprint can take a building out of a ruin's small pool, and a ruin blueprint
whose remaining buildings all wait on a locked parent is wasted until that parent is in.
"""

from ..utils.fmt import header

TIERS = {1: "common", 2: "uncommon", 3: "rare", 4: "very rare"}
RUIN_LABEL = {"bunker": "Bunker", "hotel": "Hotel", "hospital": "Hospital"}
EXPLORABLE = {"Abandoned Bunker": "bunker", "Abandoned Hotel": "hotel", "Abandoned Hospital": "hospital"}

# Item uid → (pool, tier). pool "normal" = Construction Blueprint.
_BLUEPRINT_UIDS = {"bplan_c": ("normal", 1), "bplan_u": ("normal", 2), "bplan_r": ("normal", 3),
                   "bplan_e": ("normal", 4)}
for _prefix, _ruin in (("bb", "bunker"), ("hb", "hotel"), ("mb", "hospital")):
    for _suffix, _tier in (("u", 2), ("r", 3), ("e", 4)):
        _BLUEPRINT_UIDS[f"{_prefix}plan_{_suffix}"] = (_ruin, _tier)


def _label(pool: str, tier: int) -> str:
    kind = "Construction" if pool == "normal" else RUIN_LABEL[pool]
    return f"{kind} Blueprint ({TIERS[tier]})"


def _bank_blueprints(bank: list[dict]) -> dict[tuple[str, int], int]:
    out: dict[tuple[str, int], int] = {}
    for item in bank:
        key = _BLUEPRINT_UIDS.get(item.get("uid") or "")
        if key and item["count"]:
            out[key] = out.get(key, 0) + item["count"]
    return out


def _ruins_on_map(data: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for z in data.get("zones", []):
        ruin = EXPLORABLE.get((z.get("ruin") or {}).get("name"))
        if ruin:
            out.setdefault(ruin, []).append(z["coords"])
    return out


def pool_state(buildings: list[dict], pool: str, tier: int) -> dict:
    """What a blueprint of this pool and tier could unlock now.

    ready:   buildings it can pick right now (locked, parent unlocked)
    waiting: [(building, parent)] locked buildings of the pool whose parent is locked
    size:    the whole pool (ruin list for the tier, or every building of that rarity)
    """
    by_id = {b["id"]: b for b in buildings}
    members = [b for b in buildings if b["rarity"] == tier
               and (pool == "normal" or pool in b.get("ruin_pools", []))]
    locked = [b for b in members if not b["blueprint_found"]]
    ready, waiting = [], []
    for b in locked:
        parent = by_id.get(b["parent_id"]) if b["parent_id"] else None
        if parent is None or parent["blueprint_found"]:
            ready.append(b)
        else:
            waiting.append((b, parent))
    return {"ready": ready, "waiting": waiting, "size": len(members)}


def blueprint_order(data: dict) -> dict:
    """Reading plan for the blueprints in the bank: read now (in order), read after the
    ruin ones, hold, wasted. Also the state of each ruin pool on the map."""
    buildings = data["buildings"]
    in_bank = _bank_blueprints(data.get("bank", []))
    on_map = _ruins_on_map(data)
    # Ruins whose pools a normal blueprint should not raid: those with blueprints in the
    # bank, and those on the map (they may still yield blueprints).
    guarded = {pool for pool, _ in in_bank if pool != "normal"} | set(on_map)

    plan = {"ruin_ready": [], "normal_free": [], "normal_after": [], "hold": [], "wasted": []}
    for (pool, tier), count in sorted(in_bank.items(), key=lambda kv: (kv[0][0] == "normal", -kv[0][1])):
        st = pool_state(buildings, pool, tier)
        entry = {"label": _label(pool, tier), "count": count, "pool": pool, "tier": tier, **st}
        if pool != "normal":
            if st["ready"]:
                plan["ruin_ready"].append(entry)
            elif st["waiting"]:
                plan["hold"].append(entry)
            else:
                plan["wasted"].append(entry)
            continue
        if not st["ready"]:
            plan["hold" if st["waiting"] else "wasted"].append(entry)
            continue
        overlap = [b for b in st["ready"] if set(b.get("ruin_pools", [])) & guarded]
        entry["overlap"] = overlap
        plan["normal_after" if overlap else "normal_free"].append(entry)

    ruins = {}
    for ruin, coords in on_map.items():
        ruins[ruin] = {"coords": coords,
                       "tiers": {t: pool_state(buildings, ruin, t) for t in (2, 3, 4)}}
    return {"in_bank": in_bank, "plan": plan, "ruins": ruins, "guarded": guarded}


def _names(bs: list[dict], limit: int = 6) -> str:
    names = [b["name"] for b in bs]
    return ", ".join(names[:limit]) + (f", +{len(names) - limit} more" if len(names) > limit else "")


def _waiting_text(waiting: list[tuple[dict, dict]], buildings: list[dict]) -> str:
    """'X needs Y (common blueprint: 1 in 18 per read)' — the odds that a normal blueprint
    of Y's rarity unlocks Y now, when Y itself is reachable."""
    parts = []
    for b, p in waiting:
        if not p["rarity"]:
            parts.append(f"{b['name']} needs {p['name']} built first")
            continue
        ready = pool_state(buildings, "normal", p["rarity"])["ready"]
        odds = f": 1 in {len(ready)} per read" if any(x["id"] == p["id"] for x in ready) else ""
        parts.append(f"{b['name']} needs {p['name']} ({TIERS[p['rarity']]} Construction Blueprint{odds})")
    return "; ".join(parts)


def format_blueprint_order(data: dict) -> str:
    if data.get("error"):
        return f"Error: {data['error']}"
    if not any("ruin_pools" in b for b in data.get("buildings", [])):
        return "Blueprint order needs Fata's /towndata catalogue; this day's data comes from the legacy archive."
    meta = data["meta"]
    r = blueprint_order(data)
    plan = r["plan"]
    lines = [header("Blueprint reading order", meta)]
    if r["ruins"]:
        lines.append("Explorable ruin on the map: " + ", ".join(
            f"Abandoned {RUIN_LABEL[k]} {' '.join(v['coords'])}" for k, v in r["ruins"].items()))
    buildings = data["buildings"]

    if not r["in_bank"]:
        lines += ["", "No blueprints in the bank."]
    else:
        step = 0
        if plan["ruin_ready"] or plan["normal_free"] or plan["normal_after"]:
            lines += ["", "### Read in this order"]
        for e in plan["ruin_ready"]:
            step += 1
            lines.append(f"{step}. {e['label']} ×{e['count']} — picks one of {len(e['ready'])}: {_names(e['ready'])}")
        for e in plan["normal_free"]:
            step += 1
            lines.append(f"{step}. {e['label']} ×{e['count']} — any time: none of its {len(e['ready'])} "
                         "candidates is in a ruin pool")
        for e in plan["normal_after"]:
            step += 1
            k, n = len(e["overlap"]), len(e["ready"])
            lines.append(f"{step}. {e['label']} ×{e['count']} — last: {k} of its {n} candidates are ruin "
                         f"buildings ({round(100 * k / n)}% per read to take one: {_names(e['overlap'])}). "
                         "Hold it while that ruin still yields blueprints.")
        if plan["hold"]:
            lines += ["", "### Hold (nothing to unlock until a parent is in)"]
            for e in plan["hold"]:
                lines.append(f"- {e['label']} ×{e['count']} — {_waiting_text(e['waiting'], buildings)}")
        if plan["wasted"]:
            lines += ["", "### Do not read (would be consumed for nothing)"]
            for e in plan["wasted"]:
                lines.append(f"- {e['label']} ×{e['count']} — every building it can unlock is already unlocked")

    if r["ruins"]:
        lines += ["", "### Ruin pools (what its blueprints can still unlock)"]
        for ruin, v in r["ruins"].items():
            for tier, st in v["tiers"].items():
                if st["ready"]:
                    state = f"{len(st['ready'])} ready: {_names(st['ready'])}"
                elif st["waiting"]:
                    state = f"waiting — {_waiting_text(st['waiting'], buildings)}"
                else:
                    state = "exhausted (a blueprint of this tier is wasted)"
                if st["ready"] and st["waiting"]:
                    state += f"; waiting — {_waiting_text(st['waiting'], buildings)}"
                lines.append(f"- {RUIN_LABEL[ruin]} {TIERS[tier]} ({st['size']}): {state}")
    return "\n".join(lines)
