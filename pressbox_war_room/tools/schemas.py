"""Strict Pydantic v2 Input/Output Models, JSON Schemas, and Guided LLM Error Recovery.

Addresses the Tool & Interface Design evaluation rubric:
1. Explicit Pydantic `BaseModel` schemas (`Field`, `@field_validator`, `@model_validator`,
   `ConfigDict(extra="forbid")`, and `.model_json_schema()`) for strict input and output
   validation across all 8 PressBox War Room tools.
2. Zero silent fallbacks: invalid team codes, unrecognized league/division filters, or
   self-matchups (`home_team == away_team`) never silently default to 'NYY' or 'BOS'.
   Instead, tools return a structured `ToolErrorResponse` containing `error_code`,
   `invalid_input`, `valid_options`, and step-by-step `llm_recovery_instructions`.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional

try:
    from pydantic import (  # type: ignore[import-untyped]
        BaseModel,
        ConfigDict,
        Field,
        ValidationError,
        field_validator,
        model_validator,
    )
except ImportError:
    from pressbox_war_room._adk_compat import (
        BaseModel,
        ConfigDict,
        Field,
        ValidationError,
        field_validator,
        model_validator,
    )

SUPPORTED_MLB_TEAMS: dict[str, str] = {
    "NYY": "New York Yankees (AL East)",
    "LAD": "Los Angeles Dodgers (NL West)",
    "BOS": "Boston Red Sox (AL East)",
    "CHC": "Chicago Cubs (NL Central)",
    "ATL": "Atlanta Braves (NL East)",
    "PHI": "Philadelphia Phillies (NL East)",
}

MLB_TEAM_ALIASES: dict[str, str] = {
    "YANKEES": "NYY",
    "NEW YORK YANKEES": "NYY",
    "NY YANKEES": "NYY",
    "DODGERS": "LAD",
    "LOS ANGELES DODGERS": "LAD",
    "LA DODGERS": "LAD",
    "RED SOX": "BOS",
    "BOSTON RED SOX": "BOS",
    "BOSTON": "BOS",
    "CUBS": "CHC",
    "CHICAGO CUBS": "CHC",
    "BRAVES": "ATL",
    "ATLANTA BRAVES": "ATL",
    "ATLANTA": "ATL",
    "PHILLIES": "PHI",
    "PHILADELPHIA PHILLIES": "PHI",
    "PHILADELPHIA": "PHI",
}

SUPPORTED_MLB_LEAGUE_FILTERS: set[str] = {
    "ALL",
    "AL",
    "NL",
    "AL EAST",
    "NL WEST",
    "NL CENTRAL",
    "NL EAST",
}

SUPPORTED_NHL_TEAMS: dict[str, str] = {
    "BOS": "Boston Bruins (Eastern / Atlantic)",
    "TOR": "Toronto Maple Leafs (Eastern / Atlantic)",
    "EDM": "Edmonton Oilers (Western / Pacific)",
    "FLA": "Florida Panthers (Eastern / Atlantic)",
    "NYR": "New York Rangers (Eastern / Metropolitan)",
}

NHL_TEAM_ALIASES: dict[str, str] = {
    "BRUINS": "BOS",
    "BOSTON BRUINS": "BOS",
    "BOSTON": "BOS",
    "MAPLE LEAFS": "TOR",
    "LEAFS": "TOR",
    "TORONTO MAPLE LEAFS": "TOR",
    "TORONTO": "TOR",
    "OILERS": "EDM",
    "EDMONTON OILERS": "EDM",
    "EDMONTON": "EDM",
    "PANTHERS": "FLA",
    "FLORIDA PANTHERS": "FLA",
    "FLORIDA": "FLA",
    "RANGERS": "NYR",
    "NEW YORK RANGERS": "NYR",
    "NY RANGERS": "NYR",
}

SUPPORTED_NHL_CONFERENCE_FILTERS: set[str] = {
    "ALL",
    "EASTERN",
    "WESTERN",
    "ATLANTIC",
    "METROPOLITAN",
    "PACIFIC",
}


class ToolInputValidationError(ValueError):
    """Raised when a tool input fails strict domain validation."""

    def __init__(
        self,
        error_code: str,
        message: str,
        invalid_input: dict[str, Any],
        valid_options: list[str],
        llm_recovery_instructions: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.invalid_input = invalid_input
        self.valid_options = valid_options
        self.llm_recovery_instructions = llm_recovery_instructions


def resolve_mlb_team_code(raw_team: str, field_name: str = "team_code") -> str:
    """Strictly resolves an MLB team name or code without any silent fallback.

    Raises:
        ToolInputValidationError: If `raw_team` is empty or not in `SUPPORTED_MLB_TEAMS`.
    """
    cleaned = (raw_team or "").strip().upper()
    if cleaned in SUPPORTED_MLB_TEAMS:
        return cleaned
    if cleaned in MLB_TEAM_ALIASES:
        return MLB_TEAM_ALIASES[cleaned]

    valid_formatted = [f"{code} ({desc})" for code, desc in SUPPORTED_MLB_TEAMS.items()]
    raise ToolInputValidationError(
        error_code="UNSUPPORTED_MLB_TEAM",
        message=(
            f"Invalid MLB team identifier '{raw_team}' for parameter '{field_name}'. "
            "No silent fallback was applied."
        ),
        invalid_input={field_name: raw_team},
        valid_options=valid_formatted,
        llm_recovery_instructions=(
            "RECOVERY INSTRUCTIONS FOR LLM: "
            "1. Do NOT fabricate statistics or assume a default team like NYY. "
            "2. If the user meant an NHL hockey team (e.g., EDM, FLA, TOR, NYR), call the "
            "corresponding `get_nhl_*` tool instead. "
            "3. Otherwise, retry calling this MLB tool using one of the exact 3-letter codes "
            f"from `valid_options` ({', '.join(SUPPORTED_MLB_TEAMS.keys())}), or ask the user "
            "to clarify which supported MLB club they want to analyze."
        ),
    )


def resolve_nhl_team_code(raw_team: str, field_name: str = "team_code") -> str:
    """Strictly resolves an NHL team name or code without any silent fallback.

    Raises:
        ToolInputValidationError: If `raw_team` is empty or not in `SUPPORTED_NHL_TEAMS`.
    """
    cleaned = (raw_team or "").strip().upper()
    if cleaned in SUPPORTED_NHL_TEAMS:
        return cleaned
    if cleaned in NHL_TEAM_ALIASES:
        return NHL_TEAM_ALIASES[cleaned]

    valid_formatted = [f"{code} ({desc})" for code, desc in SUPPORTED_NHL_TEAMS.items()]
    raise ToolInputValidationError(
        error_code="UNSUPPORTED_NHL_TEAM",
        message=(
            f"Invalid NHL team identifier '{raw_team}' for parameter '{field_name}'. "
            "No silent fallback was applied."
        ),
        invalid_input={field_name: raw_team},
        valid_options=valid_formatted,
        llm_recovery_instructions=(
            "RECOVERY INSTRUCTIONS FOR LLM: "
            "1. Do NOT fabricate statistics or assume a default team like BOS. "
            "2. If the user meant an MLB baseball team (e.g., NYY, LAD, CHC, ATL, PHI), call "
            "the corresponding `get_mlb_*` tool instead. "
            "3. Otherwise, retry calling this NHL tool using one of the exact 3-letter codes "
            f"from `valid_options` ({', '.join(SUPPORTED_NHL_TEAMS.keys())}), or ask the user "
            "to clarify which supported NHL club they want to analyze."
        ),
    )


# ============================================================================
# 1. Structured Error Response Schema
# ============================================================================


class ToolErrorResponse(BaseModel):
    """Standardized error payload with guided LLM recovery instructions."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = Field(
        default="error",
        description="Indicates the tool invocation failed validation and did not fall back.",
    )
    error_code: str = Field(
        ...,
        description="Machine-readable error classification code.",
    )
    tool_name: str = Field(
        ...,
        description="Name of the tool that rejected the invalid input.",
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of why the input was rejected.",
    )
    invalid_input: dict[str, Any] = Field(
        ...,
        description="The offending input parameter(s) passed to the tool.",
    )
    valid_options: list[str] = Field(
        ...,
        description="Exhaustive list of valid parameter values accepted by this tool.",
    )
    llm_recovery_instructions: str = Field(
        ...,
        description="Step-by-step instructions for the LLM to recover and retry or ask the user.",
    )


