import streamlit as st
from sqlalchemy import select
from radar.config import get_settings
from radar.db import SessionLocal, init_db
from radar.digest import csv_digest, markdown_digest
from radar.models import Connector, Developer, Evaluation, ReviewAction, ScanRun
from radar.queries import developer_rows
from radar.seed import seed
from radar.service import run_scan

st.set_page_config(page_title="VoiceERA Developer Radar",layout="wide")
init_db()
with SessionLocal() as db: seed(db)
st.title("VoiceERA Developer Radar")
radar,profiles,sources,configuration,history=st.tabs(["Daily Radar","Developers","Sources & health","Configuration","Run history"])
with radar:
    with SessionLocal() as db:
        rows=developer_rows(db,get_settings().app_timezone)
        cols=st.columns(5); labels=[("Signals",len(rows)),("PASS",sum(x["qualification"]=="PASS" for x in rows)),("UNSURE",sum(x["qualification"]=="UNSURE" for x in rows)),("Approved",sum(x["funnel_status"]=="APPROVED" for x in rows)),("Rejected",sum(x["funnel_status"]=="ARCHIVED" for x in rows))]
        for col,(label,value) in zip(cols,labels): col.metric(label,value)
        if st.button("Run scan",type="primary"):
            with st.spinner("Scanning enabled sources…"):
                enabled=[x.type for x in db.scalars(select(Connector).where(Connector.enabled.is_(True)))]
                result=run_scan(db,enabled); st.success(f"Run {result.id}: {result.status}"); st.rerun()
        verdict=st.multiselect("Qualification",["PASS","UNSURE","FAIL"],default=["PASS","UNSURE","FAIL"])
        shown=[r for r in rows if r["qualification"] in verdict]
        st.dataframe(shown,use_container_width=True,hide_index=True,column_config={"profile":st.column_config.LinkColumn(),"activity_url":st.column_config.LinkColumn(),"opportunity_url":st.column_config.LinkColumn()})
        st.download_button("Download CSV",csv_digest(db,get_settings().app_timezone),"voiceera-radar.csv","text/csv")
        st.download_button("Download Markdown",markdown_digest(db,get_settings().app_timezone),"voiceera-radar.md","text/markdown")
        st.subheader("Review")
        for row in [r for r in shown if r["qualification"]=="PASS"][:10]:
            with st.expander(f"{row['developer']} · {row['score']} · {row['voiceera_route']}"):
                text=st.text_area("Draft",row["personalised_message"] or "",key=f"draft-{row['evaluation_id']}")
                a,e,r,m=st.columns(4)
                if a.button("Approve",key=f"a-{row['evaluation_id']}"):
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="APPROVE",draft_text=text)); db.get(Developer,row["id"]).funnel_stage="APPROVED"; db.commit(); st.rerun()
                if e.button("Save edit",key=f"e-{row['evaluation_id']}"):
                    ev=db.get(Evaluation,row["evaluation_id"]); db.add(ReviewAction(evaluation_id=ev.id,action="EDIT",draft_text=ev.draft_text,edited_text=text)); ev.draft_text=text; db.commit(); st.success("Saved")
                if r.button("Reject",key=f"r-{row['evaluation_id']}"):
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="REJECT",draft_text=text)); db.get(Developer,row["id"]).funnel_stage="ARCHIVED"; db.commit(); st.rerun()
                if m.button("Monitor",key=f"m-{row['evaluation_id']}"):
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="MONITOR",draft_text=text)); db.commit(); st.success("Monitoring")
with profiles:
    with SessionLocal() as db:
        for d in db.scalars(select(Developer)).all():
            with st.expander(f"{d.display_name or d.primary_handle} · {d.funnel_stage}"):
                st.write(d.profile_url or "No public profile URL")
                for s in sorted(d.signals,key=lambda x:x.activity_at,reverse=True): st.markdown(f"- {s.activity_at.isoformat()} [{s.activity_type}: {s.title}]({s.canonical_url})")
with sources:
    with SessionLocal() as db: st.dataframe([{"source":x.name,"enabled":x.enabled,"last_success":x.last_success_at,"cursor":x.last_cursor,"items":x.items_collected,"last_error":x.last_error or ""} for x in db.scalars(select(Connector)).all()],use_container_width=True)
with configuration:
    st.info("Connector configuration is stored in source_connectors.config_json and seeded from radar/seed.py. Secrets remain server-side in .env.")
    with SessionLocal() as db: st.json({x.type:x.config_json for x in db.scalars(select(Connector)).all()})
with history:
    with SessionLocal() as db: st.dataframe([{"id":x.id,"started":x.started_at,"completed":x.completed_at,"status":x.status,"counts":x.source_counts_json,"errors":x.error_summary} for x in db.scalars(select(ScanRun).order_by(ScanRun.id.desc())).all()],use_container_width=True)

