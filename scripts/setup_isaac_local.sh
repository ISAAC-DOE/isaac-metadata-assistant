#!/usr/bin/env bash
# One-command setup of the local-first ISAAC historical-import tools on a Mac (or Linux).
#
#   scripts/setup_isaac_local.sh [options]
#
#   --with-processing / --skip-processing   install the spectrum-processing extra (default: install)
#   --skip-portal                           do not install the offline portal validator
#   --skip-cli                              do not (re)install the CLI (use with --install-skill alone)
#   --install-skill                         copy the Claude Code skill into ~/.claude/skills
#   --refresh-skill                         ONLY re-copy the skill (no Python packages, no portal validator,
#                                           no network): what a stale skill copy needs
#   --skill-dir DIR                         where skills go (default: ~/.claude/skills; a project's own
#                                           .claude/skills works too)
#   --check                                 change nothing; only report what is and is not installed
#                                           (including whether an installed skill copy is out of date,
#                                           and whether this checkout is behind GitHub's main: a
#                                           `git fetch` that changes no file in your ISAAC folder (it
#                                           updates git's record of what's on GitHub) and sends no data)
#   --update                                bring this checkout up to GitHub's main (fast-forward only:
#                                           refused with local changes, on another branch, diverged, or
#                                           when it would replace a file git does not track, such as
#                                           your data in examples/), then re-copy the skill
#   --offline                               skip the GitHub check (no network at all)
#   -h, --help
#
# ISAAC_FETCH_TIMEOUT=<seconds> (a whole number; default 15) bounds the GitHub check.
#
# What it does (idempotent; safe to re-run; needs no sudo):
#   1. a Python 3.11 virtual environment in <this checkout>/.venv (uv if present, else
#      python3.11/python3) and the `isaac` command              -> scripts/install_local_cli.sh,
#      with the small PDF-reading extra (pypdf, for the quote check) -> pip install -e ".[reading]"
#   2. the processing extra (numpy, xraylarch)                 -> pip install -e ".[processing]"
#   3. the offline portal validator's packages (it ships in vendor/isaac-portal-validator/, pinned;
#      nothing is cloned)                                         -> scripts/install_portal_validator.sh
#   4. optionally, the skill, COPIED (not linked) into the skills folder, with a small
#      checkout-path.txt so the skill can find this installation. Every run that changes anything also
#      writes .claude/skills/isaac-historical-import/checkout-path.txt (this folder's path; gitignored),
#      which the skill reads when Claude Code is started in this folder.
#
# What it downloads: packages from the Python package index (steps 1-3), and, if uv has to make a
# Python, a Python build;
# and, unless --offline, the latest ISAAC code record from this checkout's `origin` (a `git fetch`,
# to say whether this folder is behind; it changes no file in your ISAAC folder (it updates git's
# record of what's on GitHub) and sends no data).
# What it never does: sudo, change system Python, edit your shell profile, upload or send anything.
set -uo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$CHECKOUT/.venv"
SKILL_NAME="isaac-historical-import"
WITH_PROCESSING=1; WITH_PORTAL=1; WITH_CLI=1; INSTALL_SKILL=0; CHECK_ONLY=0; UPDATE=0; OFFLINE=0; REFRESH_SKILL=0
DEFAULT_SKILL_DIR="$HOME/.claude/skills"
SKILL_DIR="$DEFAULT_SKILL_DIR"
MAIN_BRANCH="main"
#: the repository `origin` normally is; another one (a fork) is compared with, and said
CANONICAL_REPO="ISAAC-DOE/isaac-metadata-assistant"
#: seconds the GitHub check may take before it is skipped (never a failure); a bad value is the default
FETCH_TIMEOUT="${ISAAC_FETCH_TIMEOUT:-15}"
[[ "$FETCH_TIMEOUT" =~ ^[1-9][0-9]{0,3}$ ]] || FETCH_TIMEOUT=15

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-processing) WITH_PROCESSING=1 ;;
    --skip-processing) WITH_PROCESSING=0 ;;
    --skip-portal) WITH_PORTAL=0 ;;
    --skip-cli) WITH_CLI=0 ;;
    --install-skill) INSTALL_SKILL=1 ;;
    --refresh-skill) REFRESH_SKILL=1 ;;
    --skill-dir) shift; SKILL_DIR="${1:?--skill-dir needs a folder}" ;;
    --check) CHECK_ONLY=1 ;;
    --update) UPDATE=1 ;;
    --offline) OFFLINE=1 ;;
    -h|--help) sed -n '2,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# --check never changes anything, so it is never combined with an option that does
