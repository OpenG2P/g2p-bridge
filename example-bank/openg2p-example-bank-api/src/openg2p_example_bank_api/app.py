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
from sqlalchemy import create_engine

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

        asyncio.run(migrate())


def get_engine():
    if _config.db_datasource:
        db_engine = create_engine(_config.db_datasource)
        return db_engine
