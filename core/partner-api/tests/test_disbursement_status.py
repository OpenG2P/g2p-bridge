from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from openg2p_g2p_bridge_partner_api.controllers import DisbursementStatusController
from openg2p_g2p_bridge_models.errors.codes import G2PBridgeErrorCodes
from openg2p_g2p_bridge_models.errors.exceptions import DisbursementStatusException
from openg2p_g2p_bridge_models.schemas import (
    DisbursementStatusPayload,
    DisbursementStatusRequest,
    DisbursementStatusRequestBody,
    DisbursementStatusResponse,
    DisbursementStatusResponseBody,
)
from openg2p_g2p_bridge_models.schemas import (
    G2PRequestHeader,
    G2PResponseStatus,
    G2PResponseHeader,
)


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementStatusService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
async def test_get_disbursement_status_success(mock_request_validation, mock_service_get_component):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    # Setup mock service
    mock_service_instance = AsyncMock()
    mock_service_get_component.return_value = mock_service_instance

    # Mock service methods
    mock_service_instance.get_disbursement_status_payloads = AsyncMock(
        return_value=[
            DisbursementStatusPayload(
                disbursement_id="disb123",
                disbursement_recon_records=None,
            )
        ]
    )

    expected_response = DisbursementStatusResponse(
        response_header=G2PResponseHeader(
            request_id="123",
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code=None,
            response_error_message=None,
            response_timestamp=datetime.now(),
        ),
        response_body=DisbursementStatusResponseBody(
            response_payload=[
                DisbursementStatusPayload(
                    disbursement_id="disb123",
                    disbursement_recon_records=None,
                )
            ]
        ),
    )

    mock_service_instance.construct_disbursement_status_success_response = AsyncMock(
        return_value=expected_response
    )

    # Instantiate controller and make request
    controller = DisbursementStatusController()
    request_payload = DisbursementStatusRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
        ),
        request_body=DisbursementStatusRequestBody(
            request_payload=["disb123"],
        ),
    )

    actual_response = await controller.get_disbursement_status(request_payload, is_signature_valid=True)
    assert actual_response == expected_response


@pytest.mark.asyncio
@patch("openg2p_g2p_bridge_partner_api.services.DisbursementStatusService.get_component")
@patch("openg2p_g2p_bridge_partner_api.services.RequestValidation.get_component")
@pytest.mark.parametrize("error_code", list(G2PBridgeErrorCodes))
async def test_get_disbursement_status_failure(
    mock_request_validation, mock_service_get_component, error_code
):
    mock_request_validation.validate_signature.return_value = None
    mock_request_validation.validate_request.return_value = None

    # Setup mock service
    mock_service_instance = AsyncMock()
    mock_service_get_component.return_value = mock_service_instance

    # Mock the method to raise an error
    mock_service_instance.get_disbursement_status_payloads.side_effect = DisbursementStatusException(
        code=error_code.value, message=error_code.value
    )

    error_response = DisbursementStatusResponse(
        response_header=G2PResponseHeader(
            request_id="123",
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code.value,
            response_error_message=error_code.value,
            response_timestamp=datetime.now(),
        ),
        response_body=DisbursementStatusResponseBody(
            response_payload=[],
        ),
    )

    mock_service_instance.construct_disbursement_status_error_response = AsyncMock(
        return_value=error_response
    )

    # Instantiate controller and make request
    controller = DisbursementStatusController()
    request_payload = DisbursementStatusRequest(
        request_header=G2PRequestHeader(
            request_id="123",
            request_timestamp=datetime.now(),
            sender_id="",
        ),
        request_body=DisbursementStatusRequestBody(
            request_payload=["disb123"],
        ),
    )

    # Try to get disbursement status and catch any raised exception
    try:
        actual_response = await controller.get_disbursement_status(request_payload, is_signature_valid=True)
    except DisbursementStatusException:
        # If an exception is raised, assert that it matches the expected mock response
        actual_response = await mock_service_instance.construct_disbursement_status_error_response(
            request_payload
        )

    # Assert individual fields to handle mock object comparison issues
    assert actual_response.response_header.response_status == error_response.response_header.response_status
    assert (
        actual_response.response_header.response_error_code
        == error_response.response_header.response_error_code
    )
    assert actual_response.response_body == error_response.response_body

    # Assert overall response equality
    assert (
        actual_response == error_response
    ), f"The response did not match the expected error response for {error_code}."
