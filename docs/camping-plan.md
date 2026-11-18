# Camping support — implementation plan

Status: **all phases A-G implemented and reviewed 2026-11-17, not committed.** Changes vs the
text below, decided in review: camping log "probable" needs an update dated day N at 19:00
or later (else not counted: day trips); zone level shown to players as "camp bonus +N%";
get_camping_odds also prints the max-bonus sequence for the next nights; the camping log is
written only where TOWN_LOG_AUTO is on (the Pi): one writer for the shared towns/ repo.

Goal: the town starts camping on day 25 (town 8299). The bot must answer "can I camp here,
and how many camp upgrades do I build, in which order?" with numbers from the game rules,
and the town files must track who camped which night.

Read first: `CLAUDE.md` (hard constraints, style: condensed outputs, one tool per player
question), `docs/development.md`, `src/myhordes_mcp/fata/towndata.py` (Fata field meanings),
`src/myhordes_mcp/fata/cp.py` (pattern for a per-town JSON log updated on every fetch),
`src/myhordes_mcp/fata/client.py:_load` (where per-fetch hooks run),
`knowledge/tactics/game-mechanics.md` (Camping rules section).
Game source: `myhordes-docker/myhordes/` (gitignored clone; `docs/source-map.md`).

Public repo: no player names in code, docs, tests or commit messages (citizen ids in
fixtures are fine).

---

## 1. Verified facts (do not re-derive; cite these in docstrings)

### 1.1 What Fata `/towndata` (v1.2) sends and we ignore

Checked on the town 8299 day 25 raw dump (`towns/<folder>/cache/day-25.towndata.live.json.gz`).

| Field | Meaning | Use |
|---|---|---|
| `town_info.winds` | `{"<day>": {level, direction, source}}` from day 8 on. Key N = wind of the night N−1 → N (checked: day 20 final → day 21, the only refilled zone is SE, `winds["21"]` = SE) | Phase A |
| `town_maps[].direction` | Zone sector "N", "NE", … (game `Zone::getDirection`) | Phase A |
| `building_data[].camp_boost` | Ruin camping bonus, −50…50 (= game `ZonePrototype.campingLevel`) | Phase B, E |
| `building_data[].camp_slots` | How many can hide inside the ruin, −1 = unlimited, 1…5 (= `ZonePrototype.capacity`) | Phase B, E |
| `building_data[].drops`, `min_km`, `max_km`, `explorable` | Ruin dig table, spawn distance | not in scope |
| `town_info.citizen_alive`, `town_score`, `roles.cata`, `town_citizens[].ban` | misc | not in scope |

Not in Fata, not in the official API: a citizen's camping counter, hidden status, inventory,
zone improvement level, Fata's own camping planner plans (**since v1.3, 2026-11-18, Fata
sends them: section 1.3**). The public GitLab repo
(`gitlab.com/DavidG2604/fata-morgana-legacy`, HEAD 604773e 2026-11-08) is the **legacy**
Fata: only `/exportdata`, no `/towndata`, winds, routes or camp fields. The user asks the
Fata developer to expose camp plans; Phase D keeps our own record, still the fallback (1.3).

Fata citizen positions are as of each citizen's `last_update {day, time}` and can be stale by
many days (town 8299 day 21: a citizen shown outside with last update day 3).

`town_maps[].building_digs` = digs left to uncover a buried ruin (already parsed as
`digs_remaining`, towndata.py:555): > 0 = buried.

### 1.2 Game rules (myhordes-docker/myhordes)

**Night outside** (`src/Service/NightlyHandler.php` `stage1_vanish`, :282-340): every living
citizen on a zone at night either is hidden (`tg_hide` or `tg_tomb`) and rolls
`campingChance`, or dies (Vanished, death type 5). Survived roll → `campingCounter + 1` and,
first time on a ruin with a blueprint, the blueprint drops. Devastated town: a failed roll
marks a delayed death instead. ⇒ **outside at the end of day N and alive on day N+1 = one
camping night.**

**Odds are frozen when the citizen hides** (`src/EventListener/Game/Action/CampingItemActionListener.php`
case 10: `setCampingChance(getCampingOdds())`). Upgrades, zombies, other campers and the clock
count as they are at that moment. ⇒ upgrade first, hide last.

