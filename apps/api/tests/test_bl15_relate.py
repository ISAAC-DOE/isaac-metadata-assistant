"""What belongs to what, and what disagrees — with no disagreement ever resolved.

The tests are weighted toward the two shortcuts the authorizing brief forbids by name
(one macro is not one Run; one scan file is not one Run) and toward the four false
positives that would pollute a conflict list. A conflict list with wrong entries in it
is a list a scientist stops reading, which makes a false conflict worse than a missing
feature.
"""

from __future__ import annotations

import hashlib

import pytest

from isaac_api.bl15 import evidence as ev
from isaac_api.bl15 import relate as R
from isaac_api.bl15.inventory import SourceRecord


def rec(path: str, *, content: str | None = None) -> SourceRecord:
    """A SourceRecord for a path. Content defaults to the path, so digests differ."""
    basename = path.rsplit("/", 1)[-1]
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    body = (content if content is not None else path).encode("utf-8")
    return SourceRecord(
        archive_path=path,
        basename=basename,
        extension=basename.rsplit(".", 1)[1].lower() if "." in basename else "",
        size_bytes=len(body),
        content_sha256=hashlib.sha256(body).hexdigest(),
        parent_dir=parent,
        depth=path.count("/"),
    )


SPEC = ev.SOURCE_TYPE_SPEC_ACQUISITION
SCAN = ev.SOURCE_TYPE_SCAN_EXPORT
MACRO = ev.SOURCE_TYPE_MACRO


def a_measurement(stem: str, *, scans: int = 2, content: str | None = None):
    """An acquisition, its byte-identical `_dir` copy, and N scan children.

    The copy is included because THE REAL ARCHIVE ALWAYS HAS ONE, and a fixture without
    it would not exercise the deduplication that stops the corpus doubling.
    """
    body = content if content is not None else f"#F {stem}\n"
    entries = [rec(stem, content=body), rec(f"{stem}_dir/{stem}", content=body)]
    classifications = {stem: SPEC, f"{stem}_dir/{stem}": SPEC}
    for i in range(1, scans + 1):
        path = f"{stem}_dir/{stem}_{i:03d}.dat"
        entries.append(rec(path))
        classifications[path] = SCAN
    return entries, classifications


# --- the two forbidden shortcuts --------------------------------------------


def test_a_macro_declaring_eight_measurements_produces_eight_units_not_one():
    """One `.mac` is NOT one Run. The real corpus's worst case is 8 in one file."""
    entries: list[SourceRecord] = [rec("run15.mac")]
    classifications = {"run15.mac": MACRO}
    targets = [f"{n:02d}_02_ZZ1_base_filter10_850mV" for n in range(15, 23)]
    for stem in targets:
        e, c = a_measurement(stem, scans=1)
        entries += e
        classifications |= c

    out = R.relate(
        entries=entries,
        classifications=classifications,
        macro_declarations={"run15.mac": targets},
    )
    assert len(out.units) == 8
    # every unit knows which macro block declared it, with the block index
    for i, unit in enumerate(out.units):
        assert len(unit.declared_by) == 1
        assert unit.declared_by[0].macro_path == "run15.mac"
        assert unit.declared_by[0].block_index == i
        assert unit.declared_by[0].acquired is True
    # and the macro itself is NOT a unit
    assert all(u.acquisition_path != "run15.mac" for u in out.units)


def test_a_macro_declaring_nothing_is_not_a_unit_and_is_not_an_error():
    """Four real macros declare no measurement — a method definition, a trigger, two
    motor snapshots. A relate pass must place them without inventing a measurement."""
    entries = [rec("Ir_XAS.mac"), rec("trigger.mac"), rec("motors_cpy_pre77.mac")]
    classifications = {
        "Ir_XAS.mac": ev.SOURCE_TYPE_ACQUISITION_METHOD_MACRO,
        "trigger.mac": MACRO,
        "motors_cpy_pre77.mac": ev.SOURCE_TYPE_MOTOR_SNAPSHOT_MACRO,
    }
    out = R.relate(
        entries=entries,
        classifications=classifications,
        macro_declarations={"Ir_XAS.mac": [], "trigger.mac": [], "motors_cpy_pre77.mac": []},
    )
    assert out.units == ()
    assert {u["archive_path"] for u in out.unattached} == set(classifications)
    # each carries a reason naming what it IS, not one shared "unmatched" bucket
    reasons = {u["archive_path"]: u["reason"] for u in out.unattached}
    assert "acquisition method" in reasons["Ir_XAS.mac"]
    assert "instrument state" in reasons["motors_cpy_pre77.mac"]


