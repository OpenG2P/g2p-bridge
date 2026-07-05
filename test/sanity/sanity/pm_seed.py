"""Register the Bridge (and, for the trial, its test partners) in Partner Manager (PM).

The Bridge no longer stores partner keys — it verifies inbound signatures against
public keys served by PM, and SPAR verifies the Bridge's resolve calls the same way.
So two things must exist in PM:

  * PARTNER_G2P_BRIDGE — the Bridge's OWN public key, derived from its signing .p12.
    Onboarding this is the Bridge's own responsibility (production too) so SPAR can
    verify it — customers are not expected to register it by hand.
  * PARTNER_TEST_SANITY / PARTNER_TRAINING — the trial test partners (from the
    committed test cert) so the sanity suite and Postman walkthrough can call the
    Bridge. Only when the trial test partner is enabled.

This module onboards each (idempotently, via PM's admin request→approve flow) and is
safe to run on every install/upgrade.

Env (set by the pm-register Helm Job):
  SANITY_PM_PARTNER_API_URL   PM partner-api base (key fetch / servability check)
  SANITY_PM_ADMIN_URL         PM staff-portal-api base (onboarding/approve)
  SANITY_PM_TOKEN_URL         Keycloak token endpoint (client-credentials)
  SANITY_PM_CLIENT_ID         Keycloak client with the `partner_manager` role
  SANITY_PM_CLIENT_SECRET     that client's secret
  SANITY_VERIFY_TLS           "false" to skip TLS verification
  # Self (the Bridge's own key) — derived from the mounted signing .p12:
  SANITY_PM_SELF_PARTNER_IDS  comma-separated ids to register with the .p12 key (e.g. PARTNER_G2P_BRIDGE)
  SANITY_PM_SIGNING_KEY_PATH  path to the Bridge's signing .p12
  SANITY_PM_SIGNING_KEY_PASSWORD  its password
  SANITY_PM_SELF_KID          kid to register (blank → the cert's SHA-256 thumbprint)
  # Test partners (trial only) — from a committed public cert:
  SANITY_PM_TEST_PARTNER_IDS  comma-separated ids (e.g. PARTNER_TEST_SANITY,PARTNER_TRAINING)
  SANITY_PM_TEST_CERT_PEM     the public certificate (PEM)
  SANITY_PM_TEST_KID          kid the test partners sign with (blank → cert thumbprint)
  SANITY_PM_ALGORITHM         JWS algorithm (default RS256)
"""
import base64
import os

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12


def _env(name, default=""):
    return os.environ.get(name, default)


def _verify_tls() -> bool:
    return _env("SANITY_VERIFY_TLS", "true").lower() not in ("false", "0", "no")


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _cert_public_pem_kid(cert, override_kid: str):
    """SPKI public PEM + kid (override or the cert's SHA-256 thumbprint) from an x509 cert."""
    pub_pem = cert.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    kid = override_kid or _b64u(cert.fingerprint(hashes.SHA256()))
    return pub_pem, kid


def _from_p12(path: str, password: str, override_kid: str):
    with open(path, "rb") as fh:
        data = fh.read()
    _key, cert, _extra = pkcs12.load_key_and_certificates(
        data, password.encode() if password else None
    )
    if cert is None:
        raise ValueError(f"{path}: PKCS#12 has no certificate")
    return _cert_public_pem_kid(cert, override_kid)


def _from_cert_pem(cert_pem: str, override_kid: str):
    from cryptography.x509 import load_pem_x509_certificate

    cert = load_pem_x509_certificate(cert_pem.encode("utf-8"))
    return _cert_public_pem_kid(cert, override_kid)


def _admin_token(token_url, client_id, client_secret, verify):
    if not (token_url and client_secret):
        return None
    r = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        verify=verify,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _servable(partner_api_url, partner_id, kid, verify) -> bool:
    if not partner_api_url:
        return False
    url = f"{partner_api_url}/keys/{partner_id}/{kid}"
    return httpx.get(url, verify=verify, timeout=20).status_code == 200


