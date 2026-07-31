"""Safety tests for the shared reconnaissance service and its CLI wrapper.

The reconnaissance logic now lives in ``apps/api/isaac_api/db_recon.py`` (it
has to: the Dockerfile COPY allowlist does not ship ``scripts/db_recon.py``, and
per ``docs/postgres-test-db-guide.md`` the database is reachable only from the
deployed pod). ``scripts/db_recon.py`` is a thin CLI wrapper over it. These
tests therefore target TWO objects:

* the ``recon`` fixture — ``isaac_api.db_recon``, the service module, which owns
  every gate, redaction primitive, SQL constant and aggregation;
* the ``cli`` fixture — ``scripts/db_recon.py``, which owns only argument
  parsing, ``--out`` path safety, exit codes and ``main()``.

These tests run with NO database and NO ``psycopg2``. Everything is driven
through a fake DBAPI connection/cursor, so what is under test is the part that
actually matters: the fail-closed gates, the redaction guarantees, the
read-only statement guard, and the determinism of the aggregation.

The CLI is loaded via ``importlib.util.spec_from_file_location``, matching the
convention already used by ``tests/test_graphify_freshness.py`` and
``apps/api/tests/test_committed_snapshot.py`` for repo scripts that are not
importable packages. The service module is a normal import (``pyproject.toml``
puts ``apps/api`` on the pytest path).

Deliberate isolation from work in flight: ``isaac_records.diagnostics`` may or
may not exist (and may be mid-edit) in any given working tree, so no test here
imports it. The diagnostics/official fallback is exercised by monkeypatching
``load_diagnostics_enricher``, which is why this file passes either way.
"""

from __future__ import annotations

import importlib.util
import io
import json
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "db_recon.py"
SERVICE = REPO_ROOT / "apps" / "api" / "isaac_api" / "db_recon.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("db_recon_cli_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recon():
    """The shared service module — where all reconnaissance logic lives."""
    from isaac_api import db_recon

    return db_recon


@pytest.fixture(scope="module")
def cli():
    """The thin ``scripts/db_recon.py`` wrapper: argparse, --out, exit codes."""
    return _load_cli()


# --- fakes -------------------------------------------------------------------

#: Obviously-fake sensitive content. Every one of these strings must be absent
#: from the serialised report.
FAKE_TITLE = "TOTALLY-FAKE Operando XANES of Sample ZZ-QQ-000"
FAKE_SAMPLE = "FAKE-CuO-NANOPOWDER-9999"
FAKE_VALUE = "8979.3-eV-FAKE-EDGE-VALUE"
FAKE_PERSON = "Notareal Person"
FAKE_DRIFT_KEY = "portal_only_drift_field"

#: C1 regression fixtures. These are IDENTIFIER-SHAPED scientific values that
#: appear as object KEYS at ``additionalProperties``-open schema locations. The
#: first two are lifted verbatim from the repo's own committed fixture
#: tests/fixtures/official/ex_situ_xanes_cuo2_record.json. A character-class
#: heuristic cannot distinguish these from real schema field names, which is
#: precisely why the policy is anchored to the vendored schema instead.
FAKE_SPECIES_KEY = "CuO2_mass_fraction"
FAKE_SPECIES_KEY_2 = "sucrose_mass_fraction"
FAKE_CONFIG_KEY = "monochromator_crystal"
FAKE_PRESSURE_KEY = "FAKEGAS_C7H8_partial_pressure_bar"
FAKE_CONDITION_KEY = "fake_electrode_loading_mg_cm2"

IDENTIFIER_SHAPED_SENSITIVE = (
    FAKE_SPECIES_KEY,
    FAKE_SPECIES_KEY_2,
    FAKE_CONFIG_KEY,
    FAKE_PRESSURE_KEY,
    FAKE_CONDITION_KEY,
)
FAKE_ULID_A = "01JQZ0FAKEREC0NAAAAAAAAAAA"
FAKE_ULID_B = "01JQZ0FAKEREC0NBBBBBBBBBBB"
FAKE_PASSWORD = "not-a-real-password-1234"
FAKE_HOST = "fake-host.invalid.example"


def fake_record(record_id: str) -> dict:
    """A synthetic record shaped like a drifted production record."""
    return {
        "isaac_record_version": "1.05",
        "record_id": record_id,
        "record_type": "evidence",
        "record_domain": "characterization",
        "source_type": "facility",
        "timestamps": {"created": "2026-01-01T00:00:00Z"},
        "sample": {
            "name": FAKE_SAMPLE,
            "notes": FAKE_VALUE,
            # additionalProperties-open map: keys are chemical species
            "composition": {FAKE_SPECIES_KEY: 0.7, FAKE_SPECIES_KEY_2: 0.3},
        },
        "system": {"configuration": {FAKE_CONFIG_KEY: FAKE_VALUE}},
        "context": {
            "transport": {"feed": {"partial_pressures": {FAKE_PRESSURE_KEY: 0.2}}}
        },
        "measurement": {"series": [{"conditions": {FAKE_CONDITION_KEY: 1.5}}]},
        "attribution": {"created_by": FAKE_PERSON},
        "descriptors": [
            {"name": "edge_energy", "value": FAKE_VALUE},
            {"name": "edge_step", "value": FAKE_VALUE},
        ],
        "title": FAKE_TITLE,
        FAKE_DRIFT_KEY: {"nested": FAKE_VALUE},
    }


class FakeCursor:
    def __init__(self, rows: dict, log: list):
        self._rows = rows
        self._log = log
        self._last = None
        self.closed = False

    def execute(self, sql, params=None):
        self._last = sql
        self._log.append((sql, params))

    def fetchall(self):
        return list(self._rows.get(self._last, []))

    def close(self):
        self.closed = True


class FakeConnection:
    """Minimal DBAPI-ish stand-in: cursor()/close(), plus set_session()."""

    def __init__(self, rows: dict, *, with_set_session: bool = True):
        self._rows = rows
        self.log: list = []
        self.readonly_requested = False
        self.closed = False
        if not with_set_session:
            # emulate a driver without psycopg2's set_session
            self.set_session = None  # type: ignore[assignment]

    def set_session(self, readonly=False, **kwargs):  # noqa: D102
        self.readonly_requested = bool(readonly)

    def cursor(self):
        return FakeCursor(self._rows, self.log)

    def close(self):
        self.closed = True


def base_rows(recon, records=(FAKE_ULID_A, FAKE_ULID_B)) -> dict:
    """A fully-passing row map; individual tests override single entries."""
    page = [
        (rid + " ", "evidence", "characterization", fake_record(rid)) for rid in records
    ]
    return {
        recon.Q_TRANSACTION_READ_ONLY: [("on",)],
        recon.Q_CURRENT_DATABASE: [("metadata_assistant",)],
        recon.Q_CURRENT_USER: [("metadata_assistant", "metadata_assistant")],
        recon.Q_SSL: [(True, "TLSv1.3", "TLS_AES_256_GCM_SHA384", 256)],
        recon.Q_RECORDS_TABLE_PRESENT: [(1,)],
        recon.Q_RECORDS_TABLE_OWNER: [("metadata_assistant",)],
        recon.Q_IS_SUPERUSER: [("off",)],
        recon.Q_SERVER_VERSION: [("18.0", "180000")],
        recon.Q_RECORD_COUNT: [(len(page),)],
        recon.Q_TABLE_INVENTORY: [("records",), ("vocabulary_cache",), ("templates",)],
        recon.Q_RECORDS_BY_TYPE: [("evidence", len(page))],
        recon.Q_RECORDS_BY_DOMAIN: [("characterization", len(page))],
        recon.Q_RECORDS_PAGE: page,
        recon.Q_VOCAB_TABLE_PRESENT: [(1,)],
        recon.Q_VOCAB_COLUMNS: [
            ("id", "integer"),
            ("category", "character varying"),
            ("term", "text"),
        ],
        recon.Q_VOCAB_COUNT: [(1234,)],
        recon.vocab_group_sql("category"): [("technique", 900), ("element", 334)],
    }


