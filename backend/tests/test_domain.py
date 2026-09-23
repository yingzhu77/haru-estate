from datetime import date

import pytest

from app.domain import D, aggregate, allocate, calculate, month_range, shift
from app.schemas import Assumptions, Cost, Dataset, Overrides, Payment, Phase
from app.seeds import demo_dataset

ORIGIN = date(2026, 8, 31)


def tiny() -> Dataset:
    return Dataset(
        phases=[
            Phase(
                id="p",
                name="样例",
                area="10",
                price="1000",
                sales_start="2026-09",
                sales_months=1,
                delivery_month="2026-09",
            )
        ],
        costs=[
            Cost(
                id=category,
                phase_id="p",
                category=category,
                amount=value,
                incurred_month="2026-09",
                known_on=date(2026, 1, 1),
                payments=[Payment(month="2026-09", amount=value)],
            )
            for category, value in (("land", "2000"), ("construction", "4000"), ("other", "1000"))
        ],
        assumptions=Assumptions(
            opening_month="2026-09",
            monthly_overhead="0",
            marketing_rate="0",
            tax_rate="0",
            loan_limit="0",
            annual_interest_rate="0",
        ),
    )


def test_independently_checked_small_example() -> None:
    result = calculate(tiny(), ORIGIN, ORIGIN)
    september = next(m for m in result.months if m.month == "2026-09")
    assert (september.revenue, september.cogs, september.profit) == (
        "10000.00",
        "7000.00",
        "3000.00",
    )
    assert september.collections == "3000.00"
    assert september.uncovered_gap == "4000.00"
    assert result.summary.twelve_month_profit == "3000.00"
    assert result.months[-1].cash_balance == "3000.00"
    assert result.target_months == month_range("2026-09", "2027-08")


def test_collection_delay_does_not_move_revenue() -> None:
    data = tiny()
    original = calculate(data, ORIGIN, ORIGIN)
    changed = calculate(data, ORIGIN, ORIGIN, overrides=Overrides(collection_delay=2))
    assert [(m.month, m.revenue) for m in original.months] == [
        (m.month, m.revenue) for m in changed.months
    ]
    assert original.summary.twelve_month_profit == changed.summary.twelve_month_profit
    assert next(m for m in changed.months if m.month == "2027-02").collections == "7000.00"


def test_delivery_moves_matching_cost_and_preserves_tail() -> None:
    result = calculate(tiny(), ORIGIN, ORIGIN, overrides=Overrides(delivery_delays={"p": 13}))
    assert result.summary.twelve_month_profit == "0.00"
    october = next(m for m in result.months if m.month == "2027-10")
    assert (october.revenue, october.cogs, october.profit) == ("10000.00", "7000.00", "3000.00")
    assert result.summary.lifecycle_profit == "3000.00"


def test_land_installments_only_change_payment_timing() -> None:
    data = tiny()
    data.costs[0].payments = [
        Payment(month="2026-09", amount="1000"),
        Payment(month="2026-12", amount="1000"),
    ]
    result = calculate(data, ORIGIN, ORIGIN)
    assert result.summary.twelve_month_profit == "3000.00"
    assert sum(D(m.payments) for m in result.months) == 7000


def test_historical_and_signed_amounts_survive_future_overrides() -> None:
    data = demo_dataset()
    before = calculate(data, ORIGIN, ORIGIN)
    after = calculate(
        data, ORIGIN, ORIGIN, overrides=Overrides(price_change="0.1", remaining_cost_change="0.1")
    )
    assert [m for m in before.months if m.period == "actual"] == [
        m for m in after.months if m.period == "actual"
    ]
    assert [
        s for s in before.sources if s.record_id.startswith("contract:") and s.metric == "revenue"
    ] == [s for s in after.sources if s.record_id.startswith("contract:") and s.metric == "revenue"]


def test_missing_cost_is_not_zero() -> None:
    data = tiny()
    data.costs = data.costs[:2]
    with pytest.raises(ValueError, match="缺少"):
        calculate(data, ORIGIN, ORIGIN)


def test_late_known_cost_is_not_in_past_forecast() -> None:
    data = tiny()
    data.costs[1].known_on = date(2026, 9, 1)
    with pytest.raises(ValueError, match="缺少"):
        calculate(data, ORIGIN, ORIGIN)


def test_aggregate_money_and_no_cash_pooling() -> None:
    first = calculate(tiny(), ORIGIN, ORIGIN)
    rich = tiny()
    rich.assumptions.opening_cash = "1000000"
    second = calculate(rich, ORIGIN, ORIGIN)
    total = aggregate([first, second])
    assert total.summary.twelve_month_profit == "6000.00"
    assert total.summary.max_funding_gap == "4000.00"
    assert next(m for m in total.months if m.month == "2026-09").cash_balance == "992000.00"
    assert total.summary.range_low == str(
        (D(first.summary.range_low) + D(second.summary.range_low)).quantize(D(".01"))
    )


def test_repeated_calculations_and_allocation() -> None:
    assert calculate(tiny(), ORIGIN, ORIGIN) == calculate(tiny(), ORIGIN, ORIGIN)
    assert allocate(D("1.00"), [D(1)] * 3) == [D(".33"), D(".33"), D(".34")]
    assert shift("2026-12", 1) == "2027-01"
    assert shift("2026-01", -1) == "2025-12"


def test_demo_monthly_profit_and_cash_reconcile() -> None:
    result = calculate(demo_dataset(), ORIGIN, ORIGIN)
    assert sum(D(m.profit) for m in result.months if m.month in result.target_months) == D(
        result.summary.twelve_month_profit
    )
    cash = D("10000000")
    for row in result.months:
        cash += D(row.net_cash_flow)
        assert cash == D(row.cash_balance)
        assert D(row.profit) == D(row.revenue) - D(row.cogs) - D(row.expenses) - D(row.taxes) - D(
            row.interest
        )
