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
