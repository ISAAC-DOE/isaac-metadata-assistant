import './screens.css';
import '../components/assistant.css';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { GraphStatusChip } from '../components/GraphStatusChip';
import { AssistantPanel } from '../components/AssistantPanel';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { MemoryGraphCard } from './MemoryGraphCard';
import { Network, ChevronDown, ChevronRight, Search } from '../components/icons';
import { LABELS } from '../lib/labels';
import { conceptDisplayTitle, relationDisplayLabel } from '../lib/displayLabels';
import { api } from '../lib/api';
import { compose } from '../lib/assistantComposer';
import {
  classifyGraphQuestion,
  describeGraphProvenance,
  type AssistantGraphCapability,
  type GraphSurfaceContext,
  type GraphUrlParam,
} from '../lib/graphCommands';
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
// P33 S3 (D6) — the internal sections of Project Memory. These are LOCAL page
// tabs (never added to the global LeftNav): Overview carries the memory
// health/status, Sources holds the Source Index, Concepts holds the Concept
// Lookup. P36.2 adds a fourth tab, Graph — a deterministic, capped, served-
// file reference projection (not the full source graph). The grounded
// assistant lives in the right rail across ALL four.
type MemoryTab = 'overview' | 'sources' | 'concepts' | 'graph';

const MEMORY_TABS: { id: MemoryTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'sources', label: 'Sources' },
  { id: 'concepts', label: 'Concepts' },
  { id: 'graph', label: 'Graph' },
];

const tabId = (id: MemoryTab) => `memory-tab-${id}`;
const panelId = (id: MemoryTab) => `memory-tabpanel-${id}`;

