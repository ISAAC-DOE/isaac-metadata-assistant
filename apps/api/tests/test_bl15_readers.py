"""The BL15-2 source readers, against SANITIZED SYNTHETIC fixtures only.

**NO PART OF THE REAL ARCHIVE IS IN THIS REPOSITORY** (``CLAUDE.md`` §6). Every
fixture under ``tests/fixtures/bl15/`` is invented, and
:func:`test_every_fixture_is_synthetic` greps them all for a list of real-corpus
markers so a future session cannot quietly paste a real file in.

The two tests this suite exists for, stated up front because everything else is
in service of them:

* :func:`test_every_raw_literal_is_byte_identical_to_its_source` — across EVERY
  fixture, every emitted ``raw_literal`` appears verbatim in the bytes it was read
  from. A reader that rewrote its input would make the whole evidence contract a
  decoration.
* :func:`test_one_unknown_token_never_discards_a_filename` — the **negative
  control**. A stem carrying a token the profile does not know still yields a
  named statement for every token it does know, plus an ``unknown_token`` for the
  rest.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from isaac_api.bl15 import classify, filenames, macros, notes, profiles, scans, spec
from isaac_api.bl15._emit import SKIP_EVIDENCE_CEILING
from isaac_api.bl15.evidence import (
    CONCEPT_ACQUISITION_METHOD,
    CONCEPT_ACQUISITION_TARGET,
    CONCEPT_BEAMSIZE,
    CONCEPT_BEAMTIME_DATES,
    CONCEPT_BEAMTIME_PURPOSE,
    CONCEPT_BEFORE_AFTER_STATE,
    CONCEPT_CYCLING_STATE,
    CONCEPT_DETECTOR_COLUMN,
    CONCEPT_DRY_STATE,
    CONCEPT_ECHEM_PROCEDURE,
    CONCEPT_ELECTROLYTE_OR_MEDIUM,
    CONCEPT_ELEMENT,
    CONCEPT_EMISSION_ENERGY,
    CONCEPT_ENERGY_GRID,
    CONCEPT_FILTER,
    CONCEPT_FLOW_RATE,
    CONCEPT_GAS_CONDITION,
    CONCEPT_LEGACY_NUMBER,
    CONCEPT_LOADING_OR_THICKNESS,
    CONCEPT_MONOCHROMATOR_CALIBRATION,
    CONCEPT_MOTOR_POSITION,
    CONCEPT_NEW_SPOT,
    CONCEPT_NOTE_FILE_NUMBER_ROW,
    CONCEPT_PH,
    CONCEPT_POTENTIAL_MAGNITUDE,
    CONCEPT_POTENTIAL_REFERENCE,
    CONCEPT_QUALITY_NOTE,
    CONCEPT_REPEAT_MARKER,
    CONCEPT_SAMPLE_NAME,
    CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
    CONCEPT_SAMPLE_POSITION,
    CONCEPT_SAMPLE_PREPARATION,
    CONCEPT_SCAN_COMMAND,
    CONCEPT_SCAN_COUNT,
    CONCEPT_SPEC_FILE_DECLARATION,
    CONCEPT_SPEC_USER_STRING,
    CONCEPT_SPECTROMETER_CONFIG,
    CONCEPT_STEP_NUMBER,
    CONCEPT_TRIGGER,
    CONCEPT_UNKNOWN_TOKEN,
    CONCEPTS,
    DETERMINISM_NORMALIZED,
    DETERMINISM_READ,
    MAX_EVIDENCE_PER_SOURCE,
    MAX_SOURCE_BYTES,
    SCOPE_BEAMTIME,
    SCOPE_MEASUREMENT,
    SCOPE_SAMPLE_GROUP,
    SCOPE_SCAN,
    SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
    SOURCE_TYPE_ALIGNMENT,
    SOURCE_TYPE_BEAMTIME_NOTES,
    SOURCE_TYPE_DETECTOR_PRODUCT,
    SOURCE_TYPE_MACRO,
    SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
    SOURCE_TYPE_PROCESSED_SPECTRUM,
    SOURCE_TYPE_SCAN_EXPORT,
    SOURCE_TYPE_SHARED_README,
    SOURCE_TYPE_SPEC_ACQUISITION,
    SOURCE_TYPE_STANDARD_OR_REFERENCE,
    SOURCE_TYPE_UNKNOWN,
    ReaderResult,
    SourceEvidence,
)
from isaac_api.bl15.inventory import SourceRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "bl15"


# --- helpers ----------------------------------------------------------------


def _record(path: Path, *, archive_path: str | None = None) -> SourceRecord:
    data = path.read_bytes()
    base = path.name
    extension = base.rsplit(".", 1)[1].lower() if "." in base else ""
    rel = archive_path or base
    return SourceRecord(
        archive_path=rel,
        basename=base,
        extension=extension,
        size_bytes=len(data),
        content_sha256=hashlib.sha256(data).hexdigest(),
        parent_dir=rel.rsplit("/", 1)[0] if "/" in rel else "",
        depth=rel.count("/"),
    )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _synthetic_record(
    basename: str, *, body: str = "", extension: str | None = None
) -> SourceRecord:
    ext = (
        extension
        if extension is not None
        else (basename.rsplit(".", 1)[1].lower() if "." in basename else "")
    )
    return SourceRecord(
        archive_path=basename,
        basename=basename,
        extension=ext,
        size_bytes=len(body.encode("utf-8")),
        content_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        parent_dir="",
        depth=0,
    )


def _stems(name: str) -> list[str]:
    """Non-comment, non-blank lines of a filename fixture."""
    return [
        line.strip()
        for line in _text(FIXTURES / "filenames" / name).splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _read_stem(stem: str, **kwargs) -> ReaderResult:
    return filenames.read_filename(
        _synthetic_record(stem), stem=stem, **kwargs
    )


def _by_concept(result: ReaderResult, concept: str) -> list[SourceEvidence]:
    return [e for e in result.evidence if e.concept == concept]


def _one(result: ReaderResult, concept: str) -> SourceEvidence:
    matches = _by_concept(result, concept)
    assert len(matches) == 1, (
        f"expected exactly one {concept!r}, got {len(matches)}: "
        f"{[m.raw_literal for m in matches]}"
    )
    return matches[0]


SPEC_FIXTURE = FIXTURES / "spec" / "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
DAT_FIXTURE = (
    FIXTURES / "scans" / "03_01_ZZ1_acid_beforeCycling_100mV_filter10_001.dat"
)
RENAME_GROUP = FIXTURES / "spec" / "rename-group"
NOTES_FIXTURE = FIXTURES / "notes" / "beamtime-notes.txt"
README_FIXTURE = FIXTURES / "notes" / "readme.txt"


def _every_fixture_file() -> list[Path]:
    return sorted(p for p in FIXTURES.rglob("*") if p.is_file())


# ===========================================================================
# 1. DATA GOVERNANCE — the guard that must exist
# ===========================================================================

#: Literals that appear in the REAL archive and must never appear in a fixture.
#: Sample codes, a material, the scientist's surname from the archive folder, a
#: real emission energy and a real beamsize energy. `CLAUDE.md` §6.
REAL_CORPUS_MARKERS: tuple[str, ...] = (
    "JK1",
    "JK2",
    "JK3",
    "IrTiO2",
    "Sokaras",
    "9175.4",
    "11215",
)


def test_every_fixture_is_synthetic():
    """No real-corpus marker appears anywhere under ``tests/fixtures/bl15/``.

    Read as BYTES, decoded permissively, so a fixture with an unusual encoding
    cannot slip past by failing to decode — the same trap ``CLAUDE.md`` §11
    records for a text tool handed bytes it cannot read.
    """
    offenders: list[tuple[str, str]] = []
    files = _every_fixture_file()
    assert files, "the fixture directory is empty — the guard would be vacuous"
    for path in files:
        body = path.read_bytes().decode("utf-8", "replace")
        for marker in REAL_CORPUS_MARKERS:
            if marker in body:
                offenders.append((str(path.relative_to(REPO_ROOT)), marker))
    assert not offenders, (
        "a real-corpus marker appears in a committed fixture: " f"{offenders}"
    )


def test_the_synthetic_guard_would_actually_fire():
    """Negative control for the guard above.

    A guard that passes because its marker list can never match is worse than no
    guard. This proves the mechanism detects a marker when one is present.
    """
    body = "sample: JK2 in base\n"
    assert any(marker in body for marker in REAL_CORPUS_MARKERS)


def test_no_fixture_holds_a_nul_byte():
    """``CLAUDE.md`` §11's greppability rule, applied to this directory.

    A tracked file holding a NUL is invisible to ``grep``/``rg`` without ``-a``,
    and a zero-hit sweep over it is indistinguishable from a skipped file. That
    has cost this repository whole sessions.
    """
    holders = [
        str(p.relative_to(REPO_ROOT))
        for p in _every_fixture_file()
        if b"\x00" in p.read_bytes()
    ]
    assert holders == []


# ===========================================================================
# 2. THE TWO TESTS THAT ARE THE WHOLE POINT
# ===========================================================================


def _all_fixture_readings() -> list[tuple[str, bytes, ReaderResult]]:
    """Every reader run over every fixture it applies to.

    Returns ``(label, source bytes, result)`` so a caller can check a reading
    against the exact bytes it came from.
    """
    readings: list[tuple[str, bytes, ReaderResult]] = []

    for name in (
        "angel-style-set.txt",
        "potential-units-set.txt",
        "ffilter-typo-set.txt",
        "duplicate-legacy-number-set.txt",
        "unknown-token-set.txt",
    ):
        source = (FIXTURES / "filenames" / name).read_bytes()
        for stem in _stems(name):
            readings.append(
                (f"filenames/{name}:{stem}", source, _read_stem(stem))
            )

    for path in sorted((FIXTURES / "spec").rglob("*")):
        if not path.is_file() or path.suffix == ".md":
            continue
        readings.append(
            (
                f"spec/{path.name}",
                path.read_bytes(),
                spec.read_spec_acquisition(_record(path), _text(path)),
            )
        )

    readings.append(
        (
            "scans/dat",
            DAT_FIXTURE.read_bytes(),
            scans.read_scan_export(_record(DAT_FIXTURE), _text(DAT_FIXTURE)),
        )
    )

    for path in sorted((FIXTURES / "macros").glob("*.mac")):
        readings.append(
            (
                f"macros/{path.name}",
                path.read_bytes(),
                macros.read_macro(_record(path), _text(path)),
            )
        )

    readings.append(
        (
            "notes/readme.txt",
            README_FIXTURE.read_bytes(),
            notes.read_shared_readme(
                _record(README_FIXTURE), _text(README_FIXTURE)
            ),
        )
    )
    readings.append(
        (
            "notes/beamtime-notes.txt",
            NOTES_FIXTURE.read_bytes(),
            notes.read_beamtime_notes(
                _record(NOTES_FIXTURE), _text(NOTES_FIXTURE)
            ),
        )
    )
    return readings


def test_every_raw_literal_is_byte_identical_to_its_source():
    """``raw_literal`` is VERBATIM, for every item of every reading.

    Checked against the source's own BYTES rather than against a re-derived
    string.

    **Two sources, and they are kept apart rather than merged into one
    permissive haystack.** Most statements are read from a file's CONTENT. A
    few are read from its NAME — a ``.dat``'s stem and scan index, and every
    filename token — and for those the name IS the source. The test therefore
    requires each literal to appear in the content, OR in the name AND to carry
    a locator that says so (``basename`` / ``filename token``). A literal that
    appeared in neither, or that came from the name while claiming a content
    locator, fails.
    """
    readings = _all_fixture_readings()
    assert len(readings) > 40, (
        f"only {len(readings)} readings collected — this test is only as strong "
        f"as its coverage"
    )
    total = 0
    from_name = 0
    for label, source_bytes, result in readings:
        content = source_bytes.decode("utf-8", "replace")
        name = result.source_path
        for item in result.evidence:
            total += 1
            if item.raw_literal in content:
                continue
            names_the_name = item.locator.startswith(
                ("basename ", "filename token ")
            )
            assert names_the_name, (
                f"{label}: raw_literal {item.raw_literal!r} is not in the "
                f"source's content and its locator {item.locator!r} does not "
                f"say it was read from the name"
            )
            assert item.raw_literal in name or item.raw_literal in label, (
                f"{label}: raw_literal {item.raw_literal!r} at "
                f"{item.locator!r} appears in neither the content nor the name"
            )
            from_name += 1
    assert total > 300, f"only {total} evidence items checked"
    # Exactly ONE name-derived literal reaches the second branch, and naming it
    # is stronger than a threshold: the filename fixtures LIST their stems, so
    # every filename token is also literally present in the file it was read
    # from, and only the `.dat`'s basename statement is name-only.
    assert from_name == 1, (
        f"expected exactly one name-only literal (the .dat basename), saw "
        f"{from_name}"
    )


_SPAN = re.compile(r"\[chars (\d+)\.\.(\d+)\]")


def test_a_filename_locator_names_the_exact_character_span():
    """``filename token 4 [chars 23..31]`` -> ``stem[23:31] == raw_literal``.

    The locator is what a scientist uses to find the token by eye. A span that
    was merely plausible would be worse than no span.
    """
    checked = 0
    for name in (
        "angel-style-set.txt",
        "potential-units-set.txt",
        "ffilter-typo-set.txt",
        "duplicate-legacy-number-set.txt",
        "unknown-token-set.txt",
    ):
        for stem in _stems(name):
            for item in _read_stem(stem).evidence:
                match = _SPAN.search(item.locator)
                assert match, f"no span in locator {item.locator!r}"
                start, end = int(match.group(1)), int(match.group(2))
                assert stem[start:end] == item.raw_literal, (
                    f"{stem!r}: locator says chars {start}..{end} = "
                    f"{stem[start:end]!r}, literal is {item.raw_literal!r}"
                )
                checked += 1
    assert checked > 80, f"only {checked} spans checked"


def test_one_unknown_token_never_discards_a_filename():
    """THE NEGATIVE CONTROL.

    Every stem in ``unknown-token-set.txt`` carries at least one token no
    recognizer claims. For each, the reader must still emit a NAMED statement for
    every token it does recognise, AND an ``unknown_token`` for the rest — never
    a refusal and never a silent drop.
    """
    stems = _stems("unknown-token-set.txt")
    assert stems, "the negative-control fixture is empty"

    with_unknown = 0
    with_empty_token = 0
    for stem in stems:
        result = _read_stem(stem)
        assert result.refused_reason is None, (
            f"{stem!r} was REFUSED because of an unknown token: "
            f"{result.refused_reason}"
        )
        # Every non-empty token produced at least one statement. This is the
        # load-bearing half: nothing is dropped, whatever the anomaly.
        tokens = [t for t in stem.split("_") if t]
        literals = {item.raw_literal for item in result.evidence}
        assert literals == set(tokens), (
            f"{stem!r}: tokens {sorted(set(tokens))} but literals "
            f"{sorted(literals)} — a token was dropped"
        )
        # Each stem's anomaly is DISCLOSED as one of the two kinds it can be:
        # a token nothing claimed, or a token structure that is not a token.
        unknown = _by_concept(result, CONCEPT_UNKNOWN_TOKEN)
        empty = [e for e in result.skipped if e["reason"] == "empty_token"]
        assert unknown or empty, (
            f"{stem!r} produced neither an unknown_token statement nor an "
            f"empty_token disclosure — its anomaly went unreported"
        )
        with_unknown += bool(unknown)
        with_empty_token += bool(empty)
    assert with_unknown >= 5, (
        f"only {with_unknown} stems exercised the unknown_token path"
    )
    assert with_empty_token == 1, (
        "the doubled-separator stem is the one empty-token case in this set"
    )

    # And the specific case that matters most: a recognisable stem with ONE
    # foreign word in the middle still yields every other concept.
    result = _read_stem("07_01_ZZ1_acid_zzzUnknownToken_filter10_100mV")
    assert _one(result, CONCEPT_LEGACY_NUMBER).normalized_value == 7
    assert _one(result, CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER).normalized_value == 1
    assert _one(result, CONCEPT_SAMPLE_NAME).normalized_value == "ZZ1"
    assert _one(result, CONCEPT_ELECTROLYTE_OR_MEDIUM).normalized_value == "acid"
    assert _one(result, CONCEPT_FILTER).normalized_value == 10
    assert _one(result, CONCEPT_POTENTIAL_MAGNITUDE).normalized_value == 0.1
    assert _one(result, CONCEPT_UNKNOWN_TOKEN).raw_literal == "zzzUnknownToken"


def test_a_stem_with_nothing_recognisable_still_reports_every_token():
    result = _read_stem("totally_opaque_thing")
    assert result.refused_reason is None
    assert [e.raw_literal for e in result.evidence] == [
        "totally",
        "opaque",
        "thing",
    ]
    assert {e.concept for e in result.evidence} == {CONCEPT_UNKNOWN_TOKEN}
    # An unrecognised token is READ, not normalised: there is nothing to name.
    assert all(
        e.determinism == DETERMINISM_READ and e.normalization_rule is None
        for e in result.evidence
    )


# ===========================================================================
# 3. THE PROFILE REGISTRY
# ===========================================================================


def test_the_profile_registry_holds_exactly_the_one_measured_profile():
    assert list(profiles.PROFILES) == ["ssrl_bl152_angel"]
    profile = profiles.profile_for("ssrl_bl152_angel")
    assert profile is not None
    assert profile.profile_version == "1"
    assert (
        profile.display_name
        == "SSRL BL15-2 — Angel-style historical naming profile v1"
    )


def test_the_profile_docstring_records_the_convention_verbatim():
    """The convention the project owner supplied must be quotable from the code.

    Not a style check: the convention is the only statement of intent behind the
    alias tables, and a reader who cannot find it has no way to judge them.
    """
    description = profiles.SSRL_BL152_ANGEL_V1.description
    assert (
        "runNo_sample/electrodeNo_sampleName_loading_electrolyte_gas_"
        "condition_pH_flowRate_filter_Potential" in description
    )
    assert "FIRST PROFILE" in description
    assert "NOT A BEAMLINE STANDARD" in description
    assert "VOCABULARY AND NOT A POSITIONAL GRAMMAR" in description


def test_an_unknown_profile_is_refused_and_does_not_raise():
    result = filenames.read_filename(
        _synthetic_record("03_01_ZZ1_acid"), profile_id="no_such_profile"
    )
    assert result.refused_reason is not None
    assert "unknown_naming_profile" in result.refused_reason
    assert result.evidence == ()


def test_every_recognizer_a_profile_names_is_implemented():
    for profile in profiles.PROFILES.values():
        for name in profile.token_recognizers:
            assert name in filenames._RECOGNIZERS, (
                f"profile {profile.profile_id!r} names recognizer {name!r}, "
                f"which bl15.filenames does not implement"
            )


def test_every_state_alias_canonical_form_has_a_concept():
    """The profile owns the LITERALS; the reader owns the CONCEPTS.

    A canonical form with no concept would make its recognizer silently return
    ``None`` and the token would read as unknown — the exact failure mode that
    looks like a working reader.
    """
    for profile in profiles.PROFILES.values():
        for _literal, canonical in profile.state_aliases:
            assert canonical in filenames._STATE_CONCEPTS, (
                f"state alias canonical {canonical!r} has no concept"
            )


def test_the_unexercised_recognizers_are_named_and_are_the_measured_three():
    """Three recognizers have no real filename example, and that is DECLARED.

    Measured over every token of every stem in the archive: no filename carries a
    gas condition, a pH or a flow rate. The concepts are corpus-attested — the
    beamtime notes state all three in prose — but their FILENAME spellings are
    convention-derived, and a recognizer that has never seen a real example is
    exactly the sort of thing that silently becomes a wrong alias table.
    """
    assert profiles.UNEXERCISED_RECOGNIZERS == frozenset(
        {
            profiles.RECOGNIZER_GAS,
            profiles.RECOGNIZER_PH,
            profiles.RECOGNIZER_FLOW_RATE,
        }
    )
    for name in profiles.UNEXERCISED_RECOGNIZERS:
        assert name in profiles.SSRL_BL152_ANGEL_V1.token_recognizers


def test_a_second_profile_needs_no_change_to_the_reader():
    """The architecture requirement, exercised rather than asserted.

    A second scientist's convention is a profile plus alias tables. This builds
    one that reuses two recognizers, drops the rest, and renames the medium
    vocabulary — and reads a stem through it without a line of
    :mod:`bl15.filenames` changing.
    """
    second = profiles.NamingProfile(
        profile_id="test_second_scientist",
        profile_version="1",
        display_name="A second scientist's convention, for this test only",
        description="Synthetic. Exists to prove the registry is a registry.",
        token_recognizers=(
            profiles.RECOGNIZER_MEDIUM,
            profiles.RECOGNIZER_BARE_INTEGER,
        ),
        medium_aliases=(("saure", "acid"), ("lauge", "base")),
    )
    profiles.PROFILES[second.profile_id] = second
    try:
        result = filenames.read_filename(
            _synthetic_record("07_02_lauge_filter10"),
            profile_id=second.profile_id,
            stem="07_02_lauge_filter10",
        )
        assert result.refused_reason is None
        assert _one(result, CONCEPT_LEGACY_NUMBER).normalized_value == 7
        assert (
            _one(result, CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER).normalized_value
            == 2
        )
        assert (
            _one(result, CONCEPT_ELECTROLYTE_OR_MEDIUM).normalized_value
            == "base"
        )
        # `filter10` is unknown to THIS profile, and survives as such.
        assert _one(result, CONCEPT_UNKNOWN_TOKEN).raw_literal == "filter10"
        # Every statement is stamped with the profile that produced it.
        assert {e.profile_id for e in result.evidence} == {second.profile_id}
    finally:
        del profiles.PROFILES[second.profile_id]


# ===========================================================================
# 4. FILENAME TOKEN READING — exact positive cases
# ===========================================================================


@pytest.mark.parametrize(
    "token,volts",
    [
        ("060mV", 0.06),
        ("100mV", 0.1),
        ("400mV", 0.4),
        ("850mV", 0.85),
        ("1200mV", 1.2),
        ("1500mV", 1.5),
        ("1600mV", 1.6),
        ("1800mV", 1.8),
        ("2000mV", 2.0),
        ("2400mV", 2.4),
        ("1600mv", 1.6),
        ("1p2V", 1.2),
        ("1p5V", 1.5),
        ("1p6V", 1.6),
        ("1p8V", 1.8),
    ],
)
def test_a_potential_is_normalised_to_volts(token, volts):
    result = _read_stem(f"03_01_ZZ1_acid_{token}")
    item = _one(result, CONCEPT_POTENTIAL_MAGNITUDE)
    assert item.raw_literal == token
    assert item.normalized_value == pytest.approx(volts)
    assert item.unit == "V"
    assert item.determinism == DETERMINISM_NORMALIZED
    assert item.normalization_rule in filenames.NORMALIZATION_RULES


def test_a_filename_never_states_a_potential_reference_basis():
    """MANDATORY SEPARATION, and the concept's own docstring says why.

    A filename says ``850mV`` and says nothing about what it is measured against.
    The basis is stated only in the beamtime notes. Asserted over every stem in
    every fixture, not just one.
    """
    for name in (
        "angel-style-set.txt",
        "potential-units-set.txt",
        "ffilter-typo-set.txt",
        "duplicate-legacy-number-set.txt",
        "unknown-token-set.txt",
    ):
        for stem in _stems(name):
            result = _read_stem(stem)
            assert _by_concept(result, CONCEPT_POTENTIAL_REFERENCE) == [], (
                f"{stem!r} emitted a potential_reference_basis from a FILENAME"
            )


@pytest.mark.parametrize(
    "token,number",
    [
        ("filter10", 10),
        ("filter0", 0),
        ("filter20", 20),
        ("filter22", 22),
        ("filter35", 35),
        ("Filter35", 35),
        ("f35", 35),
        ("f10", 10),
        ("f20", 20),
    ],
)
def test_a_filter_is_read_in_both_spellings(token, number):
    item = _one(_read_stem(f"03_01_ZZ1_{token}"), CONCEPT_FILTER)
    assert item.raw_literal == token
    assert item.normalized_value == number


def test_the_ffilter_typo_is_preserved_verbatim_and_named_as_a_typo():
    """The literal is NEVER rewritten, and the rule says what it thinks happened.

    Rewriting ``ffilter35`` to ``filter35`` would destroy the only thing that
    lets a scientist disagree with the reading.
    """
    stem = "46_04_ZZ2_base_after1500Cycling_ffilter35_newSpots_1600mV"
    item = _one(_read_stem(stem), CONCEPT_FILTER)
    assert item.raw_literal == "ffilter35"
    assert item.normalized_value == 35
    assert item.determinism == DETERMINISM_NORMALIZED
    assert item.normalization_rule == filenames.RULE_FILTER_DOUBLED_PREFIX
    assert "DOUBLED-PREFIX TYPO" in item.normalization_rule
    # And a correctly-spelled sibling cites the OTHER rule, so the two are
    # distinguishable in a review surface.
    ok = _one(
        _read_stem("45_04_ZZ2_base_after1500Cycling_filter35_newSpots_1500mV"),
        CONCEPT_FILTER,
    )
    assert ok.normalization_rule == filenames.RULE_FILTER_COUNT


@pytest.mark.parametrize(
    "token,value,unit",
    [
        ("0p5nm", 0.5, "nm"),
        ("2nm", 2, "nm"),
        ("0p2wpc", 0.2, "wt%"),
        ("0p2wtpc", 0.2, "wt%"),
        ("5wpc", 5, "wt%"),
        ("5wtpc", 5, "wt%"),
    ],
)
def test_loading_and_thickness(token, value, unit):
    item = _one(_read_stem(f"71_07_SyTiO2_{token}"), CONCEPT_LOADING_OR_THICKNESS)
    assert item.raw_literal == token
    assert item.normalized_value == pytest.approx(value)
    assert item.unit == unit


@pytest.mark.parametrize(
    "token,side",
    [
        ("beforeCycling", "before"),
        ("after1200Cycling", "after"),
        ("after1200mVCycling", "after"),
        ("after1500Cycling", "after"),
        ("after1500mVCycling", "after"),
        ("after1400Cycling", "after"),
        ("after1400cycling", "after"),
        ("after1stCycling", "after"),
        ("after2ndCycling", "after"),
        ("after1500CV", "after"),
    ],
)
def test_cycling_state_and_its_separate_before_after_statement(token, side):
    result = _read_stem(f"03_01_ZZ1_acid_{token}_filter10")
    cycling = _one(result, CONCEPT_CYCLING_STATE)
    assert cycling.raw_literal == token
    assert cycling.normalized_value == token.casefold()
    state = _one(result, CONCEPT_BEFORE_AFTER_STATE)
    assert state.raw_literal == token
    assert state.normalized_value == side
    # Two statements, ONE locator: they are different facts about one token.
    assert cycling.locator == state.locator


def test_the_cycling_magnitude_is_deliberately_not_interpreted():
    """``after1500Cycling`` could be 1500 mV or 1500 cycles, and both forms exist.

    ``after1200mVCycling`` states millivolts explicitly, ``after1stCycling``
    states an ordinal. So the bare form is genuinely ambiguous, and the reader
    reports a case-folded literal with NO magnitude and NO unit.
    """
    item = _one(
        _read_stem("17_02_ZZ2_base_after1500Cycling_filter10_100mV"),
        CONCEPT_CYCLING_STATE,
    )
    assert item.unit is None
    assert item.normalized_value == "after1500cycling"
    assert "domain question" in item.normalization_rule


@pytest.mark.parametrize(
    "token,concept,value",
    [
        ("newSpots", CONCEPT_NEW_SPOT, "new_spot"),
        ("newGrid", CONCEPT_NEW_SPOT, "new_grid"),
        ("again", CONCEPT_REPEAT_MARKER, "repeat"),
        ("ave", CONCEPT_REPEAT_MARKER, "averaged"),
        ("dry", CONCEPT_DRY_STATE, "dry"),
        ("asIs", CONCEPT_BEFORE_AFTER_STATE, "as_is"),
        ("AsIs", CONCEPT_BEFORE_AFTER_STATE, "as_is"),
        ("acid", CONCEPT_ELECTROLYTE_OR_MEDIUM, "acid"),
        ("base", CONCEPT_ELECTROLYTE_OR_MEDIUM, "base"),
        ("NoElectrolyte", CONCEPT_ELECTROLYTE_OR_MEDIUM, "none"),
        ("noElectrolyte", CONCEPT_ELECTROLYTE_OR_MEDIUM, "none"),
        ("TRANSMISSION", CONCEPT_ACQUISITION_METHOD, "transmission"),
        ("transmission", CONCEPT_ACQUISITION_METHOD, "transmission"),
        ("HERFD", CONCEPT_ACQUISITION_METHOD, "herfd"),
        ("pellet", CONCEPT_SAMPLE_PREPARATION, "pellet"),
        ("oldPellet", CONCEPT_SAMPLE_PREPARATION, "old_pellet"),
    ],
)
def test_the_qualifier_vocabulary(token, concept, value):
    item = _one(_read_stem(f"03_01_ZZ1_{token}"), concept)
    assert item.raw_literal == token
    assert item.normalized_value == value


def test_folding_case_is_itself_recorded_as_a_normalisation():
    """``asIs`` matches its own alias literal; ``AsIs`` matched only after folding.

    Both are normalisations, and they cite DIFFERENT rules, so a reader can tell
    "the file wrote it exactly this way" from "the file wrote it another way and
    we folded case".
    """
    exact = _one(
        _read_stem("90_09_SyTiO2_asIs"), CONCEPT_BEFORE_AFTER_STATE
    )
    folded = _one(
        _read_stem("90_09_SyTiO2_AsIs"), CONCEPT_BEFORE_AFTER_STATE
    )
    assert exact.normalization_rule == filenames.RULE_ALIAS_EXACT
    assert folded.normalization_rule == filenames.RULE_ALIAS_FOLD
    assert exact.normalized_value == folded.normalized_value == "as_is"


@pytest.mark.parametrize("index", ["step05", "step07", "step12"])
def test_a_step_index_drops_its_zero_padding(index):
    item = _one(_read_stem(f"52_05_ZZ3_base_{index}"), CONCEPT_STEP_NUMBER)
    assert item.raw_literal == index
    assert item.normalized_value == int(index[4:])


@pytest.mark.parametrize("code", ["ZZ1", "ZZ2", "ZZ3", "SYNTH2"])
def test_a_sample_code_is_read_by_shape(code):
    item = _one(_read_stem(f"03_01_{code}_acid"), CONCEPT_SAMPLE_NAME)
    assert item.raw_literal == code
    assert item.normalized_value == code
    assert item.normalization_rule == filenames.RULE_SAMPLE_CODE_SHAPE


@pytest.mark.parametrize("name", ["SyOx", "SyTiO2"])
def test_a_formula_style_sample_name_needs_a_profile_alias(name):
    """A mixed-case formula reaches NO shape rule and must be an alias.

    This is the fact that makes the registry a registry: a new material is a
    profile addition, not a regex edit.

    **AND IT CANNOT BE EXERCISED WITH THE SHIPPED PROFILE, deliberately.** The
    shipped alias table declares the archive's REAL material names, and
    ``CLAUDE.md`` §6 keeps those out of a fixture. So the mechanism is exercised
    exactly as a second scientist would be added — a profile with its own table
    — and the shipped table is checked separately, against itself, in
    :func:`test_the_shipped_profile_alias_tables_each_resolve`.
    """
    # With the SHIPPED profile, a synthetic formula is unknown. That is the
    # negative half and it proves the shape rule genuinely cannot reach one.
    shipped = _read_stem(f"71_07_{name}_0p5nm")
    assert _by_concept(shipped, CONCEPT_SAMPLE_NAME) == []
    assert [
        e.raw_literal for e in _by_concept(shipped, CONCEPT_UNKNOWN_TOKEN)
    ] == [name]

    aliased = profiles.NamingProfile(
        profile_id="test_formula_alias",
        profile_version="1",
        display_name="A profile declaring the synthetic materials",
        description="Synthetic. Exists to exercise the alias table mechanism.",
        token_recognizers=(
            profiles.RECOGNIZER_SAMPLE_NAME,
            profiles.RECOGNIZER_BARE_INTEGER,
        ),
        sample_name_aliases=(("SyOx", "SyOx"), ("SyTiO2", "SyTiO2")),
    )
    profiles.PROFILES[aliased.profile_id] = aliased
    try:
        item = _one(
            filenames.read_filename(
                _synthetic_record(f"71_07_{name}_0p5nm"),
                stem=f"71_07_{name}_0p5nm",
                profile_id=aliased.profile_id,
            ),
            CONCEPT_SAMPLE_NAME,
        )
    finally:
        del profiles.PROFILES[aliased.profile_id]
    assert item.raw_literal == name
    assert item.normalization_rule == filenames.RULE_ALIAS_EXACT


def test_the_shipped_profile_alias_tables_each_resolve():
    """Every literal the shipped profile declares is reachable and named.

    This is where the shipped tables — which hold the archive's real material
    names and so may not appear in a fixture — are actually exercised. A table
    entry whose recognizer does not claim it would make the token read as
    unknown, which looks exactly like a working reader.
    """
    profile = profiles.SSRL_BL152_ANGEL_V1
    tables = (
        "medium",
        "state",
        "acquisition_method",
        "preparation",
        "gas",
        "sample_name",
    )
    checked = 0
    for table in tables:
        literals = profile.alias_literals(table)
        assert literals, f"alias table {table!r} is empty"
        for literal in literals:
            assert profile.alias(table, literal) is not None
            # Case-insensitively too, which is the property the corpus needs.
            assert profile.alias(table, literal.upper()) is not None
            assert profile.alias(table, literal.lower()) is not None
            result = _read_stem(f"03_01_{literal}")
            claimed = [
                e
                for e in result.evidence
                if e.raw_literal == literal
                and e.concept != CONCEPT_UNKNOWN_TOKEN
            ]
            assert claimed, (
                f"{table} alias {literal!r} is declared but no recognizer "
                f"claims it"
            )
            checked += 1
    declared = sum(len(profile.alias_literals(t)) for t in tables)
    assert checked == declared == 24, (
        f"exercised {checked} of {declared} declared alias literals; the "
        f"shipped tables held 24 when this was written, and a table that "
        f"shrank would otherwise pass silently"
    )


def test_the_bare_integer_ordinal_rule_and_its_boundaries():
    """First bare integer is the legacy number, second the sample/electrode.

    An ordinal among the NUMERIC tokens, not a token position — which is why a
    stem with one numeric token gets a legacy number and nothing else, and a stem
    with three gets no role for the third.
    """
    two = _read_stem("52_05_ZZ3_base_filter20_850mV")
    assert _one(two, CONCEPT_LEGACY_NUMBER).normalized_value == 52
    assert _one(two, CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER).normalized_value == 5

    one = _read_stem("01_SyOx_oldPellet_f35")
    assert _one(one, CONCEPT_LEGACY_NUMBER).normalized_value == 1
    assert _by_concept(one, CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER) == []

    three = _read_stem("43_44_04_ZZ2_base_after1500CV_f20_f35_1200mV")
    assert _one(three, CONCEPT_LEGACY_NUMBER).normalized_value == 43
    assert _one(three, CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER).normalized_value == 44
    unknown = _by_concept(three, CONCEPT_UNKNOWN_TOKEN)
    assert [u.raw_literal for u in unknown] == ["04"]


def test_the_second_numeric_tokens_meaning_is_recorded_as_domain_confirmed():
    """``DEC-47``: the token IS a sample/electrode instance number.

    **This test was INVERTED, not deleted, and the inversion is the point.** It used to
    require the rule string to say ``NOT ESTABLISHED`` and *"agreement is not
    confirmation"* — a correct caveat that became a false one when the domain owner
    confirmed the meaning on 2026-09-17. A test pinning a retired caveat is a test that
    fails the correction, which is why the repository's established remedy is to invert
    it.

    Two things it keeps asserting, because neither changed: the rule still carries its
    VERSIONED ID (the reading is byte-identical, so the id stays ``.v1``), and the
    convention is still a vocabulary rather than a grammar.
    """
    item = _one(
        _read_stem("52_05_ZZ3_base_filter20_850mV"),
        CONCEPT_SAMPLE_OR_ELECTRODE_NUMBER,
    )
    rule = item.normalization_rule
    assert "bl15.filenames.bare_integer_ordinal.v1" in rule
    assert "CONFIRMED" in rule
    assert "DEC-47" in rule
    assert "NOT A GRAMMAR" in rule
    # and the caveat that was retired is gone rather than softened
    assert "NOT ESTABLISHED" not in rule
    assert "agreement is not confirmation" not in rule


def test_a_duplicate_legacy_number_is_read_twice_and_never_deduplicated():
    """A legacy number is not a key, and the archive proves it.

    Two distinct measurements carry number 32. A reader that treated the number
    as an identity would lose one of them.
    """
    stems = _stems("duplicate-legacy-number-set.txt")
    numbers = []
    for stem in stems:
        for item in _by_concept(_read_stem(stem), CONCEPT_LEGACY_NUMBER):
            numbers.append((item.normalized_value, item.measurement_stem))
    thirty_twos = [stem for value, stem in numbers if value == 32]
    assert len(thirty_twos) == 2
    assert len(set(thirty_twos)) == 2, "the two stems collapsed into one"


def test_a_doubled_separator_is_reported_rather_than_dropped():
    """It changes the token indices a scientist would count by eye."""
    result = _read_stem("08_01_ZZ1__acid_beforeCycling_filter10_100mV")
    assert any(entry["reason"] == "empty_token" for entry in result.skipped)
    # And the tokens AFTER it still read correctly.
    assert _one(result, CONCEPT_ELECTROLYTE_OR_MEDIUM).normalized_value == "acid"


def test_the_convention_fields_with_no_real_filename_example_still_read():
    """Gas / pH / flow rate: no archive filename carries one.

    The concepts are corpus-attested — the beamtime notes state all three in
    prose — so the recognizers exist and are exercised HERE and nowhere else,
    which :data:`profiles.UNEXERCISED_RECOGNIZERS` declares.
    """
    result = _read_stem("80_08_SyTiO2_0p5nm_base_ArSat_pH13_10mLmin_filter10_100mV")
    assert _one(result, CONCEPT_GAS_CONDITION).normalized_value == "ar_saturated"
    assert _one(result, CONCEPT_PH).normalized_value == 13
    flow = _one(result, CONCEPT_FLOW_RATE)
    assert flow.normalized_value == 10
    assert flow.unit == "mL/min"

    second = _read_stem("81_08_SyTiO2_0p5nm_base_N2_pH7_5sccm_filter10_200mV")
    assert _one(second, CONCEPT_GAS_CONDITION).normalized_value == "n2"
    assert _one(second, CONCEPT_FLOW_RATE).unit == "sccm"


def test_every_emitted_rule_is_a_declared_constant():
    """A rule invented at a call site is indistinguishable from a guess.

    Asserted over every reader, not just the filename one.
    """
    declared = (
        filenames.NORMALIZATION_RULES
        | spec.NORMALIZATION_RULES
        | scans.NORMALIZATION_RULES
        | macros.NORMALIZATION_RULES
        | notes.NORMALIZATION_RULES
    )
    seen = set()
    for _label, _source, result in _all_fixture_readings():
        for item in result.evidence:
            if item.normalization_rule:
                seen.add(item.normalization_rule)
    assert seen, "no normalisation rule was exercised at all"
    # Composite rules join two declared rules with ` | `; split before checking.
    for rule in seen:
        for part in rule.split(" | "):
            assert part in declared, f"undeclared normalization rule: {part!r}"


def test_a_normalised_statement_cannot_exist_without_a_named_rule():
    """The contract's own guard, exercised rather than assumed."""
    with pytest.raises(ValueError, match="requires normalization_rule"):
        SourceEvidence(
            evidence_id="x",
            source_path="p",
            source_type=SOURCE_TYPE_UNKNOWN,
            locator="l",
            raw_literal="060mV",
            concept=CONCEPT_POTENTIAL_MAGNITUDE,
            parser_id="t",
            determinism=DETERMINISM_NORMALIZED,
            normalized_value=0.06,
        )


