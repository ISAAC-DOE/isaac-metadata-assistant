#!/usr/bin/env bash
# End-to-end self-test of the local-first ISAAC import chain on SYNTHETIC data.
#
#   scripts/isaac_selftest.sh [--keep] [--isaac <path to isaac>]
#
# Runs, in a temporary folder, on tests/fixtures/bl15/semantics/multi_operator_corpus (made-up
# data, safe to show Claude): import, check, cross-check (plan, excerpt, blind annotate, reveal),
# group, process, decide, build-records, validate, export, upload --dry-run, and prints PASS,
# FAIL or SKIP for each step with the reason. Every decision it records is labelled
# "SYNTHETIC SELF-TEST (not a scientist)". It uploads nothing and needs no network.
#
# Exit 0: no step failed (skipped steps are listed, with what to install). Exit 1: a step failed.
# Exit 2: ISAAC is not installed (run scripts/setup_isaac_local.sh).
#
# A step the build does not have yet (grouping, processing) is SKIPPED with a notice and the steps
# that depend on it run in the form that is still meaningful (for example drafts that are
# incomplete are expected to be refused, and that refusal is asserted).
set -uo pipefail

CHECKOUT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC="${ISAAC_BIN:-$CHECKOUT/.venv/bin/isaac}"
KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --isaac) shift; ISAAC="${1:?--isaac needs a path}" ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
PY="${ISAAC_PYTHON:-$(dirname "$ISAAC")/python}"
[[ -x "$PY" ]] || PY="$(command -v python3)"
CORPUS="$CHECKOUT/tests/fixtures/bl15/semantics/multi_operator_corpus"
BY="SYNTHETIC SELF-TEST (not a scientist)"
MODEL="SYNTHETIC-SELF-TEST-MODEL"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/isaac-selftest.XXXXXX")"
cleanup() { if [[ $KEEP -eq 0 ]]; then rm -rf "$WORK"; else echo "Kept: $WORK"; fi; }
trap cleanup EXIT
BUNDLE="$WORK/bundle"; RECORDS="$WORK/records"; N=0; PASSED=0; FAILED=0; SKIPPED=0; RC=0; OUT=""

# Always run from a neutral folder, so a pass cannot depend on the current directory.
cd "$WORK" || exit 2

report() {  # $1 = PASS|FAIL|SKIP, $2 = name, $3 = detail
  case "$1" in PASS) PASSED=$((PASSED+1));; FAIL) FAILED=$((FAILED+1));; SKIP) SKIPPED=$((SKIPPED+1));; esac
  printf '%-5s %-34s %s\n' "$1" "$2" "${3:-}"
}
run() {  # run a command, keep stdout+stderr in $OUT and the exit code in $RC
  N=$((N+1)); OUT="$WORK/out.$N.txt"; "$@" >"$OUT" 2>&1; RC=$?
}
expect() {  # expect <name> <wanted exit code> <detail on pass>
  if [[ "$RC" -eq "$2" ]]; then report PASS "$1" "${3:-exit $RC}"; return 0; fi
  report FAIL "$1" "exit $RC, wanted $2: $(head -c 300 "$OUT" | tr '\n' ' ')"; return 1
}
json() {  # json <file> <python expression over d> ; prints the value
  "$PY" - "$1" "$2" <<'PYEND'
import json, sys
d = json.load(open(sys.argv[1]))
print(eval(sys.argv[2]))
PYEND
}
has() { "$ISAAC" "$@" --help >/dev/null 2>&1; }

echo "ISAAC self-test on SYNTHETIC data (nothing real, nothing sent)"
echo "isaac: $ISAAC"
if ! "$ISAAC" import --help >/dev/null 2>&1 || "$ISAAC" import --help 2>&1 | grep -q "need the ISAAC local import package"; then
  echo "error: ISAAC is not installed for this checkout. Run: scripts/setup_isaac_local.sh" >&2; exit 2
fi
[[ -d "$CORPUS" ]] || { echo "error: the synthetic corpus is missing at $CORPUS" >&2; exit 2; }
echo

