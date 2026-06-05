"""TEMPORARY probe 4 — D-only invalid-disbursement recon error."""
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
    return f"C{d.strftime('%y%m%d')}{cur}" + f"{a:0.2f}".replace(".", ",")


cur, acct = cfg.treasury_currency, cfg.treasury_account_number
bad = f"{ns.run_id}_RC_NOEXIST"
narr = "\n".join(["N1", "N2", "N3", "BENE_1", "N5", "N6"])
line61 = today.strftime("%y%m%d") + today.strftime("%m%d") + "D" + amt15(1000) + "NTRF" + bad + "//BR1"
mt940 = "\n".join([
    f":20:{ns.run_id}_STMT", f":25:{acct}", ":28C:1/1", f":60F:{bal(100000000, today, cur)}",
    f":61:{line61}", f":86:{narr}", f":62F:{bal(100000000, today, cur)}",
])
st, body = bridge.upload_mt940(mt940.encode())
print("upload HTTP", st)


def status_for(rid):
    _, b = bridge.get_disbursement_status(ns.request_id(), [rid])
    return b


def errs(b):
    p = g2p.response_payload(b)
    out = []
    if isinstance(p, list):
        for it in p:
            recs = (it or {}).get("disbursement_recon_records") or {}
            for e in recs.get("disbursement_error_recon_payloads") or []:
                out.append(e.get("error_reason"))
    return out


ok, last = poll_until(lambda: status_for(bad),
                      predicate=lambda b: "INVALID_DISBURSEMENT_ID" in errs(b),
                      timeout=180, interval=10, description="invalid-disb recon")
print("ok=", ok, "errors=", errs(last))
print("payload:", json.dumps(g2p.response_payload(last))[:600])
bridge.close()
print("DONE")
