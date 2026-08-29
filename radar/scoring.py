from datetime import datetime, timezone
from .models import Intent, Route, Verdict
from .vocabulary import BOT_SUFFIXES, SEGMENTS, STRONG_TERMS, WEAK_TERMS


def is_bot(handle: str) -> bool:
    clean=handle.lower(); return clean.endswith(BOT_SUFFIXES) or clean in {"dependabot","renovate","github-actions"}


def classify_intent(activity_type: str, text: str) -> Intent:
    t=text.lower()
    if activity_type=="pull_request": return Intent.INTEGRATING if "integrat" in t else Intent.CONTRIBUTING
    if activity_type=="issue": return Intent.TROUBLESHOOTING
    if activity_type=="release": return Intent.LAUNCHING
    if "benchmark" in t or "versus" in t or " vs " in t: return Intent.EVALUATING
    if "tutorial" in t or "how to" in t: return Intent.LEARNING
    if "dataset" in t or "research" in t: return Intent.RESEARCHING
    if activity_type=="commit": return Intent.CONTRIBUTING
    return Intent.COMMUNITY_DISCUSSION


def evaluate(signal, now: datetime | None=None, weights: dict | None=None):
    now=now or datetime.now(timezone.utc); text=" ".join([signal.activity_title,signal.activity_text," ".join(signal.repository_topics)," ".join(signal.programming_languages)]).lower()
    strong=sum(term in text for term in STRONG_TERMS); weak=sum(term in text for term in WEAK_TERMS)
    hard=[]
    if is_bot(signal.actor_handle): hard.append("bot account")
    if not signal.intent_evidence: hard.append("missing evidence")
    if strong<1 and weak<2: hard.append("insufficient voice-AI terms")
    days=max(0,(now.date()-signal.activity_at.date()).days)
    score=min(30,strong*15+weak*5)+ (20 if days<=7 else 14 if days<=14 else 8 if days<=30 else 0)
    technical=sum(term in text for term in ["python","typescript","webrtc","telephony","api","model","streaming","sip"])
    score+=min(20,technical*5)
    score+=15 if signal.activity_type in {"pull_request","issue","commit","release"} else 7
    score+=15 if strong else (7 if weak>=2 else 0)
    if hard: score=min(score,49)
    verdict=Verdict.PASS if score>=70 and not hard else Verdict.UNSURE if score>=50 and not hard else Verdict.FAIL
    segment="Voice-agent application developer"
    for key,value in SEGMENTS.items():
        if key in text: segment=value; break
    reason=("; ".join(hard) if hard else f"{strong} strong and {weak} supporting relevance terms; {days} days old; {signal.activity_type} evidence")
    return score,verdict,segment,reason


def choose_opportunity(signal, opportunities):
    text=(signal.activity_title+" "+signal.activity_text+" "+" ".join(signal.repository_topics)).lower()
    ranked=[]
    for opportunity in opportunities:
        overlap=sum(topic.lower() in text for topic in opportunity.required_topics_json)
        if overlap: ranked.append((overlap, 1 if opportunity.activation_type=="TEST_INTEGRATION" else 0, opportunity))
    if not ranked: return Route.GENERAL_INTRO,None
    opportunity=max(ranked,key=lambda x:(x[0],x[1]))[2]
    route=Route.ISSUE if opportunity.activation_type in {"GOOD_FIRST_ISSUE","CODE_CONTRIBUTION"} else Route.INTEGRATION if opportunity.activation_type=="TEST_INTEGRATION" else Route.USE_CASE
    return route,opportunity


def draft_message(signal, route, opportunity=None):
    date=signal.activity_at.date().isoformat(); excerpt=signal.intent_evidence.strip().replace("\n"," ")[:140]
    if route==Route.MONITOR: return None
    if opportunity:
        return f"On {date}, your {signal.activity_type} in {signal.repository_name or signal.source} focused on “{excerpt}”. That overlaps with VoiceERA’s {opportunity.title}. Would you be open to trying the setup and sharing one quick impression? {opportunity.url}"
    return f"On {date}, your {signal.activity_type} in {signal.repository_name or signal.source} focused on “{excerpt}”. VoiceERA is an open-source multilingual voice-AI stack, and that work looks technically adjacent. Open to taking a quick look and sharing whether it fits your work? https://github.com/voiceera/voiceera"
