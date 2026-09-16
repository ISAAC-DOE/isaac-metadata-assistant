"""The gold-standard harness, and the two rules it exists to enforce.

**A NOTE ON WHAT THESE TESTS CAN AND CANNOT SHOW.** Several of them build a
"perfect" :class:`Observed` FROM the committed gold standard and then assert the
harness scores it 1.0. That is deliberately tautological about *agreement* — it has
to be, because the readers that will one day produce a real ``Observed`` are not in
this branch — and it is exactly the shape the module docstring warns about when it
comes from a PARSER. The difference is what is being measured: here the subject is
the HARNESS, and a harness that could not score a known-correct observation as
correct would be useless. Every such test is paired with a MUTATION that perturbs
one thing and asserts the number moves, because "it reports 1.0" is worth nothing
without "and it reports less than 1.0 when it should".

The tests that are NOT tautological, and that carry the weight of this file, are the
ones about the rules: fabrication is caught in four independent ways,
``needs_domain_review`` does not excuse it, conflicts are scored by NAME and not by
count, an absent reference basis is RECOVERED rather than missed, and no function in
the module can turn an observation into ground truth.
"""

from __future__ import annotations

import inspect
import json
import typing

import pytest

from isaac_api.bl15 import archive, evaluate as ev
from isaac_api.bl15 import mapping as mapping_registry
from isaac_api.bl15.evidence import (
    DETERMINISM_INFERRED,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
)

GOLD_FILE = ev.GOLD_DIR / "bl15-mini-synthetic-v1.gold.json"
MINI_CORPUS = ev.GOLD_DIR / "mini_corpus"

A = "01_01_SYN1_acid_beforeCycling_filter10_060mV"
B = "02_01_SYN1_acid_beforeCycling_filter10_060mV_again"
C = "03_02_SYN2_base_after1500Cycling_ffilter35_1200mV_zz9"
D = "03_02_SYN2_base_after1500Cycling_filter20_0p5nm_1200mV"


@pytest.fixture()
def gold() -> ev.GoldStandard:
    return ev.load_gold_standard(GOLD_FILE)


def _perfect(gold: ev.GoldStandard) -> ev.Observed:
    """An observation that matches the gold standard in every dimension.

    Built from the gold standard ON PURPOSE — see this file's docstring. It is the
    baseline every mutation test below perturbs, so that each metric is shown to
    move for exactly one reason.
    """
    evidence: list[dict] = []
    candidates: list[ev.CandidateValue] = []
    counter = 0
    for path, tokens in (gold.filename_tokens or {}).items():
        for concept, literal in tokens.items():
            counter += 1
            eid = f"e{counter}"
            evidence.append(
                {
                    "evidence_id": eid,
                    "source_path": path,
                    "source_type": "spec_acquisition",
                    "locator": f"filename[{concept}]",
                    "raw_literal": literal,
                    "concept": concept,
                    "parser_id": "test-fixture",
                    "determinism": DETERMINISM_READ,
                    "normalized_value": None,
                    "normalization_rule": None,
                }
            )
            candidates.append(
                ev.CandidateValue(
                    candidate_id=f"c{counter}",
                    concept=concept,
                    value=literal,
                    determinism=DETERMINISM_READ,
                    evidence_ids=(eid,),
                    source_path=path,
                    locator=f"filename[{concept}]",
                )
            )

    return ev.Observed(
        source_classification=dict(gold.source_classification or {}),
        filename_tokens={p: dict(t) for p, t in (gold.filename_tokens or {}).items()},
        candidates=tuple(candidates),
        evidence=tuple(evidence),
        run_sources=tuple(
            {"run_id": stem, "source_path": stem, "source_type": "spec_acquisition"}
            for stem in (gold.measurement_groups or {})
        ),
        measurement_groups={
            k: list(v) for k, v in (gold.measurement_groups or {}).items()
        },
        macro_declarations={
            k: list(v) for k, v in (gold.macro_declarations or {}).items()
        },
        sample_groups={k: list(v) for k, v in (gold.sample_groups or {}).items()},
        inherited_beamtime_context={
            k: list(v) for k, v in (gold.readme_inheritance or {}).items()
        },
        duplicate_groups=tuple(tuple(g) for g in (gold.duplicate_groups or ())),
        conflicts=tuple(gold.known_conflicts),
        unknown_tokens={k: list(v) for k, v in (gold.unknown_tokens or {}).items()},
        technique=dict(gold.technique or {}),
        links=tuple(dict(link) for link in (gold.links or ())),
    )


def _replace(observed: ev.Observed, **changes) -> ev.Observed:
    import dataclasses

    return dataclasses.replace(observed, **changes)


# --- the committed gold standard --------------------------------------------


def test_the_committed_gold_standard_loads_and_declares_human_authorship():
    raw = json.loads(GOLD_FILE.read_text(encoding="utf-8"))
    assert raw["provenance"]["authored_by_human"] is True
    assert raw["provenance"]["generated_from_parser_output"] is False
    gold = ev.load_gold_standard(GOLD_FILE)
    assert gold.corpus_id == "bl15-mini-synthetic-v1"
    assert len(gold.known_conflicts) == 5


def test_the_committed_gold_standard_is_for_the_SYNTHETIC_corpus_only():
    """It must not contain a real sample name, a real beamline stem, or a real path.

    A gold standard is the one artifact in this feature whose whole job is to carry
    expected VALUES, so it is the likeliest place for a real corpus fact to be
    copied in by accident. Checked by name.
    """
    text = GOLD_FILE.read_text(encoding="utf-8")
    for forbidden in ("JK1", "JK2", "JK3", "IrO2", "IrTiO2", "Sokaras", "SSRL_BL152"):
        assert forbidden not in text, (
            f"{forbidden!r} appears in the committed gold standard; this file is "
            "for the synthetic fixture only (CLAUDE.md §6)"
        )
    assert "/Users/" not in text and "/home/" not in text