def test_an_empty_stem_is_reported_and_does_not_raise():
    result = filenames.read_filename(_synthetic_record("x"), stem="")
    assert result.refused_reason is None
    assert result.evidence == ()
    assert [e["reason"] for e in result.skipped] == ["empty_stem"]


def test_an_oversized_stem_is_refused_whole():
    stem = "a" * (filenames.MAX_STEM_CHARS + 1)
    result = filenames.read_filename(_synthetic_record("x"), stem=stem)
    assert result.refused_reason is not None
    assert "source_too_large" in result.refused_reason
    assert str(filenames.MAX_STEM_CHARS) in result.refused_reason
    assert result.evidence == ()


def test_too_many_tokens_is_bounded_and_disclosed():
    stem = "_".join(str(i) for i in range(filenames.MAX_TOKENS + 10))
    result = filenames.read_filename(_synthetic_record("x"), stem=stem)
    assert result.refused_reason is None
    reasons = [e["reason"] for e in result.skipped]
    assert "too_many_tokens" in reasons


# ===========================================================================
# 5. CLASSIFICATION
# ===========================================================================


def test_content_beats_the_name_for_the_two_measured_counterexamples():
    """``run29`` has no extension and is a macro; ``alignment`` is an acquisition.

    The whole reason classification is content-led.
    """
    macro = classify.classify(
        _synthetic_record("run29", extension=""),
        head_text="qdo Ir_XAS.mac\n\nmv Sx -1 Sy 2\n\nnewfile 39_04_ZZ2_base\n",
    )
    assert macro.source_type == SOURCE_TYPE_MACRO
    assert macro.confidence == classify.CONFIDENCE_CONTENT

    alignment = classify.classify(
        _record(FIXTURES / "spec" / "alignment"),
        head_text=_text(FIXTURES / "spec" / "alignment"),
    )
    assert alignment.source_type == SOURCE_TYPE_ALIGNMENT
    assert alignment.confidence == classify.CONFIDENCE_CONTENT


