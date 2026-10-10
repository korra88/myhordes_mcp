"""Fata Morgana — crowd-sourced town state scraped from the spy page.

Every request goes through client.fetch_town_data(); the other modules only
parse or format its result.
"""

from .bank import format_bank, format_bank_summary
from .buildings import format_buildings
from .client import fetch_town_data
from .pathing import find_safe_path
from .town import format_citizens, format_defense, format_town_overview
from .zones import format_scout, format_zone_path, format_zones

__all__ = [
    "fetch_town_data",
    "format_bank",
    "format_bank_summary",
    "format_buildings",
    "format_citizens",
    "format_defense",
    "format_scout",
    "format_town_overview",
    "format_zone_path",
    "format_zones",
    "find_safe_path",
]
