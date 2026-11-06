"""Local database storage outside temporary and synchronized project folders."""
import os
import sqlite3
import tempfile
import time
from pathlib import Path


def data_directory():
    override = os.getenv('SAFESENSE_DATA_DIR')
    if override:
        return Path(override)
    if os.name == 'nt':
        return Path(os.environ['LOCALAPPDATA']) / 'SafeSense'
    return Path.home() / '.local' / 'share' / 'safesense'


def demo_database():
    folder = data_directory()
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / 'demo.db'
    previous = Path(tempfile.gettempdir()) / 'safesense-local' / 'demo.db'
    if not destination.exists() and previous.is_file():
        # SQLite backup includes committed WAL contents; leave the old file untouched.
        with sqlite3.connect(f'{previous.as_uri()}?mode=ro', uri=True) as source:
            with sqlite3.connect(folder / f'demo-before-move-{time.time_ns()}.db') as backup:
                source.backup(backup)
            with sqlite3.connect(destination) as target:
                source.backup(target)
    return destination
