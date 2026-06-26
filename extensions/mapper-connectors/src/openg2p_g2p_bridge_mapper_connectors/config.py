from openg2p_fastapi_common.config import Settings as BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="g2p_bridge_mapper_connectors_", env_file=".env", extra="allow"
    )

    # SPAR Mapper configuration
    spar_mapper_url: str = "http://localhost:8080/mapper/resolve"
    spar_mapper_api_sign_enabled: bool = False
    spar_mapper_api_sign_crypto_helper_name: str = "spar_mapper_crypto"

    # Outbound request signing (local, Keymanager-free). When SPAR enforces
    # signature verification, the Bridge signs each resolve request with its own
    # private key (a JWK file, normally mounted from a Kubernetes Secret) and
    # sends a detached JWS in the "Signature" header. SPAR must hold the matching
    # public key (registered as PARTNER_<BRIDGE_MNEMONIC>).
    signing_key_path: str = "/etc/g2p-bridge/signing-key/signing-key.json"
    signing_key_kid: str = ""
    signing_algorithm: str = "RS256"
    signing_allowed_algorithms: str = "RS256"
