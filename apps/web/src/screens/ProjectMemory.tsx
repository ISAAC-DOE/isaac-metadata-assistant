import './screens.css';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Network } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type { ApiGraphStatus } from '../lib/types';

/**
 * Project Memory — a deliberately separate destination from the experiment queue
 * (never blended into S1). This is the memory/query plane (Graphify + docs);
 * it returns leads to verify, never verdicts.
 *
 * The status detail card below is driven entirely by the live
 * `GET /api/graph/status` response — every figure it renders comes from that
 * response; anything the endpoint does not return is omitted, never defaulted.
 *
 * P24.4 (source/file explorer) and P24.5 (concept lookup) are separate, later
 * slices that add more `.card` sections below this one — this card stays
 * self-contained so those can be added without reworking it.
 */
export function ProjectMemory() {
  const graph = useFetch(() => api.getGraphStatus(), []);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="memory" />}
      mainPad="pad"
    >
      <div className="placeholder">
        <span className="eyebrow">Memory / Query Plane</span>
        <h2>{LABELS.navMemory}</h2>
        <p>
          Project Memory is the assistant's memory and navigation surface — Graphify plus project
          docs. It is deliberately separate from the experiment queue and never appears inside it. It
          surfaces related records, prior documents, and "how is this connected?" answers as leads to
          verify — it never validates, completes, or supplies a value.
        </p>
        <div className="card placeholder-card">
          {graph.status === 'loading' && <LoadingPanel label="Checking memory status…" />}
          {graph.status === 'error' && <BackendDown error={graph.error} onRetry={graph.reload} />}
          {graph.status === 'data' && <MemoryStatusDetail data={graph.data} />}
        </div>
        <p style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-tertiary)' }}>
          <Network size={15} strokeWidth={2} aria-hidden="true" />
          Browse depth is out of scope for this first build.
        </p>
      </div>
    </AppShell>
  );
}

// --- status detail card --------------------------------------------------

function MemoryStatusDetail({ data }: { data: ApiGraphStatus }) {
  const available = data.status === 'fresh' || data.status === 'stale';

  return (
    <>
      <GraphStatusChip status={data.status} note={data.note} />
      {available ? (
        <>
          <p>
            Graphify is a memory plane, not a truth plane — every lead points back to a cited file
            to confirm.
          </p>
          {data.status === 'stale' && (
            <p className="memory-stale-note">
              Memory may be out of date — re-verify against the cited files.
            </p>
          )}
          <MemoryFigures data={data} />
          <p className="memory-indexed-note">
            Project memory indexes this project's source code, docs, schema, and test fixtures via
            Graphify — metadata and provenance only, never file contents.
          </p>
        </>
      ) : (
        <MemoryUnavailablePanel />
      )}
    </>
  );
}

interface FigureRow {
  label: string;
  value: string;
  mono?: boolean;
}

/** Only figures the live response actually returned — nothing is ever defaulted. */
function MemoryFigures({ data }: { data: ApiGraphStatus }) {
  const rows: FigureRow[] = [];
  if (data.node_count != null) rows.push({ label: 'Nodes', value: String(data.node_count), mono: true });
  if (data.edge_count != null) rows.push({ label: 'Edges', value: String(data.edge_count), mono: true });
  if (data.community_count != null) {
    rows.push({ label: 'Communities', value: String(data.community_count), mono: true });
  }
  if (data.file_count != null) {
    rows.push({ label: 'Indexed files', value: String(data.file_count), mono: true });
  }
  if (data.concept_count != null) {
    rows.push({ label: 'Concepts', value: String(data.concept_count), mono: true });
  }
  if (data.built_at_commit != null) {
    rows.push({ label: 'Built at commit', value: shortSha(data.built_at_commit), mono: true });
  }
  // No invented timestamps: the age line is derived from the shipped age
  // signal (`graph_mtime`) only, and is omitted entirely when it is absent.
  if (data.graph_mtime != null) {
    rows.push({ label: 'Age', value: formatGraphAge(data.graph_mtime) });
  }

  if (rows.length === 0) return null;

  return (
    <dl className="memory-figures">
      {rows.map((row) => (
        <div className="memory-figure" key={row.label}>
          <dt>{row.label}</dt>
          <dd className={row.mono ? 'mono' : undefined}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The honest degraded panel for `status:"missing"` — covers hosted (no graph
 * shipped), local-no-graph, and unreadable-graph alike. Not an error state:
 * no red, no counts, no fake placeholders.
 */
function MemoryUnavailablePanel() {
  return (
    <div className="memory-unavailable">
      <p className="memory-unavailable-title">
        Project memory is unavailable on this backend — the memory graph artifacts are not
        present.
      </p>
      <p className="memory-unavailable-text">
        The hosted demo does not currently ship the Graphify graph artifacts; when run locally
        against local artifacts, Project Memory works.
      </p>
      <p className="memory-unavailable-text">
        Future path: hosted Project Memory is designed to be wired later to an approved source —
        a sanitized graph snapshot, a database-backed memory index, or an institution-hosted
        memory service behind login.
      </p>
    </div>
  );
}

// --- pure helpers (derived only from the live response; no invented values) --

/** First 7 characters, the conventional "short sha" length — never truncates a shorter string. */
function shortSha(commit: string): string {
  return commit.length > 7 ? commit.slice(0, 7) : commit;
}

/** Human-readable relative age from the shipped `graph_mtime` (epoch seconds). */
function formatGraphAge(mtimeSeconds: number): string {
  const diffSec = Math.max(0, Math.round(Date.now() / 1000 - mtimeSeconds));
  if (diffSec < 90) return 'built moments ago';
  const minutes = Math.round(diffSec / 60);
  if (minutes < 90) return `built ${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.round(diffSec / 3600);
  if (hours < 36) return `built ${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(diffSec / 86400);
  if (days < 45) return `built ${days} day${days === 1 ? '' : 's'} ago`;
  const months = Math.round(diffSec / (86400 * 30));
  return `built ${months} month${months === 1 ? '' : 's'} ago`;
}