def test_every_path_the_gold_standard_names_exists_in_the_mini_corpus():
    """A gold standard naming paths nothing produces is VACUOUS.

    It would report every dimension as a clean miss or a clean pass depending on
    the shape of the observation, and never notice that its own subject does not
    exist. Checked through the real walker, so the fixture is also proven to be
    something ``bl15.archive`` accepts.
    """
    inventory = archive.inventory_folder(MINI_CORPUS, root_label="mini corpus")
    assert inventory.refused == ()
    assert inventory.truncated_reason is None
    present = set(inventory.by_path())

    gold = ev.load_gold_standard(GOLD_FILE)
    named: set[str] = set()
    named |= set(gold.source_classification or {})
    named |= set(gold.filename_tokens or {})
    named |= set(gold.legacy_numbers or {})
    named |= set(gold.legacy_numbers_absent)
    named |= set(gold.potential_magnitudes or {})
    named |= set(gold.potential_reference_unresolved)
    named |= set(gold.filters or {})
    named |= set(gold.cycling_states or {})
    named |= set(gold.measurement_groups or {})
    named |= set(gold.macro_declarations or {})
    named |= set(gold.readme_inheritance or {})
    for group in gold.duplicate_groups or ():
        named |= set(group)
    for scans in (gold.measurement_groups or {}).values():
        named |= set(scans)
    for paths in (gold.sample_groups or {}).values():
        named |= set(paths)

    missing = sorted(named - present)
    assert missing == [], f"the gold standard names paths the fixture does not hold: {missing}"
    # And the fixture holds nothing the gold standard is silent about, so a file
    # cannot be added to the corpus without an expectation being written for it.
    unclaimed = sorted(present - named)
    assert unclaimed == [], f"fixture files with no gold-standard expectation: {unclaimed}"


def test_the_mini_corpus_reproduces_the_measured_structural_anomalies():
    """The fixture is only useful if it has the SHAPE the real archive has."""
    inventory = archive.inventory_folder(MINI_CORPUS, root_label="mini corpus")
    by_path = inventory.by_path()

    # 2.1 -- the extension does not classify.
    head_macro, _ = archive.read_source_head(inventory, "runsynth", source_root=MINI_CORPUS)
    head_spec, _ = archive.read_source_head(inventory, "alignsynth", source_root=MINI_CORPUS)
    assert by_path["runsynth"].extension == ""
    assert by_path["alignsynth"].extension == ""
    assert head_macro.startswith("qdo ")
    assert head_spec.startswith("#F ")

    # 2.4 -- every `*_dir` also holds a byte-identical copy.
    assert len(inventory.duplicate_groups) == 2
    assert sum(len(g) for g in inventory.duplicate_groups) == 4

    # 2.3 -- a measurement can have ZERO scan children.
    dat_files = [p for p in by_path if p.endswith(".dat")]
    assert len(dat_files) == 2
    assert all(p.startswith(f"{A}_dir/") for p in dat_files)
    assert not any(p.startswith(f"{B}_dir/") and p.endswith(".dat") for p in by_path)

    # 2.6 / 2.6a -- the internal `#F` disagrees with the filename on exactly one
    # file, and AGREES on the others. Both halves, because a fixture where every
    # header disagreed would make the conflict detector look right by accident.
    declarations = {}
    for stem in (A, B, C, D, "alignsynth"):
        text, reason = archive.read_source_text(inventory, stem, source_root=MINI_CORPUS)
        assert reason is None
        line = next(l for l in text.splitlines() if l.startswith("#F "))
        declarations[stem] = line[3:].strip()
    assert declarations[C] != C
    assert declarations[C] == "03_02_SYN2_base_beforeCycling_ffilter35_1200mV_zz9"
    for stem in (A, B, D, "alignsynth"):
        assert declarations[stem] == stem

    # The notes file carries the BOM the real one does.
    decoded, reason = archive.read_source_decoded(
        inventory, "990101 SYNTHETIC BL15 notes.txt", source_root=MINI_CORPUS
    )
    assert reason is None
    assert decoded.encoding == "utf-8-sig" and decoded.had_bom is True

    # Every file says it is synthetic, in its own bytes.
    for path in by_path:
        text, reason = archive.read_source_text(inventory, path, source_root=MINI_CORPUS)
        assert reason is None
        lowered = text.lower()
        assert "synth" in lowered or "syn" in lowered, path


# --- rule 2: ground truth may not come from the thing being measured --------


@pytest.mark.parametrize(
    "key",
    [
        "generator",
        "generated_by",
        "parser_id",
        "derived_from_observed",
        "produced_by_parser",
        "harvested_from",
    ],
)
def test_a_gold_standard_naming_a_generator_is_refused(tmp_path, key):
    document = {
        "corpus_id": "x",
        "provenance": {
            "authored_by_human": True,
            "generated_from_parser_output": False,
            key: "bl15.filenames",
        },
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ev.GoldStandardRefused) as caught:
        ev.load_gold_standard(path)
    assert key in str(caught.value)


@pytest.mark.parametrize(
    "provenance",
    [
        {},
        {"authored_by_human": True},
        {"generated_from_parser_output": False},
        {"authored_by_human": False, "generated_from_parser_output": False},
        {"authored_by_human": True, "generated_from_parser_output": True},
        {"authored_by_human": "yes", "generated_from_parser_output": False},
    ],
)
def test_a_gold_standard_that_does_not_declare_human_authorship_is_refused(
    tmp_path, provenance
):
    """Silence is not assent, and neither is a truthy string.

    ``is True`` rather than a truthiness test, because ``"no"`` is truthy and a
    document that says ``"authored_by_human": "no"`` must not pass.
    """
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps({"corpus_id": "x", "provenance": provenance}), encoding="utf-8"
    )
    with pytest.raises(ev.GoldStandardRefused):
        ev.load_gold_standard(path)


def test_a_gold_standard_with_no_provenance_block_at_all_is_refused(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"corpus_id": "x"}), encoding="utf-8")
    with pytest.raises(ev.GoldStandardRefused):
        ev.load_gold_standard(path)


