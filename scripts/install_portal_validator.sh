#!/usr/bin/env bash
# Make the OFFLINE upstream ISAAC portal validator ready for `isaac bundle validate`.
#
#   scripts/install_portal_validator.sh
#
# The validator itself SHIPS WITH THIS REPOSITORY: vendor/isaac-portal-validator/a1cb1c8/ holds the four
# files the upstream portal's `validate_record_full` reads (plus the record contract the skill quotes),
# unmodified, at the pinned commit (vendor/isaac-portal-validator/PROVENANCE.md). Nothing is cloned.
#
# What this script does (idempotent; safe to re-run; no sudo):
#   1. checks each vendored file's sha256 against PROVENANCE.md (a changed file is refused; an extra
#      file in that folder is refused by step 3's check, the one `isaac bundle validate` makes);
#   2. installs the validator's packages into THIS checkout's .venv:
#        pip install -e ".[portal]"   (jsonschema rfc3339-validator PyYAML GitPython requests)
#   3. runs the vendored validator once, in an isolated interpreter (`python -I`), on a made-up record,
#      and says which copy `isaac bundle validate` will use.
#
# It DOWNLOADS: those five packages from the Python package index. It never touches system Python,
# your shell profile or Docker, and it uploads nothing. Validation itself makes no network call.
# The .venv comes from scripts/setup_isaac_local.sh (which runs this script as its step 3).
set -euo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$CHECKOUT/.venv"
PIN="a1cb1c8"
VENDORED="$CHECKOUT/vendor/isaac-portal-validator/$PIN"
PROVENANCE="$CHECKOUT/vendor/isaac-portal-validator/PROVENANCE.md"

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "error: this script takes no arguments any more: the validator ships with the repository at $PIN" >&2
       echo "       (vendor/isaac-portal-validator/). To refresh it to another commit, follow PROVENANCE.md there." >&2
       exit 2 ;;
  esac
fi

# 1. the vendored files are the ones PROVENANCE.md lists (its table rows: | `path` | `sha256` |)
[[ -f "$VENDORED/portal/validation.py" && -f "$PROVENANCE" ]] || {
  echo "error: the vendored validator is missing from this checkout ($VENDORED). Restore it with git (git checkout -- vendor/)." >&2
  exit 2
}
n=0
while IFS='|' read -r _ path sum _; do
  path="$(echo "$path" | tr -d ' `')"; sum="$(echo "$sum" | tr -d ' `')"
  [[ "$path" =~ ^(portal|schema|data)/ && "$sum" =~ ^[0-9a-f]{64}$ ]] || continue
  got="$(shasum -a 256 "$VENDORED/$path" 2>/dev/null | cut -d' ' -f1)"
  if [[ "$got" != "$sum" ]]; then
    echo "error: $VENDORED/$path does not match PROVENANCE.md (sha256 ${got:-missing}, expected $sum)." >&2
    echo "       Restore it with git (git checkout -- vendor/), or refresh the copy as PROVENANCE.md says." >&2
    exit 2
  fi
  n=$((n+1))
done < "$PROVENANCE"
[[ $n -ge 5 ]] || { echo "error: PROVENANCE.md lists $n vendored files, expected 5." >&2; exit 2; }
echo "Vendored validator at $PIN: $n files, each sha256 as PROVENANCE.md lists."

# 2. its packages, into this checkout's .venv
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "error: $VENV does not exist yet. Run scripts/setup_isaac_local.sh first (it creates it, then runs this script)." >&2
  exit 2
fi
if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
  "$VENV/bin/python" -m ensurepip --upgrade >/dev/null
fi
echo "Installing the validator's packages into $VENV ..."
"$VENV/bin/python" -m pip install --quiet -e "$CHECKOUT[portal]"

# 3. one run of the vendored validator, isolated, on a made-up record; then what `isaac` will use
PYC="$(mktemp -d "${TMPDIR:-/tmp}/isaac-portal-pyc.XXXXXX")"; trap 'rm -rf "$PYC"' EXIT
# -B and a throwaway pycache_prefix, as the real runner: no compiled file is read from or written to vendor/
( cd "$VENDORED/portal" && env -i PATH=/usr/bin:/bin HOME="$HOME" "$VENV/bin/python" -I -B -X pycache_prefix="$PYC" -c '
import json, sys
sys.path.insert(0, ".")
import validation
result = validation.validate_record_full({"record_id": "SYNTHETIC-INSTALL-PROBE"})
outcome, _ = validation.outcome(result)
assert outcome == "reject", outcome  # an empty made-up record must be rejected
print("portal validator OK (a made-up empty record is rejected, as it must be)")
' )
( cd / && PYTHONPATH="$CHECKOUT/src:$CHECKOUT/apps/api" "$VENV/bin/python" -c '
from isaac_api.local_import import portal as P
w = P.locate()
if w["available"]:
    print("isaac bundle validate will use the %s copy at %s, run with %s" % (w["source"], w["commit"][:7], w["python"]))
else:
    raise SystemExit("error: " + w["reason"])
' )
echo
echo "Installed. Check everything with: scripts/setup_isaac_local.sh --check"
