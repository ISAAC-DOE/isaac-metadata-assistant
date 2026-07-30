"""`diagnostics.py` must normalize official-schema errors without ever becoming a
second source of truth.

Two classes of test live here:

* **Behavioural** — the normalization is correct against the authoritative
  schema: pointers, conditional detection, ordering, missing-vs-invalid, labels.
* **Structural** — the module is *incapable* of validating against a partial
  schema. Those tests read `diagnostics.py`'s own AST/tokens, because a
  behavioural test can only show that the full schema was used *this time*.

Every record here is a hand-built minimal dict or an in-memory mutation of the
committed synthetic fixtures in `tests/fixtures/official/`. Nothing is real
experimental data; the identifiers are deliberately obvious placeholders.
"""

import ast
import collections
import copy
import hashlib
import io
import json
import shutil
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from isaac_records import diagnostics as diagnostics_module
from isaac_records import official
from isaac_records.diagnostics import (
    INVALID,
    MISSING,
    Diagnostic,
    DiagnosticReport,
    DiagnosticsIntegrityError,
    diagnose,
    json_pointer,
    schema_fingerprint,
)
from isaac_records.official import EXPECTED_VERSION

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "tests" / "fixtures" / "official"
DIAGNOSTICS_FIXTURES = ROOT / "tests" / "fixtures" / "diagnostics"
COVERAGE_ARTIFACT = DIAGNOSTICS_FIXTURES / "rule_family_coverage.json"

SCHEMA_FILE = ROOT / "schema" / "isaac_record_v1.json"
MODULE_FILE = Path(diagnostics_module.__file__)

#: Obviously-fake ULID: 26 chars of [0-9A-Z], all zeros.
FAKE_ULID = "0" * 26
#: A second obviously-fake ULID for link targets.
FAKE_ULID_2 = "0" * 25 + "1"

ROOT_REQUIRED = [
    "isaac_record_version",
    "record_id",
    "record_type",
    "record_domain",
    "source_type",
    "timestamps",
]


def minimal_valid_record() -> dict:
    """The smallest record the authoritative schema accepts.

    `record_type` is deliberately *not* `evidence`: the schema's first `allOf`
    conditional would then require `descriptors`, which would add noise to every
    test built on this baseline.
    """
    return {
        "isaac_record_version": "1.05",
        "record_id": FAKE_ULID,
        "record_type": "intent",
        "record_domain": "characterization",
        "source_type": "laboratory",
        "timestamps": {"created_utc": "2026-01-01T00:00:00Z"},
    }


@pytest.fixture
def minimal():
    return minimal_valid_record()


@pytest.fixture
def xanes():
    """The committed synthetic XANES example (valid, `record_type: evidence`)."""
    return json.loads(
        (OFFICIAL / "ex_situ_xanes_cuo2_record.json").read_text(encoding="utf-8")
    )


def pointers(report: DiagnosticReport) -> list[str]:
    return [d.pointer for d in report.diagnostics]


def only(report: DiagnosticReport) -> Diagnostic:
    """Assert the report holds exactly one diagnostic and return it."""
    assert len(report.diagnostics) == 1, [
        (d.pointer, d.rule_family, d.message) for d in report.diagnostics
    ]
    return report.diagnostics[0]


def at(report: DiagnosticReport, pointer: str, rule_family: str) -> Diagnostic:
    """Return the single diagnostic at `pointer` for `rule_family`."""
    hits = [
        d
        for d in report.diagnostics
        if d.pointer == pointer and d.rule_family == rule_family
    ]
    assert len(hits) == 1, (
        f"expected exactly one {rule_family} at {pointer}, got "
        f"{[(d.pointer, d.rule_family) for d in report.diagnostics]}"
    )
    return hits[0]


# ---------------------------------------------------------------------------
# Baseline: the layer must agree with the authoritative validator
# ---------------------------------------------------------------------------


def test_minimal_record_is_clean(minimal):
    report = diagnose(minimal, ROOT)
    assert report.ok
    assert report.diagnostics == ()
    assert report.missing() == ()
    assert report.invalid() == ()


@pytest.mark.parametrize(
    "path", sorted(OFFICIAL.glob("*.json")), ids=lambda p: p.name
)
def test_committed_official_examples_produce_no_diagnostics(path):
    record = json.loads(path.read_text(encoding="utf-8"))
    report = diagnose(record, ROOT)
    assert report.ok, [(d.pointer, d.message) for d in report.diagnostics]


def test_diagnostics_agree_with_official_validator_on_pass_fail(xanes):
    """`ok` must never disagree with the existing truth-path validator."""
    broken = copy.deepcopy(xanes)
    broken["record_id"] = "not-a-ulid"
    for record, expected_ok in [(xanes, True), (broken, False)]:
        assert diagnose(record, ROOT).ok is expected_ok
        assert official.validate_official(record, ROOT).ok is expected_ok


def test_report_carries_schema_version_and_fingerprint(minimal):
    report = diagnose(minimal, ROOT)
    assert report.schema_version == EXPECTED_VERSION
    assert report.schema_version == "1.05"
    assert report.schema_fingerprint == schema_fingerprint(ROOT)


# ---------------------------------------------------------------------------
# Structural: the full-schema invariant
# ---------------------------------------------------------------------------


def module_source() -> str:
    return MODULE_FILE.read_text(encoding="utf-8")


def module_code_only() -> str:
    """`diagnostics.py` with every comment and string literal removed.

    Substring assertions must not be satisfied (or defeated) by prose: the
    module's own docstring names `json.load` and `Draft202012Validator` while
    explaining that it uses neither.
    """
    kept = []
    for token in tokenize.generate_tokens(io.StringIO(module_source()).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept)


def module_code_and_literals() -> str:
    """`diagnostics.py` with comments and DOCSTRINGS removed — literals kept.

    `module_code_only` joins tokens with spaces and drops every STRING token,
    which makes three kinds of assertion unfalsifiable: `json.loads` tokenizes
    to `json . loads`, a hardcoded path is a STRING, and a hand-maintained
    label catalog's keys are STRINGs. An independent review demonstrated all
    three passing against a module that contained exactly the forbidden
    construct. Anything checking for a literal must use THIS view.

    Docstrings are still removed, because the module legitimately names
    `json.load` and `Draft202012Validator` in prose while explaining that it
    uses neither.
    """
    tree = ast.parse(module_source())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0].value.value = ""
    return ast.unparse(tree)


def module_string_literals() -> list[str]:
    """Every string literal in `diagnostics.py` except docstrings."""
    tree = ast.parse(module_source())
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]


def module_ast() -> ast.Module:
    return ast.parse(module_source())


def test_diagnose_signature_admits_no_schema_or_validator_override():
    import inspect

    params = list(inspect.signature(diagnose).parameters)
    assert params == ["record", "root"], params
    kinds = {
        name: p.kind
        for name, p in inspect.signature(diagnose).parameters.items()
    }
    # No *args/**kwargs back door either.
    assert all(
        kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        )
        for kind in kinds.values()
    ), kinds


def test_module_imports_only_stdlib_and_official():
    tree = module_ast()
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                absolute.add((node.module or "").split(".")[0])
            else:
                relative.add((node.level, node.module))
    assert absolute == {
        "__future__",
        "hashlib",
        "dataclasses",
        "pathlib",
        "typing",
    }, absolute
    assert relative == {(1, "official")}, relative
    assert "jsonschema" not in absolute
    assert "json" not in absolute


