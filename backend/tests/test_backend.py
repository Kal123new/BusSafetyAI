import hashlib
import io
import secrets
import time
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from backend.app import create_app
from backend.config import Settings
from backend.dependencies import Actor, actor
from backend.manage import migrate, seed
from backend.models import Account, Guardian, Notification, Trip, TripEvent
from backend.offline_queue import OfflineQueue
from backend.services.geofence import observe
from backend.services.notifications import dispatch
from backend.services.routing import nearest_order, plan_route


@pytest.fixture
def env(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", mode="demo")
    migrate(settings.database_url)
    app = create_app(settings)
    with app.state.sessions.begin() as db:
        trip_id = seed(db)
    with TestClient(app) as client:
        yield client, app, trip_id


def snapshot(env):
    return env[0].get(f"/api/v1/trips/{env[2]}").json()


def change(env, student, status, **extra):
    client, _, trip_id = env
    body = {"expected_version": snapshot(env)["version"], "status": status,
            "operator_confirmed_stopped": True, **extra}
    return client.patch(f"/api/v1/trips/{trip_id}/students/{student}", json=body,
                        headers={"Idempotency-Key": str(uuid.uuid4())})


def prepare(env, status="boarded"):
    for student in snapshot(env)["students"]:
        assert change(env, student["student_id"], status).status_code == 200


def start(env, key=None):
    return env[0].post(f"/api/v1/trips/{env[2]}/start", json={
        "expected_version": snapshot(env)["version"], "route_confirmed": True,
        "operator_confirmed_stopped": True,
    }, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def test_health_and_openapi(env):
    client, _, _ = env
    assert client.get('/health').json()['database_online']
    assert not client.get('/health').json()['model_loaded']
    assert client.get('/health').json()['confidence_threshold'] == 0.45
    assert '/api/v1/trips/{trip_id}/start' in client.get('/openapi.json').json()['paths']


def test_confidence_default_and_override(monkeypatch):
    monkeypatch.delenv('YOLO_CONFIDENCE', raising=False)
    assert Settings.from_env().confidence == 0.45
    monkeypatch.setenv('YOLO_CONFIDENCE', '0.6')
    assert Settings.from_env().confidence == 0.6


def test_write_commits_before_success_headers(env):
    _, app, _ = env
    committed_at_send = []

    async def checked_app(scope, receive, send):
        async def checked_send(message):
            if message['type'] == 'http.response.start' and message['status'] == 201:
                with app.state.sessions() as db:
                    committed_at_send.append(db.scalar(select(Guardian).where(
                        Guardian.display_name == 'Committed before response')) is not None)
            await send(message)
        await app(scope, receive, checked_send)

    with TestClient(checked_app) as client:
        response = client.post('/api/v1/guardians', json={'display_name': 'Committed before response'})
    assert response.status_code == 201
    assert committed_at_send == [True]


def test_account_creation_and_private_guardian_inbox(env):
    client, app, _ = env
    guardian = client.get('/api/v1/catalog').json()['guardians'][0]
    created = client.post('/api/v1/accounts', json={'display_name': 'Test parent', 'role': 'guardian', 'subject_id': guardian['id']})
    assert created.status_code == 201
    data = created.json()
    auth = {'Authorization': f"Bearer {data['token']}"}
    assert client.get('/api/v1/me', headers=auth).json()['role'] == 'guardian'
    assert client.get('/api/v1/inbox', headers=auth).status_code == 200
    assert client.get('/api/v1/trips', headers=auth).status_code == 403
    assert client.post('/api/v1/accounts', headers=auth, json={'display_name': 'No', 'role': 'admin'}).status_code == 403
    assert client.post(f"/api/v1/accounts/{data['id']}/revoke").status_code == 200
    assert client.get('/api/v1/me', headers=auth).status_code == 401


def test_stationary_evidence_can_replace_checkbox(env):
    prepare(env); start(env)
    trip = snapshot(env); stop = trip['stops'][1]; now = time.time()
    for sequence, seconds in enumerate([6, 3, 0]):
        body = dict(device_id='stationary-test', sequence_number=sequence, recorded_at=now-seconds,
                    latitude=stop['latitude'], longitude=stop['longitude'], accuracy_m=5, speed_mps=0)
        assert env[0].post(f'/api/v1/trips/{env[2]}/locations', json=body).status_code == 200
    assert snapshot(env)['motion']['status'] == 'stationary'
    student = next(s for s in trip['students'] if s['dropoff_stop_id'] == stop['id'])
    assert change(env, student['student_id'], 'dropped', operator_confirmed_stopped=False,
                  override_reason='Test operator confirmed assigned stop').status_code == 200


def test_public_demo_services_never_send_live_location(env):
    from dataclasses import replace
    env[1].state.settings = replace(env[1].state.settings, public_demo_services=True, osrm_url='https://router.project-osrm.org')
    response = env[0].get(f'/api/v1/trips/{env[2]}/navigation')
    assert response.status_code == 200 and response.json()['available'] is False


def test_public_routing_rejects_non_demo_coordinates():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        plan_route([SimpleNamespace(latitude=25, longitude=55)],
                   Settings(database_url='sqlite://', mode='demo', public_demo_services=True, osrm_url='https://router.project-osrm.org'))
    assert error.value.status_code == 403


def test_public_live_navigation_requires_fresh_fix(env, monkeypatch):
    from dataclasses import replace
    from backend import operations
    env[1].state.settings = replace(env[1].state.settings, public_live_locations=True,
                                   osrm_url='https://router.project-osrm.org')
    calls = []
    def route(stops, settings):
        calls.append([(s.latitude, s.longitude) for s in stops])
        return {'distance_m': 900, 'eta_s': 60, 'geometry': {'type': 'LineString', 'coordinates': []}}
    monkeypatch.setattr(operations, 'plan_route', route)
    endpoint = f'/api/v1/trips/{env[2]}/navigation'
    assert env[0].get('/api/v1/capabilities').json()['public_live_locations'] is True
    assert env[0].get(endpoint).json()['available'] is False
    assert calls == []
    prepare(env); start(env)
    payload = dict(device_id='synthetic-live', sequence_number=1, recorded_at=time.time(),
                   latitude=25.0, longitude=55.0, accuracy_m=5, speed_mps=0)
    assert env[0].post(f'/api/v1/trips/{env[2]}/locations', json=payload).status_code == 200
    result = env[0].get(endpoint).json()
    assert result['available'] is True and result['eta_s'] == 60
    assert calls[0][0] == (25.0, 55.0)
    env[0].get(endpoint)
    assert len(calls) == 1, 'Cached navigation must not repeatedly call the provider'


def test_public_live_router_accepts_non_demo_coordinates_with_consent():
    seen = []
    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={'code': 'Ok', 'routes': [{'distance': 900, 'duration': 60,
            'geometry': {'type': 'LineString', 'coordinates': []}, 'legs': []}]})
    stops = [SimpleNamespace(id='a', latitude=25, longitude=55), SimpleNamespace(id='b', latitude=25.01, longitude=55.01)]
    settings = Settings(database_url='sqlite://', mode='demo', public_live_locations=True,
                        osrm_url='https://router.project-osrm.org')
    result = plan_route(stops, settings, client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert result['eta_s'] == 60 and '55,25;55.01,25.01' in seen[0]


def test_browser_gps_unknown_speed_is_not_stopped(env):
    prepare(env)
    assert start(env).status_code == 200
    trip = snapshot(env)
    stop = trip['stops'][1]
    payload = dict(device_id='browser-test', sequence_number=1, recorded_at=time.time(),
                   latitude=stop['latitude'], longitude=stop['longitude'], accuracy_m=5, speed_mps=None)
    response = env[0].post(f'/api/v1/trips/{env[2]}/locations', json=payload)
    assert response.status_code == 200
    assert response.json()['arrival_status'] == 'unknown'
    saved = env[0].get(f'/api/v1/trips/{env[2]}/location').json()
    assert saved['available'] and saved['speed_mps'] is None
    assert snapshot(env)['counts']['on_bus_count'] == 2
    student = trip['students'][0]['student_id']
    assert change(env, student, 'dropped').status_code == 422


def test_moving_or_unknown_speed_revokes_arrival():
    arrived = {'status': 'arrived', 'last_fix': 1}
    assert observe(arrived, now=2, fix=2, distance=0, accuracy=1, speed=None)['status'] == 'unknown'
    assert observe(arrived, now=2, fix=2, distance=0, accuracy=1, speed=10)['status'] == 'outside'


def test_pending_not_absent(env):
    counts = snapshot(env)['counts']
    assert counts['pending_count'] == 2
    assert counts['absent_count'] == counts['on_bus_count'] == 0
    assert start(env).status_code == 422


def test_full_trip_and_inspection(env):
    prepare(env)
    assert start(env).status_code == 200
    for student in snapshot(env)['students']:
        assert change(env, student['student_id'], 'dropped', override_reason='Operator confirmed correct stop despite unavailable GPS').status_code == 200
    trip = snapshot(env)
    assert trip['status'] == 'awaiting_safety_check'
    assert trip['last_dropoff_at'] is not None
    payload = dict(expected_version=trip['version'], physically_inspected=False, physically_empty=True,
                   operator_confirmed_stopped=True, notes='Walked the entire bus')
    headers = {'Idempotency-Key': str(uuid.uuid4())}
    assert env[0].post(f'/api/v1/trips/{env[2]}/finish', json=payload, headers=headers).status_code == 422
    payload['physically_inspected'] = True
    result = env[0].post(f'/api/v1/trips/{env[2]}/finish', json=payload, headers=headers)
    assert result.status_code == 200
    assert result.json()['status'] == 'finished'
    assert result.json()['ended_at'] >= trip['last_dropoff_at']


def test_duplicate_start_is_idempotent(env):
    prepare(env)
    headers = {'Idempotency-Key': str(uuid.uuid4())}
    body = {'expected_version': snapshot(env)['version'], 'route_confirmed': True, 'operator_confirmed_stopped': True}
    url = f'/api/v1/trips/{env[2]}/start'
    first = env[0].post(url, json=body, headers=headers)
    second = env[0].post(url, json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with env[1].state.sessions() as db:
        assert len(db.scalars(select(Notification)).all()) == 2
    body['route_confirmed'] = False
    assert env[0].post(url, json=body, headers=headers).status_code == 409


def test_stale_attendance_conflict(env):
    student = snapshot(env)['students'][0]['student_id']
    change(env, student, 'boarded')
    result = env[0].patch(f'/api/v1/trips/{env[2]}/students/{student}',
        json={'expected_version': 1, 'status': 'absent', 'operator_confirmed_stopped': True},
        headers={'Idempotency-Key': str(uuid.uuid4())})
    assert result.status_code == 409
    assert snapshot(env)['counts']['on_bus_count'] == 1


def test_no_drop_before_departure_or_without_stop_confirmation(env):
    student = snapshot(env)['students'][0]['student_id']
    assert change(env, student, 'dropped').status_code == 422
    assert change(env, student, 'boarded', operator_confirmed_stopped=False).status_code == 422
    prepare(env); start(env)
    assert change(env, student, 'dropped').status_code == 422
    assert change(env, student, 'absent').status_code == 409


def test_all_absent_still_needs_inspection(env):
    prepare(env, 'absent')
    result = start(env)
    assert result.json()['status'] == 'awaiting_safety_check'
    assert result.json()['last_dropoff_at'] is None


def test_persistence_across_app_restart(env):
    student = snapshot(env)['students'][0]['student_id']
    change(env, student, 'boarded')
    app = create_app(env[1].state.settings)
    with TestClient(app) as client:
        assert client.get(f'/api/v1/trips/{env[2]}').json()['counts']['on_bus_count'] == 1


def test_demo_rejects_tunnel_headers(env):
    assert env[0].get('/api/v1/trips', headers={'X-Forwarded-For': '198.51.100.1'}).status_code == 403
    assert env[0].get('/api/v1/trips', headers={'Origin': 'https://unrelated.example'}).status_code == 403


def test_production_requires_token_and_revocation(env):
    settings = Settings(database_url=env[1].state.settings.database_url)
    app = create_app(settings)
    token = secrets.token_urlsafe(32)
    with app.state.sessions.begin() as db:
        account = Account(display_name='Test admin', role='admin', token_hash=hashlib.sha256(token.encode()).hexdigest())
        db.add(account); db.flush(); key = account.id
    with TestClient(app) as client:
        assert client.get('/api/v1/trips').status_code == 401
        assert client.get('/api/v1/trips', headers={'Authorization': f'Bearer {token}'}).status_code == 200
        with app.state.sessions.begin() as db:
            db.get(Account, key).active = False
        assert client.get('/api/v1/trips', headers={'Authorization': f'Bearer {token}'}).status_code == 401


def test_driver_and_guardian_scope(env):
    app = env[1]
    app.dependency_overrides[actor] = lambda: Actor('test-driver', 'driver', 'another-driver')
    assert env[0].get(f'/api/v1/trips/{env[2]}').status_code == 403
    assert env[0].post('/api/v1/buses', json={'bus_code': 'X', 'plate_number': 'Y', 'passenger_capacity': 10}).status_code == 403
    app.dependency_overrides[actor] = lambda: Actor('test-guardian', 'guardian', guardian_id='another-guardian')
    assert env[0].get(f'/api/v1/trips/{env[2]}').status_code == 403
    assert env[0].get('/api/v1/inbox').json() == []


def test_inbox_delivery_and_isolation(env):
    prepare(env); start(env)
    app = env[1]
    with app.state.sessions.begin() as db:
        assert dispatch(db, app.state.settings) == 2
        rows = db.scalars(select(Notification)).all()
        target = rows[0].guardian_id
        other_notice = rows[1].id
    app.dependency_overrides[actor] = lambda: Actor('guardian-test', 'guardian', guardian_id=target)
    inbox = env[0].get('/api/v1/inbox').json()
    assert len(inbox) == 1 and inbox[0]['push_state'] == 'inbox'
    assert env[0].post(f"/api/v1/inbox/{inbox[0]['id']}/read").status_code == 200
    assert env[0].post(f'/api/v1/inbox/{other_notice}/read').status_code == 403


def test_push_retry(env):
    prepare(env); start(env)
    settings = Settings(database_url=env[1].state.settings.database_url, ntfy_url='http://private-push')
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with env[1].state.sessions.begin() as db:
        for g in db.scalars(select(Guardian)):
            g.push_topic = 'private-test-topic-1234'
        dispatch(db, settings, client=httpx.Client(transport=transport))
        rows = db.scalars(select(Notification)).all()
        assert all(r.state == 'retry' and r.attempts == 1 and r.published_at for r in rows)


def test_gps_does_not_drop_students(env):
    prepare(env); start(env)
    stop = snapshot(env)['stops'][1]
    now = time.time()
    for index, offset in enumerate((10, 5, 0)):
        body = dict(device_id='demo-device', sequence_number=index, recorded_at=now-offset,
                    latitude=stop['latitude'], longitude=stop['longitude'], accuracy_m=5, speed_mps=0)
        response = env[0].post(f'/api/v1/trips/{env[2]}/locations', json=body)
        assert response.status_code == 200, response.text
    assert response.json()['arrival_status'] == 'arrived'
    assert snapshot(env)['counts']['on_bus_count'] == 2
    assert env[0].post(f'/api/v1/trips/{env[2]}/locations', json=body).json()['reason'] == 'duplicate'
    student = next(s for s in snapshot(env)['students'] if s['dropoff_stop_id'] == stop['id'])
    assert change(env, student['student_id'], 'dropped').status_code == 200


def test_bad_gps_is_not_arrival(env):
    prepare(env); start(env)
    stop = snapshot(env)['stops'][1]
    body = dict(device_id='demo', sequence_number=1, recorded_at=time.time()-30,
                latitude=stop['latitude'], longitude=stop['longitude'], accuracy_m=100, speed_mps=0)
    result = env[0].post(f'/api/v1/trips/{env[2]}/locations', json=body)
    assert result.json()['arrival_status'] == 'unknown'
    body['sequence_number'] = 2
    body['recorded_at'] -= 10
    assert env[0].post(f'/api/v1/trips/{env[2]}/locations', json=body).status_code == 409


def test_geofence_pass_by_and_hysteresis():
    state = {}
    for second in (0, 5, 10):
        state = observe(state, now=second, fix=second, distance=10, accuracy=5, speed=0)
    assert state['status'] == 'arrived'
    assert observe(state, now=12, fix=12, distance=65, accuracy=10, speed=0)['status'] == 'arrived'
    assert observe(state, now=12, fix=12, distance=100, accuracy=10, speed=0)['status'] == 'outside'
    assert observe({}, now=0, fix=0, distance=0, accuracy=5, speed=10)['status'] == 'outside'


def frame(color):
    stream = io.BytesIO(); Image.new('RGB', (100, 100), color).save(stream, format='JPEG')
    return stream.getvalue()


@pytest.mark.parametrize('data,status', [(b'bad-image', 'decode_error'), (frame('black'), 'too_dark'), (frame('white'), 'model_unavailable')], ids=['corrupt', 'black', 'model-missing'])
def test_camera_unknown_not_zero(env, data, status):
    result = env[0].post('/predict', files={'file': ('frame.jpg', data, 'image/jpeg')}).json()
    assert result['frame_status'] == status
    assert result['visible_person_count'] is None


def test_camera_stale_and_size(env):
    assert env[0].post('/predict', files={'file': ('f.jpg', frame('white'))}, data={'captured_at': time.time()-60}).json()['frame_status'] == 'stale'
    assert env[0].post('/predict', files={'file': ('f.jpg', b'x' * (5 * 1024 * 1024 + 1))}).status_code == 413


def test_route_unavailable_keeps_trip(env):
    before = snapshot(env)
    result = env[0].post(f'/api/v1/trips/{env[2]}/route', json={'expected_version': before['version']},
                        headers={'Idempotency-Key': str(uuid.uuid4())})
    assert result.status_code == 503
    assert snapshot(env)['version'] == before['version']


def test_osrm_adapter_and_nearest():
    matrix = [[0, 10, 2, 9], [10, 0, 1, 1], [2, 1, 0, 5], [9, 1, 5, 0]]
    assert nearest_order(matrix) == [0, 2, 1, 3]
    def respond(request):
        if '/table/' in str(request.url):
            return httpx.Response(200, json={'code': 'Ok', 'durations': matrix})
        return httpx.Response(200, json={'code': 'Ok', 'routes': [{'distance': 100, 'duration': 20,
            'geometry': {'type': 'LineString', 'coordinates': []}, 'legs': []}]})
    stops = [SimpleNamespace(id=str(i), longitude=54+i/100, latitude=24) for i in range(4)]
    settings = Settings(database_url='sqlite://', osrm_url='http://local-router')
    result = plan_route(stops, settings, 'nearest', httpx.Client(transport=httpx.MockTransport(respond)))
    assert result['stop_order'] == ['0', '2', '1', '3']
    assert result['eta_s'] == 20


def test_offline_queue_conflict_is_not_silently_merged(tmp_path):
    queue = OfflineQueue(tmp_path / 'offline.db')
    payload = {'event_id': 'offline-event-123', 'trip_id': 'x', 'student_id': 'y', 'mutation': {}}
    queue.enqueue(payload); queue.enqueue(payload)
    result = queue.flush('http://local', 'test', httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(409))))
    assert result == 'conflict'
    queue.close()
    queue = OfflineQueue(tmp_path / 'offline.db')
    assert queue.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0] == 1
    assert queue.flush('http://local', 'test', httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))) == 'conflict'
    with pytest.raises(ValueError):
        queue.resolve_conflict('offline-event-123')
    queue.resolve_conflict('offline-event-123', discard_confirmed=True)
    assert queue.flush('http://local', 'test', httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))) == 'synced'
    queue.close()


