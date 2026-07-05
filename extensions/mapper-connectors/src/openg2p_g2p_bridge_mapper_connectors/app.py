# ruff: noqa: E402


from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.utils.crypto import build_crypto_helper
from openg2p_fastapi_partner_auth.jwt_validation_helper import JWTValidationHelper

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
        JWTValidationHelper()
        # Outbound SPAR-request signing helper, registered under the name the
        # SPARMapperClient looks up. Signing always uses the LOCAL backend (it signs
        # with the Bridge's own .p12); PM is verify-only, so force backend="local"
        # regardless of the inbound crypto_backend.
        build_crypto_helper(name=_config.spar_mapper_api_sign_crypto_helper_name, backend="local")
