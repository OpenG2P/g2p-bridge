"""L1 negatives — business-rule validation on the Partner API.

Ported from the legacy ``test/functional-test`` Postman collection
(``Bridge REST APIs`` + ``Downstream Batch Testing``) so the regression suite is
the single source of truth. Unlike ``test_l1_partner_api`` (which only pokes
endpoints with bogus refs), these create real TEST_SANITY-namespaced envelopes
and then violate a business rule, asserting the Bridge rejects it with a graceful
G2P **ERROR** envelope.

Behaviour was confirmed against a live deployment. Three buckets:

* **Enforced** (assert ERROR): missing beneficiary, negative amount,
  disbursements over the envelope's declared sum / count, cancelling an
  already-cancelled envelope.
* **Validation gaps** (xfail, strict=False — the Bridge currently ACCEPTS these
  and *should* reject them): past schedule date, unknown program mnemonic,
  duplicate beneficiary in a batch, disbursements against a cancelled envelope.
  They xpass once the Bridge adds the validation.
* **Ungraceful 500** (xfail, strict=False — the cancel endpoints return HTTP 500
  even on the happy path instead of a 200 envelope): cancel envelope / cancel
  disbursements happy paths and partial-invalid cancel batch.
"""

from __future__ import annotations

import datetime

import pytest

from sanity import g2p

pytestmark = pytest.mark.contract

xfail_missing_validation = pytest.mark.xfail(
    reason="Bridge does not yet validate this input — it accepts it instead of "
    "returning a graceful ERROR envelope (validation gap)",
    strict=False,
)
xfail_cancel_500 = pytest.mark.xfail(
    reason="cancel_disbursement_envelope / cancel_disbursements return HTTP 500 "
    "(even on the happy path) instead of a 200 G2P envelope (robustness gap)",
    strict=False,
)


# --------------------------------------------------------------------------- #
# payload builders
# --------------------------------------------------------------------------- #
def _today() -> str:
    return datetime.date.today().isoformat()


def _env_payload(config, run_ns, *, n, total, sched=None, mnemonic=None):
    return {
        "benefit_program_id": config.benefit_program_id,
        "benefit_program_mnemonic": mnemonic or run_ns.program_mnemonic,
        "benefit_program_description": f"{run_ns.prefix} negatives",
        "target_registry": run_ns.target_registry,
        "benefit_code_id": config.benefit_code_id,
        "benefit_code_mnemonic": run_ns.benefit_code_mnemonic,
        "benefit_code_description": "Negative-path sanity",
        "benefit_type": "CASH_DIGITAL",
        "disbursement_cycle_id": config.disbursement_cycle_id,
        "disbursement_frequency": config.disbursement_frequency,
        "cycle_code_mnemonic": f"{run_ns.prefix}_CYCLE",
        "number_of_beneficiaries": n,
        "number_of_disbursements": n,
        "total_disbursement_quantity": total,
        "measurement_unit": config.treasury_currency,
        "disbursement_schedule_date": sched or _today(),
    }


def _disb(config, env_id, disb_id, beneficiary_id, quantity):
    return {
        "disbursement_id": disb_id,
        "disbursement_envelope_id": env_id,
        "beneficiary_id": beneficiary_id,
        "beneficiary_name": "Negative Bene",
        "disbursement_quantity": quantity,
        "disbursement_cycle_id": config.disbursement_cycle_id,
        "narrative": "negative-path",
    }


def _make_envelope(bridge, config, run_ns, *, n=1, total=1000, **kw) -> str | None:
    _, body = bridge.create_envelopes(
        run_ns.request_id(), [_env_payload(config, run_ns, n=n, total=total, **kw)]
    )
    p = g2p.response_payload(body)
    return p[0].get("id") if isinstance(p, list) and p else None


# --------------------------------------------------------------------------- #
# assertions
# --------------------------------------------------------------------------- #
def _assert_g2p(status, body, endpoint):
    assert status == 200, f"{endpoint} HTTP {status}: {body}"
    assert g2p.is_g2p_response(body), f"{endpoint} not a G2P envelope: {body}"


def _assert_error(status, body, endpoint):
    _assert_g2p(status, body, endpoint)
    assert (
        g2p.response_status(body) == "ERROR"
    ), f"{endpoint} expected ERROR, got {g2p.response_status(body)}: {body}"


def _assert_success(status, body, endpoint):
    _assert_g2p(status, body, endpoint)
    assert (
        g2p.response_status(body) == "SUCCESS"
    ), f"{endpoint} expected SUCCESS, got {g2p.response_status(body)}: {body}"


