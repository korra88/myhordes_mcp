# Game mechanics in code

Rules the model must apply the same way every time belong in Python, not in a `.md` the
model reads and re-applies. The tool computes, the prose (`knowledge/tactics/`,
`prompts/game-primer.md`) only explains, and says which tool to trust. Small models
(Sonnet on the Discord bot, local gemma) get the arithmetic wrong; code does not.

## One place: `src/myhordes_mcp/fata/game.py`

Every rule of the game's simulation (constants and pure functions, each citing the game class
or method it was checked against) lives in `fata/game.py`. Planners, formatters, Fata parsing
and the bot-facing texts import from it and never restate a number. When a rule changes or must
be re-checked against the source (`myhordes-docker/`, see `source-map.md`), open `game.py`, find
the topic below, and nothing else needs editing. `fata/geo.py` stays the home of coordinates and
distances (`moves`, `km`, `spread_steps`, the zone map); `game.py` imports it.

How to move or add one rule:

1. Check it in the game source and cite the class / method in `game.py`.
2. Implement it there as a pure function or constant; planners import it. Do not write the same
   number or condition twice (grep before adding).
3. Check it against a cached town in `towns/*/cache/`; `make golden` (outputs) and
   `tests/camping_checks.py` (camping rules) must stay green.
4. Make the tool output state the result in words ("stale: 4 h old", "teleport: yes").
5. Cut the procedure from the `.md`: keep a short explanation and the tool name.
6. Update the index below.

## Index of `game.py` by topic

