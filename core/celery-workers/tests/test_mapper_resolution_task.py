from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openg2p_g2p_bridge_celery_workers.tasks.mapper_resolution_task import (
    make_resolve_request,
    mapper_resolution_worker,
    process_and_store_resolution,
)
from openg2p_g2p_bridge_models.models import (
    BenefitType,
    Disbursement,
    DisbursementBatchControl,
    DisbursementEnvelope,
    DisbursementFrequency,
    ProcessStatus,
)


class MockSession:
    def __init__(self):
        self.committed = False
        self.flushed = False
        self.details_list = []
        self.updates = []
        self.query_args = ()
        self.disbursement_batch_controls = [
            DisbursementBatchControl(
                id="test_batch_control_id",
                disbursement_cycle_id=1,
                disbursement_envelope_id="test_envelope_id",
                fa_resolution_status=ProcessStatus.PENDING,
                sponsor_bank_dispatch_status=ProcessStatus.PENDING,
                geo_resolution_status=ProcessStatus.PENDING,
                warehouse_allocation_status=ProcessStatus.PENDING,
                agency_allocation_status=ProcessStatus.PENDING,
            ),
        ]
        self.disbursement = Disbursement(
            id="test_disbursement_id",
            disbursement_envelope_id="test_envelope_id",
            beneficiary_id="test_beneficiary_id",
            beneficiary_name="Test Beneficiary",
            disbursement_quantity=100.0,
            narrative="Test disbursement",
            disbursement_cycle_id=1,
            disbursement_batch_control_id="test_batch_control_id",
        )
        self.disbursements = [self.disbursement]
        self.disbursement_envelope = DisbursementEnvelope(
            id="test_envelope_id",
            benefit_program_mnemonic="test_program",
            benefit_code_id=1,
            benefit_type=BenefitType.CASH_DIGITAL,
            disbursement_cycle_id=1,
            disbursement_frequency=DisbursementFrequency.Monthly,
            cycle_code_mnemonic="test_cycle_mnemonic",
            number_of_beneficiaries=10,
            number_of_disbursements=10,
            total_disbursement_quantity=1000,
            measurement_unit="KES",
            disbursement_schedule_date=datetime.now().date(),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def execute(self, *args):
        # Simulate SQLAlchemy select queries
        select_obj = args[0]
        model_cls = select_obj.column_descriptions[0]["type"]
        query_type = None
        if model_cls is DisbursementBatchControl:
            query_type = "batch_control"
        elif model_cls is Disbursement:
            query_type = "disbursement"

        class ScalarResult:
            def __init__(self, parent, query_type):
                self.parent = parent
                self.query_type = query_type

            def scalars(self):
                class AllResult:
                    def all(inner_self):
                        if self.query_type == "batch_control":
                            return self.parent.disbursement_batch_controls
                        elif self.query_type == "disbursement":
                            return [self.parent.disbursement]
                        return []

                    def first(inner_self):
                        if self.query_type == "batch_control":
                            if not self.parent.disbursement_batch_controls:
                                return None
                            return self.parent.disbursement_batch_controls[0]
                        elif self.query_type == "disbursement":
                            if not self.parent.disbursements:
                                return None
                            return self.parent.disbursements[0]
                        return None

                return AllResult()

            def first(self):
                # Return the first batch control or disbursement depending on context
                if hasattr(self, "disbursement_batch_controls") and self.disbursement_batch_controls:
                    return self.disbursement_batch_controls[0]
                if hasattr(self, "disbursements") and self.disbursements:
                    return self.disbursements[0]
                return None

        return ScalarResult(self, query_type)

    def scalars(self):
        return self

    def all(self):
        if not self.query_args:
            return []
        if self.query_args[0] is DisbursementBatchControl:
            return self.disbursement_batch_controls
        elif self.query_args[0] is Disbursement:
            return self.disbursements
        return []

    def query(self, *args):
        self.query_args = args
        return self

    def filter(self, *args):
        self.filter_args = args
        return self

    def update(self, *args, **kwargs):
        # Always append a dict to self.updates for both success and error paths.
        # Production keys the update dict by InstrumentedAttribute column objects, so
        # normalise the keys to their plain column names for easy assertions.
        def _normalize(d):
            normalized = {}
            for key, value in d.items():
                key_name = getattr(key, "key", key)
                normalized[key_name] = value
            return normalized

        for arg in args:
            if isinstance(arg, dict):
                self.updates.append(_normalize(arg))
        if kwargs:
            self.updates.append(_normalize(kwargs))
        return True

    def add(self, item):
        self.added = item

    def add_all(self, items):
        self.details_list.extend(items)

    def commit(self):
        self.committed = True

    def flush(self):
        self.flushed = True

    def first(self):
        if not self.query_args:
            return None
        if self.query_args[0] is DisbursementBatchControl:
            return self.disbursement_batch_controls[0]
        elif self.query_args[0] is Disbursement:
            return self.disbursements[0]
        return None


@pytest.fixture
def mock_session_maker():
    mock_session = MockSession()

    with patch(
        "openg2p_g2p_bridge_celery_workers.tasks.mapper_resolution_task.sessionmaker",
        return_value=lambda: mock_session,
    ):
        yield mock_session


@pytest.fixture
def mock_resolve_helper():
    # Use MagicMock for the helper and set async methods with AsyncMock
    mock_helper = MagicMock()
    mock_helper.create_jwt_token = AsyncMock(return_value="mocked_jwt_token")
    mock_helper.construct_single_resolve_request.return_value = MagicMock()
    mock_helper.construct_resolve_request.return_value = MagicMock(
        dict=MagicMock(return_value={"key": "value"})  # Mock the dict method
    )
    mock_helper.deconstruct_fa.return_value = {
        "mapper_resolved_fa_type": "BANK",
        "bank_account_number": "123",
        "bank_code": "ABC",
        "branch_code": "001",
    }

    with patch(
        "openg2p_g2p_bridge_celery_workers.tasks.mapper_resolution_task.ResolveHelper.get_component",
        return_value=mock_helper,
    ):
        yield mock_helper


@pytest.fixture
def mock_resolve_client():
    # The current code resolves through MapperFactory.get_component().get_mapper(),
    # whose .resolve(...) coroutine returns the ResolveResponse.
    mock_mapper = MagicMock()
    mock_mapper.resolve = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.get_mapper.return_value = mock_mapper

    with patch(
        "openg2p_g2p_bridge_celery_workers.tasks.mapper_resolution_task.MapperFactory.get_component",
        return_value=mock_factory,
    ):
        yield mock_mapper.resolve


def test_mapper_resolution_worker_success(mock_session_maker, mock_resolve_helper, mock_resolve_client):
    # ResolveResponse exposes .results; each result carries .id, .fa and .name.
    single_result = MagicMock(id="test_beneficiary_id", fa={"account_number": "123"})
    single_result.name = "TEST_NAME"
    mock_response = MagicMock(results=[single_result])
    mock_resolve_client.return_value = mock_response

    # Only pass the batch control ID (session is handled by patching sessionmaker)
    mapper_resolution_worker("test_batch_control_id")

    assert len(mock_session_maker.details_list) != 0
    update_values = next(
        (item for item in mock_session_maker.updates if "fa_resolution_status" in item),
        None,
    )
    assert update_values is not None
    assert update_values["fa_resolution_status"] == ProcessStatus.PROCESSED.value
    assert isinstance(update_values["fa_resolution_timestamp"], datetime)
    assert update_values["fa_resolution_latest_error_code"] is None

    assert mock_session_maker.flushed
    assert mock_session_maker.committed


def test_mapper_resolution_worker_failure(mock_session_maker, mock_resolve_helper, mock_resolve_client):
    # The except path records the error directly on the batch control object (not via
    # a query().update()) and, while attempts stay below the max, leaves status PENDING.
    mock_session_maker.disbursement_batch_controls[0].fa_resolution_attempts = 0
    mock_resolve_client.side_effect = Exception("TEST_ERROR")

    mapper_resolution_worker("test_batch_id")

    batch_control = mock_session_maker.disbursement_batch_controls[0]
    assert batch_control.fa_resolution_status == ProcessStatus.PENDING.value
    assert "TEST_ERROR" in batch_control.fa_resolution_latest_error_code
    assert isinstance(batch_control.fa_resolution_timestamp, datetime)

    assert mock_session_maker.committed


@pytest.mark.asyncio
async def test_make_resolve_request_success(mock_resolve_helper, mock_resolve_client):
    disbursements = [
        Disbursement(
            id="test_disbursement_id",
            disbursement_envelope_id="test_envelope_id",
            beneficiary_id="test_beneficiary_id",
            beneficiary_name="Test Beneficiary",
            disbursement_quantity=100.0,
            narrative="Test disbursement",
            disbursement_cycle_id=1,
            disbursement_batch_control_id="test_batch_control_id",
        )
    ]
    mock_response = "RESOLVE_RESPONSE"
    mock_resolve_client.return_value = mock_response

    response, error = await make_resolve_request(disbursements)
    assert response == mock_response
    assert error is None


@pytest.mark.asyncio
async def test_make_resolve_request_failure(mock_resolve_helper, mock_resolve_client):
    disbursements = [
        Disbursement(
            id="test_disbursement_id",
            disbursement_envelope_id="test_envelope_id",
            beneficiary_id="test_beneficiary_id",
            beneficiary_name="Test Beneficiary",
            disbursement_quantity=100.0,
            narrative="Test disbursement",
            disbursement_cycle_id=1,
            disbursement_batch_control_id="test_batch_control_id",
        )
    ]
    # A falsy resolve response makes make_resolve_request report a failure.
    mock_resolve_client.return_value = None

    response, error_msg = await make_resolve_request(disbursements)
    assert response is None
    assert "Failed to resolve the request" in error_msg


def test_process_and_store_resolution_success(mock_session_maker, mock_resolve_helper):
    # A resolved beneficiary (id present in the map and a non-empty fa) yields one
    # DisbursementResolutionFinancialAddress row, and the batch is marked PROCESSED.
    single_result = MagicMock(
        id="test_beneficiary_id",
        fa={"account_number": "123", "bank_code": "ABC", "branch_code": "001"},
    )
    single_result.name = "Test Name"
    mock_response = MagicMock(results=[single_result])
    beneficiary_map = {"test_beneficiary_id": "test_disbursement_id"}

    process_and_store_resolution("test_batch_control_id", mock_response, beneficiary_map, mock_session_maker)

    assert len(mock_session_maker.details_list) == 1
    update_values = next(
        (item for item in mock_session_maker.updates if "fa_resolution_status" in item),
        None,
    )
    assert update_values is not None
    assert update_values["fa_resolution_status"] == ProcessStatus.PROCESSED.value
    assert isinstance(update_values["fa_resolution_timestamp"], datetime)
    assert update_values["fa_resolution_latest_error_code"] is None
    assert mock_session_maker.flushed
    assert mock_session_maker.committed


def test_process_and_store_resolution_failure(mock_session_maker, mock_resolve_helper):
    # An unresolved beneficiary (fa is falsy) is now simply SKIPPED: no financial-address
    # row is created, batch_has_error stays False, so the batch is still marked PROCESSED.
    single_result = MagicMock(id="test_beneficiary_id", fa=None)
    single_result.name = "Test Name"
    mock_response = MagicMock(results=[single_result])
    beneficiary_map = {"test_beneficiary_id": "test_disbursement_id"}

    process_and_store_resolution("test_batch_control_id", mock_response, beneficiary_map, mock_session_maker)

    assert len(mock_session_maker.details_list) == 0
    update_values = next(
        (item for item in mock_session_maker.updates if "fa_resolution_status" in item),
        None,
    )
    assert update_values is not None
    assert update_values["fa_resolution_status"] == ProcessStatus.PROCESSED.value
    assert update_values["fa_resolution_latest_error_code"] is None
    assert mock_session_maker.flushed
    assert mock_session_maker.committed
