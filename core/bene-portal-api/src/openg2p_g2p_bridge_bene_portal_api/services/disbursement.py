import logging
from datetime import datetime
from typing import List

from openg2p_fastapi_common.context import dbengine

from openg2p_fastapi_common.schemas import G2PResponseHeader, G2PResponseStatus, G2PPaginationResponse
from openg2p_fastapi_common.service import BaseService
from openg2p_fastapi_auth_models.schemas import AuthCredentials
from openg2p_g2p_bridge_models.errors import BridgeException
from openg2p_g2p_bridge_models.models import (
    Disbursement,
    DisbursementBatchControl,
    DisbursementEnvelope,
)
from openg2p_g2p_bridge_models.schemas import (
    DisbursementSchemaForPortal,
    DisbursementRequestForPortal,
    DisbursementResponseForPortal,
    DisbursementResponseBody,
    DisbursementSummary,
    DisbursementSummaryRequest,
    DisbursementSummaryResponse,
    DisbursementSummaryResponseBody,
    DisbursementResponseBodyForPortal,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class DisbursementService(BaseService):
    async def get_all_disbursements(
        self, disbursement_request: DisbursementRequestForPortal, auth: AuthCredentials
    ) -> DisbursementResponseForPortal:
        _logger.info("Get All Disbursements Request")

        pagination = (
            disbursement_request.request_body.pagination_request
            if disbursement_request.request_body
            else None
        )

        # Extract pagination parameters
        page_size = pagination.page_size if pagination else 30
        current_page = pagination.current_page if pagination else 1
        offset = (current_page - 1) * page_size

        # Extract beneficiary_id from auth.sub
        beneficiary_id: str = auth.sub

        session_maker_bridge = async_sessionmaker(dbengine.get(), expire_on_commit=False)

        async with session_maker_bridge() as session_bridge:
            # Count total disbursements for the beneficiary
            total_count_result = await session_bridge.execute(
                select(func.count(Disbursement.id)).where(Disbursement.beneficiary_id == beneficiary_id)
            )
            total_count = total_count_result.scalar()
            total_pages = (total_count + page_size - 1) // page_size

            # Fetch paginated disbursements with related data
            disbursements_query = (
                select(
                    Disbursement,
                    DisbursementEnvelope,
                    DisbursementBatchControl,
                )
                .join(
                    DisbursementEnvelope,
                    DisbursementEnvelope.id == Disbursement.disbursement_envelope_id,
                )
                .join(
                    DisbursementBatchControl,
                    DisbursementBatchControl.disbursement_envelope_id == DisbursementEnvelope.id,
                )
                .where(Disbursement.beneficiary_id == beneficiary_id)
                .offset(offset)
                .limit(page_size)
            )

            disbursements_result = await session_bridge.execute(disbursements_query)
            disbursements_data = disbursements_result.all()

            if not disbursements_data:
                raise BridgeException(
                    code="DISBURSEMENT_NOT_FOUND",
                    message="No disbursements found for the beneficiary",
                )

            # Map to portal disbursement format
            disbursements: List[DisbursementSchemaForPortal] = []
            for disbursement, envelope, batch_control in disbursements_data:
                disbursements.append(
                    DisbursementSchemaForPortal(
                        disbursement_id=str(disbursement.id),
                        disbursement_envelope_id=disbursement.disbursement_envelope_id,
                        program_mnemonic=envelope.benefit_program_mnemonic,
                        cycle_code_mnemonic=envelope.cycle_code_mnemonic,
                        disbursement_quantity=disbursement.disbursement_quantity,
                        benefit_code=envelope.benefit_code_mnemonic,
                        benefit_type=envelope.benefit_type,
                        agency_mnemonic="AGENCY_PLACEHOLDER",  # TODO: Map from actual agency data
                        measurement_unit=envelope.measurement_unit,
                        disbursement_schedule_date=envelope.disbursement_schedule_date,
                    )
                )

        return await self.construct_disbursement_success_response(
            disbursement_request, disbursements, total_count, total_pages
        )

    async def construct_disbursement_success_response(
        self,
        disbursement_request: DisbursementRequestForPortal,
        disbursements: List[DisbursementSchemaForPortal],
        total_count: int = 0,
        total_pages: int = 0,
    ) -> DisbursementResponseForPortal:
        disbursement_response = DisbursementResponseForPortal(
            response_header=G2PResponseHeader(
                request_id=disbursement_request.request_header.request_id,
                response_status=G2PResponseStatus.SUCCESS,
                response_timestamp=datetime.now(),
                response_error_code=None,
                response_error_message=None,
            ),
            response_body=DisbursementResponseBodyForPortal(
                pagination_response=G2PPaginationResponse(
                    number_of_items=total_count,
                    number_of_pages=total_pages,
                ),
                response_payload=disbursements,
            ),
        )
        return disbursement_response

    async def construct_disbursement_failure_response(
        self,
        disbursement_request: DisbursementRequestForPortal,
        error_code: str,
        error_message: str | None = None,
    ) -> DisbursementResponseForPortal:
        disbursement_response = DisbursementResponseForPortal(
            response_header=G2PResponseHeader(
                request_id=disbursement_request.request_header.request_id,
                response_status=G2PResponseStatus.ERROR,
                response_error_code=error_code,
                response_error_message=error_message,
                response_timestamp=datetime.now(),
            ),
            response_body=DisbursementResponseBodyForPortal(
                response_payload=[],
            ),
        )
        return disbursement_response

    async def get_disbursement_summary_till_date(
        self, disbursement_summary_request: DisbursementSummaryRequest, auth: AuthCredentials
    ) -> DisbursementSummaryResponse:
        _logger.info("Get Disbursement Summary Till Date Request")

        # Extract beneficiary_id from auth.sub
        beneficiary_id: str = auth.sub

        session_maker_bridge = async_sessionmaker(dbengine.get(), expire_on_commit=False)

        async with session_maker_bridge() as session_bridge:
            # Query to get disbursement summary grouped by benefit_code_mnemonic
            summary_query = (
                select(
                    DisbursementEnvelope.benefit_code_mnemonic,
                    DisbursementEnvelope.benefit_type,
                    DisbursementEnvelope.measurement_unit,
                    func.sum(Disbursement.disbursement_quantity).label("total_quantity_received"),
                )
                .join(
                    DisbursementEnvelope,
                    DisbursementEnvelope.id == Disbursement.disbursement_envelope_id,
                )
                .where(Disbursement.beneficiary_id == beneficiary_id)
                .group_by(
                    DisbursementEnvelope.benefit_code_mnemonic,
                    DisbursementEnvelope.benefit_type,
                    DisbursementEnvelope.measurement_unit,
                )
            )

            summary_result = await session_bridge.execute(summary_query)
            summary_data = summary_result.all()

            if not summary_data:
                raise BridgeException(
                    code="DISBURSEMENT_SUMMARY_NOT_FOUND",
                    message="No disbursement summary found for the beneficiary",
                )

            # Map to disbursement summary format
            disbursement_summaries: List[DisbursementSummary] = []
            for row in summary_data:
                disbursement_summaries.append(
                    DisbursementSummary(
                        benefit_code_mnemonic=row.benefit_code_mnemonic,
                        benefit_type=row.benefit_type,
                        measurement_unit=row.measurement_unit,
                        total_quantity_received=float(row.total_quantity_received),
                    )
                )

        return await self.construct_disbursement_summary_success_response(
            disbursement_summary_request, disbursement_summaries
        )

    async def construct_disbursement_summary_success_response(
        self,
        disbursement_summary_request: DisbursementSummaryRequest,
        disbursement_summaries: List[DisbursementSummary],
    ) -> DisbursementSummaryResponse:
        disbursement_summary_response = DisbursementSummaryResponse(
            response_header=G2PResponseHeader(
                request_id=disbursement_summary_request.request_header.request_id,
                response_status=G2PResponseStatus.SUCCESS,
                response_timestamp=datetime.now(),
                response_error_code=None,
                response_error_message=None,
            ),
            response_body=DisbursementSummaryResponseBody(
                response_payload=disbursement_summaries,
            ),
        )
        return disbursement_summary_response

    async def construct_disbursement_summary_failure_response(
        self,
        disbursement_summary_request: DisbursementSummaryRequest,
        error_code: str,
        error_message: str | None = None,
    ) -> DisbursementSummaryResponse:
        disbursement_summary_response = DisbursementSummaryResponse(
            response_header=G2PResponseHeader(
                request_id=disbursement_summary_request.request_header.request_id,
                response_status=G2PResponseStatus.ERROR,
                response_timestamp=datetime.now(),
                response_error_code=error_code,
                response_error_message=error_message,
            ),
            response_body=DisbursementSummaryResponseBody(
                response_payload=[],
            ),
        )
        return disbursement_summary_response
