from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.constants import BatchStatus, Book, Bucket, GapType, LadderView, RecommendationRule, Role, ShiftDirection, ShiftUnit

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @computed_field
    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size


# ---------------------------------------------------------------- health

class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    version: str


class DbHealthResponse(BaseModel):
    status: str
    database: str
    error: str | None = None


# ---------------------------------------------------------------- auth

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    username: str
    full_name: str | None = None
    role: Role
    location: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class CurrentUser(BaseModel):
    id: int
    username: str
    role: Role
    location: str | None = None

    @property
    def is_support(self) -> bool:
        return self.role == Role.SUPPORT

    def allowed_locations(self, all_locations) -> set[str]:
        return set(all_locations) if self.is_support else {self.location}


# ---------------------------------------------------------------- ingestion

class RowError(ORMModel):
    row_number: int
    transaction_id: str | None = None
    column_name: str
    rule: str
    value: str | None = None
    message: str


class BatchOut(ORMModel):
    id: int
    book: Book
    file_name: str
    run_date: date
    status: BatchStatus
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    created_at: datetime


class UploadResult(BaseModel):
    batch: BatchOut
    errors_preview: list[RowError]
    message: str
    predictions: str | None = None


class RunDateOut(BaseModel):
    run_date: date
    has_assets: bool
    has_liabilities: bool
    has_predictions: bool


# ---------------------------------------------------------------- ladders

class BucketValue(BaseModel):
    bucket: Bucket
    assets: float
    liabilities: float
    net_gap: float
    asset_count: int
    liability_count: int


class LadderSeries(BaseModel):
    currency: str
    location: str
    buckets: list[BucketValue]


class LadderResponse(BaseModel):
    run_date: date
    view: LadderView
    series: list[LadderSeries]
    totals_by_currency: dict[str, list[BucketValue]]


class TransactionRow(BaseModel):
    transaction_id: str
    book: Book
    entity: str
    location: str
    customer_id: str
    customer_segment: str
    client_rating: int
    currency: str
    principal: float
    interest_amount: float
    maturity_cashflow: float
    interest_rate_pct: float
    market_interest_rate_pct: float
    product_type: str
    transaction_date: date
    contractual_maturity: date
    adjusted_maturity: date | None = None
    p_early: float | None = None
    risk_level: str | None = None
    days_pulled_forward: int | None = None
    bucket: Bucket


class CompareBucket(BaseModel):
    bucket: Bucket
    deterministic_gap: float
    ai_gap: float
    difference: float
    recommendation_count: int


class CompareCurrency(BaseModel):
    currency: str
    buckets: list[CompareBucket]


class CompareResponse(BaseModel):
    run_date: date
    currencies: list[CompareCurrency]


# ---------------------------------------------------------------- what-if

class TenorShift(BaseModel):
    value: int = Field(ge=0, le=600)
    unit: ShiftUnit = ShiftUnit.MONTHS
    direction: ShiftDirection = ShiftDirection.EARLIER

    def label(self) -> str:
        unit = self.unit.value[:-1] if self.value == 1 else self.unit.value
        return f"{self.value} {unit} {self.direction.value}"


class ScenarioRequest(BaseModel):
    run_date: date
    location: str | None = None
    currency: str | None = None
    asset_shift: TenorShift | None = None
    liability_shift: TenorShift | None = None

    @model_validator(mode="after")
    def needs_a_shift(self):
        if not any(s and s.value for s in (self.asset_shift, self.liability_shift)):
            raise ValueError("Set a non-zero shift for assets, liabilities or both")
        return self


class ScenarioResponse(BaseModel):
    description: str
    baseline: LadderResponse
    scenario: LadderResponse


# ---------------------------------------------------------------- recommendations

class RecommendationOut(BaseModel):
    id: str
    rule_code: RecommendationRule
    category: str
    currency: str
    location: str
    bucket: Bucket
    gap_type: GapType
    severity: str                  # high | medium | low (Rule A), surplus (B), monitor (C), medium (D)
    deterministic_gap: float
    ai_gap: float
    gap_difference: float          # ai_gap - deterministic_gap: the behavioural effect
    amount: float                  # headline amount of the action
    investable_surplus: float = 0  # Rule B / D: what can actually be invested
    reserved_amount: float = 0     # Rule C / D: what should be kept back
    required_buffer: float = 0
    action_text: str
    detailed_action: str
    reason: str
    rationale: str


# ---------------------------------------------------------------- behavioral model

class FeatureDriver(BaseModel):
    feature: str
    value: str
    contribution: float
    effect: str


class PredictionRationale(BaseModel):
    transaction_id: str
    book: Book
    p_early: float
    predicted_early: bool
    risk_level: str
    threshold: float
    expected_shift_days: int
    contractual_maturity: date
    adjusted_maturity: date
    days_pulled_forward: int
    drivers: list[FeatureDriver]
    summary: str


class ModelInfo(BaseModel):
    book: Book
    algorithm: str
    available: bool
    threshold: float | None = None
    trained_at: str | None = None
    training_rows: int | None = None
    metrics: dict | None = None


class PredictResponse(BaseModel):
    run_date: date
    predicted: int
    avg_p_early_assets: float
    avg_p_early_liabilities: float


# ---------------------------------------------------------------- analytics

class ExitTrendPoint(BaseModel):
    period: str
    group: str
    total: int
    early_exits: int
    early_exit_rate: float


class ExitTrendResponse(BaseModel):
    group_by: str
    points: list[ExitTrendPoint]


class AnomalyPoint(BaseModel):
    date: date
    outflow: float
    rolling_avg: float | None
    ratio: float | None
    is_anomaly: bool
    message: str | None


class AnomalyResponse(BaseModel):
    window_days: int
    multiplier: float
    currency: str | None
    location: str | None
    points: list[AnomalyPoint]
    anomaly_count: int