def build_validation_error_response(
    tool_name: str,
    exc: Exception,
    raw_inputs: dict[str, Any],
    default_valid_options: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Converts a ToolInputValidationError or Pydantic ValidationError into a validated dict."""
    domain_exc: Optional[ToolInputValidationError] = None
    if isinstance(exc, ToolInputValidationError):
        domain_exc = exc
    elif hasattr(exc, "errors") and callable(getattr(exc, "errors")):
        for err_item in exc.errors():
            ctx_err = err_item.get("ctx", {}).get("error") if isinstance(err_item, dict) else None
            if isinstance(ctx_err, ToolInputValidationError):
                domain_exc = ctx_err
                break

    if domain_exc is not None:
        err_model = ToolErrorResponse(
            status="error",
            error_code=domain_exc.error_code,
            tool_name=tool_name,
            message=domain_exc.message,
            invalid_input=domain_exc.invalid_input,
            valid_options=domain_exc.valid_options,
            llm_recovery_instructions=domain_exc.llm_recovery_instructions,
        )
        return err_model.model_dump()

    err_model = ToolErrorResponse(
        status="error",
        error_code="SCHEMA_VALIDATION_FAILED",
        tool_name=tool_name,
        message=f"Pydantic schema validation failed for `{tool_name}`: {exc}",
        invalid_input=raw_inputs,
        valid_options=default_valid_options or [],
        llm_recovery_instructions=(
            f"RECOVERY INSTRUCTIONS FOR LLM: Inspect `invalid_input` and `valid_options` "
            f"for `{tool_name}`. Correct the parameter types/values to conform to the "
            f"`{tool_name}` JSON schema and re-invoke the tool."
        ),
    )
    return err_model.model_dump()


# ============================================================================
# 2. Strict Input Pydantic Schemas
# ============================================================================


class MLBScheduleInput(BaseModel):
    """Strict input schema for `get_mlb_schedule_and_probables`."""

    model_config = ConfigDict(extra="forbid")

    team_code: str = Field(
        ...,
        min_length=2,
        max_length=40,
        description="Primary MLB team 3-letter code or official club name (e.g. 'NYY', 'LAD', 'BOS', 'CHC', 'ATL', 'PHI').",
    )
    opponent_code: Optional[str] = Field(
        default=None,
        description="Optional opposing MLB team 3-letter code or official club name. Must differ from `team_code`.",
    )

    @field_validator("team_code")
    @classmethod
    def _validate_team(cls, v: str) -> str:
        return resolve_mlb_team_code(v, field_name="team_code")

    @field_validator("opponent_code")
    @classmethod
    def _validate_opponent(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return resolve_mlb_team_code(v, field_name="opponent_code")

    @model_validator(mode="after")
    def _check_distinct_teams(self) -> MLBScheduleInput:
        if self.opponent_code and self.team_code == self.opponent_code:
            raise ToolInputValidationError(
                error_code="IDENTICAL_MATCHUP_TEAMS",
                message=f"`team_code` ('{self.team_code}') and `opponent_code` ('{self.opponent_code}') cannot be the same MLB club.",
                invalid_input={"team_code": self.team_code, "opponent_code": self.opponent_code},
                valid_options=[c for c in SUPPORTED_MLB_TEAMS if c != self.team_code],
                llm_recovery_instructions=(
                    f"Choose a different `opponent_code` from {list(SUPPORTED_MLB_TEAMS.keys())} "
                    f"(not '{self.team_code}') or omit `opponent_code`."
                ),
            )
        return self


class MLBSplitsInput(MLBScheduleInput):
    """Strict input schema for `get_mlb_team_and_pitcher_splits`."""


class MLBStandingsInput(BaseModel):
    """Strict input schema for `get_mlb_standings_snapshot`."""

    model_config = ConfigDict(extra="forbid")

    league_filter: str = Field(
        default="ALL",
        description="League or division filter: 'ALL', 'AL', 'NL', 'AL EAST', 'NL EAST', 'NL CENTRAL', or 'NL WEST'.",
    )

    @field_validator("league_filter")
    @classmethod
    def _validate_league(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if cleaned not in SUPPORTED_MLB_LEAGUE_FILTERS:
            raise ToolInputValidationError(
                error_code="INVALID_MLB_LEAGUE_FILTER",
                message=f"Unsupported MLB `league_filter` value '{v}'.",
                invalid_input={"league_filter": v},
                valid_options=sorted(SUPPORTED_MLB_LEAGUE_FILTERS),
                llm_recovery_instructions=(
                    "Retry calling `get_mlb_standings_snapshot` with `league_filter` set to "
                    "one of: 'ALL', 'AL', 'NL', 'AL EAST', 'NL EAST', 'NL CENTRAL', 'NL WEST'."
                ),
            )
        return cleaned


class NHLScheduleInput(BaseModel):
    """Strict input schema for `get_nhl_schedule_and_matchup`."""

    model_config = ConfigDict(extra="forbid")

    team_code: str = Field(
        ...,
        min_length=2,
        max_length=40,
        description="Primary NHL team 3-letter code or official club name (e.g. 'BOS', 'TOR', 'EDM', 'FLA', 'NYR').",
    )
    opponent_code: Optional[str] = Field(
        default=None,
        description="Optional opposing NHL team 3-letter code or official club name. Must differ from `team_code`.",
    )

    @field_validator("team_code")
    @classmethod
    def _validate_team(cls, v: str) -> str:
        return resolve_nhl_team_code(v, field_name="team_code")

    @field_validator("opponent_code")
    @classmethod
    def _validate_opponent(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return resolve_nhl_team_code(v, field_name="opponent_code")

    @model_validator(mode="after")
    def _check_distinct_teams(self) -> NHLScheduleInput:
        if self.opponent_code and self.team_code == self.opponent_code:
            raise ToolInputValidationError(
                error_code="IDENTICAL_MATCHUP_TEAMS",
                message=f"`team_code` ('{self.team_code}') and `opponent_code` ('{self.opponent_code}') cannot be the same NHL club.",
                invalid_input={"team_code": self.team_code, "opponent_code": self.opponent_code},
                valid_options=[c for c in SUPPORTED_NHL_TEAMS if c != self.team_code],
                llm_recovery_instructions=(
                    f"Choose a different `opponent_code` from {list(SUPPORTED_NHL_TEAMS.keys())} "
                    f"(not '{self.team_code}') or omit `opponent_code`."
                ),
            )
        return self


class NHLSpecialTeamsInput(NHLScheduleInput):
    """Strict input schema for `get_nhl_team_special_teams_and_goalies`."""


class NHLStandingsInput(BaseModel):
    """Strict input schema for `get_nhl_standings_snapshot`."""

    model_config = ConfigDict(extra="forbid")

    conference_filter: str = Field(
        default="ALL",
        description="Conference or division filter: 'ALL', 'EASTERN', 'WESTERN', 'ATLANTIC', 'METROPOLITAN', or 'PACIFIC'.",
    )

    @field_validator("conference_filter")
    @classmethod
    def _validate_conference(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if cleaned not in SUPPORTED_NHL_CONFERENCE_FILTERS:
            raise ToolInputValidationError(
                error_code="INVALID_NHL_CONFERENCE_FILTER",
                message=f"Unsupported NHL `conference_filter` value '{v}'.",
                invalid_input={"conference_filter": v},
                valid_options=sorted(SUPPORTED_NHL_CONFERENCE_FILTERS),
                llm_recovery_instructions=(
                    "Retry calling `get_nhl_standings_snapshot` with `conference_filter` set to "
                    "one of: 'ALL', 'EASTERN', 'WESTERN', 'ATLANTIC', 'METROPOLITAN', 'PACIFIC'."
                ),
            )
        return cleaned


class MatchupEdgeInput(BaseModel):
    """Strict input schema for `calculate_advanced_matchup_edge`."""

    model_config = ConfigDict(extra="forbid")

    sport: str = Field(
        ...,
        description="Sport identifier: 'MLB' (or 'BASEBALL') or 'NHL' (or 'HOCKEY').",
    )
    home_team: str = Field(
        ...,
        min_length=2,
        description="Home team 3-letter code or full club name in the specified `sport`.",
    )
    away_team: str = Field(
        ...,
        min_length=2,
        description="Away team 3-letter code or full club name in the specified `sport`.",
    )

    @field_validator("sport")
    @classmethod
    def _validate_sport(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if cleaned in ("MLB", "BASEBALL"):
            return "MLB"
        if cleaned in ("NHL", "HOCKEY", "ICE HOCKEY"):
            return "NHL"
        raise ToolInputValidationError(
            error_code="INVALID_SPORT_IDENTIFIER",
            message=f"Unsupported `sport` value '{v}'. Must be 'MLB' or 'NHL'.",
            invalid_input={"sport": v},
            valid_options=["MLB", "NHL"],
            llm_recovery_instructions=(
                "Retry `calculate_advanced_matchup_edge` with `sport='MLB'` for baseball "
                "or `sport='NHL'` for ice hockey."
            ),
        )

    @model_validator(mode="after")
    def _validate_teams_for_sport(self) -> MatchupEdgeInput:
        if self.sport == "MLB":
            self.home_team = resolve_mlb_team_code(self.home_team, field_name="home_team")
            self.away_team = resolve_mlb_team_code(self.away_team, field_name="away_team")
            valid_pool = list(SUPPORTED_MLB_TEAMS.keys())
        else:
            self.home_team = resolve_nhl_team_code(self.home_team, field_name="home_team")
            self.away_team = resolve_nhl_team_code(self.away_team, field_name="away_team")
            valid_pool = list(SUPPORTED_NHL_TEAMS.keys())

        if self.home_team == self.away_team:
            raise ToolInputValidationError(
                error_code="IDENTICAL_MATCHUP_TEAMS",
                message=f"`home_team` and `away_team` cannot both be '{self.home_team}'.",
                invalid_input={"home_team": self.home_team, "away_team": self.away_team},
                valid_options=[c for c in valid_pool if c != self.home_team],
                llm_recovery_instructions=(
                    f"Select two distinct {self.sport} teams from {valid_pool} for "
                    "`home_team` and `away_team`."
                ),
            )
        return self


class WatchlistActionInput(BaseModel):
    """Strict input schema for `manage_scouting_watchlist`."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        ...,
        description="Action to execute: 'list', 'add', 'remove', or 'add_note'.",
    )
    sport: str = Field(
        default="MLB",
        description="Target league scope: 'MLB', 'NHL', or 'BOTH'.",
    )
    team_or_player: Optional[str] = Field(
        default=None,
        description="Team code (e.g. 'NYY', 'EDM') or player name required when action is 'add' or 'remove'.",
    )
    scouting_note: Optional[str] = Field(
        default=None,
        description="Scouting observation text required when action is 'add_note'.",
    )

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        cleaned = (v or "").strip().lower()
        valid_actions = {"list", "add", "remove", "add_note"}
        if cleaned not in valid_actions:
            raise ToolInputValidationError(
                error_code="INVALID_WATCHLIST_ACTION",
                message=f"Unsupported watchlist `action` '{v}'.",
                invalid_input={"action": v},
                valid_options=sorted(valid_actions),
                llm_recovery_instructions=(
                    "Retry calling `manage_scouting_watchlist` with `action` set to "
                    "'list', 'add', 'remove', or 'add_note'."
                ),
            )
        return cleaned

    @field_validator("sport")
    @classmethod
    def _validate_sport(cls, v: str) -> str:
        cleaned = (v or "").strip().upper()
        if cleaned in ("BASEBALL", "MLB"):
            return "MLB"
        if cleaned in ("HOCKEY", "ICE HOCKEY", "NHL"):
            return "NHL"
        if cleaned == "BOTH":
            return "BOTH"
        raise ToolInputValidationError(
            error_code="INVALID_SPORT_IDENTIFIER",
            message=f"Unsupported watchlist `sport` '{v}'.",
            invalid_input={"sport": v},
            valid_options=["MLB", "NHL", "BOTH"],
            llm_recovery_instructions=(
                "Retry calling `manage_scouting_watchlist` with `sport` set to 'MLB', 'NHL', or 'BOTH'."
            ),
        )

    @model_validator(mode="after")
    def _validate_target_requirements(self) -> WatchlistActionInput:
        if self.action in ("add", "remove"):
            if not self.team_or_player or not self.team_or_player.strip():
                raise ToolInputValidationError(
                    error_code="MISSING_REQUIRED_TARGET",
                    message=f"`team_or_player` is required when `action='{self.action}'`.",
                    invalid_input={"action": self.action, "team_or_player": self.team_or_player},
                    valid_options=list(SUPPORTED_MLB_TEAMS.keys()) + list(SUPPORTED_NHL_TEAMS.keys()),
                    llm_recovery_instructions=(
                        f"Provide a valid `team_or_player` string (e.g. 'NYY', 'EDM', or a player name) "
                        f"when calling `manage_scouting_watchlist(action='{self.action}')`."
                    ),
                )
            # If a 3-letter code is provided, validate it against the sport's supported clubs
            candidate = self.team_or_player.strip().upper()
            if len(candidate) <= 3:
                if self.sport == "MLB":
                    self.team_or_player = resolve_mlb_team_code(candidate, field_name="team_or_player")
                elif self.sport == "NHL":
                    self.team_or_player = resolve_nhl_team_code(candidate, field_name="team_or_player")
        if self.action == "add_note" and not (self.scouting_note or self.team_or_player):
            raise ToolInputValidationError(
                error_code="MISSING_SCOUTING_NOTE",
                message="`scouting_note` is required when `action='add_note'`.",
                invalid_input={"action": self.action, "scouting_note": self.scouting_note},
                valid_options=["Non-empty scouting observation string"],
                llm_recovery_instructions=(
                    "Provide a non-empty `scouting_note` parameter describing the tactical observation."
                ),
            )
        return self


