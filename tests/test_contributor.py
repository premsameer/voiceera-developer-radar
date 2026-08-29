import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from radar.api import app
from radar.config import get_settings
from radar.contributor import SUPPORTED_WEBHOOKS, detect_stalled_prs, normalize_github_event, process_webhook, reconcile_github, verify_webhook_signature
from radar.db import get_db
from radar.models import ContributorEvent, ContributorPipeline, Developer, EngagementEvent, GitHubWebhookDelivery, MaintainerAlert


def developer(db, login="octocat", github_id=None):
    row=Developer(primary_source="github",primary_handle=login,github_user_id=github_id,display_name="Different Name",public_links_json={})
    db.add(row); db.commit(); return row


def payload(event="fork", login="octocat", github_id=7, fork_repo="octocat/radar"):
    base={"action":"created","sender":{"id":github_id,"login":login},"repository":{"id":1,"full_name":"voiceera/radar","html_url":"https://github.com/voiceera/radar","fork":False}}
    if event=="fork": base["forkee"]={"id":22,"full_name":fork_repo,"html_url":f"https://github.com/{fork_repo}","created_at":"2026-08-29T08:00:00Z","owner":{"id":github_id,"login":login}}
    if event=="pull_request":
        base["action"]="opened"; base["pull_request"]={"id":33,"number":4,"title":"Add voice adapter","html_url":"https://github.com/voiceera/radar/pull/4","created_at":"2026-08-29T09:00:00Z","updated_at":"2026-08-29T09:00:00Z","user":{"id":github_id,"login":login}}
    return base


def test_signature_verification():
    body=b'{"zen":"safe"}'; signature="sha256="+hmac.new(b"secret",body,hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body,signature,"secret")
    assert not verify_webhook_signature(body,"sha256=bad","secret")


def test_delivery_idempotency_and_exact_login_match(db):
    row=developer(db)
    first=process_webhook(db,"delivery-1","fork",payload())
    second=process_webhook(db,"delivery-1","fork",payload())
    event=db.scalar(select(ContributorEvent)); pipeline=db.scalar(select(ContributorPipeline)); deliveries=db.scalars(select(GitHubWebhookDelivery)).all()
    assert first["processed"]==1 and second["status"]=="duplicate" and len(deliveries)==1
    assert event.developer_id==row.id and row.github_user_id==7
    assert pipeline.stage=="FORKED" and not event.meaningful and event.repository_scope=="FORK"


def test_identity_never_matches_name_or_email(db):
    developer(db,login="someone-else")
    data=payload(); data["sender"]={"id":99,"login":"unmatched","name":"Different Name","email":"octocat@example.com"}; data["forkee"]["owner"]=data["sender"]
    process_webhook(db,"delivery-identity","fork",data)
    assert db.scalar(select(ContributorEvent)).developer_id is None


def test_fork_activity_and_upstream_pr_are_distinct(db):
    row=developer(db,github_id=7); process_webhook(db,"fork-1","fork",payload())
    push=payload(); push["repository"]={"full_name":"octocat/radar","html_url":"https://github.com/octocat/radar","fork":True,"parent":{"full_name":"voiceera/radar"}}; push.update({"after":"abc","head_commit":{"message":"Implement adapter","timestamp":"2026-08-29T10:00:00Z"}})
    process_webhook(db,"push-1","push",push)
    pipeline=db.scalar(select(ContributorPipeline).where(ContributorPipeline.developer_id==row.id))
    assert pipeline.stage=="MEANINGFUL_FORK_ACTIVITY"
    process_webhook(db,"pr-1","pull_request",payload("pull_request"))
    events=db.scalars(select(ContributorEvent).order_by(ContributorEvent.id)).all()
    assert [(x.event_type,x.repository_scope) for x in events]==[("FORK","FORK"),("PUSH","FORK"),("PULL_REQUEST","UPSTREAM")]
    assert db.scalar(select(ContributorPipeline)).stage=="UPSTREAM_PR_OPENED"


