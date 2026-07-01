#!/bin/bash
# Run the sanity suite in-cluster (post-install/post-upgrade hook, or on demand).
#
#   SANITY_RUN_E2E=false (default) -> smoke + contract only (creates NO data).
#                       true       -> full suite incl. the data-creating e2e.
#   SANITY_FAIL_ON_ERROR=false (default) -> always exit 0, so a failing run never
#                       fails the install/upgrade; read the report/logs for results.
#                       true       -> propagate pytest's exit code (CD gating).
#   SANITY_READINESS_TIMEOUT (default 300s) -> wait for ALL dependent services to be
#                       ready before running, so a fresh install doesn't false-fail.
#
# Results (report.html + junit.xml) are written under $SANITY_RESULTS_DIR.
set -o pipefail
cd /app

# --- wait for EVERY dependent service to answer /ping before running ---
# The Helm post-install hook fires when resources are CREATED, not when pods are
# Ready, so this is the real readiness gate. We wait for all services the suite calls
# that expose /ping (Bridge, Bene Portal, Example Bank). With the fail-loud
# `migrate && serve` images, /ping only answers once the DB schema exists, so a 200
# here means "up AND migrated". SPAR has no /ping in the client, so it is not gated.
# If something is still not ready at the timeout we run anyway, so a genuinely-down
# service surfaces as a test failure rather than a hung install.
python - <<'PY'
import os, sys, time
import httpx

verify = (os.environ.get("SANITY_VERIFY_TLS", "true").lower() not in ("false", "0", "no"))
targets = {
    "Bridge": os.environ.get("SANITY_BRIDGE_BASE_URL"),
    "BenePortal": os.environ.get("SANITY_BENE_PORTAL_BASE_URL"),
    "ExampleBank": os.environ.get("SANITY_EXAMPLE_BANK_BASE_URL"),
}
pending = {n: u.rstrip("/") + "/ping" for n, u in targets.items() if u}
if not pending:
    sys.exit(0)
deadline = time.time() + int(os.environ.get("SANITY_READINESS_TIMEOUT", "300"))
while pending and time.time() < deadline:
    for name, url in list(pending.items()):
        try:
            if httpx.get(url, timeout=10, verify=verify).status_code == 200:
                print(f"[sanity] {name} ready at {url}")
                del pending[name]
        except Exception:
            pass
    if pending:
        time.sleep(5)
if pending:
    print(f"[sanity] WARNING: not ready after wait: {', '.join(sorted(pending))} — running anyway")
else:
    print("[sanity] all dependencies ready")
PY

if [ "${SANITY_RUN_E2E}" = "true" ]; then
  echo "[sanity] running FULL suite (smoke + contract + e2e)"
  pytest "$@"
else
  echo "[sanity] running smoke + contract only (SANITY_RUN_E2E=false)"
  pytest -m "smoke or contract" "$@"
fi
rc=$?

if [ "${SANITY_FAIL_ON_ERROR}" = "true" ]; then
  exit $rc
fi
echo "[sanity] SANITY_FAIL_ON_ERROR=false -> exiting 0 (deploy not affected). pytest rc=${rc}"
exit 0
