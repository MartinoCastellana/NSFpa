import hashlib
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import reject_if_not_tenant, session_dep
from app.core.config import get_settings
from app.core.crypto import EnvelopeCipher
from app.core.security import Principal, get_principal, require_original_access
from app.db.models import (
    ApiCall,
    ApiResponse,
    AuditEvent,
    Document,
    DocumentPage,
    EntityEvidence,
    EntityOccurrence,
    OcrBlock,
    ProcessingRequest,
    PseudonymizedText,
    PseudonymMapping,
    RequestStatus,
    ResolvedEntity,
    ReviewStatus,
    Tenant,
    User,
)
from app.schemas.api import (
    DocumentOut,
    EvidenceOut,
    EvidencePatch,
    RequestCreate,
    RequestOut,
    RestoreOut,
    ReviewApprove,
    SafeTextOut,
    ValidationOut,
)
from app.services.nec import RuleEntityClassifier
from app.services.ner import detect_pii
from app.services.ocr import LocalOcrAdapter, MiniCPMOcrAdapter
from app.services.openai_client import SafeOpenAIClient
from app.services.pseudonymization import Pseudonymizer
from app.services.restoration import restore_typed
from app.services.validation import validate_safe_text

router = APIRouter()
settings = get_settings()
cipher = EnvelopeCipher(settings.data_encryption_key)


async def _ensure_identity(session: AsyncSession, principal: Principal) -> None:
    if not await session.get(Tenant, principal.tenant_id):
        session.add(Tenant(id=principal.tenant_id, name="Development tenant"))
    if not await session.get(User, principal.user_id):
        session.add(User(id=principal.user_id, tenant_id=principal.tenant_id, subject=str(principal.user_id)))
    await session.flush()


async def _request(session: AsyncSession, request_id: UUID, principal: Principal) -> ProcessingRequest:
    item = await session.get(ProcessingRequest, request_id)
    if not item:
        raise HTTPException(404, "Request not found")
    reject_if_not_tenant(item.tenant_id, principal)
    return item


async def _document(session: AsyncSession, document_id: UUID, principal: Principal) -> Document:
    item = await session.get(Document, document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    reject_if_not_tenant(item.tenant_id, principal)
    return item


async def _audit(session: AsyncSession, principal: Principal, resource_type: str, resource_id: UUID | None, action: str, outcome: str = "success") -> None:
    session.add(AuditEvent(actor_id=principal.user_id, tenant_id=principal.tenant_id, resource_type=resource_type, resource_id=resource_id, action=action, outcome=outcome))


async def _document_text(session: AsyncSession, document: Document) -> tuple[str, list[DocumentPage]]:
    pages = list((await session.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_index))).all())
    pieces: list[str] = []
    for page in pages:
        blocks = list((await session.scalars(select(OcrBlock).where(OcrBlock.page_id == page.id).order_by(OcrBlock.reading_order))).all())
        pieces.append(" ".join(cipher.decrypt(block.encrypted_text) for block in blocks))
    return "\n".join(pieces), pages


async def _request_text(session: AsyncSession, request_id: UUID, tenant_id: UUID) -> tuple[str, list[Document]]:
    documents = list((await session.scalars(select(Document).where(Document.request_id == request_id, Document.tenant_id == tenant_id).order_by(Document.created_at))).all())
    texts = []
    for document in documents:
        text, _ = await _document_text(session, document)
        texts.append(text)
    return "\n\n".join(texts), documents


def _safe_filename(filename: str | None) -> str:
    raw = Path(filename or "document").name
    raw = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    return raw[:255] or "document"


def _sniff_mime(prefix: bytes, declared: str | None) -> str:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if declared == "text/plain" and b"\x00" not in prefix:
        return "text/plain"
    raise HTTPException(415, "Unsupported or invalid document format")


