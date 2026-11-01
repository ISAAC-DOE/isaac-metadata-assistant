#!/usr/bin/env bash
# One-command setup of the local-first ISAAC historical-import tools on a Mac (or Linux).
#
#   scripts/setup_isaac_local.sh [options]
#
#   --with-processing / --skip-processing   install the spectrum-processing extra (default: install)
#   --skip-portal                           do not install the offline portal validator
#   --skip-cli                              do not (re)install the CLI (use with --install-skill alone)
#   --install-skill                         copy the Claude Code skill into ~/.claude/skills
#   --skill-dir DIR                         where skills go (default: ~/.claude/skills)
#   --check                                 change nothing; only report what is and is not installed
#                                           (including whether an installed skill copy is out of date)
#   -h, --help
#
# What it does (idempotent; safe to re-run; needs no sudo):
#   1. a Python >= 3.11 virtual environment in <this checkout>/.venv (uv if present, else
#      python3.11/3.12/3.13/python3) and the `isaac` command  -> scripts/install_local_cli.sh
#   2. the processing extra (numpy, xraylarch)                 -> pip install -e ".[processing]"
#   3. the offline portal validator, pinned                    -> scripts/install_portal_validator.sh
#   4. optionally, the skill, COPIED (not linked) into the skills folder, with a small
#      checkout-path.txt so the skill can find this installation.
#
# What it downloads: packages from the Python package index (steps 1-3), the upstream ISAAC
# repository at one pinned commit (step 3), and, if uv has to make a Python, a Python build.
# What it never does: sudo, change system Python, edit your shell profile, upload or send anything.
set -uo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$CHECKOUT/.venv"
SKILL_NAME="isaac-historical-import"
WITH_PROCESSING=1; WITH_PORTAL=1; WITH_CLI=1; INSTALL_SKILL=0; CHECK_ONLY=0
SKILL_DIR="$HOME/.claude/skills"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-processing) WITH_PROCESSING=1 ;;
    --skip-processing) WITH_PROCESSING=0 ;;
    --skip-portal) WITH_PORTAL=0 ;;
    --skip-cli) WITH_CLI=0 ;;
    --install-skill) INSTALL_SKILL=1 ;;
    --skill-dir) shift; SKILL_DIR="${1:?--skill-dir needs a folder}" ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,24p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

OK="[ok]"; BAD="[missing]"; SKIP="[skipped]"
FINAL=()          # checklist lines
PROBLEMS=0
note() { FINAL+=("$1"); }

version_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }

if [[ ! -f "$CHECKOUT/schema/isaac_record_v1.json" || ! -d "$CHECKOUT/apps/api/isaac_api" ]]; then
  echo "error: $CHECKOUT does not look like an ISAAC folder (schema/ or apps/api/ missing)." >&2
  exit 2
fi

have_cli()        { ( cd / && "$VENV/bin/python" -c 'import isaac_api.local_import.cli, isaac_records.cli' ) >/dev/null 2>&1; }
have_processing() { ( cd / && "$VENV/bin/python" -c 'import numpy, larch' ) >/dev/null 2>&1; }
have_portal()     { compgen -G "$HOME/.cache/isaac/portal-validator/*/venv/bin/python" >/dev/null 2>&1; }

# The installed skill is a COPY. Scientists start `claude` outside this folder, so Claude Code runs
# that copy, which can be older than this checkout's. Compare them (ignoring checkout-path.txt and
# Finder files); read-only.
skill_state() {
  local src="$CHECKOUT/.claude/skills/$SKILL_NAME" dest="$SKILL_DIR/$SKILL_NAME" recorded=""
  if [[ ! -f "$dest/SKILL.md" ]]; then
    echo "$SKIP skill not installed at $dest (re-run with --install-skill)"; return
  fi
  if [[ ! -f "$src/SKILL.md" ]]; then
    echo "$OK skill installed at $dest (this checkout has no copy to compare with)"; return
  fi
  [[ -f "$dest/checkout-path.txt" ]] && recorded="$(head -n 1 "$dest/checkout-path.txt")"
  if ! diff -rq -x checkout-path.txt -x .DS_Store "$src" "$dest" >/dev/null 2>&1; then
    echo "[stale] skill at $dest differs from this checkout's copy, so Claude Code is using other instructions. Refresh: scripts/setup_isaac_local.sh --install-skill (then restart Claude Code)"
  elif [[ "$recorded" != "$CHECKOUT" ]]; then
    echo "[stale] skill at $dest points at another ISAAC folder (${recorded:-none recorded}). Refresh from this one: scripts/setup_isaac_local.sh --install-skill"
  else
    echo "$OK skill installed at $dest, same as this checkout's"
  fi
}

