import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import Settings, get_settings
from .connectors.community import ForemConnector, HackerNewsConnector, RSSConnector
from .connectors.github import GitHubConnector
from .connectors.reddit import RedditConnector
from .models import Connector, Developer, Evaluation, Opportunity, Repository, Route, ScanRun, Signal, Verdict
from .schemas import NormalizedSignal
from .scoring import choose_opportunity, classify_intent, draft_message, evaluate


def adapter_for(name: str, settings: Settings):
    if name=="github": return GitHubConnector(settings.github_token)
    if name=="devto": return ForemConnector(settings.forem_api_key)
    if name=="hackernews": return HackerNewsConnector()
    if name=="rss": return RSSConnector()
    if name=="reddit":
        if not settings.reddit_client_id or not settings.reddit_client_secret: raise RuntimeError("Reddit disabled: OAuth credentials are not configured")
        return RedditConnector(settings.reddit_client_id,settings.reddit_client_secret,settings.reddit_user_agent)
    raise ValueError(f"Unknown source: {name}")


def persist_signal(session: Session, item: NormalizedSignal) -> bool:
    url=str(item.canonical_url)
    if session.scalar(select(Signal).where((Signal.source==item.source)&(Signal.external_id==item.external_id))) or session.scalar(select(Signal).where(Signal.canonical_url==url)): return False
    developer=session.scalar(select(Developer).where((Developer.primary_source==item.source)&(Developer.primary_handle==item.actor_handle)))
    if not developer:
        developer=Developer(primary_source=item.source,primary_handle=item.actor_handle,display_name=item.actor_display_name,profile_url=str(item.actor_profile_url) if item.actor_profile_url else None,latest_observed_intent=item.observed_intent.value,latest_intent_evidence=item.intent_evidence,latest_activity_at=item.activity_at)
        session.add(developer); session.flush()
    else:
        latest=developer.latest_activity_at
        if latest is not None and latest.tzinfo is None:
            latest=latest.replace(tzinfo=timezone.utc)
        if latest is None or item.activity_at>latest:
            developer.latest_activity_at=item.activity_at; developer.latest_observed_intent=item.observed_intent.value; developer.latest_intent_evidence=item.intent_evidence
    repository=None
    if item.repository_name:
        repository=session.scalar(select(Repository).where(Repository.full_name==item.repository_name))
        if not repository:
            meta=item.raw_metadata
            repository=Repository(github_node_id=meta.get("github_node_id"),full_name=item.repository_name,url=str(item.repository_url),topics_json=item.repository_topics,languages_json=item.programming_languages,stars=meta.get("stars",0),fork=meta.get("fork",False),archived=False,last_pushed_at=item.activity_at,discovery_query=item.discovery_query)
            session.add(repository); session.flush()
    intent=classify_intent(item.activity_type,item.activity_text)
    item.observed_intent=intent
    digest=hashlib.sha256(f"{item.source}|{item.external_id}|{url}".encode()).hexdigest()
    signal=Signal(source=item.source,external_id=item.external_id,canonical_url=url,developer_id=developer.id,repository_id=repository.id if repository else None,activity_type=item.activity_type,title=item.activity_title,excerpt=item.activity_text,activity_at=item.activity_at,observed_intent=intent.value,intent_evidence=item.intent_evidence,raw_metadata_json=item.raw_metadata,content_hash=digest)
    session.add(signal); session.flush()
    score,verdict,segment,reason=evaluate(item)
    opportunities=session.scalars(select(Opportunity).where(Opportunity.active.is_(True))).all()
    route,opportunity=choose_opportunity(item,opportunities) if verdict==Verdict.PASS else (Route.MONITOR,None)
    evaluation=Evaluation(signal_id=signal.id,rule_score=score,verdict=verdict.value,segment=segment,observed_intent=intent.value,intent_evidence=item.intent_evidence,proof_quote=item.intent_evidence[:200] if verdict==Verdict.PASS else None,proof_url=url,proof_date=item.activity_at,reason=reason,confidence=1.0,recommended_route=route.value,matched_opportunity_id=opportunity.id if opportunity else None,draft_text=draft_message(item,route,opportunity) if verdict==Verdict.PASS else None)
    session.add(evaluation); developer.segment=segment
    return True


def run_scan(session: Session, sources: list[str], lookback_days: int=30, settings: Settings | None=None):
    settings=settings or get_settings(); run=ScanRun(); session.add(run); session.commit(); counts={}; errors=[]
    for source in sources:
        connector=session.scalar(select(Connector).where(Connector.type==source))
        if not connector or not connector.enabled:
            errors.append(f"{source}: disabled"); counts[source]={"status":"disabled","collected":0}; continue
        if connector.last_success_at:
            checkpoint=connector.last_success_at
            if checkpoint.tzinfo is None:
                checkpoint=checkpoint.replace(tzinfo=timezone.utc)
            since=checkpoint-timedelta(hours=2)
        else:
            since=datetime.now(timezone.utc)-timedelta(days=lookback_days)
        try:
            items=adapter_for(source,settings).collect(since,connector.config_json); added=0
            for item in items:
                try:
                    if persist_signal(session,item): added+=1
                except IntegrityError: session.rollback()
            connector.last_success_at=datetime.now(timezone.utc); connector.last_cursor=connector.last_success_at.isoformat(); connector.last_error=None; connector.items_collected=len(items)
            counts[source]={"status":"ok","collected":len(items),"added":added,"duplicates":len(items)-added}; session.commit()
        except Exception as exc:
            session.rollback(); connector=session.scalar(select(Connector).where(Connector.type==source)); connector.last_error=str(exc)[:500]; session.commit()
            errors.append(f"{source}: {exc}"); counts[source]={"status":"error","error":str(exc)[:200]}
    run=session.get(ScanRun,run.id); run.completed_at=datetime.now(timezone.utc); run.status="PARTIAL" if errors else "SUCCESS"; run.source_counts_json=counts; run.error_summary="\n".join(errors) or None; session.commit(); return run
