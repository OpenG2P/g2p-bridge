FROM python:3.12.11-alpine3.22

# External OpenG2P library ref (not part of this repo). Override via build-arg /
# workflow input. The g2p-bridge code itself is installed from local source.
ARG FASTAPI_COMMON_REF=develop

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libmagic

WORKDIR /app

# External libs (openg2p-fastapi-common family)
RUN pip install --no-cache-dir \
    "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-common" \
    "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth-models" \
    "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-auth" \
    "git+https://github.com/openg2p/openg2p-fastapi-common@${FASTAPI_COMMON_REF}#subdirectory=openg2p-fastapi-partner-auth"

# Local g2p-bridge source (build context = repo root). Remaining deps
# (g2pconnect libs, etc.) resolve from PyPI via each package's pyproject.
COPY core/models /src/models
COPY core/partner-api /src/partner-api
RUN pip install --no-cache-dir /src/models /src/partner-api

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV G2P_BRIDGE_NO_OF_WORKERS=2
ENV G2P_BRIDGE_HOST=0.0.0.0
ENV G2P_BRIDGE_PORT=8000
ENV G2P_BRIDGE_WORKER_TYPE=gunicorn

CMD python3 -m openg2p_g2p_bridge_partner_api.main migrate; \
    gunicorn "openg2p_g2p_bridge_partner_api.main:app" --workers ${G2P_BRIDGE_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${G2P_BRIDGE_HOST}:${G2P_BRIDGE_PORT} --log-level info
