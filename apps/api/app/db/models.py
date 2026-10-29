import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RequestStatus(enum.StrEnum):
    CREATED = "CREATED"
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    DETECTING = "DETECTING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    PSEUDONYMIZING = "PSEUDONYMIZING"
    VALIDATING = "VALIDATING"
    READY_TO_SEND = "READY_TO_SEND"
    SENDING = "SENDING"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    RESTORING = "RESTORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED_LEAKAGE = "BLOCKED_LEAKAGE"
    RESTORE_REVIEW_REQUIRED = "RESTORE_REVIEW_REQUIRED"
    CANCELLED = "CANCELLED"


class ReviewStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80), unique=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class ProcessingRequest(TimestampMixin, Base):
    __tablename__ = "processing_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), default=uuid.uuid4, unique=True, index=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, native_enum=False), default=RequestStatus.CREATED, index=True
    )
    policy_version: Mapped[str] = mapped_column(String(80), default="policy-v1")
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderSetting(TimestampMixin, Base):
    __tablename__ = "provider_settings"
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    endpoint: Mapped[str] = mapped_column(String(500), default="https://api.openai.com/v1")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini")
    mode: Mapped[str] = mapped_column(String(20), default="mock")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="UPLOADED", index=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentPage(TimestampMixin, Base):
    __tablename__ = "document_pages"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_index: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    ocr_engine: Mapped[str] = mapped_column(String(100))
    ocr_quality: Mapped[float | None] = mapped_column(nullable=True)
    orientation: Mapped[int] = mapped_column(Integer, default=0)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (UniqueConstraint("document_id", "page_index"),)


class OcrBlock(TimestampMixin, Base):
    __tablename__ = "ocr_blocks"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_pages.id", ondelete="CASCADE"), index=True
    )
    reading_order: Mapped[int] = mapped_column(Integer)
    encrypted_text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[dict[str, float]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column()
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)


class EntityEvidence(TimestampMixin, Base):
    __tablename__ = "entity_evidence"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_pages.id"), index=True)
    block_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ocr_blocks.id"), nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSON)
    encrypted_original: Mapped[str] = mapped_column(Text)
    detector: Mapped[str] = mapped_column(String(100))
    detector_version: Mapped[str] = mapped_column(String(80))
    score: Mapped[float] = mapped_column()
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    semantic_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False), default=ReviewStatus.PENDING, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)


class ResolvedEntity(TimestampMixin, Base):
    __tablename__ = "resolved_entities"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    entity_key: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), default=uuid.uuid4, unique=True
    )
    entity_type: Mapped[str] = mapped_column(String(60))
    semantic_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column()
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False), default=ReviewStatus.PENDING
    )


class EntityOccurrence(Base):
    __tablename__ = "entity_occurrences"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    resolved_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resolved_entities.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entity_evidence.id", ondelete="CASCADE"), index=True
    )
    occurrence_order: Mapped[int] = mapped_column(Integer)
    dedup_status: Mapped[str] = mapped_column(String(40), default="resolved")


class PseudonymMapping(TimestampMixin, Base):
    __tablename__ = "pseudonym_mappings"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resolved_entities.id", ondelete="CASCADE"), index=True
    )
    encrypted_original: Mapped[str] = mapped_column(Text)
    pseudonym: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(60))
    strategy: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("request_id", "entity_id"),)


class PseudonymizedText(TimestampMixin, Base):
    __tablename__ = "pseudonymized_texts"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    encrypted_text: Mapped[str] = mapped_column(Text)
    provenance_map: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiCall(TimestampMixin, Base):
    __tablename__ = "api_calls"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_requests.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    outbound_text_snapshot: Mapped[str] = mapped_column(Text)
    outbound_payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(120))
    schema_version: Mapped[str] = mapped_column(String(80))
    openai_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ApiResponse(Base):
    __tablename__ = "api_responses"
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    api_call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_calls.id", ondelete="CASCADE"), unique=True
    )
    pseudonymized_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    restored_json_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(40))
    mapping_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(40))
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), default=uuid.uuid4, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


Index("ix_api_calls_request_created", ApiCall.request_id, ApiCall.created_at)
