"""L0 — liveness / reachability of every service. Fast, no data created."""

import pytest

pytestmark = pytest.mark.smoke


def test_bridge_ping(bridge):
    r = bridge.ping()
    assert r.status_code == 200, f"Bridge /ping returned {r.status_code}"


def test_bene_portal_ping(bene_portal):
    r = bene_portal.ping()
    assert r.status_code == 200, f"Bene-portal /ping returned {r.status_code}"


def test_example_bank_ping(example_bank):
    r = example_bank.ping()
    assert r.status_code == 200, f"Example Bank /ping returned {r.status_code}"


def test_treasury_account_seeded(example_bank, config):
    """The sponsor/treasury account must exist and be funded (chart seed)."""
    status, body = example_bank.check_funds(
        config.treasury_account_number,
        config.treasury_currency,
        config.e2e_amount_per_beneficiary,
    )
    assert status == 200, f"check_funds HTTP {status}: {body}"
    assert isinstance(body, dict), f"unexpected body: {body}"
    assert (
        body.get("has_sufficient_funds") is True
    ), f"Treasury {config.treasury_account_number} not seeded/funded: {body}"


def test_spar_mapper_reachable(spar, run_ns, config):
    """SPAR mapper partner API should be reachable (needed for e2e seeding)."""
    if not config.run_e2e:
        pytest.skip("run_e2e disabled; SPAR not required")
    # An empty unlink is a cheap reachability probe; we only assert it responds.
    status, body = spar.unlink(run_ns.request_id(), run_ns.run_id, [])
    assert (
        status < 500
    ), f"SPAR mapper unreachable / server error (HTTP {status}): {body}"