# --------------------------------------------------------------------------- #
# Enforced business rules — graceful ERROR expected
# --------------------------------------------------------------------------- #
def test_disbursement_missing_beneficiary_id(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    d = _disb(config, eid, run_ns.disbursement_id(1), "BENE", 1000)
    d.pop("beneficiary_id")
    status, body = bridge.create_disbursements(run_ns.request_id(), [d])
    _assert_error(status, body, "create_disbursements (missing beneficiary_id)")


def test_disbursement_negative_amount(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    d = _disb(config, eid, run_ns.disbursement_id(2), "BENE_NEG", -500)
    status, body = bridge.create_disbursements(run_ns.request_id(), [d])
    _assert_error(status, body, "create_disbursements (negative amount)")


def test_disbursements_exceed_envelope_sum(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns, n=2, total=2000)
    payloads = [
        _disb(config, eid, run_ns.disbursement_id(3), "BENE_A", 2500),
        _disb(config, eid, run_ns.disbursement_id(4), "BENE_B", 2500),
    ]
    status, body = bridge.create_disbursements(run_ns.request_id(), payloads)
    _assert_error(status, body, "create_disbursements (total exceeds envelope sum)")


def test_disbursements_exceed_envelope_count(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns, n=2, total=6000)
    payloads = [
        _disb(config, eid, run_ns.disbursement_id(5), "BENE_C", 1000),
        _disb(config, eid, run_ns.disbursement_id(6), "BENE_D", 1000),
        _disb(config, eid, run_ns.disbursement_id(7), "BENE_E", 1000),
    ]
    status, body = bridge.create_disbursements(run_ns.request_id(), payloads)
    _assert_error(status, body, "create_disbursements (count exceeds envelope)")


def test_cancel_already_cancelled_envelope(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    # First cancel actually cancels (it currently also returns 500 — see
    # xfail_cancel_500 — but the state change still happens); ignore its result.
    bridge.cancel_envelope(run_ns.request_id(), eid)
    # Second cancel must be a graceful ALREADY_CANCELED error.
    status, body = bridge.cancel_envelope(run_ns.request_id(), eid)
    _assert_error(status, body, "cancel_disbursement_envelope (already cancelled)")


# --------------------------------------------------------------------------- #
# Validation gaps — Bridge currently ACCEPTS these (should reject)
# --------------------------------------------------------------------------- #
@xfail_missing_validation
def test_envelope_past_schedule_date_rejected(bridge, config, run_ns):
    past = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    _, body = bridge.create_envelopes(
        run_ns.request_id(), [_env_payload(config, run_ns, n=1, total=1000, sched=past)]
    )
    assert g2p.response_status(body) == "ERROR", body


@xfail_missing_validation
def test_envelope_unknown_program_mnemonic_rejected(bridge, config, run_ns):
    _, body = bridge.create_envelopes(
        run_ns.request_id(),
        [_env_payload(config, run_ns, n=1, total=1000, mnemonic="DOES_NOT_EXIST_XYZ")],
    )
    assert g2p.response_status(body) == "ERROR", body


@xfail_missing_validation
def test_duplicate_beneficiary_in_batch_rejected(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns, n=2, total=2000)
    payloads = [
        _disb(config, eid, run_ns.disbursement_id(8), "BENE_DUP", 1000),
        _disb(config, eid, run_ns.disbursement_id(9), "BENE_DUP", 1000),
    ]
    _, body = bridge.create_disbursements(run_ns.request_id(), payloads)
    assert g2p.response_status(body) == "ERROR", body


@xfail_missing_validation
def test_create_disbursements_against_cancelled_envelope_rejected(
    bridge, config, run_ns
):
    eid = _make_envelope(bridge, config, run_ns)
    bridge.cancel_envelope(run_ns.request_id(), eid)  # cancel (ignore 500)
    d = _disb(config, eid, run_ns.disbursement_id(10), "BENE_X", 1000)
    _, body = bridge.create_disbursements(run_ns.request_id(), [d])
    assert g2p.response_status(body) == "ERROR", body


# --------------------------------------------------------------------------- #
# Ungraceful 500 on the cancel endpoints (robustness gap)
# --------------------------------------------------------------------------- #
@xfail_cancel_500
def test_cancel_envelope_happy(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    status, body = bridge.cancel_envelope(run_ns.request_id(), eid)
    _assert_success(status, body, "cancel_disbursement_envelope (happy)")


@xfail_cancel_500
def test_cancel_disbursements_happy(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    did = run_ns.disbursement_id(11)
    bridge.create_disbursements(
        run_ns.request_id(), [_disb(config, eid, did, "BENE_L", 1000)]
    )
    status, body = bridge.cancel_disbursements(run_ns.request_id(), [did])
    _assert_success(status, body, "cancel_disbursements (happy)")


@xfail_cancel_500
def test_cancel_disbursements_partial_invalid_batch(bridge, config, run_ns):
    eid = _make_envelope(bridge, config, run_ns)
    did = run_ns.disbursement_id(12)
    bridge.create_disbursements(
        run_ns.request_id(), [_disb(config, eid, did, "BENE_P", 1000)]
    )
    status, body = bridge.cancel_disbursements(
        run_ns.request_id(), [did, "TEST_SANITY_INVALID_DISB"]
    )
    _assert_g2p(status, body, "cancel_disbursements (partial-invalid)")
