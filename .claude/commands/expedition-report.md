Audit or generate the town's expedition roster: who is outside, who is on no list, how many are scrapping. Pass an existing BBCode list to audit it; pass nothing to build one fresh.

## Step 1 — Fetch live positions

Call `get_citizen_positions()` once. That is the only required call.

It returns, per citizen: **name, class, coordinates**. Nothing else.
It does NOT return inventory — never claim a citizen has a bike, shoes, drugs or
any item based on this tool. Bike/booster slots stay `???` unless the user says who has what.

Do not also call `get_town_overview` — its roster is condensed and redundant here.

## Step 2 — Classify every citizen outside

Distance from town = **Manhattan**: `|x| + |y|` (movement is orthogonal, so this is AP cost).

| Distance | Bucket |
|---|---|
| 1 — exactly `[1\|0]`, `[-1\|0]`, `[0\|1]`, `[0\|-1]` | **Scrapper**. Count only, never assign to an expedition slot. |
| ≥2 | Expedition candidate. Must appear on a list. |

Citizens inside town are out of scope. Never list them.

## Step 3 — Reconcile against the user's list

For each name on the user's list, confirm it appears in the live outside roster.
Then split the outside roster three ways and **verify the arithmetic**:

```
listed + scrappers + unaccounted = total outside
```

State that equation with real numbers in the report. If it does not balance, stop
and re-check — a name was misread or a citizen walked home.

Report in this order:
1. **Unaccounted** — outside, distance ≥2, on no list. Table: name, class, position, distance. This is the headline; it is what the user asked for.
2. **Scrapper count** — one total, plus their tiles.
3. **Ghosts** — names on the list not found outside (in town, or died).

**Never remove a name from the list.** A name on the list is a reserved slot: that
citizen may have already run their trip and walked home, or may be leaving later in
the day. A citizen found inside town keeps their slot — annotate it (e.g.
`[i](in town)[/i]`) and say so in the summary. Only death removes a name, and then
say so explicitly.

## Step 4 — Verify class tags

The user's list carries class icons that drift as citizens change job or get
mislabelled at sign-up. Compare each against live data and correct silently in
the rewritten list, then note every change in a one-line summary after it.

| Class | Icon |
|---|---|
| Guardian | `:guard:` |
| Tamer | `:tamer:` |
| Scavenger | `:scav:` |
| Technician | `:tech:` |
| Survivalist | `:surv:` |
| Scout | `:scout:` |
| Shaman | `:sham:` |
| Unknown / placeholder | `:human:` |

`:protamer:` marks a Tamer carrying a **pro** camping kit — this is user-supplied
knowledge, not derivable from the API. Preserve it wherever the user already wrote
it; never add or remove it on your own.

If unsure an icon name exists on the town's forum, use `:human:` and say so
rather than inventing a tag.

## Step 5 — Group by destination

Group expedition members by **exact shared tile**, not by proximity. Citizens two
cells apart are two groups, and saying otherwise hides a split party.

To name the ruin on a tile, call `get_zone_details()` with no arguments — it lists
every zone holding a ruin or ground items, with names. There is no lookup-by-name
parameter; match the name yourself against the returned coordinates. Only pass
`x1/y1/x2/y2` to narrow a large map, never to find a ruin you cannot place.

Flag any group whose members are scattered across tiles — a five-person expedition
sitting on three tiles is not a convoy, and the organiser needs to know.

## Step 6 — Output

Reproduce the user's own BBCode structure verbatim: same section order, same
`{hr}` separators, same `[b][big]...[/big][/b]` headers, same numbering, same
handles. This gets pasted straight into the forum — a reformatted list is a
useless list.

Preserve struck-through cancelled sections (`[s]...[/s]`) and their italic notes.

Place newly found citizens in existing empty `???` slots before adding new ones.

Write every name the way it already appears on the user's list. If an entry carries
an `@name:userid` handle, keep that handle verbatim. For a name you are adding, or
one whose user ID you do not have, write the **bare name** — `PlayerName`, not
`@PlayerName:?????`. Never invent an ID and never emit a `?????` placeholder: the forum
does not parse it and the organiser has to hand-edit every one.

Close the list with the scrapper total:

```
[b]Scrappers (distance 1):[/b] N
```

Then, outside the code block, a short summary of every change made: names added,
class tags corrected, groups flagged as scattered.

## Step 7 — Offer the bike pass

Mobility slots stay `???` because no tool attributes items to citizens. Close the
report by offering the one path that does, in a single line:

> Bike slots are blank — no tool says who carries what. Paste the bank log and I
> will fill them.

Only the **bank log** (the `X took Mountain Bike` transaction lines) names the
citizen. `get_bank_inventory` returns current contents, so it yields a count of
bikes gone, never a name — do not call it for this and do not offer it as a
substitute.

If the user supplies the log: match taker names against the outside roster, mark
those citizens `[BIKE]` in their slot, and move the first confirmed bike carrier
into Free Expeditions slot 1. Takers who are back inside town get no mark. Say how
many bikes were unaccounted for, if any.

Skip this offer entirely when the user already supplied bike data.

## Generate mode (no list supplied)

Same steps 1–2 and 5. Build sections per ruin found at occupied tiles, plus a
`Free Expeditions` section for everyone else at distance ≥2, plus the scrapper
total. Leave slot 1 of Free Expeditions as `:human: with a bike ???` — the town's
convention for the mobility slot.
