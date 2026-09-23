"""Explicit synthetic examples, unrelated to any company's operating data."""

from datetime import date
from typing import Literal, cast

from app.domain import D, money, shift
from app.schemas import Actual, Assumptions, Contract, Cost, Dataset, Metric, Payment, Phase


def demo_dataset(variant: int = 0) -> Dataset:
    known = date(2026, 1, 1)
    phases = [
        Phase(
            id=f"phase-{i}",
            name=f"{i}期住宅",
            area=str(10000 + variant * 2000),
            price=str(12000 + variant * 1000),
            sales_start=shift(month, variant * 2),
            sales_months=6,
            delivery_month=shift(delivery, variant * 3),
            known_on=known,
        )
        for i, month, delivery in ((1, "2026-09", "2026-09"), (2, "2027-01", "2027-06"))
    ]
    costs: list[Cost] = []
    contracts: list[Contract] = []
    actuals: list[Actual] = []
    for phase in phases:
        for category, amount, incurred, payment in (
            ("land", "20000000", "2026-02", "2026-02"),
            (
                "construction",
                "35000000",
                "2026-10" if phase.id == "phase-1" else "2027-04",
                "2026-12" if phase.id == "phase-1" else "2027-07",
            ),
            ("other", "5000000", "2026-08", "2026-09"),
        ):
            value = money(D(amount) * (1 + D(variant) / 5))
            cost_id = f"{phase.id}-{category}"
            costs.append(
                Cost(
                    id=cost_id,
                    phase_id=phase.id,
                    category=cast(Literal["land", "construction", "other"], category),
                    amount=value,
                    incurred_month=incurred,
                    known_on=known,
                    payments=[
                        Payment(
                            month=shift(payment, variant * 2) if payment > "2026-08" else payment,
                            amount=value,
                        )
                    ],
                )
            )
            if incurred <= "2026-08":
                actuals.append(
                    Actual(
                        id=f"actual:{cost_id}:incurred",
                        phase_id=phase.id,
                        month=incurred,
                        known_on=date.fromisoformat(incurred + "-28"),
                        metric="development",
                        amount=value,
                    )
                )
            if payment <= "2026-08":
                actuals.append(
                    Actual(
                        id=f"actual:{cost_id}:paid",
                        phase_id=phase.id,
                        month=payment,
                        known_on=date.fromisoformat(payment + "-28"),
                        metric="payments",
                        amount=value,
                    )
                )
        contract_amount = D(phase.price) * 2000
        contract_id = f"contract:{phase.id}"
        contracts.append(
            Contract(
                id=contract_id,
                phase_id=phase.id,
                sale_month="2026-06",
                area="2000",
                amount=money(contract_amount),
                known_on=date(2026, 6, 1),
                collections=[
                    Payment(month="2026-06", amount=money(contract_amount * D(".3"))),
                    Payment(
                        month=shift("2026-10", variant * 2), amount=money(contract_amount * D(".7"))
                    ),
                ],
            )
        )
        for metric, contract_value in (
            ("sales", contract_amount),
            ("collections", contract_amount * D(".3")),
        ):
            actuals.append(
                Actual(
                    id=f"{contract_id}:{metric}",
                    phase_id=phase.id,
                    month="2026-06",
                    known_on=date(2026, 6, 30),
                    metric=cast(Metric, metric),
                    amount=money(contract_value),
                    contract_id=contract_id,
                )
            )
    actuals.append(
        Actual(
            id="loan:actual",
            phase_id=phases[0].id,
            month="2026-01",
            known_on=known,
            metric="borrowing",
            amount="40000000",
        )
    )
    for index in range(8):
        month = shift("2026-01", index)
        for metric, amount in (
            ("expenses", "100000"),
            ("expense_payments", "100000"),
            ("interest", "166666.67"),
        ):
            actuals.append(
                Actual(
                    id=f"actual:{metric}:{month}",
                    phase_id=phases[0].id,
                    month=month,
                    known_on=date.fromisoformat(month + "-28"),
                    metric=cast(Metric, metric),
                    amount=amount,
                )
            )
    assumptions = Assumptions(
        opening_cash="10000000",
        monthly_overhead="100000",
        loan_limit="60000000",
        loan_repayments=[Payment(month="2027-12", amount="40000000")],
    )
    return Dataset(
        phases=phases, contracts=contracts, costs=costs, actuals=actuals, assumptions=assumptions
    )
