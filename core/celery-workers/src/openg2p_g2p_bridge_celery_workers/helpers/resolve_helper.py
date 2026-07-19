import enum
import logging
import re
from typing import List

from openg2p_fastapi_common.service import BaseService
from openg2p_g2p_bridge_models.models import MapperResolvedFaType
from openg2p_g2p_bridge_mapper_connectors.schemas import (
    ResolveRequest,
)
from pydantic import BaseModel

from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class FAKeys(enum.Enum):
    account_number = "account_number"
    bank_code = "bank_code"
    branch_code = "branch_code"
    account_type = "account_type"
    mobile_number = "mobile_number"
    mobile_wallet_provider = "mobile_wallet_provider"
    email_address = "email_address"
    email_wallet_provider = "email_wallet_provider"
    fa_type = "fa_type"


class KeyValuePair(BaseModel):
    key: FAKeys
    value: str


class ResolveHelper(BaseService):
    def construct_resolve_request(self, beneficiary_ids: List[str]) -> ResolveRequest:
        _logger.info(f"Constructing resolve request for {len(beneficiary_ids)} beneficiary IDs")
        resolve_request = ResolveRequest(
            beneficiary_ids=beneficiary_ids,
        )
        _logger.info(f"Constructed resolve request for {len(beneficiary_ids)} single resolve requests")
        return resolve_request

    def _deconstruct(self, value: str, strategy: str) -> List[KeyValuePair]:
        _logger.info(f"Deconstructing ID/FA: {value}")
        regex_res = re.match(strategy, value)
        deconstructed_list = []
        if regex_res:
            regex_res = regex_res.groupdict()
            try:
                # Coalesce None (from optional groups) to empty strings
                deconstructed_list = [
                    KeyValuePair(key=FAKeys(k), value=(v if v is not None else ""))
                    for k, v in regex_res.items()
                ]
            except Exception as e:
                _logger.error(f"Error while deconstructing ID/FA: {e}")
                raise ValueError("Error while deconstructing ID/FA") from e
        _logger.info(f"Deconstructed ID/FA: {value}")
        return deconstructed_list

    def deconstruct_fa(self, fa: str) -> dict:
        _logger.info("Deconstructing FA")
        deconstruct_strategy = self._get_deconstruct_strategy(fa)
        _logger.info(f"Deconstruction strategy: {deconstruct_strategy}")
        if deconstruct_strategy:
            deconstructed_pairs = self._deconstruct(fa, deconstruct_strategy)
            deconstructed_fa = {pair.key.value: pair.value for pair in deconstructed_pairs}
            _logger.info(f"Deconstructed FA Returning: {deconstructed_fa}")
            return deconstructed_fa
        return {}

    def _get_deconstruct_strategy(self, fa: str) -> str:
        _logger.info("Getting deconstruction strategy")
        if fa.endswith(MapperResolvedFaType.BANK_ACCOUNT.value):
            return _config.bank_fa_deconstruct_strategy
        elif fa.endswith(MapperResolvedFaType.MOBILE_WALLET.value):
            return _config.mobile_wallet_fa_deconstruct_strategy
        elif fa.endswith(MapperResolvedFaType.EMAIL_WALLET.value):
            return _config.email_wallet_fa_deconstruct_strategy
        _logger.info("Deconstruction strategy not found!")
        return ""
