"""Account administration, deployment capabilities and current-stop navigation."""
import hashlib
import secrets
import time
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .dependencies import actor, admin, get_db, trip_access
from .models import Account, Driver, Guardian
from .schemas import Input, Name
from .services import trips
from .services.routing import plan_route

router = APIRouter(prefix='/api/v1')


class AccountInput(Input):
    display_name: Name
    role: Literal['admin', 'driver', 'guardian']
    subject_id: str | None = Field(default=None, max_length=100)


@router.get('/capabilities')
def capabilities(request: Request, who=Depends(actor)):
    settings = request.app.state.settings
    return {'routing_configured': bool(settings.osrm_url), 'tile_url': settings.tile_url,
            'tile_attribution': settings.tile_attribution, 'mode': settings.mode,
            'public_demo_services': settings.public_demo_services,
            'public_live_locations': settings.public_live_locations}


@router.get('/accounts')
def accounts(db=Depends(get_db, scope="function"), who=Depends(admin)):
    return [{'id': a.id, 'display_name': a.display_name, 'role': a.role, 'active': a.active}
            for a in db.scalars(select(Account))]


@router.post('/accounts', status_code=201)
def create_account(body: AccountInput, db=Depends(get_db, scope="function"), who=Depends(admin)):
    if body.role != 'admin':
        trips.required(db, Driver if body.role == 'driver' else Guardian, body.subject_id)
    token = secrets.token_urlsafe(32)
    row = Account(display_name=body.display_name, role=body.role,
                  token_hash=hashlib.sha256(token.encode()).hexdigest(),
                  driver_id=body.subject_id if body.role == 'driver' else None,
                  guardian_id=body.subject_id if body.role == 'guardian' else None)
    db.add(row)
    db.flush()
    return {'id': row.id, 'token': token, 'role': row.role}


@router.post('/accounts/{account_id}/revoke')
def revoke(account_id: str, db=Depends(get_db, scope="function"), who=Depends(admin)):
    row = trips.required(db, Account, account_id)
    row.active = False
    return {'id': row.id, 'active': False}


@router.get('/trips/{trip_id}/navigation')
def navigation(trip_id: str, request: Request, db=Depends(get_db, scope="function"), who=Depends(actor)):
    trip = trip_access(db, trip_id, who)
    if request.app.state.settings.public_demo_services:
        return {'available': False, 'reason': 'Public service is limited to the fictional planned route; live GPS is kept private.'}
    stop = next((s for s in trips.stops(db, trip) if not s.completed_at), None)
    if stop is None:
        return {'available': False, 'reason': 'no_remaining_stops'}
    fix = trips.latest_location(db, trip)
    if not fix or not 0 <= time.time() - fix.recorded_at <= 15 or fix.accuracy_m > 25:
        return {'available': False, 'reason': 'fresh_accurate_gps_required'}
    # A short per-trip cache limits road requests; expired results are never called live.
    cache = request.app.state.navigation_cache
    key = (trip.id, stop.id)
    cached = cache.get(key)
    if cached and time.time() - cached['calculated_at'] < 20:
        return cached
    source = SimpleNamespace(id='vehicle', latitude=fix.latitude, longitude=fix.longitude)
    route = plan_route([source, stop], request.app.state.settings)
    result = {'available': True, 'trip_stop_id': stop.id, 'calculated_at': time.time(),
              'gps_recorded_at': fix.recorded_at, **route}
    if len(cache) >= 100:
        cache.clear()
    cache[key] = result
    return result