# 1. import -------------------------------------------------------------------------------------
run "$ISAAC" import "$CORPUS" --out "$BUNDLE"
if expect "import" 0 && [[ -f "$BUNDLE/bundle.json" && -f "$BUNDLE/summary.md" ]] && grep -q "NOT a validated official ISAAC record" "$OUT"; then
  report PASS "import: files + honesty line" "bundle.json, summary.md; says it is not an official record"
else report FAIL "import: files + honesty line" "bundle files or the honesty line are missing"; fi
RUNS="$(json "$BUNDLE/bundle.json" "len(d['runs'])" 2>/dev/null || echo 0)"
if [[ "$RUNS" -gt 0 ]]; then report PASS "import: found runs" "$RUNS runs"; else report FAIL "import: found runs" "0 runs"; fi

# 2. data minimisation + bundle check -------------------------------------------------------------
if ! grep -q "$CHECKOUT" "$BUNDLE/bundle.json" && [[ "$(json "$BUNDLE/bundle.json" "d['source_root'].get('local_root_hint')")" == "None" ]]; then
  report PASS "no local path recorded" "no absolute path in the bundle (data minimisation)"
else report FAIL "no local path recorded" "the bundle contains this computer's path"; fi
run "$ISAAC" bundle check "$BUNDLE"; expect "bundle check" 0 "bundle meets the v1 contract"

# 3. blind cross-check ----------------------------------------------------------------------------
run "$ISAAC" bundle crosscheck-plan "$BUNDLE" --limit 200
expect "crosscheck-plan" 0 "plan with coverage, no values" || true
cp "$OUT" "$WORK/plan.json"
TARGET="$(json "$WORK/plan.json" "next((i['target']['id'] for i in d['items'] if i['target']['kind']=='candidate'), d['items'][0]['target']['id'])" 2>/dev/null)"
if [[ -n "$TARGET" ]]; then
  run "$ISAAC" bundle excerpt "$BUNDLE" "$TARGET" --source "$CORPUS"; expect "excerpt (raw text, no parser value)" 0 "target $TARGET"
  run "$ISAAC" bundle annotate "$BUNDLE" --target "$TARGET" --value "synthetic reading" --excerpt-locator "synthetic locator" --model "$MODEL" --blind --rationale "SYNTHETIC SELF-TEST"
  expect "annotate --blind" 0 "" >/dev/null
  BL="$(json "$BUNDLE/bundle.json" "[a for a in d['ai_interpretations'] if a['target']['id']=='$TARGET'][-1]['blind']" 2>/dev/null)"
  if [[ "$BL" == "True" ]]; then report PASS "annotate --blind is blind" "no value had been shown for this target"; else report FAIL "annotate --blind is blind" "stored blind=$BL"; fi
  run "$ISAAC" bundle reveal "$BUNDLE" "$TARGET"; expect "reveal (records an exposure)" 0 ""
  EXPO="$(json "$BUNDLE/bundle.json" "len([e for e in d['exposures'] if e['target']['id']=='$TARGET'])" 2>/dev/null)"
  if [[ "${EXPO:-0}" -ge 1 ]]; then report PASS "exposure recorded" "$EXPO"; else report FAIL "exposure recorded" "none"; fi
  run "$ISAAC" bundle annotate "$BUNDLE" --target "$TARGET" --value "second reading" --model "$MODEL" --blind --rationale "SYNTHETIC SELF-TEST after reveal"
  BL2="$(json "$BUNDLE/bundle.json" "[a for a in d['ai_interpretations'] if a['target']['id']=='$TARGET'][-1]['blind']" 2>/dev/null)"
  if [[ "$BL2" == "False" ]]; then report PASS "late --blind is not blind" "honestly stored as not blind after the value was shown"; else report FAIL "late --blind is not blind" "stored blind=$BL2"; fi
else report FAIL "crosscheck target" "no target in the plan"; fi

