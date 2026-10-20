from fastapi.testclient import TestClient
from support_agent.mock_api import app


def test_old_module_name_uses_authenticated_application():
    with TestClient(app) as client:
        assert client.get("/").json()["version"] == "0.2.0"
        assert client.get("/agent/runs").status_code == 401
