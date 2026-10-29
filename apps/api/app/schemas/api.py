from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import RequestStatus, ReviewStatus


class RequestCreate(BaseModel):
    policy: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = "policy-v1"
    idempotency_key: str | None = Field(default=None, max_length=255)


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scope_id: UUID
    status: RequestStatus
    policy_version: str
    created_at: datetime
    updated_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    pages: int
    status: str
    created_at: datetime


class EvidenceOut(BaseModel):
    id: UUID
    page_id: UUID
    start_offset: int
    end_offset: int
    bbox: dict[str, Any]
    entity_type: str
    semantic_role: str | None
    score: float
    detector: str
    reason_codes: list[str]
    review_status: ReviewStatus
    original_text: str | None = None


class EvidencePatch(BaseModel):
    entity_type: str | None = None
    semantic_role: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    bbox: dict[str, Any] | None = None
    review_status: Literal["PENDING", "APPROVED", "REJECTED", "REVIEW_REQUIRED"] | None = None

    @field_validator("end_offset")
    @classmethod
    def valid_end(cls, value: int | None, info):
        start = info.data.get("start_offset")
        if value is not None and start is not None and value <= start:
            raise ValueError("end_offset must be greater than start_offset")
        return value


class ReviewApprove(BaseModel):
    evidence_ids: list[UUID] = Field(default_factory=list)
    confirm_all: bool = False


class ValidationOut(BaseModel):
    status: str
    report: dict[str, Any]


class SafeTextOut(BaseModel):
    request_id: UUID
    revision: int
    text: str
    validation_report: dict[str, Any]
    approved: bool


class RestoreOut(BaseModel):
    api_call_id: UUID
    status: str
    restored: dict[str, Any] | None = None


class ProviderSettingsUpdate(BaseModel):
    endpoint: str = Field(default="https://api.openai.com/v1", min_length=1, max_length=500)
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=120)
    mode: Literal["mock", "live"] = "mock"
    api_key: str | None = Field(default=None, max_length=500)


class ProviderSettingsOut(BaseModel):
    endpoint: str
    model: str
    mode: str
    configured: bool
    api_key_masked: str | None


class ErrorOut(BaseModel):
    code: str
    message: str
    correlation_id: UUID
    details: dict[str, Any] = Field(default_factory=dict)
