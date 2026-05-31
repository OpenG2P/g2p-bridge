from celery import Celery

from .config import Settings

_config = Settings.get_config()

celery_app = Celery(
    "example_bank",
    broker=_config.celery_broker_url,
    backend=_config.celery_backend_url,
)

celery_app.conf.timezone = "UTC"