if [[ $CHECK_ONLY -eq 1 && ( $UPDATE -eq 1 || $REFRESH_SKILL -eq 1 || $INSTALL_SKILL -eq 1 ) ]]; then
  echo "error: --check changes nothing, so it cannot be combined with --update, --refresh-skill or --install-skill. Run them separately." >&2
  exit 2
fi
if [[ $UPDATE -eq 1 && $REFRESH_SKILL -eq 1 ]]; then
  echo "error: --update already re-copies the skill; pass one of --update or --refresh-skill." >&2
  exit 2
fi
# --refresh-skill: the skill copy and nothing else (no package index, no GitHub, no portal validator)
if [[ $REFRESH_SKILL -eq 1 ]]; then INSTALL_SKILL=1; WITH_CLI=0; WITH_PORTAL=0; WITH_PROCESSING=0; OFFLINE=1; fi
# the --skill-dir to repeat in a suggested command (empty for the default folder)
SKILL_DIR_ARG=""
[[ "$SKILL_DIR" == "$DEFAULT_SKILL_DIR" ]] || SKILL_DIR_ARG=" --skill-dir \"$SKILL_DIR\""

OK="[ok]"; BAD="[missing]"; SKIP="[skipped]"
FINAL=()          # checklist lines
PROBLEMS=0
note() { FINAL+=("$1"); }

