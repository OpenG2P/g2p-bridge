import json
import logging
import uuid
from typing import List

from openg2p_example_bank_models.models import (
    InitiatePaymentBatchRequest,
    PaymentStatus,
)
from openg2p_example_bank_models.schemas import (
    InitiatePaymentPayload,
    InitiatePaymentResponse,
)
from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.controller import BaseController
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class PaymentController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["Payments Management"]

        self.router.add_api_route(
            "/initiate_payment",
            self.initiate_payment,
            response_model=InitiatePaymentResponse,
            methods=["POST"],
        )

    async def initiate_payment(
        self, initiate_payment_payloads: List[InitiatePaymentPayload]
    ) -> InitiatePaymentResponse:
        _logger.info("Initiating payment")
        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            batch_id = str(uuid.uuid4())
            initiate_payment_batch_request = InitiatePaymentBatchRequest(
                batching_request_status=PaymentStatus.PENDING,
                initiate_payment_payloads=json.dumps(
                    [payload.model_dump() for payload in initiate_payment_payloads]
                ),
                batch_id=batch_id,
                active=True,
            )
            _logger.info(
                f"INITIATE_PAYMENT_BATCH_REQUEST: {initiate_payment_batch_request}"
            )
            session.add(initiate_payment_batch_request)
            await session.commit()
            _logger.info("Payment initiated successfully")
            return InitiatePaymentResponse(status="success", error_message="")
