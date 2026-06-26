# Partner Authentication & Local Signature Verification (G2P-5209)

> **Status:** Local working doc. To be moved into the GitBook
> (`openg2p-documentation`) once reviewed.

This describes how the G2P Bridge authenticates partners **without Keymanager**.
Partner request signatures are now verified **in-process** with a local crypto
library, and partner public keys are onboarded as local files (mounted from a
Kubernetes Secret). The Bridge also signs its own outbound requests to SPAR
locally with its own private key.

## Why this changed

Previously the Bridge delegated all JWS signing/verification to the shared
**Keymanager** service (`/jwtSign`, `/jwtVerify`), authenticated via a Keycloak
client-credentials token. That made Keymanager (and Keycloak) a hard runtime
dependency just to check a signature. Keymanager was used for **only** these two
things — nothing else (no encryption, no key generation) — so it could be
replaced with a small local helper.

**Removed:** the Keymanager API calls, the Keymanager service dependency, the
OAuth/Keycloak client that existed solely to authenticate to Keymanager, and all
related Helm values/questions/env.

## What replaces it

`PyJWTCryptoHelper` (in `openg2p_g2p_bridge_models.crypto`) is a drop-in
replacement for the old `KeymanagerCryptoHelper`. It implements the same
`verify_jwt` / `create_jwt_token` interface but does the crypto locally with
[`PyJWT`](https://pyjwt.readthedocs.io/) (+ `cryptography`), resolving keys from a
local store.

> **Relation to the platform `PyJWTCryptoHelper` proposal.** This is the
> Bridge-local instance of the shared
> [`PyJWTCryptoHelper`](https://docs.openg2p.org/platform/platform-services/privacy-and-security/pyjwtcryptohelper)
> design — same library, wire format, canonicalization, interface and
> fail-closed behavior. It lives in the Bridge for now (changing
> `openg2p-fastapi-common` would ripple through every product); the plan is to
> move it into `fastapi-common` `partner_auth` so all products share one
> implementation, at which point the Bridge just swaps the one-line registration
> in `app.py`. The Bridge version additionally hardens the design with `kid`-based
> multi-key rotation, an explicit algorithm allow-list (RS256 only; HS*/none hard
> blocked), a configurable signing key, and Secret-volume mounts (not K8s-API
> reads) — carry these upstream at migration.

| Direction | Operation | Key used | Source |
| --- | --- | --- | --- |
| **Inbound** (partner → Bridge) | `verify_jwt` | partner **public** key | partner key store (JWKS files) |
| **Outbound** (Bridge → SPAR) | `create_jwt_token` | Bridge **private** key | signing-key Secret |

Inbound verification is **on by default in the bundled trial/demo install** (via
the test partner — see below) and **off for production** until you onboard real
partners (`global.g2pBridgeSignatureValidationEnabled=true`). Outbound signing
turns on only when SPAR enforces signatures (`...SPAR_MAPPER_API_SIGN_ENABLED=true`).

## The signing contract (unchanged — no partner-facing change)

The wire format is identical to what the Keymanager path used, so existing
partners need no change.

* The signature is a **detached JWS** sent in the **`Signature`** HTTP header:
  `BASE64URL(protected_header)` + `.` + `.` + `BASE64URL(signature)`
  (i.e. `header..signature` — the middle/payload segment is empty).
* The **signing input** is:
  `BASE64URL(protected_header)` + `.` + `BASE64URL(canonical_json(body))`
* **canonical_json** = compact, UTF-8, **sorted keys** (the exact bytes the
  client also sends as the request body).
* The protected header carries **`alg`** and **`kid`**.

The Bridge reconstructs the signing input from the request body it receives and
verifies the signature against the partner's registered public key.

## Algorithms

**RS256 only.** The Bridge supports a single algorithm — **RS256** (RSA with
SHA-256), an **asymmetric** scheme using a public/private keypair.

* **Symmetric algorithms are not supported.** The HMAC family (`HS*`), which uses
  a shared secret, is **always rejected** — as is `none`. Accepting a symmetric
  algorithm against an asymmetric key store is the classic JWS
  algorithm-confusion attack, so this is a hard block independent of config.
* The allowed set is still configurable (`global.g2pBridgeSignatureAllowedAlgorithms`,
  default `RS256`) for flexibility, but RS256 is the only algorithm in use, and the
  algorithm in a partner's JWS header must match the algorithm registered with
  that key.
* RSA keys of **2048 bits or larger** are recommended.

## Onboarding a partner (inbound)

A partner is identified by `sender_app_mnemonic` in the request header, which the
Bridge maps to the reference id `PARTNER_<MNEMONIC>` (uppercased, dashes →
underscores). Onboarding = **registering that partner's public key** under that
reference id.

### 1. Partner generates a keypair and gives you the public key

The partner keeps the private key and signs requests with it. They share the
**public** key (as a JWK). Example (operator-side, for testing — in production the
partner generates their own):

```bash
python - <<'PY'
import json
from joserfc.jwk import generate_key
k = generate_key("RSA", 2048, {"kid": "psp-2026-01", "alg": "RS256", "use": "sig"})
open("my_psp_private.json", "w").write(json.dumps(k.as_dict(private=True)))
open("my_psp_public.json", "w").write(json.dumps(k.as_dict(private=False)))
PY
```

### 2. Build a JWKS file per partner

One file named `PARTNER_<MNEMONIC>.json`, a standard JWKS holding one or more
public keys:

```json
{ "keys": [ { "kty": "RSA", "kid": "psp-2026-01", "alg": "RS256",
              "use": "sig", "n": "...", "e": "AQAB" } ] }
```

For a partner with `sender_app_mnemonic = my-psp`, the file is
`PARTNER_MY_PSP.json`.

### 3. Put the files into the partner-keys Secret

```bash
kubectl create secret generic g2p-bridge-partner-keys -n <namespace> \
  --from-file=PARTNER_MY_PSP.json \
  --from-file=PARTNER_OTHER_PARTNER.json
```

The Secret name defaults to `<release>-partner-keys`
(`global.g2pBridgePartnerKeysSecret`) and is mounted read-only at
`/etc/g2p-bridge/partner-keys`. The mount is `optional`, so the API starts even
before the Secret exists. After updating the Secret, restart the Partner API pods
(or let the kubelet refresh the mount; the store reloads files on mtime change).

### 4. Enable verification

Set `global.g2pBridgeSignatureValidationEnabled=true` and `helm upgrade`.

## Key rotation

Rotation is an **overlap** operation, keyed by `kid` — no coordinated cutover:

1. Partner generates a new keypair with a **new `kid`**.
2. Add the new public key to the partner's JWKS file (now two keys) and update
   the Secret. Both keys are now accepted.
3. Partner switches signing to the new `kid`.
4. After the overlap window, remove the old key from the JWKS and update the
   Secret.

Compromise: remove (or stop trusting) the affected `kid` immediately. Keep each
key's validity window short enough that routine rotation (~6–12 months) is
normal.

## Outbound signing to SPAR

When SPAR enforces signature verification (it uses a single global switch for all
its callers — there is no per-caller bypass), the Bridge must sign its resolve
requests too. The Bridge signs locally with its **own private key**:

1. Generate a Bridge signing keypair (RS256 / RSA-2048+), store the **private**
   JWK as `signing-key.json` in the signing-key Secret:

   ```bash
   kubectl create secret generic g2p-bridge-signing-key -n <namespace> \
     --from-file=signing-key.json
   ```

   Default Secret name `<release>-signing-key`
   (`global.g2pBridgeSigningKeySecret`), mounted read-only at
   `/etc/g2p-bridge/signing-key`.

2. Register the Bridge's **public** key on the SPAR side as
   `PARTNER_<BRIDGE_MNEMONIC>` (whatever key store SPAR uses).

3. Enable signing: `...SPAR_MAPPER_API_SIGN_ENABLED=true` and set
   `global.g2pBridgeSigningKeyKid` / `global.g2pBridgeSigningAlgorithm`.

If the Bridge is SPAR's only caller and SPAR has verification off, outbound
signing can stay off.

## Testing with auth on — the trial profile

The bundled trial install (Example Bank on) exercises the **signed** Partner API
out of the box. A committed **TEST-ONLY** keypair (`test/keys/`, also mirrored
inline in the chart under `testPartner`) drives this:

* `global.testPartnerEnabled` (default **true**) makes the chart **onboard** the
  test partner's public key (as `PARTNER_TEST_SANITY` and `PARTNER_TRAINING`) and
  **turn signature validation on**.
* The **sanity suite** signs every Partner API request with the test private key
  by default (`sign_requests=true`); the chart mounts that key into the sanity
  Job. Locally it reads `test/keys/test-partner.key.json`.
* The **Postman walkthrough** signs via a collection pre-request (loads
  `jsrsasign` from a pinned CDN, signs with the test key in `signing_private_jwk`).
  Set `sign_requests=false` in the environment to disable.

⚠️ **The test private key is committed to the repo.** Any install that onboards
it can be impersonated. For production: set **`global.testPartnerEnabled=false`**
(do this together with disabling the Example Bank), onboard real partner keys, and
choose `g2pBridgeSignatureValidationEnabled` explicitly. See
[`test/keys/README.md`](../test/keys/README.md).

> The Postman pre-request uses RS256 via `jsrsasign` in the Postman sandbox. The
> signing logic is validated against the Bridge verifier, but the Postman-runtime
> plumbing (CDN load + header injection) should be smoke-tested in Postman/newman
> against a live trial before relying on it.

## Configuration reference

### Helm values (`global.*`)

| Value | Default | Purpose |
| --- | --- | --- |
| `g2pBridgeSignatureValidationEnabled` | `false` | Verify partner signatures on the Partner API |
| `g2pBridgePartnerKeysDir` | `/etc/g2p-bridge/partner-keys` | Mount path for partner JWKS files |
| `g2pBridgePartnerKeysSecret` | `<release>-partner-keys` | Secret holding partner JWKS files |
| `g2pBridgeSignatureAllowedAlgorithms` | `RS256` | Allowed JWS algorithms (RS256 only) |
| `g2pBridgeSigningKeyDir` | `/etc/g2p-bridge/signing-key` | Mount path for the Bridge signing key |
| `g2pBridgeSigningKeySecret` | `<release>-signing-key` | Secret holding the Bridge private JWK |
| `g2pBridgeSigningKeyKid` | `""` | `kid` for outbound signatures (else key's own) |
| `g2pBridgeSigningAlgorithm` | `RS256` | Algorithm for outbound signing |

### Environment variables

Partner API: `G2P_BRIDGE_SIGNATURE_VALIDATION_ENABLED`,
`G2P_BRIDGE_PARTNER_KEYS_DIR`, `G2P_BRIDGE_SIGNATURE_ALLOWED_ALGORITHMS`.

Mapper connectors (celery worker):
`G2P_BRIDGE_MAPPER_CONNECTORS_SPAR_MAPPER_API_SIGN_ENABLED`,
`G2P_BRIDGE_MAPPER_CONNECTORS_SIGNING_KEY_PATH`,
`G2P_BRIDGE_MAPPER_CONNECTORS_SIGNING_KEY_KID`,
`G2P_BRIDGE_MAPPER_CONNECTORS_SIGNING_ALGORITHM`,
`G2P_BRIDGE_MAPPER_CONNECTORS_SIGNING_ALLOWED_ALGORITHMS`.

## Performance & scalability

Local verification is cheap and is **strictly faster than the old Keymanager
path**, which made a network round-trip (`POST /jwtVerify`) plus an OAuth token
fetch on every request. There are now **no network calls and no external
dependency** in the hot path.

Measured single-core throughput (Python, `PyJWTCryptoHelper`):

| Operation | Throughput | Per op |
| --- | --- | --- |
| RS256 verify (inbound) | ~11,000 /sec | ~0.09 ms |
| RS256 sign (outbound) | ~1,000 /sec | ~1.0 ms |

Inbound **verification** is the request hot path and is fast (~0.09 ms). RSA
**signing** is intrinsically slower (~1 ms), but it is **outbound-only** (Bridge →
SPAR), **off by default**, and runs in the **async Celery workers** — never on the
Partner API request path — so it does not affect inbound throughput.

Why this scales to several thousand disbursement requests comfortably:

* **Keys are cached in-process** — a partner's JWKS is read from disk only on
  first use and reloaded only when the file's mtime changes; steady state is a
  single `stat()` plus an in-memory verify, no per-request I/O.
* **Verification is a negligible fraction of request time** — a sub-millisecond
  CPU cost next to the database writes the request already does.
* **The heavy disbursement pipeline is asynchronous** (Celery beats/workers); the
  Partner API only accepts and enqueues, and **outbound signing runs in the
  workers**, off the request path.
* **Scale horizontally** — add Partner API replicas and Celery workers as usual;
  there is no shared crypto service to bottleneck on.

If verification CPU ever became material at extreme concurrency, the verify could
be offloaded to a thread pool — not needed at the scales above.

## Security considerations & limitations

* **The MT940 upload endpoint (`account_statement`) is not signature-protected.**
  It is the bank → Bridge statement callback (a different trust boundary from
  partner requests), so it never required a partner signature. If it is reachable
  by untrusted callers, authenticate or network-restrict it separately —
  otherwise forged statements could drive false reconciliation.
* **No replay protection.** A captured, validly-signed request can be replayed —
  the signature binds the body, not freshness. This matches the previous
  Keymanager behavior (no regression). If replay matters, enforce `request_id`
  uniqueness and/or a `request_timestamp` window.
* **Malformed JSON body.** The upstream `JWTSignatureValidator` parses the body
  with `orjson.loads` before verifying; a non-JSON body can surface as an HTTP 500
  rather than a clean rejection. (This lives in the `partner_auth` library, not
  this repo.)
* **Pin the algorithm per key.** Onboarding includes `alg` in each JWK and the
  helper checks the header `alg` against it; keep `alg` present in partner JWKS so
  the algorithm is fixed per key (defense in depth beyond key-type matching).

## Code map

| Path | What |
| --- | --- |
| `core/models/src/openg2p_g2p_bridge_models/crypto/pyjwt_crypto_helper.py` | `PyJWTCryptoHelper` — local verify + sign (PyJWT) |
| `core/models/src/openg2p_g2p_bridge_models/crypto/key_store.py` | `PartnerKeyStore` — JWKS-per-partner file store |
| `core/models/src/openg2p_g2p_bridge_models/crypto/constants.py` | Allowed-algorithm policy |
| `core/partner-api/.../app.py` | Registers `PyJWTCryptoHelper` for inbound verify |
| `extensions/mapper-connectors/.../app.py` | Registers the named signing helper for SPAR |
| `core/partner-api/tests/test_pyjwt_crypto_helper.py` | Unit tests |
