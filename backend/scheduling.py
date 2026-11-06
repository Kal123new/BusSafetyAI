"""School-day trip generation. Each run is a fresh, unstarted manifest."""
from datetime import date, datetime, timezone
import logging
from threading import Event, Thread
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .dependencies import Actor, actor, admin, get_db
from .models import Bus, ServicePlan, ScheduledRun, Trip
from .schemas import Input, Identifier, Assignment, TripInput
from .services import trips

router = APIRouter(prefix='/api/v1')
log = logging.getLogger(__name__)


class PlanInput(Input):
    name: str = Field(min_length=1, max_length=100)
    bus_id: Identifier
    shift: str = Field(pattern='^(morning|afternoon)$')
    trip_type: str = Field(pattern='^(pickup|dropoff)$')
    stop_ids: list[Identifier] = Field(min_length=2, max_length=100)
    students: list[Assignment] = Field(min_length=1, max_length=100)
    timezone: str = Field(min_length=1, max_length=100)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start_date: date
    end_date: date
    excluded_dates: list[date] = Field(default_factory=list, max_length=366)
    active: bool = True

    @model_validator(mode='after')
    def valid_calendar(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Choose a valid school timezone, such as Asia/Dubai')
        if any(day not in range(7) for day in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError('Choose distinct school weekdays')
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 366:
            raise ValueError('Service dates must span at most one year')
        return self


def trip_body(db, plan, service_date):
    bus = trips.required(db, Bus, plan.bus_id)
    if not bus.default_driver_id:
        trips.fail('Assign a default driver to this bus before enabling its service plan')
    config = plan.configuration
    return TripInput(trip_code=f'{plan.name[:24]}-{service_date}-{plan.id[:8]}',
        bus_id=bus.id, driver_id=bus.default_driver_id, service_date=service_date,
        **{key: config[key] for key in ('shift', 'trip_type', 'stop_ids', 'students')})


def ensure_daily(db, now=None):
    now = now or datetime.now(timezone.utc)
    created = []
    # Row locks serialize concurrent workers on Postgres. The primary key is a second guard.
    plans = db.scalars(select(ServicePlan).where(ServicePlan.active.is_(True)).order_by(ServicePlan.id).with_for_update()).all()
    for plan in plans:
        config = plan.configuration
        today = now.astimezone(ZoneInfo(config['timezone'])).date()
        day = today.isoformat()
        if not config['start_date'] <= day <= config['end_date'] or today.weekday() not in config['weekdays'] or day in config['excluded_dates']:
            continue
        if db.get(ScheduledRun, (plan.id, day)):
            continue
        try:
            with db.begin_nested():
                body = trip_body(db, plan, day)
                result = trips.create_trip(db, body, Actor('daily-scheduler', 'admin'))
                db.add(ScheduledRun(plan_id=plan.id, service_date=day, trip_id=result['id']))
                db.flush()
                trips.event(db, db.get(Trip, result['id']), Actor('daily-scheduler', 'admin'), 'trip.generated', details={'plan_id': plan.id})
            plan.last_error = None
            created.append(result['id'])
        except IntegrityError:
            if not db.get(ScheduledRun, (plan.id, day)):
                plan.last_error = 'A conflicting record prevented creation. Review this service plan.'
        except HTTPException as exc:
            plan.last_error = str(exc.detail)[:500]
    return created


def save_plan(body, db, plan=None):
    # Lock buses in a consistent way to serialize conflicting plan setup.
    bus = db.scalar(select(Bus).where(Bus.id == body.bus_id).with_for_update())
    if not bus:
        trips.fail('Bus not found', 404)
    row = plan or ServicePlan(id=__import__('uuid').uuid4().hex, name=body.name, bus_id=body.bus_id)
    row.name, row.bus_id, row.active = body.name, body.bus_id, body.active
    row.configuration = body.model_dump(mode='json', exclude={'name', 'bus_id', 'active'})
    if body.active:
        trips.validate_trip(db, trip_body(db, row, body.start_date.isoformat()))
        others = db.scalars(select(ServicePlan).where(ServicePlan.active.is_(True), ServicePlan.id != row.id)).all()
        for other in others:
            other_bus = db.get(Bus, other.bus_id)
            c = other.configuration
            overlap = max(c['start_date'], str(body.start_date)) <= min(c['end_date'], str(body.end_date))
            shared_resource = other.bus_id == body.bus_id or other_bus.default_driver_id == bus.default_driver_id
            if shared_resource and c['shift'] == body.shift and overlap and set(c['weekdays']) & set(body.weekdays):
                trips.fail('This bus or driver already has an overlapping service plan for this shift. Pause or edit that plan first.', 409)
    row.last_error = None
    db.add(row)
    db.flush()
    return row


@router.get('/service-plans')
def list_plans(db=Depends(get_db, scope='function'), who=Depends(admin)):
    return [dict(id=p.id, name=p.name, bus_id=p.bus_id, active=p.active, last_error=p.last_error, **p.configuration)
            for p in db.scalars(select(ServicePlan).order_by(ServicePlan.created_at.desc()))]


@router.post('/service-plans', status_code=201)
def add_plan(body: PlanInput, db=Depends(get_db, scope='function'), who=Depends(admin)):
    plan = save_plan(body, db)
    ensure_daily(db)
    return {'id': plan.id}


@router.patch('/service-plans/{plan_id}')
def update_plan(plan_id: str, body: PlanInput, db=Depends(get_db, scope='function'), who=Depends(admin)):
    plan = db.scalar(select(ServicePlan).where(ServicePlan.id == plan_id).with_for_update())
    if plan is None:
        trips.fail('Service plan not found', 404)
    save_plan(body, db, plan)
    ensure_daily(db)
    return {'id': plan.id}


@router.post('/trips/ensure-daily')
def prepare_today(db=Depends(get_db, scope='function'), who=Depends(actor)):
    if who.role not in {'driver', 'admin'}:
        trips.fail('Only drivers and administrators can prepare daily service', 403)
    ensure_daily(db)
    return {'ready': True}


def start_scheduler(sessions):
    stop = Event()
    def run():
        while not stop.is_set():
            try:
                with sessions.begin() as db:
                    if db.bind.dialect.name == 'sqlite':
                        db.execute(text('BEGIN IMMEDIATE'))
                    ensure_daily(db)
            except Exception:
                log.warning('Daily trip generation could not complete; it will retry.')
            stop.wait(60)
    worker = Thread(target=run, name='daily-trips', daemon=True)
    worker.start()
    return stop, worker