GOOD_ENV = {
    "PGDATABASE": "metadata_assistant",
    "ISAAC_RUN_SLAC_DB_RECON": "1",
    "PGHOST": FAKE_HOST,
    "PGUSER": "metadata_assistant",
    "PGPASSWORD": FAKE_PASSWORD,
}


def run_ok(recon, *, rows=None, env=None, **kwargs):
    rows = base_rows(recon) if rows is None else rows
    env = dict(GOOD_ENV) if env is None else env
    return recon.run_recon(FakeConnection(rows), env=env, salt="test-salt", **kwargs)


# --- the nine fail-closed gates -----------------------------------------------
# opt_in · pgdatabase_env · current_database · current_user · tls ·
# records_table · not_production_shaped · transaction_read_only · no_mutation


def test_gate_opt_in_refuses_when_env_var_absent(recon):
    env = {k: v for k, v in GOOD_ENV.items() if k != "ISAAC_RUN_SLAC_DB_RECON"}
    with pytest.raises(recon.ReconRefusal) as exc:
        recon.check_env_gates(env)
    assert exc.value.gate == "opt_in"
    assert exc.value.exit_code != 0


@pytest.mark.parametrize("value", ["", "0", "yes", "true", "2", " "])
def test_gate_opt_in_requires_exactly_one(recon, value):
    env = dict(GOOD_ENV, ISAAC_RUN_SLAC_DB_RECON=value)
    with pytest.raises(recon.ReconRefusal) as exc:
        recon.check_env_gates(env)
    assert exc.value.gate == "opt_in"


@pytest.mark.parametrize(
    "value", ["", "postgres", "isaac_records", "metadata_assistant_prod", "METADATA_ASSISTANT"]
)
def test_gate_pgdatabase_env_refuses_anything_else(recon, value):
    env = dict(GOOD_ENV, PGDATABASE=value)
    with pytest.raises(recon.ReconRefusal) as exc:
        recon.check_env_gates(env)
    assert exc.value.gate == "pgdatabase_env"


def test_gate_env_both_pass_together(recon):
    assert recon.check_env_gates(GOOD_ENV) == {"opt_in": "pass", "pgdatabase_env": "pass"}


def test_gate_current_database_refuses_mismatch(recon):
    """Guards a PGDATABASE lie or a redirected connection."""
    rows = base_rows(recon)
    rows[recon.Q_CURRENT_DATABASE] = [("isaac_production",)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "current_database"


def test_gate_current_user_refuses_wrong_role(recon):
    rows = base_rows(recon)
    rows[recon.Q_CURRENT_USER] = [("postgres", "postgres")]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "current_user"


def test_gate_current_user_refuses_role_switch(recon):
    """SET ROLE must not let a different session_user slip past."""
    rows = base_rows(recon)
    rows[recon.Q_CURRENT_USER] = [("metadata_assistant", "postgres")]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "current_user"


@pytest.mark.parametrize(
    "ssl_rows",
    [
        [],  # no pg_stat_ssl row at all -> TLS unproven
        [(False, None, None, None)],  # explicitly not encrypted
        [(None, None, None, None)],  # unknown -> absence of proof
    ],
)
def test_gate_tls_refuses_unless_confirmed(recon, ssl_rows):
    rows = base_rows(recon)
    rows[recon.Q_SSL] = ssl_rows
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "tls"


def test_gate_tls_pass_reports_cipher_but_no_certificate_material(recon):
    report = run_ok(recon)
    tls = report["connection"]["tls"]
    assert tls["confirmed"] is True
    assert tls["cipher"] == "TLS_AES_256_GCM_SHA384"
    assert set(tls) == {"confirmed", "version", "cipher", "bits"}


def test_gate_records_table_refuses_when_missing(recon):
    rows = base_rows(recon)
    rows[recon.Q_RECORDS_TABLE_PRESENT] = [(0,)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "records_table"


def test_gate_not_production_shaped_refuses_huge_table(recon):
    rows = base_rows(recon)
    rows[recon.Q_RECORD_COUNT] = [(recon.MAX_PLAUSIBLE_RECORD_ROWS + 1,)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "not_production_shaped"


def test_gate_not_production_shaped_refuses_foreign_table_owner(recon):
    rows = base_rows(recon)
    rows[recon.Q_RECORDS_TABLE_OWNER] = [("isaac_portal",)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "not_production_shaped"


def test_gate_not_production_shaped_refuses_superuser_session(recon):
    rows = base_rows(recon)
    rows[recon.Q_IS_SUPERUSER] = [("on",)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "not_production_shaped"


def test_gate_not_production_shaped_allows_documented_seed_size(recon):
    ids = [f"01JQZ0FAKEREC0N{i:011d}" for i in range(recon.DOCUMENTED_SEED_ROWS)]
    rows = base_rows(recon, records=ids)
    report = run_ok(recon, rows=rows)
    assert report["records"]["total"] == recon.DOCUMENTED_SEED_ROWS
    assert report["production_detection"]["heuristic_is_a_backstop_not_a_guarantee"] is True


def test_transaction_read_only_is_verified_not_assumed(recon):
    rows = base_rows(recon)
    rows[recon.Q_TRANSACTION_READ_ONLY] = [("off",)]
    with pytest.raises(recon.ReconRefusal) as exc:
        run_ok(recon, rows=rows)
    assert exc.value.gate == "transaction_read_only"


def test_all_gates_recorded_as_pass_on_a_clean_run(recon):
    report = run_ok(recon)
    assert report["gates"] == {
        "current_database": "pass",
        "current_user": "pass",
        "no_mutation": "pass",
        "not_production_shaped": "pass",
        "opt_in": "pass",
        "pgdatabase_env": "pass",
        "records_table": "pass",
        "tls": "pass",
        "transaction_read_only": "pass",
    }


def test_every_refusal_exits_non_zero(recon):
    for cls in (
        recon.ReconRefusal,
        recon.UnsafeStatement,
        recon.MissingDependency,
        recon.ConnectionRefused,
        recon.MutationDetected,
        recon.UsageError,
    ):
        assert cls.exit_code != 0


# --- read-only enforcement ---------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM records",
        "delete from records where id = 1",
        "INSERT INTO records (record_id) VALUES ('x')",
        "UPDATE records SET record_type = 'intent'",
        "DROP TABLE records",
        "TRUNCATE records",
        "ALTER TABLE records ADD COLUMN x int",
        "CREATE TABLE t (a int)",
        "GRANT ALL ON records TO public",
        "COPY records TO '/tmp/x.csv'",
        "SELECT 1; DROP TABLE records",
        "SELECT pg_terminate_backend(1)",
        "SELECT * INTO other FROM records",
        "SET ROLE postgres",
        "BEGIN",
        "COMMIT",
        "VACUUM FULL",
        "REFRESH MATERIALIZED VIEW v",
        "SELECT 1 -- harmless\n; DELETE FROM records",
        "/* c */ DELETE FROM records",
        "",
        "   ",
    ],
)
def test_read_only_guard_rejects_writes_and_multi_statements(recon, sql):
    with pytest.raises(recon.UnsafeStatement):
        recon.assert_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT current_database()",
        "select count(*) from records",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT record_id, created_at FROM records ORDER BY created_at",
        "SELECT count(*) FROM record_history",
        "SELECT 1;",
    ],
)
def test_read_only_guard_accepts_selects(recon, sql):
    assert recon.assert_read_only_sql(sql) == sql


def test_columns_named_like_keywords_do_not_false_positive(recon):
    """``created_at``/``updated_at`` must not trip the write-token scan."""
    recon.assert_read_only_sql("SELECT created_at, updated_at FROM records")


def test_every_module_level_query_passes_its_own_guard(recon):
    names = [n for n in dir(recon) if n.startswith("Q_")]
    assert len(names) >= 12
    for name in names:
        recon.assert_read_only_sql(getattr(recon, name))


def test_session_statements_are_a_frozen_allowlist(recon):
    for statement in recon.SESSION_READ_ONLY_STATEMENTS:
        assert recon._assert_session_statement(statement) == statement
    for bad in ("SET ROLE postgres", "SET default_transaction_read_only = off", "DELETE FROM records"):
        with pytest.raises(recon.UnsafeStatement):
            recon._assert_session_statement(bad)


def test_identifier_interpolation_refuses_injection(recon):
    assert recon._quote_ident("category") == '"category"'
    for bad in ('cat"; DROP TABLE records --', "a b", "1abc", "", "cat)"):
        with pytest.raises(recon.UnsafeStatement):
            recon._quote_ident(bad)


def test_run_recon_only_ever_executes_guarded_statements(recon):
    conn = FakeConnection(base_rows(recon))
    recon.run_recon(conn, env=GOOD_ENV, salt="s")
    assert conn.readonly_requested is True
    for sql, params in conn.log:
        if sql in recon.SESSION_READ_ONLY_STATEMENTS:
            continue
        recon.assert_read_only_sql(sql)
        # values are always bound parameters, never interpolated
        assert params is None or isinstance(params, tuple)


def test_run_recon_works_without_driver_set_session(recon):
    conn = FakeConnection(base_rows(recon), with_set_session=False)
    report = recon.run_recon(conn, env=GOOD_ENV, salt="s")
    assert report["connection"]["driver_readonly_session_applied"] is False
    # the server-side verification is what actually gates the run
    assert report["gates"]["transaction_read_only"] == "pass"


# --- redaction ---------------------------------------------------------------

SENSITIVE_STRINGS = (
    FAKE_TITLE,
    FAKE_SAMPLE,
    FAKE_VALUE,
    FAKE_PERSON,
    FAKE_ULID_A,
    FAKE_ULID_B,
    FAKE_PASSWORD,
    FAKE_HOST,
)


def test_report_contains_no_sensitive_value_from_the_fake_rows(recon):
    """The central redaction guarantee, asserted on the serialised output."""
    payload = json.dumps(run_ok(recon), sort_keys=True)
    for secret in SENSITIVE_STRINGS:
        assert secret not in payload, f"leaked {secret!r}"


def test_report_contains_no_sensitive_substring_even_case_folded(recon):
    payload = json.dumps(run_ok(recon), sort_keys=True).lower()
    for secret in SENSITIVE_STRINGS:
        assert secret.lower() not in payload


def test_structural_drift_is_reported_as_a_count_and_parent_path(recon, monkeypatch):
    """C1/I2: drift is signalled WITHOUT naming the undeclared key.

    The previous version of this test asserted the undeclared key name WAS
    present, which codified the C1 leak. The drift signal an operator needs is
    "N undeclared properties at this parent path", which is exactly as
    actionable and names nothing.
    """
    monkeypatch.setattr(recon, "load_diagnostics_enricher", lambda: (None, "forced-off"))
    report = run_ok(recon)
    payload = json.dumps(report, sort_keys=True)
    assert FAKE_DRIFT_KEY not in payload  # the undeclared name: never
    assert FAKE_VALUE not in payload  # its value: never
    unexpected = report["validation"]["unexpected_properties"]
    assert unexpected["total_occurrences"] >= 1
    assert unexpected["undeclared_name_count"] >= 1
    assert "$" in {e["parent_path"] for e in unexpected["by_parent_path"]}


# --- C1: identifier-shaped scientific values used as object KEYS -------------


def test_identifier_shaped_species_keys_never_escape(recon):
    """C1 regression: the channel the character-class heuristic could not see.

    Chemical formulas, gas species, beamline configuration slugs and sample
    codes are all identifier-shaped, so the old ``[A-Za-z_][A-Za-z0-9_]*``
    test waved them through as if they were schema field names.
    """
    payload = json.dumps(run_ok(recon), sort_keys=True)
    for key in IDENTIFIER_SHAPED_SENSITIVE:
        assert key not in payload, f"leaked identifier-shaped key {key!r}"


def test_real_committed_fixture_composition_keys_never_escape(recon, monkeypatch):
    """C1 regression driven by the repo's own real fixture, end to end."""
    monkeypatch.setattr(recon, "load_diagnostics_enricher", lambda: (None, "forced-off"))
    record = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json").read_text()
    )
    composition_keys = list(record["sample"]["composition"])
    assert composition_keys, "fixture must actually exercise an open map"
    rows = base_rows(recon)
    rows[recon.Q_RECORDS_PAGE] = [(FAKE_ULID_A, "evidence", "characterization", record)]
    rows[recon.Q_RECORD_COUNT] = [(1,)]
    payload = json.dumps(run_ok(recon, rows=rows), sort_keys=True)
    for key in composition_keys:
        assert key not in payload, f"leaked real composition key {key!r}"
    for key in record.get("system", {}).get("configuration", {}):
        assert key not in payload, f"leaked real configuration key {key!r}"


