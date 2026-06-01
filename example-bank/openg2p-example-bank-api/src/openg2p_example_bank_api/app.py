# ruff: noqa: E402
import asyncio
import logging

from openg2p_example_bank_api.config import Settings

_config = Settings.get_config()
from openg2p_example_bank_models.models import (
    Account,
    AccountingLog,
    AccountStatement,
    FundBlock,
    InitiatePaymentBatchRequest,
    InitiatePaymentRequest,
)
from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.context import dbengine
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select

from openg2p_example_bank_api.controllers import (
    AccountStatementController,
    BlockFundsController,
    FundAvailabilityController,
    PaymentController,
    USSDController,
)

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()

        BlockFundsController().post_init()
        FundAvailabilityController().post_init()
        PaymentController().post_init()
        AccountStatementController().post_init()
        USSDController().post_init()

    def migrate_database(self, args):
        super().migrate_database(args)

        async def migrate():
            _logger.info("Migrating database")
            await Account.create_migrate()
            await FundBlock.create_migrate()
            await InitiatePaymentRequest.create_migrate()
            await InitiatePaymentBatchRequest.create_migrate()
            await AccountStatement.create_migrate()
            await AccountingLog.create_migrate()
            _logger.info("Database migration completed")
            await self._seed_treasury_account()

        asyncio.run(migrate())

    async def _seed_treasury_account(self):
        """Idempotently seed the treasury/sponsor account used by the G2P Bridge
        for digital cash transfer. Created only if absent; existing rows (and
        their balances) are left untouched."""
        if not _config.seed_treasury_account:
            return
        if not _config.treasury_account_number:
            _logger.warning(
                "seed_treasury_account is enabled but treasury_account_number is empty; skipping seed"
            )
            return

        account_number = _config.treasury_account_number
        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            existing = (
                (
                    await session.execute(
                        select(Account).where(Account.account_number == account_number)
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                _logger.info(
                    "Treasury account %s already exists; leaving as-is", account_number
                )
                return
            session.add(
                Account(
                    account_holder_name=_config.treasury_account_holder_name,
                    account_number=account_number,
                    account_currency=_config.treasury_account_currency,
                    account_holder_phone=_config.treasury_account_holder_phone
                    or f"treasury-{account_number}",
                    account_holder_email=_config.treasury_account_holder_email
                    or f"treasury-{account_number}@example.invalid",
                    book_balance=_config.treasury_available_balance,
                    available_balance=_config.treasury_available_balance,
                    blocked_amount=0,
                )
            )
            await session.commit()
            _logger.info(
                "Seeded treasury account %s (balance %s %s)",
                account_number,
                _config.treasury_available_balance,
                _config.treasury_account_currency,
            )


def get_engine():
    if _config.db_datasource:
        db_engine = create_engine(_config.db_datasource)
        return db_engine
