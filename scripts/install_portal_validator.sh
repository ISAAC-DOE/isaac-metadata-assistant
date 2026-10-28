#!/usr/bin/env bash
# Install the OFFLINE upstream ISAAC portal validator, pinned, for `isaac bundle validate`.
#
#   scripts/install_portal_validator.sh [COMMIT] [REPO_URL]
#
# Clones ISAAC-DOE/isaac-ai-ready-record at a PINNED commit (default a1cb1c8) into
#   ~/.cache/isaac/portal-validator/<commit>/src
# and creates an ISOLATED venv at
#   ~/.cache/isaac/portal-validator/<commit>/venv
# holding exactly: jsonschema rfc3339-validator PyYAML GitPython requests.
#
# Idempotent: an existing checkout is verified (HEAD must start with the pinned commit)
# and reused; an existing venv is reused. It DOWNLOADS: the upstream repository (git
# clone) and those five packages (pip). It never touches this checkout's .venv, system
# Python, or Docker, and it uploads nothing. `isaac bundle validate` then runs the
# validator in a subprocess with `python -I`; validation itself makes no network call
# from this application.
set -euo pipefail

COMMIT="${1:-a1cb1c8}"
REPO="${2:-https://github.com/ISAAC-DOE/isaac-ai-ready-record.git}"
BASE="$HOME/.cache/isaac/portal-validator/$COMMIT"
SRC="$BASE/src"
VENV="$BASE/venv"

if [[ ! "$COMMIT" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "error: commit must be a 7-40 character hex sha, got '$COMMIT'." >&2
  exit 2
fi
command -v git >/dev/null 2>&1 || { echo "error: git is required." >&2; exit 2; }

mkdir -p "$BASE"
if [[ -d "$SRC/.git" ]]; then
  echo "Reusing $SRC"
else
  echo "Cloning $REPO into $SRC ..."
  git clone --quiet "$REPO" "$SRC"
fi
git -C "$SRC" checkout --quiet "$COMMIT"
HEAD="$(git -C "$SRC" rev-parse HEAD)"
if [[ "$HEAD" != "$COMMIT"* ]]; then
  echo "error: $SRC is at $HEAD, not the pinned $COMMIT." >&2
  exit 2
fi
if [[ ! -f "$SRC/portal/validation.py" ]]; then
  echo "error: $SRC has no portal/validation.py at $COMMIT." >&2
  exit 2
fi

PY=""
for candidate in python3.11 python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$candidate")"; break
  fi
done
[[ -n "$PY" ]] || { echo "error: no Python >= 3.10 found." >&2; exit 2; }

if [[ ! -x "$VENV/bin/python" ]]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet jsonschema rfc3339-validator PyYAML GitPython requests

( cd "$SRC/portal" && "$VENV/bin/python" -I -c 'import sys; sys.path.insert(0, "."); import validation; print("portal validator OK")' )
echo
echo "Installed. isaac bundle validate will find it at $BASE"
echo "(or set ISAAC_PORTAL_VALIDATOR_DIR=$SRC ISAAC_PORTAL_VALIDATOR_PYTHON=$VENV/bin/python)"