def test_scan_exports_stay_children_and_never_become_units():
    """One `.dat` is NOT one Run. 233 scans in one real directory; still one unit."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=233)
    out = R.relate(entries=entries, classifications=classifications)
    assert len(out.units) == 1
    unit = out.units[0]
    assert unit.scan_count == 233
    assert all(c.scan_index is not None for c in unit.scans)
    # the indices are READ from the filenames, not assigned by listing order
    assert [c.scan_index for c in unit.scans] == list(range(1, 234))
    assert out.unattached == ()


def test_a_measurement_with_zero_scans_is_still_a_unit():
    """Two real measurements have empty scan directories, so "has scans" cannot gate."""
    entries, classifications = a_measurement("01_ZZ_oldPellet_f35", scans=0)
    out = R.relate(entries=entries, classifications=classifications)
    assert len(out.units) == 1
    assert out.units[0].scan_count == 0
    assert out.units[0].scan_dir is None


# --- the deduplication that stops the corpus doubling -----------------------


def test_a_byte_identical_copy_does_not_become_a_second_measurement():
    """THE FACTOR-OF-TWO BUG, pinned.

    Every `*_dir` in the real archive holds a byte-identical copy of its root
    acquisition, and a content-led classifier calls those copies acquisitions —
    CORRECTLY, since they begin with `#F`. Letting them become units turned 94
    measurements into 181, 908 scans into 1,332, and one duplicated legacy number into
    89. The copy is still listed; it is just not a second measurement.
    """
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=3)
    out = R.relate(entries=entries, classifications=classifications)

    assert len(out.units) == 1
    unit = out.units[0]
    # the ROOT path is canonical (shallowest), not the one inside the directory
    assert unit.acquisition_path == "15_02_ZZ1_base_filter10_850mV"
    assert unit.suppressed_duplicate_acquisitions == (
        "15_02_ZZ1_base_filter10_850mV_dir/15_02_ZZ1_base_filter10_850mV",
    )
    # and the copy is NOT reported as unattached — it is accounted for
    assert out.unattached == ()


def test_deduplication_is_by_content_and_never_by_name():
    """Two acquisitions with the same stem and DIFFERENT bytes are two measurements.

    Names are unreliable in this corpus — four files were renamed after acquisition, and
    `run29.mac` / `run29.mac.mac` hold different content under similar names. So identity
    is the digest.
    """
    entries = [
        rec("a/30_03_ZZ1_base_filter20_850mV", content="#F one\n"),
        rec("b/30_03_ZZ1_base_filter20_850mV", content="#F two\n"),
    ]
    classifications = dict.fromkeys((e.archive_path for e in entries), SPEC)
    out = R.relate(entries=entries, classifications=classifications)
    assert len(out.units) == 2
    assert all(u.suppressed_duplicate_acquisitions == () for u in out.units)


def test_source_count_counts_identical_bytes_once():
    """A duplicate must not inflate a scientist's confidence for a filesystem reason."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=2)
    out = R.relate(entries=entries, classifications=classifications)
    # 1 acquisition + 2 scans, and NOT the byte-identical copy
    assert out.units[0].source_count == 3


# --- the conflicts -----------------------------------------------------------


def test_an_internal_declaration_disagreeing_with_the_filename_is_a_conflict():
    stem = "29_03_ZZ1_base_after1500Cycling_filter20_060mV"
    entries, classifications = a_measurement(stem, scans=1)
    out = R.relate(
        entries=entries,
        classifications=classifications,
        internal_declarations={stem: "29_03_ZZ1_base_beforeCycling_filter20_060mV"},
    )
    conflicts = out.units[0].conflicts
    assert [c.kind for c in conflicts] == [R.CONFLICT_DECLARATION_VS_FILENAME]
    readings = conflicts[0].readings
    assert {r.locator for r in readings} == {"filename", "#F"}
    # NEITHER is preferred, and the explanation says so
    assert "Neither is preferred automatically" in conflicts[0].explanation
    assert conflicts[0].unresolved_reason == R.UNRESOLVED_SOURCES_DISAGREE


