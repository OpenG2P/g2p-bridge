"""Idempotent onboarding of the Bridge's test partners into Partner Manager (PM).

The Bridge no longer stores partner keys locally — it verifies inbound partner
signatures against public keys served by PM, and SPAR verifies the Bridge's
resolve calls the same way. So the signed sanity e2e needs the test partners to
exist and be active in PM with the public key the sanity/Bridge sign with:

  * PARTNER_TEST_SANITY  — the sanity suite signs its Bridge/SPAR calls as this.
  * PARTNER_TRAINING     — the Postman walkthrough signs as this (optional).
  * PARTNER_G2P_BRIDGE   — the Bridge signs its resolve calls to SPAR as this;
                           onboarding it lets SPAR verify the Bridge via PM.

All three share the committed TEST public certificate (test only). This module
onboards each (idempotently) via PM's admin API and approves it, so PM's
unauthenticated key-fetch API then serves the key. Safe to run on every
install/upgrade.

Env (set by the pm-seed Helm Job):
  SANITY_PM_PARTNER_API_URL  PM partner-api base (key fetch / servability check)
  SANITY_PM_ADMIN_URL        PM staff-portal-api base (onboarding/approve)
  SANITY_PM_TOKEN_URL        Keycloak token endpoint (client-credentials)
  SANITY_PM_CLIENT_ID        Keycloak client with the `partner_manager` role
  SANITY_PM_CLIENT_SECRET    that client's secret
  SANITY_PM_PARTNER_IDS      comma-separated partner ids to onboard
  SANITY_PM_KID              kid to register (must match how they sign)
  SANITY_PM_PUBLIC_CERT_PEM  the public certificate (PEM) to register
  SANITY_PM_ALGORITHM        JWS algorithm (default RS256)
  SANITY_VERIFY_TLS          "false" to skip TLS verification
"""
import os

import httpx


def _env(name, default=""):
    return os.environ.get(name, default)


def _verify_tls() -> bool:
    return _env("SANITY_VERIFY_TLS", "true").lower() not in ("false", "0", "no")


def _admin_token(token_url, client_id, client_secret, verify):
    """Client-credentials token for PM's admin API. None if creds are absent."""
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
    """True if PM already serves (partner_id, kid)."""
    if not partner_api_url:
        return False
    url = f"{partner_api_url}/keys/{partner_id}/{kid}"
    return httpx.get(url, verify=verify, timeout=20).status_code == 200


def ensure_partner(cfg, partner_id) -> str:
    """Ensure one partner+key exists and is servable in PM. Returns the outcome."""
    if _servable(cfg["partner_api_url"], partner_id, cfg["kid"], cfg["verify"]):
        return "exists"
    if not cfg["admin_url"]:
        raise RuntimeError(f"{partner_id}: key not servable and SANITY_PM_ADMIN_URL not set")

    admin = cfg["admin_url"]
    token = cfg["token"]
    key_input = {"public_key": cfg["cert_pem"], "kid": cfg["kid"], "algorithm": cfg["algorithm"]}

    r = httpx.post(
        f"{admin}/partners/requests/onboarding",
        headers=_headers(token),
        json={
            "partner_id": partner_id,
            "name": f"{partner_id} (G2P Bridge sanity)",
            "org_name": "OpenG2P G2P Bridge sanity suite",
            "description": "Persistent test partner for the G2P Bridge signed e2e. Test only.",
            "keys": [key_input],
        },
        verify=cfg["verify"],
        timeout=30,
    )
    outcome = "onboarded"
    if r.status_code == 409:
        # Already exists — (re)add the key and make sure the partner is enabled.
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
            f"{partner_id}: PM admin API rejected the seed ({r.status_code}). The "
            f"seed client '{cfg['client_id']}' needs the 'partner_manager' role in "
            f"the staff realm (token_sent={token is not None})."
        )
    r.raise_for_status()
    request_id = r.json()["id"]

    httpx.post(
        f"{admin}/partners/requests/{request_id}/approve",
        headers=_headers(token),
        json={"notes": "auto-approved by G2P Bridge sanity pm-seed"},
        verify=cfg["verify"],
        timeout=30,
    ).raise_for_status()

    if not _servable(cfg["partner_api_url"], partner_id, cfg["kid"], cfg["verify"]):
        raise RuntimeError(f"{partner_id}: onboarded but key '{cfg['kid']}' still not servable")
    return outcome


def main() -> int:
    partner_api_url = _env("SANITY_PM_PARTNER_API_URL").rstrip("/")
    if not partner_api_url:
        print("[pm-seed] SANITY_PM_PARTNER_API_URL not set — nothing to seed; skipping")
        return 0
    cert_pem = _env("SANITY_PM_PUBLIC_CERT_PEM")
    partner_ids = [p.strip() for p in _env("SANITY_PM_PARTNER_IDS").split(",") if p.strip()]
    if not (cert_pem and partner_ids):
        print("[pm-seed] no cert / partner ids configured — skipping")
        return 0

    verify = _verify_tls()
    cfg = {
        "partner_api_url": partner_api_url,
        "admin_url": _env("SANITY_PM_ADMIN_URL").rstrip("/"),
        "kid": _env("SANITY_PM_KID"),
        "cert_pem": cert_pem,
        "algorithm": _env("SANITY_PM_ALGORITHM", "RS256"),
        "client_id": _env("SANITY_PM_CLIENT_ID", "partner-management-staff-portal"),
        "verify": verify,
    }
    try:
        cfg["token"] = _admin_token(
            _env("SANITY_PM_TOKEN_URL"), cfg["client_id"],
            _env("SANITY_PM_CLIENT_SECRET"), verify,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[pm-seed] could not obtain PM admin token: {exc}")
        return 1

    rc = 0
    for pid in partner_ids:
        try:
            print(f"[pm-seed] {pid}: {ensure_partner(cfg, pid)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[pm-seed] {pid}: FAILED — {exc}")
            rc = 1
    return rc


if __name__ == "__main__":
    import sys

    sys.exit(main())
