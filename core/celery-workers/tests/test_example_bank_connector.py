"""Unit tests for the Example Bank bank connector.

The Example Bank carries the full ``disbursement_id`` in the MT940 ``:86:`` field
(narrative #5 -> ``narratives[4]``) because the ``:61:`` customer-reference is
capped at 16 chars and disbursement ids can be longer. The connector recovers it
from there, falling back to the ``:61:`` reference for statements produced before
that change.
"""

from openg2p_g2p_bridge_bank_connectors.bank_connectors.example_bank_connector import (
    ExampleBankConnector,
)


def _connector():
    # Skip BaseService.__init__ — retrieve_reconciliation_id is a pure method.
    return ExampleBankConnector.__new__(ExampleBankConnector)


def test_reconciliation_id_read_from_86_field():
    long_id = "TEST_SANITY_20260604T101500_a1b2c3_DISB_001"  # 43 chars
    # narrative_1..6; the disbursement id is in narrative_5 (index 4)
    narratives = ["narrative", "PROGRAM", "CYCLE", "BENE_001", long_id, ""]
    reconciliation_id = _connector().retrieve_reconciliation_id("bank_reference", long_id[:16], narratives)
    assert reconciliation_id == long_id


def test_reconciliation_id_falls_back_to_customer_reference():
    # Legacy statements left narrative_5 empty; the (short) id was only in :61:.
    short_id = "DISB_001"
    narratives = ["narrative", "PROGRAM", "CYCLE", "BENE_001", "", ""]
    reconciliation_id = _connector().retrieve_reconciliation_id("bank_reference", short_id, narratives)
    assert reconciliation_id == short_id
