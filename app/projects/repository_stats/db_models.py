from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import db


class RepositoryStatsVisibilitySnapshot(db.Model):
    __tablename__ = "repository_stats_visibility_snapshots"
    __table_args__ = (
        db.UniqueConstraint(
            "github_id",
            "captured_on",
            name="uq_repository_stats_visibility_snapshots_github_id_captured_on",
        ),
        db.Index("ix_repository_stats_visibility_snapshots_captured_on", "captured_on"),
    )

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    # Any GitHub Enterprise organisation, e.g. "ministryofjustice" or "moj-analytical-services".
    org: Mapped[str] = mapped_column(db.String, nullable=False)
    name: Mapped[str] = mapped_column(db.String, nullable=False)
    visibility: Mapped[str] = mapped_column(db.String, nullable=False)
    archived: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    fork: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    created_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    captured_on: Mapped[date] = mapped_column(db.Date, nullable=False)

    def __repr__(self):
        return f"<RepositoryStatsVisibilitySnapshot id={self.id}, name={self.name}, captured_on={self.captured_on}>"


class RepositoryStatsVisibilityEvent(db.Model):
    __tablename__ = "repository_stats_visibility_events"
    __table_args__ = (
        db.Index("ix_repository_stats_visibility_events_occurred_on", "occurred_on"),
        db.Index("ix_repository_stats_visibility_events_event_type", "event_type"),
        db.Index("ix_repository_stats_visibility_events_name", "name"),
    )

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    org: Mapped[str] = mapped_column(db.String, nullable=False)
    name: Mapped[str] = mapped_column(db.String, nullable=False)
    # One of: changed, created, deleted, archived
    event_type: Mapped[str] = mapped_column(db.String, nullable=False)
    from_visibility: Mapped[str | None] = mapped_column(db.String, nullable=True)
    to_visibility: Mapped[str | None] = mapped_column(db.String, nullable=True)
    occurred_on: Mapped[date] = mapped_column(db.Date, nullable=False)
    actor: Mapped[str | None] = mapped_column(db.String, nullable=True)
    # One of: scan, audit_log, import
    source: Mapped[str] = mapped_column(db.String, nullable=False)

    def __repr__(self):
        return f"<RepositoryStatsVisibilityEvent id={self.id}, name={self.name}, event_type={self.event_type}>"


class RepositoryStatsJobRun(db.Model):
    """One row per run of a Repository Stats data-collection job.

    The pages show the finish time of the latest successful run as "Last updated".
    Times are stored in UTC. org is empty when one run covers every configured organisation.
    """

    __tablename__ = "repository_stats_job_runs"
    __table_args__ = (
        db.Index(
            "ix_repository_stats_job_runs_job_name_status_finished_at",
            "job_name",
            "status",
            "finished_at",
        ),
    )

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(db.String, nullable=False)
    org: Mapped[str | None] = mapped_column(db.String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        db.DateTime(timezone=True), nullable=True
    )
    # One of: running, success, failed
    status: Mapped[str] = mapped_column(db.String, nullable=False)

    def __repr__(self):
        return f"<RepositoryStatsJobRun id={self.id}, job_name={self.job_name}, status={self.status}>"


class RepositoryStatsTeamAccess(db.Model):
    """Which teams can access each repository, as of the latest successful scan.

    Written by the record_repository_visibility job, which replaces an organisation's
    rows on each run. github_id matches repository_stats_visibility_snapshots.github_id.
    """

    __tablename__ = "repository_stats_team_access"
    __table_args__ = (
        db.UniqueConstraint(
            "org",
            "github_id",
            "team_slug",
            name="uq_repository_stats_team_access_org_github_id_team_slug",
        ),
        db.Index("ix_repository_stats_team_access_github_id", "github_id"),
    )

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    org: Mapped[str] = mapped_column(db.String, nullable=False)
    github_id: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    team_slug: Mapped[str] = mapped_column(db.String, nullable=False)
    team_name: Mapped[str] = mapped_column(db.String, nullable=False)
    # The parent team's slug, for nested teams.
    parent_team_slug: Mapped[str | None] = mapped_column(db.String, nullable=True)
    # GitHub's role name: admin, maintain, write, triage, read or a custom role.
    permission: Mapped[str] = mapped_column(db.String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False
    )

    def __repr__(self):
        return f"<RepositoryStatsTeamAccess id={self.id}, github_id={self.github_id}, team_slug={self.team_slug}>"


class RepositoryStatsOrganisation(db.Model):
    """GitHub organisation details, recorded by the record_repository_visibility job.

    display_name is the organisation's profile name (GET /orgs/{org} "name"), or None
    if it has none; pages show the login then.
    """

    __tablename__ = "repository_stats_organisations"

    login: Mapped[str] = mapped_column(db.String, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(db.String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), nullable=False
    )

    def __repr__(self):
        return f"<RepositoryStatsOrganisation login={self.login}>"
