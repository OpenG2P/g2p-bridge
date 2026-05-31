import logging

from openg2p_example_bank_models.models import (
    AccountStatement,
    AccountStatementStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..app import celery_app, get_engine
from ..config import Settings

_config = Settings.get_config()
_engine = get_engine()
_logger = logging.getLogger(_config.logging_default_logger_name)


@celery_app.task(name="account_statement_generator_beat_producer")
def account_statement_generator_beat_producer():
    _logger.info("Processing account statement generation")
    session_maker = sessionmaker(bind=_engine, expire_on_commit=False)
    with session_maker() as session:
        account_statements = (
            session.execute(
                select(AccountStatement).where(
                    (
                        AccountStatement.account_statement_generation_status.in_(
                            ["PENDING"]
                        )
                    )
                    & (AccountStatement.active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        _logger.info(
            f"Picked up {len(account_statements)} account statements for generation"
        )
        for account_statement in account_statements:
            _logger.info(
                f"Queuing account statement generation for account: {account_statement.account_number}"
            )
            celery_app.send_task(
                "account_statement_generator_worker",
                args=[account_statement.id],
                queue="example_bank_queue",
            )
            account_statement.account_statement_generation_status = (
                AccountStatementStatus.PROCESSING
            )
            session.commit()

        _logger.info(
            f"Account statement generated for {len(account_statements)} accounts"
        )
