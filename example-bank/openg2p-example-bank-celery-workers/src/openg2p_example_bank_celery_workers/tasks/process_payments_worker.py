import logging
import random
import uuid
from datetime import datetime
from typing import List

from fastnanoid import generate
from openg2p_example_bank_models.models import (
    Account,
    AccountingLog,
    AccountStatement,
    AccountStatementStatus,
    DebitCreditTypes,
    FundBlock,
    InitiatePaymentBatchRequest,
    InitiatePaymentRequest,
    PaymentStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..app import celery_app, get_engine
from ..config import Settings

_config = Settings.get_config()
_engine = get_engine()
_logger = logging.getLogger(_config.logging_default_logger_name)


@celery_app.task(name="process_payments_worker")
def process_payments_worker(payment_request_batch_id: str):
    _logger.info(f"Processing payments for batch: {payment_request_batch_id}")
    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)
    with session_maker() as session:
        _logger.info(f"Processing payments for batch: {payment_request_batch_id}")
        initiate_payment_batch_request = (
            session.execute(
                select(InitiatePaymentBatchRequest).where(
                    InitiatePaymentBatchRequest.batch_id == payment_request_batch_id
                )
            )
            .scalars()
            .first()
        )
        _logger.info(
            f"Initiate payment batch request: {initiate_payment_batch_request}"
        )
        try:
            initiate_payment_requests = (
                session.execute(
                    select(InitiatePaymentRequest).where(
                        InitiatePaymentRequest.batch_id == payment_request_batch_id
                    )
                )
                .scalars()
                .all()
            )

            failure_logs = []
            for initiate_payment_request in initiate_payment_requests:
                accounting_log_debit: AccountingLog = (
                    construct_accounting_log_for_debit(initiate_payment_request)
                )
                (
                    credit_account_number,
                    credit_account_name,
                    credit_account_phone,
                    credit_account_email,
                ) = construct_credit_account_details(initiate_payment_request)

                accounting_log_credit: AccountingLog = (
                    construct_accounting_log_for_credit(
                        initiate_payment_request, credit_account_number
                    )
                )

                remitting_account = update_account_for_debit(
                    accounting_log_debit.account_number,
                    initiate_payment_request.payment_amount,
                    session,
                )
                fund_block = update_fund_block(
                    accounting_log_debit.corresponding_block_reference_no,
                    initiate_payment_request.payment_amount,
                    session,
                )

                credit_account = update_account_for_credit(
                    credit_account_name,
                    credit_account_number,
                    credit_account_phone,
                    credit_account_email,
                    initiate_payment_request.beneficiary_account_currency,
                    initiate_payment_request.payment_amount,
                    session,
                )
                failure_random_number = random.randint(1, 100)
                if (
                    failure_random_number <= 30
                    and initiate_payment_request.beneficiary_bank_code
                    != _config.bank_simulator_code
                ):
                    failure_logs.append(accounting_log_debit)
                    failure_logs.append(accounting_log_credit)

                session.add(accounting_log_debit)
                session.add(accounting_log_credit)
                session.add(fund_block)
                session.add(remitting_account)
                session.add(credit_account)

            # End of loop

            generate_failures(failure_logs, session)
            initiate_payment_batch_request.payment_initiate_attempts += 1
            initiate_payment_batch_request.payment_status = PaymentStatus.SUCCESS
            _logger.info(f"Payments processed for batch: {payment_request_batch_id}")
            account_statement = AccountStatement(
                account_number=initiate_payment_requests[0].remitting_account,
                account_statement_generation_status=AccountStatementStatus.PENDING,
                active=True,
            )
            session.add(account_statement)
            session.commit()
            # TODO: create beat for account statement generation
            _logger.info("Account statement generation task created")
            celery_app.send_task(
                "account_statement_generator",
                args=(account_statement.id,),
            )
        except Exception as e:
            _logger.error(f"Error processing payment: {e}")
            session.rollback()
            initiate_payment_batch_request.payment_status = PaymentStatus.PENDING
            initiate_payment_batch_request.payment_initiate_attempts += 1
            session.commit()


def construct_accounting_log_for_debit(
    initiate_payment_request: InitiatePaymentRequest,
):
    return AccountingLog(
        reference_no=generate(size=23),
        corresponding_block_reference_no=initiate_payment_request.funds_blocked_reference_number,
        customer_reference_no=initiate_payment_request.payment_reference_number,
        debit_credit=DebitCreditTypes.DEBIT,
        account_number=initiate_payment_request.remitting_account,
        transaction_amount=initiate_payment_request.payment_amount,
        transaction_date=datetime.utcnow(),
        transaction_currency=initiate_payment_request.remitting_account_currency,
        transaction_code="DBT",
        narrative_1=initiate_payment_request.narrative_1,
        narrative_2=initiate_payment_request.narrative_2,
        narrative_3=initiate_payment_request.narrative_3,
        narrative_4=initiate_payment_request.narrative_4,
        narrative_5=initiate_payment_request.narrative_5,
        narrative_6=initiate_payment_request.narrative_6,
        active=True,
    )


