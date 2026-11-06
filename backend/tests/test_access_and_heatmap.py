"""Role separation and the operator-only heat map, enforced at the backend."""
import re

import pytest

from app.main import app
from app.models import Journey

from .conftest import allocate_and_confirm, cancel_x5, simulate_prefs


def _operator_routes():
    for path, methods in app.openapi()["paths"].items():
        if path.startswith("/api/op/"):
            for method in methods:
                yield method.upper(), re.sub(r"\{[^}]+\}", "1", path)


OPERATOR_ROUTES = sorted(set(_operator_routes()))


def test_route_introspection_found_the_operator_api():
    assert len(OPERATOR_ROUTES) >= 25


@pytest.mark.parametrize("method,path", OPERATOR_ROUTES)
def test_every_operator_route_rejects_anonymous_users(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


@pytest.mark.parametrize("method,path", OPERATOR_ROUTES)
def test_every_operator_route_rejects_passengers(client, as_user, method, path):
    assert client.request(method, path, json={}, headers=as_user("asha")).status_code == 403


def test_forged_token_is_rejected(client):
    assert client.get("/api/op/heatmap", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_token_signed_with_the_wrong_key_is_rejected(client):
    import jwt
    forged = jwt.encode({"sub": "1", "role": "operator"}, "wrong-key-of-a-sensible-length-for-hs256", "HS256")
    assert client.get("/api/op/heatmap", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_role_comes_from_the_database_not_the_token_claim(client, db):
    """A passenger's validly signed token claiming operator is still refused."""
    import jwt
    from app.config import settings
    from app.models import User
    asha = db.query(User).filter_by(email="asha@stranded.demo").one()
    forged = jwt.encode({"sub": str(asha.id), "role": "operator"}, settings.jwt_secret, "HS256")
    assert client.get("/api/op/heatmap", headers={"Authorization": f"Bearer {forged}"}).status_code == 403


def test_operators_cannot_use_passenger_routes(client, operator):
    assert client.get("/api/me/journeys", headers=operator).status_code == 403
    assert client.get("/api/carpool/requests", headers=operator).status_code == 403


def test_public_registration_cannot_create_an_operator(client):
    r = client.post("/api/auth/register", json={"email": "new@example.com", "password": "longenough1",
                                                "name": "New User", "role": "operator"})
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "passenger"


def test_demo_controls_need_an_operator(client, as_user):
    assert client.post("/api/demo/reset").status_code == 401
    assert client.post("/api/demo/reset", headers=as_user("asha")).status_code == 403
    assert client.post("/api/demo/simulate-preferences", headers=as_user("asha")).status_code == 403


def test_heatmap_is_aggregated_and_carries_no_identity(client, db, op, operator):
    cancel_x5(db, op)
    r = client.get("/api/op/heatmap", headers=operator)
    assert r.status_code == 200
    text = r.text
    for j in db.query(Journey):
        assert j.ref not in text
        assert j.user.name not in text
        assert f"{j.lat:.4f}" not in text and f"{j.lng:.4f}" not in text


def test_heatmap_coordinates_are_snapped_to_the_grid(client, db, op, operator):
    cancel_x5(db, op)
    for c in client.get("/api/op/heatmap", headers=operator).json()["cells"]:
        assert round(c["lat"], 2) == c["lat"] and round(c["lng"], 2) == c["lng"]


def test_heatmap_totals_match_affected_passengers(client, db, op, operator):
    cancel_x5(db, op)
    body = client.get("/api/op/heatmap", headers=operator).json()
    assert sum(c["affected"] for c in body["cells"]) == 24 == body["total"]
    assert body["simulated"] is True


def test_heatmap_filters(client, db, op, operator):
    cancel_x5(db, op)
    simulate_prefs(db)
    allocate_and_confirm(db, op)
    get = lambda **p: client.get("/api/op/heatmap", params=p, headers=operator).json()  # noqa: E731
    assert get(status="unresolved")["total"] + get(status="official")["total"] == 24
    assert get(destination="WFD")["total"] < 24
    assert get(dep_from=1200, dep_to=1300)["total"] == 0
    dest = get(layer="destination")
    assert dest["layer"] == "destination" and dest["total"] == 24
    assert client.get("/api/op/heatmap", params={"status": "bogus"}, headers=operator).status_code == 422


def test_heatmap_reports_capacity_by_zone(client, db, op, operator):
    cancel_x5(db, op)
    zones = {z["zone"]: z for z in client.get("/api/op/heatmap", headers=operator).json()["zones"]}
    assert zones["East"]["capacity"] == 8     # RV-1 only
    assert zones["Central"]["capacity"] == 20  # all three vehicles call here
