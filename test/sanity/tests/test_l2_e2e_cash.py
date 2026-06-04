"""L2 — full digital-cash disbursement lifecycle, verified stage by stage.

A batch of disbursements is pushed through the complete chain and **each stage is
asserted independently**, so a failure tells you exactly where the pipeline
stalled:

  1. create envelope + disbursements   Bridge accepts the batch (response SUCCESS)
  2. FA resolution                     batch_control.fa_resolution_status == PROCESSED
  3. funds checked with bank           envelope.funds_available_with_bank == FUNDS_AVAILABLE
  4. funds blocked with bank           envelope.funds_blocked_with_bank == FUNDS_BLOCK_SUCCESS
  5. disbursed to bank                 batch_control.sponsor_bank_dispatch_status == PROCESSED
  6. bank distributes to beneficiaries Example Bank credits each beneficiary account
  7. reconciliation                    disbursement.disbursement_recon_records populated (MT940)

All data is namespaced under TEST_SANITY; SPAR links are unlinked at teardown.
"""

from __future__ import annotations

import datetime
import logging
import time

import pytest

from sanity import g2p
from sanity.clients import poll_until

pytestmark = pytest.mark.e2e
_logger = logging.getLogger("sanity")


def _payload(body):
    return g2p.response_payload(body)


def _field(body, name):
    p = _payload(body)
    return p.get(name) if isinstance(p, dict) else None


@pytest.fixture(scope="session")
def cash_flow(config, bridge, example_bank, seeded_links, run_ns):
    if not config.run_e2e:
        pytest.skip("run_e2e disabled in config")
    if config.keymanager_auth_enabled:
        pytest.skip("keymanager auth enabled — write flow needs signed requests")

    n = config.e2e_num_beneficiaries
    amount = config.e2e_amount_per_beneficiary
    total = n * amount
    poll = config.e2e_poll_interval_seconds

    r: dict = {"n": n, "amount": amount}

    # 0) Treasury funded for our total.
    _, funds = example_bank.check_funds(
        config.treasury_account_number, config.treasury_currency, total
    )
    r["treasury_ok"] = (
        isinstance(funds, dict) and funds.get("has_sufficient_funds") is True
    )

    # 1) Seed SPAR ID->FA links (same beneficiary IDs we disburse to).
    beneficiaries = [seeded_links.link_beneficiary(i)[0] for i in range(1, n + 1)]
    r["seeding_ok"] = all(e["link_status"] == 200 for e in seeded_links.entries)

    # 2) Create the CASH_DIGITAL envelope.
    today = datetime.date.today().isoformat()
    env_payload = {
        "benefit_program_id": config.benefit_program_id,
        "benefit_program_mnemonic": run_ns.program_mnemonic,
        "benefit_program_description": f"{run_ns.prefix} sanity program",
        "target_registry": run_ns.target_registry,
        "benefit_code_id": config.benefit_code_id,
        "benefit_code_mnemonic": run_ns.benefit_code_mnemonic,
        "benefit_code_description": "Digital cash sanity",
        "benefit_type": "CASH_DIGITAL",
        "disbursement_cycle_id": 1,
        "disbursement_frequency": config.disbursement_frequency,
        "cycle_code_mnemonic": f"{run_ns.prefix}_CYCLE",
        "number_of_beneficiaries": n,
        "number_of_disbursements": n,
        "total_disbursement_quantity": total,
        "measurement_unit": config.treasury_currency,
        "disbursement_schedule_date": today,
    }
    env_status, env_body = bridge.create_envelopes(run_ns.request_id(), [env_payload])
    r["env_status"], r["env_body"] = env_status, env_body
    payload = _payload(env_body)
    envelope_id = (
        payload[0].get("id") if isinstance(payload, list) and payload else None
    )
    r["envelope_id"] = envelope_id

    # 3) Create disbursements; capture the batch-control id from the response.
    disb_ids = [run_ns.disbursement_id(i) for i in range(1, n + 1)]
    r["disb_ids"] = disb_ids
    batch_control_id = None
    if envelope_id:
        disb_payloads = [
            {
                "disbursement_id": disb_ids[i - 1],
                "disbursement_envelope_id": envelope_id,
                "beneficiary_id": beneficiaries[i - 1],
                "beneficiary_name": f"{run_ns.prefix} Beneficiary {i}",
                "disbursement_quantity": amount,
                "narrative": f"{run_ns.prefix} sanity disbursement {i}",
            }
            for i in range(1, n + 1)
        ]
        ds_status, ds_body = bridge.create_disbursements(
            run_ns.request_id(), disb_payloads
        )
        r["disb_status"], r["disb_body"] = ds_status, ds_body
        try:
            batch_control_id = ds_body["response_body"].get(
                "disbursement_batch_control_id"
            )
        except (KeyError, TypeError):
            batch_control_id = None
    r["batch_control_id"] = batch_control_id

    # --- staged polling with a single shared budget for stages 2-6 ---
    deadline = time.monotonic() + config.e2e_pipeline_timeout_seconds

    def remaining():
        return max(1, int(deadline - time.monotonic()))

    def batch_body():
        _, b = bridge.get_batch_control(run_ns.request_id(), batch_control_id)
        return b

    def env_body_now():
        _, b = bridge.get_envelope_status(run_ns.request_id(), envelope_id)
        return b

    def disb_body_now():
        _, b = bridge.get_disbursement_status(run_ns.request_id(), disb_ids)
        return b

    # Stage 2 — FA resolution (Bridge ↔ SPAR)
    if envelope_id and batch_control_id:
        r["fa_ok"], r["fa_last"] = poll_until(
            batch_body,
            predicate=lambda b: _field(b, "fa_resolution_status") == "PROCESSED",
            timeout=remaining(),
            interval=poll,
            description="FA resolution",
        )
    else:
        r["fa_ok"], r["fa_last"] = False, None

    # Stage 3 — funds checked with bank
    if r["fa_ok"]:
        r["check_ok"], r["check_last"] = poll_until(
            env_body_now,
            predicate=lambda b: _field(b, "funds_available_with_bank")
            == "FUNDS_AVAILABLE",
            timeout=remaining(),
            interval=poll,
            description="funds available",
        )
    else:
        r["check_ok"], r["check_last"] = False, None

    # Stage 4 — funds blocked with bank
    if r["check_ok"]:
        r["block_ok"], r["block_last"] = poll_until(
            env_body_now,
            predicate=lambda b: _field(b, "funds_blocked_with_bank")
            == "FUNDS_BLOCK_SUCCESS",
            timeout=remaining(),
            interval=poll,
            description="funds blocked",
        )
    else:
        r["block_ok"], r["block_last"] = False, None

    # Stage 5 — disbursed to bank (sponsor bank dispatch)
    if r["block_ok"]:
        r["disburse_ok"], r["disburse_last"] = poll_until(
            batch_body,
            predicate=lambda b: _field(b, "sponsor_bank_dispatch_status")
            == "PROCESSED",
            timeout=remaining(),
            interval=poll,
            description="sponsor bank dispatch",
        )
    else:
        r["disburse_ok"], r["disburse_last"] = False, None

    # Stage 6 — bank distributes: each beneficiary account credited in Example Bank
    def all_credited():
        for e in seeded_links.entries:
            _, b = example_bank.check_funds(
                e["account_number"], config.treasury_currency, amount
            )
            if not (isinstance(b, dict) and b.get("has_sufficient_funds")):
                return False
        return True

    if r["disburse_ok"]:
        r["distrib_ok"], _ = poll_until(
            all_credited,
            predicate=lambda ok: ok is True,
            timeout=remaining(),
            interval=poll,
            description="bank distributed to beneficiaries",
        )
    else:
        r["distrib_ok"] = False

    # Stage 7 — reconciliation (MT940 back to Bridge); its own longer budget
    def reconciled(b):
        p = _payload(b)
        return (
            isinstance(p, list)
            and len(p) >= len(disb_ids)
            and all(item.get("disbursement_recon_records") for item in p)
        )

    if r["disburse_ok"]:
        r["recon_ok"], r["recon_last"] = poll_until(
            disb_body_now,
            predicate=reconciled,
            timeout=config.e2e_recon_timeout_seconds,
            interval=poll,
            description="reconciliation",
        )
    else:
        r["recon_ok"], r["recon_last"] = False, None

    return r


