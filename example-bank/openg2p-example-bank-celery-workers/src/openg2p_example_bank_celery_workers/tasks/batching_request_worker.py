import json
import logging

from openg2p_example_bank_models.models import (
    FundBlock,
    InitiatePaymentBatchRequest,
    InitiatePaymentRequest,
    PaymentStatus,
)
from openg2p_example_bank_models.schemas import InitiatePaymentPayload
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..app import celery_app, get_engine
from ..config import Settings

_config = Settings.get_config()
_engine = get_engine()
_logger = logging.getLogger(_config.logging_default_logger_name)


@celery_app.task(name="batching_request_worker")
def batching_request_worker(payment_request_batch_id: str):
    _logger.info(f"Creating payment requests for batch: {payment_request_batch_id}")
    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)
    with session_maker() as session:
        initiate_payment_batch_request = (
            session.execute(
                select(InitiatePaymentBatchRequest).where(
                    InitiatePaymentBatchRequest.batch_id == payment_request_batch_id
                )
            )
            .scalars()
            .first()
        )
        try:
            initiate_payment_requests = []
            initiate_payment_payloads = [
                InitiatePaymentPayload(**payload)
                for payload in json.loads(
                    initiate_payment_batch_request.initiate_payment_payloads
                )
            ]
            for initiate_payment_payload in initiate_payment_payloads:
                fund_block = (
                    session.execute(
                        select(FundBlock).where(
                            FundBlock.block_reference_no
                            == initiate_payment_payload.funds_blocked_reference_number
                        )
                    )
                    .scalars()
                    .first()
                )
                if (
                    not fund_block
                    or initiate_payment_payload.payment_amount > fund_block.amount
                    or fund_block.currency
                    != initiate_payment_payload.remitting_account_currency
                ):
                    _logger.error(
                        "Invalid funds block reference or mismatch in details"
                    )

                initiate_payment_request = InitiatePaymentRequest(
                    batch_id=payment_request_batch_id,
                    payment_reference_number=initiate_payment_payload.payment_reference_number,
                    remitting_account=initiate_payment_payload.remitting_account,
                    remitting_account_currency=initiate_payment_payload.remitting_account_currency,
                    payment_amount=initiate_payment_payload.payment_amount,
                    funds_blocked_reference_number=initiate_payment_payload.funds_blocked_reference_number,
                    beneficiary_name=initiate_payment_payload.beneficiary_name,
                    beneficiary_account=initiate_payment_payload.beneficiary_account,
                    beneficiary_account_currency=initiate_payment_payload.beneficiary_account_currency,
                    beneficiary_account_type=initiate_payment_payload.beneficiary_account_type,
                    beneficiary_bank_code=initiate_payment_payload.beneficiary_bank_code,
                    beneficiary_branch_code=initiate_payment_payload.beneficiary_branch_code,
                    beneficiary_mobile_wallet_provider=initiate_payment_payload.beneficiary_mobile_wallet_provider,
                    beneficiary_phone_no=initiate_payment_payload.beneficiary_phone_no,
                    beneficiary_email=initiate_payment_payload.beneficiary_email,
                    beneficiary_email_wallet_provider=initiate_payment_payload.beneficiary_email_wallet_provider,
                    payment_date=initiate_payment_payload.payment_date,
                    narrative_1=initiate_payment_payload.narrative_1,
                    narrative_2=initiate_payment_payload.narrative_2,
                    narrative_3=initiate_payment_payload.narrative_3,
                    narrative_4=initiate_payment_payload.narrative_4,
                    narrative_5=initiate_payment_payload.narrative_5,
                    narrative_6=initiate_payment_payload.narrative_6,
                    active=True,
                )
                initiate_payment_requests.append(initiate_payment_request)

            initiate_payment_batch_request.batching_request_status = (
                PaymentStatus.SUCCESS
            )
            initiate_payment_batch_request.batching_request_latest_error_code = None
            initiate_payment_batch_request.payment_status = PaymentStatus.PENDING

            session.add_all(initiate_payment_requests)
            session.commit()
            _logger.info(
                f"Initiate payment requests created successfully for batch: {payment_request_batch_id}"
            )

        except Exception as e:
            _logger.error(
                f"Error creating payment requests for initiate_payment_batch_request {payment_request_batch_id}: {e}"
            )
            session.rollback()
            initiate_payment_batch_request.batching_request_status = (
                PaymentStatus.FAILED
            )
            initiate_payment_batch_request.batching_request_latest_error_code = str(e)
            session.commit()
            raise e
