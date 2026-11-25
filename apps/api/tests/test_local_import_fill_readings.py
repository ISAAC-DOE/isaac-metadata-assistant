"""Bundle format 1.19.0: fills from CHECKED Claude readings (slice 2 of DEC-96, DEC-97;
``docs/fill-first-design-2026-11-25.md``, review findings 3, 6 and 9). SYNTHETIC data only: the committed
multi-operator corpus (unmistakably fake: year 2100, samples ZZ1..ZZ3) plus two invented memo files, imported under a
fake folder name, and in-memory edits of those bundles.

* ``annotate --from-readings --apply`` keeps each reading's quote check (``quote_check``: result, checker, a
  deterministic reading-pass id, and the checked file's path, source id and ``content_sha256``) and its scope;
* ``isaac.fill.reading_stated.v1`` fills a field a checked ``stated`` reading names when its quote itself states the
  value (the lexical tie); an unchecked reading (no block, a failed check, a block that is not the bundle's own source
  or not the reading it was made for) never fills, and the validator refuses an edited or copied block;
* an INFERRED reading never fills, however many quotes agree (DEC-97, after a real-beamtime replay);
* a sample's own label is never filled as its material; an electrolyte name carrying a concentration never fills;
* any disagreement (another reading, a file value) means no fill, and one dissenting target stops a whole beamtime
  finding; a beamtime-scoped reading never fills a run-level or sample field (DEC-69), a runs-scoped one fills only its
  runs, and one bound to its run by the run's name waits for the naming;
* a decision always wins; a correction is recorded by ``decide --question``, a workbook row and a site card;
* a reading fill composes as ``inferred`` with the quote and a derivation naming the rule and the reading pass, and
  passes the draft validator and ``isaac export``;
* a file rule and an agreeing reading are one fill under the file rule; a rule-set-1 bundle is STALE; answer memory
  never learns a reading fill.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import openpyxl
import pytest

from isaac_api.local_import import answer_memory as AM
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import REPO_ROOT, SEMANTICS, fake_upstream_env  # noqa: E402,F401
from test_local_import_fill_first import _add_group, _reject_local_starts  # noqa: E402

FOLDER = "SYN_BL00_2100-01_FillReadings"
MEMO = "SYN_fill_memo.txt"
MEMO2 = "SYN_fill_memo_two.txt"
NOTES = "2099 SYNTHETIC semantics notes.txt"
MODEL = "syn-reader-model"
BY = dict(by="SYN Scientist", orcid=None)
RUN1 = "01_01_ZZ1_acid_after500Cycling_filter10_100mV"
ENV = "context.environment"
FORM = "sample.sample_form"
BEAMLINE = "system.facility.beamline"
TEMP = "context.temperature_K"
GROUP = "attribution.produced_by.group"
NAME = "sample.material.name"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
DOMAIN = "system.domain"

#: The invented memo: each quote below is on the line named (1-based).
MEMO_LINES = {
    1: "# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value below is invented.",
    5: "01_01_ZZ1 was measured in situ in the synthetic cell",
    8: "the synthetic beamline was SYN-BL9 throughout",
    9: "Every synthetic sample in this beamtime was a pressed pellet",
    12: "the ZZ1 material is a SYN-oxide on SYN-support (SYNTHETIC)",
    14: "the data were produced by the SYN group of the synthetic lab",
    16: "every synthetic run here is an experimental measurement",
    18: "Sample 3 ZZ9 in base (SYNTHETIC)",
    21: "Working potential set to 0.1 V (SYNTHETIC)",
    20: "the electrolyte was 0.1 M SYN acid throughout",
    22: "the ZZ1 sample was remeasured twice",
    25: "ZZ1 is again called a SYN-oxide on SYN-support (SYNTHETIC)",
    27: "held at room temperature throughout",
    28: "the cell was held at 25 °C and the potential at 100 mV",
    30: "All synthetic runs were measured in situ",
    31: "Working potential set to 0.4 V (SYNTHETIC)",
    33: "It looked like a steady hold and I began logging (SYNTHETIC)",
    36: "the ZZ1 material is a SYN-other-oxide (SYNTHETIC)",
    38: "Sample 1 ZZ1 film in acid, as before (SYNTHETIC)",
}
MEMO2_LINES = {1: "# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT.", 2: "a second memo: ZZ1 is a SYN-oxide on SYN-support (SYNTHETIC)"}


def _write(path: Path, lines: dict[int, str], total: int) -> None:
    path.write_text("\n".join(lines.get(n, f"synthetic memo filler line {n}") for n in range(1, total + 1)) + "\n",
                    encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """No portal validator installed (as in CI), so the question set does not depend on the machine."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