def test_open_map_keys_are_masked_but_shape_is_preserved(recon):
    """Masking must not destroy the structural signal the recon exists for."""
    paths, _ = recon.structural_paths(
        {"sample": {"composition": {FAKE_SPECIES_KEY: 1, FAKE_SPECIES_KEY_2: 2}}}
    )
    assert "sample/composition" in paths  # the open map is still visible
    assert f"sample/composition/{recon.MASK_OPEN_MAP_KEY}" in paths
    assert not any(FAKE_SPECIES_KEY in p for p in paths)


def test_declared_schema_property_names_are_still_emitted(recon):
    """The allowlist must not blind the report to genuine schema structure."""
    paths, _ = recon.structural_paths(
        {"sample": {"name": "x"}, "timestamps": {"created_utc": "y"}, "descriptors": [{"name": 1}]}
    )
    assert "sample/name" in paths
    assert "timestamps/created_utc" in paths
    assert "descriptors/[]/name" in paths


def test_masked_key_counter_is_truthful(recon):
    """C2: the counter an operator checks must not read 0 while keys are masked."""
    _, stats = recon.structural_paths(
        {"sample": {"composition": {FAKE_SPECIES_KEY: 1, FAKE_SPECIES_KEY_2: 2}}}
    )
    assert stats["masked_key_segments"] == 2
    report = run_ok(recon)
    assert report["structure"]["masked_key_segments"] > 0


def test_undeclared_key_outside_an_open_map_gets_its_own_mask(recon):
    paths, _ = recon.structural_paths({"totally_undeclared_block": {"inner": 1}})
    assert recon.MASK_UNDECLARED_KEY in paths[0]
    assert "totally_undeclared_block" not in " ".join(paths)


def test_schema_allowlist_is_loaded_from_the_vendored_schema(recon):
    declared, open_maps = recon.load_schema_vocabulary(REPO_ROOT)
    # anchored to the real schema, not a hardcoded list
    assert "composition" in declared and "descriptors" in declared
    assert FAKE_SPECIES_KEY not in declared
    assert "sample/composition" in open_maps
    assert "system/configuration" in open_maps
    assert "context/transport/feed/partial_pressures" in open_maps
    assert "measurement/series/[]/conditions" in open_maps


def test_unexpected_property_names_are_masked_when_undeclared(recon):
    declared, _ = recon.load_schema_vocabulary(REPO_ROOT)
    msg = f"Additional properties are not allowed ('{FAKE_SPECIES_KEY}' was unexpected)"
    names = recon.unexpected_property_names(msg, declared)
    assert FAKE_SPECIES_KEY not in names
    assert names == [recon.MASK_UNDECLARED_KEY]


def test_unexpected_property_names_may_emit_a_declared_schema_token(recon):
    """A name that IS in the public vendored schema is a safe public token."""
    declared, _ = recon.load_schema_vocabulary(REPO_ROOT)
    msg = "Additional properties are not allowed ('beamline' was unexpected)"
    assert recon.unexpected_property_names(msg, declared) == ["beamline"]


def test_no_record_payload_object_is_embedded(recon):
    report = run_ok(recon)
    assert "data" not in report["records"]
    assert "raw_record_ids" not in report["records"]
    # descriptor VALUES must not appear anywhere; only their paths
    payload = json.dumps(report, sort_keys=True)
    assert "descriptors/[]/value" in payload
    assert FAKE_VALUE not in payload


def test_host_is_withheld(recon):
    assert run_ok(recon)["connection"]["host"] == recon.MASK_WITHHELD


