"""Unit tests for the Example Bank MT940 writer.

The MT940 :61: customer-reference subfield is limited to 16 characters; a longer
value (e.g. a long disbursement_id) makes the statement unparseable. The writer
must cap it so every generated statement is valid.
"""

from datetime import date
from decimal import Decimal

from openg2p_example_bank_celery_workers.utils import Mt940Writer, TransactionType


def _writer():
    # Skip BaseService.__init__ (needs app context) — these tests only exercise
    # the pure string-formatting methods.
    return Mt940Writer.__new__(Mt940Writer)


def _customer_reference_in_61(line):
    # :61: ...NTRF<customer_reference>//<bank_reference>
    after_ntrf = line.split("NTRF", 1)[1]
    return after_ntrf.split("//", 1)[0]


def _transaction(writer, customer_reference):
    return writer.create_transaction(
        date(2026, 6, 19),
        date(2026, 6, 19),
        "D",
        Decimal("1000.00"),
        TransactionType.transfer,
        customer_reference,
        "BANKREF0001",
        "",
        "",
        "narrative",
    )


def test_long_customer_reference_capped_to_16_chars():
    writer = _writer()
    long_id = "TEST_SANITY_20260604T101500_a1b2c3_DISB_001"  # 43 chars
    line = writer.format_transaction(_transaction(writer, long_id))
    customer_reference = _customer_reference_in_61(line)
    assert len(customer_reference) <= 16
    assert customer_reference == long_id[:16]


def test_short_customer_reference_unchanged():
    writer = _writer()
    short_id = "DISB_001"
    line = writer.format_transaction(_transaction(writer, short_id))
    assert _customer_reference_in_61(line) == short_id
