"""Shared scenario factors and a read-only view of effective draft parameters."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.schemas import EffectiveParameters, EffectivePhase, Overrides, Revision, Scenario

SCENARIO_FACTORS = {
    "base": (Decimal("1"), Decimal("1")),
    "optimistic": (Decimal("1.05"), Decimal("0.97")),
    "prudent": (Decimal("0.95"), Decimal("1.05")),
}


def factors(scenario: str, overrides: Overrides) -> tuple[Decimal, Decimal]:
    if scenario not in SCENARIO_FACTORS:
        raise ValueError("未知情景")
    price, cost = SCENARIO_FACTORS[scenario]
    return (1 + Decimal(overrides.price_change)) * price, (
        1 + Decimal(overrides.remaining_cost_change)
    ) * cost


def effective_parameters(
    revision: Revision, name: str, cutoff: date, scenario: Scenario, overrides: Overrides
) -> EffectiveParameters:
    from app.domain import money, shift

    data = revision.data
    price_factor, cost_factor = factors(scenario, overrides)
    scenario_price, scenario_cost = SCENARIO_FACTORS[scenario]
    phases = [p for p in data.phases if p.known_on <= cutoff]
    if not set(overrides.delivery_delays).issubset(p.id for p in phases):
        raise ValueError("延期变更引用了截止时点之外的分期")
    if any(
        overrides.delivery_delays.get(p.id, 0) and p.delivery_month <= data.actual_closed_through
        for p in phases
    ):
        raise ValueError("不能延后已交付历史分期")
    costs = [c for c in data.costs if c.known_on <= cutoff and c.phase_id in {p.id for p in phases}]
    future = [c for c in costs if c.incurred_month > data.actual_closed_through]
    warnings = []
    complete_costs = bool(phases) and all(
        {c.category for c in costs if c.phase_id == p.id} == {"land", "construction", "other"}
        for p in phases
    )
    if not complete_costs:
        warnings.append("成本资料未齐，暂不显示完整成本合计；正式测算仍需通过数据检查。")
    if not phases:
        warnings.append("截止时点没有可用分期，请先补齐计划。")
    return EffectiveParameters(
        project_id=revision.project_id,
        project_name=name,
        revision_id=revision.id,
        version=revision.version,
        scenario=scenario,
        scenario_price_percent=money((scenario_price - 1) * 100),
        scenario_cost_percent=money((scenario_cost - 1) * 100),
        price_percent=money((price_factor - 1) * 100),
        cost_percent=money((cost_factor - 1) * 100),
        future_cost_before=money(sum((Decimal(c.amount) for c in future), Decimal(0)))
        if complete_costs
        else None,
        future_cost_after=money(
            sum(
                (
                    (Decimal(c.amount) * cost_factor).quantize(
                        Decimal(".01"), rounding=ROUND_HALF_UP
                    )
                    for c in future
                ),
                Decimal(0),
            )
        )
        if complete_costs
        else None,
        collection_lag=data.assumptions.collection_lag + overrides.collection_delay,
        extra_collection_delay=overrides.collection_delay,
        phases=[
            EffectivePhase(
                id=p.id,
                name=p.name,
                original_price=p.price,
                effective_price=money(Decimal(p.price) * price_factor),
                original_delivery=p.delivery_month,
                effective_delivery=shift(p.delivery_month, overrides.delivery_delays.get(p.id, 0)),
            )
            for p in phases
        ],
        warnings=warnings,
    )
