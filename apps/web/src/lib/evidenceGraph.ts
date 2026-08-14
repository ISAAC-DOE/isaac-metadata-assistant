/*
 * evidenceGraph — the SCIENTIST-FACING evidence graph, scoped to ONE experiment
 * and shaped around its RUNS.
 *
 * ── Three graphs now exist in this app. They are not interchangeable ────────
 *
 *   · `lib/graphModel.ts`      — the PROJECT MEMORY graph: repo file paths and
 *                                documentation concepts. A graph of the CODEBASE.
 *                                Nothing in this module reads it, imports from it
 *                                beyond pure geometry, or exposes any of its
 *                                concepts. A scientist looking at their own runs
 *                                must never be shown a module name or a repo path.
 *   · `lib/experimentGraph.ts` — the DRAFT-STRUCTURE graph: sections, fields, the
 *                                workflow, the exported record's blocks. It answers
 *                                "what is this record made of".
 *   · THIS MODULE              — the EVIDENCE graph: Experiment → Runs → the
 *                                grounded things each run actually carries, and the
 *                                evidence and validation state under them. It
 *                                answers "what belongs to Run 2", "what supports
 *                                this measurement", "which asset is referenced",
 *                                "where did this descriptor come from" and "which
 *                                validation issue belongs to which run".
 *
 * Geometry is REUSED, not forked: `computeLayout`, `screenBoundedUnits` and the
 * scale clamp come from `graphModel`, and `viewBoxFor` / `ViewportBox` from
 * `experimentGraph`, so the three canvases cannot drift apart on layout. The
 * DOMAIN is this module's own, because a second domain gets a second model rather
 * than a widened one.
 *
 * ── The rule that governs every line in this file ───────────────────────────
 *
 * EVERY node and EVERY edge derives from stored schema, provenance, evidence or
 * validation state, and says which. `NODE_PRODUCERS` and `EDGE_PRODUCERS` are the
 * closed, named lists, and every emitted node/edge carries its producer string
 * verbatim — a test asserts that no emitted producer is outside the list, which is
 * what stops a future slice from inventing a relationship that merely looks
 * plausible.
 *
 * NOTHING here infers scientific causality, and the surface says so out loud (see
 * {@link EVIDENCE_GRAPH_DISCLOSURE}). Specifically NOT emitted, because no
 * deterministic source for them exists:
 *
 *   · "this run caused that result" / any temporal or causal ordering between runs
 *     — `created_utc` orders records in time, which is not causation;
 *   · similarity between runs, samples or descriptors — no embeddings exist;
 *   · "same sample" inferred from a matching formula, batch string or sample id —
 *     a matching string is not an entity;
 *   · instrument / beamline / proposal identity across runs;
 *   · any interpretation of a value ("this edge shift indicates …") — nothing in
 *     this application computes one, and `review.py` is a NoOpReviewer;
 *   · anything at all sourced from the Graphify snapshot.
 *
 * `conflicts_with` is in the permitted vocabulary and is emitted ONLY from the
 * server's own `conflicting_evidence` classification, and even then only when the
 * classified address carries EXACTLY TWO evidence entries — because with three or
 * more, "these conflict" does not say WHICH PAIR disagrees, and drawing all pairs
 * would be an invention. That case is disclosed in words instead. See
 * {@link buildEvidenceGraph} step 6.
 *
 * ── Freshness ───────────────────────────────────────────────────────────────
 *
 * The graph itself holds NO cache: it is a pure function of the data handed to it,
 * rebuilt per render, so a stale evidence graph is structurally impossible rather
 * than merely unlikely. The ONE thing that is cached — a run's validation check,
 * because it costs a request — is keyed on the AUTHORITATIVE version tokens
 * (`detail.version` for the experiment, `run.version` for the run) and on the
 * workspace scope. See {@link RunCheckStore}: a key mismatch EVICTS rather than
 * serves. This repository has been bitten by a point-in-time projection presented
 * as current; there is no index here to go stale.
 *
 * Pure by construction: no React, no fetch, no DOM, no clock, no randomness.
 */
import type {
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiMemoryGraphEdge,
  ApiRunCheckFinding,
  ApiRunCheckResponse,
  ApiRunView,
  FieldEvidence,
} from './types';
import {
  MAX_SCALE,
  MIN_SCALE,
  VIEW_EXTENT,
  computeLayout,
  type GraphPoint,
  type GraphViewport,
} from './graphModel';
import {
  DEFAULT_VIEWPORT_BOX,
  shortLabel,
  viewBoxFor,
  type ViewportBox,
} from './experimentGraph';
import { runFindingText } from './runFields';
import { inheritedTally } from './runOverrides';
import { titleCase } from './labels';

export { MAX_SCALE, MIN_SCALE, VIEW_EXTENT, DEFAULT_VIEWPORT_BOX, shortLabel, viewBoxFor };
export type { ViewportBox, GraphPoint, GraphViewport };

// ------------------------------------------------------------------ the disclosure

/**
 * The sentence this surface must always carry, verbatim.
 *
 * It is a CONSTANT rather than copy inside a component so that the test which
 * asserts it is on screen cannot pass against a paraphrase, and so that the two
 * places that state it (the panel header and the "what this will not draw"
 * details) cannot drift into saying different things.
 */
export const EVIDENCE_GRAPH_DISCLOSURE =
  'Edges show recorded schema, evidence, and provenance relationships — not inferred scientific causality.';

// ------------------------------------------------------------------ bounds

/**
 * Hard cap on nodes in ONE evidence graph.
 *
 * The run list is BOUNDED for measured reasons (`docs/run-scale-measurements.md`:
 * the cost is the payload, ~7.5 KiB per run, and 1000 runs is 7.47 MiB and an
 * unusable 10.3 s load). This graph must not undo that, so it never asks for more
 * runs than the reader has loaded, and this cap bounds what the bounded page can
 * still expand into — a run carrying thousands of addresses degrades VISIBLY, with
 * a note, instead of freezing the browser.
 */
export const MAX_EVIDENCE_GRAPH_NODES = 1200;

/** Bound on nodes DRAWN at once. Progressive disclosure means the anchor's
 *  neighbourhood plus whatever the reader explicitly opened — never everything. */
export const MAX_VISIBLE_EVIDENCE_NODES = 200;

/** Bound on the in-graph search result list. An unbounded list is not a result. */
export const MAX_EVIDENCE_SEARCH_RESULTS = 12;

// ------------------------------------------------------- closed vocabularies

/**
 * The CLOSED set of node kinds — the scientist's vocabulary, not the schema's and
 * certainly not the repository's.
 */
export const EVIDENCE_NODE_KINDS = [
  'experiment',
  'run',
  'sample',
  'context',
  'measurement',
  'asset',
  'descriptor',
  'evidence_entry',
  'evidence_source',
  'validation_finding',
] as const;

export type EvidenceNodeKind = (typeof EVIDENCE_NODE_KINDS)[number];

/**
 * The CLOSED set of edge kinds — exactly the permitted relationship kinds, and
 * nothing else. A kind absent from this list cannot be constructed, because
 * {@link EvidenceGraphEdge.kind} is typed by it.
 */
export const EVIDENCE_EDGE_KINDS = [
  'has_run',
  'performed_on',
  'measured_under',
  'has_context',
  'has_descriptor',
  'references',
  'supported_by',
  'derived_from',
  'validated_by',
  'conflicts_with',
] as const;

export type EvidenceEdgeKind = (typeof EVIDENCE_EDGE_KINDS)[number];

/** The five GROUPED child kinds an address can land in. */
export const GROUP_KINDS = ['sample', 'context', 'measurement', 'asset', 'descriptor'] as const;

export type GroupKind = (typeof GROUP_KINDS)[number];

/**
 * The named deterministic producer for each node kind — the answer to "where did
 * this come from?", shown verbatim in the details pane. A kind with no producer is
 * a kind that should not exist.
 *
 * Note what is NOT here: no file path, no module name, no repository concept. The
 * only "file" this graph ever names is a SOURCE FILE a scientist's own evidence
 * cites (a campaign spreadsheet, an archive listing), which is the scientist's
 * artifact and is already shown on the Evidence screen beside this one.
 */
