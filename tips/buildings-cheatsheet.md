Here's the compressed output:

---

# Buildings Cheat Sheet

156 standard-mode buildings (excludes 4 private-town-only). Descriptions/effects/strategy: `search_knowledge_base`. Built/available/locked status: `get_buildings`.

**Flags:** `T` = temporary (destroyed after attack) · `I` = impervious (survives attacks) · `BP-C/U/R/VR` = blueprint required (common/uncommon/rare/very rare) · `UP` = upgradable

Resources: **standard mode**. Hardcore costs differ — check knowledge base.

**Resource abbreviations:** `MS`=Metal Support · `PB`=Patchwork Beam · `TP`=Twisted Plank · `WI`=Wrought Iron · `HNB`=Handful of nuts and bolts · `WR`=Water Ration · `SM`=Sheet Metal · `CP`=Copper Pipe · `UCB`=Unshaped Concrete Blocks · `BDG`=Bag of Damp Grass · `WiR`=Wire Reel · `LD`=Laser Diode · `EOC`=Empty Oil Can · `DT`=Duct Tape · `EC`=Electronic component · `PP`=Pharmaceutical Products · `CD`=Compact detonator

**Efficiency column (Eff):** Def per scarce resource. `A:n` = def÷AP. `W:n` = def÷water rations. `H:n` = def÷nuts-and-bolts. Higher = better. `—` = no def.

**Quick efficiency reference (top 5 per metric):**
- **Best Def/AP:** Reactor (5.0), Bait (3.0), Abject Panic (2.8), Frat House (2.5), Vita-Mines (2.5)
- **Best Def/WR:** Abject Panic (35), Gas Gun (28), Acid Spray (13.3), Mines (11.5), Sprinkler System (9.2)
- **Best Def/HNB:** Gas Gun (140), Underground city (133.3), Labyrinth (75), Abject Panic (70), Dump Upgrade (65)
- **Water-producing buildings (add to well):** Pump (+15), Drilling Rig (+50), Eden Project (+50), Divining Rocket (+60), Mechanical Pump (+75), Divining Rods (+100), No Holes Barred (+100), Hydraulic Network (+5), Water Catcher (+2/day)

Indentation = **unlock tree** (parent required first). Top-level = basic town only.

