"""Unit tests for MLB tools, NHL tools, quantitative analytics, Pydantic schemas, and LLM recovery."""

from __future__ import annotations

import os
import unittest

os.environ["WAR_ROOM_OFFLINE_FALLBACK"] = "TRUE"

from pressbox_war_room._adk_compat import ToolContext
from pressbox_war_room.tools import (
    TOOL_JSON_SCHEMAS,
    calculate_advanced_matchup_edge,
    compute_log5_probability,
    compute_pythagorean_expectancy,
    get_mlb_schedule_and_probables,
    get_mlb_standings_snapshot,
    get_mlb_team_and_pitcher_splits,
    get_nhl_schedule_and_matchup,
    get_nhl_standings_snapshot,
    get_nhl_team_special_teams_and_goalies,
    manage_scouting_watchlist,
    verify_and_approve_dossier,
)


class TestPressBoxWarRoomTools(unittest.TestCase):
    """Verifies Tool & Interface Design (Pydantic schemas + zero silent fallbacks) and Context & Memory."""

    def test_all_tools_expose_pydantic_input_output_and_error_json_schemas(self) -> None:
        expected_tools = [
            get_mlb_schedule_and_probables,
            get_mlb_team_and_pitcher_splits,
            get_mlb_standings_snapshot,
            get_nhl_schedule_and_matchup,
            get_nhl_team_special_teams_and_goalies,
            get_nhl_standings_snapshot,
            calculate_advanced_matchup_edge,
            manage_scouting_watchlist,
            verify_and_approve_dossier,
        ]
        for tool_fn in expected_tools:
            self.assertTrue(hasattr(tool_fn, "input_schema"))
            self.assertTrue(hasattr(tool_fn, "output_schema"))
            self.assertTrue(hasattr(tool_fn, "error_schema"))
            self.assertIn(tool_fn.__name__, TOOL_JSON_SCHEMAS)
            schema_bundle = TOOL_JSON_SCHEMAS[tool_fn.__name__]
            self.assertIn("properties", schema_bundle["input_json_schema"])
            self.assertIn("properties", schema_bundle["output_json_schema"])
            self.assertIn("llm_recovery_instructions", schema_bundle["error_json_schema"]["properties"])

    def test_no_silent_fallback_on_invalid_mlb_or_nhl_inputs(self) -> None:
        # 1. Invalid MLB team code must NOT silently default to NYY
        bad_mlb = get_mlb_schedule_and_probables("INVALID_TEAM_XYZ", "LAD")
        self.assertEqual(bad_mlb["status"], "error")
        self.assertEqual(bad_mlb["error_code"], "UNSUPPORTED_MLB_TEAM")
        self.assertTrue(len(bad_mlb["valid_options"]) >= 6)
        self.assertIn("RECOVERY INSTRUCTIONS FOR LLM", bad_mlb["llm_recovery_instructions"])

        # 2. Identical MLB matchup teams must return guided error
        same_mlb = get_mlb_team_and_pitcher_splits("NYY", "Yankees")
        self.assertEqual(same_mlb["status"], "error")
        self.assertEqual(same_mlb["error_code"], "IDENTICAL_MATCHUP_TEAMS")

        # 3. Invalid NHL team code must NOT silently default to BOS
        bad_nhl = get_nhl_schedule_and_matchup("LAKERS", "TOR")
        self.assertEqual(bad_nhl["status"], "error")
        self.assertEqual(bad_nhl["error_code"], "UNSUPPORTED_NHL_TEAM")
        self.assertIn("RECOVERY INSTRUCTIONS FOR LLM", bad_nhl["llm_recovery_instructions"])

        # 4. Invalid league / conference filters must return guided error
        bad_standings = get_mlb_standings_snapshot("PREMIER_LEAGUE")
        self.assertEqual(bad_standings["status"], "error")
        self.assertEqual(bad_standings["error_code"], "INVALID_MLB_LEAGUE_FILTER")

        bad_nhl_standings = get_nhl_standings_snapshot("NBA_WEST")
        self.assertEqual(bad_nhl_standings["status"], "error")
        self.assertEqual(bad_nhl_standings["error_code"], "INVALID_NHL_CONFERENCE_FILTER")

        # 5. Invalid sport in calculate_advanced_matchup_edge
        bad_edge = calculate_advanced_matchup_edge("SOCCER", "NYY", "LAD")
        self.assertEqual(bad_edge["status"], "error")
        self.assertEqual(bad_edge["error_code"], "INVALID_SPORT_IDENTIFIER")

    def test_mlb_schedule_and_splits_populate_tool_context(self) -> None:
        ctx = ToolContext(state={})
        sched = get_mlb_schedule_and_probables("Yankees", "Dodgers", tool_context=ctx)
        self.assertEqual(sched["status"], "success")
        self.assertEqual(sched["home_team"]["code"], "NYY")
        self.assertEqual(sched["away_team"]["code"], "LAD")
        self.assertIn("Gerrit Cole", sched["home_team"]["probable_starter"]["name"])

        splits = get_mlb_team_and_pitcher_splits("NYY", "LAD", tool_context=ctx)
        self.assertEqual(splits["status"], "success")
        self.assertGreater(splits["run_differential"], 100)
        self.assertIn("temp:mlb_intel", ctx.state)
        self.assertIn("mlb_scouting_intel", ctx.state)

    def test_mlb_standings_snapshot(self) -> None:
        ctx = ToolContext(state={})
        standings = get_mlb_standings_snapshot("AL", tool_context=ctx)
        self.assertEqual(standings["status"], "success")
        self.assertTrue(all(t["league"] == "AL" for t in standings["standings"]))

    def test_nhl_schedule_and_special_teams(self) -> None:
        ctx = ToolContext(state={})
        sched = get_nhl_schedule_and_matchup("Bruins", "Maple Leafs", tool_context=ctx)
        self.assertEqual(sched["status"], "success")
        self.assertEqual(sched["home_team"]["code"], "BOS")
        self.assertEqual(sched["away_team"]["code"], "TOR")

        stats = get_nhl_team_special_teams_and_goalies("BOS", "TOR", tool_context=ctx)
        self.assertEqual(stats["status"], "success")
        self.assertAlmostEqual(
            stats["special_teams"]["net_special_teams_index"], 104.7, places=1
        )
        self.assertIn("temp:nhl_intel", ctx.state)

    def test_nhl_standings_snapshot(self) -> None:
        standings = get_nhl_standings_snapshot("Eastern")
        self.assertEqual(standings["status"], "success")
        self.assertGreaterEqual(len(standings["standings"]), 3)

    def test_quantitative_matchup_analytics_mlb_and_nhl(self) -> None:
        ctx = ToolContext(state={})
        pyth = compute_pythagorean_expectancy(815, 668, exponent=1.83)
        self.assertGreater(pyth, 0.58)
        self.assertAlmostEqual(compute_log5_probability(0.600, 0.600), 0.500, places=3)

        mlb_edge = calculate_advanced_matchup_edge("MLB", "NYY", "LAD", tool_context=ctx)
        self.assertEqual(mlb_edge["sport"], "MLB")
        self.assertAlmostEqual(
            mlb_edge["win_probability"]["NYY"] + mlb_edge["win_probability"]["LAD"],
            1.0,
            places=4,
        )

        nhl_edge = calculate_advanced_matchup_edge("NHL", "BOS", "TOR", tool_context=ctx)
        self.assertEqual(nhl_edge["sport"], "NHL")
        self.assertGreater(
            nhl_edge["tactical_edges"]["special_teams_edge_for_home"], 0.0
        )
        self.assertIn("temp:matchup_edges", ctx.state)

    def test_memory_watchlist_and_loop_escalation(self) -> None:
        ctx = ToolContext(state={})
        res_add = manage_scouting_watchlist(
            action="add",
            sport="NHL",
            team_or_player="EDM",
            scouting_note="Elite 26.3% Power Play unit led by Connor McDavid",
            tool_context=ctx,
        )
        self.assertIn("EDM", res_add["watchlist"]["NHL"])
        self.assertEqual(res_add["scouting_notes_count"], 1)

        res_remove = manage_scouting_watchlist(
            action="remove",
            sport="NHL",
            team_or_player="EDM",
            tool_context=ctx,
        )
        self.assertNotIn("EDM", res_remove["watchlist"]["NHL"])

        # Missing required corrections_needed when verification_passed=False should return error
        bad_reject = verify_and_approve_dossier(
            verification_passed=False,
            audited_claims_count=4,
            audit_summary="Starter ERA mismatch",
            corrections_needed=None,
            tool_context=ctx,
        )
        self.assertEqual(bad_reject["status"], "error")
        self.assertEqual(bad_reject["error_code"], "MISSING_CORRECTION_INSTRUCTIONS")

        # Valid Critic rejection without escalation
        reject_res = verify_and_approve_dossier(
            verification_passed=False,
            audited_claims_count=4,
            audit_summary="Starter ERA mismatch",
            corrections_needed="Update Gerrit Cole ERA to 3.18",
            tool_context=ctx,
        )
        self.assertFalse(reject_res["verification_passed"])
        self.assertFalse(ctx.actions.escalate)

        # Critic approval triggering ADK exit_loop (escalate = True)
        approve_res = verify_and_approve_dossier(
            verification_passed=True,
            audited_claims_count=6,
            audit_summary="All MLB & NHL statistics verified against raw tool outputs.",
            tool_context=ctx,
        )
        self.assertTrue(approve_res["verification_passed"])
        self.assertTrue(ctx.actions.escalate)


if __name__ == "__main__":
    unittest.main()
