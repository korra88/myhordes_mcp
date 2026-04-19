# Buildings Cheat Sheet

156 standard-mode buildings (excludes 4 private-town-only). Built/available/locked status: `get_buildings`.

## Phase-based building guides

Full tables (resources, AP, def, flags, efficiency) split by game phase in `knowledge/buildings/`:

| File | Phase | Days |
|---|---|---|
| `knowledge/buildings/basic.md` | Must-build foundations | Day 1–5 |
| `knowledge/buildings/intermediate.md` | Defense ramp + utility unlocks | Day 6–10 |
| `knowledge/buildings/defense-focus.md` | Heavy defense + water-consumers | Day 9–15 |
| `knowledge/buildings/advanced.md` | Mega-defenses, dump strategy | Day 15+ |
| `knowledge/buildings/wonders.md` | Distinction buildings, no def value | Any |

Use `search_knowledge(query, section='buildings')` to fetch the relevant file.
Use `search_wiki(query, category='buildings')` for item/mechanic details.

## Quick efficiency reference

- **Best Def/AP:** Reactor (5.0), Bait (3.0), Abject Panic (2.8), Frat House (2.5), Vita-Mines (2.5)
- **Best Def/WR:** Abject Panic (35), Gas Gun (28), Acid Spray (13.3), Mines (11.5), Sprinkler System (9.2)
- **Best Def/HNB:** Gas Gun (140), Underground city (133.3), Labyrinth (75), Abject Panic (70), Dump Upgrade (65)
- **Water-producing buildings (add to well):** Pump (+15), Drilling Rig (+50), Eden Project (+50), Divining Rocket (+60), Mechanical Pump (+75), Divining Rods (+100), No Holes Barred (+100), Hydraulic Network (+5), Water Catcher (+2/day)

## Flags

`T`=temporary (destroyed after attack) · `I`=impervious (survives attacks) · `BP-C/U/R/VR`=blueprint required · `UP`=upgradable

## Resource abbreviations

`MS`=Metal Support · `PB`=Patchwork Beam · `TP`=Twisted Plank · `WI`=Wrought Iron · `HNB`=Handful of nuts and bolts · `WR`=Water Ration · `SM`=Sheet Metal · `CP`=Copper Pipe · `UCB`=Unshaped Concrete Blocks · `BDG`=Bag of Damp Grass · `WiR`=Wire Reel · `LD`=Laser Diode · `EOC`=Empty Oil Can · `DT`=Duct Tape · `EC`=Electronic component · `PP`=Pharmaceutical Products · `CD`=Compact detonator