def test_unrecognised_enum_values_are_masked_not_echoed(recon):
    rows = base_rows(recon)
    rows[recon.Q_RECORDS_BY_TYPE] = [("evidence", 1), ("SECRET_PORTAL_TYPE", 1)]
    rows[recon.Q_RECORDS_BY_DOMAIN] = [("characterization", 1), ("SECRET_DOMAIN", 1)]
    payload = json.dumps(run_ok(recon, rows=rows), sort_keys=True)
    assert "SECRET_PORTAL_TYPE" not in payload
    assert "SECRET_DOMAIN" not in payload
    assert recon.MASK_UNRECOGNISED in payload


def test_unrecognised_record_version_is_masked(recon):
    assert recon.safe_version_value("1.05") == "1.05"
    assert recon.safe_version_value("1.06") == "1.06"
    assert recon.safe_version_value("v1.05-portal-secret") == recon.MASK_UNRECOGNISED
    assert recon.safe_version_value(None) == recon.MASK_NULL_BUCKET


def test_non_identifier_object_keys_are_masked(recon):
    # ``notes`` is a real declared schema property, so it survives; the
    # non-identifier key is masked and counted. Using a declared name here is
    # deliberate: under the schema-allowlist policy an invented key like
    # "ok_key" would ALSO mask, which would make the count assertion pass for
    # the wrong reason.
    paths, stats = recon.structural_paths({"notes": 1, "FAKE-SAMPLE-ID-42": 2})
    assert "FAKE-SAMPLE-ID-42" not in paths
    assert recon.MASK_NON_IDENTIFIER in paths
    assert "notes" in paths
    assert stats["masked_key_segments"] == 1


def test_vocabulary_values_withheld_when_not_slug_shaped(recon):
    rows = base_rows(recon)
    rows[recon.vocab_group_sql("category")] = [("technique", 5), ("FAKE Free Text Term!", 2)]
    report = run_ok(recon, rows=rows)
    grouped = report["vocabulary_cache"]["grouped"][0]
    payload = json.dumps(report, sort_keys=True)
    assert grouped["values_emitted"] is False
    assert "FAKE Free Text Term!" not in payload
    # One bad value withholds the whole column: no vocabulary VALUE is emitted.
    # Scoped to the vocabulary section on purpose — "technique" is also a
    # declared schema property name that legitimately appears elsewhere in the
    # report (e.g. the instance path "system/technique"), so a whole-payload
    # substring assertion would collide with public schema structure and pass
    # or fail for reasons unrelated to vocabulary redaction.
    assert "technique" not in json.dumps(report["vocabulary_cache"], sort_keys=True)
    assert grouped["group_counts_only"] == [5, 2]  # counts survive


def test_vocabulary_term_column_is_never_grouped(recon):
    """``term`` holds vocabulary term values; it is not in the allowlist."""
    report = run_ok(recon)
    assert [g["column"] for g in report["vocabulary_cache"]["grouped"]] == ["category"]
    assert report["vocabulary_cache"]["row_count"] == 1234


def test_validator_messages_are_never_emitted(recon):
    """jsonschema messages embed the offending value; only families escape."""
    report = run_ok(recon)
    payload = json.dumps(report, sort_keys=True)
    for fragment in ("is not one of", "is not of type", "was unexpected", "Additional properties"):
        assert fragment not in payload
    assert report["validation"]["failed"] >= 1


# --- record_id handling ------------------------------------------------------


def test_raw_ulids_never_appear_in_default_output(recon):
    payload = json.dumps(run_ok(recon), sort_keys=True)
    assert FAKE_ULID_A not in payload
    assert FAKE_ULID_B not in payload
    assert recon._ULID_RE.search(payload) is None


def test_record_ids_are_emitted_as_salted_truncated_digests(recon):
    report = run_ok(recon)
    digests = report["records"]["record_id_digests"]
    assert digests["count"] == 2
    assert len(set(digests["digests"])) == 2
    assert all(len(d) == 16 and all(c in "0123456789abcdef" for c in d) for d in digests["digests"])
    assert digests["salt_emitted"] is False
    assert report["records"]["raw_record_ids_emitted"] is False


def test_digest_is_salt_dependent_and_salt_is_not_emitted(recon):
    a = recon.run_recon(FakeConnection(base_rows(recon)), env=GOOD_ENV, salt="salt-one")
    b = recon.run_recon(FakeConnection(base_rows(recon)), env=GOOD_ENV, salt="salt-two")
    assert a["records"]["record_id_digests"]["digests"] != b["records"]["record_id_digests"]["digests"]
    assert "salt-one" not in json.dumps(a, sort_keys=True)


def test_char26_blank_padding_is_stripped_before_hashing(recon):
    """docs/postgres-test-db-guide.md: CHAR(26) is blank-padded on read."""
    assert recon.hash_record_id(FAKE_ULID_A, "s") == recon.hash_record_id(FAKE_ULID_A + "   ", "s")
    report = run_ok(recon)  # base_rows deliberately pads every record_id
    expected = sorted(recon.hash_record_id(r, "test-salt") for r in (FAKE_ULID_A, FAKE_ULID_B))
    assert report["records"]["record_id_digests"]["digests"] == expected


def test_raw_ids_emitted_only_when_explicitly_requested(recon):
    report = recon.run_recon(
        FakeConnection(base_rows(recon)), env=GOOD_ENV, salt="s", emit_raw_record_ids=True
    )
    assert report["records"]["raw_record_ids_emitted"] is True
    assert FAKE_ULID_A in report["records"]["raw_record_ids"]


def test_raw_id_flag_alone_is_refused_without_the_env_authorisation(recon, capsys, cli):
    code = cli.main(
        ["--emit-raw-record-ids"],
        env=dict(GOOD_ENV),
        connect=lambda env: FakeConnection(base_rows(recon)),
    )
    assert code == recon.UsageError.exit_code
    assert "raw_ids_not_authorized" in capsys.readouterr().err


def test_raw_id_flag_with_env_authorisation_is_allowed(recon, capsys, cli):
    env = dict(GOOD_ENV, ISAAC_DB_RECON_ALLOW_RAW_IDS="1")
    code = cli.main(
        ["--emit-raw-record-ids", "--id-salt", "s", "--quiet"],
        env=env,
        connect=lambda e: FakeConnection(base_rows(recon)),
    )
    assert code == 0
    assert FAKE_ULID_A in capsys.readouterr().out


# --- structural signatures ---------------------------------------------------


def test_structural_paths_strips_values(recon):
    # Declared schema names, so the assertion isolates value-stripping rather
    # than incidentally testing the allowlist.
    paths, _ = recon.structural_paths({"notes": "SECRET", "sample": {"formula": 12345}})
    assert paths == ["notes", "sample", "sample/formula"]


def test_structural_paths_collapses_array_indices(recon):
    doc = {"descriptors": [{"name": 1}, {"name": 2}, {"unit": 3}]}
    paths, _ = recon.structural_paths(doc)
    assert paths == [
        "descriptors",
        "descriptors/[]",
        "descriptors/[]/name",
        "descriptors/[]/unit",
    ]


def test_structural_paths_handles_nested_arrays_and_empties(recon):
    paths, _ = recon.structural_paths(
        {"links": [[{"rel": 1}]], "tags": [], "assets": {}, "notes": None}
    )
    assert paths == [
        "assets",
        "links",
        "links/[]",
        "links/[]/[]",
        "links/[]/[]/rel",
        "notes",
        "tags",
    ]


def test_structural_paths_is_order_independent_and_sorted(recon):
    a, _ = recon.structural_paths({"z": 1, "a": {"y": 2, "b": 3}})
    b, _ = recon.structural_paths({"a": {"b": 3, "y": 2}, "z": 1})
    assert a == b == sorted(a)


def test_signature_is_stable_and_shared_by_identical_structures(recon):
    s1 = recon.signature_id(recon.structural_paths({"a": 1, "b": [{"c": 2}]})[0])
    s2 = recon.signature_id(recon.structural_paths({"b": [{"c": 99}], "a": "other"})[0])
    assert s1 == s2 and len(s1) == 16


def test_signature_differs_when_structure_differs(recon):
    s1 = recon.signature_id(recon.structural_paths({"name": 1})[0])
    s2 = recon.signature_id(recon.structural_paths({"name": 1, "notes": 2})[0])
    assert s1 != s2


