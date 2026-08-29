import secrets
from fastapi import Depends, FastAPI, Header, HTTPException, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from .config import get_settings
from .db import get_db, init_db
from .digest import csv_digest, markdown_digest
from .importer import import_csv_text
from .models import Campaign,Connector,Developer,DeveloperOrganization,DeveloperSegment,DeveloperTechnology,EngagementEvent,Evaluation,MessageVersion,Organization,ReviewAction,ScanRun,Signal
from .queries import developer_rows
from .schemas import CampaignCreate,DraftPatch,EngagementEventCreate,OrganizationLinkCreate,ScanRequest,SegmentOverride,StagePatch
from .intelligence import FUNNEL_STAGES,record_event,update_next_action
from .analytics import funnel_analytics,message_analytics,segment_analytics
from .seed import seed
from .service import run_scan

app=FastAPI(title="VoiceERA Developer Radar",version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()
    from .db import SessionLocal
    with SessionLocal() as db: seed(db)


def admin(x_admin_secret: str=Header(default="")):
    if x_admin_secret!=get_settings().admin_secret: raise HTTPException(401,"Invalid admin secret")


@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/api/scans",dependencies=[Depends(admin)])
def scan(body: ScanRequest,db:Session=Depends(get_db)): return run_scan(db,body.sources,body.lookback_days)

@app.get("/api/scans/{run_id}")
def scan_status(run_id:int,db:Session=Depends(get_db)):
    value=db.get(ScanRun,run_id)
    if not value: raise HTTPException(404,"Scan not found")
    return value

@app.get("/api/signals")
def signals(db:Session=Depends(get_db)): return developer_rows(db,get_settings().app_timezone)

@app.get("/api/signals/{signal_id}")
def signal(signal_id:int,db:Session=Depends(get_db)):
    value=db.scalar(select(Signal).options(joinedload(Signal.evaluation)).where(Signal.id==signal_id))
    if not value: raise HTTPException(404,"Signal not found")
    return value

def review(evaluation_id:int,action:str,db:Session):
    value=db.get(Evaluation,evaluation_id)
    if not value: raise HTTPException(404,"Evaluation not found")
    review_row=ReviewAction(evaluation_id=evaluation_id,action=action,draft_text=value.draft_text); db.add(review_row); db.flush()
    developer=value.signal.developer
    if action=="APPROVE":
        record_event(db,developer,"OUTREACH_APPROVED","MANUAL_VERIFIED","review"); db.add(MessageVersion(review_action_id=review_row.id,template_version=value.prompt_version,generated_text=value.draft_text or "",final_text=value.draft_text,approved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
    elif action=="REJECT": record_event(db,developer,"ARCHIVED","MANUAL_VERIFIED","review")
    else: update_next_action(db,developer)
    db.commit(); return {"status":action,"stage":developer.current_funnel_stage,"next_best_action":developer.next_best_action}

@app.post("/api/evaluations/{evaluation_id}/approve",dependencies=[Depends(admin)])
def approve(evaluation_id:int,db:Session=Depends(get_db)): return review(evaluation_id,"APPROVE",db)

@app.post("/api/evaluations/{evaluation_id}/reject",dependencies=[Depends(admin)])
def reject(evaluation_id:int,db:Session=Depends(get_db)): return review(evaluation_id,"REJECT",db)

@app.post("/api/evaluations/{evaluation_id}/monitor",dependencies=[Depends(admin)])
def monitor(evaluation_id:int,db:Session=Depends(get_db)): return review(evaluation_id,"MONITOR",db)

@app.patch("/api/evaluations/{evaluation_id}/draft",dependencies=[Depends(admin)])
def edit_draft(evaluation_id:int,body:DraftPatch,db:Session=Depends(get_db)):
    value=db.get(Evaluation,evaluation_id)
    if not value: raise HTTPException(404,"Evaluation not found")
    old=value.draft_text; value.draft_text=body.text; db.add(ReviewAction(evaluation_id=evaluation_id,action="EDIT",draft_text=old,edited_text=body.text)); db.commit(); return {"text":body.text}

@app.get("/api/developers/{developer_id}")
def developer(developer_id:int,db:Session=Depends(get_db)):
    value=db.scalar(select(Developer).options(joinedload(Developer.signals)).where(Developer.id==developer_id))
    if not value: raise HTTPException(404,"Developer not found")
    return value

@app.patch("/api/developers/{developer_id}/stage",dependencies=[Depends(admin)])
def stage(developer_id:int,body:StagePatch,db:Session=Depends(get_db)):
    legacy={"APPROVED":"OUTREACH_APPROVED","VISITED_REPO":"REPO_VISITED","ACTIVATED":"FIRST_INTERACTION"}; requested=legacy.get(body.stage,body.stage)
    if requested not in FUNNEL_STAGES: raise HTTPException(422,"Invalid stage")
    value=db.get(Developer,developer_id)
    if not value: raise HTTPException(404,"Developer not found")
    record_event(db,value,requested,"MANUAL_VERIFIED","manual",metadata={"legacy_stage_endpoint":True}); db.commit(); return {"stage":value.current_funnel_stage,"next_best_action":value.next_best_action}

@app.get("/api/developers/{developer_id}/segments")
def segments(developer_id:int,db:Session=Depends(get_db)):
    return db.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer_id).order_by(DeveloperSegment.manual_override.desc(),DeveloperSegment.is_primary.desc())).all()

@app.post("/api/developers/{developer_id}/segments/override",dependencies=[Depends(admin)])
def override_segment(developer_id:int,body:SegmentOverride,db:Session=Depends(get_db)):
    developer=db.get(Developer,developer_id)
    if not developer: raise HTTPException(404,"Developer not found")
    allowed={"VOICE_APP_BUILDER","REALTIME_TELEPHONY_ENGINEER","SPEECH_ML_ENGINEER","INDIC_LANGUAGE_BUILDER","OSS_CONTRIBUTOR","DEVELOPER_EDUCATOR","UNKNOWN_DEVELOPER"}
    if body.segment_code not in allowed: raise HTTPException(422,"Invalid segment")
    for row in db.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer_id)): row.is_primary=False
    row=db.scalar(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer_id,DeveloperSegment.segment_code==body.segment_code,DeveloperSegment.manual_override.is_(True)))
    if not row: row=DeveloperSegment(developer_id=developer_id,segment_code=body.segment_code,confidence=1.0,classifier_version="manual-v2a",manual_override=True); db.add(row)
    row.is_primary=True; row.evidence_signal_id=body.evidence_signal_id; row.override_reason=body.reason
    developer.primary_segment_code=body.segment_code; db.commit(); return row

