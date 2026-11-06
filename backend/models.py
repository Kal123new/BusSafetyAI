import time
import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Student(Record, Base):
    __tablename__ = "students"
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))


class Driver(Record, Base):
    __tablename__ = "drivers"
    display_name: Mapped[str] = mapped_column(String(200))


class Guardian(Record, Base):
    __tablename__ = "guardians"
    display_name: Mapped[str] = mapped_column(String(200))
    push_topic: Mapped[str | None] = mapped_column(String(100), nullable=True)


class StudentGuardian(Base):
    __tablename__ = "student_guardians"
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), primary_key=True)
    guardian_id: Mapped[str] = mapped_column(ForeignKey("guardians.id"), primary_key=True)


class Account(Record, Base):
    __tablename__ = "accounts"
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    guardian_id: Mapped[str | None] = mapped_column(ForeignKey("guardians.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("role IN ('admin','driver','guardian')"),)


class Bus(Record, Base):
    __tablename__ = "buses"
    bus_code: Mapped[str] = mapped_column(String(40), unique=True)
    plate_number: Mapped[str] = mapped_column(String(40), unique=True)
    passenger_capacity: Mapped[int] = mapped_column(Integer)
    default_driver_id: Mapped[str | None] = mapped_column(ForeignKey("drivers.id"), nullable=True)
    __table_args__ = (CheckConstraint("passenger_capacity > 0"),)


class Stop(Record, Base):
    __tablename__ = "stops"
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    __table_args__ = (CheckConstraint("latitude BETWEEN -90 AND 90"), CheckConstraint("longitude BETWEEN -180 AND 180"))


class Trip(Record, Base):
    __tablename__ = "trips"
    trip_code: Mapped[str] = mapped_column(String(50), unique=True)
    bus_id: Mapped[str] = mapped_column(ForeignKey("buses.id"))
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    service_date: Mapped[str] = mapped_column(String(10))
    shift: Mapped[str] = mapped_column(String(15))
    trip_type: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    version: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_dropoff_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    route: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    route_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("status IN ('scheduled','in_progress','awaiting_safety_check','finished')"),
        CheckConstraint("shift IN ('morning','afternoon')"),
        CheckConstraint("trip_type IN ('pickup','dropoff')"),
        Index("one_active_bus", "bus_id", unique=True,
              sqlite_where=text("status IN ('in_progress','awaiting_safety_check')"),
              postgresql_where=text("status IN ('in_progress','awaiting_safety_check')")),
        Index("one_active_driver", "driver_id", unique=True,
              sqlite_where=text("status IN ('in_progress','awaiting_safety_check')"),
              postgresql_where=text("status IN ('in_progress','awaiting_safety_check')")),
    )


class TripStop(Record, Base):
    __tablename__ = "trip_stops"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observation: Mapped[dict] = mapped_column(JSON, default=dict)
    arrived_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("trip_id", "sequence"),
                      CheckConstraint("latitude BETWEEN -90 AND 90"), CheckConstraint("longitude BETWEEN -180 AND 180"))


class TripStudent(Base):
    __tablename__ = "trip_students"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"), primary_key=True)
    pickup_stop_id: Mapped[str] = mapped_column(ForeignKey("trip_stops.id"))
    dropoff_stop_id: Mapped[str] = mapped_column(ForeignKey("trip_stops.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    boarded_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropped_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (CheckConstraint("status IN ('pending','absent','boarded','dropped')"),)


class LocationSample(Record, Base):
    __tablename__ = "location_samples"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(100))
    sequence_number: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("trip_id", "device_id", "sequence_number"),)


class TripEvent(Record, Base):
    __tablename__ = "trip_events"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(Record, Base):
    __tablename__ = "notification_outbox"
    event_id: Mapped[str] = mapped_column(ForeignKey("trip_events.id"))
    guardian_id: Mapped[str] = mapped_column(ForeignKey("guardians.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=time.time)
    published_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    read_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    __table_args__ = (UniqueConstraint("event_id", "guardian_id"),)


class SafetyCheck(Record, Base):
    __tablename__ = "safety_checks"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(Text)
    physically_empty: Mapped[bool] = mapped_column(Boolean)


class Mutation(Base):
    __tablename__ = "mutation_receipts"
    actor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class ServicePlan(Record, Base):
    __tablename__ = "service_plans"
    name: Mapped[str] = mapped_column(String(100))
    bus_id: Mapped[str] = mapped_column(ForeignKey("buses.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ScheduledRun(Base):
    __tablename__ = "scheduled_runs"
    plan_id: Mapped[str] = mapped_column(ForeignKey("service_plans.id"), primary_key=True)
    service_date: Mapped[str] = mapped_column(String(10), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), unique=True)


class PassengerTransfer(Record, Base):
    __tablename__ = "passenger_transfers"
    source_trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    target_trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id"))
    previous_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("source_trip_id", "student_id"),)
