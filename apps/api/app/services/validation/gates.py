import re
from dataclasses import dataclass

from app.services.pseudonymization.service import normalize_for_match


@dataclass(frozen=True)
class ValidationResult:
    status: str
    report: dict


SENSITIVE_PATTERNS = [
    re.compile(
        r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b", re.I
    ),
    re.compile(r"\bIT\d{2}[A-Z]\d{22}\b", re.I),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
]


def validate_safe_text(
    original_text: str, safe_text: str, originals: list[str], approved: bool
) -> ValidationResult:
    residual_patterns = [
        pattern.pattern for pattern in SENSITIVE_PATTERNS if pattern.search(safe_text)
    ]
    leaked_originals = [
        value
        for value in originals
        if value and normalize_for_match(value) in normalize_for_match(safe_text)
    ]
    issues: list[str] = []
    if not approved:
        issues.append("manual_approval_required")
    if residual_patterns:
        issues.append("sensitive_pattern_residual")
    if leaked_originals:
        issues.append("original_value_residual")
    if not safe_text.strip():
        issues.append("empty_safe_text")
    status = "PASSED" if not issues else "BLOCKED"
    return ValidationResult(
        status,
        {
            "status": status,
            "issues": issues,
            "original_length": len(original_text),
            "safe_length": len(safe_text),
            "residual_patterns": residual_patterns,
            "leaked_value_count": len(leaked_originals),
            "limitations": [
                "Indirect re-identification and semantic leakage require human review."
            ],
        },
    )
