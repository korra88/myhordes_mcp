# Game mechanics in code

Rules the model must apply the same way every time belong in Python, not in a `.md` the
model reads and re-applies. The tool computes, the prose (`knowledge/tactics/`,
`prompts/game-primer.md`) only explains, and says which tool to trust. Small models
(Sonnet on the Discord bot, local gemma) get the arithmetic wrong; code does not.

How to move one rule:

1. Check it in the game source (`myhordes-docker/`, see `source-map.md`) and cite the
   class in the module docstring, as `fata/supplies.py` does.
2. Implement it in the module that owns the data; check it against a cached town in
   `towns/*/cache/` (the repo has no test suite yet).
3. Make the tool output state the result in words ("stale: 4 h old", "teleport: yes").
4. Cut the procedure from the `.md`: keep a short explanation and the tool name.
5. Update the tables below.

## Already in code

| Rule | Where | Tool |
|---|---|---|
| Consumables restore to a level, once-a-day limits, drugs/addiction, alcohol | `fata/supplies.py` | `plan_expedition_supplies` |
| Thirst step counter (11/22/33), only water resets it | `fata/supplies.py` (`THIRST_STEP`, `thirst_state`), `fata/pathing.py` | `plan_expedition_supplies`, `find_expedition_path` |
| EP: paid first leaving a 3+ km zone, refill only shoes/bike part | `fata/supplies.py` | `plan_expedition_supplies` |
| Manhattan move cost, rounded-Euclidean km | `fata/geo.py:km`, `fata/pathing.py` | route tools |
| Observation Platform teleport range and AP saved, Labyrinth entry cost | `fata/risk.py` (`teleport_range`, `platform_return_saving`), `fata/supplies.py:end_requirements` | supplies, `get_town_changes` |
| Rucksack slots along a trip: `slots` free at departure (default 5 = 4 + Enduring 1); at each pickup, supplies still to use (a use at the pickup zone counts as made) + items picked so far ≤ slots, a picked item takes a slot heavy or not; supplies are never dropped (plan redone with fewer departure slots only if thirst/AP outcome stays the same, else not feasible + slots missing) | `fata/pickups.py` (`fit`, `timeline`) | `plan_expedition_supplies` (`slots`, `pickups`) |
| Heavy items: one per citizen (bike, trolley and heavy pickups count; more is refused); Guardian (`guardian`) carries two, group CP -2 on every leg after the 2nd heavy pickup (per-leg CP in `search_route`, `route_risks`) | `fata/pickups.py` (`heavy_check`, `leg_cps`), `fata/pathing.py` | `plan_expedition_supplies` |
| Second Wind by Enduring level 1-4 (skill levels 0-3 in code) | `fata/supplies.py` | `plan_expedition_supplies` (`second_wind`) |
| Zone CP vs zombies, Trapped | `fata/risk.py`, `fata/cp.py` | `find_expedition_path`, `get_citizen_cp`, overview |
| Zone / citizen data staleness (by day) | `fata/risk.py` (`age_days`, `is_stale`, `_staleness_tag`, `_zone_freshness`) | map, overview |
| Snapshot age + stale label (1 h / 3 h) in every header | `utils/clock.py:data_updated`, `meta.live` set in `fata/client.py` | every Fata tool |
| Zones seen today (platform radius): today's danger beats an older zombie count | `fata/towndata.py` `danger_today`, `risk.py:_zone_threat`, `pathing.py:_classify_cell` | map, route tools |
| Dried: newest of zone update / scavenger radar / excavation | `fata/towndata.py` | map, `get_town_changes` |
| Building efficiency (def/AP, def/resource), what the bank can build | `fata/planning.py` | `get_build_options` |
| Defensive Focus multiplier (as Fata reports it) | `fata/town.py` | `get_defense_status` |
| Attack window verdict: SAFE / AT RISK / DANGER with the gap | `fata/town.py:format_defense` | `get_defense_status` |
| Blueprint reading order: random pick among locked buildings with unlocked parent; ruin lists per tier from Fata's catalogue; wasted / hold / odds | `fata/blueprints.py` | `get_blueprint_order` |
| One zone's reach: moves, km, EP zone, platform teleport (level + gate), Heroic Return R1–R4 9/11/13/15 km, Rescue U1–U3 1/2/3 km | `fata/risk.py:zone_reach` | `get_zone_details` (x1=x2, y1=y2) |
| Zombies to kill on a route: per zone exact (today), grown by the nights since (+1 average, +2 at most), or from the danger band; zone n = n ÷ 2 pairs + n mod 2 single (a 2-kill weapon on 1 zombie wastes a kill); everything on the route must die (Despair comes after the spread) | `fata/kills.py` (`zone_estimate`, `analyse_route`, `buckets`), `fata/risk.py:zombie_growth` | `plan_kill_route` |
| Kill weapons from the bank: Laser Pointer (Battery 4/3/2 charges), Machete, Battery Launcher Mk. II, Serrated Knife, Aqua-Splash, Water Pistol, repair items; average and worst capacity per kit, slots, what the bank cannot cover | `fata/kills.py` (`WEAPONS`, `pick_kit`, `capacity`) | `plan_kill_route` |
| Zombie clusters (the likely zoo) and their sides; respawn warning after the planned kills | `fata/kills.py` (`zoo_clusters`, `respawn_after_kills`), `fata/risk.py:respawn_totals` | `plan_kill_route` |
| Nightly zombie growth (spreadCycleMH): +1 (90%) / +0 / +2 per zone with zombies, 1–2 on an empty neighbour of a bigger zone, 8 neighbours; one growth function for the map, route risks and kills | `fata/risk.py` (`zombie_growth`, `_spread_risk_for_clear`) | map, route tools, `plan_kill_route` |
| Global respawn: whole map < 25 × (day + 1) zombies at night (15 in small towns) → regrowth from the day-1 layout; compared with what Fata counts | `fata/risk.py:respawn_check` | `get_scout_map` |
| Night alarms on Fata's time (old data says so): gate open from 23:00, citizens outside from 22:00 (farthest first), defense below tonight's estimate from 23:00; by day the defense verdict says it is normal | `fata/risk.py:night_alerts` (`gate_alert`, `outside_alert`, `defense_alert`) | overview, defense, citizens, `get_town_changes` |

## Candidates (prose today)

None open (2026-10-16): items 1–7 are in code (table above), 8 stays prose (below).
Add a row here when a rule the model keeps getting wrong could be computed:

| # | Rule | Prose | Idea | Notes |
|---|---|---|---|---|

Not candidates: strategy and reading other players' intent (Opti signs, coalition
habits, player timezones). They stay in `knowledge/tactics/`.

## Rules that stay prose

- **AP and statuses per citizen** (max 6 / 5 wounded, food/water/drugs raise to a level,
  overnight thirst, Hooked): Fata does not send citizen statuses, so no tool can apply them
  to a citizen. `game-mechanics.md` "Action Points" / "Water and thirst" was checked against
  the game code on 2026-10-16 (it wrongly said water does not clear Thirsty, and missed that
  the thirst counter restarts at midnight). The consumable rules for a route are in code
  (`plan_expedition_supplies`).
- **Desert soul points** (`days × (days + 1) / 2`, community formula): score only, no game
  decision depends on them; left in `opti-town-meta.md`, unverified, on purpose.