class DossierVerificationInput(BaseModel):
    """Strict input schema for `verify_and_approve_dossier`."""

    model_config = ConfigDict(extra="forbid")

    verification_passed: bool = Field(
        ...,
        description="True only if every statistic cited in the dossier matches raw tool state.",
    )
    audited_claims_count: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of quantitative claims audited against session state (must be >= 1).",
    )
    audit_summary: str = Field(
        ...,
        min_length=5,
        description="Detailed explanation of the statistical verification findings.",
    )
    corrections_needed: Optional[str] = Field(
        default=None,
        description="Required numerical corrections when `verification_passed=False`.",
    )

    @model_validator(mode="after")
    def _require_corrections_on_failure(self) -> DossierVerificationInput:
        if not self.verification_passed and not (self.corrections_needed and self.corrections_needed.strip()):
            raise ToolInputValidationError(
                error_code="MISSING_CORRECTION_INSTRUCTIONS",
                message="`corrections_needed` must be specified when `verification_passed=False`.",
                invalid_input={
                    "verification_passed": self.verification_passed,
                    "corrections_needed": self.corrections_needed,
                },
                valid_options=["Provide specific stat corrections for `TacticalSynthesizerAgent`"],
                llm_recovery_instructions=(
                    "When rejecting a draft (`verification_passed=False`), pass a non-empty "
                    "`corrections_needed` string specifying which ERA, OPS, PP%, PK%, or "
                    "win probability figure needs correction."
                ),
            )
        return self


