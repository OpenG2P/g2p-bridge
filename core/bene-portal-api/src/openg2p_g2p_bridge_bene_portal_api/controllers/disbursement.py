import logging
from typing import Annotated
from fastapi import Depends

from openg2p_fastapi_auth.auth import AuthFactory
from openg2p_fastapi_auth_models.schemas import AuthCredentials

from openg2p_fastapi_common.controller import BaseController
from openg2p_g2p_bridge_models.errors import BridgeException
from openg2p_g2p_bridge_models.schemas import (
    DisbursementRequestForPortal,
    DisbursementResponseForPortal,
    DisbursementSummaryRequest,
    DisbursementSummaryResponse,
)

from ..config import Settings
from ..services import DisbursementService

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class DisbursementController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["Bridge Bene Portal - Disbursements"]
        self.disbursement_service = DisbursementService.get_component()
        self.router.prefix = "/disbursement"

        self.router.add_api_route(
            "/get_all_disbursements",
            self.get_all_disbursements,
            responses={200: {"model": DisbursementResponseForPortal}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_disbursement_summary_till_date",
            self.get_disbursement_summary_till_date,
            responses={200: {"model": DisbursementSummaryResponse}},
            methods=["POST"],
        )

    async def get_all_disbursements(
        self,
        auth: Annotated[AuthCredentials, Depends(AuthFactory())],
        disbursement_request: DisbursementRequestForPortal,
    ) -> DisbursementResponseForPortal:
        _logger.debug("Get All Disbursements Request: %s", disbursement_request)
        try:
            disbursement_response: DisbursementResponseForPortal = (
                await self.disbursement_service.get_all_disbursements(disbursement_request, auth)
            )
            _logger.info("Disbursements retrieved successfully")
            _logger.debug("Get All Disbursements Response: %s", disbursement_response)
            return disbursement_response
        except BridgeException as e:
            error_response: DisbursementResponseForPortal = (
                await self.disbursement_service.construct_disbursement_failure_response(
                    disbursement_request, e.code, e.message
                )
            )
            return error_response

    async def get_disbursement_summary_till_date(
        self,
        auth: Annotated[AuthCredentials, Depends(AuthFactory())],
        disbursement_summary_request: DisbursementSummaryRequest,
    ) -> DisbursementSummaryResponse:
        _logger.debug("Get Disbursement Summary Till Date Request: %s", disbursement_summary_request)
        try:
            disbursement_summary_response: DisbursementSummaryResponse = (
                await self.disbursement_service.get_disbursement_summary_till_date(
                    disbursement_summary_request, auth
                )
            )
            _logger.info("Disbursement summary retrieved successfully")
            _logger.debug("Get Disbursement Summary Till Date Response: %s", disbursement_summary_response)
            return disbursement_summary_response
        except BridgeException as e:
            error_response: DisbursementSummaryResponse = (
                await self.disbursement_service.construct_disbursement_summary_failure_response(
                    disbursement_summary_request, e.code, e.message
                )
            )
            return error_response