def test_a_macro_agreeing_with_the_internal_declaration_makes_it_a_THREE_way_conflict():
    """The real corpus's most instructive case, and a surface built for two would miss it.

    For the 29-32 group the macro declared the *internal* name while the file carries
    the renamed one — so the macro, the header and the filename are three sources.
    """
    stem = "29_03_ZZ1_base_after1500Cycling_filter20_060mV"
    declared = "29_03_ZZ1_base_beforeCycling_filter20_060mV"
    entries, classifications = a_measurement(stem, scans=1)
    entries.append(rec("run29.mac"))
    classifications["run29.mac"] = MACRO

    out = R.relate(
        entries=entries,
        classifications=classifications,
        internal_declarations={stem: declared},
        macro_declarations={"run29.mac": [declared]},
    )
    conflict = next(
        c
        for c in out.units[0].conflicts
        if c.kind == R.CONFLICT_DECLARATION_VS_FILENAME
    )
    assert len(conflict.readings) == 3
    assert [r.locator for r in conflict.readings] == [
        "filename",
        "#F",
        "newfile block 0",
    ]


def test_an_absolute_path_in_the_declaration_is_NOT_a_conflict():
    """MEASURED FALSE POSITIVE, and the reason this comparison is on basenames.

    Two real files declare themselves with an absolute filesystem path rather than a
    bare stem. Over all 188 files carrying a declaration: 186 bare stems, 2 absolute
    paths, and ZERO whose basename still differs once the path is stripped. A raw
    comparison reported both as conflicts.
    """
    stem = "ave_ZZ1_filter10.mca"
    entries = [rec(stem, content="#F /data/beamline/2099-04/MERGE/ave_ZZ1_filter10.mca\n")]
    classifications = {stem: SPEC}
    out = R.relate(
        entries=entries,
        classifications=classifications,
        internal_declarations={
            stem: "/data/beamline/2099-04/MERGE/ave_ZZ1_filter10.mca"
        },
    )
    assert out.units[0].conflicts == ()
    # the declaration is still RECORDED, verbatim and untrimmed
    assert out.units[0].internal_declaration.startswith("/data/")


def test_a_duplicated_legacy_number_keeps_both_files_and_prefers_neither():
    entries, c1 = a_measurement("32_03_ZZ1_base_after1400Cycling_filter20_1500mV", scans=1)
    more, c2 = a_measurement("32_03_ZZ1_base_after1500Cycling_filter20_1500mV", scans=1)
    out = R.relate(entries=entries + more, classifications=c1 | c2)

    assert len(out.units) == 2
    conflicts = [
        c for c in out.corpus_conflicts if c.kind == R.CONFLICT_DUPLICATE_LEGACY_NUMBER
    ]
    assert len(conflicts) == 1
    assert conflicts[0].subject == "32"
    assert len(conflicts[0].readings) == 2
    assert "neither is the 'real' one" in conflicts[0].explanation


def test_a_declared_target_that_was_never_acquired_is_a_corpus_conflict():
    entries = [rec("run29.mac")]
    classifications = {"run29.mac": MACRO}
    out = R.relate(
        entries=entries,
        classifications=classifications,
        macro_declarations={"run29.mac": ["44_04_ZZ1_base_filter20_1500mV"]},
    )
    assert out.units == ()
    kinds = [c.kind for c in out.corpus_conflicts]
    assert kinds == [R.CONFLICT_DECLARED_NEVER_ACQUIRED]
    assert out.corpus_conflicts[0].subject == "44_04_ZZ1_base_filter20_1500mV"


