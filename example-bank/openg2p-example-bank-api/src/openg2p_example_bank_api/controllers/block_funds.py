import logging
import uuid

from openg2p_example_bank_models.models import Account, FundBlock
from openg2p_example_bank_models.schemas import (
    BlockFundsRequest,
    BlockFundsResponse,
)
from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.controller import BaseController
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class BlockFundsController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["Funds Management"]

        self.router.add_api_route(
            "/block_funds",
            self.block_funds,
            response_model=BlockFundsResponse,
            methods=["POST"],
        )

    async def block_funds(self, request: BlockFundsRequest) -> BlockFundsResponse:
        _logger.info("Blocking funds")
        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            stmt = select(Account).where(
                (Account.account_number == request.account_number)
                & (Account.account_currency == request.currency)
            )
            result = await session.execute(stmt)
            account = result.scalars().first()

            if not account:
                _logger.error("Account not found")
                return BlockFundsResponse(
                    status="failed",
                    block_reference_no="",
                    error_message="Account not found",
                )
            if account.available_balance < request.amount:
                _logger.error("Insufficient funds")
                return BlockFundsResponse(
                    status="failed",
                    block_reference_no="",
                    error_message="Insufficient funds",
                )

            await session.execute(
                update(Account)
                .where(Account.account_number == request.account_number)
                .values(
                    available_balance=account.book_balance
                    - (account.blocked_amount + request.amount),
                    blocked_amount=account.blocked_amount + request.amount,
                )
            )

            block_reference_no = str(uuid.uuid4())
            fund_block = FundBlock(
                block_reference_no=block_reference_no,
                account_number=request.account_number,
                amount=request.amount,
                currency=request.currency,
                active=True,
            )
            session.add(fund_block)

            await session.commit()
            _logger.info("Funds blocked successfully")
            return BlockFundsResponse(
                status="success",
                block_reference_no=block_reference_no,
                error_message="",
            )