version_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }
is_311()     { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' 2>/dev/null; }

if [[ ! -f "$CHECKOUT/schema/isaac_record_v1.json" || ! -d "$CHECKOUT/apps/api/isaac_api" ]]; then
  echo "error: $CHECKOUT does not look like an ISAAC folder (schema/ or apps/api/ missing)." >&2
  exit 2
fi

# The Python that runs the ISAAC tools: this folder's .venv. In a git WORKTREE that has none (a second
# working folder of the same repository), the main checkout's .venv is used, with THIS folder's code put
# first on its path (PYTHONPATH), so what is checked is this folder's code. Set once more after step 1.
PYBIN="$VENV/bin/python"; PYPATH=""; VENV_NOTE=""
main_checkout() {   # the main checkout of a git worktree, else nothing
  local common
  common="$(git -C "$CHECKOUT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 0
  [[ "$(basename "$common")" == ".git" ]] || return 0
  common="$(dirname "$common")"
  [[ "$(cd "$common" 2>/dev/null && pwd -P)" != "$(cd "$CHECKOUT" && pwd -P)" ]] && printf '%s' "$common"
}
pick_python() {
  PYBIN="$VENV/bin/python"; PYPATH=""; VENV_NOTE=""
  [[ -x "$PYBIN" ]] && return 0
  local main; main="$(main_checkout)"
  if [[ -n "$main" && -x "$main/.venv/bin/python" ]]; then
    PYBIN="$main/.venv/bin/python"; PYPATH="$CHECKOUT/src:$CHECKOUT/apps/api"
    VENV_NOTE=" (this is a git worktree with no .venv of its own: using the main checkout's, $main/.venv, with this folder's code first; to give it its own, run scripts/setup_isaac_local.sh here)"
  fi
}
pick_python
py() { ( cd / && if [[ -n "$PYPATH" ]]; then PYTHONPATH="$PYPATH" "$PYBIN" "$@"; else "$PYBIN" "$@"; fi ); }

have_cli()        { py -c 'import isaac_api.local_import.cli, isaac_records.cli' >/dev/null 2>&1; }
have_processing() { py -c 'import numpy, larch' >/dev/null 2>&1; }
have_reading()    { py -c 'import pypdf' >/dev/null 2>&1; }
# the offline portal check, as `isaac bundle validate` itself finds it (env vars, the cache, then the copy
# vendored in this repository): one line "ok <source> <commit> <python>" or "no <reason>"
portal_state()    {
  py -c '
from isaac_api.local_import import portal as P
w = P.locate()
print("ok %s %s %s" % (w["source"], w["commit"][:7], w["python"]) if w["available"] else "no " + w["reason"])
' 2>/dev/null || echo "no the ISAAC tools are not installed, so the portal check cannot be looked for"
}
have_portal()     { [[ "$(portal_state)" == ok\ * ]]; }
# poppler's pdftoppm: lets Claude look at a PDF's pages as images (scanned logbooks). Optional.
pdftoppm_path()   { command -v pdftoppm 2>/dev/null || { for d in /opt/homebrew/bin /usr/local/bin; do [[ -x "$d/pdftoppm" ]] && { echo "$d/pdftoppm"; return; }; done; }; }

# The skill's Step 0 reads checkout-path.txt BESIDE its SKILL.md to find this folder. Claude Code started
# in this folder runs this checkout's own copy, so the file is written there too (gitignored: a local path).
OWN_SKILL="$CHECKOUT/.claude/skills/$SKILL_NAME"
write_own_checkout_path() {
  [[ -f "$OWN_SKILL/SKILL.md" ]] || return 0
  [[ "$(head -n 1 "$OWN_SKILL/checkout-path.txt" 2>/dev/null)" == "$CHECKOUT" ]] && return 0
  printf '%s\n' "$CHECKOUT" > "$OWN_SKILL/checkout-path.txt" 2>/dev/null \
    || echo "warning: could not write $OWN_SKILL/checkout-path.txt; the skill will ask where this folder is." >&2
}
own_checkout_path_state() {
  if [[ ! -f "$OWN_SKILL/SKILL.md" ]]; then echo "$SKIP skill path file  this checkout has no skill folder"
  elif [[ "$(head -n 1 "$OWN_SKILL/checkout-path.txt" 2>/dev/null)" == "$CHECKOUT" ]]; then
    echo "$OK skill path file     $OWN_SKILL/checkout-path.txt points here"
  else
    echo "$BAD skill path file     $OWN_SKILL/checkout-path.txt is missing or points elsewhere, so the skill will ask where this folder is. Write it (changes nothing else): scripts/setup_isaac_local.sh --refresh-skill --skill-dir \"$CHECKOUT/.claude/skills\""
  fi
}

# The installed skill is a COPY. Scientists start `claude` outside this folder, so Claude Code runs
# that copy, which can be older than this checkout's. Compare them (ignoring checkout-path.txt and
# Finder files); read-only.
skill_state() {
  local src="$CHECKOUT/.claude/skills/$SKILL_NAME" dest="$SKILL_DIR/$SKILL_NAME" recorded=""
  if [[ ! -f "$dest/SKILL.md" ]]; then
    if [[ "$SKILL_DIR" == "$DEFAULT_SKILL_DIR" && -f "$src/SKILL.md" ]]; then
      # the usual way: Claude Code started IN this folder uses this folder's own copy; no other copy to go stale
      echo "$OK skill                this folder's own copy ($src) is used when Claude Code is started in this folder (to use it from any folder too: scripts/setup_isaac_local.sh --install-skill)"
    else
      echo "$SKIP skill not installed at $dest (copy it: scripts/setup_isaac_local.sh --refresh-skill$SKILL_DIR_ARG)"
    fi
    return
  fi
  if [[ ! -f "$src/SKILL.md" ]]; then
    echo "$OK skill installed at $dest (this checkout has no copy to compare with)"; return
  fi
  if [[ "$(cd "$dest" && pwd -P)" == "$(cd "$src" && pwd -P)" ]]; then
    echo "$OK skill at $dest is this checkout's own copy (always current)"; return
  fi
  [[ -f "$dest/checkout-path.txt" ]] && recorded="$(head -n 1 "$dest/checkout-path.txt")"
  if ! diff -rq -x checkout-path.txt -x .DS_Store "$src" "$dest" >/dev/null 2>&1; then
    echo "[stale] skill at $dest differs from this checkout's copy, so Claude Code is using other instructions. Refresh (copies the skill only): scripts/setup_isaac_local.sh --refresh-skill$SKILL_DIR_ARG (then re-read $dest/SKILL.md; no restart needed)"
  elif [[ "$recorded" != "$CHECKOUT" ]]; then
    echo "[stale] skill at $dest points at another ISAAC folder (${recorded:-none recorded}). Refresh from this one (copies the skill only): scripts/setup_isaac_local.sh --refresh-skill$SKILL_DIR_ARG"
  else
    echo "$OK skill installed at $dest, same as this checkout's"
  fi
}

# --- is this checkout behind GitHub's main? ----------------------------------------------------
# `git fetch` downloads the code record only: it changes no file in your ISAAC folder (it updates
# git's record of what's on GitHub), and sends nothing but the request. Never prompts for a
# password, never fails the check: an unreachable GitHub is a [skipped] line.
g() { git -C "$CHECKOUT" "$@"; }
is_git_checkout() { [[ "$(g rev-parse --show-toplevel 2>/dev/null)" == "$(cd "$CHECKOUT" && pwd -P)" ]]; }

# Ctrl-C, a TERM or a hang-up stops the script with the usual status (130, 143, 129). Set at the top
# level so a shell waiting for `$(...)` stops too once that subshell has cleaned up.
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP

# run "$@" for at most $1 seconds (macOS has no `timeout`); its exit status, or 124 when cut off.
# The command runs in its OWN process group (job control on for that one start). A timeout, Ctrl-C, a
# TERM or a hang-up kills the whole group, so a helper git started (ssh, a transport) is never left
# running. "Cut off" is known from the watcher's own flag file, never guessed from an exit status.
WT_PID=""; WT_WATCHER=""; WT_FLAGDIR=""
_wt_stop() {   # $1: the exit status for the signal that arrived
  [[ -n "$WT_WATCHER" ]] && kill "$WT_WATCHER" 2>/dev/null
  if [[ -n "$WT_PID" ]]; then
    kill -TERM -- "-$WT_PID" 2>/dev/null; sleep 0.2; kill -KILL -- "-$WT_PID" 2>/dev/null
  fi
  [[ -n "$WT_FLAGDIR" ]] && rm -rf "$WT_FLAGDIR"
  exit "$1"
}
with_timeout() {
  local secs="$1"; shift
  local rc flag
  WT_FLAGDIR="$(mktemp -d "${TMPDIR:-/tmp}/isaac-timeout.XXXXXX")" || return 1
  flag="$WT_FLAGDIR/fired"
  trap '_wt_stop 130' INT; trap '_wt_stop 143' TERM; trap '_wt_stop 129' HUP
  set -m
  "$@" & WT_PID=$!
  set +m
  ( trap 'exit 0' TERM; n=0; while (( n < secs * 10 )); do sleep 0.1; kill -0 "$WT_PID" 2>/dev/null || exit 0; n=$((n+1)); done
    : > "$flag"; kill -TERM -- "-$WT_PID" 2>/dev/null ) &
  WT_WATCHER=$!
  wait "$WT_PID" 2>/dev/null; rc=$?
  if kill -0 "$WT_WATCHER" 2>/dev/null; then kill "$WT_WATCHER" 2>/dev/null; fi
  wait "$WT_WATCHER" 2>/dev/null
  # the group's leader has ended, however it ended: anything it left behind in its group goes too
  kill -KILL -- "-$WT_PID" 2>/dev/null
  [[ -e "$flag" ]] && rc=124
  rm -rf "$WT_FLAGDIR"
  WT_PID=""; WT_WATCHER=""; WT_FLAGDIR=""
  trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
  return $rc
}

# a URL without any user name or token in it, to print
plain_url() { printf '%s' "$1" | sed -E 's#^([a-zA-Z][a-zA-Z0-9+.-]*://)[^@/]*@#\1#'; }
ORIGIN_URL=""
FETCH_ERR=""     # why the last fetch failed: "timeout", "no_main" or "unreachable"
USER_SSH=0       # 1 when the user's own ssh command (core.sshCommand, GIT_SSH_COMMAND, GIT_SSH) is used

# The user's own ssh setup wins: only when neither GIT_SSH_COMMAND, GIT_SSH nor core.sshCommand is set
# is ssh told not to prompt (BatchMode) and to give up connecting after a few seconds. With their own
# command, a passphrase prompt cannot be shown (the fetch runs in the background), so a failure says so.
fetch_main() {
  local err rc askpass=/usr/bin/true
  [[ -x "$askpass" ]] || askpass=/bin/true
  local -a env_add=(GIT_TERMINAL_PROMPT=0 "GIT_ASKPASS=$askpass" "SSH_ASKPASS=$askpass")
  if [[ -z "${GIT_SSH_COMMAND:-}" && -z "${GIT_SSH:-}" && -z "$(g config --get core.sshCommand 2>/dev/null)" ]]; then
    USER_SSH=0
    env_add+=("GIT_SSH_COMMAND=ssh -o BatchMode=yes -o ConnectTimeout=$(( FETCH_TIMEOUT < 10 ? FETCH_TIMEOUT : 10 ))")
  else
    USER_SSH=1
  fi
  err="$(mktemp "${TMPDIR:-/tmp}/isaac-fetch.XXXXXX")" || return 1
  with_timeout "$FETCH_TIMEOUT" env "${env_add[@]}" git -C "$CHECKOUT" \
    -c http.lowSpeedLimit=1000 -c "http.lowSpeedTime=$FETCH_TIMEOUT" \
    fetch --quiet origin "+refs/heads/$MAIN_BRANCH:refs/remotes/origin/$MAIN_BRANCH" >/dev/null 2>"$err" </dev/null
  rc=$?
  if (( rc == 0 )); then FETCH_ERR=""
  elif (( rc == 124 )); then FETCH_ERR="timeout"
  elif grep -qi "couldn't find remote ref\|could not find remote ref" "$err" 2>/dev/null; then FETCH_ERR="no_main"
  else FETCH_ERR="unreachable"; fi
  rm -f "$err"
  return $rc
}

# the fetch failure in plain words (after fetch_main failed)
fetch_failure() {
  local ssh_note=""
  (( USER_SSH == 1 )) && ssh_note="; your own ssh command is used, and a passphrase prompt cannot be shown during the check: unlock your key first (ssh-add) or pass --offline"
  case "$FETCH_ERR" in
    timeout) echo "GitHub did not answer within ${FETCH_TIMEOUT}s (origin: $(plain_url "$ORIGIN_URL"))$ssh_note" ;;
    no_main) echo "origin ($(plain_url "$ORIGIN_URL")) has no '$MAIN_BRANCH' branch to compare with (a fork or another repository?)" ;;
    *) echo "could not reach GitHub (origin: $(plain_url "$ORIGIN_URL"); offline, or the address does not answer)$ssh_note" ;;
  esac
}

