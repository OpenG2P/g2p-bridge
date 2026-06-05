# Regression sanity suite, packaged to run in-cluster (Helm test Job / on demand).
# Build context = repo root. The suite has no OpenG2P-library dependencies.
FROM python:3.12.11-alpine3.22

RUN apk add --no-cache bash

WORKDIR /app

# Test runtime deps (kept in sync with test/sanity/pyproject.toml).
RUN pip install --no-cache-dir pytest pytest-html httpx PyYAML

# The suite itself.
COPY test/sanity /app
COPY docker/g2p-bridge-sanity/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1
# Results are written here; mount a volume (PVC) to persist them for the viewer.
ENV SANITY_RESULTS_DIR=/results
# Off by default — auto (helm test) runs only smoke+contract (no data created).
ENV SANITY_RUN_E2E=false

ENTRYPOINT ["/app/entrypoint.sh"]
