from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class RawExport(Base):
    __tablename__ = "raw_exports"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String, nullable=False)
    platform = Column(String)
    league_id = Column(String)
    data_type = Column(String)
    raw_json = Column(Text, nullable=False)
    received_at = Column(DateTime, default=utcnow)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    team_id = Column(Integer, nullable=False)
    city_name = Column(String)
    nick_name = Column(String)
    abbr_name = Column(String)
    division_name = Column(String)
    conference_name = Column(String)
    overall_rating = Column(Integer)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("league_id", "team_id", name="uq_team"),
    )

    @property
    def display_name(self):
        if self.city_name and self.nick_name:
            return f"{self.city_name} {self.nick_name}"
        return self.abbr_name or f"Team {self.team_id}"


class Standing(Base):
    __tablename__ = "standings"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    team_id = Column(Integer, nullable=False)
    seed = Column(Integer)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    total_ties = Column(Integer, default=0)
    div_wins = Column(Integer, default=0)
    div_losses = Column(Integer, default=0)
    div_ties = Column(Integer, default=0)
    conf_wins = Column(Integer, default=0)
    conf_losses = Column(Integer, default=0)
    conf_ties = Column(Integer, default=0)
    points_for = Column(Integer, default=0)
    points_against = Column(Integer, default=0)
    conference_name = Column(String)
    division_name = Column(String)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("league_id", "team_id", name="uq_standing"),
    )

    @property
    def record(self):
        parts = [str(self.total_wins or 0), str(self.total_losses or 0)]
        if self.total_ties:
            parts.append(str(self.total_ties))
        return "-".join(parts)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    team_id = Column(Integer)
    roster_id = Column(Integer, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    position = Column(String)
    overall_rating = Column(Integer)
    age = Column(Integer)
    jersey_num = Column(Integer)
    height = Column(Integer)
    weight = Column(Integer)
    college = Column(String)
    years_pro = Column(Integer)
    dev_trait = Column(String)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("league_id", "roster_id", name="uq_player"),
    )

    @property
    def full_name(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else f"Player {self.roster_id}"


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    week_type = Column(String)
    week_number = Column(Integer)
    home_team_id = Column(Integer)
    away_team_id = Column(Integer)
    home_score = Column(Integer)
    away_score = Column(Integer)
    status = Column(String)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "league_id", "week_type", "week_number",
            "home_team_id", "away_team_id",
            name="uq_schedule",
        ),
    )


class PlayerStat(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    week_type = Column(String)
    week_number = Column(Integer)
    stat_type = Column(String, nullable=False)
    roster_id = Column(Integer)
    full_name = Column(String)
    team_id = Column(Integer)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "league_id", "week_type", "week_number",
            "stat_type", "roster_id",
            name="uq_player_stat",
        ),
    )


class TeamStat(Base):
    __tablename__ = "team_stats"

    id = Column(Integer, primary_key=True, index=True)
    league_id = Column(String, nullable=False)
    week_type = Column(String)
    week_number = Column(Integer)
    team_id = Column(Integer, nullable=False)
    raw_json = Column(Text)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "league_id", "week_type", "week_number", "team_id",
            name="uq_team_stat",
        ),
    )
