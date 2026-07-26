from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..errors import MBIError


class EncryptedKeyVault:
    """Small encrypted-at-rest key vault for self-hosted deployments.

    Production operators should supply MBI_KEY_VAULT_MASTER_KEY from a secret manager.
    The key is never serialized, logged, or returned from listing methods.
    """

    def __init__(self, path: Path, master_key: bytes | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._master_key = master_key or self._key_from_environment()
        if len(self._master_key) != 32:
            raise MBIError("KEY_VAULT_MASTER_KEY", "Key-vault master key must be exactly 32 bytes.")
        self._cipher = AESGCM(self._master_key)

    @staticmethod
    def _key_from_environment() -> bytes:
        encoded = os.getenv("MBI_KEY_VAULT_MASTER_KEY")
        if not encoded:
            raise MBIError(
                "KEY_VAULT_MASTER_KEY_MISSING",
                "MBI_KEY_VAULT_MASTER_KEY is required for persistent provider keys.",
            )
        try:
            return base64.urlsafe_b64decode(encoded)
        except Exception as exc:
            raise MBIError("KEY_VAULT_MASTER_KEY", "Key-vault master key is not valid URL-safe base64.") from exc

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MBIError("KEY_VAULT_CORRUPT", "Encrypted key vault could not be read.") from exc
        if not isinstance(payload, dict):
            raise MBIError("KEY_VAULT_CORRUPT", "Encrypted key vault root is invalid.")
        return payload

    def _write(self, payload: dict[str, dict[str, str]]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".writing")
        try:
            temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), "utf-8")
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _record_id(user_id: str, provider: str) -> str:
        if not user_id or not provider:
            raise MBIError("KEY_VAULT_ID", "User and provider identifiers are required.")
        return f"{user_id}:{provider}"

    def put(self, user_id: str, provider: str, api_key: str) -> None:
        if not api_key:
            raise MBIError("KEY_VAULT_EMPTY_KEY", "Provider API key cannot be empty.")
        record_id = self._record_id(user_id, provider)
        nonce = os.urandom(12)
        aad = record_id.encode("utf-8")
        encrypted = self._cipher.encrypt(nonce, api_key.encode("utf-8"), aad)
        with self._lock:
            payload = self._load()
            payload[record_id] = {
                "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
                "ciphertext": base64.urlsafe_b64encode(encrypted).decode("ascii"),
            }
            self._write(payload)

    def get(self, user_id: str, provider: str) -> str:
        record_id = self._record_id(user_id, provider)
        with self._lock:
            record = self._load().get(record_id)
        if record is None:
            raise MBIError("KEY_VAULT_NOT_FOUND", "Provider API key is not configured.")
        try:
            nonce = base64.urlsafe_b64decode(record["nonce"])
            encrypted = base64.urlsafe_b64decode(record["ciphertext"])
            return self._cipher.decrypt(nonce, encrypted, record_id.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            raise MBIError("KEY_VAULT_DECRYPT", "Provider API key could not be decrypted.") from exc

    def delete(self, user_id: str, provider: str) -> bool:
        record_id = self._record_id(user_id, provider)
        with self._lock:
            payload = self._load()
            removed = payload.pop(record_id, None) is not None
            self._write(payload)
        return removed

    def list_configured(self, user_id: str) -> list[str]:
        prefix = f"{user_id}:"
        with self._lock:
            keys = self._load()
        return sorted(record_id[len(prefix):] for record_id in keys if record_id.startswith(prefix))
