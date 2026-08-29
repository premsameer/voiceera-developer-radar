from fastapi import Depends, FastAPI, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from .config import get_settings
from .db import get_db, init_db
from .digest import csv_digest, markdown_digest
from .importer import import_csv_text
from .models import Connector, Developer, Evaluation, ReviewAction, ScanRun, Signal
from .queries import developer_rows
from .schemas import DraftPatch, ScanRequest, StagePatch
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
    db.add(ReviewAction(evaluation_id=evaluation_id,action=action,draft_text=value.draft_text)); value.signal.developer.funnel_stage="APPROVED" if action=="APPROVE" else "ARCHIVED" if action=="REJECT" else "DISCOVERED"; db.commit(); return {"status":action}

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
    allowed={"DISCOVERED","QUALIFIED","APPROVED","CONTACTED","RESPONDED","VISITED_REPO","INSTALLED","ACTIVATED","CONTRIBUTED","ARCHIVED"}
    if body.stage not in allowed: raise HTTPException(422,"Invalid stage")
    value=db.get(Developer,developer_id)
    if not value: raise HTTPException(404,"Developer not found")
    value.funnel_stage=body.stage; db.commit(); return {"stage":body.stage}

@app.get("/api/connectors/health")
def connector_health(db:Session=Depends(get_db)): return db.scalars(select(Connector)).all()

@app.get("/api/digests/daily")
def digest(format:str="markdown",db:Session=Depends(get_db)):
    data=csv_digest(db,get_settings().app_timezone) if format=="csv" else markdown_digest(db,get_settings().app_timezone)
    media="text/csv" if format=="csv" else "text/markdown"; return Response(data,media_type=media)

@app.post("/api/import/manual-signals",dependencies=[Depends(admin)])
async def import_manual(file:UploadFile,db:Session=Depends(get_db)): return {"imported":import_csv_text(db,(await file.read()).decode())}

