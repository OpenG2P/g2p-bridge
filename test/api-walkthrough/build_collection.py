#!/usr/bin/env python3
"""Generate the G2P Bridge **API Walkthrough** Postman artifacts.

This is the maintainer source-of-truth (like ``provision_dashboards.py`` for the
Superset bundle). Running it emits three files that implementers import/run:

  * ``beneficiaries.csv``                         — editable seed data (one row
                                                    per beneficiary; the Postman
                                                    Collection Runner data file)
  * ``G2P-Bridge-API-Walkthrough.postman_collection.json``
  * ``G2P-Bridge.postman_environment.json``

The walkthrough drives the full digital-cash disbursement lifecycle against a
live Bridge + SPAR + Example Bank, manually, from an implementer's laptop. It
mirrors the request shapes used by the automated sanity suite (``test/sanity``),
which is the single source of truth for the G2PConnect envelope and the staged
pipeline. Auth is assumed disabled (signature/keymanager validation off).

Run order (documented in GitBook → Developer Zone → API Walkthrough):

  1 · Health checks                       (run once)
  2 · Create disbursement envelope        (run once)
  3 · Link beneficiaries in SPAR          (run with beneficiaries.csv; builds the batch)
  4 · Create disbursements (one batch)    (run once — whole batch in one call)
  5 · Observe the pipeline                (run manually, RE-RUN as the async stages advance)
  6 · Cleanup — unlink SPAR               (run with beneficiaries.csv)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# 1) Seed data — editable CSV (the Collection Runner "data file").
# --------------------------------------------------------------------------- #
# Volume: enough to look like a real batch (not a 2-row sanity check), small
# enough to run in well under a minute. Composition exercises the happy path
# plus the two negative cases the implementers asked for.
N_HAPPY = 20
N_MISSING = 3  # not linked in SPAR  -> FA resolution skips them (never paid)
N_BADACCT = 2  # linked at a FOREIGN bank -> money never lands in their account


def _csv_rows() -> list[dict]:
    rows: list[dict] = []
    i = 1

    def row(scenario: str, bank: str) -> dict:
        nonlocal i
        r = {
            "beneficiary_id": f"BENE_{i:04d}",
            "beneficiary_name": f"Beneficiary {i:04d}",
            "account_number": f"ACC{1000000 + i}",
            "branch_code": "0001",
            "bank_code": bank,
            "mobile": f"+1000{i:06d}",
            "email": f"bene{i:04d}@example.org",
            "amount": 1000,
            "currency": "USD",
            "scenario": scenario,
        }
        i += 1
        return r

    for _ in range(N_HAPPY):
        rows.append(row("happy", "EXAMPLE-BANK"))
    for _ in range(N_MISSING):
        rows.append(row("missing_from_spar", "EXAMPLE-BANK"))
    for _ in range(N_BADACCT):
        # A valid-format account at a bank the simulator treats as "foreign": the
        # FA resolves, but the credit is routed to a clearing account, so the
        # beneficiary's own account is never funded (with ~30% explicit reversal).
        rows.append(row("bad_account", "OTHER-BANK"))
    return rows


CSV_COLUMNS = [
    "beneficiary_id",
    "beneficiary_name",
    "account_number",
    "branch_code",
    "bank_code",
    "mobile",
    "email",
    "amount",
    "currency",
    "scenario",
]


def write_csv() -> None:
    rows = _csv_rows()
    with open(HERE / "beneficiaries.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    total = sum(r["amount"] for r in rows)
    print(f"beneficiaries.csv: {len(rows)} rows, total amount {total}")


# --------------------------------------------------------------------------- #
# Small helpers to build Postman v2.1 nodes.
# --------------------------------------------------------------------------- #
def _script(lines: str) -> dict:
    return {"type": "text/javascript", "exec": lines.strip("\n").split("\n")}


def _event(listen: str, lines: str) -> dict:
    return {"listen": listen, "script": _script(lines)}


def _raw_body(obj_text: str) -> dict:
    return {
        "mode": "raw",
        "raw": obj_text.strip("\n"),
        "options": {"raw": {"language": "json"}},
    }


def _url(raw: str) -> dict:
    # Postman is happy with just {"raw": ...}; it parses host/path on import.
    return {"raw": raw}


def _request(method: str, url_raw: str, body_text: str | None = None) -> dict:
    req: dict = {
        "method": method,
        "header": (
            [{"key": "Content-Type", "value": "application/json"}] if body_text else []
        ),
        "url": _url(url_raw),
    }
    if body_text is not None:
        req["body"] = _raw_body(body_text)
    return req


def item(name, method, url_raw, *, body=None, pre=None, test=None, desc=None) -> dict:
    node: dict = {"name": name, "request": _request(method, url_raw, body)}
    events = []
    if pre:
        events.append(_event("prerequest", pre))
    if test:
        events.append(_event("test", test))
    if events:
        node["event"] = events
    if desc:
        node["request"]["description"] = desc
    return node


# --------------------------------------------------------------------------- #
# Reusable G2PConnect request_header. request_id / request_timestamp are set by the
# collection pre-request (not the {{$guid}}/{{$isoTimestamp}} dynamic vars) so the
# signed bytes equal exactly what Postman sends — the signature is computed over
# the resolved body.
# --------------------------------------------------------------------------- #
HEADER = """
  "request_header": {
    "sender_app_mnemonic": "{{sender_app}}",
    "sender_app_url": "{{sender_app_url}}",
    "request_id": "{{request_id}}",
    "request_timestamp": "{{request_timestamp}}",
    "instance_id": null
  }"""


# --------------------------------------------------------------------------- #
# Collection-level pre-request: sign Partner API requests (TEST/DEMO).
#
# Signs the request body as a detached JWS in the "Signature" header, matching the
# Bridge's local (PyJWT) verification: signing input = base64url(header) + "." +
# base64url(canonical_json(body)), canonical = sorted-keys compact JSON. Only
# requests to {{bridge_base_url}} are signed. Uses the committed TEST-ONLY PEM key
# in {{signing_private_pem}} (exported from test/keys/test-partner.p12 — the Postman
# sandbox's jsrsasign cannot read a password-protected .p12). jsrsasign is loaded
# once from a pinned CDN (needs internet) and cached in a collection variable.
# Set sign_requests=false in the environment to disable (unsigned Bridge).
# --------------------------------------------------------------------------- #
SIGN_PREREQUEST = r"""
// Deterministic request id + timestamp, referenced by the body templates, so the
// signed bytes equal what Postman sends.
pm.collectionVariables.set('request_id', pm.variables.replaceIn('{{$guid}}'));
pm.collectionVariables.set('request_timestamp', new Date().toISOString());

