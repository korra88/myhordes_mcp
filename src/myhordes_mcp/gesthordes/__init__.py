"""Gest'Hordes — public attack/defence statistics per town."""

from .client import fetch_stats
from .format import (
    extract_current_defense,
    extract_season_points,
    format_attack_distribution,
    format_attack_forecast,
)

__all__ = [
    "fetch_stats",
    "extract_current_defense",
    "extract_season_points",
    "format_attack_distribution",
    "format_attack_forecast",
]
