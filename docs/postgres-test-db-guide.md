# Postgres database guide

isaac-metadata-assistant has its own Postgres database on the in-cluster ISAAC
CloudNativePG cluster. The app owns it: its schema, its rows, its reads and writes. It is
isolated from the production ISAAC records database, and it is seeded with a sample of real
record data so the app can work against the real thing.

**You do not need Kubernetes access, a kubeconfig, or credentials to write code against
it.** The deployment already carries the standard libpq environment variables, so the normal
cycle -- push to `main`, GitHub Actions builds the image, Flux deploys it -- lands your code
in a pod where the database is reachable. Write against the environment contract below and
verify in the deployed app. The port-forward section near the end is an optional convenience
for whoever already holds a SLAC cluster context; nothing else in this guide depends on it.

## What exists

- A database named `metadata_assistant` on the in-cluster CloudNativePG Postgres
  cluster (Postgres 18), owned by the least-privilege login role `metadata_assistant`.
- The schema is identical to the production ISAAC records database (the
  isaac-ai-ready-record portal's DB): `records`, `record_history`, `templates`,
  `vocabulary_cache`, `vocabulary_sync_log`, `vocabulary_proposals`, `api_requests`,
  `portal_access_log`, plus the `update_updated_at_column()` trigger on `templates`.
- Seed data: the 30 earliest real records from production (by `created_at`), plus
  the full production `vocabulary_cache` contents so vocabulary validation can run
  against real terms.
- The database is isolated from production. The `metadata_assistant` role's only pg_hba
  grant is `hostssl metadata_assistant metadata_assistant ... scram-sha-256` -- it has no
  grant into any other database on the cluster, so it cannot reach the production records
  DB at all. Inside its own database it is the owner: read, write, add tables, migrate the
  schema. Nothing done here can affect production.

Two separate questions, worth not conflating: the app may **write** whatever it needs to,
but the seeded rows are real production-derived records, so what the hosted app
**displays** is a separate decision -- see [Displaying record content](#displaying-record-content).

## Connection

The deployment already carries the standard libpq environment variables, so DB code
can rely on them being present in the pod:

| Env var | Value |
|---|---|
| `PGHOST` | `isaac-psql-rw.isaac-psql.svc.cluster.local` |
| `PGPORT` | `5432` |
| `PGDATABASE` | `metadata_assistant` |
| `PGUSER` | from Secret `metadata-assistant-db-app` (value: `metadata_assistant`) |
| `PGPASSWORD` | from Secret `metadata-assistant-db-app` |

Auth is SCRAM-SHA-256 over TLS, enforced server-side by `hostssl`: a connection either gets
TLS or is refused. Treat `PGHOST` being set as the feature switch (DB configured or not), so
the app still runs in environments without a database.

### The driver is not installed yet

Add it to the `api` extra in `pyproject.toml`:

```toml
api = ["fastapi>=0.110", "uvicorn>=0.29", "httpx>=0.27", "psycopg2-binary>=2.9"]
```

The Dockerfile's only install step is `pip install --no-cache-dir ".[api]"`, so a dependency
that is not declared there is absent from the image regardless of what the code imports.
This dependency is authorized -- add it in the same slice as the first DB code.

Example connection (matching the conventions of the existing ISAAC portal code):

```python
import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        database=os.environ.get("PGDATABASE", "metadata_assistant"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        cursor_factory=RealDictCursor,  # rows come back as dicts
    )
```

### Optional: local port-forward

Only relevant if you already have a SLAC cluster context. This is a convenience for poking
at the database by hand, not a prerequisite for writing or verifying code.

From a shell with cluster access:

```bash
kubectl port-forward -n isaac-psql svc/isaac-psql-rw 5432:5432
```

then export the five `PG*` variables pointing at `localhost` (get the password from
the `metadata-assistant-db-app` Secret in the `metadata-assistant` namespace). Without
the env set, the app should behave as it does today (no DB).

## The records table

```sql
CREATE TABLE records (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id CHAR(26) UNIQUE NOT NULL,
    record_type VARCHAR(50) NOT NULL,
    record_domain VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Indexes exist on `record_id`, `record_type`, `record_domain`, `created_at`, and a GIN
index on `data`.

`data` holds the complete ISAAC AI-Ready Record JSON document, written by the
isaac-ai-ready-record portal against v1.05 -- the same version this repo vendors as
`schema/isaac_record_v1.json`. `record_id`, `record_type`, and `record_domain` are
denormalized copies of the corresponding JSON fields, kept in sync on write.

Whether every seeded record passes the vendored schema is expected but **unverified**: that
schema is `additionalProperties: false` at the root and in dozens of nested places, so any
drift in the portal's writers shows up as a validation failure rather than being tolerated.
Finding drift is a useful result, not a problem with the database -- report it rather than
working around it.

Gotchas to code around:

- `id` is `GENERATED ALWAYS AS IDENTITY`: never supply it on INSERT.
- `record_id` is `CHAR(26)` (a ULID) and Postgres blank-pads fixed-width columns:
  call `.strip()` on every `record_id` read back from the database.
- Some sampled records contain `data->'links'` entries referencing `record_id`s that
  are not part of the 30-row sample. There are no foreign keys, so nothing breaks;
  a lookup of a dangling link simply returns no row.
- Always parameterize SQL (`%s` placeholders); never string-format values into
  queries.

## Constraints of the role

`metadata_assistant` owns the database and its `public` schema, so it can freely
create and alter tables, indexes, sequences, and plpgsql trigger functions -- adding
app-specific tables next to the mirrored schema is fine.

It is NOSUPERUSER / NOCREATEDB / NOCREATEROLE and cannot `CREATE EXTENSION`. The
mirrored schema needs no extensions (JSONB, GIN, and plpgsql are built in); if an
extension is ever needed, ask the cluster admin to install it once.

The role has a small connection limit (5). Open connections per request or use a
small pool; do not hold many idle connections.

## Displaying record content

Writing to this database is unrestricted. Rendering its rows in the hosted app is not, because
the seeded records are production-derived.

Hosted display of per-record content is **closed by default** pending an explicit visibility
decision. Aggregate output -- record counts, counts by type and domain, validation totals,
schema version, database reachability -- is fine to build and show now. Per-record fields
(titles, scientific values, evidence, full JSON) need the visibility decision first, so build
any read path with that boundary in it rather than adding the gate afterwards.

Note that `PGHOST` is already set in the deployed pod, so anything placed behind the
"DB configured" switch goes live on the next image roll. Decide the boundary before shipping
the read path, not after.
