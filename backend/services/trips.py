import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import select

from ..models import (Bus, Driver, Guardian, LocationSample, Mutation, SafetyCheck,
                      Stop, Student, StudentGuardian, Trip, TripEvent, TripStop, TripStudent, PassengerTransfer)
from .notifications import enqueue


def fail(message, status=422):
    raise HTTPException(status, message)


def required(db, model, key):
    value = db.get(model, key)
    if value is None:
        fail(f"{model.__name__} not found", 404)
    return value


def roster(db, trip):
    return db.scalars(select(TripStudent).where(TripStudent.trip_id == trip.id,
        ~select(PassengerTransfer.id).where(PassengerTransfer.source_trip_id == trip.id,
            PassengerTransfer.student_id == TripStudent.student_id).exists())).all()


def stops(db, trip):
    return db.scalars(select(TripStop).where(TripStop.trip_id == trip.id).order_by(TripStop.sequence)).all()


def counts(rows):
    return {"manifest_total": len(rows), "on_bus_count": sum(r.status == "boarded" for r in rows),
            "pending_count": sum(r.status == "pending" for r in rows),
            "absent_count": sum(r.status == "absent" for r in rows),
            "dropped_count": sum(r.status == "dropped" for r in rows)}


def snapshot(db, trip):
    rows = roster(db, trip)
    students = []
    for row in rows:
        student = db.get(Student, row.student_id)
        students.append({"student_id": row.student_id, "first_name": student.first_name,
                         "last_name": student.last_name, "status": row.status,
                         "reviewed_at": row.reviewed_at, "boarded_at": row.boarded_at,
                         "dropped_at": row.dropped_at, "pickup_stop_id": row.pickup_stop_id,
                         "dropoff_stop_id": row.dropoff_stop_id})
    return {"id": trip.id, "trip_code": trip.trip_code, "bus_id": trip.bus_id,
            "bus_code": db.get(Bus, trip.bus_id).bus_code, "driver_id": trip.driver_id,
            "status": trip.status, "version": trip.version, "shift": trip.shift,
            "trip_type": trip.trip_type, "service_date": trip.service_date,
            "started_at": trip.started_at, "last_dropoff_at": trip.last_dropoff_at,
            "ended_at": trip.ended_at, "counts": counts(rows), "students": students,
            "route_approved": trip.route_approved,
            "motion": motion_state(db, trip),
            "transfers": transfer_history(db, trip),
            "stops": [{"id": s.id, "stop_id": s.stop_id, "name": s.name, "sequence": s.sequence,
                       "latitude": s.latitude, "longitude": s.longitude,
                       "arrived_at": s.arrived_at, "completed_at": s.completed_at} for s in stops(db, trip)]}


def transfer_history(db, trip):
    records = db.scalars(select(PassengerTransfer).where(
        (PassengerTransfer.source_trip_id == trip.id) | (PassengerTransfer.target_trip_id == trip.id))).all()
    result = []
    for item in records:
        student = db.get(Student, item.student_id)
        source, target = db.get(Trip, item.source_trip_id), db.get(Trip, item.target_trip_id)
        result.append(dict(student_id=item.student_id, student_name=f'{student.first_name} {student.last_name}',
            source_trip_id=source.id, target_trip_id=target.id,
            source_bus=db.get(Bus, source.bus_id).bus_code, target_bus=db.get(Bus, target.bus_id).bus_code,
            previous_status=item.previous_status, reason=item.reason, recorded_at=item.created_at))
    return result


def event(db, trip, who, kind, student_id=None, details=None):
    row = TripEvent(trip_id=trip.id, actor_id=who.id, event_type=kind,
                    student_id=student_id, details=details or {})
    db.add(row)
    db.flush()
    return row


def mutate(db, who, key, scope, payload, trip, action):
    if not key or not 8 <= len(key) <= 100:
        fail("Idempotency-Key must contain 8-100 characters", 400)
    digest = hashlib.sha256(json.dumps({"scope": scope, "body": payload.model_dump(mode="json")},
                                       sort_keys=True).encode()).hexdigest()
    receipt = db.get(Mutation, (who.id, key))
    if receipt:
        if receipt.request_hash != digest:
            fail("Idempotency key was already used for a different request", 409)
        return receipt.response
    if trip.version != payload.expected_version:
        fail({"message": "Trip changed; refresh before retrying", "current_version": trip.version}, 409)
    action()
    trip.version += 1
    db.flush()
    result = snapshot(db, trip)
    db.add(Mutation(actor_id=who.id, key=key, request_hash=digest, response=result))
    db.flush()
    return result


