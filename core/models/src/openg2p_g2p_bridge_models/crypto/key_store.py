"""Filesystem-backed store of partner public keys for inbound JWS verification.

This replaces the remote Keymanager certificate lookup. Each partner gets one
JWKS file named ``<reference_id>.json`` inside ``keys_dir`` — e.g.
``PARTNER_MY_PSP.json`` for reference id ``PARTNER_MY_PSP`` (the value
``JWTValidationHelper`` derives from ``sender_app_mnemonic``). Each file is a
standard JWKS (``{"keys": [ ... ]}``) holding one or more public keys, each with
a ``kid`` and ``alg``.

Multiple keys per partner make rotation an overlap operation: register the new
key, let the partner switch signing to it, then drop the old key — no coordinated
cutover, because lookup is by ``kid``. The directory is normally mounted from a
Kubernetes Secret/ConfigMap; files are cached and reloaded automatically when
their mtime changes.
"""

import json
import logging
import os
import threading

_logger = logging.getLogger("openg2p_g2p_bridge_models.crypto.key_store")


class PartnerKeyStore:
    def __init__(self, keys_dir):
        self.keys_dir = keys_dir
        self._cache = {}  # reference_id -> (mtime, list[jwk dict])
        self._lock = threading.Lock()

    def _path_for(self, reference_id):
        # reference_id is an opaque token like PARTNER_MY_PSP. Reject anything
        # that could escape keys_dir.
        if not reference_id or "/" in reference_id or os.sep in reference_id or ".." in reference_id:
            return None
        return os.path.join(self.keys_dir, f"{reference_id}.json")

    def get_keys(self, reference_id):
        """Return the partner's JWK dicts (a JWKS ``keys`` list), or None if unknown."""
        if not self.keys_dir:
            return None
        path = self._path_for(reference_id)
        if not path or not os.path.isfile(path):
            _logger.warning("No partner key file for reference id '%s'", reference_id)
            return None
        mtime = os.path.getmtime(path)
        with self._lock:
            cached = self._cache.get(reference_id)
            if cached and cached[0] == mtime:
                return cached[1]
        try:
            with open(path, encoding="utf-8") as handle:
                jwks = json.load(handle)
            keys = jwks.get("keys") if isinstance(jwks, dict) else None
            if not isinstance(keys, list) or not keys:
                _logger.error("Partner JWKS for '%s' has no 'keys' array", reference_id)
                return None
        except Exception:
            _logger.exception("Failed to load partner JWKS for '%s'", reference_id)
            return None
        with self._lock:
            self._cache[reference_id] = (mtime, keys)
        return keys
