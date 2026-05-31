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
| [`deployment/`](deployment) | `openg2p-g2p-bridge-deployment` + `openg2p-g2p-bridge-example-bank-deployment` | Helm charts for G2P Bridge (`charts/core`) and the example bank (`charts/example-bank*`) |
| [`test/`](test) | `openg2p-g2p-bridge-test` | Functional / Postman tests |

The redundant `openg2p-g2p-bridge-` prefix has been stripped from folder and
file names within the repo. Python package names (e.g. `openg2p_g2p_bridge_models`),
Docker image names, and Helm `Chart.yaml` names are intentionally left unchanged.

## CI workflows

All GitHub Actions live in [`.github/workflows`](.github/workflows) (the only
location GitHub runs them from). Each is scoped with `paths:` filters so it only
runs when its own component changes:

- `tag.yml` — tag the whole repo.
- `pre-commit.yml` — runs each sub-project's own pre-commit config.
- `core-test.yml`, `example-bank-test.yml` — test + coverage.
- `core-pypi-publish.yml`, `example-bank-pypi-publish.yml` — publish Python packages.
- `docker-build-apis.yml`, `docker-build-celery.yml`, `docker-build-example-bank.yml` — build/push images. **The image tag matches the g2p-bridge repository ref** (branch name or git tag).
- `helm-publish.yml` — package and publish every Helm chart under `deployment/charts/` (G2P Bridge + example bank).

## Notes

- Versions (Python `__init__`/pyproject, Helm `Chart.yaml`, image refs) were
  copied **as-is** from the source repos and will be reconciled as a follow-up.
- The Dockerfiles still install services from GitHub via a `G2P_REF` build-arg
  and the `adapters/{version}.txt` mechanism (preserved under `docker/`);
  pointing these at this consolidated repo is part of the same follow-up.
- Detailed documentation will be added separately.
