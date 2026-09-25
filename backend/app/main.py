import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, Header, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app import schemas as s


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from app.application import service

    service.start()
    yield
    service.stop()


app = FastAPI(
    title="HaruEstate",
    version="0.1.0",
    lifespan=lifespan,
    responses={status: {"model": s.ApiError} for status in (400, 404, 409, 413, 422, 500)},
)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": (
                "CONFLICT"
                if exc.status_code == 409
                else "VALIDATION_ERROR"
                if exc.status_code == 422
                else "REQUEST_ERROR"
            ),
            "message": str(exc.detail),
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = (
        "配置格式无效，请检查密钥与模型名称。"
        if request.url.path == "/api/v1/model-config"
        else "; ".join(str(e["msg"]) for e in exc.errors())
    )
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": messages,
            "request_id": request.state.request_id,
        },
    )


@app.middleware("http")
async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request.state.request_id = str(uuid4())
    configuration = request.url.path.rstrip("/") == "/api/v1/model-config"
    if configuration:
        from app.application import service
        from app.config_security import allowed

        if not allowed(request, service.agent.configuration_token):
            return JSONResponse(
                status_code=403,
                content={
                    "code": "FORBIDDEN",
                    "message": "请从本机应用页面打开模型配置。",
                    "request_id": request.state.request_id,
                },
                headers={"Cache-Control": "no-store"},
            )
    try:
        response = await call_next(request)
    except Exception:
        if configuration:
            logging.getLogger(__name__).error(
                "Configuration request failed: %s", request.state.request_id
            )
        else:
            logging.getLogger(__name__).exception("Request failed: %s", request.state.request_id)
        response = JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务执行失败，请凭请求编号核查后重试",
                "request_id": request.state.request_id,
            },
        )
    response.headers["X-Request-ID"] = request.state.request_id
    if configuration:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/model-config", response_model=s.ModelConfigurationStatus)
def model_configuration() -> object:
    from app.application import service

    return service.agent.configuration_status()


@app.put("/api/v1/model-config", response_model=s.ModelConfigurationStatus)
def configure_model(body: s.ModelConfiguration) -> object:
    from app.application import service

    return service.agent.configure(body)


@app.delete("/api/v1/model-config", response_model=s.ModelConfigurationStatus)
def clear_model() -> object:
    from app.application import service

    return service.agent.configure(None)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    from app.application import service

    service.health()
    return {
        "status": "ok",
        "ai": "configured" if service.agent.status().configured else "not_connected",
    }


@app.get("/api/v1/agent/status", response_model=s.AgentStatus)
def agent_status() -> object:
    from app.application import service

    return service.agent.status()


