"""Idempotently provision ALL G2P Bridge Superset dashboards (connections,
datasets, charts, dashboards) via the Superset app ORM. Run inside the Superset
pod:  python provision_dashboards.py

The read-only role `superset_ro` is created by the bridge chart
(supersetReadOnly.enabled=true) which publishes its password in the
`<release>-superset-ro` Secret. Pass that password in via the RO_PASS env var:
  RO_PASS=$(kubectl -n <ns> get secret <release>-superset-ro \
    -o jsonpath='{.data.password}' | base64 -d)
  kubectl -n <ns> exec <superset-pod> -- env RO_PASS="$RO_PASS" python /tmp/provision_dashboards.py
"""
import json
import os

from superset.app import create_app

# Read-only role password — from the <release>-superset-ro Secret (see module docstring).
RO_PASS = os.environ.get("RO_PASS", "CHANGE_ME")
PG_HOST = os.environ.get("PG_HOST", "commons-postgresql")
# Database names. The bridge DB defaults to "g2p_bridge" but is derived from the
# Helm release name (dashes->underscores), so set BRIDGE_DB for a renamed release
# (e.g. release "openg2p-bridge" -> BRIDGE_DB=openg2p_bridge).
BRIDGE_DB = os.environ.get("BRIDGE_DB", "g2p_bridge")
SPAR_DB = os.environ.get("SPAR_DB", "spar")
EXAMPLE_BANK_DB = os.environ.get("EXAMPLE_BANK_DB", "example_bank_db")


def uri(dbname):
    return f"postgresql+psycopg2://superset_ro:{RO_PASS}@{PG_HOST}:5432/{dbname}"


