import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from radar.db import Base
from radar.seed import seed

@pytest.fixture()
def db():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine); session=sessionmaker(engine,expire_on_commit=False)(); seed(session)
    yield session
    session.close()