if [[ $CHECK_ONLY -eq 0 && $WITH_CLI -eq 1 ]]; then
  # A Python >= 3.11 must exist, or uv must be able to fetch one. Explain, don't guess.
  if [[ ! -x "$VENV/bin/python" ]] && ! command -v uv >/dev/null 2>&1; then
    found=""
    for c in python3.11 python3.12 python3.13 python3; do
      if command -v "$c" >/dev/null 2>&1 && version_ok "$(command -v "$c")"; then found="$c"; break; fi
    done
    if [[ -z "$found" ]]; then
      cat >&2 <<'MSG'
error: this Mac has no Python 3.11 or newer, and no `uv` to fetch one. Nothing was changed.
Pick ONE of these, then run this script again:
  - install uv (a small installer, no admin rights):  curl -LsSf https://astral.sh/uv/install.sh | sh
  - or install Python 3.11+ from https://www.python.org/downloads/ (or `brew install python@3.11`)
MSG
      exit 2
    fi
  fi
  echo "== 1/4 ISAAC command-line tools"
  if bash "$CHECKOUT/scripts/install_local_cli.sh"; then :; else
    echo "error: the command-line install failed; see the message above." >&2; PROBLEMS=$((PROBLEMS+1))
  fi
fi

if [[ $CHECK_ONLY -eq 0 && $WITH_PROCESSING -eq 1 && $WITH_CLI -eq 1 && -x "$VENV/bin/python" ]]; then
  echo "== 2/4 Spectrum processing (numpy, xraylarch; a larger download)"
  if have_processing; then echo "Already installed."; else
    "$VENV/bin/python" -m pip install --quiet -e "$CHECKOUT[processing]" \
      || { echo "warning: the processing extra did not install; everything else still works." >&2; }
  fi
fi

if [[ $CHECK_ONLY -eq 0 && $WITH_PORTAL -eq 1 ]]; then
  echo "== 3/4 Offline portal validator (pinned upstream commit)"
  if have_portal; then echo "Already installed."; else
    bash "$CHECKOUT/scripts/install_portal_validator.sh" \
      || { echo "warning: the portal validator did not install; records cannot become 'exportable' without it." >&2; }
  fi
fi

SKILL_STATE=""
if [[ $INSTALL_SKILL -eq 1 && $CHECK_ONLY -eq 0 ]]; then
  SRC="$CHECKOUT/.claude/skills/$SKILL_NAME"
  DEST="$SKILL_DIR/$SKILL_NAME"
  if [[ ! -f "$SRC/SKILL.md" ]]; then
    SKILL_STATE="$BAD the skill is missing from this checkout ($SRC)"; PROBLEMS=$((PROBLEMS+1))
  else
    echo "== 4/4 Claude Code skill"
    mkdir -p "$SKILL_DIR"
    TMP="$(mktemp -d "$SKILL_DIR/.${SKILL_NAME}.XXXXXX")"
    cp -R "$SRC/." "$TMP/"                       # a copy, never a link
    chmod 755 "$TMP"
    printf '%s\n' "$CHECKOUT" > "$TMP/checkout-path.txt"
    rm -rf "$DEST"
    mv "$TMP" "$DEST"
    echo "Copied to $DEST"
  fi
fi
[[ -n "$SKILL_STATE" ]] || SKILL_STATE="$(skill_state)"

# --- final checklist (what is true now, measured, not assumed) -------------------------------
echo
echo "================ ISAAC local setup: checklist ================"
if [[ -x "$VENV/bin/python" ]] && version_ok "$VENV/bin/python"; then
  echo "$OK Python environment   $("$VENV/bin/python" -V) in $VENV"
else
  echo "$BAD Python environment   none yet. Run: scripts/setup_isaac_local.sh"; PROBLEMS=$((PROBLEMS+1))
fi
if have_cli; then
  echo "$OK isaac command        $VENV/bin/isaac"
else
  echo "$BAD isaac command        not working. Run: scripts/setup_isaac_local.sh"; PROBLEMS=$((PROBLEMS+1))
fi
if have_processing; then echo "$OK processing           spectrum processing is available"
else echo "$BAD processing           not installed (curves and quality checks unavailable). Run: scripts/setup_isaac_local.sh --with-processing"; fi
if have_portal; then echo "$OK portal check         offline portal validator found"
else echo "$BAD portal check         not installed (records cannot become 'exportable'). Run: scripts/install_portal_validator.sh"; fi
echo "$SKILL_STATE"
echo
echo "Next steps:"
echo "  1. Check everything works end to end on made-up data:  scripts/isaac_selftest.sh"
echo "  2. In a terminal:  cd <your beamtime folder's parent>   then start Claude Code:  claude"
echo "  3. Ask:  /isaac-historical-import   (install the skill first with --install-skill if you have not)"
echo "Your data stays on this computer unless you let Claude read it; the skill asks you first."
[[ $PROBLEMS -eq 0 ]] || { echo; echo "Some required parts are missing (see [missing] above)."; exit 1; }
exit 0
