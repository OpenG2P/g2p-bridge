# ruff: noqa: E402


from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_g2p_bridge_models.crypto import PyJWTCryptoHelper

from .client import SPARMapperClient
from .config import Settings
from .factory import MapperFactory
from .implementations import SPARMapper

_config = Settings.get_config()


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        MapperFactory()
        SPARMapperClient()
        SPARMapper()
        # Local signing helper used by SPARMapperClient when outbound request
        # signing is enabled (spar_mapper_api_sign_enabled). Registered under the
        # name the client looks up.
        PyJWTCryptoHelper(
            name=_config.spar_mapper_api_sign_crypto_helper_name,
            signing_key_path=_config.signing_key_path,
            signing_key_kid=_config.signing_key_kid or None,
            signing_algorithm=_config.signing_algorithm,
            allowed_algorithms=[
                alg.strip() for alg in _config.signing_allowed_algorithms.split(",") if alg.strip()
            ],
        )
