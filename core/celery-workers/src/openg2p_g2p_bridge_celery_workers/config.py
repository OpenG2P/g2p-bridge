from pydantic_settings import SettingsConfigDict
from openg2p_fastapi_common.config import Settings as BaseSettings

from . import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="g2p_bridge_celery_workers_", env_file=".env", extra="allow")
    openapi_title: str = "OpenG2P G2P Bridge Celery Workers"
    openapi_description: str = """
        Celery workers for OpenG2P G2P Bridge API
        ***********************************
        Further details goes here
        ***********************************
        """
    openapi_version: str = __version__

    db_dbname: str = "openg2p_g2p_bridge_db"
    db_driver: str = "postgresql"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_backend_url: str = "redis://localhost:6379/0"

    celery_task_queue: str = "g2p_bridge_queue"

    bank_fa_deconstruct_strategy: str = (
        r"^account_number:(?P<account_number>.*)\.branch_code:(?P<branch_code>.*)\.bank_code:(?P<bank_code>.*)\.mobile_number:(?P<mobile_number>.*)\.email_address:(?P<email_address>.*)\.fa_type:(?P<fa_type>.*)$"
    )
    mobile_wallet_deconstruct_strategy: str = (
        r"^mobile_number:(?P<mobile_number>.*)\.wallet_provider_name:(?P<wallet_provider_name>.*)\.wallet_provider_code:(?P<wallet_provider_code>.*)\.fa_type:(?P<fa_type>.*)$"
    )
    email_wallet_deconstruct_strategy: str = (
        r"^email_address:(?P<email_address>.*)\.wallet_provider_name:(?P<wallet_provider_name>.*)\.wallet_provider_code:(?P<wallet_provider_code>.*)\.fa_type:(?P<fa_type>.*)$"
    )

    mapper_request_jwt_enabled: bool = True
    mapper_request_sender_id: str = "openg2p-g2p-bridge"

    agency_allocation_max_attempts: int = 3
    warehouse_allocation_max_attempts: int = 3
    geo_resolution_max_attempts: int = 3
    mapper_resolution_max_attempts: int = 3
    check_funds_with_bank_max_attempts: int = 3
    block_funds_with_bank_max_attempts: int = 3
    disburse_funds_with_bank_max_attempts: int = 3
    mt940_processor_max_attempts: int = 3
    agency_notification_max_attempts: int = 3
    warehouse_notification_max_attempts: int = 3
    beneficiary_notification_max_attempts: int = 3

    # In-kind disbursement support (geo/warehouse/agency). When False (the
    # default), the Bridge runs pure digital cash transfer and does NOT touch
    # the registry or PBMS databases.
    in_kind_enabled: bool = False

    # PBMS database connection settings (only used when in_kind_enabled is True)
    db_driver_pbms: str = "postgresql"
    db_username_pbms: str = "postgres"
    db_password_pbms: str = "postgres"
    db_hostname_pbms: str = "localhost"
    db_port_pbms: int = 5432
    db_dbname_pbms: str = "pbmsdb"

    # Sponsor bank configuration for pure digital cash (in_kind_enabled False),
    # sourced from config / Helm values instead of PBMS. Keyed by
    # "<benefit_program_id>:<benefit_code_id>" with "default" as a fallback.
    # Each value: {sponsor_bank_code, program_account_number,
    #              program_account_type, program_account_branch_code}.
    sponsor_bank_configurations: dict = {}

    suppress_notifications: bool = False