# " (origin is <url>, not ISAAC-DOE/...)" when origin is not the ISAAC repository (a fork), else empty
origin_note() {
  case "$ORIGIN_URL" in
    *"$CANONICAL_REPO"|*"$CANONICAL_REPO.git"|*"$CANONICAL_REPO/") ;;
    *) printf ' (origin is %s, not github.com/%s: compared with that)' "$(plain_url "$ORIGIN_URL")" "$CANONICAL_REPO" ;;
  esac
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

# Does git see something it does NOT track (untracked or ignored) at exactly this path, or inside it
# when it is a folder? Asked of git, not of the filesystem, so a TRACKED file is never counted, even
# under a case-folded name on a case-insensitive disk (an upstream Foo.txt -> foo.txt rename).
untracked_at() {
  [[ -n "$( { g ls-files --others --exclude-standard -- ":(literal)$1"
              g ls-files --others --ignored --exclude-standard -- ":(literal)$1"; } 2>/dev/null | head -n 1)" ]]
}

# Paths the incoming commits ADD where this folder holds something git does not track: an untracked or
# ignored file or folder at that exact path (e.g. your data in examples/), or an untracked/ignored FILE
# where the update needs a folder. A fast-forward would replace or remove them, so --update refuses.
# A tracked file that the update turns into a folder is git's own business, never counted.
# NUL-separated, one per path.
incoming_collisions() {
  local p d
  while IFS= read -r -d '' p; do
    [[ -n "$p" ]] || continue
    if untracked_at "$p"; then printf '%s\0' "$p"; continue; fi
    d="$(dirname "$p")"
    while [[ "$d" != "." && "$d" != "/" ]]; do
      if [[ -L "$CHECKOUT/$d" || ( -e "$CHECKOUT/$d" && ! -d "$CHECKOUT/$d" ) ]] && untracked_at "$d"; then
        printf '%s\0' "$d"; break
      fi
      d="$(dirname "$d")"
    done
  done < <(g diff -z --name-only --no-renames --diff-filter=A HEAD "origin/$MAIN_BRANCH" 2>/dev/null)
}

