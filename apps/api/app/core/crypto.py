import base64
import hashlib
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EnvelopeCipher:
    """AES-GCM envelope cipher; production should source the key from a KMS/secret manager."""

    def __init__(self, key_material: str):
        digest = hashlib.sha256(key_material.encode("utf-8")).digest()
        self._key = digest

    def encrypt(self, value: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, value.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, value: str) -> str:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        return AESGCM(self._key).decrypt(raw[:12], raw[12:], None).decode("utf-8")

    def encrypt_json(self, value: Any) -> str:
        return self.encrypt(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def decrypt_json(self, value: str) -> Any:
        return json.loads(self.decrypt(value))