def test_sync_retry_and_atomic_rollback(env):
    trip = snapshot(env)
    event = {'event_id': str(uuid.uuid4()), 'trip_id': trip['id'], 'student_id': trip['students'][0]['student_id'],
             'mutation': {'expected_version': 1, 'status': 'boarded', 'operator_confirmed_stopped': True}}
    first = env[0].post('/api/v1/sync/attendance', json={'events': [event]})
    assert first.status_code == 200
    assert env[0].post('/api/v1/sync/attendance', json={'events': [event]}).json() == first.json()
    second = {**event, 'event_id': str(uuid.uuid4()), 'student_id': trip['students'][1]['student_id'],
              'mutation': {**event['mutation'], 'expected_version': 2}}
    bad = {**event, 'event_id': str(uuid.uuid4()), 'mutation': {**event['mutation'], 'expected_version': 1}}
    assert env[0].post('/api/v1/sync/attendance', json={'events': [second, bad]}).status_code == 409
    assert snapshot(env)['counts']['on_bus_count'] == 1


def test_arrival_is_lost_after_fix_goes_stale():
    result = observe({'status': 'arrived', 'last_fix': 0}, now=30, fix=0, distance=0, accuracy=5, speed=0)
    assert result['status'] == 'unknown'


def test_inference_valid_result_and_busy(env):
    service = env[1].state.inference
    class Model:
        names = {0: 'person'}
        def predict(self, image, **kwargs):
            return [SimpleNamespace(boxes=[], names=self.names)]
    service.model = Model()
    result = service.predict(frame('white'), 'test-frame', time.time())
    assert result['frame_status'] == 'valid' and result['visible_person_count'] == 0
    service.lock.acquire()
    try:
        with pytest.raises(Exception) as error:
            service.predict(frame('white'), 'busy', time.time())
        assert error.value.status_code == 429
    finally:
        service.lock.release()


