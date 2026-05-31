from typing import Optional

from pydantic import BaseModel


class CheckFundRequest(BaseModel):
    account_number: str
    account_currency: str
    total_funds_needed: float


class CheckFundResponse(BaseModel):
    status: str
    account_number: str
    has_sufficient_funds: bool
    error_message: Optional[str] = None


class BlockFundsRequest(BaseModel):
    account_number: str
    currency: str
    amount: float


class BlockFundsResponse(BaseModel):
    status: str
    block_reference_no: str
    error_message: Optional[str] = None
