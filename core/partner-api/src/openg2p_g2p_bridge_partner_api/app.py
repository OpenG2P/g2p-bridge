# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.models import PartnerKey
from openg2p_fastapi_common.utils.crypto import build_crypto_helper, seed_partner_certs
from openg2p_g2p_bridge_models.models import (
    AccountStatement,
    AccountStatementLob,
    Disbursement,
    DisbursementBatchControl,
    DisbursementBatchControlGeo,
    DisbursementBatchControlGeoAttributes,
    DisbursementEnvelope,
    DisbursementErrorRecon,
    DisbursementRecon,
    DisbursementResolutionFinancialAddress,
    DisbursementResolutionGeoAddress,
    EnvelopeBatchStatusForCash,
    EnvelopeControl,
    NotificationLog,
)
from openg2p_fastapi_partner_auth.jwt_validation_helper import JWTValidationHelper

from .controllers import (
    AccountStatementController,
    DisbursementController,
    DisbursementEnvelopeController,
    DisbursementEnvelopeStatusController,
    DisbursementStatusController,
)
from .services import (
    AccountStatementService,
    DisbursementEnvelopeService,
    DisbursementEnvelopeStatusService,
    DisbursementService,
    DisbursementStatusService,
    RequestValidation,
)

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize()
        RequestValidation()
        DisbursementEnvelopeService()
        DisbursementService()
        AccountStatementService()
        DisbursementStatusService()
        DisbursementEnvelopeStatusService()
        # Inbound partner-signature verification. Backend (keymanager | local) is
        # chosen by crypto_backend config; see openg2p_fastapi_common.utils.crypto.
        build_crypto_helper()
        JWTValidationHelper()
        DisbursementEnvelopeController().post_init()
        DisbursementController().post_init()
        AccountStatementController().post_init()
        DisbursementStatusController().post_init()
        DisbursementEnvelopeStatusController().post_init()

    def migrate_database(self, args):
        super().migrate_database(args)

        async def migrate():
            _logger.info("Migrating database")
            await AccountStatement.create_migrate()
            await AccountStatementLob.create_migrate()
            await Disbursement.create_migrate()
            await DisbursementBatchControl.create_migrate()
            await DisbursementBatchControlGeo.create_migrate()
            await DisbursementBatchControlGeoAttributes.create_migrate()
            await DisbursementEnvelope.create_migrate()
            await DisbursementErrorRecon.create_migrate()
            await DisbursementRecon.create_migrate()
            await DisbursementResolutionFinancialAddress.create_migrate()
            await DisbursementResolutionGeoAddress.create_migrate()
            await EnvelopeBatchStatusForCash.create_migrate()
            await EnvelopeControl.create_migrate()
            await NotificationLog.create_migrate()
            # Local crypto backend: create the partner_keys table and seed-onboard
            # configured partner certs (idempotent). No-op for the keymanager backend.
            if _config.crypto_backend == "local":
                await PartnerKey.create_migrate()
                await seed_partner_certs(_config.crypto_partner_certs)

        asyncio.run(migrate())