def test_acquired_never_declared_fires_only_when_macros_were_actually_supplied():
    """Otherwise every measurement in a macro-less import would carry a false conflict."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=1)
    without = R.relate(entries=entries, classifications=classifications)
    assert without.units[0].conflicts == ()

    with_macros = R.relate(
        entries=entries + [rec("run01.mac")],
        classifications=classifications | {"run01.mac": MACRO},
        macro_declarations={"run01.mac": ["99_99_other"]},
    )
    assert [c.kind for c in with_macros.units[0].conflicts] == [
        R.CONFLICT_ACQUIRED_NEVER_DECLARED
    ]


def test_alignment_and_standards_do_not_get_a_never_declared_conflict():
    """MEASURED FALSE POSITIVE: 5 entries no scientist would call a discrepancy.

    Nobody expects a macro to have declared an alignment scan or a reference pellet.
    """
    entries, classifications = a_measurement("alignment", scans=4)
    classifications = {
        k: (ev.SOURCE_TYPE_ALIGNMENT if v == SPEC else v)
        for k, v in classifications.items()
    }
    out = R.relate(
        entries=entries + [rec("run01.mac")],
        classifications=classifications | {"run01.mac": MACRO},
        macro_declarations={"run01.mac": ["99_99_other"]},
    )
    assert out.units[0].conflicts == ()


def test_a_conflict_cannot_exist_with_fewer_than_two_readings_or_no_explanation():
    with pytest.raises(ValueError):
        R.Conflict(
            kind=R.CONFLICT_DUPLICATE_LEGACY_NUMBER,
            subject="32",
            readings=(R.Reading(source_path="a", locator="filename", value="x"),),
            explanation="two files share a number",
        )
    with pytest.raises(ValueError):
        R.Conflict(
            kind=R.CONFLICT_DUPLICATE_LEGACY_NUMBER,
            subject="32",
            readings=(
                R.Reading(source_path="a", locator="filename", value="x"),
                R.Reading(source_path="b", locator="filename", value="y"),
            ),
            explanation="",
        )
    with pytest.raises(ValueError):
        R.Conflict(kind="made_up", subject="x", readings=(), explanation="y")


# --- run candidacy, grouping, attachment ------------------------------------


def test_alignment_and_standards_are_units_but_not_run_candidates():
    """Their scans must attach to something: orphaning them mislabelled 242 real files."""
    align, ca = a_measurement("alignment", scans=5)
    ca = {k: (ev.SOURCE_TYPE_ALIGNMENT if v == SPEC else v) for k, v in ca.items()}
    std, cs = a_measurement("ZZ_pellet_transmission", scans=2)
    cs = {
        k: (ev.SOURCE_TYPE_STANDARD_OR_REFERENCE if v == SPEC else v)
        for k, v in cs.items()
    }
    sample, cm = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=1)

    out = R.relate(entries=align + std + sample, classifications=ca | cs | cm)
    assert len(out.units) == 3
    assert sum(u.scan_count for u in out.units) == 8
    assert out.unattached == ()

    by_stem = out.by_stem()
    assert by_stem["alignment"].run_candidate is False
    assert by_stem["ZZ_pellet_transmission"].run_candidate is False
    assert by_stem["15_02_ZZ1_base_filter10_850mV"].run_candidate is True


def test_groups_report_contiguity_and_an_interleaved_token_is_flagged():
    """A broken range is the signal that the token does not mean an instance.

    In the real corpus all ten ranges are contiguous, which corroborates the notes'
    sample sections — so the test that matters is that interleaving IS detected, since
    that is the case the corpus cannot demonstrate.
    """
    entries: list[SourceRecord] = []
    classifications: dict[str, str] = {}
    for number, token in [(1, "01"), (2, "01"), (3, "02"), (4, "01")]:
        e, c = a_measurement(f"{number:02d}_{token}_ZZ1_base_filter10_850mV", scans=0)
        entries += e
        classifications |= c
    out = R.relate(entries=entries, classifications=classifications)
    groups = {g.group_token: g for g in out.groups}
    assert groups["01"].legacy_low == 1 and groups["01"].legacy_high == 4
    assert groups["01"].contiguous is False  # 3 belongs to token 02
    assert groups["02"].contiguous is True


def test_a_stem_with_no_group_token_is_grouped_under_None_not_a_placeholder():
    entries, classifications = a_measurement("alignment", scans=0)
    out = R.relate(entries=entries, classifications=classifications)
    assert out.units[0].group_token is None
    assert [g.group_token for g in out.groups] == [None]


def test_scans_attach_by_their_directory_and_never_by_filename_prefix():
    """Prefix matching would cross-attach stems that differ only late in the name.

    Both of these exist in the real corpus under legacy number 32.
    """
    a, ca = a_measurement("32_03_ZZ1_base_after1400Cycling_filter20_1500mV", scans=2)
    b, cb = a_measurement("32_03_ZZ1_base_after1500Cycling_filter20_1500mV", scans=3)
    out = R.relate(entries=a + b, classifications=ca | cb)
    by_stem = out.by_stem()
    assert by_stem["32_03_ZZ1_base_after1400Cycling_filter20_1500mV"].scan_count == 2
    assert by_stem["32_03_ZZ1_base_after1500Cycling_filter20_1500mV"].scan_count == 3


def test_processed_products_attach_by_leading_number_and_unmatched_ones_stay_visible():
    """Deliberately weak matching: merged names are re-spelled, and 7 name no number."""
    entries, classifications = a_measurement("11_02_ZZ1_base_filter10_060mV", scans=1)
    entries += [rec("MERGE/11_02_ZZ1_base_f10_060mV.txt"), rec("MERGE/ave_ZZ1_f10.txt")]
    classifications["MERGE/11_02_ZZ1_base_f10_060mV.txt"] = (
        ev.SOURCE_TYPE_PROCESSED_SPECTRUM
    )
    classifications["MERGE/ave_ZZ1_f10.txt"] = ev.SOURCE_TYPE_PROCESSED_SPECTRUM

    out = R.relate(entries=entries, classifications=classifications)
    assert out.units[0].processed_products == ("MERGE/11_02_ZZ1_base_f10_060mV.txt",)
    assert [u["archive_path"] for u in out.unattached] == ["MERGE/ave_ZZ1_f10.txt"]
    assert "names no measurement number" in out.unattached[0]["reason"]


def test_shared_context_is_unattached_because_it_belongs_to_the_WHOLE_import():
    """A README is inherited, never copied into each measurement."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=1)
    entries.append(rec("readme.txt"))
    classifications["readme.txt"] = ev.SOURCE_TYPE_SHARED_README
    out = R.relate(entries=entries, classifications=classifications)
    assert [u["archive_path"] for u in out.unattached] == ["readme.txt"]
    assert "belongs to the whole import" in out.unattached[0]["reason"]
    assert "inherited rather than copied" in out.unattached[0]["reason"]


