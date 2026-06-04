"""Builders for the G2PConnect request/response envelope used by the Bridge APIs.

Envelope (from openg2p_fastapi_common.schemas):

    {
      "request_header": {
        "sender_app_mnemonic": str,
        "sender_app_url": str,
        "request_id": str,
        "request_timestamp": iso8601,
        "instance_id": str | null
      },
      "request_body": {
        "pagination_request": null,
        "request_payload": <payload>      # list or str or dict per endpoint
      }
    }
"""

from __future__ import annotations

import datetime
from typing import Any


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def request_header(request_id: str, sender: str, sender_url: str) -> dict[str, Any]:
    return {
        "sender_app_mnemonic": sender,
        "sender_app_url": sender_url,
        "request_id": request_id,
        "request_timestamp": _now_iso(),
        "instance_id": None,
    }


def envelope(
    request_id: str,
    payload: Any,
    *,
    sender: str,
    sender_url: str = "http://sanity.test",
    body_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a request_payload in the full G2PRequest envelope.

    ``body_extra`` adds extra keys to request_body (e.g.
    ``disbursement_batch_control_id`` so the caller controls the batch id).
    """
    return {
        "request_header": request_header(request_id, sender, sender_url),
        "request_body": {
            "pagination_request": None,
            "request_payload": payload,
            **(body_extra or {}),
        },
    }


def response_status(body: dict[str, Any]) -> str | None:
    """Return response_header.response_status ('SUCCESS' | 'ERROR') if present."""
    try:
        return body["response_header"]["response_status"]
    except (KeyError, TypeError):
        return None


def response_error_code(body: dict[str, Any]) -> str | None:
    try:
        return body["response_header"].get("response_error_code")
    except (AttributeError, KeyError, TypeError):
        return None


def response_payload(body: dict[str, Any]) -> Any:
    try:
        return body["response_body"]["response_payload"]
    except (KeyError, TypeError):
        return None


def is_g2p_response(body: Any) -> bool:
    """True if the body is a structurally valid G2PResponse envelope."""
    return (
        isinstance(body, dict)
        and isinstance(body.get("response_header"), dict)
        and "response_status" in body["response_header"]
        and "response_body" in body
    )
