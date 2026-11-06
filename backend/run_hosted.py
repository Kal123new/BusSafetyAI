"""Single-process hosted entry point; never enables unauthenticated demo access."""
import logging
from dataclasses import replace
import os
from pathlib import Path

import uvicorn

from .config import Settings
from .manage import migrate


def validate_hosted(settings):
    if settings.mode != 'production':
        raise ValueError('Hosted service requires SAFESENSE_MODE=production')
    if not settings.model_path or not Path(settings.model_path).is_file():
        raise ValueError('Hosted service requires the existing YOLO_MODEL_PATH checkpoint')
    if not (Path(__file__).resolve().parents[1] / 'dist' / 'index.html').is_file():
        raise ValueError('Build the dashboard before starting the hosted service')


def main():
    logging.basicConfig(level=logging.INFO)
    settings = replace(Settings.from_env(), require_model=True)
    validate_hosted(settings)
    logging.info('Applying database migrations')
    migrate(settings.database_url)
    # Import after validation; this uses the same environment as the migration.
    from .app import create_app
    app = create_app(settings)
    uvicorn.run(app, host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', '8000')),
                workers=1, proxy_headers=False, limit_concurrency=32,
                timeout_keep_alive=5, access_log=False)


if __name__ == '__main__':
    main()
