"""Read-only GitHub contributor ingestion, reconciliation, attribution and alerts."""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    ContributorEvent, ContributorPipeline, Developer, EngagementEvent,
    GitHubWebhookDelivery, MaintainerAlert, MessageVersion, utcnow,
)

CONTRIBUTOR_STAGES = [
    "DISCOVERED", "FORKED", "MEANINGFUL_FORK_ACTIVITY", "UPSTREAM_PR_OPENED",
    "REVIEW_IN_PROGRESS", "CHANGES_REQUESTED", "CHECKS_PASSING", "MERGED",
    "CLOSED_UNMERGED", "STALLED",
]
STAGE_RANK = {stage: index for index, stage in enumerate(CONTRIBUTOR_STAGES)}
SUPPORTED_WEBHOOKS = {
    "fork", "watch", "issues", "issue_comment", "pull_request",
    "pull_request_review", "pull_request_review_comment", "push",
    "check_run", "check_suite",
}


def verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return utcnow()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _repository(payload: dict) -> tuple[str, str, str | None]:
    repository = payload.get("repository") or {}
    full_name = repository.get("full_name") or "unknown/unknown"
    is_fork = bool(repository.get("fork"))
    upstream = ((repository.get("parent") or {}).get("full_name") if is_fork else full_name) or full_name
    return upstream, "FORK" if is_fork else "UPSTREAM", full_name if is_fork else None


def _actor(payload: dict, event_name: str) -> dict:
    key = {
        "fork": "forkee", "issue_comment": "comment", "pull_request_review": "review",
        "pull_request_review_comment": "comment",
    }.get(event_name)
    if key == "fork":
        return (payload.get("forkee") or {}).get("owner") or payload.get("sender") or {}
    if key:
        return (payload.get(key) or {}).get("user") or payload.get("sender") or {}
    if event_name == "pull_request":
        return (payload.get("pull_request") or {}).get("user") or payload.get("sender") or {}
    if event_name == "issues":
        return (payload.get("issue") or {}).get("user") or payload.get("sender") or {}
    return payload.get("sender") or {}


def _match_developer(db: Session, actor: dict) -> Developer | None:
    github_id, login = actor.get("id"), actor.get("login")
    if github_id is not None:
        developer = db.scalar(select(Developer).where(Developer.github_user_id == int(github_id)))
        if developer:
            return developer
    if not login:
        return None
    developer = db.scalar(select(Developer).where(
        Developer.primary_source == "github",
        func.lower(Developer.primary_handle) == login.lower(),
    ))
    if developer and developer.github_user_id is None and github_id is not None:
        developer.github_user_id = int(github_id)
    return developer


def _explicit_campaign(payload: dict) -> int | None:
    value = (payload.get("voiceera_attribution") or {}).get("campaign_id")
    return int(value) if value is not None else None


def classify_attribution(db: Session, developer: Developer | None, occurred_at: datetime, payload: dict) -> tuple[str, str]:
    campaign_id = _explicit_campaign(payload)
    if campaign_id:
        return "OUTREACH_ATTRIBUTED", f"Explicit VoiceERA campaign evidence: campaign_id={campaign_id}"
    if not developer:
        return "UNKNOWN", "No exact GitHub identity match"
    first_outreach = db.scalar(select(func.min(EngagementEvent.event_at)).where(
        EngagementEvent.developer_id == developer.id,
        EngagementEvent.event_type.in_(["OUTREACH_APPROVED", "MESSAGE_SENT"]),
    ))
    first_sent = db.scalar(select(func.min(MessageVersion.sent_at)).join(
        EngagementEvent, EngagementEvent.message_id == MessageVersion.id, isouter=True,
    ).where(EngagementEvent.developer_id == developer.id, MessageVersion.sent_at.is_not(None)))
    candidates = [x for x in (first_outreach, first_sent) if x]
    if not candidates:
        return "ORGANIC", "No recorded outreach existed when this activity was observed"
    if _utc(occurred_at) <= min(_utc(x) for x in candidates):
        return "PRE_EXISTING", "Activity predates the earliest recorded outreach"
    return "UNKNOWN", "Activity followed outreach but has no causal attribution evidence"


