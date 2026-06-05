"""TEMPORARY probe 3 — MT940 recon-error pipeline (black-box)."""
import datetime
import json
from sanity.clients import BridgeClient, poll_until
from sanity.config import load_config
from sanity.naming import RunNamespace
from sanity import g2p

cfg = load_config()
ns = RunNamespace.new(cfg.test_prefix)
bridge = BridgeClient(cfg.bridge_base_url, verify_tls=cfg.verify_tls,
                      timeout=cfg.request_timeout_seconds, sender=cfg.test_prefix)
today = datetime.date.today()


def amt15(a):
    return "{:015.2f}".format(float(a)).replace(".", ",")


def bal(a, d, cur):
    cat = "C" if a >= 0 else "D"
    return f"{cat}{d.strftime('%y%m%d')}{cur}" + f"{abs(a):0.2f}".replace(".", ",")


def txn(d, drcr, a, ref, bankref, narr):
    line61 = (d.strftime("%y%m%d") + d.strftime("%m%d") + drcr + ""
              + amt15(a) + "NTRF" + ref + f"//{bankref}")
    return f":61:{line61}\n:86:{narr}"


def narr(b):
    return "\\n".join(["N1", "N2", "N3", b, "N5", "N6"]).replace("\\n", "\n")


cur = cfg.treasury_currency
acct = cfg.treasury_account_number
bad_debit = f"{ns.run_id}_RC_NOEXIST"
bad_rev = f"{ns.run_id}_RC_REVERSAL"
stmt_id = f"{ns.run_id}_STMT"

lines = [f":20:{stmt_id}", f":25:{acct}", ":28C:1/1", f":60F:{bal(100000000, today, cur)}"]
lines.append(txn(today, "D", 1000, bad_debit, "BR1", narr("BENE_1")))
lines.append(txn(today, "RD", 500, bad_rev, "BR2", narr("BENE_2")))
lines.append(f":62F:{bal(100000000, today, cur)}")
mt940 = "\n".join(lines)
print("=== MT940 ===")
print(mt940)
print("=== upload ===")
st, body = bridge.upload_mt940(mt940.encode())
print("upload HTTP", st, "body:", json.dumps(body)[:300])


def status_for(rid):
    _, b = bridge.get_disbursement_status(ns.request_id(), [rid])
    return b


def errors_in(b):
    out = []
    p = g2p.response_payload(b)
    if isinstance(p, list):
        for item in p:
            recs = (item or {}).get("disbursement_recon_records") or {}
            for e in (recs.get("disbursement_error_recon_payloads") or []):
                out.append(e.get("error_reason"))
    return out


print("=== poll invalid-disbursement (max 240s) ===")
ok1, last1 = poll_until(lambda: status_for(bad_debit),
                        predicate=lambda b: "INVALID_DISBURSEMENT_ID" in errors_in(b),
                        timeout=240, interval=10, description="invalid-disb recon")
print("ok1=", ok1, "errors=", errors_in(last1))
print("last1 payload:", json.dumps(g2p.response_payload(last1))[:500])
print("=== poll invalid-reversal (max 120s) ===")
ok2, last2 = poll_until(lambda: status_for(bad_rev),
                        predicate=lambda b: "INVALID_REVERSAL" in errors_in(b),
                        timeout=120, interval=10, description="invalid-reversal recon")
print("ok2=", ok2, "errors=", errors_in(last2))
bridge.close()
print("DONE")
