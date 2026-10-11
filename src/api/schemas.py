"""Request/response models. Pydantic enforces the structured-input guardrails:
allowed category values, numeric ranges and text lengths."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DisruptionType = Literal["Port Congestion", "Geopolitical", "Labor Strike", "Natural Disaster", "Cyber Attack", "Factory Incident"]
Industry = Literal["Electronics", "Automotive", "Consumer Goods", "Pharmaceuticals", "Aerospace"]
Region = Literal["Asia-Pacific", "Europe", "North America", "South America", "Africa/Middle East"]
Size = Literal["Small", "Medium", "Large"]
ResponseType = Literal["Alternative Supplier", "Production Reroute", "Inventory Buffer", "Customer Delay", "Combined Strategy"]
Tier = Literal[1, 2, 3, 4]
Severity = Field(ge=1, le=5)


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disruption_type: Optional[list[DisruptionType]] = None
    industry: Optional[list[Industry]] = None
    supplier_tier: Optional[list[Tier]] = None
    supplier_region: Optional[list[Region]] = None
    supplier_size: Optional[list[Size]] = None
    response_type: Optional[list[ResponseType]] = None
    has_backup_supplier: Optional[bool] = None
    disruption_severity: Optional[int] = Field(None, ge=1, le=5)
    min_severity: Optional[int] = Field(None, ge=1, le=5)
    max_severity: Optional[int] = Field(None, ge=1, le=5)


class QueryText(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, examples=["Typhoon shut down our Taiwanese chip supplier's plant for two weeks"])

    @field_validator("query")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("query is empty")
        return v


class ClassifyRequest(QueryText):
    pass


class SearchRequest(QueryText):
    top_k: int = Field(10, ge=1, le=50)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    alpha: float = Field(0.6, ge=0, le=1, description="Weight of semantic vs keyword ranking in hybrid fusion")
    filters: Optional[Filters] = None
    auto_filter: bool = Field(False, description="Derive filters from the classification agent")


class DisruptionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disruption_type: DisruptionType
    industry: Industry
    supplier_tier: Tier
    supplier_region: Region
    supplier_size: Size = "Medium"
    has_backup_supplier: bool = False
    disruption_severity: int = Severity
    response_type: Optional[ResponseType] = None


class ProfileOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disruption_type: Optional[DisruptionType] = None
    industry: Optional[Industry] = None
    supplier_tier: Optional[Tier] = None
    supplier_region: Optional[Region] = None
    supplier_size: Optional[Size] = None
    has_backup_supplier: Optional[bool] = None
    disruption_severity: Optional[int] = Field(None, ge=1, le=5)


class RecommendRequest(QueryText):
    profile: Optional[ProfileOverrides] = None
    top_k: int = Field(10, ge=3, le=50)
    filters: Optional[Filters] = None


class PrioritizeItem(BaseModel):
    id: Optional[str] = Field(None, max_length=64)
    disruption_severity: int = Severity
    production_impact_pct: float = Field(..., ge=0, le=100)
    revenue_loss_usd: float = Field(..., ge=0, le=1e11)
    supplier_tier: Tier = 2
    has_backup_supplier: bool = True
    description: Optional[str] = Field(None, max_length=500)


class PrioritizeRequest(BaseModel):
    items: list[PrioritizeItem] = Field(..., min_length=1, max_length=500)


class ExplainRequest(BaseModel):
    profile: DisruptionProfile
    target: Literal["production_impact_pct", "revenue_loss_usd", "full_recovery_days", "partial_recovery_days",
                    "high_impact", "permanent_supplier_change"] = "full_recovery_days"
    narrate: bool = False


class RiskRequest(BaseModel):
    industry: Industry
    supplier_region: Region
    supplier_tier: Tier = 1
    supplier_size: Size = "Medium"
    has_backup_supplier: bool = False
    assumed_severity: int = Field(3, ge=1, le=5)


class AnalyzeRequest(QueryText):
    profile: Optional[ProfileOverrides] = None
    production_impact_pct: Optional[float] = Field(None, ge=0, le=100, description="Observed impact, if known")
    revenue_loss_usd: Optional[float] = Field(None, ge=0, le=1e11, description="Observed loss, if known")
    filters: Optional[Filters] = None
    top_k: int = Field(10, ge=3, le=30)


class JudgeRequest(QueryText):
    answer: dict[str, Any] = Field(..., description="The analysis/recommendation to evaluate")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Retrieved evidence used to produce the answer")


class DeepCheckRequest(QueryText):
    plan: dict[str, Any] = Field(..., description="The response plan to check, including its fact_sheet (the evidence it was given)")


class OutcomeReport(DisruptionProfile):
    response_type: ResponseType
    production_impact_pct: float = Field(..., ge=0, le=100)
    revenue_loss_usd: float = Field(..., ge=0)
    response_time_days: int = Field(..., ge=0, le=365)
    partial_recovery_days: int = Field(..., ge=0, le=1000)
    full_recovery_days: int = Field(..., ge=0, le=2000)
    permanent_supplier_change: bool = False


class FeedbackRequest(BaseModel):
    query: Optional[str] = Field(None, max_length=2000)
    endpoint: Literal["analyze", "recommend", "search", "classify", "other"] = "analyze"
    rating: Optional[int] = Field(None, ge=1, le=5)
    helpful: Optional[bool] = None
    comment: Optional[str] = Field(None, max_length=1000)
    recommended_strategy: Optional[ResponseType] = None
    chosen_strategy: Optional[ResponseType] = None
    cited_cases: Optional[list[str]] = Field(None, max_length=50)
    plan_text: Optional[str] = Field(None, max_length=5000)
    outcome: Optional[OutcomeReport] = None

    @model_validator(mode="after")
    def needs_a_signal(self):
        if self.rating is None and self.helpful is None and not (self.comment or "").strip() and not self.chosen_strategy and not self.outcome:
            raise ValueError("Feedback needs at least a rating, a helpful yes/no, a comment, the strategy chosen, or an outcome.")
        return self
