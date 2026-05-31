from openg2p_fastapi_auth.config import Settings as BaseSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="g2p_bridge_bene_portal_api_", env_file=".env", extra="allow"
    )

    openapi_title: str = "OpenG2P Bridge Bene Portal API"
    openapi_description: str = """
        FastAPI Service for OpenG2P Bridge Bene Portal API
        ***********************************
        Further details goes here
        ***********************************
        """
    openapi_version: str = __version__

    # Bridge Database
    db_dbname: str = "bridgedb"