def test_ortools_fixed_endpoints():
    pytest.importorskip('ortools')
    from backend.services.routing import optimize_order
    order = optimize_order([[0, 10, 2, 9], [10, 0, 1, 1], [2, 1, 0, 5], [9, 1, 5, 0]])
    assert order[0] == 0 and order[-1] == 3 and sorted(order) == [0, 1, 2, 3]


def test_active_bus_constraint(env):
    prepare(env); start(env)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with env[1].state.sessions.begin() as db:
            first = db.get(Trip, env[2])
            db.add(Trip(trip_code='CONFLICT', bus_id=first.bus_id, driver_id=first.driver_id,
                        service_date='2026-10-11', shift='afternoon', trip_type='dropoff', status='in_progress'))
            db.flush()


def test_schema_rejects_invalid_coordinates(env):
    response = env[0].post('/api/v1/stops', json={'name': 'bad', 'latitude': 100, 'longitude': 0})
    assert response.status_code == 422


def test_missing_model_file_does_not_crash(tmp_path):
    from backend.services.inference import Inference
    model = Inference(Settings(database_url='sqlite://', model_path=str(tmp_path / 'missing.pt')))
    model.load()
    assert model.model is None


def test_postgresql_migration_compiles():
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    output = io.StringIO()
    config = Config(str(Path(__file__).parents[1] / 'alembic.ini'), output_buffer=output)
    config.attributes['database_url'] = 'postgresql+psycopg://unused:unused@localhost/unused'
    command.upgrade(config, 'head', sql=True)
    assert 'geography(Point,4326)' in output.getvalue()
    assert 'CREATE UNIQUE INDEX one_active_bus' in output.getvalue()


