import pytest
from fastapi.testclient import TestClient

from lima_cloud import acquire, server
from lima_cloud.crc import build_payload

# Cuadrante fuera de la grilla real (6x6, filas/columnas 0-5) -- garantiza
# que nunca colisione con un archivo real en cache/, sin importar el tamano
# de grilla que se use en produccion.
FAKE_QUAD = "9_9"


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    """El lifespan de FastAPI (_load_cache_from_disk) lee de acquire.CACHE_DIR
    al arrancar el TestClient. Sin esto, un cache/ real en el repo (de una
    corrida real de adquisicion) sobreescribe silenciosamente lo que el test
    acaba de inyectar via server.set_cache() -- ya paso una vez con el
    cuadrante "3_2", que dejo de ser un id de prueba seguro en cuanto
    empezamos a correr adquisiciones reales contra esa grilla."""
    monkeypatch.setattr(acquire, "CACHE_DIR", tmp_path)
    server._cache.clear()
    yield
    server._cache.clear()


def test_get_cache_returns_404_for_unknown_quadrant():
    with TestClient(server.app) as client:
        r = client.get(f"/cache/{FAKE_QUAD}")
        assert r.status_code == 404


def test_get_cache_returns_exact_signed_payload_bytes():
    payload, _info = build_payload({"ndvi": 0.17, "lvl": "VERDE"}, "2026-06-30")
    server.set_cache({FAKE_QUAD: {"payload": payload}})

    with TestClient(server.app) as client:
        r = client.get(f"/cache/{FAKE_QUAD}")
        assert r.status_code == 200
        # bytes exactos, no un dict re-serializado por FastAPI/Starlette
        assert r.text == payload


def test_post_result_accepts_the_firmware_body_shape():
    with TestClient(server.app) as client:
        r = client.post(f"/result/{FAKE_QUAD}", json={
            "quad": FAKE_QUAD, "votes": 37, "level": "ROJO", "rssi": -78, "battery_v": None,
        })
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_health_reports_expected_quadrant_count():
    with TestClient(server.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["expected"] > 0
