import logging
from decimal import Decimal

import requests
from openg2p_example_bank_models.models import (
    Account,
    AccountingLog,
    AccountStatement,
    AccountStatementStatus,
    DebitCreditTypes,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..app import celery_app, get_engine
from ..config import Settings
from ..utils import Mt940Writer, TransactionType

_config = Settings.get_config()
_engine = get_engine()

_logger = logging.getLogger(_config.logging_default_logger_name)


@celery_app.task(name="account_statement_generator_worker")
def account_statement_generator_worker(account_statement_id: int):
    _logger.info("Generating account statement")
    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)
    with session_maker() as session:
        account_statement = (
            session.execute(
                select(AccountStatement).where(
                    AccountStatement.id == account_statement_id
                )
            )
            .scalars()
            .first()
        )

        if not account_statement:
            _logger.error("Account statement not found")
            return

        account = (
            session.execute(
                select(Account).where(
                    Account.account_number == account_statement.account_number
                )
            )
            .scalars()
            .first()
        )

        if not account:
            _logger.error("Account not found")
            return

        account_logs = (
            session.execute(
                select(AccountingLog).where(
                    AccountingLog.account_number == account_statement.account_number,
                    AccountingLog.reported_in_mt940.is_(False),
                )
            )
            .scalars()
            .all()
        )

        if not account_logs:
            _logger.error("Account logs not found")
            return

        mt940_writer = Mt940Writer.get_component()
        currency = account.account_currency
        statement_date = account_statement.account_statement_date
        mt940_account = account.account_number
        mt940_opening_balance = mt940_writer.create_balance(
            Decimal("100000000"), statement_date, currency
        )
        mt940_closing_balance = mt940_writer.create_balance(
            Decimal(account.book_balance), statement_date, currency
        )

        transactions = []
        for account_log in account_logs:
            transaction_debit_credit = account_log.debit_credit
            if account_log.debit_credit == DebitCreditTypes.DEBIT:
                transaction_debit_credit = "D"
            if account_log.debit_credit == DebitCreditTypes.CREDIT:
                transaction_debit_credit = "C"
            if (
                account_log.debit_credit == DebitCreditTypes.DEBIT
                and account_log.transaction_amount < 0
            ):
                transaction_debit_credit = "RD"
            if (
                account_log.debit_credit == DebitCreditTypes.CREDIT
                and account_log.transaction_amount < 0
            ):
                transaction_debit_credit = "RC"

            transactions.append(
                mt940_writer.create_transaction(
                    account_log.transaction_date,
                    account_log.transaction_date,
                    transaction_debit_credit,
                    Decimal(abs(account_log.transaction_amount)),
                    TransactionType.transfer,
                    account_log.customer_reference_no,
                    account_log.reference_no,
                    "",
                    "",
                    f"{account_log.narrative_1}\n{account_log.narrative_2}"
                    f"\n{account_log.narrative_3}\n{account_log.narrative_4}"
                    f"\n{account_log.narrative_5}\n{account_log.narrative_6}",
                )
            )
            # Update the log to indicate that it has been reported in the MT940 statement
            account_log.reported_in_mt940 = True

        statement = mt940_writer.create_statement(
            account_statement_id,
            mt940_account,
            "1/1",
            mt940_opening_balance,
            mt940_closing_balance,
            transactions,
        )
        mt940_statement = mt940_writer.format_statement(statement)
        account_statement.account_statement_lob = str(mt940_statement)
        account_statement.account_statement_generation_status = (
            AccountStatementStatus.SUCCESS
        )
        _logger.info("Account statement generated successfully")
        session.commit()

        # Prepare the in-memory file content
        mt940_content = str(mt940_statement)

        # Send multipart/form-data with the file field required by FastAPI
        files = {
            "statement_file": ("statement.mt940", mt940_content, "text/plain"),
        }

        # If your API also expects additional form fields, include them here:
        # data = {"account_statement_id": str(account_statement_id)}
        data = None

        try:
            response = requests.post(
                _config.mt940_statement_callback_url,
                files=files,
                data=data,
                timeout=30,
            )
            response.raise_for_status()
            _logger.info("MT940 statement uploaded successfully")
        except requests.exceptions.RequestException as e:
            # Include response text if available for easier troubleshooting
            err_text = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    err_text = f" | response_text={e.response.text}"
                except Exception:
                    pass
            _logger.error(f"Failed to upload MT940 statement: {e}{err_text}")
