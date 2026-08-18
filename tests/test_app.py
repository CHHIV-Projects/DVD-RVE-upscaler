from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_imports():
    assert app is not None


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_landing_page_returns_http_success():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_landing_page_contains_application_identity():
    response = client.get("/")
    assert response.status_code == 200
    assert "DVD RVE Upscaler" in response.text