update_state() {
  if [[ $OFFLINE -eq 1 ]]; then echo "$SKIP update check  --offline: not compared with GitHub"; return; fi
  if ! is_git_checkout; then echo "$SKIP update check  not a git checkout, so it cannot be compared with GitHub"; return; fi
  ORIGIN_URL="$(g config --get remote.origin.url 2>/dev/null)" || { echo "$SKIP update check  this checkout has no 'origin' to compare with"; return; }
  if ! fetch_main; then echo "$SKIP update check  $(fetch_failure); using the ISAAC code as it is"; return; fi
  local behind why
  behind="$(g rev-list --count "HEAD..origin/$MAIN_BRANCH" 2>/dev/null)" || {
    echo "$SKIP update check  could not compare with origin/$MAIN_BRANCH"; return; }
  if [[ "$behind" == "0" ]]; then
    local branch ahead extra=""
    branch="$(g symbolic-ref --short -q HEAD 2>/dev/null)"
    ahead="$(g rev-list --count "origin/$MAIN_BRANCH..HEAD" 2>/dev/null || echo 0)"
    [[ "$branch" == "$MAIN_BRANCH" ]] || extra=" (on ${branch:-a detached commit}, not $MAIN_BRANCH)"
    [[ "$ahead" == "0" ]] || extra="$extra, plus $ahead local commit(s)"
    echo "$OK update check     has everything on GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD))$extra$(origin_note)"; return
  fi
  why="$(update_refusal)"
  [[ -n "$why" ]] || why="$(collision_refusal)"
  echo "[behind $behind commits] update check  this ISAAC folder is $behind updates behind GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD) here)$(origin_note). Update: scripts/setup_isaac_local.sh --update${why:+ (it would refuse now: $why)}"
}

