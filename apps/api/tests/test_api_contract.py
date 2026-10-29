from app.main import app


def test_openapi_exposes_versioned_api():
    paths = app.openapi()["paths"]
    assert "/api/v1/requests" in paths
    assert "/api/v1/requests/{request_id}/send" in paths
    assert "/api/v1/api-calls/{api_call_id}/restore" in paths
