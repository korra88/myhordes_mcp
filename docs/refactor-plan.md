# Piano: normalizzazione e riuso del codice

Stato: **piano approvato dall'utente 2026-10-30.** B1–B3 fatti; fase A fatta (20 commit da 89daf98 a 16be11f, eseguita da Sonnet, rivista da Opus; resti sotto); prossimo: fase B. Ogni fase va
avviata su conferma dell'utente; le fasi C e D cambiano testi o numeri che il bot legge e vanno
approvate punto per punto.

Leggi prima: `CLAUDE.md` (vincoli: read-only, nessun polling, output testuale condensato),
`docs/mechanics-in-code.md` (regole di gioco in Python), `docs/kill-route-plan.md`.
Revisione fatta su HEAD `817595e` (~9 400 righe: main.py 1 066, kills 845, pathing 807,
supplies 639, risk 569). I numeri di riga sotto si riferiscono a quel commit: verificali prima
di modificare.

## Regole per chi esegue

1. **Rete di sicurezza: `make golden`** (`tests/golden.py`, ~15 s). 176 golden offline: 174 casi
   (tutti i tool, varianti di argomenti, rami d'errore, ogni tool senza città e con un giorno
   mancante, livelli dell'Osservatorio 0–4, sera con gli avvisi delle 23:10, stime ricostruite
   dall'archivio, registro della città acceso, città scelta da file utente / file corrente) sulla
   città 8299 (API beta, giorni 1–3 e 5–7) e sulla 8212 (giorni beta 4–8 e 13, giorni 1–5 dalla
   vecchia pagina spy, letti da `parse.py`), più due pseudo-casi: `_files` (ogni file scritto
   nella copia temporanea di towns/, con hash del contenuto) e `_tools` (nome, docstring e schema
   di ogni tool: ciò che il bot vede).
   - Orologio fisso (patch prima di importare il codice), log città spento salvo nei casi
     `townlog_*`, Fata e Gest'Hordes serviti da file (Gest'Hordes solo per 8299).
   - Il test si ferma se un modulo usa ancora i percorsi o l'orologio veri, e se la `towns/`
     vera cambia durante l'esecuzione.
   - Prima di ogni intervento: `make golden` deve dare `176 same, 0 different`.
   - Dopo un intervento delle fasi A e B: **identico**, nessuna eccezione.
   - Una volta per fase anche `make golden-anyseed` (seme dell'hash casuale: trova ordini di set
     che finiscono nell'output).
   - Fasi C e D: il diff è il cambiamento voluto. Mostralo all'utente, poi `make golden-update`.
   - Mai `--freeze` durante un refactoring: rifà le fixture dai dati vivi e i golden non
     valgono più.
   - `tests/golden/` contiene dati veri (nomi dei giocatori): è in `.gitignore`, **mai
     committarlo**. I golden esistono solo su questa macchina (WSL).
   - Nuovo comportamento → aggiungi un caso in `CASES` (nome stabile = nome del file golden;
     opzioni per caso: `clock`, `env`, `files`, `hide`, `townlog`).
   - **Non coperto, verifica a mano** (audit del 2026-10-30): fine nel Labirinto (`end_ap`,
     nessuna fixture ne ha uno); Osservatorio non costruito; `plan_expedition_supplies` a livelli
     diversi da 4 (il tool non ha `day`); variante "dig" che vince e morte per disidratazione nei
     rifornimenti; stima legacy "tomorrow"; chiave della cache della griglia (A1: non usare
     `id(data)`); velocità dopo A6 (cronometra `make golden`); codice morto da rimuovere (grep
     anche in scripts, kb_build, .claude/commands); docstring della fase C9 e comportamento
     del bot su Discord.
2. **Un commit per intervento** (o per gruppo piccolo dello stesso tipo), messaggio che dice
   "no output change" per le fasi A/B.
3. Il repo non ha altri test. Per le parti non coperte dai casi (es. `townlog`, che è spento
   nel test) verifica a mano.
4. Deploy (commit, push, pull sul Pi, restart solo se cambiano prompt/toml): dopo ogni fase,
   su conferma dell'utente.

## Già trovato durante la revisione (bug, non refactoring)

B1–B3 **fatti** il 2026-10-30 (vedi git log); B4–B6 confluiscono nelle fasi C e D. Ognuno è un commit a sé,
con il suo diff dei golden.

| # | Dove | Problema | Proposta |
|---|---|---|---|
| B1 | `fata/changes.py` (ordine "Other" nel blocco Bank) | A parità di quantità l'ordine dipende dall'hash delle stringhe (cambia a ogni avvio del processo). Il test fissa `PYTHONHASHSEED=0` per questo. | Ordinare i pareggi per nome. Cerca altri `set` di stringhe iterati in output. |
| B2 | `cp.party_cp` (cp.py:159-170) vs `roster._norm` (roster.py:29-31) | `party="@Korra:123"` non trova il cittadino (match esatto minuscolo); il roster accetta `@Name:123`. | Una `citizen_key(name)` condivisa. |
| B3 | `bank._sum_items` (bank.py:203-224) | `entry[1] += item["broken"]` somma il flag 0/1: "+N broken" conta le pile rotte, non gli oggetti. `include_broken` non cambia nulla (entrambi i rami danno lo stesso totale). | Verificare nel formato di `_fmt_bucket` cosa si vuole mostrare; correggere e togliere il parametro morto. |
| B4 | `kills.zone_map` vs `pathing._zone_grid` | Le conte del radar scout (`data["scout"]`) valgono per i percorsi ma non per le uccisioni (lì la zona risulta "mai visitata"). | In fase D, con la stima unica. |
| B5 | `kills.edge_gap` (kills.py:~169-183) | Non passa `final`: su un giorno passato stima diversa dal resto della rotta. | Passare `final` (cambia numeri solo sui giorni passati). |
| B6 | intestazioni dei tool | Nome città mancante mostrato come `None` (planning:349, changes:77, dump:99, roster:88, night:57, main:133), "?" altrove, "Unknown Town" in town.py:78. | Fase C1. |

## Fase A — refactoring senza cambi di output (S, golden identici)

Ordine consigliato: A1 → A2 → A3 → A4 → A5, poi A6–A8 in qualsiasi ordine.

### A1. Griglia di pathing come dataclass
`pathing._zone_grid` (197-214) ritorna una tupla di 4; `search_route` la allarga a 6
(cp, bounds, r. 318); spacchettata a 225, 317, 339, 445 (`[1]`), 540. Il 2026-10-30 aggiungere
`bounds` ha rotto uno spacchettamento a 5. In più `zone_map` e `spread_map` non dipendono dal CP
ma vengono ricostruite per ogni CP e ogni chiamata: `loop_return` chiama `search_route` per ogni
zona di teletrasporto (fino a 12 al livello 4, 394-395); `route_risks` costruisce griglie a 445,
447 e 491; `loop_return` si fa un suo set `dried` (388).
- `@dataclass(frozen=True) class ZoneGrid: zone_map, spread_map, day, bounds` costruita una volta
  per `data` da `zone_grid(data)`; `cell_class(cp)` con cache per CP.
- `_leg_search(grid, cp, ...)` legge i campi per nome.

### A2. Coordinate e mappa delle zone in un posto solo (nuovo `fata/geo.py`)
- `xy(c: str | dict) -> Cell | None` (oggi `risk._parse_coords`, "privata" ma importata da 7
  moduli; più tre finti dict per parsare stringhe: changes.py:27-28, roster.py:44, zones.py:168-169).
- `fmt_xy(cell) -> "[x|y]"` (~40 f-string sparse: supplies 335/376-377, pathing 558/581/626/682/696,
  kills 558/702/796/809/812/829, pickups 96/100/210, zones 249, towndata 243/266/382/506,
  parse 122/344/433). Solo il formato `|`; il formato `[x/y]` dell'itinerario resta (vedi C5).
- `moves(a, b=(0, 0))` = distanza Manhattan (zones 118/135/168/170/186/234, changes 45/50,
  roster 45, risk 65/407, pathing 380/402/410); sposta qui anche `km`.
- `zone_map(data, *, scout=False)`: oggi costruita 5 volte (pathing 200-210 con radar,
  kills 50-51, pickups 63-67, zones 241-246, set `dried` pathing 388). Kills resta `scout=False`
  finché non si decide B4.
- `NEIGHBOURS8` (risk 162, kills 42), `NEIGHBOURS4` (pathing 246 inline, `kills.DIRS4` 552),
  `in_bounds(bounds, cell)` (pathing 250, kills 573; `edge_gap` affetta la tupla con `[2:]`/`[:2]`:
  meglio un `Bounds` NamedTuple xmin, xmax, ymin, ymax).
- `format_zoo` (kills 624) usa `risk.never_visited` invece di ricalcolare.

### A3. Una tabella sola per le bande di pericolo
`risk.DANGER_LEVELS` (testo, 116-121), `risk._DANGER_MIN` (423), `risk.DANGER_MAX_EST` (428),
`kills._DANGER_BAND` (43) descrivono la stessa cosa, con fallback diversi per valori sconosciuti
(`(6, 9)` in kills 72/89, `DANGER_MAX_EST[3]` in pathing 98, `None` in pathing 107).
- `risk.DANGER_BAND = {0: (0, 0), 1: (1, 2), 2: (3, 5), 3: (6, 9)}` + `danger_band(d)`; MIN e MAX
  derivati. **Mantieni** il `None` di pathing 107 (dichiaralo nel codice): cambiarlo è fase D.
- `pathing._DANGER_WALK` è un peso di cammino: resta a parte.

### A4. Costanti di gioco duplicate
- Soglia EP in km: `pathing.EP_MIN_KM` (743), `supplies.EP_MIN_KM` (35), `risk.EP_FROM_KM` (374) → una.
- Sete: `pathing` 11/22/33 (744) vs `supplies.THIRST_STEP = 10` (36); nomi degli stati in
  `pathing._thirst` (747) e `supplies.THIRST` (314) → derivare da supplies.
- "40 AP" scritto nei testi (supplies 405, kills 697, main 728) → da `MAX_PATH_AP`.
- Osservatorio: `supplies.end_requirements` (323-325) rifà `risk.platform_level` con il suo nome
  minuscolo; `changes.platform_discount` (31-36) scrive a mano 2/3 AP che derivano da
  `risk.teleport_range` (361-369) → `platform_return_saving(level)` accanto a `teleport_range`.
- CP base 2: `risk.CP_PER_CITIZEN` (342), `cp.party_cp(base=2)` (159), testo "assume 2" (cp 205),
  `pathing` `cp=2` (292) → `CP_PER_CITIZEN` ovunque.
- `"[0|0]"`: `night.TOWN_COORDS` (9) e letterale in supplies 337.
- `planning.py:199` scrive "below 2.0" a mano invece di `WATER_RATIO_CRITICAL`.
- CP per tappa: `list(cp) if isinstance(...) else [cp] * legs` (pathing 311, 444) → `_per_leg`.

### A5. Codice morto
- `walkability(revisit=)` (pathing 146/151): nessun chiamante lo passa.
- `if short or dead: pass` (supplies 580-581).
- `bank._fmt_bucket(show_items=)` (227/230) mai passato; `_sum_items(include_broken=)` vedi B3.

### A6. Tuple di costo e stato dei rifornimenti
- Costo (11 campi): il test di fattibilità `cost[0] or cost[1]` è scritto a mano in
  kills 717/723/793, main 752/781/785, supplies 300, pickups 183; slice magiche `[:5]`
  (pickups 182/185), `[:6]` (main 750), `c[9]` (supplies 279), unpack a 11 (528).
  → `supplies.feasible(result)`, `THIRST_KEY = slice(0, 5)`, `SUPPLY_KEY = slice(0, 6)`.
- Stato (10 campi, `final[1]`, `final[4]`, `state[9]`, `nxt[1]`): `typing.NamedTuple State`
  (resta hashabile per la `lru_cache`). Effort M.

### A7. Formattatori: piccoli helper ripetuti
- Bank: totali per nome (planning 35-41, dump 31-38, snapshot 13-15, bank 83-84) →
  `bank.totals(bank, *, intact_only=False)`; conteggio "Armor" (bank 304, planning 116, il commento
  dice già che devono coincidere) → `bank.defense_count`.
- Edifici: test "costruibile" (planning 88-90, 98-101; buildings 157-164) → `is_buildable(b)`;
  filtro città private (buildings 118-119, planning 84-85) → `visible(...)`; filtri acqua (tupla in
  bank 273-276 vs `planning.WATER_FILTERS` 27) → `has_water_filter`; `upgrade_days` letto 3 volte
  con cast diversi (buildings 76-84, 131-136; planning 310-311) → `upgrades_by_day(built)`; nomi di
  rarità in 3 tabelle (buildings 10, blueprints 22, bank 330) → da `blueprints.TIERS`; difesa
  degli edifici sommata 2 volte (buildings 55, 124).
- Gest'Hordes: accesso alle serie con gli offset di giorno (`attaque_jour[day]`,
  `morts_reels[day-1]`) in planning 262-275, night 12-18, gesthordes/format 27-38 e 121-123 →
  `atk_series(gh)` + `at_day(series, key, day)` nel pacchetto gesthordes.
