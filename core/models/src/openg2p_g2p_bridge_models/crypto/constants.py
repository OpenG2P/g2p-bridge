"""Algorithm policy for local JWS signing/verification.

The Bridge supports **RS256 only** — an asymmetric algorithm (RSA public/private
keys). Symmetric algorithms (the HMAC ``HS*`` family, which use a shared secret)
and ``none`` are always rejected. The allowed set is still configurable per
app/Helm, but defaults to RS256 alone.
"""

# Default set of allowed JWS algorithms. RS256 only (asymmetric). Override per
# app/Helm if a deployment ever needs more, but never add HS*/none.
DEFAULT_ALLOWED_ALGORITHMS = ("RS256",)

# Default for the Bridge's own outbound signing key.
DEFAULT_SIGNING_ALGORITHM = "RS256"


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
