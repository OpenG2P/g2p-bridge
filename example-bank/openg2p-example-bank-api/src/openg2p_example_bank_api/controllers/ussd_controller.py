import logging
from typing import Optional

from fastapi import Form
from fastapi.responses import PlainTextResponse
from openg2p_example_bank_models.models import (
    Account,
    AccountingLog,
    DebitCreditTypes,
)
from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.controller import BaseController
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class USSDController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["USSD Controller"]

        self.router.add_api_route(
            "/ussd",
            self.ussd,
            response_class=PlainTextResponse,
            response_model=str,
            methods=["POST"],
        )

    async def ussd(
        self,
        sessionId: str = Form(),
        serviceCode: str = Form(),
        phoneNumber: str = Form(),
        networkCode: str = Form(),
        text: Optional[str] = Form(""),
    ):
        response: str = ""
        _logger.info(f"Your input is {text}")
        if text == "":
            response = "CON Welcome to Example Bank. What do you want to do? \n \n"
            response += "1. Get account balance \n"
            response += "2. Initiate transfer \n"
            response += "3. See recent transactions"
        elif text == "1":
            response = await self.get_account_balance(phoneNumber)
        elif text == "2":
            response = "END Bye!"
        elif text == "3":
            response = await self.get_recent_transactions(phoneNumber)
        else:
            response = "END Invalid choice selected!"

        return response

    async def get_account_balance(self, phone_number: str) -> str:
        _logger.info("Fetching account balance through USSD")
        _logger.info(f"Phone Number: {phone_number}")
        phone_number_parsed = phone_number[1:]
        _logger.info(f"Parsed Phone Number: {phone_number_parsed}")

        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            account_db_query = select(Account).where(
                Account.account_holder_phone == phone_number_parsed
            )
            result = await session.execute(account_db_query)
            account = result.scalars().first()

            if not account:
                _logger.error("Account not found")
                return f"END Account not found for this phone number: {phone_number}"

            return (
                f"END Available balance in account ending with {account.account_number[-4:]} is"
                f" ${account.available_balance:,.2f}"
            )

    async def get_recent_transactions(self, phone_number: str) -> str:
        _logger.info("Fetching account transactions through USSD")
        _logger.info(f"Phone Number: {phone_number}")
        phone_number_parsed = phone_number[1:]
        _logger.info(f"Parsed Phone Number: {phone_number_parsed}")

        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            account_db_query = select(Account).where(
                Account.account_holder_phone == phone_number_parsed
            )
            account_result = await session.execute(account_db_query)
            account = account_result.scalars().first()

            if not account:
                _logger.error("Account not found")
                return f"END Account not found for this phone number: {phone_number}"

            accounting_logs_query = (
                select(AccountingLog)
                .where(AccountingLog.account_number == account.account_number)
                .order_by(desc(AccountingLog.id))
                .limit(3)
            )
            accounting_log_result = await session.execute(accounting_logs_query)
            accounting_logs = accounting_log_result.scalars()
            transaction_text = ""
            for accounting_log in accounting_logs:
                date_formatted = accounting_log.transaction_date.strftime(
                    "%d/%b"
                ).upper()  # Format and convert to uppercase
                credit_debit_type = (
                    "CR"
                    if accounting_log.debit_credit == DebitCreditTypes.CREDIT
                    else "DR"
                )
                transaction_text += (
                    f"{credit_debit_type} - ${accounting_log.transaction_amount:,.2f} "
                    f"- {date_formatted} - {accounting_log.narrative_3} "
                    f"- {accounting_log.narrative_4} \n"
                )
            return f"END {transaction_text}"
