from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException

from alembic import command
from app import schemas as s
from app.application import Service
from app.revision_diff import dataset_changes


@pytest.fixture
def service(tmp_path: Path) -> Service:
    result = Service(tmp_path, seed=False)
    result.start(worker=False)
    return result


def test_project_and_revision_retry_survive_restart(service: Service) -> None:
    body = s.ProjectCreate(name="重试模拟住宅", template="demo")
    project = service.create_project(body, key="create-project-key")
    assert service.create_project(body, key="create-project-key") == project
    data = service.revision(project.id).data
    write = s.RevisionWrite(base_version=1, known_on=date(2026, 9, 1), data=data)
    revision = service.revise(project.id, write, key="revision-key")
    reopened = Service(service.directory, seed=False)
    reopened.start(worker=False)
    assert reopened.revise(project.id, write, key="revision-key") == revision
    assert reopened.create_project(body, key="create-project-key") == project
    assert len(reopened.projects()) == 1
    with pytest.raises(HTTPException) as conflict:
        reopened.create_project(s.ProjectCreate(name="另一项目"), key="create-project-key")
    assert conflict.value.status_code == 409


def test_import_preview_and_confirm_reject_foreign_contract_atomically(service: Service) -> None:
    project = service.create_project(s.ProjectCreate(name="导入模拟住宅", template="demo"))
    before = service.revision(project.id)
    phase = before.data.phases[0].id
    csv = (
        "id,phase_id,month,known_on,metric,amount,contract_id\n"
        f"invalid,{phase},2026-08,2026-08-31,collections,100,missing-contract\n"
    )
    assert service.preview_import(project.id, csv.encode()).errors
    record = s.Actual(
        id="invalid",
        phase_id=phase,
        month="2026-08",
        known_on=date(2026, 8, 31),
        metric="collections",
        amount="100",
        contract_id="missing-contract",
    )
    with pytest.raises(HTTPException) as invalid:
        service.confirm_import(
            project.id,
            s.ImportConfirm(base_version=1, known_on=date(2026, 8, 31), records=[record]),
        )
    assert invalid.value.status_code == 422
    assert service.revision(project.id) == before


def test_history_filters_before_pagination_and_retains_revision_diff(service: Service) -> None:
    first = service.create_project(s.ProjectCreate(name="早期项目", template="demo"))
    second = service.create_project(s.ProjectCreate(name="近期项目", template="demo"))
    old = service.create_run(s.RunCreate(project_ids=[first.id]), "early-run")
    for index in range(102):
        service.create_run(s.RunCreate(project_ids=[second.id]), f"recent-{index}")
    assert [run.id for run in service.runs(first.id)] == [old.id]
    page = service.run_page(second.id, offset=100, limit=20)
    assert page.total == 102 and len(page.items) == 2
    before = service.revision(first.id)
    data = before.data.model_copy(deep=True)
    data.phases[0].price = "12345"
    after = service.revise(
        first.id, s.RevisionWrite(base_version=1, known_on=date(2026, 9, 1), data=data)
    )
    assert service.revisions(first.id, offset=1, limit=1).items[0].id == before.id
    changes = service.compare_revisions(first.id, before.id, after.id).changes
    assert any(
        change.before == before.data.phases[0].price and change.after == "12345"
        for change in changes
    )
    with pytest.raises(HTTPException) as wrong_project:
        service.compare_revisions(second.id, before.id, after.id)
    assert wrong_project.value.status_code == 404


def test_import_retry_and_patch_receipts_are_atomic(service: Service) -> None:
    project = service.create_project(s.ProjectCreate(name="导入重试", template="demo"))
    revision = service.revision(project.id)
    record = s.Actual(
        id="new-record",
        phase_id=revision.data.phases[0].id,
        month="2026-08",
        known_on=date(2026, 8, 31),
        metric="expenses",
        amount="100",
    )
    body = s.ImportConfirm(base_version=1, known_on=date(2026, 8, 31), records=[record])
    saved = service.confirm_import(project.id, body, key="csv-retry")
    assert service.confirm_import(project.id, body, key="csv-retry") == saved
    assert service.revisions(project.id).total == 2
    patch = s.ProjectPatch(name="修订名称", base_version=2)
    changed = service.patch_project(project.id, patch, key="patch-retry")
    assert service.patch_project(project.id, patch, key="patch-retry") == changed
    assert service.revisions(project.id).total == 3
    with pytest.raises(HTTPException) as stale:
        service.confirm_import(project.id, body, key="a-new-operation")
    assert stale.value.status_code == 409


def test_failed_import_does_not_consume_key_or_partially_write(service: Service) -> None:
    project = service.create_project(s.ProjectCreate(name="导入回滚", template="demo"))
    before = service.revision(project.id)
    valid = s.Actual(
        id="ok",
        phase_id=before.data.phases[0].id,
        month="2026-08",
        known_on=date(2026, 8, 31),
        metric="expenses",
        amount="1",
    )
    invalid = valid.model_copy(update={"id": "bad", "phase_id": "other-project-phase"})
    body = s.ImportConfirm(base_version=1, known_on=date(2026, 8, 31), records=[valid, invalid])
    with pytest.raises(HTTPException):
        service.confirm_import(project.id, body, key="failed-import-key")
    assert service.revision(project.id) == before
    corrected = body.model_copy(update={"records": [valid]})
    assert service.confirm_import(project.id, corrected, key="failed-import-key").version == 2


def test_diff_uses_record_ids_not_array_positions(service: Service) -> None:
    project = service.create_project(s.ProjectCreate(name="版本差异", template="demo"))
    original = service.revision(project.id).data
    reordered = original.model_copy(deep=True)
    reordered.phases.reverse()
    reordered.costs.reverse()
    assert dataset_changes(original, reordered) == []
    reordered.phases[0].price = "321"
    changes = dataset_changes(original, reordered)
    assert len(changes) == 1 and reordered.phases[0].id in changes[0].path


def test_scope_filter_excludes_children_and_other_portfolio_members(service: Service) -> None:
    first = service.create_project(s.ProjectCreate(name="范围A", template="demo"))
    second = service.create_project(s.ProjectCreate(name="范围B", template="demo"))
    single = service.create_run(s.RunCreate(project_ids=[first.id]), "scope-single")
    group = service.create_run(
        s.RunCreate(kind="portfolio", project_ids=[first.id, second.id]), "scope-group"
    )
    assert [r.id for r in service.runs(scope_ids=first.id)] == [single.id]
    assert [r.id for r in service.runs(scope_ids=f"{second.id},{first.id}")] == [group.id]
    assert service.run_page(first.id).total == 2
    assert service.run_page(first.id, kind="portfolio").total == 1


def test_existing_database_upgrade_preserves_original_projects_and_runs(tmp_path: Path) -> None:
    old = Service(tmp_path, seed=False)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with old.engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
    project = old.create_project(s.ProjectCreate(name="升级前模拟项目", template="demo"))
    run = old.create_run(s.RunCreate(project_ids=[project.id]), "migration-run")
    assert old.process_next()
    saved = old.run(run.id)
    upgraded = Service(tmp_path, seed=False)
    upgraded.start(worker=False)
    assert upgraded.projects() == [project]
    assert upgraded.run(run.id) == saved
    created = upgraded.create_project(s.ProjectCreate(name="升级后重试"), key="upgraded-create")
    assert (
        upgraded.create_project(s.ProjectCreate(name="升级后重试"), key="upgraded-create")
        == created
    )