def ensure_partner(cfg, partner_id, public_pem, kid) -> str:
    """Ensure one partner+key exists and is servable in PM. Returns the outcome."""
    if _servable(cfg["partner_api_url"], partner_id, kid, cfg["verify"]):
        return "exists"
    if not cfg["admin_url"]:
        raise RuntimeError(f"{partner_id}: key not servable and SANITY_PM_ADMIN_URL not set")

    admin, token = cfg["admin_url"], cfg["token"]
    key_input = {"public_key": public_pem, "kid": kid, "algorithm": cfg["algorithm"]}

    r = httpx.post(
        f"{admin}/partners/requests/onboarding",
        headers=_headers(token),
        json={
            "partner_id": partner_id,
            "name": f"{partner_id} (G2P Bridge)",
            "org_name": "OpenG2P G2P Bridge",
            "description": "Registered automatically by the G2P Bridge.",
            "keys": [key_input],
        },
        verify=cfg["verify"],
        timeout=30,
    )
    outcome = "onboarded"
    if r.status_code == 409:
        outcome = "key-added"
        httpx.post(
            f"{admin}/partners/{partner_id}/enable",
            headers=_headers(token), verify=cfg["verify"], timeout=20,
        )
        r = httpx.post(
            f"{admin}/partners/requests/key-update",
            headers=_headers(token),
            json={"partner_id": partner_id, "keys": [key_input]},
            verify=cfg["verify"],
            timeout=30,
        )
    if r.status_code in (401, 403):
        raise RuntimeError(
            f"{partner_id}: PM admin API rejected the request ({r.status_code}). The "
            f"client '{cfg['client_id']}' needs the 'partner_manager' role in the staff "
            f"realm (token_sent={token is not None})."
        )
    r.raise_for_status()
    request_id = r.json()["id"]

    httpx.post(
        f"{admin}/partners/requests/{request_id}/approve",
        headers=_headers(token),
        json={"notes": "auto-approved by G2P Bridge pm-register"},
        verify=cfg["verify"],
        timeout=30,
    ).raise_for_status()

    if not _servable(cfg["partner_api_url"], partner_id, kid, cfg["verify"]):
        raise RuntimeError(f"{partner_id}: onboarded but key '{kid}' still not servable")
    return outcome


def _entries():
    """Yield (partner_id, public_pem, kid) — the Bridge's own key first, then test partners."""
    self_ids = [p.strip() for p in _env("SANITY_PM_SELF_PARTNER_IDS").split(",") if p.strip()]
    key_path = _env("SANITY_PM_SIGNING_KEY_PATH")
    if self_ids and key_path and os.path.exists(key_path):
        pub, kid = _from_p12(key_path, _env("SANITY_PM_SIGNING_KEY_PASSWORD"), _env("SANITY_PM_SELF_KID"))
        for pid in self_ids:
            yield pid, pub, kid

    test_ids = [p.strip() for p in _env("SANITY_PM_TEST_PARTNER_IDS").split(",") if p.strip()]
    cert_pem = _env("SANITY_PM_TEST_CERT_PEM")
    if test_ids and cert_pem:
        pub, kid = _from_cert_pem(cert_pem, _env("SANITY_PM_TEST_KID"))
        for pid in test_ids:
            yield pid, pub, kid


def main() -> int:
    partner_api_url = _env("SANITY_PM_PARTNER_API_URL").rstrip("/")
    if not partner_api_url:
        print("[pm-register] SANITY_PM_PARTNER_API_URL not set — nothing to do; skipping")
        return 0
    entries = list(_entries())
    if not entries:
        print("[pm-register] no partners configured to register — skipping")
        return 0

    verify = _verify_tls()
    cfg = {
        "partner_api_url": partner_api_url,
        "admin_url": _env("SANITY_PM_ADMIN_URL").rstrip("/"),
        "algorithm": _env("SANITY_PM_ALGORITHM", "RS256"),
        "client_id": _env("SANITY_PM_CLIENT_ID", "commons-services-staff-portal"),
        "verify": verify,
    }
    try:
        cfg["token"] = _admin_token(
            _env("SANITY_PM_TOKEN_URL"), cfg["client_id"], _env("SANITY_PM_CLIENT_SECRET"), verify,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[pm-register] could not obtain PM admin token: {exc}")
        return 1

    rc = 0
    for pid, pub, kid in entries:
        try:
            print(f"[pm-register] {pid} (kid={kid}): {ensure_partner(cfg, pid, pub, kid)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[pm-register] {pid}: FAILED — {exc}")
            rc = 1
    return rc


if __name__ == "__main__":
    import sys

    sys.exit(main())
