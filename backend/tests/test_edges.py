from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from test_domain import ORIGIN, tiny

from app.application import Service
from app.backup import backup
from app.domain import D, aggregate, calculate
from app.schemas import Actual, Overrides, Payment, ProjectPatch, RunCreate


def test_zero_cost_is_explicitly_supported() -> None:
    data = tiny()
    data.costs[2].amount = "0"
    data.costs[2].payments = [Payment(month="2026-09", amount="0")]
    assert calculate(data, ORIGIN, ORIGIN).summary.twelve_month_profit == "4000.00"


def test_missing_closed_month_is_not_silently_zero() -> None:
    data = tiny()
    data.assumptions.opening_month = "2026-08"
    with pytest.raises(ValueError, match="缺少已结账月份"):
        calculate(data, ORIGIN, ORIGIN)


def test_prepaid_cost_is_not_adjusted_retroactively() -> None:
    data = tiny()
    data.assumptions.opening_month = "2026-08"
    data.actuals = [
        Actual(
            id="prepaid",
            phase_id="p",
            month="2026-08",
            known_on=ORIGIN,
            metric="payments",
            amount="1000",
        )
    ]
    data.costs[1].payments = [
        Payment(month="2026-08", amount="1000"),
        Payment(month="2026-09", amount="3000"),
    ]
    result = calculate(data, ORIGIN, ORIGIN, overrides=Overrides(remaining_cost_change="0.1"))
    assert result.months[0].payments == "1000.00"
    assert result.months[1].payments == "6700.00"
    assert sum(D(m.payments) for m in result.months) == 7700


def test_shorter_project_cash_and_gap_carry_to_portfolio_tail() -> None:
    first = tiny()
    first.assumptions.opening_cash = "-5000"
    short = calculate(first, ORIGIN, ORIGIN)
    long = calculate(tiny(), ORIGIN, ORIGIN, overrides=Overrides(delivery_delays={"p": 24}))
    total = aggregate([short, long])
    assert total.months[-1].cash_balance == "1000.00"
    assert total.months[-1].uncovered_gap == "2000.00"


def test_metadata_conflicts_and_backup_restore(tmp_path: Path) -> None:
    app = Service(tmp_path / "original")
    app.start(worker=False)
    project = app.projects()[0]
    old = app.revision(project.id)
    updated = app.patch_project(project.id, ProjectPatch(name="重命名模拟项目", base_version=1))
    assert updated.version == 2
    assert app.revision(project.id).data == old.data
    with pytest.raises(HTTPException) as error:
        app.patch_project(project.id, ProjectPatch(name="失效修改", base_version=1))
    assert error.value.status_code == 409
    run = app.create_run(RunCreate(project_ids=[project.id]), "backup-test")
    app.process_next()
    saved = app.run(run.id)
    destination = tmp_path / "restored" / "haru.sqlite3"
    backup(app.directory / "haru.sqlite3", destination)
    restored = Service(destination.parent, seed=False)
    restored.start(worker=False)
    assert restored.projects() == app.projects()
    assert restored.run(run.id) == saved
    with pytest.raises(ValueError, match="already exists"):
        backup(app.directory / "haru.sqlite3", destination)
    evidence = restored.evidence(run.id, "cash_balance", "2026-09")
    assert any(r.metric == "opening_cash" for r in evidence.sources)
    assert all(r.month <= "2026-09" for r in evidence.sources)


def test_late_actuals_make_history_incomplete() -> None:
    data = tiny()
    data.assumptions.opening_month = "2026-08"
    data.actuals = [
        Actual(
            id="late",
            phase_id="p",
            month="2026-08",
            known_on=date(2026, 9, 1),
            metric="expenses",
            amount="1",
        )
    ]
    with pytest.raises(ValueError, match="缺少已结账"):
        calculate(data, ORIGIN, ORIGIN)


def test_missing_historical_cost_payment_is_rejected() -> None:
    from app.seeds import demo_dataset

    data = demo_dataset()
    data.actuals = [r for r in data.actuals if r.metric != "payments"]
    with pytest.raises(ValueError, match="不勾稽"):
        calculate(data, ORIGIN, ORIGIN)


def test_cumulative_profit_reconciles_with_summary() -> None:
    result = calculate(tiny(), ORIGIN, ORIGIN)
    last = next(r for r in result.months if r.month == result.target_months[-1])
    assert last.cumulative_profit == result.summary.twelve_month_profit


def test_corrected_run_links_prior_without_modifying_it(tmp_path: Path) -> None:
    service = Service(tmp_path)
    service.start(worker=False)
    first, second = service.projects()
    prior = service.create_run(RunCreate(project_ids=[first.id]), "prior")
    service.process_next()
    completed = service.run(prior.id)
    linked = service.create_run(
        RunCreate(project_ids=[first.id], supersedes_run_id=prior.id), "linked"
    )
    assert linked.supersedes_run_id == prior.id
    assert service.run(prior.id) == completed
    with pytest.raises(HTTPException):
        service.create_run(
            RunCreate(project_ids=[second.id], supersedes_run_id=prior.id), "wrong-link"
        )
