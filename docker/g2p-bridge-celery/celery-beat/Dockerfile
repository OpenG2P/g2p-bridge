FROM python:3.12.11-alpine3.22

ARG G2P_REF=v2.1.0

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libffi-dev openssl-dev

WORKDIR /app

# Dynamic adapters for beat (optional)
COPY adapters.requirements.txt /tmp/adapters.requirements.txt
RUN if [ -s /tmp/adapters.requirements.txt ]; then pip install --no-cache-dir -r /tmp/adapters.requirements.txt; fi

RUN pip install --upgrade pip setuptools && \
    pip install --disable-pip-version-check \
        "git+https://github.com/openg2p/openg2p-fastapi-common@v1.1.5#subdirectory=openg2p-fastapi-common" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@v1.1.5#subdirectory=openg2p-fastapi-auth-models" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@v1.1.5#subdirectory=openg2p-fastapi-auth" \
        "git+https://github.com/openg2p/openg2p-fastapi-common@v1.1.5#subdirectory=openg2p-fastapi-partner-auth" \
        "git+https://github.com/openg2p/openg2p-g2p-bridge@${G2P_REF}#subdirectory=openg2p-g2p-bridge-models" \
        "git+https://github.com/openg2p/openg2p-g2p-bridge@${G2P_REF}#subdirectory=openg2p-g2p-bridge-celery-beat-producers"

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1

CMD ["celery", "-A", "openg2p_g2p_bridge_celery_beat_producers.main.celery_app", "worker", "--beat", "--loglevel=info", "--schedule=/tmp/celery-beat-schedule.db"]
