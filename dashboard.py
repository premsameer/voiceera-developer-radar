import math
import streamlit as st
from sqlalchemy import select
from radar.analytics import funnel_analytics,segment_analytics
from radar.config import get_settings
from radar.db import SessionLocal,init_db
from radar.digest import csv_digest,markdown_digest
from radar.intelligence import FUNNEL_STAGES,record_event
from radar.models import Connector,Developer,DeveloperOrganization,DeveloperSegment,DeveloperTechnology,Evaluation,Organization,ReviewAction,ScanRun
from radar.queries import developer_rows
from radar.seed import seed
from radar.service import run_scan

st.set_page_config(page_title="VoiceERA Developer Radar",layout="wide")
init_db()
with SessionLocal() as db: seed(db)
PAGES=["Daily Radar","Developer Profile","Intelligence","Funnel Analytics","Sources & Health","Configuration","Run History"]
page=st.sidebar.radio("Navigate",PAGES)
st.sidebar.caption("Only the selected page is rendered.")
st.title("VoiceERA Developer Radar")


def select_developer(db):
    developers=db.scalars(select(Developer).order_by(Developer.latest_activity_at.desc())).all()
    lookup={f"{d.display_name or d.primary_handle} (@{d.primary_handle})":d for d in developers}
    if not lookup: st.info("No developers yet."); return None
    return lookup[st.selectbox("Developer",list(lookup))]


if page=="Daily Radar":
    with SessionLocal() as db:
        rows=developer_rows(db,get_settings().app_timezone)
        cols=st.columns(5); labels=[("Developers",len(rows)),("PASS",sum(x["qualification"]=="PASS" for x in rows)),("UNSURE",sum(x["qualification"]=="UNSURE" for x in rows)),("Approved",sum(x["funnel_status"]=="OUTREACH_APPROVED" for x in rows)),("Archived",sum(x["funnel_status"]=="ARCHIVED" for x in rows))]
        for col,(label,value) in zip(cols,labels): col.metric(label,value)
        if st.button("Run scan",type="primary"):
            with st.spinner("Scanning enabled sources…"):
                enabled=[x.type for x in db.scalars(select(Connector).where(Connector.enabled.is_(True)))]
                result=run_scan(db,enabled); st.success(f"Run {result.id}: {result.status}"); st.rerun()
        verdicts=st.multiselect("Qualification",["PASS","UNSURE","FAIL"],default=["PASS","UNSURE","FAIL"])
        query=st.text_input("Search developer, repository, activity or segment").strip().lower()
        filtered=[r for r in rows if r["qualification"] in verdicts and (not query or query in " ".join(str(r.get(k) or "") for k in ["developer","handle","repository","recent_activity","primary_segment"]).lower())]
        page_size=st.selectbox("Rows per page",[25,50,100],index=0)
        total_pages=max(1,math.ceil(len(filtered)/page_size)); page_number=st.number_input("Page",1,total_pages,1)
        start=(page_number-1)*page_size; shown=filtered[start:start+page_size]
        fields=["developer","handle","primary_segment","intent_strength","observed_intent","repository","recent_activity","days_since_activity","qualification","score","voiceera_route","matched_opportunity","funnel_status","next_best_action"]
        st.caption(f"Showing {start+1 if filtered else 0}–{min(start+page_size,len(filtered))} of {len(filtered)}")
        st.dataframe([{k:r.get(k) for k in fields} for r in shown],width="stretch",hide_index=True)
        with st.expander("Exports"):
            st.download_button("Download CSV",csv_digest(db,get_settings().app_timezone),"voiceera-radar.csv","text/csv")
            st.download_button("Download Markdown",markdown_digest(db,get_settings().app_timezone),"voiceera-radar.md","text/markdown")
        pass_rows=[r for r in filtered if r["qualification"]=="PASS"]
        if pass_rows:
            st.subheader("Review one qualified developer")
            options={f"{r['developer']} · {r['score']} · {r['voiceera_route']}":r for r in pass_rows}; row=options[st.selectbox("Review candidate",list(options))]
            text=st.text_area("Draft",row["personalised_message"] or "",height=140); a,e,rj,m=st.columns(4)
            if a.button("Approve"):
                db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="APPROVE",draft_text=text)); record_event(db,db.get(Developer,row["id"]),"OUTREACH_APPROVED","MANUAL_VERIFIED","review"); db.commit(); st.rerun()
            if e.button("Save edit"):
                evaluation=db.get(Evaluation,row["evaluation_id"]); db.add(ReviewAction(evaluation_id=evaluation.id,action="EDIT",draft_text=evaluation.draft_text,edited_text=text)); evaluation.draft_text=text; db.commit(); st.success("Saved")
            if rj.button("Reject"):
                db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="REJECT",draft_text=text)); record_event(db,db.get(Developer,row["id"]),"ARCHIVED","MANUAL_VERIFIED","review"); db.commit(); st.rerun()
            if m.button("Monitor"):
                db.add(ReviewAction(evaluation_id=row["evaluation_id"],action="MONITOR",draft_text=text)); db.commit(); st.success("Monitoring")

