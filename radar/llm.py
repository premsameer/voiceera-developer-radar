from pydantic import BaseModel, Field
from .models import Intent, Route, Verdict


class LLMEvaluation(BaseModel):
    verdict: Verdict; developer_segment: str; observed_intent: Intent; intent_evidence: str
    relevance_summary: str=Field(max_length=300); proof_quote: str=Field(max_length=200); proof_url: str; proof_date: str
    matched_opportunity_id: str|None=None; recommended_route: Route; reason: str=Field(max_length=500); confidence: float=Field(ge=0,le=1)


def evaluate_with_openai(signal, api_key: str, model: str="gpt-4.1-mini") -> LLMEvaluation:
    from openai import OpenAI
    client=OpenAI(api_key=api_key)
    prompt={"source":signal.source,"url":signal.canonical_url,"date":signal.activity_at.isoformat(),"activity_type":signal.activity_type,"title":signal.activity_title,"excerpt":signal.activity_text[:1000],"rules":["Use only supplied evidence","PASS requires proof URL/date/quote","Use UNKNOWN rather than guessing"]}
    result=client.responses.parse(model=model,input=[{"role":"system","content":"Classify public voice-AI developer activity. Return grounded schema data only."},{"role":"user","content":str(prompt)}],text_format=LLMEvaluation)
    parsed=result.output_parsed
    if parsed.verdict==Verdict.PASS and (not parsed.proof_quote or not parsed.proof_url or not parsed.proof_date): raise ValueError("Unsafe PASS: missing proof")
    return parsed

