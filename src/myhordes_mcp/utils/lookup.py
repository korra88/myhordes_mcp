"""Pick one name from a list by what the player typed: exact, then unique prefix, then
unique substring (case-insensitive). Each tool says what it does with none or several."""

from typing import NamedTuple


class Found(NamedTuple):
    match: str | None        # the one name, None when none or several matched
    hits: list[str]          # names matched at the first level that matched (distinct)
    how: str                 # "exact" | "prefix" | "substring" | "" (nothing matched)


def lookup(names, query: str) -> Found:
    low = query.strip().lower()
    distinct = list(dict.fromkeys(names))
    for how, test in (("exact", lambda n: n == low),
                      ("prefix", lambda n: n.startswith(low)),
                      ("substring", lambda n: low in n)):
        hits = [n for n in distinct if test(n.lower())]
        if hits:
            return Found(hits[0] if len(hits) == 1 else None, hits, how)
    return Found(None, [], "")


def ambiguous(query: str, hits: list[str], what: str = "names", limit: int = 12) -> str:
    """'Error: 'x' matches 3 routes: a; b; c. Use the full name.'"""
    shown = "; ".join(hits[:limit]) + (f" (+{len(hits) - limit} more)" if len(hits) > limit else "")
    return f"Error: '{query.strip()}' matches {len(hits)} {what}: {shown}. Use the full name."
