# G2P Bridge Docker

Dockerfiles for the G2P Bridge service images.

- `g2p-bridge-apis/` — `partner-api` and `beneportal-api` images.
- `g2p-bridge-celery/` — a **single** celery image (`openg2p/openg2p-g2p-bridge-celery`)
  that contains both the celery-workers and celery-beat-producers code. The role
  is chosen at runtime via the `CELERY_APP` / `CELERY_OPTS` environment variables
  (see `run_celery.py`); the Helm chart sets these so the same image runs as the
  worker in one deployment and the beat producer in the other. Defaults to the
  worker role.

Images are built/pushed by the workflows under `.github/workflows/` and tagged
with the g2p-bridge repository ref.