def test_later_activity_is_not_claimed_as_outreach_attributed(db):
    row=developer(db,github_id=7); db.add(EngagementEvent(developer_id=row.id,event_type="OUTREACH_APPROVED",event_at=datetime(2026,8,28,tzinfo=timezone.utc),evidence_level="MANUAL_VERIFIED",source="review",metadata_json={})); db.commit()
    process_webhook(db,"after-outreach","pull_request",payload("pull_request"))
    event=db.scalar(select(ContributorEvent)); assert event.attribution=="UNKNOWN" and "no causal" in event.attribution_evidence


def test_stalled_pr_alert_is_idempotent(db):
    row=developer(db,github_id=7); process_webhook(db,"pr-stall","pull_request",payload("pull_request"))
    pipeline=db.scalar(select(ContributorPipeline)); pipeline.latest_event_at=datetime.now(timezone.utc)-timedelta(days=9); db.commit()
    assert detect_stalled_prs(db,7)==1 and detect_stalled_prs(db,7)==0
    assert pipeline.stage=="STALLED" and len(db.scalars(select(MaintainerAlert).where(MaintainerAlert.alert_type=="STALLED_PR")).all())==1


def test_webhook_api_rejects_bad_signature_and_accepts_valid(db):
    get_settings().github_webhook_secret="test-secret"; app.dependency_overrides[get_db]=lambda:db
    body=json.dumps(payload()).encode(); valid="sha256="+hmac.new(b"test-secret",body,hashlib.sha256).hexdigest()
    try:
        client=TestClient(app)
        assert client.post("/api/github/webhook",content=body,headers={"Content-Type":"application/json","X-GitHub-Delivery":"bad","X-GitHub-Event":"fork","X-Hub-Signature-256":"sha256=bad"}).status_code==401
        response=client.post("/api/github/webhook",content=body,headers={"Content-Type":"application/json","X-GitHub-Delivery":"good","X-GitHub-Event":"fork","X-Hub-Signature-256":valid})
        assert response.status_code==200 and response.json()["processed"]==1
    finally:
        app.dependency_overrides.clear(); get_settings().github_webhook_secret=None


def test_all_requested_webhook_types_are_supported():
    assert SUPPORTED_WEBHOOKS=={"fork","watch","issues","issue_comment","pull_request","pull_request_review","pull_request_review_comment","push","check_run","check_suite"}
    for name in SUPPORTED_WEBHOOKS:
        assert normalize_github_event(name,payload(name if name in {"fork","pull_request"} else "base")) is not None


def test_rest_reconciliation_covers_forks_prs_reviews_checks_and_known_fork_commits(db):
    developer(db,github_id=7)
    class FakeAPI:
        def get(self,path,params=None):
            if path.endswith("/forks"): return [{"id":22,"full_name":"octocat/radar","html_url":"https://github.com/octocat/radar","created_at":"2026-08-29T08:00:00Z","owner":{"id":7,"login":"octocat"}}]
            if path.endswith("/pulls"): return [{"id":33,"number":4,"state":"open","title":"Adapter","html_url":"https://github.com/voiceera/radar/pull/4","created_at":"2026-08-29T09:00:00Z","updated_at":datetime.now(timezone.utc).isoformat(),"user":{"id":7,"login":"octocat"},"head":{"sha":"headsha"}}]
            if path.endswith("/reviews"): return [{"id":44,"state":"APPROVED","submitted_at":datetime.now(timezone.utc).isoformat(),"html_url":"https://github.com/voiceera/radar/pull/4#review","user":{"id":8,"login":"maintainer"}}]
            if path.endswith("/check-runs"): return {"check_runs":[{"id":55,"name":"tests","status":"completed","conclusion":"success","completed_at":datetime.now(timezone.utc).isoformat(),"html_url":"https://github.com/voiceera/radar/actions"}]}
            if path=="/repos/octocat/radar/commits": return [{"sha":"forksha","html_url":"https://github.com/octocat/radar/commit/forksha","commit":{"message":"work"},"created_at":datetime.now(timezone.utc).isoformat(),"author":{"id":7,"login":"octocat"}}]
            raise AssertionError(path)
    counts=reconcile_github(db,["voiceera/radar"],"unused",FakeAPI())
    assert counts=={"forks":1,"pull_requests":1,"reviews":1,"checks":1,"fork_activity":1}
    assert {x.repository_scope for x in db.scalars(select(ContributorEvent)).all()}=={"FORK","UPSTREAM"}
