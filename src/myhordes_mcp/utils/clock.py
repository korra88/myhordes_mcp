"""Game clock helpers. MyHordes runs on French time (attack at ~23:59 CET/CEST)."""

from datetime import datetime
from zoneinfo import ZoneInfo

GAME_TZ = ZoneInfo("Europe/Paris")


def now() -> datetime:
    return datetime.now(GAME_TZ)


def fmt_epoch(ts: int | float | None, with_date: bool = False) -> str:
    """Epoch seconds → 'HH:MM' (or 'YYYY-MM-DD HH:MM') in game time."""
    if not ts:
        return "?"
    dt = datetime.fromtimestamp(ts, GAME_TZ)
    return dt.strftime("%Y-%m-%d %H:%M" if with_date else "%H:%M")


# How old a live Fata snapshot may get before tools say so
# (knowledge/tactics/mcp-guidelines.md, "Staleness rules").
MAYBE_STALE_MIN = 60
STALE_MIN = 180


def _duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min"


def data_updated(meta: dict, at: datetime | None = None) -> str:
    """The 'Data updated:' header line: when Fata last got a report, how long ago,
    and whether that is stale, so the model never compares clock times itself.
    Fata updates only when a player sends data, so a live day ages as the game
    goes on; a past day's snapshot gets no age (`meta['live']` False)."""
    raw = meta.get("data_time")
    if not raw:
        return "Data updated: unknown (treat as stale)"
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=GAME_TZ)
    except ValueError:
        return f"Data updated: {raw}"
    shown = dt.strftime("%Y-%m-%d %H:%M")
    if meta.get("live") is False:
        return f"Data updated: {shown} (snapshot of past day {meta.get('day', '?')})"
    minutes = max(0, int(((at or now()) - dt).total_seconds() // 60))
    age = f"{_duration(minutes)} ago"
    if minutes >= STALE_MIN:
        return (f"Data updated: {shown} ({age}) — STALE: say so, and do not state who is "
                "inside or outside, or the current defense, as fact")
    if minutes >= MAYBE_STALE_MIN:
        return f"Data updated: {shown} ({age}) — may be stale: positions may have changed"
    return f"Data updated: {shown} ({age})"