def test_mca_is_decided_by_extension_BEFORE_the_F_test():
    """**The order matters and the obvious order is wrong for this one case.**

    Both ``.mca`` detector products in the measured archive BEGIN WITH ``#F``.
    A classifier that reaches the ``#F`` branch first calls them SPEC
    acquisitions, which was measured to produce two spurious measurement units
    and two false name conflicts downstream.
    """
    result = classify.classify(
        _synthetic_record("ave_ZZ2_filter10.mca"),
        head_text=(
            "#F /data/synthetic/fixture/MERGE/ave_ZZ2_filter10.mca\n"
            "#E 1000000000\n"
        ),
    )
    assert result.source_type == SOURCE_TYPE_DETECTOR_PRODUCT
    assert "#F" in result.reason or "`#F`" in result.reason


@pytest.mark.parametrize(
    "path,expected",
    [
        ("spec/03_01_ZZ1_acid_beforeCycling_100mV_filter10", SOURCE_TYPE_SPEC_ACQUISITION),
        ("spec/rename-group/29_03_ZZ2_base_after1500Cycling_filter20_100mV", SOURCE_TYPE_SPEC_ACQUISITION),
        ("spec/alignment", SOURCE_TYPE_ALIGNMENT),
        ("spec/SyOx_5wpc_pellet_transmission", SOURCE_TYPE_STANDARD_OR_REFERENCE),
        ("scans/03_01_ZZ1_acid_beforeCycling_100mV_filter10_001.dat", SOURCE_TYPE_SCAN_EXPORT),
        ("macros/run15.mac", SOURCE_TYPE_MACRO),
        ("macros/Ir_XAS.mac", SOURCE_TYPE_ACQUISITION_METHOD_MACRO),
        ("macros/motors_cpy_pre99.mac", SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO),
        ("notes/readme.txt", SOURCE_TYPE_SHARED_README),
        ("notes/beamtime-notes.txt", SOURCE_TYPE_BEAMTIME_NOTES),
        ("processed/63_06_ZZ1_f10.txt", SOURCE_TYPE_PROCESSED_SPECTRUM),
    ],
)
def test_every_fixture_family_classifies_as_itself(path, expected):
    target = FIXTURES / path
    # The archive path is the BASENAME, so every fixture is at depth 0 — which
    # is what the real archive's readme, notes, acquisitions and macros are.
    # The fixture directory layout is this repository's, not the archive's.
    record = _record(target)
    result = classify.classify(record, head_text=_text(target)[:8192])
    assert result.source_type == expected, result.reason
    assert result.confidence == classify.CONFIDENCE_CONTENT
    assert result.overridable is True