if (String(pm.variables.get('sign_requests')) !== 'true') return;
var raw = pm.request.body && pm.request.body.raw;
if (!raw) return;
var reqUrl = pm.variables.replaceIn(pm.request.url.toString());
var bridgeBase = pm.variables.replaceIn('{{bridge_base_url}}');
if (reqUrl.indexOf(bridgeBase) !== 0) return; // sign only Bridge Partner API calls

function canonical(o) {
  if (Array.isArray(o)) return '[' + o.map(canonical).join(',') + ']';
  if (o && typeof o === 'object') {
    return '{' + Object.keys(o).sort().map(function (k) {
      return JSON.stringify(k) + ':' + canonical(o[k]);
    }).join(',') + '}';
  }
  return JSON.stringify(o);
}

function doSign() {
  var b64u = function (s) { return hextob64u(rstrtohex(s)); };
  var body = JSON.parse(pm.variables.replaceIn(raw));
  var key = KEYUTIL.getKey(pm.variables.get('signing_private_pem'));
  var header = { alg: 'RS256', kid: pm.variables.get('signing_kid') };
  var p1 = b64u(JSON.stringify(header));
  var p2 = b64u(canonical(body));
  var sig = new KJUR.crypto.Signature({ alg: 'SHA256withRSA' });
  sig.init(key); sig.updateString(p1 + '.' + p2);
  var p3 = hextob64u(sig.sign());
  pm.request.headers.upsert({ key: 'Signature', value: p1 + '..' + p3 });
}

var cached = pm.collectionVariables.get('_jsrsasign_src');
if (cached) { eval(cached); doSign(); return; }
return new Promise(function (resolve) {
  pm.sendRequest(pm.variables.get('jsrsasign_url'), function (err, res) {
    if (err || !res) { console.log('jsrsasign load failed; sending unsigned:', err); return resolve(); }
    var src = res.text();
    pm.collectionVariables.set('_jsrsasign_src', src);
    try { eval(src); doSign(); } catch (e) { console.log('signing error:', e); }
    resolve();
  });
});
"""


# =========================================================================== #
# Folder 1 — Health checks
# =========================================================================== #
F1 = {
    "name": "1 · Health checks",
    "description": (
        "Confirm the three services are reachable and the treasury (sponsor) "
        "account is funded. Run this once, first.\n\n"
        "Update the three base URLs in the environment to match YOUR namespace "
        "before running."
    ),
    "item": [
        item(
            "Bridge — ping",
            "GET",
            "{{bridge_base_url}}/ping",
            test="""