def test_structure_depth_is_bounded(recon):
    doc = cur = {}
    for _ in range(recon.MAX_STRUCTURE_DEPTH + 10):
        cur["n"] = {}
        cur = cur["n"]
    _, stats = recon.structural_paths(doc)
    assert stats["depth_truncated"] is True


def test_aggregate_structure_groups_signatures_with_counts(recon):
    same = recon.structural_paths({"name": 1})
    other = recon.structural_paths({"name": 1, "notes": 2})
    agg = recon.aggregate_structure([same, same, other])
    assert agg["records_analyzed"] == 3
    assert agg["distinct_signature_count"] == 2
    assert agg["distinct_signatures"][0]["count"] == 2
    presence = {e["path"]: e["records_with_path"] for e in agg["path_presence"]}
    assert presence == {"name": 3, "notes": 1}


def test_two_records_with_identical_shape_share_one_signature(recon):
    report = run_ok(recon)
    assert report["structure"]["records_analyzed"] == 2
    assert report["structure"]["distinct_signature_count"] == 1
    assert report["structure"]["distinct_signatures"][0]["count"] == 2


def test_collapse_instance_path_and_pointer(recon):
    assert recon.collapse_instance_path("descriptors.0.name") == "descriptors/[]/name"
    assert recon.collapse_instance_path("$") == "$"
    assert recon.collapse_instance_path("") == "$"
    assert recon.collapse_json_pointer("/descriptors/12/name") == "descriptors/[]/name"
    assert recon.collapse_json_pointer("") == "$"
    assert recon.collapse_json_pointer("/") == "$"
    assert (
        recon.collapse_instance_path("sample.FAKE SAMPLE")
        == "sample/" + recon.MASK_NON_IDENTIFIER
    )
    # An undeclared segment masks even when identifier-shaped (C1).
    assert recon.collapse_instance_path("ZZQQ_undeclared") == recon.MASK_UNDECLARED_KEY
    # A schema pointer keeps its JSON Schema keywords — public structure.
    assert (
        recon.collapse_schema_pointer("/properties/sample/properties/name")
        == "properties/sample/properties/name"
    )


# --- validation summary + diagnostics fallback -------------------------------


def test_validation_reports_counts_and_families_only(recon):
    report = run_ok(recon)
    validation = report["validation"]
    assert validation["records_validated"] == 2
    assert validation["passed"] + validation["failed"] == 2
    assert validation["failed"] == 2  # the fake records carry a drift key
    assert validation["all_records_valid"] is False
    families = {f["family"] for f in validation["failure_rule_families"]}
    assert families  # some taxonomy was produced
    for entry in validation["failure_rule_families"]:
        assert set(entry) == {"family", "records_affected", "error_count"}


def test_validation_answers_the_headline_question_for_clean_records(recon, monkeypatch):
    """A schema-clean record must be reported as passing."""
    monkeypatch.setattr(recon, "load_diagnostics_enricher", lambda: (None, "forced-off"))
    clean = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "official" / "ex_situ_xanes_cuo2_record.json").read_text()
    )
    rows = base_rows(recon)
    rows[recon.Q_RECORDS_PAGE] = [(FAKE_ULID_A, "evidence", "characterization", clean)]
    rows[recon.Q_RECORD_COUNT] = [(1,)]
    report = run_ok(recon, rows=rows)
    assert report["validation"]["passed"] == 1
    assert report["validation"]["failed"] == 0
    assert report["validation"]["all_records_valid"] is True
    assert report["validation"]["failure_rule_families"] == []


def test_additional_properties_drift_is_surfaced_without_naming_the_key(recon, monkeypatch):
    """The highest-value drift signal, via the official engine — anonymously.

    The previous version asserted the undeclared key NAME was present, which
    codified the C1 leak: an undeclared key can be a scientific value used as a
    key. Count plus parent path is exactly as actionable and names nothing.
    """
    monkeypatch.setattr(recon, "load_diagnostics_enricher", lambda: (None, "forced-off"))
    report = run_ok(recon)
    validation = report["validation"]
    assert validation["engine"] == "official"
    families = {f["family"] for f in validation["failure_rule_families"]}
    assert "additional_properties" in families
    names = {e["name"] for e in validation["unexpected_property_names"]}
    assert FAKE_DRIFT_KEY not in names
    assert recon.MASK_UNDECLARED_KEY in names
    assert validation["unexpected_properties"]["total_occurrences"] >= 1
    # Under this engine the counters ARE an observation, and say so.
    assert validation["unexpected_properties"]["names_computed"] is True
    assert validation["unexpected_properties"]["not_computed_reason"] is None


def test_drift_detail_says_not_computed_under_the_diagnostics_engine(recon, monkeypatch):
    """M-3: a zero that means "not computed" must not read as "none found".

    ``isaac_records.diagnostics`` reports the additionalProperties failure but
    not the offending key names, so ``_diagnostics_findings`` emits an empty
    name list and every counter in ``unexpected_properties`` stays 0 — while the
    same records really do carry structural drift, which the official engine
    counts (the test above). Presenting that 0 as an observation was the defect;
    the block now states which of the two it is.
    """

    class Item:
        rule_family = "additionalProperties"  # the raw jsonschema keyword
        kind = "error"
        pointer = "/descriptors/3/name"
        schema_pointer = None
        conditional = None

    class Report:
        diagnostics = [Item()]

    monkeypatch.setattr(
        recon, "load_diagnostics_enricher", lambda: (lambda rec, root: Report(), "fake.diagnose")
    )
    validation = run_ok(recon)["validation"]
    assert validation["engine"] == "diagnostics"
    unexpected = validation["unexpected_properties"]
    assert unexpected["total_occurrences"] == 0
    assert unexpected["names_computed"] is False
    assert "not computed" in (unexpected["not_computed_reason"] or "")
    # ...and the drift itself is still reported, under the engine's own label.
    assert {f["family"] for f in validation["failure_rule_families"]} == {"additionalProperties"}


def test_zero_drift_is_reported_as_an_observation_when_it_is_one(recon):
    """The other side of the flag: no additionalProperties failure at all.

    Nothing was withheld here, so the same zero is a real "none found" and must
    not be labelled uncomputed — otherwise the flag would be a constant.
    """
    agg = recon.aggregate_validation(
        [(False, [{"family": "required", "instance_path": "a", "unexpected_properties": []}])],
        engine="official",
        engine_detail="d",
    )
    assert agg["unexpected_properties"]["total_occurrences"] == 0
    assert agg["unexpected_properties"]["names_computed"] is True
    assert agg["unexpected_properties"]["not_computed_reason"] is None


def test_official_engine_used_when_diagnostics_is_unavailable(recon, monkeypatch):
    monkeypatch.setattr(
        recon, "load_diagnostics_enricher", lambda: (None, "unavailable (ImportError: ImportError)")
    )
    report = run_ok(recon)
    assert report["validation"]["engine"] == "official"
    assert report["diagnostics_module"]["available"] is False
    assert "validate_official" in report["validation"]["engine_detail"]


def test_diagnostics_engine_used_when_available(recon, monkeypatch):
    """Frozen contract: diagnose(record, root).diagnostics[*].rule_family/.pointer/..."""

    class Item:
        rule_family = "additionalProperties"
        kind = "error"
        pointer = "/descriptors/3/name"
        schema_pointer = "/properties/descriptors/items/properties/name"
        conditional = "evidence_requires_descriptors"

    class Report:
        diagnostics = [Item()]

    monkeypatch.setattr(
        recon, "load_diagnostics_enricher", lambda: (lambda rec, root: Report(), "fake.diagnose")
    )
    report = run_ok(recon)
    validation = report["validation"]
    assert validation["engine"] == "diagnostics"
    assert validation["engine_detail"] == "fake.diagnose"
    assert report["diagnostics_module"]["available"] is True
    assert [f["family"] for f in validation["failure_rule_families"]] == ["additionalProperties"]
    assert validation["failing_instance_paths"][0]["path"] == "descriptors/[]/name"
    assert validation["failing_schema_paths"][0]["schema_path"] == (
        "properties/descriptors/items/properties/name"
    )
    assert validation["conditional_rules_triggered"][0]["conditional"] == (
        "evidence_requires_descriptors"
    )
    # pass/fail still comes from the official validator, not from diagnostics
    assert validation["failed"] == 2


