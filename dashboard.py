import streamlit as st
from sqlalchemy import select
from radar.config import get_settings
from radar.db import SessionLocal, init_db
from radar.digest import csv_digest, markdown_digest
from radar.models import Connector,Developer,DeveloperOrganization,DeveloperSegment,DeveloperTechnology,EngagementEvent,Evaluation,Organization,ReviewAction,ScanRun
from radar.intelligence import FUNNEL_STAGES,record_event
from radar.analytics import funnel_analytics,segment_analytics
from radar.queries import developer_rows
from radar.seed import seed
from radar.service import run_scan

st.set_page_config(page_title="VoiceERA Developer Radar",layout="wide")
init_db()
with SessionLocal() as db: seed(db)
st.title("VoiceERA Developer Radar")
radar,profiles,intelligence,funnel,sources,configuration,history=st.tabs(["Daily Radar","Developers","Intelligence","Funnel analytics","Sources & health","Configuration","Run history"])
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
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="APPROVE",draft_text=text)); record_event(db,db.get(Developer,row["id"]),"OUTREACH_APPROVED","MANUAL_VERIFIED","review"); db.commit(); st.rerun()
                if e.button("Save edit",key=f"e-{row['evaluation_id']}"):
                    ev=db.get(Evaluation,row["evaluation_id"]); db.add(ReviewAction(evaluation_id=ev.id,action="EDIT",draft_text=ev.draft_text,edited_text=text)); ev.draft_text=text; db.commit(); st.success("Saved")
                if r.button("Reject",key=f"r-{row['evaluation_id']}"):
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="REJECT",draft_text=text)); record_event(db,db.get(Developer,row["id"]),"ARCHIVED","MANUAL_VERIFIED","review"); db.commit(); st.rerun()
                if m.button("Monitor",key=f"m-{row['evaluation_id']}"):
                    db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="MONITOR",draft_text=text)); db.commit(); st.success("Monitoring")
with profiles:
    with SessionLocal() as db:
        for d in db.scalars(select(Developer)).all():
            with st.expander(f"{d.display_name or d.primary_handle} · {d.primary_segment_code} · {d.current_funnel_stage}"):
                st.write(d.profile_url or "No public profile URL")
                st.metric("Intent strength",d.intent_strength); st.info(f"Next: {d.next_best_action} — {d.next_action_reason or ''}")
                segments=db.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==d.id)).all(); st.write("Segments",[{"code":x.segment_code,"primary":x.is_primary,"manual":x.manual_override,"evidence_signal":x.evidence_signal_id} for x in segments])
                override_code=st.selectbox("Override primary segment",["VOICE_APP_BUILDER","REALTIME_TELEPHONY_ENGINEER","SPEECH_ML_ENGINEER","INDIC_LANGUAGE_BUILDER","OSS_CONTRIBUTOR","DEVELOPER_EDUCATOR","UNKNOWN_DEVELOPER"],key=f"segment-{d.id}")
                override_reason=st.text_input("Override reason",key=f"segment-reason-{d.id}")
                if st.button("Save segment override",key=f"segment-save-{d.id}"):
                    if len(override_reason.strip())<3: st.error("A reason is required.")
                    else:
                        for segment in segments: segment.is_primary=False
                        evidence=max(d.signals,key=lambda x:x.activity_at).id if d.signals else None
                        manual=db.scalar(select(DeveloperSegment).where(DeveloperSegment.developer_id==d.id,DeveloperSegment.segment_code==override_code,DeveloperSegment.manual_override.is_(True)))
                        if not manual: manual=DeveloperSegment(developer_id=d.id,segment_code=override_code,confidence=1.0,classifier_version="manual-v2a",manual_override=True); db.add(manual)
                        manual.is_primary=True; manual.evidence_signal_id=evidence; manual.override_reason=override_reason; d.primary_segment_code=override_code; db.commit(); st.rerun()
                technologies=db.scalars(select(DeveloperTechnology).where(DeveloperTechnology.developer_id==d.id)).all(); st.write("Technologies",[{"type":x.technology_type,"name":x.technology_name,"evidence_signal":x.evidence_signal_id} for x in technologies])
                links=db.execute(select(DeveloperOrganization,Organization).join(Organization,Organization.id==DeveloperOrganization.organization_id).where(DeveloperOrganization.developer_id==d.id)).all(); st.write("Organizations",[{"name":org.name,"relationship":link.relationship_type,"evidence":link.evidence_url} for link,org in links])
                org_name=st.text_input("Organization name",key=f"org-name-{d.id}"); org_url=st.text_input("Organization evidence URL",key=f"org-url-{d.id}"); relationship=st.selectbox("Relationship",["MEMBER","EMPLOYEE","MAINTAINER","CONTRIBUTOR","MANUAL_VERIFIED"],key=f"org-rel-{d.id}")
                if st.button("Add verified organization",key=f"org-save-{d.id}"):
                    if not org_name.strip() or not org_url.startswith("http"): st.error("Name and public evidence URL are required.")
                    else:
                        org=Organization(name=org_name.strip(),profile_url=org_url,metadata_json={}); db.add(org); db.flush(); db.add(DeveloperOrganization(developer_id=d.id,organization_id=org.id,relationship_type=relationship,evidence_url=org_url,manually_verified=True)); db.commit(); st.rerun()
                for s in sorted(d.signals,key=lambda x:x.activity_at,reverse=True): st.markdown(f"- {s.activity_at.isoformat()} [{s.activity_type}: {s.title}]({s.canonical_url})")
                event_type=st.selectbox("Record funnel event",FUNNEL_STAGES,key=f"event-{d.id}")
                note=st.text_input("Evidence/note",key=f"note-{d.id}")
                if st.button("Add verified event",key=f"add-event-{d.id}"):
                    record_event(db,d,event_type,"MANUAL_VERIFIED","manual",metadata={"note":note}); db.commit(); st.success(f"Recorded {event_type}"); st.rerun()
with intelligence:
    with SessionLocal() as db:
        metrics=segment_analytics(db); st.subheader("Developer segmentation")
        st.dataframe(metrics,width="stretch",hide_index=True)
        st.caption("Small-sample warnings apply below 10 developers per segment.")
        rows=developer_rows(db,get_settings().app_timezone)
        st.dataframe([{"developer":r["developer"],"segment":r["primary_segment"],"intent_strength":r["intent_strength"],"qualification":r["qualification"],"next_best_action":r["next_best_action"]} for r in rows],width="stretch",hide_index=True)
with funnel:
    with SessionLocal() as db:
        data=funnel_analytics(db); st.metric("Developers",data["denominator"])
        if data["small_sample"]: st.warning("Small sample: interpret conversion cautiously.")
        st.dataframe(data["stages"],width="stretch",hide_index=True)
with sources:
    with SessionLocal() as db: st.dataframe([{"source":x.name,"enabled":x.enabled,"last_success":x.last_success_at,"cursor":x.last_cursor,"items":x.items_collected,"last_error":x.last_error or ""} for x in db.scalars(select(Connector)).all()],use_container_width=True)
with configuration:
    st.info("Connector configuration is stored in source_connectors.config_json and seeded from radar/seed.py. Secrets remain server-side in .env.")
    with SessionLocal() as db: st.json({x.type:x.config_json for x in db.scalars(select(Connector)).all()})
with history:
    with SessionLocal() as db: st.dataframe([{"id":x.id,"started":x.started_at,"completed":x.completed_at,"status":x.status,"counts":x.source_counts_json,"errors":x.error_summary} for x in db.scalars(select(ScanRun).order_by(ScanRun.id.desc())).all()],use_container_width=True)