def test_module_never_names_json_or_jsonschema():
    """No `json.loads`, no `jsonschema` anything — not even indirectly."""
    forbidden = {"json", "jsonschema", "Draft202012Validator"}
    used = {
        node.id for node in ast.walk(module_ast()) if isinstance(node, ast.Name)
    }
    assert not (used & forbidden), used & forbidden
    code = module_code_only()
    assert "Draft202012Validator" not in code
    # These two MUST use the literals-preserving view. Under `module_code_only`
    # they were unfalsifiable: `json.loads` tokenizes to `json . loads`, and a
    # hardcoded schema path is a STRING token that the helper strips. An
    # independent review passed both against a module containing exactly the
    # forbidden construct.
    literal_code = module_code_and_literals()
    assert "json.load" not in literal_code
    assert "isaac_record_v1" not in literal_code
    assert not any("isaac_record_v1" in s for s in module_string_literals())


def test_the_structural_assertions_are_falsifiable():
    """Guard the guards: prove the code view can SEE a forbidden construct.

    Every assertion above is a substring check over a derived view of the
    source. If that view silently stops containing what it searches for, the
    assertions keep passing while enforcing nothing — which is precisely the
    defect an independent review found here. This test pins the property that
    makes them meaningful.
    """
    injected = (
        '"""Docstring naming json.load and isaac_record_v1 harmlessly."""\n'
        "import json\n"
        '_PATH = "schema/isaac_record_v1.json"\n'
        '_CATALOG = {"record_id": "Record Identifier"}\n'
        "def f(p):\n"
        "    return json.loads(open(p).read())\n"
    )
    tree = ast.parse(injected)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.FunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0].value.value = ""
    view = ast.unparse(tree)
    # The literals-preserving view SEES all three; this is what makes the real
    # assertions capable of failing.
    assert "json.load" in view
    assert "isaac_record_v1" in view
    assert "record_id" in view
    # ...and the docstring was still removed, so prose cannot trip them.
    assert "harmlessly" not in view


def test_module_never_derives_a_narrowed_validator():
    """Close the bypass an independent review proved: `.evolve(schema=trimmed)`.

    `Validator.evolve` / `.descend` return a NEW validator over a caller-supplied
    schema. Neither needs a new import, a file read, nor any identifier
    containing "Validator", so every other structural test here passed while two
    `required` failures silently vanished and the report still advertised the
    full-schema fingerprint. Forbid the attribute names outright.
    """
    forbidden = {"evolve", "descend", "iter_errors_from", "subschema"}
    used = {
        node.attr for node in ast.walk(module_ast()) if isinstance(node, ast.Attribute)
    }
    assert not (used & forbidden), used & forbidden


def test_diagnose_binds_its_validator_only_from_the_official_loader():
    """Every `validator` binding inside `diagnose` must be the loader call.

    This is what makes "the full schema is always used" checkable rather than
    aspirational: a module-global `_VALIDATOR_OVERRIDE or load_official_validator(root)`
    passed all prior structural tests.
    """
    fn = next(
        n
        for n in ast.walk(module_ast())
        if isinstance(n, ast.FunctionDef) and n.name == "diagnose"
    )
    bindings = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "validator" for t in node.targets
        )
    ]
    assert bindings, "diagnose must bind a `validator` local"
    for node in bindings:
        call = node.value
        assert isinstance(call, ast.Call), ast.dump(call)
        func = call.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        assert name == "load_official_validator", (
            f"validator bound from {name!r}; the only permitted source is "
            "official.load_official_validator"
        )
        # no `or`/`if` fallback smuggling an override in
        assert not isinstance(call, ast.BoolOp)


def test_module_has_no_validator_override_global():
    """No module-level name may hold a validator to be consulted first."""
    suspicious = {"_VALIDATOR_OVERRIDE", "_VALIDATOR", "VALIDATOR", "_SCHEMA", "SCHEMA"}
    assigned = {
        t.id
        for node in module_ast().body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert not (assigned & suspicious), assigned & suspicious


def test_module_constructs_no_validator():
    """Only `official` may build a validator; there must be no second one."""
    constructed = []
    for node in ast.walk(module_ast()):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None) or ""
            if "Validator" in name:
                constructed.append(name)
    assert constructed == [], constructed


def test_module_reads_the_schema_only_as_whole_raw_bytes():
    """The single schema-file read is `read_bytes()` of the entire file.

    A partial read (`read_text` + slicing, `open`, a streaming parse) is what a
    subset-schema bug would look like, so none of those may appear at all.
    """
    code = module_code_only()
    assert code.count("read_bytes") == 1, code.count("read_bytes")
    for forbidden in ("read_text", "readline", "readlines", "seek"):
        assert forbidden not in code, forbidden
    attribute_calls = collections.Counter(
        node.func.attr
        for node in ast.walk(module_ast())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    )
    assert attribute_calls["read_bytes"] == 1
    assert attribute_calls["open"] == 0
    assert attribute_calls["read"] == 0