@router.post("/requests", response_model=RequestOut, status_code=201)
async def create_request(payload: RequestCreate, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _ensure_identity(session, principal)
    if payload.idempotency_key:
        existing = await session.scalar(select(ProcessingRequest).where(ProcessingRequest.tenant_id == principal.tenant_id, ProcessingRequest.idempotency_key == payload.idempotency_key))
        if existing:
            return existing
    item = ProcessingRequest(tenant_id=principal.tenant_id, owner_id=principal.user_id, policy=payload.policy, policy_version=payload.policy_version, idempotency_key=payload.idempotency_key, expires_at=datetime.now(UTC) + timedelta(days=settings.retention_days))
    session.add(item)
    await session.flush()
    await _audit(session, principal, "processing_request", item.id, "create")
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/requests/{request_id}", response_model=RequestOut)
async def get_request(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    return await _request(session, request_id, principal)


@router.post("/requests/{request_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(request_id: UUID, file: UploadFile = File(...), session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    target_dir = settings.storage_root / str(principal.tenant_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    document_id = UUID(bytes=hashlib.sha256(f"{request_id}:{time.time_ns()}".encode()).digest()[:16])
    target = target_dir / f"{document_id.hex}.upload"
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413, "Upload exceeds the configured size limit")
            digest.update(chunk)
            handle.write(chunk)
    with target.open("rb") as handle:
        prefix = handle.read(512)
    mime = _sniff_mime(prefix, file.content_type)
    document = Document(id=document_id, tenant_id=principal.tenant_id, request_id=request.id, original_name=_safe_filename(file.filename), mime_type=mime, size_bytes=size, storage_path=str(target), checksum=digest.hexdigest(), retention_until=request.expires_at)
    session.add(document)
    request.status = RequestStatus.UPLOADED
    await _audit(session, principal, "document", document.id, "upload")
    await session.commit()
    await session.refresh(document)
    return document


@router.get("/requests/{request_id}/documents", response_model=list[DocumentOut])
async def list_documents(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _request(session, request_id, principal)
    return list((await session.scalars(select(Document).where(Document.request_id == request_id, Document.tenant_id == principal.tenant_id).order_by(Document.created_at))).all())


@router.post("/documents/{document_id}/extract", response_model=DocumentOut, status_code=202)
async def extract_document(document_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    document = await _document(session, document_id, principal)
    request = await _request(session, document.request_id, principal)
    request.status = RequestStatus.EXTRACTING
    await session.flush()
    try:
        adapter = MiniCPMOcrAdapter(settings.minicpm_ocr_command) if settings.minicpm_ocr_enabled else LocalOcrAdapter(settings)
        pages = adapter.extract(Path(document.storage_path), document.mime_type)
        for page_result in pages:
            page = DocumentPage(tenant_id=principal.tenant_id, document_id=document.id, page_index=page_result.page_index, width=page_result.width, height=page_result.height, ocr_engine=adapter.name, ocr_quality=page_result.quality, orientation=page_result.orientation)
            session.add(page)
            await session.flush()
            offset = 0
            for order, word in enumerate(page_result.words):
                start = offset
                end = start + len(word.text)
                session.add(OcrBlock(tenant_id=principal.tenant_id, page_id=page.id, reading_order=order, encrypted_text=cipher.encrypt(word.text), bbox=word.bbox, confidence=word.confidence, start_offset=start, end_offset=end))
                offset = end + 1
        document.pages = len(pages)
        document.status = "EXTRACTED"
        request.status = RequestStatus.EXTRACTED
        await _audit(session, principal, "document", document.id, "extract")
        await session.commit()
    except Exception:
        request.status = RequestStatus.FAILED
        document.status = "FAILED"
        await session.commit()
        raise
    await session.refresh(document)
    return document


@router.get("/documents/{document_id}/pages/{page}/preview")
async def page_preview(document_id: UUID, page: int, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    require_original_access(principal)
    document = await _document(session, document_id, principal)
    if page < 0 or page >= max(document.pages, 1):
        raise HTTPException(404, "Page not found")
    return FileResponse(document.storage_path, media_type=document.mime_type, filename=document.original_name)


@router.get("/documents/{document_id}/ocr")
async def get_ocr(document_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    require_original_access(principal)
    document = await _document(session, document_id, principal)
    text, pages = await _document_text(session, document)
    await _audit(session, principal, "document", document.id, "read_original")
    await session.commit()
    return {"document_id": str(document.id), "text": text, "pages": len(pages)}


@router.post("/requests/{request_id}/detect", status_code=202)
async def detect(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    request.status = RequestStatus.DETECTING
    text, documents = await _request_text(session, request.id, principal.tenant_id)
    candidates = detect_pii(text)
    classifier = RuleEntityClassifier()
    for candidate in candidates:
        context = text[max(0, candidate.start - 70):min(len(text), candidate.end + 70)]
        classification = classifier.classify(candidate.entity_type, context)
        candidate.semantic_role = classification.semantic_role
        candidate.score = min(candidate.score, classification.confidence)
        candidate.reason_codes.extend(classification.reason_codes)
        candidate.page_index = text[:candidate.start].count("\n")
        document = documents[0] if documents else None
        if not document:
            continue
        pages = list((await session.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_index))).all())
        page = pages[min(candidate.page_index, len(pages) - 1)] if pages else None
        if not page:
            continue
        evidence = EntityEvidence(tenant_id=principal.tenant_id, request_id=request.id, page_id=page.id, start_offset=candidate.start, end_offset=candidate.end, bbox=candidate.bbox or {"x": 0, "y": 0, "w": 0, "h": 0}, encrypted_original=cipher.encrypt(candidate.text), detector=candidate.detector, detector_version="local-rules-v1", score=candidate.score, entity_type=candidate.entity_type, semantic_role=candidate.semantic_role, review_status=ReviewStatus.PENDING, reason_codes=candidate.reason_codes)
        session.add(evidence)
        await session.flush()
        entity = ResolvedEntity(tenant_id=principal.tenant_id, request_id=request.id, entity_type=candidate.entity_type, semantic_role=candidate.semantic_role, confidence=candidate.score, provenance={"detector": candidate.detector, "source_offset": [candidate.start, candidate.end]}, review_status=ReviewStatus.PENDING)
        session.add(entity)
        await session.flush()
        session.add(EntityOccurrence(tenant_id=principal.tenant_id, resolved_entity_id=entity.id, evidence_id=evidence.id, occurrence_order=0))
    request.status = RequestStatus.REVIEW_REQUIRED if candidates else RequestStatus.REVIEW_APPROVED
    await _audit(session, principal, "processing_request", request.id, "detect")
    await session.commit()
    return {"request_id": str(request.id), "status": request.status, "evidence_count": len(candidates)}


@router.get("/requests/{request_id}/evidences", response_model=list[EvidenceOut])
async def list_evidences(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _request(session, request_id, principal)
    rows = list((await session.scalars(select(EntityEvidence).where(EntityEvidence.request_id == request_id, EntityEvidence.tenant_id == principal.tenant_id).order_by(EntityEvidence.created_at))).all())
    can_read = principal.can_read_originals()
    return [EvidenceOut(id=row.id, page_id=row.page_id, start_offset=row.start_offset, end_offset=row.end_offset, bbox=row.bbox, entity_type=row.entity_type, semantic_role=row.semantic_role, score=row.score, detector=row.detector, reason_codes=row.reason_codes, review_status=row.review_status, original_text=cipher.decrypt(row.encrypted_original) if can_read else None) for row in rows]


@router.patch("/evidences/{evidence_id}", response_model=EvidenceOut)
async def patch_evidence(evidence_id: UUID, payload: EvidencePatch, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    if not (principal.roles & {"admin", "reviewer"}):
        raise HTTPException(403, "Reviewer role required")
    row = await session.get(EntityEvidence, evidence_id)
    if not row or row.tenant_id != principal.tenant_id:
        raise HTTPException(404, "Evidence not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, ReviewStatus(value) if key == "review_status" else value)
    row.reviewer_id = principal.user_id
    await _audit(session, principal, "evidence", row.id, "update")
    await session.commit()
    return EvidenceOut(id=row.id, page_id=row.page_id, start_offset=row.start_offset, end_offset=row.end_offset, bbox=row.bbox, entity_type=row.entity_type, semantic_role=row.semantic_role, score=row.score, detector=row.detector, reason_codes=row.reason_codes, review_status=row.review_status, original_text=cipher.decrypt(row.encrypted_original))


@router.post("/requests/{request_id}/review/approve")
async def approve_review(request_id: UUID, payload: ReviewApprove, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    if not (principal.roles & {"admin", "reviewer"}):
        raise HTTPException(403, "Reviewer role required")
    request = await _request(session, request_id, principal)
    rows = list((await session.scalars(select(EntityEvidence).where(EntityEvidence.request_id == request.id, EntityEvidence.tenant_id == principal.tenant_id))).all())
    selected = set(payload.evidence_ids)
    for row in rows:
        if payload.confirm_all or row.id in selected:
            row.review_status = ReviewStatus.APPROVED
            row.reviewer_id = principal.user_id
    if all(row.review_status == ReviewStatus.APPROVED for row in rows):
        request.status = RequestStatus.REVIEW_APPROVED
    else:
        request.status = RequestStatus.REVIEW_REQUIRED
    await _audit(session, principal, "processing_request", request.id, "review_approve")
    await session.commit()
    return {"status": request.status, "approved_count": sum(row.review_status == ReviewStatus.APPROVED for row in rows), "total": len(rows)}


@router.post("/requests/{request_id}/pseudonymize", response_model=SafeTextOut)
async def pseudonymize(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    if request.status != RequestStatus.REVIEW_APPROVED:
        raise HTTPException(409, "All evidences must be reviewed before pseudonymization")
    request.status = RequestStatus.PSEUDONYMIZING
    original_text, documents = await _request_text(session, request.id, principal.tenant_id)
    evidences = list((await session.scalars(select(EntityEvidence).where(EntityEvidence.request_id == request.id).order_by(EntityEvidence.start_offset))).all())
    entities = []
    pseudo = Pseudonymizer(cipher)
    for evidence in evidences:
        entity = await session.scalar(select(ResolvedEntity).join(EntityOccurrence, EntityOccurrence.resolved_entity_id == ResolvedEntity.id).where(EntityOccurrence.evidence_id == evidence.id))
        if entity:
            from app.services.ner.detectors import EntityCandidate
            value = cipher.decrypt(evidence.encrypted_original)
            entities.append((EntityCandidate(evidence.start_offset, evidence.end_offset, value, evidence.entity_type, evidence.score, evidence.detector, semantic_role=evidence.semantic_role), entity.id))
    result = pseudo.apply(original_text, entities)
    for mapping in result.mappings:
        session.add(PseudonymMapping(tenant_id=principal.tenant_id, request_id=request.id, entity_id=UUID(mapping["entity_id"]), encrypted_original=mapping["encrypted_original"], pseudonym=mapping["pseudonym"], entity_type=mapping["entity_type"], strategy=mapping["strategy"], version=1))
    report = {"status": "PENDING", "issues": ["validation_required"], "replacement_count": len(result.replacements)}
    if not documents:
        raise HTTPException(409, "No extracted document available")
    revision = (await session.scalar(select(PseudonymizedText.revision).where(PseudonymizedText.request_id == request.id).order_by(PseudonymizedText.revision.desc()).limit(1)) or 0) + 1
    safe_text = PseudonymizedText(tenant_id=principal.tenant_id, request_id=request.id, document_id=documents[0].id, revision=revision, encrypted_text=cipher.encrypt(result.text), provenance_map=[{"source_start": item.start, "source_end": item.end, "target": item.replacement, "entity_id": str(item.entity_id), "mapping_version": item.mapping_version} for item in result.replacements], validation_report=report)
    session.add(safe_text)
    request.status = RequestStatus.VALIDATING
    await _audit(session, principal, "processing_request", request.id, "pseudonymize")
    await session.commit()
    return SafeTextOut(request_id=request.id, revision=revision, text=result.text, validation_report=report, approved=False)


@router.get("/requests/{request_id}/pseudonymized-text", response_model=SafeTextOut)
async def get_pseudonymized_text(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _request(session, request_id, principal)
    row = await session.scalar(select(PseudonymizedText).where(PseudonymizedText.request_id == request_id).order_by(PseudonymizedText.revision.desc()))
    if not row:
        raise HTTPException(404, "Pseudonymized text not found")
    return SafeTextOut(request_id=request_id, revision=row.revision, text=cipher.decrypt(row.encrypted_text), validation_report=row.validation_report, approved=row.approved_at is not None)


@router.post("/requests/{request_id}/validate", response_model=ValidationOut)
async def validate(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    row = await session.scalar(select(PseudonymizedText).where(PseudonymizedText.request_id == request_id).order_by(PseudonymizedText.revision.desc()))
    if not row:
        raise HTTPException(404, "Pseudonymized text not found")
    original, _ = await _request_text(session, request.id, principal.tenant_id)
    evidences = list((await session.scalars(select(EntityEvidence).where(EntityEvidence.request_id == request.id))).all())
    originals = [cipher.decrypt(item.encrypted_original) for item in evidences]
    result = validate_safe_text(original, cipher.decrypt(row.encrypted_text), originals, all(item.review_status == ReviewStatus.APPROVED for item in evidences))
    row.validation_report = result.report
    if result.status == "PASSED":
        row.approved_by = principal.user_id
        row.approved_at = datetime.now(UTC)
        request.status = RequestStatus.READY_TO_SEND
    else:
        request.status = RequestStatus.BLOCKED_LEAKAGE
    await _audit(session, principal, "processing_request", request.id, "validate", result.status.lower())
    await session.commit()
    return ValidationOut(status=result.status, report=result.report)


SCHEMA = {"type": "object", "additionalProperties": True, "properties": {"document_text": {"type": "string"}}}


@router.post("/requests/{request_id}/send")
async def send(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    if request.status != RequestStatus.READY_TO_SEND:
        raise HTTPException(409, "Request is not approved for outbound transmission")
    safe_row = await session.scalar(select(PseudonymizedText).where(PseudonymizedText.request_id == request.id).order_by(PseudonymizedText.revision.desc()))
    if not safe_row or safe_row.validation_report.get("status") != "PASSED":
        raise HTTPException(409, "Safe text validation gate has not passed")
    text = cipher.decrypt(safe_row.encrypted_text)
    evidences = list((await session.scalars(select(EntityEvidence).where(EntityEvidence.request_id == request.id))).all())
    originals = [cipher.decrypt(item.encrypted_original) for item in evidences]
    request.status = RequestStatus.SENDING
    await session.flush()
    started = time.perf_counter()
    api_call = ApiCall(tenant_id=principal.tenant_id, request_id=request.id, revision=safe_row.revision, outbound_text_snapshot=text, outbound_payload_snapshot={"input": text, "schema": SCHEMA}, model=settings.openai_model, schema_version="v1", status="SENDING")
    session.add(api_call)
    await session.flush()
    try:
        completion = SafeOpenAIClient(settings).complete(text, SCHEMA, originals)
        api_call.openai_response_id = completion.response_id
        api_call.token_usage = completion.usage
        api_call.latency_ms = completion.latency_ms
        api_call.status = "SUCCEEDED"
        session.add(ApiResponse(tenant_id=principal.tenant_id, api_call_id=api_call.id, pseudonymized_json=completion.payload, validation_status="VALIDATED", mapping_version=safe_row.revision))
        request.status = RequestStatus.RESPONSE_RECEIVED
        await _audit(session, principal, "api_call", api_call.id, "send")
        await session.commit()
        return {"api_call_id": str(api_call.id), "status": api_call.status, "response": completion.payload}
    except Exception as exc:
        api_call.status = "FAILED"
        api_call.error_code = type(exc).__name__
        api_call.latency_ms = int((time.perf_counter() - started) * 1000)
        request.status = RequestStatus.FAILED
        await session.commit()
        raise HTTPException(502, "Provider call failed; no original data was sent") from exc


@router.get("/requests/{request_id}/api-calls")
async def api_calls(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _request(session, request_id, principal)
    rows = list((await session.scalars(select(ApiCall).where(ApiCall.request_id == request_id, ApiCall.tenant_id == principal.tenant_id).order_by(ApiCall.created_at.desc()))).all())
    return [{"id": str(row.id), "revision": row.revision, "text": row.outbound_text_snapshot, "model": row.model, "status": row.status, "usage": row.token_usage, "response_id": row.openai_response_id, "error_code": row.error_code} for row in rows]


@router.get("/api-calls/{api_call_id}/response")
async def api_response(api_call_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    row = await session.get(ApiCall, api_call_id)
    if not row or row.tenant_id != principal.tenant_id:
        raise HTTPException(404, "API call not found")
    response = await session.scalar(select(ApiResponse).where(ApiResponse.api_call_id == api_call_id))
    if not response:
        raise HTTPException(404, "API response not found")
    return {"api_call_id": str(api_call_id), "status": response.validation_status, "json": response.pseudonymized_json}


@router.post("/api-calls/{api_call_id}/restore", response_model=RestoreOut)
async def restore(api_call_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    require_original_access(principal)
    call = await session.get(ApiCall, api_call_id)
    if not call or call.tenant_id != principal.tenant_id:
        raise HTTPException(404, "API call not found")
    response = await session.scalar(select(ApiResponse).where(ApiResponse.api_call_id == api_call_id))
    if not response:
        raise HTTPException(404, "API response not found")
    mappings_rows = list((await session.scalars(select(PseudonymMapping).where(PseudonymMapping.request_id == call.request_id))).all())
    mappings = {str(row.entity_id): {"pseudonym": row.pseudonym, "original": cipher.decrypt(row.encrypted_original)} for row in mappings_rows}
    restore_status, restored, issues = restore_typed(response.pseudonymized_json, mappings)
    response.validation_status = restore_status
    if restored is not None:
        response.restored_json_encrypted = cipher.encrypt_json(restored)
        request = await session.get(ProcessingRequest, call.request_id)
        if request:
            request.status = RequestStatus.COMPLETED
    else:
        request = await session.get(ProcessingRequest, call.request_id)
        if request:
            request.status = RequestStatus.RESTORE_REVIEW_REQUIRED
    await _audit(session, principal, "api_response", response.id, "restore", restore_status.lower())
    await session.commit()
    return RestoreOut(api_call_id=api_call_id, status=restore_status, restored=restored if restored is not None else {"issues": issues})


@router.get("/api-calls/{api_call_id}/restored")
async def get_restored(api_call_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    require_original_access(principal)
    call = await session.get(ApiCall, api_call_id)
    if not call or call.tenant_id != principal.tenant_id:
        raise HTTPException(404, "API call not found")
    response = await session.scalar(select(ApiResponse).where(ApiResponse.api_call_id == api_call_id))
    if not response or not response.restored_json_encrypted:
        raise HTTPException(404, "Restored response not available")
    await _audit(session, principal, "api_response", response.id, "read_restored")
    await session.commit()
    return {"api_call_id": str(api_call_id), "json": cipher.decrypt_json(response.restored_json_encrypted)}


@router.get("/requests/{request_id}/audit")
async def audit(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    await _request(session, request_id, principal)
    rows = list((await session.scalars(select(AuditEvent).where(AuditEvent.tenant_id == principal.tenant_id, AuditEvent.resource_id == request_id).order_by(AuditEvent.timestamp))).all())
    return [{"action": row.action, "outcome": row.outcome, "resource_type": row.resource_type, "timestamp": row.timestamp, "correlation_id": row.correlation_id} for row in rows]


@router.delete("/requests/{request_id}", status_code=204)
async def delete_request(request_id: UUID, session: AsyncSession = Depends(session_dep), principal: Principal = Depends(get_principal)):
    request = await _request(session, request_id, principal)
    documents = list((await session.scalars(select(Document).where(Document.request_id == request.id))).all())
    for document in documents:
        Path(document.storage_path).unlink(missing_ok=True)
    request.status = RequestStatus.CANCELLED
    await _audit(session, principal, "processing_request", request.id, "retention_delete")
    await session.commit()
