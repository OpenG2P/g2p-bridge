"""TEMPORARY probe — learn real trial API behavior for negative scenarios.

Run: venv/bin/python probe_negatives.py
Deletes nothing; creates TEST_SANITY-namespaced envelopes only.
"""
import datetime
import json

from sanity.clients import BridgeClient
from sanity.config import load_config
from sanity.naming import RunNamespace
from sanity import g2p

cfg = load_config()
ns = RunNamespace.new(cfg.test_prefix)
bridge = BridgeClient(
    cfg.bridge_base_url, verify_tls=cfg.verify_tls,
    timeout=cfg.request_timeout_seconds, sender=cfg.test_prefix,
)
today = datetime.date.today().isoformat()
past = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()


def env_payload(n, total, *, sched=today, mnemonic=None):
    return {
        "benefit_program_id": cfg.benefit_program_id,
        "benefit_program_mnemonic": mnemonic or ns.program_mnemonic,
        "benefit_program_description": f"{ns.prefix} probe",
        "target_registry": ns.target_registry,
        "benefit_code_id": cfg.benefit_code_id,
        "benefit_code_mnemonic": ns.benefit_code_mnemonic,
        "benefit_code_description": "probe",
        "benefit_type": "CASH_DIGITAL",
        "disbursement_cycle_id": cfg.disbursement_cycle_id,
        "disbursement_frequency": cfg.disbursement_frequency,
        "cycle_code_mnemonic": f"{ns.prefix}_CYCLE",
        "number_of_beneficiaries": n,
        "number_of_disbursements": n,
        "total_disbursement_quantity": total,
        "measurement_unit": cfg.treasury_currency,
        "disbursement_schedule_date": sched,
    }


def disb(env_id, did, bene, qty):
    d = {
        "disbursement_id": did,
        "disbursement_envelope_id": env_id,
        "beneficiary_id": bene,
        "beneficiary_name": "Probe Bene",
        "disbursement_quantity": qty,
        "disbursement_cycle_id": cfg.disbursement_cycle_id,
        "narrative": "probe",
    }
    return d


def make_env(n=2, total=2000, **kw):
    st, body = bridge.create_envelopes(ns.request_id(), [env_payload(n, total, **kw)])
    p = g2p.response_payload(body)
    eid = p[0].get("id") if isinstance(p, list) and p else None
    return eid, st, body


def show(label, st, body):
    rs = g2p.response_status(body)
    code = msg = None
    try:
        p = g2p.response_payload(body)
        if isinstance(p, list) and p and isinstance(p[0], dict):
            code = p[0].get("response_error_code") or p[0].get("error_code")
            msg = p[0].get("response_error_message") or p[0].get("error_message")
        # also check response_header
        rh = body.get("response_header", {}) if isinstance(body, dict) else {}
        code = code or rh.get("response_error_code")
    except Exception:
        pass
    print(f"[{label}] HTTP={st} status={rs} code={code} msg={str(msg)[:80]}")


print("=== baseline create envelope (happy) ===")
eid, st, body = make_env()
show("envelope-happy", st, body)
print("  envelope_id:", eid)

print("\n=== A. past schedule date ===")
_, st, body = make_env(sched=past)
show("past-schedule-date", st, body)

print("\n=== B. non-existent program mnemonic ===")
_, st, body = make_env(mnemonic="DOES_NOT_EXIST_PROGRAM_XYZ")
show("nonexistent-program-mnemonic", st, body)

# disbursement-level: fresh envelope each, n=2 total=2000
print("\n=== C. duplicate beneficiary id (two disb same bene) ===")
e2, _, _ = make_env()
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e2, ns.disbursement_id(1), "BENE_DUP", 1000),
    disb(e2, ns.disbursement_id(2), "BENE_DUP", 1000),
])
show("duplicate-beneficiary", st, body)

print("\n=== D. no beneficiary id ===")
e3, _, _ = make_env()
d = disb(e3, ns.disbursement_id(3), "x", 1000)
d.pop("beneficiary_id")
st, body = bridge.create_disbursements(ns.request_id(), [d])
show("no-beneficiary", st, body)

print("\n=== E. negative amount ===")
e4, _, _ = make_env()
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e4, ns.disbursement_id(4), "BENE_NEG", -500),
])
show("negative-amount", st, body)

print("\n=== F. over-sum (disb total 5000 > envelope 2000) ===")
e5, _, _ = make_env(n=2, total=2000)
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e5, ns.disbursement_id(5), "BENE_A", 2500),
    disb(e5, ns.disbursement_id(6), "BENE_B", 2500),
])
show("over-sum", st, body)

print("\n=== G. over-count (3 disb > envelope number_of_disbursements 2) ===")
e6, _, _ = make_env(n=2, total=6000)
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e6, ns.disbursement_id(7), "BENE_C", 1000),
    disb(e6, ns.disbursement_id(8), "BENE_D", 1000),
    disb(e6, ns.disbursement_id(9), "BENE_E", 1000),
])
show("over-count", st, body)

print("\n=== H. cancel envelope happy, then cancel again ===")
e7, _, _ = make_env()
st, body = bridge.cancel_envelope(ns.request_id(), e7)
show("cancel-envelope-happy", st, body)
st, body = bridge.cancel_envelope(ns.request_id(), e7)
show("cancel-envelope-already-cancelled", st, body)

print("\n=== I. create disbursement against cancelled envelope ===")
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e7, ns.disbursement_id(10), "BENE_F", 1000),
])
show("create-against-cancelled", st, body)

print("\n=== J. cancel disbursements partial-invalid batch ===")
e8, _, _ = make_env()
st, body = bridge.create_disbursements(ns.request_id(), [
    disb(e8, ns.disbursement_id(11), "BENE_G", 1000),
])
real_id = ns.disbursement_id(11)
st, body = bridge.cancel_disbursements(ns.request_id(), [real_id, "TEST_SANITY_INVALID_DISB"])
show("cancel-disb-partial-invalid", st, body)

bridge.close()
print("\nDONE")