# why --update must refuse because of files git does not track (empty when none). It names NO file:
# only how many and in which top-level folders ("the top folder" for one at the root), because a
# file's name can itself be data
collision_refusal() {
  local n=0 tops="" p top
  while IFS= read -r -d '' p; do
    n=$((n+1))
    if [[ "$p" == */* ]]; then top="${p%%/*}/"; else top="the top folder"; fi
    case ",$tops," in *",$top,"*) ;; *) tops="${tops:+$tops,}$top" ;; esac
  done < <(incoming_collisions)
  (( n == 0 )) && return
  echo "the update adds its own files where this folder holds $n file(s) or folder(s) that git does not track (in: ${tops//,/, }); they can be your own data and would be replaced or removed. Move them out of the ISAAC folder first"
}

# --update: fast-forward to GitHub's main, then re-install the skill with the UPDATED script
if [[ $UPDATE -eq 1 ]]; then
  refuse() { echo "Not updated: $1. Nothing was changed." >&2; exit 3; }
  is_git_checkout || refuse "$CHECKOUT is not a git checkout"
  ORIGIN_URL="$(g config --get remote.origin.url 2>/dev/null)" || refuse "this checkout has no 'origin' to update from"
  fetch_main || refuse "$(fetch_failure)"
  why="$(update_refusal)"; [[ -z "$why" ]] || refuse "$why"
  before="$(g rev-parse HEAD)"
  behind="$(g rev-list --count "HEAD..origin/$MAIN_BRANCH")"
  if [[ "$behind" == "0" ]]; then
    echo "Already up to date with GitHub's $MAIN_BRANCH ($(g rev-parse --short HEAD))$(origin_note)."
  else
    why="$(collision_refusal)"; [[ -z "$why" ]] || refuse "$why"
    # --no-overwrite-ignore: git otherwise replaces an IGNORED file (examples/ is ignored) without a word.
    # The check above already refused; this is the second lock.
    g merge --ff-only --no-overwrite-ignore --quiet "origin/$MAIN_BRANCH" >/dev/null 2>&1 \
      || refuse "the fast-forward failed (a file here would have been overwritten); nothing was merged"
    echo "Updated $behind commits: $(g rev-parse --short "$before") -> $(g rev-parse --short HEAD)$(origin_note) (code only; no data was touched)."
  fi
  # then the UPDATED script re-copies the skill (and nothing else: no download). The editable install
  # already runs the new code; when its dependencies changed, the tools refresh is said, not run.
  if ! g diff --quiet "$before" HEAD -- pyproject.toml scripts/install_local_cli.sh 2>/dev/null; then
    echo "Its Python dependencies changed. To refresh the ISAAC tools (downloads packages from the Python package index): scripts/setup_isaac_local.sh --skip-portal$( have_processing || printf ' --skip-processing')"
  fi
  exec bash "$CHECKOUT/scripts/setup_isaac_local.sh" --refresh-skill --skill-dir "$SKILL_DIR"
fi

if [[ $CHECK_ONLY -eq 0 && $WITH_CLI -eq 1 ]]; then
  # A Python 3.11 must exist, or uv must be able to fetch one. Explain, don't guess.
  if [[ ! -x "$VENV/bin/python" ]] && ! command -v uv >/dev/null 2>&1; then
    found=""
    for c in python3.11 python3; do
      if command -v "$c" >/dev/null 2>&1 && is_311 "$(command -v "$c")"; then found="$c"; break; fi
    done
    if [[ -z "$found" ]]; then
      cat >&2 <<'MSG'
error: this Mac has no Python 3.11, and no `uv` to fetch one. Nothing was changed.
Pick ONE of these, then run this script again:
  - install uv (a small installer, no admin rights):  curl -LsSf https://astral.sh/uv/install.sh | sh
  - or install Python 3.11 from https://www.python.org/downloads/ (or `brew install python@3.11`)
MSG
      exit 2
    fi
  fi
fi
# from here on this run changes things (--check never does, and every refusal above changed nothing)
[[ $CHECK_ONLY -eq 1 ]] || write_own_checkout_path

if [[ $CHECK_ONLY -eq 0 && $WITH_CLI -eq 1 ]]; then
  echo "== 1/4 ISAAC command-line tools"
  if bash "$CHECKOUT/scripts/install_local_cli.sh"; then :; else
    echo "error: the command-line install failed; see the message above." >&2; PROBLEMS=$((PROBLEMS+1))
  fi
  pick_python
  if [[ -x "$VENV/bin/python" ]] && ! have_reading; then
    "$VENV/bin/python" -m pip install --quiet -e "$CHECKOUT[reading]" \
      || { echo "warning: the PDF-reading extra (pypdf) did not install; quotes cited from a PDF cannot be checked." >&2; }
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
  echo "== 3/4 Offline portal validator (shipped in vendor/, pinned upstream commit; its packages go into .venv)"
  if [[ "$(portal_state)" == "ok vendored "* ]]; then echo "Already installed: $(portal_state | cut -d' ' -f2-)."
  elif [[ ! -x "$VENV/bin/python" ]]; then
    echo "warning: no $VENV yet (step 1 did not finish), so the portal validator's packages were not installed." >&2
  else
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
  elif [[ -d "$DEST" && "$(cd "$DEST" && pwd -P)" == "$(cd "$SRC" && pwd -P)" ]]; then
    # --skill-dir is this checkout's own .claude/skills: that IS the source, never replaced
    echo "== 4/4 Claude Code skill"
    echo "$DEST is this checkout's own copy of the skill; it is always current, nothing to copy."
    echo "Skill written to: $DEST/SKILL.md"
  else
    echo "== 4/4 Claude Code skill"
    # Atomic: build the new copy in a temp folder, move the old copy aside, move the new one in, and put
    # the old one back if that fails. Each message says what is true afterwards, never more.
    copy_failed() { echo "error: could not copy the skill into $SKILL_DIR ($1)." >&2; exit 1; }
    mkdir -p "$SKILL_DIR" || copy_failed "cannot make the folder; nothing there changed"
    TMP="$(mktemp -d "$SKILL_DIR/.${SKILL_NAME}.XXXXXX")" || copy_failed "cannot write there; nothing there changed"
    OLD="$TMP.old"
    if ! { cp -R "$SRC/." "$TMP/" && chmod 755 "$TMP" && printf '%s\n' "$CHECKOUT" > "$TMP/checkout-path.txt"; }; then
      rm -rf "$TMP"; copy_failed "the copy failed; the installed copy is unchanged"   # a copy, never a link
    fi
    if [[ -e "$DEST" || -L "$DEST" ]]; then
      mv "$DEST" "$OLD" || { rm -rf "$TMP"; copy_failed "could not move the old copy aside; it is unchanged"; }
    fi
    if ! mv "$TMP" "$DEST"; then
      rm -rf "$TMP"
      if [[ ! -e "$OLD" ]]; then copy_failed "could not move the new copy into place; there was no old copy"
      elif mv "$OLD" "$DEST"; then copy_failed "could not move the new copy into place; the old copy was put back"
      else copy_failed "could not move the new copy into place, nor put the old one back: it is at $OLD"; fi
    fi
    rm -rf "$OLD"
    echo "Copied to $DEST"
    # the exact file to re-read (a refreshed skill is followed from this path, wherever --skill-dir put it)
    echo "Skill written to: $DEST/SKILL.md"
  fi
fi
[[ -n "$SKILL_STATE" ]] || SKILL_STATE="$(skill_state)"
if [[ $REFRESH_SKILL -eq 1 ]]; then
  # --refresh-skill: only the skill line (nothing else was touched); exit 0 when the copy is current
  echo "$SKILL_STATE"
  [[ "$SKILL_STATE" == "$OK"* ]] && exit 0
  exit 1
fi
UPDATE_STATE="$(update_state)"

# --- final checklist (what is true now, measured, not assumed) -------------------------------
echo
echo "================ ISAAC local setup: checklist ================"
if [[ -x "$PYBIN" ]] && version_ok "$PYBIN"; then
  PY_NOTE=""
  is_311 "$PYBIN" || PY_NOTE=" (not 3.11, the version ISAAC is tested with; to rebuild on 3.11: move that .venv aside, then run scripts/setup_isaac_local.sh)"
  echo "$OK Python environment   $("$PYBIN" -V) in $(dirname "$(dirname "$PYBIN")")$PY_NOTE$VENV_NOTE"
else
  echo "$BAD Python environment   none yet. Run: scripts/setup_isaac_local.sh"; PROBLEMS=$((PROBLEMS+1))
fi
if have_cli; then
  echo "$OK isaac command        $(dirname "$PYBIN")/isaac"
else
  echo "$BAD isaac command        not working. Run: scripts/setup_isaac_local.sh"; PROBLEMS=$((PROBLEMS+1))
fi
if have_processing; then echo "$OK processing           spectrum processing is available"
else echo "$BAD processing           not installed (curves and quality checks unavailable). Run: scripts/setup_isaac_local.sh --with-processing"; fi
if have_reading; then echo "$OK pdf reading         PDF text for the quote check is available"
else echo "$BAD pdf reading         not installed (quotes cited from a PDF cannot be checked). Run: scripts/setup_isaac_local.sh"; fi
PORTAL_STATE="$(portal_state)"
if [[ "$PORTAL_STATE" == ok\ * ]]; then
  read -r _ p_source p_commit p_python <<<"$PORTAL_STATE"
  case "$p_source" in
    vendored) p_where="the copy shipped in vendor/isaac-portal-validator/" ;;
    *) p_where="the folder ISAAC_PORTAL_VALIDATOR_DIR names" ;;
  esac
  echo "$OK portal check         offline portal validator at $p_commit: $p_where, run with $p_python"
else
  echo "$BAD portal check         not ready (records cannot become 'exportable'): ${PORTAL_STATE#no }. Run: scripts/setup_isaac_local.sh"
fi
if [[ -n "$(pdftoppm_path)" ]]; then echo "$OK pdf pages           $(pdftoppm_path) (Claude can look at PDF pages as images)"
else echo "[optional] pdf pages    pdftoppm not found: Claude cannot look at scanned PDF pages as images (text PDFs still work). Install it with Homebrew: brew install poppler"; fi
own_checkout_path_state
echo "$SKILL_STATE"
echo "$UPDATE_STATE"
echo
echo "Next steps:"
echo "  1. Check everything works end to end on made-up data:  scripts/isaac_selftest.sh"
echo "  2. In this folder ($CHECKOUT) start Claude Code:  claude"
echo "  3. Type  /isaac-historical-import  and tell it where your beamtime folder is (it uses this folder's own copy of the skill)"
echo "Your data stays on this computer unless you let Claude read it; the skill asks you first."
[[ $PROBLEMS -eq 0 ]] || { echo; echo "Some required parts are missing (see [missing] above)."; exit 1; }
exit 0