# 4. group ------------------------------------------------------------------------------------------
GROUPED=0
if has bundle group; then
  run "$ISAAC" bundle group "$BUNDLE"; expect "group" 0 "" && GROUPED=1
else report SKIP "group" "this build has no 'isaac bundle group' yet; later steps run without groups"; fi
GROUPS_N="$(json "$BUNDLE/bundle.json" "len(d.get('record_groups', []))" 2>/dev/null || echo 0)"
if [[ $GROUPED -eq 1 ]]; then
  if [[ "$GROUPS_N" -gt 0 ]]; then report PASS "groups proposed" "$GROUPS_N groups, all 'proposed' (none confirmed)"; else report FAIL "groups proposed" "0 groups"; fi
fi

# 5. process (optional extra) ------------------------------------------------------------------------
PROCESSED=0
if has process; then
  if [[ "$GROUPS_N" -gt 0 ]]; then
    run "$ISAAC" process "$BUNDLE" --source "$CORPUS"
    if [[ "$RC" -eq 0 ]]; then report PASS "process" "ran (draft protocol)"; PROCESSED=1
    elif grep -q "processing_unavailable" "$OUT"; then report SKIP "process" "the processing extra is not installed (scripts/setup_isaac_local.sh --with-processing)"; MISSING_PROCESSING=1
    else report FAIL "process" "exit $RC: $(head -c 300 "$OUT" | tr '\n' ' ')"; fi
  else report SKIP "process" "no groups to process"; fi
else report SKIP "process" "this build has no 'isaac process' yet"; fi

# 6. decide ------------------------------------------------------------------------------------------
if [[ "$GROUPS_N" -gt 0 ]]; then
  json "$BUNDLE/bundle.json" "'\n'.join(g['group_id'] for g in d['record_groups'])" > "$WORK/groups.txt"
  run "$ISAAC" bundle decide "$BUNDLE" --targets-file "$WORK/groups.txt" --decision confirm --by "$BY" --note "SYNTHETIC test decision"
  expect "decide: confirm groups" 0 "$GROUPS_N groups confirmed" || true
  CONFIRMED="$(json "$BUNDLE/bundle.json" "len([g for g in d['record_groups'] if g['status']=='scientist_confirmed'])" 2>/dev/null)"
  if [[ "$CONFIRMED" == "$GROUPS_N" ]]; then report PASS "groups are scientist_confirmed" "$CONFIRMED of $GROUPS_N"; else report FAIL "groups are scientist_confirmed" "$CONFIRMED of $GROUPS_N"; fi
else report SKIP "decide: confirm groups" "no groups"; fi
run "$ISAAC" bundle list "$BUNDLE" conflicts --limit 200; cp "$OUT" "$WORK/conflicts.json"
CONF_ID="$(json "$WORK/conflicts.json" "d['items'][0]['conflict_id'] if d.get('items') else ''" 2>/dev/null)"
if [[ -n "$CONF_ID" ]]; then
  run "$ISAAC" bundle decide "$BUNDLE" --target "$CONF_ID" --decision confirm --value "synthetic choice" --by "$BY" --note "SYNTHETIC test decision"
  expect "decide: a conflict needs a value" 0 "recorded as local_unverified" || true
  run "$ISAAC" bundle decide "$BUNDLE" --target "$CONF_ID" --decision confirm --by "$BY"
  expect "decide: refuses a conflict without a value" 2 "refused, nothing written" || true
  run "$ISAAC" bundle decide "$BUNDLE" --target "$CONF_ID" --decision confirm --value x --by ""
  expect "decide: refuses an empty name" 2 "refused" || true
else report SKIP "decide: conflict" "no conflicts in this bundle"; fi

# 7. approve processing, build-records, validate, answer what is missing, validate again ---------------
if [[ $PROCESSED -eq 1 ]]; then
  "$PY" - "$BUNDLE/bundle.json" > "$WORK/proc_ids.txt" <<'PYEND'
