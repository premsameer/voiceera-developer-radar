import math
from urllib.parse import quote
import streamlit as st
from sqlalchemy import select
from radar.analytics import funnel_analytics,segment_analytics
from radar.contributor import contributor_metrics
from radar.config import get_settings
from radar.db import SessionLocal,init_db
from radar.digest import csv_digest,markdown_digest
from radar.intelligence import FUNNEL_STAGES,record_event
from radar.models import Connector,ContributorEvent,ContributorPipeline,Developer,DeveloperOrganization,DeveloperSegment,DeveloperTechnology,Evaluation,MaintainerAlert,Organization,ReviewAction,ScanRun
from radar.queries import developer_rows
from radar.seed import seed
from radar.service import run_scan

st.set_page_config(page_title="VoiceERA Developer Radar",layout="wide")
init_db()
with SessionLocal() as db: seed(db)
PAGES=["Daily Radar","Contributor Pipeline","Developer Profile","Intelligence","Funnel Analytics","Sources & Health","Configuration","Run History"]
PAGE_COPY={
    "Daily Radar":("01 / RADAR","Developer intelligence, distilled.","Review fresh signals, qualify intent, and move the right builders forward."),
    "Contributor Pipeline":("02 / CONTRIBUTORS","From signal to contribution.","Track fork-local work and upstream pull requests as separate, evidence-backed paths."),
    "Developer Profile":("03 / PROFILE","See the person behind the signal.","Trace activity, technology, organizations, and verified funnel progress."),
    "Intelligence":("03 / INTELLIGENCE","Patterns worth acting on.","Understand how your developer audience is forming across segments."),
    "Funnel Analytics":("04 / FUNNEL","From discovery to conversation.","Measure verified movement without losing the evidence behind it."),
    "Sources & Health":("05 / SOURCES","A radar you can trust.","Keep every connector observable, current, and accountable."),
    "Configuration":("06 / CONFIGURATION","Simple controls. Clear boundaries.","Inspect source settings while keeping credentials out of the interface."),
    "Run History":("07 / HISTORY","Every scan leaves a trace.","Review completed runs, collection counts, and source-level errors."),
}
st.markdown("""
<style>
:root{--ink:#031011;--panel:#07191a;--panel-2:#0a2021;--cream:#f4efe6;--muted:rgba(244,239,230,.58);--line:rgba(244,239,230,.12);--cyan:#22bec6}
.stApp{background:var(--ink);color:var(--cream)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"]{right:1rem}
[data-testid="stSidebar"]{background:#051617;border-right:1px solid var(--line)}
[data-testid="stSidebar"]>div:first-child{padding-top:1.6rem}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:var(--muted)}
[data-testid="stSidebar"] div[role="radiogroup"]{gap:.3rem}
[data-testid="stSidebar"] div[role="radiogroup"] label{padding:.7rem .75rem;border:1px solid transparent;border-radius:.5rem;transition:none}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){background:rgba(34,190,198,.09);border-color:rgba(34,190,198,.28)}
.radar-nav{display:flex;flex-direction:column;gap:.3rem;margin:.25rem 0 1rem}.radar-nav a{color:var(--muted);text-decoration:none;padding:.72rem .8rem;border:1px solid transparent;border-radius:.5rem}.radar-nav a:hover{color:var(--cream);border-color:var(--line)}.radar-nav a.active{color:var(--cream);background:rgba(34,190,198,.09);border-color:rgba(34,190,198,.28)}.radar-nav a.active:before{content:'•';color:var(--cyan);margin-right:.65rem}
.block-container{max-width:1440px;padding-top:2.2rem;padding-bottom:4rem}
h1,h2,h3,p,label,button,input,textarea{font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
h1,h2,h3{color:var(--cream)!important;letter-spacing:-.035em}
h1{font-size:clamp(2.6rem,5vw,5.2rem)!important;line-height:.98!important;font-weight:800!important;max-width:950px;margin:.25rem 0 1rem!important}
h2{font-size:2rem!important;margin-top:2.5rem!important}
h3{font-size:1.25rem!important}
p,.stCaption,label{color:var(--muted)!important}
.brand{color:var(--cream);font-size:1.05rem;font-weight:750;letter-spacing:-.03em;margin-bottom:1.4rem}.brand b{color:var(--cyan)}
.eyebrow{color:var(--cyan);font-size:.72rem;font-weight:700;letter-spacing:.18em;text-transform:uppercase;margin-top:.4rem}
.hero-sub{font-size:1.12rem;line-height:1.6;max-width:720px;color:var(--muted);margin:0 0 2.4rem}
.hero-rule{height:1px;background:linear-gradient(90deg,var(--cyan),var(--line) 35%,transparent);margin:0 0 2rem}
[data-testid="stMetric"]{background:var(--panel);border:1px solid var(--line);border-radius:.65rem;padding:1rem .72rem;min-height:112px}
[data-testid="stMetricLabel"]{color:var(--muted);font-size:.76rem}
[data-testid="stMetricValue"]{color:var(--cream);font-size:clamp(1.25rem,2.2vw,2.1rem);font-weight:720;letter-spacing:-.04em}
.stButton>button,.stDownloadButton>button{border-radius:999px;border:1px solid rgba(34,190,198,.55);background:transparent;color:var(--cream);min-height:2.7rem;padding:.45rem 1.15rem}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--cyan);color:var(--cyan);background:rgba(34,190,198,.07)}
.stButton>button[kind="primary"]{background:var(--cyan);color:#021011;border-color:var(--cyan);font-weight:750}
[data-testid="stDataFrame"],div[data-testid="stExpander"],div[data-baseweb="select"]>div,input,textarea{border-color:var(--line)!important;border-radius:.55rem!important}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input{background:var(--panel-2)!important;color:var(--cream)!important;-webkit-text-fill-color:var(--cream)!important;caret-color:var(--cyan)!important}
[data-testid="stTextArea"] textarea::placeholder,[data-testid="stTextInput"] input::placeholder{color:rgba(244,239,230,.38)!important;-webkit-text-fill-color:rgba(244,239,230,.38)!important}
[data-testid="stTextArea"] textarea:focus,[data-testid="stTextInput"] input:focus{border-color:var(--cyan)!important;box-shadow:0 0 0 1px var(--cyan)!important}
div[data-testid="stExpander"]{background:rgba(7,25,26,.65)}
[data-testid="stAlert"]{background:var(--panel);border:1px solid var(--line);color:var(--cream)}
hr{border-color:var(--line)!important}
@media(max-width:800px){.block-container{padding-top:1rem}h1{font-size:2.65rem!important}.hero-sub{font-size:1rem}}
</style>
""",unsafe_allow_html=True)
st.sidebar.markdown('<div class="brand">voiceera<span style="color:#22bec6">°</span> radar</div>',unsafe_allow_html=True)
page=st.query_params.get("page","Daily Radar")
if page not in PAGES: page="Daily Radar"
st.sidebar.caption("Navigate")
links="".join(f'<a class="{"active" if item==page else ""}" href="?page={quote(item)}" target="_self">{item}</a>' for item in PAGES)
st.sidebar.markdown(f'<nav class="radar-nav">{links}</nav>',unsafe_allow_html=True)
st.sidebar.caption("Signal in. Clarity out.")
eyebrow,title,description=PAGE_COPY[page]
st.markdown(f'<div class="eyebrow">{eyebrow}</div><h1>{title}</h1><p class="hero-sub">{description}</p><div class="hero-rule"></div>',unsafe_allow_html=True)


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

