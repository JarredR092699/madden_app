"""
GET routes that serve HTML pages for viewing franchise data.
"""

import json

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse
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

# Columns where MAX is more meaningful than SUM in season aggregation
_MAX_COLUMNS = {"rushLongest", "recLongest", "fGLongest", "puntLongest"}

# Columns that are derived (recalculated after summing base components)
_DERIVED_COLUMNS = {"passCompPct", "passYdsPerAtt", "passerRating",
                    "recCatchPct", "puntNetYdsPerAtt"}


def _recalculate_derived(agg: dict):
    """Recalculate percentage/average columns from summed base stats."""
    att = agg.get("passAtt", 0)
    if att:
        comp = agg.get("passComp", 0)
        yds = agg.get("passYds", 0)
        tds = agg.get("passTDs", 0)
        ints = agg.get("passInts", 0)
        agg["passCompPct"] = round(comp / att * 100, 1)
        agg["passYdsPerAtt"] = round(yds / att, 1)
        # NFL passer rating formula
        a = min(max(((comp / att) - 0.3) * 5, 0), 2.375)
        b = min(max(((yds / att) - 3) * 0.25, 0), 2.375)
        c = min(max((tds / att) * 20, 0), 2.375)
        d = min(max(2.375 - ((ints / att) * 25), 0), 2.375)
        agg["passerRating"] = round((a + b + c + d) / 6 * 100, 1)

    punt_att = agg.get("puntAtt", 0)
    if punt_att:
        agg["puntNetYdsPerAtt"] = round(agg.get("puntNetYds", 0) / punt_att, 1)

    # recCatchPct needs targets which we may not have — leave as-is if not calculable


def _aggregate_season(player_stats, columns, team_map):
    """Aggregate per-week stats into season totals by player."""
    from collections import defaultdict
    grouped = defaultdict(list)
    for ps in player_stats:
        grouped[ps.roster_id].append(ps)

    rows = []
    for roster_id, entries in grouped.items():
        first = entries[0]
        team = team_map.get(first.team_id)
        agg = {
            "name": first.full_name or f"Player {roster_id}",
            "team": team.abbr_name if team else str(first.team_id or ""),
            "week": "SZN",
            "roster_id": roster_id,
            "portrait_url": None,
        }
        # Sum/max across weeks
        for col in columns:
            if col in _DERIVED_COLUMNS:
                continue  # recalculated below
            vals = []
            for ps in entries:
                raw = json.loads(ps.raw_json) if ps.raw_json else {}
                v = raw.get(col)
                if v is not None and v != "":
                    try:
                        vals.append(float(v))
                    except (ValueError, TypeError):
                        pass
            if vals:
                agg[col] = int(max(vals)) if col in _MAX_COLUMNS else int(sum(vals))
            else:
                agg[col] = ""

        _recalculate_derived(agg)

        # Fill any remaining derived columns that weren't recalculated
        for col in columns:
            if col not in agg:
                agg[col] = "-"

        rows.append(agg)

    return rows