def test_diagnostics_failure_falls_back_without_breaking_the_run(recon, monkeypatch):
    def exploding(rec, root):
        raise RuntimeError("mid-flight module")

    monkeypatch.setattr(recon, "load_diagnostics_enricher", lambda: (exploding, "boom.diagnose"))
    report = run_ok(recon)
    assert report["validation"]["engine"] == "official"
    assert report["validation"]["failed"] == 2


def test_diagnostics_loader_never_raises(recon):
    """Whatever state isaac_records.diagnostics is in, loading must not raise."""
    enricher, detail = recon.load_diagnostics_enricher()
    assert isinstance(detail, str) and detail
    assert enricher is None or callable(enricher)


def test_boolean_conditional_gets_a_stable_label(recon):
    agg = recon.aggregate_validation(
        [(False, [{"family": "required", "instance_path": "a", "conditional": True}])],
        engine="x",
        engine_detail="y",
    )
    assert agg["conditional_rules_triggered"] == [
        {"conditional": "unnamed_conditional", "error_count": 1}
    ]


def test_free_text_conditional_label_is_withheld(recon):
    agg = recon.aggregate_validation(
        [(False, [{"family": "required", "instance_path": "a", "conditional": "FAKE secret note!"}])],
        engine="x",
        engine_detail="y",
    )
    assert agg["conditional_rules_triggered"][0]["conditional"] == recon.MASK_WITHHELD


def test_rule_family_classification(recon):
    cases = {
        "Additional properties are not allowed ('x' was unexpected)": "additional_properties",
        "'record_id' is a required property": "required",
        "'1.05' was expected": "const",
        "'bogus' is not one of ['evidence', 'intent']": "enum",
        "'x' is not of type 'number'": "type",
        "'x' does not match '^[0-9]+$'": "pattern",
        "'x' is not valid under any of the given schemas": "any_of",
        "['a', 'a'] has non-unique elements": "unique_items",
        "[] is too short": "bounds",
        "something entirely novel": "other",
    }
    for message, expected in cases.items():
        assert recon.rule_family(message) == expected, message


def test_unexpected_property_names_masks_everything_undeclared(recon):
    # Both names are UNDECLARED, so both collapse to the same mask — an
    # unexpected property is by definition not in the schema. ``good_key`` was
    # emitted verbatim under the old character-class policy: that was C1.
    msg = "Additional properties are not allowed ('good_key', 'BAD KEY!' were unexpected)"
    assert recon.unexpected_property_names(msg) == [recon.MASK_UNDECLARED_KEY]
    assert recon.unexpected_property_names("'x' is a required property") == []


# --- mutation proof ----------------------------------------------------------


def test_mutation_check_confirms_equal_counts(recon):
    check = run_ok(recon)["mutation_check"]
    assert check["records_before"] == check["records_after"] == 2
    assert check["vocabulary_cache_before"] == check["vocabulary_cache_after"] == 1234
    assert check["unchanged"] is True


def test_changing_record_count_mid_run_is_detected(recon):
    class DriftingCursor(FakeCursor):
        def fetchall(self):
            rows = super().fetchall()
            if self._last == self._count_sql:
                self._calls += 1
                if self._calls > 1:
                    return [(999,)]
            return rows

    rows = base_rows(recon)

    class DriftingConnection(FakeConnection):
        def cursor(self):
            cur = DriftingCursor(self._rows, self.log)
            cur._count_sql = recon.Q_RECORD_COUNT
            cur._calls = 0
            return cur

    with pytest.raises(recon.MutationDetected) as exc:
        recon.run_recon(DriftingConnection(rows), env=GOOD_ENV, salt="s")
    assert exc.value.gate == "no_mutation"
    assert exc.value.exit_code == 4


def test_changing_vocabulary_count_mid_run_is_detected(recon):
    calls = {"n": 0}

    class DriftingCursor(FakeCursor):
        def fetchall(self):
            if self._last == recon.Q_VOCAB_COUNT:
                calls["n"] += 1
                return [(1234,)] if calls["n"] == 1 else [(4321,)]
            return super().fetchall()

    class DriftingConnection(FakeConnection):
        def cursor(self):
            return DriftingCursor(self._rows, self.log)

    with pytest.raises(recon.MutationDetected):
        recon.run_recon(DriftingConnection(base_rows(recon)), env=GOOD_ENV, salt="s")


# --- leak scan ---------------------------------------------------------------


def test_leak_scan_passes_a_clean_report(recon):
    payload = json.dumps(run_ok(recon), sort_keys=True)
    assert recon.scan_for_leaks(payload, env=GOOD_ENV, allow_raw_ids=False) == []


def test_leak_scan_catches_raw_ulid(recon):
    issues = recon.scan_for_leaks(
        '{"x": "%s"}' % FAKE_ULID_A, env=GOOD_ENV, allow_raw_ids=False
    )
    assert "raw_ulid_present" in issues


def test_leak_scan_allows_ulid_when_explicitly_authorised(recon):
    issues = recon.scan_for_leaks('{"x": "%s"}' % FAKE_ULID_A, env=GOOD_ENV, allow_raw_ids=True)
    assert "raw_ulid_present" not in issues


@pytest.mark.parametrize(
    "text,code",
    [
        ('{"k": "-----BEGIN CERTIFICATE-----"}', "secret_shape:pem_block"),
        ('{"k": "postgresql://u:p@h/db"}', "secret_shape:connection_uri"),
        ('{"k": "password = hunter2"}', "secret_shape:password_assignment"),
        ('{"k": "PGPASSWORD"}', "secret_shape:pgpassword_literal"),
        ('{"k": "Bearer abcdefgh12345678"}', "secret_shape:bearer_token"),
    ],
)
def test_leak_scan_catches_secret_shapes(recon, text, code):
    assert code in recon.scan_for_leaks(text, env={}, allow_raw_ids=True)


def test_leak_scan_catches_env_values(recon):
    issues = recon.scan_for_leaks(
        '{"k": "%s"}' % FAKE_PASSWORD, env=GOOD_ENV, allow_raw_ids=True
    )
    assert "env_value_present:PGPASSWORD" in issues
    issues = recon.scan_for_leaks('{"k": "%s"}' % FAKE_HOST, env=GOOD_ENV, allow_raw_ids=True)
    assert "env_value_present:PGHOST" in issues


def test_leak_scan_does_not_flag_the_role_name(recon):
    """PGUSER's value is emitted on purpose as gate-3 evidence."""
    assert recon.scan_for_leaks(
        '{"current_user": "metadata_assistant"}', env=GOOD_ENV, allow_raw_ids=False
    ) == []


def test_leak_scan_issue_codes_never_contain_the_matched_text(recon):
    issues = recon.scan_for_leaks(
        '{"k": "%s", "j": "%s"}' % (FAKE_PASSWORD, FAKE_ULID_A),
        env=GOOD_ENV,
        allow_raw_ids=False,
    )
    joined = " ".join(issues)
    assert FAKE_PASSWORD not in joined
    assert FAKE_ULID_A not in joined


def test_main_aborts_and_writes_nothing_when_the_leak_scan_trips(recon, tmp_path, capsys, cli):
    out = tmp_path / "recon.json"

    def leaky_connect(env):
        return FakeConnection(base_rows(recon))

    # force a leak by making the report echo the password. Patched on the CLI
    # module: it imported ``run_recon`` by name from the service module, so the
    # CLI's own binding is what its ``main()`` actually calls.
    original = cli.run_recon

    def patched(*a, **k):
        report = original(*a, **k)
        report["oops"] = FAKE_PASSWORD
        return report

    cli.run_recon = patched
    try:
        code = cli.main(
            ["--out", str(out), "--id-salt", "s", "--quiet"],
            env=dict(GOOD_ENV),
            connect=leaky_connect,
        )
    finally:
        cli.run_recon = original
    assert code == recon.LeakDetected.exit_code
    assert not out.exists(), "no file may be written when the leak scan trips"
    captured = capsys.readouterr()
    assert "leak_scan" in captured.err
    assert FAKE_PASSWORD not in captured.err
    assert captured.out == ""


