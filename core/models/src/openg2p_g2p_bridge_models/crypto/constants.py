"""Algorithm policy for local JWS signing/verification.

Centralises which JWS algorithms the Bridge will accept so the choice is explicit
(the old Keymanager-backed path pinned nothing and trusted whatever the JWS header
declared). ES256 is the recommended baseline — small, fast, FIPS/HSM-friendly and
universally supported. EdDSA is preferred for partners that can use it; PS256/RS256
are kept for RSA-bound partners (RS256 is legacy/backward-compatible only).
"""

# Default set of allowed JWS algorithms (asymmetric only). Override per app/Helm.
DEFAULT_ALLOWED_ALGORITHMS = ("ES256", "EdDSA", "PS256", "RS256")

# Recommended default for the Bridge's own outbound signing key.
DEFAULT_SIGNING_ALGORITHM = "ES256"


def is_forbidden_algorithm(alg) -> bool:
    """True for algorithms that must never be accepted regardless of config.

    Blocks ``none`` (unsigned) and the HMAC family (``HS*``) — accepting a
    symmetric algorithm against an asymmetric key store is the classic JWS
    algorithm-confusion attack.
    """
    if not alg:
        return True
    normalized = str(alg).strip()
    if normalized.lower() == "none":
        return True
    if normalized.upper().startswith("HS"):
        return True
    return False
