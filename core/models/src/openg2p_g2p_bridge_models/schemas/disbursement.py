import datetime
from typing import List, Optional

from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
)
from pydantic import BaseModel

from ..models import DisbursementCancellationStatus
from .disbursement_envelope import DisbursementBatchControlGeoPayload


# Disbursement
class DisbursementPayload(BaseModel):
    disbursement_id: str
    disbursement_envelope_id: Optional[str] = None
    beneficiary_id: Optional[str] = None
    beneficiary_name: Optional[str] = None
    disbursement_quantity: Optional[float] = None
    compute_elements: Optional[dict] = None
    narrative: Optional[str] = None
    receipt_time_stamp: Optional[datetime.datetime] = None
    cancellation_status: Optional[DisbursementCancellationStatus] = None
    cancellation_time_stamp: Optional[datetime.datetime] = None
    disbursement_cycle_id: Optional[int] = None
    disbursement_batch_control_id: Optional[str] = None
    response_error_codes: Optional[List[str]] = None


class DisbursementRequestBody(G2PRequestBody):
    disbursement_batch_control_id: Optional[str] = None
    request_payload: List[DisbursementPayload]


class DisbursementRequest(G2PRequest):
    request_body: DisbursementRequestBody


class DisbursementResponseBody(G2PResponseBody):
    disbursement_batch_control_id: Optional[str] = None
    response_payload: Optional[List[DisbursementPayload]] = None


class DisbursementResponse(G2PResponse):
    response_body: DisbursementResponseBody


# Disbursement Batch Control
class DisbursementBatchControlPayload(BaseModel):
    disbursement_batch_control_id: str
    disbursement_cycle_id: int = None
    disbursement_cycle_code_mnemonic: Optional[str] = None
    disbursement_envelope_id: str
    benefit_code_id: Optional[int] = None
    benefit_code_mnemonic: Optional[str] = None
    benefit_type: str
    measurement_unit: str
    fa_resolution_status: Optional[str] = None
    fa_resolution_timestamp: Optional[datetime.datetime] = None
    fa_resolution_latest_error_code: Optional[str] = None
    fa_resolution_attempts: Optional[int] = None
    sponsor_bank_dispatch_status: Optional[str] = None
    sponsor_bank_dispatch_timestamp: Optional[datetime.datetime] = None
    sponsor_bank_dispatch_latest_error_code: Optional[str] = None
    sponsor_bank_dispatch_attempts: Optional[int] = None
    geo_resolution_status: Optional[str] = None
    geo_resolution_timestamp: Optional[datetime.datetime] = None
    geo_resolution_latest_error_code: Optional[str] = None
    geo_resolution_attempts: Optional[int] = None
    warehouse_allocation_status: Optional[str] = None
    warehouse_allocation_timestamp: Optional[datetime.datetime] = None
    warehouse_allocation_latest_error_code: Optional[str] = None
    warehouse_allocation_attempts: Optional[int] = None
    agency_allocation_status: Optional[str] = None
    agency_allocation_timestamp: Optional[datetime.datetime] = None
    agency_allocation_latest_error_code: Optional[str] = None
    agency_allocation_attempts: Optional[int] = None
    disbursement_batch_control_geos: Optional[List[DisbursementBatchControlGeoPayload]] = None


class DisbursementBatchControlRequestBody(G2PRequestBody):
    request_payload: str


class DisbursementBatchControlRequest(G2PRequest):
    request_body: DisbursementBatchControlRequestBody


class DisbursementBatchControlResponseBody(G2PResponseBody):
    response_payload: Optional[DisbursementBatchControlPayload] = None


class DisbursementBatchControlResponse(G2PResponse):
    response_body: DisbursementBatchControlResponseBody
