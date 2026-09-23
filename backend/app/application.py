"""Application services shared by HTTP and future controlled Agent tools."""

import hashlib
import io
import logging
import os
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

import pandas as pd
from alembic.config import Config
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app import schemas as s
from app.domain import D, aggregate, calculate
from app.mutations import remember, replay
from app.revision_diff import dataset_changes
from app.seeds import demo_dataset
from app.storage import ProjectRow, RevisionRow, RunRow, make_engine


def now() -> str:
    return datetime.now(UTC).isoformat()


T = TypeVar("T")


def require(value: T | None, message: str, code: int = 404) -> T:
    if value is None:
        raise HTTPException(code, message)
    return value


class Service:
    def __init__(self, directory: Path | None = None, *, seed: bool = True) -> None:
        self.directory = directory or Path(os.environ.get("HARU_DATA_DIR", "data"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = make_engine(self.directory / "haru.sqlite3")
        self.lock = threading.RLock()
        self.halt = threading.Event()
        self.thread: threading.Thread | None = None
        self.seed = seed

    def start(self, *, worker: bool = True) -> None:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with self.engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with self.lock, Session(self.engine) as db, db.begin():
            for row in db.scalars(select(RunRow).where(RunRow.status.in_(["running", "waiting"]))):
                row.status = "interrupted"
                self._event(row, "恢复检查", "interrupted", "服务重启，等待按原输入继续")
        if self.seed and not self.projects():
            self.create_project(s.ProjectCreate(name="云汀花园", template="demo"), variant=0)
            self.create_project(s.ProjectCreate(name="松岚雅苑", template="demo"), variant=1)
        self.halt.clear()
        if worker:
            self.thread = threading.Thread(target=self._worker, name="haru-jobs", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.halt.set()
        if self.thread:
            self.thread.join(timeout=10)

    def health(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def projects(self) -> list[s.Project]:
        with Session(self.engine) as db:
            return [s.Project.model_validate(r.payload) for r in db.scalars(select(ProjectRow))]

    def create_project(
        self, body: s.ProjectCreate, variant: int = 0, *, key: str | None = None
    ) -> s.Project:
        project_id, revision_id = str(uuid4()), str(uuid4())
        data = demo_dataset(variant) if body.template == "demo" else s.Dataset()
        created = now()
        project = s.Project(
            id=project_id,
            name=body.name.strip(),
            archived=False,
            version=1,
            revision_id=revision_id,
            created_at=created,
        )
        known = "2026-08-31" if body.template == "demo" else date.today().isoformat()
        revision = s.Revision(
            id=revision_id,
            project_id=project_id,
            version=1,
            known_on=known,
            created_at=created,
            note="模拟模板" if body.template == "demo" else "空白项目",
            data=data,
        )
        with self.lock, Session(self.engine) as db, db.begin():
            cached = replay(db, key, "create-project", body)
            if cached is not None:
                return s.Project.model_validate(cached)
            db.add(ProjectRow(id=project_id, version=1, payload=project.model_dump(mode="json")))
            db.flush()
            db.add(
                RevisionRow(
                    id=revision_id,
                    project_id=project_id,
                    version=1,
                    known_on=known,
                    payload=revision.model_dump(mode="json"),
                )
            )
            remember(db, key, "create-project", body, project)
        return project

    def patch_project(
        self, project_id: str, body: s.ProjectPatch, *, key: str | None = None
    ) -> s.Project:
        with self.lock, Session(self.engine) as db, db.begin():
            operation = f"patch-project:{project_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.Project.model_validate(cached)
            row = require(db.get(ProjectRow, project_id), "项目不存在")
            if row.version != body.base_version:
                raise HTTPException(409, "项目版本已变化，请重新核对")
            previous = require(db.get(RevisionRow, row.payload["revision_id"]), "版本不存在")
            revision_id = str(uuid4())
            row.version += 1
            payload = {
                **previous.payload,
                "id": revision_id,
                "version": row.version,
                "created_at": now(),
                "note": "项目基本信息修订，业务输入保持不变",
            }
            db.add(
                RevisionRow(
                    id=revision_id,
                    project_id=project_id,
                    version=row.version,
                    known_on=previous.known_on,
                    payload=payload,
                )
            )
            row.payload = {
                **row.payload,
                "name": body.name.strip(),
                "archived": body.archived,
                "version": row.version,
                "revision_id": revision_id,
            }
            result = s.Project.model_validate(row.payload)
            remember(db, key, operation, body, result)
            return result

    def revision(self, project_id: str, revision_id: str | None = None) -> s.Revision:
        with Session(self.engine) as db:
            project = require(db.get(ProjectRow, project_id), "项目不存在")
            row = require(
                db.get(RevisionRow, revision_id or project.payload["revision_id"]), "版本不存在"
            )
            if row.project_id != project_id:
                raise HTTPException(404, "版本不属于该项目")
            return s.Revision.model_validate(row.payload)

    def revise(
        self, project_id: str, body: s.RevisionWrite, *, key: str | None = None
    ) -> s.Revision:
        with self.lock, Session(self.engine) as db, db.begin():
            operation = f"revise:{project_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.Revision.model_validate(cached)
            revision = self._write_revision(db, project_id, body)
            remember(db, key, operation, body, revision)
            return revision

    def _write_revision(self, db: Session, project_id: str, body: s.RevisionWrite) -> s.Revision:
        row = require(db.get(ProjectRow, project_id), "项目不存在")
        if row.version != body.base_version:
            raise HTTPException(409, "数据已被修订；保留草稿并重新核对基础版本")
        if row.payload["archived"]:
            raise HTTPException(409, "归档项目不能修改")
        revision = s.Revision(
            id=str(uuid4()),
            project_id=project_id,
            version=row.version + 1,
            known_on=body.known_on.isoformat(),
            created_at=now(),
            note=body.note,
            data=body.data,
        )
        db.add(
            RevisionRow(
                id=revision.id,
                project_id=project_id,
                version=revision.version,
                known_on=revision.known_on,
                payload=revision.model_dump(mode="json"),
            )
        )
        row.version = revision.version
        row.payload = {**row.payload, "version": revision.version, "revision_id": revision.id}
        return revision

    def revisions(self, project_id: str, *, offset: int = 0, limit: int = 20) -> s.RevisionPage:
        with Session(self.engine) as db:
            require(db.get(ProjectRow, project_id), "项目不存在")
            query = select(RevisionRow).where(RevisionRow.project_id == project_id)
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = db.scalars(
                query.order_by(RevisionRow.version.desc()).offset(offset).limit(limit)
            )
            return s.RevisionPage(
                items=[
                    s.RevisionInfo.model_validate(
                        {k: v for k, v in row.payload.items() if k != "data"}
                    )
                    for row in rows
                ],
                total=total,
                offset=offset,
                limit=limit,
            )

    def compare_revisions(
        self, project_id: str, left_id: str, right_id: str
    ) -> s.RevisionComparison:
        left, right = self.revision(project_id, left_id), self.revision(project_id, right_id)
        return s.RevisionComparison(
            project_id=project_id,
            left_id=left_id,
            right_id=right_id,
            changes=dataset_changes(left.data, right.data),
        )

    def preview_import(self, project_id: str, data: bytes) -> s.ImportPreview:
        revision = self.revision(project_id)
        result = s.ImportPreview(
            project_id=project_id,
            base_version=revision.version,
            additions=[],
            duplicates=[],
            errors=[],
        )
        if len(data) > 2_000_000:
            raise HTTPException(413, "CSV上限为2MB")
        try:
            frame = pd.read_csv(
                io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig"
            )
            required = {"id", "phase_id", "month", "known_on", "metric", "amount"}
            if not required.issubset(frame.columns):
                raise ValueError("CSV缺少字段：" + ", ".join(sorted(required - set(frame.columns))))
            if len(frame) > 5000:
                raise ValueError("CSV最多5000行")
            existing = {r.id: r for r in revision.data.actuals}
            contracts = {c.id: c for c in revision.data.contracts}
            for index, row in enumerate(frame.to_dict(orient="records"), start=2):
                try:
                    payload = {str(k): v for k, v in row.items() if v != ""}
                    record = s.Actual.model_validate(payload)
                    if record.phase_id not in {p.id for p in revision.data.phases}:
                        raise ValueError("分期不属于当前项目")
                    if record.contract_id and (
                        record.contract_id not in contracts
                        or contracts[record.contract_id].phase_id != record.phase_id
                    ):
                        raise ValueError("实际记录关联的合同不属于对应分期")
                    if record.id in existing:
                        if record != existing[record.id]:
                            raise ValueError("相同编号有不同内容，请通过修订编辑")
                        result.duplicates.append(record.id)
                    else:
                        result.additions.append(record)
                        existing[record.id] = record
                except ValueError as exc:
                    result.errors.append(f"第{index}行：{exc}")
        except (ValueError, UnicodeError) as exc:
            result.errors.append(str(exc))
        return result

    def confirm_import(
        self, project_id: str, body: s.ImportConfirm, *, key: str | None = None
    ) -> s.Revision:
        with self.lock, Session(self.engine) as db, db.begin():
            operation = f"confirm-import:{project_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.Revision.model_validate(cached)
            project = require(db.get(ProjectRow, project_id), "项目不存在")
            if project.payload["archived"]:
                raise HTTPException(409, "归档项目不能导入")
            row = require(db.get(RevisionRow, project.payload["revision_id"]), "版本不存在")
            revision = s.Revision.model_validate(row.payload)
            if revision.version != body.base_version:
                raise HTTPException(409, "导入预览后数据已变化，请重新预览")
            existing = {r.id: r for r in revision.data.actuals}
            for record in body.records:
                if record.id in existing and record != existing[record.id]:
                    raise HTTPException(409, "记录编号相同但内容不同")
                existing[record.id] = record
            if list(existing.values()) == revision.data.actuals:
                remember(db, key, operation, body, revision)
                return revision
            try:
                data = s.Dataset.model_validate(
                    {**revision.data.model_dump(), "actuals": list(existing.values())}
                )
            except ValidationError as exc:
                message = "; ".join(error["msg"] for error in exc.errors())
                raise HTTPException(422, message) from exc
            saved = self._write_revision(
                db,
                project_id,
                s.RevisionWrite(
                    base_version=body.base_version,
                    known_on=body.known_on,
                    note="CSV增量导入",
                    data=data,
                ),
            )
            remember(db, key, operation, body, saved)
            return saved

    def _event(self, row: RunRow, name: str, status: str, message: str) -> None:
        steps = row.payload.get("steps", [])
        step = s.Step(
            sequence=len(steps) + 1,
            name=name,
            status=status,
            message=message,
            created_at=now(),
            attempt=row.payload.get("attempt", 1),
        )
        row.payload = {**row.payload, "steps": [*steps, step.model_dump()]}

    def _make_row(
        self,
        body: s.RunCreate,
        snapshots: list[s.Revision],
        names: list[str],
        parent_id: str | None = None,
    ) -> RunRow:
        run = s.Run(
            id=str(uuid4()),
            kind=body.kind,
            status="queued",
            created_at=now(),
            forecast_origin=body.forecast_origin.isoformat(),
            information_cutoff=body.information_cutoff.isoformat(),
            scenario=body.scenario,
            project_ids=body.project_ids,
            project_names=names,
            revision_ids=[r.id for r in snapshots],
            overrides=body.overrides,
            parent_id=parent_id,
            supersedes_run_id=body.supersedes_run_id if parent_id is None else None,
        )
        row = RunRow(
            id=run.id,
            status="queued",
            kind=body.kind,
            created_at=run.created_at,
            request_hash="",
            payload=run.model_dump(mode="json"),
            snapshots=[r.model_dump(mode="json") for r in snapshots],
        )
        self._event(row, "固定输入", "completed", "项目、时点和输入版本已冻结")
        return row

    def create_run(self, body: s.RunCreate, key: str) -> s.Run:
        digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        with self.lock, Session(self.engine) as db, db.begin():
            existing = db.scalar(select(RunRow).where(RunRow.idempotency_key == key))
            if existing:
                if existing.request_hash != digest:
                    raise HTTPException(409, "幂等键已用于不同请求")
                return self._view(db, existing)
            if body.supersedes_run_id:
                previous = require(db.get(RunRow, body.supersedes_run_id), "关联的旧运行不存在")
                if previous.kind != body.kind or set(previous.payload["project_ids"]) != set(
                    body.project_ids
                ):
                    raise HTTPException(409, "关联运行必须具有相同项目范围和运行类型")
            snapshots, names = [], []
            for project_id in body.project_ids:
                project = require(db.get(ProjectRow, project_id), "项目不存在")
                if project.payload["archived"]:
                    raise HTTPException(409, "归档项目不能新建预测")
                if (
                    project_id in body.base_versions
                    and body.base_versions[project_id] != project.version
                ):
                    raise HTTPException(409, "输入版本已变化，请重新核对")
                revision = db.scalar(
                    select(RevisionRow)
                    .where(
                        RevisionRow.project_id == project_id,
                        RevisionRow.known_on <= body.information_cutoff.isoformat(),
                    )
                    .order_by(RevisionRow.version.desc())
                    .limit(1)
                )
                if revision is None:
                    # Persist the failed attempt without calculating with future information.
                    revision = require(
                        db.get(RevisionRow, project.payload["revision_id"]), "缺少输入"
                    )
                snapshots.append(s.Revision.model_validate(revision.payload))
                names.append(project.payload["name"])
            row = self._make_row(body, snapshots, names)
            row.idempotency_key, row.request_hash = key, digest
            if body.kind == "portfolio":
                row.status = "waiting"
                members = []
                for snapshot, name in zip(snapshots, names, strict=True):
                    child_body = body.model_copy(
                        update={
                            "kind": "project",
                            "project_ids": [snapshot.project_id],
                            "overrides": {
                                snapshot.project_id: body.overrides.get(
                                    snapshot.project_id, s.Overrides()
                                )
                            },
                        }
                    )
                    child = self._make_row(child_body, [snapshot], [name], parent_id=row.id)
                    db.add(child)
                    members.append(
                        s.Member(
                            project_id=snapshot.project_id,
                            project_name=name,
                            run_id=child.id,
                            revision_id=snapshot.id,
                            status="queued",
                        ).model_dump()
                    )
                row.payload = {**row.payload, "members": members}
            db.add(row)
            db.flush()
            return self._view(db, row)

    def _view(self, db: Session, row: RunRow) -> s.Run:
        run = s.Run.model_validate({**row.payload, "status": row.status, "result": row.result})
        for member in run.members:
            child = require(db.get(RunRow, member.run_id), "子运行不存在")
            member.status = child.status
            member.error = child.payload.get("error")
            if child.result:
                member.profit = str(child.result["summary"]["twelve_month_profit"])
        return run

    def run(self, run_id: str) -> s.Run:
        with Session(self.engine) as db:
            return self._view(db, require(db.get(RunRow, run_id), "运行不存在"))

    def runs(self, project_id: str | None = None, *, scope_ids: str | None = None) -> list[s.Run]:
        return self.run_page(project_id, limit=100, scope_ids=scope_ids).items

    def run_page(
        self,
        project_id: str | None = None,
        *,
        kind: str | None = None,
        offset: int = 0,
        limit: int = 20,
        scope_ids: str | None = None,
    ) -> s.RunPage:
        with Session(self.engine) as db:
            query = select(RunRow).where(RunRow.payload["parent_id"].as_string().is_(None))
            if project_id:
                query = query.where(
                    text(
                        "EXISTS (SELECT 1 FROM json_each(runs.payload, '$.project_ids') "
                        "WHERE value = :project_id)"
                    ).bindparams(project_id=project_id)
                )
            if kind:
                query = query.where(RunRow.kind == kind)
            if scope_ids is not None:
                ids = sorted(set(scope_ids.split(",")))
                if len(ids) > 50 or any(not project for project in ids):
                    raise HTTPException(422, "查询范围须为1至50个项目编号")
                query = query.where(
                    func.json_array_length(RunRow.payload["project_ids"]) == len(ids)
                )
                for index, project in enumerate(ids):
                    parameter = f"scope_{index}"
                    query = query.where(
                        text(
                            "EXISTS (SELECT 1 FROM json_each(runs.payload, '$.project_ids') "
                            f"WHERE value = :{parameter})"
                        ).bindparams(**{parameter: project})
                    )
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = db.scalars(
                query.order_by(RunRow.created_at.desc(), RunRow.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return s.RunPage(
                items=[self._view(db, row) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    def resume(self, run_id: str) -> s.Run:
        with self.lock, Session(self.engine) as db, db.begin():
            row = require(db.get(RunRow, run_id), "运行不存在")
            if row.status not in ("interrupted", "failed", "incomplete"):
                return self._view(db, row)
            targets = [row]
            targets.extend(
                require(db.get(RunRow, m["run_id"]), "子运行不存在")
                for m in row.payload.get("members", [])
            )
            for target in targets:
                if target.status == "completed":
                    continue
                target.status = "waiting" if target.kind == "portfolio" else "queued"
                target.payload = {
                    **target.payload,
                    "attempt": target.payload["attempt"] + 1,
                    "error": None,
                }
                self._event(target, "恢复请求", "queued", "按原快照重试，不采用最新输入")
            return self._view(db, row)

    def process_next(self) -> bool:
        with self.lock, Session(self.engine) as db, db.begin():
            row = db.scalar(
                select(RunRow)
                .where(RunRow.status == "queued", RunRow.kind == "project")
                .order_by(RunRow.created_at)
                .limit(1)
            )
            if row is None:
                return self._aggregate_ready(db)
            row.status = "running"
            self._event(row, "数据检查与计算", "running", "程序按固定输入与计算规则执行测算")
            run_id = row.id
            snapshot = s.Revision.model_validate(row.snapshots[0])
            request = s.Run.model_validate({**row.payload, "status": row.status})
        try:
            if snapshot.known_on > request.information_cutoff:
                raise ValueError("信息截止时点之前没有可用输入版本")
            result = calculate(
                snapshot.data,
                date.fromisoformat(request.forecast_origin),
                date.fromisoformat(request.information_cutoff),
                request.scenario,
                request.overrides.get(snapshot.project_id),
            )
            with self.lock, Session(self.engine) as db, db.begin():
                saved = require(db.get(RunRow, run_id), "运行不存在")
                saved.result = result.model_dump(mode="json")
                saved.status = "completed"
                self._event(
                    saved, "结果校验与保存", "completed", "数值、来源和情景结果已保存；AI尚未接入"
                )
        except Exception as exc:
            if not isinstance(exc, ValueError):
                logging.getLogger(__name__).exception("Calculation failed: run %s", run_id)
            with self.lock, Session(self.engine) as db, db.begin():
                saved = require(db.get(RunRow, run_id), "运行不存在")
                message = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "程序执行失败，请检查服务日志与运行编号"
                )
                saved.status = "failed"
                saved.payload = {**saved.payload, "error": message}
                self._event(saved, "执行失败", "failed", message)
        return True

    def _aggregate_ready(self, db: Session) -> bool:
        for row in db.scalars(
            select(RunRow).where(RunRow.status == "waiting", RunRow.kind == "portfolio")
        ):
            children = [
                require(db.get(RunRow, m["run_id"]), "子运行不存在") for m in row.payload["members"]
            ]
            if any(c.status in ("queued", "running", "waiting") for c in children):
                continue
            if any(c.status != "completed" for c in children):
                row.status = "incomplete"
                row.payload = {**row.payload, "error": "部分项目未完成，未输出完整汇总总额"}
                self._event(row, "项目汇总", "incomplete", row.payload["error"])
            else:
                result = aggregate(s.ForecastResult.model_validate(c.result) for c in children)
                row.result = result.model_dump(mode="json")
                row.status = "completed"
                self._event(row, "项目汇总", "completed", "按绑定子运行汇总；缺口逐项目保留")
            return True
        return False

    def _worker(self) -> None:
        while not self.halt.is_set():
            if not self.process_next():
                self.halt.wait(0.2)

    def evidence(self, run_id: str, metric: str, month: str | None) -> s.Evidence:
        run = self.run(run_id)
        related = {
            "profit": {"revenue", "cogs", "expenses", "taxes", "interest"},
            "net_cash_flow": {
                "collections",
                "payments",
                "expense_payments",
                "tax_payments",
                "interest",
                "borrowing",
                "repayment",
            },
        }
        cumulative = metric in {"cash_balance", "uncovered_gap", "max_funding_gap"}
        profit_window = metric in {"twelve_month_profit", "cumulative_profit"}
        if profit_window:
            related[metric] = related["profit"]
        metrics = (
            related["net_cash_flow"] | {"opening_cash"}
            if cumulative
            else related.get(metric, {metric})
        )
        if metric in {"max_funding_gap", "uncovered_gap"} and run.result and not month:
            month = max(
                (m for m in run.result.months if m.month >= run.result.target_months[0]),
                key=lambda m: D(m.uncovered_gap),
            ).month
        sources = (
            [
                r
                for r in run.result.sources
                if r.metric in metrics
                and (not month or (r.month <= month if cumulative else r.month == month))
            ]
            if run.result
            else []
        )
        if profit_window and run.result:
            end = month or run.result.target_months[-1]
            sources = [
                r
                for r in run.result.sources
                if r.metric in metrics and run.result.target_months[0] <= r.month <= end
            ]
        return s.Evidence(
            run_id=run_id,
            metric=metric,
            month=month,
            revision_ids=run.revision_ids,
            sources=sources,
            members=run.members,
        )

    def compare(self, left_id: str, right_id: str) -> s.Comparison:
        from app.domain_analysis import compare_results

        left, right = self.run(left_id), self.run(right_id)
        if not left.result or not right.result:
            raise HTTPException(409, "仅可比较完整结果")
        try:
            bridge, total = compare_results(left.result, right.result)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return s.Comparison(
            left_id=left_id,
            right_id=right_id,
            months=[row.month for row in bridge],
            profit_deltas=[row.profit for row in bridge],
            membership_changed=set(left.project_ids) != set(right.project_ids),
            bridge=bridge,
            total_bridge=total,
        )


service = Service()
