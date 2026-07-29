from __future__ import annotations

from mbi import hashing


def test_nonsecurity_hash_explicitly_disables_fips_security_use(
    monkeypatch,
) -> None:
    calls = []

    class Digest:
        def digest(self) -> bytes:
            return b"\0\0\0"

    def blake2s(data: bytes, **kwargs):
        calls.append((data, kwargs))
        return Digest()

    monkeypatch.setattr(hashing.hashlib, "blake2s", blake2s)
    assert hashing.nonsecurity_blake2s(b"palette", digest_size=3).digest()
    assert calls == [
        (
            b"palette",
            {
                "usedforsecurity": False,
                "digest_size": 3,
            },
        )
    ]
