from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, func, text
from fastapi import HTTPException

from backend.db import make_engine, session_factory
from backend.manage import migrate, seed
from backend.models import Bus, Driver, Trip, TripStudent, ServicePlan, ScheduledRun
from backend.scheduling import PlanInput, save_plan, ensure_daily

NOW = datetime(2026,10,29,8,tzinfo=timezone.utc)

@pytest.fixture
def data(tmp_path):
    url = f'sqlite:///{(tmp_path / "calendar.db").as_posix()}'
    migrate(url)
    engine = make_engine(url)
    sessions = session_factory(engine)
    with sessions.begin() as db:
        trip = db.get(Trip, seed(db))
        bus = db.get(Bus, trip.bus_id); bus.default_driver_id = trip.driver_id
        from backend.services.trips import snapshot
        snap = snapshot(db, trip)
        body = PlanInput(name='School morning', bus_id=bus.id, shift='morning', trip_type='pickup',
            timezone='Asia/Dubai', weekdays=[0,1,2,3,4], start_date='2026-10-01', end_date='2027-06-30',
            stop_ids=[s['stop_id'] for s in snap['stops']],
            students=[dict(student_id=s['student_id'], pickup_sequence=0, dropoff_sequence=i+1) for i,s in enumerate(snap['students'])])
        plan_id = save_plan(body,db).id
    yield sessions, plan_id, body
    engine.dispose()


def test_daily_idempotent_pending_and_history(data):
    sessions, pid, _ = data
    with sessions.begin() as db:
        ids = ensure_daily(db,NOW)
        assert len(ids)==1
        assert ensure_daily(db,NOW)==[]
        trip=db.get(Trip,ids[0]); assert trip.status=='scheduled' and trip.started_at is None and not trip.route_approved
        rows=list(db.scalars(select(TripStudent).where(TripStudent.trip_id==trip.id)))
        assert all(r.status=='pending' and r.reviewed_at is None and r.boarded_at is None for r in rows)
        old_driver=trip.driver_id
        driver=Driver(display_name='Replacement');db.add(driver);db.flush()
        db.get(Bus,trip.bus_id).default_driver_id=driver.id;db.flush()
        ids2=ensure_daily(db,datetime(2026,10,30,8,tzinfo=timezone.utc))
        assert db.get(Trip,ids2[0]).driver_id==driver.id
        assert trip.driver_id==old_driver


def test_calendar_timezone_holidays_and_pause(data):
    sessions,pid,body=data
    with sessions.begin() as db:
        plan=db.get(ServicePlan,pid)
        config=dict(plan.configuration);config['excluded_dates']=['2026-10-29'];plan.configuration=config
        assert ensure_daily(db,NOW)==[]
        assert ensure_daily(db,datetime(2026,10,31,8,tzinfo=timezone.utc))==[]
        assert ensure_daily(db,datetime(2027,7,1,8,tzinfo=timezone.utc))==[]
        # UTC Thursday evening is Friday in the configured school timezone.
        ids=ensure_daily(db,datetime(2026,10,29,21,tzinfo=timezone.utc))
        assert db.get(Trip,ids[0]).service_date=='2026-10-30'
        plan.active=False;db.flush()
        assert ensure_daily(db,datetime(2026,11,2,8,tzinfo=timezone.utc))==[]


def test_missing_driver_and_overlapping_plans(data):
    sessions,pid,body=data
    with sessions.begin() as db:
        with pytest.raises(HTTPException,match='overlapping'):
            save_plan(body,db)
        bus=db.get(Bus,body.bus_id);bus.default_driver_id=None;db.flush()
        assert ensure_daily(db,NOW)==[]
        assert 'default driver' in db.get(ServicePlan,pid).last_error
        assert db.scalar(select(func.count()).select_from(ScheduledRun))==0


def test_two_workers_create_exactly_one(data):
    sessions,pid,body=data
    def worker():
        with sessions.begin() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            return ensure_daily(db,NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:worker(),range(2)))
    assert sum(map(len,results))==1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ScheduledRun))==1


def test_invalid_calendars(data):
    _,_,body=data
    from pydantic import ValidationError
    for change in ({'timezone':'Not/AZone'},{'weekdays':[7]},{'weekdays':[]},{'end_date':'2025-01-01'}):
        with pytest.raises(ValidationError):
            PlanInput.model_validate({**body.model_dump(),**change})
