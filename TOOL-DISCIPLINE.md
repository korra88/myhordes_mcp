# Tool discipline

Measured on a 12B local model: without these rules it repeated one identical
`search_wiki` call six times and never answered. With them, one call, answered.

## Never repeat a call
Do not call a tool twice with the same arguments. If a call returned results,
those ARE the results — calling again returns the same thing. If you need
something else, change the query.

## A partial match is evidence
If you search for an item and get a similarly-named one, say what you found
and how it differs from what was asked. Do not re-search hoping for a better
match. If two different searches fail, the thing is not in the wiki — say so.

## Ground every claim
Every number, item name, effect and cost you state must come from a tool
result in this conversation. If you did not read it in a tool result, do not
state it. This matters most for item effects and roles: never infer what an
item does from its name.

## Label estimates, refuse the unknowable
When you extrapolate beyond the data, say "estimate, not from data" and show
what you extrapolated from. When the answer is not obtainable — a future day
the forecast does not cover, a real-world identity, an item that does not
exist — say that plainly instead of filling the gap.

## Prefer the condensed tool output
Tools that take a `detail` or `mode` argument default to the summary form on
purpose. Use the default. Only request the full/raw form when the user
explicitly asks for a complete listing.
