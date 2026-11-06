from backend.tests.test_backend import env, snapshot
from backend.dependencies import actor, Actor


def test_bus_driver_relationship(env):
    client, app, trip_id = env
    before = snapshot(env)
    driver = client.post('/api/v1/drivers', json={'display_name': 'Replacement'}).json()['id']
    result = client.patch(f"/api/v1/buses/{before['bus_id']}/driver", json={'default_driver_id': driver})
    assert result.status_code == 200
    bus = next(b for b in client.get('/api/v1/catalog').json()['buses'] if b['id'] == before['bus_id'])
    assert bus['default_driver_id'] == driver
    assert snapshot(env)['driver_id'] == before['driver_id']
    assert client.patch(f"/api/v1/buses/{before['bus_id']}/driver", json={'default_driver_id': 'missing'}).status_code == 404
    app.dependency_overrides[actor] = lambda: Actor('driver-account', 'driver', driver)
    assert client.patch(f"/api/v1/buses/{before['bus_id']}/driver", json={'default_driver_id': None}).status_code == 403
    assert client.get(f'/api/v1/trips/{trip_id}').status_code == 403


def test_create_bus_with_driver_and_guardian_links(env):
    client, _, _ = env
    catalog = client.get('/api/v1/catalog').json()
    assert all(s['guardian_ids'] for s in catalog['students'])
    body = {'bus_code': 'LINKED', 'plate_number': 'LINKED', 'passenger_capacity': 10, 'default_driver_id': catalog['drivers'][0]['id']}
    assert client.post('/api/v1/buses', json=body).status_code == 201
    body.update(bus_code='BAD', plate_number='BAD', default_driver_id='missing')
    assert client.post('/api/v1/buses', json=body).status_code == 404
