# openg2p-g2p-bridge-test

Test artefacts for the G2P Bridge.

- [`sanity/`](sanity/) — the **regression sanity suite**: a point-at-a-deployed-system
  pytest suite that verifies every API and the full end-to-end cash-flow stage by
  stage, plus business-rule negatives and MT940 reconciliation-error handling.

The earlier Postman collections and the standalone MT940 script (formerly under
`functional-test/`) have been consolidated into the sanity suite so there is a
single, automated source of truth. See the Regression Sanity Suite docs for how
to run it and view results.
