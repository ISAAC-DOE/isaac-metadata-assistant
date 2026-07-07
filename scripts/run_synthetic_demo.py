#!/usr/bin/env python3
"""Run the ISAAC synthetic XANES demo end-to-end and (re)generate the sample record.

This script is a THIN reviewer/demo driver. It only *calls* the existing, unchanged
pipeline — it defines no validation, schema, extraction, or export behaviour of its own,
and it imports nothing from the memory/query (Graphify) plane. It exists so the committed
sample under ``docs/samples/`` is reproducible by one documented command instead of a
throwaway script.

What it does, on committed SYNTHETIC fixtures only (never ``examples/``):

    tests/fixtures/synthetic/mock_campaign.csv      ─┐
    tests/fixtures/synthetic/raw_scan_listing.txt   ─┤ build_draft   (deterministic extract)
                                                     ▼
                                            validate_draft            (no-guessing checks)
                                                     ▼  apply_answers (simulated human answers)
    tests/fixtures/synthetic/xanes_completion_answers.json
                                                     ▼  export_draft  (schema-gated transform)
                                    <out>/<ULID>.json  + <out>/<ULID>.evidence.json

Reproducibility: the official RECORD is byte-identical to the committed sample because
this script pins both the record id and the ``created_utc`` timestamp. The evidence
SIDECAR is identical *except* its ``generated_utc`` field, which ``export.build_sidecar``
stamps with the real wall clock by design — so the sidecar is not byte-identical, and this
script does not claim it is.

No value is invented here: every scientific value comes from a committed synthetic fixture,
the fake year-2099 session makes the data unmistakably not real, and no SLAC/SSRL data is
touched. This is a demonstration harness, not part of the deterministic truth core.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reproducibility constants — chosen to regenerate the committed docs/samples record.
RECORD_ID = "01JQZ0SYNTHXANESDEMO000000"
CREATED_UTC = "2099-03-05T20:15:00Z"  # pins record timestamps.created_utc (fake, year 2099)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYN = REPO_ROOT / "tests" / "fixtures" / "synthetic"
CSV_PATH = SYN / "mock_campaign.csv"
LISTING_PATH = SYN / "raw_scan_listing.txt"
ANSWERS_PATH = SYN / "xanes_completion_answers.json"
COMMITTED_SAMPLE = REPO_ROOT / "docs" / "samples" / f"{RECORD_ID}.json"


def _dump(obj: dict) -> str:
    """Serialize exactly the way the committed sample was written (indent=2 + newline)."""
    return json.dumps(obj, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="/tmp/isaac-demo",
        help="directory to write the regenerated record + sidecar (default: /tmp/isaac-demo)",
    )
    args = parser.parse_args()

    # Imported here so --help works even if the package is not installed.
    from isaac_records.complete import apply_answers
    from isaac_records.draft_validator import validate_draft
    from isaac_records.export import export_draft
    from isaac_records.extract.draft_builder import build_draft

    print("ISAAC synthetic XANES demo  (SYNTHETIC data — fake year-2099 session)")
    print("=" * 68)

    # 1. Deterministic extraction: structured sheet + raw file listing -> draft.
    print("\n[1] build_draft  (deterministic extraction, no guessing)")
    print(f"      sheet:   {CSV_PATH.relative_to(REPO_ROOT)}")
    print(f"      listing: {LISTING_PATH.relative_to(REPO_ROOT)}")
    draft = build_draft(CSV_PATH, LISTING_PATH)
    pending = draft.get("pending") or []
    print(f"      -> {len(draft.get('fields', {}))} evidenced fields, "
          f"{len(draft.get('assets') or [])} assets, {len(pending)} pending blocker(s)")
    for entry in pending:
        print(f"         pending[{entry.get('kind')}]: {entry.get('question')}")

    # 2. No-guessing draft validation (this passes even with pending blockers open).
    print("\n[2] validate_draft  (no-guessing checks)")
    draft_report = validate_draft(draft)
    print(f"      draft ok: {draft_report.ok}  "
          f"(pending blockers are surfaced, never guessed)")
    if not draft_report.ok:
        print(draft_report.render())
        return 1

    # 3. Apply the SIMULATED human answers (stand-ins for /isaac-complete input).
    print("\n[3] apply_answers  (simulated human answers -> user_confirmation evidence)")
    print(f"      answers: {ANSWERS_PATH.relative_to(REPO_ROOT)}")
    answers = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
    completed = apply_answers(draft, answers)
    print(f"      -> {len(completed.get('pending') or [])} pending remaining, "
          f"{len(completed.get('assets') or [])} assets now resolved (sha256 supplied)")

    # 4. Schema-gated export -> official record + evidence sidecar.
    print("\n[4] export_draft  (schema-gated transform)")
    result = export_draft(completed, REPO_ROOT, record_id=RECORD_ID, now=CREATED_UTC)
    if not result.ok:
        print("      EXPORT BLOCKED:")
        print(result.draft_report.render())
        if result.official_report is not None:
            print(result.official_report.render())
        return 1
    print(f"      official schema valid: {result.official_report.ok}  (ISAAC v1.05)")
    print(f"      record_id: {result.record['record_id']}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    record_path = out_dir / f"{RECORD_ID}.json"
    sidecar_path = out_dir / f"{RECORD_ID}.evidence.json"
    record_path.write_text(_dump(result.record), encoding="utf-8")
    sidecar_path.write_text(_dump(result.sidecar), encoding="utf-8")
    print(f"      wrote: {record_path}")
    print(f"      wrote: {sidecar_path}")

    # 5. Reproducibility check against the committed sample (record only).
    print("\n[5] reproducibility check")
    if COMMITTED_SAMPLE.exists():
        identical = record_path.read_bytes() == COMMITTED_SAMPLE.read_bytes()
        print(f"      record byte-identical to committed docs/samples sample: {identical}")
        print("      sidecar generated_utc is wall-clock (not byte-identical, by design)")
        if not identical:
            print("      NOTE: record differs from the committed sample — investigate before"
                  " trusting this run.")
            return 1
    else:
        print(f"      committed sample not found at {COMMITTED_SAMPLE} — skipping check")

    print("\nDone. Verify the generated record with the official CLI:")
    print(f"      .venv/bin/isaac validate {record_path} --official")
    print(f"      .venv/bin/isaac audit --records-dir {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