# --- output path safety ------------------------------------------------------


def test_out_path_outside_the_repo_is_allowed(recon, tmp_path, cli):
    target = tmp_path / "isaac-db-recon.json"
    assert cli.validate_out_path(str(target)) == target.resolve()


def test_out_path_inside_the_repo_is_refused_when_not_gitignored(recon, cli):
    with pytest.raises(recon.UsageError) as exc:
        cli.validate_out_path(str(REPO_ROOT / "scripts" / "leaky-recon.json"))
    assert exc.value.gate == "out_path"


def test_out_path_inside_the_repo_is_allowed_when_gitignored(recon, cli):
    """``.gitignore`` covers ``examples/*``, so this target is safe."""
    target = REPO_ROOT / "examples" / "db-recon.json"
    assert cli.validate_out_path(str(target)) == target.resolve()
    assert not target.exists(), "validation must not create the file"


def test_out_path_refused_when_git_cannot_prove_it_is_ignored(recon, cli):
    """No proof of ignoring -> refuse. Fail closed."""
    with pytest.raises(recon.UsageError):
        cli.validate_out_path(
            str(REPO_ROOT / "docs" / "x.json"), git_check=lambda root, rel: False
        )


def test_main_writes_the_report_to_an_allowed_out_path(recon, tmp_path, capsys, cli):
    out = tmp_path / "nested" / "recon.json"
    code = cli.main(
        ["--out", str(out), "--id-salt", "s", "--quiet"],
        env=dict(GOOD_ENV),
        connect=lambda env: FakeConnection(base_rows(recon)),
    )
    assert code == 0
    written = json.loads(out.read_text())
    assert written["gates"]["tls"] == "pass"
    assert json.loads(capsys.readouterr().out) == written


def test_main_refuses_a_repo_out_path(recon, capsys, cli):
    code = cli.main(
        ["--out", str(REPO_ROOT / "scripts" / "nope.json"), "--quiet"],
        env=dict(GOOD_ENV),
        connect=lambda env: FakeConnection(base_rows(recon)),
    )
    assert code == recon.UsageError.exit_code
    assert "out_path" in capsys.readouterr().err
    assert not (REPO_ROOT / "scripts" / "nope.json").exists()


# --- missing psycopg2 --------------------------------------------------------


def test_missing_psycopg2_gives_an_actionable_error_not_a_traceback(recon):
    """The driver import is lazy, so an absent driver is a refusal not a crash.

    ``psycopg2-binary`` IS now a declared dependency (the ``api`` extra,
    authorized by ``docs/postgres-test-db-guide.md`` line 58), so the message
    must no longer tell the operator to keep it out of ``pyproject.toml``. It
    must tell them this interpreter is simply missing the extra.
    """
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        pass
    else:  # pragma: no cover - only when the api extra is installed here
        pytest.skip("psycopg2 is installed in this environment")

    with pytest.raises(recon.MissingDependency) as exc:
        recon.connect_psycopg2(GOOD_ENV)
    reason = exc.value.reason
    assert "psycopg2 is not importable" in reason
    assert "pyproject.toml" in reason
    assert "api" in reason  # names the extra to install
    # the retired, now-false instruction must be gone
    assert "Do NOT add it to pyproject.toml" not in reason
    assert "intentionally NOT a project" not in reason
    assert exc.value.exit_code == 5


def test_psycopg2_binary_is_declared_in_the_api_extra():
    """T1: the guide authorizes exactly this dependency, in exactly this extra."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    api_line = next(l for l in text.splitlines() if l.strip().startswith("api = ["))
    assert "psycopg2-binary>=2.9" in api_line


def test_main_reports_missing_psycopg2_as_json_refusal(recon, capsys, cli):
    def boom(env):
        raise recon.MissingDependency("psycopg2 is not installed (test)")

    code = cli.main(["--quiet"], env=dict(GOOD_ENV), connect=boom)
    assert code == 5
    payload = json.loads(capsys.readouterr().err)
    assert payload == {
        "ok": False,
        "refused_gate": "psycopg2_available",
        "reason": "psycopg2 is not installed (test)",
    }


def test_neither_module_imports_psycopg2_at_module_scope(recon):
    """The lazy import is the whole reason this test file runs at all."""
    for path in (SCRIPT, SERVICE):
        source = path.read_text(encoding="utf-8")
        module_level = [
            line for line in source.splitlines() if line.startswith(("import ", "from "))
        ]
        assert not any("psycopg2" in line for line in module_level), path
    service_source = SERVICE.read_text(encoding="utf-8")
    # it IS imported, just not at module scope, and only in the service module
    assert "import psycopg2" in service_source
    assert "import psycopg2" not in SCRIPT.read_text(encoding="utf-8")


def test_connect_refuses_when_libpq_env_is_incomplete(recon, monkeypatch):
    """Reached only if psycopg2 exists; otherwise the dependency gate fires."""
    fake = type("M", (), {"connect": staticmethod(lambda **kw: None)})
    monkeypatch.setitem(__import__("sys").modules, "psycopg2", fake)
    with pytest.raises(recon.ConnectionRefused) as exc:
        recon.connect_psycopg2({"PGDATABASE": "metadata_assistant"})
    assert "PGHOST" in exc.value.reason
    assert exc.value.exit_code == 6


def test_connect_error_reports_only_the_exception_class(recon, monkeypatch):
    def exploding(**kwargs):
        raise RuntimeError(f"FATAL: password authentication failed for {FAKE_HOST}")

    fake = type("M", (), {"connect": staticmethod(exploding)})
    monkeypatch.setitem(__import__("sys").modules, "psycopg2", fake)
    with pytest.raises(recon.ConnectionRefused) as exc:
        recon.connect_psycopg2(GOOD_ENV)
    assert FAKE_HOST not in exc.value.reason
    assert FAKE_PASSWORD not in exc.value.reason
    assert "RuntimeError" in exc.value.reason


def test_connect_pins_the_database_name_rather_than_trusting_env(recon, monkeypatch):
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return "conn"

    fake = type("M", (), {"connect": staticmethod(capture)})
    monkeypatch.setitem(__import__("sys").modules, "psycopg2", fake)
    recon.connect_psycopg2(dict(GOOD_ENV, PGDATABASE="something_else"))
    assert captured["dbname"] == recon.EXPECTED_DATABASE
    assert captured["sslmode"] == "require"
    assert captured["application_name"] == "isaac_db_recon"


# --- determinism -------------------------------------------------------------


def test_output_is_byte_identical_for_identical_input(recon):
    def once():
        return json.dumps(
            recon.run_recon(FakeConnection(base_rows(recon)), env=GOOD_ENV, salt="fixed"),
            indent=2,
            sort_keys=True,
        )

    assert once() == once()


def test_report_carries_no_wall_clock_timestamp(recon):
    assert run_ok(recon)["generated_at"] is None


def test_dict_insertion_order_does_not_change_the_report(recon):
    rows_a = base_rows(recon)
    rows_b = base_rows(recon)
    reordered = []
    for rid, rtype, rdomain, rec in rows_b[recon.Q_RECORDS_PAGE]:
        reordered.append((rid, rtype, rdomain, dict(reversed(list(rec.items())))))
    rows_b[recon.Q_RECORDS_PAGE] = reordered
    a = recon.run_recon(FakeConnection(rows_a), env=GOOD_ENV, salt="f")
    b = recon.run_recon(FakeConnection(rows_b), env=GOOD_ENV, salt="f")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_counted_buckets_is_deterministic_and_merges(recon):
    assert recon.counted_buckets([("b", 1), ("a", 1), ("b", 2)]) == [
        {"value": "b", "count": 3},
        {"value": "a", "count": 1},
    ]


def test_main_rejects_a_zero_max_records(recon, capsys, cli):
    code = cli.main(
        ["--max-records", "0", "--quiet"],
        env=dict(GOOD_ENV),
        connect=lambda env: FakeConnection(base_rows(recon)),
    )
    assert code == recon.UsageError.exit_code
    assert "max_records" in capsys.readouterr().err


def test_main_opt_in_gate_runs_before_any_connection_attempt(recon, capsys, cli):
    attempted = []

    def connect(env):
        attempted.append(True)
        return FakeConnection(base_rows(recon))

    code = cli.main(
        ["--quiet"],
        env={k: v for k, v in GOOD_ENV.items() if k != "ISAAC_RUN_SLAC_DB_RECON"},
        connect=connect,
    )
    assert code == 2
    assert attempted == [], "no socket may be opened before the env gates pass"


def test_main_closes_the_connection(recon, cli):
    conn = FakeConnection(base_rows(recon))
    cli.main(["--id-salt", "s", "--quiet"], env=dict(GOOD_ENV), connect=lambda env: conn)
    assert conn.closed is True


def test_report_documents_its_own_honest_limitations(recon):
    notes = " ".join(run_ok(recon)["notes"])
    assert "BACKSTOP" in notes
    assert "cannot connect to the production records database" in notes
    assert "UNDECIDED" in notes


# --- orchestrator fixes for independent-review findings I3, I4, C2, M ---------
# These cover defects found by the independent safety review and fixed directly
# by the orchestrator (subagents were unavailable). Each asserts the reviewed
# behaviour, not the implementation.


def test_unhandled_exception_never_leaks_its_message(recon, cli):
    """I3: anything not modelled as a refusal bypassed the leak scan entirely."""

    def boom(env):
        raise ValueError("CuO nanopowder 99.99% host=db.internal password=hunter2")

    err, out = io.StringIO(), io.StringIO()
    code = cli.main(
        [],
        env={"ISAAC_RUN_SLAC_DB_RECON": "1", "PGDATABASE": "metadata_assistant"},
        connect=boom,
        stdout=out,
        stderr=err,
    )
    blob = err.getvalue() + out.getvalue()
    assert code == recon.EXIT_UNEXPECTED_ERROR
    for secret in ("CuO nanopowder", "db.internal", "hunter2", "99.99"):
        assert secret not in blob, f"unhandled exception leaked {secret!r}"
    assert "ValueError" in blob  # the class name IS reported — that is the signal
    assert "Traceback" not in blob


def test_unexpected_error_exit_code_is_distinct_from_every_refusal(recon):
    """An operator must be able to tell a gate refusal from a crash."""
    refusal_codes = {
        cls.exit_code
        for cls in vars(recon).values()
        if isinstance(cls, type)
        and issubclass(cls, recon.ReconRefusal)
    }
    assert recon.EXIT_UNEXPECTED_ERROR not in refusal_codes


def test_trailing_newline_cannot_bypass_the_identifier_check(recon):
    """I4: Python's ``$`` matches before a trailing newline; ``\\Z`` does not."""
    declared, open_maps = recon.load_schema_vocabulary(REPO_ROOT)
    # "sample" IS declared, so only the newline can decide this one.
    assert recon.safe_key_segment("sample", "", declared, open_maps) == "sample"
    assert (
        recon.safe_key_segment("sample\n", "", declared, open_maps)
        == recon.MASK_NON_IDENTIFIER
    )
    assert recon.safe_sql_identifier("category\n") == recon.MASK_NON_IDENTIFIER
    # safe_version_value strips first, so a trailing newline is legitimately
    # normalised away rather than masked — assert the real behaviour, not a
    # stricter one it never had. The hardening that matters is in the pattern:
    # under the old ``$`` these would have matched.
    assert recon.safe_version_value("1.05\n") == "1.05"
    assert recon._VERSION_RE.match("1.05\n") is None
    assert recon._LOWER_SLUG_RE.match("technique\n") is None
    assert recon._IDENTIFIER_RE.match("sample\n") is None