elif page=="Contributor Pipeline":
    with SessionLocal() as db:
        metrics=contributor_metrics(db); c1,c2,c3,c4=st.columns(4)
        c1.metric("Contributors",metrics["denominator"]); c2.metric("Meaningful activity",f"{metrics['meaningful_activity_rate']:.0%}"); c3.metric("Upstream PR",f"{metrics['upstream_pr_rate']:.0%}"); c4.metric("Merged",metrics["merged"])
        alerts=db.scalars(select(MaintainerAlert).where(MaintainerAlert.status=="OPEN").order_by(MaintainerAlert.created_at.desc())).all()
        if alerts:
            st.subheader("Maintainer alerts")
            st.dataframe([{"severity":a.severity,"type":a.alert_type,"message":a.message,"created":a.created_at} for a in alerts],width="stretch",hide_index=True)
        rows=db.execute(select(ContributorPipeline,Developer).join(Developer,Developer.id==ContributorPipeline.developer_id).order_by(ContributorPipeline.latest_event_at.desc())).all()
        st.subheader("Pipeline")
        st.caption("Forks remain weak intent until a meaningful fork-local event occurs. Upstream PR stages are shown independently.")
        st.dataframe([{"developer":d.display_name or d.primary_handle,"github_login":d.primary_handle,"stage":p.stage,"attribution":p.attribution,"upstream":p.upstream_repository,"fork":p.fork_repository,"pr":p.pull_request_number,"checks":p.checks_state,"latest_activity":p.latest_event_at} for p,d in rows],width="stretch",hide_index=True)
        st.subheader("Conversion by stage")
        st.dataframe([{"stage":stage,"contributors":count} for stage,count in metrics["stages"].items()],width="stretch",hide_index=True)

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
            contribution_events=db.scalars(select(ContributorEvent).where(ContributorEvent.developer_id==d.id).order_by(ContributorEvent.occurred_at.desc())).all()
            if contribution_events:
                st.subheader("Contribution timeline")
                st.caption("Repository scope makes fork-local activity distinct from upstream pull-request activity.")
                st.dataframe([{"when":e.occurred_at,"event":e.event_type,"scope":e.repository_scope,"repository":e.fork_full_name if e.repository_scope=="FORK" else e.repository_full_name,"pull_request":e.pull_request_number,"attribution":e.attribution,"evidence":e.attribution_evidence,"url":e.canonical_url} for e in contribution_events],width="stretch",hide_index=True)

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
