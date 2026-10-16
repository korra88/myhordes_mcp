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
| Thirst step counter (11/22/33), only water resets it | `fata/supplies.py`, `fata/pathing.py` | `plan_expedition_supplies`, `find_expedition_path` |
| EP: paid first leaving a 3+ km zone, refill only shoes/bike part | `fata/supplies.py` | `plan_expedition_supplies` |
| Manhattan move cost, rounded-Euclidean km | `fata/risk.py:km`, `fata/pathing.py` | route tools |
| Observation Platform teleport range, Labyrinth entry cost | `fata/risk.py:teleport_range`, `fata/changes.py:platform_discount` | supplies, `get_town_changes` |
| Zone CP vs zombies, Trapped | `fata/risk.py`, `fata/cp.py` | `find_expedition_path`, `get_citizen_cp`, overview |
| Zone / citizen data staleness (by day) | `fata/risk.py:_staleness_tag`, `_zone_freshness` | map, overview |
| Snapshot age + stale label (1 h / 3 h) in every header | `utils/clock.py:data_updated`, `meta.live` set in `fata/client.py` | every Fata tool |
| Zones seen today (platform radius): today's danger beats an older zombie count | `fata/towndata.py` `danger_today`, `risk.py:_zone_threat`, `pathing.py:_classify_cell` | map, route tools |
| Dried: newest of zone update / scavenger radar / excavation | `fata/towndata.py` | map, `get_town_changes` |
| Building efficiency (def/AP, def/resource), what the bank can build | `fata/planning.py` | `get_build_options` |
| Defensive Focus multiplier (as Fata reports it) | `fata/town.py` | `get_defense_status` |
| Attack window verdict: SAFE / AT RISK / DANGER with the gap | `fata/town.py:format_defense` | `get_defense_status` |
| Gate: open by day is normal, ⚠ only from 23:00 on Fata's time (old data says so) | `fata/risk.py:gate_line`, `gate_alert` | overview, defense, citizens, `get_town_changes` |

## Candidates (prose today)

Ordered by value for the bot. "Prose" is where the rule lives now.

| # | Rule | Prose | Idea | Notes |
|---|---|---|---|---|
| 3 | **Ruin blueprints before normal ones** | `strategy-quirks.md`, `game-mechanics.md` | `get_bank_inventory` flags "read the Bunker/Hospital/Hotel blueprints first" when both kinds are in the bank | `fata/bank.py` groups only `Construction Blueprint (…)` today. The parent-building exception stays prose. |
| 4 | **Distances for one zone**: moves, km, EP zone, platform teleport, Heroic Return (9/11/13/15 km), Rescue (1/2/3 km) | `expedition-planning.md` | `get_zone_details` prints them | Ranges verified in source: both use `Zone::getDistance` (km). |
| 5 | **Night alarms**: gate open near the attack, citizens out late, defense short | `session-protocols.md`, primer | Overview flags them with the time; the "normal states" list leaves the prose | Needs the clock and the gate state from Fata. |
| 6 | **AP per citizen per day**: 6, 5 wounded; food/water raise to a level | `game-mechanics.md` | Already in supplies; a `citizen` view would need statuses Fata may not expose | Check `towndata.py` for statuses first. |
| 7 | **Map zombie respawn threshold** (25 × day) | `opti-town-meta.md` | `get_scout_map` prints total map zombies vs threshold | S18 formula, not checked in source: verify before coding. |
| 8 | **Desert soul points** `days × (days + 1) / 2` | `opti-town-meta.md` | Low value | Verify in source. |

Not candidates: strategy and reading other players' intent (Opti signs, coalition
habits, player timezones). They stay in `knowledge/tactics/`.

## Known prose issues

- `game-mechanics.md` repeats the thirst counter and the Observation Platform rules from
  `expedition-planning.md`. Keep one copy when either moves to code.