import json, sys
from isaac_api.local_import import bundle as B
d = json.load(open(sys.argv[1]))
print("\n".join(B.processing_id(r) for r in d.get("processing_results", [])))
PYEND
  if [[ -s "$WORK/proc_ids.txt" ]]; then
    # The QC STATUS is a person's statement (LOCAL-4 D2: `warn` is never mapped); here it is a
    # SYNTHETIC statement, labelled as such, so the full path can be exercised.
    run "$ISAAC" bundle decide "$BUNDLE" --targets-file "$WORK/proc_ids.txt" --decision approve --qc-status compromised --qc-note "SYNTHETIC SELF-TEST: made-up curve, status stated by a test" --by "$BY" --note "SYNTHETIC test decision: approving made-up curves" --qc-status "${ISAAC_SELFTEST_QC_STATUS:-valid}" --qc-note "SYNTHETIC SELF-TEST QC statement (not a scientist)"
    expect "decide: approve processing + QC status" 0 "$(wc -l < "$WORK/proc_ids.txt" | tr -d ' ') synthetic approvals, each with a stated QC status" || true
  else report SKIP "decide: approve processing" "no processing results"; fi
else report SKIP "decide: approve processing" "processing did not run"; fi

run "$ISAAC" bundle build-records "$BUNDLE" --test-marker; expect "build-records" 0 "$(ls "$BUNDLE/drafts" 2>/dev/null | grep -c 'draft.json') drafts" || true
DRAFTS="$(ls "$BUNDLE/drafts" 2>/dev/null | grep -c 'draft.json')"
if [[ "$GROUPS_N" -gt 0 ]]; then
  if [[ "$DRAFTS" -eq "$GROUPS_N" ]]; then report PASS "one draft per confirmed group" "$DRAFTS"; else report FAIL "one draft per confirmed group" "$DRAFTS drafts for $GROUPS_N groups"; fi
else
  if [[ "$DRAFTS" -eq 0 ]]; then report PASS "no groups, no drafts" "nothing is composed from unconfirmed runs"; else report FAIL "no groups, no drafts" "$DRAFTS drafts"; fi
fi
run "$ISAAC" bundle validate "$BUNDLE"; VAL_RC=$RC; cp "$OUT" "$WORK/validate1.json"
INCOMPLETE1="$(json "$WORK/validate1.json" "len([v for v in d['verdicts'].values() if v=='incomplete'])" 2>/dev/null || echo 0)"
if [[ "$GROUPS_N" -gt 0 ]]; then
  if [[ "$INCOMPLETE1" -eq "$DRAFTS" && "$VAL_RC" -eq 1 ]]; then report PASS "validate: unanswered drafts are incomplete" "$INCOMPLETE1 of $DRAFTS incomplete (exit 1); nothing is defaulted"
  else report FAIL "validate: unanswered drafts are incomplete" "$INCOMPLETE1 of $DRAFTS incomplete, exit $VAL_RC"; fi
fi

run "$ISAAC" bundle questions "$BUNDLE" --blocking-only --limit 5; cp "$OUT" "$WORK/q_before.json"
BLK1="$(json "$WORK/q_before.json" "d['counts']['blocking']" 2>/dev/null || echo -1)"
if [[ "$RC" -eq 0 && "$BLK1" -gt 0 && "$(json "$WORK/q_before.json" "'minimum_for_one_group' in d and all(q['blocking'] and q['answer_command'] for q in d['questions'])" 2>/dev/null)" == "True" ]]; then
  report PASS "questions --blocking-only" "$BLK1 blocking questions, each with its answer command; minimum for one group stated"
else report FAIL "questions --blocking-only" "exit $RC, blocking=$BLK1"; fi

# Answer every required value the drafts name, with clearly labelled SYNTHETIC values. A value no
# source states is a `missing value` (answered with --value); one a source suggested is a
# candidate (confirmed as extracted). Required paths with neither stay missing and are reported.
if [[ "$GROUPS_N" -gt 0 ]]; then
  "$PY" - "$BUNDLE" "$WORK" "$CHECKOUT" <<'PYEND'
