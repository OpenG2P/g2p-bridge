"""Local (Keymanager-free) JWS sign/verify helper, built on PyJWT.

Drop-in replacement for ``openg2p_fastapi_common.utils.crypto.KeymanagerCryptoHelper``:
same ``verify_jwt`` / ``create_jwt_token`` interface, but all crypto is done
in-process with **PyJWT** (+ ``cryptography``), resolving keys from a local store
instead of calling the remote Keymanager service.

This is the Bridge-local instance of the shared ``PyJWTCryptoHelper`` design
(see the OpenG2P platform docs). It is kept here for now; the strategic plan is to
move it into ``openg2p-fastapi-common`` ``partner_auth`` so every product shares
one implementation — at which point the Bridge swaps the one-line registration in
``app.py``. See ``docs/local-signature-verification.md``.

* Inbound ``verify_jwt`` — verifies a detached JWS (``header..signature``) sent by
  a partner in the ``Signature`` header, against the partner's public key looked up
  by ``km_ref_id`` (e.g. ``PARTNER_<MNEMONIC>``).
* Outbound ``create_jwt_token`` — signs a payload with the Bridge's own private key
  and returns a detached JWS, for downstream services (e.g. SPAR).

Signing input matches the established wire contract:
``base64url(protected_header)`` + ``.`` + ``base64url(canonical_json(body))`` where
canonical JSON is compact, UTF-8, sort-keys (``orjson`` ``OPT_SORT_KEYS``).
"""

import base64
import json
import logging

import orjson
from jwt import PyJWK, PyJWS
from openg2p_fastapi_common.utils.crypto import CryptoHelper

from .constants import (
    DEFAULT_ALLOWED_ALGORITHMS,
    DEFAULT_SIGNING_ALGORITHM,
    is_forbidden_algorithm,
)
from .key_store import PartnerKeyStore

_logger = logging.getLogger("openg2p_g2p_bridge_models.crypto.pyjwt_crypto_helper")


class PyJWTCryptoHelper(CryptoHelper):
    def __init__(
        self,
        *,
        partner_keys_dir=None,
        signing_key_path=None,
        signing_key_kid=None,
        signing_algorithm=DEFAULT_SIGNING_ALGORITHM,
        allowed_algorithms=None,
        name="",
        **kwargs,
    ):
        super().__init__(name=name)
        self.allowed_algorithms = tuple(allowed_algorithms or DEFAULT_ALLOWED_ALGORITHMS)
        self._partner_key_store = PartnerKeyStore(partner_keys_dir) if partner_keys_dir else None
        self._signing_key_path = signing_key_path
        self._signing_key_kid = signing_key_kid
        self._signing_algorithm = signing_algorithm
        self._signing_key = None  # lazy-loaded cryptography private key
        self._signing_kid = None  # kid read from the signing JWK on load
        self._jws = PyJWS()

    async def aclose(self):
        """No remote client to close; kept for interface parity."""

    # ------------------------------ verify (inbound) ------------------------------

    async def verify_jwt(self, orig_jwt, payload=None, km_app_id=None, km_ref_id=None, **kwargs) -> bool:
        if not orig_jwt:
            _logger.error("Empty JWS signature")
            return False
        try:
            part1, part2, part3 = orig_jwt.split(".")
        except ValueError:
            _logger.error("Malformed detached JWS; expected 'header..signature'")
            return False

        header = self._decode_header(part1)
        if header is None:
            return False
        alg = header.get("alg")
        if not self._is_algorithm_allowed(alg):
            _logger.error("Rejected JWS algorithm '%s' (not in allowed set %s)", alg, self.allowed_algorithms)
            return False

        if self._partner_key_store is None:
            _logger.error("Partner key store not configured; cannot verify signature")
            return False
        keys = self._partner_key_store.get_keys(km_ref_id)
        if not keys:
            _logger.error("No registered keys for partner '%s'", km_ref_id)
            return False

        candidates = self._candidate_keys(keys, header, alg)
        if not candidates:
            _logger.error("No registered key matches kid/alg for partner '%s'", km_ref_id)
            return False

        if payload is None:
            if not part2:
                _logger.error("Detached JWS supplied without a payload to verify against")
                return False
            verifiable = orig_jwt
        else:
            verifiable = f"{part1}.{self._b64u(self._canonical(payload))}.{part3}"

        for jwk in candidates:
            try:
                key = PyJWK.from_dict(jwk).key
                self._jws.decode(verifiable, key, algorithms=[alg])
            except Exception:
                continue
            _logger.info(
                "JWS signature verified for partner '%s' (alg=%s, kid=%s)",
                km_ref_id,
                alg,
                header.get("kid"),
            )
            return True

        _logger.error("JWS signature verification failed for partner '%s'", km_ref_id)
        return False

    # ------------------------------- sign (outbound) ------------------------------

    async def create_jwt_token(self, payload, include_payload=False, **kwargs) -> str:
        key = self._load_signing_key()
        alg = kwargs.get("algorithm") or self._signing_algorithm
        if not self._is_algorithm_allowed(alg):
            raise ValueError(f"Signing algorithm '{alg}' is not in the allowed set")
        headers = {}
        kid = self._signing_key_kid or self._signing_kid
        if kid:
            headers["kid"] = kid
        full = self._jws.encode(self._canonical(payload), key, algorithm=alg, headers=headers)
        part1, _part2, part3 = full.split(".")
        if include_payload:
            return full
        return f"{part1}..{part3}"

    # ---------------------------------- helpers -----------------------------------

    def _load_signing_key(self):
        if self._signing_key is not None:
            return self._signing_key
        if not self._signing_key_path:
            raise ValueError("Signing key path not configured; cannot create JWS")
        with open(self._signing_key_path, encoding="utf-8") as handle:
            jwk = orjson.loads(handle.read())
        self._signing_kid = jwk.get("kid")
        self._signing_key = PyJWK.from_dict(jwk).key
        return self._signing_key

    def _candidate_keys(self, keys, header, alg):
        """Keys eligible to verify this header: matching kid (if present) and a
        registered alg that is consistent with the header alg."""
        kid = header.get("kid")
        candidates = []
        for jwk in keys:
            if kid and jwk.get("kid") and jwk.get("kid") != kid:
                continue
            key_alg = jwk.get("alg")
            if key_alg and key_alg != alg:
                continue
            candidates.append(jwk)
        return candidates

    def _is_algorithm_allowed(self, alg):
        return bool(alg) and not is_forbidden_algorithm(alg) and alg in self.allowed_algorithms

    @staticmethod
    def _decode_header(part1):
        try:
            padded = part1 + "=" * (-len(part1) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))
        except Exception:
            _logger.exception("Failed to decode JWS protected header")
            return None

    @staticmethod
    def _canonical(payload) -> bytes:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload.encode()
        return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)

    @staticmethod
    def _b64u(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")
