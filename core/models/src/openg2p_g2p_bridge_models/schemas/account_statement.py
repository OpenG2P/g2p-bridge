from typing import Optional
from typing import List
from pydantic import BaseModel
from openg2p_fastapi_common.schemas import G2PRequest, G2PRequestBody, G2PResponse, G2PResponseBody


# Account Statement
class AccountStatementPayload(BaseModel):
    statement_id: Optional[str] = None


class AccountStatementResponseBody(G2PResponseBody):
    response_payload: AccountStatementPayload


class AccountStatementResponse(G2PResponse):
    response_body: AccountStatementResponseBody
