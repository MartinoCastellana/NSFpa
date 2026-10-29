import re
from dataclasses import dataclass, field


@dataclass
class EntityCandidate:
    start: int
    end: int
    text: str
    entity_type: str
    score: float
    detector: str
    reason_codes: list[str] = field(default_factory=list)
    semantic_role: str | None = None
    page_index: int = 0
    bbox: dict[str, float] = field(default_factory=dict)


CF_RE = re.compile(
    r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b", re.I
)
VAT_RE = re.compile(r"\b(?:IT\s*)?\d{11}\b", re.I)
IBAN_RE = re.compile(r"\bIT\d{2}[A-Z]\d{22}\b", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+39[ .-]?)?3\d{2}[ .-]?\d{6,7}(?!\d)")
DATE_RE = re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}\b")
PERSON_RE = re.compile(
    r"\b(?:richiedente|delegato|delegata|proprietario|proprietaria|testimone|sig\.?|sig\.ra)\s+([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'-]+){1,3})"
)
PLACE_RE = re.compile(r"\b(?:nato|nata)\s+a\s+([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ' -]{2,50})", re.I)
ADDRESS_RE = re.compile(
    r"\b(?:residente|domiciliato|domiciliata|indirizzo)\s+(?:in\s+)?((?:via|viale|piazza|corso|strada)\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9 .,'/-]{3,80})",
    re.I,
)


def _candidate(
    match, entity_type: str, detector: str, score: float, text: str, reason: str, group: int = 0
) -> EntityCandidate:
    start, end = match.span(group)
    return EntityCandidate(start, end, text[start:end], entity_type, score, detector, [reason])


def detect_pii(text: str) -> list[EntityCandidate]:
    found: list[EntityCandidate] = []
    for regex, kind, detector, score, reason in [
        (IBAN_RE, "IBAN", "it-iban", 0.99, "iban_checksum_shape"),
        (CF_RE, "TAX_ID", "it-tax-code", 0.96, "tax_code_shape"),
        (VAT_RE, "VAT_ID", "it-vat", 0.91, "vat_shape"),
        (EMAIL_RE, "EMAIL", "email", 0.99, "email_shape"),
        (PHONE_RE, "PHONE", "phone-it", 0.90, "phone_shape"),
    ]:
        found.extend(
            _candidate(m, kind, detector, score, text, reason) for m in regex.finditer(text)
        )

    for match in DATE_RE.finditer(text):
        context = text[max(0, match.start() - 40) : match.start()].lower()
        if re.search(r"nato|nata|nascita|nascit[ao]", context):
            found.append(
                _candidate(match, "BIRTH_DATE", "context-date", 0.90, text, "birth_context")
            )
        else:
            found.append(
                _candidate(
                    match, "OTHER_PII", "ambiguous-date", 0.55, text, "date_without_birth_context"
                )
            )

    for match in PERSON_RE.finditer(text):
        found.append(
            _candidate(match, "PERSON", "italian-role-name", 0.88, text, "role_context", 1)
        )
    for match in PLACE_RE.finditer(text):
        found.append(
            _candidate(match, "BIRTH_PLACE", "birth-place-context", 0.87, text, "birth_context", 1)
        )
    for match in ADDRESS_RE.finditer(text):
        found.append(
            _candidate(
                match, "ADDRESS", "italian-address-context", 0.86, text, "residence_context", 1
            )
        )

    for item in found:
        context = text[max(0, item.start - 60) : min(len(text), item.end + 60)].lower()
        if item.entity_type == "PERSON":
            if "delegat" in context:
                item.semantic_role = "delegate"
            elif "propriet" in context:
                item.semantic_role = "owner"
            elif "testimone" in context:
                item.semantic_role = "witness"
            else:
                item.semantic_role = "applicant"
        elif item.entity_type == "BIRTH_PLACE":
            item.semantic_role = "birthplace"
        elif item.entity_type == "BIRTH_DATE":
            item.semantic_role = "birth_date"
        elif item.entity_type == "ADDRESS":
            item.semantic_role = "residence"
    return _deduplicate(found)


def _deduplicate(candidates: list[EntityCandidate]) -> list[EntityCandidate]:
    result: list[EntityCandidate] = []
    for candidate in sorted(
        candidates, key=lambda item: (item.start, -(item.end - item.start), -item.score)
    ):
        if any(
            candidate.start >= current.start and candidate.end <= current.end for current in result
        ):
            continue
        result = [
            current
            for current in result
            if not (current.start >= candidate.start and current.end <= candidate.end)
        ]
        result.append(candidate)
    return sorted(result, key=lambda item: item.start)
