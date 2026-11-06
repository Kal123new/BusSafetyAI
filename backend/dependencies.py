import hashlib
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from sqlalchemy import select, text

from .models import Account, Trip


def get_db(request: Request):
    # Callers use function scope so commit failures occur before a success response.
    with request.app.state.sessions() as session:
        if (session.bind.dialect.name == "sqlite" and request.method in {"POST", "PATCH", "DELETE"}
                and request.url.path.startswith("/api/")):
            # Serialize local writes, including version/receipt checks.
            session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@dataclass(frozen=True)
class Actor:
    id: str
    role: str
    driver_id: str | None = None
    guardian_id: str | None = None


bearer = HTTPBearer(auto_error=False)


def actor(request: Request, credentials=Depends(bearer), db=Depends(get_db, scope="function")):
    if request.app.state.settings.mode == "demo":
        # Demo has no real credentials and must never be tunnel-accessible.
        if (request.client.host not in {"127.0.0.1", "::1", "testclient"}
                or any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host"))
                or request.url.hostname not in {"127.0.0.1", "localhost", "testserver"}
                or request.headers.get("origin", "") not in {
                    "", "http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:4173", "http://127.0.0.1:4173",
                    f"{request.url.scheme}://{request.url.netloc}"}):
            raise HTTPException(403, "Demo is loopback-only; production requires authentication")
        if not request.headers.get("authorization"):
            return Actor("local-demo", "admin")
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or len(header) > 512:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    hashed = hashlib.sha256(header[7:].encode()).hexdigest()
    account = db.scalar(select(Account).where(Account.token_hash == hashed, Account.active.is_(True)))
    if account is None:
        raise HTTPException(401, "Invalid or revoked token")
    return Actor(account.id, account.role, account.driver_id, account.guardian_id)


def admin(who=Depends(actor)):
    if who.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return who


def trip_access(db, trip_id, who, *, lock=False):
    if who.role not in {"admin", "driver"}:
        raise HTTPException(403, "Trip manifest is private")
    query = select(Trip).where(Trip.id == trip_id)
    if lock:
        query = query.with_for_update()
    trip = db.scalar(query)
    if trip is None:
        raise HTTPException(404, "Trip not found")
    if who.role == "driver" and trip.driver_id != who.driver_id:
        raise HTTPException(403, "Trip is assigned to a different driver")
    return trip
