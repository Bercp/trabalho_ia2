from fastapi.testclient import TestClient

from penal.web import app


def test_status_does_not_leak_key():
    with TestClient(app) as client:
        result = client.get("/api/status")
        assert result.status_code == 200
        assert "api_key" not in result.text.lower()


def test_rejects_cross_origin_mutation():
    with TestClient(app) as client:
        result = client.post("/api/chat", json={"message": "crime"}, headers={"Origin": "https://untrusted.example"})
        assert result.status_code == 403


def test_rejects_excessive_question():
    with TestClient(app) as client:
        result = client.post("/api/chat", json={"message": "crime" * 500})
        assert result.status_code == 422


def test_arbitrary_document_path_is_not_served():
    with TestClient(app) as client:
        result = client.get("/documents/.env/pdf")
        assert result.status_code == 404
