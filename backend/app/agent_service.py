"""One bounded LangGraph for queries and proposals; only humans confirm changes."""

import logging
import secrets
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict
from uuid import uuid4

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas as s
from app.agent_model import DeepSeekModel, ModelFailure, QueryModel
from app.domain_changes import apply_change
from app.domain_parameters import effective_parameters
from app.domain_query import query_result
from app.mutations import remember, replay
from app.storage import AgentTaskRow

if TYPE_CHECKING:
    from app.application import Service


class GraphState(TypedDict):
    task_id: str
    round: int
    plan: NotRequired[dict[str, Any]]


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class AgentService:
    def __init__(self, application: "Service", model: QueryModel | None = None) -> None:
        self.application = application
        self.model: QueryModel = model or DeepSeekModel()
        self.configuration_source: Literal["environment", "memory", "none"] = (
            "environment" if self.model.configured else "none"
        )
        self.configuration_token = secrets.token_urlsafe(32)
        self.configuring = False
        self.connection = sqlite3.connect(
            application.directory / "agent-checkpoints.sqlite3",
            check_same_thread=False,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.saver = SqliteSaver(self.connection)
        self.saver.setup()
        builder = StateGraph(GraphState)
        builder.add_node("understand", self._understand)
        builder.add_node("clarify", self._clarify)
        builder.add_node("query", self._query)
        builder.add_node("draft", self._draft)
        builder.add_edge(START, "understand")
        builder.add_conditional_edges(
            "understand",
            self._route,
            {
                "clarify": "clarify",
                "query": "query",
                "draft": "draft",
            },
        )
        builder.add_edge("clarify", "understand")
        builder.add_edge("query", END)
        builder.add_edge("draft", END)
        self.graph = builder.compile(checkpointer=self.saver)
        with application.lock, Session(application.engine) as db, db.begin():
            for row in db.scalars(select(AgentTaskRow).where(AgentTaskRow.status == "running")):
                row.status = "interrupted"
                row.payload = self._event(
                    row.payload, "恢复检查", "interrupted", "服务重启，按原运行继续"
                )

    def close(self) -> None:
        self.connection.close()

    def status(self) -> s.AgentStatus:
        return s.AgentStatus(
            configured=self.model.configured,
            provider=self.model.provider,
            model=self.model.model,
        )

    def configuration_status(self) -> s.ModelConfigurationStatus:
        with self.application.lock:
            return s.ModelConfigurationStatus(
                configured=self.model.configured,
                model=self.model.model,
                source=self.configuration_source,
                csrf_token=self.configuration_token,
            )

    def configure(self, body: s.ModelConfiguration | None) -> s.ModelConfigurationStatus:
        with self.application.lock, Session(self.application.engine) as db:
            if self.configuring or db.scalar(
                select(AgentTaskRow.id)
                .where(AgentTaskRow.status.in_(["queued", "running"]))
                .limit(1)
            ):
                raise HTTPException(409, "模型正在处理任务或测试连接，请稍后再配置")
            self.configuring = True
        try:
            candidate = DeepSeekModel(
                api_key=body.api_key.get_secret_value() if body else "",
                model=body.model if body else "",
            )
            if body:
                # Only synthetic routing metadata; no project data or task is persisted.
                candidate.plan(
                    "未来12个月利润是多少？",
                    [],
                    {
                        "mode": "query",
                        "project_names": ["连接测试"],
                        "scope_kind": "project",
                        "scenario": "base",
                        "target_months": ["2026-09"],
                        "available_months": ["2026-09"],
                        "phases": [],
                        "dialogue": [],
                    },
                )
            with self.application.lock:
                self.model = candidate
                self.configuration_source = "memory" if body else "none"
            return self.configuration_status()
        except Exception:
            # Never include provider exceptions, response text or submitted credentials.
            raise HTTPException(
                502, "连接测试失败，原配置保持不变。请核对密钥、模型名称或网络后重试。"
            ) from None
        finally:
            with self.application.lock:
                self.configuring = False

    @staticmethod
    def _view(row: AgentTaskRow) -> s.AgentTask:
        dialogue = list(row.payload.get("dialogue", []))
        if not dialogue:  # older saved tasks already contain plans and reply text
            replies = iter(row.payload.get("replies", []))
            for _, plan in sorted(
                row.payload.get("plans", {}).items(), key=lambda item: int(item[0])
            ):
                if plan.get("action") == "clarify":
                    dialogue.append({"role": "assistant", "content": plan["clarification"]})
                    reply = next(replies, None)
                    if reply is not None:
                        dialogue.append({"role": "user", "content": reply})
        return s.AgentTask.model_validate(
            {
                **{
                    key: value
                    for key, value in row.payload.items()
                    if key in s.AgentTask.model_fields
                },
                "status": row.status,
                "dialogue": dialogue,
            }
        )

    @staticmethod
    def _event(payload: dict[str, Any], name: str, status: str, message: str) -> dict[str, Any]:
        steps = list(payload.get("steps", []))
        steps.append(
            s.Step(
                sequence=len(steps) + 1,
                name=name,
                status=status,
                message=message,
                created_at=timestamp(),
                attempt=payload.get("attempt", 1),
            ).model_dump(mode="json")
        )
        return {**payload, "steps": steps}

    def _row(self, db: Session, task_id: str) -> AgentTaskRow:
        row = db.get(AgentTaskRow, task_id)
        if row is None:
            raise HTTPException(404, "问数任务不存在")
        return row

    def get(self, task_id: str) -> s.AgentTask:
        with Session(self.application.engine) as db:
            return self._view(self._row(db, task_id))

    def list(self, run_id: str, offset: int = 0) -> list[s.AgentTask]:
        self.application.run(run_id)
        with Session(self.application.engine) as db:
            return [
                self._view(row)
                for row in db.scalars(
                    select(AgentTaskRow)
                    .where(AgentTaskRow.run_id == run_id)
                    .order_by(AgentTaskRow.created_at.desc())
                    .offset(offset)
                    .limit(20)
                )
            ]

    def create(self, body: s.AgentCreate, key: str) -> s.AgentTask:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            if self.configuring:
                raise HTTPException(409, "模型正在测试连接，请稍后提交")
            cached = replay(db, key, "agent-create", body)
            if cached is not None:
                return s.AgentTask.model_validate(cached)
            if not self.model.configured:
                raise HTTPException(503, "DeepSeek 未配置；请在服务端设置密钥及模型名称")
            run = self.application.run(body.run_id)
            if run.status != "completed" or run.result is None:
                raise HTTPException(409, "只能查询已完成的预测运行")
            if body.mode == "change":
                if run.kind != "project" or len(run.project_ids) != 1 or body.known_on is None:
                    raise HTTPException(422, "变更草稿须绑定单项目预测并明确获知日期")
                base = self.application.revision(run.project_ids[0])
                if run.revision_ids != [base.id]:
                    raise HTTPException(409, "绑定预测已不是最新输入版本，请先用最新版本生成预测")
                if body.known_on.isoformat() < base.known_on:
                    raise HTTPException(422, "变更获知日期不能早于基础版本")
            task = s.AgentTask(
                id=str(uuid4()),
                run_id=run.id,
                question=body.question,
                status="queued",
                created_at=timestamp(),
                model=self.model.model,
                provider=self.model.provider,
                mode=body.mode,
                known_on=body.known_on,
            )
            payload = self._event(
                task.model_dump(mode="json"), "提交问数", "queued", "绑定已完成运行，等待解析"
            )
            task = s.AgentTask.model_validate(payload)
            db.add(
                AgentTaskRow(
                    id=task.id,
                    run_id=task.run_id,
                    status=task.status,
                    created_at=task.created_at,
                    payload={**payload, "plans": {}, "replies": []},
                )
            )
            remember(db, key, "agent-create", body, task)
            return task

    def reply(self, task_id: str, body: s.AgentReply, key: str) -> s.AgentTask:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            if self.configuring:
                raise HTTPException(409, "模型正在测试连接，请稍后补充")
            operation = f"agent-reply:{task_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.AgentTask.model_validate(cached)
            if not self.model.configured:
                raise HTTPException(503, "请先配置模型，再继续补充回答")
            row = self._row(db, task_id)
            if row.status != "awaiting_reply" or row.payload.get("reply_token") != body.token:
                raise HTTPException(409, "澄清问题已变化或已经回答，请刷新任务")
            if row.payload["calls"] >= 3:
                raise HTTPException(409, "本任务已达到模型调用上限，请用明确的问题新建任务")
            row.status = "queued"
            row.payload = self._event(
                {
                    **row.payload,
                    "replies": [*row.payload["replies"], body.reply],
                    "dialogue": [
                        *[message.model_dump() for message in self._view(row).dialogue],
                        {"role": "user", "content": body.reply},
                    ],
                    "pending_reply": {"token": body.token, "reply": body.reply},
                    "reply_token": None,
                    "error": None,
                },
                "补充回答",
                "queued",
                "已保存回答，等待继续解析",
            )
            task = self._view(row)
            remember(db, key, operation, body, task)
            return task

    def resume(self, task_id: str) -> s.AgentTask:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            if self.configuring:
                raise HTTPException(409, "模型正在测试连接，请稍后恢复")
            row = self._row(db, task_id)
            if row.status in {
                "queued",
                "running",
                "completed",
                "awaiting_reply",
                "awaiting_confirmation",
            }:
                return self._view(row)
            if not self.model.configured:
                raise HTTPException(503, "DeepSeek 未配置")
            if row.payload["attempt"] >= 3:
                raise HTTPException(409, "已达到任务恢复上限，请新建任务")
            row.status = "queued"
            row.payload = self._event(
                {
                    **row.payload,
                    "attempt": row.payload["attempt"] + 1,
                    "error": None,
                },
                "恢复问数",
                "queued",
                "沿用原运行及已保存的检查点",
            )
            return self._view(row)

    def _payload(self, task_id: str) -> dict[str, Any]:
        with Session(self.application.engine) as db:
            return dict(self._row(db, task_id).payload)

    def _update(
        self,
        task_id: str,
        changes: dict[str, Any],
        *,
        status: str | None = None,
        event: tuple[str, str, str] | None = None,
    ) -> None:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            row = self._row(db, task_id)
            payload = {**row.payload, **changes}
            row.payload = self._event(payload, *event) if event else payload
            if status is not None:
                row.status = status

    def _understand(self, state: GraphState) -> dict[str, Any]:
        task_id, round_key = state["task_id"], str(state["round"])
        payload = self._payload(task_id)
        cached = payload["plans"].get(round_key)
        if cached is not None:
            return {"plan": cached}
        if payload["calls"] >= 3:
            raise ModelFailure("本任务已达到三次模型调用上限，请用明确的问题新建任务")
        if payload["model"] != self.model.model or payload["provider"] != self.model.provider:
            raise ModelFailure("模型配置已变化；请恢复原模型配置或新建任务")
        run = self.application.run(payload["run_id"])
        if run.result is None:
            raise ModelFailure("绑定运行缺少结果")
        self._update(
            task_id,
            {"calls": payload["calls"] + 1},
            event=(
                "解析问题",
                "running",
                "模型仅选择指标和期间，不接收或生成财务金额",
            ),
        )
        plan = self.model.plan(
            payload["question"],
            payload["replies"],
            {
                "forecast_origin": run.forecast_origin,
                "project_names": run.project_names,
                "scope_kind": run.kind,
                "scenario": run.scenario,
                "target_months": run.result.target_months,
                "available_months": [month.month for month in run.result.months],
                "dialogue": [message.model_dump() for message in self.get(task_id).dialogue],
                "mode": payload.get("mode", "query"),
                "phases": [
                    {"id": phase.id, "name": phase.name}
                    for phase in self.application.revision(
                        run.project_ids[0], run.revision_ids[0]
                    ).data.phases
                ]
                if run.kind == "project"
                else [],
            },
        )
        # Validate even injected adapters: the tool boundary trusts no model implementation.
        plan = s.AgentPlan.model_validate(plan.model_dump())
        # Model routing is advisory. Independently reject named foreign projects,
        # portfolio subsets and comparison requests before accessing any amount.
        latest = " ".join([payload["question"], *payload["replies"]])
        if payload["replies"] and "当前范围" in payload["replies"][-1]:
            latest = payload["replies"][-1]
        mentioned = {p.name for p in self.application.projects() if p.name in latest}
        mentioned.update(plan.project_names)
        if plan.action in {"query", "draft"} and (
            plan.scope != "bound"
            or bool(mentioned - set(run.project_names))
            or (run.kind == "portfolio" and bool(mentioned) and mentioned != set(run.project_names))
            or (
                run.kind == "project"
                and any(w in latest for w in ("所有项目", "全部项目", "跨项目", "组合", "对比"))
            )
        ):
            plan = s.AgentPlan(
                action="clarify",
                clarification="本任务只绑定“"
                + "、".join(run.project_names)
                + "”的这次结果。若要查询其他范围，请打开对应预测；"
                + "若继续当前范围，请明确说查询当前范围及指标、期间。",
            )
        if plan.action == "draft" and payload.get("mode", "query") != "change":
            plan = s.AgentPlan(
                action="clarify",
                clarification="当前是只读问数。请使用变更草稿入口并明确项目、分期和获知日期。",
            )
        changes: dict[str, Any] = {"plans": {**payload["plans"], round_key: plan.model_dump()}}
        if plan.action == "clarify":
            if payload["calls"] + 1 >= 3:
                raise ModelFailure("三次解析后仍需澄清，请明确指标和期间后新建任务")
            changes.update(clarification=plan.clarification, reply_token=str(uuid4()))
            changes["dialogue"] = [
                *[message.model_dump() for message in self.get(task_id).dialogue],
                {"role": "assistant", "content": plan.clarification},
            ]
        self._update(task_id, changes, event=("解析完成", "completed", "只读查询结构已校验"))
        return {"plan": plan.model_dump()}

    @staticmethod
    def _route(state: GraphState) -> str:
        return str(state["plan"]["action"])

    def _clarify(self, state: GraphState) -> dict[str, Any]:
        payload = self._payload(state["task_id"])
        interrupt({"question": payload["clarification"], "token": payload["reply_token"]})
        return {"round": state["round"] + 1}

    def _query(self, state: GraphState) -> dict[str, Any]:
        payload = self._payload(state["task_id"])
        run = self.application.run(payload["run_id"])
        if run.result is None:
            raise ModelFailure("绑定运行缺少结果")
        try:
            answer = query_result(run.result, s.AgentPlan.model_validate(state["plan"]))
        except ValueError:
            raise ModelFailure("查询期间或指标不在原运行范围内，请核对问题后新建任务") from None
        self._update(
            state["task_id"],
            {
                "answer": answer.model_dump(mode="json"),
                "clarification": None,
                "reply_token": None,
            },
            event=("查询结果", "completed", "程序从绑定运行读取金额，保留来源入口"),
        )
        return {}

    def _draft(self, state: GraphState) -> dict[str, Any]:
        payload = self._payload(state["task_id"])
        if payload.get("draft"):
            return {}  # crash after business save, before graph checkpoint
        task = self.get(state["task_id"])
        plan = s.AgentPlan.model_validate(state["plan"])
        run = self.application.run(task.run_id)
        if task.mode != "change" or run.kind != "project" or not task.known_on or not plan.change:
            raise ModelFailure("变更必须从单项目草稿入口发起")
        base = self.application.revision(run.project_ids[0], run.revision_ids[0])
        try:
            data, before, after = apply_change(base.data, plan.change, task.known_on)
            preview = effective_parameters(
                base.model_copy(update={"data": data}),
                run.project_names[0],
                task.known_on,
                "base",
                s.Overrides(),
            )
        except ValueError as exc:
            raise ModelFailure(str(exc)) from None
        phase = next(p for p in data.phases if p.id == plan.change.phase_id)
        draft = s.ChangeDraft(
            id=str(uuid4()),
            token=str(uuid4()),
            project_id=base.project_id,
            project_name=run.project_names[0],
            phase_id=phase.id,
            phase_name=phase.name,
            base_revision_id=base.id,
            base_version=base.version,
            known_on=task.known_on,
            change=plan.change,
            before=before,
            after=after,
            preview=preview,
        )
        self._update(
            task.id,
            {"draft": draft.model_dump(mode="json")},
            event=("生成草稿", "completed", "程序生成参数预览，等待人工确认；尚未修改输入"),
        )
        return {}

    def confirm(self, task_id: str, body: s.ChangeConfirm, key: str) -> s.AgentTask:
        # Confirmation and revision share one transaction. Models cannot call this method.
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            operation = f"agent-confirm:{task_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.AgentTask.model_validate(cached)
            row = self._row(db, task_id)
            task = self._view(row)
            draft = task.draft
            if draft is None or body != s.ChangeConfirm(
                draft_id=draft.id,
                token=draft.token,
                project_id=draft.project_id,
                phase_id=draft.phase_id,
                base_revision_id=draft.base_revision_id,
                base_version=draft.base_version,
            ):
                raise HTTPException(409, "确认与原项目、分期、基础版本或草稿不一致")
            if draft.revision_id:
                return task
            if row.status != "awaiting_confirmation":
                raise HTTPException(409, "草稿尚不可确认")
            base = self.application.revision(draft.project_id, draft.base_revision_id)
            data, _, _ = apply_change(base.data, draft.change, draft.known_on)
            revision = self.application._write_revision(
                db,
                draft.project_id,
                s.RevisionWrite(
                    base_version=draft.base_version,
                    known_on=draft.known_on,
                    note=f"人工确认变更草稿 {draft.id}",
                    data=data,
                ),
            )
            draft.revision_id = revision.id
            row.status = "completed"
            row.payload = self._event(
                {**row.payload, "draft": draft.model_dump(mode="json")},
                "人工确认",
                "completed",
                "已保存新输入版本；原预测保持不变，请选择新时点重新测算",
            )
            result = self._view(row)
            remember(db, key, operation, body, result)
            return result

    def process_next(self) -> bool:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            if self.configuring:
                return False
            row = db.scalar(
                select(AgentTaskRow)
                .where(AgentTaskRow.status == "queued")
                .order_by(AgentTaskRow.created_at)
                .limit(1)
            )
            if row is None:
                return False
            row.status = "running"
            task_id = row.id
        config: RunnableConfig = {"configurable": {"thread_id": task_id}, "recursion_limit": 12}
        try:
            # Do not send local business state to an optional tracing service.
            with tracing_context(enabled=False):
                checkpoint = self.graph.get_state(config)
                payload = self._payload(task_id)
                if not checkpoint.values:
                    result = self.graph.invoke({"task_id": task_id, "round": 0}, config)
                elif any(task.interrupts for task in checkpoint.tasks):
                    reply = payload.get("pending_reply")
                    waiting_token = next(
                        item.value.get("token")
                        for task in checkpoint.tasks
                        for item in task.interrupts
                    )
                    if reply is None or reply["token"] != waiting_token:
                        self._update(task_id, {}, status="awaiting_reply")
                        return True
                    result = self.graph.invoke(Command(resume=reply["reply"]), config)
                elif checkpoint.next:
                    result = self.graph.invoke(None, config)
                else:
                    result = checkpoint.values
            if result.get("__interrupt__"):
                self._update(
                    task_id,
                    {"pending_reply": None},
                    status="awaiting_reply",
                    event=(
                        "等待澄清",
                        "awaiting_reply",
                        "问题已保存，关闭页面后仍可继续",
                    ),
                )
            else:
                draft = self._payload(task_id).get("draft")
                self._update(
                    task_id,
                    {"pending_reply": None},
                    status="awaiting_confirmation"
                    if draft and not draft.get("revision_id")
                    else "completed",
                    event=(
                        "问数完成",
                        "completed",
                        "草稿已保存，等待人工确认"
                        if draft
                        else "答案来自原运行，未修改业务输入或预测",
                    ),
                )
        except ModelFailure as exc:
            self._update(
                task_id,
                {"error": str(exc)},
                status="failed",
                event=(
                    "问数失败",
                    "failed",
                    "保留原运行及检查点，可在预算内重试",
                ),
            )
        except Exception:
            logging.getLogger(__name__).error("Agent task %s failed unexpectedly", task_id)
            self._update(
                task_id,
                {"error": "问数执行失败，请凭任务编号检查服务；原预测不受影响"},
                status="failed",
                event=("问数失败", "failed", "内部错误，保留检查点"),
            )
        return True
