"""Local administrative commands. No passwords or tokens are stored in source."""
import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from .config import Settings
from .db import make_engine, session_factory
from .dependencies import Actor
from .models import Account, Bus, Driver, Guardian, Student, StudentGuardian, Stop, Trip
from .schemas import TripInput
from .services.notifications import dispatch
from .services.trips import create_trip


def migrate(url):
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def seed(db):
    existing = db.scalar(select(Trip).where(Trip.trip_code == "DEMO-001"))
    if existing:
        return existing.id
    driver = Driver(display_name="Demo Driver")
    bus = Bus(bus_code="DEMO-47B", plate_number="DEMO-ONLY", passenger_capacity=24)
    db.add_all([driver, bus])
    db.flush()
    locations = [Stop(name="Demo School", latitude=24.4539, longitude=54.3773),
                 Stop(name="Demo Stop A", latitude=24.455, longitude=54.379),
                 Stop(name="Demo Stop B", latitude=24.457, longitude=54.382)]
    db.add_all(locations)
    db.flush()
    assignments = []
    for index in range(2):
        guardian = Guardian(display_name=f"Demo Guardian {index + 1}")
        student = Student(first_name=f"Demo {index + 1}", last_name="Student")
        db.add_all([guardian, student])
        db.flush()
        db.add(StudentGuardian(student_id=student.id, guardian_id=guardian.id))
        assignments.append({"student_id": student.id, "pickup_sequence": 0, "dropoff_sequence": index + 1})
    body = TripInput(trip_code="DEMO-001", bus_id=bus.id, driver_id=driver.id,
                     service_date="2026-10-11", shift="afternoon", trip_type="dropoff",
                     stop_ids=[s.id for s in locations], students=assignments)
    return create_trip(db, body, Actor("local-seed", "admin"))["id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "seed-demo", "create-token", "revoke-token", "worker", "accounts", "set-push"])
    parser.add_argument("--role", choices=["admin", "driver", "guardian"], default="admin")
    parser.add_argument("--name", default="Operator")
    parser.add_argument("--subject-id")
    parser.add_argument("--account-id")
    parser.add_argument("--topic")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == "migrate":
        migrate(settings.database_url)
        return
    engine = make_engine(settings.database_url)
    sessions = session_factory(engine)
    try:
        if args.command == "worker":
            while True:
                with sessions.begin() as db:
                    if engine.dialect.name == "sqlite":
                        db.execute(text("BEGIN IMMEDIATE"))
                    dispatch(db, settings)
                if args.once:
                    break
                time.sleep(5)
            return
        with sessions.begin() as db:
            if args.command == "seed-demo":
                if settings.mode != "demo":
                    parser.error("Set SAFESENSE_MODE=demo before seeding synthetic data")
                print(json.dumps({"trip_id": seed(db)}))
            elif args.command == "accounts":
                print(json.dumps([{"id": a.id, "name": a.display_name, "role": a.role, "active": a.active}
                                  for a in db.scalars(select(Account))]))
            elif args.command == "revoke-token":
                account = db.get(Account, args.account_id)
                if not account:
                    parser.error("Account not found")
                account.active = False
            elif args.command == "set-push":
                import re
                guardian = db.get(Guardian, args.subject_id)
                if not guardian or not args.topic or not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", args.topic):
                    parser.error("Provide a guardian ID and a private topic of 20-100 safe characters")
                guardian.push_topic = args.topic
            else:
                if args.role != "admin" and not db.get(Driver if args.role == "driver" else Guardian, args.subject_id):
                    parser.error("Provide an existing driver/guardian ID")
                token = secrets.token_urlsafe(32)
                account = Account(display_name=args.name, role=args.role, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                  driver_id=args.subject_id if args.role == "driver" else None,
                                  guardian_id=args.subject_id if args.role == "guardian" else None)
                db.add(account)
                db.flush()
                db.commit()
                print(f"Account: {account.id}\nToken (shown once; keep private): {token}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
