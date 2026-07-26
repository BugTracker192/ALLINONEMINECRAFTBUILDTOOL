from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode


class ArtifactSigner:
    """HMAC signer for short-lived artifact URLs.

    Tokens bind the artifact path, user-visible filename, and expiry.  The
    implementation is intentionally stateless so multiple API replicas can
    validate the same URL when configured with the same secret.
    """

    def __init__(self, secret: str, ttl_seconds: int = 900) -> None:
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = max(30, int(ttl_seconds))

    @property
    def enabled(self) -> bool:
        return bool(self._secret)

    def signature(self, resource: str, filename: str, expires: int) -> str:
        message = f"{resource}\n{filename}\n{expires}".encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def create_query(self, resource: str, filename: str, now: int | None = None) -> str:
        if not self.enabled:
            return urlencode({"filename": filename})
        expires = int(now if now is not None else time.time()) + self.ttl_seconds
        return urlencode({"filename": filename, "expires": expires, "signature": self.signature(resource, filename, expires)})

    def verify(self, resource: str, filename: str, expires: int | None, signature: str | None, now: int | None = None) -> bool:
        if not self.enabled or expires is None or not signature:
            return False
        current = int(now if now is not None else time.time())
        if expires < current or expires > current + self.ttl_seconds + 30:
            return False
        expected = self.signature(resource, filename, expires)
        return hmac.compare_digest(signature, expected)
