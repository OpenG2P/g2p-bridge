from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from openg2p_g2p_bridge_partner_api.controllers import DisbursementController
from openg2p_g2p_bridge_models.errors.codes import G2PBridgeErrorCodes
from openg2p_g2p_bridge_models.errors.exceptions import DisbursementException
from openg2p_g2p_bridge_models.models import CancellationStatus
from openg2p_g2p_bridge_models.schemas import (
    DisbursementPayload,
    DisbursementRequest,
    DisbursementRequestBody,
    DisbursementResponse,
    DisbursementResponseBody,
)
from openg2p_g2p_bridge_models.schemas import (
    G2PRequestHeader,
    G2PResponseStatus,
    G2PResponseHeader,
)


def mock_create_disbursements(is_valid, disbursement_request):
    if not is_valid:
        raise DisbursementException(
            code=G2PBridgeErrorCodes.INVALID_DISBURSEMENT_PAYLOAD,
            disbursement_payloads=disbursement_request.request_body.request_payload,
        )
    return disbursement_request


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
async def test_create_disbursements_success(mock_request_validation, mock_service_get_component):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    mock_service_instance = AsyncMock()
    disbursement_payloads = [
        DisbursementPayload(
            disbursement_id="disb123",
            disbursement_envelope_id="env123",
            beneficiary_id="123AB",
            disbursement_quantity=1000,
        )
    ]
    disbursement_request = DisbursementRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
            sender_app_mnemonic="test_app",
            sender_app_url="http://test.app",
        ),
        request_body=DisbursementRequestBody(
            request_payload=disbursement_payloads,
        ),
    )
    mock_service_instance.create_disbursements = AsyncMock(
        return_value=mock_create_disbursements(True, disbursement_request)
    )
    mock_service_instance.construct_disbursement_success_response = AsyncMock(
        return_value=DisbursementResponse(
            response_header=G2PResponseHeader(
                request_id="123",
                response_status=G2PResponseStatus.SUCCESS,
                response_error_code=None,
                response_error_message=None,
                response_timestamp=datetime.now(),
            ),
            response_body=DisbursementResponseBody(
                response_payload=disbursement_payloads,
            ),
        )
    )

    mock_service_get_component.return_value = mock_service_instance

    controller = DisbursementController()
    request_payload = disbursement_request

    response = await controller.create_disbursements(request_payload, is_signature_valid=True)

    assert response.response_body.response_payload == disbursement_payloads


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
async def test_create_disbursements_failure(mock_request_validation, mock_service_get_component):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    mock_service_instance = AsyncMock()
    disbursement_payloads = [
        DisbursementPayload(
            disbursement_id="disb123",
            disbursement_envelope_id="env123",
            beneficiary_id="123AB",
            disbursement_quantity=1000,
        )
    ]
    disbursement_request = DisbursementRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
            sender_app_mnemonic="test_app",
            sender_app_url="http://test.app",
        ),
        request_body=DisbursementRequestBody(
            request_payload=disbursement_payloads,
        ),
    )
    mock_service_instance.create_disbursements = AsyncMock(
        side_effect=lambda req: mock_create_disbursements(False, req)
    )
    mock_service_instance.construct_disbursement_error_response = AsyncMock(
        return_value=DisbursementResponse(
            response_header=G2PResponseHeader(
                request_id="123",
                response_status=G2PResponseStatus.ERROR,
                response_error_code=G2PBridgeErrorCodes.INVALID_DISBURSEMENT_PAYLOAD.value,
                response_error_message=G2PBridgeErrorCodes.INVALID_DISBURSEMENT_PAYLOAD.value,
                response_timestamp=datetime.now(),
            ),
            response_body=DisbursementResponseBody(
                response_payload=disbursement_payloads,
            ),
        )
    )

    mock_service_get_component.return_value = mock_service_instance

    controller = DisbursementController()
    request_payload = disbursement_request

    response = await controller.create_disbursements(request_payload, is_signature_valid=True)

    assert (
        response.response_header.response_error_code == G2PBridgeErrorCodes.INVALID_DISBURSEMENT_PAYLOAD.value
    )


