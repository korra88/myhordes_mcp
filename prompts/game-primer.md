# MyHordes in one page

The core rules you need to answer players correctly. Details are in the knowledge base
(index at the end). **Numbers come from tools, not from you**: when a tool computes
something (route, supplies, CP, defense, attack range), report its result; never redo the
math by hand, and never guess a value no tool gave you.

## The day

- 40 citizens, one town, a desert map around it. Every night at **23:59 (Paris time)** the
  horde attacks: town defense must beat the attack or citizens die. The site is closed
  for a few minutes around it (tools return `nightly_attack`: retry after).
- **Gate** must be closed before the attack (normally after 23:00, or earlier if everyone
  is inside). Citizens outside the walls at midnight are on their own.
- A town with fewer than 40 citizens has **no attack**: the day just extends, nothing
  resets or progresses until it fills.
- Attack grows fast: days 1–3 trivial, 4–10 exponential, 11–20 where most towns die,
  21+ only fortified towns survive. The real attack is random between a min and a max
  (`get_attack_forecast`, `get_defense_status`): defense inside that window is a gamble.
- **Map zombies are not the attack.** Killing zombies in the desert does not lower the
  night attack; 50 zombies on the map with a 25 000 attack is normal.

## Action Points (AP)

- 6 AP a day (**5 when wounded**). Moving, building and working cost AP; eating, drinking,
  searching, picking up, taking from the bank are free.
- **Food, water, alcohol and drugs raise AP to a level, they never add.** 5 AP + food = 6,
  not 11. One meal a day, one water for AP a day (Refreshed).
- 7 AP food → 7. Twinoid → 8. A second drug the same day makes the citizen an **addict**
  (permanent, dies any night without a drug). Alcohol → Drunk, then Hungover next day.

## Thirst

- **Thirst counter:** every desert move +1. Move 11 → Thirsty, 22 → Dehydrated, 33 → death.
  Only water resets it.
- **Overnight:** no water during the day → thirst goes up one level at midnight.
  Dehydrated at midnight → death. A Dehydrated citizen needs two rations.
- Thirsty and Refreshed are separate statuses: coming home Thirsty but Refreshed is safe.

## Desert

- **Moves are orthogonal**: AP cost = |x| + |y| (Manhattan). The "km" the game shows is
  the rounded straight-line distance: a "15 km" zone can cost 16 AP.
- **EP** (exploration points, scouts / shoes / bike) are spent before AP when leaving a
  zone at 3+ km.
- **Control Points:** zombie = 1 CP, citizen = 2 CP (up to 8 with boosts, **0 when
  Terrorised**, −1 when Drunk or Thirsty). If zombies have more CP than the citizens in a
  zone, everyone there is **Trapped**: cannot move or search, fleeing wounds. A lone
  citizen with no boosts is trapped by 3 zombies. `get_citizen_cp` has each citizen's CP.
- Ways home: Observation Platform level 3/4 teleports from 1/2 km (gate open); Heroic
  Return (hero skill) from 9–15 km; Rescue (cast from town) on a citizen 1–3 km out.

## Town

- Bank items are shared. Buildings cost AP + resources; many need a **blueprint** first.
  **Read explorable-ruin blueprints (Bunker/Hospital/Hotel) before normal ones**: a normal
  blueprint can steal a building from the ruin's small pool and waste the ruin blueprint.
- **Defensive Focus** raises each defensive object in the bank (1.5 → 3.0 DP).
  **Defensive Adjustment** adds a % to total defense (+10 → +13%). Different things.
- **Watchmen** add personal defense at the risk of their lives.
- Professions: Guardian, Scavenger, Scout, Survivalist, Tamer, Technician (heroes);
  residents have no hero actions. Use `search_wiki` for any ability: never guess.

## Coordinated ("Opti") towns

Signs a town follows a plan, not a crisis: a big stock of poisons/toxins in the bank
(fuel for **All or Nothing**, which turns bank items into one night of defense), a
Tamer-heavy roster, one quadrant of the map never cleaned (zombie zoo), a Survivalist
dying mid-game (Ghoul sacrifice), everyone leaving together at the end (exodus).
Unfilled slots in a coalition town are often deliberate.

## Reading the data

- Data comes from **Fata Morgana**, updated only when a player sends it. Every tool shows
  `Data updated:` with its age and, when old, `may be stale` or `STALE`: quote it and
  follow the label. A zone's line says what is from today and what from an older day.
- **Normal, not alarming:** empty water in the bank (the well is there to be used),
  citizens outside in daytime, gate open before evening, American players coming back at
  22:00–23:00. Alarming: gate open near the attack, citizens far out late, defense below
  the attack, a planned build missing a resource.

## Knowledge base — what to search

`search_knowledge(query, section)` returns the curated notes; `search_wiki` the game wiki.
The search matches words, so use specific terms (a file name returns the whole file).

| Question about | Search |
|---|---|
| Thirst counter, EP, drinking/eating rules, ways home | `search_knowledge("expedition-planning", "tactics")` |
| CP boosters, statuses, AP sources, blueprints, camping | `search_knowledge("CP boosters" / "drunk drugged" / "camping blueprint", "tactics")` |
| What to build at this stage | `search_knowledge("basic" (day 1–5) / "intermediate" (6–10) / "defense-focus" (9–15) / "advanced" (15+) / "wonders", "buildings")`, plus `get_build_options` |
| Opti towns | `search_knowledge("AoN" / "zombie zoo" / "Ghoul" / "Dump vault", "tactics")` |
| Season 19 meta | `search_knowledge("s19-meta", "tactics")` |
| An item, building, status, profession | `search_wiki("<name>")` |

For an expedition, call `find_expedition_path` then `plan_expedition_supplies`.
