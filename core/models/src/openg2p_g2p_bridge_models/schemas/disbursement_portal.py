from datetime import date, datetime
from typing import List, Optional

from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestHeader,
    G2PRequestBody,
    G2PPaginationRequest,
    G2PResponse,
    G2PResponseHeader,
    G2PResponseBody,
    G2PPaginationResponse,
    G2PResponseStatus,
)
from pydantic import BaseModel


# Disbursement
class Disbursement(BaseModel):
    disbursement_id: str
    disbursement_envelope_id: Optional[str] = None
    program_mnemonic: str
    cycle_code_mnemonic: str
    disbursement_quantity: float
    benefit_code: str
    benefit_type: str
    agency_mnemonic: str
    measurement_unit: str
    disbursement_schedule_date: date


class DisbursementRequestBody(G2PRequestBody):
    request_payload: Optional[dict] = None


class DisbursementRequest(G2PRequest):
    request_body: Optional[DisbursementRequestBody] = None


class DisbursementResponseBody(G2PResponseBody):
    response_payload: List[Disbursement]


class DisbursementResponse(G2PResponse):
    response_body: DisbursementResponseBody


# Disbursement Summary
class DisbursementSummary(BaseModel):
    benefit_code_mnemonic: str
    benefit_type: str  # TODO: Add ENUM
    measurement_unit: str
    total_quantity_received: float


class DisbursementSummaryRequestBody(G2PRequestBody):
    request_payload: Optional[dict] = None


class DisbursementSummaryRequest(G2PRequest):
    request_body: DisbursementSummaryRequestBody


class DisbursementSummaryResponseBody(G2PResponseBody):
    response_payload: List[DisbursementSummary]


class DisbursementSummaryResponse(G2PResponse):
    response_body: DisbursementSummaryResponseBody