def test_a_classification_reason_names_the_evidence_it_used():
    """It reaches a review surface verbatim. ``matched rule 7`` would be useless."""
    result = classify.classify(
        _record(SPEC_FIXTURE), head_text=_text(SPEC_FIXTURE)
    )
    assert "#F" in result.reason
    assert len(result.reason) > 40


def test_without_content_the_confidence_is_capped_at_path():
    for basename, expected in (
        ("x_001.dat", SOURCE_TYPE_SCAN_EXPORT),
        ("run44.mac", SOURCE_TYPE_MACRO),
        ("ave.mca", SOURCE_TYPE_DETECTOR_PRODUCT),
        ("readme.txt", SOURCE_TYPE_SHARED_README),
    ):
        result = classify.classify(
            _synthetic_record(basename), head_text=None
        )
        assert result.source_type == expected
        assert result.confidence == classify.CONFIDENCE_PATH
        assert "run29" in result.reason and "alignment" in result.reason


def test_an_unrecognisable_entry_with_no_content_is_unknown_not_guessed():
    result = classify.classify(
        _synthetic_record("notes.docx"), head_text=None
    )
    assert result.source_type == SOURCE_TYPE_UNKNOWN
    assert result.confidence == classify.CONFIDENCE_UNKNOWN


def test_every_classification_is_overridable():
    """A scientist must always be able to correct a classification.

    ``overridable`` is a constant ``True`` and is checked over every branch this
    suite reaches, because a single non-overridable branch is the one a scientist
    would meet.
    """
    seen = set()
    for path, _expected in (
        ("spec/alignment", None),
        ("macros/run15.mac", None),
        ("notes/readme.txt", None),
        ("processed/63_06_ZZ1_f10.txt", None),
    ):
        target = FIXTURES / path
        result = classify.classify(
            _record(target, archive_path=path), head_text=_text(target)
        )
        assert result.overridable is True
        seen.add(result.source_type)
    assert classify.classify(
        _synthetic_record("x"), head_text=None
    ).overridable is True
    assert classify.classify(
        _synthetic_record("x"), head_text="\n \n"
    ).overridable is True
    assert len(seen) == 4


def test_the_classifier_docstring_states_the_run_candidacy_rule():
    """``macro`` and ``scan_export`` are NEVER run candidates, and it must say so.

    One macro declares up to eight measurements; 908 ``.dat`` files are the
    children of ~92. Promoting either would invent measurements nobody performed.
    """
    doc = classify.__doc__ or ""
    assert "RUN_CANDIDATE_SOURCE_TYPES" in doc
    assert "never" in doc
    assert "816" in doc


# ===========================================================================
# 6. THE SPEC ACQUISITION READER
# ===========================================================================


def _spec_result() -> ReaderResult:
    return spec.read_spec_acquisition(_record(SPEC_FIXTURE), _text(SPEC_FIXTURE))