**Odds** (`src/Service/CitizenHandler.php` `getCampingOdds` :667, `getCampingValues` :675):
sum of the terms below / 100, clamped to [0, cap].

| Term | Value |
|---|---|
| previous (by `campingCounter`, index capped at the end of the table) | normal `[80,60,35,15,0]`; pro camper `[80,70,60,40,30,20,0]`; panda town `[50,30,20,10,0]` / panda pro `[50,45,40,30,20,10,0]`; then always `-50,-100,-200,-400,-1000,-2000,-5000` |
| pro camper | skill `procamp` (legacy, no limit) or any Reclusive level (`super_recluse0..3`, pro table only while counter < limit: 6 for `super_recluse0`, 8 from `super_recluse1` up; one level per group) (`HeroSkillDataService.php` :66-69, :295-319; verified 2026-11-18 against 60 Fata planner players) |
| tomb (`tg_tomb`, dug grave) | +8 |
| town | `OptModifierCampingBonus`, default 0 (`TownSetting.php` :608) — executor: check whether any town type overrides it (config / town presets) |
| zone | zone improvement level (the camp upgrades), 1:1 |
| zoneBuilding | ruin not buried and hiding slot free → `camp_boost`; buried ruin → +15; no ruin or ruin full → −25 (`getZoneBuildingBonus`, `canHideInsideCurrentBuilding`: slot free if `camp_slots` < 0 or citizens hidden before < `camp_slots`) |
| lighthouse | +25 if building `small_lighthouse_#00` built |
| campitems | +5 per `camp_bonus` item in the backpack |
| zombies | −7 per zombie on the zone, −3 with the Scout's worn vest (`vest_on_#00`) |
| campers | citizens hidden on the zone before you: index `[0,0,-10,-30,-50,-70]` (0 or 1 before you = 0) |
| night | +10 if hiding at hour < 7 or > 18 (`TownConf::isNightTime`, default range `[7,18]`) |
| distance | by zone distance (= Fata `km`, confirmed by the user 2026-11-17): `[-100,-75,-50,-25,-10,0,0,0,0,0,0,0,5,7,10,15,20]` (index capped at 16) |
| devastated | −50 |
| cap | Survivalist 1.0; Reclusive top level (`super_recluse3`, shown in game as Reclusive 4) 0.99; everyone else 0.9 (`CitizenProperties::CampingChanceCap` default 0.9) |

**Camp upgrades** (fixtures `packages/myhordes-fixtures/src/templates/`):

| Action | Effect | Requirements |
|---|---|---|
| Improve campsite (`cm_campsite_improve`) | zone level +5 | 1 AP, not exhausted, not hidden, zone improvable |
| Install defensive item (`improve` on door, plate, trestle, bed, wood_plate, out_def, table) | zone level +9, item consumed | 1 AP, outside not at the doors, zone improvable |
| Tamer dog dig + hide (`hero_tamer_5b`) | +5 and tomb | out of scope, mention only |

"Zone improvable" = level < 50 (`ActionRequirementProvider.php` :306 `maxLevel(50)`): the last
action may cross 50. Every night: level − 15, minimum 0 (`NightlyHandler.php` :1504-1506).
The level belongs to the **zone**: every camper there gets it, the decay hits it for all.

