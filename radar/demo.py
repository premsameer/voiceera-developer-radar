from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from .models import Intent
from .schemas import NormalizedSignal
from .service import persist_signal


def seed_demo(session: Session, count: int=20) -> int:
    topics=[("streaming WebRTC voice agent",Intent.BUILDING,"pipecat-ai/pipecat"),("multilingual speech-to-text benchmark",Intent.EVALUATING,"AI4Bharat/IndicConformer"),("telephony SIP integration",Intent.INTEGRATING,"livekit/agents"),("voice activity detection issue",Intent.TROUBLESHOOTING,"voiceera/voiceera")]
    added=0; now=datetime.now(timezone.utc)
    for i in range(count):
        title,intent,repo=topics[i%len(topics)]; at=now-timedelta(days=i%30)
        item=NormalizedSignal(source="github",external_id=f"demo-{i}",canonical_url=f"https://github.com/{repo}/issues/{1000+i}",actor_handle=f"demo-developer-{i:02d}",actor_display_name=f"Demo Developer {i:02d}",actor_profile_url=f"https://github.com/demo-developer-{i:02d}",observed_intent=intent,intent_evidence=f"Implemented {title} with Python API support",activity_type="pull_request" if i%3 else "issue",activity_title=title,activity_text=f"Implemented {title} with Python API support",activity_at=at,repository_name=repo,repository_url=f"https://github.com/{repo}",repository_topics=["voice-ai","speech","webrtc"],programming_languages=["Python","TypeScript"],discovery_query="seeded demo fixture",collected_at=now,raw_metadata={"github_node_id":f"demo-node-{i}","stars":100+i,"fork":False})
        if persist_signal(session,item): added+=1
    session.commit(); return added

