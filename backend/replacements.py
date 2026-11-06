"""Explicit, audited replacement-bus trips; no automatic passenger handovers."""
import time
import uuid
from fastapi import APIRouter, Depends, Header
from pydantic import Field
from sqlalchemy import select, or_
from .dependencies import admin, get_db, trip_access
from .models import (Bus, Driver, Trip, TripStop, TripStudent, Stop, PassengerTransfer,
                     Student, StudentGuardian, Notification)
from .schemas import Versioned, Identifier
from .services import trips

router = APIRouter(prefix='/api/v1')


class ReplacementInput(Versioned):
    target_bus_id: Identifier
    handover_stop_id: Identifier
    student_ids: list[Identifier] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=10, max_length=500)
    source_stopped: bool = False
    target_stopped: bool = False
    handover_confirmed: bool = False


def create_replacement(db, source, body, who):
    if source.status not in {'scheduled', 'in_progress'}:
        trips.fail('Only scheduled or active trips can use a replacement bus', 409)
    if source.bus_id == body.target_bus_id:
        trips.fail('Choose a different bus')
    bus = db.scalar(select(Bus).where(Bus.id == body.target_bus_id).with_for_update())
    if not bus or not bus.default_driver_id:
        trips.fail('Replacement bus must have a default driver')
    driver = db.scalar(select(Driver).where(Driver.id == bus.default_driver_id).with_for_update())
    if driver.id == source.driver_id:
        trips.fail('Choose a replacement bus with a different driver; the original bus still needs its safety check')
    if db.scalar(select(Trip.id).where(Trip.status.in_(['in_progress', 'awaiting_safety_check']),
            or_(Trip.bus_id == bus.id, Trip.driver_id == driver.id))):
        trips.fail('Replacement bus or driver has an unfinished active trip', 409)
    if db.scalar(select(Trip.id).join(TripStudent).where(Trip.bus_id == bus.id,
            Trip.status == 'scheduled', TripStudent.status == 'boarded')):
        trips.fail('Replacement bus already has boarded passengers on another scheduled trip', 409)
    if len(body.student_ids) != len(set(body.student_ids)):
        trips.fail('Select each student only once')
    rows = {r.student_id: r for r in trips.roster(db, source)}
    if any(key not in rows or rows[key].status not in {'pending', 'boarded'} for key in body.student_ids):
        trips.fail('Only unresolved students still assigned to the source trip can be moved', 409)
    selected = [rows[key] for key in body.student_ids]
    if len(selected) > bus.passenger_capacity:
        trips.fail('Replacement manifest exceeds bus capacity')
    trips.stopped(db, source, body.source_stopped)
    if not body.target_stopped:
        trips.fail('Confirm that the receiving bus is stopped')
    if any(r.status == 'boarded' for r in selected) and not body.handover_confirmed:
        trips.fail('Confirm physical handover of every selected onboard student to the receiving driver')
    handover = trips.required(db, Stop, body.handover_stop_id)
    target = Trip(trip_code=f'REPLACEMENT-{uuid.uuid4().hex[:12]}', bus_id=bus.id, driver_id=driver.id,
        service_date=source.service_date, shift=source.shift, trip_type='pickup' if any(r.status == 'pending' for r in selected) else 'dropoff',
        status='scheduled', route_approved=False)
    db.add(target); db.flush()
    first = TripStop(trip_id=target.id, stop_id=handover.id, sequence=0, name=handover.name,
        latitude=handover.latitude, longitude=handover.longitude)
    db.add(first); db.flush()
    needed = {r.dropoff_stop_id for r in selected} | {r.pickup_stop_id for r in selected if r.status == 'pending'}
    copied = {}
    for old in trips.stops(db, source):
        if old.id in needed:
            stop = TripStop(trip_id=target.id, stop_id=old.stop_id, sequence=len(copied)+1,
                name=old.name, latitude=old.latitude, longitude=old.longitude)
            db.add(stop); db.flush(); copied[old.id] = stop
    now = time.time()
    for row in selected:
        boarded = row.status == 'boarded'
        db.add(TripStudent(trip_id=target.id, student_id=row.student_id, status=row.status,
            pickup_stop_id=first.id if boarded else copied[row.pickup_stop_id].id,
            dropoff_stop_id=copied[row.dropoff_stop_id].id,
            reviewed_at=now if boarded else None, boarded_at=now if boarded else None))
        db.add(PassengerTransfer(source_trip_id=source.id, target_trip_id=target.id,
            student_id=row.student_id, previous_status=row.status, reason=body.reason, actor_id=who.id))
        details = dict(target_trip_id=target.id, source_trip_id=source.id,
            source_bus_id=source.bus_id, target_bus_id=bus.id, reason=body.reason,
            physical_handover=boarded, handover_stop_id=handover.id)
        trips.event(db, source, who, 'student.transferred_out' if boarded else 'student.reassigned', row.student_id, details)
        notice = trips.event(db, target, who, 'student.transferred_in' if boarded else 'student.reassigned', row.student_id, details)
        student = db.get(Student, row.student_id)
        action = 'was physically transferred to' if boarded else 'is now assigned to'
        for guardian_id in db.scalars(select(StudentGuardian.guardian_id).where(StudentGuardian.student_id == row.student_id)):
            db.add(Notification(event_id=notice.id, guardian_id=guardian_id,
                message=f'{student.first_name} {action} replacement bus {bus.bus_code}. This is not a drop-off confirmation.'))
    trips.event(db, target, who, 'trip.replacement_created', details={'source_trip_id': source.id, 'reason': body.reason})
    db.flush()
    remaining = trips.roster(db, source)
    if source.status == 'in_progress':
        for stop in trips.stops(db, source):
            outstanding = any((r.status == 'pending' and r.pickup_stop_id == stop.id) or
                (r.status in {'pending', 'boarded'} and r.dropoff_stop_id == stop.id) for r in remaining)
            if not outstanding:
                stop.completed_at = stop.completed_at or now
    if not any(r.status in {'pending', 'boarded'} for r in remaining):
        source.status = 'awaiting_safety_check'
        trips.event(db, source, who, 'trip.inspection_required', details={'reason': 'replacement_bus'})
    return target.id


@router.post('/trips/{trip_id}/replacement')
def replacement(trip_id: str, body: ReplacementInput, idempotency_key: str = Header(),
                db=Depends(get_db, scope='function'), who=Depends(admin)):
    source = trip_access(db, trip_id, who, lock=True)
    return trips.mutate(db, who, idempotency_key, f'replacement:{trip_id}', body, source,
                        lambda: create_replacement(db, source, body, who))
