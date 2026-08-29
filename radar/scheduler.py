from apscheduler.schedulers.blocking import BlockingScheduler
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Connector
from .seed import seed
from .service import run_scan
from .contributor import detect_stalled_prs, github_access_token, reconcile_github
from sqlalchemy import select


def main():
    settings=get_settings(); init_db()
    with SessionLocal() as db: seed(db)
    hour,minute=map(int,settings.daily_schedule.split(":")); scheduler=BlockingScheduler(timezone=settings.app_timezone)
    def job():
        with SessionLocal() as db:
            run_scan(db,[x.type for x in db.scalars(select(Connector).where(Connector.enabled.is_(True)))])
            repositories=[x.strip() for x in settings.github_contributor_repositories.split(",") if x.strip()]
            token=github_access_token(settings)
            if token and repositories: reconcile_github(db,repositories,token)
            detect_stalled_prs(db,settings.contributor_stalled_pr_days)
    scheduler.add_job(job,"cron",hour=hour,minute=minute,id="daily-radar",replace_existing=True); scheduler.start()


if __name__=="__main__": main()
