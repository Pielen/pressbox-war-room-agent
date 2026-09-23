"""Quantitative Cross-Sport Matchup Analytics Tools (Pythagorean, Log5, Special Teams & Platoon Edges)."""

from __future__ import annotations

from typing import Any, Optional

from pressbox_war_room._adk_compat import ToolContext
from pressbox_war_room.tools.mlb_tools import MLB_TEAM_DIRECTORY, normalize_mlb_team_code
from pressbox_war_room.tools.nhl_tools import NHL_TEAM_DIRECTORY, normalize_nhl_team_code


def compute_pythagorean_expectancy(
    scored: float, allowed: float, exponent: float = 1.83
) -> float:
    """Computes Bill James Pythagorean win expectancy: S^exp / (S^exp + A^exp)."""
    if scored <= 0 and allowed <= 0:
        return 0.500
    if allowed <= 0:
        return 0.999
    s_pow = float(scored) ** exponent
    a_pow = float(allowed) ** exponent
    return round(s_pow / (s_pow + a_pow), 4)


def compute_log5_probability(prob_a: float, prob_b: float) -> float:
    """Computes Bill James Log5 head-to-head probability for Team A vs Team B."""
    pa = min(max(prob_a, 0.01), 0.99)
    pb = min(max(prob_b, 0.01), 0.99)
    denom = pa + pb - (2.0 * pa * pb)
    if abs(denom) < 1e-9:
        return 0.500
    return round((pa - (pa * pb)) / denom, 4)


def calculate_advanced_matchup_edge(
    sport: str,
    home_team: str,
    away_team: str,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Calculates quantitative head-to-head win probabilities and tactical edges for MLB or NHL.

    Computes:
    - Pythagorean Win Expectancy (exponent 1.83 for MLB, 2.05 for NHL)
    - Bill James Log5 Head-to-Head Win Probability (including home-field/ice adjustment)
    - Sport-specific tactical deltas (Starter ERA & Platoon OPS for MLB; Net Special Teams
      Index PP%+PK% & Goalie GSAx delta for NHL)

    Args:
        sport: Either 'MLB' (baseball) or 'NHL' (ice hockey).
        home_team: Home team code or name (e.g. 'NYY', 'LAD', 'BOS', 'EDM').
        away_team: Away team code or name (e.g. 'LAD', 'BOS', 'TOR', 'FLA').
        tool_context: Optional ADK ToolContext to persist calculated edges in session state.

    Returns:
        dict[str, Any]: Quantitative matchup edge breakdown and recommended tactical keys.
    """
    sport_norm = sport.strip().upper()
    if sport_norm in ("BASEBALL", "MLB"):
        home_code = normalize_mlb_team_code(home_team)
        away_code = normalize_mlb_team_code(away_team)
        home_info = MLB_TEAM_DIRECTORY.get(home_code, MLB_TEAM_DIRECTORY["NYY"])
        away_info = MLB_TEAM_DIRECTORY.get(away_code, MLB_TEAM_DIRECTORY["LAD"])

        home_pyth = compute_pythagorean_expectancy(
            home_info["runs_scored"], home_info["runs_allowed"], exponent=1.83
        )
        away_pyth = compute_pythagorean_expectancy(
            away_info["runs_scored"], away_info["runs_allowed"], exponent=1.83
        )
        neutral_log5 = compute_log5_probability(home_pyth, away_pyth)
        # Standard MLB home-field advantage (~ +2.0% win prob boost)
        home_win_prob = round(min(max(neutral_log5 + 0.02, 0.05), 0.95), 4)
        away_win_prob = round(1.0 - home_win_prob, 4)

        starter_era_delta = round(
            away_info["probable_starter"]["era"] - home_info["probable_starter"]["era"],
            2,
        )
        bullpen_era_delta = round(
            away_info["bullpen_era"] - home_info["bullpen_era"], 2
        )

        result = {
            "status": "success",
            "sport": "MLB",
            "home_team": home_code,
            "away_team": away_code,
            "pythagorean_expectancy": {
                home_code: home_pyth,
                away_code: away_pyth,
                "exponent": 1.83,
            },
            "win_probability": {
                home_code: home_win_prob,
                away_code: away_win_prob,
                "neutral_site_log5": neutral_log5,
                "favored_team": home_code if home_win_prob >= 0.5 else away_code,
            },
            "tactical_edges": {
                "starting_pitching_era_edge_for_home": starter_era_delta,
                "bullpen_era_edge_for_home": bullpen_era_delta,
                "home_starter": home_info["probable_starter"]["name"],
                "away_starter": away_info["probable_starter"]["name"],
            },
        }
    else:
        home_code = normalize_nhl_team_code(home_team)
        away_code = normalize_nhl_team_code(away_team)
        home_info = NHL_TEAM_DIRECTORY.get(home_code, NHL_TEAM_DIRECTORY["BOS"])
        away_info = NHL_TEAM_DIRECTORY.get(away_code, NHL_TEAM_DIRECTORY["TOR"])

        home_pyth = compute_pythagorean_expectancy(
            home_info["goals_for"], home_info["goals_against"], exponent=2.05
        )
        away_pyth = compute_pythagorean_expectancy(
            away_info["goals_for"], away_info["goals_against"], exponent=2.05
        )
        neutral_log5 = compute_log5_probability(home_pyth, away_pyth)
        # Standard NHL home-ice last-change advantage (~ +2.5% win prob boost)
        home_win_prob = round(min(max(neutral_log5 + 0.025, 0.05), 0.95), 4)
        away_win_prob = round(1.0 - home_win_prob, 4)

        home_st_index = round(home_info["pp_pct"] + home_info["pk_pct"], 1)
        away_st_index = round(away_info["pp_pct"] + away_info["pk_pct"], 1)
        goalie_gsax_delta = round(
            home_info["starting_goalie"]["gsax"] - away_info["starting_goalie"]["gsax"],
            1,
        )

        result = {
            "status": "success",
            "sport": "NHL",
            "home_team": home_code,
            "away_team": away_code,
            "pythagorean_expectancy": {
                home_code: home_pyth,
                away_code: away_pyth,
                "exponent": 2.05,
            },
            "win_probability": {
                home_code: home_win_prob,
                away_code: away_win_prob,
                "neutral_site_log5": neutral_log5,
                "favored_team": home_code if home_win_prob >= 0.5 else away_code,
            },
            "tactical_edges": {
                "home_net_special_teams_index": home_st_index,
                "away_net_special_teams_index": away_st_index,
                "special_teams_edge_for_home": round(home_st_index - away_st_index, 1),
                "goalie_gsax_edge_for_home": goalie_gsax_delta,
                "home_goalie": home_info["starting_goalie"]["name"],
                "away_goalie": away_info["starting_goalie"]["name"],
            },
        }

    if tool_context is not None:
        edges = tool_context.state.setdefault("temp:matchup_edges", {})
        edges[f"{result['sport']}:{home_code}_vs_{away_code}"] = result

    return result
