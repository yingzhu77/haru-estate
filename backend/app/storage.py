from pathlib import Path
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class RevisionRow(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    version: Mapped[int]
    known_on: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str]
    created_at: Mapped[str]
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)
    request_hash: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MutationRow(Base):
    __tablename__ = "mutation_receipts"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    operation: Mapped[str]
    request_hash: Mapped[str]
    response: Mapped[dict[str, Any]] = mapped_column(JSON)


class AgentTaskRow(Base):
    __tablename__ = "agent_tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


def make_engine(path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 15}
    )

    @event.listens_for(engine, "connect")
    def configure(connection: Any, _: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    return engine
