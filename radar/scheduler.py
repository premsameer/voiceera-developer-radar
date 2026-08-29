from apscheduler.schedulers.blocking import BlockingScheduler
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Connector
from .seed import seed
from .service import run_scan
from sqlalchemy import select


def main():
    settings=get_settings(); init_db()
    with SessionLocal() as db: seed(db)
    hour,minute=map(int,settings.daily_schedule.split(":")); scheduler=BlockingScheduler(timezone=settings.app_timezone)
    def job():
        with SessionLocal() as db: run_scan(db,[x.type for x in db.scalars(select(Connector).where(Connector.enabled.is_(True)))])
    scheduler.add_job(job,"cron",hour=hour,minute=minute,id="daily-radar",replace_existing=True); scheduler.start()


if __name__=="__main__": main()

