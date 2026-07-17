import './screens.css';
import { useCallback, useState } from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Network, ChevronDown, ChevronRight } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type {
  ApiGraphStatus,
  ApiMemoryFileResponse,
  ApiMemoryFileSummary,
} from '../lib/types';

/**
 * Project Memory — a deliberately separate destination from the experiment queue
 * (never blended into S1). This is the memory/query plane (Graphify + docs);
 * it returns leads to verify, never verdicts.
 *
 * The status detail card below is driven entirely by the live
 * `GET /api/graph/status` response — every figure it renders comes from that
 * response; anything the endpoint does not return is omitted, never defaulted.
 *
 * P24.4 adds the Source Index card below: the served-allowlist file list from
 * `GET /api/memory/files`, with a lazy per-row provenance detail fetched from
 * `GET /api/memory/file?path=`. It is a provenance navigator, not a file
 * browser or content viewer — no file bytes are ever fetched or rendered.
 * P24.5 (concept lookup) is a separate, later slice.
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
        {/* Skip the second fetch when the screen already knows the backend is
            unreachable — one screen-level BackendDown, not two, mirroring how
            P24.3 owns that state for the whole page. */}
        {graph.status !== 'error' && <SourceIndexCard />}
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

// --- Source Index card (P24.4) --------------------------------------------
// A provenance navigator over the served-allowlist files Graphify indexed —
// NOT a file browser, NOT a content viewer. `local_reference` is inert text;
// nothing here ever fetches or renders file bytes.

function SourceIndexCard() {
  const list = useFetch(() => api.getMemoryFiles(), []);
  return (
    <div className="card placeholder-card source-index-card">
      <h3 className="source-index-heading">Source Index</h3>
      <p className="source-index-subtitle">
        Files Graphify indexed for project memory — metadata and provenance only, never file
        contents.
      </p>
      {list.status === 'loading' && <LoadingPanel label="Loading source index…" />}
      {list.status === 'error' && <BackendDown error={list.error} onRetry={list.reload} />}
      {list.status === 'data' && (
        <SourceIndexList available={list.data.available} files={list.data.files} />
      )}
    </div>
  );
}

interface SourceIndexListProps {
  available: boolean;
  files: ApiMemoryFileSummary[];
}

/**
 * The row list, grouped by `file_type` (never by community — 214 communities
 * is far too many groups; community is per-row context instead). Only one
 * row's provenance panel is open at a time (accordion); a related-file lead
 * inside an open panel can activate a different row the same way a click on
 * that row would.
 */
