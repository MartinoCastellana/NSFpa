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
    if issues:
        return "RESTORE_REVIEW_REQUIRED", None, issues
    return "RESTORED", restored, []
