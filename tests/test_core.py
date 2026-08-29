from datetime import datetime, timedelta, timezone
from radar.demo import seed_demo
from radar.models import Route, Verdict
from radar.queries import days_since, developer_rows
from radar.scoring import choose_opportunity, classify_intent, draft_message, evaluate, is_bot
from radar.schemas import NormalizedSignal
from radar.models import Connector
from radar.service import persist_signal, run_scan
from unittest.mock import patch


def signal(**overrides):
    values=dict(source="github",external_id="x1",canonical_url="https://github.com/o/r/pull/1",actor_handle="human",actor_profile_url="https://github.com/human",intent_evidence="WebRTC realtime voice agent integration using Python API",activity_type="pull_request",activity_title="Add WebRTC voice agent",activity_text="WebRTC realtime voice agent integration using Python API",activity_at=datetime.now(timezone.utc)-timedelta(days=2),repository_name="o/r",repository_url="https://github.com/o/r",repository_topics=["voice-ai","webrtc"],programming_languages=["Python"],discovery_query="test",collected_at=datetime.now(timezone.utc))
    values.update(overrides); return NormalizedSignal(**values)


def test_normalization_and_intent():
    item=signal(); assert str(item.canonical_url).startswith("https://"); assert classify_intent("issue","broken voice stream").value=="TROUBLESHOOTING"

def test_bot_exclusion():
    assert is_bot("dependabot[bot]"); score,verdict,_,reason=evaluate(signal(actor_handle="renovate-bot")); assert verdict==Verdict.FAIL and "bot" in reason

def test_scoring_pass_and_dated_proof():
    score,verdict,_,reason=evaluate(signal()); assert score>=70 and verdict==Verdict.PASS and "days old" in reason

def test_dynamic_recency():
    assert days_since(datetime.now(timezone.utc)-timedelta(days=5),"Asia/Kolkata") in {4,5}

def test_matching_and_fallback(db):
    opportunities=list(db.query(__import__("radar.models",fromlist=["Opportunity"]).Opportunity).all())
    route,opportunity=choose_opportunity(signal(),opportunities); assert route==Route.INTEGRATION and opportunity
    route,opportunity=choose_opportunity(signal(activity_text="voice synthesis",activity_title="voice synthesis",repository_topics=[]),[]); assert route==Route.GENERAL_INTRO and opportunity is None

def test_message_grounding(db):
    item=signal(); route,opp=choose_opportunity(item,list(db.query(__import__("radar.models",fromlist=["Opportunity"]).Opportunity).all())); message=draft_message(item,route,opp)
    assert item.activity_at.date().isoformat() in message and str(opp.url) in message and len(message.split())<90

def test_dedup_and_complete_rows(db):
    assert seed_demo(db,20)==20; assert seed_demo(db,20)==0
    rows=developer_rows(db,"Asia/Kolkata"); assert len(rows)==20
    required={"observed_intent","intent_evidence","repository","last_activity","days_since_activity","qualification","score","reason","voiceera_route","personalised_message","funnel_status"}
    assert required.issubset(rows[0])

def test_naive_sqlite_checkpoint_is_normalized(db):
    connector=db.query(Connector).filter_by(type="github").one()
    connector.last_success_at=datetime.now().replace(microsecond=0); db.commit()
    with patch("radar.service.adapter_for") as factory:
        factory.return_value.collect.return_value=[]
        result=run_scan(db,["github"])
    assert result.status=="SUCCESS"
    since=factory.return_value.collect.call_args.args[0]
    assert since.tzinfo is not None

def test_existing_naive_developer_timestamp_is_normalized(db):
    first=signal(external_id="naive-1",canonical_url="https://github.com/o/r/pull/naive-1")
    assert persist_signal(db,first); db.commit()
    developer=first.actor_handle
    stored=db.query(__import__("radar.models",fromlist=["Developer"]).Developer).filter_by(primary_handle=developer).one()
    stored.latest_activity_at=stored.latest_activity_at.replace(tzinfo=None)
    later=signal(external_id="naive-2",canonical_url="https://github.com/o/r/pull/naive-2",activity_at=datetime.now(timezone.utc))
    assert persist_signal(db,later)