import json, os, sys
bundle_dir, work, checkout = sys.argv[1:4]
b = json.load(open(os.path.join(bundle_dir, "bundle.json")))
required = set()
for name in os.listdir(os.path.join(bundle_dir, "validation")):
    required.update(json.load(open(os.path.join(bundle_dir, "validation", name))).get("missing_required", []))
schema = json.load(open(os.path.join(checkout, "schema", "isaac_record_v1.json")))
def enum_first(*path, prefer=None):
    node = schema
    for key in path:
        node = node["properties"][key]
    values = node["enum"]
    return prefer if prefer in values else values[0]
portal = json.load(open(os.path.join(checkout, "apps/api/isaac_api/data/portal_vocabulary_a1cb1c8.json")))
SYNTHETIC = {
    "attribution.produced_by.group": "SYNTHETIC SELF-TEST GROUP",
    "attribution.produced_by.organization": "SYNTHETIC SELF-TEST ORGANISATION",
    "context.environment": enum_first("context", "environment", prefer="ex_situ"),
    "sample.sample_form": portal["Sample"]["sample.sample_form"]["values"][0],
    "system.domain": enum_first("system", "domain", prefer="experimental"),
    "sample.material.name": "SYNTHETIC SELF-TEST MATERIAL",
    "system.technique": enum_first("system", "technique", prefer="XAS"),
}
plan = {"missing": {}, "candidates": {}, "unanswerable": []}
for path in sorted(required):
    miss = [m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path]
    cand = [c for c in b["candidates"] if c.get("target_field_path") == path and c.get("value_state") in ("needs_review", "candidate_extracted")]
    with_value = [c["candidate_id"] for c in cand if c.get("value") is not None]
    without_value = [c["candidate_id"] for c in cand if c.get("value") is None]
    if miss and path in SYNTHETIC:
        plan["missing"][path] = {"value": SYNTHETIC[path], "ids": miss}
    elif with_value:
        plan["candidates"][path] = with_value  # a source suggested a value: confirm it as extracted
    elif without_value and path in SYNTHETIC:
        plan["missing"][path] = {"value": SYNTHETIC[path], "ids": without_value}  # nothing to confirm: give a value
    else:
        plan["unanswerable"].append(path)
json.dump(plan, open(os.path.join(work, "answer_plan.json"), "w"))
for i, (path, item) in enumerate(plan["missing"].items()):
    open(os.path.join(work, f"answer_missing_{i}.txt"), "w").write("\n".join(item["ids"]))
    open(os.path.join(work, f"answer_missing_{i}.value"), "w").write(item["value"])
for i, (path, ids) in enumerate(plan["candidates"].items()):
    open(os.path.join(work, f"answer_cand_{i}.txt"), "w").write("\n".join(ids))
PYEND
  ANS_OK=1
  for f in "$WORK"/answer_missing_*.txt; do
    [[ -e "$f" ]] || continue
    KIND=confirm; grep -q '^cand-' "$f" && KIND=correct
    run "$ISAAC" bundle decide "$BUNDLE" --targets-file "$f" --decision "$KIND" --value "$(cat "${f%.txt}.value")" --by "$BY" --note "SYNTHETIC test value"
    [[ $RC -eq 0 ]] || { ANS_OK=0; report FAIL "decide: answer a required value" "exit $RC: $(head -c 200 "$OUT" | tr '\n' ' ')"; }
  done
  for f in "$WORK"/answer_cand_*.txt; do
    [[ -e "$f" ]] || continue
    run "$ISAAC" bundle decide "$BUNDLE" --targets-file "$f" --decision confirm --by "$BY" --note "SYNTHETIC test confirmation"
    [[ $RC -eq 0 ]] || { ANS_OK=0; report FAIL "decide: confirm an extracted value" "exit $RC: $(head -c 200 "$OUT" | tr '\n' ' ')"; }
  done
  UNANS="$(json "$WORK/answer_plan.json" "len(d['unanswerable'])")"
  if [[ $ANS_OK -eq 1 ]]; then report PASS "decide: required values answered" "$(json "$WORK/answer_plan.json" "len(d['missing'])+len(d['candidates'])") required paths answered with SYNTHETIC values; $UNANS left missing"; fi
  run "$ISAAC" bundle build-records "$BUNDLE" --test-marker; expect "build-records (after answers)" 0 "" || true
  run "$ISAAC" bundle questions "$BUNDLE" --blocking-only --limit 5; BLK2="$(json <(cat "$OUT") "d['counts']['blocking']" 2>/dev/null || echo -1)"
  if [[ "$BLK2" -ge 0 && "$BLK2" -lt "$BLK1" ]]; then report PASS "questions: answering reduces the blocking list" "$BLK1 -> $BLK2"; else report FAIL "questions: answering reduces the blocking list" "$BLK1 -> $BLK2"; fi
