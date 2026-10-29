# Weapons — killing zombies in the desert

Keywords: weapon, weapons, kill, kills, killing, zombie, zombies, zed, zeds, zoo trimming,
trim the zoo, cutting zeds, clearing a zone, armoury, break, broken, battery, water pistol.
All tables at once: `search_knowledge("weapons", "tactics")`.

Checked in the game code (`ActionDataService`, v5.0.6); the wiki table agrees except where
noted. Using a weapon costs **0 AP**. Melee weapons need AP left (not Exhausted) and no hand
wound. Grenades kill in the whole zone; every other weapon kills per use.
Killing map zombies does not lower the night attack (see the primer).

**Avg** = expected kills before the weapon breaks or empties = kills × kill% ÷ break%
(per load for water and battery weapons). H = heavy (one per citizen).

## Melee

| Weapon | Kills | Kill % | Break % | Avg | After |
|---|---|---|---|---|---|
| Lawnmower (H) | 2 | 100 | 20 | 10 | Broken |
| Machete | 2 | 100 | 25 | 8 | Broken |
| Primitive Hurling Stick | 1 | 60 | 15 | 4 | Broken |
| Serrated Knife | 1 | 100 | 33 | 3 | Broken |
| Old Washing Machine (H) | 1 | 100 | 40 | 2.5 | Broken |
| Beer Fridge (H) | 1 | 100 | 40 | 2.5 | Broken |
| Carcinogenic Oven (H) | 1 | 100 | 43 (wiki: 40) | 2.3 | Broken |
| PC Base Unit (H) | 1 | 100 | 50 | 2 | Broken |
| Unshaped Concrete Blocks (H) | 1 | 100 | 50 | 2 | Broken — a defensive object |
| Rusty Chain | 1 | 50 | 25 | 2 | Broken |
| Adjustable Spanner | 1 | 33 | 20 | 1.7 | Broken |
| Broken Human Bone | 1 | 100 | 80 | 1.3 | Broken |
| Torch | 1 | 100 | 100 | 1 | Burnt out Torch — a defensive object |
| Retro Overhead Projector (H) | 1 | 100 | 100 | 1 | Convex Lens |
| Ektorp-Gluten Chair (H) | 1 | 50 | 50 | 1 | Broken |
| Box Cutter | 1 | 60 | 70 | 0.9 | Broken |
| Staff | 1 | 40 | 50 (wiki: 60) | 0.8 | Broken Staff |
| Screwdriver | 1 | 20 | 40 | 0.5 | Broken |
| Can Opener | 1 | 50 | 100 | 0.5 | Broken |
| Pathetic Penknife | 1 | 15 | 45 | 0.3 | Broken |
| Swiss Army Knife | 1 | 15 | 50 | 0.3 | Broken |
| Burnt out Torch | 1 | 10 | 75 | 0.1 | Broken |

Broken melee weapons can be repaired (Kwik-Fix, Repair Kit, Technician). Repairing costs
1 AP; a Repair Kit becomes a Repair Kit (damaged).

A 2-kill weapon on a zone with 1 zombie kills that one: the second kill is lost
(`ProcessZoneEffect`: kills = min(zombies in the zone, weapon kills)). Keep 2-kill weapons
(Machete, Laser Pointer) for pairs and 1-kill weapons for the odd zombie.

## Water weapons (reload: Water Ration)

| Weapon | Per load | Notes |
|---|---|---|
| Aqua-Splash | 5 shots × 1 kill | 100% |
| Water Pistol | 3 shots × 1 kill | 100% |
| Kalashni-Splash (H) | 1 shot × 3 kills | 100% |
| Jerrycan Gun | 1 kill per shot, 15% empties (avg 6.7) | reload with a Full Jerrycan |

## Battery weapons (reload: Battery)

Reloading costs 0 AP and works in the desert. "Battery back" = the shot drops the battery
again, ready to reload: Avg per battery counts those reloads.

| Weapon | Kills | Kill % | Empties | Avg per battery | Battery back |
|---|---|---|---|---|---|
| Chainsaw (H) | 3 | 100 | 30% | 10 | — |
| Burning Laser Pointer | 2 per charge | 100 | after its charges: a battery loads 4 (50%), 3 (25%) or 2 (25%) | 6.5 (worst 4) | — |
| Battery Launcher Mk. II | 1 | 100 | always | 5 (worst 1) | 80% |
| Devastator | 2 | 100 | always | 4 (worst 2) | 50% |
| Electric Whisk | 1 | 100 | 40% | 2.5 | — |
| Battery Launcher 1-ITF | 1 | 90 | always | 0.9 | never (Crushed Battery) |
| Taser | 1 | 30 | 70% | 0.4 | — |

## Grenades (consumed, kill in the whole zone)

Exploding Water Bomb 6–10 · Exploding Grapefruit 5–9 · Water Bomb 2–4 ·
Mobile Phone 1–2 (leaves parts).

## Animals (1 kill, then maybe lost)

| Animal | Lost after use | Avg |
|---|---|---|
| Guard Dog (defensive object) | 10% | 10 |
| Mangy Dachshund (defensive object) | 15% | 6.7 |
| Fat Cat | 20% | 5 |
| Chicken, Giant Rat, Stinking Pig (H), Huge Snake (H) | always | 1 |
| Furious Kitten | always | 50%: kills every zombie in the zone; 50%: wounds you |

## Planning a kill run (zoo trimming)

Use `plan_kill_route` (a Fata route by name, own waypoints, or `zoo=True` for the clusters and
their sides). It counts the zombies per zone, splits them into pairs and singles, picks the
weapons from the bank on the **Avg** values above, and plans the supplies on the exact route.
Do not count or pick weapons by hand. What it applies:

- Kill **every** zombie of each zone on the run: one left alive spreads to the clean zones
  around it that night, before Zombie Despair (see opti-town-meta.md, Spawn rules).
- A zone with n zombies = n ÷ 2 pairs (2-kill weapons) + n mod 2 single (1-kill weapon).
- Grenades for crowded zones are not planned by the tool: mention them if the bank has them.
- Using a defensive object (Concrete Blocks, Torch, Guard Dog, Dachshund) as a weapon
  can cost bank defense: say so.
- Watch control points while killing: a zone with more zombie CP than citizen CP traps
  you (the tool warns; `get_citizen_cp` for the party).
