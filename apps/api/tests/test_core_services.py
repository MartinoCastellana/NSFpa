from uuid import uuid4

from app.core.crypto import EnvelopeCipher
from app.services.ner import detect_pii
from app.services.pseudonymization import Pseudonymizer
from app.services.restoration import restore_typed
from app.services.validation import validate_safe_text


def test_crypto_roundtrip():
    cipher = EnvelopeCipher("test-key")
    value = "Martino Castellana"
    assert cipher.decrypt(cipher.encrypt(value)) == value


def test_italian_detectors_and_roles():
    text = (
        "Il richiedente Martino Castellana, nato a Lecce il 21/02/1997, email martino@example.test."
    )
    found = detect_pii(text)
    kinds = {item.entity_type for item in found}
    assert "PERSON" in kinds
    assert "BIRTH_PLACE" in kinds
    assert "BIRTH_DATE" in kinds
    assert "EMAIL" in kinds
    assert any(item.semantic_role == "applicant" for item in found if item.entity_type == "PERSON")


def test_replacement_offsets_are_reversible():
    cipher = EnvelopeCipher("test-key")
    source = "Il richiedente Martino Castellana, email martino@example.test."
    entity = next(item for item in detect_pii(source) if item.entity_type == "PERSON")
    entity_id = uuid4()
    result = Pseudonymizer(cipher).apply(source, [(entity, entity_id)])
    assert entity.text not in result.text
    mapping = result.mappings[0]
    restored = {str(entity_id): {"pseudonym": mapping["pseudonym"], "original": entity.text}}
    status, payload, issues = restore_typed(
        {"richiedente": {"value": mapping["pseudonym"], "entity_id": str(entity_id)}}, restored
    )
    assert status == "RESTORED"
    assert not issues
    assert payload["richiedente"]["value"] == entity.text


def test_validation_blocks_original_leakage_and_unapproved_text():
    result = validate_safe_text(
        "Mario mario@example.test",
        "Mario mario@example.test",
        ["mario@example.test"],
        approved=False,
    )
    assert result.status == "BLOCKED"
    assert "original_value_residual" in result.report["issues"]