elif page=="Developer Profile":
    with SessionLocal() as db:
        d=select_developer(db)
        if d:
            st.subheader(d.display_name or d.primary_handle); st.write(d.profile_url or "No public profile URL")
            c1,c2,c3=st.columns(3); c1.metric("Segment",d.primary_segment_code); c2.metric("Intent strength",d.intent_strength); c3.metric("Stage",d.current_funnel_stage)
            st.info(f"Next: {d.next_best_action} — {d.next_action_reason or ''}")
            segments=db.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==d.id)).all(); st.write("Segments",[{"code":x.segment_code,"primary":x.is_primary,"manual":x.manual_override,"reason":x.override_reason,"evidence_signal":x.evidence_signal_id} for x in segments])
            with st.expander("Override primary segment"):
                code=st.selectbox("Segment",["VOICE_APP_BUILDER","REALTIME_TELEPHONY_ENGINEER","SPEECH_ML_ENGINEER","INDIC_LANGUAGE_BUILDER","OSS_CONTRIBUTOR","DEVELOPER_EDUCATOR","UNKNOWN_DEVELOPER"]); reason=st.text_input("Reason")
                if st.button("Save override"):
                    if len(reason.strip())<3: st.error("A reason is required.")
                    else:
                        for row in segments: row.is_primary=False
                        evidence=max(d.signals,key=lambda x:x.activity_at).id if d.signals else None
                        manual=db.scalar(select(DeveloperSegment).where(DeveloperSegment.developer_id==d.id,DeveloperSegment.segment_code==code,DeveloperSegment.manual_override.is_(True)))
                        if not manual: manual=DeveloperSegment(developer_id=d.id,segment_code=code,confidence=1.0,classifier_version="manual-v2a",manual_override=True); db.add(manual)
                        manual.is_primary=True; manual.evidence_signal_id=evidence; manual.override_reason=reason; d.primary_segment_code=code; db.commit(); st.rerun()
            technologies=db.scalars(select(DeveloperTechnology).where(DeveloperTechnology.developer_id==d.id)).all(); st.write("Technologies",[{"type":x.technology_type,"name":x.technology_name,"evidence_signal":x.evidence_signal_id} for x in technologies])
            links=db.execute(select(DeveloperOrganization,Organization).join(Organization,Organization.id==DeveloperOrganization.organization_id).where(DeveloperOrganization.developer_id==d.id)).all(); st.write("Organizations",[{"name":org.name,"relationship":link.relationship_type,"evidence":link.evidence_url} for link,org in links])
            with st.expander("Add verified organization"):
                name=st.text_input("Organization name"); url=st.text_input("Public evidence URL"); relationship=st.selectbox("Relationship",["MEMBER","EMPLOYEE","MAINTAINER","CONTRIBUTOR","MANUAL_VERIFIED"])
                if st.button("Save organization"):
                    if not name.strip() or not url.startswith("http"): st.error("Name and public evidence URL are required.")
                    else:
                        org=Organization(name=name.strip(),profile_url=url,metadata_json={}); db.add(org); db.flush(); db.add(DeveloperOrganization(developer_id=d.id,organization_id=org.id,relationship_type=relationship,evidence_url=url,manually_verified=True)); db.commit(); st.rerun()
            with st.expander("Record funnel event"):
                event_type=st.selectbox("Event",FUNNEL_STAGES); note=st.text_input("Evidence/note")
                if st.button("Add verified event"):
                    record_event(db,d,event_type,"MANUAL_VERIFIED","manual",metadata={"note":note}); db.commit(); st.rerun()
            st.subheader("Activity timeline")
            for signal in sorted(d.signals,key=lambda x:x.activity_at,reverse=True): st.markdown(f"- {signal.activity_at.isoformat()} [{signal.activity_type}: {signal.title}]({signal.canonical_url})")

elif page=="Intelligence":
    with SessionLocal() as db:
        st.subheader("Developer segmentation"); st.dataframe(segment_analytics(db),width="stretch",hide_index=True); st.caption("Small-sample warnings apply below 10 developers per segment.")
elif page=="Funnel Analytics":
    with SessionLocal() as db:
        data=funnel_analytics(db); st.metric("Developers",data["denominator"])
        if data["small_sample"]: st.warning("Small sample: interpret conversion cautiously.")
        st.dataframe(data["stages"],width="stretch",hide_index=True)
elif page=="Sources & Health":
    with SessionLocal() as db: st.dataframe([{"source":x.name,"enabled":x.enabled,"last_success":x.last_success_at,"cursor":x.last_cursor,"items":x.items_collected,"last_error":x.last_error or ""} for x in db.scalars(select(Connector)).all()],width="stretch",hide_index=True)
elif page=="Configuration":
    st.info("Connector configuration is stored server-side. Secrets remain in .env.")
    with SessionLocal() as db: st.json({x.type:x.config_json for x in db.scalars(select(Connector)).all()})
elif page=="Run History":
    with SessionLocal() as db: st.dataframe([{"id":x.id,"started":x.started_at,"completed":x.completed_at,"status":x.status,"counts":x.source_counts_json,"errors":x.error_summary} for x in db.scalars(select(ScanRun).order_by(ScanRun.id.desc())).all()],width="stretch",hide_index=True)
