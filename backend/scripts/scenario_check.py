"""Runs the demonstration scenario at engine level and prints what happens. Uses a scratch DB."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tempfile.mkdtemp()) / "scenario.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.engines import allocation, carpool, disruption, reporting  # noqa: E402
from app.engines.network import Network  # noqa: E402
from app.models import Allocation, Journey, JourneyOption, PassengerGroup, Preference, User  # noqa: E402
from app.routers.demo import SILENT, WALKUP_FIRST  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import fmt  # noqa: E402

Base.metadata.create_all(engine)
db = SessionLocal()
seed(db)
op = db.query(User).filter_by(role="operator").one()
disruption.create(db, kind="cancellation", actor=op, service_id="X5")
db.commit()

print("Affected:", sum(j.party_size for j in db.query(Journey).filter_by(status="affected")),
      "in", db.query(Journey).filter_by(status="affected").count(), "parties;",
      "unaffected parties:", db.query(Journey).filter_by(status="normal").count())
print("\nGROUPS")
for g in db.query(PassengerGroup).filter_by(status="active"):
    refs = [j.ref for j in db.query(Journey).filter_by(group_id=g.id)]
    print(f"  {g.label} {g.combined_size:>2}p score={g.score:.2f} {g.destination_zone:8} {refs}")

print("\nOPTIONS")
for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref):
    opts = db.query(JourneyOption).filter_by(journey_id=j.id, status="active").all()
    print(f"  {j.ref} {j.origin_stop}->{j.dest_stop} x{j.party_size}:",
          [f"{o.title[:28]} {fmt(o.departure)}-{fmt(o.arrival)}{'' if o.meets_deadline else ' LATE'}" for o in opts])

for j in db.query(Journey).filter_by(status="affected").order_by(Journey.ref):
    if j.ref in SILENT:
        continue
    opts = db.query(JourneyOption).filter_by(journey_id=j.id, status="active", meets_deadline=True).all()
    opts.sort(key=lambda o: (o.reservable if j.ref in WALKUP_FIRST else not o.reservable, o.arrival, o.key))
    for rank, o in enumerate(opts[:2], 1):
        db.add(Preference(journey_id=j.id, option_id=o.id, rank=rank))
db.commit()

net = Network.load(db)
run = allocation.run_allocation(db, net, op)
db.commit()
print("\nRUN", run.solver, {k: v for k, v in run.summary.items() if k != "unplaced"})
for u in run.summary["unplaced"]:
    print("  UNPLACED", u["ref"], f"x{u['party_size']}", u["reason"])
for a in db.query(Allocation).filter_by(status="proposed").order_by(Allocation.priority_score.desc()):
    print(f"  {a.journey.ref} x{a.seats} -> {a.vehicle_id} score={a.priority_score:.2f} {a.preference_outcome}")
print("\nGREEDY comparison:")
print(allocation.reserve_all(db, net, op))
carpool.sync_demand(db, net, op)
db.commit()
print("\nCARPOOL", reporting.carpool_monitor(db)["summary"])
for r in reporting.carpool_monitor(db)["requests"]:
    print(" ", r)
print("\nMETRICS", reporting.metrics(db))
print("INTEGRITY", reporting.integrity(db))