# --- honesty about what the pass could see ----------------------------------


def test_inputs_present_distinguishes_absent_evidence_from_absent_relationships():
    """Stops a consumer reading "no macro declared this" when no macro was offered."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=1)
    bare = R.relate(entries=entries, classifications=classifications)
    assert bare.inputs_present == ("entries", "classifications")
    assert bare.units[0].declared_by == ()
    assert bare.units[0].conflicts == ()

    full = R.relate(
        entries=entries,
        classifications=classifications,
        internal_declarations={"15_02_ZZ1_base_filter10_850mV": "other_name"},
        macro_declarations={"run01.mac": ["15_02_ZZ1_base_filter10_850mV"]},
        note_file_numbers={15: [{"step": "1", "note": "synthetic row"}]},
        duplicate_groups=[["a", "b"]],
    )
    assert full.inputs_present == (
        "entries",
        "classifications",
        "internal_declarations",
        "macro_declarations",
        "note_file_numbers",
        "duplicate_groups",
    )
    assert full.units[0].note_rows == ({"step": "1", "note": "synthetic row"},)


def test_the_pass_is_deterministic_under_input_reordering():
    """Two passes over one archive must produce identical state, or a diff means nothing."""
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=4)
    more, c2 = a_measurement("16_02_ZZ1_base_filter10_1200mV", scans=2)
    forward = R.relate(entries=entries + more, classifications=classifications | c2)
    backward = R.relate(
        entries=list(reversed(entries + more)), classifications=classifications | c2
    )
    assert forward.to_state() == backward.to_state()


def test_nothing_in_the_output_carries_a_scientific_value():
    """Relate assembles STRUCTURE. Values arrive from the readers and are mapped apart.

    Asserted because the tempting next step is to hang a parsed potential off a unit,
    and that would put an unmapped value one step from a record with no registry between.
    """
    entries, classifications = a_measurement("15_02_ZZ1_base_filter10_850mV", scans=1)
    out = R.relate(entries=entries, classifications=classifications)
    state = out.units[0].to_state()
    assert set(state) == {
        "stem",
        "acquisition_path",
        "source_type",
        "run_candidate",
        "legacy_number",
        "group_token",
        "scan_dir",
        "scans",
        "scan_count",
        "duplicate_copies",
        "suppressed_duplicate_acquisitions",
        "declared_by",
        "processed_products",
        "note_rows",
        "internal_declaration",
        "conflicts",
        "source_count",
    }
