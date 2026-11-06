"""Hugging Face entry point with durable external storage and private sign-in."""
import logging
import os
from dataclasses import replace

import uvicorn

from .config import Settings
from .db import make_engine, session_factory
from .manage import migrate
from .run_hosted import validate_hosted
from .space_bootstrap import ensure_initial_admin
from .space_transport import NeonBridge


def main():
    logging.basicConfig(level=logging.INFO)
    secret = os.environ.get('DATABASE_URL', '')
    if not secret:
        raise SystemExit('Add DATABASE_URL as a Secret in your Space Settings; use your Neon connection string')
    os.environ['SAFESENSE_MODE'] = 'production'
    with NeonBridge(secret) as bridge:
        os.environ['DATABASE_URL'] = bridge.database_url
        settings = replace(Settings.from_env(), require_model=True)
        validate_hosted(settings)
        phase = 'migration'
        try:
            migrate(settings.database_url)
            logging.info('Database migrations complete')
            phase = 'owner-account setup'
            engine = make_engine(settings.database_url)
            try:
                ensure_initial_admin(session_factory(engine), os.getenv('SAFESENSE_INITIAL_ADMIN_TOKEN', ''))
            finally:
                engine.dispose()
        except Exception as exc:
            # SQLAlchemy exceptions may include SQL and parameters. Don't expose those in logs.
            logging.error('Database setup failed at %s (%s). No credentials logged.', phase, type(exc).__name__)
            if isinstance(exc, ValueError):
                logging.error('Initial owner token must contain 32-200 random characters and no internal spaces. Check SAFESENSE_INITIAL_ADMIN_TOKEN.')
            code = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
            if code:
                logging.error('Database SQLSTATE: %s', code)
            raise SystemExit(1) from None
        from .app import create_app
        app = create_app(settings)
        uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', '7860')),
                    workers=1, proxy_headers=False, limit_concurrency=32, access_log=False)


if __name__ == '__main__':
    main()