def mock_cancel_disbursements(is_valid, disbursement_request):
    if not is_valid:
        raise DisbursementException(
            code=G2PBridgeErrorCodes.DISBURSEMENT_ALREADY_CANCELED,
            disbursement_payloads=disbursement_request.request_body.request_payload,
        )
    for payload in disbursement_request.request_body.request_payload:
        payload.cancellation_status = CancellationStatus.CANCELLED
        payload.cancellation_time_stamp = datetime.now()
    return disbursement_request


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
async def test_cancel_disbursements_success(mock_request_validation, mock_service_get_component):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    mock_service_instance = AsyncMock()
    disbursement_payloads = [
        DisbursementPayload(
            disbursement_id="123",
            beneficiary_id="123AB",
            disbursement_quantity=1000,
            cancellation_status=None,
        )
    ]
    disbursement_request = DisbursementRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
            sender_app_mnemonic="test_app",
            sender_app_url="http://test.app",
        ),
        request_body=DisbursementRequestBody(
            request_payload=disbursement_payloads,
        ),
    )
    mock_service_instance.cancel_disbursements = AsyncMock(
        return_value=mock_cancel_disbursements(True, disbursement_request)
    )
    mock_service_instance.construct_disbursement_success_response = AsyncMock(
        return_value=DisbursementResponse(
            response_header=G2PResponseHeader(
                request_id="123",
                response_status=G2PResponseStatus.SUCCESS,
                response_error_code=None,
                response_error_message=None,
                response_timestamp=datetime.now(),
            ),
            response_body=DisbursementResponseBody(
                response_payload=disbursement_payloads,
            ),
        )
    )

    mock_service_get_component.return_value = mock_service_instance

    controller = DisbursementController()
    request_payload = disbursement_request

    response = await controller.cancel_disbursements(request_payload, is_signature_valid=True)

    assert response.response_header.response_status == G2PResponseStatus.SUCCESS
    assert all(
        payload.cancellation_status == CancellationStatus.CANCELLED
        for payload in response.response_body.response_payload
    )


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
async def test_cancel_disbursements_failure(mock_request_validation, mock_service_get_component):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    mock_service_instance = AsyncMock()
    disbursement_payloads = [
        DisbursementPayload(
            disbursement_id="123",
            beneficiary_id="123AB",
            disbursement_quantity=1000,
            cancellation_status=None,
        )
    ]
    disbursement_request = DisbursementRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
            sender_app_mnemonic="test_app",
            sender_app_url="http://test.app",
        ),
        request_body=DisbursementRequestBody(
            request_payload=disbursement_payloads,
        ),
    )
    mock_service_instance.cancel_disbursements = AsyncMock(
        side_effect=lambda req: mock_cancel_disbursements(False, req)
    )
    mock_service_instance.construct_disbursement_error_response = AsyncMock(
        return_value=DisbursementResponse(
            response_header=G2PResponseHeader(
                request_id="123",
                response_status=G2PResponseStatus.ERROR,
                response_error_code=G2PBridgeErrorCodes.DISBURSEMENT_ALREADY_CANCELED.value,
                response_error_message=G2PBridgeErrorCodes.DISBURSEMENT_ALREADY_CANCELED.value,
                response_timestamp=datetime.now(),
            ),
            response_body=DisbursementResponseBody(
                response_payload=disbursement_payloads,
            ),
        )
    )

    mock_service_get_component.return_value = mock_service_instance

    controller = DisbursementController()
    request_payload = disbursement_request

    response = await controller.cancel_disbursements(request_payload, is_signature_valid=True)

    assert response.response_header.response_status == G2PResponseStatus.ERROR
    assert (
        response.response_header.response_error_code
        == G2PBridgeErrorCodes.DISBURSEMENT_ALREADY_CANCELED.value
    )
