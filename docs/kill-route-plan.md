# Piano: rotte di uccisione zombie (`plan_kill_route`)

Stato: **approvato dall'utente 2026-10-29** (design + stima + regola "pulizia totale" + soglia =
solo avviso). Fasi 1–5 = v1, **fatte e in produzione 2026-10-29** (d431876, Pi aggiornato). Fase 6
(generazione automatica rotte) = v2, solo schizzo: **non implementarla senza nuova revisione
dell'utente**.

**2026-10-30 (feedback zoo trimming di Korra):** zona mai visitata = stima dai vicini infetti
(min 0, media dei vicini infetti, max il loro max; `kills.unvisited_estimate`); avviso quando una
striscia si ferma prima del bordo mappa (`kills.edge_gap`, asse lungo, lato lontano dalla città);
rifornimenti: se gli oggetti dati non bastano il piano aggiunge i booster (una droga, un alcol) e
dice cosa manca; controllo duro slot kit + rifornimenti; i percorsi non escono più dalla mappa
(`pathing._leg_search` rispetta `map_bounds`).

Leggi prima: `CLAUDE.md` (vincoli: read-only, nessun polling, output testuale condensato),
`docs/mechanics-in-code.md` (regole di gioco in Python, non in prosa), `knowledge/tactics/weapons.md`
e `knowledge/tactics/opti-town-meta.md` § Zombie Zoo (già corretti col sorgente il 2026-10-29).

## Obiettivo

Un giocatore prepara una spedizione di uccisione (pulire un lato dello zoo, aprire un'area,
aprire un corridoio verso una rovina da campeggiare). Il tool risponde a: *quanti zombie devo
uccidere lungo questa rotta, divisi in coppie e singoli, con quali armi dalla banca, e cosa porto
per arrivarci e tornare?*

Caso reale di riferimento (città 8299, giorno 6, rotte Fata "SpecialAgent1–4", tutte di uccisione):

| Rotta | Passi | Zone con zombie | Zombie | Coppie | Singoli |
|---|---|---|---|---|---|
| SpecialAgent1 - scout | 35 | 4 | 12 | 5 | 2 |
| SpecialAgent2 - tech | 31 | 11 | 26 | 11 | 4 |
| SpecialAgent3 - guard | 27 | 7 | 19 | 8 | 3 |
| SpecialAgent4 - anyclass | 27 | 5 | 13 | 4 | 5 |

Contati da `max_zombies` del giorno 6 (zone tutte aggiornate quel giorno). SA3 = zone
2,5,3,2,2,3,2. Kit reale dell'utente su SA3: Water, Twinoid, cibo 7 AP, 2 Battery, Burning Laser
Pointer, Machete, Manbag (slot extra). Archivio: `towns/8299/` (giorno 6 salvato il 2026-10-29).
**Test di accettazione**: il tool su SA3 col giorno 6 deve riprodurre 19 / 8 / 3.

## Regole di gioco (verificate nel sorgente, `myhordes-docker/myhordes/`)

Fixtures: `packages/myhordes-fixtures/src/templates/Service/ActionDataService.php`.

1. **Uccidere = pulizia totale.** `src/Service/Maps/MapMaker.php` `zombieSpawnGovernorMH`:
   ogni notte respawn check → un ciclo di spread → Despair. Despair =
   ⌊(uccisi oggi nella zona − 1) ÷ 2⌋, applicato **dopo** lo spread; lo spread delle zone vicine
   legge la conta prima del Despair (`spreadCycleMH`, `$zone_original_db`). Uno zombie lasciato
   vivo infetta le zone pulite intorno. Il tool pianifica sempre **tutti** gli zombie di ogni zona.
