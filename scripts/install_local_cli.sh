#!/usr/bin/env bash
# Install the local-first `isaac import` / `isaac bundle` CLI into THIS checkout's .venv.
#
# What it does (idempotent; safe to re-run):
#   1. ensures <checkout>/.venv exists with Python >= 3.11 — created with `uv venv` if
#      uv is installed, else `python3.11 -m venv` (or `python3` if that is >= 3.11);
#   2. `pip install -e .` into that venv (the `isaac` command and the truth core);
#   3. writes ONE .pth file into the venv's site-packages pointing at
#      <checkout>/apps/api, so `isaac import` can import `isaac_api` from any directory.
#
# What it may download: `pip install -e .` resolves pyproject.toml's dependencies (and
# setuptools for the editable build) from the package index; and when uv is used,
# `uv venv --python ">=3.11"` DOWNLOADS a Python build if none >= 3.11 is installed.
# What it never does: touch system Python, install anything outside .venv, or touch
# Docker. It does not change pyproject.toml packaging: isaac_api is put on the venv's
# path, not installed, so the server image keeps importing its own copied apps/api/.
set -euo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$CHECKOUT/.venv"
PTH_NAME="isaac_local_import_apps_api.pth"

if [[ ! -f "$CHECKOUT/schema/isaac_record_v1.json" || ! -d "$CHECKOUT/apps/api/isaac_api" ]]; then
  echo "error: $CHECKOUT does not look like an ISAAC checkout (schema/ or apps/api/ missing)." >&2
  exit 2
fi

version_ok() {  # $1 = python executable; true if it is >= 3.11
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

if [[ -x "$VENV/bin/python" ]]; then
  if ! version_ok "$VENV/bin/python"; then
    echo "error: $VENV exists but its Python is older than 3.11." >&2
    echo "       Move it aside and re-run this script; it will not replace it for you." >&2
    exit 2
  fi
  echo "Using existing $VENV ($("$VENV/bin/python" -V))."
else
  if command -v uv >/dev/null 2>&1; then
    echo "Creating $VENV with uv (Python >= 3.11; uv may download a Python build if none is installed)..."
    uv venv --python ">=3.11" "$VENV"
  else
    PY=""
    for candidate in python3.11 python3.12 python3.13 python3; do
      if command -v "$candidate" >/dev/null 2>&1 && version_ok "$(command -v "$candidate")"; then
        PY="$(command -v "$candidate")"
        break
      fi
    done
    if [[ -z "$PY" ]]; then
      echo "error: no Python >= 3.11 found (tried python3.11, python3.12, python3.13, python3)." >&2
      echo "       Install one (or uv), then re-run. Nothing was changed." >&2
      exit 2
    fi
    echo "Creating $VENV with $PY..."
    "$PY" -m venv "$VENV"
  fi
fi

if ! version_ok "$VENV/bin/python"; then
  echo "error: $VENV/bin/python is older than 3.11." >&2
  exit 2
fi

if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
  "$VENV/bin/python" -m ensurepip --upgrade >/dev/null
fi

echo "Installing the checkout (editable) into $VENV..."
"$VENV/bin/python" -m pip install --quiet -e "$CHECKOUT"

SITE="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PTH="$SITE/$PTH_NAME"
WANT="$CHECKOUT/apps/api"
if [[ -f "$PTH" && "$(cat "$PTH")" == "$WANT" ]]; then
  echo "Path file already present: $PTH"
else
  printf '%s\n' "$WANT" > "$PTH"
  echo "Wrote $PTH -> $WANT"
fi

# Verify from a neutral directory, so the check does not pass only because of the cwd.
( cd / && "$VENV/bin/python" -c 'import isaac_api.local_import.cli, isaac_records.cli' )
echo
echo "Done. Try:"
echo "  $VENV/bin/isaac import <folder-or-zip> --out <bundle-dir>"
echo "  $VENV/bin/isaac bundle check <bundle-dir>"
