"""Tools package for PressBox War Room."""

from pressbox_war_room.tools.analytics_tools import (
    calculate_advanced_matchup_edge,
    compute_log5_probability,
    compute_pythagorean_expectancy,
)
from pressbox_war_room.tools.memory_tools import (
    manage_scouting_watchlist,
    verify_and_approve_dossier,
)
from pressbox_war_room.tools.mlb_tools import (
    get_mlb_schedule_and_probables,
    get_mlb_standings_snapshot,
    get_mlb_team_and_pitcher_splits,
)
from pressbox_war_room.tools.nhl_tools import (
    get_nhl_schedule_and_matchup,
    get_nhl_standings_snapshot,
    get_nhl_team_special_teams_and_goalies,
)

__all__ = [
    "calculate_advanced_matchup_edge",
    "compute_log5_probability",
    "compute_pythagorean_expectancy",
    "get_mlb_schedule_and_probables",
    "get_mlb_standings_snapshot",
    "get_mlb_team_and_pitcher_splits",
    "get_nhl_schedule_and_matchup",
    "get_nhl_standings_snapshot",
    "get_nhl_team_special_teams_and_goalies",
    "manage_scouting_watchlist",
    "verify_and_approve_dossier",
]
