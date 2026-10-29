from fastapi.testclient import TestClient

from app.main import app


def test_upload_to_safe_outbound_flow_and_tenant_isolation():
    headers = {"X-Roles": "admin,reviewer", "X-Tenant-ID": "00000000-0000-0000-0000-000000000001"}
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/requests", json={"policy": {"manual_approval": True}}, headers=headers
        )
        assert created.status_code == 201
        request_id = created.json()["id"]
        forbidden = client.get(
            f"/api/v1/requests/{request_id}",
            headers={"X-Tenant-ID": "00000000-0000-0000-0000-000000000002"},
        )
        assert forbidden.status_code == 404

        upload = client.post(
            f"/api/v1/requests/{request_id}/documents",
            files={
                "file": (
                    "fixture.txt",
                    b"Il richiedente Marta Verdi, email marta@example.test.",
                    "text/plain",
                )
            },
            headers=headers,
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]
        assert (
            client.post(f"/api/v1/documents/{document_id}/extract", headers=headers).status_code
            == 202
        )
        assert (
            client.post(f"/api/v1/requests/{request_id}/detect", headers=headers).status_code == 202
        )
        assert (
            client.post(
                f"/api/v1/requests/{request_id}/review/approve",
                json={"confirm_all": True},
                headers=headers,
            ).status_code
            == 200
        )
        safe = client.post(f"/api/v1/requests/{request_id}/pseudonymize", headers=headers)
        assert safe.status_code == 200
        assert "Marta Verdi" not in safe.json()["text"]
        assert "marta@example.test" not in safe.json()["text"]
        assert (
            client.post(f"/api/v1/requests/{request_id}/validate", headers=headers).json()["status"]
            == "PASSED"
        )
        sent = client.post(f"/api/v1/requests/{request_id}/send", headers=headers)
        assert sent.status_code == 200
        assert "Marta Verdi" not in sent.text
        calls = client.get("/api/v1/api-calls", headers=headers)
        assert calls.status_code == 200
        assert any(call["request_id"] == request_id for call in calls.json())
        assert all("Marta Verdi" not in str(call) for call in calls.json())