@app.get("/api/developers/{developer_id}/technologies")
def technologies(developer_id:int,db:Session=Depends(get_db)): return db.scalars(select(DeveloperTechnology).where(DeveloperTechnology.developer_id==developer_id)).all()

@app.get("/api/developers/{developer_id}/timeline")
def timeline(developer_id:int,db:Session=Depends(get_db)):
    developer=db.get(Developer,developer_id)
    if not developer: raise HTTPException(404,"Developer not found")
    return {"developer_id":developer_id,"stage":developer.current_funnel_stage,"next_best_action":developer.next_best_action,"next_action_reason":developer.next_action_reason,"events":db.scalars(select(EngagementEvent).where(EngagementEvent.developer_id==developer_id).order_by(EngagementEvent.event_at.desc())).all()}

@app.post("/api/developers/{developer_id}/events",dependencies=[Depends(admin)])
def add_event(developer_id:int,body:EngagementEventCreate,db:Session=Depends(get_db)):
    developer=db.get(Developer,developer_id)
    if not developer: raise HTTPException(404,"Developer not found")
    try: event=record_event(db,developer,body.event_type,body.evidence_level,body.source,body.event_at,body.campaign_id,body.metadata)
    except ValueError as exc: raise HTTPException(422,str(exc))
    db.commit(); return {"event_id":event.id,"stage":developer.current_funnel_stage,"next_best_action":developer.next_best_action}

@app.post("/api/developers/{developer_id}/organizations",dependencies=[Depends(admin)])
def link_organization(developer_id:int,body:OrganizationLinkCreate,db:Session=Depends(get_db)):
    if not db.get(Developer,developer_id): raise HTTPException(404,"Developer not found")
    organization=db.scalar(select(Organization).where((Organization.canonical_domain==body.canonical_domain) if body.canonical_domain else (Organization.github_org==body.github_org))) if (body.canonical_domain or body.github_org) else None
    if not organization:
        organization=Organization(name=body.name,canonical_domain=body.canonical_domain,github_org=body.github_org,profile_url=str(body.profile_url) if body.profile_url else None,metadata_json={}); db.add(organization); db.flush()
    link=DeveloperOrganization(developer_id=developer_id,organization_id=organization.id,relationship_type=body.relationship_type,evidence_url=str(body.evidence_url),manually_verified=body.manually_verified); db.add(link); db.commit(); return link

@app.post("/api/campaigns",dependencies=[Depends(admin)])
def create_campaign(body:CampaignCreate,db:Session=Depends(get_db)):
    campaign=Campaign(name=body.name,destination_url=str(body.destination_url),segment_code=body.segment_code,source=body.source,route=body.route,tracking_code=secrets.token_urlsafe(12)); db.add(campaign); db.commit(); return campaign

@app.get("/api/analytics/funnel")
def funnel(db:Session=Depends(get_db)): return funnel_analytics(db)

@app.get("/api/analytics/segments")
def segment_metrics(db:Session=Depends(get_db)): return segment_analytics(db)

@app.get("/api/analytics/messages")
def message_metrics(db:Session=Depends(get_db)): return message_analytics(db)

@app.get("/r/{tracking_code}")
def track(tracking_code:str,db:Session=Depends(get_db)):
    campaign=db.scalar(select(Campaign).where(Campaign.tracking_code==tracking_code,Campaign.active.is_(True)))
    if not campaign: raise HTTPException(404,"Tracking link not found")
    db.add(EngagementEvent(developer_id=None,event_type="REPO_VISITED",evidence_level="ATTRIBUTED",source="attributed_link",campaign_id=campaign.id,metadata_json={})); db.commit(); return RedirectResponse(campaign.destination_url,status_code=307)

@app.get("/api/connectors/health")
def connector_health(db:Session=Depends(get_db)): return db.scalars(select(Connector)).all()

@app.get("/api/digests/daily")
def digest(format:str="markdown",db:Session=Depends(get_db)):
    data=csv_digest(db,get_settings().app_timezone) if format=="csv" else markdown_digest(db,get_settings().app_timezone)
    media="text/csv" if format=="csv" else "text/markdown"; return Response(data,media_type=media)

@app.post("/api/import/manual-signals",dependencies=[Depends(admin)])
async def import_manual(file:UploadFile,db:Session=Depends(get_db)): return {"imported":import_csv_text(db,(await file.read()).decode())}