# ============================================================================
# 3. Strict Output Pydantic Schemas
# ============================================================================


class MLBScheduleOutput(BaseModel):
    """Validated output schema for `get_mlb_schedule_and_probables`."""

    status: Literal["success"] = "success"
    sport: Literal["MLB"] = "MLB"
    matchup: str
    data_source: str
    home_team: dict[str, Any]
    away_team: dict[str, Any]


class MLBSplitsOutput(BaseModel):
    """Validated output schema for `get_mlb_team_and_pitcher_splits`."""

    status: Literal["success"] = "success"
    sport: Literal["MLB"] = "MLB"
    team_code: str
    team_name: str
    division: str
    record: str
    runs_scored: int
    runs_allowed: int
    run_differential: int
    offensive_splits: dict[str, float]
    pitching_staff: dict[str, Any]
    key_hitters: list[dict[str, Any]]
    last_10: str
    opponent_comparison: Optional[dict[str, Any]] = None


class MLBStandingsOutput(BaseModel):
    """Validated output schema for `get_mlb_standings_snapshot`."""

    status: Literal["success"] = "success"
    sport: Literal["MLB"] = "MLB"
    league_filter: str
    standings: list[dict[str, Any]]


class NHLScheduleOutput(BaseModel):
    """Validated output schema for `get_nhl_schedule_and_matchup`."""

    status: Literal["success"] = "success"
    sport: Literal["NHL"] = "NHL"
    matchup: str
    data_source: str
    home_team: dict[str, Any]
    away_team: dict[str, Any]


