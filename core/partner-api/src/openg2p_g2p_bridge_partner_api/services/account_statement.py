import logging
import uuid
from datetime import datetime

from fastapi import UploadFile
from openg2p_fastapi_common.context import dbengine
from openg2p_fastapi_common.service import BaseService
from openg2p_g2p_bridge_models.errors.codes import G2PBridgeErrorCodes
from openg2p_g2p_bridge_models.models import AccountStatement, AccountStatementLob
from openg2p_g2p_bridge_models.schemas import (
    AccountStatementResponse,
    AccountStatementPayload,
    AccountStatementResponseBody,
)
from openg2p_fastapi_common.schemas import G2PResponseHeader, G2PResponseStatus
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class AccountStatementService(BaseService):
    async def upload_mt940(self, statement_file: UploadFile) -> str:
        _logger.info("Uploading statement file")
        try:
            statement_file = await statement_file.read()
        except Exception as e:
            _logger.error(f"Error reading file: {str(e)}")
            raise e

        statement_id = str(uuid.uuid4())
        statement_date = datetime.now()

        session_maker = async_sessionmaker(dbengine.get(), expire_on_commit=False)
        async with session_maker() as session:
            statement = AccountStatement(
                statement_id=statement_id,
                statement_date=statement_date,
            )
            session.add(statement)

            statement_lob = AccountStatementLob(
                statement_id=statement_id,
                statement_lob=str(statement_file.decode("utf-8")),
            )
            session.add(statement_lob)

            await session.commit()
        _logger.info("Statement file uploaded successfully")
        return statement_id

    async def construct_account_statement_success_response(
        self, statement_id: str
    ) -> AccountStatementResponse:
        _logger.info("Constructing account statement success response")
        response_payload = AccountStatementPayload(
            statement_id=statement_id,
        )
        return AccountStatementResponse(
            response_header=G2PResponseHeader(
                request_id="",
                response_status=G2PResponseStatus.SUCCESS,
                response_error_code=None,
                response_error_message=None,
                response_timestamp=datetime.now(),
            ),
            response_body=AccountStatementResponseBody(
                response_payload=response_payload,
            ),
        )

    async def construct_account_statement_error_response(
        self, code: G2PBridgeErrorCodes
    ) -> AccountStatementResponse:
        _logger.error("Constructing account statement error response")
        return AccountStatementResponse(
            response_header=G2PResponseHeader(
                request_id="",
                response_status=G2PResponseStatus.ERROR,
                response_error_code=code.value,
                response_error_message=code.description,
                response_timestamp=datetime.now(),
            ),
            response_body=AccountStatementResponseBody(
                response_payload=None,
            ),
        )