def normalize_github_event(event_name: str, payload: dict) -> dict | None:
    if event_name not in SUPPORTED_WEBHOOKS:
        return None
    action = payload.get("action")
    actor = _actor(payload, event_name)
    upstream, scope, fork_name = _repository(payload)
    issue, pr = payload.get("issue") or {}, payload.get("pull_request") or {}
    review, comment = payload.get("review") or {}, payload.get("comment") or {}
    check = payload.get("check_run") or payload.get("check_suite") or {}
    if event_name == "fork":
        fork = payload.get("forkee") or {}; scope, fork_name = "FORK", fork.get("full_name")
        external_id, url, title, occurred = f"fork:{fork.get('id') or fork_name}", fork.get("html_url"), f"Forked {upstream}", fork.get("created_at")
    elif event_name == "watch":
        external_id, url, title, occurred = f"watch:{upstream}:{actor.get('id') or actor.get('login')}", (payload.get("repository") or {}).get("html_url"), f"Watched {upstream}", None
    elif event_name in {"issues", "issue_comment"}:
        item = comment if event_name == "issue_comment" else issue
        external_id = f"{event_name}:{item.get('id')}:{action or ''}"
        url, title = item.get("html_url"), issue.get("title") or "Issue activity"
        occurred = item.get("updated_at") or item.get("created_at")
    elif event_name == "pull_request":
        external_id = f"pull_request:{pr.get('id')}:{action or ''}:{pr.get('updated_at') or ''}"
        url, title, occurred = pr.get("html_url"), pr.get("title"), pr.get("updated_at") or pr.get("created_at")
    elif event_name == "pull_request_review":
        external_id = f"review:{review.get('id')}:{action or ''}"
        url, title, occurred = review.get("html_url"), pr.get("title") or "Pull request review", review.get("submitted_at")
    elif event_name == "pull_request_review_comment":
        external_id = f"review_comment:{comment.get('id')}:{action or ''}"
        url, title, occurred = comment.get("html_url"), pr.get("title") or "Review comment", comment.get("updated_at") or comment.get("created_at")
    elif event_name == "push":
        external_id = f"push:{payload.get('after')}"
        url, title, occurred = (payload.get("repository") or {}).get("html_url"), (payload.get("head_commit") or {}).get("message") or "Push", (payload.get("head_commit") or {}).get("timestamp")
    else:
        prs = check.get("pull_requests") or []
        pr = prs[0] if prs else pr
        external_id = f"{event_name}:{check.get('id')}:{action or ''}:{check.get('status') or ''}:{check.get('conclusion') or ''}"
        url, title, occurred = check.get("html_url"), check.get("name") or event_name.replace("_", " "), check.get("completed_at") or check.get("updated_at") or check.get("created_at")
    pr_number = pr.get("number") or issue.get("number") if issue.get("pull_request") else pr.get("number")
    meaningful = event_name not in {"fork", "watch"}
    return {
        "source": "WEBHOOK", "external_id": external_id, "event_type": event_name.upper(),
        "action": action, "actor": actor, "repository_full_name": upstream,
        "repository_scope": scope, "fork_full_name": fork_name,
        "pull_request_number": pr_number, "canonical_url": url, "title": title,
        "occurred_at": _parse_time(occurred), "meaningful": meaningful,
        "raw_metadata_json": {"check_status": check.get("status"), "check_conclusion": check.get("conclusion"), "review_state": review.get("state"), "merged": pr.get("merged",False)},
    }


def _stage_for(event: ContributorEvent) -> str:
    if event.event_type == "FORK": return "FORKED"
    if event.repository_scope == "FORK" and event.meaningful: return "MEANINGFUL_FORK_ACTIVITY"
    if event.event_type == "PULL_REQUEST":
        if event.action == "closed" and event.raw_metadata_json.get("merged"): return "MERGED"
        if event.action == "closed": return "CLOSED_UNMERGED"
        return "UPSTREAM_PR_OPENED"
    if event.event_type == "PULL_REQUEST_REVIEW":
        return "CHANGES_REQUESTED" if event.raw_metadata_json.get("review_state") == "changes_requested" else "REVIEW_IN_PROGRESS"
    if event.event_type in {"CHECK_RUN", "CHECK_SUITE"} and event.raw_metadata_json.get("check_conclusion") == "success": return "CHECKS_PASSING"
    return "DISCOVERED"


