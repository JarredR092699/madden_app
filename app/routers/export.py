"""
POST endpoints that receive JSON data from the Madden Companion App.

The Companion App appends path segments to the base URL you provide.
Every endpoint saves the raw JSON to disk and parses known fields into the DB.
"""

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.database import get_db
from app.models import (
    RawExport, Team, Standing, Player, Schedule,
    PlayerStat, TeamStat,
)
from app.services.parser import (
    parse_team, parse_standing, parse_player,
    parse_schedule, parse_player_stat, parse_team_stat,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _save_raw(league_id: str, data_type: str, body: dict):
    """Save raw JSON to disk as a backup."""
    league_dir = os.path.join(DATA_DIR, league_id)
    os.makedirs(league_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{data_type}_{ts}.json"
    filepath = os.path.join(league_dir, filename)
    with open(filepath, "w") as f:
        json.dump(body, f, indent=2)
    return filepath


def _log_export(db: Session, endpoint: str, platform: str,
                league_id: str, data_type: str, body: dict):
    """Log every incoming POST to the raw_exports table."""
    record = RawExport(
        endpoint=endpoint,
        platform=platform,
        league_id=league_id,
        data_type=data_type,
        raw_json=json.dumps(body),
    )
    db.add(record)
    db.commit()


def _upsert(db: Session, model, unique_fields: dict, update_fields: dict):
    """Insert or update a row based on unique field values."""
    existing = db.query(model).filter_by(**unique_fields).first()
    if existing:
        for key, value in update_fields.items():
            if value is not None:
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        return existing
    else:
        row = model(**unique_fields, **update_fields)
        db.add(row)
        db.commit()
        return row


# ── League Teams ──────────────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/leagueteams")
async def receive_league_teams(
    platform: str, league_id: str, request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, "leagueteams", body)
    _log_export(db, request.url.path, platform, league_id, "leagueteams", body)

    teams_list = body.get("leagueTeamInfoList", [])
    count = 0
    for raw_team in teams_list:
        parsed = parse_team(raw_team)
        team_id = parsed.pop("team_id", None)
        if team_id is None:
            continue
        _upsert(
            db, Team,
            unique_fields={"league_id": league_id, "team_id": team_id},
            update_fields={**parsed, "raw_json": json.dumps(raw_team)},
        )
        count += 1

    return {"status": "ok", "teams_imported": count}


# ── Standings ─────────────────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/standings")
async def receive_standings(
    platform: str, league_id: str, request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, "standings", body)
    _log_export(db, request.url.path, platform, league_id, "standings", body)

    standings_list = body.get("teamStandingInfoList", [])
    count = 0
    for raw_standing in standings_list:
        parsed = parse_standing(raw_standing)
        team_id = parsed.pop("team_id", None)
        if team_id is None:
            continue
        _upsert(
            db, Standing,
            unique_fields={"league_id": league_id, "team_id": team_id},
            update_fields={**parsed, "raw_json": json.dumps(raw_standing)},
        )
        count += 1

    return {"status": "ok", "standings_imported": count}


# ── Rosters (per team) ───────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/team/{team_id}/roster")
async def receive_team_roster(
    platform: str, league_id: str, team_id: int,
    request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, f"roster_team{team_id}", body)
    _log_export(db, request.url.path, platform, league_id, f"roster_team{team_id}", body)

    roster_list = body.get("rosterInfoList", [])
    count = 0
    for raw_player in roster_list:
        parsed = parse_player(raw_player)
        roster_id = parsed.pop("roster_id", None)
        if roster_id is None:
            continue
        _upsert(
            db, Player,
            unique_fields={"league_id": league_id, "roster_id": roster_id},
            update_fields={
                **parsed,
                "team_id": team_id,
                "raw_json": json.dumps(raw_player),
            },
        )
        count += 1

    return {"status": "ok", "players_imported": count}


# ── Free Agents ───────────────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/freeagents/roster")
async def receive_free_agents(
    platform: str, league_id: str, request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, "freeagents", body)
    _log_export(db, request.url.path, platform, league_id, "freeagents", body)

    roster_list = body.get("rosterInfoList", [])
    count = 0
    for raw_player in roster_list:
        parsed = parse_player(raw_player)
        roster_id = parsed.pop("roster_id", None)
        if roster_id is None:
            continue
        _upsert(
            db, Player,
            unique_fields={"league_id": league_id, "roster_id": roster_id},
            update_fields={
                **parsed,
                "team_id": -1,
                "raw_json": json.dumps(raw_player),
            },
        )
        count += 1

    return {"status": "ok", "free_agents_imported": count}


# ── Schedules ─────────────────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/week/{week_type}/{week_number}/schedules")
async def receive_schedules(
    platform: str, league_id: str, week_type: str, week_number: int,
    request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, f"schedules_{week_type}_wk{week_number}", body)
    _log_export(db, request.url.path, platform, league_id,
                f"schedules_{week_type}_wk{week_number}", body)

    schedule_list = body.get("gameScheduleInfoList", [])
    count = 0
    for raw_game in schedule_list:
        parsed = parse_schedule(raw_game)
        home_id = parsed.get("home_team_id")
        away_id = parsed.get("away_team_id")
        if home_id is None or away_id is None:
            continue
        _upsert(
            db, Schedule,
            unique_fields={
                "league_id": league_id,
                "week_type": week_type,
                "week_number": week_number,
                "home_team_id": home_id,
                "away_team_id": away_id,
            },
            update_fields={
                "home_score": parsed.get("home_score"),
                "away_score": parsed.get("away_score"),
                "status": parsed.get("status"),
                "raw_json": json.dumps(raw_game),
            },
        )
        count += 1

    return {"status": "ok", "games_imported": count}


# ── Team Stats ────────────────────────────────────────────────────────────────

@router.post("/{platform}/{league_id}/week/{week_type}/{week_number}/teamstats")
async def receive_team_stats(
    platform: str, league_id: str, week_type: str, week_number: int,
    request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, f"teamstats_{week_type}_wk{week_number}", body)
    _log_export(db, request.url.path, platform, league_id,
                f"teamstats_{week_type}_wk{week_number}", body)

    stats_list = body.get("teamStatInfoList", [])
    count = 0
    for raw_stat in stats_list:
        parsed = parse_team_stat(raw_stat)
        team_id = parsed.get("team_id")
        if team_id is None:
            continue
        _upsert(
            db, TeamStat,
            unique_fields={
                "league_id": league_id,
                "week_type": week_type,
                "week_number": week_number,
                "team_id": team_id,
            },
            update_fields={"raw_json": json.dumps(raw_stat)},
        )
        count += 1

    return {"status": "ok", "team_stats_imported": count}


# ── Player Stats (passing, rushing, receiving, defense, kicking, punting) ────

STAT_TYPE_BODY_KEYS = {
    "passing": "playerPassingStatInfoList",
    "rushing": "playerRushingStatInfoList",
    "receiving": "playerReceivingStatInfoList",
    "defense": "playerDefensiveStatInfoList",
    "kicking": "playerKickingStatInfoList",
    "punting": "playerPuntingStatInfoList",
}


@router.post("/{platform}/{league_id}/week/{week_type}/{week_number}/{stat_type}")
async def receive_player_stats(
    platform: str, league_id: str, week_type: str, week_number: int,
    stat_type: str, request: Request, db: Session = Depends(get_db)
):
    body = await request.json()
    _save_raw(league_id, f"{stat_type}_{week_type}_wk{week_number}", body)
    _log_export(db, request.url.path, platform, league_id,
                f"{stat_type}_{week_type}_wk{week_number}", body)

    body_key = STAT_TYPE_BODY_KEYS.get(stat_type)
    if body_key is None:
        # Unknown stat type -- try common patterns
        for key in body:
            if isinstance(body[key], list):
                body_key = key
                break

    stats_list = body.get(body_key, []) if body_key else []
    count = 0
    for raw_stat in stats_list:
        parsed = parse_player_stat(raw_stat)
        roster_id = parsed.get("roster_id")
        if roster_id is None:
            continue
        _upsert(
            db, PlayerStat,
            unique_fields={
                "league_id": league_id,
                "week_type": week_type,
                "week_number": week_number,
                "stat_type": stat_type,
                "roster_id": roster_id,
            },
            update_fields={
                "full_name": parsed.get("full_name"),
                "team_id": parsed.get("team_id"),
                "raw_json": json.dumps(raw_stat),
            },
        )
        count += 1

    return {"status": "ok", "stat_type": stat_type, "stats_imported": count}


# ── Catch-all for unexpected endpoints ────────────────────────────────────────

@router.post("/{path:path}")
async def catch_all(path: str, request: Request, db: Session = Depends(get_db)):
    """Log any POST that doesn't match a known route."""
    try:
        body = await request.json()
    except Exception:
        body = {"_raw_body": (await request.body()).decode("utf-8", errors="replace")}

    logger.warning(f"Unknown POST endpoint: /{path}")
    _save_raw("_unknown", path.replace("/", "_"), body)
    _log_export(db, request.url.path, "", "", f"unknown_{path}", body)

    return {"status": "ok", "message": f"Received unknown endpoint: /{path}"}
