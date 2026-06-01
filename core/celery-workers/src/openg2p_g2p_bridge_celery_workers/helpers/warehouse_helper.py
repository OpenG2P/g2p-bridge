import logging
import re

from openg2p_fastapi_common.service import BaseService
from openg2p_g2p_bridge_models.schemas import SponsorBankConfiguration
from openg2p_g2p_bridge_warehouse_allocator.models.warehouse import (
    G2PWarehouseProgramBenefitCode,
)
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..engine import get_engine

_config = Settings.get_config()
_logger = logging.getLogger("openg2p_g2p_bridge")
_engine = get_engine()


def extract(tag, data):
    if f"#{tag}#" not in data:
        return None
    match = re.search(rf"#{tag}#([^#]*)", data)
    return match.group(1) if match else None


def _sponsor_config_from_dict(data: dict) -> SponsorBankConfiguration:
    # Build a SponsorBankConfiguration from a config/Helm-values entry.
    return SponsorBankConfiguration(
        program_account_number=data.get("program_account_number") or "",
        program_account_type=data.get("program_account_type"),
        program_account_branch_code=data.get("program_account_branch_code") or "",
        sponsor_bank_code=data.get("sponsor_bank_code") or "",
    )


class WarehouseHelper(BaseService):
    def retrieve_sponsor_bank_configuration(self, benefit_program_id: int, benefit_code_id: int):
        """
        Retrieve the sponsor bank configuration for the given benefit program and code.

        Pure digital cash (in_kind_enabled False): sourced from config / Helm
        values (sponsor_bank_configurations), keyed by "<program_id>:<code_id>"
        with "default" as fallback — no PBMS access.

        In-kind (in_kind_enabled True): read from PBMS
        g2p_warehouse_program_benefit_codes, parsing additional_info.
        """
        if not _config.in_kind_enabled:
            configs = _config.sponsor_bank_configurations or {}
            entry = configs.get(f"{benefit_program_id}:{benefit_code_id}") or configs.get("default")
            if not entry:
                _logger.error(
                    f"No sponsor bank configuration in config for program {benefit_program_id} "
                    f"and code {benefit_code_id} (and no 'default'); set sponsor_bank_configurations."
                )
                return SponsorBankConfiguration(
                    program_account_number="",
                    program_account_type=None,
                    program_account_branch_code="",
                    sponsor_bank_code="",
                )
            return _sponsor_config_from_dict(entry)

        pbms_session_maker = sessionmaker(bind=_engine.get("db_engine_pbms"), expire_on_commit=False)
        _logger.info(
            f"Retrieving sponsor bank configuration for program {benefit_program_id} and code {benefit_code_id}"
        )
        with pbms_session_maker() as session:
            record = (
                session.query(G2PWarehouseProgramBenefitCode)
                .filter(
                    G2PWarehouseProgramBenefitCode.program_id == benefit_program_id,
                    G2PWarehouseProgramBenefitCode.benefit_code_id == benefit_code_id,
                )
                .first()
            )
            if not record or not record.additional_info:
                _logger.error(
                    f"No warehouse program benefit code found for program {benefit_program_id} and code {benefit_code_id}"
                )
                return SponsorBankConfiguration(
                    program_account_number=None,
                    program_account_type=None,
                    program_account_branch_code=None,
                    sponsor_bank_code=None,
                )
            info = record.additional_info
            _logger.info(f"Found warehouse program benefit code: {info}")
            return SponsorBankConfiguration(
                program_account_number=extract("ACCOUNT", info),
                program_account_type=extract("TYPE", info),
                program_account_branch_code=extract("BRANCH", info),
                sponsor_bank_code=record.warehouse_mnemonic,
            )

    def retrieve_sponsor_bank_configuration_for_account_number(
        self, account_number: str
    ) -> SponsorBankConfiguration:
        """
        Retrieve the sponsor bank configuration for the given account number.

        Pure digital cash: match against the configured sponsor_bank_configurations
        by program_account_number — no PBMS access.

        In-kind: search PBMS additional_info LIKE '%#ACCOUNT#{account_number}%'.
        """
        if not _config.in_kind_enabled:
            configs = _config.sponsor_bank_configurations or {}
            for entry in configs.values():
                if isinstance(entry, dict) and entry.get("program_account_number") == account_number:
                    return _sponsor_config_from_dict(entry)
            _logger.error(f"No sponsor bank configuration in config for account number {account_number}")
            return None

        pbms_session_maker = sessionmaker(bind=_engine.get("db_engine_pbms"), expire_on_commit=False)
        with pbms_session_maker() as session:
            like_pattern = f"%#ACCOUNT#{account_number}%"
            record = (
                session.query(G2PWarehouseProgramBenefitCode)
                .filter(G2PWarehouseProgramBenefitCode.additional_info.like(like_pattern))
                .first()
            )
            if not record or not record.additional_info:
                _logger.error(f"No SponsorBankConfiguration found for account number {account_number}")
                return None
            info = record.additional_info
            return SponsorBankConfiguration(
                program_account_number=extract("ACCOUNT", info),
                program_account_type=extract("TYPE", info),
                program_account_branch_code=extract("BRANCH", info),
                sponsor_bank_code=record.warehouse_mnemonic,
            )