def construct_accounting_log_for_credit(
    initiate_payment_request: InitiatePaymentRequest, credit_account_number: str
):
    return AccountingLog(
        reference_no=generate(size=23),
        corresponding_block_reference_no="",
        customer_reference_no=initiate_payment_request.payment_reference_number,
        debit_credit=DebitCreditTypes.CREDIT,
        account_number=credit_account_number,
        transaction_amount=initiate_payment_request.payment_amount,
        transaction_date=datetime.utcnow(),
        transaction_currency=initiate_payment_request.remitting_account_currency,
        transaction_code="DBT",
        narrative_1=initiate_payment_request.narrative_1,
        narrative_2=initiate_payment_request.narrative_2,
        narrative_3=initiate_payment_request.narrative_3,
        narrative_4=initiate_payment_request.narrative_4,
        narrative_5=initiate_payment_request.narrative_5,
        narrative_6=initiate_payment_request.narrative_6,
        active=True,
    )


def construct_credit_account_details(initiate_payment_request: InitiatePaymentRequest):
    if initiate_payment_request.beneficiary_account_type == "MOBILE_WALLET":
        return (
            f"CLEARING - {initiate_payment_request.beneficiary_mobile_wallet_provider}",
            f"Clearing account for {initiate_payment_request.beneficiary_mobile_wallet_provider}",
            None,
            None,
        )
    elif initiate_payment_request.beneficiary_account_type == "EMAIL_WALLET":
        return (
            f"CLEARING - {initiate_payment_request.beneficiary_email_wallet_provider}",
            f"Clearing account for {initiate_payment_request.beneficiary_email_wallet_provider}",
            None,
            None,
        )
    elif initiate_payment_request.beneficiary_account_type == "BANK_ACCOUNT":
        if (
            initiate_payment_request.beneficiary_bank_code
            == _config.bank_simulator_code
        ):
            return (
                initiate_payment_request.beneficiary_account,
                initiate_payment_request.beneficiary_name,
                initiate_payment_request.beneficiary_phone_no,
                initiate_payment_request.beneficiary_email,
            )
        else:
            random_id = str(uuid.uuid4())
            random_phone = f"254{random.randint(700000000, 799999999)}"
            return (
                f"CLEARING - {initiate_payment_request.beneficiary_bank_code}",
                f"Clearing account for {initiate_payment_request.beneficiary_bank_code}",
                random_phone,
                f"{random_id}@email.com",
            )


def generate_failures(failure_logs: List[AccountingLog], session):
    _logger.info("Generating failures")
    failure_reasons = [
        "ACCOUNT_CLOSED",
        "ACCOUNT_NOT_FOUND",
        "ACCOUNT_DORMANT",
        "ACCOUNT_DECEASED",
    ]
    for failure_log in failure_logs:
        failure_reason = random.choice(failure_reasons)
        account_log: AccountingLog = AccountingLog(
            reference_no=generate(size=23),
            customer_reference_no=failure_log.customer_reference_no,
            debit_credit=failure_log.debit_credit,
            account_number=failure_log.account_number,
            transaction_amount=-failure_log.transaction_amount,
            transaction_date=failure_log.transaction_date,
            transaction_currency=failure_log.transaction_currency,
            transaction_code=failure_log.transaction_code,
            narrative_1=failure_log.narrative_1,
            narrative_2=failure_log.narrative_2,
            narrative_3=failure_log.narrative_3,
            narrative_4=failure_log.narrative_4,
            narrative_5=failure_log.narrative_5,
            narrative_6=failure_reason,
            active=True,
        )
        if failure_log.debit_credit == DebitCreditTypes.DEBIT:
            account = update_account_for_debit(
                account_log.account_number, account_log.transaction_amount, session
            )
            fund_block = update_fund_block(
                failure_log.corresponding_block_reference_no,
                account_log.transaction_amount,
                session,
            )
            session.add(fund_block)
        else:
            account = update_account_for_credit(
                None,
                account_log.account_number,
                None,
                None,
                None,
                account_log.transaction_amount,
                session,
            )

        session.add(account_log)
        session.add(account)


def update_account_for_debit(
    remitting_account_number, payment_amount, session
) -> Account:
    account = (
        session.execute(
            select(Account).where(Account.account_number == remitting_account_number)
        )
        .scalars()
        .first()
    )
    account.book_balance -= payment_amount
    account.blocked_amount -= payment_amount
    account.available_balance = account.book_balance - account.blocked_amount
    return account


def update_account_for_credit(
    beneficiary_name,
    credit_account_number,
    account_holder_phone,
    account_holder_email,
    remitting_currency,
    payment_amount,
    session,
) -> Account:
    account = (
        session.execute(
            select(Account).where(Account.account_number == credit_account_number)
        )
        .scalars()
        .first()
    )
    if not account:
        account = Account(
            account_holder_name=beneficiary_name,
            account_number=credit_account_number,
            book_balance=0,
            available_balance=0,
            blocked_amount=0,
            account_holder_phone=account_holder_phone,
            account_holder_email=account_holder_email,
            account_currency=remitting_currency,
            active=True,
        )
        session.add(account)
    account.book_balance += payment_amount
    account.available_balance = account.book_balance - account.blocked_amount
    return account


def update_fund_block(block_reference_no, payment_amount, session) -> FundBlock:
    fund_block = (
        session.execute(
            select(FundBlock).where(FundBlock.block_reference_no == block_reference_no)
        )
        .scalars()
        .first()
    )
    fund_block.amount_released += payment_amount
    return fund_block
