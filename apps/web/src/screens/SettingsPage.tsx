import './screens.css';
import { useMemo, useState, type ReactNode } from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, Search, ChevronRight } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type {
  ApiAboutResponse,
  ApiOpenApiResponse,
  OpenApiMethod,
  OpenApiParameter,
} from '../lib/types';

/**
 * Settings — P36.4 gives this stub two functional sections: Help / About
 * (live app metadata + the truth/memory authority boundary) and API
 * Documentation (a searchable reference generated from the REAL running
 * OpenAPI contract, never a hand-maintained duplicate description). Both are
 * read-only; neither mutates anything. The "local · offline · no telemetry"
 * framing from the original stub is kept.
 */
export function SettingsPage() {
  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="settings" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Local Configuration</span>
        <h1>{LABELS.navSettings}</h1>
        <p>
          Local, offline settings only — no telemetry, no analytics, no cloud sync. The data regime
          is fixed to synthetic in this build.
        </p>
        <div className="card placeholder-card">
          <span className="mono" style={{ fontSize: 12, color: 'var(--text-slate)' }}>
            {LABELS.version}
          </span>
          <p>local · offline · no telemetry</p>
        </div>

        <HelpAboutCard />
        <ApiDocsCard />
      </div>
    </AppShell>
  );
}

// --- Help / About (P36.4) --------------------------------------------------

const IN_REPO_DOCS = [
  'CLAUDE.md',
  'AGENTS.md',
  'README.md',
  'docs/mentor-brief.md',
  'schema/PROVENANCE.md',
];

function HelpAboutCard() {
  const about = useFetch(() => api.getAbout(), []);
  return (
    <section className="card placeholder-card settings-card" aria-labelledby="settings-about-heading">
      <header className="settings-card-head">
        <CircleHelp size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
        <div>
          <h2 id="settings-about-heading">Help / About</h2>
          <p className="settings-card-sub">
            App identity and provenance — and where truth ends and memory/advisory help begins.
          </p>
        </div>
      </header>

      {about.status === 'loading' && <LoadingPanel label="Loading app info…" />}
      {about.status === 'error' && <BackendDown error={about.error} onRetry={about.reload} />}
      {about.status === 'data' && <AboutDetail data={about.data} />}
    </section>
  );
}