Worked values (tests must reproduce them): from 0 with enough AP and items the best is
8 improve + 2 install = 40 → 49 → 58. Next day 58 − 15 = 43 → 1 improve + 1 install = 57
(the players' guide says 56: its arithmetic is wrong).

**Wind** (`NightlyHandler.php` :1450-1500, `BuildingQueryListener.php` :195-204): each night
one random direction; zones in that sector farther than `OptModifierWindDistance` (default 2 km)
regain digs with chance by Searchtower (`small_gather_#02`) level: none 0.25, 1 0.37, 2 0.49,
3 0.61, 4 0.73, 5 0.85; × 0.33 if the zone is not depleted. The direction is recorded only
with the Searchtower built. Fata `level` matches the Searchtower level in town 8299 (5) —
executor: confirm on one more town before relying on it, else derive the level from buildings.

### 1.3 Fata camp plans (v1.3, since 2026-11-18)

Measured on town 8299 day 26 (25 plans, 60 plan players; raw copy archived under
`towns/s19-autoritares-opium-der-einsiedler/`). Parsed in `towndata.py` (module docstring has the
raw shape): `result["camp_plans"]`, `zone["camp_level"]`; helpers `plans_for_day / _zone / _citizen`.

- **Root `town_camping`**: every saved plan, past `target_day`s (25 still there on day 26) and
  future ones (up to 31). The game UI shows only `target_day == today`, so do we. Several plans
  can share one zone and day (e.g. two on [7|-13] for day 26); a player can be in several.
  `x`/`y` absolute (relative = x − tx, ty − y). `mode` 1 basic, 2 advanced planner: informational.
- **Units**: `pre_existing_upgrades` / `new_upgrades` are upgrade units: improve campsite = 1.0,
  defensive item = 1.8; **percent camp bonus = units × 5** (8.6 units = 43%). The planned bonus
  is round((pre + new) × 5).
- **`town_maps[].camping_upgrade`**: Fata's estimate of the zone's level TODAY in the same units,
  computed by its day rollover from yesterday's plan (pre + new − 3 units = −15% a night, min 0);
  null on most zones (725 of 729). Verified on 4 zones. An estimate from players' plans, not a
  game reading.
- **Plan players**: `order` (hide order, 1 first = people hidden before: index in the order),
  `r_value` R1..R4 = `reclusive1..4`, `previous_campings` = nights, `camouflaged_scout` = vest,
  `camping_aids` = camp items, `tomb`, `job` (icon key: book = Survivalist, vest = Scout, shield =
  Guardian, ...), `effective_chances` (capped, floored at 0), `theoretical_chances` (uncapped sum).
  `building_id` = `building_data` id; absent / 0 = no ruin.
- **Validation**: `camping.plan_player_odds` (= `camping_terms` on the plan's own distance,
  zombies, night, devastated, hardcore, lighthouse, ruin, level) reproduces `theoretical_chances` and
  `effective_chances` for all 60 players. `tests/camping_checks.py` checks it on an anonymised
  snippet; `get_camping_odds` prints a `MISMATCH` line when a plan player's numbers differ.
- **`day` parameter** (get_camping_odds): 0 = tonight, a later day D = projection for the night of
  D (past day = error). Plans of target_day D; camp bonus: explicit `camp_level` > bonus typed in D's
  plan (`level_before` of the citizen's plan, or of the zone's plan(s) when they agree) > today's
  level (Fata estimate, else camp-zones record) minus 15 per night, min 0, "assuming no upgrades
  until then" > 0; zombies = today's reading; nights = plan of D, else the camping log (nights
  camped from tonight to D not included, ask the player). Nothing is recorded for a future day.
- **Cap wording**: at the cap the tool says "no upgrade needed, N points to spare" with the zombie
  tolerance floor(N/7) (floor(N/3) with the vest); the multi-night max-level plan is a separate
  "Optional, for later nights only" line, shown only when it leaves more bonus after the night
  (level - 15) than the minimal plan does.

`get_camping_odds` priorities:
- **Zone camp level**: explicit `camp_level` > `zone["camp_level"]` (Fata estimate, labelled as such)
  > `camp-zones.json` record estimate (Phase D) > assumed 0. Fata null falls through to the record.
  Explicit values are still recorded; the Fata estimate is never written to the record.
- **Plan for tonight** (the citizen is in a plan with `target_day` = today on the zone; if several,
  the one with the most campers, and the output says so): its nights, skill, vest, camp items, tomb
  and hide order replace the arguments left at the default (nights −1, skill none, vest None,
  camp_items 0, tomb False, hidden_before 0); explicit arguments win; each is named in the
  assumptions ("from <creator>'s Fata plan"). `hidden_before` counts only plan members before the
  citizen who are alive (plans keep campers who have since died). With a citizen and no x/y, the zone is the
  citizen's plan zone (they may still stand elsewhere).
- **Block "Fata plan tonight"**: every plan of today on the zone: campers in order with Fata's
  odds, bonus before -> after the planned upgrades. `get_citizen_positions` tags outside citizens
  who are in a plan today with `⛺ plan [x|y]`.
- Older data (v1.2 and earlier archived days) has neither field: `camp_plans` = [], `camp_level`
  None, and everything behaves as before.

