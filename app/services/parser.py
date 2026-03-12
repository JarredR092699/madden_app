"""
Extract known fields from raw Companion App JSON payloads.

Field names are based on Madden 22-25 patterns and may need adjustment
for Madden 26. All lookups use .get() so missing fields return None
instead of crashing.
"""


def parse_team(raw: dict) -> dict:
    return {
        "team_id": raw.get("teamId"),
        "city_name": raw.get("cityName"),
        "nick_name": raw.get("nickName"),
        "abbr_name": raw.get("abbrName"),
        "division_name": raw.get("divName"),
        "conference_name": raw.get("conferenceId"),
        "overall_rating": raw.get("ovrRating"),
    }


def parse_standing(raw: dict) -> dict:
    return {
        "team_id": raw.get("teamId"),
        "seed": raw.get("seed"),
        "total_wins": raw.get("totalWins"),
        "total_losses": raw.get("totalLosses"),
        "total_ties": raw.get("totalTies"),
        "div_wins": raw.get("divWins"),
        "div_losses": raw.get("divLosses"),
        "div_ties": raw.get("divTies"),
        "conf_wins": raw.get("confWins"),
        "conf_losses": raw.get("confLosses"),
        "conf_ties": raw.get("confTies"),
        "points_for": raw.get("ptsFor"),
        "points_against": raw.get("ptsAgainst"),
        "conference_name": raw.get("conferenceName"),
        "division_name": raw.get("divisionName"),
    }


def parse_player(raw: dict) -> dict:
    return {
        "roster_id": raw.get("rosterId"),
        "first_name": raw.get("firstName"),
        "last_name": raw.get("lastName"),
        "position": raw.get("position"),
        "overall_rating": raw.get("playerBestOvr", raw.get("overallRating")),
        "age": raw.get("age"),
        "jersey_num": raw.get("jerseyNum"),
        "height": raw.get("height"),
        "weight": raw.get("weight"),
        "college": raw.get("college"),
        "years_pro": raw.get("yearsPro"),
        "dev_trait": raw.get("devTrait"),
        "portrait_id": raw.get("portraitId"),
    }


_SCHEDULE_STATUS = {1: "Scheduled", 2: "In Progress", 3: "Final"}


def parse_schedule(raw: dict) -> dict:
    raw_status = raw.get("status")
    return {
        "home_team_id": raw.get("homeTeamId"),
        "away_team_id": raw.get("awayTeamId"),
        "home_score": raw.get("homeScore"),
        "away_score": raw.get("awayScore"),
        "status": _SCHEDULE_STATUS.get(raw_status, str(raw_status) if raw_status is not None else None),
    }


def parse_player_stat(raw: dict) -> dict:
    return {
        "roster_id": raw.get("rosterId"),
        "full_name": raw.get("fullName"),
        "team_id": raw.get("teamId"),
    }


def parse_team_stat(raw: dict) -> dict:
    return {
        "team_id": raw.get("teamId"),
    }