def _advance_pipeline(db: Session, event: ContributorEvent) -> None:
    if not event.developer_id:
        return
    pipeline = db.scalar(select(ContributorPipeline).where(ContributorPipeline.developer_id == event.developer_id))
    stage = _stage_for(event)
    if not pipeline:
        pipeline = ContributorPipeline(developer_id=event.developer_id, stage=stage, attribution=event.attribution,
            first_event_at=event.occurred_at, latest_event_at=event.occurred_at)
        db.add(pipeline)
    pipeline.latest_event_at = max(_utc(pipeline.latest_event_at), _utc(event.occurred_at))
    attribution_rank={"UNKNOWN":0,"ORGANIC":1,"PRE_EXISTING":2,"OUTREACH_ATTRIBUTED":3}
    if attribution_rank.get(event.attribution,0)>attribution_rank.get(pipeline.attribution,0): pipeline.attribution=event.attribution
    pipeline.upstream_repository = event.repository_full_name
    pipeline.fork_repository = event.fork_full_name or pipeline.fork_repository
    pipeline.pull_request_number = event.pull_request_number or pipeline.pull_request_number
    if event.meaningful: pipeline.last_meaningful_activity_at = event.occurred_at
    if event.event_type in {"CHECK_RUN", "CHECK_SUITE"}: pipeline.checks_state = event.raw_metadata_json.get("check_conclusion") or event.raw_metadata_json.get("check_status")
    terminal = stage in {"MERGED", "CLOSED_UNMERGED"}
    if terminal or STAGE_RANK.get(stage, 0) > STAGE_RANK.get(pipeline.stage, 0): pipeline.stage = stage
    if stage in {"UPSTREAM_PR_OPENED", "CHANGES_REQUESTED"}:
        alert = MaintainerAlert(developer_id=event.developer_id, contributor_event_id=event.id,
            alert_type="NEW_PR" if stage == "UPSTREAM_PR_OPENED" else "CHANGES_REQUESTED",
            severity="ACTION", message=f"{event.actor_login} · {stage.replace('_',' ').title()} · {event.repository_full_name}#{event.pull_request_number}")
        db.add(alert)


def ingest_normalized(db: Session, normalized: dict, payload: dict | None = None) -> tuple[ContributorEvent, bool]:
    existing = db.scalar(select(ContributorEvent).where(
        ContributorEvent.source == normalized["source"], ContributorEvent.external_id == normalized["external_id"]))
    if existing: return existing, False
    actor = normalized.pop("actor", {})
    developer = _match_developer(db, actor)
    attribution, evidence = classify_attribution(db, developer, normalized["occurred_at"], payload or {})
    event = ContributorEvent(**normalized, actor_github_id=actor.get("id"), actor_login=actor.get("login"),
        developer_id=developer.id if developer else None, attribution=attribution, attribution_evidence=evidence)
    db.add(event); db.flush(); _advance_pipeline(db, event)
    return event, True


def process_webhook(db: Session, delivery_id: str, event_name: str, payload: dict) -> dict:
    existing = db.scalar(select(GitHubWebhookDelivery).where(GitHubWebhookDelivery.delivery_id == delivery_id))
    if existing: return {"delivery_id": delivery_id, "status": "duplicate", "processed": 0}
    delivery = GitHubWebhookDelivery(delivery_id=delivery_id, event_name=event_name, action=payload.get("action")); db.add(delivery)
    normalized = normalize_github_event(event_name, payload)
    if not normalized:
        delivery.status, delivery.processed_at = "IGNORED", utcnow(); db.commit()
        return {"delivery_id": delivery_id, "status": "ignored", "processed": 0}
    try:
        _, created = ingest_normalized(db, normalized, payload)
        delivery.status, delivery.processed_at = "PROCESSED", utcnow(); db.commit()
        return {"delivery_id": delivery_id, "status": "processed", "processed": int(created)}
    except Exception as exc:
        db.rollback()
        failed = GitHubWebhookDelivery(delivery_id=delivery_id, event_name=event_name, action=payload.get("action"), status="FAILED", error=str(exc), processed_at=utcnow())
        db.add(failed); db.commit(); raise


class GitHubRESTClient:
    def __init__(self, token: str):
        self.client = httpx.Client(headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}, timeout=30)
    def get(self, path: str, params: dict | None = None) -> Any:
        response = self.client.get(f"https://api.github.com{path}", params=params); response.raise_for_status(); return response.json()


def github_access_token(settings: Any) -> str | None:
    """Return a configured token or mint a short-lived GitHub App installation token."""
    if settings.github_token: return settings.github_token
    if not (settings.github_app_id and settings.github_app_installation_id and settings.github_app_private_key_path): return None
    import jwt
    now=int(datetime.now(timezone.utc).timestamp())
    app_jwt=jwt.encode({"iat":now-60,"exp":now+540,"iss":settings.github_app_id},Path(settings.github_app_private_key_path).read_text(),algorithm="RS256")
    response=httpx.post(f"https://api.github.com/app/installations/{settings.github_app_installation_id}/access_tokens",
        headers={"Authorization":f"Bearer {app_jwt}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"},timeout=30)
    response.raise_for_status(); return response.json()["token"]