# --------------------------------------------------------------------------- #
# One assertion per stage — the report shows exactly how far the flow got.
# --------------------------------------------------------------------------- #
def test_stage0_treasury_funded(cash_flow):
    assert cash_flow["treasury_ok"], "Treasury account not funded for the e2e total"


def test_stage1a_spar_seeded(cash_flow, config):
    assert cash_flow["seeding_ok"], (
        f"SPAR ID->FA seeding failed — check spar_bank_strategy_id "
        f"(={config.spar_bank_strategy_id}) and {config.spar_mapper_base_url}"
    )


def test_stage1b_envelope_created(cash_flow):
    assert g2p.response_status(cash_flow["env_body"]) == "SUCCESS", cash_flow[
        "env_body"
    ]
    assert cash_flow["envelope_id"], "no envelope id returned"


def test_stage1c_disbursements_created(cash_flow):
    assert cash_flow.get("disb_status") == 200
    assert g2p.response_status(cash_flow["disb_body"]) == "SUCCESS", cash_flow[
        "disb_body"
    ]
    assert cash_flow[
        "batch_control_id"
    ], "no batch_control_id returned by create_disbursements"


def test_stage2_fa_resolved(cash_flow):
    assert cash_flow[
        "fa_ok"
    ], f"FA resolution did not complete. last: {cash_flow['fa_last']}"


def test_stage3_funds_checked(cash_flow):
    assert cash_flow[
        "check_ok"
    ], f"funds not confirmed available. last: {cash_flow['check_last']}"


def test_stage4_funds_blocked(cash_flow):
    assert cash_flow["block_ok"], f"funds not blocked. last: {cash_flow['block_last']}"


def test_stage5_disbursed_to_bank(cash_flow):
    assert cash_flow[
        "disburse_ok"
    ], f"sponsor bank dispatch did not complete. last: {cash_flow['disburse_last']}"


def test_stage6_bank_distributed(cash_flow):
    assert cash_flow[
        "distrib_ok"
    ], "Example Bank did not credit all beneficiary accounts (bank distribution stage)"


def test_stage7_reconciled(cash_flow):
    assert cash_flow[
        "recon_ok"
    ], f"disbursements not reconciled via MT940. last: {cash_flow['recon_last']}"
