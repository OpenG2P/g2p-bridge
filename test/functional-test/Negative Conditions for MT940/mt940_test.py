import requests
import time
from datetime import datetime
from uuid import uuid4
from sqlalchemy import create_engine, Column, String, Float, DateTime, Boolean, Integer, Enum as SqlEnum
from sqlalchemy.orm import sessionmaker, declarative_base
from enum import Enum as PyEnum

# Replace with your actual database URL
DATABASE_URL = 'postgresql://user:password@localhost:port/example_bank_db'

# API endpoints
GENERATE_ACCOUNT_STATEMENT_URL = 'https://example-bank.dev.openg2p.net/api/example-bank/generate_account_statement'
GET_DISBURSEMENT_STATUS_URL = 'https://g2p-bridge.dev.openg2p.net/api/g2p-bridge/get_disbursement_status'

# Replace with your actual authentication headers
API_HEADERS = {
    'Content-Type': 'application/json'
}

# Setup database connection
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()

class DebitCreditTypes(PyEnum):
    DEBIT = 'DEBIT'
    CREDIT = 'CREDIT'

class AccountingLog(Base):
    __tablename__ = 'accounting_logs'
    id = Column(Integer, primary_key=True)
    reference_no = Column(String, index=True, unique=True)
    corresponding_block_reference_no = Column(String, nullable=True)
    customer_reference_no = Column(String, index=True)
    debit_credit = Column(SqlEnum(DebitCreditTypes))
    account_number = Column(String, index=True)
    transaction_amount = Column(Float)
    transaction_date = Column(DateTime)
    transaction_currency = Column(String)
    transaction_code = Column(String, nullable=True)
    narrative_1 = Column(String, nullable=True)
    narrative_2 = Column(String, nullable=True)
    narrative_3 = Column(String, nullable=True)
    narrative_4 = Column(String, nullable=True)
    narrative_5 = Column(String, nullable=True)
    narrative_6 = Column(String, nullable=True)
    reported_in_mt940 = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    active = Column(Boolean, default=True)

def add_duplicate_debit():
    duplicate_entry = AccountingLog(
        reference_no=str(uuid4()),
        customer_reference_no='1728381398013415',
        debit_credit=DebitCreditTypes.DEBIT,
        account_number='MOW_FS_ACC_1',  # Use the same account number as in the API call
        transaction_amount=100.00,  # Amount same as the original to simulate duplicate
        transaction_date=datetime.now(),
        transaction_currency='USD',
        transaction_code='DUPLICATE_DEBIT',
        narrative_1='1728381398013415',
        narrative_2='PROGRAM_X',
        narrative_3='CYCLE_1',
        narrative_4='BENE_1',
        narrative_5='',
        narrative_6='',
        reported_in_mt940=False
    )
    session.add(duplicate_entry)
    session.commit()
    print("Duplicate debit entry added for Disbursement ID - 1")

def add_invalid_disbursement_id():
    invalid_entry = AccountingLog(
        reference_no=str(uuid4()),
        customer_reference_no='1003',
        debit_credit=DebitCreditTypes.DEBIT,
        account_number='MOW_FS_ACC_1',
        transaction_amount=150.00,
        transaction_date=datetime.now(),
        transaction_currency='USD',
        transaction_code='INVALID_DISBURSEMENT_ID',
        narrative_1='1003',
        narrative_2='PROGRAM_Y',
        narrative_3='CYCLE_2',
        narrative_4='BENE_1003',
        narrative_5='',
        narrative_6='',
        reported_in_mt940=False
    )
    session.add(invalid_entry)
    session.commit()
    print("Debit entry added for Invalid Disbursement ID - 1003")

def add_reversal_debit():
    reversal_entry = AccountingLog(
        reference_no=str(uuid4()),
        customer_reference_no='1728381400681693',
        debit_credit=DebitCreditTypes.DEBIT,
        account_number='MOW_FS_ACC_1',
        transaction_amount=-200.00,
        transaction_date=datetime.now(),
        transaction_currency='USD',
        transaction_code='REVERSAL_DEBIT',
        narrative_1='1728381400681693',
        narrative_2='BENE_INV',
        narrative_3='CYCLE_3',
        narrative_4='BENE_1002',
        narrative_5='',
        narrative_6='',
        reported_in_mt940=False
    )
    session.add(reversal_entry)
    session.commit()
    print("Reversal debit entry added for Disbursement ID - 1002")

def generate_account_statement():
    payload = {
        "program_account_number": "MOW_FS_ACC_1"
    }
    response = requests.post(
        GENERATE_ACCOUNT_STATEMENT_URL,
        headers=API_HEADERS,
        json=payload
    )
    if response.status_code == 200:
        print("Account statement generated and uploaded successfully.")
    else:
        print(f"Failed to generate account statement. Status Code: {response.status_code}")
        print(f"Response: {response.text}")

# Function to check for reconciliation errors
def check_reconciliation_errors(disbursement_ids):
    payload = {
        "signature": "string",
        "header": {
            "version": "1.0.0",
            "message_id": "string",
            "message_ts": "string",
            "action": "string",
            "sender_id": "string",
            "sender_uri": "",
            "receiver_id": "",
            "total_count": 0,
            "is_msg_encrypted": False,
            "meta": "string"
        },
        "message": disbursement_ids
    }
    response = requests.post(
        GET_DISBURSEMENT_STATUS_URL,
        headers=API_HEADERS,
        json=payload
    )

    if response.status_code == 200:
        recon_errors = response.json()
        print("Reconciliation errors fetched successfully.")
        print(recon_errors)
        return recon_errors
    else:
        print(f"Failed to fetch reconciliation errors. Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def assert_recon_errors(recon_response, expected_disbursement_ids):
    # Collect all disbursement_error_recon_payloads
    error_entries = []
    for message_item in recon_response.get('message', []):
        disbursement_id = message_item.get('disbursement_id')
        recon_records = message_item.get('disbursement_recon_records', {})
        error_payloads = recon_records.get('disbursement_error_recon_payloads', [])
        for error_payload in error_payloads:
            error_entries.append({
                'disbursement_id': disbursement_id,
                'error_payload': error_payload
            })

    # Check that the expected disbursement IDs have errors
    errors_found = {disbursement_id: False for disbursement_id in expected_disbursement_ids}
    print("Expected Disbursement IDs with errors:", expected_disbursement_ids)
    print("Reconciliation errors fetched:", error_entries)
    for entry in error_entries:
        disbursement_id = entry['disbursement_id']
        if disbursement_id in errors_found:
            errors_found[disbursement_id] = True
    print("Reconciliation errors found:",errors_found)
    # Assert all expected errors are present
    assert all(errors_found.values()), "Not all expected errors are present in reconciliation errors."
    print("All expected reconciliation errors are present.")

def main():
    # Step 1: Insert entries into AccountingLog
    add_duplicate_debit()
    add_invalid_disbursement_id()
    add_reversal_debit()
    #
    # # Step 2: Generate account statement via API
    generate_account_statement()
    #
    # # Wait for a moment to ensure processing
    time.sleep(20)

    # Step 3: Check for reconciliation errors
    # Use the disbursement IDs you expect errors for
    expected_disbursement_ids = ['1728381398013415', '1003', '1728381400681693']
    recon_response = check_reconciliation_errors(expected_disbursement_ids)
    if recon_response:
        # Step 4: Assert that the expected errors are present
        assert_recon_errors(recon_response, expected_disbursement_ids)
    else:
        print("No reconciliation errors found.")

if __name__ == "__main__":
    main()