- town.py: tag `[Shaman]` 5 volte (113/119/138/188/199), staleness 3 volte, riga di morte
  2 volte (151, 211; simile night 75-76, townlog 176), `format_trapped(trapped_citizens(data),
  fmt_epoch)` 3 volte (town 124/142, changes 158) → `_citizen_label`, `_death_line`,
  `risk.trapped_lines(data)`. `current_day` riusato come variabile di ciclo (town 206).
- Giorni di età: stessa aritmetica con 4 guardie diverse (risk 124-131/148-157/256-258/287,
  zones 97/324, pathing 111-112/606-607) → `age_days(day, current)`, `is_stale(...)`. **Tieni le
  etichette** (`[STALE: day N]`, `(updated dN, STALE)`, `dN, stale`): unificarle è C2.

### A8. main.py e livello dati
Numeri di riga di questa sezione: alcuni della revisione erano sbagliati (townlog, config):
cerca per nome di funzione.
- **Preambolo dei tool** (~20 tool: `resolve_town_id` → controllo `isinstance(str)` →
  `fetch_town_data(tid, day=day or None)`; il controllo d'errore dei dati è a volte in main
  — 130, 311, 691 —, a volte nel formattatore — 16 guardie —, night.py:50 lo rifà dopo main:311)
  → `async def _town(town_id, day=0) -> tuple[int, dict] | str` in main.py. **Niente
  decoratore**: FastMCP legge la firma delle funzioni per lo schema dei tool. Le guardie nei
  formattatori restano come rete.
