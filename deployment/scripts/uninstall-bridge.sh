#!/usr/bin/env bash
#
# uninstall-bridge.sh
# -------------------
# Cleanly uninstall an OpenG2P G2P Bridge Helm release and every resource it
# touched, including the PostgreSQL databases and roles that live inside the
# commons-postgresql instance (which are NOT owned by the bridge Helm release
# and therefore survive `helm uninstall`).
#
# What it does, in order:
#   1. helm uninstall <release>            (bridge + bundled example-bank
#                                           workloads, services, helm-owned
#                                           secrets & configmaps, the keycloak
#                                           client K8s secret, etc.)
#   2. Delete leftover Jobs + their Pods   (helm hook / subchart jobs like
#                                           postgres-init and keycloak-init keep
#                                           themselves around via
#                                           hook-delete-policy: before-hook-creation)
#   3. Sweep leftover Secrets/ConfigMaps   (label: app.kubernetes.io/instance)
#   4. Drop Postgres databases + roles     (via `kubectl exec` into
#                                           commons-postgresql-0)
#   5. Delete PVCs by label                (app.kubernetes.io/instance)
#   6. Delete PVs still bound to those PVCs
#      (typically `Released` PVs created with reclaimPolicy=Retain)
#
# Databases dropped (only those THIS chart's postgres-init creates):
#   - <release-underscored>            e.g. g2p_bridge
#   - example_bank_db                  (bundled example-bank simulator)
# It does NOT drop registry_db or pbms_db — those are owned by other
# components, not by the bridge.
#
# Requires: kubectl (cluster admin), helm, bash 4+.
#
# USAGE:
#   ./uninstall-bridge.sh \
#       --namespace <ns> \
#       [--release <name>]            (default: g2p-bridge)
#       [--postgres-release <name>]   (default: commons-postgresql)
#       [--postgres-namespace <ns>]   (default: same as --namespace)
#       [--keep-example-bank-db]      (do NOT drop example_bank_db / bankuser)
#       [--keep-pvs]                  (delete PVCs but not PVs)
#       [--drop-superset-ro]          (also drop the superset_ro analytics role +
#                                      its secret; otherwise left for reinstall.
#                                      NOTE: remove the dashboards from Superset
#                                      separately via remove_dashboards.py.)
#       [--dry-run]                   (print actions, change nothing)
#       [--yes]                       (skip interactive confirmation)
#
# NOTE: example_bank_db / bankuser are FIXED names (not release-scoped). If
# multiple bridge releases share one commons-postgresql, dropping them affects
# all of them — use --keep-example-bank-db in that case.
#
# EXAMPLES:
#   # Dry run first — no changes made:
#   ./uninstall-bridge.sh --namespace trial --dry-run
#
#   # For real, with confirmation prompt:
#   ./uninstall-bridge.sh --namespace trial
#
#   # Non-interactive (CI / scripted):
#   ./uninstall-bridge.sh --namespace trial --yes

set -euo pipefail

# ---------- defaults ----------
RELEASE="g2p-bridge"
NAMESPACE=""
POSTGRES_RELEASE="commons-postgresql"
POSTGRES_NAMESPACE=""
KEEP_EXAMPLE_BANK_DB=false
KEEP_PVS=false
DROP_SUPERSET_RO=false
DRY_RUN=false
ASSUME_YES=false

# ---------- cli ----------
usage() { sed -n '2,60p' "$0"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release)            RELEASE="$2";            shift 2 ;;
    --namespace|-n)       NAMESPACE="$2";          shift 2 ;;
    --postgres-release)   POSTGRES_RELEASE="$2";   shift 2 ;;
    --postgres-namespace) POSTGRES_NAMESPACE="$2"; shift 2 ;;
    --keep-example-bank-db) KEEP_EXAMPLE_BANK_DB=true; shift ;;
    --keep-pvs)           KEEP_PVS=true;           shift ;;
    --drop-superset-ro)   DROP_SUPERSET_RO=true;   shift ;;
    --dry-run)            DRY_RUN=true;            shift ;;
    --yes|-y)             ASSUME_YES=true;         shift ;;
    -h|--help)            usage ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
done

