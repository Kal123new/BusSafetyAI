"""Create a consistent SQLite backup without copying a live WAL database file."""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url
from .config import Settings


def main():
    url = make_url(Settings.from_env().database_url)
    if url.get_backend_name() != 'sqlite' or not url.database:
        raise SystemExit('This command is for the single-server SQLite deployment; use pg_dump for PostgreSQL.')
    source = Path(url.database).resolve()
    folder = source.parent / 'backups'
    folder.mkdir(mode=0o700, exist_ok=True)
    destination = folder / ('safesense-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
            if writer.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise SystemExit('Backup integrity check failed')
    os.chmod(destination, 0o600)
    print(destination)


if __name__ == '__main__':
    main()