function shortCommit(commit: string | null): string {
  if (!commit) return 'not set';
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

function AboutDetail({ data }: { data: ApiAboutResponse }) {
  const rows: { label: string; value: ReactNode }[] = [
    { label: 'App version', value: <span className="mono">{data.app_version}</span> },
    {
      label: 'Build commit',
      value: data.build_commit ? (
        <span className="settings-commit">
          <span className="mono settings-commit-short">{shortCommit(data.build_commit)}</span>
          {data.build_commit.length > 12 && (
            <span className="mono settings-commit-full">{data.build_commit}</span>
          )}
        </span>
      ) : (
        <span className="settings-commit-note">not set (no build identity injected)</span>
      ),
    },
    { label: 'ISAAC record schema', value: <span className="mono">v{data.record_schema_version}</span> },
    { label: 'Runtime mode', value: <span className="mono">{data.runtime_mode}</span> },
    { label: 'Data regime', value: <span className="mono">{data.data_regime}</span> },
    { label: 'Persistence', value: <span className="mono">{data.persistence}</span> },
    { label: 'Core', value: <span className="mono">{data.core}</span> },
  ];
  return (
    <>
      <dl className="settings-figures">
        {rows.map((row) => (
          <div className="settings-figure" key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>

      <div className="settings-provenance-note">
        <p>
          <strong>Truth vs. memory.</strong> Record validity, export, and audit are decided ENTIRELY
          by the deterministic core (the official ISAAC v{data.record_schema_version} schema, the
          draft validator, and the export/audit pipeline) — never by the assistant or by Project
          Memory. Graphify and the assistant are the memory/query plane: they surface leads,
          context, and provenance to verify, but they cannot mark a record valid, mutate it, or
          authorize export.
        </p>
        <p>
          <strong>No-guessing.</strong> Every finalized field carries either cited evidence or an
          explicit user confirmation — nothing scientific is invented. This build's data regime is
          synthetic-only; real experiment data requires separate, explicit governance approval.
        </p>
      </div>

      <div className="settings-docs-note">
        <p className="settings-docs-label">In-repository documentation</p>
        <ul className="settings-docs-list">
          {IN_REPO_DOCS.map((doc) => (
            <li key={doc}>
              <code className="mono">{doc}</code>
            </li>
          ))}
        </ul>
        <p className="settings-docs-caption">
          Tracked in the repository, not served as pages by this app.
        </p>
      </div>
    </>
  );
}

// --- API Documentation (P36.4) ----------------------------------------------

interface ApiDocRow {
  method: OpenApiMethod;
  path: string;
  group: string;
  summary?: string;
  description?: string;
  parameters: OpenApiParameter[];
}

const METHOD_ORDER: OpenApiMethod[] = ['get', 'post', 'put', 'delete'];

/** The path segment right after `/api/` (or the first non-parameter segment
 * when that marker is absent) — a deterministic, no-guessing grouping key
 * derived straight from the real schema, never a hand-maintained tag map
 * (this backend does not assign OpenAPI `tags`). */
function deriveGroup(path: string): string {
  const marker = '/api/';
  const idx = path.indexOf(marker);
  const rest = idx >= 0 ? path.slice(idx + marker.length) : path.replace(/^\/+/, '');
  const segment = rest.split('/').find((s) => s.length > 0 && !s.startsWith('{'));
  return segment ?? 'root';
}

function flattenOpenApi(schema: ApiOpenApiResponse): ApiDocRow[] {
  const rows: ApiDocRow[] = [];
  for (const [path, item] of Object.entries(schema.paths ?? {})) {
    for (const method of METHOD_ORDER) {
      const op = item?.[method];
      if (!op) continue;
      rows.push({
        method,
        path,
        group: deriveGroup(path),
        summary: op.summary,
        description: op.description,
        parameters: op.parameters ?? [],
      });
    }
  }
  rows.sort(
    (a, b) =>
      a.group.localeCompare(b.group) ||
      a.path.localeCompare(b.path) ||
      a.method.localeCompare(b.method),
  );
  return rows;
}

function groupRows(rows: ApiDocRow[]): { key: string; rows: ApiDocRow[] }[] {
  const groups: { key: string; rows: ApiDocRow[] }[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.key === row.group) last.rows.push(row);
    else groups.push({ key: row.group, rows: [row] });
  }
  return groups;
}

function ApiDocsCard() {
  const openapi = useFetch(() => api.getOpenApi(), []);
  return (
    <section className="card placeholder-card settings-card" aria-labelledby="settings-apidocs-heading">
      <header className="settings-card-head">
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
        <div>
          <h2 id="settings-apidocs-heading">API Documentation</h2>
          <p className="settings-card-sub">
            Generated live from this app's own OpenAPI contract — the exact routes an authenticated
            caller can reach, never a hand-maintained duplicate.
          </p>
        </div>
      </header>

      {openapi.status === 'loading' && <LoadingPanel label="Loading API documentation…" />}
      {openapi.status === 'error' && <BackendDown error={openapi.error} onRetry={openapi.reload} />}
      {openapi.status === 'data' && <ApiDocsBody schema={openapi.data} />}
    </section>
  );
}

function ApiDocsBody({ schema }: { schema: ApiOpenApiResponse }) {
  const [query, setQuery] = useState('');
  const rows = useMemo(() => flattenOpenApi(schema), [schema]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) => r.path.toLowerCase().includes(q) || (r.summary ?? '').toLowerCase().includes(q),
    );
  }, [rows, query]);

  const groups = useMemo(() => groupRows(filtered), [filtered]);

  return (
    <>
      <div className="settings-search" role="search">
        <label className="settings-search-label" htmlFor="api-docs-search">
          Search endpoints
        </label>
        <div className="settings-search-input-wrap">
          <Search size={14} strokeWidth={2.2} aria-hidden="true" className="settings-search-icon" />
          <input
            id="api-docs-search"
            type="search"
            className="settings-search-input"
            placeholder="Filter by path or summary…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <p className="settings-doc-count" aria-live="polite">
        {filtered.length} of {rows.length} endpoint{rows.length === 1 ? '' : 's'}
      </p>

      {groups.length === 0 && (
        <p className="settings-doc-empty">No endpoints match "{query}".</p>
      )}

      <div className="api-docs-groups">
        {groups.map((group) => (
          <div className="api-docs-group" key={group.key}>
            <h3 className="api-docs-group-heading">
              {group.key}
              <span className="api-docs-group-count">{group.rows.length}</span>
            </h3>
            <ul className="api-docs-rows">
              {group.rows.map((row) => (
                <ApiDocRowItem key={`${row.method}:${row.path}`} row={row} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}

function ApiDocRowItem({ row }: { row: ApiDocRow }) {
  return (
    <li className="api-docs-row">
      <details>
        <summary className="api-docs-row-summary">
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" className="api-docs-row-chevron" />
          <span className={`api-docs-method api-docs-method-${row.method}`}>
            {row.method.toUpperCase()}
          </span>
          <code className="mono api-docs-path">{row.path}</code>
          {row.summary && <span className="api-docs-summary-text">{row.summary}</span>}
        </summary>
        <div className="api-docs-row-body">
          {row.description && <p className="api-docs-description">{row.description}</p>}
          {row.parameters.length > 0 ? (
            <div className="api-docs-params-wrap">
              <table className="api-docs-params">
                <caption className="sr-only">Parameters</caption>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">In</th>
                    <th scope="col">Required</th>
                  </tr>
                </thead>
                <tbody>
                  {row.parameters.map((p) => (
                    <tr key={p.name}>
                      <td className="mono">{p.name}</td>
                      <td>{p.in}</td>
                      <td>{p.required ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="api-docs-no-params">No parameters.</p>
          )}
        </div>
      </details>
    </li>
  );
}
