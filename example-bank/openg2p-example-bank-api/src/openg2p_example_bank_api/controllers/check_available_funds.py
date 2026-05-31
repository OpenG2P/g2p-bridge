import logging

from openg2p_example_bank_models.models import Account
from openg2p_example_bank_models.schemas import (
    CheckFundRequest,
    CheckFundResponse,
)
from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.controller import BaseController
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class FundAvailabilityController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["Fund Availability"]

        self.router.add_api_route(
            "/check_funds",
            self.check_available_funds,
            response_model=CheckFundResponse,
            methods=["POST"],
        )

    async def check_available_funds(
        self, request: CheckFundRequest
    ) -> CheckFundResponse:
        _logger.info("Checking available funds")
        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            stmt = select(Account).where(
                Account.account_number == request.account_number
            )
            result = await session.execute(stmt)
            account = result.scalars().first()

            if not account:
                _logger.error("Account not found")
                return CheckFundResponse(
                    status="failed",
                    account_number=request.account_number,
                    has_sufficient_funds=False,
                    error_message="Account not found",
                )

            if account.available_balance >= request.total_funds_needed:
                _logger.info("Sufficient funds")
                return CheckFundResponse(
                    status="success",
                    account_number=account.account_number,
                    has_sufficient_funds=True,
                    error_message="",
                )
            else:
                _logger.error("Insufficient funds")
                return CheckFundResponse(
                    status="failed",
                    account_number=account.account_number,
                    has_sufficient_funds=False,
                    error_message="Insufficient funds",
                )
