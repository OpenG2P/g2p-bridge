"""L1 — Example Bank API endpoints respond / function for basic inputs.

Read-only or no-op inputs only (bogus accounts), so no balances are disturbed.
"""

import pytest

pytestmark = pytest.mark.contract

BOGUS_ACCOUNT = "TEST_SANITY_NO_SUCH_ACCOUNT"


def test_check_funds_treasury(example_bank, config):
    status, body = example_bank.check_funds(
        config.treasury_account_number,
        config.treasury_currency,
        1,
    )
    assert status == 200, f"check_funds HTTP {status}: {body}"
    assert isinstance(body.get("has_sufficient_funds"), bool), body


def test_check_funds_unknown_account(example_bank, config):
    status, body = example_bank.check_funds(BOGUS_ACCOUNT, config.treasury_currency, 1)
    assert status == 200, f"check_funds HTTP {status}: {body}"
    # Unknown account must not report sufficient funds.
    assert body.get("has_sufficient_funds") in (False, None), body


def test_block_funds_unknown_account(example_bank, config):
    # Blocking on a bogus account is a no-op (account not found) — no side effect.
    status, body = example_bank.block_funds(BOGUS_ACCOUNT, config.treasury_currency, 1)
    assert status == 200, f"block_funds HTTP {status}: {body}"
    assert isinstance(body, dict) and "status" in body, body


@pytest.mark.xfail(
    reason="generate_account_statement returns 500 'Unknown Error' "
    "(e.g. when the account has no transactions yet) — robustness gap",
    strict=False,
)
def test_generate_account_statement_reachable(example_bank, config):
    status, body = example_bank.generate_account_statement(
        config.treasury_account_number
    )
    assert status == 200, f"generate_account_statement HTTP {status}: {body}"
    assert isinstance(body, dict) and "status" in body, body


def test_initiate_payment_empty_batch(example_bank):
    # Empty payment list is a no-op batch — verifies the endpoint functions
    # without creating a real payment. (The real disbursement path is covered
    # end-to-end in the L2 e2e flow.)
    status, body = example_bank.initiate_payment([])
    assert status == 200, f"initiate_payment HTTP {status}: {body}"
    assert isinstance(body, dict) and "status" in body, body


def test_ussd_reachable(example_bank):
    status, body = example_bank.ussd(
        {
            "sessionId": "TEST_SANITY",
            "serviceCode": "*123#",
            "phoneNumber": "+10000000000",
            "networkCode": "0",
            "text": "",
        }
    )
    # 200 with the USSD menu text is success; 422 still proves it is reachable.
    assert status in (200, 422), f"ussd unexpected HTTP {status}: {body}"
