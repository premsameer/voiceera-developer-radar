from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    settings = get_settings()
    settings.ensure_data_dir()
    target = url or settings.database_url
    return create_engine(target, connect_args={"check_same_thread": False} if target.startswith("sqlite") else {})


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)

