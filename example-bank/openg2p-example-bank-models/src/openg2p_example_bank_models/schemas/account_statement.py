from typing import Optional

from pydantic import BaseModel


class AccountStatementRequest(BaseModel):
    program_account_number: str


class AccountStatementResponse(BaseModel):
    status: str
    account_statement_id: Optional[str] = None
    error_message: Optional[str] = None
