"""Deterministic, clearly-marked test-data naming.

Every identifier the suite creates carries the configured prefix (default
``TEST_SANITY``) plus a per-run token, so test data is:
  * isolated      — never collides with real data or another run,
  * identifiable  — operational reports exclude ``... LIKE 'TEST_%'``,
  * traceable     — the run token ties data back to a single run.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RunNamespace:
    prefix: str
    run_token: str

    @classmethod
    def new(cls, prefix: str) -> "RunNamespace":
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        short = uuid.uuid4().hex[:6]
        return cls(prefix=prefix, run_token=f"{stamp}_{short}")

    @property
    def run_id(self) -> str:
        """Stable identifier for this run, e.g. TEST_SANITY_20260604T101500_a1b2c3."""
        return f"{self.prefix}_{self.run_token}"

    # --- field builders -------------------------------------------------------
    @property
    def program_mnemonic(self) -> str:
        # The key field for report filtering — keep it the bare prefix so a single
        # 'TEST_%' pattern excludes every run.
        return self.prefix

    @property
    def benefit_code_mnemonic(self) -> str:
        return f"{self.prefix}_CASH"

    @property
    def target_registry(self) -> str:
        return self.prefix

    def beneficiary_id(self, n: int) -> str:
        return f"{self.run_id}_BENE_{n:03d}"

    def disbursement_id(self, n: int) -> str:
        return f"{self.run_id}_DISB_{n:03d}"

    def account_number(self, n: int) -> str:
        return f"{self.run_id}_ACC_{n:03d}"

    def request_id(self) -> str:
        return f"{self.run_id}_REQ_{uuid.uuid4().hex[:8]}"

    def reference_id(self, n: int) -> str:
        return f"{self.run_id}_REF_{n:03d}"

    def batch_control_id(self) -> str:
        return f"{self.run_id}_BCTL"