def test_the_spec_reader_reads_the_file_level_header():
    result = _spec_result()
    declaration = _one(result, CONCEPT_SPEC_FILE_DECLARATION)
    # The literal is the ABSOLUTE PATH the file states, whole.
    assert declaration.raw_literal == (
        "/data/synthetic/2001-09_fixture/"
        "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
    )
    assert (
        declaration.normalized_value
        == "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
    )
    assert declaration.normalization_rule == spec.RULE_F_CARRIES_A_PATH
    assert (
        declaration.measurement_stem
        == "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
    )

    user = _one(result, CONCEPT_SPEC_USER_STRING)
    assert user.raw_literal == "spec  User = synthetic"


def test_a_bare_stem_F_is_read_not_normalised():
    """186 of 188 real ``#F`` lines are bare stems. Those need no rule."""
    target = FIXTURES / "spec" / "alignment"
    item = _one(
        spec.read_spec_acquisition(_record(target), _text(target)),
        CONCEPT_SPEC_FILE_DECLARATION,
    )
    assert item.raw_literal == "alignment"
    assert item.determinism == DETERMINISM_READ
    assert item.normalization_rule is None
    assert item.measurement_stem == "alignment"


def test_the_epoch_becomes_iso_utc_and_D_is_not_reconciled_against_it():
    """Two statements, never merged.

    ``#E`` is an unambiguous instant. ``#D`` is a local-time string with no zone,
    so it gets NO ``timestamp_utc`` — assigning one would require inventing a
    timezone.
    """
    result = _spec_result()
    from isaac_api.bl15.evidence import (
        CONCEPT_ACQUISITION_EPOCH,
        CONCEPT_ACQUISITION_TIMESTAMP,
    )

    epoch = _one(result, CONCEPT_ACQUISITION_EPOCH)
    assert epoch.raw_literal == "1000000000"
    assert epoch.timestamp_utc == "2001-09-09T01:46:40+00:00"
    assert epoch.normalization_rule == spec.RULE_EPOCH_TO_UTC

    stamps = _by_concept(result, CONCEPT_ACQUISITION_TIMESTAMP)
    assert len(stamps) == 4  # one file-level, one per scan
    assert all(s.timestamp_utc is None for s in stamps)
    assert all(s.determinism == DETERMINISM_READ for s in stamps)


def test_the_O_P_pairing_agrees_with_the_dat_export_of_the_same_scan():
    """**THE INDEPENDENT CHECK.** No index is hard-coded anywhere.

    The acquisition's positions are paired by ``#O``/``#P`` index and column; the
    ``.dat`` export of the same scan names each motor explicitly. They must
    agree on every motor, and the two readers share no pairing code.
    """
    acquisition = _spec_result()
    export = scans.read_scan_export(_record(DAT_FIXTURE), _text(DAT_FIXTURE))

    paired = {}
    for item in acquisition.evidence:
        if "(scan 1)" in item.locator and "motor `" in item.locator:
            paired[item.locator.split("motor `")[1].split("`")[0]] = (
                item.raw_literal,
                item.concept,
            )
    keyed = {}
    for item in export.evidence:
        if "key `" in item.locator:
            keyed[item.locator.split("key `")[1].split("`")[0]] = (
                item.raw_literal,
                item.concept,
            )

    assert len(paired) == 14, sorted(paired)
    assert set(paired) == set(keyed)
    assert paired == keyed, "the paired reading disagrees with the keyed one"

    # And the specific motors the brief names must land where a human reads them.
    assert paired["energy"] == ("1000.5", CONCEPT_MOTOR_POSITION)
    assert paired["emiss"] == ("1050", CONCEPT_EMISSION_ENERGY)
    assert paired["filter"] == ("10", CONCEPT_FILTER)
    for axis in ("Sx", "Sy", "Sz", "Sr"):
        assert paired[axis][1] == CONCEPT_SAMPLE_POSITION
    assert paired["gap"][1] == CONCEPT_MOTOR_POSITION


def test_a_mispaired_P_line_is_refused_whole_and_names_both_counts():
    """A mispaired mapping is worse than none.

    One missing field shifts every later position onto the wrong motor's name, so
    the whole line contributes nothing and the skip states both counts.
    """
    result = _spec_result()
    mispaired = [
        e
        for e in result.skipped
        if e["reason"] == spec.SKIP_MISPAIRED_POSITIONS
    ]
    assert len(mispaired) == 1
    entry = mispaired[0]
    assert entry["name_count"] == 3
    assert entry["position_count"] == 2
    assert "#P1" in entry["locator"]
    assert "3" in entry["detail"] and "2" in entry["detail"]

    # Scan 3's `#O1`/`#P1` pair produced NO evidence at all.
    scan3_gap = [
        e
        for e in result.evidence
        if "(scan 3)" in e.locator and "motor `gap`" in e.locator
    ]
    assert scan3_gap == []
    # while its correctly-paired `#P0` and `#P2` lines still read.
    scan3 = [e for e in result.evidence if "(scan 3)" in e.locator]
    assert any("motor `Sz`" in e.locator for e in scan3)
    assert any("motor `mono`" in e.locator for e in scan3)


def test_positions_with_no_names_are_reported_rather_than_guessed():
    body = "#F x\n#P0 1 2 3\n#N 1\n#L energy\n1 2\n"
    result = spec.read_spec_acquisition(_synthetic_record("x", body=body), body)
    assert _by_concept(result, CONCEPT_MOTOR_POSITION) == []
    reasons = [e["reason"] for e in result.skipped]
    assert spec.SKIP_UNPAIRED_POSITIONS in reasons


def test_the_scan_command_and_the_gscan_grid_literal():
    result = _spec_result()
    commands = _by_concept(result, CONCEPT_SCAN_COMMAND)
    assert len(commands) == 3
    assert commands[0].raw_literal.startswith("gscan energy 1000")
    assert commands[2].raw_literal.startswith("ascan Sz")

    grids = _by_concept(result, CONCEPT_ENERGY_GRID)
    # TWO grids, not three: `ascan` carries none and gets none.
    assert len(grids) == 2
    assert grids[0].raw_literal == "1000 1020 5 1040 1 1100 2"
    assert all("gscan" in g.locator for g in grids)


def test_the_counting_time_reads_its_own_declared_unit():
    from isaac_api.bl15.evidence import CONCEPT_COUNTING_TIME

    items = _by_concept(_spec_result(), CONCEPT_COUNTING_TIME)
    assert len(items) == 3
    assert items[0].raw_literal == "0.5  (sec)"
    assert items[0].normalized_value == 0.5
    assert items[0].unit == "s"


def test_a_counting_time_in_an_undeclared_unit_gets_no_normalised_value():
    body = "#F x\n#S 1  gscan energy 1 2 3 0.5\n#T 500  (msec)\n#N 1\n#L energy\n"
    from isaac_api.bl15.evidence import CONCEPT_COUNTING_TIME

    result = spec.read_spec_acquisition(_synthetic_record("x", body=body), body)
    item = _one(result, CONCEPT_COUNTING_TIME)
    assert item.raw_literal == "500  (msec)"
    assert item.normalized_value is None
    assert item.unit is None
    assert item.determinism == DETERMINISM_READ


def test_N_is_reported_as_the_column_count_and_never_as_a_point_count():
    """**A MEASURED DISAGREEMENT WITH THE SLICE BRIEF, recorded in the rule.**

    The brief said ``#N`` -> ``point_count``. Measured over the archive, ``#N``
    equals the ``#L`` column count in 920 of 920 scan blocks while the scans
    carry 444 to 7,320 data rows. ``bl15.evidence`` has no column-count concept,
    so publishing ``#N`` as ``point_count`` would be a false statement; it is
    reported under ``skipped`` with the measurement instead.
    """
    result = _spec_result()
    from isaac_api.bl15.evidence import CONCEPT_POINT_COUNT

    assert _by_concept(result, CONCEPT_POINT_COUNT) == []
    entries = [
        e for e in result.skipped if e["reason"] == spec.SKIP_N_IS_COLUMN_COUNT
    ]
    assert len(entries) == 1
    assert entries[0]["occurrence_count"] == 3
    assert "920 of 920" in entries[0]["detail"]
    # Each `#L` column name IS read.
    columns = _by_concept(result, CONCEPT_DETECTOR_COLUMN)
    assert [c.raw_literal for c in columns[:4]] == [
        "energy",
        "sec",
        "I1",
        "vortDT",
    ]
    assert len(columns) == 12  # 4 columns x 3 scans


def test_the_data_rows_are_counted_and_not_read():
    result = _spec_result()
    rows = [e for e in result.skipped if e["reason"] == spec.SKIP_DATA_ROWS]
    assert [e["row_count"] for e in rows] == [3, 2, 1]
    assert all(e["complete"] for e in rows)
    # No evidence item's locator points into a data block.
    assert not any("data block" in e.locator for e in result.evidence)


def test_scan_level_and_file_level_statements_carry_different_scopes():
    result = _spec_result()
    scopes = {e.concept: set() for e in result.evidence}
    for e in result.evidence:
        scopes[e.concept].add(e.scope)
    assert scopes[CONCEPT_SPEC_FILE_DECLARATION] == {SCOPE_MEASUREMENT}
    assert scopes[CONCEPT_SPEC_USER_STRING] == {SCOPE_MEASUREMENT}
    assert scopes[CONCEPT_SCAN_COMMAND] == {SCOPE_SCAN}
    assert scopes[CONCEPT_DETECTOR_COLUMN] == {SCOPE_SCAN}
    # And every statement carries the stem the FILE declared.
    assert {e.measurement_stem for e in result.evidence} == {
        "03_01_ZZ1_acid_beforeCycling_100mV_filter10"
    }


def test_the_rename_group_is_read_as_a_group_and_nothing_is_detected():
    """**THREE files, ONE substitution. A rename, not a typo.**

    Each file's internal ``#F`` says ``beforeCycling`` while its name says
    ``after1500Cycling``. The reader reports what the file says and detects
    nothing — but the fixture is a GROUP on purpose: a single self-disagreeing
    file invites a "probably a typo" heuristic that the real corpus refutes.
    """
    members = sorted(p for p in RENAME_GROUP.iterdir() if p.suffix != ".md")
    assert len(members) == 3, [p.name for p in members]
    for path in members:
        result = spec.read_spec_acquisition(_record(path), _text(path))
        declared = _one(result, CONCEPT_SPEC_FILE_DECLARATION).raw_literal
        assert "beforeCycling" in declared
        assert "after1500Cycling" in path.name
        assert declared != path.name
        # NOTHING is detected, reconciled or flagged here.
        assert result.refused_reason is None
        assert not any(
            "conflict" in entry["reason"] for entry in result.skipped
        )


def test_the_spec_reader_refuses_a_scan_export_and_does_not_raise():
    result = spec.read_spec_acquisition(
        _record(DAT_FIXTURE), _text(DAT_FIXTURE)
    )
    assert result.refused_reason is not None
    assert "not_a_spec_acquisition" in result.refused_reason
    assert result.evidence == ()


def test_the_spec_reader_refuses_a_macro_and_does_not_raise():
    target = FIXTURES / "macros" / "run15.mac"
    result = spec.read_spec_acquisition(_record(target), _text(target))
    assert result.refused_reason is not None
    assert "not_a_spec_acquisition" in result.refused_reason


def test_the_spec_reader_survives_garbage_and_an_empty_source():
    for body in ("", "\n\n\n", "not a spec file at all", "\x7f\x7f\x7f"):
        result = spec.read_spec_acquisition(
            _synthetic_record("x", body=body), body
        )
        assert result.refused_reason is not None
        assert result.evidence == ()


def test_a_bom_prefixed_spec_file_still_reads():
    body = "﻿#F x\n#E 1000000000\n#O0 energy\n#S 1  gscan energy 1 2 0.5\n#P0 5\n"
    result = spec.read_spec_acquisition(_synthetic_record("x", body=body), body)
    assert result.refused_reason is None
    assert _one(result, CONCEPT_SPEC_FILE_DECLARATION).raw_literal == "x"