fi
run "$ISAAC" bundle validate "$BUNDLE"; VAL_RC=$RC; cp "$OUT" "$WORK/validate.json"
EXPORTABLE="$(json "$WORK/validate.json" "len([v for v in d['verdicts'].values() if v=='exportable'])" 2>/dev/null || echo 0)"
NOTEXP="$(json "$WORK/validate.json" "len([v for v in d['verdicts'].values() if v!='exportable'])" 2>/dev/null || echo 0)"
INCOMPLETE2="$(json "$WORK/validate.json" "len([v for v in d['verdicts'].values() if v=='incomplete'])" 2>/dev/null || echo 0)"
KNOWN="$(json "$WORK/validate.json" "all(v in ('incomplete','invalid_official','portal_check_unavailable','portal_check_degraded','portal_hold','portal_reject','exportable') for v in d['verdicts'].values())" 2>/dev/null)"
if [[ "$KNOWN" == "True" ]]; then report PASS "validate: verdicts" "$EXPORTABLE exportable, $NOTEXP not ($(json "$WORK/validate.json" "sorted(set(d['verdicts'].values()))" 2>/dev/null))"; else report FAIL "validate: verdicts" "an unknown verdict"; fi
if { [[ "$NOTEXP" -eq 0 && "$VAL_RC" -eq 0 ]] || [[ "$NOTEXP" -gt 0 && "$VAL_RC" -eq 1 ]]; }; then
  report PASS "validate: exit code matches" "exit $VAL_RC"; else report FAIL "validate: exit code matches" "exit $VAL_RC with $NOTEXP not exportable"; fi
if [[ $PROCESSED -eq 0 && "$GROUPS_N" -gt 0 && "$EXPORTABLE" -gt 0 ]]; then
  report FAIL "nothing exportable without processing" "$EXPORTABLE exportable although no spectrum was processed"
elif [[ $PROCESSED -eq 0 && "$GROUPS_N" -gt 0 ]]; then
  report PASS "nothing exportable without processing" "drafts without a processed spectrum stay incomplete"; fi
if [[ $PROCESSED -eq 1 && "$GROUPS_N" -gt 0 ]]; then
  if [[ "$INCOMPLETE2" -lt "$INCOMPLETE1" || "$INCOMPLETE1" -eq 0 ]]; then
    report PASS "validate: answers move drafts forward" "incomplete drafts $INCOMPLETE1 -> $INCOMPLETE2"
  else report FAIL "validate: answers move drafts forward" "still $INCOMPLETE2 incomplete: $(json "$WORK/validate.json" "[d['verdicts'][k] for k in d['verdicts']][:3]")"; fi
fi

