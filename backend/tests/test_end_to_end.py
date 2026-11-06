"""The full 13-step demonstration, driven only through the public HTTP API."""
from app.seed import hm


def test_full_recovery_workflow(client, operator, as_user):
    get = lambda path, h=operator: client.get(path, headers=h).json()  # noqa: E731

    # Normal network: nobody is affected.
    assert get("/api/op/overview")["affected"] == 0

    # 1. Operator triggers a cancellation.
    r = client.post("/api/op/disruptions", json={"kind": "cancellation", "service_id": "X5"}, headers=operator)
    assert r.status_code == 201, r.text

    # 2. Affected passengers are identified, and the passenger sees it.
    overview = get("/api/op/overview")
    assert overview["affected"] == 24 and overview["parties"] == 14
    asha = as_user("asha")
    journey = get("/api/me/journeys", asha)[0]
    assert journey["stage"]["code"] == "choose_options"
    assert any("cancelled" in n["title"] for n in get("/api/me/notifications", asha))

    # 3. Passengers are grouped.
    groups = get("/api/op/groups")
    assert sum(g["passengers"] for g in groups) == 24 and len(groups) < 14

    # 4. Alternatives are generated.
    options = get(f"/api/me/journeys/{journey['id']}/options", asha)
    assert len(options) >= 2

    # 5. One real passenger selects; the rest are simulated.
    r = client.put(f"/api/me/journeys/{journey['id']}/preferences", headers=asha,
                   json={"first_option_id": options[0]["id"], "second_option_id": options[1]["id"]})
    assert r.status_code == 200
    assert client.post("/api/demo/simulate-preferences", headers=operator).json()["simulated"] == 10

    # 6. Operator sees preferences, including those who did not respond.
    prefs = get("/api/op/preferences")
    # Silent: P-06 and P-13 by design, and P-14, who has no in-time option to choose.
    assert prefs["submitted"] == 11 and prefs["not_selected"] == 3

    # 7. Smart allocation assigns seats, without overbooking or forcing 20.
    run = client.post("/api/op/allocation/run", headers=operator).json()
    assert run["summary"]["engine"]["seats"] <= 20
    assert client.post("/api/op/allocations/confirm-all", headers=operator).json()["failed"] == []
    metrics = get("/api/op/metrics")
    assert metrics["over_allocation_count"] == 0
    assert metrics["official_confirmed"] == run["summary"]["engine"]["seats"]
    assert metrics["pct_decisions_explained"] == 100

    seated = get("/api/me/journeys", as_user("lakshmi"))[0]
    assert seated["stage"]["code"] == "seat_confirmed" and seated["allocation"]["pickup_stop"]

    # 8. Heat map shows concentrations.
    heat = get("/api/op/heatmap?status=unresolved")
    assert heat["total"] == 24 - metrics["official_confirmed"]

    # 9. Remaining passengers become carpool requests.
    meera = as_user("meera")
    listings = get("/api/carpool/requests", meera)
    assert sum(r["passengers_waiting"] for r in listings) == heat["total"]
    hebbal = next(r for r in listings if r["pickup_area"] == "Hebbal area" and r["destination"] == "Whitefield")
    assert hebbal["passengers_waiting"] == 3

    # 10. An ordinary user offers a carpool.
    r = client.post("/api/carpool/offers", headers=meera, json={
        "origin_stop": "HEB", "dest_stop": "WFD", "departure": hm("18:10"), "available_seats": 3,
        "vehicle_type": "Hatchback", "consent": True})
    assert r.status_code == 201, r.text

    # 11. The system proposes a match.
    assert r.json()["matches_proposed"] == 1
    match = get("/api/carpool/matches/mine", meera)[0]
    assert match["status"] == "awaiting_passenger" and match["matched_seats"] == 3
    assert get("/api/op/carpool")["summary"]["proposed_matches"] == 1

    # 12. Passengers and provider confirm.
    url = f"/api/carpool/matches/{match['id']}"
    for who in ("asha", "vikram"):
        assert client.post(f"{url}/passenger-response", json={"accept": True}, headers=as_user(who)).status_code == 200
    assert client.post(f"{url}/provider-response", json={"accept": True}, headers=meera).status_code == 200

    # 13. Both dashboards update.
    assert get("/api/me/journeys", asha)[0]["stage"]["code"] == "carpool_confirmed"
    assert get("/api/carpool/matches/mine", asha)[0]["contact"][0]["name"] == "Meera"
    monitor = get("/api/op/carpool")["summary"]
    assert monitor["confirmed_arrangements"] == 1 and monitor["confirmed_passengers"] == 3
    final = get("/api/op/metrics")
    assert final["carpool_confirmed"] == 3
    assert final["unresolved"] == 24 - final["official_confirmed"] - 3
    assert final["over_allocation_count"] == 0

    # The audit trail covers the scenario end to end.
    types = set(get("/api/op/audit?limit=500")["types"])
    assert {"disruption_created", "grouping_run", "preference_submitted", "allocation_run", "seat_reserved",
            "carpool_request_published", "carpool_offer_created", "carpool_match_proposed",
            "carpool_passenger_response", "carpool_confirmed"} <= types

    # And the guided demo reports completion.
    assert all(s["state"] == "done" for s in get("/api/demo/progress"))


def test_reset_restores_the_scenario(client, operator):
    client.post("/api/op/disruptions", json={"kind": "cancellation", "service_id": "X5"}, headers=operator)
    assert client.post("/api/demo/reset", headers=operator).status_code == 200
    overview = client.get("/api/op/overview", headers=operator).json()
    assert overview["affected"] == 0 and overview["capacity"]["available"] == 20


def test_new_passenger_can_register_and_join_a_disrupted_service(client, operator):
    client.post("/api/op/disruptions", json={"kind": "cancellation", "service_id": "X5"}, headers=operator)
    token = client.post("/api/auth/register", json={"email": "new@example.com", "password": "longenough1",
                                                    "name": "New Rider"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/me/journeys", headers=h, json={
        "origin_stop": "MGR", "dest_stop": "KOR", "party_size": 1, "dep_earliest": hm("18:00"),
        "dep_latest": hm("18:30"), "latest_arrival": hm("19:30"), "booked_service_id": "X5"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "affected"
    assert client.get(f"/api/me/journeys/{r.json()['id']}/options", headers=h).json()


def test_journey_validation(client):
    token = client.post("/api/auth/register", json={"email": "v@example.com", "password": "longenough1",
                                                    "name": "Val Idate"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    base = {"origin_stop": "MGR", "dest_stop": "KOR", "party_size": 1, "dep_earliest": 1100,
            "dep_latest": 1130, "latest_arrival": 1200}
    assert client.post("/api/me/journeys", headers=h, json={**base, "dest_stop": "MGR"}).status_code == 422
    assert client.post("/api/me/journeys", headers=h, json={**base, "dep_latest": 1000}).status_code == 422
    assert client.post("/api/me/journeys", headers=h, json={**base, "party_size": 0}).status_code == 422
    assert client.post("/api/me/journeys", headers=h, json={**base, "origin_stop": "NOPE"}).status_code == 422
