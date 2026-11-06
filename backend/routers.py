import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select, text, case

from .dependencies import actor, admin, get_db, trip_access
from .models import (Bus, Driver, Guardian, LocationSample, Notification, Stop, Student,
                     StudentGuardian, Trip, TripEvent, TripStop)
from .schemas import (AttendanceInput, BusAssignmentInput, BusInput, DriverInput, FinishInput, GuardianInput,
                      LocationInput, RouteInput, StartInput, StopInput, StudentInput, SyncBatch, TripInput)
from .services import geofence, trips
from .services.routing import plan_route

router = APIRouter(prefix="/api/v1")


@router.get("/me")
def me(who=Depends(actor)):
    return vars(who)


@router.get("/catalog")
def catalog(db=Depends(get_db, scope="function"), who=Depends(admin)):
    return {
        "students": [{"id": s.id, "first_name": s.first_name, "last_name": s.last_name, "guardian_ids": list(db.scalars(select(StudentGuardian.guardian_id).where(StudentGuardian.student_id == s.id)))} for s in db.scalars(select(Student))],
        "drivers": [{"id": s.id, "display_name": s.display_name} for s in db.scalars(select(Driver))],
        "guardians": [{"id": s.id, "display_name": s.display_name} for s in db.scalars(select(Guardian))],
        "buses": [{"id": s.id, "bus_code": s.bus_code, "passenger_capacity": s.passenger_capacity, "plate_number": s.plate_number, "default_driver_id": s.default_driver_id} for s in db.scalars(select(Bus))],
        "stops": [{"id": s.id, "name": s.name, "latitude": s.latitude, "longitude": s.longitude} for s in db.scalars(select(Stop))],
    }