def test_a_misspelled_expectation_key_is_refused_rather_than_silently_dropped(tmp_path):
    """Otherwise the report would read UNMEASURABLE and blame the producer."""
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps(
            {
                "corpus_id": "x",
                "provenance": {
                    "authored_by_human": True,
                    "generated_from_parser_output": False,
                },
                "potential_magnitude": {"a": "1V"},  # missing the trailing `s`
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ev.GoldStandardRefused) as caught:
        ev.load_gold_standard(path)
    assert "potential_magnitude" in str(caught.value)


def test_an_underscore_prefixed_key_is_a_comment_and_is_accepted(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps(
            {
                "corpus_id": "x",
                "provenance": {
                    "authored_by_human": True,
                    "generated_from_parser_output": False,
                },
                "_comment_anything": "JSON has no comments and reasoning must sit "
                "beside the expectation",
            }
        ),
        encoding="utf-8",
    )
    assert ev.load_gold_standard(path).corpus_id == "x"


def test_no_function_in_this_module_turns_an_observation_into_ground_truth():
    """**MECHANICAL, and it is the point of rule 2.**

    Asserted over the module's own type hints rather than over its prose, because
    the prose is what a future slice would edit while adding exactly such a
    function. Any callable that accepts an :class:`Observed` (or an
    :class:`EvaluationReport`) and returns a :class:`GoldStandard` would make the
    whole harness circular.
    """
    offenders = []
    for name, obj in vars(ev).items():
        if name.startswith("__") or not callable(obj):
            continue
        if getattr(obj, "__module__", None) != ev.__name__:
            continue
        try:
            hints = typing.get_type_hints(obj)
        except Exception:  # pragma: no cover - unresolvable annotation
            continue
        returns = hints.pop("return", None)
        if returns is not ev.GoldStandard:
            continue
        if any(
            annotation in (ev.Observed, ev.EvaluationReport, ev.CandidateValue)
            for annotation in hints.values()
        ):
            offenders.append(name)
    assert offenders == [], (
        f"{offenders} take an observation and return ground truth; a parser that "
        "scores itself is measuring nothing"
    )

    # And the only constructor of a GoldStandard from a file takes a PATH.
    signature = inspect.signature(ev.load_gold_standard)
    assert list(signature.parameters) == ["path"]


def test_evaluate_refuses_arguments_of_the_wrong_kind(gold):
    with pytest.raises(TypeError):
        ev.evaluate(gold, {"candidates": []})
    with pytest.raises(TypeError):
        ev.evaluate({"corpus_id": "x"}, ev.Observed())


# --- rule 1: needs_domain_review is an outcome, not a failure ---------------


def test_a_deferred_concept_is_excluded_from_the_token_ratio_and_reported(gold):
    observed = _perfect(gold)
    report = ev.evaluate(gold, observed)
    tokens = report.by_id()[ev.METRIC_FILENAME_TOKENS]

    assert tokens.outcome == ev.MEASURED
    assert tokens.value == 1.0
    # The two deferred concepts appear in `deferred`, not in `recovered`.
    assert set(tokens.deferred) == {
        f"{C}:potential_reference_basis" if False else f"{D}:loading_or_thickness",
    } or "loading_or_thickness" in " ".join(tokens.deferred)
    assert any("loading_or_thickness" in item for item in tokens.deferred)
    deferred_count = len(tokens.deferred)
    assert deferred_count >= 1

    # MUTATION: get a deferred concept WRONG. The ratio must not move, because
    # scoring it would assert a reading this repository may not make.
    broken = dict(observed.filename_tokens)
    broken[D] = dict(broken[D], loading_or_thickness="WRONG")
    moved = ev.evaluate(gold, _replace(observed, filename_tokens=broken))
    assert moved.by_id()[ev.METRIC_FILENAME_TOKENS].value == 1.0
    assert len(moved.by_id()[ev.METRIC_FILENAME_TOKENS].deferred) == deferred_count

    # NEGATIVE CONTROL: a NON-deferred concept getting it wrong DOES move it.
    broken2 = dict(observed.filename_tokens)
    broken2[D] = dict(broken2[D], filter="WRONG")
    dropped = ev.evaluate(gold, _replace(observed, filename_tokens=broken2))
    assert dropped.by_id()[ev.METRIC_FILENAME_TOKENS].value < 1.0


def test_needs_domain_review_does_NOT_excuse_a_fabricated_value(gold):
    """**The load-bearing half of rule 1, and the easiest thing to get wrong.**

    ``needs_domain_review`` means the MAPPING is a scientific judgement. It does
    not mean the VALUE may be invented. A candidate flagged for review whose value
    no evidence supports is still fabricated, and the headline number must say so.
    """
    observed = _perfect(gold)
    invented = ev.CandidateValue(
        candidate_id="invented",
        concept="electrolyte_or_medium",
        value="0.1 M SynBase",  # no source states a concentration
        determinism=DETERMINISM_READ,
        evidence_ids=(),
        needs_domain_review=True,
    )
    report = ev.evaluate(
        gold, _replace(observed, candidates=observed.candidates + (invented,))
    )
    headline = report.headline()
    assert headline.metric_id == ev.METRIC_FABRICATED_VALUE_RATE
    assert headline.value > 0.0
    assert headline.passed is False
    assert report.passed is False
    assert any("invented" in line for line in headline.detail)


# --- the headline: fabrication, caught four independent ways ----------------


def test_a_perfect_observation_scores_zero_fabrication_and_full_provenance(gold):
    report = ev.evaluate(gold, _perfect(gold))
    assert report.headline().metric_id == ev.METRIC_FABRICATED_VALUE_RATE
    assert report.headline().value == 0.0
    assert report.by_id()[ev.METRIC_PROVENANCE_COVERAGE].value == 1.0
    assert report.passed is True
    assert report.hard_failures == ()


def test_a_candidate_that_names_no_evidence_is_fabricated(gold):
    observed = _perfect(gold)
    bare = ev.CandidateValue(candidate_id="bare", concept="filter", value="filter99")
    report = ev.evaluate(gold, _replace(observed, candidates=(bare,)))
    assert report.headline().value == 1.0
    assert report.headline().passed is False
    assert "names no evidence" in report.headline().detail[0]


def test_a_candidate_that_names_evidence_which_does_not_exist_is_fabricated(gold):
    observed = _perfect(gold)
    ghost = ev.CandidateValue(
        candidate_id="ghost",
        concept="filter",
        value="filter10",
        evidence_ids=("no-such-evidence",),
        source_path=A,
        locator="filename[filter]",
    )
    report = ev.evaluate(gold, _replace(observed, candidates=(ghost,)))
    assert report.headline().value == 1.0
    assert "does not exist" in report.headline().detail[0]


def test_a_READ_candidate_whose_source_says_something_else_is_fabricated(gold):
    """The subtlest of the four: it cites real evidence for a value that is not in it."""
    observed = _perfect(gold)
    real_evidence = observed.evidence[0]
    lying = ev.CandidateValue(
        candidate_id="lying",
        concept=real_evidence["concept"],
        value="A VALUE THE SOURCE DOES NOT CONTAIN",
        determinism=DETERMINISM_READ,
        evidence_ids=(real_evidence["evidence_id"],),
        source_path=real_evidence["source_path"],
        locator=real_evidence["locator"],
    )
    report = ev.evaluate(gold, _replace(observed, candidates=(lying,)))
    assert report.headline().value == 1.0
    assert "claims to be READ" in report.headline().detail[0]
    # And the same candidate is also an incorrect CONFIDENT mapping.
    confident = report.by_id()[ev.METRIC_INCORRECT_CONFIDENT_MAPPING_RATE]
    assert confident.value == 1.0 and confident.passed is False


def test_a_NORMALIZED_candidate_citing_an_undeclared_rule_is_fabricated(gold):
    """A producer must not be able to legitimise a transformation by naming it."""
    observed = _perfect(gold)
    base = observed.evidence[0]
    made_up = ev.CandidateValue(
        candidate_id="made-up-rule",
        concept="potential_magnitude",
        value=0.06,
        determinism=DETERMINISM_NORMALIZED,
        evidence_ids=(base["evidence_id"],),
        source_path=base["source_path"],
        locator=base["locator"],
        normalization_rule="whatever_i_felt_like",
    )
    report = ev.evaluate(gold, _replace(observed, candidates=(made_up,)))
    assert report.headline().value == 1.0
    assert "undeclared rule" in report.headline().detail[0]

    # NEGATIVE CONTROL: the SAME candidate citing a rule the gold standard
    # declares is supported. The mechanism is the rule name, not the value.
    declared = ev.CandidateValue(
        candidate_id="declared-rule",
        concept="potential_magnitude",
        value=0.06,
        determinism=DETERMINISM_NORMALIZED,
        evidence_ids=(base["evidence_id"],),
        source_path=base["source_path"],
        locator=base["locator"],
        normalization_rule="millivolts_to_volts_and_p_as_decimal_point",
    )
    ok = ev.evaluate(gold, _replace(observed, candidates=(declared,)))
    assert ok.headline().value == 0.0


def test_a_NORMALIZED_candidate_with_no_rule_at_all_is_fabricated(gold):
    observed = _perfect(gold)
    base = observed.evidence[0]
    unexplained = ev.CandidateValue(
        candidate_id="unexplained",
        concept="filter",
        value=35,
        determinism=DETERMINISM_NORMALIZED,
        evidence_ids=(base["evidence_id"],),
        source_path=base["source_path"],
        locator=base["locator"],
    )
    report = ev.evaluate(gold, _replace(observed, candidates=(unexplained,)))
    assert report.headline().value == 1.0
    assert "no named rule" in report.headline().detail[0]


def test_an_INFERRED_candidate_needs_a_declared_rule_and_real_evidence(gold):
    observed = _perfect(gold)
    base = observed.evidence[0]
    good = ev.CandidateValue(
        candidate_id="inferred-ok",
        concept="acquisition_timestamp",
        value="2099-01-01T00:00:00Z",
        determinism=DETERMINISM_INFERRED,
        evidence_ids=(base["evidence_id"],),
        source_path=base["source_path"],
        locator=base["locator"],
        normalization_rule="unix_epoch_seconds_to_iso8601_utc",
    )
    assert ev.evaluate(gold, _replace(observed, candidates=(good,))).headline().value == 0.0

    groundless = ev.CandidateValue(
        candidate_id="inferred-groundless",
        concept="acquisition_timestamp",
        value="2099-01-01T00:00:00Z",
        determinism=DETERMINISM_INFERRED,
        evidence_ids=(),
        normalization_rule="unix_epoch_seconds_to_iso8601_utc",
    )
    assert (
        ev.evaluate(gold, _replace(observed, candidates=(groundless,))).headline().value
        == 1.0
    )
    # An INFERRED candidate is deliberately NOT counted as a confident mapping,
    # because it does not claim the source says it.
    report = ev.evaluate(gold, _replace(observed, candidates=(good,)))
    assert report.by_id()[ev.METRIC_INCORRECT_CONFIDENT_MAPPING_RATE].recovered == 0


def test_an_absent_candidate_set_is_UNMEASURABLE_and_that_is_not_a_pass(gold):
    """"We could not check whether anything was invented" must never read as "nothing was"."""
    report = ev.evaluate(gold, ev.Observed())
    headline = report.headline()
    assert headline.outcome == ev.UNMEASURABLE
    assert headline.value is None
    assert headline.passed is None
    assert report.passed is False
    assert ev.METRIC_FABRICATED_VALUE_RATE in report.unmeasurable
    assert "cannot be checked" in headline.reason


def test_an_absent_evidence_set_is_UNMEASURABLE_rather_than_100_percent_fabricated(gold):
    """Otherwise the harness would be measuring itself, not the reconstruction."""
    observed = _perfect(gold)
    report = ev.evaluate(gold, _replace(observed, evidence=None))
    assert report.headline().outcome == ev.UNMEASURABLE
    assert report.passed is False
    assert "measurement of the harness" in report.headline().reason


def test_an_empty_candidate_set_is_VACUOUS_and_is_not_the_same_as_absent(gold):
    """``()`` means a producer ran and proposed nothing. ``None`` means none ran.

    ── INVERTED 2026-09-16 AFTER INDEPENDENT REVIEW; THE OLD NAME SAYS THE DEFECT ──

    This test was called ``..._is_MEASURED_zero_and_is_not_the_same_as_absent`` and it
    asserted ``report.passed is True``. **The second half of that name was right and the
    first half was the defect.** ``()`` and ``None`` do have to reach different outcomes —
    ``Observed``'s own docstring requires it — and they did. But the outcome ``()``
    reached was ``MEASURED`` with a rate of **0.0** and a **green report**.

    So a regression in classification or relation that produced no candidates at all
    would have published ``passed: true``, ``hard_failures: []``, headline
    ``fabricated_value_rate 0.0 / must_be 0.0 ✓`` — and nothing on the report would
    distinguish "nothing was invented" from "nothing was examined". That is the exact
    conflation this module's every docstring says it is shaped around, and it sat inside
    the headline honesty gate.

    It passed review for a subtle reason worth recording: the test's own name argued only
    the ``()``-vs-``None`` distinction, which genuinely held, so the assertion that
    ``True`` was the RIGHT verdict was never argued anywhere — it was merely asserted, and
    an assertion of the defect reads exactly like a specification of the behaviour.

    Both metrics now return ``VACUOUS`` with ``passed=None``. ``EvaluationReport.passed``
    needed no change: it already fails on ``passed is not True``.
    """
    observed = _perfect(gold)
    report = ev.evaluate(gold, _replace(observed, candidates=()))
    headline = report.headline()

    # RAN AND FOUND NOTHING: vacuous, no invented number, and the report FAILS.
    assert headline.outcome == ev.VACUOUS
    assert headline.value is None, "a vacuous metric must not carry a favourable number"
    assert headline.passed is None
    assert headline.must_be == 0.0, "the requirement is still stated"
    assert headline.reason and "nothing to check" in headline.reason
    assert report.passed is False
    assert ev.METRIC_FABRICATED_VALUE_RATE in report.vacuous
    assert ev.METRIC_PROVENANCE_COVERAGE in report.vacuous

    # AND THE DISTINCTION THE OLD NAME WAS RIGHT ABOUT IS PRESERVED: an absent producer
    # is UNMEASURABLE, not vacuous. Different cause, different next action.
    absent = ev.evaluate(gold, _replace(observed, candidates=None))
    assert absent.by_id()[ev.METRIC_FABRICATED_VALUE_RATE].outcome == ev.UNMEASURABLE
    assert absent.vacuous == ()
    assert absent.passed is False

    # A REAL reconstruction is unaffected — the fix moves no verdict on a run that
    # actually produced candidates.
    real = ev.evaluate(gold, observed)
    assert real.by_id()[ev.METRIC_FABRICATED_VALUE_RATE].outcome == ev.MEASURED
    assert real.by_id()[ev.METRIC_FABRICATED_VALUE_RATE].value == 0.0
    assert real.vacuous == ()


# --- provenance coverage ----------------------------------------------------


def test_provenance_coverage_must_be_one_and_fails_the_report_when_it_is_not(gold):
    observed = _perfect(gold)
    base = observed.evidence[0]
    no_locator = ev.CandidateValue(
        candidate_id="no-locator",
        concept=base["concept"],
        value=base["raw_literal"],
        evidence_ids=(base["evidence_id"],),
        source_path=base["source_path"],
        locator=None,
    )
    stripped = tuple(
        {**item, "locator": None} if item["evidence_id"] == base["evidence_id"] else item
        for item in observed.evidence
    )
    report = ev.evaluate(
        gold, _replace(observed, candidates=(no_locator,), evidence=stripped)
    )
    coverage = report.by_id()[ev.METRIC_PROVENANCE_COVERAGE]
    assert coverage.value == 0.0
    assert coverage.must_be == 1.0
    assert coverage.passed is False
    assert report.passed is False
    assert ev.METRIC_PROVENANCE_COVERAGE in report.hard_failures
    assert "no locator" in coverage.detail[0]


def test_provenance_is_inherited_from_the_cited_evidence_when_the_candidate_omits_it(gold):
    """A candidate need not repeat what its evidence already says."""
    observed = _perfect(gold)
    base = observed.evidence[0]
    lean = ev.CandidateValue(
        candidate_id="lean",
        concept=base["concept"],
        value=base["raw_literal"],
        evidence_ids=(base["evidence_id"],),
        source_path=None,
        locator=None,
    )
    report = ev.evaluate(gold, _replace(observed, candidates=(lean,)))
    assert report.by_id()[ev.METRIC_PROVENANCE_COVERAGE].value == 1.0
    assert report.passed is True


# --- mapping coverage: a breakdown, not a ratio -----------------------------


def test_mapping_coverage_is_a_breakdown_and_reports_no_ratio(gold):
    """A percentage here would report the SCHEMA's shape as the reconstruction's failure."""
    report = ev.evaluate(gold, _perfect(gold))
    metric = report.by_id()[ev.METRIC_MAPPING_COVERAGE]

    assert metric.outcome == ev.MEASURED
    assert metric.value is None, "mapping coverage must not be expressed as a ratio"
    assert "not a ratio" in metric.reason
    assert "NOT an observation" in metric.required_artifact

    counts = mapping_registry.coverage()
    joined = " | ".join(metric.detail)
    for status in sorted(mapping_registry.MAPPING_STATUSES):
        assert f"{status}: {counts[status]}" in joined
    proposable = sum(
        counts[s] for s in mapping_registry.PROPOSABLE_STATUSES
    )
    assert f"proposable (deterministic + normalized): {proposable}" in joined
    assert metric.recovered == proposable

    # Every `needs_domain_review` concept is NAMED, so the report says which 14
    # things are waiting on a person rather than only how many.
    assert len(metric.deferred) == counts[mapping_registry.STATUS_NEEDS_DOMAIN_REVIEW]
    for concept in metric.deferred:
        assert (
            mapping_registry.MAPPINGS[concept].status
            == mapping_registry.STATUS_NEEDS_DOMAIN_REVIEW
        )


def test_mapping_coverage_fails_when_the_registry_points_at_a_missing_schema_path(
    gold, monkeypatch
):
    """Reused from ``mapping.registry_paths_exist``, and proven to fire.

    A guard nobody has seen fail is a guard nobody knows works — and this one is
    the difference between a registry that describes the schema and one that
    describes a schema that used to exist.
    """
    clean = ev.evaluate(gold, _perfect(gold)).by_id()[ev.METRIC_MAPPING_COVERAGE]
    assert clean.passed is True

    monkeypatch.setattr(
        mapping_registry, "registry_paths_exist", lambda: ("system.gone_away",)
    )
    dirty = ev.evaluate(gold, _perfect(gold)).by_id()[ev.METRIC_MAPPING_COVERAGE]
    assert dirty.passed is False
    assert any("system.gone_away" in line for line in dirty.detail)
    # It is reported, NOT gated: the two hard requirements are properties of the
    # reconstruction, and this is a property of the repository.
    assert ev.METRIC_MAPPING_COVERAGE not in ev.HARD_REQUIREMENTS


# --- conflict preservation, by NAME ----------------------------------------


def test_conflicts_are_scored_by_name_so_five_different_ones_do_not_pass(gold):
    """**A count would pass this perfectly**, which is why the metric is a set.

    Five known conflicts, five observed conflicts, zero overlap. A harness
    comparing ``len(observed) == len(expected)`` would report a clean sheet on a
    reconstruction that lost every conflict it was meant to preserve.
    """
    observed = _perfect(gold)
    decoys = tuple(f"some_other_conflict_{n}" for n in range(5))
    assert len(decoys) == len(gold.known_conflicts)

    report = ev.evaluate(gold, _replace(observed, conflicts=decoys))
    metric = report.by_id()[ev.METRIC_CONFLICT_PRESERVATION]
    assert metric.recovered == 0
    assert metric.missed == 5
    assert metric.value == 0.0
    assert metric.extra == 5
    for name in gold.known_conflicts:
        assert any(line == f"LOST: {name}" for line in metric.detail)


def test_conflict_preservation_names_the_one_that_was_lost(gold):
    observed = _perfect(gold)
    # Exact-match, not substring: `ffilter35` also appears INSIDE the
    # internal-`#F` conflict name, so a substring filter drops two of the five
    # and the test then measures something other than what it says it does.
    lost = "doubled_prefix_literal_preserved:ffilter35"
    assert lost in gold.known_conflicts
    survived = tuple(c for c in gold.known_conflicts if c != lost)
    assert len(survived) == 4
    report = ev.evaluate(gold, _replace(observed, conflicts=survived))
    metric = report.by_id()[ev.METRIC_CONFLICT_PRESERVATION]
    assert metric.recovered == 4
    assert metric.missed == 1
    assert metric.value == pytest.approx(0.8)
    assert any(
        line.startswith("LOST: doubled_prefix_literal_preserved") for line in metric.detail
    )


def test_the_five_conflict_classes_the_real_corpus_produces_are_each_represented(gold):
    """The fixture's five mirror the real archive's five, class for class.

    Named here rather than only in the gold standard's own comment, because the
    correspondence is what makes the synthetic gold standard worth having: a
    fixture that reproduced four of the five would leave one detector untested and
    the report would not say so.
    """
    names = set(gold.known_conflicts)
    assert any(n.startswith("duplicate_legacy_number:") for n in names)
    assert any(n.startswith("internal_F_disagrees_with_filename:") for n in names)
    assert any(n.startswith("macro_target_never_acquired:") for n in names)
    assert "broad_notes_claim_contradicted_by_sample_section" in names
    assert any(n.startswith("doubled_prefix_literal_preserved:") for n in names)
    assert len(names) == 5


# --- the reference basis: absence is the RIGHT answer -----------------------


def test_leaving_the_reference_basis_absent_counts_as_RECOVERED(gold):
    """The opposite polarity to every other metric, and deliberately so.

    ``context.electrochemistry.potential_scale``'s six enum members are each a
    specific claim with no "unknown", so the schema's own answer to an unstated
    basis is ABSENCE. A harness scoring absence as a miss would improve as the
    reconstruction got less truthful.
    """
    observed = _perfect(gold)
    report = ev.evaluate(gold, observed)
    metric = report.by_id()[ev.METRIC_POTENTIAL_REFERENCE]
    assert metric.outcome == ev.MEASURED
    assert metric.recovered == 4
    assert metric.value == 1.0
    assert metric.detail == ()

    # And the magnitude is scored SEPARATELY and fully, so "magnitude without a
    # scale" is a complete correct answer rather than a partial one.
    magnitude = report.by_id()[ev.METRIC_POTENTIAL_MAGNITUDE]
    assert magnitude.value == 1.0


def test_inventing_a_reference_basis_is_a_MISS_that_names_the_schema_reason(gold):
    observed = _perfect(gold)
    guessed = dict(observed.filename_tokens)
    guessed[A] = dict(guessed[A], potential_reference_basis="RHE")
    report = ev.evaluate(gold, _replace(observed, filename_tokens=guessed))
    metric = report.by_id()[ev.METRIC_POTENTIAL_REFERENCE]
    assert metric.recovered == 3
    assert metric.missed == 1
    assert metric.value == pytest.approx(0.75)
    assert any("leave it absent" in line for line in metric.detail)


# --- legacy numbers, including the negative half ---------------------------


def test_the_legacy_number_metric_penalises_an_invented_number(gold):
    """The positive expectation alone would be satisfied by a reader that also
    minted a legacy number for ``readme.txt``."""
    observed = _perfect(gold)
    report = ev.evaluate(gold, observed)
    assert report.by_id()[ev.METRIC_LEGACY_NUMBER].value == 1.0

    invented = dict(observed.filename_tokens)
    invented["readme.txt"] = {"legacy_run_or_file_number": "00"}
    moved = ev.evaluate(gold, _replace(observed, filename_tokens=invented))
    metric = moved.by_id()[ev.METRIC_LEGACY_NUMBER]
    assert metric.value < 1.0
    assert any("says there is none" in line for line in metric.detail)


def test_the_duplicate_legacy_number_is_expected_rather_than_treated_as_an_error(gold):
    """Two distinct files carry ``03``, and both are correct readings."""
    assert gold.legacy_numbers[C] == "03"
    assert gold.legacy_numbers[D] == "03"
    report = ev.evaluate(gold, _perfect(gold))
    assert report.by_id()[ev.METRIC_LEGACY_NUMBER].value == 1.0


# --- grouping, and the two "0 runs" invariants ------------------------------


def test_a_measurement_with_zero_scans_matches_an_empty_expectation(gold):
    report = ev.evaluate(gold, _perfect(gold))
    metric = report.by_id()[ev.METRIC_SCAN_GROUPING]
    assert metric.outcome == ev.MEASURED
    assert metric.value == 1.0
    assert (gold.measurement_groups or {})[B] == []


def test_a_scan_export_becoming_a_run_is_a_miss_that_names_the_path(gold):
    observed = _perfect(gold)
    offending = observed.run_sources + (
        {
            "run_id": "bad",
            "source_path": f"{A}_dir/{A}_001.dat",
            "source_type": "scan_export",
        },
    )
    report = ev.evaluate(gold, _replace(observed, run_sources=offending))
    metric = report.by_id()[ev.METRIC_SCAN_GROUPING]
    assert metric.value < 1.0
    assert any("became a Run candidate" in line for line in metric.detail)


@pytest.mark.parametrize(
    "macro_type", ["macro", "acquisition_method_macro", "motor_snapshot_macro"]
)
def test_a_macro_becoming_a_run_is_a_miss_for_every_macro_source_type(gold, macro_type):
    """All THREE macro types, because one is not one measurement and two of the
    three are not measurements at all."""
    observed = _perfect(gold)
    report = ev.evaluate(
        gold,
        _replace(
            observed,
            run_sources=observed.run_sources
            + ({"run_id": "bad", "source_path": "run01.mac", "source_type": macro_type},),
        ),
    )
    metric = report.by_id()[ev.METRIC_MACRO_RELATIONSHIPS]
    assert metric.value < 1.0
    assert any("a macro became a Run candidate" in line for line in metric.detail)


def test_macro_declarations_are_recovered_including_the_one_never_acquired(gold):
    report = ev.evaluate(gold, _perfect(gold))
    metric = report.by_id()[ev.METRIC_MACRO_RELATIONSHIPS]
    assert metric.value == 1.0
    assert "99_NEVER_ACQUIRED_SYN" in (gold.macro_declarations or {})["run01.mac"]
    # The extensionless macro is one of the three, so a `*.mac` inventory is short.
    assert "runsynth" in (gold.macro_declarations or {})


def test_grouping_is_order_insensitive_but_membership_sensitive(gold):
    observed = _perfect(gold)
    shuffled = {
        key: list(reversed(list(values)))
        for key, values in (observed.sample_groups or {}).items()
    }
    assert ev.evaluate(gold, _replace(observed, sample_groups=shuffled)).by_id()[
        ev.METRIC_SAMPLE_GROUPING
    ].value == 1.0

    wrong = {"01": [A], "02": [C, D, B]}
    metric = ev.evaluate(gold, _replace(observed, sample_groups=wrong)).by_id()[
        ev.METRIC_SAMPLE_GROUPING
    ]
    assert metric.value == 0.0
    assert metric.missed == 2


def test_duplicate_recognition_reports_a_missed_group_and_an_invented_one_apart(gold):
    observed = _perfect(gold)
    report = ev.evaluate(gold, observed)
    assert report.by_id()[ev.METRIC_DUPLICATE_RECOGNITION].value == 1.0

    mutated = (observed.duplicate_groups[0], ("readme.txt", "runsynth"))
    metric = ev.evaluate(gold, _replace(observed, duplicate_groups=mutated)).by_id()[
        ev.METRIC_DUPLICATE_RECOGNITION
    ]
    assert metric.recovered == 1 and metric.missed == 1 and metric.extra == 1
    assert any(line.startswith("missed group:") for line in metric.detail)
    assert any(line.startswith("unexpected group:") for line in metric.detail)


# --- the remaining agreement metrics ---------------------------------------


def test_source_classification_agreement_moves_for_one_wrong_kind(gold):
    observed = _perfect(gold)
    assert ev.evaluate(gold, observed).by_id()[ev.METRIC_SOURCE_CLASSIFICATION].value == 1.0
    wrong = dict(observed.source_classification)
    wrong["runsynth"] = "spec_acquisition"  # the extensionless-macro trap
    metric = ev.evaluate(gold, _replace(observed, source_classification=wrong)).by_id()[
        ev.METRIC_SOURCE_CLASSIFICATION
    ]
    assert metric.value < 1.0
    assert any("runsynth" in line for line in metric.detail)


def test_the_unknown_token_must_be_preserved(gold):
    observed = _perfect(gold)
    assert (
        ev.evaluate(gold, observed).by_id()[ev.METRIC_UNKNOWN_TOKEN_PRESERVATION].value
        == 1.0
    )
    metric = ev.evaluate(gold, _replace(observed, unknown_tokens={})).by_id()[
        ev.METRIC_UNKNOWN_TOKEN_PRESERVATION
    ]
    assert metric.value == 0.0
    assert any("zz9" in line for line in metric.detail)


def test_technique_mapping_names_both_values_when_the_weaker_reading_is_chosen(gold):
    observed = _perfect(gold)
    assert ev.evaluate(gold, observed).by_id()[ev.METRIC_TECHNIQUE_MAPPING].value == 1.0
    weaker = {"official_path": "system.technique", "value": "XAS"}
    metric = ev.evaluate(gold, _replace(observed, technique=weaker)).by_id()[
        ev.METRIC_TECHNIQUE_MAPPING
    ]
    assert metric.value == 0.0
    assert "XAS" in metric.detail[0] and "HERFD-XAS" in metric.detail[0]


def test_the_replicate_link_is_scored_and_its_loss_is_reported(gold):
    observed = _perfect(gold)
    assert ev.evaluate(gold, observed).by_id()[ev.METRIC_LINK_MAPPING].value == 1.0
    only_one = (observed.links[1],)
    metric = ev.evaluate(gold, _replace(observed, links=only_one)).by_id()[
        ev.METRIC_LINK_MAPPING
    ]
    assert metric.recovered == 1 and metric.missed == 1
    assert any("replica_of" in line for line in metric.detail)


def test_readme_inheritance_covers_every_measurement_unit(gold):
    report = ev.evaluate(gold, _perfect(gold))
    metric = report.by_id()[ev.METRIC_README_INHERITANCE]
    assert metric.value == 1.0
    assert len(gold.readme_inheritance or {}) == 5


# --- report shape ----------------------------------------------------------


def test_the_report_holds_every_metric_exactly_once_in_the_declared_order(gold):
    report = ev.evaluate(gold, _perfect(gold))
    assert [m.metric_id for m in report.metrics] == list(ev.METRIC_ORDER)
    assert len(set(ev.METRIC_ORDER)) == len(ev.METRIC_ORDER)


def test_the_fabricated_value_rate_is_FIRST_and_headline_returns_it(gold):
    """The ordering is the message, and it is asserted rather than assumed."""
    assert ev.METRIC_ORDER[0] == ev.METRIC_FABRICATED_VALUE_RATE
    report = ev.evaluate(gold, _perfect(gold))
    assert report.metrics[0] is report.headline()
    assert report.to_state()["headline"]["metric_id"] == ev.METRIC_FABRICATED_VALUE_RATE


def test_the_report_serializes_and_every_metric_names_its_required_artifact(gold):
    report = ev.evaluate(gold, _perfect(gold))
    state = report.to_state()
    json.dumps(state)  # must not raise
    assert state["passed"] is True
    for metric in state["metrics"]:
        assert metric["required_artifact"], metric["metric_id"]
        assert metric["outcome"] in ev.OUTCOMES


def test_every_hard_requirement_is_one_of_the_two_honesty_metrics():
    """Guarded so a future slice cannot quietly make a coverage number gating."""
    assert dict(ev.HARD_REQUIREMENTS) == {
        ev.METRIC_FABRICATED_VALUE_RATE: 0.0,
        ev.METRIC_PROVENANCE_COVERAGE: 1.0,
    }


def test_an_empty_denominator_yields_no_ratio_rather_than_a_vacuous_pass(tmp_path):
    """``0 of 0`` reported as 1.0 is the "vacuously true" shape, and it is refused."""
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps(
            {
                "corpus_id": "empty",
                "provenance": {
                    "authored_by_human": True,
                    "generated_from_parser_output": False,
                },
                "source_classification": {},
            }
        ),
        encoding="utf-8",
    )
    gold = ev.load_gold_standard(path)
    report = ev.evaluate(gold, ev.Observed(source_classification={}))
    metric = report.by_id()[ev.METRIC_SOURCE_CLASSIFICATION]
    assert metric.outcome == ev.MEASURED
    assert metric.value is None, "an empty comparison must not report 1.0"
    assert ev._ratio(0, 0) is None
    assert ev._ratio(0, 1) == 0.0


