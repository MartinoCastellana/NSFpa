from fastapi.testclient import TestClient

from app.main import app


def test_provider_settings_are_encrypted_and_masked():
    headers = {"X-Roles": "admin", "X-Tenant-ID": "00000000-0000-0000-0000-000000000003"}
    with TestClient(app) as client:
        saved = client.put(
            "/api/v1/settings/provider",
            json={
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "mode": "mock",
                "api_key": "sk-test-never-return-this",
            },
            headers=headers,
        )
        assert saved.status_code == 200
        assert "sk-test" not in saved.text
        assert saved.json()["api_key_masked"].endswith("this")
        loaded = client.get("/api/v1/settings/provider", headers=headers)
        assert loaded.status_code == 200
        assert "sk-test-never-return-this" not in loaded.text