export const NODE_PRODUCERS: Readonly<Record<EvidenceNodeKind, string>> = Object.freeze({
  experiment: 'Experiment.id / Experiment.title (GET /api/experiments/{id})',
  run: 'one element of runs[] (GET /api/experiments/{id}/runs)',
  sample:
    'the sample.* addresses this owner actually resolves (run.fields / run.inherited, or the evidence trail)',
  context:
    'the context.* addresses this owner actually resolves (run.fields / run.inherited, or the evidence trail)',
  measurement:
    'the measurement.* / series* / qc* addresses this owner actually resolves (run.fields / run.inherited, or the evidence trail)',
  asset:
    'the assets* addresses this owner actually resolves (run.fields / run.inherited, or the evidence trail)',
  descriptor:
    'the descriptors* addresses this owner actually resolves (run.fields / run.inherited, or the evidence trail)',
  evidence_entry:
    'one stored evidence entry — run.fields[address].evidence[] for a run, GET /api/experiments/{id}/evidence for the experiment',
  evidence_source:
    'the source recorded ON an evidence entry: its source_file, its derivation rule, or your own confirmation',
  validation_finding:
    'one finding of the run check (POST /api/experiments/{id}/runs/{runId}/check) — blockers, draft errors, official-schema errors',
});

/**
 * The named producers for each EDGE kind. An edge carries one of these strings
 * verbatim, and a test asserts membership — so "every edge kind traces to stored
 * state" is checked mechanically rather than asserted in a comment.
 *
 * Two kinds carry more than one producer, and both are deliberate rather than
 * sloppy: `references` joins an owner to an asset AND an owner to nothing else,
 * while `derived_from` covers both an evidence entry's own recorded source and a
 * run value the SERVER reports as inherited from the experiment. Each producer
 * names exactly which stored field it read.
 */
export const EDGE_PRODUCERS: Readonly<Record<EvidenceEdgeKind, readonly string[]>> = Object.freeze({
  has_run: ['runs[].experiment_id (GET /api/experiments/{id}/runs)'],
  performed_on: ['a sample.* address present on this owner'],
  measured_under: ['a measurement.* / series* / qc* address present on this owner'],
  has_context: ['a context.* address present on this owner'],
  has_descriptor: ['a descriptors* address present on this owner'],
  references: ['an assets* address present on this owner'],
  supported_by: ['a stored evidence entry recorded at an address in this group'],
  derived_from: [
    'the source recorded on this evidence entry (source_file / rule / user confirmation)',
    "the server's own inherited state for this run (run.inherited[address].state === 'inherited')",
  ],
  validated_by: ['a finding of the run check (POST .../runs/{runId}/check)'],
  conflicts_with: [
    "the server's evidence-support classification `conflicting_evidence` at an address carrying exactly two entries",
  ],
});

/** Product-facing name for each node kind. */
export const NODE_KIND_LABELS: Readonly<Record<EvidenceNodeKind, string>> = Object.freeze({
  experiment: 'Experiment',
  run: 'Run',
  sample: 'Sample',
  context: 'Context',
  measurement: 'Measurement',
  asset: 'Asset',
  descriptor: 'Descriptor',
  evidence_entry: 'Evidence Entry',
  evidence_source: 'Evidence Source',
  validation_finding: 'Validation Finding',
});

/** Product-facing name for each edge kind, for the legend and the details pane. */
export const EDGE_KIND_LABELS: Readonly<Record<EvidenceEdgeKind, string>> = Object.freeze({
  has_run: 'has run',
  performed_on: 'performed on',
  measured_under: 'measured under',
  has_context: 'has context',
  has_descriptor: 'has descriptor',
  references: 'references',
  supported_by: 'supported by',
  derived_from: 'derived from',
  validated_by: 'validated by',
  conflicts_with: 'conflicts with',
});

/** The containment edge kind for each grouped child — one map, no second copy. */
const GROUP_EDGE_KIND: Readonly<Record<GroupKind, EvidenceEdgeKind>> = Object.freeze({
  sample: 'performed_on',
  context: 'has_context',
  measurement: 'measured_under',
  asset: 'references',
  descriptor: 'has_descriptor',
});

/** Stable reading order for a run's children, so two runs never differ in shape. */
export const GROUP_ORDER: readonly GroupKind[] = GROUP_KINDS;

// ------------------------------------------------------------------ types

export interface EvidenceGraphDetailLine {
  term: string;
  value: string;
}

export interface EvidenceGraphNode {
  id: string;
  kind: EvidenceNodeKind;
  label: string;
  /** The exact deterministic producer that emitted THIS node. */
  producer: string;
  /** Already-stored facts. Nothing here is computed from science. */
  detail: EvidenceGraphDetailLine[];
  /** The run this node belongs to, or null for experiment-level nodes. */
  runId: string | null;
  /**
   * The node this one hangs under in the CONTAINMENT tree — which is what makes a
   * non-visual, keyboard-navigable equivalent of the diagram possible at all. Null
   * for the experiment. Cross-links (`conflicts_with`, run→experiment
   * `derived_from`) are NOT parents; they are reachable from the details pane.
   */
  parentId: string | null;
}

export interface EvidenceGraphEdge {
  source: string;
  target: string;
  kind: EvidenceEdgeKind;
  /** One of EDGE_PRODUCERS[kind], verbatim. */
  producer: string;
  /** The sentence the details pane shows — WHY this edge exists. Never a claim
   *  the producer cannot support. */
  why: string;
  /** A short verbatim tag when the stored state carries one. */
  label: string | null;
  /** True when this edge is the containment edge that puts target under source. */
  containment: boolean;
}

export interface EvidenceGraphAdjacent {
  id: string;
  edge: EvidenceGraphEdge;
  /** true when this node is the edge's `target` (the edge points AT it). */
  incoming: boolean;
}

export type EvidenceGraphNoteKind =
  | 'no_runs'
  | 'runs_bounded'
  | 'unmodelled_addresses'
  | 'unreadable_evidence'
  | 'conflict_pair_unknown'
  | 'checks_on_demand'
  | 'focus_run_unknown'
  | 'node_cap'
  | 'visible_cap';

export interface EvidenceGraphNote {
  kind: EvidenceGraphNoteKind;
  text: string;
}

export interface EvidenceGraph {
  /** Where a reader starts: the focused run when one is named, else the experiment. */
  anchorId: string;
  /** The experiment node id — the tree root, focused or not. */
  rootId: string;
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  byId: Map<string, EvidenceGraphNode>;
  adjacency: Map<string, EvidenceGraphAdjacent[]>;
  /** Containment children, in stable order. The backbone of the accessible tree. */
  childrenOf: Map<string, string[]>;
  /** Deterministic coordinates for EVERY node — expanding never reshuffles. */
  layout: Map<string, GraphPoint>;
  counts: Record<EvidenceNodeKind, number>;
  /** Run node ids in server order. */
  runOrder: string[];
  notes: EvidenceGraphNote[];
  truncated: boolean;
  /** The freshness key this graph was built under. Rendered, never hidden. */
  freshnessKey: string;
}

/** The four numbers the runs route always sends — quoted, never recomputed. */
export interface EvidenceGraphRunsMeta {
  total: number;
  matched: number;
  returned: number;
  offset: number;
}

export interface EvidenceGraphInput {
  detail: ApiExperimentDetail;
  /** The runs actually LOADED — a bounded page, never "all runs". */
  runs: ApiRunView[];
  runsMeta: EvidenceGraphRunsMeta;
  /** The experiment-level evidence trail (GET .../evidence). */
  evidence: ApiEvidenceEntry[];
  /** The evidence-support classification (GET .../evidence-classification). */
  classification: ApiEvidenceClassification;
  /** Run checks that have ALREADY been fetched, by run id. Absent = not fetched. */
  checks: Record<string, ApiRunCheckResponse>;
  /** The `?run=` focus, if any. An id naming no loaded run is stated, not guessed. */
  focusRunId?: string | null;
}

/**
 * TUTORIAL ISOLATION, as a value rather than as a convention — the same guard
 * `experimentGraph` states, for the same reason: the worked-example records exist
 * only inside a temporary session workspace, and a graph built from one must never
 * keep rendering once the surface is addressing the other.
 */
export interface EvidenceGraphScope {
  readIn: string | null;
  current: string | null;
}

export type EvidenceGraphResult =
  | { ok: true; graph: EvidenceGraph }
  | { ok: false; reason: 'workspace_scope_changed'; message: string };

// ------------------------------------------------------------------ freshness

