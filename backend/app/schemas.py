"""Public API contracts. Money is serialized as decimal text, in CNY yuan."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Month = Annotated[str, Field(pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")]
Amount = Annotated[str, Field(pattern=r"^-?\d+(\.\d{1,8})?$", max_length=24)]
Metric = Literal[
    "sales", "collections", "revenue", "cogs", "development", "payments", "expenses",
    "expense_payments", "taxes", "tax_payments", "interest", "borrowing", "repayment",
]
Scenario = Literal["base", "optimistic", "prudent"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Payment(Model):
    month: Month
    amount: Amount


class Phase(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    area: Amount
    price: Amount
    sales_start: Month
    sales_months: int = Field(default=6, ge=1, le=60)
    delivery_month: Month
    known_on: date = date(2026, 1, 1)


class Contract(Model):
    id: str
    phase_id: str
    sale_month: Month
    area: Amount
    amount: Amount
    known_on: date
    recognized_month: Month | None = None
    collections: list[Payment] = Field(default_factory=list)


class Cost(Model):
    id: str
    phase_id: str
    category: Literal["land", "construction", "other"]
    amount: Amount
    incurred_month: Month
    known_on: date
    payments: list[Payment] = Field(default_factory=list)


class Actual(Model):
    id: str
    phase_id: str
    month: Month
    known_on: date
    metric: Metric
    amount: Amount
    note: str = ""


class Assumptions(Model):
    opening_month: Month = "2026-01"
    opening_cash: Amount = "0"
    monthly_overhead: Amount = "50000"
    marketing_rate: Amount = "0.02"
    tax_rate: Amount = "0.03"
    down_payment_rate: Amount = "0.30"
    collection_lag: int = Field(default=3, ge=0, le=24)
    expense_payment_lag: int = Field(default=0, ge=0, le=24)
    loan_limit: Amount = "20000000"
    annual_interest_rate: Amount = "0.05"
    loan_draws: list[Payment] = Field(default_factory=list)
    loan_repayments: list[Payment] = Field(default_factory=list)

    @field_validator("marketing_rate", "tax_rate", "down_payment_rate", "annual_interest_rate")
    @classmethod
    def validate_rate(cls, value: str) -> str:
        if not Decimal(0) <= Decimal(value) <= Decimal(1):
            raise ValueError("比例须在0至1之间")
        return value


class Dataset(Model):
    phases: list[Phase] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    costs: list[Cost] = Field(default_factory=list)
    actuals: list[Actual] = Field(default_factory=list)
    assumptions: Assumptions = Field(default_factory=Assumptions)
    actual_closed_through: Month = "2026-08"

    @model_validator(mode="after")
    def validate_references(self) -> "Dataset":
        phase_ids = {p.id for p in self.phases}
        if len(phase_ids) != len(self.phases):
            raise ValueError("分期编号重复")
        for items in (self.contracts, self.costs, self.actuals):
            if len({item.id for item in items}) != len(items):
                raise ValueError("记录编号重复")
            if any(item.phase_id not in phase_ids for item in items):
                raise ValueError("记录引用了不存在的分期")
        return self


class ProjectCreate(Model):
    name: str = Field(min_length=1, max_length=100)
    template: Literal["blank", "demo"] = "blank"


class ProjectPatch(Model):
    name: str = Field(min_length=1, max_length=100)
    archived: bool = False
    base_version: int


class RevisionWrite(Model):
    base_version: int
    known_on: date
    note: str = Field(default="手动修订", max_length=300)
    data: Dataset


class Revision(Model):
    id: str
    project_id: str
    version: int
    known_on: str
    created_at: str
    note: str
    data: Dataset


class Project(Model):
    id: str
    name: str
    archived: bool
    version: int
    revision_id: str
    created_at: str


class Overrides(Model):
    price_change: Amount = "0"
    remaining_cost_change: Amount = "0"
    collection_delay: int = Field(default=0, ge=0, le=24)
    delivery_delays: dict[str, int] = Field(default_factory=dict)

    @field_validator("price_change", "remaining_cost_change")
    @classmethod
    def validate_change(cls, value: str) -> str:
        if not Decimal("-0.9") <= Decimal(value) <= Decimal("2"):
            raise ValueError("变动幅度须在-90%至200%之间")
        return value

    @field_validator("delivery_delays")
    @classmethod
    def validate_delays(cls, value: dict[str, int]) -> dict[str, int]:
        if any(v < 0 or v > 36 for v in value.values()):
            raise ValueError("延期须在0至36个月之间")
        return value


class RunCreate(Model):
    project_ids: list[str] = Field(min_length=1, max_length=50)
    kind: Literal["project", "portfolio"] = "project"
    forecast_origin: date = date(2026, 8, 31)
    information_cutoff: date = date(2026, 8, 31)
    scenario: Scenario = "base"
    overrides: dict[str, Overrides] = Field(default_factory=dict)
    base_versions: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope(self) -> "RunCreate":
        if len(set(self.project_ids)) != len(self.project_ids):
            raise ValueError("不能重复选择同一项目")
        if self.kind == "project" and len(self.project_ids) != 1:
            raise ValueError("单项目预测只能选择一个项目")
        if self.information_cutoff > self.forecast_origin:
            raise ValueError("信息截止不得晚于预测基准")
        if not set(self.overrides).issubset(self.project_ids):
            raise ValueError("变更范围不属于本次项目")
        return self


class Source(Model):
    record_id: str
    phase_id: str = ""
    month: str
    metric: str
    amount: str
    rule: str
    description: str


class MonthResult(Model):
    month: str
    period: Literal["actual", "estimate", "forecast", "mixed"]
    sales: str = "0.00"
    collections: str = "0.00"
    revenue: str = "0.00"
    cogs: str = "0.00"
    development: str = "0.00"
    payments: str = "0.00"
    expenses: str = "0.00"
    expense_payments: str = "0.00"
    taxes: str = "0.00"
    tax_payments: str = "0.00"
    interest: str = "0.00"
    borrowing: str = "0.00"
    repayment: str = "0.00"
    profit: str = "0.00"
    net_cash_flow: str = "0.00"
    cash_balance: str = "0.00"
    uncovered_gap: str = "0.00"


class Summary(Model):
    next_month_profit: str
    twelve_month_profit: str
    lifecycle_profit: str
    max_funding_gap: str
    ending_debt: str
    ending_receivables: str
    range_low: str
    range_high: str


class Sensitivity(Model):
    label: str
    profit: str
    delta: str


class ForecastResult(Model):
    currency: str = "CNY"
    unit: str = "元"
    profit_basis: str = "模拟管理口径利润"
    rule_version: str = "demo-1"
    target_months: list[str]
    months: list[MonthResult]
    summary: Summary
    sources: list[Source]
    warnings: list[str]
    sensitivity: list[Sensitivity] = Field(default_factory=list)
    scenario_totals: dict[str, str] = Field(default_factory=dict)


class Step(Model):
    sequence: int
    name: str
    status: str
    message: str
    created_at: str
    attempt: int


class Member(Model):
    project_id: str
    project_name: str
    run_id: str
    revision_id: str
    status: str
    profit: str | None = None
    error: str | None = None


class Run(Model):
    id: str
    kind: Literal["project", "portfolio"]
    status: str
    created_at: str
    forecast_origin: str
    information_cutoff: str
    scenario: Scenario
    project_ids: list[str]
    project_names: list[str]
    revision_ids: list[str]
    error: str | None = None
    attempt: int = 1
    parent_id: str | None = None
    result: ForecastResult | None = None
    members: list[Member] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)


class ImportPreview(Model):
    project_id: str
    base_version: int
    additions: list[Actual]
    duplicates: list[str]
    errors: list[str]


class ImportConfirm(Model):
    base_version: int
    known_on: date
    records: list[Actual]


class Comparison(Model):
    left_id: str
    right_id: str
    months: list[str]
    profit_deltas: list[str]
    membership_changed: bool


class Evidence(Model):
    run_id: str
    metric: str
    month: str | None
    revision_ids: list[str]
    sources: list[Source]
    members: list[Member]


class ApiError(Model):
    code: str
    message: str
    request_id: str