@pytest.fixture(scope="module")
def src(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("readings-src") / FOLDER
    shutil.copytree(SEMANTICS, folder)
    _write(folder / MEMO, MEMO_LINES, 40)
    _write(folder / MEMO2, MEMO2_LINES, 4)
    return folder


@pytest.fixture(scope="module")
def imported(src, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("readings-bundle") / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def grouped(imported, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("readings-grouped") / "bundle"
    shutil.copytree(imported, out)
    M.group(out)
    assert B.naming_check(M.load(out)) == "grouped_no_counter_question"
    return out


@pytest.fixture()
def bdir(grouped, tmp_path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(grouped, target)
    return target


@pytest.fixture()
def ungrouped(imported, tmp_path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(imported, target)
    return target


def _finding(path: str, value, line: int, quote: str | None = None, *, runs=(RUN1,), strength="stated",
             file=MEMO, locator: str | None = None) -> dict:
    lines = MEMO2_LINES if file == MEMO2 else MEMO_LINES
    return {"field_path": path, "value": value,
            "applies_to": {"scope": "runs", "runs": list(runs)} if runs else {"scope": "experiment"},
            "source": {"path": file, "locator": locator or f"line {line}"},
            "quote": quote if quote is not None else lines[line], "strength": strength, "reasoning": "synthetic"}


def _file(*findings) -> dict:
    return {"format": S.READINGS_FORMAT, "findings": list(findings)}


def _apply(bdir: Path, src: Path, *findings, **kw) -> dict:
    return M.annotate_from_readings(bdir, _file(*findings), model_id=MODEL, apply=True, root=src, **kw)


def _value(b: dict, path: str, run_id: str | None = "run-001") -> dict:
    """The missing value (else the candidate) of ``path`` for ``run_id``."""
    got = [m for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id
           and not B.is_answer_slot(m)]
    if got:
        return got[0]
    return next(c for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] == run_id)


def _id(o: dict) -> str:
    return o.get("value_id") or o.get("candidate_id")


def _readings_of(b: dict, o: dict) -> list[dict]:
    return [i for i in b["ai_interpretations"] if i["target"]["id"] == _id(o)]


def _derived(b: dict) -> dict:
    return B.apply_derivations(json.loads(json.dumps(b)))


def _source(b: dict, rel: str) -> dict:
    return next(s for s in b["sources"] if s["relative_path"] == rel)


def _targets(payload) -> set[str]:
    return {t["id"] for q in payload["questions"] for t in q.get("targets") or ()}


# --- the stored quote check (design item 6) ---------------------------------------------------------------------------


def test_annotate_apply_stores_the_quote_check_and_a_deterministic_reading_pass_id(bdir, src, capsys):
    f = _finding(ENV, "in_situ", 5)
    done = _apply(bdir, src, f)
    assert done["applied"] and done["interpretations"] == 1 and done["quote_check"]["failed"] == 0
    assert all("content_sha256" not in r and "lines" not in r for r in done["quote_check"]["results"])  # stored only
    b = M.load(bdir)
    assert b["format_version"] == B.FORMAT_VERSION == "1.19.0" and b["fill_rule_set"] == B.FILL_RULE_SET == 2
    assert B.validate_bundle(b) == []
    [i] = _readings_of(b, _value(b, ENV))
    qc = i["quote_check"]
    memo = _source(b, MEMO)
    assert qc["result"] == "pass" and qc["checker"] == B.QUOTE_CHECKER_ID == "isaac.reading_check.v1"
    assert qc["reading_pass_id"] == M.reading_pass_id(_file(f), MODEL) and qc["reading_pass_id"].startswith("rp-")
    assert qc["reading_pass_id"] == B.reading_pass_id_of(MODEL, qc["findings_sha256"])
    assert qc["findings_sha256"] == M.findings_sha256(_file(f))
    assert qc["quote_sha256"] == hashlib.sha256(i["quote"].encode("utf-8")).hexdigest()
    assert qc["reading_sha256"] == B.reading_sha256(i)
    [entry] = qc["files"]
    assert (entry["path"], entry["source_id"], entry["content_sha256"], entry["lines"]) == (
        MEMO, memo["source_id"], memo["content_sha256"], [5, 5])
    assert entry["content_sha256"] == hashlib.sha256((src / MEMO).read_bytes()).hexdigest()
    assert i["scope"] == "runs"
    # the id is the findings' (as parsed) and the model's: the file's layout does not move it; another model does
    assert M.reading_pass_id(json.loads(json.dumps(_file(f), indent=3)), MODEL) == qc["reading_pass_id"]
    assert M.reading_pass_id(_file(f), "another-model") != qc["reading_pass_id"]
    # loading the same file again records nothing new
    again = _apply(bdir, src, f)
    assert again["interpretations"] == 0 and again["already_recorded"] == 1
    # the CLI report prints neither stored key
    findings = bdir.parent / "findings.json"
    findings.write_text(json.dumps(_file(f)))
    capsys.readouterr()
    assert cli.main(["bundle", "check-readings", str(bdir), str(findings), "--root", str(src)]) == 0
    assert "content_sha256" not in capsys.readouterr().out


def test_a_corrected_quote_is_recorded_as_a_new_reading(bdir, src):
    """Review M5: the quote is part of a reading's identity: the same finding with a corrected quote is recorded."""
    assert _apply(bdir, src, _finding(ENV, "in_situ", 5, quote="01_01_ZZ1 was measured in situ"))["interpretations"] == 1
    assert _apply(bdir, src, _finding(ENV, "in_situ", 5))["interpretations"] == 1
    b = M.load(bdir)
    assert len(_readings_of(b, _value(b, ENV))) == 2 and B.validate_bundle(b) == []


def test_a_findings_file_holding_nan_is_refused_not_raised(bdir, src, tmp_path, capsys):
    """Review M1: Python's json reads NaN; a findings file holding one is refused with the reason, never a traceback."""
    bad = _file(_finding(SETPOINT, float("nan"), 21, quote="Working potential set to 0.1 V", file=MEMO))
    with pytest.raises(M.MutationRefused, match="not standard JSON"):
        _apply(bdir, src, *bad["findings"])
    with pytest.raises(M.MutationRefused, match="not standard JSON"):
        M.check_readings(M.load(bdir), bad, src)
    path = tmp_path / "nan.json"
    path.write_text(json.dumps(bad))  # json.dumps writes the bare token NaN
    capsys.readouterr()
    code = cli.main(["bundle", "annotate", str(bdir), "--from-readings", str(path), "--model", MODEL, "--root", str(src),
                     "--apply"])
    assert code != 0 and "Traceback" not in capsys.readouterr().err


def test_a_reading_an_earlier_build_recorded_unchecked_is_recorded_again_with_its_check(bdir, src):
    """An older bundle's readings carry no block, so they never fill: loading the same findings again WITH the check
    records the checked reading beside the old one (the log is append-only), and that one fills."""
    f = _finding(ENV, "in_situ", 5)
    M.annotate_from_readings(bdir, _file(f), model_id=MODEL, apply=True, root=src, check_quotes=False)
    b = M.load(bdir)
    assert "quote_check" not in _readings_of(b, _value(b, ENV))[0] and _value(b, ENV)["value_state"] == B.STATE_NEEDS_REVIEW
    assert _apply(bdir, src, f)["interpretations"] == 1
    b = M.load(bdir)
    assert len(_readings_of(b, _value(b, ENV))) == 2 and _value(b, ENV)["value_state"] == B.STATE_FILLED


# --- isaac.fill.reading_stated.v1 -------------------------------------------------------------------------------------


def test_a_stated_checked_reading_fills_the_field_it_names_only_on_the_named_run(bdir, src):
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    m = _value(b, ENV)
    [i] = _readings_of(b, m)
    assert m["value_state"] == B.STATE_FILLED
    assert m["fill"] == {"rule_id": B.FILL_READING_STATED_RULE_ID, "value": "in_situ",
                         "readings": [i["interpretation_id"]], "reading_pass_ids": [i["quote_check"]["reading_pass_id"]]}
    assert m["eligibility_for_official_record"]["eligible"] is True
    assert _value(b, ENV, "run-002")["value_state"] == B.STATE_MISSING  # the reading names run-001 only
    assert m["value_id"] not in _targets(Q.consolidate(b))  # filled: not asked
    assert b["counts"]["filled"] >= 1 and B.validate_bundle(b) == []


def test_an_unchecked_reading_never_fills(bdir, src):
    # (a) no check ran (this package's synthetic path): no block, an AI reading alone -> needs_review, never filled
    M.annotate_from_readings(bdir, _file(_finding(ENV, "in_situ", 5)), model_id=MODEL, apply=True, root=src,
                             check_quotes=False)
    b = M.load(bdir)
    m = _value(b, ENV)
    assert "quote_check" not in _readings_of(b, m)[0]
    assert m["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in m
    assert m["eligibility_for_official_record"]["eligible"] is False
    # (b) `annotate --target`: one reading, never checked
    other = _value(b, ENV, "run-002")
    M.annotate(bdir, target_id=other["value_id"], value="in_situ", excerpt_locator="line 5", source_id=None,
               model_id=MODEL, blind=False, rationale="synthetic")
    assert _value(M.load(bdir), ENV, "run-002")["value_state"] == B.STATE_NEEDS_REVIEW


@pytest.mark.parametrize("edit, valid", [("failed", True), ("no_scope", False), ("another_checker", False),
                                         ("not_imported", False), ("no_pass_id", False)])
def test_a_reading_whose_stored_check_does_not_hold_never_fills(bdir, src, edit, valid):
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    assert _value(b, ENV)["value_state"] == B.STATE_FILLED
    [i] = _readings_of(b, _value(b, ENV))
    if edit == "failed":
        i["quote_check"]["result"] = "fail"
    elif edit == "no_scope":
        i.pop("scope")
    elif edit == "another_checker":
        i["quote_check"]["checker"] = "isaac.reading_check.v0"
    elif edit == "not_imported":  # a file under the folder the import did not read: no hash ties it to the bundle
        i["quote_check"]["files"][0].update(source_id=None, path="SYN_added_later.txt")
        i["source_refs"][0]["source_id"] = None
    elif edit == "no_pass_id":
        i["quote_check"]["reading_pass_id"] = ""
    got = _derived(b)
    m = _value(got, ENV)
    assert m["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in m
    # a failed check is not an error (it never fills); every other edit no longer matches what was checked
    assert (B.validate_bundle(got) == []) is valid


@pytest.mark.parametrize("edit, said", [
    ("sha", "content_sha256"),
    ("quote", "quote_sha256"),
    ("path", "but that source is"),
    ("unnamed_source", "without its source id"),
    ("value", "reading_sha256"),  # review I1: the value edited by hand
    ("strength", "reading_sha256"),  # ... the strength flipped
    ("copied", "reading_sha256"),  # ... the block copied onto another target
    ("pass_id", "reading_pass_id"),
])
def test_a_stored_check_that_is_not_the_reading_or_the_bundles_own_source_is_refused_and_never_fills(
        bdir, src, edit, said):
    _apply(bdir, src, _finding(ENV, "in_situ", 5, strength="inferred" if edit == "strength" else "stated"))
    if edit == "copied":
        M.annotate_from_readings(bdir, _file(_finding(ENV, "in_situ", 5, runs=("02_01_ZZ1_acid_after500Cycling_filter10_200mV",),
                                                      strength="inferred")),
                                 model_id=MODEL, apply=True, root=src, check_quotes=False)
    b = M.load(bdir)
    [i] = [x for x in _readings_of(b, _value(b, ENV)) if x.get("quote_check")]
    entry = i["quote_check"]["files"][0]
    if edit == "sha":
        entry["content_sha256"] = "0" * 64  # a stale or forged check
    elif edit == "quote":
        i["quote"] = "01_01_ZZ1 was measured operando in the synthetic cell"
    elif edit == "path":
        entry["path"] = NOTES
    elif edit == "unnamed_source":
        entry["source_id"] = None
    elif edit == "value":
        i["proposed_value"] = "operando"
    elif edit == "strength":  # an inferred reading made to look stated
        i["strength"] = "stated"
    elif edit == "copied":
        [target] = _readings_of(b, _value(b, ENV, "run-002"))
        target.update(strength="stated", quote_check=copy.deepcopy(i["quote_check"]))
        assert target is not i
    elif edit == "pass_id":
        i["quote_check"]["reading_pass_id"] = "rp-" + "0" * 32
    errors = B.validate_bundle(b)
    assert any(said in e for e in errors), errors
    got = _derived(b)
    for run in (("run-002",) if edit == "copied" else ("run-001", "run-002")):  # a copy leaves the original valid
        m = _value(got, ENV, run)
        assert m["value_state"] != B.STATE_FILLED and "fill" not in m, (edit, run)


def test_the_reading_sha_covers_what_a_reading_says():
    assert set(B.READING_SHA_FIELDS) == {"target", "proposed_value", "strength", "scope", "field_path",
                                         "finding_field_path", "run_ids", "source_refs", "excerpt_locator",
                                         "source_path", "quote"}
    i = {"target": {"kind": "missing_value", "id": "miss-0001"}, "proposed_value": "in_situ", "strength": "stated",
         "quote_check": {"files": [{"path": "a.txt", "source_id": "src-0001", "content_sha256": "1" * 64,
                                    "lines": [3, 3], "at": "line 3"}]}}
    base = B.reading_sha256(i)
    for k, v in (("proposed_value", "operando"), ("strength", "inferred"), ("scope", "runs"),
                 ("target", {"kind": "missing_value", "id": "miss-0002"})):
        assert B.reading_sha256({**i, k: v}) != base, k
    moved = copy.deepcopy(i)
    moved["quote_check"]["files"][0]["lines"] = [4, 4]
    assert B.reading_sha256(moved) != base
    said = copy.deepcopy(i)
    said["quote_check"]["files"][0]["at"] = "line 3 (reworded)"
    assert B.reading_sha256(said) == base  # the check's own words are not what the reading says


# --- the lexical tie (D2) ----------------------------------------------------------------------------------------------


def test_a_stated_reading_whose_quote_does_not_state_its_value_never_fills(bdir, src):
    """The replay's 13: two quotes that name no environment ("a steady hold", "began logging") never fill one, stated
    or inferred."""
    _apply(bdir, src, _finding(ENV, "operando", 33))
    m = _value(M.load(bdir), ENV)
    assert m["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in m


def test_room_temperature_never_fills_a_temperature_and_a_stated_number_does(bdir, src):
    _apply(bdir, src, _finding(TEMP, 298.15, 27))
    assert _value(M.load(bdir), TEMP)["value_state"] == B.STATE_NEEDS_REVIEW
    _apply(bdir, src, _finding(TEMP, 298.15, 28, quote="the cell was held at 25 °C", runs=("02_01_ZZ1_acid_after500Cycling_filter10_200mV",)))
    t = _value(M.load(bdir), TEMP, "run-002")
    assert t["value_state"] == B.STATE_FILLED and t["fill"]["value"] == 298.15  # 25 °C, a declared conversion


@pytest.mark.parametrize("path, value, quote, ties", [
    (SETPOINT, 0.1, "Working potential set to 0.1 V (SYNTHETIC)", True),
    (SETPOINT, 0.1, "the potential at 100 mV", True),  # a declared conversion
    (SETPOINT, 100, "the potential at 100 mV", False),  # mV is never read as V
    (SETPOINT, 0.2, "Working potential set to 0.1 V (SYNTHETIC)", False),
    (TEMP, 298.15, "held at room temperature throughout", False),
    (TEMP, 298.15, "held at 25 °C", True),
    (TEMP, 298.0, "held at 298 K", True),
    ("context.electrochemistry.electrolyte.concentration_M", 0.1, "in 100 mM synthetic acid", True),
    ("context.electrochemistry.electrolyte.concentration_M", 0.1, "in 0.1 M synthetic acid", True),
    (ENV, "in_situ", "was measured in situ", True),
    (ENV, "in_situ", "was measured in-situ", True),
    (ENV, "in_situ", "was not in situ", False),  # negated
    (ENV, "operando", "It looked like a steady hold and I began logging (SYNTHETIC)", False),
    ("context.electrochemistry.cell_type", "flow_cell", "in a synthetic flow cell", True),
    ("context.electrochemistry.cell_type", "h_cell", "an H type cell", True),  # a registered synonym
    (FORM, "pellet", "pressed into pellets", True),  # a registered synonym
    (FORM, "powder", "pressed into pellets", False),
    (NAME, "SYN-oxide on SYN-support", "the ZZ1 material is a SYN-oxide on SYN-support (SYNTHETIC)", True),
    (NAME, "SYN-oxide on SYN-support", "the ZZ1 material is a SYN-oxide (SYNTHETIC)", False),
    (NAME, "Zr", "Zr", False),  # no significant word
    (BEAMLINE, "SYN-BL9", "the synthetic beamline was SYN-BL9 throughout", True),
    # re-review I1: a number ties only with its field's own unit (or a declared conversion); never inside a heading
    ("context.electrochemistry.current_setpoint_mA_cm2", 0.1, "scan rate was 0.1 mV/s", False),
    (TEMP, 0.1, "0.1 M SYN acid", False),
    ("context.electrochemistry.pH", 1, "Sample 1 ZZ1", False),
    (SETPOINT, 1, "Sample 1 ZZ1", False),
    (SETPOINT, 1, "scan 1 of file 01_01_ZZ1", False),
    (SETPOINT, 0.06, "held at 0.06 V vs RHE", True),
    (SETPOINT, 0.1, "held at 0.1 throughout", False),  # a bare number, for a field with a unit
    ("context.electrochemistry.pH", 13, "in 1 M SYN base, pH 13 for the base", True),  # a bare number, unitless field
    ("context.electrochemistry.current_setpoint_mA_cm2", -10, "held at -10 mA/cm2", True),
    ("context.electrochemistry.current_setpoint_mA_cm2", -10, "held at -10 mA cm-2", True),
    ("context.electrochemistry.current_setpoint_mA_cm2", 5, "held at 5 mA in total", False),
    # re-review I3: a negation anywhere earlier in the same clause
    (ENV, "in_situ", "the cell was never operated in situ for this run", False),
    (ENV, "in_situ", "it wasn't measured in situ", False),
    (ENV, "in_situ", "neither dry nor in situ", False),
    (ENV, "in_situ", "not dry, measured in situ", False),  # one sentence: asked (the safe direction)
    (ENV, "in_situ", "not dry; measured in situ", True),  # the negation is in another sentence
    # final check 3: a negation AFTER the member, or across a comma or a colon, in the same sentence
    (ENV, "in_situ", "an in situ measurement was not possible here", False),
    (ENV, "in_situ", "the cell was never, at any point in this beamtime, operated in situ", False),
    (ENV, "in_situ", "In situ: not possible with this cell", False),
    (ENV, "in_situ", "in situ, not ex situ", False),
    (ENV, "in_situ", "the dry run was not used. Then it was measured in situ", True),
    # final check 1: a scan rate is no set-point, however it is written
    (SETPOINT, 0.1, "swept at 100 mV s-1 from OCV", False),
    (SETPOINT, 0.1, "swept at 100 mV s^-1 from OCV", False),
    (SETPOINT, 0.1, "swept at 100 mV s⁻¹ from OCV", False),
    (SETPOINT, 0.1, "swept at 100 mV /s from OCV", False),
    (SETPOINT, 0.1, "swept at 100 mV/s from OCV", False),
    (SETPOINT, 0.06, "held at 0.06 V vs RHE", True),
    # final check 2: the pH only right after its own word
    ("context.electrochemistry.pH", 2, "two runs on 2 electrodes", False),
    ("context.electrochemistry.pH", 500, "after 500 cycles", False),
    ("context.electrochemistry.pH", 13, "0.1 M SYN-OH, pH = 13", True),
    ("context.electrochemistry.pH", 13, "the base was at pH of 13", True),
    ("context.electrochemistry.pH", 13, "pH13 base", True),
    ("context.electrochemistry.pH", 13, "13 in pH units", False),
    # final check 5: a C rate is no temperature
    (TEMP, 274.15, "cycled at 1 C rate", False),
    (TEMP, 274.15, "cycled at 1C rate", False),
    (TEMP, 298.15, "held at 25 C.", True),
    (TEMP, 298.15, "held at 25 degC", True),
    (TEMP, 298.15, "held at 25C throughout", True),
    # last fixes 1: a rate word right after the unit, a two-word unit included, makes the number a rate
    ("context.electrochemistry.current_setpoint_mA_cm2", 10, "ramped at 10 mA cm-2 s-1 from rest", False),
    (SETPOINT, 0.1, "swept at 100 mV per second", False),
    (SETPOINT, 0.1, "swept at 100 mV per s", False),
    (SETPOINT, 0.1, "swept at 100 mV s^{-1}", False),
    (SETPOINT, 0.1, "swept at 100 mV sec-1", False),
    (SETPOINT, 0.1, "swept at 100 mV /sec", False),
    ("context.electrochemistry.current_setpoint_mA_cm2", -10, "held at -10 mA cm-2 for an hour", True),
    (SETPOINT, 0.06, "Working potential set to 0.06 V vs reference (SYNTHETIC)", True),  # the replay's tie
    # last fixes 2: more negation words, and a wrapped line is one sentence (a blank line ends one)
    (ENV, "in_situ", "measured ex situ instead of in situ", False),
    (ENV, "in_situ", "we were unable to measure in situ", False),
    (ENV, "in_situ", "it can't be called in situ", False),
    (ENV, "in_situ", "in situ was planned\nbut not done", False),
    (ENV, "in_situ", "the dry run was not used\n\nThen it was measured in situ", True),
])
def test_the_lexical_tie(path, value, quote, ties):
    from isaac_api.local_import import reading_tie as T

    assert (T.tie_problem(path, value, quote, B.allowed_values(path)) is None) is ties


def test_every_numeric_field_has_its_units_and_an_unlisted_one_never_ties():
    from isaac_api.local_import import reading_tie as T

    numeric = {p for p in B._writable_paths() if (B._schema_node(p) or {}).get("type") in
               ("number", "integer", ["number", "null"], ["integer", "null"])}
    assert numeric == set(T.FIELD_UNITS)
    assert [p for p, u in T.FIELD_UNITS.items() if u.get("unitless")] == ["context.electrochemistry.pH"]
    assert T.FIELD_UNITS["context.electrochemistry.pH"]["anchor"] == "pH"
    assert {"mV s-1", "mV/s", "C-rate"} <= T.OTHER_UNITS
    assert {"cannot", "unable", "impossible", "instead", "rather", "failed", "absent", "unavailable",
            "lacking"} <= T.NEGATIONS
    assert T.number_tie("sample.some_unlisted_number", 5, "held at 5 V") is False


def test_the_synonym_list_is_explicit_and_small_and_names_real_members():
    from isaac_api.local_import import reading_tie as T

    assert sum(len(v) for m in T.MEMBER_SYNONYMS.values() for v in m.values()) <= 12
    for path, members in T.MEMBER_SYNONYMS.items():
        assert set(members) <= set(B.allowed_values(path)), path
    assert set(T.UNIT_CONVERSIONS) <= B._writable_paths()


def test_the_tie_is_checked_against_the_stored_quote(bdir, src):
    """Review M3: the stored quote (as kept, possibly truncated at 300 characters) is what must state the value."""
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    [i] = _readings_of(b, _value(b, ENV))
    assert B.reading_ties(i, ENV)
    assert not B.reading_ties({**i, "quote": "01_01_ZZ1 was measured"}, ENV)


def test_an_electrolyte_name_carrying_a_concentration_never_fills(bdir, src):
    """Review M2: an electrolyte name with a concentration (or a pH) in it is never filled, even when stated."""
    _apply(bdir, src, _finding("context.electrochemistry.electrolyte.name", "0.1 M SYN acid", 20))
    name = _value(M.load(bdir), "context.electrochemistry.electrolyte.name")
    assert name["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in name
    from isaac_api.local_import import reading_tie as T

    assert T.electrolyte_name_problem("SYN acid pH 1") and T.electrolyte_name_problem("2 mol/L SYN base")
    assert T.electrolyte_name_problem("SYN acid") is None


def test_an_electrolyte_read_as_a_whole_is_offered_unsplit_and_never_fills(bdir, src):
    """A finding about the electrolyte as a whole is offered, unsplit, on its name and its concentration (§20): splitting
    it is the scientist's step, so it fills neither. A finding naming the name itself does."""
    _apply(bdir, src, _finding("context.electrochemistry.electrolyte", "0.1 M SYN acid", 20))
    b = M.load(bdir)
    name = _value(b, "context.electrochemistry.electrolyte.name")
    assert _readings_of(b, name)[0]["finding_field_path"] == "context.electrochemistry.electrolyte"
    assert name["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in name


def test_an_unsplit_reading_disagrees_with_a_name_reading(bdir, src):
    _apply(bdir, src, _finding("context.electrochemistry.electrolyte", "0.1 M SYN acid", 20),
           _finding("context.electrochemistry.electrolyte.name", "SYN acid", 20, quote="0.1 M SYN acid"))
    name = _value(M.load(bdir), "context.electrochemistry.electrolyte.name")
    assert name["value_state"] == B.STATE_NEEDS_REVIEW  # the unsplit reading on it states "0.1 M SYN acid"


def test_a_name_reading_alone_fills(bdir, src):
    _apply(bdir, src, _finding("context.electrochemistry.electrolyte.name", "SYN acid", 20, quote="0.1 M SYN acid"))
    name = _value(M.load(bdir), "context.electrochemistry.electrolyte.name")
    assert name["value_state"] == B.STATE_FILLED and name["fill"]["value"] == "SYN acid"


# --- a sample's own label is not its material (D3) ----------------------------------------------------------------------


def test_a_sample_heading_code_is_never_filled_as_the_material(bdir, src):
    """The replay's 49: "Sample 3 ZZ9 in base (SYNTHETIC)" (stated, scoped to the runs) names the sample, never its material."""
    _apply(bdir, src, _finding(NAME, "ZZ9", 18))
    m = _value(M.load(bdir), NAME)
    assert m["value_state"] != B.STATE_FILLED and "fill" not in m


def test_a_sample_label_and_one_more_word_is_never_the_material(bdir, src):
    """Re-review I2: "ZZ1 film" (the sample's own label plus a word) is never filled as the material."""
    _apply(bdir, src, _finding(NAME, "ZZ1 film", 38))
    c = _value(M.load(bdir), NAME)
    assert c["value_state"] != B.STATE_FILLED and "fill" not in c
    ctx = B.fill_context(M.load(bdir))
    assert B.fill_value_problem(NAME, "ZZ1 film", "run-001", ctx) == "a sample's own label is not its material"
    assert B.fill_value_problem(NAME, "ZZ9 oxide", "run-001", ctx, ["Sample 3 ZZ9 in base (SYNTHETIC)"])  # a heading code word
    # final check 4: a label split by a space, or run into the next word, is still the label
    assert B.fill_value_problem(NAME, "ZZ 1 film", "run-001", ctx) == "a sample's own label is not its material"
    assert B.fill_value_problem(NAME, "ZZ-1film", "run-001", ctx)
    assert B.fill_value_problem(NAME, "SYN-oxide on SYN-support", "run-001", ctx) is None


def test_the_file_name_sample_token_is_never_filled_as_the_material(bdir, src):
    b = M.load(bdir)
    c = _value(b, NAME)
    # slice 1: the file-name reader's sample token is a candidate with NO value, held for the scientist (who alone says
    # whether it is a material or an electrode label), so parser_exact never fills it; its literal is a hint only
    assert c["value"] is None and c["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in c
    assert [e["literal_value"] for e in c["evidence"] if e["locator"].startswith("filename")][0] == "ZZ1"
    _apply(bdir, src, _finding(NAME, "ZZ1", 22))
    c = _value(M.load(bdir), NAME)
    assert c["value_state"] != B.STATE_FILLED and "fill" not in c
    ctx = B.fill_context(M.load(bdir))
    assert B.fill_value_problem(NAME, "zz-1", "run-001", ctx) == "a sample's own label is not its material"
    assert B.fill_value_problem(NAME, "sample 01", "run-001", ctx)  # the run's sample id
    assert B.fill_value_problem(NAME, "SYN-oxide on SYN-support", "run-001", ctx) is None


def test_a_label_valued_parser_candidate_is_not_filled_by_parser_exact(bdir):
    """D3 applies to parser_exact too: a material candidate whose value is the run's own sample token is not filled."""
    b = M.load(bdir)
    c = _value(b, NAME)
    c.update(value="ZZ1", extracted_state=B.STATE_CANDIDATE_EXTRACTED)
    c["state_basis"].update(review_status="ready", proposable=True, not_proposable_reason=None)
    for e in c["evidence"]:
        e["relation"] = "supports"
    got = _value(_derived(b), NAME)
    assert got["value_state"] == B.STATE_CANDIDATE_EXTRACTED and "fill" not in got


# --- inferred readings never fill (D1) ----------------------------------------------------------------------------------


def test_an_inferred_reading_never_fills_however_many_quotes_agree(bdir, src):
    value = "SYN-oxide on SYN-support"
    _apply(bdir, src, _finding(NAME, value, 12, strength="inferred"), _finding(NAME, value, 25, strength="inferred"),
           _finding(NAME, value, 2, file=MEMO2, strength="inferred"))
    c = _value(M.load(bdir), NAME)
    assert c["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in c
    assert B.FILL_READING_STATED_RULE_ID in B.FILL_RULES and "isaac.fill.reading_inferred.v1" not in B.FILL_RULES


def test_an_inferred_reading_beside_the_file_value_never_fills(bdir, src):
    sp = _value(M.load(bdir), SETPOINT)
    assert "candidate_id" in sp and sp["value"] == 0.1 and sp["value_state"] == B.STATE_NEEDS_REVIEW
    _apply(bdir, src, _finding(SETPOINT, 0.1, 21, file=MEMO, strength="inferred"))
    sp = _value(M.load(bdir), SETPOINT)
    assert sp["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in sp


def test_a_stated_reading_beside_the_file_value_fills_and_one_that_differs_does_not(bdir, src):
    _apply(bdir, src, _finding(SETPOINT, 0.1, 21, file=MEMO))
    sp = _value(M.load(bdir), SETPOINT)
    assert sp["value_state"] == B.STATE_FILLED and sp["fill"]["rule_id"] == B.FILL_READING_STATED_RULE_ID
    run2 = "02_01_ZZ1_acid_after500Cycling_filter10_200mV"
    assert _value(M.load(bdir), SETPOINT, "run-002")["value"] == 0.2
    _apply(bdir, src, _finding(SETPOINT, 0.4, 31, runs=(run2,), file=MEMO))
    sp2 = _value(M.load(bdir), SETPOINT, "run-002")
    assert sp2["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in sp2  # its file value is 0.2


# --- disagreement ------------------------------------------------------------------------------------------------------


def test_disagreeing_readings_never_fill(bdir, src):
    _apply(bdir, src, _finding(NAME, "SYN-oxide on SYN-support", 12),
           _finding(NAME, "SYN-other-oxide", 36))
    assert _value(M.load(bdir), NAME)["value_state"] == B.STATE_NEEDS_REVIEW
    # an UNCHECKED reading that disagrees blocks a checked one too
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    assert _value(b, ENV)["value_state"] == B.STATE_FILLED
    M.annotate(bdir, target_id=_value(b, ENV)["value_id"], value="operando", excerpt_locator=None, source_id=None,
               model_id=MODEL, blind=False, rationale="")
    assert _value(M.load(bdir), ENV)["value_state"] == B.STATE_NEEDS_REVIEW


def test_a_runs_own_differing_reading_stops_a_beamtime_fill_for_that_run(bdir):
    """FILL_RULE_SET 2: a run's own AI reading of a field is one of its readings: one that states another value stops a
    beamtime-wide fill reaching that run (the composer and the questions read the same rows)."""
    b = M.load(bdir)
    other = _value(b, FORM, "run-002")
    M.annotate(bdir, target_id=other["value_id"], value="powder", excerpt_locator=None, source_id=None,
               model_id=MODEL, blind=False, rationale="")
    rows = B.fill_run_blocks(M.load(bdir))[FORM]
    assert ("reading", other["value_id"], "powder", None) in rows["run-002"]
    stopped = B.runs_a_fill_cannot_reach(rows, FORM, "pellet")
    assert stopped == {"run-002": [other["value_id"]]}
    assert B.runs_a_fill_cannot_reach(rows, FORM, "powder") == {}


@pytest.mark.parametrize("how", ["reading", "decision"])
def test_one_dissenting_target_stops_the_whole_beamtime_finding(bdir, src, how):
    """D6 (review I4): a beamtime-scoped finding fills none of its targets when one of them dissents (another reading of
    one run's value, or a scientist's other answer for it)."""
    _apply(bdir, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()))
    lines = [m for m in M.load(bdir)["missing_values"] if m["target_field_path"] == BEAMLINE and not B.is_answer_slot(m)]
    assert len(lines) == 9 and all(m["value_state"] == B.STATE_FILLED for m in lines)
    other = _value(M.load(bdir), BEAMLINE, "run-002")
    if how == "reading":
        M.annotate(bdir, target_id=other["value_id"], value="SYN-BL7", excerpt_locator=None, source_id=None,
                   model_id=MODEL, blind=False, rationale="")
    else:
        M.decide(bdir, target_ids=[other["value_id"]], decision="correct", value="SYN-BL7", **BY)
    b = M.load(bdir)
    lines = [m for m in b["missing_values"] if m["target_field_path"] == BEAMLINE and not B.is_answer_slot(m)]
    assert not any(m["value_state"] == B.STATE_FILLED for m in lines)
    assert B.validate_bundle(b) == []


def test_a_defer_on_one_target_is_no_dissent(bdir, src):
    _apply(bdir, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()))
    other = _value(M.load(bdir), BEAMLINE, "run-002")
    M.decide(bdir, target_ids=[other["value_id"]], decision="defer", value=None, **BY)
    b = M.load(bdir)
    states = {m["run_id"]: m["value_state"] for m in b["missing_values"] if m["target_field_path"] == BEAMLINE
              and not B.is_answer_slot(m)}
    assert states.pop("run-002") != B.STATE_FILLED  # the defer itself beats the fill on its own target
    assert set(states.values()) == {B.STATE_FILLED}


# --- DEC-69, scope and the naming gate (design item 3) ------------------------------------------------------------------


def test_a_beamtime_reading_never_fills_a_run_level_field_and_a_runs_reading_fills_only_its_runs(bdir, src):
    _apply(bdir, src, _finding(ENV, "in_situ", 30, runs=()))  # scope: experiment
    b = M.load(bdir)
    envs = [m for m in b["missing_values"] if m["target_field_path"] == ENV]
    assert envs and all(m["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in m for m in envs)
    assert all(i["scope"] == "experiment" for m in envs for i in _readings_of(b, m))
    assert B.reading_scope_problem(_readings_of(b, envs[0])[0], envs[0], ENV, B.fill_context(b)).startswith("DEC-69")
    # the same statement scoped to the run it names fills that run only
    _apply(bdir, src, _finding(ENV, "in_situ", 30, runs=(RUN1,)))
    b = M.load(bdir)
    filled = {m["run_id"] for m in b["missing_values"] if m["target_field_path"] == ENV and m["value_state"] == B.STATE_FILLED}
    assert filled == {"run-001"}
    # a beamtime reading of a field that is neither run-level nor a sample's fills every run's value
    _apply(bdir, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()))
    b = M.load(bdir)
    lines = [m for m in b["missing_values"] if m["target_field_path"] == BEAMLINE and not B.is_answer_slot(m)]
    assert len(lines) == 9 and all(m["value_state"] == B.STATE_FILLED and m["fill"]["value"] == "SYN-BL9" for m in lines)
    assert B.validate_bundle(b) == []


def test_a_beamtime_reading_of_a_sample_field_fills_only_a_one_sample_beamtime(bdir, src):
    """D5 (review I2): with three samples (ZZ1..ZZ3) a beamtime statement about "every sample" fills no run's sample
    field; with exactly one sample it is a statement about every run's."""
    _apply(bdir, src, _finding(FORM, "pellet", 9, runs=()))
    b = M.load(bdir)
    assert not B.fill_context(b)["one_sample"]
    forms = [m for m in b["missing_values"] if m["target_field_path"] == FORM]
    assert forms and not any(m["value_state"] == B.STATE_FILLED for m in forms)
    one = copy.deepcopy(b)
    for r in one["runs"]:
        r["sample_id"] = "sample-01"
    for c in one["candidates"]:
        if c["statement_key"] == "sample_name":
            for e in c["evidence"]:
                e["literal_value"] = "ZZ1"
    one = B.apply_derivations(one)
    assert B.fill_context(one)["one_sample"]
    forms = [m for m in one["missing_values"] if m["target_field_path"] == FORM and not B.is_answer_slot(m)]
    assert forms and all(m["value_state"] == B.STATE_FILLED for m in forms)
    # re-review hardening (c): sample_id comes from the file name, so the logbook's sample headings must agree too
    x = copy.deepcopy(one)
    steps = x["candidates"][0]["evidence"][0]["normalization"]
    steps.append({"step": "normalize", "rule_id": "bl15.notes.syn", "from": "", "to": {"section": "Sample 1 ZZ1 in acid (SYNTHETIC)"}})
    assert B._one_sample(x)
    steps.append({"step": "normalize", "rule_id": "bl15.notes.syn", "from": "", "to": {"section": "Sample 2 ZZ2 in base (SYNTHETIC)"}})
    assert not B._one_sample(x)


def test_the_run_level_paths_a_beamtime_reading_never_fills():
    many, one = {"one_sample": False}, {"one_sample": True}
    for path in (*R.RUN_ONLY_PATHS, "context.reaction.name", "context.reaction.catalysis", "context.reaction.drive",
                 SETPOINT, B.CURRENT_SETPOINT_PATH, B.CONTROL_MODE_PATH, "context.electrochemistry.potential_scale"):
        assert B.reading_run_level(path, many) and B.reading_run_level(path, one), path
    for path in (FORM, NAME, "sample.material.formula"):
        assert B.reading_run_level(path, many) and not B.reading_run_level(path, one), path
    for path in (BEAMLINE, DOMAIN, "context.electrochemistry.electrolyte.name"):
        assert not B.reading_run_level(path, many), path


def test_a_reading_bound_to_its_run_by_name_waits_for_the_naming(ungrouped, src):
    """A runs-scoped reading of a logbook line reaches its run because the READER matched the run's name: before the
    naming is settled (a fresh import, or an open counter question) it does not fill; once settled it does. A quote in
    the run's OWN acquisition file needs no name and is not gated."""
    _apply(ungrouped, src, _finding(ENV, "in_situ", 5),
           _finding(BEAMLINE, "SYNTHETIC FIXTURE", 4, quote="#C SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT.", file=RUN1))
    b = M.load(ungrouped)
    assert B.naming_check(b) == "not_grouped"
    assert _value(b, ENV)["value_state"] == B.STATE_NEEDS_REVIEW  # the memo: bound by name, waits
    assert _value(b, BEAMLINE)["value_state"] == B.STATE_FILLED  # the run's own file: not gated
    counter_open = [{"kind": "naming_counter_positions", "positions": [1], "id": "syn", "text": "SYN?"}]
    x = copy.deepcopy(b)
    x["grouping_questions"] = counter_open
    assert _value(B.apply_derivations(x), ENV)["value_state"] == B.STATE_NEEDS_REVIEW
    x["grouping_questions"] = []  # grouped, no counter question
    assert _value(B.apply_derivations(x), ENV)["value_state"] == B.STATE_FILLED


# --- precedence (design item 6) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("decision, value, state", [
    ("correct", "ex_situ", B.STATE_SCIENTIST_CONFIRMED),
    ("reject", None, B.STATE_REJECTED),
    ("defer", None, B.STATE_NEEDS_REVIEW),  # a defer is a decision: no fill over it (the reading alone: needs_review)
])
def test_a_decision_beats_a_reading_fill(bdir, src, decision, value, state):
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    vid = _value(M.load(bdir), ENV)["value_id"]
    M.decide(bdir, target_ids=[vid], decision=decision, value=value, **BY)
    m = _value(M.load(bdir), ENV)
    assert m["value_state"] == state and "fill" not in m
    assert B.validate_bundle(M.load(bdir)) == []


def test_a_file_fill_and_an_agreeing_reading_are_one_fill_under_the_file_rule(bdir, src):
    _apply(bdir, src, _finding(DOMAIN, "experimental", 16, runs=()))
    b = M.load(bdir)
    dom = _value(b, DOMAIN, None)
    [i] = _readings_of(b, dom)
    assert dom["fill"] == {"rule_id": B.FILL_DOMAIN_RULE_ID, "value": "experimental",
                           "readings": [i["interpretation_id"]], "reading_pass_ids": [i["quote_check"]["reading_pass_id"]]}
    # a checked reading that disagrees: no fill at all
    _apply(bdir, src, _finding(DOMAIN, "computational", 16, runs=()))
    dom = _value(M.load(bdir), DOMAIN, None)
    assert dom["value_state"] == B.STATE_NEEDS_REVIEW and "fill" not in dom


# --- corrections stay possible ----------------------------------------------------------------------------------------


def _group_question(b: dict) -> str:
    vid = _value(b, GROUP, None)["value_id"]
    return next(q["question_id"] for q in Q.consolidate(b, include_answered=True)["questions"]
                if vid in {t["id"] for t in q["targets"]})


def _fill_the_group(bdir: Path, src: Path) -> str:
    _apply(bdir, src, _finding(GROUP, "SYN group", 14, runs=()))
    m = _value(M.load(bdir), GROUP, None)
    assert m["value_state"] == B.STATE_FILLED and m["fill"]["rule_id"] == B.FILL_READING_STATED_RULE_ID
    return m["value_id"]


def test_a_reading_fill_is_not_asked_but_decide_question_records_a_correction(bdir, src):
    vid = _fill_the_group(bdir, src)
    b = M.load(bdir)
    assert vid not in _targets(Q.consolidate(b))
    qid = _group_question(b)
    assert vid in Q.filled_targets(b, Q.targets_for(Q.consolidate(b, include_answered=True), qid))
    M.decide_question(bdir, question_id=qid, decision="correct", value="SYN other group", **BY)
    m = _value(M.load(bdir), GROUP, None)
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and "fill" not in m


def test_a_workbook_answer_to_a_reading_fill_is_recorded(bdir, src, tmp_path, capsys):
    qid = _group_question(M.load(bdir))  # asked before the reading is loaded
    _fill_the_group(bdir, src)
    xlsx = tmp_path / "SYN_questions.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("2 Missing (blocks export)")
    ws["A1"] = "SYN title line"
    for c, h in enumerate(["Ref", "Folder", "Topic", "YOUR ANSWER", "ISAAC question ID"], start=1):
        ws.cell(2, c, h)
    for c, v in enumerate(["2-0001", FOLDER, "Producing group", "SYN other group", qid], start=1):
        ws.cell(3, c, v)
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", "SYN Scientist", "--apply"]) == 0
    capsys.readouterr()
    assert _value(M.load(bdir), GROUP, None)["value_state"] == B.STATE_SCIENTIST_CONFIRMED


def test_a_question_site_answer_to_a_reading_fill_is_recorded(bdir, src, tmp_path):
    from isaac_api.local_import import question_site as SITE
    from isaac_api.local_import import question_site_import as SI

    site = tmp_path / "site"
    SITE.export_site(bdir, site, site_template=tmp_path / "no-template")  # the card is exported before the fill
    data = json.loads((site / "data" / "site-data.json").read_text())
    card = next(c for c in data["cards"] if (c.get("field") or {}).get("path") == GROUP)
    _fill_the_group(bdir, src)
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({
        "format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
        "bundle_version": data["bundle_version"], "exported_at": "2100-02-01T10:00:00Z", "log": [],
        "answers": [{"card_id": card["card_id"], "action": "value", "value": "SYN other group", "typed": False,
                     "note": "", "by": "SYN Scientist", "at": "2100-02-01T10:00:00Z"}]}))
    rep = SI.import_answers(bdir, answers, site_data=site / "data" / "site-data.json", apply=True)
    [a] = rep["answers"]
    assert a["outcome"] == "recorded", a
    assert _value(M.load(bdir), GROUP, None)["value_state"] == B.STATE_SCIENTIST_CONFIRMED


# --- a RUN-level reading fill: the question leaves it out and says so (re-review M1) ------------------------------------


def _fill_run1_env(bdir: Path, src: Path) -> str:
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    m = _value(M.load(bdir), ENV)
    assert m["value_state"] == B.STATE_FILLED
    return m["value_id"]


def _env_question(b: dict) -> dict:
    return next(q for q in Q.consolidate(b)["questions"] if q.get("target_field_path") == ENV)


def test_a_run_level_fill_is_left_out_of_its_question_and_the_question_says_so(bdir, src):
    vid = _fill_run1_env(bdir, src)
    q = _env_question(M.load(bdir))
    assert vid not in {t["id"] for t in q["targets"]} and len(q["targets"]) == 8
    assert q["left_out_as_filled"] == [{"run_id": "run-001", "target_id": vid}]
    assert "Left out, because a rule filled the value from the evidence: 1 value(s), for " + RUN1 in q["text"]
    assert f"--target {vid}" in q["text"]


def test_decide_question_answers_the_runs_it_asks_and_leaves_the_fill(bdir, src):
    vid = _fill_run1_env(bdir, src)
    q = _env_question(M.load(bdir))
    M.decide_question(bdir, question_id=q["question_id"], decision="correct", value="ex_situ", **BY)
    b = M.load(bdir)
    assert _value(b, ENV)["value_state"] == B.STATE_FILLED  # left out: the filled run keeps its fill
    assert {_value(b, ENV, f"run-00{n}")["value_state"] for n in range(2, 10)} == {B.STATE_SCIENTIST_CONFIRMED}
    # ...and `decide --target` corrects the filled run itself
    M.decide(bdir, target_ids=[vid], decision="correct", value="operando", **BY)
    m = _value(M.load(bdir), ENV)
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and "fill" not in m


def test_a_workbook_answer_to_a_run_level_question_leaves_the_fill(bdir, src, tmp_path, capsys):
    _fill_run1_env(bdir, src)
    qid = _env_question(M.load(bdir))["question_id"]
    xlsx = tmp_path / "SYN_questions.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("2 Missing (blocks export)")
    ws["A1"] = "SYN title line"
    for c, h in enumerate(["Ref", "Folder", "Topic", "YOUR ANSWER", "ISAAC question ID"], start=1):
        ws.cell(2, c, h)
    for c, v in enumerate(["2-0001", FOLDER, "Environment", "ex_situ", qid], start=1):
        ws.cell(3, c, v)
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", "SYN Scientist", "--apply"]) == 0
    capsys.readouterr()
    b = M.load(bdir)
    assert _value(b, ENV)["value_state"] == B.STATE_FILLED
    assert _value(b, ENV, "run-002")["value_state"] == B.STATE_SCIENTIST_CONFIRMED


def test_a_site_card_lists_the_filled_run_it_leaves_out_and_its_answer_leaves_the_fill(bdir, src, tmp_path):
    from isaac_api.local_import import question_site as SITE
    from isaac_api.local_import import question_site_import as SI

    _fill_run1_env(bdir, src)
    site = tmp_path / "site"
    SITE.export_site(bdir, site, site_template=tmp_path / "no-template")
    data = json.loads((site / "data" / "site-data.json").read_text())
    cards = [c for c in data["cards"] if (c.get("field") or {}).get("path") == ENV]
    [zz1] = [c for c in cards if "ZZ1" in c["title"]]
    [shown] = [x for x in zz1["context"] if x.get("label", "").startswith("Filled from your files, so not asked here")]
    assert shown["rows"] == [[RUN1, "in_situ"]] and "final review" in shown["source"]
    assert not any(x.get("label", "").startswith("Filled from your files") for c in cards if c is not zz1
                   for x in c["context"])  # another sample's card does not list it
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({
        "format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
        "bundle_version": data["bundle_version"], "exported_at": "2100-02-01T10:00:00Z", "log": [],
        "answers": [{"card_id": zz1["card_id"], "action": "value", "value": "ex_situ", "typed": False,
                     "note": "", "by": "SYN Scientist", "at": "2100-02-01T10:00:00Z"}]}))
    rep = SI.import_answers(bdir, answers, site_data=site / "data" / "site-data.json", apply=True)
    [a] = rep["answers"]
    assert a["outcome"] == "recorded", a
    b = M.load(bdir)
    assert _value(b, ENV)["value_state"] == B.STATE_FILLED
    assert {_value(b, ENV, r)["value_state"] for r in ("run-002", "run-003")} == {B.STATE_SCIENTIST_CONFIRMED}


def test_answer_memory_never_learns_a_reading_fill(bdir, src):
    _apply(bdir, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()), _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    assert any((o.get("fill") or {}).get("rule_id") in B.READING_FILL_RULES for o in b["missing_values"])
    assert AM.person_values(b) == [] and AM.entries_from_bundle(b) == []


# --- composition, draft validation, export ----------------------------------------------------------------------------


def _answer_the_required(bdir: Path) -> None:
    """Every required value neither a fill nor the reading supplies, answered."""
    b = M.load(bdir)

    def miss(path, run_id):
        return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id)

    def cand(path, run_id):
        return next(c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] == run_id)

    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(bdir, target_ids=[cand("sample.material.name", "run-001")], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(bdir, target_ids=[cand("system.technique", None)], decision="correct", value="HERFD-XAS", **BY)
    for path, value in [("attribution.produced_by.group", "SYN group"),
                        ("attribution.produced_by.organization", "SYN University")]:
        M.decide(bdir, target_ids=[miss(path, None)], decision="correct", value=value, **BY)
    for path, value in [("sample.sample_form", "pellet"), ("context.environment", "ex_situ"),
                        ("context.temperature_K", 298.0)]:
        M.decide(bdir, target_ids=[miss(path, "run-001")], decision="correct", value=value, **BY)


def test_a_reading_fill_composes_as_inferred_passes_the_draft_validator_and_isaac_export(ungrouped, src,
                                                                                       fake_upstream_env):
    from isaac_records.draft_validator import validate_draft
    from isaac_records.export import export_draft

    _add_group(ungrouped)
    _answer_the_required(ungrouped)
    _reject_local_starts(ungrouped, "run-001")
    _apply(ungrouped, src, _finding(BEAMLINE, "SYN-BL9", 8, runs=()))  # a beamtime statement; not run-level
    b = M.load(ungrouped)
    m = _value(b, BEAMLINE)
    assert m["value_state"] == B.STATE_FILLED and m["fill"]["rule_id"] == B.FILL_READING_STATED_RULE_ID
    [i] = _readings_of(b, m)
    R.build_records(ungrouped)
    draft = json.loads((ungrouped / "drafts" / "g1.draft.json").read_text())
    comp = json.loads((ungrouped / "drafts" / "g1.composition.json").read_text())
    env = draft["fields"][BEAMLINE]
    assert env["value"] == "SYN-BL9" and env["status"] == "inferred"
    [w] = [e for e in env["evidence"] if e.get("method") == "ai_interpretation"]
    assert w["source_type"] == "document" and w["source_file"] == MEMO and w["quote"] == MEMO_LINES[8]
    assert w["locator"] == "line 8" and w["relation"] == "supports" and w["method_id"] == MODEL
    assert w["reading_pass_id"] == i["quote_check"]["reading_pass_id"]
    assert w["quote_check"]["content_sha256"] == _source(b, MEMO)["content_sha256"]
    [d] = [e for e in env["evidence"] if e.get("source_type") == "derivation"]
    assert d["rule"] == B.FILL_READING_STATED_RULE_ID and d["rule_text"] == B.FILL_RULES[d["rule"]]
    assert d["readings"] == [i["interpretation_id"]] and d["reading_pass_ids"] == [i["quote_check"]["reading_pass_id"]]
    assert not any(e["source_type"] == "user_confirmation" for e in env["evidence"])
    assert any(f["path"] == BEAMLINE and B.FILL_READING_STATED_RULE_ID in f["rules"] for f in comp["filled_by_rule"])
    report = validate_draft(draft)
    assert report.ok, report.errors
    assert not [x for x in report.warnings if x[0].startswith("fields." + BEAMLINE)], report.warnings
    result = export_draft(draft, REPO_ROOT)
    assert result.ok, (result.draft_report.errors, result.official_report and result.official_report.errors)
    assert result.record["system"]["facility"]["beamline"] == "SYN-BL9"
    text = json.dumps(result.sidecar)
    assert B.FILL_READING_STATED_RULE_ID in text and i["quote_check"]["reading_pass_id"] in text


# --- versioning ---------------------------------------------------------------------------------------------------------


def test_the_rules_and_their_texts():
    assert B.READING_FILL_RULES == {B.FILL_READING_STATED_RULE_ID} and B.FILL_READING_STATED_RULE_ID in B.FILL_RULES
    assert not hasattr(B, "FILL_READING_INFERRED_RULE_ID")  # D1: no dead rule
    schema = B.bundle_schema()
    assert set(schema["$defs"]["fill"]["properties"]["rule_id"]["enum"]) == set(B.FILL_RULES)
    qc = schema["$defs"]["ai_interpretation"]["properties"]["quote_check"]
    assert qc["properties"]["checker"]["enum"] == [B.QUOTE_CHECKER_ID] and "reading_sha256" in qc["required"]
    assert B.FILL_RULE_SET == 2 and B.FORMAT_VERSION == "1.19.0" and "1.19.0" in B.CHANGES_ADDED_IN
    assert "inferred" in B.FILL_READING_STATED_RULE and ". " not in B.FILL_READING_STATED_RULE


def test_a_rule_set_1_bundle_is_stale_and_its_next_write_re_derives_it(bdir, src, monkeypatch, capsys):
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = json.loads((bdir / "bundle.json").read_text())
    with monkeypatch.context() as mp:  # what rule set 1 derived: no reading fill
        mp.setattr(B, "reading_fill_for", lambda *a, **k: None)
        B.apply_derivations(b)
    b["fill_rule_set"] = 1
    vid = _value(b, ENV)["value_id"]
    assert _value(b, ENV)["value_state"] == B.STATE_NEEDS_REVIEW
    (bdir / "bundle.json").write_text(json.dumps(b))
    assert B.fill_rule_set_stale(b) and B.validate_bundle(b)
    errors, stale = B.validate_allowing_stale(b)
    assert errors == [] and [(s["id"], s["value_state"]) for s in stale] == [(vid, B.STATE_FILLED)]
    assert B.FILL_READING_STATED_RULE_ID in stale[0]["reason"]
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 1 and capsys.readouterr().out.startswith("STALE:")
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["fill_rule_set"] == 2 and B.validate_bundle(saved) == []
    assert [r["id"] for r in saved["eligibility_rederived"]] == [vid]
    assert _value(saved, ENV)["value_state"] == B.STATE_FILLED


def test_a_1_18_0_bundle_is_raised_to_1_19_0_by_its_next_write(bdir):
    b = json.loads((bdir / "bundle.json").read_text())
    b["format_version"], b["fill_rule_set"] = "1.18.0", 1
    (bdir / "bundle.json").write_text(json.dumps(b))
    errors, stale = B.validate_allowing_stale(b)
    assert errors == [] and stale == []  # nothing a reading fills, nothing moves
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["format_version"] == "1.19.0" and saved["fill_rule_set"] == 2 and B.validate_bundle(saved) == []
    [u] = [u for u in saved["format_upgrades"] if u["from_format_version"] == "1.18.0"]
    assert B.CHANGES_ADDED_IN["1.19.0"] in u["statement"]


def test_a_quote_check_off_the_schema_is_refused(bdir, src):
    _apply(bdir, src, _finding(ENV, "in_situ", 5))
    b = M.load(bdir)
    [i] = _readings_of(b, _value(b, ENV))
    i["quote_check"]["reading_pass_id"] = "rp-not-hex"
    assert any("reading_pass_id" in e for e in B.validate_bundle(b))
    b = M.load(bdir)
    _readings_of(b, _value(b, ENV))[0]["quote_check"]["extra"] = 1
    assert any("quote_check" in e for e in B.validate_bundle(b))
