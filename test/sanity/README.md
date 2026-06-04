# G2P Bridge — Regression Sanity Suite

A Python (pytest) suite that checks the **sanity of an already-installed** G2P
Bridge by pointing at its live URLs. It verifies every API and the full
digital-cash end-to-end flow. It creates only clearly-marked, self-cleaning test
data, so it is safe to run against a fresh **or** an in-use environment.

> **Phase 1** — point-and-run against a deployed system. CI/CD automation
> (GitHub workflow, auto-deploy, emailed reports) is intentionally a later phase.

## What it tests

| Level | Marker | What | Side effects |
| --- | --- | --- | --- |
| **L0** | `smoke` | `/ping` of every service, treasury seeded, SPAR reachable | none |
| **L1** | `contract` | **Every** Partner / Bene-Portal / Example-Bank endpoint responds for basic input | none |
| **L2** | `e2e` | Full cash lifecycle, **verified stage by stage** (see below) | creates `TEST_SANITY_*` data; SPAR links auto-unlinked |

### Endpoint coverage (L0/L1)

| System | Endpoints covered |
| --- | --- |
| Partner API | `ping`, `create_disbursement_envelopes`, `cancel_disbursement_envelope`, `amend_disbursement_envelope`†, `create_disbursements`†, `cancel_disbursements`†, `get_disbursement_status`, `get_disbursement_envelope_status`, `get_disbursement_batch_control`, `upload_mt940` |
| Bene-Portal | `ping`, `disbursement/get_all_disbursements`, `disbursement/get_disbursement_summary_till_date` |
| Example Bank | `ping`, `check_funds`, `block_funds`, `generate_account_statement`†, `initiate_payment`, `ussd` |

† Marked `xfail` — these currently return HTTP 500 `Unknown Error` on not-found/invalid
input instead of a graceful response (a Bridge/Example-Bank robustness gap). They are
called and tracked; they'll auto-pass once the services handle those inputs gracefully.

### End-to-end stage verification (L2)

A batch of disbursements is pushed through the whole chain and **each stage is asserted
independently**, so a failure pinpoints exactly where it stalled:

| Stage | Verified via |
| --- | --- |
| 1. Envelope + disbursements created | partner response `SUCCESS` |
| 2. FA resolved (Bridge ↔ SPAR) | `get_disbursement_batch_control` → `fa_resolution_status == PROCESSED` |
| 3. Funds checked with bank | `get_disbursement_envelope_status` → `funds_available_with_bank == FUNDS_AVAILABLE` |
| 4. Funds blocked with bank | envelope status → `funds_blocked_with_bank == FUNDS_BLOCK_SUCCESS` |
| 5. Disbursed to bank | batch control → `sponsor_bank_dispatch_status == PROCESSED` |
| 6. **Bank distributes to beneficiaries** | Example Bank `check_funds(<beneficiary acct>)` → credited |
| 7. Reconciled (MT940 → Bridge) | `get_disbursement_status` → `disbursement_recon_records` populated |

## Relationship to the unit tests (`core/.../tests/`)

This suite is **complementary** to the in-repo unit tests (e.g.
`core/partner-api/tests/`). Those are white-box tests that import the controllers and
mock the services/DB — fast, hermetic, run in CI on every commit to catch code-logic
regressions. This sanity suite is **black-box** against a **deployed** system (real
network, DB, Celery, SPAR, bank) to catch integration/deployment regressions. Keep both:
they catch different classes of bug.

## Test-data convention

Everything the suite creates is namespaced under a single prefix (default
`TEST_SANITY`) plus a per-run token, e.g. `TEST_SANITY_20260604T1015_a1b2c3`.

* The disbursement **program/benefit mnemonic is `TEST_SANITY`** — exclude test
  data from operational reports with a single filter: `benefit_program_mnemonic
  LIKE 'TEST_%'`.