pm.test('Bridge reachable (HTTP 200)', () => pm.response.code === 200);
console.log('Bridge ping: ' + pm.response.code);
""",
        ),
        item(
            "Example Bank — ping",
            "GET",
            "{{example_bank_base_url}}/ping",
            test="""
pm.test('Example Bank reachable (HTTP 200)', () => pm.response.code === 200);
console.log('Example Bank ping: ' + pm.response.code);
""",
        ),
        item(
            "Example Bank — treasury is funded",
            "POST",
            "{{example_bank_base_url}}/check_funds",
            body="""
{
  "account_number": "{{treasury_account}}",
  "account_currency": "{{currency}}",
  "total_funds_needed": {{total_amount}}
}""",
            test="""
pm.test('check_funds returned 200', () => pm.response.code === 200);
const j = pm.response.json() || {};
pm.test('Treasury has enough for the whole batch', () => j.has_sufficient_funds === true);
console.log('Treasury ' + pm.environment.get('treasury_account') +
            ' sufficient for ' + pm.environment.get('total_amount') +
            '? -> ' + j.has_sufficient_funds);
""",
            desc="The sponsor/treasury account must hold at least total_amount or "
            "the funds-check stage will never pass.",
        ),
    ],
}


# =========================================================================== #
# Folder 2 — Create the disbursement envelope (run once)
# =========================================================================== #
ENV_PRE = """
// Start a fresh campaign: new run id, batch-control id, empty id list.
const stamp = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14);
const run = (pm.environment.get('run_prefix') || 'TRAINING') + '_' + stamp;
pm.collectionVariables.set('run_id', run);
pm.collectionVariables.set('batch_control_id', run + '_BCTL');
pm.collectionVariables.set('created_disbursement_ids', '[]');
pm.collectionVariables.set('disbursements_accum', '[]');
// Short, MT940-safe token for disbursement ids. The Example Bank writes the
// disbursement_id into the MT940 :61: reference (max 16 chars), so ids must be
// short or reconciliation fails to parse. 'D' + 8 hex + 2-digit index <= 16.
pm.collectionVariables.set('run_token',
  (Date.now() % 0x100000000).toString(16).padStart(8, '0'));
// Default the schedule date to today if the implementer left it blank.
if (!pm.environment.get('schedule_date')) {
  pm.environment.set('schedule_date', new Date().toISOString().slice(0, 10));
}
console.log('Campaign run_id = ' + run + ' | schedule_date = ' +
            pm.environment.get('schedule_date'));
"""

ENV_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": [
      {
        "benefit_program_id": {{program_id}},
        "benefit_program_mnemonic": "{{program_mnemonic}}",
        "benefit_program_description": "API walkthrough training program",
        "target_registry": "{{target_registry}}",
        "benefit_code_id": {{benefit_code_id}},
        "benefit_code_mnemonic": "{{benefit_code_mnemonic}}",
        "benefit_code_description": "Digital cash training",
        "benefit_type": "CASH_DIGITAL",
        "disbursement_cycle_id": {{cycle_id}},
        "disbursement_frequency": "{{frequency}}",
        "cycle_code_mnemonic": "{{program_mnemonic}}_CYCLE",
        "number_of_beneficiaries": {{num_disbursements}},
        "number_of_disbursements": {{num_disbursements}},
        "total_disbursement_quantity": {{total_amount}},
        "measurement_unit": "{{currency}}",
        "disbursement_schedule_date": "{{schedule_date}}"
      }
    ]
  }
}"""
)

ENV_TEST = """
pm.test('Envelope accepted (HTTP 200)', () => pm.response.code === 200);
const j = pm.response.json() || {};
const st = j.response_header && j.response_header.response_status;
pm.test('response_status SUCCESS', () => st === 'SUCCESS');
const p = j.response_body && j.response_body.response_payload;
const eid = Array.isArray(p) && p.length ? p[0].id : null;
pm.test('envelope id returned', () => !!eid);
pm.collectionVariables.set('envelope_id', eid || '');
console.log('envelope_id = ' + eid + '  | declared ' +
            pm.environment.get('num_disbursements') + ' disbursements, total ' +
            pm.environment.get('total_amount'));
"""

