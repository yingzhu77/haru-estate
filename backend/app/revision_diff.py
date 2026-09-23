"""Structural input differences; record IDs are stable even when lists are reordered."""

import json
from typing import Any, Literal

from app.schemas import Dataset, FieldChange


def dataset_changes(left: Dataset, right: Dataset) -> list[FieldChange]:
    changes: list[FieldChange] = []

    def display(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def walk(
        before: Any,
        after: Any,
        path: str,
        *,
        kind: Literal["added", "removed", "changed"] = "changed",
    ) -> None:
        if before == after and kind == "changed":
            return
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(before.keys() | after.keys()):
                mode: Literal["added", "removed", "changed"] = (
                    "added" if key not in before else "removed" if key not in after else "changed"
                )
                walk(before.get(key), after.get(key), f"{path}/{key}", kind=mode)
        elif (
            isinstance(before, list)
            and isinstance(after, list)
            and all(isinstance(item, dict) and "id" in item for item in [*before, *after])
        ):
            walk({item["id"]: item for item in before}, {item["id"]: item for item in after}, path)
        else:
            changes.append(
                FieldChange(
                    path=path,
                    before=display(before),
                    after=display(after),
                    kind=kind,
                )
            )

    walk(left.model_dump(mode="json"), right.model_dump(mode="json"), "data")
    return changes
