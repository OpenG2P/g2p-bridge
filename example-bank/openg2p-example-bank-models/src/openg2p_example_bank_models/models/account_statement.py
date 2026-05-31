from datetime import datetime
from enum import Enum

from openg2p_fastapi_common.models import BaseORMModelWithTimes
from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column


class DebitCreditTypes(Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class AccountStatementStatus(Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AccountStatement(BaseORMModelWithTimes):
    __tablename__ = "account_statements"
    account_number: Mapped[str] = mapped_column(String, index=True)
    account_statement_lob: Mapped[str] = mapped_column(Text, nullable=True)
    account_statement_generation_status: Mapped[AccountStatementStatus] = mapped_column(
        SqlEnum(AccountStatementStatus), default=AccountStatementStatus.PENDING
    )
    account_statement_date: Mapped[datetime.date] = mapped_column(
        DateTime, default=datetime.date(datetime.utcnow())
    )


class AccountingLog(BaseORMModelWithTimes):
    __tablename__ = "accounting_logs"
    reference_no: Mapped[str] = mapped_column(String, index=True, unique=True)
    corresponding_block_reference_no: Mapped[str] = mapped_column(String, nullable=True)
    customer_reference_no: Mapped[str] = mapped_column(String, index=True)
    debit_credit: Mapped[DebitCreditTypes] = mapped_column(SqlEnum(DebitCreditTypes))
    account_number: Mapped[str] = mapped_column(String, index=True)
    transaction_amount: Mapped[float] = mapped_column(Float)
    transaction_date: Mapped[datetime] = mapped_column(DateTime)
    transaction_currency: Mapped[str] = mapped_column(String)
    transaction_code: Mapped[str] = mapped_column(String, nullable=True)

    narrative_1: Mapped[str] = mapped_column(String, nullable=True)  # disbursement id
    narrative_2: Mapped[str] = mapped_column(String, nullable=True)  # beneficiary id
    narrative_3: Mapped[str] = mapped_column(String, nullable=True)  # program pneumonic
    narrative_4: Mapped[str] = mapped_column(
        String, nullable=True
    )  # cycle code pneumonic
    narrative_5: Mapped[str] = mapped_column(String, nullable=True)  # beneficiary email
    narrative_6: Mapped[str] = mapped_column(
        String, nullable=True
    )  # beneficiary phone number
    reported_in_mt940: Mapped[bool] = mapped_column(Boolean, default=False)
