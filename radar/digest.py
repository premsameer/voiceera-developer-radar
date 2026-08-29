import csv, io
from .queries import developer_rows


FIELDS=["developer","handle","profile","observed_intent","intent_evidence","repository","repository_url","recent_activity","activity_url","last_activity","days_since_activity","qualification","score","reason","voiceera_route","matched_opportunity","opportunity_url","personalised_message","funnel_status"]


def csv_digest(session, timezone_name):
    buffer=io.StringIO(newline=""); writer=csv.DictWriter(buffer,fieldnames=FIELDS,extrasaction="ignore",lineterminator="\n"); writer.writeheader(); writer.writerows(developer_rows(session,timezone_name)); return buffer.getvalue()


def markdown_digest(session, timezone_name):
    rows=developer_rows(session,timezone_name); counts={k:sum(r["qualification"]==k for r in rows) for k in ["PASS","UNSURE","FAIL"]}
    lines=["# VoiceERA Developer Radar",f"\nSurfaced: {len(rows)} · PASS: {counts['PASS']} · UNSURE: {counts['UNSURE']} · FAIL: {counts['FAIL']}","\n## Top qualified",""]
    for r in [x for x in rows if x["qualification"]=="PASS"][:10]: lines.append(f"- [{r['developer']}]({r['profile']}) — {r['score']} — {r['observed_intent']} — {r['voiceera_route']}")
    lines.extend(["\n## Complete developer table","","| Developer | Intent | Repository | Activity | Days | Verdict | Score | Route | Opportunity | Funnel |","|---|---|---|---|---:|---|---:|---|---|---|"])
    for r in rows: lines.append(f"| [{r['developer']}]({r['profile'] or ''}) | {r['observed_intent']} | {r['repository'] or '—'} | [{r['recent_activity']}]({r['activity_url']}) | {r['days_since_activity']} | {r['qualification']} | {r['score']} | {r['voiceera_route']} | {r['matched_opportunity'] or '—'} | {r['funnel_status']} |")
    return "\n".join(lines)
