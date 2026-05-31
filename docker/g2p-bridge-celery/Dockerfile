FROM python:3.12.11-alpine3.22

# External OpenG2P library refs (not part of this repo). Override via build-arg /
# workflow input. The g2p-bridge code (core + extensions) is installed from
# local source. openg2p-spar-models is only required by the mapper-connectors
# extension and is the one git-only external dependency.
ARG FASTAPI_COMMON_REF=v1.1.5
ARG SPAR_REF=2.0

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libffi-dev openssl-dev

WORKDIR /app

# External libs (openg2p-fastapi-common family + openg2p-spar-models)
RUN pip install --upgrade pip setuptools && \
    pip install --no-cache-dir \
        "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-common" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth-models" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-partner-auth" \
        "git+https://github.com/openg2p/openg2p-spar@${SPAR_REF}#subdirectory=openg2p-spar-models"

# Local source: models, both celery roles, and all extension connectors, so the
# single image can run as worker or beat (selected at runtime via env vars).
# Build context = repo root. Remaining deps resolve from PyPI via pyproject.
COPY core/models /src/models
COPY core/celery-beat-producers /src/celery-beat-producers
COPY core/celery-workers /src/celery-workers
COPY extensions /src/extensions
RUN pip install --no-cache-dir \
        /src/models \
        /src/extensions/bank-connectors \
        /src/extensions/geo-resolver \
        /src/extensions/notification-connectors \
        /src/extensions/agency-allocator \
        /src/extensions/warehouse-allocator \
        /src/extensions/mapper-connectors \
        /src/celery-beat-producers \
        /src/celery-workers

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1

# Default role = worker. Override CELERY_APP / CELERY_OPTS (e.g. from the Helm
# chart) to run the same image as the beat producer instead.
ENV CELERY_APP=openg2p_g2p_bridge_celery_workers.main.celery_app
ENV CELERY_OPTS="worker -Q g2p_bridge_celery_worker_tasks --loglevel=info"
ENV CELERY_IMPORTS=""

COPY docker/g2p-bridge-celery/run_celery.py /app/run_celery.py

# Always use the python wrapper to handle imports and startup
CMD ["python3", "/app/run_celery.py"]
