import logging

from openg2p_example_bank_models.models import (
    InitiatePaymentBatchRequest,
    PaymentStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..app import celery_app, get_engine
from ..config import Settings

_config = Settings.get_config()
_engine = get_engine()
_logger = logging.getLogger(_config.logging_default_logger_name)


@celery_app.task(name="process_payments_beat_producer")
def process_payments_beat_producer():
    _logger.info("Processing payments")
    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)
    with session_maker() as session:
        initiate_payment_batch_requests = (
            session.execute(
                select(InitiatePaymentBatchRequest).where(
                    (InitiatePaymentBatchRequest.payment_status.in_(["PENDING"]))
                    & (
                        InitiatePaymentBatchRequest.payment_initiate_attempts
                        < _config.payment_initiate_attempts
                    )
                )
            )
            .scalars()
            .all()
        )

        for initiate_payment_batch_request in initiate_payment_batch_requests:
            _logger.info(
                f"Initiating payment processing for batch: {initiate_payment_batch_request.batch_id}"
            )
            celery_app.send_task(
                "process_payments_worker",
                args=[initiate_payment_batch_request.batch_id],
                queue=_config.celery_worker_task_queue,
            )
            initiate_payment_batch_request.payment_status = PaymentStatus.PROCESSING
            session.add(initiate_payment_batch_request)
        session.commit()
