"""Builders for SPAR link/unlink requests used to seed (and clean) ID->FA maps.

A BankAccountFa is linked for each beneficiary, deliberately using the Example
Bank's own simulator bank code so the downstream payment is not randomly failed
(the Example Bank only injects ~30% failures for *foreign* bank codes), keeping
the happy path deterministic.
"""

from __future__ import annotations

import datetime
from typing import Any

from .config import Config


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def bank_fa(cfg: Config, account_number: str) -> dict[str, Any]:
    return {
        "strategy_id": cfg.spar_bank_strategy_id,
        "fa_type": "BANK",
        "bank_name": cfg.beneficiary_bank_name,
        "bank_code": cfg.beneficiary_bank_code,
        "branch_name": cfg.beneficiary_branch_name,
        "branch_code": cfg.beneficiary_branch_code,
        "account_number": account_number,
    }


def link_request(
    cfg: Config,
    *,
    reference_id: str,
    beneficiary_id: str,
    account_number: str,
    name: str,
) -> dict[str, Any]:
    return {
        "reference_id": reference_id,
        "timestamp": _now_iso(),
        "id": beneficiary_id,
        "fa": bank_fa(cfg, account_number),
        "name": name,
        "additional_info": [{"strategy_id": cfg.spar_bank_strategy_id}],
        "locale": "en",
    }


def unlink_request(*, reference_id: str, beneficiary_id: str) -> dict[str, Any]:
    return {
        "reference_id": reference_id,
        "timestamp": _now_iso(),
        "id": beneficiary_id,
    }
