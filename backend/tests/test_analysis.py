import pytest
from test_domain import ORIGIN, tiny

from app.domain import D, calculate
from app.domain_analysis import compare_results
from app.schemas import Overrides, Payment


def test_independent_sensitivity_profit_and_funding_gap() -> None:
    result = calculate(tiny(), ORIGIN, ORIGIN)
    price, cost, delay = result.sensitivity
    assert (price.profit, price.delta, price.max_funding_gap, price.funding_gap_delta) == (
        "3500.00",
        "500.00",
        "3850.00",
        "-150.00",
    )
    assert (cost.profit, cost.delta, cost.max_funding_gap, cost.funding_gap_delta) == (
        "2650.00",
        "-350.00",
        "4350.00",
        "350.00",
    )
    assert delay.delta == "0.00"  # No overhead: receipt timing alone is not revenue.
    assert delay.funding_gap_delta == "0.00"  # Same peak can last longer.


def test_delay_exposes_new_cash_deficit_without_profit_change() -> None:
    data = tiny()
    data.assumptions.collection_lag = 0
    result = calculate(data, ORIGIN, ORIGIN)
    assert result.summary.max_funding_gap == "0.00"
    delay = result.sensitivity[2]
    assert delay.profit == "3000.00" and delay.delta == "0.00"
    assert delay.max_funding_gap == "4000.00" and delay.funding_gap_delta == "4000.00"


def test_unavailable_sensitivity_does_not_invalidate_valid_base() -> None:
    result = calculate(
        tiny(),
        ORIGIN,
        ORIGIN,
        overrides=Overrides(
            price_change="2",
            remaining_cost_change="2",
            collection_delay=24,
        ),
    )
    assert result.summary.twelve_month_profit == "9000.00"
    assert all(
        row.error and row.profit is None and row.max_funding_gap is None
        for row in result.sensitivity
    )


def test_profit_bridge_uses_signed_components_and_common_months() -> None:
    before = calculate(tiny(), ORIGIN, ORIGIN)
    after = calculate(
        tiny(),
        ORIGIN,
        ORIGIN,
        overrides=Overrides(
            price_change="0.1",
            remaining_cost_change="0.1",
        ),
    )
    rows, total = compare_results(before, after)
    assert (rows[0].revenue, rows[0].cogs, rows[0].profit) == ("1000.00", "-700.00", "300.00")
    assert total.profit == "300.00"
    assert all(
        sum(D(getattr(row, key)) for key in ("revenue", "cogs", "expenses", "taxes", "interest"))
        == D(row.profit)
        for row in rows
    )
    after.target_months = after.target_months[1:]
    assert compare_results(before, after)[1].profit == "0.00"


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("unit", "万元"),
        ("profit_basis", "其他口径"),
        ("rule_version", "other"),
    ],
)
def test_incompatible_comparisons_rejected(field: str, value: str) -> None:
    before = calculate(tiny(), ORIGIN, ORIGIN)
    after = before.model_copy(update={field: value})
    with pytest.raises(ValueError, match="不能直接比较"):
        compare_results(before, after)


def test_comparison_rejects_missing_month_and_unreconciled_result() -> None:
    before = calculate(tiny(), ORIGIN, ORIGIN)
    after = before.model_copy(deep=True)
    after.months[0].profit = "0.00"
    with pytest.raises(ValueError, match="不一致"):
        compare_results(before, after)
    after.months = after.months[1:]
    with pytest.raises(ValueError, match="缺少"):
        compare_results(before, after)
    after.target_months = ["2030-01"]
    with pytest.raises(ValueError, match="没有共同"):
        compare_results(before, after)


def test_installment_tail_keeps_cash_and_cost_totals_separate() -> None:
    data = tiny()
    data.costs[0].payments = [
        Payment(month="2026-09", amount="1"),
        Payment(month="2028-01", amount="1999"),
    ]
    result = calculate(data, ORIGIN, ORIGIN)
    assert next(row for row in result.months if row.month == "2028-01").payments == "1999.00"
    assert all(D(row.payments) == 0 for row in result.months if row.month > "2028-01")
    assert result.summary.twelve_month_profit == "3000.00"
    assert sum(D(row.payments) for row in result.months) == 7000
    assert sum(D(row.cogs) for row in result.months) == 7000
