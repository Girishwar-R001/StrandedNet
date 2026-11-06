"""Grouping must reflect real route and time compatibility, not destination names."""
from app.engines.grouping import cluster, pair_compat, run_grouping
from app.engines.network import Network
from app.models import Journey, PassengerGroup

from .conftest import cancel_x5, journey


def _from_whitefield(db, like):
    """A party heading into the city, the opposite way to everyone in the seeded scenario."""
    return Journey(ref="T-01", origin_stop="WFD", dest_stop="SBC", party_size=1, dep_earliest=like.dep_earliest,
                   dep_latest=like.dep_latest, latest_arrival=like.latest_arrival, max_walk_m=500, requirements=[])


def test_same_destination_name_from_opposite_directions_is_not_compatible(db):
    """Both go to City Railway Station, one from the north, one from the east."""
    net = Network.load(db)
    a = journey(db, "P-10")
    b = _from_whitefield(db, a)
    assert a.dest_stop == b.dest_stop
    result = pair_compat(a, b, net)
    assert not result.ok
    assert "overlap" in result.reason


def test_shared_road_in_opposite_directions_counts_for_nothing(db):
    """Windows are aligned so direction is the only thing that can reject this pair."""
    net = Network.load(db)
    outbound = journey(db, "P-03")  # City<->Whitefield
    inbound = _from_whitefield(db, outbound)
    ride = net.travel(outbound.origin_stop, inbound.origin_stop)
    inbound.dep_earliest = outbound.dep_earliest + ride
    inbound.dep_latest = outbound.dep_latest + ride
    result = pair_compat(outbound, inbound, net)
    assert not result.ok
    assert "overlap" in result.reason
    db.rollback()


def test_boarding_along_the_same_route_is_compatible(db):
    net = Network.load(db)
    result = pair_compat(journey(db, "P-03"), journey(db, "P-05"), net)
    assert result.ok and result.parts["route"] >= 0.4


def test_departure_windows_that_miss_each_other_are_incompatible(db):
    net = Network.load(db)
    a, b = journey(db, "P-01"), journey(db, "P-02")
    assert pair_compat(a, b, net).ok
    b.dep_earliest, b.dep_latest = a.dep_latest + 60, a.dep_latest + 90
    result = pair_compat(a, b, net)
    assert not result.ok and "windows" in result.reason
    db.rollback()


def test_groups_are_complete_linkage(db, op):
    """Every pair inside a group must be compatible, not merely chained."""
    cancel_x5(db, op)
    net = Network.load(db)
    for g in db.query(PassengerGroup).filter_by(status="active"):
        members = db.query(Journey).filter_by(group_id=g.id).all()
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                assert pair_compat(a, b, net).ok, (a.ref, b.ref)


def test_every_affected_party_is_in_exactly_one_group(db, op):
    cancel_x5(db, op)
    affected = db.query(Journey).filter_by(status="affected").all()
    assert all(j.group_id for j in affected)
    assert sum(g.combined_size for g in db.query(PassengerGroup).filter_by(status="active")) == 24


def test_group_size_is_bounded(db):
    net = Network.load(db)
    journeys = db.query(Journey).filter(Journey.booked_service_id == "X5").all()
    for members, _ in cluster(journeys, net, max_size=4, max_step_free=4):
        assert sum(j.party_size for j in members) <= 4


def test_step_free_groups_fit_the_largest_accessible_vehicle(db):
    net = Network.load(db)
    journeys = db.query(Journey).filter(Journey.booked_service_id == "X5").all()
    for members, _ in cluster(journeys, net, max_size=8, max_step_free=5):
        if any({"wheelchair", "step_free"} & set(j.requirements) for j in members):
            assert sum(j.party_size for j in members) <= 5


def test_grouping_is_deterministic(db, op):
    cancel_x5(db, op)
    net = Network.load(db)
    first = sorted(sorted(j.ref for j in m) for m, _ in cluster(db.query(Journey).filter_by(status="affected").all(), net, 8, 5))
    second = sorted(sorted(j.ref for j in m) for m, _ in cluster(db.query(Journey).filter_by(status="affected").all()[::-1], net, 8, 5))
    assert first == second


def test_groups_carry_required_display_fields(db, op):
    cancel_x5(db, op)
    for g in run_grouping(db, Network.load(db), op):
        assert g.label and g.destination_zone and g.pickup_stop and g.explanation
        assert 0 < g.score <= 1 and g.est_minutes > 0
