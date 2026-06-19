"""L2 — MT940 reconciliation ERROR path.

Ported from the legacy ``test/functional-test/Negative Conditions for MT940``
script, but kept **black-box**: instead of injecting rows into the bank's
database, it uploads a crafted MT940 statement (in the exact wire format the
bundled Example Bank emits) whose debit references a reconciliation id the Bridge
has never seen, then polls ``get_disbursement_status`` until the asynchronous
MT940 processor records the reconciliation ERROR.

Covered: ``INVALID_RECONCILIATION_ID`` — a debit whose reconciliation id matches
no disbursement (nor any batch-control-geo). This is self-contained (no
pre-existing disbursement needed) and exercises the full upload -> async parse ->
reconciliation-error -> status-readout pipeline. (The MT940 processor raises
``INVALID_RECONCILIATION_ID`` for an unmatched debit; ``INVALID_DISBURSEMENT_ID``
is a related code used elsewhere.)

Two wire-format constraints were confirmed against a live deployment and drive
the test design:

* The reconciliation id (the disbursement id) travels in the MT940 ``:86:``
  field (narrative #5); the Example Bank connector reads it from there because
  the tag-61 ``customer_reference`` is capped at **16 characters**. This test
  puts the id in *both* fields, so it matches on the older (tag-61) connector as
  well as the current (:86:) one.
* The statement must be drawn on the treasury account (tag ``:25:``) — the Bridge
  resolves the bank connector from that account number via the sponsor-bank
  config.

The legacy script's other two conditions are intentionally NOT reproduced here,
for concrete reasons confirmed against a live deployment:

* ``INVALID_REVERSAL`` — would require a reversal (``RD``) transaction line, but
  the MT940 parser the Bridge uses rejects ``RD`` lines outright ("Unable to
  parse Statement"), so a reversal cannot be ingested via ``upload_mt940`` at
  all. The Example Bank only ever emits ``RD`` on a negative amount, which does
  not occur in normal flow, so this path is effectively dormant.
* ``DUPLICATE_DISBURSEMENT`` — requires a *previously successful* reconciliation
  to duplicate, i.e. a real disbursement that already has a DisbursementRecon.
  That depends on a completed happy-path e2e run; it is left as a follow-on.
"""

from __future__ import annotations

import datetime

import pytest

from sanity import g2p
from sanity.clients import poll_until

pytestmark = pytest.mark.e2e


# --------------------------------------------------------------------------- #
# MT940 builder — mirrors example-bank Mt940Writer exactly (D/C lines only;
# the parser cannot handle RD/RC, so reversals are out of scope — see module
# docstring).
# --------------------------------------------------------------------------- #
def _amount15(amount) -> str:
    return "{:015.2f}".format(float(amount)).replace(".", ",")


def _balance(amount, date, currency) -> str:
    cat = "C" if amount >= 0 else "D"
    return f"{cat}{date.strftime('%y%m%d')}{currency}" + (
        f"{abs(amount):0.2f}".replace(".", ",")
    )


def _narratives(beneficiary: str, recon_id: str) -> str:
    # narrative_1..6; the Example Bank connector reads the beneficiary from #4
    # and the reconciliation id (disbursement id) from #5 (:86:), because the
    # :61: customer_reference is capped at 16 chars.
    return "\n".join(["N1", "N2", "N3", beneficiary, recon_id, "N6"])


def _debit(date, amount, customer_ref, bank_ref, beneficiary, recon_id) -> str:
    # :61: value_date(yymmdd) entry_date(mmdd) D funds_code('') amount NTRF
    #      customer_reference //bank_reference     (then :86: narratives)
    line61 = (
        date.strftime("%y%m%d")
        + date.strftime("%m%d")
        + "D"
        + _amount15(amount)
        + "NTRF"
        + customer_ref
        + f"//{bank_ref}"
    )
    return f":61:{line61}\n:86:{_narratives(beneficiary, recon_id)}"


def _statement(account, statement_id, currency, date, txns) -> str:
    lines = [
        f":20:{statement_id}",
        f":25:{account}",
        ":28C:1/1",
        f":60F:{_balance(100000000, date, currency)}",
    ]
    lines.extend(txns)
    lines.append(f":62F:{_balance(100000000, date, currency)}")
    return "\n".join(lines)


def _error_reasons(body) -> list[str]:
    out: list[str] = []
    payload = g2p.response_payload(body)
    if isinstance(payload, list):
        for item in payload:
            recs = (item or {}).get("disbursement_recon_records") or {}
            for err in recs.get("disbursement_error_recon_payloads") or []:
                if err and err.get("error_reason"):
                    out.append(err["error_reason"])
    return out


# --------------------------------------------------------------------------- #
# One upload, polled for the recon error (module-scoped)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mt940_recon(config, bridge, run_ns):
    currency = config.treasury_currency
    account = config.treasury_account_number
    today = datetime.date.today()

    # The id is matched from :86: now, but we mirror it in the tag-61
    # customer_reference too (max 16 chars) so the test also passes against an
    # older connector. Keep it short and run-unique to avoid colliding with
    # error recons left by earlier runs.
    short = run_ns.run_token.split("_")[-1]
    unknown_id = f"TST{short}NORECON"[:16]
    statement = _statement(
        account,
        "STMT1",
        currency,
        today,
        [_debit(today, 1000, unknown_id, "BR1", "BENE_1", unknown_id)],
    )

    up_status, up_body = bridge.upload_mt940(statement.encode())

    ok, last = poll_until(
        lambda: bridge.get_disbursement_status(run_ns.request_id(), [unknown_id])[1],
        predicate=lambda b: "INVALID_RECONCILIATION_ID" in _error_reasons(b),
        timeout=config.e2e_recon_timeout_seconds,
        interval=config.e2e_poll_interval_seconds,
        description="INVALID_RECONCILIATION_ID recon error",
    )
    return {
        "upload_status": up_status,
        "upload_body": up_body,
        "ok": ok,
        "last": last,
    }


def test_mt940_upload_accepted(mt940_recon):
    assert (
        mt940_recon["upload_status"] == 200
    ), f"upload_mt940 HTTP {mt940_recon['upload_status']}: {mt940_recon['upload_body']}"


def test_recon_error_invalid_disbursement_id(mt940_recon):
    assert mt940_recon["ok"], (
        "Bridge did not record an INVALID_DISBURSEMENT_ID reconciliation error for a "
        f"debit referencing an unknown disbursement. Last status: {mt940_recon['last']}"
    )