| Topic | Names in `game.py` | Used by |
|---|---|---|
| Danger levels as zombie counts | `DANGER_LEVELS` (labels), `DANGER_BAND`, `DANGER_TOP`, `danger_band` | `risk.threat_text`, `zones`, `camping`, estimates |
| Which reading is today's, reading age | `zone_is_today`, `age_days` | `risk`, `pathing`, `zones`, `camping` |
| Nightly zombie growth (`MapMaker::spreadCycleMH`): +1 (90%) / +0 / +2 per zone with zombies, 1-2 on an empty neighbour of a bigger zone, 8 neighbours | `GROWTH_AVG`, `GROWTH_MAX`, `zombie_growth`, `zombie_sources`, `Arrival`, `zombie_arrival`, `earliest_zombie_day` | one model for the map, zone details, route risks, kills and camping |
| The one zombie estimate of a zone (exact today / grown / danger band / early / spread / exposed) | `Estimate`, `zone_estimate` (`_by_arrival`, `_unvisited`) | `risk.zone_threats` / `threat_text`, `pathing`, `kills`, `camping._project_zombies` |
| Global respawn threshold (`MapMaker::aboveMinNumberOfZombies`): 25 x (day + 1), 15 in small towns | `RESPAWN_PER_DAY`, `DEFAULT_RESPAWN_PER_DAY`, `respawn_threshold` | `risk.respawn_totals` / `respawn_check`, `kills` |
| EP zone (>= 3 km, `Zone::getDistance`) | `EP_MIN_KM`, `ep_zone`, `pays_ep` | `supplies.plan`, `pathing.step_rows`, `risk.zone_reach` |
| Control points | `CP_PER_CITIZEN`, `MAX_CP_PER_CITIZEN` | `cp`, `pathing`, `kills`, `supplies`, `risk.trapped_citizens` |
| Observation Platform: teleport range (level 3 = 1 km, 4 = 2 km), AP saved | `OBSERVATION_PLATFORM`, `platform_level`, `teleport_range`, `platform_return_saving` | `supplies.end_requirements`, `pathing.loop_return`, `risk`, `changes`, `snapshot` |
| Hero skill reach: Heroic Return R1-R4 9/11/13/15 km, Rescue U1-U3 1/2/3 km | `HEROIC_RETURN_KM`, `RESCUE_KM`, `skill_level_for` | `risk.zone_reach` |
| Camping odds (`CitizenHandler::getCampingOdds`): the twelve terms, previous-nights tables, Pandemonium, crowd, distance, cap, pro camper limit | `PREVIOUS`, `PRO_CAMPER_LIMIT`, `PANDA_TOWN_BONUS`, `CROWD`, `DISTANCE`, `SKILLS`, `LIGHTHOUSE_UID`, `LIGHTHOUSE_BONUS`, `NIGHT_BONUS`, `HIDING_FROM_HOUR`, `DEVASTATED_PENALTY`, `NO_RUIN_TERM`, `BURIED_RUIN_TERM`, `ZOMBIE_PENALTY(_VEST)`, `TOMB_BONUS`, `CAMP_ITEM_BONUS`, `is_pro_camper`, `odds_cap`, `ruin_term`, `camping_terms`, `camping_odds`, `is_panda`, `lighthouse_built` | `camping`, `groupcamp`, `camplog` |
| Camp level: improve +5, install +9, act only below 50, -15 a night, installable items, camp items, steak | `IMPROVE_LEVEL`, `INSTALL_LEVEL`, `MAX_LEVEL_TO_ACT`, `NIGHTLY_DROP`, `level_after_nights`, `level_ok`, `improves_left`, `position_terms`, `INSTALLABLE`, `ITEM_UIDS`, `STEAK_UID` | `camping.plan_upgrades` / `max_level_plan`, `groupcamp`, `camp_zones`, `towndata` (units) |
| AP and thirst: max AP 6 (5 wounded), EP pools (scout 2, shoes 1, bike 2), thirst counter (11 / 22 / 33), Labyrinth entry | `MAX_AP`, `WOUNDED_MAX_AP`, `SCOUT_EP`, `SHOES_EP`, `BIKE_EP`, `THIRST_STEP`, `THIRST_DEAD`, `LABYRINTH_ENTRY_AP`, `ap_max`, `ep_extension`, `ep_max`, `count_move`, `thirst_level`, `thirst_counter_at` | `supplies`, `pathing`, `groupcamp`, `planning` |
| Item effects: water, food, drugs, alcohol, coffee; Second Wind by Enduring level | `Item`, `ITEMS`, `SECOND_WIND`, `refill_ep`, `drink_water`, `eat_food`, `take_drug`, `drink_alcohol`, `drink_coffee`, `use_second_wind` | `supplies.plan` (the search) |
| Kill weapons and pairs / singles | `Weapon`, `WEAPONS`, `state_cap`, `kill_buckets` | `kills` |
| Scout with Camouflage Vest detection chance | `scout_detection` | `pathing` |
| Wind refill of depleted zones | `WIND_REFILL`, `WIND_DISTANCE`, `WIND_NOT_DEPLETED`, `wind_refill_chance` | `zones` |
| Heavy items (one per citizen, Guardian two, group CP -2) | `heavy_cap`, `GUARDIAN_CP_LOSS` | `pickups` |
| Town size before the first attack | `TOWN_SIZE` | `town.roster_line` |