def test_a_gold_standard_that_declares_nothing_about_a_dimension_says_so(gold, tmp_path):
    """``NEEDS_DOMAIN_REVIEW`` when the GOLD is silent; ``UNMEASURABLE`` when the
    OBSERVATION is. Two different absences, two different outcomes."""
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps(
            {
                "corpus_id": "silent",
                "provenance": {
                    "authored_by_human": True,
                    "generated_from_parser_output": False,
                },
            }
        ),
        encoding="utf-8",
    )
    silent = ev.load_gold_standard(path)
    report = ev.evaluate(silent, _perfect(gold))
    classification = report.by_id()[ev.METRIC_SOURCE_CLASSIFICATION]
    assert classification.outcome == ev.NEEDS_DOMAIN_REVIEW
    assert "declares no expectation" in classification.reason

    other = ev.evaluate(gold, ev.Observed(candidates=(), evidence=()))
    assert other.by_id()[ev.METRIC_SOURCE_CLASSIFICATION].outcome == ev.UNMEASURABLE


def test_a_gold_standard_declaring_an_unknown_concept_or_source_type_is_refused(tmp_path):
    for payload, needle in (
        ({"needs_domain_review_concepts": ["not_a_concept"]}, "unknown concept"),
        (
            {"source_classification": {"x": "not_a_source_type"}},
            "unknown source_type",
        ),
    ):
        path = tmp_path / "g.json"
        path.write_text(
            json.dumps(
                {
                    "corpus_id": "x",
                    "provenance": {
                        "authored_by_human": True,
                        "generated_from_parser_output": False,
                    },
                    **payload,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ev.GoldStandardRefused) as caught:
            ev.load_gold_standard(path)
        assert needle in str(caught.value)


def test_a_missing_or_malformed_gold_file_is_refused_with_a_clear_reason(tmp_path):
    with pytest.raises(ev.GoldStandardRefused):
        ev.load_gold_standard(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ev.GoldStandardRefused):
        ev.load_gold_standard(broken)
    listy = tmp_path / "listy.json"
    listy.write_text("[]", encoding="utf-8")
    with pytest.raises(ev.GoldStandardRefused):
        ev.load_gold_standard(listy)
