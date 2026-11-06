import hashlib
import socket
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import select

pytest.importorskip('websockets')
from websockets.sync.client import connect as real_connect
from websockets.sync.server import serve

from backend.config import Settings
from backend.db import make_engine, session_factory
from backend.manage import migrate
from backend.models import Account
from backend.space_bootstrap import ensure_initial_admin
from backend.space_transport import NeonBridge, neon_endpoint
import backend.space_transport as transport


@pytest.fixture
def sessions(tmp_path):
    url = f'sqlite:///{tmp_path / "space.db"}'
    migrate(url)
    engine = make_engine(url)
    yield session_factory(engine)
    engine.dispose()


def test_first_account_is_hashed_once_and_revocation_is_preserved(sessions):
    token='synthetic-first-token-'+'x'*32
    assert ensure_initial_admin(sessions, token)
    with sessions.begin() as db:
        owner=db.scalar(select(Account))
        assert owner.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert owner.role == 'admin'
        owner.active=False
    assert not ensure_initial_admin(sessions, 'different-'+'y'*32)
    with sessions() as db:
        accounts=list(db.scalars(select(Account)))
        assert len(accounts)==1
        assert not accounts[0].active
        assert accounts[0].token_hash == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.parametrize('token', ['', 'short', 'x'*32+' space'])
def test_weak_or_missing_initial_token_does_not_create_account(sessions,token):
    with pytest.raises(ValueError,match='private Space Secret'):
        ensure_initial_admin(sessions,token)
    with sessions() as db:
        assert db.scalar(select(Account)) is None


@pytest.mark.parametrize('url', ['sqlite:///data.db', 'postgresql://user:password@example.com/db',
    'postgresql://user:password@ep-demo.neon.tech.attacker.test/db',
    'postgresql://user:password@ep-demo.neon.tech:80/db'])
def test_connection_rejects_non_neon_destinations(url):
    with pytest.raises(ValueError,match='Neon project'):
        neon_endpoint(url)


def test_neon_bridge_tls_target_and_concurrent_binary_roundtrip(monkeypatch):
    def echo(ws):
        for message in ws:
            ws.send(message)
    with serve(echo,'127.0.0.1',0) as server:
        remote_thread=threading.Thread(target=server.serve_forever,daemon=True)
        remote_thread.start()
        remote_port=server.socket.getsockname()[1]
        connections=[]
        def test_connect(uri,**options):
            assert uri == 'wss://ep-demo.eu-central-1.aws.neon.tech/v2'
            assert options['ssl'].check_hostname
            import ssl
            assert options['ssl'].verify_mode == ssl.CERT_REQUIRED
            connections.append(uri)
            return real_connect(f'ws://127.0.0.1:{remote_port}',compression=None)
        monkeypatch.setattr(transport,'connect',test_connect)
        with NeonBridge('postgresql://test:password@ep-demo.eu-central-1.aws.neon.tech/db?sslmode=require&channel_binding=require') as bridge:
            from sqlalchemy.engine import make_url
            url=make_url(bridge.database_url)
            assert url.host=='127.0.0.1'
            assert url.drivername=='postgresql+psycopg'
            assert url.query['sslmode']=='disable'
            assert url.query['channel_binding']=='disable'
            assert bridge.server.server_address[0]=='127.0.0.1'
            def roundtrip(payload):
                with socket.create_connection(('127.0.0.1',url.port),timeout=5) as sock:
                    sock.sendall(payload)
                    result=b''
                    while len(result)<len(payload):
                        data=sock.recv(65536)
                        assert data
                        result+=data
                    assert result==payload
            errors=[]
            def run(payload):
                try: roundtrip(payload)
                except Exception as error: errors.append(error)
            threads=[threading.Thread(target=run,args=(bytes(range(256))*n,)) for n in [100,1700]]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=10)
            assert not any(thread.is_alive() for thread in threads)
            assert not errors
            assert len(connections)==2
        server.shutdown()
        remote_thread.join(timeout=5)


def test_transport_failure_closes_client_without_logging_secret(monkeypatch,caplog):
    def fail(*args,**kwargs):
        raise RuntimeError('PRIVATE-CREDENTIAL-SHOULD-NOT-APPEAR')
    monkeypatch.setattr(transport,'connect',fail)
    with NeonBridge('postgresql://test:secret@ep-demo.neon.tech/db') as bridge:
        with socket.create_connection(('127.0.0.1',bridge.server.server_address[1]),timeout=5) as sock:
            assert sock.recv(1)==b''
    assert 'PRIVATE-CREDENTIAL' not in caplog.text
    assert 'could not connect' in caplog.text
