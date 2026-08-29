from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import DeveloperSegment, DeveloperTechnology, EngagementEvent, Intent

SEGMENT_RULES={
    "VOICE_APP_BUILDER":["voice agent","voice app","conversational voice","assistant"],
    "REALTIME_TELEPHONY_ENGINEER":["webrtc","sip","telephony","calling","realtime audio","streaming audio"],
    "SPEECH_ML_ENGINEER":["speech-to-text","text-to-speech","stt","tts","vad","diarization","inference","speech recognition"],
    "INDIC_LANGUAGE_BUILDER":["indic","hindi","tamil","telugu","kannada","malayalam","marathi","bengali","bhashini","ai4bharat"],
    "OSS_CONTRIBUTOR":["pull_request","commit","documentation","test"],
    "DEVELOPER_EDUCATOR":["tutorial","workshop","article","how to","benchmark"],
}
TECHNOLOGY_RULES={
    "LANGUAGE":{"Python":["python"],"TypeScript":["typescript"],"JavaScript":["javascript"],"Go":["golang"," go "],"Rust":["rust"]},
    "FRAMEWORK":{"WebRTC":["webrtc"],"LiveKit":["livekit"],"Pipecat":["pipecat"],"Vocode":["vocode"],"FastAPI":["fastapi"]},
    "SPEECH":{"Whisper":["whisper"],"Deepgram":["deepgram"],"ElevenLabs":["elevenlabs"],"VAD":["voice activity detection"," vad "]},
    "TELEPHONY":{"SIP":[" sip "],"Twilio":["twilio"],"Vonage":["vonage"]},
    "DEPLOYMENT":{"Docker":["docker"],"Kubernetes":["kubernetes","k8s"],"Self-hosted":["self-hosted","on-prem"]},
    "LANGUAGE_REGION":{"Indic":["indic"],"Hindi":["hindi"],"Tamil":["tamil"],"Telugu":["telugu"]},
}
INTENT_BASE={"release":95,"repository":90,"issue":80,"pull_request":80,"benchmark":70,"article":65,"comment":40,"commit":80}
FUNNEL_STAGES=["DISCOVERED","QUALIFIED","OUTREACH_APPROVED","CONTACTED","RESPONDED","REPO_VISITED","DOCS_VISITED","INSTALL_ATTEMPTED","INSTALLED","FIRST_INTERACTION","PROJECT_CREATED","RETURNED_14D","CONTRIBUTED","ARCHIVED"]


def _text(item):
    return f" {item.activity_type} {item.activity_title} {item.activity_text} {' '.join(item.repository_topics)} {' '.join(item.programming_languages)} ".lower()


def segment_codes(item):
    text=_text(item); found=[]
    for code,terms in SEGMENT_RULES.items():
        if any(term in text for term in terms): found.append(code)
    if item.activity_type in {"pull_request","commit"} and "OSS_CONTRIBUTOR" not in found: found.append("OSS_CONTRIBUTOR")
    return found or ["UNKNOWN_DEVELOPER"]


def intent_strength(item, relevant_activity_count:int=1):
    text=_text(item); key="benchmark" if "benchmark" in text or "comparison" in text else item.activity_type
    base=INTENT_BASE.get(key,55 if item.activity_type=="post" else 40)
    now=datetime.now(timezone.utc); at=item.activity_at if item.activity_at.tzinfo else item.activity_at.replace(tzinfo=timezone.utc); days=max(0,(now.date()-at.date()).days)
    final=base+(10 if days<=7 else 5 if days<=14 else 0)+(10 if relevant_activity_count>=2 else 0)
    if any(term in text for term in ["webrtc","telephony","multilingual","voice agent","speech-to-text","text-to-speech"]): final+=10
    return base,min(100,final)


