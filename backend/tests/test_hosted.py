import hashlib
import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.config import Settings
from backend.manage import migrate
from backend.models import Account
from backend.run_hosted import validate_hosted
from backend.services.inference import Inference


def test_hosted_rejects_demo_and_missing_model(tmp_path):
    settings = Settings(database_url='sqlite://', mode='demo')
    with pytest.raises(ValueError, match='production'):
        validate_hosted(settings)
    with pytest.raises(ValueError, match='checkpoint'):
        validate_hosted(replace(settings, mode='production'))


def test_required_model_fails_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(Inference, 'load', lambda self: None)
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "fail.db"}', require_model=True))
    with pytest.raises(RuntimeError, match='not loaded'):
        with TestClient(app):
            pass


def test_readiness_checks_database(tmp_path):
    url = f'sqlite:///{tmp_path / "ready.db"}'
    with TestClient(create_app(Settings(database_url=url))) as client:
        assert client.get('/ready').status_code == 503
        migrate(url)
        assert client.get('/ready').json() == {'ready': True}


def test_production_camera_auth_and_independent_frames(tmp_path):
    url = f'sqlite:///{tmp_path / "auth.db"}'
    migrate(url)
    app = create_app(Settings(database_url=url, mode='production'))
    with app.state.sessions.begin() as db:
        for name, role in [('first', 'admin'), ('second', 'admin'), ('parent', 'guardian')]:
            db.add(Account(display_name=name, role=role,
                           token_hash=hashlib.sha256(name.encode()).hexdigest()))
    calls = []
    def predict(data, frame_id, captured_at):
        calls.append(frame_id)
        return {'frame_id': frame_id, 'visible_person_count': len(calls), 'frame_status': 'valid'}
    app.state.inference.predict = predict
    image = io.BytesIO()
    Image.new('RGB', (32, 32), 'white').save(image, format='JPEG')
    frame = image.getvalue()
    with TestClient(app) as client:
        assert client.get('/api/v1/trips').status_code == 401
        for token, expected in [('', 401), ('wrong', 401), ('parent', 403)]:
            response = client.post('/predict', files={'file': ('frame.jpg', frame, 'image/jpeg')},
                                   headers={'Authorization': f'Bearer {token}'})
            assert response.status_code == expected
        assert calls == []
        for token, frame_id in [('first', 'device-a'), ('second', 'device-b')]:
            response = client.post('/predict', files={'file': ('frame.jpg', frame, 'image/jpeg')},
                                   data={'frame_id': frame_id}, headers={'Authorization': f'Bearer {token}'})
            assert response.status_code == 200
            assert response.json()['frame_id'] == frame_id
        assert calls == ['device-a', 'device-b']
