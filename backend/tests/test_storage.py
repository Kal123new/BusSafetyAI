import sqlite3

from backend import storage


def test_demo_migration_preserves_original_and_never_overwrites(tmp_path, monkeypatch):
    old_folder = tmp_path / 'old' / 'safesense-local'
    old_folder.mkdir(parents=True)
    original = old_folder / 'demo.db'
    with sqlite3.connect(original) as db:
        db.execute('CREATE TABLE checks (value TEXT)')
        db.execute("INSERT INTO checks VALUES ('original')")
    target = tmp_path / 'permanent'
    monkeypatch.setenv('SAFESENSE_DATA_DIR', str(target))
    monkeypatch.setattr(storage.tempfile, 'gettempdir', lambda: str(tmp_path / 'old'))
    destination = storage.demo_database()
    assert original.exists()
    assert len(list(target.glob('demo-before-move-*.db'))) == 1
    with sqlite3.connect(destination) as db:
        assert db.execute('SELECT value FROM checks').fetchone()[0] == 'original'
        db.execute("UPDATE checks SET value='new'")
    assert storage.demo_database() == destination
    with sqlite3.connect(destination) as db:
        assert db.execute('SELECT value FROM checks').fetchone()[0] == 'new'
    with sqlite3.connect(original) as db:
        assert db.execute('SELECT value FROM checks').fetchone()[0] == 'original'
