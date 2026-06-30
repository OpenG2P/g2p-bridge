"""Detached-JWS request signing for the sanity suite.

Mirrors the Bridge's local (PyJWT) verification contract exactly: the signing input
is ``base64url(protected_header)`` + ``.`` + ``base64url(canonical_json(body))``
where canonical JSON is compact, UTF-8, sort-keys (``orjson`` ``OPT_SORT_KEYS``).
The result is a detached JWS (``header..signature``) sent in the ``Signature``
header.

Used so the sanity suite can exercise the *signed* Partner API (local backend, auth
on). The key is loaded from the committed TEST-ONLY PKCS#12 (.p12) keystore under
``test/keys`` (unlocked with its password) — never a production key.
"""

from __future__ import annotations

import base64
import logging

import orjson
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from jwt import PyJWS

_logger = logging.getLogger("sanity")


class RequestSigner:
    def __init__(self, key_path: str, password: str = "", kid: str = "", algorithm: str = "RS256"):
        self.key_path = key_path
        self.password = password
        self.kid = kid
        self.algorithm = algorithm
        self._key = None
        self._jws = PyJWS()

    def _load(self):
        if self._key is None:
            with open(self.key_path, "rb") as handle:
                data = handle.read()
            password = self.password.encode() if self.password else None
            private_key, cert, _extra = pkcs12.load_key_and_certificates(data, password)
            if private_key is None:
                raise ValueError("PKCS#12 keystore contains no private key")
            self._key = private_key
            if not self.kid and cert is not None:
                self.kid = base64.urlsafe_b64encode(cert.fingerprint(hashes.SHA256())).decode().rstrip("=")
        return self._key

    @property
    def available(self) -> bool:
        try:
            self._load()
            return True
        except Exception:
            _logger.warning("Request signer unavailable (key not loadable at %s)", self.key_path)
            return False

    def sign(self, body) -> str:
        key = self._load()
        payload = orjson.dumps(body, option=orjson.OPT_SORT_KEYS)
        headers = {"kid": self.kid} if self.kid else {}
        full = self._jws.encode(payload, key, algorithm=self.algorithm, headers=headers)
        part1, _payload, part3 = full.split(".")
        return f"{part1}..{part3}"
