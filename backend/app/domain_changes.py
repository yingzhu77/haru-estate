"""Whitelist changes to a copied input; no I/O and no model arithmetic."""

from datetime import date
from decimal import Decimal

from app.domain import money, shift
from app.schemas import Dataset, PhaseChange


def apply_change(data: Dataset, change: PhaseChange, known_on: date) -> tuple[Dataset, str, str]:
    copied = data.model_copy(deep=True)
    phase = next((p for p in copied.phases if p.id == change.phase_id), None)
    if phase is None:
        raise ValueError("变更分期不属于绑定项目")
    if known_on < phase.known_on:
        raise ValueError("变更获知日期不能早于原分期资料")
    if phase.delivery_month <= data.actual_closed_through:
        raise ValueError("不能通过草稿修改已交付历史分期")
    value = Decimal(change.value)
    if change.field == "price_change":
        if not Decimal("-0.9") <= value <= Decimal("2"):
            raise ValueError("未售售价调整须在-90%至200%之间")
        before = phase.price
        phase.price = money(Decimal(before) * (1 + value))
        after = phase.price
    else:
        if value != value.to_integral_value() or not 0 <= value <= 36:
            raise ValueError("交付延期须为0至36个整月")
        before = phase.delivery_month
        phase.delivery_month = shift(before, int(value))
        after = phase.delivery_month
    if before == after or (change.field == "price_change" and Decimal(before) == Decimal(after)):
        raise ValueError("调整没有改变参数，请重新说明")
    phase.known_on = known_on
    return Dataset.model_validate(copied.model_dump()), before, after