2. **Coppie e singoli.** `ProcessZoneEffect.php` ~r.105: kills = min(zombie in zona, kill
   dell'arma). Arma da 2 su zona da 1 = un colpo sprecato. Per zona con n zombie:
   coppie = n ÷ 2 (intero), singoli = n mod 2.
3. **Crescita notturna** (`spreadCycleMH`, giorno ≥ 2, vicini = 8 zone): zona con zombie
   +1 (90%), +0 (5%), +2 (5%); zona vuota accanto a una con più zombie: 1–2 (o 0); zona vuota
   senza vicini infetti: resta vuota. Gli zombie non camminano.
4. **Armi** (catalogo di v1 = liste dell'utente; costo d'uso 0 AP; ricarica 0 AP anche fuori):

   | Bucket | Arma (nomi Fata `name_en`) | Kill/uso | Fine | Media | Peggiore |
   |---|---|---|---|---|---|
   | coppie | Burning Laser Pointer (N charges / Empty), id 287–291 | 2 | dopo le cariche; una Battery carica 4 (50%), 3 (25%), 2 (25%) (`load_lpointer`) | 3,25 coppie per Battery | 2 |
   | coppie | Machete, id 15 | 2 | si rompe 25% per uso (`throw_b_cutcut`, `g_break_25`) | 4 coppie | 1 |
   | singoli | Battery Launcher Mk. II (loaded/empty), id 187/186 | 1 | sempre vuoto; Battery restituita 80% (`fire_pilegun2`) → ricarichi | 5 per Battery | 1 |
   | singoli | Serrated Knife, id 14 | 1 | si rompe 33% (`throw_b_knife`) | 3 | 1 |
   | singoli | Aqua-Splash (N shots / empty), id 182,183,93,94,95,7 | 1 | 5 colpi per Water Ration (`fill_asplash*`) | 5 per acqua | 5 |
   | singoli | Water Pistol (N shots / empty), id 179–181, 92 | 1 | 3 colpi per Water Ration | 3 per acqua | 3 |

   Riparazione (Machete, Serrated Knife): Repair Kit (id 91) o Kwik-fix (id 159), **1 AP**
   (`repair_1`, `repair_2`); il Repair Kit diventa "Repair Kit (damaged)" (id 90). Una
   riparazione = un'altra media d'usi. Armi da mischia: servono AP > 0 (`not_tired`) e mani
   non ferite. Un'arma con cariche/colpi noti (es. "Laser (3 charges)") vale quelle esatte.
   Le acque usate come munizione **non** sono acque da bere: contano a parte.
   Ogni arma, Battery, acqua-munizione, kit di riparazione = 1 slot.
5. **Soglia di respawn**: già in codice, `risk.respawn_check` (soglia 25 × (giorno+1), 15 × in
   città piccole). Le uccisioni del giorno abbassano il totale controllato quella notte.
6. **Bloccati**: entrare in una zona con zombie > CP del gruppo blocca finché non li uccidi;
   armi esaurite = bloccato. `pathing.route_risks` lo segnala già.

## Fase 1 — rotte Fata nel dict

File: `src/myhordes_mcp/fata/towndata.py`.

- In `build_result` aggiungi `"routes": _parse_routes(raw.get("town_routes") or [], rel, who)`.
- Forma raw (verificata, 86 rotte in 8299 g.6): `{name, route_day, ap, mode, color, creator,
  editor, source, route: [{x,y}, …] (assoluti, angoli; segmenti dritti tra uno e l'altro),
  instructions: null | {"<indice passo>": "testo"}}`. Il primo punto è la città.
- Output per rotta: `name`, `day` (= route_day), `ap`, `creator` (nome via `who`),
  `waypoints` (relativi), `path` (tutte le zone passo per passo, relative, città esclusa
  all'inizio; espansione: avanza di 1 in x e/o y verso il punto seguente, come i segmenti Fata),
  `instructions` (dict indice → testo; l'indice è il passo nel `path`, 1 = prima zona: verifica
  su SA1 che il passo 29 cada su [4|5]).
- Aggiorna la docstring in testa al file (`town_routes` non più "unused"; scrivi la forma).
- `fata/parse.py` (giorni legacy) non ha rotte: `routes` assente/[] e il tool lo dice.

## Fase 2 — modulo `src/myhordes_mcp/fata/kills.py`

Docstring di testa con le regole sopra e le classi del sorgente citate (stile `supplies.py`).

1. `zone_estimate(zone, day, zone_map) -> dict` → `{min, avg, max, source}`:
   - aggiornata oggi (`risk.zone_is_today` e `zombies >= 0`): esatta, min = avg = max =
     `zombies`. Se `zombies_max` > `zombies`: aggiungi `killed_today = zombies_max - zombies`.
   - contata il giorno d < oggi, notti = oggi − d: con z > 0 → min z, avg z + notti, max
     z + 2 × notti. Con z = 0 → 0, salvo vicini (8) con zombie alla loro ultima conta: allora
     min 0, avg notti, max 2 × notti.
   - senza conta, solo `danger`: 1 → 1–2, 2 → 3–5, 3 → 6–9 (avg = centro); se non è
     `danger_today`, aggiungi la crescita come sopra.
   - mai visitata o fuori dalla mappa nota: `source = "unknown"`, esclusa dai totali,
     elencata ("da scoutare prima").
   - `source` in parole: "today", "day 4 (+2 nights)", "danger 2", "unknown".
   Con `day` passato (analisi di una rotta già fatta), usa `zombies_max` dove > 0: è la conta
   prima delle uccisioni. Il test di accettazione SA3 passa così.
2. `buckets(n) -> (pairs, singles)`; totali per rotta su min, avg, max separati.
3. `WEAPONS`: tabella del punto 4, con chiave interna, bucket, nomi Fata per stato (con
   cariche/colpi noti), media e peggiore. Riconoscimento per `name` del bank parsato
   (`data["bank"]`, nomi `name_en`), broken esclusi salvo armi riparabili (segnalate "da
   riparare in città").
4. `pick_kit(pairs, singles, stock, slots) -> dict`: copre le coppie con armi da coppia e i
   singoli con armi da singolo, sulla **media**, con le scorte della banca. Se mancano armi da
   singolo, un'arma da coppia copre il singolo (dillo: "1 colpo sprecato"); se mancano armi da
   coppia, un'arma da singolo copre la coppia con 2 usi. Preferenze: Laser con Battery prima
   del Machete solo se le Battery bastano; ricarica (Battery, Water, Repair Kit) prima di una
   seconda arma uguale se costa meno slot. Output: lista oggetti con quantità e slot, capacità
   media e peggiore per bucket, scoperto (se la banca non basta), copertura del **max** stimato.
   Modalità alternativa: `kit` dato dal giocatore ("laser, machete, battery=2") → solo verifica
   di copertura, nessuna scelta.
5. `respawn_after_kills(data, planned_avg) -> list[str]`: riusa i conti di
   `risk.respawn_check` (estrai una funzione che ritorni `known` e `threshold` invece di
   duplicare). Se `known − planned_avg < threshold` o la conta Fata è incompleta: riga
   "**Rischio respawn**: …" con i numeri. **Solo avviso**, non riduce le uccisioni proposte.

## Fase 3 — zoo e lati (`kills.zoo_clusters(data)`)

1. Zone "infette" = stima avg > 0 (fase 2) o `danger` > 0. Cluster = componenti connesse a 8
   vicini. Le zone mai visitate (`nyv`, non in `data["zones"]`; `meta.map_zones` = totale)
   adiacenti a un cluster gli si attaccano come "interno non visto".
2. Per cluster: n zone, zombie stimati (min/avg/max), riquadro, zone mai visitate, se tocca il
   bordo mappa. "Probabile zoo" = il più grande che tocca il bordo o ha zone mai visitate
   (euristica di `opti-town-meta.md` § Scout patterns).
3. Lati: zona di bordo = zona del cluster con almeno un vicino (4 direzioni) visitato e pulito.
   Lato = direzione di quel vicino (N/S/E/O; N = y crescente, coordinate relative alla città).
   Per lato: zone, zombie stimati, coppie/singoli, coordinate (max ~12, poi "+N").
4. In città 8299 g.6 lo zoo atteso è a nord/nord-ovest (zone mai visitate in alto a sinistra);
   il sud è pulito; la fascia x 1–6, y 0–13 è stata pulita il giorno 6.

## Fase 4 — tool `plan_kill_route` in `main.py`

Firma (solo dichiarazione in `main.py`, logica in `fata/kills.py` + supplies):

```
plan_kill_route(route: str = "", waypoints: str = "", zoo: bool = False, kit: str = "",
                party: str = "", group_cp: int = -1, start_ap: int = 6, slots: int = 5,
                available: str = "", second_wind: int = 0, day: int = 0, town_id: int = 0)
```

- `zoo=True` (o nessuna rotta): elenco cluster e lati (fase 3) + respawn check, e la riga
  "Chiedi al giocatore quale lato pulire, o quale area / corridoio". Niente kit.
- `route="SpecialAgent3"`: rotta Fata del giorno (match per nome, case-insensitive, prima
  esatto poi prefisso; più match → elencali e fermati). Con `day` la rotta di quel giorno.
- `waypoints="1,0; 1,13; 2,13; 2,0"`: rotta propria, segmenti dritti tra i punti, partenza città.
- Output (condensato, testo):
  1. intestazione: rotta, passi, AP;
  2. tabella zone con zombie: passo, zona, stima (min–max o esatta), fonte, coppie, singoli;
     zone "unknown" a parte;
  3. totali coppie/singoli (avg, e range min–max);
  4. kit dalla banca (o verifica del `kit` dato), slot del kit, scoperto;
  5. rifornimenti: chiama `supplies.plan` sulla **stessa rotta esatta** (non la safest path)
     con `slots − slot del kit`; riusa formattazione e rischi come fa
     `plan_expedition_supplies` (leggi `main.py` da r. 640 in poi per il cablaggio di Start,
     ritorno, teletrasporto, `end_requirements`). Le rotte Fata spesso finiscono vicino alla
     città (SA1–3 su [1|2]): gestisci il rientro come fa supplies;
  6. avvisi: respawn (fase 2.5), zone dove i zombie superano il CP del gruppo ("uccidi tutto
     prima di uscire"), istruzioni Fata della rotta.
- Docstring: quando usarlo ("kill run", "pulire lo zoo", "uccisioni", "SpecialAgent"), che
  ogni zona va pulita del tutto, che non deve inventare armi o conti propri, quando NON
  chiamare altro (non serve `get_zone_details` per le conte).

## Fase 5 — documentazione e deploy

- `docs/mechanics-in-code.md` tabella "Already in code": coppie/singoli, armi, despair/spread,
  stima crescita.
- `knowledge/tactics/weapons.md` § Planning a kill run: accorcia la procedura, rimanda al tool.
- `CLAUDE.md` (lista tool Live), `README.md` se elenca i tool, `prompts/game-primer.md` (una
  riga: uccisioni → `plan_kill_route`), `discord-listener.example.toml` allowlist.
- **Pi**: la toml del Pi è modificata a mano (gitignored): aggiungi
  `mcp__myhordes__plan_kill_route` all'allowlist, poi restart `discord-listener`
  (vedi memoria deploy flow: commit, push, pull sul Pi, restart perché cambiano prompt/toml).
- Allinea `risk._zombie_max_estimate` (+1,75/notte) e `_spread_risk_for_clear` (fino a 4 per
  passo) alle regole del sorgente (+2/notte max; zona vuota 1–2): stessa funzione di crescita
  in un posto solo. Cambia l'output di `get_zone_details`/mappa: verifica a mano su 8299.

Verifica (il repo non ha test suite): script di prova in scratchpad contro l'archivio
`towns/8299` (giorno 6) e una chiamata live; SA1–4 devono dare la tabella in alto.

## Fase 6 — v2, solo schizzo (rivedere con l'utente prima)

Generazione della rotta dato l'obiettivo:
- **lato dello zoo**: percorso lungo le zone di bordo di quel lato, ordinate per vicinanza;
- **area** (riquadro): passata a serpentina (boustrophedon) per righe o colonne, scegliendo
  l'orientamento con meno AP;
- **corridoio verso una rovina**: Dijkstra di `pathing` con costo che *non* evita gli zombie
  (costo = AP + peso uccisioni), larghezza 1;
- spezzare in più spedizioni quando AP (con supplies) o armi non bastano: ogni spedizione
  parte e torna dalla città, coprendo un tratto contiguo; output = elenco spedizioni con
  waypoint pronti da disegnare su Fata (il tool non scrive su Fata: read-only).
