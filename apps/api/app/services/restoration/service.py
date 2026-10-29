from typing import Any

from app.services.pseudonymization.service import normalize_for_match

ALLOWED_PERSONAL_FIELDS = {
    "richiedente",
    "luogo_nascita",
    "data_nascita",
    "indirizzo",
    "email",
    "telefono",
}


def restore_typed(
    payload: dict[str, Any], mappings: dict[str, dict[str, str]]
) -> tuple[str, dict[str, Any] | None, list[str]]:
    """Restore only typed object fields with a matching opaque entity_id and pseudonym."""
    restored = dict(payload)
    issues: list[str] = []
    safe_values = [
        normalize_for_match(str(item.get("pseudonym", "")))
        for item in mappings.values()
        if item.get("pseudonym")
    ]
    for field in ALLOWED_PERSONAL_FIELDS:
        value = payload.get(field)
        if not isinstance(value, dict):
            continue
        entity_id = value.get("entity_id")
        safe_value = value.get("value")
        mapping = mappings.get(str(entity_id))
        if not mapping or not isinstance(safe_value, str):
            issues.append(f"{field}:missing_or_unknown_entity")
            continue
        if normalize_for_match(safe_value) != normalize_for_match(mapping["pseudonym"]):
            issues.append(f"{field}:pseudonym_mismatch")
            continue
        restored[field] = {**value, "value": mapping["original"]}
    # A free-text answer is deliberately never rewritten. If it contains a safe
    # pseudonym, automatic restore would be an unsafe global replacement.
    for field, value in payload.items():
        if field in ALLOWED_PERSONAL_FIELDS or not isinstance(value, str):
            continue
        normalized = normalize_for_match(value)
        if any(safe and safe in normalized for safe in safe_values):
            issues.append(f"{field}:untyped_pseudonym")
    if issues:
        return "RESTORE_REVIEW_REQUIRED", None, issues
    return "RESTORED", restored, []
