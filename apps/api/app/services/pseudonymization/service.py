import re
from dataclasses import dataclass
from uuid import UUID

from app.core.crypto import EnvelopeCipher
from app.services.ner.detectors import EntityCandidate


@dataclass(frozen=True)
class Replacement:
    start: int
    end: int
    replacement: str
    entity_id: UUID
    mapping_version: int


@dataclass(frozen=True)
class PseudonymizedResult:
    text: str
    replacements: list[Replacement]
    mappings: list[dict]


class Pseudonymizer:
    def __init__(self, cipher: EnvelopeCipher):
        self.cipher = cipher
        self._used: set[str] = set()

    def generate(self, entity_type: str, ordinal: int) -> str:
        pools = {
            "PERSON": ["Mario Rossi", "Giulia Bianchi", "Luca Ferri", "Anna Romano"],
            "BIRTH_PLACE": ["Roma", "Milano", "Bologna", "Torino"],
            "BIRTH_DATE": ["15/06/1985", "08/11/1978", "22/03/1990"],
            "ADDRESS": ["Via Roma 25", "Via Verdi 14", "Piazza Italia 8"],
            "EMAIL": ["EMAIL_001", "EMAIL_002"],
            "PHONE": ["+39 300 0000000", "+39 301 0000000"],
            "TAX_ID": ["TAX_ID_001", "TAX_ID_002"],
            "VAT_ID": ["VAT_ID_001", "VAT_ID_002"],
            "IBAN": ["IBAN_001"],
        }
        values = pools.get(entity_type, [f"{entity_type}_{ordinal:03d}"])
        for value in values:
            if value not in self._used:
                self._used.add(value)
                return value
        value = f"{entity_type}_{ordinal:03d}"
        self._used.add(value)
        return value

    def apply(self, text: str, entities: list[tuple[EntityCandidate, UUID]]) -> PseudonymizedResult:
        replacements: list[Replacement] = []
        mappings: list[dict] = []
        for ordinal, (entity, entity_id) in enumerate(entities, start=1):
            pseudonym = self.generate(entity.entity_type, ordinal)
            replacements.append(Replacement(entity.start, entity.end, pseudonym, entity_id, 1))
            mappings.append(
                {
                    "entity_id": str(entity_id),
                    "encrypted_original": self.cipher.encrypt(entity.text),
                    "pseudonym": pseudonym,
                    "entity_type": entity.entity_type,
                    "strategy": "synthetic-local-v1",
                    "version": 1,
                }
            )
        output = text
        for item in sorted(replacements, key=lambda replacement: replacement.start, reverse=True):
            output = output[: item.start] + item.replacement + output[item.end :]
        return PseudonymizedResult(output, replacements, mappings)


def normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
