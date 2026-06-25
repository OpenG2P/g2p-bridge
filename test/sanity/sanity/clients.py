"""HTTP clients for the four systems the sanity suite talks to.

All clients are thin httpx wrappers. POST helpers return ``(status_code, json)``
tuples; ``json`` is ``None`` when the body is not JSON.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from . import g2p

_logger = logging.getLogger("sanity")


class _Base:
    def __init__(
        self,
        base_url: str,
        *,
        verify_tls: bool,
        timeout: int,
        sender: str = "TEST_SANITY",
        signer=None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(
                f"{type(self).__name__}: base_url is {self.base_url!r} — empty or "
                "missing an 'http(s)://' scheme. Set the matching *_base_url in "
                "config.yaml. The sanity suite runs off-cluster, so use the public "
                "https URL (e.g. https://spar.<ns>.openg2p.org/api/mapper/mapper), "
                "not an in-cluster service name."
            )
        self.sender = sender
        # Optional request signer (detached JWS in the Signature header). Set when
        # the target enforces partner signature validation (the trial default).
        self.signer = signer
        self._http = httpx.Client(verify=verify_tls, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    # --- low level ---
    def _json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return None

    def get(self, path: str) -> httpx.Response:
        return self._http.get(self.base_url + path)

    def post_json(self, path: str, body: Any) -> tuple[int, Any]:
        headers = None
        if self.signer is not None:
            try:
                headers = {"Signature": self.signer.sign(body)}
            except Exception:
                _logger.exception("Failed to sign request; sending unsigned")
        r = self._http.post(self.base_url + path, json=body, headers=headers)
        return r.status_code, self._json(r)


class BridgeClient(_Base):
    """G2P Bridge Partner API (G2PConnect envelope)."""

    def ping(self) -> httpx.Response:
        return self.get("/ping")

    def _post(self, path: str, request_id: str, payload: Any) -> tuple[int, Any]:
        return self.post_json(
            path, g2p.envelope(request_id, payload, sender=self.sender)
        )

    def create_envelopes(
        self, request_id: str, payloads: list[dict]
    ) -> tuple[int, Any]:
        return self._post("/create_disbursement_envelopes", request_id, payloads)

    def cancel_envelope(self, request_id: str, envelope_id: str) -> tuple[int, Any]:
        return self._post(
            "/cancel_disbursement_envelope", request_id, [{"id": envelope_id}]
        )

    def amend_envelope(self, request_id: str, payload: dict) -> tuple[int, Any]:
        return self._post("/amend_disbursement_envelope", request_id, [payload])

    def create_disbursements(
        self, request_id: str, payloads: list[dict], batch_control_id: str | None = None
    ) -> tuple[int, Any]:
        # Supplying disbursement_batch_control_id lets the caller correlate/poll
        # the batch (the API does not echo a generated id back).
        body_extra = (
            {"disbursement_batch_control_id": batch_control_id}
            if batch_control_id
            else None
        )
        env = g2p.envelope(
            request_id, payloads, sender=self.sender, body_extra=body_extra
        )
        return self.post_json("/create_disbursements", env)

    def cancel_disbursements(self, request_id: str, ids: list[str]) -> tuple[int, Any]:
        return self._post(
            "/cancel_disbursements", request_id, [{"disbursement_id": i} for i in ids]
        )

    def get_disbursement_status(
        self, request_id: str, ids: list[str]
    ) -> tuple[int, Any]:
        return self._post("/get_disbursement_status", request_id, ids)

    def get_envelope_status(self, request_id: str, envelope_id: str) -> tuple[int, Any]:
        return self._post("/get_disbursement_envelope_status", request_id, envelope_id)

    def get_batch_control(self, request_id: str, envelope_id: str) -> tuple[int, Any]:
        return self._post("/get_disbursement_batch_control", request_id, envelope_id)

    def upload_mt940(
        self, file_bytes: bytes, filename: str = "statement.mt940"
    ) -> tuple[int, Any]:
        r = self._http.post(
            self.base_url + "/upload_mt940",
            files={"statement_file": (filename, file_bytes, "text/plain")},
        )
        return r.status_code, self._json(r)


class BenePortalClient(_Base):
    """G2P Bridge Beneficiary Portal API (G2PConnect envelope, dict payloads).

    The disbursement routes live under a ``/disbursement`` router prefix.
    """

    def ping(self) -> httpx.Response:
        return self.get("/ping")

    def get_all_disbursements(self, request_id: str, payload: dict) -> tuple[int, Any]:
        return self.post_json(
            "/disbursement/get_all_disbursements",
            g2p.envelope(request_id, payload, sender=self.sender),
        )

    def get_disbursement_summary_till_date(
        self, request_id: str, payload: dict
    ) -> tuple[int, Any]:
        return self.post_json(
            "/disbursement/get_disbursement_summary_till_date",
            g2p.envelope(request_id, payload, sender=self.sender),
        )


class ExampleBankClient(_Base):
    """Example Bank simulator API (plain JSON, no envelope)."""

    def ping(self) -> httpx.Response:
        return self.get("/ping")

    def check_funds(
        self, account: str, currency: str, amount: float
    ) -> tuple[int, Any]:
        return self.post_json(
            "/check_funds",
            {
                "account_number": account,
                "account_currency": currency,
                "total_funds_needed": amount,
            },
        )

    def block_funds(
        self, account: str, currency: str, amount: float
    ) -> tuple[int, Any]:
        return self.post_json(
            "/block_funds",
            {
                "account_number": account,
                "currency": currency,
                "amount": amount,
            },
        )

    def generate_account_statement(
        self, program_account_number: str
    ) -> tuple[int, Any]:
        return self.post_json(
            "/generate_account_statement",
            {"program_account_number": program_account_number},
        )

    def initiate_payment(self, payloads: list[dict]) -> tuple[int, Any]:
        return self.post_json("/initiate_payment", payloads)

    def ussd(self, fields: dict) -> tuple[int, Any]:
        # USSD is a form-encoded endpoint returning plain text.
        r = self._http.post(self.base_url + "/ussd", data=fields)
        return r.status_code, (r.text if r.status_code == 200 else self._json(r))


class SparClient(_Base):
    """SPAR Mapper Partner API — used to seed/clean ID->FA links."""

    def link(
        self, request_id: str, transaction_id: str, link_requests: list[dict]
    ) -> tuple[int, Any]:
        payload = {"transaction_id": transaction_id, "link_request": link_requests}
        return self.post_json(
            "/link", g2p.envelope(request_id, payload, sender=self.sender)
        )

    def unlink(
        self, request_id: str, transaction_id: str, unlink_requests: list[dict]
    ) -> tuple[int, Any]:
        payload = {"transaction_id": transaction_id, "unlink_request": unlink_requests}
        return self.post_json(
            "/unlink", g2p.envelope(request_id, payload, sender=self.sender)
        )


def poll_until(
    fn: Callable[[], Any],
    *,
    predicate: Callable[[Any], bool],
    timeout: int,
    interval: int,
    description: str = "condition",
) -> tuple[bool, Any]:
    """Call ``fn`` every ``interval`` seconds until ``predicate(result)`` or timeout.

    Returns ``(succeeded, last_result)``. Never raises on predicate failure.
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    attempt = 0
    while True:
        attempt += 1
        try:
            last = fn()
            if predicate(last):
                _logger.info("poll '%s': satisfied on attempt %d", description, attempt)
                return True, last
        except Exception as exc:  # noqa: BLE001 - polling is best-effort
            _logger.warning(
                "poll '%s' attempt %d raised: %s", description, attempt, exc
            )
        if time.monotonic() >= deadline:
            _logger.error("poll '%s': timed out after %ds", description, timeout)
            return False, last
        time.sleep(interval)
