"""Deterministic profit reconciliation, not a causal or model-generated explanation."""

from app.domain import ZERO, D, money
from app.schemas import ForecastResult, ProfitBridge

COMPONENT_SIGNS = {"revenue": 1, "cogs": -1, "expenses": -1, "taxes": -1, "interest": -1}


def compare_results(
    left: ForecastResult, right: ForecastResult
) -> tuple[list[ProfitBridge], ProfitBridge]:
    for field in ("currency", "unit", "profit_basis", "rule_version"):
        if getattr(left, field) != getattr(right, field):
            raise ValueError("币种、单位、利润口径或计算规则不同，不能直接比较")
    months = sorted(set(left.target_months) & set(right.target_months))
    if not months:
        raise ValueError("两次预测没有共同目标月份")
    before = {row.month: row for row in left.months}
    after = {row.month: row for row in right.months}
    bridge = []
    for month in months:
        if month not in before or month not in after:
            raise ValueError("比较结果缺少目标月份，不能补零")
        components = {
            field: (D(getattr(after[month], field)) - D(getattr(before[month], field))) * sign
            for field, sign in COMPONENT_SIGNS.items()
        }
        delta = D(after[month].profit) - D(before[month].profit)
        if sum(components.values(), ZERO) != delta:
            raise ValueError("利润变化与组成项不一致，请核查原运行")
        bridge.append(
            ProfitBridge(
                month=month,
                profit=money(delta),
                **{key: money(value + ZERO) for key, value in components.items()},
            )
        )
    total = ProfitBridge(
        month="共同月份合计",
        **{
            field: money(sum((D(getattr(row, field)) for row in bridge), ZERO))
            for field in [*COMPONENT_SIGNS, "profit"]
        },
    )
    return bridge, total
