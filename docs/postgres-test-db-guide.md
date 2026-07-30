# Postgres test database guide

A standalone Postgres test database is provisioned for isaac-metadata-assistant so the
app can start testing reads and uploads of real ISAAC record data. This guide covers
what exists, how to connect, and the conventions to follow when writing DB code.

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
- This DB is fully isolated from production. The `metadata_assistant` role cannot
  connect to the production records database at all. Everything here is disposable
  test data: write, mutate, and drop freely.

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

Auth is SCRAM-SHA-256 over TLS. Treat `PGHOST` being set as the feature switch
(DB configured or not), so the app still runs in environments without a database.

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

### Local development

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

`data` holds the complete ISAAC AI-Ready Record v1.05 JSON document -- the same
schema this repo already vendors and validates against (`schema/isaac_record_v1.json`).
`record_id`, `record_type`, and `record_domain` are denormalized copies of the
corresponding JSON fields, kept in sync on write.

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
