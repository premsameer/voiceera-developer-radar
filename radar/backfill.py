from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session,joinedload
from .intelligence import enrich_developer,update_next_action
from .models import Developer,Signal


def backfill_v2(session:Session):
    signals=session.scalars(select(Signal).options(joinedload(Signal.repository),joinedload(Signal.developer))).all(); enriched=0
    for signal in signals:
        repository=signal.repository
        item=SimpleNamespace(activity_type=signal.activity_type,activity_title=signal.title,activity_text=signal.excerpt,activity_at=signal.activity_at,repository_topics=repository.topics_json if repository else [],programming_languages=repository.languages_json if repository else [])
        enrich_developer(session,signal,item); enriched+=1
    session.flush()
    for developer in session.scalars(select(Developer)): update_next_action(session,developer)
    session.commit(); return enriched
