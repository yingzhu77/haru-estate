"""Credentials are synthetic sentinels. No live network calls."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import application
from app.agent_model import DeepSeekModel
from app.application import Service
from app.main import app
from app.schemas import AgentPlan, ModelConfiguration

SENTINEL = "configuration-test-secret-do-not-persist"
HEADERS = {"X-Haru-Config": "1", "Origin": "http://127.0.0.1:18080"}


def test_configuration_test_clear_restart_and_secret_not_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    service = Service(tmp_path)
    monkeypatch.setattr(application, "service", service)
    calls = []

    def plan(self: DeepSeekModel, *args: object) -> AgentPlan:
        calls.append(args)
        return AgentPlan(action="query", metric="profit", period="twelve_month")

    monkeypatch.setattr(DeepSeekModel, "plan", plan)
    with TestClient(app, base_url="http://127.0.0.1:18000") as client:
        status = client.get("/api/v1/model-config", headers=HEADERS)
        assert status.headers["cache-control"] == "no-store"
        headers = HEADERS | {"X-Haru-CSRF": status.json()["csrf_token"]}
        response = client.put(
            "/api/v1/model-config",
            headers=headers,
            json={"api_key": SENTINEL, "model": "test-model"},
        )
        assert response.status_code == 200 and response.json()["configured"]
        assert response.json()["source"] == "memory"
        assert SENTINEL not in response.text
        assert len(calls) == 1 and SENTINEL not in str(calls)
        assert client.get("/api/v1/agent/status").json()["configured"]

        def failure(self: DeepSeekModel, *args: object) -> AgentPlan:
            raise RuntimeError(SENTINEL)

        monkeypatch.setattr(DeepSeekModel, "plan", failure)
        failed = client.put(
            "/api/v1/model-config",
            headers=headers,
            json={"api_key": SENTINEL, "model": "replacement"},
        )
        assert failed.status_code == 502 and SENTINEL not in failed.text
        assert service.agent.model.model == "test-model"
        invalid = client.put(
            "/api/v1/model-config", headers=headers, json={"api_key": SENTINEL, "model": SENTINEL}
        )
        assert invalid.status_code == 422 and SENTINEL not in invalid.text
        malformed = client.put(
            "/api/v1/model-config",
            headers=headers | {"Content-Type": "application/json"},
            content='{"api_key":"' + SENTINEL,
        )
        assert malformed.status_code == 422 and SENTINEL not in malformed.text
        cleared = client.request("DELETE", "/api/v1/model-config", headers=headers, json={})
        assert cleared.status_code == 200 and not cleared.json()["configured"]
        monkeypatch.setattr(DeepSeekModel, "plan", plan)
        client.put(
            "/api/v1/model-config",
            headers=headers,
            json={"api_key": SENTINEL, "model": "test-model"},
        )
    assert SENTINEL not in caplog.text
    for path in tmp_path.glob("*.sqlite3*"):
        assert SENTINEL.encode() not in path.read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:18000") as client:
        assert not client.get("/api/v1/agent/status").json()["configured"]


def test_configuration_blocks_cross_site_and_missing_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(application, "service", Service(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1:18000") as client:
        assert client.get("/api/v1/model-config").status_code == 403
        for headers in [
            HEADERS | {"Origin": "https://evil.example"},
            HEADERS | {"Host": "evil.example"},
            HEADERS | {"Sec-Fetch-Site": "cross-site"},
        ]:
            assert client.get("/api/v1/model-config", headers=headers).status_code == 403
        assert (
            client.put(
                "/api/v1/model-config",
                headers=HEADERS,
                json={"api_key": SENTINEL, "model": "test-model"},
            ).status_code
            == 403
        )


def test_model_configuration_does_not_race_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException
    from test_agent import completed_run

    from app.schemas import AgentCreate

    service = Service(tmp_path)
    service.start(worker=False)
    run = completed_run(service)
    entered, release = threading.Event(), threading.Event()

    def slow(self: DeepSeekModel, *args: object) -> AgentPlan:
        entered.set()
        assert release.wait(5)
        return AgentPlan(action="query", metric="profit", period="twelve_month")

    monkeypatch.setattr(DeepSeekModel, "plan", slow)
    body = ModelConfiguration(api_key=SENTINEL, model="test-model")
    thread = threading.Thread(target=lambda: service.agent.configure(body))
    thread.start()
    assert entered.wait(5)
    try:
        with pytest.raises(HTTPException) as exc:
            service.agent.create(AgentCreate(run_id=run.id, question="利润"), "config-race")
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException):
            service.agent.configure(None)
    finally:
        release.set()
        thread.join()
    service.agent.create(AgentCreate(run_id=run.id, question="利润"), "queued-race")
    with pytest.raises(HTTPException) as exc:
        service.agent.configure(None)
    assert exc.value.status_code == 409
    service.stop()


def test_clearing_configuration_preserves_pending_reply(tmp_path: Path) -> None:
    from fastapi import HTTPException
    from test_agent import CLARIFY, DeterministicModel, completed_run

    from app.schemas import AgentCreate, AgentReply

    service = Service(tmp_path, agent_model=DeterministicModel([CLARIFY]))
    service.start(worker=False)
    run = completed_run(service)
    task = service.agent.create(AgentCreate(run_id=run.id, question="利润"), "pending-config")
    service.agent.process_next()
    waiting = service.agent.get(task.id)
    assert waiting.reply_token
    service.agent.configure(None)
    with pytest.raises(HTTPException) as exc:
        service.agent.reply(
            task.id, AgentReply(token=waiting.reply_token, reply="未来12个月"), "pending-reply"
        )
    assert exc.value.status_code == 503
    assert service.agent.get(task.id) == waiting
    service.stop()


@pytest.mark.parametrize(
    "key,model",
    [("   ", "test-model"), (" secret-value ", "secret-value"), ("secret", "SK-credential")],
)
def test_rejects_blank_and_disguised_credentials(key: str, model: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModelConfiguration(api_key=key, model=model)
