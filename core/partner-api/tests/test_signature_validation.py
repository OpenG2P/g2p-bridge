"""Auth-on tests for inbound partner signature validation.

Two layers:

* ``RequestValidation.validate_signature`` — the gate that enforces/skips based on
  ``signature_validation_enabled``.
* ``JWTSignatureValidator`` end to end — a real partner-signed request flows
  through the partner-auth validator → ``JWTValidationHelper`` → ``LocalCryptoHelper``
  → local key store, exactly as it does on a live Partner API call (no Keymanager).
"""

import json
from unittest.mock import patch

import orjson
import pytest
from joserfc import jws
from joserfc.jwk import generate_key
from openg2p_fastapi_partner_auth.jwt_signature_validator import JWTSignatureValidator
from openg2p_fastapi_partner_auth.jwt_validation_helper import JWTValidationHelper
from openg2p_g2p_bridge_models.crypto import LocalCryptoHelper
from openg2p_g2p_bridge_models.errors import RequestValidationException
from openg2p_g2p_bridge_partner_api.services import request_validations
from openg2p_g2p_bridge_partner_api.services.request_validations import RequestValidation
from starlette.requests import Request


# --------------------------- the enforce/skip gate ---------------------------


@pytest.fixture
def restore_signature_flag():
    original = request_validations._config.signature_validation_enabled
    yield
    request_validations._config.signature_validation_enabled = original


def test_gate_skips_when_validation_disabled(restore_signature_flag):
    request_validations._config.signature_validation_enabled = False
    # Even an invalid signature passes when validation is off.
    assert RequestValidation().validate_signature(is_signature_valid=False) is None


def test_gate_accepts_valid_when_enabled(restore_signature_flag):
    request_validations._config.signature_validation_enabled = True
    assert RequestValidation().validate_signature(is_signature_valid=True) is None


def test_gate_rejects_invalid_when_enabled(restore_signature_flag):
    request_validations._config.signature_validation_enabled = True
    with pytest.raises(RequestValidationException):
        RequestValidation().validate_signature(is_signature_valid=False)


# ------------------------ end-to-end signature validation ------------------------


def _canonical(body: dict) -> bytes:
    return orjson.dumps(body, option=orjson.OPT_SORT_KEYS)


def _sign_detached(body: dict, key, alg: str, kid: str) -> str:
    full = jws.serialize_compact({"alg": alg, "kid": kid}, _canonical(body), key, algorithms=[alg])
    part1, _payload, part3 = full.split(".")
    return f"{part1}..{part3}"


def _make_request(body_bytes: bytes, signature) -> Request:
    headers = [(b"signature", signature.encode())] if signature is not None else []
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    return Request(scope, receive)


def _helper_for(tmp_path):
    """A JWTValidationHelper bound to a LocalCryptoHelper over tmp_path's key store."""
    local = LocalCryptoHelper(partner_keys_dir=str(tmp_path))
    helper = JWTValidationHelper()
    helper.crypto_helper = local
    return helper


def _onboard(tmp_path, reference_id, key):
    (tmp_path / f"{reference_id}.json").write_text(json.dumps({"keys": [key.as_dict(private=False)]}))


BODY = {"request_header": {"sender_app_mnemonic": "my-psp"}, "amount": 100}


@pytest.mark.asyncio
async def test_validator_accepts_valid_partner_signature(tmp_path):
    key = generate_key("EC", "P-256", {"kid": "psp-1", "alg": "ES256", "use": "sig"})
    _onboard(tmp_path, "PARTNER_MY_PSP", key)
    helper = _helper_for(tmp_path)

    sig = _sign_detached(BODY, key, "ES256", "psp-1")
    request = _make_request(json.dumps(BODY).encode(), sig)

    with patch.object(JWTValidationHelper, "get_component", return_value=helper):
        assert await JWTSignatureValidator()(request) is True


@pytest.mark.asyncio
async def test_validator_rejects_missing_signature_header(tmp_path):
    key = generate_key("EC", "P-256", {"kid": "psp-1", "alg": "ES256", "use": "sig"})
    _onboard(tmp_path, "PARTNER_MY_PSP", key)
    helper = _helper_for(tmp_path)

    request = _make_request(json.dumps(BODY).encode(), None)
    with patch.object(JWTValidationHelper, "get_component", return_value=helper):
        assert await JWTSignatureValidator()(request) is False


@pytest.mark.asyncio
async def test_validator_rejects_tampered_body(tmp_path):
    key = generate_key("EC", "P-256", {"kid": "psp-1", "alg": "ES256", "use": "sig"})
    _onboard(tmp_path, "PARTNER_MY_PSP", key)
    helper = _helper_for(tmp_path)

    sig = _sign_detached(BODY, key, "ES256", "psp-1")
    # Same signature, but the transmitted body is altered.
    tampered = {"request_header": {"sender_app_mnemonic": "my-psp"}, "amount": 999}
    request = _make_request(json.dumps(tampered).encode(), sig)
    with patch.object(JWTValidationHelper, "get_component", return_value=helper):
        assert await JWTSignatureValidator()(request) is False


@pytest.mark.asyncio
async def test_validator_rejects_unonboarded_partner(tmp_path):
    key = generate_key("EC", "P-256", {"kid": "psp-1", "alg": "ES256", "use": "sig"})
    # Onboard a different partner; the request comes from my-psp (unknown).
    _onboard(tmp_path, "PARTNER_OTHER", key)
    helper = _helper_for(tmp_path)

    sig = _sign_detached(BODY, key, "ES256", "psp-1")
    request = _make_request(json.dumps(BODY).encode(), sig)
    with patch.object(JWTValidationHelper, "get_component", return_value=helper):
        assert await JWTSignatureValidator()(request) is False
