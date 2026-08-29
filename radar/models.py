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
    github_user_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    primary_source: Mapped[str]; primary_handle: Mapped[str]
    display_name: Mapped[str | None]; profile_url: Mapped[str | None]
    public_links_json: Mapped[dict] = mapped_column(JSON, default=dict)
    segment: Mapped[str | None]; latest_observed_intent: Mapped[str] = mapped_column(default="UNKNOWN")
    latest_intent_evidence: Mapped[str | None] = mapped_column(Text)
    latest_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    funnel_stage: Mapped[str] = mapped_column(default="DISCOVERED")
    primary_segment_code: Mapped[str] = mapped_column(default="UNKNOWN_DEVELOPER")
    intent_strength: Mapped[int] = mapped_column(default=0)
    current_funnel_stage: Mapped[str] = mapped_column(default="DISCOVERED")
    next_best_action: Mapped[str] = mapped_column(default="MONITOR")
    next_action_reason: Mapped[str | None] = mapped_column(Text)
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
    intent_strength_base: Mapped[int] = mapped_column(default=0)
    intent_strength_final: Mapped[int] = mapped_column(default=0)
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
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    outcome_status: Mapped[str | None]


class DeveloperSegment(Base):
    __tablename__ = "developer_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), index=True)
    segment_code: Mapped[str] = mapped_column(String(50))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    classifier_version: Mapped[str] = mapped_column(default="segments-v2a-rules-1")
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("developer_id", "segment_code", "manual_override"),)


class DeveloperTechnology(Base):
    __tablename__ = "developer_technologies"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), index=True)
    technology_type: Mapped[str] = mapped_column(String(50))
    technology_name: Mapped[str] = mapped_column(String(100))
    evidence_signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("developer_id", "technology_type", "technology_name", "evidence_signal_id"),)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    canonical_domain: Mapped[str | None] = mapped_column(String(200), unique=True)
    github_org: Mapped[str | None] = mapped_column(String(100), unique=True)
    profile_url: Mapped[str | None]
    organization_type: Mapped[str] = mapped_column(default="UNKNOWN")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeveloperOrganization(Base):
    __tablename__ = "developer_organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(50))
    evidence_url: Mapped[str]
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("developer_id", "organization_id", "relationship_type"),)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    segment_code: Mapped[str | None]
    source: Mapped[str | None]
    route: Mapped[str | None]
    tracking_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    destination_url: Mapped[str]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EngagementEvent(Base):
    __tablename__ = "engagement_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    evidence_level: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("message_versions.id", ondelete="SET NULL"))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageVersion(Base):
    __tablename__ = "message_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    review_action_id: Mapped[int | None] = mapped_column(ForeignKey("review_actions.id", ondelete="SET NULL"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    template_version: Mapped[str] = mapped_column(default="v1")
    generated_text: Mapped[str] = mapped_column(Text)
    final_text: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GitHubWebhookDelivery(Base):
    __tablename__ = "github_webhook_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    event_name: Mapped[str] = mapped_column(String(60))
    action: Mapped[str | None] = mapped_column(String(60))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED")
    error: Mapped[str | None] = mapped_column(Text)


class ContributorEvent(Base):
    __tablename__ = "contributor_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(220))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    action: Mapped[str | None] = mapped_column(String(60))
    actor_github_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor_login: Mapped[str | None] = mapped_column(String(100), index=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="SET NULL"), index=True)
    repository_full_name: Mapped[str] = mapped_column(String(220), index=True)
    repository_scope: Mapped[str] = mapped_column(String(20), default="UPSTREAM")
    fork_full_name: Mapped[str | None] = mapped_column(String(220), index=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, index=True)
    canonical_url: Mapped[str | None]
    title: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attribution: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    attribution_evidence: Mapped[str | None] = mapped_column(Text)
    meaningful: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("source", "external_id"),)


class ContributorPipeline(Base):
    __tablename__ = "contributor_pipeline"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), unique=True, index=True)
    stage: Mapped[str] = mapped_column(String(40), default="DISCOVERED", index=True)
    attribution: Mapped[str] = mapped_column(String(30), default="UNKNOWN", index=True)
    first_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latest_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    upstream_repository: Mapped[str | None] = mapped_column(String(220))
    fork_repository: Mapped[str | None] = mapped_column(String(220))
    pull_request_number: Mapped[int | None] = mapped_column(Integer)
    last_meaningful_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checks_state: Mapped[str | None] = mapped_column(String(30))
    stalled_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MaintainerAlert(Base):
    __tablename__ = "maintainer_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    developer_id: Mapped[int | None] = mapped_column(ForeignKey("developers.id", ondelete="CASCADE"), index=True)
    contributor_event_id: Mapped[int | None] = mapped_column(ForeignKey("contributor_events.id", ondelete="CASCADE"))
    alert_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("alert_type", "contributor_event_id"),)