Rules that are not in `game.py` on purpose (they are planner policy or read Fata data, not the
game): route cost weights (`pathing.WALK`), the supplies search cost order (`supplies`), kit
selection (`kills.pick_kit`), the group camping DP (`groupcamp.solve`), evening alert hours
(`risk`: the players' thresholds), data freshness, CP-reading validity (`risk.zone_cp`), item-name
classification of the bank (`bank`), death-type numbers (`towndata.death_day`).

## Where each tool applies them

| Rule | Where | Tool |
|---|---|---|
| Consumables restore to a level, once-a-day limits, drugs/addiction, alcohol | `game.py` effects; search in `fata/supplies.py` | `plan_expedition_supplies` |
| Thirst step counter (11/22/33), only water resets it | `game.py` (`THIRST_STEP`, `count_move`); `supplies.thirst_state`, `pathing.step_rows` | `plan_expedition_supplies`, `find_expedition_path` |
| EP: paid first leaving a 3+ km zone, refill only shoes/bike part | `game.py` (`pays_ep`, `refill_ep`) | `plan_expedition_supplies` |
| Manhattan move cost, rounded-Euclidean km | `fata/geo.py:km`, `moves` | route tools |
| Observation Platform teleport range and AP saved, Labyrinth entry cost | `game.py`; `fata/supplies.py:end_requirements` | supplies, `get_town_changes` |
| Rucksack slots along a trip: `slots` free at departure (default 5 = 4 + Enduring 1); at each pickup, supplies still to use (a use at the pickup zone counts as made) + items picked so far <= slots, a picked item takes a slot heavy or not; supplies are never dropped (plan redone with fewer departure slots only if thirst/AP outcome stays the same, else not feasible + slots missing) | `fata/pickups.py` (`fit`, `timeline`) | `plan_expedition_supplies` (`slots`, `pickups`) |
| Heavy items: one per citizen (bike, trolley and heavy pickups count; more is refused); Guardian (`guardian`) carries two, group CP -2 on every leg after the 2nd heavy pickup | `game.py` (`heavy_cap`, `GUARDIAN_CP_LOSS`); `fata/pickups.py` (`heavy_check`, `leg_cps`), `fata/pathing.py` | `plan_expedition_supplies` |
| Second Wind by Enduring level 1-4 (skill levels 0-3 in code) | `game.py` (`SECOND_WIND`, `use_second_wind`) | `plan_expedition_supplies` (`second_wind`) |
| Zone CP vs zombies, Trapped | `game.py` (CP); `fata/risk.py`, `fata/cp.py` | `find_expedition_path`, `get_citizen_cp`, overview |
| Zone / citizen data staleness (by day) | `fata/risk.py` (`is_stale`, `_staleness_tag`, `_zone_freshness`) | map, overview |
| Snapshot age + stale label (1 h / 3 h) in every header | `utils/clock.py:data_updated`, `meta.live` set in `fata/client.py` | every Fata tool |
| Zones seen today (platform radius): today's danger beats an older zombie count | `fata/towndata.py` `danger_today`, `game.py:zone_estimate`, `risk.py:threat_text`, `pathing.py:_classify_cell` | map, route tools |
| Dried: newest of zone update / scavenger radar / excavation | `fata/towndata.py` | map, `get_town_changes` |
| Building efficiency (def/AP, def/resource), what the bank can build | `fata/planning.py` | `get_build_options` |
| Defensive Focus multiplier (as Fata reports it) | `fata/town.py` | `get_defense_status` |
| Attack window verdict: SAFE / AT RISK / DANGER with the gap | `fata/town.py:format_defense` | `get_defense_status` |
| Blueprint reading order: random pick among locked buildings with unlocked parent; ruin lists per tier from Fata's catalogue; wasted / hold / odds | `fata/blueprints.py` | `get_blueprint_order` |
| One zone's reach: moves, km, EP zone, platform teleport (level + gate), Heroic Return, Rescue | `fata/risk.py:zone_reach` (text) over `game.py` | `get_zone_details` (x1=x2, y1=y2) |
| Zombies to kill on a route: per zone exact (today), grown by the nights since, or from the danger band; zone n = n / 2 pairs + n mod 2 single; everything on the route must die (Despair comes after the spread) | `fata/kills.py` (`analyse_route`), `game.py` (`zone_estimate`, `kill_buckets`) | `plan_kill_route` |
| Kill weapons from the bank: Laser Pointer (Battery 4/3/2 charges), Machete, Battery Launcher Mk. II, Serrated Knife, Aqua-Splash, Water Pistol, repair items; average and worst capacity per kit, slots, what the bank cannot cover | `game.py` (`WEAPONS`, `state_cap`); `fata/kills.py` (`pick_kit`, `capacity`) | `plan_kill_route` |
| Zombie clusters (the likely zoo) and their sides; respawn warning after the planned kills | `fata/kills.py` (`zoo_clusters`, `respawn_after_kills`), `fata/risk.py:respawn_totals` | `plan_kill_route` |
| Global respawn compared with what Fata counts | `game.py:respawn_threshold`, `fata/risk.py:respawn_check` | `get_scout_map` |
| Night alarms on Fata's time (old data says so): gate open from 23:00, citizens outside from 22:00 (farthest first), defense below tonight's estimate from 23:00; by day the defense verdict says it is normal | `fata/risk.py:night_alerts` | overview, defense, citizens, `get_town_changes` |

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
