import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import application
from app.application import Service
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(application, "service", Service(tmp_path))
    with TestClient(app) as api:
        yield api


def test_real_api_project_run_evidence_and_portfolio(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["ai"] == "not_connected"
    created = client.post("/api/v1/projects", json={"name": "第三模拟住宅", "template": "demo"})
    assert created.status_code == 200
    project = created.json()
    body = {"project_ids": [project["id"]]}
    headers = {"Idempotency-Key": "api-run-key"}
    submitted = client.post("/api/v1/runs", json=body, headers=headers)
    assert submitted.status_code == 202
    run_id = submitted.json()["id"]
    assert client.post("/api/v1/runs", json=body, headers=headers).json()["id"] == run_id
    for _ in range(100):
        run = client.get(f"/api/v1/runs/{run_id}").json()
        if run["status"] == "completed":
            break
        time.sleep(0.02)
    assert run["status"] == "completed"
    assert isinstance(run["result"]["summary"]["next_month_profit"], str)
    sources = client.get(f"/api/v1/runs/{run_id}/evidence?metric=twelve_month_profit").json()
    assert sources["sources"]
    assert all("2026-09" <= s["month"] <= "2027-08" for s in sources["sources"])
    wrong = client.get("/api/v1/projects").json()[0]
    rejected = client.get(
        f"/api/v1/projects/{wrong['id']}/input", params={"revision_id": run["revision_ids"][0]}
    )
    assert rejected.status_code == 404 and rejected.json()["request_id"]
    assert (
        client.get("/api/v1/compare", params={"left_id": run_id, "right_id": run_id}).json()[
            "profit_deltas"
        ]
        == ["0.00"] * 12
    )


def test_validation_errors_have_contract_and_do_not_create_runs(client: TestClient) -> None:
    invalid = client.post("/api/v1/projects", json={"name": "  "})
    assert invalid.status_code == 422 and invalid.json()["code"] == "VALIDATION_ERROR"
    project = client.get("/api/v1/projects").json()[0]
    invalid = client.post(
        "/api/v1/runs",
        headers={"Idempotency-Key": "invalid-run"},
        json={
            "project_ids": [project["id"]],
            "forecast_origin": "2026-08-31",
            "information_cutoff": "2026-09-01",
        },
    )
    assert invalid.status_code == 422
    assert client.get("/api/v1/runs").json() == []
