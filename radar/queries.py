from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from .models import Developer, Evaluation, Signal


def days_since(value: datetime, timezone_name: str) -> int:
    if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
    return max(0,(datetime.now(ZoneInfo(timezone_name)).date()-value.astimezone(ZoneInfo(timezone_name)).date()).days)


def developer_rows(session: Session, timezone_name: str):
    developers=session.scalars(select(Developer).options(joinedload(Developer.signals).joinedload(Signal.evaluation).joinedload(Evaluation.opportunity))).unique().all()
    rows=[]
    for d in developers:
        if not d.signals: continue
        latest=max(d.signals,key=lambda s:s.activity_at); e=latest.evaluation; repo=latest.repository
        rows.append({"id":d.id,"developer":d.display_name or d.primary_handle,"handle":d.primary_handle,"profile":d.profile_url,"primary_segment":d.primary_segment_code,"intent_strength":d.intent_strength,"observed_intent":e.observed_intent,"intent_evidence":e.intent_evidence,"repository":repo.full_name if repo else None,"repository_url":repo.url if repo else None,"recent_activity":f"{latest.activity_type}: {latest.title}","activity_url":latest.canonical_url,"last_activity":latest.activity_at.isoformat(),"days_since_activity":days_since(latest.activity_at,timezone_name),"qualification":e.verdict,"score":e.rule_score,"reason":e.reason,"voiceera_route":e.recommended_route,"matched_opportunity":e.opportunity.title if e.opportunity else None,"opportunity_url":e.opportunity.url if e.opportunity else None,"personalised_message":e.draft_text,"funnel_status":d.current_funnel_stage,"next_best_action":d.next_best_action,"next_action_reason":d.next_action_reason,"evaluation_id":e.id,"activities":len(d.signals)})
    return sorted(rows,key=lambda r:(r["qualification"]!="PASS",-r["score"]))
