"""Detached-JWS request signing for the sanity suite.

Mirrors the Bridge's local verification contract exactly: the signing input is
``base64url(protected_header)`` + ``.`` + ``base64url(canonical_json(body))`` where
canonical JSON is compact, UTF-8, sort-keys (``orjson`` ``OPT_SORT_KEYS``). The
result is a detached JWS (``header..signature``) sent in the ``Signature`` header.

Used so the sanity suite can exercise the *signed* Partner API (auth on). The key
is the committed TEST-ONLY key under ``test/keys`` — never a production key.
"""

from __future__ import annotations

import logging

import orjson
from joserfc import jws
from joserfc.jwk import import_key

_logger = logging.getLogger("sanity")


class RequestSigner:
    def __init__(self, key_path: str, kid: str = "", algorithm: str = "ES256"):
        self.key_path = key_path
        self.kid = kid
        self.algorithm = algorithm
        self._key = None

    def _load(self):
        if self._key is None:
            with open(self.key_path, encoding="utf-8") as handle:
                self._key = import_key(orjson.loads(handle.read()))
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
        header = {"alg": self.algorithm}
        if self.kid:
            header["kid"] = self.kid
        full = jws.serialize_compact(header, payload, key, algorithms=[self.algorithm])
        part1, _payload, part3 = full.split(".")
        return f"{part1}..{part3}"
