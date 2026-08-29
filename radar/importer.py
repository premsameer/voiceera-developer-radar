import csv, io
from datetime import datetime, timezone
from .models import Intent
from .schemas import NormalizedSignal
from .service import persist_signal


def import_csv_text(session,text:str):
    count=0
    for i,row in enumerate(csv.DictReader(io.StringIO(text))):
        item=NormalizedSignal(source=row.get("source") or "linkedin_manual",external_id=row.get("external_id") or f"manual-{i}-{row['post_url']}",canonical_url=row["post_url"],actor_handle=row["author"],actor_display_name=row.get("display_name"),actor_profile_url=row.get("profile_url") or None,observed_intent=Intent(row.get("observed_intent") or "UNKNOWN"),intent_evidence=row["text_excerpt"],activity_type=row.get("activity_type") or "post",activity_title=row.get("title") or "Manual import",activity_text=row["text_excerpt"],activity_at=datetime.fromisoformat(row["post_date"].replace("Z","+00:00")),repository_name=row.get("repository_name") or None,repository_url=row.get("repository_url") or None,discovery_query="manual CSV import",collected_at=datetime.now(timezone.utc),raw_metadata={"notes":row.get("notes")})
        if persist_signal(session,item): count+=1
    session.commit(); return count

