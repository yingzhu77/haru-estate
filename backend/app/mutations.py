"""Retry receipts share the same transaction as the corresponding business write."""

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.storage import MutationRow


def digest(body: BaseModel) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def replay(db: Session, key: str | None, operation: str, body: BaseModel) -> dict[str, Any] | None:
    if key is None:
        return None
    receipt = db.get(MutationRow, key)
    if receipt is None:
        return None
    if receipt.operation != operation or receipt.request_hash != digest(body):
        raise HTTPException(409, "幂等键已用于不同请求，请核对操作内容")
    return receipt.response


def remember(
    db: Session, key: str | None, operation: str, body: BaseModel, response: BaseModel
) -> None:
    if key is not None:
        db.add(
            MutationRow(
                key=key,
                operation=operation,
                request_hash=digest(body),
                response=response.model_dump(mode="json"),
            )
        )