def test_module_resolves_the_schema_path_only_through_official():
    """No literal schema path: the location comes from `official.schema_path`."""
    called = {
        node.func.id
        for node in ast.walk(module_ast())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "schema_path" in called
    assert diagnostics_module.schema_path is official.schema_path


def test_module_validator_getter_is_the_official_one():
    assert (
        diagnostics_module.load_official_validator
        is official.load_official_validator
    )


def test_diagnose_obtains_its_validator_from_load_official_validator(
    monkeypatch, minimal
):
    """Behavioural half of the invariant: the call really is delegated."""
    calls = []
    real = official.load_official_validator

    def spy(root):
        calls.append(root)
        return real(root)

    monkeypatch.setattr(diagnostics_module, "load_official_validator", spy)
    diagnose(minimal, ROOT)
    assert calls == [ROOT]


def test_diagnose_uses_the_complete_schema_not_a_root_subset(minimal):
    """A deeply nested rule must still fire.

    A module that had quietly kept only the schema's top level would pass every
    root-level test. This asserts a failure ten levels down.
    """
    record = copy.deepcopy(minimal)
    record["descriptors"] = {
        "outputs": [
            {
                "label": "fake-output",
                "generated_utc": "2026-01-01T00:00:00Z",
                "generated_by": {"agent": "synthetic-fixture"},
                "descriptors": [
                    {
                        "name": "fake_descriptor",
                        "kind": "absolute",
                        "source": "manual",
                        "value": 1.0,
                        "uncertainty": {"sigma": None, "unit": "eV"},
                        "relative_to": 12345,
                    }
                ],
            }
        ]
    }
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == (
        "/descriptors/outputs/0/descriptors/0/relative_to"
    )


def test_frozen_public_api_shape():
    assert MISSING == "missing"
    assert INVALID == "invalid"
    assert [f.name for f in Diagnostic.__dataclass_fields__.values()] == [
        "pointer",
        "schema_pointer",
        "rule_family",
        "kind",
        "label",
        "message",
        "conditional",
        "blocking",
    ]
    assert [
        f.name for f in DiagnosticReport.__dataclass_fields__.values()
    ] == ["diagnostics", "schema_version", "schema_fingerprint"]
    assert Diagnostic.__dataclass_params__.frozen
    assert DiagnosticReport.__dataclass_params__.frozen
    assert isinstance(DiagnosticReport.ok, property)


# ---------------------------------------------------------------------------
# Schema fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_is_sha256_of_raw_bytes_and_stable():
    expected = hashlib.sha256(SCHEMA_FILE.read_bytes()).hexdigest()
    first = schema_fingerprint(ROOT)
    second = schema_fingerprint(ROOT)
    assert first == second == expected
    assert first == first.lower()
    assert len(first) == 64
    assert all(c in "0123456789abcdef" for c in first)


def test_fingerprint_changes_when_the_schema_bytes_change(tmp_path):
    """Verified on a throwaway copy — the real schema is never touched."""
    fake_root = tmp_path / "fake-root"
    (fake_root / "schema").mkdir(parents=True)
    target = fake_root / "schema" / "isaac_record_v1.json"
    shutil.copyfile(SCHEMA_FILE, target)

    assert schema_fingerprint(fake_root) == schema_fingerprint(ROOT)

    # A whitespace-only edit changes no parsed meaning but changes the bytes.
    target.write_bytes(target.read_bytes() + b"\n")
    assert schema_fingerprint(fake_root) != schema_fingerprint(ROOT)

    assert SCHEMA_FILE.read_bytes() == (fake_root / "schema" / "isaac_record_v1.json").read_bytes()[:-1]


# ---------------------------------------------------------------------------
# Problem 1: `required` errors need a pointer to the missing field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ROOT_REQUIRED)
def test_each_root_required_field_gets_its_own_pointer(minimal, field):
    record = copy.deepcopy(minimal)
    del record[field]
    report = diagnose(record, ROOT)
    diagnostic = at(report, f"/{field}", "required")
    assert diagnostic.kind == MISSING
    assert diagnostic.conditional is False
    assert diagnostic.blocking is True
    assert diagnostic.schema_pointer == "/required"
    assert diagnostic.message == f"'{field}' is a required property"


def test_all_root_required_fields_are_reported_separately():
    """The failure the old renderer hid: five distinct fields, one path `$`."""
    report = diagnose({"isaac_record_version": "1.05"}, ROOT)
    missing = report.missing()
    assert [d.pointer for d in missing if not d.conditional] == [
        "/record_domain",
        "/record_id",
        "/record_type",
        "/source_type",
        "/timestamps",
    ]
    assert len({d.pointer for d in missing}) == len(missing)
    # For contrast: the existing renderer collapses them all onto `$`.
    legacy = official.validate_official({"isaac_record_version": "1.05"}, ROOT)
    assert {e.path for e in legacy.errors} == {"$"}


def test_dropping_record_type_also_trips_the_evidence_conditional(minimal):
    """Honest pinning of real schema behaviour, not a bug in this layer.

    The `record_type == evidence` guard is `if: {properties: {...}}` with no
    `required`, so an *absent* `record_type` satisfies it vacuously and
    `descriptors` becomes required too.
    """
    record = copy.deepcopy(minimal)
    del record["record_type"]
    report = diagnose(record, ROOT)
    assert pointers(report) == ["/descriptors", "/record_type"]
    assert at(report, "/record_type", "required").conditional is False
    assert at(report, "/descriptors", "required").conditional is True


def test_nested_required_field_pointer(minimal):
    record = copy.deepcopy(minimal)
    record["timestamps"] = {}
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == "/timestamps/created_utc"
    assert diagnostic.schema_pointer == "/properties/timestamps/required"
    assert diagnostic.kind == MISSING
    assert diagnostic.label == "Timestamps → Created Utc"


def test_required_field_inside_array_item_has_index_aware_pointer(xanes):
    record = copy.deepcopy(xanes)
    del record["measurement"]["series"][0]["channels"][0]["unit"]
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == "/measurement/series/0/channels/0/unit"
    assert diagnostic.kind == MISSING
    assert diagnostic.conditional is False
    assert diagnostic.label == (
        "Measurement → Series → item 0 → Channels → item 0 → Unit"
    )


def test_required_pointer_for_a_deeper_array_index(xanes):
    """Index 1, not 0 — proves the index is read, not assumed."""
    record = copy.deepcopy(xanes)
    channels = record["measurement"]["series"][0]["channels"]
    assert len(channels) >= 2, "fixture must have at least two channels"
    del channels[1]["role"]
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == "/measurement/series/0/channels/1/role"


# ---- the self-check ----


def _fake_required_error(message, validator_value, instance):
    return SimpleNamespace(
        message=message, validator_value=validator_value, instance=instance
    )


def test_required_name_resolution_self_check_rejects_a_changed_message_format():
    """If jsonschema's message format ever changes, fail loudly, never guess."""
    err = _fake_required_error(
        "record_id is missing", ["record_id"], {}
    )  # no quotes: format changed
    with pytest.raises(DiagnosticsIntegrityError, match="message format changed"):
        diagnostics_module._missing_required_name(err)


def test_required_name_resolution_self_check_rejects_a_name_not_in_the_schema():
    err = _fake_required_error(
        "'invented_field' is a required property", ["record_id"], {}
    )
    with pytest.raises(DiagnosticsIntegrityError, match="could not resolve"):
        diagnostics_module._missing_required_name(err)


def test_required_name_resolution_self_check_rejects_a_name_already_present():
    err = _fake_required_error(
        "'record_id' is a required property",
        ["record_id"],
        {"record_id": FAKE_ULID},
    )
    with pytest.raises(DiagnosticsIntegrityError, match="could not resolve"):
        diagnostics_module._missing_required_name(err)


def test_required_name_resolution_self_check_rejects_a_non_object_instance():
    err = _fake_required_error(
        "'record_id' is a required property", ["record_id"], ["not", "an", "object"]
    )
    with pytest.raises(DiagnosticsIntegrityError, match="non-object instance"):
        diagnostics_module._missing_required_name(err)


def test_required_name_resolution_self_check_rejects_a_non_list_required():
    err = _fake_required_error(
        "'record_id' is a required property", "record_id", {}
    )
    with pytest.raises(DiagnosticsIntegrityError, match="non-list validator_value"):
        diagnostics_module._missing_required_name(err)


def test_required_name_resolution_accepts_a_real_error():
    err = _fake_required_error(
        "'record_id' is a required property", ROOT_REQUIRED, {}
    )
    assert diagnostics_module._missing_required_name(err) == "record_id"


def test_diagnose_propagates_the_integrity_error(monkeypatch, minimal):
    """A resolution failure must abort the whole report, not degrade it."""

    def boom(err):
        raise DiagnosticsIntegrityError("simulated format drift")

    monkeypatch.setattr(diagnostics_module, "_missing_required_name", boom)
    record = copy.deepcopy(minimal)
    del record["record_id"]
    with pytest.raises(DiagnosticsIntegrityError, match="simulated format drift"):
        diagnose(record, ROOT)


# ---------------------------------------------------------------------------
# Problem 2: conditional vs plain requirements
# ---------------------------------------------------------------------------


def test_evidence_conditional_does_not_fire_when_the_condition_is_false(minimal):
    record = copy.deepcopy(minimal)
    record["record_type"] = "synthesis"
    assert "descriptors" not in record
    assert diagnose(record, ROOT).ok


def test_evidence_conditional_does_not_fire_when_descriptors_are_present(xanes):
    assert xanes["record_type"] == "evidence"
    assert "descriptors" in xanes
    assert diagnose(xanes, ROOT).ok


def test_evidence_conditional_fires_when_descriptors_are_absent(xanes):
    record = copy.deepcopy(xanes)
    del record["descriptors"]
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == "/descriptors"
    assert diagnostic.kind == MISSING
    assert diagnostic.rule_family == "required"
    assert diagnostic.conditional is True
    assert diagnostic.schema_pointer == "/allOf/0/then/required"
    assert diagnostic.label == "Descriptors"


def test_plain_and_conditional_requirements_differ_only_in_schema_pointer(
    minimal, xanes
):
    plain = copy.deepcopy(minimal)
    del plain["timestamps"]
    plain_diagnostic = only(diagnose(plain, ROOT))

    conditional = copy.deepcopy(xanes)
    del conditional["descriptors"]
    conditional_diagnostic = only(diagnose(conditional, ROOT))

    assert plain_diagnostic.rule_family == conditional_diagnostic.rule_family
    assert plain_diagnostic.kind == conditional_diagnostic.kind
    assert plain_diagnostic.schema_pointer == "/required"
    assert conditional_diagnostic.schema_pointer == "/allOf/0/then/required"
    assert plain_diagnostic.conditional is False
    assert conditional_diagnostic.conditional is True


def test_performance_galvanostatic_requires_current_setpoint():
    """The rule already exercised by `test_official.py`, now with a pointer."""
    record = {
        "isaac_record_version": "1.05",
        "record_id": FAKE_ULID,
        "record_type": "intent",
        "record_domain": "performance",
        "source_type": "laboratory",
        "timestamps": {"created_utc": "2026-01-01T00:00:00Z"},
        "context": {
            "environment": "operando",
            "temperature_K": 298,
            "electrochemistry": {"control_mode": "galvanostatic"},
        },
    }
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == (
        "/context/electrochemistry/current_setpoint_mA_cm2"
    )
    assert diagnostic.kind == MISSING
    assert diagnostic.conditional is True
    assert diagnostic.schema_pointer == (
        "/allOf/2/then/properties/context/properties/electrochemistry/required"
    )
    # Unit casing survives label derivation.
    assert diagnostic.label == (
        "Context → Electrochemistry → Current Setpoint mA cm2"
    )

    satisfied = copy.deepcopy(record)
    satisfied["context"]["electrochemistry"]["current_setpoint_mA_cm2"] = 10.0
    assert diagnose(satisfied, ROOT).ok


def test_performance_domain_requires_control_mode():
    """The second root conditional (`allOf/1`), distinct from the third."""
    record = {
        "isaac_record_version": "1.05",
        "record_id": FAKE_ULID,
        "record_type": "intent",
        "record_domain": "performance",
        "source_type": "laboratory",
        "timestamps": {"created_utc": "2026-01-01T00:00:00Z"},
        "context": {
            "environment": "operando",
            "temperature_K": 298,
            "electrochemistry": {},
        },
    }
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.pointer == "/context/electrochemistry/control_mode"
    assert diagnostic.conditional is True
    assert diagnostic.schema_pointer == (
        "/allOf/1/then/properties/context/properties/electrochemistry/required"
    )


def test_allof_alone_is_not_conditional():
    """`allOf` is unconditional composition; only if/then/else are conditions."""
    assert diagnostics_module._is_conditional(["allOf", 0, "required"]) is False
    assert diagnostics_module._is_conditional(["required"]) is False
    assert (
        diagnostics_module._is_conditional(
            ["properties", "timestamps", "required"]
        )
        is False
    )
    assert diagnostics_module._is_conditional(["allOf", 0, "then", "required"])
    assert diagnostics_module._is_conditional(["if", "properties"])
    assert diagnostics_module._is_conditional(["else", "required"])


def test_a_field_literally_named_then_is_not_mistaken_for_a_conditional():
    """`then` after `properties` is a field name, not a keyword."""
    assert (
        diagnostics_module._is_conditional(
            ["properties", "then", "properties", "if", "type"]
        )
        is False
    )
    assert (
        diagnostics_module._is_conditional(
            ["properties", "then", "allOf", 0, "then", "required"]
        )
        is True
    )


def test_conditional_flag_matches_the_schema_pointer_for_every_diagnostic(xanes):
    """Cross-check the flag against its own definition, over a broad sweep.

    The cross-check deliberately uses `_is_conditional`'s KEYWORD-POSITION rule,
    not the naive `any(s in ("if","then","else"))`. An earlier version used the
    naive form, which asserts the opposite of the refinement the function
    implements; it agreed only because no v1.05 property is named after a
    name-map keyword (asserted below), so it would have contradicted the
    intended rule the moment the refinement mattered.
    """
    seen_true = seen_false = 0
    naive_agrees = True
    for report in _sweep_reports(xanes):
        for d in report.diagnostics:
            segments = [s for s in d.schema_pointer.split("/")[1:]]
            traverses = diagnostics_module._is_conditional(segments)
            assert d.conditional == traverses, d
            naive = any(s in ("if", "then", "else") for s in segments)
            naive_agrees = naive_agrees and (naive == traverses)
            seen_true += bool(traverses)
            seen_false += not traverses
    assert seen_true > 0 and seen_false > 0
    # Pin WHY the naive rule happens to agree today, so the day it stops
    # agreeing is a visible schema event rather than a silent behaviour change.
    assert naive_agrees, "a schema property now collides with a name-map keyword"


def test_a_property_named_like_a_keyword_does_not_defeat_conditional_detection():
    """Regression for the mirror-image bug an independent review found.

    `previous = segment` in the skip branch meant a property literally NAMED a
    name-map keyword caused the NEXT segment — a genuine `then` — to be skipped
    too, silently downgrading a conditional requirement to a plain one.
    Unreachable in v1.05, but a schema refresh could introduce such a name.
    """
    assert diagnostics_module._is_conditional(["properties", "properties", "then", "required"]) is True
    assert diagnostics_module._is_conditional(["properties", "definitions", "then", "required"]) is True
    assert diagnostics_module._is_conditional(["properties", "$defs", "then", "required"]) is True
    # ...while a field genuinely NAMED `then` still must not count.
    assert diagnostics_module._is_conditional(["properties", "then", "required"]) is False


# ---------------------------------------------------------------------------
# Problem 3: total, numeric, stable ordering
# ---------------------------------------------------------------------------


def test_array_indices_sort_numerically_not_lexically(minimal):
    record = copy.deepcopy(minimal)
    record["links"] = [
        {"rel": "follows", "target": FAKE_ULID_2} for _ in range(11)
    ]
    report = diagnose(record, ROOT)
    assert len(report.diagnostics) == 11
    assert pointers(report) == [f"/links/{i}/basis" for i in range(11)]
    assert pointers(report).index("/links/2/basis") < pointers(report).index(
        "/links/10/basis"
    )

    # The pre-existing renderer gets this wrong; that is why this layer exists.
    legacy = [e.path for e in official.validate_official(record, ROOT).errors]
    assert legacy.index("links.10") < legacy.index("links.2")


def test_ordering_is_numeric_at_every_array_depth(xanes):
    record = copy.deepcopy(xanes)
    template = copy.deepcopy(record["descriptors"]["outputs"][0]["descriptors"][0])
    template.pop("uncertainty")
    record["descriptors"]["outputs"][0]["descriptors"] = [
        copy.deepcopy(template) for _ in range(12)
    ]
    report = diagnose(record, ROOT)
    assert pointers(report) == [
        f"/descriptors/outputs/0/descriptors/{i}/uncertainty" for i in range(12)
    ]


def test_ordering_is_a_total_order_over_mixed_paths_and_families(xanes):
    record = copy.deepcopy(xanes)
    record["record_id"] = ""
    record["system"]["technique"] = "telepathy"
    record["isaac_record_version"] = "9.99"
    record["tags"] = ["dup", "dup"]
    del record["timestamps"]["created_utc"]
    report = diagnose(record, ROOT)
    keys = [
        (d.pointer, d.rule_family, d.message, d.conditional, d.schema_pointer)
        for d in report.diagnostics
    ]
    assert len(keys) == len(set(keys)), "order key must be unique per diagnostic"
    assert pointers(report) == [
        "/isaac_record_version",
        "/record_id",
        "/system/technique",
        "/tags",
        "/timestamps/created_utc",
    ]


# ---------------------------------------------------------------------------
# Problem 4: missing vs invalid, and the null/empty matrix
# ---------------------------------------------------------------------------


def test_kind_is_missing_exactly_when_the_family_is_required(xanes):
    families = set()
    for report in _sweep_reports(xanes):
        for d in report.diagnostics:
            assert d.kind == (MISSING if d.rule_family == "required" else INVALID)
            assert d.kind in (MISSING, INVALID)
            families.add(d.rule_family)
    assert "required" in families
    assert families - {"required"}, "sweep must also produce INVALID families"


def test_missing_and_invalid_partition_the_report(xanes):
    record = copy.deepcopy(xanes)
    del record["timestamps"]["created_utc"]
    record["record_id"] = None
    report = diagnose(record, ROOT)
    assert set(report.missing()) | set(report.invalid()) == set(
        report.diagnostics
    )
    assert not set(report.missing()) & set(report.invalid())
    # A real partition assertion. The previous form,
    # `assert report.missing() + report.invalid() or report.ok`, was
    # unconditionally true: a non-empty tuple is truthy and an empty one implies
    # `ok`, so it could never fail.
    assert len(report.missing()) + len(report.invalid()) == len(report.diagnostics)
    assert len(report.diagnostics) > 0  # this record really does fail
    assert all(d.kind == MISSING for d in report.missing())
    assert all(d.kind == INVALID for d in report.invalid())
    assert [d.pointer for d in report.missing()] == ["/timestamps/created_utc"]
    assert [d.pointer for d in report.invalid()] == ["/record_id"]


def test_absent_field_is_missing(minimal):
    record = copy.deepcopy(minimal)
    del record["record_id"]
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == MISSING
    assert diagnostic.rule_family == "required"
    assert diagnostic.pointer == "/record_id"


def test_null_field_is_invalid_via_type_not_missing(minimal):
    record = copy.deepcopy(minimal)
    record["record_id"] = None
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == INVALID
    assert diagnostic.rule_family == "type"
    assert diagnostic.pointer == "/record_id"
    assert diagnostic.message == "None is not of type 'string'"


def test_empty_string_is_invalid_where_a_pattern_constrains_it(minimal):
    record = copy.deepcopy(minimal)
    record["record_id"] = ""
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == INVALID
    assert diagnostic.rule_family == "pattern"


def test_empty_string_is_invalid_where_an_enum_constrains_it(minimal):
    record = copy.deepcopy(minimal)
    record["record_domain"] = ""
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == INVALID
    assert diagnostic.rule_family == "enum"


def test_empty_string_yields_no_diagnostic_where_the_schema_does_not_constrain_it(
    xanes,
):
    """`sample.sample_form` is `{"type": "string"}` with no further constraint.

    The honest assertion is that nothing is reported. The schema does not forbid
    an empty `sample_form`, and this layer must not invent a rule that would.
    """
    assert (
        SCHEMA["properties"]["sample"]["properties"]["sample_form"]
        == {"type": "string"}
    )
    record = copy.deepcopy(xanes)
    record["sample"]["sample_form"] = ""
    assert diagnose(record, ROOT).ok


def test_empty_array_is_invalid_where_min_items_constrains_it(xanes):
    record = copy.deepcopy(xanes)
    descriptor = record["descriptors"]["outputs"][0]["descriptors"][0]
    descriptor["uncertainty"] = {"bounds": []}
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == INVALID
    assert diagnostic.rule_family == "minItems"
    assert diagnostic.pointer == (
        "/descriptors/outputs/0/descriptors/0/uncertainty/bounds"
    )


def test_empty_array_yields_no_diagnostic_where_no_min_items_exists(xanes):
    """`measurement.series`, `descriptors.outputs` and `tags` have no `minItems`.

    An empty required array is therefore schema-valid. Reporting it would be
    this layer inventing a rule the authoritative schema does not state.
    """
    series_schema = SCHEMA["properties"]["measurement"]["properties"]["series"]
    outputs_schema = SCHEMA["properties"]["descriptors"]["properties"]["outputs"]
    assert "minItems" not in series_schema
    assert "minItems" not in outputs_schema
    assert "minItems" not in SCHEMA["properties"]["tags"]

    record = copy.deepcopy(xanes)
    record["measurement"]["series"] = []
    record["descriptors"]["outputs"] = []
    record["tags"] = []
    assert diagnose(record, ROOT).ok


def test_empty_object_is_missing_where_the_object_has_required_fields(minimal):
    record = copy.deepcopy(minimal)
    record["timestamps"] = {}
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.kind == MISSING
    assert diagnostic.pointer == "/timestamps/created_utc"


def test_empty_object_yields_no_diagnostic_where_the_object_is_open(xanes):
    """`sample.composition` is open by design — `{}` is valid."""
    assert "required" not in SCHEMA["properties"]["sample"]["properties"]["composition"]
    record = copy.deepcopy(xanes)
    record["sample"]["composition"] = {}
    record["system"]["configuration"] = {}
    assert diagnose(record, ROOT).ok


# ---------------------------------------------------------------------------
# Rule-family coverage: one test per family the schema actually contains
# ---------------------------------------------------------------------------

SCHEMA = json.loads(SCHEMA_FILE.read_bytes())


def test_family_required(minimal):
    record = copy.deepcopy(minimal)
    del record["source_type"]
    assert only(diagnose(record, ROOT)).rule_family == "required"


def test_family_type(minimal):
    record = copy.deepcopy(minimal)
    record["timestamps"] = "2026-01-01T00:00:00Z"
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "type"
    assert diagnostic.pointer == "/timestamps"


def test_family_enum(xanes):
    record = copy.deepcopy(xanes)
    record["system"]["technique"] = "telepathy"
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "enum"
    assert diagnostic.pointer == "/system/technique"
    assert diagnostic.kind == INVALID
    assert diagnostic.label == "System → Technique"


def test_family_const(minimal):
    record = copy.deepcopy(minimal)
    record["isaac_record_version"] = "9.99"
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "const"
    assert diagnostic.pointer == "/isaac_record_version"
    assert diagnostic.schema_pointer == "/properties/isaac_record_version/const"


def test_family_pattern_record_id_must_be_a_ulid(minimal):
    record = copy.deepcopy(minimal)
    record["record_id"] = "isaac-2026-cuo-xas-0001"
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "pattern"
    assert diagnostic.pointer == "/record_id"
    assert diagnostic.schema_pointer == "/properties/record_id/pattern"
    assert "^[0-9A-Z]{26}$" in diagnostic.message


def test_family_additional_properties(xanes):
    record = copy.deepcopy(xanes)
    record["literature"] = {"doi": "10.0000/fake-synthetic-doi"}
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "additionalProperties"
    assert diagnostic.pointer == ""
    assert diagnostic.schema_pointer == "/additionalProperties"
    assert diagnostic.kind == INVALID
    assert diagnostic.label == "Record"


def test_family_min_items(xanes):
    record = copy.deepcopy(xanes)
    record["descriptors"]["outputs"][0]["descriptors"][0]["uncertainty"] = {
        "bounds": [0.1]
    }
    assert only(diagnose(record, ROOT)).rule_family == "minItems"


def test_family_max_items(xanes):
    record = copy.deepcopy(xanes)
    record["descriptors"]["outputs"][0]["descriptors"][0]["uncertainty"] = {
        "bounds": [0.1, 0.2, 0.3]
    }
    assert only(diagnose(record, ROOT)).rule_family == "maxItems"


def test_family_min_length(minimal):
    record = copy.deepcopy(minimal)
    record["tags"] = [""]
    families = {d.rule_family for d in diagnose(record, ROOT).diagnostics}
    assert "minLength" in families


def test_family_max_length(minimal):
    record = copy.deepcopy(minimal)
    record["tags"] = ["x" * 65]
    assert only(diagnose(record, ROOT)).rule_family == "maxLength"


def test_family_unique_items(minimal):
    record = copy.deepcopy(minimal)
    record["tags"] = ["synthetic-fixture", "synthetic-fixture"]
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "uniqueItems"
    assert diagnostic.pointer == "/tags"


def test_family_one_of_is_the_schemas_only_one_of(xanes):
    """The schema contains exactly one `oneOf`: `descriptors[].relative_to`."""
    assert _count_keywords()["oneOf"] == 1
    record = copy.deepcopy(xanes)
    record["descriptors"]["outputs"][0]["descriptors"][0]["relative_to"] = 12345
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "oneOf"
    assert diagnostic.kind == INVALID
    assert diagnostic.pointer == (
        "/descriptors/outputs/0/descriptors/0/relative_to"
    )
    assert diagnostic.schema_pointer == (
        "/properties/descriptors/properties/outputs/items"
        "/properties/descriptors/items/properties/relative_to/oneOf"
    )
    # Both declared branches are genuinely accepted.
    for accepted in ["fake_reference_label", {"reference_label": "fake"}]:
        ok_record = copy.deepcopy(xanes)
        ok_record["descriptors"]["outputs"][0]["descriptors"][0][
            "relative_to"
        ] = accepted
        assert diagnose(ok_record, ROOT).ok


def test_family_not_is_the_schemas_only_not(xanes):
    """The schema contains exactly one `not`: a descriptor value may not be null."""
    assert _count_keywords()["not"] == 1
    record = copy.deepcopy(xanes)
    record["descriptors"]["outputs"][0]["descriptors"][0]["value"] = None
    diagnostic = only(diagnose(record, ROOT))
    assert diagnostic.rule_family == "not"
    assert diagnostic.kind == INVALID
    assert diagnostic.pointer == "/descriptors/outputs/0/descriptors/0/value"
    assert diagnostic.schema_pointer == (
        "/properties/descriptors/properties/outputs/items"
        "/properties/descriptors/items/properties/value/not"
    )
    assert diagnostic.label == (
        "Descriptors → Outputs → item 0 → Descriptors → item 0 → Value"
    )


def test_format_is_present_in_the_schema_but_not_enforced_by_this_validator():
    """Honest negative: `format` cannot be covered, and it is not our doing.

    `official.load_official_validator` builds `Draft202012Validator(schema)`
    without a `format_checker`, so under JSON Schema 2020-12 `format` is an
    annotation only. Six `format: date-time` declarations exist; none of them can
    produce a diagnostic. This layer must not add enforcement the truth path does
    not have.
    """
    assert _count_keywords()["format"] == 6
    record = minimal_valid_record()
    record["timestamps"]["created_utc"] = "definitely-not-a-timestamp"
    assert diagnose(record, ROOT).ok
    assert official.validate_official(record, ROOT).ok
    assert official.load_official_validator(ROOT).format_checker is None


# ---------------------------------------------------------------------------
# Determinism, key-order independence, de-duplication
# ---------------------------------------------------------------------------


def _sweep_reports(xanes):
    """A broad sweep of mutations, used by the cross-cutting invariant tests."""
    reports = [diagnose({"isaac_record_version": "1.05"}, ROOT)]
    for key in list(xanes):
        for mutate in (
            lambda r, k: r.pop(k),
            lambda r, k: r.__setitem__(k, None),
            lambda r, k: r.__setitem__(k, ""),
            lambda r, k: r.__setitem__(k, {}),
            lambda r, k: r.__setitem__(k, []),
            lambda r, k: r.__setitem__(k, 0),
        ):
            record = copy.deepcopy(xanes)
            mutate(record, key)
            reports.append(diagnose(record, ROOT))
    extra = copy.deepcopy(xanes)
    extra["unknown_block"] = {"x": 1}
    extra["descriptors"]["outputs"][0]["descriptors"][0]["value"] = None
    extra["record_id"] = "not-a-ulid"
    reports.append(diagnose(extra, ROOT))
    return reports


def test_diagnose_is_deterministic_across_calls(xanes):
    record = copy.deepcopy(xanes)
    del record["timestamps"]["created_utc"]
    record["system"]["technique"] = "telepathy"
    record["tags"] = ["dup", "dup"]
    first = diagnose(record, ROOT)
    second = diagnose(record, ROOT)
    assert first == second
    assert first.diagnostics == second.diagnostics
    assert first.diagnostics is not second.diagnostics


def test_diagnose_is_independent_of_dict_insertion_order(xanes):
    broken = copy.deepcopy(xanes)
    del broken["timestamps"]["created_utc"]
    broken["record_id"] = "not-a-ulid"
    broken["zzz_unknown"] = 1
    broken["aaa_unknown"] = 2

    def reorder(value, reverse):
        if isinstance(value, dict):
            keys = sorted(value, reverse=reverse)
            return {k: reorder(value[k], reverse) for k in keys}
        if isinstance(value, list):
            return [reorder(v, reverse) for v in value]
        return value

    forward = diagnose(reorder(broken, False), ROOT)
    backward = diagnose(reorder(broken, True), ROOT)
    assert forward.diagnostics == backward.diagnostics
    assert not forward.ok


def test_no_duplicate_diagnostics_anywhere_in_the_sweep(xanes):
    for report in _sweep_reports(xanes):
        identities = [
            (d.pointer, d.rule_family, d.message) for d in report.diagnostics
        ]
        assert len(identities) == len(set(identities)), identities


def test_duplicate_conditional_branches_collapse_to_one_diagnostic(xanes):
    """A real duplicate the raw validator emits, and how it is resolved.

    With `rhe_basis` absent, both `potential_vs_RHE/allOf/0/if` and `allOf/1/if`
    pass vacuously, so both `then` clauses require `value_V` and `conversion` —
    four raw errors, two distinct facts.
    """
    record = copy.deepcopy(xanes)
    record.setdefault("context", {}).setdefault("electrochemistry", {})[
        "potential_vs_RHE"
    ] = {}
    raw = list(official.load_official_validator(ROOT).iter_errors(record))
    raw_identities = [
        (tuple(e.absolute_path), e.validator, e.message) for e in raw
    ]
    assert len(raw_identities) == 5
    assert len(set(raw_identities)) == 3, "the raw validator really does duplicate"

    report = diagnose(record, ROOT)
    assert pointers(report) == [
        "/context/electrochemistry/potential_vs_RHE/conversion",
        "/context/electrochemistry/potential_vs_RHE/rhe_basis",
        "/context/electrochemistry/potential_vs_RHE/value_V",
    ]
    # The retained conditional is the lowest schema pointer, deterministically.
    for pointer in ("conversion", "value_V"):
        diagnostic = at(
            report,
            f"/context/electrochemistry/potential_vs_RHE/{pointer}",
            "required",
        )
        assert diagnostic.conditional is True
        assert diagnostic.schema_pointer.endswith("/allOf/0/then/required")


def test_deduplication_prefers_the_unconditional_diagnostic():
    """Tie-break rule, stated directly on the sort key.

    If a field were ever required both plainly and conditionally at the same
    pointer, collapsing to the conditional one would understate the requirement.
    The order key puts `conditional=False` first so the plain one survives.

    SCOPE OF THIS EVIDENCE, honestly: this is a unit test over two hand-built
    `Diagnostic` objects, NOT an end-to-end proof through `diagnose`. It is
    unreachable with the v1.05 schema — an independent review searched for a
    field required both plainly and conditionally at one instance path and found
    only `record_domain`, which sits inside an `if` GUARD that jsonschema
    suppresses, so it can never emit a diagnostic. The tie-break is therefore
    purely defensive: correct, but exercised only here.
    """
    plain = Diagnostic(
        pointer="/x",
        schema_pointer="/zzz/required",
        rule_family="required",
        kind=MISSING,
        label="X",
        message="'x' is a required property",
        conditional=False,
        blocking=True,
    )
    conditional = Diagnostic(
        pointer="/x",
        schema_pointer="/aaa/then/required",
        rule_family="required",
        kind=MISSING,
        label="X",
        message="'x' is a required property",
        conditional=True,
        blocking=True,
    )
    keys = [
        diagnostics_module._sort_key((("x",), d)) for d in (conditional, plain)
    ]
    assert keys[1] < keys[0], "unconditional must sort first despite /zzz > /aaa"


def test_every_diagnostic_is_blocking(xanes):
    for report in _sweep_reports(xanes):
        assert all(d.blocking is True for d in report.diagnostics)


# ---------------------------------------------------------------------------
# JSON Pointer (RFC 6901)
# ---------------------------------------------------------------------------


def test_root_pointer_is_the_empty_string():
    assert json_pointer([]) == ""
    assert json_pointer(()) == ""


def test_rfc6901_escaping_order_is_tilde_then_slash():
    assert json_pointer(["a~b"]) == "/a~0b"
    assert json_pointer(["a/b"]) == "/a~1b"
    # The order matters: escaping `/` first would turn `a/b` into `a~1b` and then
    # the `~` pass would corrupt it into `a~01b`.
    assert json_pointer(["a/b~c"]) == "/a~1b~0c"
    # A literal `~1` must survive as `~01`, not be read back as `/`.
    assert json_pointer(["m~1n"]) == "/m~01n"
    assert json_pointer(["~"]) == "/~0"
    assert json_pointer(["/"]) == "/~1"
    assert json_pointer(["~/"]) == "/~0~1"


def test_pointer_renders_indices_and_empty_keys():
    assert json_pointer(["links", 0, "basis"]) == "/links/0/basis"
    assert json_pointer(["links", 10]) == "/links/10"
    assert json_pointer([""]) == "/"
    assert json_pointer(["a", "", "b"]) == "/a//b"


def test_pointer_rejects_boolean_segments():
    with pytest.raises(DiagnosticsIntegrityError):
        json_pointer([True])


def test_no_schema_property_name_needs_escaping():
    """Why no end-to-end escaping fixture exists, stated honestly.

    Escaping is unit-tested above rather than through `diagnose` because the
    authoritative schema declares no property name containing `~` or `/`, and
    `additionalProperties` errors report the *parent* pointer rather than the
    offending key. There is therefore no record that both validates through this
    schema and produces a pointer needing escaping. Asserting that fact is more
    honest than fabricating a case the schema cannot produce.
    """
    names = set()

    def collect(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("properties", "patternProperties", "$defs"):
                    if isinstance(value, dict):
                        for name, sub in value.items():
                            names.add(name)
                            collect(sub)
                elif key in ("allOf", "anyOf", "oneOf", "prefixItems"):
                    if isinstance(value, list):
                        for sub in value:
                            collect(sub)
                elif key in ("if", "then", "else", "not", "items", "additionalProperties"):
                    collect(value)

    collect(SCHEMA)
    # 219 = every distinct property name the vendored v1.05 schema declares,
    # counted by the walker directly above (properties/$defs keys, recursing
    # through items, combinators and if/then/else). It is pinned so a schema
    # refresh fails loudly here and forces this suite to be re-reviewed rather
    # than silently drifting. Independently corroborated: scripts/db_recon.py's
    # load_schema_vocabulary derives the same set by a different walk and also
    # reports 219.
    assert len(names) == 219
    offenders = [n for n in names if "~" in n or "/" in n]
    assert offenders == []


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_root_label_is_record_and_never_a_dollar_sign():
    assert diagnostics_module._derive_label([]) == "Record"


@pytest.mark.parametrize(
    "segments,expected",
    [
        (["record_id"], "Record Id"),
        (["isaac_record_version"], "Isaac Record Version"),
        (["timestamps", "created_utc"], "Timestamps → Created Utc"),
        (["context", "temperature_K"], "Context → Temperature K"),
        (
            ["context", "electrochemistry", "current_setpoint_mA_cm2"],
            "Context → Electrochemistry → Current Setpoint mA cm2",
        ),
        (
            ["context", "electrochemistry", "potential_vs_RHE", "value_V"],
            "Context → Electrochemistry → Potential Vs RHE → Value V",
        ),
        (["context", "electrochemistry", "pH_basis"], "Context → Electrochemistry → pH Basis"),
        (["links", 0, "basis"], "Links → item 0 → Basis"),
        (["links", 10, "basis"], "Links → item 10 → Basis"),
        (["assets", 2, "sha256"], "Assets → item 2 → sha256"),
    ],
)
def test_label_derivation_rules(segments, expected):
    assert diagnostics_module._derive_label(segments) == expected


def test_array_index_labels_are_zero_based_and_match_the_pointer(minimal):
    """Documented choice: `item <n>` uses the same 0-based index as the pointer.

    1-based would read more naturally but would invite a reader to distrust a
    correct pointer, which matters more in a no-guessing system.
    """
    record = copy.deepcopy(minimal)
    record["links"] = [
        {"rel": "follows", "target": FAKE_ULID_2} for _ in range(3)
    ]
    for diagnostic in diagnose(record, ROOT).diagnostics:
        index = diagnostic.pointer.split("/")[2]
        assert f"item {index}" in diagnostic.label


def test_labels_preserve_scientific_casing():
    """Blanket title-casing would corrupt units and symbols."""
    assert diagnostics_module._title_word("temperature") == "Temperature"
    assert diagnostics_module._title_word("K") == "K"
    assert diagnostics_module._title_word("mA") == "mA"
    assert diagnostics_module._title_word("pH") == "pH"
    assert diagnostics_module._title_word("RHE") == "RHE"
    assert diagnostics_module._title_word("cm2") == "cm2"
    assert diagnostics_module._title_word("sha256") == "sha256"


def test_label_is_never_empty_and_never_leaks_pointer_syntax(xanes):
    for report in _sweep_reports(xanes):
        for d in report.diagnostics:
            assert d.label
            assert d.label.strip() == d.label
            assert "$" not in d.label
            assert "/" not in d.label
            assert "~" not in d.label
            assert d.label != d.pointer


def test_label_is_derived_not_catalogued():
    """No hand-maintained field-name table may exist in the module.

    The schema declares exactly one `title` (its own root title) and no property
    titles, so there is nothing to reuse; labels must come from the pointer.
    A catalog would be a second, drifting copy of schema authority.
    """
    assert _count_keywords()["title"] == 1
    assert SCHEMA["title"] == "ISAAC AI-Ready Scientific Record v1.05"
    assert not any(
        "title" in prop
        for prop in SCHEMA["properties"].values()
        if isinstance(prop, dict)
    )
    # Literals-preserving view: a hand-maintained catalog's KEYS are string
    # literals, which `module_code_only` strips — an independent review injected
    # `_LABEL_CATALOG = {"record_id": ...}` and this assertion passed.
    literal_code = module_code_and_literals()
    literals = module_string_literals()
    for field_name in (
        "record_id",
        "isaac_record_version",
        "temperature_K",
        "current_setpoint_mA_cm2",
        "descriptors",
    ):
        assert field_name not in literal_code, (
            f"{field_name} appears in diagnostics.py code — labels must be "
            "derived from the pointer, not catalogued"
        )
        assert not any(field_name in s for s in literals), (
            f"{field_name} appears in a diagnostics.py string literal — a "
            "label catalog must not creep in"
        )
    # A field the schema has never heard of still gets a usable label.
    assert (
        diagnostics_module._derive_label(["never_declared_anywhere"])
        == "Never Declared Anywhere"
    )


def test_label_survives_a_pathological_segment():
    assert diagnostics_module._derive_label(["___"]) == "(unnamed field)"
    assert diagnostics_module._derive_label([""]) == "(unnamed field)"


# ---------------------------------------------------------------------------
# Rule-family coverage artifact
# ---------------------------------------------------------------------------


def _count_keywords() -> collections.Counter:
    """Count JSON Schema keywords in *keyword position* in the real schema.

    Keys nested under `properties` (etc.) are field names, not keywords: the
    schema declares fields literally named `type`, `value` and `method`, which a
    naive recursive key count inflates (`type` counts 300 naively, 297 as a
    keyword).
    """
    name_maps = {
        "properties",
        "patternProperties",
        "dependentSchemas",
        "dependentRequired",
        "$defs",
        "definitions",
    }
    subschema_lists = {"allOf", "anyOf", "oneOf", "prefixItems"}
    subschema_values = {
        "if",
        "then",
        "else",
        "not",
        "items",
        "contains",
        "additionalProperties",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
    counts: collections.Counter = collections.Counter()

    def walk(node):
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            counts[key] += 1
            if key in name_maps:
                if isinstance(value, dict):
                    for sub in value.values():
                        walk(sub)
            elif key in subschema_lists:
                if isinstance(value, list):
                    for sub in value:
                        walk(sub)
            elif key in subschema_values:
                walk(value)

    walk(SCHEMA)
    return counts


def test_measured_keyword_counts_are_what_the_artifact_claims():
    """Sanity floor: the counts this suite reasons about, measured live."""
    counts = _count_keywords()
    assert counts["if"] == 7
    assert counts["then"] == 7
    assert counts["else"] == 0
    assert counts["oneOf"] == 1
    assert counts["allOf"] == 2
    assert counts["anyOf"] == 0
    assert counts["not"] == 1
    assert counts["enum"] == 37
    assert counts["const"] == 7
    assert counts["pattern"] == 5
    assert counts["minItems"] == 1
    assert counts["additionalProperties"] == 37
    assert counts["dependentRequired"] == 0
    assert counts["minProperties"] == 0
    assert counts["required"] == 37
    assert len(SCHEMA["required"]) == 6
    assert SCHEMA["required"] == ROOT_REQUIRED


def test_coverage_artifact_matches_the_authoritative_schema():
    """The artifact is a live gate, not a stale note.

    It records claims about a specific schema file; if the schema is refreshed
    from upstream, this fails and the artifact must be regenerated alongside
    `schema/PROVENANCE.md`.
    """
    artifact = json.loads(COVERAGE_ARTIFACT.read_text(encoding="utf-8"))
    counts = _count_keywords()

    assert artifact["schema"]["path"] == "schema/isaac_record_v1.json"
    assert artifact["schema"]["bytes"] == len(SCHEMA_FILE.read_bytes())
    assert artifact["schema"]["sha256"] == schema_fingerprint(ROOT)
    assert artifact["schema"]["root_required_field_count"] == len(
        SCHEMA["required"]
    )

    # The four partition buckets, plus the informational conditional block.
    partition = (
        "rule_families_covered",
        "present_but_not_enforceable",
        "applicators_never_a_rule_family",
        "absent_from_schema",
    )
    for bucket in partition + ("conditional_keywords",):
        for keyword, entry in artifact[bucket].items():
            assert entry["schema_occurrences"] == counts[keyword], (
                bucket,
                keyword,
                counts[keyword],
            )

    # Nothing invented and nothing omitted: the four buckets partition exactly
    # the keyword set this validator could ever act on.
    validatable = set(Draft202012Validator.VALIDATORS)
    present = {k for k in validatable if counts[k] > 0}
    bucket_sets = [set(artifact[bucket]) for bucket in partition]
    union = set().union(*bucket_sets)
    assert union == validatable, union ^ validatable
    total = sum(len(s) for s in bucket_sets)
    assert total == len(union), "buckets must not overlap"
    assert set(artifact["absent_from_schema"]) == validatable - present

    # Absent families claim no coverage.
    for keyword, entry in artifact["absent_from_schema"].items():
        assert entry["schema_occurrences"] == 0
        assert entry["covered"] is False
        assert entry["coverable"] is False
    for keyword in ("anyOf", "dependentRequired", "minProperties"):
        assert keyword in artifact["absent_from_schema"]

    # Every claimed covering test really exists in this module.
    module_globals = set(globals())

    def check_tests(entry, keyword):
        assert entry["covering_tests"], keyword
        for test_name in entry["covering_tests"]:
            assert test_name in module_globals, (keyword, test_name)

    for keyword, entry in artifact["rule_families_covered"].items():
        assert entry["covered"] is True, keyword
        check_tests(entry, keyword)
    assert len(artifact["rule_families_covered"]) == 13

    for keyword, entry in artifact["present_but_not_enforceable"].items():
        assert entry["covered"] is False
        assert entry["coverable"] is False
        check_tests(entry, keyword)
    assert set(artifact["present_but_not_enforceable"]) == {"format"}

    for keyword, entry in artifact["applicators_never_a_rule_family"].items():
        assert entry["reported_as_rule_family"] is False

    for keyword, entry in artifact["conditional_keywords"].items():
        assert entry["covered"] is (entry["schema_occurrences"] > 0), keyword
        if entry["covered"]:
            check_tests(entry, keyword)
        else:
            assert entry["coverable"] is False
    assert set(artifact["conditional_keywords"]) == {"if", "then", "else"}