F2 = {
    "name": "2 · Create disbursement envelope",
    "description": (
        "Creates ONE CASH_DIGITAL envelope. Run once (do not use a data file).\n\n"
        "IMPORTANT: `num_disbursements` and `total_amount` in the environment "
        "must match your CSV exactly — the row count, and the sum of the "
        "`amount` column. The pipeline only advances once it has received "
        "exactly that many disbursements for exactly that total. The shipped "
        "CSV is 25 rows x 1000 = 25000."
    ),
    "item": [
        item(
            "Create envelope (CASH_DIGITAL)",
            "POST",
            "{{bridge_base_url}}/create_disbursement_envelopes",
            body=ENV_BODY,
            pre=ENV_PRE,
            test=ENV_TEST,
        )
    ],
}


# =========================================================================== #
# Folder 3 — Seed SPAR + create disbursements (DATA-DRIVEN with the CSV)
# =========================================================================== #
LINK_PRE = """
// Build the SPAR link_request from the current CSV row. For the
// 'missing_from_spar' scenario we send an EMPTY array, so the beneficiary is
// deliberately left unmapped (this is the 'ID missing from SPAR' case).
const sc = (pm.iterationData.get('scenario') || 'happy');
const bid = pm.iterationData.get('beneficiary_id');
const sid = Number(pm.environment.get('spar_strategy_id'));
let arr = [];
if (sc !== 'missing_from_spar') {
  arr = [{
    reference_id: pm.variables.replaceIn('{{run_id}}') + '_REF_' + bid,
    timestamp: new Date().toISOString(),
    id: bid,
    fa: {
      strategy_id: sid,
      fa_type: 'BANK',
      bank_name: (pm.iterationData.get('bank_code') || '') + ' Bank',
      bank_code: pm.iterationData.get('bank_code'),
      branch_name: 'Branch ' + (pm.iterationData.get('branch_code') || ''),
      branch_code: pm.iterationData.get('branch_code'),
      account_number: pm.iterationData.get('account_number')
    },
    name: pm.iterationData.get('beneficiary_name'),
    additional_info: [{ strategy_id: sid }],
    locale: 'en'
  }];
}
pm.variables.set('link_request_json', JSON.stringify(arr));
"""

LINK_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": {
      "transaction_id": "{{run_id}}_LNK_{{beneficiary_id}}",
      "link_request": {{link_request_json}}
    }
  }
}"""
)

LINK_TEST = """
// 1) Report the link outcome for this row.
const sc = (pm.iterationData.get('scenario') || 'happy');
const bid = pm.iterationData.get('beneficiary_id');
if (sc === 'missing_from_spar') {
  console.log('-> ' + bid + ': intentionally NOT linked (simulating beneficiary missing from SPAR)');
  pm.test(bid + ' left unmapped (missing_from_spar)', () => true);
} else {
  pm.test('SPAR link accepted (HTTP 200)', () => pm.response.code === 200);
  const j = pm.response.json() || {};
  const st = j.response_header && j.response_header.response_status;
  pm.test('SPAR response_status SUCCESS', () => st === 'SUCCESS');
  console.log('linked ' + bid + ' @ ' + pm.iterationData.get('bank_code'));
}
// 2) Accumulate THIS beneficiary's disbursement into the batch we will create
//    in step 4 (one create_disbursements call for the whole batch — that is how
//    the API is designed to be used). Done for EVERY row, including the unmapped
//    ones (they are still part of the batch; FA resolution will just skip them).
// Short id ('D' + 8-hex token + 2-digit row index) so it fits the MT940 :61:
// reference field (max 16 chars) and reconciliation can parse it.
const idx = String((pm.info.iteration || 0) + 1).padStart(2, '0');
const disbId = 'D' + pm.variables.replaceIn('{{run_token}}') + idx;
let arr = [], ids = [];
try { arr = JSON.parse(pm.collectionVariables.get('disbursements_accum') || '[]'); } catch (e) {}
try { ids = JSON.parse(pm.collectionVariables.get('created_disbursement_ids') || '[]'); } catch (e) {}
arr.push({
  disbursement_id: disbId,
  disbursement_envelope_id: pm.collectionVariables.get('envelope_id'),
  beneficiary_id: bid,
  beneficiary_name: pm.iterationData.get('beneficiary_name'),
  disbursement_quantity: Number(pm.iterationData.get('amount')),
  disbursement_cycle_id: Number(pm.environment.get('cycle_id')),
  narrative: 'Training disbursement for ' + disbId
});
ids.push(disbId);
pm.collectionVariables.set('disbursements_accum', JSON.stringify(arr));
pm.collectionVariables.set('created_disbursement_ids', JSON.stringify(ids));
"""

F3 = {
    "name": "3 · Link beneficiaries in SPAR (build the batch)",
    "description": (
        "DATA-DRIVEN. In the Collection Runner, select THIS folder, choose "
        "`beneficiaries.csv` as the data file, then Run. It iterates once per "
        "row: link the beneficiary in SPAR (rows marked `missing_from_spar` are "
        "left unmapped on purpose) and adds that beneficiary's disbursement to "
        "the batch.\n\n"
        "It does NOT create the disbursements yet — step 4 sends the whole batch "
        "in one call (the way a real integrator does)."
    ),
    "item": [
        item(
            "SPAR — link beneficiary (+ add to batch)",
            "POST",
            "{{spar_base_url}}/link",
            body=LINK_BODY,
            pre=LINK_PRE,
            test=LINK_TEST,
        ),
    ],
}


# =========================================================================== #
# Folder 4 — Create disbursements: ONE batch call (run once)
# =========================================================================== #
CREATE_BATCH_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "disbursement_batch_control_id": "{{batch_control_id}}",
    "request_payload": {{disbursements_accum}}
  }
}"""
)

