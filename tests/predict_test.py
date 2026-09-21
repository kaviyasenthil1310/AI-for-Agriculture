import os
import sys

from PIL import Image

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.predict import USE_HEURISTIC, predict_disease


def make_color_image(rgb):
    return Image.new('RGB', (224, 224), color=rgb)


def test_predict_disease_with_color_images():
    assert USE_HEURISTIC is True

    cases = [
        ('green', (20, 180, 20)),
        ('red', (200, 30, 30)),
        ('blue', (30, 30, 200)),
        ('brown', (150, 100, 60)),
    ]

    for name, color in cases:
        img = make_color_image(color)
        pred = predict_disease(img)
        assert 'disease' in pred
        assert 'confidence' in pred
        assert 'all_probs' in pred
        assert 0.0 <= pred['confidence'] <= 1.0
        assert isinstance(pred['disease'], str)
        assert isinstance(pred['all_probs'], dict)


def test_run_server_uses_supported_uvicorn_options(monkeypatch):
    captured = {}

    def fake_run(app, **kwargs):
        captured['app'] = app
        captured['kwargs'] = kwargs

    import uvicorn
    monkeypatch.setattr(uvicorn, 'run', fake_run)

    from backend.main import run_server

    run_server()

    assert captured['app'] is not None
    assert 'timeout_notify' not in captured['kwargs']
    assert captured['kwargs']['timeout_graceful_shutdown'] == 30
    assert captured['kwargs']['workers'] == 1
