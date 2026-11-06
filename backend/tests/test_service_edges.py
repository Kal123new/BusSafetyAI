from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from backend.config import Settings
from backend.services.geofence import distance_m, observe
from backend.services.routing import plan_route


def test_distance_units_and_identity():
    assert distance_m(24, 54, 24, 54) == 0
    assert 110000 < distance_m(0, 0, 1, 0) < 112000


def test_duplicate_fix_does_not_extend_dwell():
    state = observe({}, now=10, fix=10, distance=10, accuracy=5, speed=0)
    assert observe(state, now=11, fix=10, distance=10, accuracy=5, speed=0) == state


def test_dwell_resets_after_gap():
    state = observe({}, now=0, fix=0, distance=10, accuracy=5, speed=0)
    state = observe(state, now=20, fix=20, distance=10, accuracy=5, speed=0)
    assert state['status'] == 'candidate' and state['count'] == 1


@pytest.mark.parametrize('accuracy,distance,status', [(40, 0, 'unknown'), (10, 45, 'outside'), (5, 10, 'candidate')])
def test_location_uncertainty(accuracy, distance, status):
    assert observe({}, now=1, fix=1, distance=distance, accuracy=accuracy, speed=0)['status'] == status


@pytest.mark.parametrize('response', [httpx.Response(500), httpx.Response(200, json={'code': 'NoRoute'})])
def test_osrm_failures_are_explicit(response):
    stops = [SimpleNamespace(id='a', latitude=24, longitude=54), SimpleNamespace(id='b', latitude=25, longitude=55)]
    settings = Settings(database_url='sqlite://', osrm_url='http://local-router')
    with pytest.raises(HTTPException) as error:
        plan_route(stops, settings, client=httpx.Client(transport=httpx.MockTransport(lambda r: response)))
    assert error.value.status_code == 503


@pytest.mark.parametrize('matrix', [[[0]], [[0, None], [1, 0]], [[0, -1], [1, 0]], [[0, True], [1, 0]]])
def test_bad_road_matrix_is_unavailable(matrix):
    stops = [SimpleNamespace(id='a', latitude=24, longitude=54), SimpleNamespace(id='b', latitude=25, longitude=55)]
    settings = Settings(database_url='sqlite://', osrm_url='http://local-router')
    response = httpx.Response(200, json={'code': 'Ok', 'durations': matrix})
    with pytest.raises(HTTPException) as error:
        plan_route(stops, settings, strategy='nearest', client=httpx.Client(transport=httpx.MockTransport(lambda r: response)))
    assert error.value.status_code == 503


def test_reject_invalid_config():
    with pytest.raises(ValueError):
        Settings(database_url='sqlite://', confidence=0)
    with pytest.raises(ValueError):
        Settings(database_url='sqlite://', mode='no-auth-internet')
