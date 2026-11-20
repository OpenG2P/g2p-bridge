from openg2p_fastapi_common.config import Settings as BaseSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="g2p_bridge_", env_file=".env", extra="allow")

    openapi_title: str = "OpenG2P G2P Bridge Partner API"
    openapi_description: str = """
        This module enables cash transfers from PBMS
        ***********************************
        Further details goes here
        ***********************************
        """
    openapi_version: str = __version__

    db_dbname: str = "openg2p_g2p_bridge_db"
    max_upload_file_size: int = 10485760  # 10 MB
    supported_file_types: list[str] = [
        "application/x-iso8583",
        "application/x-iso20022",
        "application/vnd.swift.mt940",
        "text/plain",
    ]

    signature_validation_enabled: bool = False

    account_validation_program_id: int = 1
    account_validation_program_mnemonic: str = "ACCOUNT-VALIDATION"
    account_validation_benefit_code_id: int = 1
    account_validation_benefit_code_mnemonic: str = "PENNY-DROP"
    account_validation_max_amount: float = 1.0
    account_validation_allowed_clients: list[str] = ["spa-registry"]
    account_validation_sponsor_account_number: str = ""
    account_validation_sponsor_account_type: str = "BANK_ACCOUNT"
    account_validation_sponsor_branch_code: str = ""
    account_validation_sponsor_bank_code: str = ""

    # Inbound partner-signature verification fetches partner public keys from the
    # Partner Manager (PM) service. `partner_mgmt_api_url` + the partner_key_* cache
    # settings are inherited from the openg2p-fastapi-common base Settings.
    crypto_backend: str = "partner-mgmt"
