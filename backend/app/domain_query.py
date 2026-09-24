"""Read frozen forecast values; model output never supplies an amount."""

from decimal import Decimal

from app.domain import money
from app.schemas import AgentAnswer, AgentPlan, ForecastResult

LABELS = {
    "profit": ("模拟管理口径利润", "收入扣除结转成本、期间费用、简化税费和利息；不是现金余额。"),
    "revenue": ("确认收入", "按模拟交付规则计入收入，与签约金额、回款时间分别处理。"),
    "cogs": ("成本结转", "把已交付房屋对应的开发成本计入当期利润扣减，不等于本月付款。"),
    "expenses": ("期间费用", "计入当期利润的费用，其支付安排可能在其他月份。"),
    "taxes": ("简化税费", "按本次模拟税费假设测算，待业务调研确认。"),
    "interest": ("利息费用", "按本次借款余额和利率规则形成的利息费用。"),
    "collections": ("销售回款", "销售款到账金额；到账不代表同月确认收入。"),
    "payments": ("开发付款", "开发相关现金支出；付款不代表同月计入利润成本。"),
    "net_cash_flow": ("净现金流", "当期现金流入减流出；汇总不代表项目间资金可以调拨。"),
    "cash_balance": ("期末现金余额", "所选期间最后一个月的现金余额，不能逐月累加。"),
    "uncovered_gap": (
        "未覆盖资金缺口峰值",
        "所选期间内缺口的最大值；汇总保留各项目缺口，不用其他项目盈余抵销。",
    ),
}


def query_result(result: ForecastResult, plan: AgentPlan) -> AgentAnswer:
    if plan.action != "query" or plan.metric is None:
        raise ValueError("不是有效的只读查询")
    if plan.period == "next_month":
        selected = result.target_months[:1]
    elif plan.period == "twelve_month":
        selected = result.target_months
    elif plan.period == "month":
        selected = [plan.month] if plan.month is not None else []
    else:
        selected = [row.month for row in result.months]
    indexed = {row.month: row for row in result.months}
    if not selected or any(month not in indexed for month in selected):
        raise ValueError("所问月份不在本次运行中，请重新选择期间")
    rows = [indexed[month] for month in selected]
    values = [Decimal(str(getattr(row, plan.metric))) for row in rows]
    evidence_month = None
    if plan.metric == "cash_balance":
        amount = values[-1]
        evidence_month = selected[-1]
    elif plan.metric == "uncovered_gap":
        amount = max(values)
        evidence_month = selected[values.index(amount)]
    else:
        amount = sum(values, Decimal("0"))
    related = {
        "profit": {"revenue", "cogs", "expenses", "taxes", "interest"},
        "net_cash_flow": {
            "collections",
            "payments",
            "expense_payments",
            "tax_payments",
            "interest",
            "borrowing",
            "repayment",
        },
    }
    source_metrics = related.get(plan.metric, {plan.metric})
    if evidence_month is not None:
        source_metrics = related["net_cash_flow"] | {"opening_cash"}
    label, explanation = LABELS[plan.metric]
    return AgentAnswer(
        metric=plan.metric,
        label=label,
        amount=money(amount),
        currency=result.currency,
        unit=result.unit,
        period_label=selected[0] if len(selected) == 1 else f"{selected[0]}—{selected[-1]}",
        months=selected,
        explanation=explanation,
        source_count=sum(
            (source.month <= evidence_month if evidence_month else source.month in selected)
            and source.metric in source_metrics
            for source in result.sources
        ),
        evidence_month=evidence_month,
    )
