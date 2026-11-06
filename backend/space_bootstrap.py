"""Bootstrap only an empty hosted database; never reset an existing account."""
import hashlib
import logging

from sqlalchemy import select, text
from .models import Account


def ensure_initial_admin(sessions, token):
    token = (token or '').strip()
    with sessions.begin() as db:
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(171936415)'))
        if db.scalar(select(Account.id).limit(1)) is not None:
            return False
        if not token or len(token) < 32 or len(token) > 200 or any(c.isspace() for c in token):
            raise ValueError('Set SAFESENSE_INITIAL_ADMIN_TOKEN as a private Space Secret: 32-200 random characters, no spaces')
        db.add(Account(display_name='SafeSense Owner', role='admin',
                       token_hash=hashlib.sha256(token.encode()).hexdigest()))
    logging.getLogger(__name__).info('Created initial owner account; token is never logged')
    return True
