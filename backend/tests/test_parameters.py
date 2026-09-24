from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_domain import tiny

from app import application
from app.application import Service
from app.domain import calculate
from app.domain_parameters import effective_parameters
from app.main import app
from app.schemas import Overrides, Revision


def test_preview_uses_multiplication_and_matches_independent_forecast() -> None:
    revision = Revision(
        id="r",
        project_id="p",
        version=1,
        known_on="2026-08-31",
        created_at="2026-08-31",
        note="模拟",
        data=tiny(),
    )
    override = Overrides(price_change="0.1", remaining_cost_change="0.1")
    preview = effective_parameters(revision, "样例", date(2026, 8, 31), "optimistic", override)
    assert preview.price_percent == "15.50"
    assert preview.cost_percent == "6.70"
    assert preview.phases[0].effective_price == "1155.00"
    assert preview.future_cost_before == "7000.00"
    assert preview.future_cost_after == "7469.00"
    result = calculate(tiny(), date(2026, 8, 31), date(2026, 8, 31), "optimistic", override)
    assert result.summary.twelve_month_profit == "4081.00"
    revision.data.costs = []
    missing = effective_parameters(revision, "样例", date(2026, 8, 31), "base", Overrides())
    assert missing.future_cost_before is None and missing.future_cost_after is None
    assert missing.warnings


def test_preview_is_read_only_and_selects_cutoff_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(application, "service", Service(tmp_path))
    with TestClient(app) as client:
        check_preview(client)


def check_preview(client: TestClient) -> None:
    project = client.get("/api/v1/projects").json()[0]
    path = f"/api/v1/projects/{project['id']}"
    original = client.get(f"{path}/input").json()
    revised = client.post(
        f"{path}/revisions",
        headers={"Idempotency-Key": "preview-new-revision"},
        json={
            "base_version": original["version"],
            "known_on": "2026-09-01",
            "data": original["data"],
        },
    )
    assert revised.status_code == 200
    response = client.post("/api/v1/parameters/preview", json={"project_ids": [project["id"]]})
    assert response.status_code == 200
    assert response.json()[0]["revision_id"] == original["id"]
    assert client.get("/api/v1/runs").json() == []
