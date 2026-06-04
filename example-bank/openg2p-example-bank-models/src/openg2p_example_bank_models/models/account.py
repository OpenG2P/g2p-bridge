from openg2p_fastapi_common.models import BaseORMModelWithTimes
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column


class Account(BaseORMModelWithTimes):
    __tablename__ = "accounts"
    account_holder_name: Mapped[str] = mapped_column(String)
    account_number: Mapped[str] = mapped_column(String)
    account_currency: Mapped[str] = mapped_column(String)
    # NOT unique: beneficiary accounts created from a bank FA carry no phone/email
    # (empty strings), so a UNIQUE constraint collides across multiple beneficiaries
    # and across runs. A bank account does not require a globally-unique phone/email.
    account_holder_phone: Mapped[str] = mapped_column(String, nullable=True)
    account_holder_email: Mapped[str] = mapped_column(String, nullable=True)
    book_balance: Mapped[float] = mapped_column(Float)
    available_balance: Mapped[float] = mapped_column(Float)
    blocked_amount: Mapped[float] = mapped_column(Float, default=0)