CREATE_BATCH_TEST = """
pm.test('Batch accepted (HTTP 200)', () => pm.response.code === 200);
const j = pm.response.json() || {};
const st = j.response_header && j.response_header.response_status;
pm.test('response_status SUCCESS', () => st === 'SUCCESS');
let n = 0;
try { n = JSON.parse(pm.collectionVariables.get('disbursements_accum') || '[]').length; } catch (e) {}
console.log('created ' + n + ' disbursements in ONE batch | batch_control_id = ' +
            pm.collectionVariables.get('batch_control_id'));
if (st !== 'SUCCESS') {
  console.log('Response: ' + JSON.stringify(j).slice(0, 300));
}
"""

F4_CREATE = {
    "name": "4 · Create disbursements (one batch)",
    "description": (
        "Run ONCE, after step 3 (no data file). Sends every beneficiary's "
        "disbursement from step 3 in a SINGLE `create_disbursements` call, under "
        "one batch-control id. The Bridge creates one batch-control row per call, "
        "so the whole batch must go together (not one call per beneficiary).\n\n"
        "After this, the asynchronous pipeline starts — watch it in step 5."
    ),
    "item": [
        item(
            "Create disbursements (whole batch)",
            "POST",
            "{{bridge_base_url}}/create_disbursements",
            body=CREATE_BATCH_BODY,
            test=CREATE_BATCH_TEST,
        ),
    ],
}


# =========================================================================== #
# Folder 5 — Observe the pipeline (run manually, RE-RUN as stages advance)
# =========================================================================== #
ENVELOPE_ID_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": "{{envelope_id}}"
  }
}"""
)

# get_disbursement_batch_control keys on the BATCH-CONTROL id (not the envelope id).
BATCH_ID_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": "{{batch_control_id}}"
  }
}"""
)

BATCH_TEST = """
pm.test('batch control fetched (HTTP 200)', () => pm.response.code === 200);
const j = pm.response.json() || {};
const p = j.response_body && j.response_body.response_payload;
if (p) {
  console.log('FA resolution     : ' + p.fa_resolution_status);
  console.log('Sponsor dispatch  : ' + p.sponsor_bank_dispatch_status);
}
"""

ENVSTATUS_TEST = """
pm.test('envelope status fetched (HTTP 200)', () => pm.response.code === 200);
const j = pm.response.json() || {};
const p = j.response_body && j.response_body.response_payload;
if (p) {
  console.log('disbursements received : ' + p.number_of_disbursements_received +
              ' / ' + pm.environment.get('num_disbursements'));
  console.log('funds available w/bank : ' + p.funds_available_with_bank);
  console.log('funds blocked  w/bank  : ' + p.funds_blocked_with_bank);
}
"""

DISBSTATUS_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": {{created_disbursement_ids}}
  }
}"""
)

DISBSTATUS_TEST = """
pm.test('disbursement status fetched (HTTP 200)', () => pm.response.code === 200);
const j = pm.response.json() || {};
const p = j.response_body && j.response_body.response_payload;
if (Array.isArray(p)) {
  // disbursement_recon_records is ALWAYS an object with two arrays; a
  // disbursement is reconciled when one of them is non-empty.
  let ok = 0, err = 0, none = 0;
  p.forEach(d => {
    const r = d.disbursement_recon_records || {};
    const a = (r.disbursement_recon_payloads || []).length;
    const e = (r.disbursement_error_recon_payloads || []).length;
    if (a) ok++; else if (e) err++; else none++;
  });
  console.log('Disbursements: ' + p.length + ' | reconciled OK: ' + ok +
              ' | reconciled ERROR (reversals): ' + err +
              ' | no recon yet / never: ' + none);
  console.log('(Re-run every ~15-30s as the async pipeline advances. End state: ' +
              '~20 OK, up to 2 ERROR (bad_account), 3 with no recon (missing_from_spar).)');
}
"""

CHECK_CREDITED_BODY = """
{
  "account_number": "{{sample_happy_account}}",
  "account_currency": "{{currency}}",
  "total_funds_needed": 1
}"""

CHECK_CREDITED_TEST = """
pm.test('check_funds returned 200', () => pm.response.code === 200);
const j = pm.response.json() || {};
console.log('Successful beneficiary ' + pm.environment.get('sample_happy_account') +
            ' credited? -> ' + (j.has_sufficient_funds === true));
