"""Local (Keymanager-free) JWS sign/verify helper.

Drop-in replacement for ``openg2p_fastapi_common.utils.crypto.KeymanagerCryptoHelper``:
it implements the same ``verify_jwt`` / ``create_jwt_token`` interface but does all
crypto in-process with ``joserfc``, resolving keys from a local store instead of
calling the remote Keymanager service.

* Inbound ``verify_jwt`` — verifies a detached JWS (``header..signature``) that a
  partner sends in the ``Signature`` header, against the partner's public key looked
  up by ``km_ref_id`` (e.g. ``PARTNER_<MNEMONIC>``).
* Outbound ``create_jwt_token`` — signs a payload with the Bridge's own private key
  and returns a detached JWS, for calls to downstream services (e.g. SPAR) that
  require a signature.

The signing input matches the established wire contract:
``base64url(protected_header) + "." + base64url(canonical_json(body))`` where
canonical JSON is compact, UTF-8, sort-keys (``orjson`` ``OPT_SORT_KEYS``) — i.e.
exactly what the Keymanager path produced, so partners need no change.
"""

import base64
import json
import logging

import orjson
from joserfc import jws
from joserfc.jwk import import_key
from openg2p_fastapi_common.utils.crypto import CryptoHelper

from .constants import (
    DEFAULT_ALLOWED_ALGORITHMS,
    DEFAULT_SIGNING_ALGORITHM,
    is_forbidden_algorithm,
)
from .key_store import PartnerKeyStore

_logger = logging.getLogger("openg2p_g2p_bridge_models.crypto.local_crypto_helper")


class LocalCryptoHelper(CryptoHelper):
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
        self._signing_key = None  # lazy-loaded JWK

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
        key_set = self._partner_key_store.get_keyset(km_ref_id)
        if key_set is None:
            _logger.error("No registered keys for partner '%s'", km_ref_id)
            return False
        if not self._algorithm_matches_key(key_set, header, alg):
            return False

        # Reconstruct the signed content: header . base64url(canonical(payload)) . signature
        if payload is None:
            if not part2:
                _logger.error("Detached JWS supplied without a payload to verify against")
                return False
            verifiable = orig_jwt
        else:
            verifiable = f"{part1}.{self._b64u(self._canonical(payload))}.{part3}"

        try:
            jws.deserialize_compact(verifiable, key_set, algorithms=[alg])
        except Exception:
            _logger.exception("JWS signature verification failed for partner '%s'", km_ref_id)
            return False
        _logger.info(
            "JWS signature verified for partner '%s' (alg=%s, kid=%s)",
            km_ref_id,
            alg,
            header.get("kid"),
        )
        return True

    # ------------------------------- sign (outbound) ------------------------------

    async def create_jwt_token(self, payload, include_payload=False, **kwargs) -> str:
        key = self._load_signing_key()
        alg = kwargs.get("algorithm") or self._signing_algorithm
        if not self._is_algorithm_allowed(alg):
            raise ValueError(f"Signing algorithm '{alg}' is not in the allowed set")
        protected = {"alg": alg}
        kid = self._signing_key_kid or getattr(key, "kid", None)
        if kid:
            protected["kid"] = kid
        full = jws.serialize_compact(protected, self._canonical(payload), key, algorithms=[alg])
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
            jwk = json.load(handle)
        self._signing_key = import_key(jwk)
        return self._signing_key

    def _is_algorithm_allowed(self, alg):
        return bool(alg) and not is_forbidden_algorithm(alg) and alg in self.allowed_algorithms

    def _algorithm_matches_key(self, key_set, header, alg):
        kid = header.get("kid")
        if not kid:
            return True  # alg is already pinned via algorithms=[alg] on verify
        try:
            key = key_set.get_by_kid(kid)
        except Exception:
            _logger.error("No key with kid '%s' for this partner", kid)
            return False
        key_alg = self._key_alg(key)
        if key_alg and key_alg != alg:
            _logger.error("Header alg '%s' does not match registered key alg '%s'", alg, key_alg)
            return False
        return True

    @staticmethod
    def _key_alg(key):
        try:
            return key.as_dict().get("alg")
        except Exception:
            return None

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
