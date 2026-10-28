import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(provider="mock", mock_latency_ms=0, db_path=str(tmp_path / "test.db"),
                    policy_path="policies/default.yaml", gateway_api_keys="")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def chat(client, text, **headers):
    return client.post("/v1/chat/completions", headers=headers,
                       json={"model": "test", "messages": [{"role": "user", "content": text}]})