[[ -z "$NAMESPACE" ]] && { echo "ERROR: --namespace is required"; exit 1; }
[[ -z "$POSTGRES_NAMESPACE" ]] && POSTGRES_NAMESPACE="$NAMESPACE"

# ---------- derived: DB / user names (templated exactly like values.yaml) ----------
# values.yaml (global):
#   bridgeDB:        '{{ printf "%s" .Release.Name | replace "-" "_" }}'
#   bridgeDBUser:    '{{ printf "%s_user" .Release.Name | replace "-" "_" }}'
#   exampleBankDB:     example_bank_db    (fixed)
#   exampleBankDBUser: bankuser           (fixed)
RELEASE_UNDERSCORED="${RELEASE//-/_}"
BRIDGE_DB="${RELEASE_UNDERSCORED}"
BRIDGE_USER="${RELEASE_UNDERSCORED}_user"
EXAMPLE_BANK_DB="example_bank_db"
EXAMPLE_BANK_USER="bankuser"

# ---------- helpers ----------
_red()   { printf "\033[31m%s\033[0m\n" "$*"; }
_green() { printf "\033[32m%s\033[0m\n" "$*"; }
_yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
_blue()  { printf "\033[34m%s\033[0m\n" "$*"; }

run() {
  # Print + execute, or just print if --dry-run.
  # Never aborts the script on non-zero exit — cleanup commands must be
  # idempotent. Already-deleted resources produce a notice and we move on.
  echo "  \$ $*"
  if [[ "$DRY_RUN" == false ]]; then
    eval "$@" || _yellow "  (command returned non-zero — continuing)"
  fi
}

kexec_psql() {
  # Run SQL as postgres superuser inside the commons-postgresql pod.
  # Uses PGPASSWORD from the pod's env so no secret reads are needed on
  # the admin's machine. Tolerant of failure — script continues.
  local sql="$1"
  local cmd=(kubectl exec -n "$POSTGRES_NAMESPACE" "$PG_POD" -c postgresql -- \
             bash -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U postgres -v ON_ERROR_STOP=0 -c \"$sql\"")
  echo "  \$ psql -U postgres -c \"$sql\""
  if [[ "$DRY_RUN" == false ]]; then
    "${cmd[@]}" || _yellow "  (psql returned non-zero — continuing)"
  fi
}

# ---------- pre-flight ----------
_blue "==> Pre-flight checks"

command -v kubectl >/dev/null || { _red "kubectl not found"; exit 1; }
command -v helm    >/dev/null || { _red "helm not found";    exit 1; }

if kubectl get ns "$NAMESPACE" >/dev/null 2>&1; then
  NAMESPACE_EXISTS=true
  _green "  Namespace '$NAMESPACE' exists"
else
  NAMESPACE_EXISTS=false
  _yellow "  Namespace '$NAMESPACE' does not exist — namespace-scoped cleanup will be skipped"
fi