app = create_app()
with app.app_context():
    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    # ---------------- helpers ----------------
    def get_db(name, dbname):
        d = db.session.query(Database).filter_by(database_name=name).first()
        if not d:
            d = Database(database_name=name)
            db.session.add(d)
        d.set_sqlalchemy_uri(uri(dbname))
        d.expose_in_sqllab = True
        db.session.commit()
        return d

    def get_ds(database, name, *, table=None, sql=None, dttm=None):
        t = db.session.query(SqlaTable).filter_by(
            table_name=name, database_id=database.id).first()
        if not t:
            t = SqlaTable(table_name=name, database=database)
            db.session.add(t)
        if sql:
            t.sql = sql
        if table and not sql:
            t.schema = "public"
        if dttm:
            t.main_dttm_col = dttm
        db.session.commit()
        t.fetch_metadata()
        db.session.commit()
        return t

    def chart(name, ds, viz, extra):
        params = {"datasource": f"{ds.id}__table", "viz_type": viz}
        params.update(extra)
        pjson = json.dumps(params)
        s = db.session.query(Slice).filter_by(slice_name=name).first()
        if not s:
            s = Slice(slice_name=name, datasource_type="table",
                      datasource_id=ds.id, viz_type=viz, params=pjson)
            db.session.add(s)
        else:
            s.datasource_type = "table"
            s.datasource_id = ds.id
            s.viz_type = viz
            s.params = pjson
        db.session.commit()
        return s

    def COUNT(label="Count"):
        return {"expressionType": "SQL", "sqlExpression": "COUNT(*)", "label": label}

    def SUM(col, label):
        return {"expressionType": "SQL", "sqlExpression": f"SUM({col})", "label": label}

    def bignum(metric, sub=""):
        return {"metric": metric, "adhoc_filters": [], "subheader": sub,
                "y_axis_format": "SMART_NUMBER"}

    def pie(groupby, metric):
        return {"groupby": [groupby], "metric": metric, "adhoc_filters": [],
                "row_limit": 100, "show_legend": True}

    def table_raw(cols, order_col):
        return {"query_mode": "raw", "all_columns": cols,
                "order_by_cols": [json.dumps([order_col, False])],
                "row_limit": 100, "adhoc_filters": []}

    def table_agg(groupby, metrics):
        return {"query_mode": "aggregate", "groupby": groupby, "metrics": metrics,
                "row_limit": 100, "adhoc_filters": [], "order_desc": True}

    def tsline(x, metric, groupby=None):
        return {"x_axis": x, "time_grain_sqla": "P1D", "metrics": [metric],
                "groupby": groupby or [], "adhoc_filters": [], "row_limit": 1000,
                "x_axis_sort_asc": True}

    def dashboard(title, slug, rows):
        # rows: list of list of (slice, width, height)
        pos = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": title}},
        }
        all_slices = []
        for ri, row in enumerate(rows):
            rid = f"ROW-{ri}"
            pos["GRID_ID"]["children"].append(rid)
            pos[rid] = {"type": "ROW", "id": rid, "children": [],
                        "parents": ["ROOT_ID", "GRID_ID"],
                        "meta": {"background": "BACKGROUND_TRANSPARENT"}}
            for ci, (slc, w, h) in enumerate(row):
                cid = f"CHART-{ri}-{ci}"
                pos[rid]["children"].append(cid)
                pos[cid] = {"type": "CHART", "id": cid, "children": [],
                            "parents": ["ROOT_ID", "GRID_ID", rid],
                            "meta": {"width": w, "height": h, "chartId": slc.id,
                                     "uuid": str(slc.uuid), "sliceName": slc.slice_name}}
                all_slices.append(slc)
        d = db.session.query(Dashboard).filter_by(slug=slug).first()
        if not d:
            d = Dashboard(dashboard_title=title, slug=slug)
            db.session.add(d)
        d.dashboard_title = title
        d.position_json = json.dumps(pos)
        d.slices = all_slices
        d.published = True
        db.session.commit()
        print("dashboard:", d.id, slug, "charts:", len(all_slices))

    # ---------------- databases ----------------
    bridge = get_db("g2p_bridge", BRIDGE_DB)
    spar = get_db("spar", SPAR_DB)
    eb = get_db("example_bank", EXAMPLE_BANK_DB)

    # ---------------- datasets ----------------
    ENRICHED_SQL = """
SELECT d.id AS disbursement_id, d.disbursement_envelope_id AS envelope_id,
  d.beneficiary_id, d.beneficiary_name, d.disbursement_quantity AS amount,
  d.cancellation_status, d.created_at, e.benefit_program_mnemonic AS program,
  e.benefit_type, e.measurement_unit AS currency, e.disbursement_schedule_date,
  bc.fa_resolution_status, bc.sponsor_bank_dispatch_status,
  ec.funds_available_with_bank, ec.funds_blocked_with_bank,
  CASE WHEN d.cancellation_status='CANCELLED' THEN '6_CANCELLED'
       WHEN bc.sponsor_bank_dispatch_status='PROCESSED' THEN '5_DISBURSED'
       WHEN ec.funds_blocked_with_bank='FUNDS_BLOCK_SUCCESS' THEN '4_FUNDS_BLOCKED'
       WHEN ec.funds_available_with_bank='FUNDS_AVAILABLE' THEN '3_FUNDS_CHECKED'
       WHEN bc.fa_resolution_status='PROCESSED' THEN '2_FA_RESOLVED'
       ELSE '1_CREATED' END AS current_stage
FROM disbursements d
LEFT JOIN disbursement_envelopes e ON d.disbursement_envelope_id=e.id
LEFT JOIN disbursement_batch_control bc ON d.disbursement_batch_control_id=bc.id
LEFT JOIN envelope_batch_status_for_cash ec ON d.disbursement_envelope_id=ec.disbursement_envelope_id
""".strip()
    disb = get_ds(bridge, "disbursements_enriched", sql=ENRICHED_SQL, dttm="created_at")
    batch = get_ds(bridge, "disbursement_batch_control", table="disbursement_batch_control", dttm="created_at")
    rerr = get_ds(bridge, "disbursement_error_recons", table="disbursement_error_recons", dttm="created_at")
    recon = get_ds(bridge, "disbursement_recons", table="disbursement_recons", dttm="created_at")
    smap = get_ds(spar, "id_fa_mappings", table="id_fa_mappings", dttm="created_at")
    sstr = get_ds(spar, "strategy", table="strategy", dttm="created_at")
    sbank = get_ds(spar, "banks", table="banks", dttm="created_at")
    eacct = get_ds(eb, "accounts", table="accounts", dttm="created_at")
    elog = get_ds(eb, "accounting_logs", table="accounting_logs", dttm="transaction_date")
    epay = get_ds(eb, "initiate_payment_batch_requests", table="initiate_payment_batch_requests", dttm="created_at")
    eblock = get_ds(eb, "fund_blocks", table="fund_blocks", dttm="created_at")
    print("datasets ready")

    # ---------------- D1 Operations Overview (ensure/refresh) ----------------
    c = chart
    d1 = [
        [(c("Total Disbursements", disb, "big_number_total", bignum(COUNT("Disbursements"))), 6, 50),
         (c("Total Amount Disbursed", disb, "big_number_total", bignum(SUM("amount", "Amount"))), 6, 50)],
        [(c("Disbursements by Stage", disb, "pie", pie("current_stage", COUNT())), 6, 50),
         (c("Disbursements by Program", disb, "pie", pie("program", COUNT())), 6, 50)],
        [(c("Disbursements over Time", disb, "echarts_timeseries_line", tsline("created_at", COUNT())), 12, 50)],
        [(c("Recent Disbursements", disb, "table",
            table_raw(["created_at", "disbursement_id", "beneficiary_id", "program", "amount", "currency", "current_stage"], "created_at")), 12, 60)],
    ]
    dashboard("G2P Bridge — Operations Overview", "g2p-bridge-operations-overview", d1)

    # ---------------- D2 Failures & Exceptions ----------------
    d2 = [
        [(c("Cancelled Disbursements", disb, "big_number_total",
            {**bignum(COUNT("Cancelled")), "adhoc_filters": [{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": "cancellation_status = 'CANCELLED'"}]}), 6, 50),
         (c("FA Resolution Errors", batch, "big_number_total",
            {**bignum(COUNT("FA errors")), "adhoc_filters": [{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": "fa_resolution_latest_error_code IS NOT NULL"}]}), 6, 50)],
        [(c("Disbursements by Current Stage", disb, "pie", pie("current_stage", COUNT())), 6, 50),
         (c("FA Errors by Code", batch, "table",
            table_agg(["fa_resolution_latest_error_code"], [COUNT()])), 6, 50)],
        [(c("Sponsor Dispatch Errors by Code", batch, "table",
            table_agg(["sponsor_bank_dispatch_latest_error_code"], [COUNT()])), 12, 50)],
    ]
    dashboard("G2P Bridge — Failures & Exceptions", "g2p-bridge-failures", d2)

    # ---------------- D3 Reconciliation & Settlement ----------------
    d3 = [
        [(c("Reconciliation Records", recon, "big_number_total", bignum(COUNT("Recon records"))), 4, 50),
         (c("Reconciliation Errors", rerr, "big_number_total", bignum(COUNT("Recon errors"))), 4, 50),
         (c("Reversals", recon, "big_number_total",
            {**bignum(COUNT("Reversals")), "adhoc_filters": [{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": "reversal_found = true"}]}), 4, 50)],
        [(c("Recon Errors by Reason", rerr, "pie", pie("error_reason", COUNT())), 6, 50),
         (c("Recon Errors by Reason (table)", rerr, "table", table_agg(["error_reason"], [COUNT()])), 6, 50)],
        [(c("Recon Errors Detail", rerr, "table",
            table_raw(["created_at", "reconciliation_id", "error_reason", "statement_id", "bank_reference_number"], "created_at")), 12, 60)],
    ]
    dashboard("G2P Bridge — Reconciliation & Settlement", "g2p-bridge-reconciliation", d3)

    # ---------------- D4 SPAR — Mappings, Strategies & Parties ----------------
    d4 = [
        [(c("Total ID→FA Mappings", smap, "big_number_total", bignum(COUNT("Mappings"))), 3, 50),
         (c("Active Mappings", smap, "big_number_total",
            {**bignum(COUNT("Active")), "adhoc_filters": [{"expressionType": "SQL", "clause": "WHERE", "sqlExpression": "active = true"}]}), 3, 50),
         (c("Strategies", sstr, "big_number_total", bignum(COUNT("Strategies"))), 3, 50),
         (c("Banks", sbank, "big_number_total", bignum(COUNT("Banks"))), 3, 50)],
        [(c("Strategy Registry", sstr, "table",
            table_raw(["id", "description", "strategy_type", "construct_strategy", "deconstruct_strategy", "active"], "id")), 12, 50)],
        [(c("Banks Registry", sbank, "table",
            table_raw(["bank_code", "bank_name", "bank_mnemonic", "active"], "bank_code")), 6, 50),
         (c("ID→FA Mappings", smap, "table",
            table_raw(["created_at", "id_value", "fa_value", "name", "phone", "active"], "created_at")), 6, 50)],
    ]
    dashboard("G2P Bridge — SPAR Mappings, Strategies & Parties", "g2p-bridge-spar", d4)

    # ---------------- D6 Example Bank (simulator) ----------------
    d6 = [
        [(c("Total Accounts", eacct, "big_number_total", bignum(COUNT("Accounts"))), 4, 50),
         (c("Total Book Balance", eacct, "big_number_total", bignum(SUM("book_balance", "Book balance"))), 4, 50),
         (c("Total Blocked", eacct, "big_number_total", bignum(SUM("blocked_amount", "Blocked"))), 4, 50)],
        [(c("Payment Batches by Status", epay, "pie", pie("payment_status", COUNT())), 6, 50),
         (c("Batching Requests by Status", epay, "pie", pie("batching_request_status", COUNT())), 6, 50)],
        [(c("Transactions over Time", elog, "echarts_timeseries_line", tsline("transaction_date", COUNT(), ["debit_credit"])), 12, 50)],
        [(c("Account Balances", eacct, "table",
            table_raw(["account_number", "account_holder_name", "account_currency", "book_balance", "available_balance", "blocked_amount"], "account_number")), 12, 60)],
    ]
    dashboard("G2P Bridge — Example Bank (Simulator)", "g2p-bridge-example-bank", d6)

    print("OK ALL DASHBOARDS PROVISIONED")
