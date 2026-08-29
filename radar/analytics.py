from collections import Counter,defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Developer,EngagementEvent,Evaluation,Signal
from .intelligence import FUNNEL_STAGES


def segment_analytics(session:Session,minimum_sample:int=10):
    developers=list(session.scalars(select(Developer)))
    grouped=defaultdict(list)
    for d in developers: grouped[d.primary_segment_code].append(d)
    return [{"segment":segment,"developers":len(items),"qualified":sum(d.current_funnel_stage!="DISCOVERED" or any(s.evaluation and s.evaluation.verdict=="PASS" for s in d.signals) for d in items),"first_interactions":sum(d.current_funnel_stage in FUNNEL_STAGES[FUNNEL_STAGES.index("FIRST_INTERACTION"):] for d in items),"small_sample":len(items)<minimum_sample} for segment,items in sorted(grouped.items())]


def funnel_analytics(session:Session,minimum_sample:int=10):
    developers=list(session.scalars(select(Developer))); counts=Counter(d.current_funnel_stage for d in developers); total=len(developers)
    return {"denominator":total,"small_sample":total<minimum_sample,"stages":[{"stage":stage,"current":counts[stage],"reached":sum(FUNNEL_STAGES.index(d.current_funnel_stage)>=i for d in developers if d.current_funnel_stage in FUNNEL_STAGES)} for i,stage in enumerate(FUNNEL_STAGES)]}


def message_analytics(session:Session,minimum_sample:int=10):
    rows=session.execute(select(Evaluation.recommended_route,Evaluation.verdict)).all(); grouped=defaultdict(lambda:{"evaluations":0,"pass":0})
    for route,verdict in rows: grouped[route]["evaluations"]+=1; grouped[route]["pass"]+=verdict=="PASS"
    return [{"route":route,**values,"small_sample":values["evaluations"]<minimum_sample} for route,values in grouped.items()]
