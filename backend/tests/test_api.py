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
    created = client.post(
        "/api/v1/projects",
        json={"name": "第三模拟住宅", "template": "demo"},
        headers={"Idempotency-Key": "create-api-project"},
    )
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
    path = f"/api/v1/runs/{run_id}/evidence"
    full = client.get(path).json()["sources"]
    long_period = client.get(path, params={"month_from": "2026-01", "month_to": "2075-12"})
    assert long_period.status_code == 200
    assert long_period.json()["sources"] == full
    period = client.get(path, params={"month_from": "2026-10", "month_to": "2026-12"})
    expected = [row for row in full if "2026-10" <= row["month"] <= "2026-12"]
    assert expected and len(expected) < len(full)
    assert period.json()["sources"] == expected
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


@pytest.mark.parametrize(
    "params",
    [
        {"month_from": "2026-01"},
        {"month_to": "2026-12"},
        {"month_from": "2026-12", "month_to": "2026-01"},
        {"month_from": "2026-01", "month_to": "2076-01"},
        {"month_from": "2026-13", "month_to": "2027-01"},
        {"month_from": "2026-01", "month_to": "2026-12", "month": "2026-01"},
        {"month_from": "2026-01", "month_to": "2026-12", "months": "2026-01"},
    ],
)
def test_evidence_rejects_invalid_or_ambiguous_ranges(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/api/v1/runs/missing/evidence", params=params)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_validation_errors_have_contract_and_do_not_create_runs(client: TestClient) -> None:
    invalid = client.post(
        "/api/v1/projects", json={"name": "  "}, headers={"Idempotency-Key": "invalid-api-project"}
    )
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


def test_input_mutation_retry_and_structured_import_rejection(client: TestClient) -> None:
    headers = {"Idempotency-Key": "http-project-retry"}
    body = {"name": "HTTP重试模拟", "template": "demo"}
    first = client.post("/api/v1/projects", json=body, headers=headers)
    assert first.headers["X-Request-ID"]
    assert client.post("/api/v1/projects", json=body, headers=headers).json() == first.json()
    project = first.json()
    revision = client.get(f"/api/v1/projects/{project['id']}/input").json()
    invalid = {
        "base_version": 1,
        "known_on": "2026-08-31",
        "records": [
            {
                "id": "invalid-http",
                "phase_id": revision["data"]["phases"][0]["id"],
                "month": "2026-08",
                "known_on": "2026-08-31",
                "metric": "collections",
                "amount": "1",
                "contract_id": "nonexistent",
            }
        ],
    }
    rejected = client.post(
        f"/api/v1/projects/{project['id']}/imports/confirm",
        json=invalid,
        headers={"Idempotency-Key": "invalid-csv-import"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "VALIDATION_ERROR"
    assert rejected.json()["request_id"] == rejected.headers["X-Request-ID"]
    assert client.get(f"/api/v1/projects/{project['id']}/input").json() == revision
    page = client.get(f"/api/v1/projects/{project['id']}/revisions").json()
    assert page["total"] == 1 and "data" not in page["items"][0]
    assert client.get("/api/v1/runs/page?limit=0").status_code == 422


def test_unexpected_error_has_request_id_without_internal_details(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(application.service, "health", fail)
    result = client.get("/api/v1/health")
    assert result.status_code == 500
    assert result.json()["code"] == "INTERNAL_ERROR"
    assert result.json()["request_id"] == result.headers["X-Request-ID"]
    assert "private internal detail" not in result.text


def test_missing_route_and_missing_mutation_key_follow_error_contract(client: TestClient) -> None:
    missing = client.get("/api/v1/no-such-route")
    assert missing.status_code == 404
    assert missing.json()["request_id"] == missing.headers["X-Request-ID"]
    rejected = client.post("/api/v1/projects", json={"name": "缺少请求键"})
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "VALIDATION_ERROR"
    assert len(client.get("/api/v1/projects").json()) == 2