"""

CHECK_FAILED_BODY = """
{
  "account_number": "{{sample_bad_account}}",
  "account_currency": "{{currency}}",
  "total_funds_needed": 1
}"""

CHECK_FAILED_TEST = """
pm.test('check_funds returned a response', () => pm.response.code === 200 || pm.response.code >= 400);
let credited = false;
try { credited = (pm.response.json() || {}).has_sufficient_funds === true; } catch (e) {}
console.log('Bad-account beneficiary ' + pm.environment.get('sample_bad_account') +
            ' credited in their OWN account? -> ' + credited +
            '  (expected false: a foreign-bank payment is routed to a clearing account)');
"""

F5_OBSERVE = {
    "name": "5 · Observe the pipeline (re-run me)",
    "description": (
        "Run these manually AFTER step 4, and RE-RUN them every ~15-30 seconds. "
        "The disbursement pipeline is asynchronous (background workers), so the "
        "statuses advance over time. Watch the order:\n\n"
        "  FA resolution -> funds available -> funds blocked -> sponsor "
        "dispatch -> beneficiaries credited -> reconciled.\n\n"
        "Expect ~20 reconciled OK (happy), up to 2 reconciled ERROR / not "
        "credited to their own account (bad_account / foreign bank), 3 never "
        "disbursed (missing_from_spar)."
    ),
    "item": [
        item(
            "Batch control status (FA + dispatch)",
            "POST",
            "{{bridge_base_url}}/get_disbursement_batch_control",
            body=BATCH_ID_BODY,
            test=BATCH_TEST,
        ),
        item(
            "Envelope status (funds)",
            "POST",
            "{{bridge_base_url}}/get_disbursement_envelope_status",
            body=ENVELOPE_ID_BODY,
            test=ENVSTATUS_TEST,
        ),
        item(
            "Disbursement status (reconciliation)",
            "POST",
            "{{bridge_base_url}}/get_disbursement_status",
            body=DISBSTATUS_BODY,
            test=DISBSTATUS_TEST,
        ),
        item(
            "Did a SUCCESSFUL beneficiary get credited?",
            "POST",
            "{{example_bank_base_url}}/check_funds",
            body=CHECK_CREDITED_BODY,
            test=CHECK_CREDITED_TEST,
        ),
        item(
            "Did a BAD-ACCOUNT beneficiary get credited?",
            "POST",
            "{{example_bank_base_url}}/check_funds",
            body=CHECK_FAILED_BODY,
            test=CHECK_FAILED_TEST,
        ),
    ],
}


# =========================================================================== #
# Folder 5 — Cleanup: unlink SPAR (DATA-DRIVEN with the CSV)
# =========================================================================== #
UNLINK_BODY = (
    "{\n"
    + HEADER
    + """,
  "request_body": {
    "pagination_request": null,
    "request_payload": {
      "transaction_id": "{{run_id}}_ULK_{{beneficiary_id}}",
      "unlink_request": [
        {
          "reference_id": "{{run_id}}_UREF_{{beneficiary_id}}",
          "timestamp": "{{$isoTimestamp}}",
          "id": "{{beneficiary_id}}"
        }
      ]
    }
  }
}"""
)

UNLINK_TEST = """
// Tolerant: unlinking a never-linked id (missing_from_spar) is a harmless no-op.
pm.test('unlink call completed', () => pm.response.code === 200 || pm.response.code >= 400);
console.log('unlink ' + pm.iterationData.get('beneficiary_id') + ' -> ' + pm.response.code);
"""

F6_CLEANUP = {
    "name": "6 · Cleanup — unlink SPAR",
    "description": (
        "DATA-DRIVEN. Select this folder + `beneficiaries.csv` and Run to "
        "remove the ID->FA links created in step 3. Disbursement data in the "
        "Bridge is left in place (it is namespaced by run_id and visible in the "
        "dashboards). Re-running the whole walkthrough creates a fresh run_id."
    ),
    "item": [
        item(
            "SPAR — unlink beneficiary",
            "POST",
            "{{spar_base_url}}/unlink",
            body=UNLINK_BODY,
            test=UNLINK_TEST,
        )
    ],
}


# --------------------------------------------------------------------------- #
# Collection + environment assembly.
# --------------------------------------------------------------------------- #
COLLECTION = {
    "event": [_event("prerequest", SIGN_PREREQUEST)],
    "info": {
        "name": "G2P Bridge - API Walkthrough",
        "description": (
            "A guided, manual walkthrough of the G2P Bridge disbursement APIs "
            "(digital cash), for implementers who have installed G2P Bridge + "
            "SPAR + the Example Bank. Seed data comes from `beneficiaries.csv` "
            "(edit it; change the schedule date / amounts as you like).\n\n"
            "Partner API requests are SIGNED by default (detached JWS in the "
            "`Signature` header) with the committed TEST-ONLY key, matching the "
            "trial Bridge's local crypto backend. Set `sign_requests=false` in the "
            "environment to target an unsigned Bridge.\n\n"
            "Run the six folders in order. Folders 3 and 6 are DATA-DRIVEN: run "
            "them from the Collection Runner with `beneficiaries.csv` as the "
            "data file. Folder 5 is meant to be RE-RUN repeatedly while the "
            "asynchronous pipeline advances.\n\n"
            "Full instructions: GitBook -> Developer Zone -> API Walkthrough."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [F1, F2, F3, F4_CREATE, F5_OBSERVE, F6_CLEANUP],
    "variable": [
        {"key": "run_id", "value": ""},
        {"key": "run_token", "value": ""},
        {"key": "batch_control_id", "value": ""},
        {"key": "envelope_id", "value": ""},
        {"key": "created_disbursement_ids", "value": "[]"},
        {"key": "disbursements_accum", "value": "[]"},
        # Set per-request by the signing pre-request; cached jsrsasign source.
        {"key": "request_id", "value": ""},
        {"key": "request_timestamp", "value": ""},
        {"key": "_jsrsasign_src", "value": ""},
    ],
}

# Environment defaults target the `trial` namespace so it works out-of-the-box
# there; implementers change the namespace in the three URLs for their own setup.
ENV_VARS = [
    ("bridge_base_url", "https://g2p-bridge.trial.openg2p.org/api/g2p-bridge"),
    ("spar_base_url", "https://spar.trial.openg2p.org/api/mapper/mapper"),
    (
        "example_bank_base_url",
        "https://example-bank.trial.openg2p.org/api/example-bank",
    ),
    ("sender_app", "TRAINING"),
    ("sender_app_url", "http://training.local"),
    # --- Request signing (TEST/DEMO; the trial Bridge enforces signature validation) ---
    # Sign Partner API requests with the committed TEST-ONLY key — the PEM exported
    # from test/keys/test-partner.p12 (jsrsasign can't read a .p12), whose cert is
    # seeded as PARTNER_TRAINING. kid = the cert's SHA-256 thumbprint. Set
    # sign_requests=false when targeting a Bridge with validation off. NEVER a
    # production key.
    ("sign_requests", "true"),
    ("signing_kid", "A6jg8w5H9fuRJYKDJM6RojY6NeNzLmsdihJlknn8wj4"),
    (
        "signing_private_pem",
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDgn8teEibr2C0F\n"
        "6G3xqVxDX0PM+CZLA4f9HzzdPrzzVD9XiIYBypsTWUrVXA7VZM/b4BaCXB3veDvE\n"
        "MO2plZ87N4AfkH9WWADi8upayY7Sl1d/sEseSGvKrMw5F26tXnnbgRQ0VGJCYhoA\n"
        "5jPHiPCqAyhwIhQ9nzeP9337QoGLchMnwx8IDdAS5jf5cDJj9RunGw95mCusrpwb\n"
        "ucjbbrIknXt5QARYE0StevBhk8+YYvHaUM2LzjBtmDpgMEE2JSpeqgs9T/Q4juQQ\n"
        "a/g1q0pQksa3MA7t/T11DVH2JUwWSpk9UywkLN9RE0CpJA9Z8auJk4fZz+Jpk9pj\n"
        "Nw3JtL/PAgMBAAECggEAFhN+YEN2cc1wN1ltnMehWrm9JyLoWI0DS3xLdg8ZcOzB\n"
        "wO+ZBAoOjatD8I44ov5ic2CltbAp/QQbE6Afa4BaAu7kd7Wy3iCODcAECmIu2EGp\n"
        "htIjv9ksRuIOvDmyVfWoEkuwWahFc/LCTX5SbnTl+j+PNN4UkS3Zvxt61TvnEXY4\n"
        "il5OteKybZAv+dLBx7utvBiUExQzL2rzCo6jHkJqvZxlfvcvg++jctv6Ja5h8cZp\n"
        "iw5z9wae/NN0qcUXuRP3EG44LaQ40he5S59AkpCPUhSlAtKccwAzo/GAR+ZGQWrR\n"
        "vftWxcFJgdQKyeRfNYXsTWcpLAdDfaUzwrswcwKGIQKBgQDyJ6kr0bLYwiKpSgL4\n"
        "o54SM9k73NepiZMUFGr19mjtsYCxTOnaZlxozpBYwzOnpCKh0h+4p7E0kkWqX2w+\n"
        "ncBPgwpGcwAASQ8erooXwliRAO3G1NxLf9gQhHpg2JvgKzV+QY2DNwV/ktLBvyiz\n"
        "uVKr1A1SVr9KlprG78j083d9PwKBgQDtd4rS5EPSYbXxaZCdX58JdYzHlUTZl5iN\n"
        "VZRPx1noiZAqlMKmTXrygX9wPpuhSl2DSO/l+PTM+qn7n+BKDPrE0r/mBd/umN9N\n"
        "sfy8paze9trPp4TgvO83MDNikpCb+5LkqNH9nrvaMbDAfxmjzyhdp3nJHmmFyIg5\n"
        "A09yN2DJcQKBgF5puDutdt2sU3dNs/rdUDQoovoEENG5Ie8iRtG/UQnbuyFlq4fL\n"
        "gRwb7YuuD+W8yQPuuQ910lF89kyHB90iBGj73nW5QLbbxVlhE9ZPn9hpVEvBkmKd\n"
        "ZdCK1mwMCDpOnnyrclFGko464JFJxsTL7L+x3b/MsqiSL6aAtwlKI7xhAoGBAKrv\n"
        "HP/3jhZ3fWd8bLvLpAhEFIVqHnhe1lIOY0cWIdLwitUL5h2dsj20F87tUkvE4xFo\n"
        "xD8PeO/AE/HrwKCtPSnG5pmmau4uHrenwlztCUYp/ZHybQT1G2DnkmWHSQ7vBWsR\n"
        "Vq8wvtouYKQAGa2/pbfcoR6zhJPnqJ8ZkeuOj14RAoGBAJ4A63DHsAyQ33d3rB+y\n"
        "VSHd9jukBMpglAAT8OTKTu3rlFugoYinr0sfNh9y5O8jmxAR6+qlmvsEgx8UXbtJ\n"
        "aJHqCQ8F6cL2nw4pXzxh+JHt1VvYut9xdIWSnfRZKTgzsx/UGZrIm9vHNUE9bNKt\n"
        "pKkB3Gzh6oyYjSifI7gp4tzY\n"
        "-----END PRIVATE KEY-----\n",
    ),
    ("jsrsasign_url", "https://cdnjs.cloudflare.com/ajax/libs/jsrsasign/11.1.0/jsrsasign-all-min.js"),
    ("spar_strategy_id", "5"),
    ("treasury_account", "SPONSOR0001"),
    ("currency", "USD"),
    ("program_id", "990001"),
    ("benefit_code_id", "990002"),
    ("cycle_id", "1"),
    ("frequency", "Monthly"),
    ("program_mnemonic", "TRAINING"),
    ("benefit_code_mnemonic", "TRAINING_CASH"),
    ("target_registry", "TRAINING"),
    ("run_prefix", "TRAINING"),
    ("num_disbursements", "25"),
    ("total_amount", "25000"),
    ("schedule_date", ""),
    ("sample_happy_account", "ACC1000001"),
    ("sample_bad_account", "ACC1000024"),
]

ENVIRONMENT = {
    "name": "G2P Bridge - Walkthrough (edit namespace)",
    "values": [
        {"key": k, "value": v, "type": "default", "enabled": True} for k, v in ENV_VARS
    ],
    "_postman_variable_scope": "environment",
}


def write_json(name: str, obj: dict) -> None:
    path = HERE / name
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    print(f"{name}: {path.stat().st_size} bytes")


def main() -> None:
    write_csv()
    write_json("G2P-Bridge-API-Walkthrough.postman_collection.json", COLLECTION)
    write_json("G2P-Bridge.postman_environment.json", ENVIRONMENT)


if __name__ == "__main__":
    main()
