from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app import schemas as s


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from app.application import service

    service.start()
    yield
    service.stop()


app = FastAPI(title="HaruEstate", version="0.1.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    from uuid import uuid4

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "CONFLICT" if exc.status_code == 409 else "REQUEST_ERROR",
            "message": str(exc.detail),
            "request_id": str(uuid4()),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    from uuid import uuid4

    messages = "; ".join(str(e["msg"]) for e in exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": messages,
            "request_id": str(uuid4()),
        },
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    from app.application import service

    service.health()
    return {"status": "ok", "ai": "not_connected"}


@app.get("/api/v1/projects", response_model=list[s.Project])
def projects() -> object:
    from app.application import service

    return service.projects()


@app.post("/api/v1/projects", response_model=s.Project)
def create_project(body: s.ProjectCreate) -> object:
    from app.application import service

    return service.create_project(body)


@app.patch("/api/v1/projects/{project_id}", response_model=s.Project)
def patch_project(project_id: str, body: s.ProjectPatch) -> object:
    from app.application import service

    return service.patch_project(project_id, body)


@app.get("/api/v1/projects/{project_id}/input", response_model=s.Revision)
def project_input(project_id: str, revision_id: str | None = None) -> object:
    from app.application import service

    return service.revision(project_id, revision_id)


@app.post("/api/v1/projects/{project_id}/revisions", response_model=s.Revision)
def revise(project_id: str, body: s.RevisionWrite) -> object:
    from app.application import service

    return service.revise(project_id, body)


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
def confirm_import(project_id: str, body: s.ImportConfirm) -> object:
    from app.application import service

    return service.confirm_import(project_id, body)


@app.post("/api/v1/runs", response_model=s.Run, status_code=202)
def create_run(body: s.RunCreate, idempotency_key: str = Header(min_length=8)) -> object:
    from app.application import service

    return service.create_run(body, idempotency_key)


@app.get("/api/v1/runs", response_model=list[s.Run])
def runs(project_id: str | None = None, scope_ids: str | None = None) -> object:
    from app.application import service

    return service.runs(project_id, scope_ids=scope_ids)


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
    run_id: str, metric: str = Query(default="profit"), month: str | None = None
) -> object:
    from app.application import service

    return service.evidence(run_id, metric, month)
