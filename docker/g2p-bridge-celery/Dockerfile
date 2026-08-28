FROM python:3.12.11-alpine3.22

# External library refs (not part of this repo), pulled from git — override via
# build-arg / CI pin. The g2p-bridge CORE (models + both celery roles) is installed
# from LOCAL source in this repo. The CONNECTORS now live in a SEPARATE repo,
# g2p-bridge-connectors, and are pulled by git ref (default develop) the same way as
# the other git dependencies. openg2p-spar-models is a transitive dep of the
# reference mapper connector.
ARG FASTAPI_COMMON_REF=develop
ARG SPAR_REF=develop
ARG G2P_BRIDGE_CONNECTORS_REF=develop

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
        "git+https://github.com/openg2p/spar@${SPAR_REF}#subdirectory=core/models"

# Core (local): models + both celery roles, so the single image can run as worker
# or beat (selected at runtime via env vars). Install models first so the connector
# packages' models dependency resolves against it.
COPY core/models /src/models
COPY core/celery-beat-producers /src/celery-beat-producers
COPY core/celery-workers /src/celery-workers
RUN pip install --no-cache-dir /src/models

# Reference/standard connectors — pulled from g2p-bridge-connectors by git ref (they
# are NOT in this repo). This set is baked into the published image. To use your own
# connector, build a derived image (FROM this one), pip-install your connector
# package, and select it via config (G2P_BRIDGE_<CONNECTOR>_CONNECTORS_IMPL[S]) — no
# fork of core or of this build is needed.
RUN pip install --no-cache-dir \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=bank-connectors" \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=geo-resolver" \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=notification-connectors" \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=agency-allocator" \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=warehouse-allocator" \
        "git+https://github.com/openg2p/g2p-bridge-connectors@${G2P_BRIDGE_CONNECTORS_REF}#subdirectory=mapper-connectors"

# Core celery roles (local).
RUN pip install --no-cache-dir /src/celery-beat-producers /src/celery-workers

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1

# Default role = worker. Override CELERY_APP / CELERY_OPTS (e.g. from the Helm
# chart) to run the same image as the beat producer instead.
ENV CELERY_APP=openg2p_g2p_bridge_celery_workers.main.celery_app
ENV CELERY_OPTS="worker -Q g2p_bridge_queue --loglevel=info"
ENV CELERY_IMPORTS=""

COPY docker/g2p-bridge-celery/run_celery.py /app/run_celery.py

# Always use the python wrapper to handle imports and startup
CMD ["python3", "/app/run_celery.py"]
