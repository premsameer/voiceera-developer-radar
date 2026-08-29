from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utcnow(): return datetime.now(timezone.utc)


class Verdict(str, Enum): PASS = "PASS"; UNSURE = "UNSURE"; FAIL = "FAIL"
class Route(str, Enum): USE_CASE = "USE_CASE"; INTEGRATION = "INTEGRATION"; ISSUE = "ISSUE"; GENERAL_INTRO = "GENERAL_INTRO"; MONITOR = "MONITOR"
class Intent(str, Enum):
    BUILDING="BUILDING"; INTEGRATING="INTEGRATING"; EVALUATING="EVALUATING"; TROUBLESHOOTING="TROUBLESHOOTING"; CONTRIBUTING="CONTRIBUTING"; LAUNCHING="LAUNCHING"; LEARNING="LEARNING"; RESEARCHING="RESEARCHING"; COMMUNITY_DISCUSSION="COMMUNITY_DISCUSSION"; UNKNOWN="UNKNOWN"


class Connector(Base):
    __tablename__ = "source_connectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_cursor: Mapped[str | None]
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    items_collected: Mapped[int] = mapped_column(default=0)


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    source_counts_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(default="rules-v1")


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[int] = mapped_column(primary_key=True)
    github_node_id: Mapped[str | None] = mapped_column(unique=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    url: Mapped[str]; description: Mapped[str | None] = mapped_column(Text)
    topics_json: Mapped[list] = mapped_column(JSON, default=list)
    languages_json: Mapped[list] = mapped_column(JSON, default=list)
    stars: Mapped[int] = mapped_column(default=0)
    fork: Mapped[bool] = mapped_column(default=False); archived: Mapped[bool] = mapped_column(default=False)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); discovery_query: Mapped[str | None]


class Developer(Base):
    __tablename__ = "developers"
    id: Mapped[int] = mapped_column(primary_key=True)
    primary_source: Mapped[str]; primary_handle: Mapped[str]
    display_name: Mapped[str | None]; profile_url: Mapped[str | None]
    public_links_json: Mapped[dict] = mapped_column(JSON, default=dict)
    segment: Mapped[str | None]; latest_observed_intent: Mapped[str] = mapped_column(default="UNKNOWN")
    latest_intent_evidence: Mapped[str | None] = mapped_column(Text)
    latest_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    funnel_stage: Mapped[str] = mapped_column(default="DISCOVERED")
    signals: Mapped[list["Signal"]] = relationship(back_populates="developer", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("primary_source", "primary_handle"),)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]; external_id: Mapped[str]; canonical_url: Mapped[str]
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id"))
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"))
    activity_type: Mapped[str]; title: Mapped[str]; excerpt: Mapped[str] = mapped_column(Text)
    activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_intent: Mapped[str] = mapped_column(default="UNKNOWN")
    intent_evidence: Mapped[str] = mapped_column(Text)
    raw_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(index=True)
    developer: Mapped[Developer] = relationship(back_populates="signals")
    repository: Mapped[Repository | None] = relationship()
    evaluation: Mapped["Evaluation | None"] = relationship(back_populates="signal", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("source", "external_id"), UniqueConstraint("canonical_url"))


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True); title: Mapped[str]; activation_type: Mapped[str]
    description: Mapped[str] = mapped_column(Text); required_topics_json: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str]; url: Mapped[str]; owner: Mapped[str]; active: Mapped[bool] = mapped_column(default=True)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), unique=True)
    rule_score: Mapped[int]; verdict: Mapped[str]; segment: Mapped[str]
    observed_intent: Mapped[str]; intent_evidence: Mapped[str] = mapped_column(Text)
    proof_quote: Mapped[str | None] = mapped_column(Text); proof_url: Mapped[str]; proof_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text); confidence: Mapped[float] = mapped_column(Float, default=1.0)
    recommended_route: Mapped[str]; matched_opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"))
    draft_text: Mapped[str | None] = mapped_column(Text); model: Mapped[str] = mapped_column(default="rules-only"); prompt_version: Mapped[str] = mapped_column(default="rules-v1")
    signal: Mapped[Signal] = relationship(back_populates="evaluation"); opportunity: Mapped[Opportunity | None] = relationship()
    reviews: Mapped[list["ReviewAction"]] = relationship(cascade="all, delete-orphan")


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"))
    action: Mapped[str]; draft_text: Mapped[str | None] = mapped_column(Text); edited_text: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(default="admin"); notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