/**
 * The FRESHNESS KEY. Everything cached on this surface is keyed on it, and a key
 * mismatch evicts rather than serves.
 *
 * It is the workspace scope plus the experiment's own authoritative version token
 * (`detail.version`, the `"<generation>.<rev>"` string the backend issues and the
 * client echoes as `If-Match`). Not a timestamp, not a fetch count, not a boolean
 * "loaded" — the same token the write path uses for optimistic concurrency, so a
 * cache entry survives exactly as long as the server says the record has not moved.
 */
export function evidenceGraphFreshnessKey(
  scope: string | null,
  experimentVersion: string,
): string {
  return `${scope ?? ''}|${experimentVersion}`;
}

/**
 * The one cache on this surface: a run's validation check, which costs a request
 * and is therefore fetched only when a reader opens that run.
 *
 * Keyed TWICE — on the experiment-level {@link evidenceGraphFreshnessKey} for the
 * whole store, and on the RUN's own `version` per entry. Either moving means the
 * cached verdict describes a document that no longer exists, and the read returns
 * null rather than a stale verdict.
 */
export interface RunCheckStore {
  key: string;
  entries: Record<string, { runVersion: string; check: ApiRunCheckResponse }>;
}

export function emptyRunCheckStore(key: string): RunCheckStore {
  return { key, entries: {} };
}

/** Re-key the store. A DIFFERENT key discards every entry — this is the eviction. */
export function rekeyRunCheckStore(store: RunCheckStore, key: string): RunCheckStore {
  return store.key === key ? store : emptyRunCheckStore(key);
}

/** The cached check for this run AT THIS VERSION, or null. Never a stale verdict. */
export function readRunCheck(
  store: RunCheckStore,
  runId: string,
  runVersion: string,
): ApiRunCheckResponse | null {
  const hit = store.entries[runId];
  if (!hit) return null;
  return hit.runVersion === runVersion ? hit.check : null;
}

export function writeRunCheck(
  store: RunCheckStore,
  runId: string,
  runVersion: string,
  check: ApiRunCheckResponse,
): RunCheckStore {
  return { key: store.key, entries: { ...store.entries, [runId]: { runVersion, check } } };
}

/** The checks map the builder takes, projected out of the store. */
export function checksFromStore(
  store: RunCheckStore,
  runs: readonly ApiRunView[],
): Record<string, ApiRunCheckResponse> {
  const out: Record<string, ApiRunCheckResponse> = {};
  for (const run of runs) {
    const check = readRunCheck(store, run.id, run.version);
    if (check) out[run.id] = check;
  }
  return out;
}

// ------------------------------------------------------------------ addressing

const byIdAsc = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

const clampScale = (s: number): number => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/**
 * Strip the DRAFT-ADDRESS namespace a run's `inherited` map uses.
 *
 * That map is keyed `field:<dotted path>` for a scalar field and `block:<dotted
 * path>` for a whole structured block (`lib/runOverrides.ts` names both prefixes).
 * Both are addressing conventions, not part of the schema path, so both come off.
 *
 * Any OTHER namespace (`assets:`, `descriptors:`, `series:`, `qc:`, `implicit:`)
 * is kept intact, because there the namespace IS the address — those are the
 * namespaced evidence keys the trail itself uses.
 */
export function bareAddress(address: string): string {
  if (address.startsWith('field:')) return address.slice('field:'.length);
  if (address.startsWith('block:')) return address.slice('block:'.length);
  return address;
}

export interface AddressGroup {
  kind: GroupKind;
  /** The identity of the item within its group — one per asset, one per group otherwise. */
  itemKey: string;
  /** The product-facing name for the item. */
  label: string;
}

const ASSET_INDEX = /^assets\[(\d+)\]/;
const DESCRIPTOR_ITEM = /^(descriptors\.outputs\[\d+\]\.descriptors\[\d+\])/;

/**
 * Which grouped child an address belongs to, or `null` when this view does not
 * model it.
 *
 * `null` is a RESULT, not a failure: `system.*`, `timestamps.*` and
 * `attribution.*` are real addresses that this scientist-facing view does not
 * draw, and the builder COUNTS them and says so on the owner rather than
 * dropping them silently. Guessing them into "Measurement" because an instrument
 * feels measurement-ish would be exactly the invention this graph refuses.
 */
export function groupForAddress(rawAddress: string): AddressGroup | null {
  const address = bareAddress(rawAddress);
  const colon = address.indexOf(':');
  if (colon > 0) {
    const ns = address.slice(0, colon);
    const name = address.slice(colon + 1);
    if (ns === 'assets') return { kind: 'asset', itemKey: address, label: name || 'Asset' };
    if (ns === 'descriptors') {
      return { kind: 'descriptor', itemKey: address, label: name || 'Descriptor' };
    }
    if (ns === 'series' || ns === 'qc' || ns === 'measurement') {
      return { kind: 'measurement', itemKey: 'measurement', label: 'Measurement' };
    }
    if (ns === 'sample') return { kind: 'sample', itemKey: 'sample', label: 'Sample' };
    if (ns === 'context') return { kind: 'context', itemKey: 'context', label: 'Context' };
    return null;
  }

  const head = address.split(/[.[]/)[0];
  if (head === 'sample') return { kind: 'sample', itemKey: 'sample', label: 'Sample' };
  if (head === 'context') return { kind: 'context', itemKey: 'context', label: 'Context' };
  if (head === 'measurement' || head === 'series' || head === 'qc') {
    return { kind: 'measurement', itemKey: 'measurement', label: 'Measurement' };
  }
  if (head === 'assets') {
    const m = ASSET_INDEX.exec(address);
    return m
      ? { kind: 'asset', itemKey: m[0], label: `Asset ${Number(m[1]) + 1}` }
      : { kind: 'asset', itemKey: 'assets', label: 'Assets' };
  }
  if (head === 'descriptors') {
    const m = DESCRIPTOR_ITEM.exec(address);
    return m
      ? { kind: 'descriptor', itemKey: m[1], label: 'Descriptor' }
      : { kind: 'descriptor', itemKey: 'descriptors', label: 'Descriptors' };
  }
  return null;
}

// ------------------------------------------------------------------ node ids

export const nodeIds = {
  experiment: (id: string) => `experiment:${id}`,
  run: (runId: string) => `run:${runId}`,
  group: (ownerId: string, kind: GroupKind, itemKey: string) => `${ownerId}/${kind}/${itemKey}`,
  evidence: (ownerId: string, address: string, index: number) =>
    `${ownerId}#ev#${address}#${index}`,
  sourceFile: (file: string) => `source:file:${file}`,
  sourceRule: (rule: string) => `source:rule:${rule}`,
  sourceConfirmation: (question: string, timestamp: string) =>
    `source:confirmation:${question}#${timestamp}`,
  finding: (runId: string, origin: string, index: number) =>
    `finding:${runId}:${origin}#${index}`,
} as const;

// ------------------------------------------------------------------ narrowing

/**
 * Narrow ONE stored evidence item to a readable entry, or return null.
 *
 * `ApiRunFieldEnvelope.evidence` is `unknown[]` on the wire and the contract does
 * not freeze its element shape, so this is a real read rather than a cast. An item
 * that carries no `source_type` string cannot be described, and is COUNTED and
 * disclosed rather than rendered as an entry with invented provenance.
 */
export function readEvidenceItem(item: unknown): FieldEvidence | null {
  if (typeof item !== 'object' || item === null || Array.isArray(item)) return null;
  const rec = item as Record<string, unknown>;
  const sourceType = rec.source_type;
  if (typeof sourceType !== 'string' || sourceType === '') return null;
  const str = (v: unknown): string | undefined =>
    typeof v === 'string' && v !== '' ? v : undefined;
  return {
    source_type: sourceType as FieldEvidence['source_type'],
    source_file: str(rec.source_file),
    locator: str(rec.locator),
    quote: str(rec.quote),
    question: str(rec.question),
    answer: str(rec.answer),
    timestamp: str(rec.timestamp),
    rule: str(rec.rule),
  };
}

function valueText(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value === 'string') return value === '' ? undefined : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return shortLabel(JSON.stringify(value), 120);
  } catch {
    return undefined;
  }
}

/** The `{value,status,evidence}` envelope shape, read defensively. */
function readEnvelope(
  payload: unknown,
): { value: unknown; status?: string; evidence: unknown[] } | null {
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return null;
  const rec = payload as Record<string, unknown>;
  return {
    value: rec.value,
    status: typeof rec.status === 'string' ? rec.status : undefined,
    evidence: Array.isArray(rec.evidence) ? rec.evidence : [],
  };
}

