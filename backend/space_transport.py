"""Loopback PostgreSQL transport over Neon's TLS WebSocket endpoint.

Only local application connections are accepted; no database port is exposed.
Neon uses this same transport in its official serverless driver. TLS is verified
on the external WebSocket. Native PG SSL is disabled only on local loopback.
"""
import logging
import re
import socket
import socketserver
import ssl
import threading
from contextlib import suppress

from sqlalchemy.engine import make_url
from websockets.sync.client import connect

log = logging.getLogger(__name__)


def neon_endpoint(connection_string):
    try:
        url = make_url(connection_string)
        if (url.get_backend_name() not in {'postgres', 'postgresql'}
                or not url.username or not url.password or not url.database
                or not re.fullmatch(r'(?:[a-zA-Z0-9-]+\.)+neon\.tech', url.host or '')
                or url.port not in (None, 5432)):
            raise ValueError
    except Exception:
        raise ValueError('DATABASE_URL must be the PostgreSQL connection string from your Neon project') from None
    return url, f'wss://{url.host}/v2'


def relay(local, remote):
    """Relay bytes with backpressure; close both sides on either disconnect."""
    def receive_remote():
        try:
            for message in remote:
                if not isinstance(message, bytes):
                    raise ValueError('Unexpected database transport message')
                local.sendall(message)
        except Exception:
            pass
        finally:
            with suppress(OSError):
                local.shutdown(socket.SHUT_RDWR)

    reader = threading.Thread(target=receive_remote, daemon=True)
    reader.start()
    try:
        while data := local.recv(65536):
            remote.send(data)
    except Exception:
        pass
    finally:
        remote.close()
        with suppress(OSError):
            local.shutdown(socket.SHUT_RDWR)
        reader.join(timeout=5)


class NeonBridge:
    def __init__(self, connection_string):
        self.original_url, self.endpoint = neon_endpoint(connection_string)
        self.server = None
        self.thread = None
        self.connections = set()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(20)

    @property
    def database_url(self):
        if self.server is None:
            raise RuntimeError('Database transport has not started')
        # No caller-controlled host, TLS or authentication options are forwarded.
        url = self.original_url.set(drivername='postgresql+psycopg', host='127.0.0.1',
            port=self.server.server_address[1],
            query={'sslmode': 'disable', 'channel_binding': 'disable', 'connect_timeout': '20'})
        return url.render_as_string(hide_password=False)

    def __enter__(self):
        owner = self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                if not owner.slots.acquire(blocking=False):
                    return
                try:
                    # Standard HTTPS port, certificate verification, no plaintext fallback.
                    with connect(owner.endpoint, ssl=ssl.create_default_context(), compression=None,
                                 open_timeout=15, close_timeout=3, max_size=16*1024*1024) as remote:
                        with owner.lock:
                            owner.connections.add(remote)
                        try:
                            relay(self.request, remote)
                        finally:
                            with owner.lock:
                                owner.connections.discard(remote)
                except Exception:
                    # Never log the connection string, authentication bytes or SQL.
                    log.warning('Database WebSocket disconnected or could not connect')
                finally:
                    owner.slots.release()
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            block_on_close = False
            allow_reuse_address = False
        self.server = Server(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        with self.lock:
            connections = tuple(self.connections)
        for remote in connections:
            remote.close()
        self.thread.join(timeout=5)
        self.server = None
