# Test signing keys — **TEST / DEMO ONLY**

⚠️ **The private key in this directory is committed to the repository on purpose.
It exists only so the bundled sanity suite and the Postman API walkthrough can
exercise the *signed* Partner API in a throwaway trial/demo install.**

**Never trust this key in a real deployment.** Anyone can read the private key
from this repo and forge requests as this partner. Production installs must:

* set `testPartner.enabled=false` in the Helm chart (so this public key is **not**
  onboarded), and
* onboard real partner public keys into the `*-partner-keys` Secret, signing with
  privately-held keys.

## Contents

| File | What | Used by |
| --- | --- | --- |
| `test-partner.key.json` | RS256 (RSA) **private** JWK | sanity client + Postman (to sign requests) |
| `PARTNER_TEST_SANITY.json` | public JWKS (sanity's `sender_app_mnemonic = TEST_SANITY`) | onboarded into the Bridge |
| `PARTNER_TRAINING.json` | public JWKS (Postman's `sender_app = TRAINING`) | onboarded into the Bridge |

All three share the **same** keypair (kid `test-partner-2026`); only the JWKS
filename (the partner reference id) differs.

The same public JWKS and private JWK are mirrored inline in the chart under
`testPartner` in `deployment/charts/openg2p-bridge/values.yaml`, which renders the
trial-profile Secrets. Keep them in sync if the key is ever rotated.
