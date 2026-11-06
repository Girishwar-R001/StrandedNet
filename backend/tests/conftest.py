import os
import tempfile
from pathlib import Path

# Must be set before the app is imported, so tests can never touch the demo database.
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["DEMO_MODE"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.engines import allocation, disruption  # noqa: E402
from app.engines.network import Network  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Journey, JourneyOption, Preference, User  # noqa: E402
from app.seed import DEMO_PASSWORD, reset  # noqa: E402

Base.metadata.create_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    reset(session)
    yield session
    session.close()


@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def op(db):
    return db.query(User).filter_by(role="operator").one()


def token_headers(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def as_user(client):
    cache = {}

    def _headers(who: str):
        email = who if "@" in who else f"{who}@stranded.demo"
        if email not in cache:
            cache[email] = token_headers(client, email)
        return cache[email]
    return _headers


@pytest.fixture
def operator(as_user):
    return as_user("operator")


def journey(db, ref) -> Journey:
    return db.query(Journey).filter_by(ref=ref).one()


def cancel_x5(db, op):
    d = disruption.create(db, kind="cancellation", actor=op, service_id="X5")
    db.commit()
    return d


def simulate_prefs(db):
    """Every party ranks replacement options first, as most passengers would."""
    for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref):
        options = db.query(JourneyOption).filter_by(journey_id=j.id, status="active", meets_deadline=True).all()
        options.sort(key=lambda o: (not o.reservable, o.arrival, o.key))
        for rank, o in enumerate(options[:2], 1):
            db.add(Preference(journey_id=j.id, option_id=o.id, rank=rank))
    db.commit()


def allocate_and_confirm(db, op):
    net = Network.load(db)
    run = allocation.run_allocation(db, net, op)
    db.commit()
    result = allocation.reserve_all(db, net, op)
    from app.engines.carpool import sync_demand
    sync_demand(db, net, op)
    db.commit()
    return run, result
