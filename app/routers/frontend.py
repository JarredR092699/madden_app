"""
GET routes that serve HTML pages for viewing franchise data.
"""

import json

from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path

from app.database import get_db
from app.models import (
    RawExport, Team, Standing, Player, Schedule, PlayerStat,
)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _get_team_map(db: Session, league_id: str = None) -> dict:
    """Build a dict mapping team_id -> Team for display purposes."""
    query = db.query(Team)
    if league_id:
        query = query.filter(Team.league_id == league_id)
    return {t.team_id: t for t in query.all()}


def _get_league_id(db: Session) -> str | None:
    """Get the most recently used league_id."""
    latest = db.query(RawExport).order_by(RawExport.received_at.desc()).first()
    return latest.league_id if latest else None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    league_id = _get_league_id(db)

    team_count = db.query(func.count(Team.id)).scalar()
    player_count = db.query(func.count(Player.id)).scalar()
    export_count = db.query(func.count(RawExport.id)).scalar()

    last_export = db.query(RawExport).order_by(RawExport.received_at.desc()).first()

    weeks_with_data = (
        db.query(Schedule.week_number)
        .distinct()
        .count()
    )

    return templates.TemplateResponse("index.html", {
        "request": request,
        "league_id": league_id,
        "team_count": team_count,
        "player_count": player_count,
        "export_count": export_count,
        "weeks_with_data": weeks_with_data,
        "last_export": last_export,
    })


# ── Standings ─────────────────────────────────────────────────────────────────

@router.get("/standings")
async def standings(request: Request, db: Session = Depends(get_db)):
    league_id = _get_league_id(db)
    team_map = _get_team_map(db, league_id)

    standings = (
        db.query(Standing)
        .filter(Standing.league_id == league_id) if league_id
        else db.query(Standing)
    )
    standings_list = standings.order_by(
        Standing.total_wins.desc(),
        Standing.total_losses.asc(),
    ).all()

    # Group by division (prefer standing's own conf/div names from Madden 26
    # standings JSON; fall back to team record for older data)
    divisions = {}
    for s in standings_list:
        team = team_map.get(s.team_id)
        div_name = s.division_name or (team.division_name if team else None) or "Unknown"
        conf_name = s.conference_name or (team.conference_name if team else None) or "Unknown"
        key = f"{conf_name} - {div_name}" if conf_name and div_name else (div_name or "Unknown")
        if key not in divisions:
            divisions[key] = []
        divisions[key].append({"standing": s, "team": team})

    return templates.TemplateResponse("standings.html", {
        "request": request,
        "divisions": divisions,
        "team_map": team_map,
    })


# ── Schedule ──────────────────────────────────────────────────────────────────

@router.get("/schedule")
async def schedule(
    request: Request,
    week: int = Query(None),
    db: Session = Depends(get_db),
):
    league_id = _get_league_id(db)
    team_map = _get_team_map(db, league_id)

    # Get available weeks
    weeks = (
        db.query(Schedule.week_type, Schedule.week_number)
        .distinct()
        .order_by(Schedule.week_number)
        .all()
    )

    # Filter by selected week or show the latest
    query = db.query(Schedule)
    if league_id:
        query = query.filter(Schedule.league_id == league_id)
    if week is not None:
        query = query.filter(Schedule.week_number == week)
    elif weeks:
        query = query.filter(Schedule.week_number == weeks[-1].week_number)

    games = query.order_by(Schedule.week_number).all()

    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "weeks": weeks,
        "selected_week": week,
        "games": games,
        "team_map": team_map,
    })


# ── Roster ────────────────────────────────────────────────────────────────────

@router.get("/roster")
async def roster(
    request: Request,
    team: int = Query(None),
    db: Session = Depends(get_db),
):
    league_id = _get_league_id(db)
    team_map = _get_team_map(db, league_id)

    query = db.query(Player)
    if league_id:
        query = query.filter(Player.league_id == league_id)
    if team is not None:
        query = query.filter(Player.team_id == team)

    players = query.order_by(
        Player.overall_rating.desc().nullslast(),
        Player.last_name,
    ).all()

    teams = sorted(team_map.values(), key=lambda t: t.display_name)

    return templates.TemplateResponse("roster.html", {
        "request": request,
        "players": players,
        "teams": teams,
        "selected_team": team,
        "team_map": team_map,
    })


# ── Stats ─────────────────────────────────────────────────────────────────────

STAT_COLUMNS = {
    # Confirmed from real Madden 26 export
    "passing": [
        "passAtt", "passComp", "passCompPct", "passYds", "passYdsPerAtt",
        "passTDs", "passInts", "passerRating", "passSacks",
    ],
    "rushing": [
        "rushAtt", "rushYds", "rushTDs", "rushFum", "rushLongest",
        "rushYdsAfterContact", "rushBrokenTackles",
    ],
    "receiving": [
        "recCatches", "recYds", "recTDs", "recDrops", "recLongest",
        "recYdsAfterCatch", "recCatchPct",
    ],
    "defense": [
        "defTotalTackles", "defSacks", "defInts", "defForcedFum",
        "defFumRec", "defDeflections", "defTDs",
    ],
    "kicking": [
        "fGMade", "fGAtt", "fGLongest", "xPMade", "xPAtt",
        "kickoffTBs",
    ],
    # Confirmed from real Madden 26 export
    "punting": [
        "puntAtt", "puntYds", "puntNetYds", "puntNetYdsPerAtt",
        "puntLongest", "puntsIn20", "puntTBs",
    ],
}


@router.get("/stats")
@router.get("/stats/{stat_type}")
async def stats(
    request: Request,
    stat_type: str = "passing",
    db: Session = Depends(get_db),
):
    league_id = _get_league_id(db)
    team_map = _get_team_map(db, league_id)

    query = db.query(PlayerStat).filter(PlayerStat.stat_type == stat_type)
    if league_id:
        query = query.filter(PlayerStat.league_id == league_id)

    player_stats = query.all()

    # Parse raw_json for display columns
    stat_rows = []
    columns = STAT_COLUMNS.get(stat_type, [])
    for ps in player_stats:
        raw = json.loads(ps.raw_json) if ps.raw_json else {}
        team = team_map.get(ps.team_id)
        row = {
            "name": ps.full_name or f"Player {ps.roster_id}",
            "team": team.abbr_name if team else str(ps.team_id or ""),
            "week": ps.week_number,
        }
        for col in columns:
            row[col] = raw.get(col, "")
        stat_rows.append(row)

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "stat_type": stat_type,
        "stat_types": list(STAT_COLUMNS.keys()),
        "columns": columns,
        "stat_rows": stat_rows,
        "team_map": team_map,
    })


# ── Exports Log ───────────────────────────────────────────────────────────────

@router.get("/exports")
async def exports(request: Request, db: Session = Depends(get_db)):
    raw_exports = (
        db.query(RawExport)
        .order_by(RawExport.received_at.desc())
        .limit(100)
        .all()
    )

    return templates.TemplateResponse("exports.html", {
        "request": request,
        "exports": raw_exports,
    })