# Locate commons-postgresql pod. Bitnami's chart gives it these labels.
PG_POD=""
if kubectl get ns "$POSTGRES_NAMESPACE" >/dev/null 2>&1; then
  PG_POD=$(kubectl get pod -n "$POSTGRES_NAMESPACE" \
    -l "app.kubernetes.io/instance=$POSTGRES_RELEASE,app.kubernetes.io/name=postgresql" \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

  # Fallback: by name.
  if [[ -z "$PG_POD" ]]; then
    if kubectl get pod -n "$POSTGRES_NAMESPACE" "${POSTGRES_RELEASE}-0" >/dev/null 2>&1; then
      PG_POD="${POSTGRES_RELEASE}-0"
    fi
  fi
fi

if [[ -z "$PG_POD" ]]; then
  PG_POD_FOUND=false
  _yellow "  commons-postgresql pod not found — DB / role drop step will be skipped"
  _yellow "  (tried label app.kubernetes.io/instance=$POSTGRES_RELEASE and pod name ${POSTGRES_RELEASE}-0 in namespace '$POSTGRES_NAMESPACE')"
else
  PG_POD_FOUND=true
  _green "  Found Postgres pod: $PG_POD (namespace: $POSTGRES_NAMESPACE)"
fi

# Helm release presence is not strictly required (user may have already uninstalled
# and is now running the cleanup half). Note it but don't abort.
if helm -n "$NAMESPACE" status "$RELEASE" >/dev/null 2>&1; then
  _green "  Helm release '$RELEASE' found in namespace '$NAMESPACE'"
  HELM_RELEASE_EXISTS=true
else
  _yellow "  Helm release '$RELEASE' not found — will skip helm uninstall step"
  HELM_RELEASE_EXISTS=false
fi

# ---------- build the DB drop list ----------
DBS_TO_DROP=("$BRIDGE_DB")
ROLES_TO_DROP=("$BRIDGE_USER")
if [[ "$KEEP_EXAMPLE_BANK_DB" == false ]]; then
  DBS_TO_DROP+=("$EXAMPLE_BANK_DB")
  ROLES_TO_DROP+=("$EXAMPLE_BANK_USER")
fi

# ---------- show the blast radius ----------
_blue "==> Plan"

echo
echo "Will DELETE:"
echo "  - Helm release:        $RELEASE (namespace: $NAMESPACE)"
echo "  - Postgres databases:  ${DBS_TO_DROP[*]}   (dropped INSIDE postgres via the SQL below)"
echo "  - Postgres roles:      ${ROLES_TO_DROP[*]}"
echo "  - namespace resources: Jobs/Secrets/ConfigMaps/PVCs/PVs labeled app.kubernetes.io/instance=$RELEASE"
echo
echo "Will PRESERVE (NOT deleted):"
echo "  - Postgres instance/pod: ${PG_POD:-<not found — DB drop will be skipped>} ($POSTGRES_NAMESPACE)"
echo "      (the script only 'kubectl exec's into it to DROP the databases/roles above)"
echo "  - Other databases:       registry_db, pbms_db (owned by other components)"
[[ "$KEEP_EXAMPLE_BANK_DB" == true ]] && echo "  - example_bank_db / bankuser (--keep-example-bank-db)"
echo

if [[ "$NAMESPACE_EXISTS" == true ]]; then
  echo "Jobs (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get job -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "Secrets (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get secret -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "ConfigMaps (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get configmap -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"

  echo "PVCs (label app.kubernetes.io/instance=$RELEASE):"
  kubectl -n "$NAMESPACE" get pvc -l "app.kubernetes.io/instance=$RELEASE" \
    --no-headers 2>/dev/null | awk '{print "  - " $1}' || echo "  (none)"
else
  echo "(namespace '$NAMESPACE' does not exist — no namespace-scoped resources to preview)"
fi

if [[ "$KEEP_PVS" == false ]]; then
  echo "PVs (bound to above PVCs):"
  if [[ "$NAMESPACE_EXISTS" == true ]]; then
    PVC_NAMES=$(kubectl -n "$NAMESPACE" get pvc -l "app.kubernetes.io/instance=$RELEASE" \
                  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    if [[ -n "$PVC_NAMES" ]]; then
      for pvc in $PVC_NAMES; do
        kubectl get pv -o json 2>/dev/null | \
          jq -r --arg ns "$NAMESPACE" --arg n "$pvc" \
            '.items[] | select(.spec.claimRef.namespace==$ns and .spec.claimRef.name==$n) | "  - " + .metadata.name' \
          2>/dev/null || true
      done
    else
      echo "  (no PVCs; will still check for orphaned PVs claimed by namespace '$NAMESPACE' or labeled with release)"
    fi
  fi
  # Orphaned / Released PVs — show regardless of namespace existence.
  kubectl get pv -o json 2>/dev/null | \
    jq -r --arg ns "$NAMESPACE" --arg rel "$RELEASE" \
      '.items[] | select((.spec.claimRef.namespace==$ns) or (.metadata.labels["app.kubernetes.io/instance"]==$rel)) | "  - " + .metadata.name + " (" + .status.phase + ")"' \
    2>/dev/null | sort -u || true
fi
echo

# ---------- confirmation ----------
if [[ "$DRY_RUN" == true ]]; then
  _yellow "DRY-RUN: no changes will be made."
fi

if [[ "$ASSUME_YES" == false && "$DRY_RUN" == false ]]; then
  _red "This is destructive. Type the release name ('$RELEASE') to confirm:"
  read -r CONFIRM
  if [[ "$CONFIRM" != "$RELEASE" ]]; then
    _red "Confirmation did not match. Aborting."
    exit 1
  fi
fi

# ========== STEP 0: stop in-flight hook Jobs FIRST ==========
# The sanity suite (and other helm-hook Jobs) run as hook resources. If a test
# pod is still running or wedged, `helm uninstall --wait` blocks on it for the
# full --timeout (5m). Delete the Jobs up front (--wait=false so we don't block)
# and force-remove their now-orphaned pods, so the uninstall below returns
# promptly. Any Deployment pods that briefly respawn here are removed by helm
# seconds later — harmless.
_blue "==> [0/6] Stop in-flight Jobs (sanity hook etc.) so the uninstall doesn't hang"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete job -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --wait=false"
  run "kubectl -n '$NAMESPACE' delete pod -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --force --grace-period=0 --wait=false"
else
  echo "  (skipped — namespace '$NAMESPACE' not present)"
fi

# ========== STEP 1: helm uninstall ==========
_blue "==> [1/6] Helm uninstall"
if [[ "$HELM_RELEASE_EXISTS" == true ]]; then
  run "helm uninstall '$RELEASE' -n '$NAMESPACE' --wait --timeout 5m || true"
else
  echo "  (skipped — release not present)"
fi

# ========== STEP 2: delete leftover Jobs (and their Pods) ==========
# Subchart hook Jobs (postgres-init, keycloak-init) are created with
# `helm.sh/hook-delete-policy: before-hook-creation`, so they are NOT cleaned
# up by `helm uninstall`. We delete them explicitly here — BEFORE dropping the
# DBs, so their Pods close their Postgres connections cleanly.
_blue "==> [2/6] Delete leftover Jobs and their Pods"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete job -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --wait=true --timeout=2m"
  # Orphan pods (completed/failed) that a Job left behind after TTL etc.
  run "kubectl -n '$NAMESPACE' delete pod -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found --field-selector=status.phase!=Running"
else
  echo "  (skipped — namespace '$NAMESPACE' not present)"
fi

# ========== STEP 3: sweep leftover Secrets & ConfigMaps ==========
_blue "==> [3/6] Sweep leftover Secrets / ConfigMaps"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  # Keep the superset-ro secret (component=superset-readonly): it is intentionally
  # durable so the read-only password survives uninstall/reinstall and an
  # already-configured Superset connection does not break. It is dropped only via
  # the explicit --drop-superset-ro path in step 4 below.
  run "kubectl -n '$NAMESPACE' delete secret    -l 'app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component!=superset-readonly' --ignore-not-found"
  run "kubectl -n '$NAMESPACE' delete configmap -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found"
else
  echo "  (skipped — namespace '$NAMESPACE' not present)"
fi

# ========== STEP 4: drop Postgres DBs & roles ==========
_blue "==> [4/6] Drop Postgres databases and roles"
if [[ "$PG_POD_FOUND" == true ]]; then
  for db in "${DBS_TO_DROP[@]}"; do
    echo "  - Database: $db"
    kexec_psql "REVOKE CONNECT ON DATABASE \\\"$db\\\" FROM PUBLIC;"
    kexec_psql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();"
    kexec_psql "DROP DATABASE IF EXISTS \\\"$db\\\";"
  done

  for role in "${ROLES_TO_DROP[@]}"; do
    echo "  - Role: $role"
    # Reassign/drop stray ownership outside the dropped DBs (roles can own cluster-wide objects).
    kexec_psql "REASSIGN OWNED BY \\\"$role\\\" TO postgres;"
    kexec_psql "DROP OWNED BY \\\"$role\\\";"
    kexec_psql "DROP ROLE IF EXISTS \\\"$role\\\";"
  done

  if [[ "$DROP_SUPERSET_RO" == true ]]; then
    echo "  - Read-only analytics role: superset_ro (+ secret)"
    # Its grants in the bridge / example_bank DBs went away when those DBs were
    # dropped above; clean any remaining grants in spar (not dropped here), then
    # drop the role. Tolerant — a lingering dependency just leaves the role.
    if [[ "$DRY_RUN" == false ]]; then
      kubectl exec -n "$POSTGRES_NAMESPACE" "$PG_POD" -c postgresql -- \
        bash -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U postgres -d spar -v ON_ERROR_STOP=0 -c 'DROP OWNED BY superset_ro;'" 2>/dev/null \
        || _yellow "  (could not clean superset_ro grants in spar — continuing)"
    fi
    kexec_psql "DROP OWNED BY superset_ro;"
    kexec_psql "DROP ROLE IF EXISTS superset_ro;"
    run "kubectl -n '$NAMESPACE' delete secret '${RELEASE}-superset-ro' --ignore-not-found"
    _yellow "  Reminder: remove the dashboards from Superset too (remove_dashboards.py)."
  fi
else
  echo "  (skipped — commons-postgresql pod not reachable; if Postgres is already gone, DBs are gone too)"
fi

# ========== STEP 5: PVCs ==========
# Includes the sanity-suite results PVC (<release>-sanity-results). Newer charts
# no longer annotate it helm.sh/resource-policy: keep, but older installs may —
# kubectl delete ignores that annotation (it is helm-only), so the label sweep
# removes it regardless. The explicit by-name delete is belt-and-suspenders.
_blue "==> [5/6] Delete PVCs (incl. sanity test-results volume)"
if [[ "$NAMESPACE_EXISTS" == true ]]; then
  run "kubectl -n '$NAMESPACE' delete pvc -l 'app.kubernetes.io/instance=$RELEASE' --ignore-not-found"
  run "kubectl -n '$NAMESPACE' delete pvc '${RELEASE}-sanity-results' --ignore-not-found"
else
  echo "  (skipped — namespace '$NAMESPACE' not present; any orphan PVs handled in step 6)"
fi

# ========== STEP 6: PVs ==========
_blue "==> [6/6] Delete PVs"
if [[ "$KEEP_PVS" == true ]]; then
  _yellow "  (skipped — --keep-pvs)"
else
  # Any PV that still references a PVC in $NAMESPACE labeled with our release.
  # After step 5 the PVCs are gone, so rely on claimRef.
  pv_list=$(kubectl get pv -o json 2>/dev/null | \
    jq -r --arg ns "$NAMESPACE" --arg rel "$RELEASE" \
      '.items[] | select(.spec.claimRef.namespace==$ns) | select(.status.phase=="Released" or .status.phase=="Failed") | .metadata.name' \
    2>/dev/null || true)
  # Also pick up PVs that were labeled at creation time.
  pv_labeled=$(kubectl get pv -l "app.kubernetes.io/instance=$RELEASE" \
                 -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
  pv_all=$(echo "$pv_list $pv_labeled" | tr ' ' '\n' | sort -u | tr '\n' ' ' | sed 's/^ *//;s/ *$//')

  if [[ -z "$pv_all" ]]; then
    echo "  (no PVs to delete)"
  else
    for pv in $pv_all; do
      run "kubectl delete pv '$pv' --ignore-not-found"
    done
  fi
fi

echo
_green "==> Done."
if [[ "$DRY_RUN" == true ]]; then
  _yellow "    (dry-run — nothing was actually changed)"
fi
_yellow "Note: the Keycloak realm/client (clientId 'g2p-bridge') is left intact —"
_yellow "      it lives in Keycloak, not in this namespace. keycloak-init is"
_yellow "      idempotent, so reinstalling reuses it."
echo
_green "Test data removed by this run:"
_green "  - Sanity results PVC ($RELEASE-sanity-results) and its PV"
_green "  - ALL rows in $BRIDGE_DB (incl. TEST_SANITY_* disbursements/envelopes)"
[[ "$KEEP_EXAMPLE_BANK_DB" == false ]] && \
_green "  - ALL rows in $EXAMPLE_BANK_DB (incl. TEST_SANITY_* accounts/payments)"
_yellow "Not touched: SPAR ID->FA test mappings (TEST_SANITY_*) live in the SPAR"
_yellow "      release's own database, not this one. The sanity suite unlinks them"
_yellow "      at end-of-run; for a crashed run use the suite's teardown:"
_yellow "      cd test/sanity && python teardown.py --all"
