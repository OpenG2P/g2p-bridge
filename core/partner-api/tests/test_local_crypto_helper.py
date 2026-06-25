"""Unit tests for the local (Keymanager-free) JWS sign/verify helper.

These exercise the partner-signature verification path used by the Partner API and
the outbound signing path used for SPAR, with keys generated and stored locally —
no Keymanager. A partner "signs" a detached JWS exactly as the wire contract
expects (signing input = base64url(header) + "." + base64url(canonical_json(body)))
and the helper verifies it against a JWKS file on disk.
"""

import base64
import json

import orjson
import pytest
from joserfc import jws
from joserfc.jwk import generate_key
from openg2p_g2p_bridge_models.crypto import LocalCryptoHelper


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _canonical(body: dict) -> bytes:
    return orjson.dumps(body, option=orjson.OPT_SORT_KEYS)


def _partner_sign(body: dict, key, alg: str, kid: str) -> str:
    """Produce a detached JWS (header..signature) the way a partner would."""
    full = jws.serialize_compact({"alg": alg, "kid": kid}, _canonical(body), key, algorithms=[alg])
    part1, _payload, part3 = full.split(".")
    return f"{part1}..{part3}"


def _write_jwks(directory, reference_id, public_keys):
    path = directory / f"{reference_id}.json"
    path.write_text(json.dumps({"keys": public_keys}))


def _gen_ec(kid):
    return generate_key("EC", "P-256", {"kid": kid, "alg": "ES256", "use": "sig"})


BODY = {"request_header": {"sender_app_mnemonic": "my-psp"}, "amount": 100, "z": 1, "a": 2}


@pytest.mark.asyncio
async def test_verify_valid_signature(tmp_path):
    key = _gen_ec("psp-1")
    _write_jwks(tmp_path, "PARTNER_MY_PSP", [key.as_dict(private=False)])
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path))

    sig = _partner_sign(BODY, key, "ES256", "psp-1")
    assert await helper.verify_jwt(sig, payload=BODY, km_ref_id="PARTNER_MY_PSP") is True


@pytest.mark.asyncio
async def test_verify_rejects_tampered_payload(tmp_path):
    key = _gen_ec("psp-1")
    _write_jwks(tmp_path, "PARTNER_MY_PSP", [key.as_dict(private=False)])
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path))

    sig = _partner_sign(BODY, key, "ES256", "psp-1")
    tampered = {**BODY, "amount": 999}
    assert await helper.verify_jwt(sig, payload=tampered, km_ref_id="PARTNER_MY_PSP") is False


@pytest.mark.asyncio
async def test_verify_rejects_unknown_partner(tmp_path):
    key = _gen_ec("psp-1")
    _write_jwks(tmp_path, "PARTNER_MY_PSP", [key.as_dict(private=False)])
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path))

    sig = _partner_sign(BODY, key, "ES256", "psp-1")
    assert await helper.verify_jwt(sig, payload=BODY, km_ref_id="PARTNER_UNKNOWN") is False


@pytest.mark.asyncio
async def test_verify_rejects_hmac_algorithm(tmp_path):
    key = _gen_ec("psp-1")
    _write_jwks(tmp_path, "PARTNER_MY_PSP", [key.as_dict(private=False)])
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path))

    header = _b64u(json.dumps({"alg": "HS256", "kid": "psp-1"}).encode())
    forged = f"{header}..{_b64u(b'x')}"
    assert await helper.verify_jwt(forged, payload=BODY, km_ref_id="PARTNER_MY_PSP") is False


@pytest.mark.asyncio
async def test_verify_rejects_disallowed_algorithm(tmp_path):
    key = _gen_ec("psp-1")
    _write_jwks(tmp_path, "PARTNER_MY_PSP", [key.as_dict(private=False)])
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path), allowed_algorithms=("RS256",))

    sig = _partner_sign(BODY, key, "ES256", "psp-1")
    assert await helper.verify_jwt(sig, payload=BODY, km_ref_id="PARTNER_MY_PSP") is False


@pytest.mark.asyncio
async def test_verify_supports_key_rotation_by_kid(tmp_path):
    key1 = _gen_ec("psp-1")
    key2 = _gen_ec("psp-2")
    _write_jwks(
        tmp_path,
        "PARTNER_MY_PSP",
        [key1.as_dict(private=False), key2.as_dict(private=False)],
    )
    helper = LocalCryptoHelper(partner_keys_dir=str(tmp_path))

    sig_old = _partner_sign(BODY, key1, "ES256", "psp-1")
    sig_new = _partner_sign(BODY, key2, "ES256", "psp-2")
    assert await helper.verify_jwt(sig_old, payload=BODY, km_ref_id="PARTNER_MY_PSP") is True
    assert await helper.verify_jwt(sig_new, payload=BODY, km_ref_id="PARTNER_MY_PSP") is True


@pytest.mark.asyncio
async def test_verify_returns_false_without_key_store():
    helper = LocalCryptoHelper()  # no partner_keys_dir configured
    key = _gen_ec("psp-1")
    sig = _partner_sign(BODY, key, "ES256", "psp-1")
    assert await helper.verify_jwt(sig, payload=BODY, km_ref_id="PARTNER_MY_PSP") is False


@pytest.mark.asyncio
async def test_create_jwt_token_round_trip(tmp_path):
    signing_key = _gen_ec("bridge-1")
    key_path = tmp_path / "signing.json"
    key_path.write_text(json.dumps(signing_key.as_dict(private=True)))
    signer = LocalCryptoHelper(
        signing_key_path=str(key_path), signing_key_kid="bridge-1", signing_algorithm="ES256"
    )

    payload = {"resolve": [1, 2, 3], "b": 1, "a": 0}
    detached = await signer.create_jwt_token(payload)
    # Detached form: empty middle segment.
    assert detached.split(".")[1] == ""

    # A verifier holding the bridge public key accepts it.
    _write_jwks(tmp_path, "PARTNER_OPENG2P_BRIDGE", [signing_key.as_dict(private=False)])
    verifier = LocalCryptoHelper(partner_keys_dir=str(tmp_path))
    assert await verifier.verify_jwt(detached, payload=payload, km_ref_id="PARTNER_OPENG2P_BRIDGE") is True


@pytest.mark.asyncio
async def test_create_jwt_token_rejects_disallowed_algorithm(tmp_path):
    signing_key = _gen_ec("bridge-1")
    key_path = tmp_path / "signing.json"
    key_path.write_text(json.dumps(signing_key.as_dict(private=True)))
    signer = LocalCryptoHelper(
        signing_key_path=str(key_path), signing_algorithm="HS256", allowed_algorithms=("ES256",)
    )
    with pytest.raises(ValueError):
        await signer.create_jwt_token({"a": 1})
