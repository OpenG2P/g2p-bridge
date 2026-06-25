"""Configuration loading for the sanity suite.

Precedence (highest first): environment variables (SANITY_<UPPER_SNAKE>) >
config.yaml (or $SANITY_CONFIG) > built-in defaults derived from namespace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_BASE_DOMAIN = "openg2p.org"

# Committed TEST-ONLY private key used to sign Partner API requests when the
# target Bridge enforces signature validation (the trial default). Resolves to
# <repo>/test/keys/test-partner.key.json for a local run; overridden in-cluster
# via SANITY_SIGNING_KEY_PATH (the chart mounts it from a Secret).
_DEFAULT_SIGNING_KEY = str(Path(__file__).resolve().parents[2] / "keys" / "test-partner.key.json")


@dataclass
class Config:
    namespace: str = "trial"
    base_domain: str = _DEFAULT_BASE_DOMAIN

    bridge_base_url: str = ""
    bene_portal_base_url: str = ""
    example_bank_base_url: str = ""
    spar_mapper_base_url: str = ""

    verify_tls: bool = True
    request_timeout_seconds: int = 30

    test_prefix: str = "TEST_SANITY"

    treasury_account_number: str = "SPONSOR0001"
    treasury_currency: str = "USD"
    treasury_opening_balance: float = 10000000

    beneficiary_bank_code: str = "EXAMPLE-BANK"
    beneficiary_bank_name: str = "Example Bank"
    beneficiary_branch_code: str = "0001"
    beneficiary_branch_name: str = "Main"
    # SPAR's configured BANK strategy id. Must point at a strategy whose construct
    # format matches the Bridge's BANK_FA_DECONSTRUCT strategy — see the SPAR
    # chart seedData.strategies, id 5 'Bank (G2P Bridge)'.
    spar_bank_strategy_id: int = 5

    run_e2e: bool = True
    e2e_num_beneficiaries: int = 2
    e2e_amount_per_beneficiary: float = 1000
    e2e_pipeline_timeout_seconds: int = 600
    # Per-stage budget for stages 2-6. Each async stage gets its OWN timeout, so a
    # slow early stage can't starve the tail stages and a hang fails the exact
    # stage that's stuck (instead of cascading). Sized generously for low beat
    # frequencies; the overall run is still bounded by the per-stage timeouts.
    e2e_stage_timeout_seconds: int = 120
    e2e_poll_interval_seconds: int = 10
    e2e_recon_timeout_seconds: int = 900

    # --- sample disbursement batch (the e2e "seed"; edit here, not in code) ---
    # Mnemonics / cycle / target-registry are derived from test_prefix; these are
    # the remaining template fields a CASH_DIGITAL envelope needs.
    benefit_program_id: int = 999001
    benefit_code_id: int = 999002
    disbursement_cycle_id: int = 1
    disbursement_frequency: str = "Monthly"

    # Partner API request signing. On by default so the suite works against a
    # Bridge that enforces signature validation (the trial profile). Set
    # sign_requests=false only when targeting a Bridge with validation off.
    sign_requests: bool = True
    signing_key_path: str = _DEFAULT_SIGNING_KEY
    signing_key_kid: str = "test-partner-2026"
    signing_algorithm: str = "ES256"

    # Bene-Portal API tests. Disabled for now — the bene-portal enforces OIDC auth
    # and the suite does not yet authenticate (calls return 401). Enable once the
    # suite obtains an access token.
    bene_portal_enabled: bool = False

    # Auto-unlink SPAR ID->FA links at session end. Set false to LEAVE the test
    # data in place for inspecting traces (the run manifest is still written, so
    # `python teardown.py --all` can clean it up later).
    cleanup_on_teardown: bool = True

    # --- results output ---
    write_results: bool = True  # write HTML + JUnit XML per run under results_dir
    results_dir: str = ""  # default: <suite>/results

    # --- derived URLs (filled in __post_init__ when left blank) ---
    def __post_init__(self) -> None:
        ns, dom = self.namespace, self.base_domain
        self.bridge_base_url = (
            self.bridge_base_url or f"https://g2p-bridge.{ns}.{dom}/api/g2p-bridge"
        )
        self.bene_portal_base_url = (
            self.bene_portal_base_url
            or f"https://g2p-bridge-bene-portal.{ns}.{dom}/api/bene-portal"
        )
        self.example_bank_base_url = (
            self.example_bank_base_url
            or f"https://example-bank.{ns}.{dom}/api/example-bank"
        )
        # spar_mapper_base_url is NOT derived — the SPAR host varies per
        # deployment, so it must be set explicitly in config.yaml (see
        # config.example.yaml). Left blank, the e2e seeding step will fail with
        # a clear message rather than hit a guessed URL.
        # Normalise: strip trailing slashes.
        for f in (
            "bridge_base_url",
            "bene_portal_base_url",
            "example_bank_base_url",
            "spar_mapper_base_url",
        ):
            setattr(self, f, getattr(self, f).rstrip("/"))
        if not self.results_dir:
            self.results_dir = str(Path(__file__).resolve().parents[1] / "results")


def _coerce(value: str, sample: Any) -> Any:
    if isinstance(sample, bool):
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(sample, int) and not isinstance(sample, bool):
        return int(value)
    if isinstance(sample, float):
        return float(value)
    return value


def load_config(path: str | None = None) -> Config:
    data: dict[str, Any] = {}
    cfg_path = path or os.environ.get("SANITY_CONFIG")
    if not cfg_path:
        default = Path(__file__).resolve().parents[1] / "config.yaml"
        if default.exists():
            cfg_path = str(default)
    if cfg_path and Path(cfg_path).exists():
        with open(cfg_path) as fh:
            data = yaml.safe_load(fh) or {}

    # Drop blank-string overrides so defaults/derivation still apply.
    data = {k: v for k, v in data.items() if not (isinstance(v, str) and v == "")}

    # Environment overrides: SANITY_<UPPER_SNAKE>.
    defaults = {f.name: f.default for f in fields(Config)}
    for name, sample in defaults.items():
        env_key = "SANITY_" + name.upper()
        if env_key in os.environ and os.environ[env_key] != "":
            data[name] = _coerce(os.environ[env_key], sample)

    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})
