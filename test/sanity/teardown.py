#!/usr/bin/env python3
"""Standalone teardown for sanity-suite test data.

The suite cleans up SPAR ID->FA links automatically at the end of a run. This
script is the manual fallback for when a run crashed and left links behind: it
reads the run manifests written under ``.sanity-runs/`` and unlinks them from
SPAR.

(The Bridge has no delete API for disbursements, so those rows are intentionally
left in place — they are namespaced under the TEST_SANITY program and excluded
from reports by the ``TEST_%`` filter.)

Usage:
  python teardown.py --list                 # list pending run manifests
  python teardown.py --all                  # unlink every pending run
  python teardown.py --run-id TEST_SANITY_...  # unlink one run
  python teardown.py --manifest path.json   # unlink from a specific manifest
  python teardown.py --all --dry-run        # show what would be unlinked
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sanity import manifest, seed  # noqa: E402
from sanity.clients import SparClient  # noqa: E402
from sanity.config import load_config  # noqa: E402


def _resolve_manifests(args) -> list[Path]:
    if args.manifest:
        return [Path(args.manifest)]
    if args.run_id:
        p = manifest.RUNS_DIR / f"{args.run_id}.json"
        return [p] if p.exists() else []
    if args.all:
        return manifest.list_manifests()
    return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--all", action="store_true", help="unlink every pending run manifest"
    )
    g.add_argument("--run-id", help="unlink a single run by id")
    g.add_argument("--manifest", help="unlink from a specific manifest file")
    ap.add_argument(
        "--list", action="store_true", help="list pending manifests and exit"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print actions, change nothing"
    )
    args = ap.parse_args()

    pending = manifest.list_manifests()
    if args.list or (not args.all and not args.run_id and not args.manifest):
        if not pending:
            print("No pending run manifests under", manifest.RUNS_DIR)
            return 0
        print(f"Pending run manifests ({len(pending)}):")
        for p in pending:
            data = manifest.read(p)
            print(
                f"  - {data.get('run_id')}  ({len(data.get('entries', []))} links)  [{p}]"
            )
        if not args.list:
            print(
                "\nPass --all, --run-id, or --manifest to unlink. (--dry-run to preview)"
            )
        return 0

    targets = _resolve_manifests(args)
    if not targets:
        print("Nothing to do (no matching manifest).")
        return 0

    cfg = load_config()
    rc = 0
    for path in targets:
        if not path.exists():
            print(f"!! manifest not found: {path}")
            rc = 1
            continue
        data = manifest.read(path)
        run_id = data.get("run_id", path.stem)
        base_url = data.get("spar_mapper_base_url", cfg.spar_mapper_base_url)
        entries = data.get("entries", [])
        if not entries:
            print(f"== {run_id}: no links recorded; removing manifest")
            if not args.dry_run:
                path.unlink()
            continue

        print(f"== {run_id}: unlinking {len(entries)} link(s) from {base_url}")
        unlink_reqs = [
            seed.unlink_request(
                reference_id=e["reference_id"], beneficiary_id=e["beneficiary_id"]
            )
            for e in entries
        ]
        for e in entries:
            print(f"   - {e['beneficiary_id']}  (ref {e['reference_id']})")
        if args.dry_run:
            continue

        client = SparClient(
            base_url,
            verify_tls=cfg.verify_tls,
            timeout=cfg.request_timeout_seconds,
            sender=cfg.test_prefix,
        )
        try:
            status, body = client.unlink(
                f"{run_id}_TEARDOWN_{uuid.uuid4().hex[:6]}", run_id, unlink_reqs
            )
            if status < 300:
                print(f"   OK (HTTP {status}); removing manifest")
                path.unlink()
            else:
                print(f"   !! unlink HTTP {status}: {body}")
                rc = 1
        except Exception as exc:  # noqa: BLE001
            print(f"   !! unlink error: {exc}")
            rc = 1
        finally:
            client.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