export function ProjectMemory() {
  const graph = useFetch(() => api.getGraphStatus(), []);

  // P26.5: deep-link readers so the ⌘K search palette's memory results actually
  // land somewhere. `?concept=<id>` auto-opens that concept in Concept Lookup;
  // `?file=<path>` auto-opens that file in the Source Index. Both reuse each
  // card's existing accordion expand/fetch mechanics — nothing new is fetched.
  const [params, setParams] = useSearchParams();
  const focusConceptId = params.get('concept');
  const focusFilePath = params.get('file');
  // P36R S4: `?tab=` makes the section part of the link, so a shared graph URL
  // (and a reload, and browser back) lands on the tab that owns the state. Read
  // through a strict allowlist — an unknown value selects nothing.
  const urlTab = params.get('tab');
  const linkedTab = MEMORY_TABS.some((t) => t.id === urlTab) ? (urlTab as MemoryTab) : null;

  // P33 S3 (D6): a deep link selects the tab that owns the target — `?file=`
  // lands on Sources, `?concept=` on Concepts — so the auto-opened item is
  // visible on arrival; otherwise the page opens on Overview.
  const [activeTab, setActiveTab] = useState<MemoryTab>(
    focusFilePath ? 'sources' : focusConceptId ? 'concepts' : (linkedTab ?? 'overview'),
  );

  // A manual tab click keeps `?tab=` truthful, but REPLACES the history entry:
  // switching tabs is not a navigation worth a back-button stop. The command
  // bar's own pushes (which carry graph state) still stack normally.
  const selectTab = useCallback(
    (tab: MemoryTab) => {
      setActiveTab(tab);
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('tab', tab);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  // Browser back/forward between two graph links: follow `?tab=` when it moves.
  useEffect(() => {
    if (linkedTab) setActiveTab(linkedTab);
  }, [linkedTab]);

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

  // P36R S5 — the mounted Graph surface publishes itself here (index, provenance,
  // a state reader, and an external `apply`) so the Assistant's graph capability
  // resolves against the SAME already-fetched projection and applies through the
  // SAME reducer. Null whenever the Graph tab is not mounted.
  const [graphSurface, setGraphSurface] = useState<GraphSurfaceContext | null>(null);
  const onGraphReady = useCallback((ctx: GraphSurfaceContext | null) => setGraphSurface(ctx), []);

  /**
   * The OPT-IN Assistant graph capability.
   *
   * Scope, deliberately narrow and documented:
   *  - Project Memory only — the four record surfaces pass nothing at all, so
   *    their Assistant behaviour is unchanged.
   *  - and only while the Graph tab is mounted, because that is where the
   *    projection has actually been fetched. Enabling it on the other tabs would
   *    mean pulling the ~120 KB projection on every Project Memory visit, which
   *    is a real cost for a capability that belongs next to the graph.
   *
   * `classify` is pure, offline, literal pattern matching over a frozen catalog
   * — no LLM, no provider, no embedding, no network. `apply` runs only from the
   * explicit "Apply to Graph" control.
   */
  const graphCapability = useMemo<AssistantGraphCapability | undefined>(() => {
    if (activeTab !== 'graph' || !graphSurface) return undefined;
    const surface = graphSurface;
    return {
      // The WHOLE live view state, read fresh on every question. A proposal's
      // stated counts are produced by folding its own actions onto exactly this
      // state through the real reducer, so they are what "Apply to Graph" will
      // put on screen — not an estimate computed from a subset of the filters.
      classify: (question: string) =>
        classifyGraphQuestion(question, surface.index, { state: surface.peek() }),
      apply: (proposal) => surface.apply(proposal.command, proposal.actions),
      provenance: describeGraphProvenance(surface.meta),
    };
  }, [activeTab, graphSurface]);

  // P25.7 / P33 S3 (D6): the grounded assistant, now in the right rail so it is
  // visible across all three tabs. It grounds ENTIRELY in the already-fetched
  // graph status (no new fetch) and mounts only once that status has loaded —
  // loading → not shown; error → the Overview BackendDown carries the state.
  const rightPanel =
    graph.status === 'data' ? (
      <AssistantDrawer railClassName="memory-right" label="Assistant (advisory)">
        <div className="card placeholder-card memory-assistant-card">
          <AssistantPanel
            {...compose({ context: 'memory', graph: graph.data })}
            experimentId="project-memory"
            queryScope="memory"
            /* The PAGE owns the visible availability label here: the
               `GraphStatusChip` on the status card below is this screen's own
               subject. The panel is therefore GIVEN the axis — it needs it for
               `classifyAnswer` and for the memory caveat — but does not restate
               it visibly. One fact, one wording, one place. Without this the
               identical "Memory Available" renders twice, and a screen reader
               hears the chip's accessible name ("Project memory available —
               memory plane, advisory only, never a validator") and this row's
               visible text as two differently-worded claims about one axis.
               (P33 HQA #7; retained through P36V S-A.) */
            availability={graph.data.availability}
            showAvailabilityStatus={false}
            graphCapability={graphCapability}
          />
        </div>
      </AssistantDrawer>
    ) : undefined;

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="memory" />}
      rightPanel={rightPanel}
      mainPad="pad"
      /* P36R S3: the Graph tab's canvas is the one surface specified to run
         edge-to-edge, so it takes `full` (--content-max: none) while every
         other tab keeps the page's `wide` measure. The mode is a property of
         the ACTIVE tab, not of the screen — Overview/Sources/Concepts are prose
         and lists and stay measured. */
      width={activeTab === 'graph' ? 'full' : 'wide'}
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

        <SectionTabs active={activeTab} onSelect={selectTab} />

        {activeTab === 'overview' && (
          <div id={panelId('overview')} role="tabpanel" aria-labelledby={tabId('overview')} tabIndex={0}>
            <div className="card placeholder-card">
              {graph.status === 'loading' && <LoadingPanel label="Checking memory status…" />}
              {graph.status === 'error' && <BackendDown error={graph.error} onRetry={graph.reload} />}
              {graph.status === 'data' && <MemoryStatusDetail data={graph.data} />}
            </div>
            {/* P36R S10 — "Browse depth is out of scope for this first build."
                was a roadmap note left in shipped copy, and it is no longer
                true: the Graph tab offers 1-hop and 2-hop neighbourhoods and a
                shortest-path search. Replaced with orientation that IS
                verifiable — `/api/memory/files`, `/api/memory/concepts` and
                `/api/memory/graph` all resolve the SAME
                `memory.get_default_reader()` instance whose status this card
                reports (`routes.py:1206/1290/1338/1394`). */}
            <p style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-tertiary)' }}>
              <Network size={15} strokeWidth={2} aria-hidden="true" />
              Sources, Concepts and Graph all read the memory graph summarised above.
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

        {activeTab === 'graph' && (
          <div id={panelId('graph')} role="tabpanel" aria-labelledby={tabId('graph')} tabIndex={0}>
            <MemoryGraphCard onReady={onGraphReady} />
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
  /*
   * The integrity-unknown case: no artifact was found at all.
   *
   * THE COPY THIS REPLACED WAS STALE, NOT JUST LOCAL-FLAVOURED. It said "the
   * hosted demo does not currently ship the Graphify graph artifacts; when run
   * locally against local artifacts, Project Memory works" — two false claims by
   * the time it was read. Both artifacts are COMMITTED
   * (`apps/api/isaac_api/data/memory-snapshot.json` and
   * `memory-graph-detail.json` are tracked in git) and both ship in the image
   * (the Dockerfile's `COPY apps/api/ apps/api/` carries the whole directory),
   * and `memory.py::_resolve_reader_choice` prefers that packaged snapshot over
   * any live `graphify-out/`. So Project Memory works on the deployment, and the
   * old copy told a reader the opposite.
   *
   * WHAT IS ACTUALLY TRUE WHEN THIS PANEL RENDERS. `integrity:"unknown"` means
   * the reader found no artifact where it looked. Given the artifact is shipped,
   * that leaves two plausible conditions — it was not included in this
   * particular build, or this deployment points its memory source elsewhere
   * (`_resolve_reader_choice` honours `ISAAC_MEMORY_SNAPSHOT` /
   * `ISAAC_MEMORY_DIR` first) — and the browser has NO signal that separates
   * them. So both are named and neither is asserted, the same discipline
   * `downCopy` uses for an unreachable API. No cause is invented, and the word
   * "local" is gone: it was never a fact this panel could know.
   *
   * THE INDEPENDENCE CLAIM IS SCOPED TO THE TRUTH PATH, because the broader one
   * was false. "No other surface depends on it" was contradicted by the code:
   * `api.ts::getRecordBundle` and `getExportReadiness` both fetch
   * `GET /api/graph/status`, the status bar renders a memory chip from it, and
   * `AssistantPanel` classifies a graph-sourced answer as DEGRADED when
   * availability is unavailable. What is true — and what a reader needs — is that
   * no verdict, validation result or export decision depends on memory, and that
   * the surfaces which do consume it report unavailability instead of guessing.
   */
  return (
    <div className="memory-unavailable">
      <p className="memory-unavailable-title">
        Project memory is unavailable in this deployment — no memory graph artifact was found where
        this build reads it.
      </p>
      <p className="memory-unavailable-text">
        ISAAC ships its memory artifacts with the application — a sanitized graph snapshot and a
        symbol-level graph — so an absent artifact is not the expected state. This page cannot tell
        which of two conditions applies: the artifacts were not included in this build, or this
        deployment is configured to read a memory source that is not present. The memory plane is
        advisory and optional: no record verdict, validation result, or export decision depends on
        it. The surfaces that do draw on memory — the status-bar memory chip, and the assistant's
        memory-sourced answers — report it as unavailable rather than inventing one.
      </p>
      <p className="memory-unavailable-text">
        Future path: the memory source can later be pointed at a richer approved source — a broader
        sanitized snapshot, or a database-backed memory index. Reaching any such source would be
        controlled by the deployment where it is operated; ISAAC manages no accounts or roles of its
        own.
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
      // P36R S10 — a DIFFERENT fact from the `on_disk` copy above: here the
      // memory graph itself is absent, so there is nothing to index. Reworded
      // only to drop the "on this backend" jargon; the meaning is unchanged and
      // is deliberately not merged with the per-file wording.
      <p className="source-index-unavailable">
        Source Index is unavailable — no memory graph is loaded in this deployment (see Project
        memory status above).
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
        Source Index is unavailable — no memory graph is loaded in this deployment.
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
          {/*
            P36V.2 F4 — the label names the value and instructs nothing. It used
            to read "local reference — open in your editor", which is
            unactionable on a deployment: there is no checkout and no editor
            there. `file.local_reference` is a repo-relative path, so that is
            what it is called. (The label is inert text either way; nothing here
            fetches or renders file bytes.)
          */}
          <span className="source-index-local-ref-label">repository path</span>
          <span className="mono">{file.local_reference}</span>
        </p>
      ) : (
        // P36R S10 — ONE sentence for `on_disk`, shared with Concepts and the
        // graph detail pane. `on_disk` is a filesystem existence check on the
        // repo root (`memory.py::_on_disk`, which never opens the file), so the
        // copy speaks only about the deployment not carrying the file. It makes
        // no claim about snapshot membership in either direction — this file IS
        // in the served snapshot, which is how its provenance is rendered above.
        <p className="source-index-local-ref source-index-local-ref-missing">
          This deployment does not carry the file itself — open it in the project to read it.
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
        <h4 className="source-index-section-heading">Related Files</h4>
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
                  {/* P36V S-B — the same relation display map the Graph legend,
                      GraphDetail and the Concepts pane use. Left raw here, one
                      relation read `Imports` on two tabs and `imports` on this
                      one. The raw value stays exact in `title`, and it is the raw
                      value the filters and the `relation` command match. */}
                  {rf.relation && (
                    <span className="source-index-relation" title={rf.relation}>
                      {relationDisplayLabel(rf.relation)}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="source-index-empty-note">no recorded leads for this file</p>
        )}
      </div>

      <div className="source-index-section">
        <h4 className="source-index-section-heading">Related Concepts</h4>
        {related.concepts.length > 0 ? (
          <ul className="source-index-related-list">
            {related.concepts.map((rc) => (
              <li key={rc.id}>
                {/* P36V S-B — derived concept title and mapped relation, matching
                    the Concepts pane. Raw values remain reachable ON THIS
                    SURFACE: the raw relation and the raw concept label are both
                    on `title`. Nothing here navigates to the concept, and this
                    tab has no Technical Details disclosure of its own — so
                    without the `title` the raw label (which is what the Concepts
                    tab's search actually matches) would be unreachable from here,
                    and the derivation would stop being lossless for the reader. */}
                <span
                  className="source-index-concept-label"
                  title={rc.label ? rc.label : undefined}
                >
                  {rc.label ? conceptDisplayTitle(rc.label) : rc.id}
                </span>
                {rc.relation && (
                  <span className="source-index-relation" title={rc.relation}>
                    {relationDisplayLabel(rc.relation)}
                  </span>
                )}
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

// --- Concept Lookup card (P24.5 · redesigned P36R Slice 7) ----------------
//
// A MASTER-DETAIL browser over the curated concepts Graphify anchored in
// project docs. It replaces the P24.5 flat single-open accordion, whose panel
// pushed the rest of the page down and which offered no way to find anything.
//
// What it is NOT: a glossary. A concept row is a POINTER at the project
// document the label was read out of — never a definition of the term and
// never a scientific conclusion. Nothing on this surface is invented: every
// word of the per-concept description below is assembled from fields the two
// memory endpoints actually returned (`source_file`, `community_*`, and the
// recorded `related` leads), and where a field is absent the sentence says so
// instead of filling the gap.
//
// Against the real graph every concept currently has ZERO edges, so
// `related.files` / `related.concepts` are honestly empty for every real
// concept. The empty-leads copy is not a bug — it is the current graph's
// honest state. Separately and permanently, the Graph tab's projection derives
// edges ONLY from a file's `related.files[]`, never from a concept's `related`
// (`memory_graph.py::_build_edges`), so a concept node has zero edges by
// construction: no neighbourhood ("browse connected items") action is offered
// for a concept at all, because it could only ever land on an empty
// neighbourhood. Recorded leads, when a snapshot has any, are listed and
// navigable in the detail panel instead.

/** Sentinel filter values. Never a real community id or document path — the
 *  backend's ids are numeric strings and its paths are repo-relative. */
const CONCEPT_FILTER_ALL = 'all';
const CONCEPT_FILTER_NO_CLUSTER = '__no_cluster__';
const CONCEPT_FILTER_UNLINKED_DOC = '__unlinked__';

/** P36R S10 — the Concepts detail pane's region id + accessible-name id, the
 *  same pair `SchemaBrowser` (`schema-field-detail`) and `SettingsPage`
 *  (`settings-api-detail`) use for their panes. */
const CONCEPT_DETAIL_ID = 'concept-lookup-detail';
const CONCEPT_DETAIL_NAME_ID = 'concept-lookup-detail-name';

/** The same bound the graph search input enforces (`MAX_QUERY_LENGTH`), kept
 *  local so this card takes no dependency on the graph module. */
const CONCEPT_QUERY_MAX = 120;

/**
 * A Project Memory link expressed ENTIRELY in the Slice-4 graph URL contract
 * (`lib/graphCommands.ts` → `GRAPH_URL_PARAMS` + Project Memory's own `tab`).
 * This surface invents no parameter of its own: `gmode` / `gnode` are decoded by
 * `decodeGraphActions`, bounded there, and resolved by the graph reducer's own
 * `resolveNode` — so a concept id that is not a node produces the graph's honest
 * "no node matches", never a guessed selection.
 *
 * Explore (select this concept on the canvas) is the ONLY graph link offered for
 * a concept. A neighbourhood link (`gnbr`/`gdepth`) is deliberately not
 * produced: `memory_graph.py::_build_edges` builds edges from file summaries'
 * `related.files[]` ONLY and never from a concept's `related`, so a concept node
 * has zero edges by construction and a 1-hop neighbourhood around one is always
 * empty — a click that would land nowhere.
 */
export function conceptGraphSearch(conceptId: string): string {
  const sp = new URLSearchParams();
  // Typed at the boundary so the coupling to GRAPH_URL_PARAMS is checked by the
  // compiler, not only by the URL-contract test.
  const setGraphParam = (key: GraphUrlParam, value: string) => sp.set(key, value);
  sp.set('tab', 'graph');
  setGraphParam('gmode', 'explore');
  setGraphParam('gnode', conceptId);
  return `?${sp.toString()}`;
}

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
        <ConceptLookupBrowser
          available={list.data.available}
          concepts={list.data.concepts}
          focusConceptId={focusConceptId}
        />
      )}
    </div>
  );
}

interface ConceptLookupBrowserProps {
  available: boolean;
  concepts: ApiMemoryConceptSummary[];
  focusConceptId?: string | null;
}

const conceptRowId = (id: string) => domId('concept-row', id);

/**
 * Master (searchable, filterable, keyboard-navigable list) + detail (the one
 * selected concept). Nothing is fetched until a concept is selected, and the
 * detail region is the ONLY thing that changes when the selection does — the
 * list never reflows underneath the pointer the way the old accordion did.
 */
function ConceptLookupBrowser({ available, concepts, focusConceptId }: ConceptLookupBrowserProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [docFilter, setDocFilter] = useState<string>(CONCEPT_FILTER_ALL);
  const [clusterFilter, setClusterFilter] = useState<string>(CONCEPT_FILTER_ALL);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Roving-tabindex cursor for the master list. Focus and SELECTION are
  // deliberately separate: an arrow key moves the reading cursor, Enter/Space
  // (native button activation) selects. Coupling them would fire one detail
  // fetch per arrow press.
  const [focusIndex, setFocusIndex] = useState(0);

  /** The always-mounted search box: the focus target when `Clear Filters`
   *  removes itself (see its onClick). */
  const searchRef = useRef<HTMLInputElement | null>(null);

  const clearFilters = useCallback(() => {
    setQuery('');
    setDocFilter(CONCEPT_FILTER_ALL);
    setClusterFilter(CONCEPT_FILTER_ALL);
  }, []);

  /** Select a concept and make sure it is actually visible in the master list
   *  — a lead followed from inside the detail, or a `?concept=` deep link,
   *  must not select something the active filters are hiding. */
  const activate = useCallback(
    (id: string) => {
      setSelectedId(id);
      clearFilters();
      // Move the roving cursor onto what was just selected, so the next Tab into
      // the list lands on the selection instead of a stale row. `clearFilters()`
      // restores the unfiltered list, so the row's index in `concepts` IS its
      // index in the list that will render.
      const index = concepts.findIndex((c) => c.id === id);
      if (index >= 0) setFocusIndex(index);
    },
    [clearFilters, concepts],
  );

  // P26.5 deep link: `?concept=<id>` from the ⌘K palette selects that concept
  // (only when it is actually in the fetched list — never invented). Routed
  // through `activate` so the deep link and an in-panel lead leave the list in
  // exactly the same state.
  useEffect(() => {
    if (focusConceptId && concepts.some((c) => c.id === focusConceptId)) {
      activate(focusConceptId);
    }
  }, [focusConceptId, concepts, activate]);

  /** Anchor documents actually present among these concepts, with counts.
   *
   *  P36R S10: a null `source_file` has TWO shapes behind it (`memory.py::
   *  _served_source_file`) — the graph node named no source at all, or it named
   *  one that is unsafe / not governance-served and was withheld. `unlinked`
   *  counts both, so the option label must not assert that an excluded source
   *  exists. Same correction `describeConcept` already carries. */
  const docOptions = useMemo(() => {
    const counts = new Map<string, number>();
    let unlinked = 0;
    for (const c of concepts) {
      if (c.source_file === null) unlinked += 1;
      else counts.set(c.source_file, (counts.get(c.source_file) ?? 0) + 1);
    }
    return {
      docs: [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0])),
      unlinked,
    };
  }, [concepts]);

  /** Clusters actually present among these concepts, with counts. Labels come
   *  from `communityLabel` — a real name, else the honest "community <id>". */
  const clusterOptions = useMemo(() => {
    const byId = new Map<string, { label: string; count: number }>();
    let noCluster = 0;
    for (const c of concepts) {
      const label = communityLabel(c);
      if (!c.community_id || !label) {
        noCluster += 1;
        continue;
      }
      const entry = byId.get(c.community_id);
      if (entry) entry.count += 1;
      else byId.set(c.community_id, { label, count: 1 });
    }
    const clusters = [...byId.entries()].sort((a, b) => a[1].label.localeCompare(b[1].label));
    return {
      clusters,
      noCluster,
      singletons: clusters.filter(([, v]) => v.count === 1).length,
    };
  }, [concepts]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return concepts.filter((c) => {
      if (needle !== '' && !(c.label.toLowerCase().includes(needle) || c.id.toLowerCase().includes(needle))) {
        return false;
      }
      if (docFilter !== CONCEPT_FILTER_ALL) {
        if (docFilter === CONCEPT_FILTER_UNLINKED_DOC) {
          if (c.source_file !== null) return false;
        } else if (c.source_file !== docFilter) return false;
      }
      if (clusterFilter !== CONCEPT_FILTER_ALL) {
        if (clusterFilter === CONCEPT_FILTER_NO_CLUSTER) {
          if (c.community_id) return false;
        } else if (c.community_id !== clusterFilter) return false;
      }
      return true;
    });
  }, [concepts, query, docFilter, clusterFilter]);

  // The cursor can outrun a shrinking list (type a query, then press Down).
  const cursor = filtered.length === 0 ? 0 : Math.min(focusIndex, filtered.length - 1);

  /**
   * Whether the per-row "source not in this deployment" marker distinguishes
   * anything. Against the real snapshot EVERY anchored concept's file is absent
   * from the deployment, so the marker was 19 identical chips carrying no
   * signal. It is shown per row only when the list is genuinely mixed; when it
   * is universal the fact is stated once, in full, above the list — never
   * dropped.
   *
   * Both flags are derived from the FILTERED rows on purpose: a sentence about
   * "the documents cited below" has to be true of the rows actually below it,
   * not of the unfiltered dataset. Concepts with no linked source (the graph
   * named none, or named one the backend withheld) cite no document at all —
   * `source_file` is null either way, so they are excluded from both flags: filtering
   * down to only those leaves `allMissing` false and the aggregate note unshown
   * rather than claiming something about documents that were never named.
   */
  /** Whether anything is narrowing the list right now — the only condition under
   *  which a Clear Filters control has work to do, and therefore the only
   *  condition under which it is rendered. */
  const filtersActive =
    query.trim() !== '' || docFilter !== CONCEPT_FILTER_ALL || clusterFilter !== CONCEPT_FILTER_ALL;

  const onDiskSpread = useMemo(() => {
    const withSource = filtered.filter((c) => c.source_file !== null);
    return {
      mixed: withSource.some((c) => c.on_disk) && withSource.some((c) => !c.on_disk),
      allMissing: withSource.length > 0 && withSource.every((c) => !c.on_disk),
    };
  }, [filtered]);

  const onListKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
      let next: number | null = null;
      if (e.key === 'ArrowDown') next = Math.min(index + 1, filtered.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(index - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = filtered.length - 1;
      if (next === null || filtered.length === 0) return;
      e.preventDefault();
      setFocusIndex(next);
      (document.getElementById(conceptRowId(filtered[next].id)) as HTMLButtonElement | null)?.focus();
    },
    [filtered],
  );

  const showInGraph = useCallback(
    (id: string) => navigate(`/memory${conceptGraphSearch(id)}`),
    [navigate],
  );
  const navigateToFile = useCallback(
    (path: string) => navigate(`/memory?file=${encodeURIComponent(path)}`),
    [navigate],
  );

  if (!available) {
    return (
      <p className="concept-lookup-unavailable">
        Concept lookup is unavailable — no memory graph is loaded in this deployment (see Project
        memory status above).
      </p>
    );
  }

  const listHeadingId = 'concept-lookup-list-heading';

  return (
    <>
      <div className="concept-lookup-toolbar">
        <label className="concept-lookup-search">
          <Search size={14} strokeWidth={2} aria-hidden="true" className="concept-lookup-search-icon" />
          <span className="sr-only">Search concepts by name or id</span>
          <input
            ref={searchRef}
            type="search"
            className="concept-lookup-search-input"
            placeholder="Search concepts…"
            maxLength={CONCEPT_QUERY_MAX}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="concept-lookup-filter">
          <span>Anchor source</span>
          <select value={docFilter} onChange={(e) => setDocFilter(e.target.value)}>
            <option value={CONCEPT_FILTER_ALL}>All sources</option>
            {docOptions.docs.map(([path, count]) => (
              <option key={path} value={path}>
                {path} ({count})
              </option>
            ))}
            {docOptions.unlinked > 0 && (
              <option value={CONCEPT_FILTER_UNLINKED_DOC}>
                no linked source ({docOptions.unlinked})
              </option>
            )}
          </select>
        </label>
        <label className="concept-lookup-filter">
          <span>Cluster</span>
          <select value={clusterFilter} onChange={(e) => setClusterFilter(e.target.value)}>
            <option value={CONCEPT_FILTER_ALL}>All clusters</option>
            {clusterOptions.clusters.map(([id, entry]) => (
              <option key={id} value={id}>
                {entry.label} ({entry.count})
              </option>
            ))}
            {clusterOptions.noCluster > 0 && (
              <option value={CONCEPT_FILTER_NO_CLUSTER}>
                no cluster ({clusterOptions.noCluster})
              </option>
            )}
          </select>
        </label>
      </div>
      {/* P36V S-A — a visible escape from the filters. The empty state has told
          readers to "clear the filters" since S7 while `clearFilters` was only
          ever called programmatically (by a followed lead or a `?concept=` deep
          link), so the instruction pointed at no control. Filter SEMANTICS are
          untouched: this is the same callback those two paths already use. */}
      {filtersActive && (
        <div className="concept-lookup-toolbar-actions">
          <button
            type="button"
            className="btn btn-secondary concept-lookup-clear"
            onClick={() => {
              clearFilters();
              // This button unmounts itself the moment the filters are cleared,
              // which would leave `document.activeElement` on <body> and dump a
              // keyboard user at the top of the document. Focus goes to the
              // always-mounted search box — the control the reader would reach
              // for next, and the one whose value was just emptied.
              searchRef.current?.focus();
            }}
          >
            Clear Filters
          </button>
        </div>
      )}
      {/* P36V S-A concision: the second sentence here ("Clusters are derived
          automatically by the upstream graph builder — advisory groupings, not
          categories the schema recognises") was a third copy of a claim already
          made in full on the Graph tab of this same screen
          (`MemoryGraphCard`'s community note and `GraphHelp`'s "Cluster
          colours"). The unique fact — how many of the clusters ON SCREEN hold a
          single concept — stays, and the advisory qualifier is compressed into
          the same sentence rather than deleted: cluster filtering happens HERE,
          so the reader choosing a cluster must not be left to over-trust it. */}
      {clusterOptions.clusters.length > 0 && (
        <p className="concept-lookup-filter-note">
          {clusterOptions.singletons === clusterOptions.clusters.length
            ? 'Every cluster represented here holds a single concept'
            : `${clusterOptions.singletons} of the ${clusterOptions.clusters.length} clusters represented here hold a single concept`}{' '}
          — advisory groupings from the upstream graph builder, not schema categories.
        </p>
      )}
      {/* Scoped to the documents actually cited by the rows below: `on_disk` is
          a filesystem-presence check (see the detail render site), and a concept
          with no linked source cites no document at all. */}
      {onDiskSpread.allMissing && (
        <p className="concept-lookup-filter-note">
          This deployment does not carry any of the documents cited below — open them in the
          project to read them.
        </p>
      )}

      <div className="concept-lookup-split">
        <div className="concept-lookup-master">
          {/* The explicit space is load-bearing, not formatting: this heading is
              the <ul>'s accessible name via aria-labelledby, and without a
              separating text node it is computed as "Concepts3 of 3". */}
          <h3 id={listHeadingId} className="concept-lookup-pane-heading">
            Concepts{' '}
            <span className="concept-lookup-pane-count">
              {filtered.length} of {concepts.length}
            </span>
          </h3>
          {filtered.length > 0 ? (
            <ul className="concept-lookup-rows" aria-labelledby={listHeadingId}>
              {filtered.map((concept, i) => (
                <ConceptLookupRow
                  key={concept.id}
                  concept={concept}
                  selected={selectedId === concept.id}
                  showOnDiskBadge={onDiskSpread.mixed}
                  tabIndex={i === cursor ? 0 : -1}
                  onSelect={() => {
                    setFocusIndex(i);
                    setSelectedId(concept.id);
                  }}
                  onKeyDown={(e) => onListKeyDown(e, i)}
                />
              ))}
            </ul>
          ) : (
            <p className="concept-lookup-empty-note">
              No concept matches the current search and filters. Nothing was approximated — widen
              the search or clear the filters.
            </p>
          )}
        </div>

        {/* P36R S10 — the same three attributes the Schema Reference and
            Settings API detail panes already carry, so the three master-detail
            panes this phase shipped behave identically for a screen reader.
            `tabIndex={-1}` is a programmatic focus target that adds no tab stop;
            the accessible name is whichever heading is showing. The name id is
            present in the empty, error and resolved states; the brief loading
            state carries its own `role="status"` announcement instead. */}
        <div
          className="concept-lookup-detailpane"
          id={CONCEPT_DETAIL_ID}
          role="region"
          tabIndex={-1}
          aria-labelledby={CONCEPT_DETAIL_NAME_ID}
        >
          {selectedId ? (
            <ConceptLookupPanelBody
              id={selectedId}
              onActivateConcept={activate}
              onShowInGraph={showInGraph}
              onNavigateFile={navigateToFile}
            />
          ) : (
            <div className="concept-lookup-detail-empty">
              <p id={CONCEPT_DETAIL_NAME_ID} className="concept-lookup-detail-empty-title">
                Select a concept to see where it is anchored.
              </p>
              <p className="concept-lookup-detail-empty-text">
                Each entry points back to the project document project memory read it from, plus any
                leads the current graph records for it. Nothing is fetched until you pick one.
              </p>
            </div>
          )}
        </div>
      </div>
      {/* P36V S-A concision: the standing caption "leads — open the cited file to
          verify" said nothing the card does not already say twice — the subtitle
          above ("memory leads, not scientific conclusions") is the page-level
          explanation, and the detail pane's boundary note carries "Open the cited
          source to judge it yourself" exactly where a cited source is on screen.
          Removed as a duplicate; neither surviving claim was weakened. */}
    </>
  );
}

interface ConceptLookupRowProps {
  concept: ApiMemoryConceptSummary;
  selected: boolean;
  /** Only when the marker actually distinguishes the VISIBLE rows — see `onDiskSpread`. */
  showOnDiskBadge: boolean;
  tabIndex: number;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
}

function ConceptLookupRow({
  concept,
  selected,
  showOnDiskBadge,
  tabIndex,
  onSelect,
  onKeyDown,
}: ConceptLookupRowProps) {
  const community = communityLabel(concept);
  // Upstream names a single-member cluster after its one member, so for most
  // real concepts `community_name` is character-for-character the label. Two
  // identical strings on one row is noise, not context — the cluster is still
  // stated in full in the detail panel, where it is a labelled field.
  const clusterChip = community && community !== concept.label ? community : null;

  // Selection comes from the native <button>: real browsers synthesize a click
  // from Enter (keydown) and Space (keyup), so no activation key is handled
  // here. `onKeyDown` only moves the roving-tabindex cursor (arrows/Home/End)
  // and never selects.
  return (
    <li className="concept-lookup-row">
      <button
        id={conceptRowId(concept.id)}
        type="button"
        className={`concept-lookup-row-btn${selected ? ' selected' : ''}`}
        aria-current={selected ? 'true' : undefined}
        aria-controls={CONCEPT_DETAIL_ID}
        tabIndex={tabIndex}
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        <ChevronRight className="concept-lookup-chevron" size={14} strokeWidth={2} aria-hidden="true" />
        <span className="concept-lookup-rowbody">
          {/* P36V S-A — the READABLE title (`lib/displayLabels.ts`), not the raw
              graph label. Presentation only: `concept.label` is untouched in
              state, still what search matches on, still what the cluster-chip
              suppression compares against, and still rendered verbatim in the
              detail pane's Technical Details disclosure. */}
          <span className="concept-lookup-label">{conceptDisplayTitle(concept.label)}</span>
          {(clusterChip || (showOnDiskBadge && !concept.on_disk)) && (
            <span className="concept-lookup-rowmeta">
              {clusterChip && <span className="concept-lookup-community">{clusterChip}</span>}
              {/* Filesystem presence, not snapshot membership — same `on_disk`
                  semantics documented at the detail render site. */}
              {showOnDiskBadge && !concept.on_disk && (
                <span className="concept-lookup-badge">source not in this deployment</span>
              )}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

interface ConceptDetailActions {
  onActivateConcept: (id: string) => void;
  onShowInGraph: (id: string) => void;
  onNavigateFile: (path: string) => void;
}

function ConceptLookupPanelBody({ id, ...actions }: { id: string } & ConceptDetailActions) {
  const detail = useFetch(() => api.getMemoryConcept(id), [id]);
  return (
    <>
      {detail.status === 'loading' && <LoadingPanel label="Loading provenance…" />}
      {detail.status === 'error' && (
        <div className="concept-lookup-panel-error">
          <p id={CONCEPT_DETAIL_NAME_ID}>Could not load provenance for this concept.</p>
          <button type="button" className="btn btn-secondary" onClick={detail.reload}>
            Retry
          </button>
        </div>
      )}
      {detail.status === 'data' && <ConceptLookupDetail data={detail.data} {...actions} />}
    </>
  );
}

/**
 * The plain-language description of ONE concept.
 *
 * There is no description field anywhere in the payload, and none is invented:
 * this describes what the ROW IS — where project memory found it, which
 * cluster the graph put it in, and how many leads it records — using only
 * `source_file`, `community_*` and the recorded `related` lists. When a field
 * is absent the sentence states the absence rather than filling it. It never
 * explains, defines or endorses the scientific term itself.
 */
export function describeConcept(
  concept: ApiMemoryConceptSummary,
  leadCount: number,
): string {
  // A null `source_file` has TWO real shapes behind it (`memory.py::
  // _served_source_file`): the graph node named no source at all, or it named
  // one that is unsafe/not governance-served and was therefore withheld. The
  // sentence must be true of both, so it states only what is observable here —
  // that no source document is named — and does not assert that one exists.
  const anchor = concept.source_file
    ? `Project memory anchored this concept in ${concept.source_file} while indexing this project's own files.`
    : 'Project memory names no source document for this concept — the graph either recorded none or pointed at one this deployment does not serve.';
  const community = communityLabel(concept);
  // Upstream names a cluster after one representative member, so a concept's
  // cluster name is very often the concept's own label. Repeating it back as
  // `grouped with the "<same words>" cluster` reads like a second fact; it is
  // not one, and this says exactly what the two equal fields mean.
  const cluster = !community
    ? 'The graph puts it in no cluster.'
    : community === concept.label
      ? 'Its cluster in the graph carries the same name as the concept itself.'
      : `The graph groups it with the "${community}" cluster.`;
  const leads =
    leadCount > 0
      ? `${leadCount} related lead${leadCount === 1 ? '' : 's'} ${leadCount === 1 ? 'is' : 'are'} recorded for it in the current graph.`
      : 'No related leads are recorded for it in the current graph.';
  return `${anchor} ${cluster} ${leads}`;
}

function ConceptLookupDetail({
  data,
  onActivateConcept,
  onShowInGraph,
  onNavigateFile,
}: { data: ApiMemoryConceptResponse } & ConceptDetailActions) {
  if (!data.available || !data.concept) {
    return (
      <p id={CONCEPT_DETAIL_NAME_ID} className="concept-lookup-panel-note">
        Concept lookup is unavailable — no memory graph is loaded in this deployment.
      </p>
    );
  }
  const { concept, related } = data;
  const community = communityLabel(concept);
  const leadCount = related.files.length + related.concepts.length;
  const hasLeads = leadCount > 0;

  return (
    <div className="concept-lookup-detail">
      {/* P36V S-A — the derived readable title (`lib/displayLabels.ts`). The raw
          `concept.label` is not gone: it is the first row of Technical Details
          below, verbatim and selectable. */}
      <h3 id={CONCEPT_DETAIL_NAME_ID} className="concept-lookup-detail-heading">
        {conceptDisplayTitle(concept.label)}
      </h3>
      <p className="concept-lookup-description">{describeConcept(concept, leadCount)}</p>
      {/* The one advisory note on this surface. The closing instruction is
          conditional: with no citable source there is nothing to open, and
          telling the reader to open one would be an instruction they cannot
          follow. */}
      <p className="concept-lookup-boundary">
        A concept is a pointer into project documents — never a definition of the term, and never a
        scientific conclusion.
        {concept.source_file ? ' Open the cited source to judge it yourself.' : ''}
      </p>

      {/* P36V S-A hierarchy: Anchor Source → Cluster → Related Leads → the graph
          action → Technical Details, each a labelled section under one heading
          level. The old inline "anchor source" eyebrow span is now this heading —
          the same two words, Title Cased. */}
      <div className="concept-lookup-section">
        <h4 className="concept-lookup-section-heading">Anchor Source</h4>
        <p className="concept-lookup-anchor">
          {concept.source_file ? (
            <button
              type="button"
              className="concept-lookup-anchor-link"
              onClick={() => onNavigateFile(concept.source_file as string)}
            >
              <span className="mono">{concept.source_file}</span>
              <span className="concept-lookup-anchor-action">open in Source Index</span>
            </button>
          ) : (
            // P24.9: render an honest note, never an empty mono span.
            // P36R S10: a null `source_file` covers BOTH shapes of
            // `memory.py::_served_source_file` — the graph node named no source
            // at all, or it named one that is unsafe / not governance-served and
            // was withheld. The old "anchor withheld (excluded source)" asserted
            // the second shape, i.e. that an excluded source exists. This states
            // only what is observable: no source is linked.
            <span className="concept-lookup-anchor-missing">no linked source</span>
          )}
        </p>
        {/* `on_disk` is a FILESYSTEM existence check on the backend
            (`memory.py::_on_disk`: resolves the path strictly under the repo root
            and never opens it). It says NOTHING about snapshot membership — every
            served file is in the snapshot's served-content manifest, and the
            deployed image simply does not copy `docs/`, which is why the hosted
            build reports `on_disk:false` for files it happily serves provenance
            for. Copy here must therefore speak about the deployment not carrying
            the file, never about the snapshot excluding it. */}
        {concept.source_file && !concept.on_disk && (
          <p className="concept-lookup-anchor-missing">
            This deployment does not carry the file itself — open it in the project to read it.
          </p>
        )}
      </div>

      {/* Same suppression rule as the row chip: upstream names a single-member
          cluster after its one member, so for most real concepts this section
          would restate the concept's own label. The fact is not dropped — the
          description states it ("Its cluster in the graph carries the same name
          as the concept itself"), and `Cluster Name` / `Cluster ID` are listed
          raw in Technical Details either way. A null community still renders,
          as "—", because that is a different fact. */}
      {community !== concept.label && (
        <div className="concept-lookup-section">
          <h4 className="concept-lookup-section-heading">Cluster</h4>
          <p className="concept-lookup-metavalue">{community ?? '—'}</p>
        </div>
      )}

      <div className="concept-lookup-section">
        <h4 className="concept-lookup-section-heading">Related Leads</h4>
        {hasLeads ? (
          <>
            {related.files.length > 0 && (
              <div className="concept-lookup-subsection">
                <h5 className="concept-lookup-subsection-heading">Files</h5>
                <ul className="concept-lookup-related-list">
                  {related.files.map((rf) => (
                    <li key={rf.path}>
                      <button
                        type="button"
                        className="concept-lookup-related-link"
                        onClick={() => onNavigateFile(rf.path)}
                      >
                        <span className="mono">{rf.path}</span>
                        {/* P36V PR2 slice B — the graph's own relation vocabulary
                            surfaces here as a lead. It is displayed through the
                            SAME closed five-value map the Graph tab uses, so
                            `imports` does not read as a raw token on one surface
                            and "Imports" on the other. A value outside that
                            measured set (e.g. `relates_to` below) passes through
                            verbatim — the `title` keeps the backend's exact
                            string either way. */}
                        {rf.relation && (
                          <span className="concept-lookup-relation" title={rf.relation}>
                            {relationDisplayLabel(rf.relation)}
                          </span>
                        )}
                        {rf.file_type && (
                          <span className="concept-lookup-relation">{rf.file_type}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {related.concepts.length > 0 && (
              <div className="concept-lookup-subsection">
                <h5 className="concept-lookup-subsection-heading">Concepts</h5>
                <ul className="concept-lookup-related-list">
                  {related.concepts.map((rc) => (
                    <li key={rc.id}>
                      <button
                        type="button"
                        className="concept-lookup-related-link"
                        onClick={() => onActivateConcept(rc.id)}
                      >
                        {/* P36V S-A — the SAME derivation the row and detail heading
                            use. Rendering the raw label here made one concept read
                            two ways on one surface: a lead said "Governance
                            allowlist" and activating it produced the heading
                            "Governance Allowlist". The raw value is still exact in
                            Technical Details once the lead is opened. */}
                        <span>{rc.label ? conceptDisplayTitle(rc.label) : rc.id}</span>
                        {rc.relation && (
                          <span className="concept-lookup-relation" title={rc.relation}>
                            {relationDisplayLabel(rc.relation)}
                          </span>
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

      <div className="concept-lookup-section">
        <div className="concept-lookup-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onShowInGraph(concept.id)}
          >
            Show in Graph Explore
          </button>
        </div>
        {/* No neighbourhood action, and no promise of one: the Graph tab's
            projection derives every edge from a FILE's `related.files[]`
            (`memory_graph.py::_build_edges`) and never from a concept's
            `related`, so a concept node carries zero edges whatever this
            endpoint returns. Recorded leads are real and are listed above — they
            are simply not edges of that projection. */}
        <p className="concept-lookup-action-note">
          {hasLeads
            ? "Explore selects this concept on the shared graph canvas. The graph's reference projection records no edges for concepts, so nothing will be drawn joining it to anything else — the leads above come from this concept's own record, not from that projection."
            : 'Explore selects this concept on the shared graph canvas. The current graph records no references to or from it, so nothing will be drawn joining it to anything else.'}
        </p>
      </div>

      {/* P36V S-A — every RAW value this pane knows, in one collapsed-by-default
          native disclosure. Nothing was deleted from the surface to make room
          for it: the graph label moved out of the heading (which now shows the
          derived title) and the concept id out of an unlabelled inline figure,
          and both are here verbatim, alongside the exact anchor path and the raw
          cluster identifiers — which the Cluster section deliberately suppresses
          when it would restate the concept itself. `<details>`/`<summary>` is the
          pattern already used by GraphDetail ("Raw node data") and the graph help
          drawer ("Technical Details"): keyboard-operable and named by its own
          summary, with no ARIA of our own. (MemoryGraphCard's "How this
          projection is built" disclosure, cited here before, no longer exists —
          this PR's slice B relocated its content into About This Graph.) */}
      <details className="concept-lookup-technical">
        <summary>Technical Details</summary>
        <dl className="concept-lookup-technical-figures">
          <div className="concept-lookup-technical-figure">
            <dt>Graph Label</dt>
            <dd className="mono">{concept.label}</dd>
          </div>
          <div className="concept-lookup-technical-figure">
            <dt>Concept ID</dt>
            <dd className="mono">{concept.id}</dd>
          </div>
          <div className="concept-lookup-technical-figure">
            <dt>Source File</dt>
            <dd className="mono">{concept.source_file ?? '—'}</dd>
          </div>
          <div className="concept-lookup-technical-figure">
            <dt>Cluster Name</dt>
            <dd className="mono">{concept.community_name ?? '—'}</dd>
          </div>
          <div className="concept-lookup-technical-figure">
            <dt>Cluster ID</dt>
            <dd className="mono">{concept.community_id ?? '—'}</dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

// --- pure helpers (derived only from the live response; no invented values) --

/** First 7 characters, the conventional "short sha" length — never truncates a shorter string.
 *  Exported for reuse by MemoryGraphCard (P36.2) — the Graph tab's provenance line. */
export function shortSha(commit: string): string {
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
 * Exported for reuse by MemoryGraphCard (P36.2) — the Graph tab's textual
 * file list groups the same way the Source Index does.
 */
export function groupFilesByType(files: ApiMemoryFileSummary[]): SourceIndexGroup[] {
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
export function humanizeFileType(fileType: string | null): string {
  if (fileType === null) return 'Other';
  if (fileType === 'code') return 'Code';
  if (fileType === 'document') return 'Documents';
  return fileType.charAt(0).toUpperCase() + fileType.slice(1);
}

/**
 * `community_name` when present; else the honest fallback "community <id>"
 * when only `community_id` is known; else `null` (never an invented name).
 */
export function communityLabel(file: {
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
export function domId(prefix: string, raw: string): string {
  return `${prefix}-${raw.replace(/[^a-zA-Z0-9]+/g, '-')}`;
}
