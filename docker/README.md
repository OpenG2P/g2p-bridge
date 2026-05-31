# G2P Bridge Docker

Dockerfiles for the G2P Bridge service images.

- `g2p-bridge-apis/` — `partner-api` and `beneportal-api` images.
- `g2p-bridge-celery/` — a **single** celery image (`openg2p/openg2p-g2p-bridge-celery`)
  that contains both the celery-workers and celery-beat-producers code. The role
  is chosen at runtime via the `CELERY_APP` / `CELERY_OPTS` environment variables
  (see `run_celery.py`); the Helm chart sets these so the same image runs as the
  worker in one deployment and the beat producer in the other. Defaults to the
  worker role.

## Builds from local source

The images install the g2p-bridge code (core services and `extensions/`
connectors) **from this repo's local source** — there are no `*.txt` service
files and no GitHub round-trip for g2p-bridge code. The build context is the
repo root (`example-bank` builds use the `example-bank/` folder).

The only dependencies fetched externally are OpenG2P libraries that don't live
in this repo:

- `openg2p-fastapi-common` (+ `auth-models`, `auth`, `partner-auth`) — all images.
- `openg2p-spar-models` — celery image only (needed by the `mapper-connectors`
  extension).

Their refs are **build args** with defaults, surfaced as **inputs on the docker
build workflows** so they show up (and can be changed) when you run a build from
the GitHub Actions UI. Other libraries (`openg2p-g2pconnect-*`, etc.) resolve
from PyPI via each package's `pyproject.toml`.

Images are built/pushed by the workflows under `.github/workflows/` and tagged
with the g2p-bridge repository ref.
