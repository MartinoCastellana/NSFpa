from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    entity_type: str
    semantic_role: str | None
    confidence: float
    reason_codes: list[str]


class EntityClassifier:
    def classify(self, entity_type: str, context: str) -> Classification:
        raise NotImplementedError


class RuleEntityClassifier(EntityClassifier):
    """Offline NEC rules; optional spaCy/Presidio recognizers can be added behind this API."""

    def classify(self, entity_type: str, context: str) -> Classification:
        normalized = context.lower()
        if entity_type == "PERSON":
            for marker, role in (
                ("delegat", "delegate"),
                ("propriet", "owner"),
                ("testimone", "witness"),
                ("richied", "applicant"),
            ):
                if marker in normalized:
                    return Classification(entity_type, role, 0.92, ["role_keyword", marker])
            return Classification(entity_type, "person", 0.70, ["person_without_role"])
        if entity_type == "BIRTH_DATE" or (entity_type == "OTHER_PII" and "nasc" in normalized):
            return Classification("BIRTH_DATE", "birth_date", 0.90, ["birth_keyword"])
        if entity_type == "BIRTH_PLACE":
            return Classification(entity_type, "birthplace", 0.92, ["birthplace_keyword"])
        if entity_type == "ADDRESS":
            return Classification(entity_type, "residence", 0.90, ["residence_keyword"])
        return Classification(entity_type, None, 0.86, ["detector_type"])
