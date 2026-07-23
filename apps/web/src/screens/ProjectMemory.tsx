import './screens.css';
import '../components/assistant.css';
import { useCallback, useEffect, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { AssistantPanel } from '../components/AssistantPanel';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { Network, ChevronDown, ChevronRight } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import { useFetch } from '../lib/useFetch';
import type {
  ApiGraphStatus,
  ApiMemoryConceptResponse,
  ApiMemoryConceptSummary,
  ApiMemoryFileResponse,
  ApiMemoryFileSummary,
  MemoryConsistency,
  SnapshotIntegrity,
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
 *
 * P24.5 adds the Concept Lookup card: the 19 curated concepts Graphify
 * anchored in project docs, from `GET /api/memory/concepts`, with a lazy
 * per-concept provenance detail from `GET /api/memory/concepts/{id}`. This is
 * the last UI slice for Phase 24 — nothing beyond concepts is built here.
 */
// P33 S3 (D6) — the three internal sections of Project Memory. These are LOCAL
// page tabs (never added to the global LeftNav): Overview carries the memory
// health/status, Sources holds the Source Index, Concepts holds the Concept
// Lookup. The grounded assistant lives in the right rail across ALL three.
type MemoryTab = 'overview' | 'sources' | 'concepts';

const MEMORY_TABS: { id: MemoryTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'sources', label: 'Sources' },
  { id: 'concepts', label: 'Concepts' },
];

const tabId = (id: MemoryTab) => `memory-tab-${id}`;
const panelId = (id: MemoryTab) => `memory-tabpanel-${id}`;

export function ProjectMemory() {
  const graph = useFetch(() => api.getGraphStatus(), []);

  // P26.5: deep-link readers so the ⌘K search palette's memory results actually
  // land somewhere. `?concept=<id>` auto-opens that concept in Concept Lookup;
  // `?file=<path>` auto-opens that file in the Source Index. Both reuse each
  // card's existing accordion expand/fetch mechanics — nothing new is fetched.
  const [params] = useSearchParams();
  const focusConceptId = params.get('concept');
  const focusFilePath = params.get('file');

  // P33 S3 (D6): a deep link selects the tab that owns the target — `?file=`
  // lands on Sources, `?concept=` on Concepts — so the auto-opened item is
  // visible on arrival; otherwise the page opens on Overview.
  const [activeTab, setActiveTab] = useState<MemoryTab>(
    focusFilePath ? 'sources' : focusConceptId ? 'concepts' : 'overview',
  );

  // A ⌘K jump to a memory item navigates /memory → /memory?file=… / ?concept=…
  // — the SAME route, so React Router never remounts this screen and the
  // once-per-mount initializer above cannot react to it. Sync the owning tab
  // whenever a deep-link param becomes present, so an in-page jump still selects
  // (and thus mounts) the target card. It ONLY forces a tab when a param exists —
  // with neither param it leaves the user's manual tab selection alone.
  useEffect(() => {
    if (focusFilePath) setActiveTab('sources');
    else if (focusConceptId) setActiveTab('concepts');
  }, [focusFilePath, focusConceptId]);

  // P25.7 / P33 S3 (D6): the grounded assistant, now in the right rail so it is
  // visible across all three tabs. It grounds ENTIRELY in the already-fetched
  // graph status (no new fetch) and mounts only once that status has loaded —
  // loading → not shown; error → the Overview BackendDown carries the state.
  const rightPanel =
    graph.status === 'data' ? (
      <aside className="memory-right" aria-label="Assistant (advisory)">
        <div className="card placeholder-card memory-assistant-card">
          <AssistantPanel
            {...compose({ context: 'memory', graph: graph.data })}
            experimentId="project-memory"
            availability={graph.data.availability}
          />
        </div>
      </aside>
    ) : undefined;

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="memory" />}
      rightPanel={rightPanel}
      mainPad="pad"
    >
      <div className="placeholder">
        <span className="eyebrow">Memory / Query Plane</span>
        <h1>{LABELS.navMemory}</h1>
        <p>
          Project Memory is the assistant's memory and navigation surface — Graphify plus project
          docs. It is deliberately separate from the experiment queue and never appears inside it. It
          surfaces related files and concepts, prior documents, and "how is this connected?" answers
          as leads to verify — it never validates, completes, or supplies a value.
        </p>

        <SectionTabs active={activeTab} onSelect={setActiveTab} />

        {activeTab === 'overview' && (
          <div id={panelId('overview')} role="tabpanel" aria-labelledby={tabId('overview')} tabIndex={0}>
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
        )}

        {activeTab === 'sources' && (
          <div id={panelId('sources')} role="tabpanel" aria-labelledby={tabId('sources')} tabIndex={0}>
            <SourceIndexCard focusFilePath={focusFilePath} />
          </div>
        )}

        {activeTab === 'concepts' && (
          <div id={panelId('concepts')} role="tabpanel" aria-labelledby={tabId('concepts')} tabIndex={0}>
            <ConceptLookupCard focusConceptId={focusConceptId} />
          </div>
        )}
      </div>
    </AppShell>
  );
}

