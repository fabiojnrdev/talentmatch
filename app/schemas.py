from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY_PATTERN = r"^[a-z][a-z0-9_]{1,48}$"


class LawfulBasis(StrEnum):
    CONSENT = "consent"  # art. 7º, I
    PRE_CONTRACTUAL = "pre_contractual"  # art. 7º, V


class AnalysisStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_info"


# ---------- Vagas ----------
class MustHave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY_PATTERN)
    description: str = Field(min_length=3, max_length=300)
    weight: float = Field(default=1.0, gt=0, le=10)


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    must_have: list[MustHave] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def _unique_keys(self) -> "JobCreate":
        keys = [m.key for m in self.must_have]
        duplicated = sorted({k for k in keys if keys.count(k) > 1})
        if duplicated:
            raise ValueError(f"chaves duplicadas em must_have: {duplicated}")
        return self


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    must_have: list[MustHave]
    created_at: datetime


# ---------- Contrato com a LLM (wire) ----------
class ChecklistItemWire(BaseModel):
    key: str
    met: bool
    evidence: str | None


class ExtractionWire(BaseModel):
    checklist: list[ChecklistItemWire]
    strengths: list[str]
    gaps: list[str]
    extraction_confidence: float
    justification: str


class ValidatedExtraction(BaseModel):
    """Saída da LLM já validada pelas regras de negócio."""

    checklist: dict[str, bool]
    evidence: dict[str, str | None]
    strengths: list[str]
    gaps: list[str]
    extraction_confidence: float = Field(ge=0, le=1)
    justification: str


# ---------- Candidatos / resultados ----------
class AnalyzeAccepted(BaseModel):
    task_id: str
    trace_id: str
    candidate_id: str | None
    status: AnalysisStatus


class ErrorOut(BaseModel):
    code: str
    message: str


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    note: str | None = Field(default=None, max_length=500)


class ReviewOut(BaseModel):
    decision: ReviewDecision
    note: str | None
    reviewed_by: str
    reviewed_at: datetime


class ResultOut(BaseModel):
    task_id: str
    trace_id: str
    status: AnalysisStatus
    result: dict[str, Any] | None = None
    error: ErrorOut | None = None
    human_review: ReviewOut | None = None


class AnalysisRef(BaseModel):
    task_id: str
    status: AnalysisStatus


class CandidateOut(BaseModel):
    candidate_id: str
    lawful_basis: LawfulBasis
    created_at: datetime
    expires_at: datetime
    redaction_report: dict[str, int]
    redacted_text: str
    analyses: list[AnalysisRef]
