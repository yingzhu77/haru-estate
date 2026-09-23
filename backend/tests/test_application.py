from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import Service
from app.domain import D
from app.schemas import ProjectCreate, RevisionWrite, RunCreate
from app.storage import RunRow


@pytest.fixture
def service(tmp_path: Path) -> Service:
    app = Service(tmp_path)
    app.start(worker=False)
    return app


def drain(service: Service) -> None:
    for _ in range(20):
        if not service.process_next():
            return
    raise AssertionError("任务未收敛")


def test_portfolio_fixed_members_and_sources(service: Service) -> None:
    projects = service.projects()
    run = service.create_run(
        RunCreate(kind="portfolio", project_ids=[p.id for p in projects]), "portfolio-1"
    )
    drain(service)
    finished = service.run(run.id)
    assert finished.status == "completed"
    assert len(finished.members) == 2
    assert finished.result is not None
    assert sum(D(m.profit or "0") for m in finished.members) == D(
        finished.result.summary.twelve_month_profit
    )
    service.create_project(ProjectCreate(name="第三项目", template="demo"))
    assert service.run(run.id) == finished
    evidence = service.evidence(finished.members[0].run_id, "profit", "2026-09")
    assert evidence.sources and evidence.revision_ids


def test_duplicate_request_idempotent_and_mismatch_rejected(service: Service) -> None:
    p = service.projects()[0]
    body = RunCreate(project_ids=[p.id])
    first = service.create_run(body, "idem-key")
    assert service.create_run(body, "idem-key").id == first.id
    with pytest.raises(HTTPException) as exc:
        service.create_run(body.model_copy(update={"scenario": "prudent"}), "idem-key")
    assert exc.value.status_code == 409


def test_revision_and_forecast_origin_isolation(service: Service) -> None:
    p = service.projects()[0]
    old = service.revision(p.id)
    run = service.create_run(RunCreate(project_ids=[p.id]), "old-run")
    drain(service)
    result = service.run(run.id)
    modified = old.data.model_copy(deep=True)
    modified.phases[0].price = "50000"
    new = service.revise(
        p.id, RevisionWrite(base_version=old.version, known_on=date(2026, 9, 22), data=modified)
    )
    past = service.create_run(RunCreate(project_ids=[p.id]), "repeat-past")
    assert past.revision_ids == [old.id]
    assert service.run(run.id) == result
    assert service.revision(p.id).id == new.id
    with pytest.raises(HTTPException):
        service.revise(
            p.id, RevisionWrite(base_version=old.version, known_on=date(2026, 9, 22), data=modified)
        )


def test_project_isolation_and_wrong_revision(service: Service) -> None:
    first, second = service.projects()
    revision = service.revision(first.id)
    with pytest.raises(HTTPException):
        service.revision(second.id, revision.id)


def test_incomplete_member_never_becomes_zero_total(service: Service) -> None:
    empty = service.create_project(ProjectCreate(name="空白项目"))
    good = service.projects()[0]
    run = service.create_run(
        RunCreate(kind="portfolio", project_ids=[good.id, empty.id]), "incomplete"
    )
    drain(service)
    result = service.run(run.id)
    assert result.status == "incomplete"
    assert result.result is None
    assert {m.status for m in result.members} == {"completed", "failed"}


def test_restart_resume_uses_snapshot(service: Service) -> None:
    p = service.projects()[0]
    run = service.create_run(RunCreate(project_ids=[p.id]), "restart")
    with Session(service.engine) as db, db.begin():
        row = db.scalar(select(RunRow).where(RunRow.id == run.id))
        assert row is not None
        row.status = "running"
    restarted = Service(service.directory)
    restarted.start(worker=False)
    assert restarted.run(run.id).status == "interrupted"
    assert restarted.resume(run.id).attempt == 2
    restarted.resume(run.id)
    drain(restarted)
    result = restarted.run(run.id)
    assert result.status == "completed" and result.attempt == 2
    assert result.revision_ids == run.revision_ids


def test_csv_preview_amount_text_and_duplicates(service: Service) -> None:
    p = service.projects()[0]
    raw = (
        b"id,phase_id,month,known_on,metric,amount\n"
        b"new,phase-1,2026-08,2026-08-31,expenses,123.45\n"
    )
    preview = service.preview_import(p.id, raw)
    assert not preview.errors and preview.additions[0].amount == "123.45"
    from app.schemas import ImportConfirm

    confirmed = service.confirm_import(
        p.id,
        ImportConfirm(
            base_version=preview.base_version, known_on=date(2026, 8, 31), records=preview.additions
        ),
    )
    repeated = service.preview_import(p.id, raw)
    assert repeated.duplicates == ["new"] and not repeated.additions
    same = service.confirm_import(
        p.id,
        ImportConfirm(
            base_version=confirmed.version, known_on=date(2026, 8, 31), records=preview.additions
        ),
    )
    assert same.id == confirmed.id