function evidenceEntryLabel(ev: FieldEvidence): string {
  if (ev.source_type === 'derivation') return 'Derivation';
  if (ev.source_type === 'user_confirmation') return 'Your confirmation';
  if (ev.source_file) return shortLabel(ev.source_file, 34);
  return titleCase(ev.source_type.replace(/_/g, ' '));
}

const SOURCE_TYPE_PHRASE: Readonly<Record<string, string>> = Object.freeze({
  spreadsheet: 'the campaign spreadsheet',
  file_listing: 'the archive file listing',
  derivation: 'a documented derivation rule',
  user_confirmation: 'your own confirmation',
  document: 'a document',
  screenshot: 'a screenshot',
  web_form: 'the submitted web form',
});

function supportWhy(ev: FieldEvidence, address: string): string {
  if (ev.source_type === 'derivation') {
    return ev.rule
      ? `Recorded at ${address}, derived by a documented rule: ${ev.rule}`
      : `Recorded at ${address}, derived by a documented rule (no rule text was stored).`;
  }
  if (ev.source_type === 'user_confirmation') {
    const when = ev.timestamp ? ` on ${ev.timestamp}` : '';
    return ev.question
      ? `Recorded at ${address}, confirmed by you${when} — you were asked: "${ev.question}"`
      : `Recorded at ${address}, confirmed by you${when}.`;
  }
  const where = SOURCE_TYPE_PHRASE[ev.source_type] ?? ev.source_type;
  const file = ev.source_file ? ` from ${ev.source_file}` : '';
  const at = ev.locator ? ` — ${ev.locator}` : '';
  return `Recorded at ${address}, supported by evidence read from ${where}${file}${at}.`;
}

function evidenceDetailLines(ev: FieldEvidence, address: string): EvidenceGraphDetailLine[] {
  const lines: EvidenceGraphDetailLine[] = [
    { term: 'Address', value: address },
    { term: 'Source type', value: ev.source_type },
  ];
  if (ev.source_file) lines.push({ term: 'Source file', value: ev.source_file });
  if (ev.locator) lines.push({ term: 'Locator', value: ev.locator });
  if (ev.quote) lines.push({ term: 'Quoted', value: ev.quote });
  if (ev.rule) lines.push({ term: 'Rule', value: ev.rule });
  if (ev.question) lines.push({ term: 'Question', value: ev.question });
  if (ev.answer) lines.push({ term: 'Your answer', value: ev.answer });
  if (ev.timestamp) lines.push({ term: 'Confirmed', value: ev.timestamp });
  return lines;
}

// ------------------------------------------------------------------ the builder

class Builder {
  readonly nodes = new Map<string, EvidenceGraphNode>();
  readonly edges: EvidenceGraphEdge[] = [];
  private readonly edgeSeen = new Set<string>();
  readonly notes: EvidenceGraphNote[] = [];
  truncated = false;

  addNode(node: EvidenceGraphNode): string | null {
    const existing = this.nodes.get(node.id);
    if (existing) {
      for (const line of node.detail) {
        if (!existing.detail.some((l) => l.term === line.term && l.value === line.value)) {
          existing.detail.push(line);
        }
      }
      return existing.id;
    }
    if (this.nodes.size >= MAX_EVIDENCE_GRAPH_NODES) {
      this.truncated = true;
      return null;
    }
    this.nodes.set(node.id, node);
    return node.id;
  }

  /**
   * An edge is kept ONLY when both endpoints already exist as nodes, and only
   * when its producer is one of the declared producers for its kind. Nothing is
   * repaired, and no endpoint is created to make an edge possible.
   */
  addEdge(edge: EvidenceGraphEdge): void {
    if (edge.source === edge.target) return;
    if (!this.nodes.has(edge.source) || !this.nodes.has(edge.target)) return;
    if (!EDGE_PRODUCERS[edge.kind].includes(edge.producer)) return;
    const key = `${edge.kind} ${edge.source} ${edge.target}`;
    if (this.edgeSeen.has(key)) return;
    this.edgeSeen.add(key);
    this.edges.push(edge);
  }

  note(kind: EvidenceGraphNoteKind, text: string): void {
    if (this.notes.some((n) => n.kind === kind)) return;
    this.notes.push({ kind, text });
  }
}

/**
 * Build the evidence graph.
 *
 * Deterministic by construction: the same input always produces the same nodes,
 * the same edges in the same order, and byte-identical coordinates.
 */