function SourceIndexList({ available, files }: SourceIndexListProps) {
  const [expandedPath, setExpandedPath] = useState<string | null>(null);

  const toggle = useCallback((path: string) => {
    setExpandedPath((current) => (current === path ? null : path));
  }, []);
  const activate = useCallback((path: string) => {
    setExpandedPath(path);
  }, []);

  if (!available) {
    return (
      <p className="source-index-unavailable">
        Source Index is unavailable — the memory graph is not present on this backend (see
        Project memory status above).
      </p>
    );
  }

  const groups = groupFilesByType(files);

  return (
    <>
      <div className="source-index-groups">
        {groups.map((group) => {
          const headingId = domId('si-group', group.key);
          return (
            <div className="source-index-group" key={group.key}>
              <h4 id={headingId} className="source-index-group-heading">
                {group.label}
                <span className="source-index-group-count">{group.files.length}</span>
              </h4>
              <ul className="source-index-rows" aria-labelledby={headingId}>
                {group.files.map((file) => (
                  <SourceIndexRow
                    key={file.path}
                    file={file}
                    expanded={expandedPath === file.path}
                    onToggle={() => toggle(file.path)}
                    onActivateFile={activate}
                  />
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      <p className="source-index-caption">project knowledge — not scientific evidence</p>
    </>
  );
}

interface SourceIndexRowProps {
  file: ApiMemoryFileSummary;
  expanded: boolean;
  onToggle: () => void;
  onActivateFile: (path: string) => void;
}

function SourceIndexRow({ file, expanded, onToggle, onActivateFile }: SourceIndexRowProps) {
  const panelId = domId('si-panel', file.path);
  const community = communityLabel(file);
  const Chevron = expanded ? ChevronDown : ChevronRight;

  // Keyboard accessibility comes from the native <button>: real browsers
  // synthesize a click from Enter (keydown) and Space (keyup), so onClick
  // alone covers pointer and keyboard activation. No custom onKeyDown — a
  // duplicate handler would double-toggle (open, then the native synthesized
  // click immediately closes) for keyboard users.
  return (
    <li className="source-index-row">
      <button
        type="button"
        className="source-index-row-btn"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <Chevron className="source-index-chevron" size={14} strokeWidth={2} aria-hidden="true" />
        <span className="source-index-path mono">{file.path}</span>
        <span className="source-index-meta">
          {community && <span className="source-index-community">{community}</span>}
          <span className="source-index-nodecount">{nodeCountLabel(file.node_count)}</span>
          {!file.on_disk && <span className="source-index-badge">not on disk</span>}
        </span>
      </button>
      {expanded && (
        <div id={panelId} className="source-index-panel">
          <SourceIndexPanelBody path={file.path} onActivateFile={onActivateFile} />
        </div>
      )}
    </li>
  );
}

function SourceIndexPanelBody({
  path,
  onActivateFile,
}: {
  path: string;
  onActivateFile: (path: string) => void;
}) {
  const detail = useFetch(() => api.getMemoryFile(path), [path]);
  return (
    <>
      {detail.status === 'loading' && <LoadingPanel label="Loading provenance…" />}
      {detail.status === 'error' && (
        <div className="source-index-panel-error">
          <p>Could not load provenance for this file.</p>
          <button type="button" className="btn btn-secondary" onClick={detail.reload}>
            Retry
          </button>
        </div>
      )}
      {detail.status === 'data' && (
        <SourceIndexDetail data={detail.data} onActivateFile={onActivateFile} />
      )}
    </>
  );
}

function SourceIndexDetail({
  data,
  onActivateFile,
}: {
  data: ApiMemoryFileResponse;
  onActivateFile: (path: string) => void;
}) {
  if (!data.available || !data.file) {
    return (
      <p className="source-index-panel-note">
        Source Index is unavailable — the memory graph is not present on this backend.
      </p>
    );
  }
  const { file, related, rationales } = data;
  const community = communityLabel(file);

  return (
    <div className="source-index-detail">
      <dl className="source-index-panel-figures">
        <div className="source-index-panel-figure">
          <dt>Type</dt>
          <dd>{humanizeFileType(file.file_type)}</dd>
        </div>
        <div className="source-index-panel-figure">
          <dt>Community</dt>
          <dd>{community ?? '—'}</dd>
        </div>
        <div className="source-index-panel-figure">
          <dt>Nodes</dt>
          <dd className="mono">{file.node_count}</dd>
        </div>
      </dl>

      {file.on_disk ? (
        <p className="source-index-local-ref">
          <span className="source-index-local-ref-label">local reference — open in your editor</span>
          <span className="mono">{file.local_reference}</span>
        </p>
      ) : (
        <p className="source-index-local-ref source-index-local-ref-missing">
          not present locally — cannot open
        </p>
      )}

      <div className="source-index-section">
        <h5 className="source-index-section-heading">Why memory draws on this file</h5>
        {rationales.length > 0 ? (
          <ul className="source-index-rationale-list">
            {rationales.map((rationale, i) => (
              <li key={i}>{rationale}</li>
            ))}
          </ul>
        ) : (
          <p className="source-index-empty-note">no recorded leads for this file</p>
        )}
      </div>

      <div className="source-index-section">
        <h5 className="source-index-section-heading">Related files</h5>
        {related.files.length > 0 ? (
          <ul className="source-index-related-list">
            {related.files.map((rf) => (
              <li key={rf.path}>
                <button
                  type="button"
                  className="source-index-related-link"
                  onClick={() => onActivateFile(rf.path)}
                >
                  <span className="mono">{rf.path}</span>
                  {rf.relation && <span className="source-index-relation">{rf.relation}</span>}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="source-index-empty-note">no recorded leads for this file</p>
        )}
      </div>

      <div className="source-index-section">
        <h5 className="source-index-section-heading">Related concepts</h5>
        {related.concepts.length > 0 ? (
          <ul className="source-index-related-list">
            {related.concepts.map((rc) => (
              <li key={rc.id}>
                <span className="source-index-concept-label">{rc.label ?? rc.id}</span>
                {rc.relation && <span className="source-index-relation">{rc.relation}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="source-index-empty-note">no recorded leads for this file</p>
        )}
      </div>
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

interface SourceIndexGroup {
  key: string;
  label: string;
  files: ApiMemoryFileSummary[];
}

/**
 * Group rows by `file_type`, humanized for display — never by community
 * (real data has 214 communities, far too many groups for a plain list;
 * community renders as per-row context instead). Within a group, rows sort
 * by `path`; groups sort alphabetically by their humanized label.
 */
function groupFilesByType(files: ApiMemoryFileSummary[]): SourceIndexGroup[] {
  const byType = new Map<string, ApiMemoryFileSummary[]>();
  for (const file of files) {
    const key = file.file_type ?? '__none__';
    const bucket = byType.get(key);
    if (bucket) bucket.push(file);
    else byType.set(key, [file]);
  }
  const groups = Array.from(byType.entries()).map(([key, groupFiles]) => ({
    key,
    label: humanizeFileType(key === '__none__' ? null : key),
    files: [...groupFiles].sort((a, b) => a.path.localeCompare(b.path)),
  }));
  groups.sort((a, b) => a.label.localeCompare(b.label));
  return groups;
}

/**
 * Humanize a real `file_type` value for a group heading. `null` (a served
 * file with no graph nodes of its own kind) becomes the honest "Other" —
 * never a fabricated specific type.
 */
function humanizeFileType(fileType: string | null): string {
  if (fileType === null) return 'Other';
  if (fileType === 'code') return 'Code';
  if (fileType === 'document') return 'Documents';
  return fileType.charAt(0).toUpperCase() + fileType.slice(1);
}

/**
 * `community_name` when present; else the honest fallback "community <id>"
 * when only `community_id` is known; else `null` (never an invented name).
 */
function communityLabel(file: {
  community_id: string | null;
  community_name: string | null;
}): string | null {
  if (file.community_name) return file.community_name;
  if (file.community_id) return `community ${file.community_id}`;
  return null;
}

function nodeCountLabel(nodeCount: number): string {
  return `${nodeCount} node${nodeCount === 1 ? '' : 's'}`;
}

/** A DOM-id-safe token derived from a repo-relative path (for aria-controls / aria-labelledby). */
function domId(prefix: string, raw: string): string {
  return `${prefix}-${raw.replace(/[^a-zA-Z0-9]+/g, '-')}`;
}