def test_out_file_is_written_owner_only(recon, tmp_path, cli):
    target = tmp_path / "recon.json"
    code = cli.main(
        ["--out", str(target), "--id-salt", "test-salt"],
        env=dict(GOOD_ENV),
        connect=lambda env: FakeConnection(base_rows(recon)),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert code == 0
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_sql_identifiers_are_not_filtered_by_the_record_schema_allowlist(recon):
    """Column names come from information_schema, not from the record schema.

    ``category`` and ``term_type`` are real mirrored-portal columns but are NOT
    ISAAC record property names. Routing them through the record allowlist
    masked the entire table and column inventory.
    """
    declared, _ = recon.load_schema_vocabulary(REPO_ROOT)
    assert "category" not in declared  # the premise of this test
    assert recon.safe_sql_identifier("category") == "category"
    assert recon.safe_sql_identifier("vocabulary_cache") == "vocabulary_cache"
    assert recon.safe_sql_identifier("DROP TABLE x") == recon.MASK_NON_IDENTIFIER


def test_schema_pointers_keep_keywords_but_instance_pointers_mask(recon):
    """The two pointer kinds must not share a redaction policy."""
    assert (
        recon.collapse_schema_pointer("/properties/sample/properties/name")
        == "properties/sample/properties/name"
    )
    # An undeclared, non-keyword segment in a SCHEMA pointer means an instance
    # pointer reached the wrong function — fail safe.
    assert recon.MASK_UNDECLARED_KEY in recon.collapse_schema_pointer("/ZZQQ_species")
    # Instance pointers always mask undeclared segments.
    assert recon.collapse_json_pointer("/ZZQQ_species") == recon.MASK_UNDECLARED_KEY


def test_open_map_masking_survives_the_instance_pointer_path(recon):
    """An open-map key must mask in validation paths too, not just structure."""
    collapsed = recon.collapse_instance_path("sample.composition.CuO2_mass_fraction")
    assert "CuO2_mass_fraction" not in collapsed
    assert collapsed == f"sample/composition/{recon.MASK_OPEN_MAP_KEY}"


def test_superuser_gate_fails_closed_on_absent_evidence(recon):
    """I3: the gate accepted "" — what `_scalar` yields for no row or NULL.

    That made it fail OPEN while the module's own posture section says
    "absence of proof is treated as failure", and while `check_tls` three
    functions above correctly refuses a missing row. The report then asserted
    `is_superuser: false` as though it had been observed.
    """
    class _Cur:
        def __init__(self, rows):
            self._rows, self._last = rows, None

        def execute(self, sql, params=None):
            self._last = sql

        def fetchall(self):
            return list(self._rows.get(self._last, []))

        def close(self):
            pass

    def _cursor(superuser_rows):
        return _Cur(
            {
                recon.Q_RECORDS_TABLE_OWNER: [("metadata_assistant",)],
                recon.Q_IS_SUPERUSER: superuser_rows,
                recon.Q_RECORD_COUNT: [(30,)],
            }
        )

    # absence of evidence must REFUSE, not pass
    for label, rows in (("no row", []), ("NULL", [(None,)]), ("empty", [("",)])):
        with pytest.raises(recon.ReconRefusal) as exc:
            recon.check_not_production_shaped(_cursor(rows), 30)
        assert exc.value.gate == "not_production_shaped", label

    # an actual superuser still refuses
    with pytest.raises(recon.ReconRefusal):
        recon.check_not_production_shaped(_cursor([("on",)]), 30)

    # and a positively-observed non-superuser passes, reporting what it SAW
    result = recon.check_not_production_shaped(_cursor([("off",)]), 30)
    assert result["is_superuser_observed"] == "off"


def test_report_does_not_claim_unconditional_determinism(recon):
    """I5: the default salt is random per run, so digests differ every time."""
    notes = " ".join(run_ok(recon)["notes"])
    assert "--id-salt" in notes and "random per run" in notes
    # and the claim it replaced must be gone
    assert "identical input yields byte-identical output (and no host" not in notes


def test_report_does_not_claim_counts_only(recon):
    """I4: verbatim server/TLS strings and vocabulary slugs ARE emitted."""
    report = run_ok(recon)
    notes = " ".join(report["notes"])
    assert "not literally 'counts only'" in notes
    # the claim is now true of what the report actually contains
    assert report["connection"]["server_version"]  # a verbatim server string