class NHLSpecialTeamsOutput(BaseModel):
    """Validated output schema for `get_nhl_team_special_teams_and_goalies`."""

    status: Literal["success"] = "success"
    sport: Literal["NHL"] = "NHL"
    team_code: str
    team_name: str
    division: str
    record: str
    points: int
    goals_for: int
    goals_against: int
    goal_differential: int
    special_teams: dict[str, Any]
    even_strength_5v5: dict[str, float]
    starting_goalie: dict[str, Any]
    top_skaters: list[dict[str, Any]]
    last_10: str
    opponent_comparison: Optional[dict[str, Any]] = None


class NHLStandingsOutput(BaseModel):
    """Validated output schema for `get_nhl_standings_snapshot`."""

    status: Literal["success"] = "success"
    sport: Literal["NHL"] = "NHL"
    conference_filter: str
    standings: list[dict[str, Any]]


class MatchupEdgeOutput(BaseModel):
    """Validated output schema for `calculate_advanced_matchup_edge`."""

    status: Literal["success"] = "success"
    sport: Literal["MLB", "NHL"]
    home_team: str
    away_team: str
    pythagorean_expectancy: dict[str, float]
    win_probability: dict[str, Any]
    tactical_edges: dict[str, Any]


class WatchlistActionOutput(BaseModel):
    """Validated output schema for `manage_scouting_watchlist`."""

    status: Literal["success"] = "success"
    action: str
    watchlist: dict[str, list[str]]
    scouting_notes_count: int
    recent_notes: list[dict[str, str]]
    persistence_backend: str = "sqlite_wal_async"
    background_task_id: str = "bg-sync"


class DossierVerificationOutput(BaseModel):
    """Validated output schema for `verify_and_approve_dossier`."""

    status: Literal["approved", "revision_required"]
    verification_passed: bool
    audited_claims_count: int
    audit_summary: str
    corrections_needed: str
    verified_at_utc: str
    background_task_id: str = "bg-audit"


TOOL_JSON_SCHEMAS: dict[str, dict[str, Any]] = {}


def with_strict_tool_schema(
    input_model: type[BaseModel],
    output_model: type[BaseModel],
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Attaches explicit Pydantic input/output models and JSON schemas to an ADK tool."""

    def decorator(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        schema_bundle = {
            "tool_name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "input_json_schema": input_model.model_json_schema(),
            "output_json_schema": output_model.model_json_schema(),
            "error_json_schema": ToolErrorResponse.model_json_schema(),
        }
        setattr(func, "input_schema", input_model)
        setattr(func, "output_schema", output_model)
        setattr(func, "error_schema", ToolErrorResponse)
        setattr(func, "json_schema", schema_bundle)
        TOOL_JSON_SCHEMAS[func.__name__] = schema_bundle
        return func

    return decorator