---

## 2. Phases

Each phase: code + unit tests + `make golden` (update goldens only for intended changes,
list them in the report) + short report. Stop after each phase for review.

### Phase A — wind

- `towndata.py`: parse `winds` into `result["winds"] = {day: {"direction", "level"}}`
  (int keys) and keep each zone's `direction`. Document both in the module docstring
  (key N = night N−1 → N).
- `get_scout_map` (and the zone list it builds): one line, only when the current day has a
  wind entry: `Last night's wind: SW (Searchtower level 5): depleted zones SW beyond 2 km had
  an 85% chance to refill. Fata's depleted flags lag until a player passes.` Mark zones of
  that sector that Fata still flags depleted as "may have refilled" if the output lists them.
- `get_zone_details`: one line when the zone lies in last night's wind sector.
- No new tool.

### Phase B — ruin camping data

- Parse `camp_boost` / `camp_slots` into the ruin catalogue next to the existing ruin
  fields.
- `get_zone_details` on a ruin zone: `Camping: ruin bonus +10, room for 2 hidden (buried:
  +15 instead until uncovered)`.

### Phase C — camping log (who camped which night)

New module `fata/camplog.py`, file `towns/<folder>/camping-log.json`, updated from
`client._load` on live fetches (same place and error handling as `cp.update_cp_log`; a
failure must never break a tool call).

Inputs for night N (day N → N+1): E = day N end state (archive `day-N` towndata, final file
preferred, else the live file; the 00:25 run of Phase F makes it reliable), M = day N+1
(current fetch). Needs the raw `out` flag: add `"out"` to `_parse_citizens` output (check
goldens: parsed dict only, outputs should not change).

Per citizen alive in M:

| Evidence | Label |
|---|---|
| E: outside on zone Z with `last_update.day == N`, and M: outside on the same Z with `last_update.day == N+1` | **sure** |
| E: outside with `last_update.day == N`, M: not updated on N+1, or back in town / elsewhere | **probable** |
| E: outside but `last_update.day < N` (stale position) | not counted |
| (since 2026-11-18) citizen in a Fata plan with `target_day == N` (plans of E and M united by uid, M wins), alive in M, not sure/probable, and not inside the town at 19:00 or later in their latest day-N record | **planned**, zone = the plan's zone (that of their latest record if several plans, else the first) |

Death type 5 on night N with last position outside: record as "died outside" (failed roll
or not hidden — Fata cannot tell which).

Record per citizen: `{"nights": [{"night": N, "zone": "[x|y]", "label": "sure|probable|planned"}],
"died_outside": N|null}`; per town: last night processed. Idempotent (re-running a night
replaces it). Counter shown as `2 sure (+1 probable)`; the odds tool uses sure + probable + planned as
the pessimistic count; every stored night carries a rules version (`camplog.RULES`, 2 = planned) so a rule change recomputes old nights once and says so. Rule from the user: ambiguous evidence is never
presented as a confirmed camping night.

Backfill: `make camp-log-backfill TOWN=… [FROM=n]` fetches missing `?day=N` finals through
`fetch_town_data` (one request per missing day, user-run only, prints the count first).
Not automatic.

Exposure: `get_night_report` adds `Camped: N sure, M probable, K planned` with names; the odds tool
(Phase E) reads the count.

### Phase D — zone camp level record

File `towns/<folder>/camp-zones.json`: per zone `{"day", "level", "source"}` where source is
`reported` (a player gave the level to the tool) or `planned` (the tool's recommended plan,
assumed done). Default level for zone Z on day D = recorded level − 15 × (D − day), floor 0,
labelled `estimate from the plan of day N, not verified` or `reported on day N`. A newer
entry replaces an older one. When Fata exposes camp plans, they replace `planned` entries
(leave a TODO with the expected shape unknown).

Written only by the odds tool (Phase E), local file like the bot memory tools: no game
action.

### Phase E — `get_camping_odds` tool

One player question: "can I camp here, and what do I build?" Module `fata/camping.py`
(pure functions, unit-tested) + tool in `main.py`.

