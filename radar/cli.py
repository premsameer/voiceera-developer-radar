from datetime import date
from pathlib import Path
import typer
from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal, init_db
from .digest import csv_digest, markdown_digest
from .importer import import_csv_text
from .models import Connector
from .seed import seed
from .demo import seed_demo
from .backfill import backfill_v2
from .service import run_scan

app=typer.Typer(help="VoiceERA Developer Radar")

@app.command("init-db")
def initialize(): init_db(); typer.echo("Database initialized")

@app.command("seed-config")
def seed_config():
    init_db()
    with SessionLocal() as db: seed(db)
    typer.echo("Configuration seeded")

@app.command()
def scan(source:str|None=typer.Option(None),all_:bool=typer.Option(False,"--all"),lookback_days:int=30,since_last_success:bool=False):
    init_db()
    with SessionLocal() as db:
        seed(db); sources=[source] if source else ([c.type for c in db.scalars(select(Connector).where(Connector.enabled.is_(True)))] if all_ else ["github"])
        result=run_scan(db,sources,lookback_days); typer.echo(f"Run {result.id}: {result.status} {result.source_counts_json}")

@app.command()
def digest(date_:str=typer.Option(date.today().isoformat(),"--date"),format:str="markdown",output:Path|None=None):
    with SessionLocal() as db: data=csv_digest(db,get_settings().app_timezone) if format=="csv" else markdown_digest(db,get_settings().app_timezone)
    if output: output.write_text(data,encoding="utf-8")
    else: typer.echo(data)

@app.command("import-csv")
def import_csv(path:Path):
    with SessionLocal() as db: typer.echo(f"Imported {import_csv_text(db,path.read_text(encoding='utf-8'))} signals")

@app.command("seed-demo")
def demo(count:int=20):
    init_db()
    with SessionLocal() as db:
        seed(db); typer.echo(f"Added {seed_demo(db,count)} demo signals")

@app.command("backfill-v2")
def backfill():
    init_db()
    with SessionLocal() as db: typer.echo(f"Enriched {backfill_v2(db)} existing signals")
