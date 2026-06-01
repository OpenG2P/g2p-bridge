## OpenG2P G2P Bridge Deployment

A single consolidated Helm chart under [`charts/`](charts):

- **`openg2p-bridge`** — the OpenG2P G2P Bridge (partner API, bene-portal API,
  celery beat producer, celery worker). It also bundles the **Example Bank
  simulator** (api + celery beat/worker), wired to the shared `commons-postgresql`
  (DB `example_bank_db` via `postgres-init`) and this chart's Redis. Toggle it
  with `exampleBank.enabled` (default `true`; set `false` for production).

  The Bridge expects a Keycloak OIDC client (`global.g2pBridgeAuthClientId`) and
  its secret to exist already — this chart does not create them.

Chart version on `develop` is `0.0.0-develop`; on a release tag it is published
as the tag. All changeable values (hostnames, Keycloak, SPAR, keymanager,
example-bank, and the Bridge/Registry/PBMS databases) are surfaced in
[`charts/openg2p-bridge/questions.yaml`](charts/openg2p-bridge/questions.yaml).

Guides:

- [OpenG2P G2P Bridge Deployment Guide](https://docs.openg2p.org/g2p-bridge/deployment/deployment-of-g2p-bridge)
- [Example Bank Simulator Deployment Guide](https://docs.openg2p.org/g2p-bridge/deployment/deployment-of-example-bank)