@router.get("/stats")
@router.get("/stats/{stat_type}")
async def stats(
    request: Request,
    stat_type: str = "passing",
    week: str = Query("season"),
    db: Session = Depends(get_db),
):
    league_id = _get_league_id(db)
    team_map = _get_team_map(db, league_id)

    # Build player map for headshot URLs
    player_map = {}
    if league_id:
        players = db.query(Player).filter(Player.league_id == league_id).all()
        player_map = {p.roster_id: p for p in players}

    # Get available weeks for this stat type
    week_query = (
        db.query(PlayerStat.week_type, PlayerStat.week_number)
        .filter(PlayerStat.stat_type == stat_type)
    )
    if league_id:
        week_query = week_query.filter(PlayerStat.league_id == league_id)
    weeks = week_query.distinct().order_by(PlayerStat.week_number).all()

    # Query stats
    query = db.query(PlayerStat).filter(PlayerStat.stat_type == stat_type)
    if league_id:
        query = query.filter(PlayerStat.league_id == league_id)

    is_season = week == "season"
    if not is_season:
        try:
            week_num = int(week)
            query = query.filter(PlayerStat.week_number == week_num)
        except ValueError:
            is_season = True

    player_stats = query.all()
    columns = STAT_COLUMNS.get(stat_type, [])

    if is_season and len(weeks) > 1:
        stat_rows = _aggregate_season(player_stats, columns, team_map)
    else:
        stat_rows = []
        for ps in player_stats:
            raw = json.loads(ps.raw_json) if ps.raw_json else {}
            team = team_map.get(ps.team_id)
            row = {
                "name": ps.full_name or f"Player {ps.roster_id}",
                "team": team.abbr_name if team else str(ps.team_id or ""),
                "week": ps.week_number,
                "roster_id": ps.roster_id,
                "portrait_url": None,
            }
            for col in columns:
                row[col] = raw.get(col, "")
            stat_rows.append(row)

    # Attach portrait URLs
    for row in stat_rows:
        player = player_map.get(row.get("roster_id"))
        if player:
            row["portrait_url"] = player.portrait_url

    # Sort by primary stat column descending (first column that looks like a total)
    sort_col = columns[0] if columns else None
    if sort_col:
        stat_rows.sort(
            key=lambda r: (float(r.get(sort_col, 0)) if r.get(sort_col, "") != "" else 0),
            reverse=True,
        )

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "stat_type": stat_type,
        "stat_types": list(STAT_COLUMNS.keys()),
        "columns": columns,
        "stat_rows": stat_rows,
        "team_map": team_map,
        "weeks": weeks,
        "selected_week": week,
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


# ── Player Detail API ────────────────────────────────────────────────────────

DEV_TRAIT_MAP = {0: "Normal", 1: "Star", 2: "Superstar", 3: "X-Factor"}


def _format_height(inches):
    """Convert height in inches to feet'inches\" format."""
    if inches is None:
        return "-"
    feet = inches // 12
    remaining = inches % 12
    return f"{feet}'{remaining}\""


def _get_key_ratings(position: str, raw: dict) -> list:
    """Return position-relevant ratings as list of {label, value} dicts."""
    position = (position or "").upper()

    qb_ratings = [
        ("Throw Power", "throwPowerRating"),
        ("Short Acc", "throwAccShortRating"),
        ("Med Acc", "throwAccMidRating"),
        ("Deep Acc", "throwAccDeepRating"),
        ("Throw on Run", "throwOnRunRating"),
        ("Under Pressure", "throwUnderPressureRating"),
        ("Speed", "speedRating"),
        ("Break Sack", "breakSackRating"),
    ]

    hb_ratings = [
        ("Speed", "speedRating"),
        ("Acceleration", "accelRating"),
        ("Agility", "agilityRating"),
        ("Carrying", "carryRating"),
        ("Juke Move", "jukeMoveRating"),
        ("Break Tackle", "breakTackleRating"),
        ("Trucking", "truckRating"),
        ("Catching", "catchRating"),
    ]

    wr_te_ratings = [
        ("Speed", "speedRating"),
        ("Acceleration", "accelRating"),
        ("Catching", "catchRating"),
        ("Spec Catch", "specCatchRating"),
        ("CIT", "cITRating"),
        ("Short Route", "routeRunShortRating"),
        ("Med Route", "routeRunMedRating"),
        ("Deep Route", "routeRunDeepRating"),
    ]

    ol_ratings = [
        ("Pass Block", "passBlockRating"),
        ("Run Block", "runBlockRating"),
        ("Impact Block", "impactBlockRating"),
        ("Strength", "strengthRating"),
        ("Awareness", "awarenessRating"),
    ]

    dl_ratings = [
        ("Block Shed", "blockShedRating"),
        ("Tackle", "tackleRating"),
        ("Power Moves", "powerMovesRating"),
        ("Finesse Moves", "finesseMovesRating"),
        ("Speed", "speedRating"),
        ("Strength", "strengthRating"),
        ("Pursuit", "pursuitRating"),
    ]

    lb_ratings = [
        ("Tackle", "tackleRating"),
        ("Block Shed", "blockShedRating"),
        ("Pursuit", "pursuitRating"),
        ("Speed", "speedRating"),
        ("Zone Coverage", "zoneCovRating"),
        ("Man Coverage", "manCovRating"),
        ("Hit Power", "hitPowerRating"),
        ("Play Recognition", "playRecRating"),
    ]

    db_ratings = [
        ("Speed", "speedRating"),
        ("Acceleration", "accelRating"),
        ("Man Coverage", "manCovRating"),
        ("Zone Coverage", "zoneCovRating"),
        ("Press", "pressRating"),
        ("Play Recognition", "playRecRating"),
        ("Catching", "catchRating"),
    ]

    k_p_ratings = [
        ("Kick Power", "kickPowerRating"),
        ("Kick Accuracy", "kickAccRating"),
        ("Awareness", "awarenessRating"),
    ]

    default_ratings = [
        ("Speed", "speedRating"),
        ("Acceleration", "accelRating"),
        ("Agility", "agilityRating"),
        ("Strength", "strengthRating"),
        ("Awareness", "awarenessRating"),
    ]

    rating_map = {
        "QB": qb_ratings,
        "HB": hb_ratings,
        "FB": hb_ratings,
        "WR": wr_te_ratings,
        "TE": wr_te_ratings,
        "LT": ol_ratings, "LG": ol_ratings, "C": ol_ratings,
        "RG": ol_ratings, "RT": ol_ratings,
        "LE": dl_ratings, "RE": dl_ratings, "DT": dl_ratings,
        "LOLB": lb_ratings, "MLB": lb_ratings, "ROLB": lb_ratings,
        "CB": db_ratings, "FS": db_ratings, "SS": db_ratings,
        "K": k_p_ratings, "P": k_p_ratings,
    }

    selected = rating_map.get(position, default_ratings)
    result = []
    for label, key in selected:
        val = raw.get(key)
        if val is not None:
            result.append({"label": label, "value": val})
    return result