@app.post("/api/v1/agent/tasks", response_model=s.AgentTask, status_code=202)
def agent_create(
    body: s.AgentCreate,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.agent.create(body, idempotency_key)


@app.get("/api/v1/agent/tasks", response_model=list[s.AgentTask])
def agent_tasks(run_id: str, offset: int = Query(0, ge=0)) -> object:
    from app.application import service

    return service.agent.list(run_id, offset)


@app.get("/api/v1/agent/tasks/{task_id}", response_model=s.AgentTask)
def agent_task(task_id: str) -> object:
    from app.application import service

    return service.agent.get(task_id)


@app.post("/api/v1/agent/tasks/{task_id}/reply", response_model=s.AgentTask, status_code=202)
def agent_reply(
    task_id: str,
    body: s.AgentReply,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.agent.reply(task_id, body, idempotency_key)


@app.post("/api/v1/agent/tasks/{task_id}/resume", response_model=s.AgentTask, status_code=202)
def agent_resume(task_id: str) -> object:
    from app.application import service

    return service.agent.resume(task_id)


@app.get("/api/v1/projects", response_model=list[s.Project])
def projects() -> object:
    from app.application import service

    return service.projects()


@app.post("/api/v1/agent/tasks/{task_id}/confirm", response_model=s.AgentTask)
def agent_confirm(
    task_id: str,
    body: s.ChangeConfirm,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.agent.confirm(task_id, body, idempotency_key)


@app.post("/api/v1/projects", response_model=s.Project)
def create_project(
    body: s.ProjectCreate, idempotency_key: str = Header(min_length=8, max_length=128)
) -> object:
    from app.application import service

    return service.create_project(body, key=idempotency_key)


@app.patch("/api/v1/projects/{project_id}", response_model=s.Project)
def patch_project(
    project_id: str,
    body: s.ProjectPatch,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.patch_project(project_id, body, key=idempotency_key)


@app.get("/api/v1/projects/{project_id}/input", response_model=s.Revision)
def project_input(project_id: str, revision_id: str | None = None) -> object:
    from app.application import service

    return service.revision(project_id, revision_id)


@app.post("/api/v1/projects/{project_id}/revisions", response_model=s.Revision)
def revise(
    project_id: str,
    body: s.RevisionWrite,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.revise(project_id, body, key=idempotency_key)


@app.get("/api/v1/projects/{project_id}/revisions", response_model=s.RevisionPage)
def revisions(
    project_id: str, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)
) -> object:
    from app.application import service

    return service.revisions(project_id, offset=offset, limit=limit)


@app.get("/api/v1/projects/{project_id}/revisions/compare", response_model=s.RevisionComparison)
def revision_compare(project_id: str, left_id: str, right_id: str) -> object:
    from app.application import service

    return service.compare_revisions(project_id, left_id, right_id)


@app.post("/api/v1/projects/{project_id}/imports/preview", response_model=s.ImportPreview)
async def preview_import(project_id: str, file: UploadFile) -> object:
    from app.application import service

    data = await file.read(2_000_001)
    return service.preview_import(project_id, data)


@app.post("/api/v1/projects/{project_id}/imports/confirm", response_model=s.Revision)
def confirm_import(
    project_id: str,
    body: s.ImportConfirm,
    idempotency_key: str = Header(min_length=8, max_length=128),
) -> object:
    from app.application import service

    return service.confirm_import(project_id, body, key=idempotency_key)


@app.post("/api/v1/runs", response_model=s.Run, status_code=202)
def create_run(
    body: s.RunCreate, idempotency_key: str = Header(min_length=8, max_length=128)
) -> object:
    from app.application import service

    return service.create_run(body, idempotency_key)


@app.get("/api/v1/runs", response_model=list[s.Run])
def runs(
    project_id: str | None = None,
    scope_ids: str | None = Query(None, max_length=4000),
    kind: str | None = Query(None, pattern="^(project|portfolio)$"),
) -> object:
    from app.application import service

    return service.run_page(project_id, scope_ids=scope_ids, kind=kind, limit=100).items


@app.post("/api/v1/parameters/preview", response_model=list[s.EffectiveParameters])
def parameter_preview(body: s.RunCreate) -> object:
    from app.application import service

    return service.parameter_preview(body)


@app.get("/api/v1/runs/page", response_model=s.RunPage)
def run_page(
    project_id: str | None = None,
    kind: str | None = Query(None, pattern="^(project|portfolio)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> object:
    from app.application import service

    return service.run_page(project_id, kind=kind, offset=offset, limit=limit)


@app.get("/api/v1/compare", response_model=s.Comparison)
def compare(left_id: str, right_id: str) -> object:
    from app.application import service

    return service.compare(left_id, right_id)


@app.get("/api/v1/runs/{run_id}", response_model=s.Run)
def run(run_id: str) -> object:
    from app.application import service

    return service.run(run_id)


@app.post("/api/v1/runs/{run_id}/resume", response_model=s.Run)
def resume(run_id: str) -> object:
    from app.application import service

    return service.resume(run_id)


@app.get("/api/v1/runs/{run_id}/evidence", response_model=s.Evidence)
def evidence(
    run_id: str,
    metric: str = Query(default="profit"),
    month: s.Month | None = None,
    months: Annotated[list[s.Month] | None, Query(max_length=240)] = None,
) -> object:
    from app.application import service

    return service.evidence(run_id, metric, month, months)
