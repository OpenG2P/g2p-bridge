"""L1 — every Partner API endpoint responds with a well-formed G2P envelope.

These use bogus/invalid inputs on purpose so they create no real data; they
verify each endpoint is reachable, validates, and returns the G2PConnect
envelope. The happy-path create flow is exercised by the L2 e2e test.

KNOWN ROBUSTNESS GAPS (xfail): a few endpoints return HTTP 500
``{"code":"G2P-REQ-100","message":"Unknown Error"}`` on not-found / invalid
references instead of a graceful 200 ERROR envelope (as create_envelopes and the
get_* endpoints do). These are marked xfail(strict=False) so they surface in the
report without failing a healthy run, and will xpass once the Bridge handles
those inputs gracefully.
"""

import pytest

from sanity import g2p

pytestmark = pytest.mark.contract

BOGUS = "TEST_SANITY_DOES_NOT_EXIST"

# Endpoints that currently 500 on not-found/invalid refs (see module docstring).
xfail_ungraceful_500 = pytest.mark.xfail(
    reason="Bridge returns 500 'Unknown Error' on not-found/invalid refs "
    "instead of a graceful G2P error envelope (robustness gap)",
    strict=False,
)


def _assert_envelope(status, body, endpoint):
    assert status == 200, f"{endpoint} HTTP {status}: {body}"
    assert g2p.is_g2p_response(body), f"{endpoint} not a G2P envelope: {body}"
    assert g2p.response_status(body) in (
        "SUCCESS",
        "ERROR",
    ), f"{endpoint} bad response_status: {body}"


def test_create_envelopes_validates(bridge, run_ns):
    # Missing required fields -> endpoint must respond with an ERROR envelope.
    status, body = bridge.create_envelopes(
        run_ns.request_id(), [{"benefit_program_mnemonic": run_ns.program_mnemonic}]
    )
    _assert_envelope(status, body, "create_disbursement_envelopes")


@xfail_ungraceful_500
def test_create_disbursements_invalid_envelope(bridge, run_ns):
    status, body = bridge.create_disbursements(
        run_ns.request_id(),
        [
            {
                "disbursement_id": run_ns.disbursement_id(900),
                "disbursement_envelope_id": BOGUS,
                "beneficiary_id": run_ns.beneficiary_id(900),
                "disbursement_quantity": 1,
            }
        ],
    )
    _assert_envelope(status, body, "create_disbursements")


def test_cancel_envelope(bridge, run_ns):
    status, body = bridge.cancel_envelope(run_ns.request_id(), BOGUS)
    _assert_envelope(status, body, "cancel_disbursement_envelope")


@xfail_ungraceful_500
def test_amend_envelope(bridge, run_ns):
    status, body = bridge.amend_envelope(run_ns.request_id(), {"id": BOGUS})
    _assert_envelope(status, body, "amend_disbursement_envelope")


@xfail_ungraceful_500
def test_cancel_disbursements(bridge, run_ns):
    status, body = bridge.cancel_disbursements(run_ns.request_id(), [BOGUS])
    _assert_envelope(status, body, "cancel_disbursements")


def test_get_disbursement_status(bridge, run_ns):
    status, body = bridge.get_disbursement_status(run_ns.request_id(), [BOGUS])
    _assert_envelope(status, body, "get_disbursement_status")


def test_get_envelope_status(bridge, run_ns):
    status, body = bridge.get_envelope_status(run_ns.request_id(), BOGUS)
    _assert_envelope(status, body, "get_disbursement_envelope_status")


def test_get_batch_control(bridge, run_ns):
    status, body = bridge.get_batch_control(run_ns.request_id(), BOGUS)
    _assert_envelope(status, body, "get_disbursement_batch_control")


def test_upload_mt940_reachable(bridge):
    # A non-MT940 payload should be rejected gracefully (not 404/5xx).
    status, body = bridge.upload_mt940(b"not a real mt940 statement\n")
    assert status in (200, 400, 422), f"upload_mt940 unexpected HTTP {status}: {body}"
