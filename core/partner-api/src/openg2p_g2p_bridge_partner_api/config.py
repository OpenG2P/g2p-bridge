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

    # Inbound partner JWS signature verification (local, Keymanager-free).
    # When enabled, each Partner API request must carry a detached JWS in the
    # "Signature" header, verified against the partner's public key loaded from
    # partner_keys_dir (one JWKS file per partner, named PARTNER_<MNEMONIC>.json).
    signature_validation_enabled: bool = False
    partner_keys_dir: str = "/etc/g2p-bridge/partner-keys"
    # Comma-separated allowed JWS algorithms. RS256 only (asymmetric); "none" and
    # HMAC (HS*) are always rejected regardless of this list.
    signature_allowed_algorithms: str = "RS256"