run "$ISAAC" bundle export "$BUNDLE" --out "$RECORDS"; EXP_RC=$RC
WROTE="$(ls "$RECORDS" 2>/dev/null | grep -vc 'evidence.json$' || true)"; WROTE="${WROTE:-0}"
[[ -d "$RECORDS" ]] || { mkdir -p "$RECORDS"; WROTE=0; }
WROTE="$(find "$RECORDS" -maxdepth 1 -name '*.json' ! -name '*.evidence.json' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$WROTE" -eq "$EXPORTABLE" ]]; then report PASS "export: only exportable records" "$WROTE written, $NOTEXP refused"; else report FAIL "export: only exportable records" "$WROTE written, $EXPORTABLE exportable"; fi
if { [[ "$NOTEXP" -eq 0 && "$EXP_RC" -eq 0 ]] || [[ "$NOTEXP" -gt 0 && "$EXP_RC" -eq 1 ]]; }; then report PASS "export: exit code matches" "exit $EXP_RC"; else report FAIL "export: exit code matches" "exit $EXP_RC"; fi
BADREC=0
for f in "$RECORDS"/*.json; do
  [[ -e "$f" ]] || continue
  case "$f" in *.evidence.json) continue ;; esac
  [[ -f "${f%.json}.evidence.json" ]] || BADREC=$((BADREC+1))
  "$PY" -c 'import json,sys; json.load(open(sys.argv[1]))' "$f" 2>/dev/null || BADREC=$((BADREC+1))
done
# (Exported records are checked against the PINNED PORTAL schema, not the vendored website schema:
# DEC-76. The vendored v1.05 schema forbids fields the portal requires, so `isaac validate --official`
# on an exported record is expected to disagree and is deliberately not asserted here.)
if [[ "$BADREC" -eq 0 ]]; then report PASS "exported records are well formed" "each is JSON and has an evidence file"; else report FAIL "exported records are well formed" "$BADREC problems"; fi
if [[ "$EXPORTABLE" -eq 0 ]]; then
  BLOCKER="$("$PY" - "$BUNDLE" <<'PYEND'
import json, os, sys
b = sys.argv[1]
names = sorted(n for n in os.listdir(os.path.join(b, "validation")) if n.endswith(".json"))
v = json.load(open(os.path.join(b, "validation", names[0])))
comp = json.load(open(os.path.join(b, "drafts", names[0].replace(".json", ".composition.json"))))
errs = (v.get("official_validation") or {}).get("errors") or []
used = comp.get("processing") or {}
bits = [f"verdict {v.get('verdict')}"]
if errs:
    bits.append("official errors: " + "; ".join(f"{e.get('path')}: {e.get('message')}" for e in errs[:4]))
for key in ("series", "qc"):
    if key in used:
        bits.append(f"processing {key}: {used[key]}")
print(" | ".join(bits))
PYEND
)"
  report SKIP "a record reaches exportable" "NOT REACHED on synthetic data. First group: $BLOCKER"
else
  FULLPATH=1
fi
if [[ ! -d "$(ls -d "$HOME/.cache/isaac/portal-validator/"*/venv 2>/dev/null | head -1)" && -z "${ISAAC_PORTAL_VALIDATOR_DIR:-}" ]]; then
  report SKIP "portal check installed" "not installed: records cannot be exportable (scripts/install_portal_validator.sh)"
else report PASS "portal check installed" "offline validator found"; fi

# 7b. a record that passed every gate: what must be true of it ---------------------------------------------
if [[ "${FULLPATH:-0}" -eq 1 ]]; then
  "$PY" - "$BUNDLE" "$RECORDS" > "$WORK/fullpath.txt" <<'PYEND'
import glob, json, os, sys
bundle, records = sys.argv[1:3]
problems, checked = [], 0
for path in sorted(glob.glob(os.path.join(bundle, "validation", "*.json"))):
    v = json.load(open(path))
    if v.get("verdict") != "exportable":
        continue
    checked += 1
    gid = os.path.basename(path)[:-5]
    if not (v.get("official_validation") or {}).get("ok"):
        problems.append(f"{gid}: not valid against the pinned portal schema")
    pc = v.get("portal_check") or {}
    if pc.get("outcome") != "publish":
        problems.append(f"{gid}: offline portal outcome is {pc.get('outcome')!r}, not 'publish'")
exported = [f for f in glob.glob(os.path.join(records, "*.json")) if not f.endswith(".evidence.json")]
if len(exported) != checked:
    problems.append(f"{len(exported)} records written for {checked} exportable drafts")
