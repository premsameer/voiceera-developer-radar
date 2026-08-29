from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Connector, Opportunity


CONNECTORS = [
 ("github","GitHub",True,{"queries":["voice agent in:name,description,readme","topic:voice-ai","Indic speech in:name,description,readme"],"watchlist":[],"max_repositories":20}),
 ("reddit","Reddit",False,{"subreddits":["LocalLLaMA","MachineLearning","opensource","LanguageTechnology"],"queries":["voice AI","speech-to-text"]}),
 ("devto","DEV/Forem",True,{"tags":["voice","webrtc","machinelearning"]}),
 ("hackernews","Hacker News",True,{"max_items":100}),
 ("rss","RSS",False,{"feeds":[]}),
]
OPPORTUNITIES = [
 ("realtime-quickstart","Realtime multilingual voice quick start","TRY_TEMPLATE",["voice agent","realtime","multilingual"],"https://github.com/voiceera/voiceera","beginner"),
 ("webrtc-integration","WebRTC integration test","TEST_INTEGRATION",["webrtc","streaming","realtime"],"https://github.com/voiceera/voiceera","intermediate"),
 ("telephony-integration","Telephony/SIP integration test","TEST_INTEGRATION",["telephony","sip","calling"],"https://github.com/voiceera/voiceera","intermediate"),
 ("docs-feedback","Quick-start documentation feedback","DOCS",["tutorial","documentation","quick start"],"https://github.com/voiceera/voiceera","beginner"),
]


def seed(session: Session):
    for typ,name,enabled,config in CONNECTORS:
        if not session.scalar(select(Connector).where(Connector.type==typ)): session.add(Connector(type=typ,name=name,enabled=enabled,config_json=config))
    for slug,title,kind,topics,url,difficulty in OPPORTUNITIES:
        if not session.scalar(select(Opportunity).where(Opportunity.slug==slug)): session.add(Opportunity(slug=slug,title=title,activation_type=kind,description=title,required_topics_json=topics,difficulty=difficulty,url=url,owner="VoiceERA",active=True))
    session.commit()