def validate_trip(db, body):
    required(db, Bus, body.bus_id)
    required(db, Driver, body.driver_id)
    if len(set(a.student_id for a in body.students)) != len(body.students):
        fail("Duplicate students")
    if len(body.students) > db.get(Bus, body.bus_id).passenger_capacity:
        fail("Manifest exceeds bus capacity")
    sources = [required(db, Stop, key) for key in body.stop_ids]
    for assignment in body.students:
        required(db, Student, assignment.student_id)
        if not 0 <= assignment.pickup_sequence < assignment.dropoff_sequence < len(sources):
            fail("Pickup must precede drop-off within this trip")
        if body.trip_type == "dropoff" and assignment.pickup_sequence != 0:
            fail("Drop-off trips must board at the starting stop")
    return sources


def create_trip(db, body, who):
    sources = validate_trip(db, body)
    trip = Trip(**body.model_dump(exclude={"stop_ids", "students"}, mode="json"))
    db.add(trip)
    db.flush()
    ordered = []
    for sequence, source in enumerate(sources):
        item = TripStop(trip_id=trip.id, stop_id=source.id, sequence=sequence,
                        name=source.name, latitude=source.latitude, longitude=source.longitude)
        db.add(item)
        ordered.append(item)
    db.flush()
    for assignment in body.students:
        db.add(TripStudent(trip_id=trip.id, student_id=assignment.student_id,
                           pickup_stop_id=ordered[assignment.pickup_sequence].id,
                           dropoff_stop_id=ordered[assignment.dropoff_sequence].id))
    event(db, trip, who, "trip.created")
    return snapshot(db, trip)


def latest_location(db, trip):
    return db.scalar(select(LocationSample).where(LocationSample.trip_id == trip.id)
                     .order_by(LocationSample.recorded_at.desc()).limit(1))


def motion_state(db, trip):
    samples = db.scalars(select(LocationSample).where(LocationSample.trip_id == trip.id)
                         .order_by(LocationSample.recorded_at.desc()).limit(20)).all()
    if not samples:
        return {"status": "unknown", "recorded_at": None}
    latest = samples[0]
    result = {"status": "unknown", "recorded_at": latest.recorded_at}
    if not 0 <= time.time() - latest.recorded_at <= 15 or latest.accuracy_m > 25 or latest.speed_mps is None:
        return result
    if latest.speed_mps > 0.5:
        return {**result, "status": "moving"}
    evidence = []
    for fix in samples:
        if (latest.recorded_at - fix.recorded_at > 15 or fix.device_id != latest.device_id
                or fix.accuracy_m > 25 or fix.speed_mps is None or fix.speed_mps > 0.5):
            break
        evidence.append(fix)
    if len(evidence) >= 3 and latest.recorded_at - evidence[-1].recorded_at >= 5:
        result['status'] = 'stationary'
    return result


def stopped(db, trip, confirmed):
    motion = motion_state(db, trip)
    if motion['status'] == 'moving':
        fail("Latest reliable GPS indicates the bus is moving")
    if motion['status'] != 'stationary' and not confirmed:
        fail("GPS cannot confirm stationary status; operator confirmation is required")


def start_trip(db, trip, body, who):
    if trip.status != "scheduled":
        fail("Only scheduled trips can start", 409)
    db.scalar(select(Bus).where(Bus.id == trip.bus_id).with_for_update())
    db.scalar(select(Driver).where(Driver.id == trip.driver_id).with_for_update())
    others = db.scalars(select(Trip).where(Trip.id != trip.id,
        ((Trip.bus_id == trip.bus_id) | (Trip.driver_id == trip.driver_id)),
        Trip.status.in_(['scheduled', 'in_progress', 'awaiting_safety_check']))).all()
    for other in others:
        if other.status != 'scheduled' or counts(roster(db, other))['on_bus_count']:
            fail(f'Resolve trip {other.trip_code} before using this bus or driver', 409)
    stopped(db, trip, body.operator_confirmed_stopped)
    if not body.route_confirmed:
        fail("Approved stopping locations and route must be confirmed")
    rows = roster(db, trip)
    if not rows:
        fail("Trip has no manifest")
    for row in rows:
        if not row.reviewed_at:
            fail("Review every student before starting")
        if trip.trip_type == "dropoff" and row.status not in {"boarded", "absent"}:
            fail("Drop-off manifest must be Boarded or confirmed Absent")
        if not db.scalar(select(StudentGuardian).where(StudentGuardian.student_id == row.student_id)):
            fail("Student has no authorized guardian")
    if counts(rows)["on_bus_count"] > db.get(Bus, trip.bus_id).passenger_capacity:
        fail("Bus capacity exceeded")
    trip.started_at = time.time()
    trip.status = "in_progress" if any(r.status in {"pending", "boarded"} for r in rows) else "awaiting_safety_check"
    trip.route_approved = True
    event(db, trip, who, "trip.started")
    first = stops(db, trip)[0]
    if not any(r.status == "pending" and r.pickup_stop_id == first.id or
               r.status == "boarded" and r.dropoff_stop_id == first.id for r in rows):
        first.completed_at = time.time()
    for row in rows:
        if row.status == "boarded":
            student = db.get(Student, row.student_id)
            notice = event(db, trip, who, "student.boarded", row.student_id)
            enqueue(db, notice, student.first_name, trip.shift, trip.trip_type)


