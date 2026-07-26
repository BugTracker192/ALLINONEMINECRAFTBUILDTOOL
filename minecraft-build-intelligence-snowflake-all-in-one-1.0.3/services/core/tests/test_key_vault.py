from __future__ import annotations

import json
import os

import pytest

from mbi.ai import EncryptedKeyVault
from mbi.errors import MBIError


def test_encrypted_key_vault_round_trip_and_tamper(tmp_path) -> None:
    path = tmp_path / "vault.json"
    vault = EncryptedKeyVault(path, b"x" * 32)
    vault.put("user", "openai", "sk-super-secret")
    raw = path.read_text("utf-8")
    assert "sk-super-secret" not in raw
    assert vault.get("user", "openai") == "sk-super-secret"
    assert vault.list_configured("user") == ["openai"]
    assert os.stat(path).st_mode & 0o777 == 0o600
    payload = json.loads(raw)
    payload["user:openai"]["ciphertext"] = payload["user:openai"]["ciphertext"][:-2] + "AA"
    path.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(MBIError) as error:
        vault.get("user", "openai")
    assert error.value.code == "KEY_VAULT_DECRYPT"
