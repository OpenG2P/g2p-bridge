# OpenG2P G2P Bridge

Consolidated monorepo for the OpenG2P **G2P Bridge**. It brings together what
were previously seven separate repositories into one, keeping each component's
folder structure intact.

## Layout

| Folder | Origin repo | Contents |
| --- | --- | --- |
| [`core/`](core) | `openg2p-g2p-bridge` | Core services: models, partner-api, bene-portal-api, celery-beat-producers, celery-workers |
| [`extensions/`](extensions) | `openg2p-g2p-bridge-extensions` | Pluggable adapters/connectors: agency-allocator, bank-connectors, geo-resolver, mapper-connectors, notification-connectors, warehouse-allocator |
| [`example-bank/`](example-bank) | `openg2p-g2p-bridge-example-bank` | Reference "example bank": api, celery-beat-producers, celery-workers, models |
| [`docker/`](docker) | `openg2p-g2p-bridge-docker` | Dockerfiles for the API and Celery service images |
| [`deployment/`](deployment) | `openg2p-g2p-bridge-deployment` + `openg2p-g2p-bridge-example-bank-deployment` | Single consolidated Helm chart `charts/openg2p-bridge` (G2P Bridge + bundled example-bank, toggle via `exampleBank.enabled`) |
| [`test/`](test) | `openg2p-g2p-bridge-test` | Functional / Postman tests |

The redundant `openg2p-g2p-bridge-` prefix has been stripped from folder and
file names within the repo. Python package names (e.g. `openg2p_g2p_bridge_models`),
Docker image names, and Helm `Chart.yaml` names are intentionally left unchanged.

## CI workflows

All GitHub Actions live in [`.github/workflows`](.github/workflows) (the only
location GitHub runs them from). Each is scoped with `paths:` filters so it only
runs when its own component changes:

- `pre-commit.yml` — runs each sub-project's own pre-commit config.
- `core-test.yml`, `example-bank-test.yml` — test + coverage.
- `docker-build-apis.yml`, `docker-build-celery.yml`, `docker-build-example-bank.yml` — build/push images. **The image tag matches the g2p-bridge repository ref** (branch name or git tag).
- `helm-publish.yml` — package and publish every Helm chart under `deployment/charts/` (G2P Bridge + example bank).

## Notes

- The Python packages are **not published to PyPI** — every image builds them
  from local in-repo source. Each module's `__version__` (in its `__init__.py`)
  is `0.0.0.dev0` on `develop`.
- Docker images build from local source. The only external OpenG2P libraries
  (`openg2p-fastapi-common`, and `openg2p-spar-models` for celery) are
  overridable inputs on the docker build workflows (defaults shown in the
  GitHub Actions UI).
- Helm `Chart.yaml` versions / `values` image tags are still to be reconciled
  (pending chart consolidation).
- Detailed documentation will be added separately.