Parameters (keep defaults small, docstring tells the model to ask the player for what Fata
cannot know):
- `x`, `y` — zone (relative coords); default: the citizen's current position.
- `citizen` — name; gives job (cap, Scout vest default), position, nights from Phase C.
- `skill` — `none` (default) | `procamp` | `reclusive1` … `reclusive4`.
- `camp_level` — current zone level; −1 (default) = Phase D record, else 0 with a note.
- `ap` — AP the player can spend on upgrades (0 = no plan, odds only).
- `defense_items` — defensive items carried for installs.
- `camp_items` — `camp_bonus` items in the backpack.
- `hidden_before` — citizens already hidden on the zone (default 0, say it is assumed).
- `nights` — override the camping count (−1 = from the log).
- `tomb` — bool; `vest` — bool, default true for a Scout.
- `record` — bool, default true: store the plan's resulting level (Phase D, `planned`).

Computed from Fata: zombies on the zone (with its update age), distance, ruin bonus / slots
/ buried, lighthouse built, devastated, town type (panda tables). Night bonus: assume the
player hides between 19:00 and 06:59 and say so.

Upgrade plan: search all sequences of improve (+5) / install (+9) under the rules (level < 50
before each action, AP ≤ `ap`, installs ≤ `defense_items`). Objective: highest final odds
after the cap, then fewest AP, then fewest items. If the cap is reached before the AP run
out, say how many AP are enough. Output the order explicitly (`8× improve, then 2× install`).

Output (condensed): odds now; plan with order, AP, items; odds after; the breakdown only
the non-zero terms; one line of play advice from the facts above (upgrade before hiding,
hide after 19:00, earlier hiders take the crowd malus off you, zombies count at hide time).

Tests: worked values of §1.2 (58, then 57 next day), cap per job/skill, crowd and slot
cases, buried ruin, panda table, counter beyond the table end.

### Phase F — automatic town-file refresh (Pi)

User decision 2026-11-17: two fixed runs a day, **00:25 and 01:30 Europe/Paris**, **active
town only** (`towns/_current_town`), only to keep the town files current; no Discord message,
no other automatic action. The Fata developer is fine with it (requests carry our user agent).

- `make town-refresh`: one `fetch_town_data(<current town>)` live call through the normal
  client (single-flight, archive, CP log, town log, camping log). Prints one line. Exit 0
  when Fata is unreachable (log it); never retries.
- 00:25: the attack blocks updates, so the live fetch is the day N end state (input E of
  Phase C).
- 01:30: if Fata has day N+1 (first post-attack updates seen at 00:43, 00:52, 02:15, 08:17,
  11:19 in town 8299), the town log closes day N, opens N+1 and the camping log runs. Else
  nothing changes and the next user query does it.
- `templates/systemd/town-refresh.{service,timer}`: `OnCalendar=*-*-* 00:25:00 Europe/Paris`
  and `*-*-* 01:30:00 Europe/Paris`, `Persistent=false` (fixed times only). Make targets
  `town-refresh-install | -disable | -uninstall` copied from `towns-commit-*`.
- Needs `TOWN_LOG_AUTO` on (it is on the Pi). The 04:00 `towns-commit` timer then commits.
- Docs: replace the absolute "no cron" wording in `CLAUDE.md` and
  `docs/game-rules-for-external-apps.md` / `docs/implementation-notes.md` with: no polling
  of the MyHordes API, ever; towards Fata only the two fixed daily refreshes of the active
  town, approved by the Fata developer; everything else on user request.

### Phase G — knowledge and bot primer

- `knowledge/tactics/game-mechanics.md` Camping rules: odds terms table, upgrade rules,
  frozen-at-hide rule, wind refill.
- Bot primer: camping questions → `get_camping_odds`; ask the player for skill, items, AP,
  hidden campers when missing. Primer change ⇒ listener restart on the Pi.

---

## 3. Order and deploy

A → B → E (odds without log/record: `nights` and `camp_level` given) → C → D → F → G.
E before C/D so the town can use the odds today. Deploy per `feedback_deploy_flow`: commit,
push, pull on the Pi, restart the listener only when the primer / toml changed; Phase F also
needs `make town-refresh-install` on the Pi (user runs it or approves).

## 4. Open points

- Fata camp plans: user asks the Fata developer; shape unknown.
- `OptModifierCampingBonus` per town type, Fata wind `level` = Searchtower level: executor
  verifies in phase E / A.