// --- internal page tabs (P33 S3 · D6) ------------------------------------
// A local tablist — Overview · Sources · Concepts — NOT part of the global
// LeftNav. Roving tabindex + arrow/Home/End keyboard navigation (automatic
// activation); native buttons carry Enter/Space activation.

function SectionTabs({
  active,
  onSelect,
}: {
  active: MemoryTab;
  onSelect: (tab: MemoryTab) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % MEMORY_TABS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + MEMORY_TABS.length) % MEMORY_TABS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = MEMORY_TABS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = MEMORY_TABS[nextIndex];
    onSelect(next.id);
    // Move focus to the newly selected tab (roving tabindex).
    (document.getElementById(tabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Project Memory sections">
      {MEMORY_TABS.map((tab, i) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            id={tabId(tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            // Only the SELECTED tab's panel is mounted (panels render
            // conditionally), so an inactive tab must not point aria-controls at
            // an id that isn't in the DOM — matching the accordion convention
            // used by the Concept Lookup / Source Index rows below.
            aria-controls={selected ? panelId(tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`section-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

// --- status detail card --------------------------------------------------

function MemoryStatusDetail({ data }: { data: ApiGraphStatus }) {
  // P24.10: the primary axis is availability. The finer axes (integrity /
  // memory policy / indexed sources) are each individually honest and are shown
  // as separate rows — never collapsed back into a single freshness verdict.
  const available = data.availability === 'available';

  return (
    <>
      <GraphStatusChip availability={data.availability} note={data.note} />
      {available ? (
        <>
          <p>
            Graphify is a memory plane, not a truth plane — every lead points back to a cited file
            to confirm.
          </p>
          <MemoryAxes data={data} />
          <MemoryFigures data={data} />
          <p className="memory-indexed-note">
            Project memory indexes this project's source code, docs, schema, and test fixtures via
            Graphify — metadata and provenance only, never file contents.
          </p>
        </>
      ) : (
        <>
          {/* When a shipped artifact is malformed/unsupported, surface WHY via the
              integrity axis; a wholly-absent artifact stays quiet (integrity unknown). */}
          {data.integrity !== 'unknown' && (
            <div className="memory-axes">
              <MemoryAxisRow
                label="Snapshot Integrity"
                caption={AXIS_CAPTION.integrity}
                presentation={INTEGRITY_AXIS[data.integrity]}
              />
            </div>
          )}
          <MemoryUnavailablePanel integrity={data.integrity} />
        </>
      )}
    </>
  );
}

// --- separated memory-plane axes (P24.10) --------------------------------
// Each axis is individually honest and advisory — NEVER a validation verdict.
// "Unknown" is quiet/neutral, never an error.

interface AxisPresentation {
  label: string;
  tone: 'ok' | 'warn' | 'quiet';
}

const INTEGRITY_AXIS: Record<SnapshotIntegrity, AxisPresentation> = {
  verified: { label: 'Verified', tone: 'ok' },
  malformed: { label: 'Malformed', tone: 'warn' },
  unsupported: { label: 'Unsupported', tone: 'warn' },
  unknown: { label: 'Unknown', tone: 'quiet' },
};

const CONSISTENCY_AXIS: Record<MemoryConsistency, AxisPresentation> = {
  current: { label: 'Current', tone: 'ok' },
  stale: { label: 'Out of Date', tone: 'warn' },
  unknown: { label: 'Unknown', tone: 'quiet' },
};

const AXIS_TONE_CLASS: Record<AxisPresentation['tone'], string> = {
  ok: 'axis-ok',
  warn: 'axis-warn',
  quiet: 'axis-quiet',
};

const AXIS_CAPTION = {
  integrity:
    'Whether the snapshot artifact is well-formed and schema-supported — not a check of its contents.',
  memoryPolicy:
    'The shipped sanitization and exclusion policy and versions match what the snapshot was built under.',
  // Scope-honest: CI proves this only over files already in the snapshot; a
  // newly added indexable file is not detected until Graphify re-indexes.
  indexedSources:
    'Proven in CI over only the files already in the snapshot — newly added indexable files are not detected until Graphify re-indexes.',
} as const;

function MemoryAxisRow({
  label,
  caption,
  presentation,
}: {
  label: string;
  caption: string;
  presentation: AxisPresentation;
}) {
  return (
    <div className="memory-axis">
      <div className="memory-axis-head">
        <span className="memory-axis-label">{label}</span>
        <span className={`memory-axis-state ${AXIS_TONE_CLASS[presentation.tone]}`}>
          {presentation.label}
        </span>
      </div>
      <p className="memory-axis-caption">{caption}</p>
    </div>
  );
}

/** The three separated freshness axes, shown only when memory is available. */
function MemoryAxes({ data }: { data: ApiGraphStatus }) {
  return (
    <div className="memory-axes">
      <MemoryAxisRow
        label="Snapshot Integrity"
        caption={AXIS_CAPTION.integrity}
        presentation={INTEGRITY_AXIS[data.integrity]}
      />
      <MemoryAxisRow
        label="Memory Policy"
        caption={AXIS_CAPTION.memoryPolicy}
        presentation={CONSISTENCY_AXIS[data.memory_policy]}
      />
      <MemoryAxisRow
        label="Indexed Sources"
        caption={AXIS_CAPTION.indexedSources}
        presentation={CONSISTENCY_AXIS[data.indexed_sources]}
      />
    </div>
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
  // "Indexed files" is the served file count from the overview (file_count).
  // The status-plane `served_file_count` can be null pre-regen; we never render
  // a broken/empty "served" figure from it — the count shown here is file_count.
  if (data.file_count != null) {
    rows.push({ label: 'Indexed files', value: String(data.file_count), mono: true });
  }
  if (data.concept_count != null) {
    rows.push({ label: 'Concepts', value: String(data.concept_count), mono: true });
  }
  if (data.provider !== 'unavailable') {
    rows.push({ label: 'Provider', value: data.provider, mono: true });
  }
  if (data.source_graph_commit != null) {
    rows.push({ label: 'Source graph commit', value: shortSha(data.source_graph_commit), mono: true });
  }
  if (data.snapshot_schema_version != null) {
    rows.push({ label: 'Snapshot schema', value: `v${data.snapshot_schema_version}`, mono: true });
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
 * The honest degraded panel for `availability:"unavailable"`. Not an error
 * state: no red, no counts, no fake placeholders. A shipped-but-malformed or
 * unsupported artifact is explained by its integrity; a wholly-absent artifact
 * (integrity unknown) shows the hosted + future-wiring context.
 */
function MemoryUnavailablePanel({ integrity }: { integrity: SnapshotIntegrity }) {
  if (integrity === 'malformed' || integrity === 'unsupported') {
    const reason =
      integrity === 'malformed'
        ? 'the snapshot artifact is present but malformed'
        : 'the snapshot artifact uses an unsupported schema version';
    return (
      <div className="memory-unavailable">
        <p className="memory-unavailable-title">
          Project memory is unavailable — {reason}, so no leads can be served.
        </p>
        <p className="memory-unavailable-text">
          This is a quiet, advisory state, not an error — the memory plane is optional. Rebuild the
          snapshot to restore leads and provenance.
        </p>
      </div>
    );
  }
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

function SourceIndexCard({ focusFilePath }: { focusFilePath?: string | null }) {
  const list = useFetch(() => api.getMemoryFiles(), []);
  return (
    <div className="card placeholder-card source-index-card">
      <h2 className="source-index-heading">Source Index</h2>
      <p className="source-index-subtitle">
        Files Graphify indexed for project memory — metadata and provenance only, never file
        contents.
      </p>
      {list.status === 'loading' && <LoadingPanel label="Loading source index…" />}
      {list.status === 'error' && <BackendDown error={list.error} onRetry={list.reload} />}
      {list.status === 'data' && (
        <SourceIndexList
          available={list.data.available}
          files={list.data.files}
          focusFilePath={focusFilePath}
        />
      )}
    </div>
  );
}

interface SourceIndexListProps {
  available: boolean;
  files: ApiMemoryFileSummary[];
  focusFilePath?: string | null;
}

/**
 * The row list, grouped by `file_type` (never by community — 214 communities
 * is far too many groups; community is per-row context instead). Only one
 * row's provenance panel is open at a time (accordion); a related-file lead
 * inside an open panel can activate a different row the same way a click on
 * that row would.
 */
function SourceIndexList({ available, files, focusFilePath }: SourceIndexListProps) {
  const [expandedPath, setExpandedPath] = useState<string | null>(null);

  const toggle = useCallback((path: string) => {
    setExpandedPath((current) => (current === path ? null : path));
  }, []);
  const activate = useCallback((path: string) => {
    setExpandedPath(path);
  }, []);

  // P26.5 deep link: `?file=<path>` from the search palette auto-opens that row
  // (only when it is actually a served file in this list — never invented).
  useEffect(() => {
    if (focusFilePath && files.some((f) => f.path === focusFilePath)) {
      setExpandedPath(focusFilePath);
    }
  }, [focusFilePath, files]);

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
              <h3 id={headingId} className="source-index-group-heading">
                {group.label}
                <span className="source-index-group-count">{group.files.length}</span>
              </h3>
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
        <h4 className="source-index-section-heading">Why memory draws on this file</h4>
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
        <h4 className="source-index-section-heading">Related files</h4>
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
        <h4 className="source-index-section-heading">Related concepts</h4>
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

// --- Concept Lookup card (P24.5) ------------------------------------------
// A browsable list of the 19 curated concepts Graphify anchored in project
// docs — memory leads, not scientific conclusions. Reuses the Source Index
// card's accordion pattern above (native-button activation, one-open-at-a-
// time, inline loading/error-with-retry) rather than inventing a second
// interaction language. Against the real local graph every concept currently
// has zero edges, so `related.files`/`related.concepts` are honestly empty
// for every real concept; the empty-leads note below is not a bug, it is the
// current graph's honest state.

function ConceptLookupCard({ focusConceptId }: { focusConceptId?: string | null }) {
  const list = useFetch(() => api.getMemoryConcepts(), []);
  const headingId = 'concept-lookup-heading';
  return (
    <div className="card placeholder-card concept-lookup-card">
      <h2 id={headingId} className="concept-lookup-heading">
        Concept Lookup
      </h2>
      <p className="concept-lookup-subtitle">
        Concepts Graphify anchored in project docs — memory leads, not scientific conclusions.
      </p>
      {list.status === 'loading' && <LoadingPanel label="Loading concepts…" />}
      {list.status === 'error' && <BackendDown error={list.error} onRetry={list.reload} />}
      {list.status === 'data' && (
        <ConceptLookupList
          available={list.data.available}
          concepts={list.data.concepts}
          headingId={headingId}
          focusConceptId={focusConceptId}
        />
      )}
    </div>
  );
}

interface ConceptLookupListProps {
  available: boolean;
  concepts: ApiMemoryConceptSummary[];
  headingId: string;
  focusConceptId?: string | null;
}

/**
 * The concept list — a flat, ungrouped set of chips/rows (the design calls
 * for 19 concepts total, too few to need grouping the way 190 files did).
 * Only one concept's provenance panel is open at a time (accordion); a
 * related-concept lead inside an open panel can activate a different concept
 * the same way a click on that concept would.
 */
function ConceptLookupList({
  available,
  concepts,
  headingId,
  focusConceptId,
}: ConceptLookupListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggle = useCallback((id: string) => {
    setExpandedId((current) => (current === id ? null : id));
  }, []);
  const activate = useCallback((id: string) => {
    setExpandedId(id);
  }, []);

  // P26.5 deep link: `?concept=<id>` from the search palette auto-opens that
  // concept (only when it is actually in the fetched list — never invented).
  useEffect(() => {
    if (focusConceptId && concepts.some((c) => c.id === focusConceptId)) {
      setExpandedId(focusConceptId);
    }
  }, [focusConceptId, concepts]);

  if (!available) {
    return (
      <p className="concept-lookup-unavailable">
        Concept lookup is unavailable — the memory graph is not present on this backend (see
        Project memory status above).
      </p>
    );
  }

  return (
    <>
      <ul className="concept-lookup-rows" aria-labelledby={headingId}>
        {concepts.map((concept) => (
          <ConceptLookupRow
            key={concept.id}
            concept={concept}
            expanded={expandedId === concept.id}
            onToggle={() => toggle(concept.id)}
            onActivateConcept={activate}
          />
        ))}
      </ul>
      <p className="concept-lookup-caption">leads — open the cited file to verify</p>
    </>
  );
}

interface ConceptLookupRowProps {
  concept: ApiMemoryConceptSummary;
  expanded: boolean;
  onToggle: () => void;
  onActivateConcept: (id: string) => void;
}

function ConceptLookupRow({ concept, expanded, onToggle, onActivateConcept }: ConceptLookupRowProps) {
  const panelId = domId('concept-panel', concept.id);
  const community = communityLabel(concept);
  const Chevron = expanded ? ChevronDown : ChevronRight;

  // Keyboard accessibility comes from the native <button>, same as the Source
  // Index rows above: no custom onKeyDown — a duplicate handler would
  // double-toggle for keyboard users (Enter/Space already synthesize a click
  // on the focused button). `aria-controls` only points at the panel id while
  // the panel actually exists in the DOM.
  return (
    <li className="concept-lookup-row">
      <button
        type="button"
        className="concept-lookup-row-btn"
        aria-expanded={expanded}
        aria-controls={expanded ? panelId : undefined}
        onClick={onToggle}
      >
        <Chevron className="concept-lookup-chevron" size={14} strokeWidth={2} aria-hidden="true" />
        <span className="concept-lookup-label">{concept.label}</span>
        {community && <span className="concept-lookup-community">{community}</span>}
      </button>
      {expanded && (
        <div id={panelId} className="concept-lookup-panel">
          <ConceptLookupPanelBody id={concept.id} onActivateConcept={onActivateConcept} />
        </div>
      )}
    </li>
  );
}

function ConceptLookupPanelBody({
  id,
  onActivateConcept,
}: {
  id: string;
  onActivateConcept: (id: string) => void;
}) {
  const detail = useFetch(() => api.getMemoryConcept(id), [id]);
  return (
    <>
      {detail.status === 'loading' && <LoadingPanel label="Loading provenance…" />}
      {detail.status === 'error' && (
        <div className="concept-lookup-panel-error">
          <p>Could not load provenance for this concept.</p>
          <button type="button" className="btn btn-secondary" onClick={detail.reload}>
            Retry
          </button>
        </div>
      )}
      {detail.status === 'data' && (
        <ConceptLookupDetail data={detail.data} onActivateConcept={onActivateConcept} />
      )}
    </>
  );
}

function ConceptLookupDetail({
  data,
  onActivateConcept,
}: {
  data: ApiMemoryConceptResponse;
  onActivateConcept: (id: string) => void;
}) {
  if (!data.available || !data.concept) {
    return (
      <p className="concept-lookup-panel-note">
        Concept lookup is unavailable — the memory graph is not present on this backend.
      </p>
    );
  }
  const { concept, related } = data;
  const community = communityLabel(concept);
  const hasLeads = related.files.length > 0 || related.concepts.length > 0;

  return (
    <div className="concept-lookup-detail">
      <p className="concept-lookup-anchor">
        <span className="concept-lookup-anchor-label">anchor source</span>
        {concept.source_file ? (
          <span className="mono">{concept.source_file}</span>
        ) : (
          // P24.9: the graph anchor points at a governance-excluded source, so
          // the backend withheld the path — render an honest note, never an
          // empty mono span.
          <span className="concept-lookup-anchor-missing">anchor withheld (excluded source)</span>
        )}
      </p>
      {concept.source_file && !concept.on_disk && (
        <p className="concept-lookup-anchor-missing">not present locally on this backend</p>
      )}

      <dl className="concept-lookup-panel-figures">
        <div className="concept-lookup-panel-figure">
          <dt>Community</dt>
          <dd>{community ?? '—'}</dd>
        </div>
      </dl>

      <div className="concept-lookup-section">
        <h3 className="concept-lookup-section-heading">Related leads</h3>
        {hasLeads ? (
          <>
            {related.files.length > 0 && (
              <div className="concept-lookup-subsection">
                <h4 className="concept-lookup-subsection-heading">Files</h4>
                {/* Related files are inert labeled text in this slice — no
                    cross-card navigation into the Source Index card, per the
                    P24.5 scope boundary. */}
                <ul className="concept-lookup-related-list">
                  {related.files.map((rf) => (
                    <li key={rf.path}>
                      <span className="mono">{rf.path}</span>
                      {rf.relation && <span className="concept-lookup-relation">{rf.relation}</span>}
                      {rf.file_type && (
                        <span className="concept-lookup-relation">{rf.file_type}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {related.concepts.length > 0 && (
              <div className="concept-lookup-subsection">
                <h4 className="concept-lookup-subsection-heading">Concepts</h4>
                <ul className="concept-lookup-related-list">
                  {related.concepts.map((rc) => (
                    <li key={rc.id}>
                      <button
                        type="button"
                        className="concept-lookup-related-link"
                        onClick={() => onActivateConcept(rc.id)}
                      >
                        <span>{rc.label ?? rc.id}</span>
                        {rc.relation && (
                          <span className="concept-lookup-relation">{rc.relation}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : (
          <p className="concept-lookup-empty-note">
            no recorded leads for this concept in the current graph
          </p>
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
