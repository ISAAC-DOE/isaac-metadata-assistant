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
#                                           (including whether an installed skill copy is out of date,
#                                           and whether this checkout is behind GitHub's main: a
#                                           `git fetch` that downloads code and sends no data)
#   --update                                bring this checkout up to GitHub's main (fast-forward only:
#                                           refused with local changes, on another branch or diverged),
#                                           then re-install the skill
#   --offline                               skip the GitHub check (no network at all)
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
# repository at one pinned commit (step 3), and, if uv has to make a Python, a Python build;
# and, unless --offline, the latest ISAAC code record from this checkout's `origin` (a `git fetch`,
# to say whether this folder is behind; it changes no file of yours and sends no data).
# What it never does: sudo, change system Python, edit your shell profile, upload or send anything.
set -uo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$CHECKOUT/.venv"
SKILL_NAME="isaac-historical-import"
WITH_PROCESSING=1; WITH_PORTAL=1; WITH_CLI=1; INSTALL_SKILL=0; CHECK_ONLY=0; UPDATE=0; OFFLINE=0
SKILL_DIR="$HOME/.claude/skills"
MAIN_BRANCH="main"
#: seconds the GitHub check may take before it is skipped (never a failure)
FETCH_TIMEOUT="${ISAAC_FETCH_TIMEOUT:-15}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-processing) WITH_PROCESSING=1 ;;
    --skip-processing) WITH_PROCESSING=0 ;;
    --skip-portal) WITH_PORTAL=0 ;;
    --skip-cli) WITH_CLI=0 ;;
    --install-skill) INSTALL_SKILL=1 ;;
    --skill-dir) shift; SKILL_DIR="${1:?--skill-dir needs a folder}" ;;
    --check) CHECK_ONLY=1 ;;
    --update) UPDATE=1 ;;
    --offline) OFFLINE=1 ;;
    -h|--help) sed -n '2,33p' "${BASH_SOURCE[0]}"; exit 0 ;;
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
    echo "[stale] skill at $dest differs from this checkout's copy, so Claude Code is using other instructions. Refresh: scripts/setup_isaac_local.sh --install-skill (then re-read its SKILL.md; no restart needed)"
  elif [[ "$recorded" != "$CHECKOUT" ]]; then
    echo "[stale] skill at $dest points at another ISAAC folder (${recorded:-none recorded}). Refresh from this one: scripts/setup_isaac_local.sh --install-skill"
  else
    echo "$OK skill installed at $dest, same as this checkout's"
  fi
}

# --- is this checkout behind GitHub's main? ----------------------------------------------------
# `git fetch` downloads the code record only (no file of yours changes, nothing is sent but the
# request). Never prompts for a password, never fails the check: offline is a [skipped] line.
g() { git -C "$CHECKOUT" "$@"; }
is_git_checkout() { [[ "$(g rev-parse --show-toplevel 2>/dev/null)" == "$(cd "$CHECKOUT" && pwd -P)" ]]; }

# run "$@" for at most $1 seconds (macOS has no `timeout`); its exit status, or 124 when cut off
with_timeout() {
  local secs="$1"; shift
  "$@" & local pid=$!
  ( trap 'exit 0' TERM; local n=0; while (( n < secs * 10 )); do sleep 0.1; kill -0 "$pid" 2>/dev/null || exit 0; n=$((n+1)); done
    kill "$pid" 2>/dev/null ) &
  local watcher=$!
  wait "$pid"; local rc=$?
  if kill -0 "$watcher" 2>/dev/null; then kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null; else wait "$watcher" 2>/dev/null; fi
  [[ $rc -eq 143 ]] && rc=124
  return $rc
}

fetch_main() {
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/echo GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" \
    with_timeout "$FETCH_TIMEOUT" git -C "$CHECKOUT" fetch --quiet origin "+refs/heads/$MAIN_BRANCH:refs/remotes/origin/$MAIN_BRANCH" >/dev/null 2>&1
}

