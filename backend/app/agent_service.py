"""One bounded read-only LangGraph, on the application's existing job executor."""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict
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
        builder.add_edge(START, "understand")
        builder.add_conditional_edges(
            "understand",
            self._route,
            {
                "clarify": "clarify",
                "query": "query",
            },
        )
        builder.add_edge("clarify", "understand")
        builder.add_edge("query", END)
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

    @staticmethod
    def _view(row: AgentTaskRow) -> s.AgentTask:
        return s.AgentTask.model_validate(
            {
                **{
                    key: value
                    for key, value in row.payload.items()
                    if key in s.AgentTask.model_fields
                },
                "status": row.status,
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

    def list(self, run_id: str) -> list[s.AgentTask]:
        self.application.run(run_id)
        with Session(self.application.engine) as db:
            return [
                self._view(row)
                for row in db.scalars(
                    select(AgentTaskRow)
                    .where(AgentTaskRow.run_id == run_id)
                    .order_by(AgentTaskRow.created_at.desc())
                    .limit(20)
                )
            ]

    def create(self, body: s.AgentCreate, key: str) -> s.AgentTask:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
            cached = replay(db, key, "agent-create", body)
            if cached is not None:
                return s.AgentTask.model_validate(cached)
            if not self.model.configured:
                raise HTTPException(503, "DeepSeek 未配置；请在服务端设置密钥及模型名称")
            run = self.application.run(body.run_id)
            if run.status != "completed" or run.result is None:
                raise HTTPException(409, "只能查询已完成的预测运行")
            task = s.AgentTask(
                id=str(uuid4()),
                run_id=run.id,
                question=body.question,
                status="queued",
                created_at=timestamp(),
                model=self.model.model,
                provider=self.model.provider,
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
            operation = f"agent-reply:{task_id}"
            cached = replay(db, key, operation, body)
            if cached is not None:
                return s.AgentTask.model_validate(cached)
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
            row = self._row(db, task_id)
            if row.status in {"queued", "running", "completed", "awaiting_reply"}:
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
            },
        )
        # Validate even injected adapters: the tool boundary trusts no model implementation.
        plan = s.AgentPlan.model_validate(plan.model_dump())
        changes: dict[str, Any] = {"plans": {**payload["plans"], round_key: plan.model_dump()}}
        if plan.action == "clarify":
            if payload["calls"] + 1 >= 3:
                raise ModelFailure("三次解析后仍需澄清，请明确指标和期间后新建任务")
            changes.update(clarification=plan.clarification, reply_token=str(uuid4()))
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

    def process_next(self) -> bool:
        with self.application.lock, Session(self.application.engine) as db, db.begin():
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
                self._update(
                    task_id,
                    {"pending_reply": None},
                    status="completed",
                    event=(
                        "问数完成",
                        "completed",
                        "答案来自原运行，未修改业务输入或预测",
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
