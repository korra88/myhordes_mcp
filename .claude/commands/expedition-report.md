Audit or generate the town's expedition roster: who is outside, who is on no list, how many are scrapping. Pass an existing BBCode list to audit it; pass nothing to build one fresh.

## Step 1 — Fetch the roster

Extract every name from the user's list (strip BBCode; keep `@name:id` handles as
written) and call `get_expedition_roster(listed="Name1, Name2, …")` once. Without a
list, call it with no arguments.

It returns, computed in code: the accounting equation
`listed + scrappers + unaccounted = outside`, the **unaccounted** citizens (outside,
distance ≥2, on no list) with class icon and distance, listed names **not outside**
(in town / dead / unknown spelling), everyone at distance ≥2 grouped by **exact
tile** with ruin names, and the scrapper count (distance 1, not listed).

Distance is Manhattan (AP from town). No tool returns inventory: never claim a
citizen carries a bike, shoes or drugs. Do not also call `get_citizen_positions`,
`get_town_overview` or `get_zone_details` — the roster already has tiles and ruins.

## Step 2 — Report

Report in this order:
1. **Unaccounted** — from the tool. This is the headline.
2. **Scrapper count** — one total, plus their tiles.
3. **Ghosts** — listed names not outside, with the tool's reason.

Quote the tool's accounting equation. **Never remove a name from the list.** A
name on the list is a reserved slot: that citizen may have already run their trip
or may leave later. A citizen in town keeps their slot — annotate it (e.g.
`[i](in town)[/i]`). Only death removes a name, and then say so explicitly.

## Step 3 — Scattered groups

Compare each expedition on the user's list with the tool's tile groups. Members
of one expedition on different tiles = a split party: flag it. Group by exact
tile, never by proximity.

## Step 4 — Verify class tags

The user's list carries class icons that drift as citizens change job or get
mislabelled at sign-up. Compare each against the tool's icons and correct silently in
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

## Step 5 — Output

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

## Step 6 — Offer the bike pass

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

Step 1 without a list. Build sections per ruin found at occupied tiles, plus a
`Free Expeditions` section for everyone else at distance ≥2, plus the scrapper
total. Leave slot 1 of Free Expeditions as `:human: with a bike ???` — the town's
convention for the mobility slot.
