"""Fata Morgana — crowd-sourced town state from the /towndata endpoint.

Every request goes through client.fetch_town_data(); the other modules only
parse or format its result.
"""

from .changes import get_town_changes
from .dump import format_dump_mapping
from .night import format_night_report
from .roster import format_roster
from .bank import expedition_extras, format_bank, format_bank_summary
from .blueprints import format_blueprint_order
from .buildings import format_buildings
from .client import fetch_town_data
from .cp import format_cp_log, load_cp_log, party_cp
from .kills import plan_kill_route
from .pathing import find_safe_path
from .planning import format_build_options, format_construction_history
from .town import format_citizens, format_defense, format_town_overview
from .zones import format_scout, format_zone_path, format_zones

__all__ = [
    "fetch_town_data",
    "format_cp_log",
    "load_cp_log",
    "party_cp",
    "expedition_extras",
    "format_bank",
    "format_bank_summary",
    "format_blueprint_order",
    "format_buildings",
    "format_citizens",
    "format_defense",
    "format_scout",
    "format_town_overview",
    "format_zone_path",
    "format_zones",
    "find_safe_path",
    "plan_kill_route",
    "get_town_changes",
    "format_dump_mapping",
    "format_night_report",
    "format_roster",
    "format_build_options",
    "format_construction_history",
]