def _rest_event(kind: str, repo: str, item: dict, scope: str = "UPSTREAM", fork: str | None = None, pr_number: int | None = None) -> dict:
    actor = item.get("user") or item.get("author") or item.get("owner") or {}
    action = item.get("state") or item.get("status")
    return {"source":"REST", "external_id":f"{kind}:{repo}:{item.get('id') or item.get('sha') or item.get('full_name')}:{item.get('updated_at') or action}",
        "event_type":kind.upper(), "action":action, "actor":actor, "repository_full_name":repo,
        "repository_scope":scope, "fork_full_name":fork, "pull_request_number":pr_number or item.get("number"),
        "canonical_url":item.get("html_url"), "title":item.get("title") or item.get("name") or kind,
        "occurred_at":_parse_time(item.get("updated_at") or item.get("created_at") or item.get("submitted_at")),
        "meaningful":kind != "fork", "raw_metadata_json":{"merged":item.get("merged",False),"review_state":item.get("state"),"check_status":item.get("status"),"check_conclusion":item.get("conclusion")}}


def reconcile_github(db: Session, repositories: Iterable[str], token: str, client: Any | None = None) -> dict:
    api = client or GitHubRESTClient(token); counts = {"forks":0,"pull_requests":0,"reviews":0,"checks":0,"fork_activity":0}
    since = utcnow() - timedelta(days=2)
    for repo in repositories:
        forks = api.get(f"/repos/{repo}/forks", {"sort":"newest","per_page":100})
        for fork in forks:
            _, created = ingest_normalized(db, _rest_event("fork", repo, fork, "FORK", fork.get("full_name"))); counts["forks"] += int(created)
        pulls = api.get(f"/repos/{repo}/pulls", {"state":"all","sort":"updated","direction":"desc","per_page":100})
        for pr in pulls:
            if _parse_time(pr.get("updated_at")) < since: continue
            _, created = ingest_normalized(db, _rest_event("pull_request", repo, pr)); counts["pull_requests"] += int(created)
            for review in api.get(f"/repos/{repo}/pulls/{pr['number']}/reviews", {"per_page":100}):
                _, made = ingest_normalized(db, _rest_event("pull_request_review", repo, review, pr_number=pr["number"])); counts["reviews"] += int(made)
            for check in api.get(f"/repos/{repo}/commits/{pr['head']['sha']}/check-runs", {"per_page":100}).get("check_runs", []):
                _, made = ingest_normalized(db, _rest_event("check_run", repo, check, pr_number=pr["number"])); counts["checks"] += int(made)
    known_forks = db.scalars(select(ContributorPipeline.fork_repository).where(ContributorPipeline.fork_repository.is_not(None))).all()
    for fork in set(known_forks):
        pipeline = db.scalar(select(ContributorPipeline).where(ContributorPipeline.fork_repository == fork))
        upstream = pipeline.upstream_repository if pipeline else fork
        for commit in api.get(f"/repos/{fork}/commits", {"since":since.isoformat(),"per_page":100}):
            _, made = ingest_normalized(db, _rest_event("push", upstream, commit, "FORK", fork)); counts["fork_activity"] += int(made)
    db.commit(); return counts


def detect_stalled_prs(db: Session, days: int = 7, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=days); created = 0
    pipelines = db.scalars(select(ContributorPipeline).where(
        ContributorPipeline.stage.in_(["UPSTREAM_PR_OPENED","REVIEW_IN_PROGRESS","CHANGES_REQUESTED","CHECKS_PASSING"]),
        ContributorPipeline.latest_event_at < cutoff,
    )).all()
    for pipeline in pipelines:
        existing = db.scalar(select(MaintainerAlert).where(MaintainerAlert.developer_id == pipeline.developer_id, MaintainerAlert.alert_type == "STALLED_PR", MaintainerAlert.status == "OPEN"))
        if existing: continue
        pipeline.stage, pipeline.stalled_since = "STALLED", cutoff
        db.add(MaintainerAlert(developer_id=pipeline.developer_id, alert_type="STALLED_PR", severity="ACTION",
            message=f"PR stalled for {days}+ days · {pipeline.upstream_repository}#{pipeline.pull_request_number}")); created += 1
    db.commit(); return created


def contributor_metrics(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(ContributorPipeline)) or 0
    stages = dict(db.execute(select(ContributorPipeline.stage, func.count()).group_by(ContributorPipeline.stage)).all())
    attrs = dict(db.execute(select(ContributorPipeline.attribution, func.count()).group_by(ContributorPipeline.attribution)).all())
    meaningful = sum(stages.get(x,0) for x in CONTRIBUTOR_STAGES[2:])
    prs = sum(stages.get(x,0) for x in CONTRIBUTOR_STAGES[3:])
    return {"denominator":total,"stages":stages,"attribution":attrs,
        "meaningful_activity_rate":round(meaningful/total,4) if total else 0,
        "upstream_pr_rate":round(prs/total,4) if total else 0,
        "merged":stages.get("MERGED",0)}
