"""Shared text pieces for tool output (headers, labels, plurals): one form each."""

from .clock import data_updated


def town_name(meta: dict) -> str:
    return meta.get("town_name") or "?"


def heading(title: str, meta: dict) -> str:
    """'## Title — Town Day N' (unknown town or day shown as '?')."""
    return f"## {title} — {town_name(meta)} Day {meta.get('day') or '?'}"


def header(title: str, meta: dict, *, suffix: str = "") -> str:
    """heading + the 'Data updated:' line (suffix goes on that line)."""
    return heading(title, meta) + "\n" + data_updated(meta, suffix=suffix)


def updated(day, stale: bool = False) -> str:
    """'(updated d7)' / '(updated d4, STALE)': how old a zone or position reading is."""
    return f"(updated d{day}{', STALE' if stale else ''})"


def estimate(lo, hi, status: str | None = None, unit: str = " zombies") -> str:
    """'321–357 zombies (partial)': an attack estimate. status: 'partial' | 'confirmed'
    (est_status); unit '' where a column or label already says what is counted."""
    return f"{lo}–{hi}{unit}" + (f" ({status})" if status else "")


def est_status(maxed) -> str:
    """Fata's `maxed` flag: a confirmed estimate has reached its final range."""
    return "confirmed" if maxed else "partial"


def num(x) -> str:
    """3 -> '3', 2.5 -> '2.5', 2.0 -> '2' (one decimal at most)."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def plural(n, word: str, plural_form: str | None = None) -> str:
    """'1 slot', '3 slots' ('1 supply', '2 supplies' with plural_form)."""
    return f"{num(n)} {word if n == 1 else plural_form or word + 's'}"