def update_attendance(db, trip, student_id, body, who):
    if trip.status not in {"scheduled", "in_progress"}:
        fail("Trip no longer accepts attendance changes", 409)
    row = required(db, TripStudent, (trip.id, student_id))
    if db.scalar(select(PassengerTransfer).where(PassengerTransfer.source_trip_id == trip.id, PassengerTransfer.student_id == student_id)):
        fail('Student is assigned to the replacement trip; update attendance there', 409)
    incoming = db.scalar(select(PassengerTransfer).where(PassengerTransfer.target_trip_id == trip.id, PassengerTransfer.student_id == student_id))
    if incoming and incoming.previous_status == 'boarded' and body.status in {'pending', 'absent'}:
        fail('A confirmed onboard transfer cannot be cleared as pending or absent', 409)
    stopped(db, trip, body.operator_confirmed_stopped)
    observed_at = body.observed_at or time.time()
    if observed_at > time.time() + 2:
        fail("Attendance observation is in the future")
    if trip.started_at and observed_at < trip.started_at:
        fail("Attendance observation predates departure; reconcile manually", 409)
    if body.status == "dropped" and row.boarded_at and observed_at < row.boarded_at:
        fail("Drop-off cannot precede boarding")
    old = row.status
    if trip.status == "scheduled":
        if body.status == "dropped":
            fail("Cannot drop a student before departure")
        if body.status == "pending" and trip.trip_type != "pickup":
            fail("Pending review is valid only for planned pickups")
    elif (old, body.status) not in {("pending", "boarded"), ("pending", "absent"), ("boarded", "dropped")}:
        fail("Invalid attendance transition", 409)
    if body.status == "boarded" and old != "boarded":
        if counts(roster(db, trip))["on_bus_count"] >= db.get(Bus, trip.bus_id).passenger_capacity:
            fail("Bus capacity exceeded")
    if trip.status == "in_progress":
        destination = row.dropoff_stop_id if body.status == "dropped" else row.pickup_stop_id
        stop = required(db, TripStop, destination)
        observation = stop.observation or {}
        fresh_arrival = observation.get("status") == "arrived" and 0 <= time.time() - observation.get("last_fix", 0) <= 15
        if not fresh_arrival and len(body.override_reason.strip()) < 10:
            fail("No current arrival confirmation; an explicit off-stop/GPS override reason is required")
    row.status = body.status
    row.reviewed_at = time.time()
    row.boarded_at = observed_at if body.status == "boarded" else row.boarded_at
    row.dropped_at = observed_at if body.status == "dropped" else row.dropped_at
    if trip.status == "scheduled" and body.status in {"pending", "absent"}:
        row.boarded_at = None
    notice = event(db, trip, who, f"student.{body.status}", student_id,
                   {"previous_status": old, "reason": body.override_reason, "observed_at": observed_at})
    if trip.status == "in_progress" and body.status in {"boarded", "dropped"}:
        enqueue(db, notice, db.get(Student, student_id).first_name, trip.shift, trip.trip_type)
    db.flush()
    rows = roster(db, trip)
    if trip.status == "in_progress":
        for stop in stops(db, trip):
            assigned = [r for r in rows if r.pickup_stop_id == stop.id or r.dropoff_stop_id == stop.id]
            outstanding = any((r.status == "pending" and r.pickup_stop_id == stop.id) or
                              (r.status in {"pending", "boarded"} and r.dropoff_stop_id == stop.id) for r in assigned)
            if assigned and not outstanding:
                stop.completed_at = stop.completed_at or time.time()
        if not any(r.status in {"pending", "boarded"} for r in rows):
            trip.status = "awaiting_safety_check"
            if body.status == "dropped":
                trip.last_dropoff_at = row.dropped_at
            event(db, trip, who, "trip.inspection_required")


def finish_trip(db, trip, body, who):
    if trip.status != "awaiting_safety_check":
        fail("Resolve all passengers before the final safety check", 409)
    if any(r.status in {"pending", "boarded"} for r in roster(db, trip)):
        fail("Unresolved students remain on this trip", 409)
    stopped(db, trip, body.operator_confirmed_stopped)
    if not body.physically_inspected or not body.physically_empty:
        fail("A physical inspection confirming an empty bus is required")
    db.add(SafetyCheck(trip_id=trip.id, actor_id=who.id, notes=body.notes, physically_empty=True))
    trip.status = "finished"
    trip.ended_at = time.time()
    event(db, trip, who, "trip.finished", details={"inspection_notes": body.notes})