def test_an_oversized_source_is_refused_with_both_numbers():
    record = SourceRecord(
        archive_path="huge",
        basename="huge",
        extension="",
        size_bytes=MAX_SOURCE_BYTES + 1,
        content_sha256="0" * 64,
        parent_dir="",
        depth=0,
    )
    result = spec.read_spec_acquisition(record, "#F huge\n")
    assert result.refused_reason is not None
    assert str(MAX_SOURCE_BYTES + 1) in result.refused_reason
    assert str(MAX_SOURCE_BYTES) in result.refused_reason
    assert result.evidence == ()


def test_the_evidence_ceiling_truncates_and_says_so():
    """**The ceiling IS reached by a real file, so this is not hypothetical.**

    Measured at ``MAX_EVIDENCE_PER_SOURCE = 4_000``: THREE of the archive's 94
    acquisitions returned a partial reading. The ceiling was then **raised to 8,000**,
    derived from the second-largest demand in the corpus (4,816), so that **no numbered
    acquisition is partial** — and exactly one file still is: ``alignment``, which
    carries 233 scans and suppresses 40,954 statements. It stays partial by design, and
    ``bl15/evidence.py`` records the argument.

    **THE INPUT IS SIZED FROM THE CONSTANT, NOT FROM A LITERAL, AND THAT IS THE POINT.**
    An earlier version hard-coded 60 scans x 100 motors = 6,121 items, which exceeded
    4,000 and then **stopped exceeding the ceiling the moment it was raised** — so the
    test would have passed while asserting nothing about truncation. A ceiling test
    whose fixture can fall under the ceiling retires itself silently.
    """
    motors = 100
    # Enough scans to overshoot whatever the ceiling is, with margin for the header
    # statements, so this holds for any future value of the constant.
    scan_count = (MAX_EVIDENCE_PER_SOURCE // motors) + 10
    header = "#F big\n#O0 " + " ".join(f"m{i}" for i in range(motors)) + "\n"
    scans_text = []
    for index in range(scan_count):
        scans_text.append(
            f"#S {index + 1}  gscan energy 1 2 0.5\n"
            "#P0 " + " ".join(str(i) for i in range(motors)) + "\n"
        )
    body = header + "".join(scans_text)
    result = spec.read_spec_acquisition(_synthetic_record("big", body=body), body)
    assert result.refused_reason is None
    assert len(result.evidence) == MAX_EVIDENCE_PER_SOURCE
    ceiling = [
        e for e in result.skipped if e["reason"] == SKIP_EVIDENCE_CEILING
    ]
    assert len(ceiling) == 1
    assert ceiling[0]["suppressed_count"] > 0
    assert ceiling[0]["ceiling"] == MAX_EVIDENCE_PER_SOURCE
    assert "PARTIAL" in ceiling[0]["detail"]


# ===========================================================================
# 7. THE `.dat` SCAN READER
# ===========================================================================


def _dat_result() -> ReaderResult:
    return scans.read_scan_export(_record(DAT_FIXTURE), _text(DAT_FIXTURE))


def test_the_stem_and_scan_index_come_from_the_basename():
    result = _dat_result()
    target = _one(result, CONCEPT_ACQUISITION_TARGET)
    assert target.raw_literal == DAT_FIXTURE.name
    assert target.normalized_value == {
        "measurement_stem": "03_01_ZZ1_acid_beforeCycling_100mV_filter10",
        "scan_index": 1,
    }
    assert target.normalization_rule == scans.RULE_BASENAME_STEM_AND_INDEX
    assert target.scope == SCOPE_SCAN


@pytest.mark.parametrize(
    "basename,expected",
    [
        ("03_01_ZZ1_acid_001.dat", ("03_01_ZZ1_acid", 1)),
        ("x_233.dat", ("x", 233)),
        ("a_b_c_007.dat", ("a_b_c", 7)),
        ("no-index.dat", (None, None)),
        ("trailing_.dat", (None, None)),
        ("wrong.txt", (None, None)),
    ],
)
def test_stem_and_index_never_guesses(basename, expected):
    assert scans.stem_and_index(basename) == expected


def test_a_basename_with_no_scan_index_is_reported_and_the_headers_still_read():
    body = _text(DAT_FIXTURE)
    result = scans.read_scan_export(
        _synthetic_record("no-index.dat", body=body), body
    )
    assert result.refused_reason is None
    assert _by_concept(result, CONCEPT_ACQUISITION_TARGET) == []
    assert scans.SKIP_NO_SCAN_INDEX in [e["reason"] for e in result.skipped]
    # The scan's own headers are unaffected.
    assert _by_concept(result, CONCEPT_SCAN_COMMAND)
    assert all(e.measurement_stem is None for e in result.evidence)


def test_the_dat_reader_reads_keyed_positions_and_needs_no_O_block():
    result = _dat_result()
    positions = {
        e.locator.split("key `")[1].split("`")[0]: e
        for e in result.evidence
        if "key `" in e.locator
    }
    assert len(positions) == 14
    assert positions["emiss"].concept == CONCEPT_EMISSION_ENERGY
    assert positions["emiss"].normalized_value == 1050
    assert positions["filter"].concept == CONCEPT_FILTER
    assert positions["Sx"].concept == CONCEPT_SAMPLE_POSITION
    assert positions["gap"].concept == CONCEPT_MOTOR_POSITION
    assert all(
        e.normalization_rule == scans.RULE_KEYED_POSITION
        for e in positions.values()
    )


def test_an_unkeyed_position_field_is_reported_not_split_by_position():
    body = (
        "#S 1  gscan energy 1 2 0.5\n"
        "#P0 dummy0=4 energy=1000.5 orphan 10\n"
        "#N 1\n#L energy\n"
    )
    result = scans.read_scan_export(
        _synthetic_record("x_001.dat", body=body), body
    )
    reasons = [e["reason"] for e in result.skipped]
    assert reasons.count(scans.SKIP_UNKEYED_POSITION) == 2
    keyed = [e for e in result.evidence if "key `" in e.locator]
    assert len(keyed) == 2


def test_the_dat_reader_shares_the_motor_concept_table_with_the_spec_reader():
    """Imported, not copied. That sharing is what makes the cross-check valid."""
    assert scans.MOTOR_CONCEPTS is spec.MOTOR_CONCEPTS
    assert spec.MOTOR_CONCEPTS["emiss"] == CONCEPT_EMISSION_ENERGY
    assert spec.MOTOR_CONCEPTS["filter"] == CONCEPT_FILTER
    assert spec.MOTOR_CONCEPTS["Sx"] == CONCEPT_SAMPLE_POSITION


def test_the_dat_reader_refuses_a_root_acquisition_and_says_which_reader_to_use():
    result = scans.read_scan_export(
        _record(SPEC_FIXTURE), _text(SPEC_FIXTURE)
    )
    assert result.refused_reason is not None
    assert "not_a_scan_export" in result.refused_reason
    assert "bl15.spec" in result.refused_reason
    assert result.evidence == ()


def test_the_dat_reader_refuses_a_file_with_no_scan_header():
    body = "just some text\n1 2\n"
    result = scans.read_scan_export(
        _synthetic_record("x_001.dat", body=body), body
    )
    assert result.refused_reason is not None
    assert "not_a_scan_export" in result.refused_reason


def test_the_dat_reader_counts_rows_and_reads_none_of_them():
    result = _dat_result()
    rows = [e for e in result.skipped if e["reason"] == scans.SKIP_DATA_ROWS]
    assert len(rows) == 1
    assert rows[0]["row_count"] == 3
    assert not any("data block" in e.locator for e in result.evidence)


def test_every_dat_statement_is_scan_scoped():
    assert {e.scope for e in _dat_result().evidence} == {SCOPE_SCAN}


# ===========================================================================
# 8. THE MACRO READER
# ===========================================================================


def test_a_macro_is_never_executed_and_this_module_contains_no_evaluator():
    """Asserted over the module's PARSED SYNTAX, not over a text grep.

    A macro is a program written for a beamline control system and it arrives
    from outside this repository. "We do not execute it" is a claim worth
    mechanising rather than promising.

    **The first version of this test was a text grep and it failed on the
    module's own docstring** — the sentence *"there is no ``eval``, no ``exec``,
    no subprocess"* contains every word the grep was looking for. A grep over
    source cannot tell a call from prose ABOUT a call, so this walks the AST
    instead: it looks at import statements and call targets only.
    """
    import ast

    tree = ast.parse(Path(macros.__file__).read_text(encoding="utf-8"))

    allowed_modules = {"__future__", "re", "typing"}
    forbidden_names = {"eval", "exec", "compile", "__import__"}
    forbidden_attrs = {
        "system",
        "popen",
        "spawn",
        "spawnv",
        "Popen",
        "run",
        "check_output",
        "check_call",
        "import_module",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed_modules, (
                    f"bl15.macros imports {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert (node.module or "").split(".")[0] in allowed_modules, (
                    f"bl15.macros imports from {node.module!r}"
                )
        elif isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                assert target.id not in forbidden_names, (
                    f"bl15.macros CALLS {target.id!r}"
                )
            elif isinstance(target, ast.Attribute):
                assert target.attr not in forbidden_attrs, (
                    f"bl15.macros calls .{target.attr}()"
                )

    # Negative control: the walk must actually reject a module that evaluates.
    bad = ast.parse("import subprocess\nsubprocess.run(['x'])\neval('1')\n")
    offences = 0
    for node in ast.walk(bad):
        if isinstance(node, ast.Import):
            offences += sum(
                1
                for alias in node.names
                if alias.name.split(".")[0] not in allowed_modules
            )
        elif isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name) and target.id in forbidden_names:
                offences += 1
            if (
                isinstance(target, ast.Attribute)
                and target.attr in forbidden_attrs
            ):
                offences += 1
    assert offences == 3, (
        "the AST walk would not have caught an evaluating module"
    )


def test_a_macro_declaring_three_targets_groups_its_commands_into_blocks():
    target = FIXTURES / "macros" / "run15.mac"
    result = macros.read_macro(_record(target), _text(target))
    assert result.refused_reason is None

    declarations = _by_concept(result, CONCEPT_ACQUISITION_TARGET)
    assert [d.normalized_value for d in declarations] == [
        "15_02_ZZ2_base_after1200Cycling_filter10_200mV",
        "16_02_ZZ2_base_after1200Cycling_filter10_400mV",
        "17_02_ZZ2_base_after1500Cycling_filter10_100mV",
    ]
    assert [d.locator for d in declarations] == [
        f"line {d.locator.split()[1]} newfile block {i}"
        for i, d in enumerate(declarations)
    ]

    # Every command inside block 1 carries block 1's stem.
    block1 = [e for e in result.evidence if "newfile block 1" in e.locator]
    assert block1
    assert {e.measurement_stem for e in block1} == {
        "16_02_ZZ2_base_after1200Cycling_filter10_400mV"
    }
    assert {e.scope for e in block1} == {SCOPE_MEASUREMENT}


def test_commands_before_the_first_newfile_belong_to_no_block():
    """``run15.mac`` opens with ``qdo`` and an absolute ``mv`` before declaring.

    Attributing them to the first block would assert a scope the file does not
    state.
    """
    target = FIXTURES / "macros" / "run15.mac"
    result = macros.read_macro(_record(target), _text(target))
    preamble = [
        e
        for e in result.evidence
        if "before any newfile declaration" in e.locator
    ]
    assert preamble
    assert {e.scope for e in preamble} == {SCOPE_BEAMTIME}
    assert {e.measurement_stem for e in preamble} == {None}
    assert any(e.concept == CONCEPT_ACQUISITION_METHOD for e in preamble)
    assert any(e.concept == CONCEPT_SAMPLE_POSITION for e in preamble)


def test_the_documented_four_argument_signature_is_read_as_four_statements():
    target = FIXTURES / "macros" / "run15.mac"
    result = macros.read_macro(_record(target), _text(target))
    from isaac_api.bl15.evidence import CONCEPT_COUNTING_TIME

    calls = [e for e in result.evidence if "`IrL3_xas`" in e.locator]
    by_concept = {}
    for item in calls:
        by_concept.setdefault(item.concept, []).append(item)
    assert set(by_concept) == {
        CONCEPT_COUNTING_TIME,
        CONCEPT_SCAN_COUNT,
        CONCEPT_EMISSION_ENERGY,
        CONCEPT_FILTER,
    }
    first = by_concept[CONCEPT_COUNTING_TIME][0]
    assert first.raw_literal == "0.5"
    assert first.normalized_value == 0.5
    assert first.unit == "s"
    emission = by_concept[CONCEPT_EMISSION_ENERGY][0]
    assert emission.normalized_value == 1050
    assert emission.unit == "eV"
    assert by_concept[CONCEPT_FILTER][0].normalized_value == 10
    assert all(
        e.normalization_rule == macros.RULE_IRL3_XAS_SIGNATURE for e in calls
    )


def test_a_call_with_the_wrong_argument_count_yields_nothing_and_says_why():
    """Assigning four documented roles to three arguments would be a guess."""
    target = FIXTURES / "macros" / "run15.mac"
    result = macros.read_macro(_record(target), _text(target))
    entries = [
        e for e in result.skipped if e["reason"] == macros.SKIP_ARGUMENT_COUNT
    ]
    assert len(entries) == 1
    assert entries[0]["argument_count"] == 3
    assert entries[0]["expected_argument_count"] == 4
    assert "Ir_XAS.mac" in entries[0]["detail"]


def test_a_macro_declaring_zero_newfile_blocks_is_not_a_failure():
    """Four real macros declare none. Each is a legitimate file."""
    for name in ("Ir_XAS.mac", "motors_cpy_pre99.mac"):
        target = FIXTURES / "macros" / name
        text = _text(target)
        result = macros.read_macro(_record(target), text)
        assert result.refused_reason is None
        assert _by_concept(result, CONCEPT_ACQUISITION_TARGET) == []
        assert macros.newfile_targets(text) == ()
        assert result.evidence, f"{name} produced no evidence at all"


def test_a_def_method_macro_reads_its_grids_and_declares_no_measurement():
    target = FIXTURES / "macros" / "Ir_XAS.mac"
    result = macros.read_macro(_record(target), _text(target))
    assert result.source_path == "Ir_XAS.mac"
    methods = _by_concept(result, CONCEPT_ACQUISITION_METHOD)
    assert [m.normalized_value for m in methods] == [
        "IrL3_xas",
        "IrL3_short_xas",
    ]
    grids = _by_concept(result, CONCEPT_ENERGY_GRID)
    # TWO grids, and neither is chosen: the macro does not state which
    # procedure any acquisition called.
    assert [g.raw_literal for g in grids] == [
        "1000 1020 5 1040 1 1060 0.5 1100 2",
        "1000 1020 5 1050 1 1100 5",
    ]
    assert {g.scope for g in grids} == {SCOPE_BEAMTIME}


def test_a_motor_snapshot_does_not_report_crystal_motors_as_sample_position():
    """``motors_cpy_*`` moves spectrometer crystals, not the sample stage.

    Calling those a sample position would be a false statement about where the
    sample was.
    """
    target = FIXTURES / "macros" / "motors_cpy_pre99.mac"
    result = macros.read_macro(_record(target), _text(target))
    assert _by_concept(result, CONCEPT_SAMPLE_POSITION) == []
    moves = _by_concept(result, CONCEPT_MOTOR_POSITION)
    assert len(moves) == 8
    assert {m.normalized_value["motor"] for m in moves} == {
        "c1p",
        "c1y",
        "c2p",
        "c2y",
        "c3p",
        "c3y",
        "c4p",
        "c4y",
    }
    assert all(m.normalized_value["relative"] is False for m in moves)


def test_absolute_and_relative_moves_stay_distinguishable():
    """Adding an ``mvr`` offset to a preceding ``mv`` would compute a position
    the file never states."""
    body = "newfile a\nmv Sx -1.25 Sz -3.5\nmvr Sz -0.3\n"
    result = macros.read_macro(_synthetic_record("m.mac", body=body), body)
    moves = _by_concept(result, CONCEPT_SAMPLE_POSITION)
    assert [
        (m.normalized_value["motor"], m.normalized_value["relative"])
        for m in moves
    ] == [("Sx", False), ("Sz", False), ("Sz", True)]


def test_an_odd_motor_argument_count_is_refused_not_paired_up():
    body = "newfile a\nmv Sx -1.25 Sz\n"
    result = macros.read_macro(_synthetic_record("m.mac", body=body), body)
    assert _by_concept(result, CONCEPT_SAMPLE_POSITION) == []
    entries = [
        e
        for e in result.skipped
        if e["reason"] == macros.SKIP_UNPAIRED_MOTOR_ARGUMENTS
    ]
    assert len(entries) == 1
    assert entries[0]["argument_count"] == 3


def test_a_trigger_is_read():
    target = FIXTURES / "macros" / "run15.mac"
    result = macros.read_macro(_record(target), _text(target))
    triggers = _by_concept(result, CONCEPT_TRIGGER)
    assert len(triggers) == 3
    assert all(t.raw_literal == "trigger" for t in triggers)


def test_a_macro_declaring_an_unacquired_target_still_reads_it():
    """A macro states an INTENTION. 9 real targets have no acquisition file."""
    target = FIXTURES / "macros" / "run99-unacquired.mac"
    text = _text(target)
    assert macros.newfile_targets(text) == (
        "99_09_ZZ3_base_after1500Cycling_filter20_100mV",
    )
    result = macros.read_macro(_record(target), text)
    item = _one(result, CONCEPT_ACQUISITION_TARGET)
    assert (
        item.normalized_value
        == "99_09_ZZ3_base_after1500Cycling_filter20_100mV"
    )
    assert item.normalization_rule == macros.RULE_NEWFILE_TARGET
    assert "INTENTION" in item.normalization_rule.upper()


def test_a_newfile_target_reads_through_the_same_recognizers_as_a_filename():
    """The conflict between a declaration and a filename is only visible if
    both are read the same way."""
    stem = "99_09_ZZ3_base_after1500Cycling_filter20_100mV"
    result = filenames.read_filename(
        _synthetic_record("run99-unacquired.mac"),
        stem=stem,
        source_type=SOURCE_TYPE_MACRO,
    )
    assert _one(result, CONCEPT_LEGACY_NUMBER).normalized_value == 99
    assert _one(result, CONCEPT_FILTER).normalized_value == 20
    assert _one(result, CONCEPT_POTENTIAL_MAGNITUDE).normalized_value == 0.1
    assert {e.source_type for e in result.evidence} == {SOURCE_TYPE_MACRO}


def test_unread_macro_lines_are_counted_rather_than_interpreted():
    body = "newfile a\nsome_unknown_command 1 2 3\nanother thing\n"
    result = macros.read_macro(_synthetic_record("m.mac", body=body), body)
    entries = [
        e for e in result.skipped if e["reason"] == macros.SKIP_UNREAD_COMMAND
    ]
    assert len(entries) == 1
    assert entries[0]["line_count"] == 2
    assert entries[0]["first_line"] == "some_unknown_command 1 2 3"


def test_the_macro_reader_refuses_a_spec_data_file():
    result = macros.read_macro(_record(SPEC_FIXTURE), _text(SPEC_FIXTURE))
    assert result.refused_reason is not None
    assert "not_a_macro" in result.refused_reason
    assert result.evidence == ()


def test_the_macro_reader_survives_an_empty_and_a_comment_only_source():
    for body in ("", "# only a comment\n\n# and another\n"):
        result = macros.read_macro(_synthetic_record("m.mac", body=body), body)
        assert result.refused_reason is None
        assert result.evidence == ()


def test_the_documented_xas_command_set_is_declared_and_used():
    """Extending it requires a source stating the new command's signature.

    Reading four roles off an unknown command's four arguments would be a guess
    dressed as a normalisation — and a plausible one, which is worse.
    """
    assert macros.DOCUMENTED_XAS_COMMANDS == ("IrL3_xas", "IrL3_short_xas")
    body = "newfile a\nSomeOther_xas 0.5 2 1050 10\n"
    result = macros.read_macro(_synthetic_record("m.mac", body=body), body)
    from isaac_api.bl15.evidence import CONCEPT_COUNTING_TIME

    assert _by_concept(result, CONCEPT_COUNTING_TIME) == []
    assert macros.SKIP_UNREAD_COMMAND in [e["reason"] for e in result.skipped]


# ===========================================================================
# 9. THE README AND THE BEAMTIME NOTES
# ===========================================================================


def test_the_readme_reads_all_four_of_its_sections_at_beamtime_scope():
    """A readme states things about the WHOLE beamtime.

    Treating any of them as a per-measurement value would be a lie about where
    it came from.
    """
    result = notes.read_shared_readme(
        _record(README_FIXTURE), _text(README_FIXTURE)
    )
    assert result.refused_reason is None
    concepts = {e.concept for e in result.evidence}
    assert concepts == {
        CONCEPT_ELEMENT,
        CONCEPT_BEAMSIZE,
        CONCEPT_SPECTROMETER_CONFIG,
        CONCEPT_MONOCHROMATOR_CALIBRATION,
    }
    assert {e.scope for e in result.evidence} == {SCOPE_BEAMTIME}
    assert {e.measurement_stem for e in result.evidence} == {None}


def test_a_readme_label_carrying_a_non_letter_before_its_colon_still_matches():
    """**A DEFECT THE REAL FILE FOUND AND NO REVIEW WOULD HAVE.**

    The first label pattern allowed only letters and spaces, so it silently
    failed to match the archive's own ``Beamsize @<energy>eV:`` label and sent the
    beamsize section to ``skipped``.
    """
    result = notes.read_shared_readme(
        _record(README_FIXTURE), _text(README_FIXTURE)
    )
    beamsize = _one(result, CONCEPT_BEAMSIZE)
    assert beamsize.raw_literal.startswith("Beamsize @1100eV:")
    # The indented continuation lines are part of the statement.
    assert "100 um vert" in beamsize.raw_literal
    assert "600 um horz" in beamsize.raw_literal
    assert beamsize.locator == "lines 9..11 (`Beamsize @1100eV`)"


def test_the_readme_element_is_read_as_itself_and_nothing_is_derived():
    item = _one(
        notes.read_shared_readme(
            _record(README_FIXTURE), _text(README_FIXTURE)
        ),
        CONCEPT_ELEMENT,
    )
    assert item.raw_literal == "Sy"
    assert item.normalized_value == "Sy"
    # No edge, no atomic number, no absorption line.
    assert "no atomic number" in item.normalization_rule


def _notes_result() -> ReaderResult:
    return notes.read_beamtime_notes(
        _record(NOTES_FIXTURE), _text(NOTES_FIXTURE)
    )


def test_the_notes_fixture_really_has_a_bom_and_crlf_endings():
    """The fixture's whole point, checked at the byte level.

    An encoding trap that is not actually present in the fixture is a test that
    proves nothing.
    """
    raw = NOTES_FIXTURE.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf"
    assert raw.count(b"\r\n") > 50
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_the_notes_reader_survives_the_bom_and_crlf():
    result = _notes_result()
    assert result.refused_reason is None
    assert result.evidence
    # No literal carries a stray CR or the BOM.
    assert not any("\r" in e.raw_literal for e in result.evidence)
    assert not any("﻿" in e.raw_literal for e in result.evidence)


def test_the_broad_claim_is_read_at_beamtime_scope_and_applied_to_nothing():
    """**THE ONE RULE THAT MATTERS MOST IN THIS READER.**

    *"In ALL experiments we used ..."* sits directly above a sample section that
    contradicts it. It is candidate shared context; the contradiction is a
    conflict for a scientist, and no reader may resolve it by preferring either.
    """
    result = _notes_result()
    media = _by_concept(result, CONCEPT_ELECTROLYTE_OR_MEDIUM)
    broad = [m for m in media if m.scope == SCOPE_BEAMTIME]
    assert len(broad) == 1
    assert broad[0].raw_literal.startswith("In ALL experiments")
    assert broad[0].normalization_rule == notes.RULE_BROAD_CLAIM
    # NO value is extracted from it: a concentration lifted out of a claim the
    # document itself contradicts would look like a resolved fact.
    assert broad[0].normalized_value is None

    # And the sample-scoped media are untouched by it — including the one that
    # contradicts it.
    sample_media = sorted(
        m.normalized_value for m in media if m.scope == SCOPE_SAMPLE_GROUP
    )
    assert sample_media == ["acid", "base", "base"]


def test_a_file_number_row_states_a_number_and_never_a_stem():
    """The notes state a legacy NUMBER. Joining it to a stem is ``relate``'s job
    — and the archive has a duplicate legacy number, so the join is not even a
    function."""
    result = _notes_result()
    rows = _by_concept(result, CONCEPT_NOTE_FILE_NUMBER_ROW)
    assert [r.normalized_value for r in rows] == [11, 12, 13, 14]
    assert all(r.measurement_stem is None for r in rows)
    assert all(r.scope == SCOPE_MEASUREMENT for r in rows)
    assert all(r.normalization_rule == notes.RULE_TABLE_ROW for r in rows)
    assert all("File Number" in r.locator for r in rows)


def test_an_empty_file_number_column_yields_no_file_numbers_at_all():
    """**THE DEFECT THE REAL DOCUMENT FOUND.**

    The first version of this reader paired any two bare integers and read
    Sample 1's STEP numbers as FILE numbers, because an empty DOCX cell flattens
    to a lone tab that a blank-line skip swallowed. Sample 1 of the fixture has
    an empty File Number column throughout; the steps must still read, and no
    file number may be invented.
    """
    result = _notes_result()
    steps = _by_concept(result, CONCEPT_STEP_NUMBER)
    rows = _by_concept(result, CONCEPT_NOTE_FILE_NUMBER_ROW)
    # Table 0 (the empty-column one) contributes 3 steps and 0 file numbers.
    table0_steps = [s for s in steps if "table 0" in s.locator]
    assert [s.normalized_value for s in table0_steps] == [1, 2, 3]
    assert [r for r in rows if "table 0" in r.locator] == []
    # and each absent cell is DISCLOSED rather than silently dropped.
    absent = [
        e
        for e in result.skipped
        if e["reason"] == notes.SKIP_UNREADABLE_TABLE_ROW
    ]
    assert len(absent) == 3
    assert all("File Number" in e["locator"] for e in absent)


def test_a_step_headed_table_with_no_file_number_column_reads_no_file_numbers():
    """Two real tables have this shape, and their rows are not file numbers."""
    result = _notes_result()
    rows = _by_concept(result, CONCEPT_NOTE_FILE_NUMBER_ROW)
    # The CV-steps table is the last one; its `1`/`2` must not appear.
    assert max(r.normalized_value for r in rows) == 14
    assert 1 not in [r.normalized_value for r in rows]


def test_the_notes_state_the_potential_reference_basis_and_the_filenames_do_not():
    """**THIS IS THE ONLY PLACE IN THE CORPUS THAT STATES A BASIS.**

    ``bl15.filenames`` deliberately never emits the concept; the notes do.
    """
    result = _notes_result()
    bases = _by_concept(result, CONCEPT_POTENTIAL_REFERENCE)
    assert bases
    literals = {b.raw_literal for b in bases}
    assert "RHE" in literals
    assert any("reference" in literal for literal in literals)
    assert all(b.scope == SCOPE_SAMPLE_GROUP for b in bases)
    assert all(
        b.normalization_rule == notes.RULE_REFERENCE_BASIS for b in bases
    )


def test_the_notes_read_the_conditions_the_filenames_never_carry():
    result = _notes_result()
    assert _one(result, CONCEPT_PH).normalized_value == 13
    gas = _one(result, CONCEPT_GAS_CONDITION)
    assert gas.normalized_value == "ar"
    flow = _one(result, CONCEPT_FLOW_RATE)
    assert flow.normalized_value == 10
    assert flow.unit == "mL/min"
    filters = _by_concept(result, CONCEPT_FILTER)
    assert [f.normalized_value for f in filters] == [20]
    assert filters[0].scope == SCOPE_SAMPLE_GROUP


def test_a_sample_heading_states_a_name_a_medium_and_sometimes_a_quality_note():
    result = _notes_result()
    names = _by_concept(result, CONCEPT_SAMPLE_NAME)
    assert [n.normalized_value for n in names] == ["ZZ1", "ZZ2", "ZZ3"]
    assert {n.scope for n in names} == {SCOPE_SAMPLE_GROUP}
    quality = _one(result, CONCEPT_QUALITY_NOTE)
    assert quality.raw_literal == "bad"
    assert quality.scope == SCOPE_SAMPLE_GROUP


def test_a_sample_heading_with_no_name_and_no_medium_is_not_invented():
    """``Sample 4`` of the fixture states neither, as two real sections do."""
    result = _notes_result()
    assert len(_by_concept(result, CONCEPT_SAMPLE_NAME)) == 3
    media = [
        m
        for m in _by_concept(result, CONCEPT_ELECTROLYTE_OR_MEDIUM)
        if m.scope == SCOPE_SAMPLE_GROUP
    ]
    assert len(media) == 3


def test_the_beamtime_dates_and_purpose_are_read_verbatim_and_not_parsed():
    result = _notes_result()
    dates = _one(result, CONCEPT_BEAMTIME_DATES)
    assert dates.raw_literal == "Beam September 9-12, 2001"
    # NOT parsed into two ISO instants: the line names no timezone.
    assert dates.timestamp_utc is None
    assert dates.normalized_value is None
    purpose = _one(result, CONCEPT_BEAMTIME_PURPOSE)
    assert purpose.raw_literal.startswith("Invented study")
    assert purpose.scope == SCOPE_BEAMTIME


def test_preparation_headings_are_declared_and_their_prose_is_not_parsed():
    """A ``Weigh <mass> of <material>`` line is a recipe step, not a metadata field."""
    result = _notes_result()
    preparations = _by_concept(result, CONCEPT_SAMPLE_PREPARATION)
    assert [p.raw_literal for p in preparations] == [
        "What to have ready",
        "Procedure for Preparing Electrode",
    ]
    assert {p.scope for p in preparations} == {SCOPE_BEAMTIME}
    assert all(p.normalized_value is None for p in preparations)


def test_the_echem_procedure_is_read_verbatim_without_splitting_the_potential():
    """Splitting the sentence would separate a magnitude from the only basis
    statement the corpus has for it."""
    result = _notes_result()
    procedures = _by_concept(result, CONCEPT_ECHEM_PROCEDURE)
    assert len(procedures) == 7
    assert all(
        "Sets the working potential to" in p.raw_literal for p in procedures
    )
    assert _by_concept(result, CONCEPT_POTENTIAL_MAGNITUDE) == []


def test_unparsed_prose_is_reported_in_contiguous_blocks_with_its_first_line():
    """One entry per block, naming the range, the count and the first line —
    not one entry per line, and not a bare total."""
    result = _notes_result()
    blocks = [
        e
        for e in result.skipped
        if e["reason"] == notes.SKIP_UNRECOGNIZED_PROSE
    ]
    assert blocks
    assert all("line_count" in e and "first_line_text" in e for e in blocks)
    assert any(e["line_count"] > 1 for e in blocks), (
        "no multi-line block was grouped — the grouping is doing nothing"
    )
    assert any(".." in e["locator"] for e in blocks)


def test_the_notes_module_says_the_docx_pdf_txt_trio_is_one_witness():
    doc = notes.__doc__ or ""
    assert "ONE SOURCE FAMILY, NOT THREE WITNESSES" in doc
    assert "no DOCX and no PDF extraction" in doc


def test_the_notes_readers_refuse_an_oversized_source():
    for reader in (notes.read_shared_readme, notes.read_beamtime_notes):
        record = SourceRecord(
            archive_path="huge.txt",
            basename="huge.txt",
            extension="txt",
            size_bytes=MAX_SOURCE_BYTES + 1,
            content_sha256="0" * 64,
            parent_dir="",
            depth=0,
        )
        result = reader(record, "Sy\n")
        assert result.refused_reason is not None
        assert result.evidence == ()


def test_the_notes_readers_survive_empty_and_hostile_input():
    for body in ("", "\r\n\r\n", "﻿", "\t\n\t\n", "Sample\nStep\n"):
        for reader in (notes.read_shared_readme, notes.read_beamtime_notes):
            result = reader(_synthetic_record("x.txt", body=body), body)
            assert result.refused_reason is None
            assert isinstance(result.evidence, tuple)


# ===========================================================================
# 10. CROSS-READER INVARIANTS
# ===========================================================================


def test_no_reader_ever_raises_on_any_fixture_handed_to_any_reader():
    """**The contract: a reader never raises for bad input.**

    Every fixture is handed to every reader — 6 readers x every fixture — and
    each must answer with a :class:`ReaderResult`, refusing where the format is
    not its own. A refusal a scientist can see beats an exception a log swallows.
    """
    readers = (
        ("spec", lambda r, t: spec.read_spec_acquisition(r, t)),
        ("scans", lambda r, t: scans.read_scan_export(r, t)),
        ("macros", lambda r, t: macros.read_macro(r, t)),
        ("readme", lambda r, t: notes.read_shared_readme(r, t)),
        ("notes", lambda r, t: notes.read_beamtime_notes(r, t)),
        ("filenames", lambda r, t: filenames.read_filename(r)),
    )
    combinations = 0
    for path in _every_fixture_file():
        if path.suffix == ".md":
            continue
        record = _record(path)
        text = path.read_bytes().decode("utf-8", "replace")
        for name, reader in readers:
            result = reader(record, text)
            assert isinstance(result, ReaderResult), f"{name} on {path.name}"
            assert result.parser_id
            assert result.source_path == record.archive_path
            combinations += 1
    assert combinations > 60, f"only {combinations} combinations exercised"


def test_every_concept_every_reader_emits_is_in_the_declared_vocabulary():
    for _label, _source, result in _all_fixture_readings():
        for item in result.evidence:
            assert item.concept in CONCEPTS


def test_every_reading_round_trips_through_to_state():
    """The wire shape carries every field, including the empty ones."""
    for _label, _source, result in _all_fixture_readings():
        state = result.to_state()
        assert set(state) == {
            "source_path",
            "parser_id",
            "evidence",
            "skipped",
            "refused_reason",
        }
        for item, wire in zip(result.evidence, state["evidence"]):
            assert wire["raw_literal"] == item.raw_literal
            assert "normalized_value" in wire
            assert "unit" in wire
            assert "measurement_stem" in wire


def test_evidence_ids_are_deterministic_for_the_same_bytes():
    """A reader is a pure function of the text it is handed.

    No clock, no random source, no process state. Two runs over the same bytes
    produce identical ids.
    """
    first = _spec_result()
    second = _spec_result()
    assert [e.evidence_id for e in first.evidence] == [
        e.evidence_id for e in second.evidence
    ]
    assert [e.to_state() for e in first.evidence] == [
        e.to_state() for e in second.evidence
    ]


def test_an_id_prefix_namespaces_a_reading_without_changing_anything_else():
    plain = _spec_result()
    prefixed = spec.read_spec_acquisition(
        _record(SPEC_FIXTURE), _text(SPEC_FIXTURE), id_prefix="session-7:"
    )
    assert all(e.evidence_id.startswith("session-7:") for e in prefixed.evidence)
    for left, right in zip(plain.evidence, prefixed.evidence):
        assert left.to_state() | {"evidence_id": None} == right.to_state() | {
            "evidence_id": None
        }


def test_no_reader_opens_a_file():
    """The boundary ``historical_import.SourceParser`` draws, kept in one place.

    Asserted over each reader module's own source: none of them mentions
    ``open(``, ``Path.read_text`` or ``io.open``.
    """
    for module in (filenames, classify, spec, scans, macros, notes, profiles):
        source = Path(module.__file__).read_text(encoding="utf-8")
        body = "\n".join(
            line
            for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        for forbidden in ("open(", "read_text", "read_bytes", "Path("):
            assert forbidden not in body, (
                f"{module.__name__} mentions {forbidden!r} — a reader takes "
                f"text the caller obtained and opens nothing"
            )
