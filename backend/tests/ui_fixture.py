"""Isolated, fictional API for browser integration tests. Never uses the demo database."""
import socket
import tempfile
from pathlib import Path

import uvicorn

from backend.app import create_app
from backend.config import Settings
from backend.manage import migrate, seed


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="safesense-ui-test-") as folder:
        url = f"sqlite:///{(Path(folder) / 'test.db').as_posix()}"
        migrate(url)
        app = create_app(Settings(database_url=url, mode="demo"))
        with app.state.sessions.begin() as db:
            seed(db)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            print(f"TEST_PORT:{sock.getsockname()[1]}", flush=True)
            uvicorn.Server(uvicorn.Config(app, proxy_headers=False, log_level="error")).run(sockets=[sock])