- **CP del gruppo** ripetuto 3 volte (main 492-496, 693-697, 893-897) →
  `cp.resolve_group_cp(data, tid, group_cp, party) -> (cp, breakdown | None)`; insieme a B2.
- **Convenzione d'errore dei parser**: `_parse_zones`, `pickups.parse`, `resolve_town_id`
  ritornano testo con "Error:", `supplies.parse_available` e `kills.parse_kit` senza (il
  chiamante aggiunge il prefisso: main 668, kills 680/771) → tutti con il prefisso. I dict Fata
  hanno sempre la chiave `error` (None se ok), quelli Gest'Hordes solo in caso d'errore: oggi
  `"error" in` è usato solo su Gest'Hordes (planning 264/381, night 14, gesthordes/format
  15/110), corretto ma fragile → `has_error(d)`.
- **Parser legacy e nuovo**: voce di stima dell'attacco costruita 4 volte (towndata `_est`
  194-197, archive `_est_entry` 244-247 e 281, parse 165/169; `maxed` int in due, grezzo nelle
  altre) → `towndata.estimation_entry(e)`; collegamento ai genitori degli edifici uguale
  (towndata 360-369, parse 308-317) → `_link_parents`; `DEATH_TYPES` e `JOB_NAMES` stanno in
  parse.py (legacy) ma li importa towndata.py (56) e roster.py (13) → spostali in towndata.
