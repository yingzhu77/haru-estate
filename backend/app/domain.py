"""Deterministic, illustrative residential-development model; no IO or model calls."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.schemas import (
    Dataset,
    ForecastResult,
    MonthResult,
    Overrides,
    Sensitivity,
    Source,
    Summary,
)

D = Decimal
ZERO = D("0")
CENT = D("0.01")
METRICS = (
    "sales",
    "collections",
    "revenue",
    "cogs",
    "development",
    "payments",
    "expenses",
    "expense_payments",
    "taxes",
    "tax_payments",
    "interest",
    "borrowing",
    "repayment",
)


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def shift(month: str, offset: int) -> str:
    year, number = map(int, month.split("-"))
    index = year * 12 + number - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    result = []
    while start <= end:
        result.append(start)
        start = shift(start, 1)
        if len(result) > 600:
            raise ValueError("演示模型最大跨度为600个月")
    return result


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    if not weights or sum(weights) <= 0:
        raise ValueError("分摊基数必须为正")
    base = sum(weights)
    values = [(total * w / base).quantize(CENT, rounding=ROUND_HALF_UP) for w in weights]
    values[-1] += total - sum(values)
    return values


def calculate(
    data: Dataset,
    origin: date,
    cutoff: date,
    scenario: str = "base",
    overrides: Overrides | None = None,
    *,
    analysis: bool = True,
) -> ForecastResult:
    override = overrides or Overrides()
    result = _calculate(data, origin, cutoff, scenario, override)
    if not analysis:
        return result
    totals = {scenario: result.summary.twelve_month_profit}
    for name in ("base", "optimistic", "prudent"):
        if name not in totals:
            totals[name] = _calculate(
                data, origin, cutoff, name, override
            ).summary.twelve_month_profit
    result.scenario_totals = totals
    result.summary.range_low = money(min(D(v) for v in totals.values()))
    result.summary.range_high = money(max(D(v) for v in totals.values()))
    for label, changes in (
        (
            "未售售价调整幅度 +5 个百分点",
            {"price_change": str(D(override.price_change) + D(".05"))},
        ),
        (
            "剩余成本调整幅度 +5 个百分点",
            {"remaining_cost_change": str(D(override.remaining_cost_change) + D(".05"))},
        ),
        ("回款延后 1 月", {"collection_delay": override.collection_delay + 1}),
    ):
        try:
            variant = Overrides.model_validate({**override.model_dump(), **changes})
            summary = _calculate(data, origin, cutoff, scenario, variant).summary
        except ValueError as exc:
            result.sensitivity.append(Sensitivity(label=label, error=str(exc)))
            continue
        result.sensitivity.append(
            Sensitivity(
                label=label,
                profit=summary.twelve_month_profit,
                delta=money(D(summary.twelve_month_profit) - D(result.summary.twelve_month_profit)),
                max_funding_gap=summary.max_funding_gap,
                funding_gap_delta=money(
                    D(summary.max_funding_gap) - D(result.summary.max_funding_gap)
                ),
            )
        )
    return result


def _calculate(
    data: Dataset,
    origin: date,
    cutoff: date,
    scenario: str,
    override: Overrides,
) -> ForecastResult:
    origin_month = origin.strftime("%Y-%m")
    closed = data.actual_closed_through
    if closed > origin_month:
        raise ValueError("已结账月份不能晚于预测基准月")
    phases = [p for p in data.phases if p.known_on <= cutoff]
    if not phases:
        raise ValueError("缺少截止时点已知的项目分期")
    phase_ids = {p.id for p in phases}
    if not set(override.delivery_delays).issubset(phase_ids):
        raise ValueError("延期变更引用了本次输入之外的分期")
    a = data.assumptions
    if any(D(v) < 0 for v in (a.monthly_overhead, a.loan_limit)):
        raise ValueError("费用与融资额度不能为负")
    price_factor = 1 + D(override.price_change)
    cost_factor = 1 + D(override.remaining_cost_change)
    if scenario == "optimistic":
        price_factor *= D("1.05")
        cost_factor *= D("0.97")
    elif scenario == "prudent":
        price_factor *= D("0.95")
        cost_factor *= D("1.05")
    ledger: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    sources: list[Source] = []
    warnings = ["模拟税费为收入比例计提；利息费用化；不含集团抵销、持股折算与复杂税务清算。"]

    def post(
        month: str,
        metric: str,
        amount: Decimal,
        record: str,
        phase: str,
        rule: str,
        description: str,
    ) -> None:
        value = D(money(amount))
        ledger[month][metric] += value
        sources.append(
            Source(
                record_id=record,
                phase_id=phase,
                month=month,
                metric=metric,
                amount=money(value),
                rule=rule,
                description=description,
            )
        )

    actuals = [r for r in data.actuals if r.known_on <= cutoff and r.month <= closed]
    if any(r.month < a.opening_month for r in actuals):
        raise ValueError("历史实际早于模型开始月份，请核对期初余额范围")
    missing_months = set(month_range(a.opening_month, closed)) - {r.month for r in actuals}
    if missing_months:
        raise ValueError("缺少已结账月份记录，不能补零：" + "、".join(sorted(missing_months)))
    sources.append(
        Source(
            record_id="assumptions:opening_cash",
            phase_id="",
            month=a.opening_month,
            metric="opening_cash",
            amount=a.opening_cash,
            rule="opening-balance",
            description="模型开始时的期初现金余额",
        )
    )
    for row in actuals:
        post(
            row.month,
            row.metric,
            D(row.amount),
            row.id,
            row.phase_id,
            "historical-actual",
            row.note or "模拟历史实际记录",
        )
    loan = sum(
        (
            D(r.amount) * (1 if r.metric == "borrowing" else -1)
            for r in actuals
            if r.metric in ("borrowing", "repayment")
        ),
        ZERO,
    )
    if loan < 0 or loan > D(a.loan_limit):
        raise ValueError("历史借款余额与融资额度不一致")
    end_receivables = ZERO
    operating_end = shift(closed, 1)
    for phase in phases:
        if D(phase.area) <= 0 or D(phase.price) <= 0:
            raise ValueError(f"{phase.name}的面积和售价须为正")
        costs = [c for c in data.costs if c.phase_id == phase.id and c.known_on <= cutoff]
        if not costs or {c.category for c in costs} != {"land", "construction", "other"}:
            raise ValueError(f"{phase.name}缺少土地、建安或其他开发成本；不能补零")
        historical_cost = sum((D(c.amount) for c in costs if c.incurred_month <= closed), ZERO)
        historical_payment = sum(
            (D(p.amount) for c in costs for p in c.payments if p.month <= closed), ZERO
        )
        for metric, expected in (
            ("development", historical_cost),
            ("payments", historical_payment),
        ):
            actual = sum(
                (D(r.amount) for r in actuals if r.phase_id == phase.id and r.metric == metric),
                ZERO,
            )
            if actual != expected:
                raise ValueError(f"{phase.name}历史{metric}实际与成本台账不勾稽，不能忽略差额")
        estimated_cost = ZERO
        for cost in costs:
            if D(cost.amount) < 0 or sum(D(p.amount) for p in cost.payments) != D(cost.amount):
                raise ValueError(f"成本{cost.id}金额或付款分配不一致")
            factor = cost_factor if cost.incurred_month > closed else D(1)
            amount = D(money(D(cost.amount) * factor))
            estimated_cost += amount
            if cost.incurred_month > closed:
                post(
                    cost.incurred_month,
                    "development",
                    amount,
                    cost.id,
                    phase.id,
                    "future-cost",
                    "未来开发投入；历史已发生金额保持不变",
                )
            historical_paid = sum((D(p.amount) for p in cost.payments if p.month <= closed), ZERO)
            remaining_payment = amount - historical_paid
            future_payments = [p for p in cost.payments if p.month > closed]
            if remaining_payment < 0 or (remaining_payment and not future_payments):
                raise ValueError(f"成本{cost.id}调整后金额不足已付款或缺少剩余付款安排")
            allocations = (
                allocate(remaining_payment, [D(p.amount) for p in future_payments])
                if remaining_payment
                else [ZERO] * len(future_payments)
            )
            for payment, value in zip(future_payments, allocations, strict=True):
                post(
                    payment.month,
                    "payments",
                    value,
                    cost.id,
                    phase.id,
                    "cost-payment",
                    "按独立合同付款节点支付开发成本",
                )
        contracts = [c for c in data.contracts if c.phase_id == phase.id and c.known_on <= cutoff]
        historical_sales = sum((D(c.amount) for c in contracts if c.sale_month <= closed), ZERO)
        actual_sales = sum(
            (D(r.amount) for r in actuals if r.phase_id == phase.id and r.metric == "sales"), ZERO
        )
        if historical_sales != actual_sales:
            raise ValueError(f"{phase.name}历史签约金额与合同台账不勾稽")
        if any(c.recognized_month and c.recognized_month > closed for c in contracts):
            raise ValueError("已确认收入月份不能晚于已结账月份；未来确认请使用交付计划")
        sold_area = sum((D(c.area) for c in contracts), ZERO)
        if sold_area > D(phase.area) or any(D(c.area) <= 0 or D(c.amount) < 0 for c in contracts):
            raise ValueError(f"{phase.name}合同面积或金额不合法")
        delivery = phase.delivery_month
        delay = override.delivery_delays.get(phase.id, 0)
        if delay and delivery <= closed:
            raise ValueError("不能延后已交付历史分期")
        delivery = shift(delivery, delay)
        forecast_contracts: list[tuple[str, str, Decimal, Decimal]] = []
        for contract in contracts:
            if contract.sale_month > closed:
                post(
                    contract.sale_month,
                    "sales",
                    D(contract.amount),
                    contract.id,
                    phase.id,
                    "signed-contract",
                    "已签合同金额保持不变",
                )
            collected = sum(
                (
                    D(r.amount)
                    for r in actuals
                    if r.metric == "collections" and r.contract_id == contract.id
                ),
                ZERO,
            )
            future_payments = [p for p in contract.collections if p.month > closed]
            if collected + sum((D(p.amount) for p in future_payments), ZERO) != D(contract.amount):
                raise ValueError(f"合同{contract.id}的历史已收款与未来收款计划不勾稽")
            end_receivables += D(contract.amount) - collected
            for payment in future_payments:
                post(
                    shift(payment.month, override.collection_delay),
                    "collections",
                    D(payment.amount),
                    contract.id,
                    phase.id,
                    "contract-collection",
                    "剩余应收按合同节点回款，独立于收入确认",
                )
                end_receivables -= D(payment.amount)
            if contract.recognized_month and contract.recognized_month <= closed:
                continue
            recognize = max(contract.sale_month, delivery, shift(closed, 1))
            forecast_contracts.append(
                (contract.id, recognize, D(contract.area), D(contract.amount))
            )
        remaining_area = D(phase.area) - sold_area
        if remaining_area:
            areas = allocate(remaining_area, [D(1)] * phase.sales_months)
            sale_start = max(phase.sales_start, shift(closed, 1))
            for index, area in enumerate(areas):
                sale_month = shift(sale_start, index)
                record_id = f"plan:{phase.id}:{sale_month}"
                amount = D(money(area * D(phase.price) * price_factor))
                post(
                    sale_month,
                    "sales",
                    amount,
                    record_id,
                    phase.id,
                    "unsold-sales-plan",
                    "剩余可售面积按均匀月度计划分配，调价只作用于未售",
                )
                first = D(money(amount * D(a.down_payment_rate)))
                post(
                    sale_month,
                    "collections",
                    first,
                    record_id,
                    phase.id,
                    "down-payment",
                    "新增销售首付",
                )
                post(
                    shift(sale_month, a.collection_lag + override.collection_delay),
                    "collections",
                    amount - first,
                    record_id,
                    phase.id,
                    "remaining-collection",
                    "新增销售尾款及按揭滞后",
                )
                forecast_contracts.append((record_id, max(sale_month, delivery), area, amount))
        historical_cogs = sum(
            (D(r.amount) for r in actuals if r.metric == "cogs" and r.phase_id == phase.id), ZERO
        )
        remaining_budget = estimated_cost - historical_cogs
        if remaining_budget < 0:
            raise ValueError("预计总成本低于已结转成本，需要明确成本调整记录")
        if forecast_contracts:
            allocations = allocate(remaining_budget, [c[2] for c in forecast_contracts])
            for (record_id, month, area, amount), allocated_cost in zip(
                forecast_contracts, allocations, strict=True
            ):
                post(
                    month,
                    "revenue",
                    amount,
                    record_id,
                    phase.id,
                    "delivery-recognition",
                    "同时满足已销售和交付条件确认收入",
                )
                post(
                    month,
                    "cogs",
                    allocated_cost,
                    record_id,
                    phase.id,
                    "area-cost-allocation",
                    f"（成本预算{money(estimated_cost)}－已结转{money(historical_cogs)}）"
                    f"×本项面积{area}÷待确认总面积{sum(c[2] for c in forecast_contracts)}；"
                    f"尾差落末项。成本记录：{','.join(c.id for c in costs)}",
                )
                operating_end = max(operating_end, month)
        elif remaining_budget:
            warnings.append(
                f"{phase.name}保留未结转成本{money(remaining_budget)}元，未自动冲销历史"
            )
    operating_end = max(operating_end, max(ledger, default=operating_end))
    for month in month_range(shift(closed, 1), operating_end):
        expenses = D(a.monthly_overhead) + ledger[month]["sales"] * D(a.marketing_rate)
        taxes = ledger[month]["revenue"] * D(a.tax_rate)
        post(
            month,
            "expenses",
            expenses,
            "assumptions:fees",
            "",
            "fixed-and-sales-fees",
            "固定管理费＋当月销售金额×营销费率",
        )
        post(
            shift(month, a.expense_payment_lag),
            "expense_payments",
            expenses,
            "assumptions:fees",
            "",
            "expense-payment",
            "费用付款与发生分开记录",
        )
        post(
            month,
            "taxes",
            taxes,
            "assumptions:tax",
            "",
            "illustrative-tax",
            "收入×模拟税费率，并非适用税法判断",
        )
        post(
            shift(month, 1),
            "tax_payments",
            taxes,
            "assumptions:tax",
            "",
            "tax-payment",
            "模拟计提次月缴付",
        )
    loan_months = [p.month for p in a.loan_draws + a.loan_repayments]
    end = max([shift(origin_month, 12), operating_end, *ledger.keys(), *loan_months])
    for month in month_range(shift(closed, 1), end):
        interest = loan * D(a.annual_interest_rate) / 12
        post(
            month,
            "interest",
            interest,
            "assumptions:loan",
            "",
            "opening-loan-interest",
            "月初借款余额×年利率÷12；当月计提并支付",
        )
        for draw in [p for p in a.loan_draws if p.month == month]:
            if D(draw.amount) < 0:
                raise ValueError("计划提款不能为负")
            allowed = min(D(draw.amount), max(ZERO, D(a.loan_limit) - loan))
            if allowed != D(draw.amount):
                warnings.append(f"{month}计划提款超过额度，未自动补足")
            loan += allowed
            post(
                month,
                "borrowing",
                allowed,
                "assumptions:loan",
                "",
                "limited-financing",
                "显式提款计划，受额度约束",
            )
        for payment in [p for p in a.loan_repayments if p.month == month]:
            if D(payment.amount) < 0 or D(payment.amount) > loan:
                raise ValueError("计划还本金额超过借款余额或为负")
            loan -= D(payment.amount)
            post(
                month,
                "repayment",
                D(payment.amount),
                "assumptions:loan",
                "",
                "scheduled-repayment",
                "按计划归还本金，不计入利润成本",
            )
    if loan:
        warnings.append(f"期末尚有借款本金{money(loan)}元，未自动清偿")
    start = min([a.opening_month, *ledger.keys()])
    cash = D(a.opening_cash)
    months: list[MonthResult] = []
    cumulative_profit = ZERO
    for month in month_range(start, end):
        amounts = ledger[month]
        profit = (
            amounts["revenue"]
            - amounts["cogs"]
            - amounts["expenses"]
            - amounts["taxes"]
            - amounts["interest"]
        )
        net = (
            amounts["collections"]
            - amounts["payments"]
            - amounts["expense_payments"]
            - amounts["tax_payments"]
            - amounts["interest"]
            + amounts["borrowing"]
            - amounts["repayment"]
        )
        cash += net
        if month > origin_month:
            cumulative_profit += profit
        period = (
            "actual" if month <= closed else "estimate" if month <= origin_month else "forecast"
        )
        values = {key: money(amounts[key]) for key in METRICS}
        months.append(
            MonthResult.model_validate(
                {
                    "month": month,
                    "period": period,
                    **values,
                    "profit": money(profit),
                    "cumulative_profit": money(cumulative_profit),
                    "net_cash_flow": money(net),
                    "cash_balance": money(cash),
                    "uncovered_gap": money(max(ZERO, -cash)),
                }
            )
        )
    targets = month_range(shift(origin_month, 1), shift(origin_month, 12))
    target_rows = [m for m in months if m.month in targets]
    target_profit = money(sum((D(m.profit) for m in target_rows), ZERO))
    return ForecastResult(
        target_months=targets,
        months=months,
        sources=sources,
        warnings=sorted(set(warnings)),
        summary=Summary(
            next_month_profit=target_rows[0].profit,
            twelve_month_profit=target_profit,
            lifecycle_profit=money(sum((D(m.profit) for m in months), ZERO)),
            max_funding_gap=money(
                max((D(m.uncovered_gap) for m in months if m.month > origin_month), default=ZERO)
            ),
            ending_debt=money(loan),
            ending_receivables=money(end_receivables),
            range_low=target_profit,
            range_high=target_profit,
        ),
    )


def aggregate(results: Iterable[ForecastResult]) -> ForecastResult:
    values = list(results)
    if not values or any(
        (v.target_months, v.currency, v.profit_basis, v.rule_version)
        != (
            values[0].target_months,
            values[0].currency,
            values[0].profit_basis,
            values[0].rule_version,
        )
        for v in values
    ):
        raise ValueError("汇总必须使用同月份、币种、口径和规则版本的完整结果")
    rows: dict[str, list[MonthResult]] = defaultdict(list)
    last_month = max(r.month for v in values for r in v.months)
    for result in values:
        for row in result.months:
            rows[row.month].append(row)
        last = result.months[-1]
        for month in month_range(shift(last.month, 1), last_month):
            rows[month].append(
                MonthResult(
                    month=month,
                    period="forecast",
                    cash_balance=last.cash_balance,
                    uncovered_gap=last.uncovered_gap,
                    cumulative_profit=last.cumulative_profit,
                )
            )
    columns = [key for key in MonthResult.model_fields if key not in ("month", "period")]
    months = []
    for month, members in sorted(rows.items()):
        periods = {m.period for m in members}
        totals = {
            key: money(sum((D(str(getattr(m, key))) for m in members), ZERO)) for key in columns
        }
        months.append(
            MonthResult.model_validate(
                {
                    "month": month,
                    "period": next(iter(periods)) if len(periods) == 1 else "mixed",
                    **totals,
                }
            )
        )

    def total(key: str) -> str:
        return money(sum((D(str(getattr(v.summary, key))) for v in values), ZERO))

    scenarios = {
        name: money(sum((D(v.scenario_totals[name]) for v in values), ZERO))
        for name in ("base", "optimistic", "prudent")
    }
    targets = values[0].target_months
    summary = Summary(
        next_month_profit=total("next_month_profit"),
        twelve_month_profit=total("twelve_month_profit"),
        lifecycle_profit=total("lifecycle_profit"),
        ending_debt=total("ending_debt"),
        ending_receivables=total("ending_receivables"),
        max_funding_gap=money(
            max((D(m.uncovered_gap) for m in months if m.month >= targets[0]), default=ZERO)
        ),
        range_low=money(min(D(v) for v in scenarios.values())),
        range_high=money(max(D(v) for v in scenarios.values())),
    )
    return ForecastResult(
        target_months=targets,
        months=months,
        summary=summary,
        sources=[],
        scenario_totals=scenarios,
        warnings=["项目汇总不含集团抵销、权益折算及资金调拨；资金缺口逐项目保留。"],
    )
