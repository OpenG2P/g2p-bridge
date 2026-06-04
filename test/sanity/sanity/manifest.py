"""Run manifests — record the test data a run created so it can be cleaned up.

The suite auto-cleans at the end of a session, but a crashed run can leave SPAR
links behind. Each run writes a manifest under ``.sanity-runs/<run_id>.json`` so
the standalone ``teardown.py`` can unlink them later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).resolve().parents[1] / ".sanity-runs"


def _path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def write(run_id: str, data: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(run_id)
    payload = {"run_id": run_id, **data}
    p.write_text(json.dumps(payload, indent=2, default=str))
    return p


def read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def list_manifests() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(RUNS_DIR.glob("*.json"))


def delete(run_id: str) -> None:
    p = _path(run_id)
    if p.exists():
        p.unlink()
