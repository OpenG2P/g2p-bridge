from openg2p_fastapi_common.models import BaseORMModelWithTimes
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column


class Account(BaseORMModelWithTimes):
    __tablename__ = "accounts"
    account_holder_name: Mapped[str] = mapped_column(String)
    account_number: Mapped[str] = mapped_column(String)
    account_currency: Mapped[str] = mapped_column(String)
    account_holder_phone: Mapped[str] = mapped_column(String, unique=True)
    account_holder_email: Mapped[str] = mapped_column(String, unique=True)
    book_balance: Mapped[float] = mapped_column(Float)
    available_balance: Mapped[float] = mapped_column(Float)
    blocked_amount: Mapped[float] = mapped_column(Float, default=0)
