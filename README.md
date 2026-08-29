# VoiceERA Developer Radar

A production-minded MVP that discovers public, dated voice-AI activity, applies deterministic qualification, matches one VoiceERA route, and prepares a human-reviewed daily queue. It never sends outreach.

V2A/V2B adds evidence-backed developer segmentation, inspectable intent-strength scoring, technology evidence, safe organization links, event-derived adoption funnels, attributed tracking links, deterministic next-best actions, and segment/funnel analytics. All V1 scans, reviews, and exports remain supported.

## What is included

- Official GitHub REST, Reddit OAuth, DEV/Forem, Hacker News Firebase, and RSS/Atom connectors
- Incremental source checkpoints with a two-hour overlap, idempotent source IDs/URLs, explicit connector errors, and retry/backoff handling
- SQLite locally and PostgreSQL through `DATABASE_URL`; SQLAlchemy models and Alembic migration
- Rules-first bot filtering, intent classification, PASS/UNSURE/FAIL scoring, opportunity matching, and evidence-grounded drafts
- FastAPI endpoints, Typer CLI, five-tab Streamlit review dashboard, Markdown/CSV export, manual CSV import, APScheduler job, Docker Compose, and tests
- Twenty-signal seeded demo mode; all unique surfaced developers remain in the dashboard/export regardless of verdict

## Local setup

Python 3.12 is recommended (3.11+ is supported).

```bash
python -m venv .venv
. .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[test]"
cp .env.example .env         # Windows: Copy-Item .env.example .env
radar init-db
radar seed-config
radar seed-demo
alembic upgrade head
radar backfill-v2
uvicorn radar.api:app --reload
```

In a second terminal:

```bash
streamlit run dashboard.py
```

API docs are at `http://localhost:8000/docs`; the dashboard is at `http://localhost:8501`. Mutation endpoints require `X-Admin-Secret` matching `ADMIN_SECRET`.

## CLI

```bash
radar init-db
radar seed-config
radar scan --source github --lookback-days 30
radar scan --all --since-last-success
radar digest --date 2026-08-29 --format markdown --output radar.md
radar digest --format csv --output radar.csv
radar import-csv manual_signals_template.csv
radar seed-demo --count 20
```

`--since-last-success` is accepted for interface compatibility; scans always use the last successful checkpoint when present and otherwise use the requested lookback.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The compose stack runs the API, dashboard, and 09:00 `Asia/Kolkata` scheduler against a shared volume. Change `DAILY_SCHEDULE` or `APP_TIMEZONE` in `.env` as needed.

## Configuration and credentials

Connector vocabulary, queries, watchlists, subreddits, feeds, and opportunities are seeded in `radar/seed.py` and persisted as editable JSON rows. GitHub works with only `GITHUB_TOKEN`. DEV and Hacker News need no credential. Reddit stays disabled until `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are set; RSS stays disabled until feeds are configured. An unavailable source is marked disabled/error, never reported as a successful zero.

The included VoiceERA opportunity URLs use the canonical placeholder `https://github.com/voiceera/voiceera` from the brief. Confirm the real public repository/quick-start URL before approving outreach.

## Architecture

```text
official APIs / feeds / CSV
          ↓
connector adapters → normalized Pydantic signal
          ↓
dedupe + bot/noise checks → deterministic score
          ↓
one opportunity route + grounded draft
          ↓
SQLAlchemy audit store
       ↙          ↘
FastAPI/CLI     Streamlit review + exports
```

## V2A/V2B intelligence

Set `V2_ENABLED=true` to enrich new signals. Existing installations should run `alembic upgrade head` followed by `radar backfill-v2` once. The backfill retains V1 records and derives segments, intent strength, and technology evidence from stored activities.

Developer segments and technologies always retain an evidence signal. Manual segment overrides are separate records with a required reason and never erase the rules result. Organization links require a public evidence URL. Funnel stages are derived from `engagement_events`; the legacy stage API now records a verified manual event instead of directly overwriting state.

New endpoints include:

```text
GET/POST /api/developers/{id}/segments
GET      /api/developers/{id}/technologies
GET      /api/developers/{id}/timeline
POST     /api/developers/{id}/events
POST     /api/developers/{id}/organizations
POST     /api/campaigns
GET      /api/analytics/funnel
GET      /api/analytics/segments
GET      /api/analytics/messages
GET      /r/{tracking_code}
```

Tracking redirects record only an attributed visit and never imply installation. Product activation ingestion remains optional future integration work; manual verified events are supported now. Analytics return denominators and flag small samples below `ANALYTICS_MINIMUM_SAMPLE`.

Every PASS has a source URL, exact timestamp, and evidence excerpt. `days_since_activity` is calculated at read time in `APP_TIMEZONE`. Cross-platform identities are not inferred. Commit emails are neither requested nor stored. The optional OpenAI adapter validates structured output and refuses a PASS missing proof; the application defaults to rules-only mode.

## Tests

```bash
pytest
```

Coverage includes normalization, intent classification, dynamic recency, bot exclusion, scoring, opportunity matching, GENERAL_INTRO fallback, message grounding, deduplication, complete developer rows, and one mocked GitHub collection flow.

## Operational assumptions and limitations

- GitHub collection is deliberately bounded by configured queries, watchlists, `per_page`, and `max_repositories`; it does not crawl GitHub.
- The MVP collects default-branch commits plus repository issues/PRs. Releases can be added through the same adapter; the current live connector does not yet call the release endpoint.
- Repository languages are represented in the normalized schema but the live GitHub adapter avoids an extra API request per repository; add language hydration if scoring quality justifies the rate cost.
- Reddit searches public posts, not comments. DEV uses tag queries and local deterministic filtering. Hacker News author enrichment is intentionally minimal.
- The dashboard displays and edits persisted configuration as JSON; a rich form editor is a follow-up refinement.
- X, Slack/email delivery, issue synchronization, and activation telemetry are P1 and are not enabled.
- No scraper, autonomous messaging, private-email collection, or account-link inference is present.

## Deployment

Set `DATABASE_URL` to a PostgreSQL URL and install `.[postgres]`. Run `alembic upgrade head` as a release step, keep the API/dashboard behind HTTPS, store secrets in the deployment secret manager, and call the protected scan endpoint from platform cron if the scheduler container is not used.
