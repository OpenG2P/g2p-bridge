"""L1 — Beneficiary Portal API endpoints respond with a well-formed envelope."""

import pytest

from sanity import g2p

pytestmark = pytest.mark.contract


def test_get_all_disbursements(bene_portal, run_ns):
    status, body = bene_portal.get_all_disbursements(run_ns.request_id(), {})
    assert status == 200, f"get_all_disbursements HTTP {status}: {body}"
    assert g2p.is_g2p_response(body), f"not a G2P envelope: {body}"


def test_get_disbursement_summary_till_date(bene_portal, run_ns):
    status, body = bene_portal.get_disbursement_summary_till_date(
        run_ns.request_id(), {}
    )
    assert status == 200, f"get_disbursement_summary_till_date HTTP {status}: {body}"
    assert g2p.is_g2p_response(body), f"not a G2P envelope: {body}"
