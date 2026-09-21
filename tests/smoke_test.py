import io
import os
import sys

from fastapi.testclient import TestClient
from PIL import Image

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.main import app

client = TestClient(app)


def test_smoke_prediction_endpoint():
    img = Image.new('RGB', (300, 300), color=(20, 180, 20))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)

    files = {'file': ('leaf.jpg', buf, 'image/jpeg')}
    response = client.post('/predict', files=files, data={'crop': 'Tomato'})

    assert response.status_code == 200
    body = response.json()
    assert body['crop'] == 'Tomato'
    assert 'prediction' in body
    assert 'advisory' in body
    assert body['prediction']['disease'] in [
        'Healthy', 'Early Blight', 'Late Blight', 'Leaf Spot', 'Bacterial Wilt'
    ]


def test_api_alias_routes_work():
    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.json()['status'] == 'ok'

    img = Image.new('RGB', (300, 300), color=(20, 180, 20))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)

    files = {'file': ('leaf.jpg', buf, 'image/jpeg')}
    response = client.post('/api/predict', files=files, data={'crop': 'Tomato'})
    assert response.status_code == 200
    assert response.json()['crop'] == 'Tomato'


def test_paddy_and_rice_are_accepted():
    img = Image.new('RGB', (300, 300), color=(20, 180, 20))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)

    files = {'file': ('leaf.jpg', buf, 'image/jpeg')}
    for crop_name in ['Paddy', 'Rice']:
        response = client.post('/predict', files=files, data={'crop': crop_name})
        assert response.status_code == 200, response.text
        assert response.json()['crop'] in ['Paddy', 'Rice']