| Building | AP | Def | Resources | Flags | Eff |
|---|---|---|---|---|---|
| **— Defensive Wall buildings —** | | | | | |
| Defensive Wall | 25 | 30 | TP ×8, WI ×4 | — | A:1.2 |
|   Armour Plating | 30 | 30 | TP ×10 | — | A:1.0 |
|   Armour Plating v2 | 30 | 30 | WI ×10 | — | A:1.0 |
|   Armour Plating v3 | 30 | 45 | TP ×8, WI ×8 | — | A:1.5 |
|   Barbed Wire | 10 | 20 | WI ×1, WiR ×2 | — | A:2.0 |
|     Bait | 10 | 30 | Meaty Bone ×2 | `T` | A:3.0 |
|   Emergency Supplies | 40 | — | TP ×5, WI ×5 | — | — |
|     Abject Panic | 25 | 70 | WR ×2, TP ×5, WI ×5, HNB ×1 | `T` `BP-C` | A:2.8 W:35 H:70 |
|     Bomb Factory | 30 | 35 | Semtex ×2 | `T` `BP-C` | A:1.2 |
|     Frat House | 20 | 50 | TP ×3, LD ×1, Radio Cassette Player ×3, Makeshift Guitar ×1 | `T` `BP-C` | A:2.5 |
|     Guerilla Traps | 30 | 60 | PB ×3, MS ×3, WI ×5, DT ×1, WiR ×1 | `T` | A:2.0 |
|     Rubbish Heap | 10 | 5 | TP ×2, WI ×2 | `T` | A:0.5 |
|       Mount Killaman-Jaro | 40 | 60 | WI ×2 | `T` `BP-C` | A:1.5 |
|       Pits | 15 | 30 | WI ×5, Human Flesh ×1 | `T` | A:2.0 |
|       Spikes | 15 | 30 | TP ×5 | `T` | A:2.0 |
|     Wood Plating | 20 | 40 | TP ×6 | `T` | A:2.0 |
|   Extrawall | 25 | 50 | TP ×15, WI ×15 | `BP-C` | A:2.0 |
|   Great Pit | 70 | 10 | — | `UP` | A:0.1 |
|     Great Moat | 60 | 60 | WR ×20 | — | A:1.0 W:3 |
|     Old-school traps | 25 | 35 | MS ×1, SM ×2 | — | A:1.4 |
|     Scavenger's Gallery | 30 | — | Semtex ×1, PB ×3, CD ×1 | `BP-R` `UP` | — |
|     Spiked pit | 35 | 45 | WI ×2, PB ×8 | — | A:1.3 |
|   Plywood | 30 | 15 | TP ×2, WI ×2 | — | A:0.5 |
|     Concrete Reinforcement | 40 | 80 | MS ×10, UCB ×5, TP ×5 | `BP-U` | A:2.0 |
|   Slip 'n' Slide | 35 | 60 | WI ×10, WR ×10, CP ×1, SM ×2, PP ×2 | — | A:1.7 W:6 |
|     Screaming Saws | 45 | 55 | WI ×10, MS ×5, HNB ×1, DT ×2, SM ×2, WiR ×1 | `BP-U` | A:1.2 H:55 |
|     Shredder Wall | 40 | 50 | WI ×15, HNB ×2 | `BP-C` | A:1.2 H:25 |
|     Zombie-shredder | 40 | 55 | WI ×15, HNB ×3, SM ×1, MS ×5, WiR ×1 | `BP-C` | A:1.4 H:18.3 |
|   Wall Upgrade v2 | 40 | 20 | HNB ×2, PB ×5, MS ×5 | — | A:0.5 H:10 |
|     Evolutive Wall | 65 | 55 | TP ×5, WI ×15, UCB ×2 | `BP-R` `UP` | A:0.8 |
|     Inner Wall | 60 | 70 | TP ×35, MS ×5 | `BP-U` | A:1.2 |
|       Third Wall | 60 | 100 | WI ×35, SM ×3, MS ×5 | `BP-R` | A:1.7 |
|     Metal Patches | 15 | 35 | PB ×5, MS ×3 | `BP-C` | A:2.3 |
|     Spiked Wall | 35 | 45 | TP ×5, WI ×2, UCB ×1 | `BP-C` | A:1.3 |
|     Überwall | 50 | 80 | TP ×10, WI ×10, UCB ×2, PB ×10, MS ×10 | `BP-C` | A:1.6 |
|   Wooden Fencing | 60 | 40 | TP ×15, PB ×5 | — | A:0.7 |
|     Small Fence | 50 | 60 | TP ×10, PB ×8, MS ×2, SM ×1 | `BP-C` | A:1.2 |
| **— Foundations buildings —** | | | | | |
| Foundations | 30 | — | TP ×8, WI ×8, UCB ×2 | — | — |
|   Air Strike | 50 | — | WI ×5, HNB ×1, WR ×10, CD ×2, Semtex ×1, LD ×1 | `T` `BP-R` | — |
|   All or Nothing | 200 | 50 | HNB ×1, TP ×10, WI ×15 | `I` | A:0.2 H:50 |
|   Bonfire | 15 | 30 | TP ×5, Box of Matches ×1 | `T` `BP-U` | A:2.0 |
|   Buzzard's Wonder Wheel | 300 | — | WR ×20, HNB ×5, UCB ×3, MS ×5 | `I` `BP-VR` | — |
|   Cinema | 75 | — | PB ×10, MS ×5, EC ×3, Convex Lens ×1, Retro Overhead Projector ×1 | `BP-VR` | — |
|   Defensive Focus | 50 | — | HNB ×3, PB ×8, MS ×8 | `UP` | — |
|   False Town | 400 | 400 | TP ×20, WI ×20, PB ×20, MS ×20, HNB ×15 | `BP-R` | A:1.0 H:26.7 |
|   Firework Foray | 90 | 100 | Super-Fuzz Powder ×1, Firework Launch Tube ×1, Box of Fireworks ×2 | — | A:1.1 |
|   Fortifications | 50 | — | UCB ×2, PB ×15, MS ×10, WI ×5 | `I` `BP-U` | — |
|     Community Involvement | 60 | — | PB ×15, MS ×15, HNB ×3 | `BP-R` | — |
|     Urban plan | 20 | — | HNB ×1, PB ×1, TP ×5, DT ×3, WiR ×5, LD ×4 | `BP-U` | — |
|   Garbage Dump | 50 | — | PB ×10, MS ×10, UCB ×2, TP ×3, WI ×5, HNB ×1 | `BP-C` `UP` | — |
|     Dump Upgrade | 150 | 65 | PB ×15, MS ×15, WR ×20, Corrosive Liquid ×1, HNB ×1 | `BP-VR` | A:0.4 W:3.2 H:65 |
|     Organized Dump | 20 | — | PB ×10, MS ×5, HNB ×2, UCB ×1, Trestle ×2 | `BP-R` | — |
|   Giant BRD | 300 | — | HNB ×2, WI ×30 | `I` `BP-VR` | — |
|   Giant Sandcastle | 300 | — | WR ×30, PB ×15, MS ×10 | `I` `BP-VR` | — |
|   Hot Air Balloon | 80 | — | PB ×5, MS ×5, HNB ×1, Groundsheet ×2, Box of Matches ×1, TP ×2 | `BP-VR` | — |
|   Labyrinth | 200 | 150 | HNB ×2, TP ×20, WI ×10, UCB ×4 | `BP-R` | A:0.8 H:75 |
|   Reactor | 100 | 500 | Battery ×10, Engine ×1, EC ×4, UCB ×2, MS ×15 | `I` `BP-VR` | A:5.0 |
|   The Big Rebuild | 300 | 300 | TP ×20, WI ×20, PB ×10, MS ×10, UCB ×5 | `BP-R` | A:1.0 |
|   Underground city | 500 | 400 | HNB ×3, Semtex ×5, WI ×10, PB ×20, MS ×20 | `BP-R` | A:0.8 H:133.3 |
| **— Portal Lock buildings —** | | | | | |
| Portal Lock | 15 | 5 | WI ×2 | `UP` | A:0.3 |
|   Automatic Piston Lock | 45 | 30 | WI ×10, MS ×2, HNB ×1, CP ×2, LD ×1 | `BP-C` | A:0.7 H:30 |
|     Last-Minute Lock | 10 | — | LD ×1 | `BP-C` | — |
|   Reinforced Gates | 35 | 25 | TP ×3 | — | A:0.7 |
|   Saniflow Macerator | 55 | 50 | SM ×2, CP ×2, PB ×4, MS ×10 | `BP-C` | A:0.9 |
|   Ventilation System | 45 | 20 | WI ×10, MS ×2, HNB ×2 | `BP-C` | A:0.4 H:10 |
|   War Mill | 25 | 20 | PB ×4, DT ×2 | `BP-C` | A:0.8 |
| **— Pump buildings —** | | | | | |
| Pump | 25 | — | WI ×8, CP ×1 | `I` `UP` | — |
|   Divining Rods | 130 | — | EC ×5, PB ×10, MS ×10, CP ×1, LD ×2 | `BP-VR` | — |
|   Drilling Rig | 55 | — | PB ×7, MS ×2 | — | — |
|     Divining Rocket | 80 | — | Semtex ×1, CP ×1, CD ×1, HNB ×1, PB ×5, MS ×5 | `BP-U` | — |
|     No Holes Barred | 150 | — | PB ×15, MS ×15, CP ×2, EOC ×2 | `BP-VR` | — |
|   Eden Project | 50 | — | TP ×10, Semtex ×2, CD ×1, MS ×5 | `I` `BP-U` | — |
|     Mechanical Pump | 86 | — | TP ×5, PB ×10, MS ×15, CP ×1 | `I` `BP-R` | — |
|   Hydraulic Network | 40 | — | HNB ×2, WI ×5, CP ×2, MS ×5, DT ×1 | `I` | — |
|     Decon Shower | 20 | 35 | WR ×10 | `BP-C` | A:1.8 W:3.5 |
|     Faucet | 130 | — | Engine ×1, HNB ×4, WI ×10, PB ×6, MS ×3, EOC ×3 | `BP-R` | — |
|     Nature area of the Survivalists | 60 | — | BDG ×2, TP ×5, Radio Cassette Player ×1, EOC ×2 | `BP-R` | — |
|     Shower | 25 | — | TP ×4, WI ×1, WR ×5, CP ×1, EOC ×1 | `BP-C` | — |
|     Sluice | 50 | 60 | TP ×8, WR ×15, CP ×1 | `BP-C` | A:1.2 W:4 |
|   Shooting Gallery | 30 | 60 | PB ×2, MS ×2, WR ×20, CP ×1, CD ×1, HNB ×1, DT ×2 | `BP-C` | A:2.0 W:3 H:60 |
|   Vaporiser | 50 | — | HNB ×2, WI ×8, CP ×2, MS ×2, WiR ×2, CD ×1 | — | — |
|     Acid Spray | 25 | 40 | WR ×3, PP ×2 | `T` `BP-C` | A:1.6 W:13.3 |
|     Boiling Fog | 40 | 60 | WR ×10, CP ×1, TP ×10, MS ×5, EOC ×1 | `BP-C` | A:1.5 W:6 |
|     Gas Gun | 60 | 140 | MS ×5, WR ×5, HNB ×1, CP ×1, PP ×2, Corrosive Liquid ×1 | `BP-C` | A:2.3 W:28 H:140 |
|     Mist Spray | 40 | 80 | WR ×15, TP ×5, WI ×5, MS ×5 | `BP-U` | A:2.0 W:5.3 |
|     Sprinkler System | 85 | 185 | WR ×20, CP ×1, PB ×7, MS ×15, LD ×1 | `BP-R` | A:2.2 W:9.2 |
|   Vegetable Plot | 60 | — | WR ×10, PP ×1, PB ×10 | `UP` | — |
|     Apple Tree | 30 | — | WR ×10, Human Flesh ×2, PP ×3, PB ×1 | `BP-R` | — |
|     Fertilizer | 30 | — | WI ×5, WR ×10, PP ×8, Anabolic Steroids ×2, BDG ×3 | `BP-R` | — |
|     Grapeboom | 40 | — | WR ×10, TP ×5, Semtex ×5, EOC ×1 | `BP-U` | — |
|       Grenade Launcher | 60 | 40 | PB ×7, MS ×2, HNB ×2, DT ×2, WiR ×2, Convex Lens ×1, Exploding Grapefruit ×4 | `BP-R` `UP` | A:0.7 H:20 |
|       Vita-Mines | 40 | 100 | MS ×2, WiR ×1, CD ×1, Exploding Grapefruit ×5 | `T` `BP-R` | A:2.5 |
|     Mines | 50 | 115 | WR ×10, WI ×3, Semtex ×1, CD ×1 | `T` `BP-C` | A:2.3 W:11.5 |
|     Ravaged pumpkins | 45 | — | WR ×15, TP ×5, WI ×2, BDG ×3, Anabolic Steroids ×1 | `BP-U` | — |
|       Scarecrows | 40 | 15 | TP ×5, DT ×3, PB ×3 | `BP-R` | A:0.4 |
|   Water Catcher | 10 | — | TP ×2, WI ×2 | `T` `BP-C` | — |
|   Water Purifier | 75 | — | HNB ×1, TP ×5, WI ×5, CP ×2, EOC ×2 | — | — |
|     Water Filter | 50 | — | WI ×10, EC ×2, Wire Mesh ×1, WiR ×1, EOC ×1 | `BP-R` | — |
|   Water Turrets | 50 | 70 | WR ×25, CP ×6, MS ×10 | `BP-R` `UP` | A:1.4 W:2.8 |
| **— Soul Purifying Source buildings —** | | | | | |
| Soul Purifying Source | 30 | 20 | WI ×1, DT ×1, BDG ×2, EOC ×1 | `UP` | A:0.7 |
|   Architect's Study | 50 | — | PB ×5, Vodka Marinostov ×1, Anabolic Steroids ×1, BDG ×2 | — | — |
|     Builder's Merchant | 45 | — | TP ×10, WR ×5, MS ×8, SM ×2, Twinoid 500mg ×1, Vodka Marinostov ×1, Opened packet of Cigarettes ×1, Trestle ×2, Ektorp-Gluten Chair ×1, Järpen Table ×1 | `BP-C` `UP` | — |
|   Blue Gold Thermal baths | 300 | — | WR ×100, MS ×8, CP ×6, PB ×6, UCB ×2, Wire Mesh ×1, Water Purifying Tablets ×4 | `I` `BP-VR` | — |
|   Crow Statue | 300 | — | Human Flesh ×3, PB ×35 | `I` `BP-VR` | — |
|   Infirmary | 40 | — | PP ×6, Paracetoid 7g ×1, PB ×5, MS ×5 | `BP-R` | — |
|   Pool | 150 | — | TP ×10, SM ×2, MS ×1, WR ×5, HNB ×2, CP ×1, BDG ×2 | `BP-VR` | — |
|   Sacrificial Blaze | 20 | — | Tortured Soul ×1, Trestle ×1, TP ×3, Torch ×1 | `T` | — |
|   Sanctuary | 20 | — | TP ×2, PB ×3, BDG ×1 | — | — |
|     Hammam | 20 | 20 | TP ×2, SM ×2 | `BP-U` | A:1.0 |
|   Small Cemetary | 42 | — | HNB ×1, TP ×10 | — | — |
|     Coffin Catapult | 85 | — | TP ×5, WI ×15, HNB ×3, Belt ×1, UCB ×2, WiR ×2 | `BP-R` | — |
| **— Watchtower buildings —** | | | | | |
| Watchtower | 15 | 10 | TP ×3, PB ×1, WI ×1 | — | A:0.7 |
|   Battlements | 25 | — | TP ×6, PB ×2, MS ×2, HNB ×1 | `UP` | — |
|     Guard Tower | 35 | — | HNB ×1, SM ×1, PB ×10, MS ×2 | `BP-R` | — |
|     Guardroom | 50 | — | PB ×6, WI ×10, HNB ×2, MS ×5, BDG ×2, Box of Matches ×1, Cafetière ×1, Opened packet of Cigarettes ×1, Trestle ×1, Ektorp-Gluten Chair ×2 | `BP-R` | — |
|     Miniature Armory | 40 | — | HNB ×1, TP ×10, WI ×8, SM ×2, DT ×2 | — | — |
|       Filtering gutters | 35 | — | TP ×10, CP ×3, MS ×3, UCB ×1, SM ×1, EOC ×1 | `BP-R` | — |
|       Manual grinder | 50 | — | HNB ×3, TP ×10, WI ×10, MS ×5, SM ×2, UCB ×2 | `BP-R` | — |
|       Pet Shop | 40 | — | TP ×5, PB ×4, MS ×2, BDG ×2, EOC ×1, Wire Mesh ×1 | `BP-R` | — |
|       Swedish Workshop | 50 | — | TP ×10, WI ×10, PB ×5, HNB ×2, UCB ×3, SM ×2, Radio Cassette Player ×1 | `BP-R` | — |
|   Cannon Mounds | 60 | 30 | PB ×8, MS ×1, UCB ×1, HNB ×1 | — | A:0.5 H:30 |
|     Brutal Cannon | 25 | 50 | MS ×1, SM ×1 | `T` `BP-C` | A:2.0 |
|     Plate Gun | 50 | 60 | PB ×5, MS ×1, HNB ×2, SM ×3, Semtex ×2 | `BP-C` | A:1.2 H:30 |
|     Railgun | 35 | 50 | WI ×10, PB ×2, MS ×2, HNB ×2, SM ×1 | `BP-U` | A:1.4 H:25 |
|     Rock Cannon | 40 | 50 | PB ×3, MS ×5, UCB ×3, EC ×1, CP ×1 | `BP-C` | A:1.2 |
|   Catapult | 40 | — | TP ×2, WI ×1, PB ×1, MS ×1 | `BP-C` | — |
|     Small Trebuchet | 30 | 60 | PB ×3, WI ×2, HNB ×1, BDG ×1, Stinking Pig ×1 | `BP-U` | A:2.0 H:60 |
|     Upgraded Catapult | 30 | — | TP ×2, WI ×2, EC ×1, Belt ×1, CP ×1, Convex Lens ×1 | `BP-C` | — |
|   Lighthouse | 30 | — | EC ×2, PB ×5, MS ×5, Battery ×1, LD ×1 | `BP-R` | — |
|   Observation platform | 30 | — | TP ×5, Telescope ×1, MS ×1 | `UP` | — |
|     Scanner | 20 | — | WI ×5, Battery ×2, LD ×1, EC ×1, Radio Cassette Player ×2 | `BP-C` | — |
|     Scouts Lair | 25 | — | CP ×1, Telescope ×1, MS ×3, TP ×2, SM ×1, Radius Radar Beacon ×2, Battery ×1 | `BP-R` | — |
|     Upgraded Map | 25 | — | Battery ×2, WI ×5, SM ×1, LD ×1, Radio Cassette Player ×2 | `BP-C` | — |
|   Predictor | 20 | — | DT ×1, EC ×1 | `BP-C` | — |
|   Public lights | 25 | — | HNB ×1, CD ×1, Convex Lens ×2, LD ×2, MS ×8, WiR ×1, Battery ×4 | `BP-C` `UP` | — |
|   Searchtower | 30 | — | EC ×1, PB ×3, MS ×1, Järpen Table ×1, Telescope ×1, LD ×2 | `UP` | — |
| **— Workshop buildings —** | | | | | |
| Workshop | 25 | — | TP ×10, WI ×8 | `UP` | — |
|   Building Registry | 15 | — | Järpen Table ×1, Ektorp-Gluten Chair ×1 | `I` | — |
|     Altar | 24 | — | PB ×3, MS ×2, Stinking Pig ×1 | `BP-C` | — |
|     Defensive Adjustment | 60 | — | PB ×5, MS ×10, HNB ×2, WiR ×1 | `BP-U` `UP` | — |
|     Ministry of Slavery | 15 | — | PB ×10, MS ×5, Rusty Chain ×2, Järpen Table ×1 | `BP-VR` | — |
|     People's Court | 12 | — | TP ×10, WI ×10, WiR ×1, Radio Cassette Player ×2 | `BP-R` | — |
|     Technicians Workbench | 60 | — | PB ×5, MS ×10, SM ×1, WiR ×2, BDG ×1, Convex Lens ×1, HNB ×2, Twinoid 500mg ×1 | `BP-R` | — |
|   Butcher | 40 | — | TP ×9, WI ×4 | — | — |
|     Abbatoir | 35 | 45 | MS ×8, SM ×2, PB ×1, Human Flesh ×1 | `BP-C` | A:1.3 |
|     Cremato-Cue | 40 | — | PB ×6, MS ×1 | `BP-U` | — |
|     Pigsty | 35 | — | TP ×8, PB ×4, HNB ×1, BDG ×3, Stinking Pig ×3 | `BP-R` | — |
|     Tamer's Trap System | 40 | — | TP ×4, WR ×10, HNB ×1, Anabolic Steroids ×1 | `BP-R` | — |
|   Central Cafeteria | 20 | — | PP ×1, PB ×5, MS ×1, Järpen Table ×1, BDG ×1, Carcinogenic Oven ×1 | `BP-C` | — |
|   Central Laboratory | 20 | — | HNB ×1, PP ×4, PB ×5, MS ×5, BDG ×2, Convex Lens ×1, Old Washing Machine ×1 | `BP-C` | — |
|   Chocolate Cross | 13 | — | PB ×1, Rusty Chain ×1 | `I` | — |
|   Factory | 40 | — | PB ×5, MS ×5, Järpen Table ×1 | — | — |
|   Gallows | 13 | — | PB ×1, Rusty Chain ×1 | `I` | — |
|   Henhouse | 25 | — | TP ×5, PB ×5, Chicken ×2, Wire Mesh ×2, BDG ×1 | `BP-U` | — |
|   Meat Locker | 40 | — | HNB ×2, WI ×8, Ektorp-Gluten Chair ×1, MS ×1 | `I` | — |
|   Small Café | 5 | — | WR ×1, TP ×3 | `T` `BP-C` | — |