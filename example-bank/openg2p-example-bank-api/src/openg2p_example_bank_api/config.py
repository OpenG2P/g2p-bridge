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

    # Treasury/sponsor account seeding (demo). When enabled, `migrate` creates an
    # account with treasury_account_number if it does not already exist. The G2P
    # Bridge is configured with the SAME account number as its digital-cash
    # sponsor account, so it can check/block/disburse against it. Idempotent.
    seed_treasury_account: bool = False
    treasury_account_number: str = ""
    treasury_account_currency: str = "USD"
    treasury_available_balance: float = 0
    treasury_account_holder_name: str = "Program Treasury"
    treasury_account_holder_phone: str = ""
    treasury_account_holder_email: str = ""