@router.post("/guardians", status_code=201)
def add_guardian(body: GuardianInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    row = Guardian(**body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id}


@router.post("/drivers", status_code=201)
def add_driver(body: DriverInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    row = Driver(**body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id}


@router.post("/buses", status_code=201)
def add_bus(body: BusInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    if body.default_driver_id:
        trips.required(db, Driver, body.default_driver_id)
    row = Bus(**body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id}


@router.patch("/buses/{bus_id}/driver")
def assign_bus_driver(bus_id: str, body: BusAssignmentInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    bus = trips.required(db, Bus, bus_id)
    if body.default_driver_id:
        trips.required(db, Driver, body.default_driver_id)
    bus.default_driver_id = body.default_driver_id
    return {"id": bus.id, "default_driver_id": bus.default_driver_id}


@router.post("/stops", status_code=201)
def add_stop(body: StopInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    row = Stop(**body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id}


@router.post("/students", status_code=201)
def add_student(body: StudentInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    for key in set(body.guardian_ids):
        trips.required(db, Guardian, key)
    row = Student(**body.model_dump(exclude={"guardian_ids"}))
    db.add(row)
    db.flush()
    for key in set(body.guardian_ids):
        db.add(StudentGuardian(student_id=row.id, guardian_id=key))
    return {"id": row.id}


@router.post("/trips", status_code=201)
def create_trip(body: TripInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    return trips.create_trip(db, body, who)


@router.get("/trips")
def list_trips(db=Depends(get_db, scope="function"), who=Depends(actor)):
    if who.role == "guardian":
        raise HTTPException(403, "Use your private inbox")
    query = select(Trip).where(Trip.status != 'finished').order_by(
        case((Trip.status.in_(['in_progress', 'awaiting_safety_check']), 0), else_=1),
        Trip.service_date.desc(), Trip.shift.desc(), Trip.created_at.desc())
    if who.role == "driver":
        query = query.where(Trip.driver_id == who.driver_id)
    rows = list(db.scalars(query))
    history = select(Trip).where(Trip.status == 'finished').order_by(Trip.service_date.desc(), Trip.created_at.desc()).limit(100)
    if who.role == 'driver':
        history = history.where(Trip.driver_id == who.driver_id)
    rows.extend(db.scalars(history))
    return [{"id": t.id, "trip_code": t.trip_code, "status": t.status, "version": t.version} for t in rows]


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str, db=Depends(get_db, scope="function"), who=Depends(actor)):
    return trips.snapshot(db, trip_access(db, trip_id, who))


@router.post("/trips/{trip_id}/start")
def start(trip_id: str, body: StartInput, idempotency_key: str = Header(), db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who, lock=True)
    return trips.mutate(db, who, idempotency_key, f"start:{trip_id}", body, trip,
                        lambda: trips.start_trip(db, trip, body, who))


@router.patch("/trips/{trip_id}/students/{student_id}")
def attendance(trip_id: str, student_id: str, body: AttendanceInput,
               idempotency_key: str = Header(), db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who, lock=True)
    return trips.mutate(db, who, idempotency_key, f"attendance:{trip_id}:{student_id}", body, trip,
                        lambda: trips.update_attendance(db, trip, student_id, body, who))


@router.post("/trips/{trip_id}/finish")
def finish(trip_id: str, body: FinishInput, idempotency_key: str = Header(), db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who, lock=True)
    return trips.mutate(db, who, idempotency_key, f"finish:{trip_id}", body, trip,
                        lambda: trips.finish_trip(db, trip, body, who))


@router.get("/trips/{trip_id}/events")
def events(trip_id: str, db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip_access(db, trip_id, who)
    rows = db.scalars(select(TripEvent).where(TripEvent.trip_id == trip_id).order_by(TripEvent.created_at.desc()).limit(200))
    return [{"id": r.id, "event_type": r.event_type, "student_id": r.student_id,
             "actor_id": r.actor_id, "recorded_at": r.created_at, "details": r.details} for r in rows]


@router.post("/trips/{trip_id}/locations")
def location(trip_id: str, body: LocationInput, db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who, lock=True)
    if trip.status != "in_progress":
        trips.fail("GPS updates require an active trip", 409)
    now = time.time()
    if body.recorded_at > now + 2:
        trips.fail("GPS timestamp is in the future")
    previous = db.scalar(select(LocationSample).where(LocationSample.trip_id == trip_id,
                         LocationSample.device_id == body.device_id,
                         LocationSample.sequence_number == body.sequence_number))
    if previous:
        if any(getattr(previous, k) != v for k, v in body.model_dump().items()):
            trips.fail("GPS sequence reused with different data", 409)
        return {"accepted": False, "reason": "duplicate"}
    latest = trips.latest_location(db, trip)
    if latest and body.recorded_at <= latest.recorded_at:
        trips.fail("Out-of-order GPS fix", 409)
    if latest and body.accuracy_m <= 25 and latest.accuracy_m <= 25:
        elapsed = body.recorded_at - latest.recorded_at
        movement = geofence.distance_m(latest.latitude, latest.longitude, body.latitude, body.longitude)
        if movement > 55 * elapsed + latest.accuracy_m + body.accuracy_m:
            trips.fail("Implausible GPS jump; fix rejected")
    db.add(LocationSample(trip_id=trip_id, **body.model_dump()))
    next_stop = next((s for s in trips.stops(db, trip) if not s.completed_at), None)
    if next_stop is None:
        return {"accepted": True, "arrival_status": "no_remaining_stops"}
    if db.bind.dialect.name == "postgresql":
        distance = db.scalar(text("SELECT ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) "
                                  "FROM trip_stops WHERE id=:id"),
                             {"lon": body.longitude, "lat": body.latitude, "id": next_stop.id})
    else:
        distance = geofence.distance_m(body.latitude, body.longitude, next_stop.latitude, next_stop.longitude)
    old = next_stop.observation or {}
    observation = geofence.observe(old, now=now, fix=body.recorded_at, distance=distance,
                                    accuracy=body.accuracy_m, speed=body.speed_mps)
    next_stop.observation = observation
    if observation["status"] == "arrived" and old.get("status") != "arrived":
        next_stop.arrived_at = next_stop.arrived_at or now
        trips.event(db, trip, who, "location.arrived", details={"trip_stop_id": next_stop.id})
    return {"accepted": True, "arrival_status": observation["status"], "distance_m": round(distance, 1),
            "trip_stop_id": next_stop.id, "sample_interval_s": 2 if distance <= 300 else 10}


@router.get("/trips/{trip_id}/location")
def latest_location(trip_id: str, db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who)
    fix = trips.latest_location(db, trip)
    if not fix:
        return {"available": False, "reason": "no_fix"}
    return {"available": 0 <= time.time() - fix.recorded_at <= 15 and fix.accuracy_m <= 25,
            "latitude": fix.latitude, "longitude": fix.longitude, "recorded_at": fix.recorded_at,
            "accuracy_m": fix.accuracy_m, "speed_mps": fix.speed_mps}


@router.get("/trips/{trip_id}/route")
def get_route(trip_id: str, db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who)
    return {"available": trip.route is not None, "approved": trip.route_approved, "route": trip.route}


@router.post("/trips/{trip_id}/route")
def route(trip_id: str, body: RouteInput, request: Request, idempotency_key: str = Header(),
          db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who, lock=True)
    def action():
        if trip.status != "scheduled":
            trips.fail("Route changes are allowed only before departure", 409)
        ordered = trips.stops(db, trip)
        plan = plan_route(ordered, request.app.state.settings, body.strategy)
        positions = {key: i for i, key in enumerate(plan["stop_order"])}
        if any(positions[r.pickup_stop_id] >= positions[r.dropoff_stop_id] for r in trips.roster(db, trip)):
            trips.fail("Proposed order violates pickup-before-drop-off; keep fixed order")
        for i, stop in enumerate(ordered):
            stop.sequence = -i - 1
        db.flush()
        for stop in ordered:
            stop.sequence = positions[stop.id]
        trip.route = {**plan, "planned_at": time.time()}
        trip.route_approved = False
        trips.event(db, trip, who, "route.planned", details={"strategy": body.strategy})
    return trips.mutate(db, who, idempotency_key, f"route:{trip_id}", body, trip, action)


@router.post("/sync/attendance")
def sync(body: SyncBatch, db=Depends(get_db, scope="function"), who=Depends(actor)):
    # All-or-nothing batch: stale versions require reconciliation, never last-write-wins.
    results = []
    for item in body.events:
        trip = trip_access(db, item.trip_id, who, lock=True)
        results.append(trips.mutate(db, who, item.event_id, f"attendance:{item.trip_id}:{item.student_id}",
                                   item.mutation, trip,
                                   lambda i=item, t=trip: trips.update_attendance(db, t, i.student_id, i.mutation, who)))
    return {"results": results}


@router.get("/inbox")
def inbox(db=Depends(get_db, scope="function"), who=Depends(actor)):
    if who.role != "guardian" or not who.guardian_id:
        raise HTTPException(403, "A guardian account is required")
    rows = db.scalars(select(Notification).where(Notification.guardian_id == who.guardian_id)
                      .order_by(Notification.created_at.desc()).limit(100))
    return [{"id": r.id, "message": r.message, "created_at": r.created_at,
             "read_at": r.read_at, "push_state": r.state} for r in rows]


@router.post("/inbox/{notification_id}/read")
def read_notification(notification_id: str, db=Depends(get_db, scope="function"), who=Depends(actor)):
    row = trips.required(db, Notification, notification_id)
    if who.role != "guardian" or row.guardian_id != who.guardian_id:
        raise HTTPException(403, "This notification belongs to another guardian")
    row.read_at = row.read_at or time.time()
    return {"id": row.id, "read_at": row.read_at}
