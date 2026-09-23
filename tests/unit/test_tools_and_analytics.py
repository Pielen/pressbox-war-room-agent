"""Unit tests for MLB tools, NHL tools, quantitative analytics, and session memory."""

from __future__ import annotations

import os
import unittest

os.environ["WAR_ROOM_OFFLINE_FALLBACK"] = "TRUE"

from pressbox_war_room._adk_compat import ToolContext
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


class TestPressBoxWarRoomTools(unittest.TestCase):
    """Verifies Tool & Interface Design and Context & Memory behavior."""

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

        # Test Critic verification without escalation first
        reject_res = verify_and_approve_dossier(
            verification_passed=False,
            audited_claims_count=4,
            audit_summary="Starter ERA mismatch",
            corrections_needed="Update Gerrit Cole ERA to 3.18",
            tool_context=ctx,
        )
        self.assertFalse(reject_res["verification_passed"])
        self.assertFalse(ctx.actions.escalate)

        # Test Critic approval triggering ADK exit_loop (escalate = True)
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
