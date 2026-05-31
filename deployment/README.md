## OpenG2P G2P Bridge Deployment

Deployment Helm charts for OpenG2P G2P Bridge and the Example Bank Simulator
(used for the G2P Bridge demo).

Charts under [`charts/`](charts):

- `core` — OpenG2P G2P Bridge.
- `example-bank` — Example Bank Simulator (umbrella), with its
  `example-bank-api`, `example-bank-celery-beat-producers` and
  `example-bank-celery-workers` subcharts.

Guides:

- [OpenG2P G2P Bridge Deployment Guide](https://docs.openg2p.org/g2p-bridge/deployment/deployment-of-g2p-bridge)
- [Example Bank Simulator Deployment Guide](https://docs.openg2p.org/g2p-bridge/deployment/deployment-of-example-bank)