* The **same beneficiary IDs** are used in both SPAR (`/link`) and the Bridge
  disbursement, so ID↔FA consistency is guaranteed by construction.
* SPAR links are unlinked at session end. Bridge disbursement rows persist (no
  delete API) but are invisible to reports by the filter above.

## Where the seed data lives

All editable sample/seed data lives in **`config.yaml`** — **not** in the test
scripts. The scripts only consume it:

* **Static seed** (treasury account, currency, beneficiary bank code/branch, SPAR
  strategy id, batch size & amount, and the sample batch template —
  `benefit_program_id`, `benefit_code_id`, `disbursement_frequency`) → `config.yaml`.
* **Run-scoped identifiers** (beneficiary IDs, disbursement IDs, account numbers,
  request IDs) are **generated per run** in `sanity/naming.py` (prefix + run token)
  — they're intentionally not static, so runs never collide.

To change what a run disburses, edit `config.yaml`; you should not need to touch
the Python.

## Results

Every run writes results to disk automatically (unless you pass your own
`--html`/`--junitxml`):

```
results/<test_prefix>_<UTC-timestamp>/
  ├── report.html     # self-contained human report
  └── junit.xml       # machine-readable (CI)
```

The output directory is printed at the end of the run. Toggle with
`write_results` / `results_dir` in `config.yaml`. (`results/` is gitignored.)

## Setup

```bash
cd test/sanity
python3 -m venv venv && source venv/bin/activate
pip install -e .            # or: pip install pytest pytest-html httpx pyyaml
cp config.example.yaml config.yaml   # then edit to point at your system
```

## Configure

Edit `config.yaml` (or override any value with `SANITY_<UPPER_SNAKE>` env vars).
The most important values:

| Value | Meaning |
| --- | --- |
| `namespace` | Environment segment; all default URLs derive from it. |
| `*_base_url` | Override individual service URLs if non-standard. |
| `verify_tls` | `false` for self-signed dev certs. |
| `treasury_account_number` / `treasury_currency` | Must match the chart's `sponsorBankConfigurations`. |
| `beneficiary_bank_code` | Use the Example Bank's simulator code (`EXAMPLE`) for a deterministic happy path. |
| `spar_bank_strategy_id` | **Environment-dependent** — the id of SPAR's BANK construct/deconstruct strategy. Required for e2e seeding. |
| `run_e2e` | `false` to run only L0/L1 (zero data created). |
| `keymanager_auth_enabled` | Keep `false` (sanity profile). If your system enforces inbound auth, the write tests skip. |

## Run

```bash
# Everything, with an HTML report:
pytest --html=report.html --self-contained-html

# Only smoke + contract (no data created):
pytest -m "smoke or contract"

# Only the end-to-end flow:
pytest -m e2e

# Point at another environment on the fly:
SANITY_NAMESPACE=qa SANITY_VERIFY_TLS=false pytest -m smoke
```

Reports: `--html=report.html` (human) and `--junitxml=report.xml` (CI-friendly).

## Teardown (manual fallback)

SPAR links are unlinked automatically at the end of each run. If a run crashed
and left links behind, each run writes a manifest under `.sanity-runs/`; clean
them up manually with the standalone script:

```bash
python teardown.py --list                # show pending run manifests
python teardown.py --all --dry-run       # preview
python teardown.py --all                 # unlink everything pending
python teardown.py --run-id TEST_SANITY_20260604T1015_a1b2c3   # one run
```

## Notes / first-run tuning

* The e2e depends on SPAR having a **BANK strategy** configured; set
  `spar_bank_strategy_id` accordingly. If seeding fails, `test_spar_seeding_succeeded`
  reports it clearly and the recon assertion explains where it stalled.
* Pipeline/reconciliation timeouts (`e2e_pipeline_timeout_seconds`,
  `e2e_recon_timeout_seconds`) are generous defaults; tune to your celery
  frequencies after observing the first real run.