for f in exported:
    text = open(f, encoding="utf-8").read()
    if "ISAAC SELF-TEST RECORD" not in text:
        problems.append(f"{os.path.basename(f)}: the self-test marker is not in the record")
    if not os.path.isfile(f[:-5] + ".evidence.json"):
        problems.append(f"{os.path.basename(f)}: no evidence file")
print("OK" if not problems else "; ".join(problems))
print(checked)
PYEND
  FP_LINE="$(sed -n 1p "$WORK/fullpath.txt")"
  if [[ "$FP_LINE" == "OK" ]]; then report PASS "exported record: portal 'publish' + marker" "$(sed -n 2p "$WORK/fullpath.txt") record(s): valid against the pinned portal schema, offline portal outcome publish, the self-test marker is in the record, evidence file written"
  else report FAIL "exported record: portal 'publish' + marker" "$FP_LINE"; fi
fi

# 8. upload is a dry run only ------------------------------------------------------------------------
run "$ISAAC" bundle upload "$RECORDS" --dry-run; UP_RC=$RC; cp "$OUT" "$WORK/upload.json"
if [[ $UP_RC -eq 0 && "$(json <(cat "$OUT") "d['network_calls']" 2>/dev/null)" == "0" ]] && grep -q "Nothing was sent" "$OUT"; then
  report PASS "upload --dry-run" "0 network calls; nothing was sent; the key is not read"; else report FAIL "upload --dry-run" "exit $UP_RC: $(head -c 200 "$OUT" | tr '\n' ' ')"; fi
if [[ "$WROTE" -gt 0 ]]; then
  LISTED="$(json "$WORK/upload.json" "len(d['records'])" 2>/dev/null)"
  if [[ "$LISTED" == "$WROTE" ]]; then report PASS "upload --dry-run lists the records" "$LISTED record(s) that would be sent; none was"; else report FAIL "upload --dry-run lists the records" "lists $LISTED of $WROTE"; fi
fi
run "$ISAAC" bundle upload "$RECORDS"; expect "upload without --dry-run is refused" 2 "uploads are disabled in this build" || true

# 9. the bundle is still valid after every change ------------------------------------------------------
run "$ISAAC" bundle check "$BUNDLE"; expect "bundle check (after all changes)" 0 "still meets the v1 contract"

echo
echo "SELF-TEST RESULT: $PASSED passed, $FAILED failed, $SKIPPED skipped (synthetic data; nothing was sent)"
if [[ $SKIPPED -gt 0 ]]; then echo "Skipped steps are not failures: they need a part this build or computer does not have yet, or a known blocker (see the notices above)."; fi
MISSING=()
[[ "${MISSING_PROCESSING:-0}" -eq 1 ]] && MISSING+=("processing (curves and quality checks): scripts/setup_isaac_local.sh --with-processing")
compgen -G "$HOME/.cache/isaac/portal-validator/*/venv/bin/python" >/dev/null || MISSING+=("the offline portal check (no record can become exportable without it): scripts/install_portal_validator.sh")
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "Missing on this computer:"; for m in "${MISSING[@]}"; do echo "  - $m"; done
fi
if [[ $FAILED -gt 0 ]]; then
  echo "IN SHORT: FAIL. $FAILED step(s) did not behave as designed (see FAIL lines above). Do not use this installation until they are fixed."
elif [[ "${FULLPATH:-0}" -eq 1 ]]; then
  echo "IN SHORT: PASS. On made-up data ISAAC read, grouped and processed the files, recorded the decisions, checked the records against the portal's rules, wrote them out, and showed an upload dry run (nothing was sent)."
else
  echo "IN SHORT: PASS WITH A GAP. Every step behaved as designed on made-up data, but no record became ready to export, so the final export of a passing record was NOT tested (reason on the SKIP line above). Nothing was sent."
fi
[[ $FAILED -eq 0 ]] && exit 0 || exit 1