def enrich_developer(session:Session, signal, item):
    developer=signal.developer
    count=len(developer.signals) if developer.signals else 1
    base,final=intent_strength(item,count); signal.intent_strength_base=base; signal.intent_strength_final=final
    codes=segment_codes(item)
    existing={x.segment_code for x in session.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer.id,DeveloperSegment.manual_override.is_(False)))}
    for index,code in enumerate(codes):
        if code not in existing: session.add(DeveloperSegment(developer_id=developer.id,segment_code=code,is_primary=index==0,confidence=1.0 if code!="UNKNOWN_DEVELOPER" else 0.3,evidence_signal_id=signal.id))
    if final>=developer.intent_strength:
        developer.intent_strength=final; developer.primary_segment_code=codes[0]
        for row in session.scalars(select(DeveloperSegment).where(DeveloperSegment.developer_id==developer.id,DeveloperSegment.manual_override.is_(False))): row.is_primary=row.segment_code==codes[0]
    text=_text(item)
    for kind,names in TECHNOLOGY_RULES.items():
        for name,terms in names.items():
            if any(term in text for term in terms):
                exists=session.scalar(select(DeveloperTechnology).where(DeveloperTechnology.developer_id==developer.id,DeveloperTechnology.technology_type==kind,DeveloperTechnology.technology_name==name,DeveloperTechnology.evidence_signal_id==signal.id))
                if not exists: session.add(DeveloperTechnology(developer_id=developer.id,technology_type=kind,technology_name=name,evidence_signal_id=signal.id,confidence=1.0))
    update_next_action(session,developer)


def derive_funnel(events):
    if not events: return "DISCOVERED"
    stages={e.event_type for e in events}; return max(stages,key=lambda x:FUNNEL_STAGES.index(x) if x in FUNNEL_STAGES else -1)


def next_action(stage:str,latest_event_at:datetime|None=None,now:datetime|None=None):
    now=now or datetime.now(timezone.utc)
    if stage in {"DISCOVERED","QUALIFIED"}: return "REVIEW_MESSAGE","Qualified developer has no approved outreach"
    if stage=="OUTREACH_APPROVED": return "SEND_MANUALLY","Approved message is ready for a human to send"
    if stage=="CONTACTED":
        at=latest_event_at or now; at=at if at.tzinfo else at.replace(tzinfo=timezone.utc); days=(now-at).days
        return ("WAIT","Contacted fewer than 7 days ago") if days<7 else ("PREPARE_FOLLOW_UP","No response after 7 days") if days<=14 else ("MONITOR","Follow-up window has passed")
    mapping={"RESPONDED":("SHARE_QUICK_START","Response recorded without repository visit"),"REPO_VISITED":("SHARE_INSTALL_HELP","Repository visited without install"),"DOCS_VISITED":("SHARE_INSTALL_HELP","Documentation visited without install"),"INSTALL_ATTEMPTED":("ASK_FOR_BLOCKER","Install attempt has not completed"),"INSTALLED":("SHARE_SMALLEST_EXAMPLE","Installed without a first interaction"),"FIRST_INTERACTION":("ASK_INTENDED_USE_CASE","First interaction completed"),"PROJECT_CREATED":("OFFER_ISSUE_OR_INTEGRATION","A project was created"),"RETURNED_14D":("OFFER_ISSUE_OR_INTEGRATION","Developer returned after 14 days"),"CONTRIBUTED":("RECOGNIZE_CONTRIBUTOR","Contribution recorded"),"ARCHIVED":("NONE","Developer is archived")}
    return mapping.get(stage,("MONITOR",f"No rule for {stage}"))


def update_next_action(session:Session,developer):
    events=list(session.scalars(select(EngagementEvent).where(EngagementEvent.developer_id==developer.id).order_by(EngagementEvent.event_at)))
    stage=derive_funnel(events)
    if not events and developer.funnel_stage in FUNNEL_STAGES: stage=developer.funnel_stage
    latest=events[-1].event_at if events else None; action,reason=next_action(stage,latest)
    developer.current_funnel_stage=stage; developer.funnel_stage=stage; developer.next_best_action=action; developer.next_action_reason=reason
    return stage,action


def record_event(session:Session,developer,event_type:str,evidence_level:str,source:str,event_at=None,campaign_id=None,metadata=None):
    if event_type not in FUNNEL_STAGES: raise ValueError("Unsupported funnel event")
    event=EngagementEvent(developer_id=developer.id,event_type=event_type,event_at=event_at or datetime.now(timezone.utc),evidence_level=evidence_level,source=source,campaign_id=campaign_id,metadata_json=metadata or {})
    session.add(event); session.flush(); update_next_action(session,developer); return event