# why `--update` would refuse right now (empty when it would not); call after a fetch
update_refusal() {
  local branch ahead
  branch="$(g symbolic-ref --short -q HEAD 2>/dev/null)"
  if [[ "$branch" != "$MAIN_BRANCH" ]]; then
    if [[ -n "$branch" ]]; then echo "this folder is on branch \"$branch\", not $MAIN_BRANCH"
    else echo "this folder is on no branch (a detached commit), not $MAIN_BRANCH"; fi
    return
  fi
  if [[ -n "$(g status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
    echo "this folder has local changes to ISAAC's files (git status lists them); they would be at risk"; return
  fi
  ahead="$(g rev-list --count "origin/$MAIN_BRANCH..HEAD" 2>/dev/null || echo 0)"
  if [[ "$ahead" != "0" ]]; then
    echo "this folder has $ahead local commit(s) that are not on GitHub's $MAIN_BRANCH (it has diverged)"; return
  fi
}

update_state() {
  if [[ $OFFLINE -eq 1 ]]; then echo "$SKIP update check  --offline: not compared with GitHub"; return; fi
  if ! is_git_checkout; then echo "$SKIP update check  not a git checkout, so it cannot be compared with GitHub"; return; fi
  if ! g remote get-url origin >/dev/null 2>&1; then echo "$SKIP update check  this checkout has no 'origin' to compare with"; return; fi
  if ! fetch_main; then echo "$SKIP update check  offline or GitHub not reachable; using the ISAAC code as it is"; return; fi
  local behind why
  behind="$(g rev-list --count "HEAD..origin/$MAIN_BRANCH" 2>/dev/null)" || {
    echo "$SKIP update check  could not compare with origin/$MAIN_BRANCH"; return; }
  if [[ "$behind" == "0" ]]; then
    local branch ahead extra=""
    branch="$(g symbolic-ref --short -q HEAD 2>/dev/null)"
    ahead="$(g rev-list --count "origin/$MAIN_BRANCH..HEAD" 2>/dev/null || echo 0)"
    [[ "$branch" == "$MAIN_BRANCH" ]] || extra=" (on ${branch:-a detached commit}, not $MAIN_BRANCH)"
    [[ "$ahead" == "0" ]] || extra="$extra, plus $ahead local commit(s)"
    echo "$OK update check     has everything on GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD))$extra"; return
  fi
  why="$(update_refusal)"
  echo "[behind $behind commits] update check  this ISAAC folder is $behind updates behind GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD) here). Update: scripts/setup_isaac_local.sh --update${why:+ (it would refuse now: $why)}"
}

# --update: fast-forward to GitHub's main, then re-install the skill with the UPDATED script
if [[ $UPDATE -eq 1 ]]; then
  refuse() { echo "Not updated: $1. Nothing was changed." >&2; exit 3; }
  is_git_checkout || refuse "$CHECKOUT is not a git checkout"
  g remote get-url origin >/dev/null 2>&1 || refuse "this checkout has no 'origin' to update from"
  fetch_main || refuse "GitHub could not be reached (offline?)"
  why="$(update_refusal)"; [[ -z "$why" ]] || refuse "$why"
  before="$(g rev-parse HEAD)"
  behind="$(g rev-list --count "HEAD..origin/$MAIN_BRANCH")"
  if [[ "$behind" == "0" ]]; then
    echo "Already up to date with GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD))."
  else
    g merge --ff-only --quiet "origin/$MAIN_BRANCH" >/dev/null 2>&1 || refuse "the fast-forward failed (a file here would be overwritten); nothing was merged"
    echo "Updated $behind commits: $(g rev-parse --short "$before") -> $(g rev-parse --short HEAD) (code only; no data was touched)."
  fi
  args=(--install-skill --skill-dir "$SKILL_DIR" --offline --skip-portal)
  if g diff --quiet "$before" HEAD -- pyproject.toml scripts/install_local_cli.sh 2>/dev/null; then
    args+=(--skip-cli)          # same dependencies: the editable install already runs the new code
  else
    echo "Its dependencies changed, so the ISAAC tools are refreshed too."
    have_processing || args+=(--skip-processing)
  fi
  exec bash "$CHECKOUT/scripts/setup_isaac_local.sh" "${args[@]}"
fi

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
UPDATE_STATE="$(update_state)"

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
echo "$UPDATE_STATE"
echo
echo "Next steps:"
echo "  1. Check everything works end to end on made-up data:  scripts/isaac_selftest.sh"
echo "  2. In a terminal:  cd <your beamtime folder's parent>   then start Claude Code:  claude"
echo "  3. Ask:  /isaac-historical-import   (install the skill first with --install-skill if you have not)"
echo "Your data stays on this computer unless you let Claude read it; the skill asks you first."
[[ $PROBLEMS -eq 0 ]] || { echo; echo "Some required parts are missing (see [missing] above)."; exit 1; }
exit 0