@router.get("/api/player/{roster_id}")
async def player_detail_api(
    roster_id: int,
    db: Session = Depends(get_db),
):
    league_id = _get_league_id(db)
    player = db.query(Player).filter(
        Player.league_id == league_id,
        Player.roster_id == roster_id,
    ).first()

    if not player:
        return JSONResponse({"error": "Player not found"}, status_code=404)

    team_map = _get_team_map(db, league_id)
    team = team_map.get(player.team_id)

    raw = json.loads(player.raw_json) if player.raw_json else {}

    # Dev trait: model stores as String, try to map int->name
    dev_raw = player.dev_trait
    try:
        dev_display = DEV_TRAIT_MAP.get(int(dev_raw), dev_raw)
    except (TypeError, ValueError):
        dev_display = dev_raw if dev_raw else "-"

    # Bio
    bio = {
        "name": player.full_name,
        "position": player.position or raw.get("position", "-"),
        "overall": player.overall_rating,
        "age": player.age,
        "height": _format_height(player.height),
        "weight": player.weight,
        "college": player.college or "-",
        "years_pro": player.years_pro,
        "jersey_num": player.jersey_num,
        "dev_trait": dev_display,
        "team_name": team.display_name if team else "-",
        "team_abbr": team.abbr_name if team else "-",
        "portrait_url": player.portrait_url,
    }

    # Key ratings
    ratings = _get_key_ratings(player.position, raw)

    # Contract info
    contract = {
        "salary": raw.get("contractSalary"),
        "bonus": raw.get("contractBonus"),
        "cap_hit": raw.get("capHit"),
        "years_left": raw.get("contractYearsLeft"),
        "cap_release_penalty": raw.get("capReleasePenalty"),
    }

    # Season stats - get all stat entries for this player
    player_stats = db.query(PlayerStat).filter(
        PlayerStat.league_id == league_id,
        PlayerStat.roster_id == roster_id,
    ).order_by(PlayerStat.stat_type, PlayerStat.week_number).all()

    stats_by_type = {}
    for ps in player_stats:
        if ps.stat_type not in stats_by_type:
            stats_by_type[ps.stat_type] = []
        raw_stat = json.loads(ps.raw_json) if ps.raw_json else {}
        entry = {"week": ps.week_number}
        columns = STAT_COLUMNS.get(ps.stat_type, [])
        for col in columns:
            entry[col] = raw_stat.get(col, "-")
        stats_by_type[ps.stat_type].append(entry)

    return JSONResponse({
        "bio": bio,
        "ratings": ratings,
        "contract": contract,
        "stats": stats_by_type,
    })
