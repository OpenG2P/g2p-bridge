"""TEMPORARY probe 2 — cancel happy paths with real disbursements."""
import datetime
from sanity.clients import BridgeClient
from sanity.config import load_config
from sanity.naming import RunNamespace
from sanity import g2p

cfg = load_config()
ns = RunNamespace.new(cfg.test_prefix)
bridge = BridgeClient(cfg.bridge_base_url, verify_tls=cfg.verify_tls,
                      timeout=cfg.request_timeout_seconds, sender=cfg.test_prefix)
today = datetime.date.today().isoformat()


def env_payload(n, total):
    return {
        "benefit_program_id": cfg.benefit_program_id,
        "benefit_program_mnemonic": ns.program_mnemonic,
        "benefit_program_description": "probe", "target_registry": ns.target_registry,
        "benefit_code_id": cfg.benefit_code_id, "benefit_code_mnemonic": ns.benefit_code_mnemonic,
        "benefit_code_description": "probe", "benefit_type": "CASH_DIGITAL",
        "disbursement_cycle_id": cfg.disbursement_cycle_id,
        "disbursement_frequency": cfg.disbursement_frequency,
        "cycle_code_mnemonic": f"{ns.prefix}_CYCLE", "number_of_beneficiaries": n,
        "number_of_disbursements": n, "total_disbursement_quantity": total,
        "measurement_unit": cfg.treasury_currency, "disbursement_schedule_date": today,
    }


def disb(env_id, did, bene, qty):
    return {"disbursement_id": did, "disbursement_envelope_id": env_id,
            "beneficiary_id": bene, "beneficiary_name": "Probe", "disbursement_quantity": qty,
            "disbursement_cycle_id": cfg.disbursement_cycle_id, "narrative": "probe"}


def make_env(n=1, total=1000):
    _, body = bridge.create_envelopes(ns.request_id(), [env_payload(n, total)])
    p = g2p.response_payload(body)
    return p[0].get("id") if isinstance(p, list) and p else None


def show(label, st, body):
    rs = g2p.response_status(body)
    code = None
    try:
        p = g2p.response_payload(body)
        if isinstance(p, list) and p and isinstance(p[0], dict):
            code = p[0].get("response_error_code")
    except Exception:
        pass
    print(f"[{label}] HTTP={st} status={rs} code={code}")


# K: envelope WITH a disbursement, then cancel envelope
e = make_env(1, 1000)
did = ns.disbursement_id(1)
st, body = bridge.create_disbursements(ns.request_id(), [disb(e, did, "BENE_K", 1000)])
show("create-disb-happy", st, body)
st, body = bridge.cancel_envelope(ns.request_id(), e)
show("cancel-envelope-with-disb", st, body)

# L: pure-happy cancel_disbursements (single valid id)
e2 = make_env(1, 1000)
did2 = ns.disbursement_id(2)
bridge.create_disbursements(ns.request_id(), [disb(e2, did2, "BENE_L", 1000)])
st, body = bridge.cancel_disbursements(ns.request_id(), [did2])
show("cancel-disbursements-happy", st, body)

bridge.close()
print("DONE")
