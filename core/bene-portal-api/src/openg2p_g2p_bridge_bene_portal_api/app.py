# ruff: noqa: E402
import logging
from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_auth.auth import AuthFactory

from .controllers import DisbursementController
from .services import DisbursementService

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()

        AuthFactory()
        DisbursementService()
        DisbursementController().post_init()
