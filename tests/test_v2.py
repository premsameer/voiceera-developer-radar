from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from radar.api import app
from radar.db import get_db
from radar.intelligence import derive_funnel,intent_strength,next_action,record_event,segment_codes
from radar.models import Campaign,Developer,DeveloperSegment,DeveloperTechnology,EngagementEvent,Organization
from radar.schemas import NormalizedSignal
from radar.service import persist_signal


def item(**updates):
    data=dict(source="github",external_id="v2-1",canonical_url="https://github.com/o/r/pull/22",actor_handle="v2-dev",actor_profile_url="https://github.com/v2-dev",intent_evidence="WebRTC realtime voice agent in Python with LiveKit",activity_type="pull_request",activity_title="Add WebRTC voice agent",activity_text="WebRTC realtime voice agent in Python with LiveKit",activity_at=datetime.now(timezone.utc)-timedelta(days=2),repository_name="o/r-v2",repository_url="https://github.com/o/r-v2",repository_topics=["voice-ai","webrtc"],programming_languages=["Python"],discovery_query="test",collected_at=datetime.now(timezone.utc),raw_metadata={"github_node_id":"v2-node"})
    data.update(updates); return NormalizedSignal(**data)


def test_segmentation_and_intent_components():
    value=item(); codes=segment_codes(value); base,final=intent_strength(value,2)
    assert "REALTIME_TELEPHONY_ENGINEER" in codes and "OSS_CONTRIBUTOR" in codes
    assert base==80 and final==100


def test_evidence_backed_enrichment(db):
    assert persist_signal(db,item()); db.commit()
    developer=db.scalar(select(Developer).where(Developer.primary_handle=="v2-dev"))
    assert developer.primary_segment_code!="UNKNOWN_DEVELOPER" and developer.intent_strength==100
    segments=db.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer.id)).all()
    technologies=db.scalars(select(DeveloperTechnology).where(DeveloperTechnology.developer_id==developer.id)).all()
    assert all(x.evidence_signal_id for x in segments) and {x.technology_name for x in technologies}>={"Python","WebRTC","LiveKit"}


def test_funnel_derivation_and_next_actions(db):
    persist_signal(db,item()); db.commit(); developer=db.scalar(select(Developer).where(Developer.primary_handle=="v2-dev"))
    first=record_event(db,developer,"CONTACTED","MANUAL_VERIFIED","manual",event_at=datetime.now(timezone.utc)-timedelta(days=8)); db.commit()
    assert developer.current_funnel_stage=="CONTACTED" and developer.next_best_action=="PREPARE_FOLLOW_UP"
    record_event(db,developer,"RESPONDED","MANUAL_VERIFIED","manual"); db.commit()
    assert developer.current_funnel_stage=="RESPONDED" and developer.next_best_action=="SHARE_QUICK_START"


def test_tracking_redirect_and_event(db):
    campaign=Campaign(name="test",tracking_code="abc-safe",destination_url="https://github.com/voiceera/voiceera",active=True); db.add(campaign); db.commit()
    app.dependency_overrides[get_db]=lambda:db
    try:
        response=TestClient(app).get("/r/abc-safe",follow_redirects=False)
        assert response.status_code==307 and response.headers["location"].startswith("https://github.com")
        event=db.scalar(select(EngagementEvent).where(EngagementEvent.campaign_id==campaign.id))
        assert event.event_type=="REPO_VISITED" and event.evidence_level=="ATTRIBUTED" and event.developer_id is None
    finally: app.dependency_overrides.clear()


def test_organization_requires_evidence_url(db):
    organization=Organization(name="Public Org",github_org="public-org",profile_url="https://github.com/public-org",metadata_json={}); db.add(organization); db.commit()
    assert organization.github_org=="public-org"
