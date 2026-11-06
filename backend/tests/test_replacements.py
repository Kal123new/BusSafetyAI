import time
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.tests.test_scheduling import data
from backend.dependencies import Actor
from backend.models import Bus, Driver, Trip, TripStudent, PassengerTransfer, Notification
from backend.replacements import ReplacementInput, create_replacement
from backend.schemas import AttendanceInput, FinishInput
from backend.services import trips

@pytest.fixture
def transfer_case(data):
    sessions,_,_ = data
    with sessions.begin() as db:
        source=db.scalar(select(Trip).where(Trip.trip_code=='DEMO-001'))
        driver=Driver(display_name='Relief driver');db.add(driver);db.flush()
        bus=Bus(bus_code='RELIEF',plate_number='RELIEF',passenger_capacity=10,default_driver_id=driver.id);db.add(bus);db.flush()
        students=trips.roster(db,source)
        source.status='in_progress';source.started_at=time.time()-60
        for row in students: row.status='boarded';row.reviewed_at=time.time();row.boarded_at=time.time()-30
        body=ReplacementInput(expected_version=source.version,target_bus_id=bus.id,
            handover_stop_id=trips.stops(db,source)[0].stop_id,
            student_ids=[r.student_id for r in students],reason='Original bus broke down safely',
            source_stopped=True,target_stopped=True,handover_confirmed=True)
        sid=source.id
    return sessions,sid,body


def test_handover_keeps_history_and_requires_inspection(transfer_case):
    sessions,sid,body=transfer_case
    who=Actor('test-admin','admin')
    with sessions.begin() as db:
        source=db.get(Trip,sid)
        def action(): create_replacement(db,source,body,who)
        result=trips.mutate(db,who,'transfer-test-001','replacement:'+sid,body,source,action)
        assert result['status']=='awaiting_safety_check'
        assert result['counts']['on_bus_count']==0
        assert len(result['transfers'])==2
        target=db.get(Trip,result['transfers'][0]['target_trip_id'])
        assert target.status=='scheduled' and not target.route_approved
        assert trips.snapshot(db,target)['counts']['on_bus_count']==2
        assert all(db.get(TripStudent,(sid,student)).status=='boarded' for student in body.student_ids)
        again=trips.mutate(db,who,'transfer-test-001','replacement:'+sid,body,source,action)
        assert again==result
        assert db.scalar(select(func.count()).select_from(PassengerTransfer))==2
        assert all('not a drop-off' in n.message for n in db.scalars(select(Notification)))
        with pytest.raises(HTTPException):
            trips.finish_trip(db,source,FinishInput(expected_version=source.version,operator_confirmed_stopped=True,physically_inspected=False,physically_empty=True,notes='not inspected'),who)
        with pytest.raises(HTTPException):
            trips.update_attendance(db,target,body.student_ids[0],AttendanceInput(expected_version=1,status='absent',operator_confirmed_stopped=True),who)


@pytest.mark.parametrize('change',[
    {'handover_confirmed':False},{'target_stopped':False},{'source_stopped':False},
    {'student_ids':['missing']},
])
def test_unsafe_handover_rejected(transfer_case,change):
    sessions,sid,body=transfer_case
    with sessions.begin() as db:
        with pytest.raises(HTTPException):
            create_replacement(db,db.get(Trip,sid),body.model_copy(update=change),Actor('test','admin'))
        assert db.scalar(select(func.count()).select_from(PassengerTransfer))==0


def test_pending_reassignment_is_not_boarding(transfer_case):
    sessions,sid,body=transfer_case
    with sessions.begin() as db:
        source=db.get(Trip,sid)
        for row in trips.roster(db,source): row.status='pending';row.boarded_at=None
        body=body.model_copy(update={'handover_confirmed':False})
        tid=create_replacement(db,source,body,Actor('test','admin'))
        target=db.get(Trip,tid)
        assert target.trip_type=='pickup'
        assert all(r.status=='pending' and r.reviewed_at is None and r.boarded_at is None for r in trips.roster(db,target))
        assert trips.snapshot(db,target)['counts']['on_bus_count']==0


def test_capacity_and_busy_bus_rejected(transfer_case):
    sessions,sid,body=transfer_case
    with sessions.begin() as db:
        source=db.get(Trip,sid);bus=db.get(Bus,body.target_bus_id);bus.passenger_capacity=1
        with pytest.raises(HTTPException,match='capacity'):
            create_replacement(db,source,body,Actor('test','admin'))
        bus.passenger_capacity=10
        db.add(Trip(trip_code='BUSY',bus_id=bus.id,driver_id=bus.default_driver_id,service_date=source.service_date,shift=source.shift,trip_type='pickup',status='awaiting_safety_check'));db.flush()
        with pytest.raises(HTTPException,match='unfinished'):
            create_replacement(db,source,body,Actor('test','admin'))
