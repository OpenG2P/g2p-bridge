# ruff: noqa: E402
import logging

from celery import Celery
from openg2p_fastapi_common.app import Initializer as BaseInitializer
from sqlalchemy import create_engine

from .config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().init_logger()
        super().init_app()


def get_engine():
    if _config.db_datasource:
        db_engine = create_engine(_config.db_datasource)
        return db_engine


celery_app = Celery(
    "example_bank_celery_tasks",
    broker=_config.celery_broker_url,
    backend=_config.celery_backend_url,
    include=["openg2p_example_bank_celery_beat_producers.tasks"],
)

celery_app.conf.beat_schedule = {
    "process_payments": {
        "task": "process_payments_beat_producer",
        "schedule": _config.process_payment_frequency,
    },
    "batching_request": {
        "task": "batching_request_beat_producer",
        "schedule": _config.process_payment_frequency,
    },
    "account_statement_generator": {
        "task": "account_statement_generator_beat_producer",
        "schedule": _config.process_payment_frequency,
    },
}

celery_app.conf.timezone = "UTC"