def test_pickup_manifest_can_review_pending(env):
    with env[1].state.sessions.begin() as db:
        db.get(Trip, env[2]).trip_type = 'pickup'
    prepare(env, 'pending')
    assert start(env).status_code == 200
    assert snapshot(env)['counts']['on_bus_count'] == 0
    student = snapshot(env)['students'][0]['student_id']
    result = change(env, student, 'boarded', override_reason='Operator confirmed pickup location with GPS unavailable')
    assert result.status_code == 200
    assert result.json()['counts']['on_bus_count'] == 1


def test_missing_guardian_blocks_start(env):
    from backend.models import StudentGuardian
    from sqlalchemy import delete
    prepare(env)
    with env[1].state.sessions.begin() as db:
        db.execute(delete(StudentGuardian))
    assert start(env).status_code == 422


def test_notification_success_does_not_claim_read(env):
    prepare(env); start(env)
    settings = Settings(database_url=env[1].state.settings.database_url, ntfy_url='http://local-push')
    with env[1].state.sessions.begin() as db:
        for guardian in db.scalars(select(Guardian)):
            guardian.push_topic = 'private-demo-topic-12345'
        dispatch(db, settings, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
        assert all(n.state == 'sent' and n.read_at is None for n in db.scalars(select(Notification)))


def test_offline_replay_success(tmp_path):
    queue = OfflineQueue(tmp_path / 'queue.db')
    queue.enqueue({'event_id': 'event-demo-123', 'trip_id': 'trip', 'student_id': 'student', 'mutation': {}})
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    assert queue.flush('http://local', 'test', client) == 'synced'
    assert queue.db.execute('SELECT state FROM pending').fetchone()[0] == 'sent'
    queue.close()
