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
