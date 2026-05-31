from openg2p_fastapi_common.config import Settings as BaseSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="example_bank_", env_file=".env", extra="allow"
    )

    openapi_title: str = "Example Bank APIs for Cash Transfer"
    openapi_description: str = """
        ***********************************
        Further details goes here
        ***********************************
        """
    openapi_version: str = __version__

    db_dbname: str = "example_bank_db"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_backend_url: str = "redis://localhost:6379/0"
