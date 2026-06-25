"""Pytest fixtures: config, HTTP clients, run namespace, and SPAR seed/cleanup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

# Make the 'sanity' package importable when running from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sanity import manifest, seed  # noqa: E402
from sanity.clients import (  # noqa: E402
    BenePortalClient,
    BridgeClient,
    ExampleBankClient,
    SparClient,
)
from sanity.config import load_config  # noqa: E402
from sanity.naming import RunNamespace  # noqa: E402
from sanity.signing import RequestSigner  # noqa: E402

_logger = logging.getLogger("sanity")


# --------------------------------------------------------------------------- #
# Always persist results (HTML + JUnit XML) per run, unless paths were given.
# --------------------------------------------------------------------------- #
def pytest_configure(config):
    cfg = load_config()
    if not getattr(cfg, "write_results", True):
        return
    import datetime

    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = Path(cfg.results_dir) / f"{cfg.test_prefix}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    # Only set if the user didn't pass --html / --junitxml explicitly.
    if getattr(config.option, "htmlpath", None) in (None, ""):
        config.option.htmlpath = str(out / "report.html")
        config.option.self_contained_html = True
    if getattr(config.option, "xmlpath", None) in (None, ""):
        config.option.xmlpath = str(out / "junit.xml")
    config._sanity_results_dir = str(out)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    out = getattr(config, "_sanity_results_dir", None)
    if out:
        terminalreporter.write_line(f"\nSanity results written to: {out}")


# --------------------------------------------------------------------------- #
# Session-scoped configuration & identity
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def config():
    cfg = load_config()
    _logger.info(
        "Target: bridge=%s example_bank=%s spar=%s",
        cfg.bridge_base_url,
        cfg.example_bank_base_url,
        cfg.spar_mapper_base_url,
    )
    return cfg


@pytest.fixture(scope="session")
def run_ns(config) -> RunNamespace:
    ns = RunNamespace.new(config.test_prefix)
    _logger.info("Run id: %s", ns.run_id)
    return ns


# --------------------------------------------------------------------------- #
# HTTP clients
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def bridge(config):
    signer = None
    if config.sign_requests:
        candidate = RequestSigner(
            config.signing_key_path,
            kid=config.signing_key_kid,
            algorithm=config.signing_algorithm,
        )
        signer = candidate if candidate.available else None
    c = BridgeClient(
        config.bridge_base_url,
        verify_tls=config.verify_tls,
        timeout=config.request_timeout_seconds,
        sender=config.test_prefix,
        signer=signer,
    )
    yield c
    c.close()


@pytest.fixture(scope="session")
def bene_portal(config):
    c = BenePortalClient(
        config.bene_portal_base_url,
        verify_tls=config.verify_tls,
        timeout=config.request_timeout_seconds,
        sender=config.test_prefix,
    )
    yield c
    c.close()


@pytest.fixture(scope="session")
def example_bank(config):
    c = ExampleBankClient(
        config.example_bank_base_url,
        verify_tls=config.verify_tls,
        timeout=config.request_timeout_seconds,
        sender=config.test_prefix,
    )
    yield c
    c.close()


@pytest.fixture(scope="session")
def spar(config):
    c = SparClient(
        config.spar_mapper_base_url,
        verify_tls=config.verify_tls,
        timeout=config.request_timeout_seconds,
        sender=config.test_prefix,
    )
    yield c
    c.close()


# --------------------------------------------------------------------------- #
# SPAR seeding with guaranteed cleanup + run manifest
# --------------------------------------------------------------------------- #
class SeededLinks:
    """Creates ID->FA links in SPAR and guarantees they are unlinked at teardown."""

    def __init__(self, spar_client: SparClient, cfg, run_ns: RunNamespace):
        self._spar = spar_client
        self._cfg = cfg
        self._ns = run_ns
        self.entries: list[dict] = []

    def link_beneficiary(self, n: int) -> tuple[str, str]:
        ref = self._ns.reference_id(n)
        bid = self._ns.beneficiary_id(n)
        acc = self._ns.account_number(n)
        req = seed.link_request(
            self._cfg,
            reference_id=ref,
            beneficiary_id=bid,
            account_number=acc,
            name=f"{self._ns.prefix} Beneficiary {n}",
        )
        status, body = self._spar.link(self._ns.request_id(), self._ns.run_id, [req])
        self.entries.append(
            {
                "reference_id": ref,
                "beneficiary_id": bid,
                "account_number": acc,
                "link_status": status,
            }
        )
        _logger.info("SPAR link bene=%s -> acc=%s (HTTP %s)", bid, acc, status)
        return bid, acc

    def cleanup(self) -> None:
        if not self.entries:
            return
        unlink_reqs = [
            seed.unlink_request(
                reference_id=e["reference_id"], beneficiary_id=e["beneficiary_id"]
            )
            for e in self.entries
        ]
        try:
            status, _ = self._spar.unlink(
                self._ns.request_id(), self._ns.run_id, unlink_reqs
            )
            _logger.info(
                "SPAR unlink of %d entries (HTTP %s)", len(unlink_reqs), status
            )
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "SPAR unlink failed: %s (manifest retained for manual teardown)", exc
            )


@pytest.fixture(scope="session")
def seeded_links(spar, config, run_ns):
    sl = SeededLinks(spar, config, run_ns)
    yield sl
    # Always persist a manifest (so teardown.py can finish the job later).
    manifest.write(
        run_ns.run_id,
        {
            "spar_mapper_base_url": config.spar_mapper_base_url,
            "namespace": config.namespace,
            "entries": sl.entries,
        },
    )
    if config.cleanup_on_teardown:
        sl.cleanup()
    else:
        _logger.info(
            "cleanup_on_teardown=false; leaving %d SPAR link(s) in place. "
            "Run 'python teardown.py --run-id %s' to clean up.",
            len(sl.entries),
            run_ns.run_id,
        )
