"""API tests run against a REAL small dataset made by the real pipeline (in memory, once per session)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base, get_db
from app.deps import get_output_dir
from app.main import app
from generator.generate import run_pipeline

SMALL = dict(n_customers=900, n_business=120, n_documents=2700, n_reviews=250, n_anomalies=6, n_controls=4)


@pytest.fixture(scope="session")
def out_dir(tmp_path_factory):
    """Where the pipeline writes ground_truth.* and validation_report.* for these tests."""
    return tmp_path_factory.mktemp("api_out")


@pytest.fixture(scope="session")
def engine(out_dir):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        run_pipeline(session, out_dir=out_dir, log=lambda *_: None, **SMALL)
    return eng


@pytest.fixture(scope="session")
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="session")
def client(engine, out_dir):
    factory = sessionmaker(bind=engine, autoflush=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_output_dir] = lambda: out_dir
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def all_pages(client, path, **params):
    """Walk every page of a list endpoint and return all items."""
    items, page = [], 1
    while True:
        body = client.get(path, params={**params, "page": page, "page_size": 200}).json()
        items += body["items"]
        if page >= body["pages"]:
            return items
        page += 1