- **archive.py**: `_find_town_dir(...) / "cache"` ripetuto ~7 volte → `cache_dir(town_id)`;
  `_meta.json` letto in 3 posti (archive ×2, `townlog._season`) → `read_meta(tdir)`; due
  marcatori `{day, taken_at}` (archive `get/set_changes_marker`, `_townlog_marker.json` in townlog)
  → `get_marker/set_marker(town_id, name)`. Formati dei file invariati.
- **gesthordes/format.py**: i due formattatori ripetono l'apertura (errore + estrazione
  stats/general/ville/giorno/nome/stagione, 15-29 vs 110-122); `str(x) if x is not None else '—'`
  8 volte → `_ville(data)`, `_cell(v)`.
- **config.resolve_town_id**: i rami file per utente e file città corrente sono lo stesso
  codice → `_read_town_file(path, label)`.
- **Codice morto** (verificato con grep su src, main, scripts, kb_build, tests: zero chiamanti):
  `parse._extract_js_data` (lascia inutilizzato l'import `json`), `archive.save_day`,
  `archive.load_day_html`, `archive.list_cached_days`, `wiki.get_page`. `TTLCache.clear` ha un
  chiamante: resta. Commento di wiki.py:14 descrive una tupla di 4 campi, sono 5 → NamedTuple.

### Resti della fase A (non fatti, da riprendere quando si tocca quel codice)
- Difesa degli edifici ancora sommata due volte (buildings ~55 e ~124); riga di morte ripetuta in
  town/night/townlog; il bucket "Defense items" di bank costruisce il suo insieme di nomi.
- `_town()` usato dai 12 tool semplici; restano a mano: find_expedition_path,
  plan_expedition_supplies, plan_kill_route (validano prima di scaricare), i due che scaricano
  in parallelo con Gest'Hordes e quelli che prendono solo l'ID. Il controllo dell'errore dei
  dati resta nei formattatori (i testi differiscono: unificarli è C6).
- `cell_class`/`spread_map` ancora ricalcolati tra `route_risks` e il formattatore del percorso
  (passare `grid=` lungo `safest_route` e `route_risks`; non è un problema di velocità).
- Variabili locali `zone_map` che coprono `geo.zone_map` in `_leg_search` e nel formattatore.
- parse.py (legacy) e towndata.py ripetono ancora il parsing degli edifici;
  `gesthordes.format._val` e `at_day` fanno lo stesso con limiti diversi.
- `parse.py` e archive (~217) tengono `maxed` grezzo (renderlo int cambierebbe file salvati).
- `age_days` tratta il giorno 0 come giorno vero (le guardie vecchie no): i giorni Fata partono
  da 1, nessun effetto oggi.

## Fase B — un solo cablaggio dei rifornimenti (M, golden identici)

`main.plan_expedition_supplies` e `kills._supplies_block` ripetono gli stessi pezzi:

| Pezzo | main.py | kills.py |
|---|---|---|
| `parse_available` + controllo e lookup di `second_wind` (stesso testo d'errore) | 666-674 | 678-686 |
| errore `slots < 1` (stesso testo) | 675-676 | 765-766 |
| ripiego booster `more = {...DEFAULT_AVAILABLE}` + `plan` | 781-790 (nota "Feasible with", tiene il piano fallito) | 717-731 (usa il nuovo piano, dice cosa aggiunge) |
| condizione `extra_options` | 791-795 | 741-746 |
| nota "Assumed: water and one 7 AP food…" | 778 | 739 |
| ritorno: `loop_return`, altrimenti `end_requirements`, nota teletrasporto | 709-729 | 687-706 |

- In `supplies.py`: `parse_supplies(available, second_wind) -> (items, sw_ap, sw_ep) | str`,
  `with_boosters(route, st, items, end_ap) -> (plan | None, added)`,
  `home_leg(data, out, cp, *, dig=False) -> HomeLeg(route, end_ap, note, teleport_from)`,
  costanti `ASSUMED_DEFAULT_NOTE`, `SLOTS_ERROR`.
- Il flag teletrasporto oggi si ricava dal testo della nota (`"teleport" in note`, main 808;
  `"teleport home" in n`, kills 750) e la nota esiste in tre versioni ("N moves saved" in supplies
  333-335, "N AP saved" in main 721-722 e kills 702-703): `format_plan(teleport=leg.teleport_from
  is not None)`. Le tre frasi restano come sono (unificarle = C).
- Ogni chiamante tiene la sua politica: le uccisioni usano il piano con i booster, la spedizione
  normale lo segnala soltanto. Altre differenze da tenere: main passa `dig` e il CP per tappa a
  `loop_return`, kills passa `group_cp` senza `dig`.
- **main.py torna "solo dichiarazioni"** (come dice CLAUDE.md): ~165 righe di logica di
  `plan_expedition_supplies` (648-811) più `_walked_again`, `_day_budget_error`, `_parse_zones`
  vanno in `fata/expedition.py:plan_supplies(data, tid, ...)`, come già `kills.plan_kill_route`.
- **Deciso dall'utente (2026-10-30):** `plan_expedition_supplies` adotta la politica delle
  uccisioni (piano completo con i booster + controllo duro degli slot), con una regola in più:
  se il piano non è fattibile come chiesto (AP, oggetti o slot dati dal giocatore), l'output lo
  dice **chiaramente e per primo** (riga in testa, prima del piano modificato: "Not feasible as
  asked: …; the plan below adds …"), così il bot non presenta il piano modificato come se
  rispettasse la richiesta. Vale anche per le uccisioni: allinea la loro nota a questa forma.
  Questo pezzo cambia l'output (diff dei golden atteso su `supplies*` e `kill_*`): commit a parte,
  dopo il refactoring identico della fase B.

## Fase C — cambi di testo (approvazione punto per punto)

Il bot legge questi testi: ogni punto è un commit con il suo diff dei golden mostrato all'utente.

- **C1. Intestazione unica** `fmt.header(title, meta, *, suffix="")` per `## Titolo — {città}
  Day {giorno}` + `data_updated` (bank 23/253, zones 62/149/189/249, buildings 126,
  blueprints 141, planning 190/349, changes 77, dump 99, roster 88, night 57, kills 621/790,
  pathing 559, main 133). Cambia: nome mancante (B6), "day" minuscolo in kills, night senza
  riga "Data updated".
- **C2. Etichette di vecchiaia** (vedi A7): una sola forma.
- **C3. Stima dell'attacco**: trattino `-` vs `–`, "zombies"/"z"/niente, "(partial)" solo in
  town e planning (town 36-41, planning 187-188/358, changes 96-97, night 64-66, townlog 185-186/207,
  risk 104) → `fmt.estimate(est, ...)`. Prima versione con argomenti per sito = identica (fase A),
  poi uniformare.
- **C4. Plurali e numeri**: helper `_n` (kills 120-122), `_supplies` (pickups 197-198),
  `'s' if` sparsi, forma "(s)" in ~20 punti → `fmt.plural(n, word)`, `fmt.num(x)`.
- **C5. `[x/y]` vs `[x|y]`**: itinerari e tabelle passo-passo usano `/` (pathing 721/791,
  supplies 466/626), tutto il resto `|`. Solo se l'utente vuole un aspetto coerente.
- **C6. Messaggi d'errore**: `if data.get("error"): return f"Error: …"` ~31 volte;
  town.py:56 dice "Error fetching town data:".
- **C7. Etichetta delle rovine** (zones 112-119, 273-278, pathing 663): `ruin_label(ruin)`;
  l'output dei percorsi guadagnerebbe "(dried)".
- **C9. Docstring dei tool**: il testo di `town_id` è copiato 18 volte e non nomina
  `towns/_user_towns`; il testo di `dig` è identico in due tool. Le docstring sono ciò che il bot
  legge: rivedere la formulazione con l'utente (non coperte dai golden).
- **C8. Ricerca per nome** (oggetti, rotte): sottostringa (zones 179-183, pickups 79), esatto poi
  prefisso (kills 660-662), esatto poi prefisso unico (dump 56-65) → `lookup(names, q, modes)`.
  Cambia quali input vengono accettati.

## Fase D — una sola stima degli zombie (M–L, cambia i numeri: ultima)

Due modelli per la stessa domanda:
- `risk._zombie_max_estimate` (148-159), `_build_spread_map` (165-214),
  `_spread_risk_for_clear` (217-239): per i percorsi (tag TRAP_RISK, deviazioni) e per mappa e
  dettagli zona.
- `kills.zone_estimate` (58-93) e `unvisited_estimate` (96-107): per le uccisioni.

Differenze: zona vuota vecchia — risk usa la distanza BFS e `min(2 + 2·(età − d), sorgente)`,
kills solo i vicini diretti e `2·notti` senza tetto (a 2+ zone di distanza kills dà 0 dove pathing
segna TRAP_RISK); zona con sola banda di pericolo — pathing nessuna crescita (107), kills +1/+2
per notte (90-92); i semi di spread ignorano le zone solo-banda e `danger_today`; radar scout (B4).
- Una `risk.zone_estimate(zone, day, zmap, spread_map, *, final) -> Estimate(min, avg, max,
  source)`: pathing usa `.max`, kills tutti e tre, la mappa il `max`. Scegliere un solo modello per
  le zone vuote: quello a 8 vicini segue `spreadCycleMH` (lo spread avanza di una zona per notte).
- Prerequisiti: A2, A3, A7 (età). Lo stesso testo di zona oggi è scritto in tre posti
  (`risk._zone_threat` 242-275, `pathing._format_zom_str` 598-617, `pathing._classify_cell`
  78-135): unificarlo qui, con `threat_text(t, style)`.
- Verifica: diff dei golden (attesi cambi su mappa, dettagli zona, percorsi, uccisioni) + a mano
  su 8299 giorno 6: la tabella SA1–4 di `docs/kill-route-plan.md` (19 / 8 / 3 su SA3) deve
  restare.

## Non vale la pena

- Fondere `step_rows`/`format_step_table` (pathing 757-807) con `supplies.plan`: significato
  diverso (AP negativi per mostrare quanto manca, nessun oggetto usato). Solo le costanti (A4).
- `format_plan` con 17 argomenti keyword: scomodo, ma una sola implementazione e due chiamanti.
- Un costruttore di tabelle generico: due sole tabelle a larghezza fissa; Discord mostra le
  tabelle Markdown come testo.
- Filtri dentro/fuori città di una riga (6 punti), set di oggetti strategici in bank (sono dati),
  `cp.load_cp_log` (API pubblica), `zones._by_day` (usato una volta), un registro dei nomi degli
  oggetti ("Water Ration" ecc. in 7 file: guadagno minimo).
- Import dentro le funzioni (`math` pathing 61, `deque` risk 183, `.bank` kills 744): solo stile.
- Il ritorno delle uccisioni senza `route_risks` (kills ha il suo avviso "blocked"): scelta di
  design, non duplicazione.