export function buildEvidenceGraph(
  input: EvidenceGraphInput,
  scope: EvidenceGraphScope = { readIn: null, current: null },
): EvidenceGraphResult {
  if (scope.readIn !== scope.current) {
    return {
      ok: false,
      reason: 'workspace_scope_changed',
      message:
        'This graph was read in a different workspace. A worked-example session and the ordinary workspace hold different experiments, so nothing loaded here describes the workspace now being addressed.',
    };
  }

  const b = new Builder();
  const { detail, runs, runsMeta, evidence, classification, checks } = input;
  const freshnessKey = evidenceGraphFreshnessKey(scope.current, detail.version);

  // ── 1. the experiment (the tree root) ─────────────────────────────────────
  const rootId = nodeIds.experiment(detail.id);
  b.addNode({
    id: rootId,
    kind: 'experiment',
    label: detail.title,
    producer: NODE_PRODUCERS.experiment,
    detail: [
      { term: 'Experiment id', value: detail.id },
      { term: 'Status', value: detail.status },
      { term: 'Version', value: detail.version },
      { term: 'Runs in this record', value: String(runsMeta.total) },
      { term: 'Runs loaded here', value: String(runsMeta.returned) },
    ],
    runId: null,
    parentId: null,
  });

  /** address → the group node it belongs to, per owner. Also the unmodelled count. */
  interface OwnerGroups {
    ownerId: string;
    runId: string | null;
    byItem: Map<string, string>;
    unmodelled: Map<string, number>;
  }

  const ownerGroups = new Map<string, OwnerGroups>();
  const groupsFor = (ownerId: string, runId: string | null): OwnerGroups => {
    const known = ownerGroups.get(ownerId);
    if (known) return known;
    const fresh: OwnerGroups = { ownerId, runId, byItem: new Map(), unmodelled: new Map() };
    ownerGroups.set(ownerId, fresh);
    return fresh;
  };

  /**
   * Ensure the grouped child for `address` under `ownerId`, or record it as
   * unmodelled. Returns the group node id, or null.
   *
   * `addresses` accumulates on the node's detail so a reader can see EXACTLY which
   * stored addresses put this node on screen — the node is not an assertion that
   * "this run has a sample", it is the list of sample addresses this run resolves.
   */
  const ensureGroup = (
    ownerId: string,
    runId: string | null,
    address: string,
    note: string,
  ): string | null => {
    const groups = groupsFor(ownerId, runId);
    const group = groupForAddress(address);
    if (!group) {
      const head = bareAddress(address).split(/[.:[]/)[0];
      groups.unmodelled.set(head, (groups.unmodelled.get(head) ?? 0) + 1);
      return null;
    }
    const id = nodeIds.group(ownerId, group.kind, group.itemKey);
    const known = groups.byItem.get(`${group.kind}/${group.itemKey}`);
    if (known) {
      const node = b.nodes.get(known);
      if (node && !node.detail.some((l) => l.term === 'Address' && l.value === address)) {
        node.detail.push({ term: 'Address', value: address });
      }
      return known;
    }
    const added = b.addNode({
      id,
      kind: group.kind,
      label: group.label,
      producer: NODE_PRODUCERS[group.kind],
      detail: [
        { term: 'Why this is here', value: note },
        { term: 'Address', value: address },
      ],
      runId,
      parentId: ownerId,
    });
    if (!added) return null;
    groups.byItem.set(`${group.kind}/${group.itemKey}`, added);
    b.addEdge({
      source: ownerId,
      target: added,
      kind: GROUP_EDGE_KIND[group.kind],
      producer: EDGE_PRODUCERS[GROUP_EDGE_KIND[group.kind]][0],
      why: `${note} The first one is ${address}; the node lists every address it stands for.`,
      label: null,
      containment: true,
    });
    return added;
  };

  /** Attach one readable evidence entry (and its source) under a group node. */
  let unreadableEvidence = 0;
  const attachEvidence = (
    ownerNodeId: string,
    ownerRunId: string | null,
    address: string,
    items: readonly unknown[],
    producer: string,
  ): string[] => {
    const made: string[] = [];
    items.forEach((raw, index) => {
      const ev = readEvidenceItem(raw);
      if (!ev) {
        unreadableEvidence += 1;
        return;
      }
      const evId = b.addNode({
        id: nodeIds.evidence(ownerNodeId, address, index),
        kind: 'evidence_entry',
        label: evidenceEntryLabel(ev),
        producer,
        detail: evidenceDetailLines(ev, address),
        runId: ownerRunId,
        parentId: ownerNodeId,
      });
      if (!evId) return;
      made.push(evId);
      b.addEdge({
        source: ownerNodeId,
        target: evId,
        kind: 'supported_by',
        producer: EDGE_PRODUCERS.supported_by[0],
        why: supportWhy(ev, address),
        label: ev.source_type,
        containment: true,
      });

      // ── the evidence entry's OWN recorded source ──────────────────────────
      let sourceId: string | null = null;
      let sourceWhy = '';
      if (ev.source_type === 'user_confirmation' || ev.question || ev.answer) {
        const question = ev.question ?? '(no question was stored)';
        const timestamp = ev.timestamp ?? '(no timestamp was stored)';
        sourceId = b.addNode({
          id: nodeIds.sourceConfirmation(question, timestamp),
          kind: 'evidence_source',
          label: ev.timestamp ? `Your confirmation · ${ev.timestamp.slice(0, 10)}` : 'Your confirmation',
          producer: NODE_PRODUCERS.evidence_source,
          detail: [
            { term: 'Question', value: question },
            ...(ev.answer ? [{ term: 'Your answer', value: ev.answer }] : []),
            { term: 'Timestamp', value: timestamp },
          ],
          runId: ownerRunId,
          parentId: evId,
        });
        sourceWhy = ev.timestamp
          ? `This entry records your own confirmation, made on ${ev.timestamp}.`
          : 'This entry records your own confirmation; no timestamp was stored with it.';
      } else if (ev.rule) {
        sourceId = b.addNode({
          id: nodeIds.sourceRule(ev.rule),
          kind: 'evidence_source',
          label: shortLabel(ev.rule, 44),
          producer: NODE_PRODUCERS.evidence_source,
          detail: [{ term: 'Rule', value: ev.rule }],
          runId: ownerRunId,
          parentId: evId,
        });
        sourceWhy = `This entry was derived by a documented rule: ${ev.rule}`;
      } else if (ev.source_file) {
        sourceId = b.addNode({
          id: nodeIds.sourceFile(ev.source_file),
          kind: 'evidence_source',
          label: ev.source_file,
          producer: NODE_PRODUCERS.evidence_source,
          detail: [
            { term: 'Source file', value: ev.source_file },
            ...(ev.locator ? [{ term: 'Locator', value: ev.locator }] : []),
          ],
          runId: ownerRunId,
          parentId: evId,
        });
        sourceWhy = ev.locator
          ? `This entry cites ${ev.source_file} — ${ev.locator}.`
          : `This entry cites ${ev.source_file}.`;
      }
      if (sourceId) {
        b.addEdge({
          source: evId,
          target: sourceId,
          kind: 'derived_from',
          producer: EDGE_PRODUCERS.derived_from[0],
          why: sourceWhy,
          label: null,
          containment: true,
        });
      }
    });
    return made;
  };

  // ── 2. the experiment's own grouped children, from the evidence trail ─────
  //
  // The experiment side is built from the evidence trail rather than from the
  // draft, because THIS surface is the evidence view: an experiment-level node
  // exists here exactly when something is recorded under it.
  /** address → the evidence-entry node ids built for it, experiment-level. */
  const experimentEntriesByAddress = new Map<string, string[]>();
  const experimentGroupByAddress = new Map<string, string>();

  for (const entry of [...evidence].sort((x, y) => byIdAsc(x.path, y.path))) {
    const groupId = ensureGroup(
      rootId,
      null,
      entry.path,
      'This experiment records evidence at addresses in this part of the record.',
    );
    if (!groupId) continue;
    experimentGroupByAddress.set(entry.path, groupId);
    if (entry.unavailable) {
      const node = b.nodes.get(groupId);
      node?.detail.push({
        term: 'Unreadable entry',
        value: `${entry.path} — ${entry.unavailable_reason ?? 'the stored evidence could not be read'}. It is not drawn, and nothing is invented in its place.`,
      });
      continue;
    }
    const made = attachEvidence(
      groupId,
      null,
      entry.path,
      entry.evidence ?? [],
      NODE_PRODUCERS.evidence_entry,
    );
    experimentEntriesByAddress.set(entry.path, made);
  }

  // ── 3. the runs ───────────────────────────────────────────────────────────
  const runOrder: string[] = [];
  for (const run of runs) {
    const runNodeId = nodeIds.run(run.id);
    const ownAddresses = Object.keys(run.fields ?? {}).sort(byIdAsc);
    const inheritedAddresses = Object.keys(run.inherited ?? {}).sort(byIdAsc);

    /*
     * THE COUNTS COME FROM `inheritedTally`, THE STRUCTURE DOES NOT — and the
     * split is deliberate.
     *
     * `runOverrides.inheritedTally` / `overrideRows` already own the decisions
     * about what an inheritance row IS, with tests behind each: `block:`
     * addresses are excluded, `absent` is excluded, a value that is not
     * one-line renderable is withheld, and `overridable` is read fail-closed.
     * Recounting here would put a second copy of those decisions on screen,
     * free to drift from the Runs section's own numbers. So the NUMBERS are
     * quoted from it.
     *
     * The graph's STRUCTURE cannot use `overrideRows`, and that is not a
     * disagreement with it. That function shapes rows for an override FORM, so
     * it deliberately drops exactly what a structural view must keep: a
     * `block:sample.material` address is a real Sample this run resolves, and an
     * object-valued measurement is a real Measurement. Dropping them would hide
     * science because it does not fit in a text input. The graph therefore reads
     * `run.inherited` directly for shape, and never re-derives `overridable`,
     * displacement history, or any verdict from it.
     */
    const tally = inheritedTally(run);

    const added = b.addNode({
      id: runNodeId,
      kind: 'run',
      label: run.label || `Run ${run.ordinal}`,
      producer: NODE_PRODUCERS.run,
      detail: [
        { term: 'Run id', value: run.id },
        { term: 'Ordinal', value: String(run.ordinal) },
        { term: 'Created', value: run.created_utc },
        { term: 'Version', value: run.version },
        { term: 'Own addresses', value: String(ownAddresses.length) },
        { term: 'Inherited from the experiment', value: String(tally.inherited) },
        { term: 'Overridden here', value: String(tally.overridden) },
        // `absent` is why a run can resolve an address and still draw nothing
        // under it. Stating the number is what stops the empty space reading as
        // a rendering failure.
        { term: 'Resolved but absent', value: String(tally.absent) },
        {
          term: 'Official record',
          value: run.record_id ?? 'not exported — no record id is invented',
        },
      ],
      runId: run.id,
      parentId: rootId,
    });
    if (!added) continue;
    runOrder.push(added);
    b.addEdge({
      source: rootId,
      target: added,
      kind: 'has_run',
      producer: EDGE_PRODUCERS.has_run[0],
      why: `The server lists this run under this experiment (runs[].experiment_id === ${run.experiment_id}).`,
      label: null,
      containment: true,
    });

    // 3a. addresses the run carries ITSELF
    for (const address of ownAddresses) {
      const envelope = readEnvelope(run.fields[address]);
      const groupId = ensureGroup(
        added,
        run.id,
        address,
        'This run stores values of its own at addresses in this part of the record.',
      );
      if (!groupId || !envelope) continue;
      const node = b.nodes.get(groupId);
      const v = valueText(envelope.value);
      if (node && v !== undefined) {
        node.detail.push({ term: `Value · ${address}`, value: v });
      }
      if (node && envelope.status) {
        node.detail.push({ term: `Status · ${address}`, value: envelope.status });
      }
      attachEvidence(groupId, run.id, address, envelope.evidence, NODE_PRODUCERS.evidence_entry);
    }

    // 3b. addresses the run RESOLVES from the experiment (or overrides)
    //
    // An `absent` address carries nothing anywhere and draws nothing — the whole
    // point of "only where the data actually exists for that run".
    for (const address of inheritedAddresses) {
      const resolution = run.inherited[address];
      if (!resolution || resolution.state === 'absent') continue;
      const bare = bareAddress(address);
      const groupId = ensureGroup(
        added,
        run.id,
        bare,
        resolution.state === 'overridden'
          ? 'This run records its own value in place of the experiment’s at addresses in this part of the record.'
          : 'This run reads the experiment’s value at addresses in this part of the record.',
      );
      if (!groupId) continue;
      const node = b.nodes.get(groupId);
      const payload = readEnvelope(resolution.payload);
      const v = payload ? valueText(payload.value) : valueText(resolution.payload);
      if (node && v !== undefined) {
        node.detail.push({
          term: `${resolution.state === 'overridden' ? 'Overridden value' : 'Inherited value'} · ${bare}`,
          value: v,
        });
      }
      if (node && resolution.state === 'overridden') {
        const displaced = readEnvelope(resolution.displaced_payload);
        const dv = displaced ? valueText(displaced.value) : valueText(resolution.displaced_payload);
        if (dv !== undefined) {
          node.detail.push({ term: `Displaced experiment value · ${bare}`, value: dv });
        }
      }
      // An OVERRIDE's own evidence lives in the run's payload envelope.
      if (payload && resolution.state === 'overridden') {
        attachEvidence(groupId, run.id, bare, payload.evidence, NODE_PRODUCERS.evidence_entry);
      }
      // The `inherited` case does not copy the experiment's evidence onto the run
      // — that would double-count it. It draws the DERIVATION instead, to the
      // experiment-level node that actually holds it.
      if (resolution.state === 'inherited') {
        const experimentGroupId = experimentGroupByAddress.get(bare);
        if (experimentGroupId) {
          b.addEdge({
            source: groupId,
            target: experimentGroupId,
            kind: 'derived_from',
            producer: EDGE_PRODUCERS.derived_from[1],
            why: `The server reports this run as \`inherited\` at ${bare}: the run stores no value of its own there and reads the experiment's. The evidence for it is the experiment's, and is shown once, there.`,
            label: 'inherited',
            containment: false,
          });
        }
      }
    }

    // 3c. validation findings — ONLY for runs whose check has been fetched
    const check = checks[run.id];
    if (check) {
      addFindings(b, run, check, added, ownerGroups.get(added));
    }
  }

  // ── 4. what this view does not model, said out loud ───────────────────────
  const unmodelledTotals = new Map<string, number>();
  for (const groups of ownerGroups.values()) {
    for (const [head, n] of groups.unmodelled) {
      unmodelledTotals.set(head, (unmodelledTotals.get(head) ?? 0) + n);
    }
  }
  if (unmodelledTotals.size > 0) {
    const parts = [...unmodelledTotals.entries()]
      .sort((x, y) => byIdAsc(x[0], y[0]))
      .map(([head, n]) => `${head} (${n})`)
      .join(', ');
    b.note(
      'unmodelled_addresses',
      `This view draws Sample, Context, Measurement, Asset and Descriptor. ${unmodelledTotals.size} other part(s) of the record carry stored addresses that are NOT drawn here: ${parts}. They are counted rather than hidden — open the record's field view to see them.`,
    );
  }
  if (unreadableEvidence > 0) {
    b.note(
      'unreadable_evidence',
      `${unreadableEvidence} stored evidence item(s) could not be read as an evidence entry, so they are not drawn. Nothing is invented in their place.`,
    );
  }

  // ── 5. runs: absence, and boundedness ─────────────────────────────────────
  if (runsMeta.total === 0) {
    b.note(
      'no_runs',
      'This experiment has no runs. Nothing is drawn under it, and no run is invented to fill the shape.',
    );
  } else if (runsMeta.returned < runsMeta.matched) {
    b.note(
      'runs_bounded',
      `${runsMeta.returned} of ${runsMeta.matched} matching run(s) are loaded (${runsMeta.total} exist in this record). The graph draws what is loaded and never fetches every run to draw it — load more to extend it.`,
    );
  }
  b.note(
    'checks_on_demand',
    'Validation findings are read per run, when you open that run. A run you have not opened shows no findings because none have been read — not because it has none.',
  );

  // ── 6. conflicts, from the server's OWN classification ────────────────────
  //
  // The ONLY source for a `conflicts_with` edge. And even here it is drawn only
  // when the classified address carries exactly two entries, because with three
  // or more the stored state says THAT they conflict and not WHICH PAIR does.
  for (const result of classification.field_results ?? []) {
    if (result.classification !== 'conflicting_evidence') continue;
    const entries = experimentEntriesByAddress.get(result.field) ?? [];
    const groupId = experimentGroupByAddress.get(result.field);
    if (entries.length === 2) {
      b.addEdge({
        source: entries[0],
        target: entries[1],
        kind: 'conflicts_with',
        producer: EDGE_PRODUCERS.conflicts_with[0],
        why: `The evidence-support classification for ${result.field} is \`conflicting_evidence\` — ${result.explanation} Exactly two entries are recorded there, so the disagreement is between these two. No winner is picked.`,
        label: 'conflicting_evidence',
        containment: false,
      });
    } else if (entries.length > 2) {
      const node = groupId ? b.nodes.get(groupId) : undefined;
      node?.detail.push({
        term: `Conflicting evidence · ${result.field}`,
        value: `${entries.length} entries are recorded and the classification is \`conflicting_evidence\`. Which pair disagrees is not recorded, so no pair is drawn.`,
      });
      b.note(
        'conflict_pair_unknown',
        'At least one address is classified as conflicting over more than two entries. The stored state says that the entries disagree, not which pair does, so no conflict line is drawn there — it is stated in the details instead.',
      );
    }
  }

  if (b.truncated) {
    b.note(
      'node_cap',
      `This experiment produced more than ${MAX_EVIDENCE_GRAPH_NODES} nodes, so the graph is incomplete. It is bounded rather than partial-and-silent.`,
    );
  }

  // ── 7. focus ──────────────────────────────────────────────────────────────
  let anchorId = rootId;
  const focus = input.focusRunId ?? null;
  if (focus) {
    const focusNodeId = nodeIds.run(focus);
    if (b.nodes.has(focusNodeId)) {
      anchorId = focusNodeId;
    } else {
      b.note(
        'focus_run_unknown',
        `No run with id "${focus}" is loaded here, so the graph is not focused on one. It may exist further down a bounded run list, or not at all — the graph does not guess which.`,
      );
    }
  }

  return { ok: true, graph: finalize(b, anchorId, rootId, runOrder, freshnessKey) };
}

// ---------------------------------------------------------------- findings

/** What a finding the server sent but this build cannot describe is called. */
export const UNDESCRIBABLE_FINDING =
  'The server reported a finding this build cannot describe.';

const FINDING_ORIGINS = [
  { key: 'blocker', label: 'Blocker' },
  { key: 'draft', label: 'Draft check' },
  { key: 'official', label: 'Official schema check' },
] as const;

/**
 * Emit one `validation_finding` node per finding of a run's check, attached to the
 * grouped child its path names when it names one, and to the run itself otherwise.
 *
 * `runFindingText` is REUSED rather than re-implemented: `ApiRunCheckFinding` is a
 * union that includes a bare string, and that module already owns the honest
 * rendering of an element carrying no describable text.
 */
function addFindings(
  b: Builder,
  run: ApiRunView,
  check: ApiRunCheckResponse,
  runNodeId: string,
  groups: { byItem: Map<string, string> } | undefined,
): void {
  const lists: Record<string, ApiRunCheckFinding[]> = {
    blocker: check.blockers ?? [],
    draft: check.draft?.errors ?? [],
    official: check.official?.errors ?? [],
  };

  for (const origin of FINDING_ORIGINS) {
    lists[origin.key].forEach((finding, index) => {
      // `runFindingText` returns null for an element carrying no describable
      // text. A null is RENDERED as the honest sentence, never dropped — the
      // same rule `RunCard` follows, so the two surfaces cannot disagree about
      // whether a finding exists.
      const text = runFindingText(finding) ?? UNDESCRIBABLE_FINDING;
      const path =
        typeof finding === 'object' && finding !== null && typeof finding.path === 'string'
          ? finding.path
          : null;
      const detail: EvidenceGraphDetailLine[] = [
        { term: 'Reported by', value: origin.label },
        { term: 'Finding', value: text },
        { term: 'Run', value: run.label || `Run ${run.ordinal}` },
        { term: 'Run version checked', value: check.checked_run_version },
      ];
      if (path) detail.push({ term: 'Path', value: path });
      if (origin.key === 'official') {
        detail.push({
          term: 'Dry run',
          value:
            check.official?.dry_run === undefined
              ? 'the server did not say'
              : check.official.dry_run
                ? 'yes — a candidate record was checked'
                : 'no — the record already written was checked',
        });
      }
      const id = b.addNode({
        id: nodeIds.finding(run.id, origin.key, index),
        kind: 'validation_finding',
        label: shortLabel(text, 52),
        producer: NODE_PRODUCERS.validation_finding,
        detail,
        runId: run.id,
        parentId: runNodeId,
      });
      if (!id) return;

      // Attach to the grouped child the finding's own path names, when it names
      // one that this run actually has. Never to a group invented for it.
      let owner = runNodeId;
      if (path && groups) {
        const group = groupForAddress(path);
        const candidate = group ? groups.byItem.get(`${group.kind}/${group.itemKey}`) : undefined;
        if (candidate) owner = candidate;
      }
      const node = b.nodes.get(id);
      if (node) node.parentId = owner;
      b.addEdge({
        source: owner,
        target: id,
        kind: 'validated_by',
        producer: EDGE_PRODUCERS.validated_by[0],
        why: `${origin.label} on ${run.label || `Run ${run.ordinal}`} (run version ${check.checked_run_version}): ${text}${path ? ` — reported at ${path}` : ''}`,
        label: origin.label,
        containment: true,
      });
    });
  }
}

// ------------------------------------------------------------------- finalize

function finalize(
  b: Builder,
  anchorId: string,
  rootId: string,
  runOrder: string[],
  freshnessKey: string,
): EvidenceGraph {
  const nodes = [...b.nodes.values()];
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  const edges = [...b.edges];

  const adjacency = new Map<string, EvidenceGraphAdjacent[]>();
  for (const n of nodes) adjacency.set(n.id, []);
  for (const e of edges) {
    adjacency.get(e.source)?.push({ id: e.target, edge: e, incoming: false });
    adjacency.get(e.target)?.push({ id: e.source, edge: e, incoming: true });
  }

  // Containment children, in INSERTION order — which is the server's run order
  // for runs, and the deterministic address order for everything below them. A
  // re-sort here would make Run 10 precede Run 2.
  const childrenOf = new Map<string, string[]>();
  for (const n of nodes) childrenOf.set(n.id, []);
  for (const n of nodes) {
    if (n.parentId && childrenOf.has(n.parentId)) childrenOf.get(n.parentId)!.push(n.id);
  }

  const counts = Object.fromEntries(EVIDENCE_NODE_KINDS.map((k) => [k, 0])) as Record<
    EvidenceNodeKind,
    number
  >;
  for (const n of nodes) counts[n.kind] += 1;

  const layoutEdges: ApiMemoryGraphEdge[] = edges.map((e) => ({
    source: e.source,
    target: e.target,
    relations: [e.kind],
  }));
  const layout = computeLayout(
    nodes.map((n) => n.id),
    layoutEdges,
  );

  return {
    anchorId,
    rootId,
    nodes,
    edges,
    byId,
    adjacency,
    childrenOf,
    layout,
    counts,
    runOrder,
    notes: b.notes,
    truncated: b.truncated,
    freshnessKey,
  };
}

// ------------------------------------------------------------------ view state

export interface EvidenceGraphViewState {
  /** Nodes whose children are revealed. Always contains the anchor. */
  expanded: string[];
  selectedId: string | null;
  /** The in-graph find query. Does NOT change what is fetched. */
  search: string;
  view: GraphViewport;
  /** Kinds the reader has hidden. Empty = everything the expansion reveals. */
  hiddenKinds: EvidenceNodeKind[];
}

/**
 * The initial state: the anchor expanded and NOTHING else.
 *
 * On the default (unfocused) graph the anchor is the experiment, so the first
 * paint is the experiment and its direct children — the runs — and every run is
 * COLLAPSED. That is the required default shape, and it is a property of this
 * function rather than of a component's first render.
 */
export function initialEvidenceGraphState(graph: EvidenceGraph): EvidenceGraphViewState {
  return {
    expanded: [graph.anchorId],
    selectedId: graph.anchorId,
    search: '',
    view: { cx: 0, cy: 0, scale: 1 },
    hiddenKinds: [],
  };
}

export type EvidenceGraphAction =
  | { kind: 'select'; nodeId: string | null }
  | { kind: 'expand'; nodeId: string }
  | { kind: 'collapse'; nodeId: string }
  | { kind: 'toggle'; nodeId: string }
  /** Expand every ancestor of the node and select it — used by find + focus. */
  | { kind: 'reveal'; nodeId: string }
  | { kind: 'search'; query: string }
  | { kind: 'toggleKind'; nodeKind: EvidenceNodeKind }
  | { kind: 'pan'; dx: number; dy: number }
  | { kind: 'zoom'; factor: number }
  | { kind: 'fit'; box?: ViewportBox }
  | { kind: 'reset'; box?: ViewportBox };

export function applyEvidenceGraphAction(
  state: EvidenceGraphViewState,
  action: EvidenceGraphAction,
  graph: EvidenceGraph,
): EvidenceGraphViewState {
  switch (action.kind) {
    case 'select': {
      if (action.nodeId === null) return { ...state, selectedId: null };
      // Identity is never guessed: an id this graph does not hold selects nothing
      // rather than selecting something that looks similar.
      if (!graph.byId.has(action.nodeId)) return state;
      return { ...state, selectedId: action.nodeId };
    }

    case 'expand': {
      if (!graph.byId.has(action.nodeId)) return state;
      if (state.expanded.includes(action.nodeId)) return state;
      return {
        ...state,
        expanded: [...state.expanded, action.nodeId].sort(byIdAsc),
        selectedId: action.nodeId,
      };
    }

    case 'collapse': {
      // The anchor is never collapsible: collapsing it leaves an empty canvas
      // with no way back except Reset.
      if (action.nodeId === graph.anchorId) return state;
      if (!state.expanded.includes(action.nodeId)) return state;
      const expanded = state.expanded.filter((id) => id !== action.nodeId);
      const visible = new Set(visibleEvidenceNodeIds({ ...state, expanded }, graph));
      return {
        ...state,
        expanded,
        selectedId:
          state.selectedId && visible.has(state.selectedId) ? state.selectedId : graph.anchorId,
      };
    }

    case 'toggle':
      return applyEvidenceGraphAction(
        state,
        state.expanded.includes(action.nodeId)
          ? { kind: 'collapse', nodeId: action.nodeId }
          : { kind: 'expand', nodeId: action.nodeId },
        graph,
      );

    case 'reveal': {
      if (!graph.byId.has(action.nodeId)) return state;
      const chain = ancestorsOf(action.nodeId, graph);
      const expanded = [...new Set([...state.expanded, ...chain])].sort(byIdAsc);
      return { ...state, expanded, selectedId: action.nodeId };
    }

    case 'search':
      return { ...state, search: action.query };

    case 'toggleKind': {
      const hidden = state.hiddenKinds.includes(action.nodeKind)
        ? state.hiddenKinds.filter((k) => k !== action.nodeKind)
        : [...state.hiddenKinds, action.nodeKind].sort(byIdAsc);
      return { ...state, hiddenKinds: hidden };
    }

    case 'pan': {
      const step = VIEW_EXTENT / state.view.scale / 8;
      return {
        ...state,
        view: {
          ...state.view,
          cx: state.view.cx + action.dx * step,
          cy: state.view.cy + action.dy * step,
        },
      };
    }

    case 'zoom':
      return {
        ...state,
        view: { ...state.view, scale: clampScale(state.view.scale * action.factor) },
      };

    case 'fit':
      return {
        ...state,
        view: fitEvidenceViewport(visibleEvidenceNodeIds(state, graph), graph, action.box),
      };

    case 'reset': {
      const next = initialEvidenceGraphState(graph);
      return {
        ...next,
        view: fitEvidenceViewport(visibleEvidenceNodeIds(next, graph), graph, action.box),
      };
    }

    default:
      return state;
  }
}

/** The node and every containment ancestor above it, root-first. */
export function ancestorsOf(nodeId: string, graph: EvidenceGraph): string[] {
  const chain: string[] = [];
  let cursor: string | null = nodeId;
  const seen = new Set<string>();
  while (cursor && !seen.has(cursor)) {
    seen.add(cursor);
    chain.unshift(cursor);
    cursor = graph.byId.get(cursor)?.parentId ?? null;
  }
  return chain;
}

// --------------------------------------------------------------- derived views

/**
 * The nodes actually drawn: the expanded set plus the direct CHILDREN of it.
 *
 * Children, not all neighbours — so a collapsed run contributes exactly one node,
 * and opening one run reveals that run's own children and nobody else's. This is
 * what "no eager explosion of all descendants" means concretely, and it is a
 * property of this function that a test can assert without rendering anything.
 */
export function visibleEvidenceNodeIds(
  state: EvidenceGraphViewState,
  graph: EvidenceGraph,
): string[] {
  const hidden = new Set(state.hiddenKinds);
  const allow = (id: string): boolean => {
    const node = graph.byId.get(id);
    if (!node) return false;
    // The anchor and the root are never hidden by a kind filter: a reader must
    // not be able to filter away the thing the graph is about.
    if (id === graph.anchorId || id === graph.rootId) return true;
    return !hidden.has(node.kind);
  };

  const out: string[] = [];
  const seen = new Set<string>();
  const push = (id: string) => {
    if (seen.has(id) || !allow(id)) return;
    seen.add(id);
    out.push(id);
  };

  // Walk the containment tree from the anchor so the ORDER is reading order —
  // which is also the order the accessible tree renders in.
  const walk = (id: string) => {
    push(id);
    if (!state.expanded.includes(id)) return;
    for (const child of graph.childrenOf.get(id) ?? []) walk(child);
  };
  walk(graph.anchorId);
  if (graph.anchorId !== graph.rootId) push(graph.rootId);
  if (state.selectedId) push(state.selectedId);

  return out.slice(0, MAX_VISIBLE_EVIDENCE_NODES);
}

/** One row of the accessible tree: a node and its depth below the anchor. */
export interface EvidenceTreeRow {
  id: string;
  /** 1-based, so it can be handed to `aria-level` unmodified. */
  level: number;
}

/**
 * The SAME set of nodes {@link visibleEvidenceNodeIds} returns, in the same
 * reading order, but carrying the DEPTH each one sits at.
 *
 * This exists so the non-visual equivalent of the diagram is not a second
 * traversal free to disagree with the first. The canvas draws
 * `visibleEvidenceNodeIds`; the tree renders these rows; a test asserts the two
 * agree over the anchor's subtree. The only ids the canvas can hold that the
 * tree cannot are the two {@link visibleEvidenceNodeIds} appends OUTSIDE the
 * walk — the root when the graph is focused on a run, and a selection that has
 * been collapsed out of view — and the panel surfaces both by other means (the
 * focus breadcrumb and the details pane) rather than leaving them unreachable.
 *
 * The rejected-parent behaviour is deliberately IDENTICAL to the walk it
 * mirrors: a node hidden by a kind filter is not emitted, but its children are
 * still walked, so hiding "Evidence Entry" does not also hide the sources under
 * it. Levels stay absolute depth, so a filtered-out parent leaves a gap rather
 * than renumbering its children.
 */
export function evidenceTreeRows(
  state: EvidenceGraphViewState,
  graph: EvidenceGraph,
): EvidenceTreeRow[] {
  const hidden = new Set(state.hiddenKinds);
  const allow = (id: string): boolean => {
    const node = graph.byId.get(id);
    if (!node) return false;
    if (id === graph.anchorId || id === graph.rootId) return true;
    return !hidden.has(node.kind);
  };

  const rows: EvidenceTreeRow[] = [];
  const seen = new Set<string>();
  const walk = (id: string, level: number): void => {
    if (!seen.has(id) && allow(id)) {
      seen.add(id);
      rows.push({ id, level });
    }
    if (!state.expanded.includes(id)) return;
    for (const child of graph.childrenOf.get(id) ?? []) walk(child, level + 1);
  };
  walk(graph.anchorId, 1);
  return rows.slice(0, MAX_VISIBLE_EVIDENCE_NODES);
}

/** True when the bound above actually bit — reported, never silently applied. */
export function visibleEvidenceTruncated(
  state: EvidenceGraphViewState,
  graph: EvidenceGraph,
): boolean {
  const hidden = new Set(state.hiddenKinds);
  let count = 0;
  const seen = new Set<string>();
  const walk = (id: string) => {
    if (seen.has(id)) return;
    const node = graph.byId.get(id);
    if (!node) return;
    if (id !== graph.anchorId && id !== graph.rootId && hidden.has(node.kind)) return;
    seen.add(id);
    count += 1;
    if (!state.expanded.includes(id)) return;
    for (const child of graph.childrenOf.get(id) ?? []) walk(child);
  };
  walk(graph.anchorId);
  return count > MAX_VISIBLE_EVIDENCE_NODES;
}

/** Edges whose BOTH endpoints are visible. An edge is never half-drawn. */
export function visibleEvidenceEdges(
  visible: readonly string[],
  graph: EvidenceGraph,
): EvidenceGraphEdge[] {
  const set = new Set(visible);
  return graph.edges.filter((e) => set.has(e.source) && set.has(e.target));
}

/** Nodes that have containment children — the expand targets. */
export function hasChildren(nodeId: string, graph: EvidenceGraph): boolean {
  return (graph.childrenOf.get(nodeId) ?? []).length > 0;
}

/** Relationships of a node that are NOT its containment edges — the cross-links
 *  a reader can only find through the details pane. */
export function crossLinksOf(nodeId: string, graph: EvidenceGraph): EvidenceGraphAdjacent[] {
  return (graph.adjacency.get(nodeId) ?? []).filter((a) => !a.edge.containment);
}

export interface EvidenceGraphSearchResult {
  id: string;
  label: string;
  kind: EvidenceNodeKind;
  /** The text that matched — never a guess about why it is relevant. */
  matchedOn: string;
  /** The run this result belongs to, for the "in Run 2" suffix. */
  runLabel: string | null;
}

/**
 * Find WITHIN the graph that is already built. Case-insensitive substring over the
 * node label and its already-stored detail values. Bounded, deterministic, and it
 * ranks nothing — a search that cannot explain its ordering should not have one.
 *
 * It deliberately does NOT fetch: narrowing which RUNS are loaded is a separate,
 * server-side control, because filtering client-side over data already downloaded
 * has already paid the whole cost (`docs/run-scale-measurements.md` §3).
 */
export function searchEvidenceGraph(
  query: string,
  graph: EvidenceGraph,
): EvidenceGraphSearchResult[] {
  const q = query.trim().toLowerCase();
  if (q === '') return [];
  const out: EvidenceGraphSearchResult[] = [];
  const runLabelOf = (node: EvidenceGraphNode): string | null => {
    if (!node.runId) return null;
    return graph.byId.get(nodeIds.run(node.runId))?.label ?? null;
  };
  for (const node of graph.nodes) {
    if (out.length >= MAX_EVIDENCE_SEARCH_RESULTS) break;
    if (node.label.toLowerCase().includes(q)) {
      out.push({
        id: node.id,
        label: node.label,
        kind: node.kind,
        matchedOn: node.label,
        runLabel: runLabelOf(node),
      });
      continue;
    }
    const line = node.detail.find((l) => l.value.toLowerCase().includes(q));
    if (line) {
      out.push({
        id: node.id,
        label: node.label,
        kind: node.kind,
        matchedOn: `${line.term}: ${shortLabel(line.value, 60)}`,
        runLabel: runLabelOf(node),
      });
    }
  }
  return out;
}

/** Viewport that frames `ids` inside `box`. Falls back to identity when empty. */
export function fitEvidenceViewport(
  ids: readonly string[],
  graph: EvidenceGraph,
  box: ViewportBox = DEFAULT_VIEWPORT_BOX,
): GraphViewport {
  const pts = ids
    .map((id) => graph.layout.get(id))
    .filter((p): p is GraphPoint => p !== undefined);
  if (pts.length === 0) return { cx: 0, cy: 0, scale: 1 };
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  const pad = 70;
  const w = Math.max(maxX - minX + pad * 2, 140);
  const h = Math.max(maxY - minY + pad * 2, 140);
  return {
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    scale: clampScale(Math.min(box.width / w, box.height / h)),
  };
}
