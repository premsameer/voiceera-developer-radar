from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl
from .models import Intent


class NormalizedSignal(BaseModel):
    source: str
    external_id: str
    canonical_url: HttpUrl
    actor_handle: str
    actor_display_name: str | None = None
    actor_profile_url: HttpUrl | None = None
    observed_intent: Intent = Intent.UNKNOWN
    intent_evidence: str
    activity_type: str
    activity_title: str
    activity_text: str
    activity_at: datetime
    repository_name: str | None = None
    repository_url: HttpUrl | None = None
    repository_topics: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    discovery_query: str
    collected_at: datetime
    raw_metadata: dict = Field(default_factory=dict)


class ScanRequest(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["github"])
    lookback_days: int = Field(default=30, ge=1, le=90)


class DraftPatch(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class StagePatch(BaseModel):
    stage: str


class SegmentOverride(BaseModel):
    segment_code: str
    reason: str = Field(min_length=3,max_length=500)
    evidence_signal_id: int | None = None


class EngagementEventCreate(BaseModel):
    event_type: str
    event_at: datetime | None = None
    evidence_level: str = "MANUAL_VERIFIED"
    source: str = "manual"
    campaign_id: int | None = None
    metadata: dict = Field(default_factory=dict)


class OrganizationLinkCreate(BaseModel):
    name: str
    relationship_type: str
    evidence_url: HttpUrl
    canonical_domain: str | None = None
    github_org: str | None = None
    profile_url: HttpUrl | None = None
    manually_verified: bool = True


class CampaignCreate(BaseModel):
    name: str
    destination_url: HttpUrl
    segment_code: str | None = None
    source: str | None = None
    route: str | None = None
