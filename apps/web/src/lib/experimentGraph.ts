/*
 * experimentGraph — the EXPERIMENT-SCOPED graph model.
 *
 * ── What this is, and what it is NOT ────────────────────────────────────────
 *
 * `lib/graphModel.ts` models the PROJECT MEMORY graph: 201 repo file paths + 19
 * documentation concepts, joined by `imports` / `calls` / `references`. It is a
 * graph of the REPOSITORY, and it contains exactly zero scientific records. It
 * is also a committed point-in-time projection, stale by construction.
 *
 * This module models ONE EXPERIMENT: its sections, its fields, the evidence
 * under each field, the source files that evidence cites, the rules and
 * confirmations behind it, the workflow it sits in, the validation issues
 * against it, and the links it DECLARES. Nothing here reads the memory
 * snapshot, and nothing here is cached — every graph is derived from the live
 * record bundle at render time, which is what makes staleness structurally
 * impossible.
 *
 * It is deliberately pure: no React, no fetch, no DOM, no clock, no randomness.
 *
 * ── Reuse, not a fork ───────────────────────────────────────────────────────
 *
 * Deterministic layout, the viewBox helper and the scale clamp are IMPORTED
 * from `graphModel.ts` — the same seeded, iteration-fixed layout the Project
 * Memory canvas uses, so the two surfaces cannot drift apart on geometry. What
 * is NOT shared is the DOMAIN: `GraphIndex` is built from
 * `ApiMemoryGraphResponse` and its state carries file/concept filters and
 * community ids, none of which exist here. A second domain gets a second model,
 * not a widened one.
 *
 * ── The no-guessing policy, applied to EDGES ────────────────────────────────
 *
 * Every node kind and every edge kind in this file has ONE named, deterministic
 * producer, and `EXPERIMENT_NODE_KINDS` / `EXPERIMENT_EDGE_KINDS` are the
 * closed sets a test asserts against. The following are NEVER emitted, because
 * no deterministic source for them exists anywhere in this codebase:
 *
 *   · semantic similarity between records — no embeddings exist;
 *   · `same_sample_as` inferred from a matching formula or sample id — that is
 *     an author's assertion, and the schema has a field for it (`links`), which
 *     is the only place this graph will read it from;
 *   · causal or temporal ordering derived from timestamps;
 *   · campaign / proposal / session grouping — `proposal_id` and `session_id`
 *     are unregistered free strings;
 *   · person↔person collaboration — contributor names are unresolved free
 *     strings;
 *   · instrument or beamline identity across records — a string is not an
 *     entity;
 *   · any scientific interpretation edge — `review.py` is a NoOpReviewer;
 *   · anything sourced from the Graphify snapshot.
 *
 * When a record declares no links, this model says so (a `no_declared_links`
 * note) instead of drawing a relationship it cannot justify.
 */
import type {
  ApiArtifactsResponse,
  ApiDraftGroup,
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiMemoryGraphEdge,
  ApiValidateResult,
  ApiWarningsResponse,
  EvidenceClass,
  FieldEvidence,
  SourceType,
} from './types';
import {
  MAX_SCALE,
  MIN_SCALE,
  VIEW_EXTENT,
  computeLayout,
  type GraphPoint,
  type GraphViewport,
} from './graphModel';
import { ROUTES } from './routes';
import { titleCase } from './labels';

export { MAX_SCALE, MIN_SCALE, VIEW_EXTENT };

/**
 * The rendered size of the canvas, in CSS pixels.
 *
 * `graphModel.viewBoxOf` is deliberately NOT reused: it emits a SQUARE viewBox
 * of `VIEW_EXTENT / scale`, which is right for the Project Memory canvas (a
 * roughly square box) and wrong here. The record screen's main column gives the
 * graph an 827x460 box at 1440px and a 240x280 box at 320px, and a square
 * viewBox in a non-square box means `preserveAspectRatio` fits the SMALLER
 * dimension — so one user unit was 0.42 px on the desktop and 0.22 px on the
 * phone, and every mark and label silently changed size with the viewport.
 * Measured, not reasoned about.
 *
 * With the box known, `scale` becomes an honest pixels-per-user-unit and a mark
 * declared in pixels renders at that many pixels everywhere.
 */
export interface ViewportBox {
  width: number;
  height: number;
}

/** Used before the element has been measured, and in jsdom, which has no layout. */
export const DEFAULT_VIEWPORT_BOX: ViewportBox = { width: 800, height: 460 };

/** The SVG viewBox for a viewport rendered into `box`. */
export function viewBoxFor(view: GraphViewport, box: ViewportBox): string {
  const w = box.width / view.scale;
  const h = box.height / view.scale;
  return `${view.cx - w / 2} ${view.cy - h / 2} ${w} ${h}`;
}

// ------------------------------------------------------------------ constants

/**
 * Hard cap on nodes in ONE experiment graph. The canonical synthetic seed
 * measures ~110 nodes, two orders of magnitude below this, so the cap is not
 * binding today — it exists so a pathological record (thousands of channels)
 * degrades VISIBLY, with a note, instead of freezing the browser.
 */
export const MAX_EXPERIMENT_NODES = 600;

/** Bound on the search result list. An unbounded list is not a search result. */
export const MAX_SEARCH_RESULTS = 12;

/** Bound on nodes drawn at once. Progressive disclosure means the anchor's
 *  neighbourhood plus whatever the reader has explicitly expanded — never the
 *  whole graph on first paint. */
export const MAX_VISIBLE_NODES = 240;

// ------------------------------------------------------------- closed vocabularies

/**
 * The CLOSED set of node kinds. A test asserts that no built graph emits a kind
 * outside this list, which is what stops a future slice from quietly adding a
 * speculative entity type.
 *
 * The first twelve are the enumerated product vocabulary. The last three
 * (`rule`, `confirmation`, `evidence_class`) are the TARGETS the enumerated
 * edge kinds `derived_by_rule`, `confirmed_by_user` and `classified_as` require
 * — an edge cannot point at something that is not a node. Each still has one
 * named deterministic producer; see `NODE_PRODUCERS` below.
 */
export const EXPERIMENT_NODE_KINDS = [
  'experiment',
  'record',
  'section',
  'field',
  'block_object',
  'implicit',
  'evidence',
  'source_file',
  'workflow_step',
  'issue',
  'warning',
  'linked_record',
  'rule',
  'confirmation',
  'evidence_class',
] as const;

export type ExperimentNodeKind = (typeof EXPERIMENT_NODE_KINDS)[number];

/**
 * The CLOSED set of edge kinds.
 *
 * `advises` is the one addition to the enumerated list, and it is deliberate.
 * `warning` is an enumerated NODE kind with no enumerated edge, which would
 * leave every advisory warning an unreachable orphan. The two alternatives were
 * both worse: dropping warning nodes silently, or reusing `fails` — and
 * `portal_warnings` is advisory and explicitly NON-GATING, so labelling one a
 * failure would be exactly the kind of verdict inflation this project keeps
 * removing. So warnings get their own edge kind whose name makes the
 * non-gating status legible.
 */
export const EXPERIMENT_EDGE_KINDS = [
  'produces',
  'has_section',
  'contains',
  'supported_by',
  'cites',
  'derived_by_rule',
  'confirmed_by_user',
  'fails',
  'at_step',
  'precedes',
  'links_to',
  'classified_as',
  'advises',
] as const;

export type ExperimentEdgeKind = (typeof EXPERIMENT_EDGE_KINDS)[number];

/**
 * The named deterministic producer for each node kind — the answer to "where
 * did this node come from?", shown verbatim in the detail pane. A kind with no
 * producer is a kind that should not exist.
 */
export const NODE_PRODUCERS: Readonly<Record<ExperimentNodeKind, string>> = Object.freeze({
  experiment: 'Experiment.id / Experiment.title (GET /api/experiments/{id})',
  record: 'Experiment.record_id — null until the record is exported',
  section: 'serialize.draft_to_groups → _GROUP_TITLES (8 stable sections + Other)',
  field: 'draft.fields key (GET /api/experiments/{id}/draft)',
  block_object: 'namespaced evidence key, and the exported official record structure',
  implicit: 'draft.implicit[] — preserved in the evidence sidecar, no official path',
  evidence: 'one entry of evidence[].evidence[] (GET /api/experiments/{id}/evidence)',
  source_file: 'evidence entry source_file',
  workflow_step: 'workflow.ordered_steps (workflow.CANONICAL_ORDER — 5 steps)',
  issue: 'official-schema validation error path (POST /api/experiments/{id}/validate)',
  warning: 'portal_warnings advisory code (GET /api/experiments/{id}/warnings)',
  linked_record: 'record.links[].target in the exported official record',
  rule: 'evidence entry rule (source_type: derivation)',
  confirmation: 'evidence entry question / answer / timestamp (source_type: user_confirmation)',
  evidence_class:
    'evidence-support classification (GET /api/experiments/{id}/evidence-classification)',
});

/** Human-readable, product-facing name for each node kind. */
export const NODE_KIND_LABELS: Readonly<Record<ExperimentNodeKind, string>> = Object.freeze({
  experiment: 'Experiment',
  record: 'Official Record',
  section: 'Section',
  field: 'Field',
  block_object: 'Structured Block',
  implicit: 'Implicit Value',
  evidence: 'Evidence',
  source_file: 'Source File',
  workflow_step: 'Workflow Step',
  issue: 'Validation Issue',
  warning: 'Advisory Warning',
  linked_record: 'Linked Record',
  rule: 'Derivation Rule',
  confirmation: 'Your Confirmation',
  evidence_class: 'Evidence Class',
});

/** Human-readable name for each edge kind, for the legend and the detail pane. */
export const EDGE_KIND_LABELS: Readonly<Record<ExperimentEdgeKind, string>> = Object.freeze({
  produces: 'produces',
  has_section: 'has section',
  contains: 'contains',
  supported_by: 'supported by',
  cites: 'cites',
  derived_by_rule: 'derived by rule',
  confirmed_by_user: 'confirmed by you',
  fails: 'fails',
  at_step: 'at step',
  precedes: 'precedes',
  links_to: 'links to',
  classified_as: 'classified as',
  advises: 'advises',
});

/**
 * The SAME eight section titles `serialize._GROUP_TITLES` uses, keyed by the
 * top-level path segment. Mirrored here (not re-derived, not renamed) so a
 * block object enumerated from the official record lands in the section a
 * reader already knows, and `Other` catches anything unmapped exactly as the
 * backend's `_OTHER` does.
 */
export const SECTION_TITLES: Readonly<Record<string, string>> = Object.freeze({
  system: 'System & Instrument',
  timestamps: 'Timestamps',
  sample: 'Sample',
  context: 'Environment & Context',
  measurement: 'Measurement',
  assets: 'Assets & Files',
  descriptors: 'Descriptors',
  attribution: 'Attribution',
});

export const OTHER_SECTION = 'Other';

/** The section a dotted official path or a namespaced key belongs to. */
export function sectionTitleFor(pathOrKey: string): string {
  const head = pathOrKey.split(/[.:[]/)[0];
  if (head === 'series' || head === 'qc' || head === 'measurement') return SECTION_TITLES.measurement;
  return SECTION_TITLES[head] ?? OTHER_SECTION;
}

// ------------------------------------------------------------------ node types

export interface ExperimentGraphDetailLine {
  term: string;
  value: string;
}

/** An in-app destination for "jump to the actual record / editor location". */
export interface ExperimentGraphJump {
  label: string;
  to: string;
}

export interface ExperimentGraphNode {
  id: string;
  kind: ExperimentNodeKind;
  label: string;
  /** The exact deterministic producer that emitted THIS node. */
  producer: string;
  /** Already-server-derived facts. Nothing here is computed from science. */
  detail: ExperimentGraphDetailLine[];
  jump: ExperimentGraphJump | null;
  /**
   * True when this node was read out of an exported artifact whose derived
   * state is `stale` — the record changed after export, so the artifact no
   * longer describes the current draft. Rendered, never silently dropped.
   */
  fromStaleArtifact?: boolean;
}

export interface ExperimentGraphEdge {
  source: string;
  target: string;
  kind: ExperimentEdgeKind;
  /**
   * The sentence the detail pane shows for this edge — WHY it exists. Never
   * cryptic, and never a claim the producer cannot support.
   */
  why: string;
  /** A verbatim short label when the edge carries one (e.g. `same_sample_as`). */
  label: string | null;
}

export interface ExperimentGraphAdjacent {
  id: string;
  edge: ExperimentGraphEdge;
  /** true when this node is the edge's `target` (the edge points AT it). */
  incoming: boolean;
}

export type ExperimentGraphNoteKind =
  | 'not_exported'
  | 'no_declared_links'
  | 'artifact_stale'
  | 'node_cap'
  | 'visible_cap'
  | 'dry_run_validation';

export interface ExperimentGraphNote {
  kind: ExperimentGraphNoteKind;
  text: string;
}

export interface ExperimentGraph {
  /** The root a reader starts from: the record when exported, else the experiment. */
  anchorId: string;
  nodes: ExperimentGraphNode[];
  edges: ExperimentGraphEdge[];
  byId: Map<string, ExperimentGraphNode>;
  adjacency: Map<string, ExperimentGraphAdjacent[]>;
  /** Deterministic coordinates for EVERY node — expanding never reshuffles. */
  layout: Map<string, GraphPoint>;
  counts: Record<ExperimentNodeKind, number>;
  notes: ExperimentGraphNote[];
  /** true when MAX_EXPERIMENT_NODES bit and some nodes were not built. */
  truncated: boolean;
}

// ------------------------------------------------------------------ the input

export interface ExperimentGraphInput {
  detail: ApiExperimentDetail;
  groups: ApiDraftGroup[];
  evidence: ApiEvidenceEntry[];
  artifacts: ApiArtifactsResponse;
  validate: ApiValidateResult;
  warnings: ApiWarningsResponse;
  classification: ApiEvidenceClassification;
}

/**
 * TUTORIAL ISOLATION, as a value rather than as a convention.
 *
 * The five worked-example records exist ONLY inside a temporary session
 * workspace, and leaving that session DESTROYS them (see `lib/workspaceScope.ts`).
 * A graph built from a session bundle must therefore never keep rendering once
 * the surface is addressing the ordinary workspace, and vice versa — the ids in
 * it name nothing in the scope now being addressed.
 *
 * So the builder takes both scopes and refuses when they disagree. This is a
 * SECOND guard, not the only one: the record surfaces already navigate away via
 * `useWorkspaceScopeChanged()`. Belt and braces is the right posture here,
 * because the failure mode is showing one workspace's science inside another.
 */
export interface ExperimentGraphScope {
  /** The workspace scope the bundle was READ in. `null` = ordinary workspace. */
  readIn: string | null;
  /** The workspace scope the surface is addressing NOW. */
  current: string | null;
}

export type ExperimentGraphResult =
  | { ok: true; graph: ExperimentGraph }
  | { ok: false; reason: 'workspace_scope_changed'; message: string };

// --------------------------------------------------------------------- helpers

const byIdAsc = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

const clampScale = (s: number): number => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/** Compact a long free-text string for use as a canvas/list label. */
export function shortLabel(text: string, max = 42): string {
  const one = text.replace(/\s+/g, ' ').trim();
  return one.length <= max ? one : `${one.slice(0, max - 1)}…`;
}

/** `sample.material.formula` → `Formula`; mirrors serialize._label. */
function lastSegmentLabel(path: string): string {
  const last = path.split('.').pop() ?? path;
  return titleCase(last.replace(/_/g, ' ').trim());
}

/** Strip the JSON-pointer-ish `$.` prefix official validation errors carry. */
export function normalizeIssuePath(path: string): string {
  return path.replace(/^\$\.?/, '');
}

const SOURCE_TYPE_PHRASE: Readonly<Record<SourceType, string>> = Object.freeze({
  spreadsheet: 'the campaign spreadsheet',
  file_listing: 'the archive file listing',
  derivation: 'a documented derivation rule',
  user_confirmation: 'your own confirmation',
  document: 'a document',
  screenshot: 'a screenshot',
  web_form: 'the submitted web form',
});

/** A short, non-technical name for one evidence entry. */
function evidenceLabel(ev: FieldEvidence): string {
  if (ev.source_type === 'derivation') return 'Derivation';
  if (ev.source_type === 'user_confirmation') return 'Your confirmation';
  if (ev.source_file) return shortLabel(ev.source_file, 32);
  return titleCase(ev.source_type.replace(/_/g, ' '));
}

/**
 * WHY a `supported_by` edge exists — assembled only from fields the evidence
 * entry actually carries. No phrase is emitted for an absent field.
 */
function supportWhy(ev: FieldEvidence): string {
  if (ev.source_type === 'derivation') {
    return ev.rule
      ? `Derived by a documented rule: ${ev.rule}`
      : 'Derived by a documented rule (no rule text was recorded).';
  }
  if (ev.source_type === 'user_confirmation') {
    const when = ev.timestamp ? ` on ${ev.timestamp}` : '';
    return ev.question
      ? `Confirmed by you${when} — you were asked: "${ev.question}"`
      : `Confirmed by you${when}.`;
  }
  const where = SOURCE_TYPE_PHRASE[ev.source_type] ?? ev.source_type;
  const file = ev.source_file ? ` from ${ev.source_file}` : '';
  const at = ev.locator ? ` — ${ev.locator}` : '';
  return `Supported by evidence read from ${where}${file}${at}.`;
}

function evidenceDetailLines(ev: FieldEvidence): ExperimentGraphDetailLine[] {
  const lines: ExperimentGraphDetailLine[] = [
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

function valueText(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value === 'string') return value;
  try {
    return shortLabel(JSON.stringify(value), 120);
  } catch {
    return undefined;
  }
}

// -------------------------------------------------------------- node ids (pure)

export const nodeIds = {
  experiment: (id: string) => `experiment:${id}`,
  record: (recordId: string) => `record:${recordId}`,
  section: (title: string) => `section:${title}`,
  field: (path: string) => `field:${path}`,
  /** A namespaced evidence key (`series:averaged_spectrum`) or an official path. */
  block: (key: string) => `block:${key}`,
  implicit: (about: string) => `implicit:${about}`,
  evidence: (ownerPath: string, index: number) => `evidence:${ownerPath}#${index}`,
  sourceFile: (file: string) => `source_file:${file}`,
  step: (stepId: string) => `workflow_step:${stepId}`,
  issue: (path: string, index: number) => `issue:${path}#${index}`,
  warning: (code: string, index: number) => `warning:${code}#${index}`,
  linkedRecord: (target: string) => `linked_record:${target}`,
  rule: (rule: string) => `rule:${rule}`,
  confirmation: (question: string, timestamp: string) => `confirmation:${question}#${timestamp}`,
  evidenceClass: (cls: EvidenceClass) => `evidence_class:${cls}`,
} as const;

// ------------------------------------------------------------------- the builder

class Builder {
  readonly nodes = new Map<string, ExperimentGraphNode>();
  readonly edges: ExperimentGraphEdge[] = [];
  private readonly edgeSeen = new Set<string>();
  readonly notes: ExperimentGraphNote[] = [];
  truncated = false;

  addNode(node: ExperimentGraphNode): string | null {
    const existing = this.nodes.get(node.id);
    if (existing) {
      // Merge only ADDITIVE detail: a node reached by two producers keeps both
      // explanations rather than the last writer silently winning.
      for (const line of node.detail) {
        if (!existing.detail.some((l) => l.term === line.term && l.value === line.value)) {
          existing.detail.push(line);
        }
      }
      if (node.fromStaleArtifact) existing.fromStaleArtifact = true;
      return existing.id;
    }
    if (this.nodes.size >= MAX_EXPERIMENT_NODES) {
      this.truncated = true;
      return null;
    }
    this.nodes.set(node.id, node);
    return node.id;
  }

  /** An edge is kept ONLY when both endpoints exist. Nothing is repaired. */
  addEdge(edge: ExperimentGraphEdge): void {
    if (edge.source === edge.target) return;
    if (!this.nodes.has(edge.source) || !this.nodes.has(edge.target)) return;
    const key = `${edge.kind} ${edge.source} ${edge.target}`;
    if (this.edgeSeen.has(key)) return;
    this.edgeSeen.add(key);
    this.edges.push(edge);
  }

  note(kind: ExperimentGraphNoteKind, text: string): void {
    if (this.notes.some((n) => n.kind === kind)) return;
    this.notes.push({ kind, text });
  }
}

/**
 * Build the experiment graph.
 *
 * Deterministic by construction: the same input always produces the same nodes,
 * the same edges (in the same order) and byte-identical coordinates. There is
 * no cache and no persisted projection — the caller re-derives per render,
 * which is what makes a stale experiment graph impossible.
 */
export function buildExperimentGraph(
  input: ExperimentGraphInput,
  scope: ExperimentGraphScope = { readIn: null, current: null },
): ExperimentGraphResult {
  if (scope.readIn !== scope.current) {
    return {
      ok: false,
      reason: 'workspace_scope_changed',
      message:
        'This graph was read in a different workspace. A worked-example session and the ordinary workspace hold different records, so nothing loaded here describes the workspace now being addressed.',
    };
  }

  const b = new Builder();
  const { detail, groups, evidence, artifacts, validate, warnings, classification } = input;

  const artifactStale = artifacts.artifact?.state === 'stale' || detail.artifact?.state === 'stale';

  // ── 1. the experiment, and the official record it produced (if any) ────────
  const experimentId = nodeIds.experiment(detail.id);
  b.addNode({
    id: experimentId,
    kind: 'experiment',
    label: detail.title,
    producer: NODE_PRODUCERS.experiment,
    detail: [
      { term: 'Experiment id', value: detail.id },
      { term: 'Status', value: detail.status },
      { term: 'Created', value: detail.created_utc },
      { term: 'Fields with evidence', value: String(detail.evidenced_field_count) },
    ],
    jump: { label: 'Open This Record', to: ROUTES.record(detail.id) },
  });

  let subjectId = experimentId;
  if (detail.record_id) {
    const recordId = nodeIds.record(detail.record_id);
    b.addNode({
      id: recordId,
      kind: 'record',
      label: detail.record_id,
      producer: NODE_PRODUCERS.record,
      detail: [
        { term: 'Record id', value: detail.record_id },
        { term: 'Schema', value: validate.schema },
        {
          term: 'Exported artifact',
          value: detail.artifact?.state ?? artifacts.artifact?.state ?? 'unknown',
        },
      ],
      jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
      fromStaleArtifact: artifactStale,
    });
    b.addEdge({
      source: experimentId,
      target: recordId,
      kind: 'produces',
      why: `This experiment was exported to official ISAAC record ${detail.record_id}.`,
      label: null,
    });
    subjectId = recordId;
  } else {
    b.note(
      'not_exported',
      'This experiment has not been exported yet, so there is no official record id. The draft structure below hangs off the experiment — no record id is invented.',
    );
  }

  if (artifactStale) {
    b.note(
      'artifact_stale',
      'The exported artifact is STALE: the record changed after export. Anything read out of it is marked, and is not presented as the current draft.',
    );
  }

  // ── 2. sections and fields, from the draft ────────────────────────────────
  const ensureSection = (title: string, fromDraft: boolean): string | null => {
    const id = nodeIds.section(title);
    const added = b.addNode({
      id,
      kind: 'section',
      label: title,
      producer: NODE_PRODUCERS.section,
      detail: fromDraft
        ? [{ term: 'Source', value: 'A draft section returned by GET /draft' }]
        : [
            {
              term: 'Source',
              value:
                'The section this path belongs to under the same _GROUP_TITLES map; it carries no draft field of its own.',
            },
          ],
      jump: { label: 'Open This Record', to: ROUTES.record(detail.id) },
    });
    if (added) {
      b.addEdge({
        source: subjectId,
        target: id,
        kind: 'has_section',
        why: `"${title}" is one of the stable draft sections (serialize.draft_to_groups groups official paths by their top-level segment).`,
        label: null,
      });
    }
    return added;
  };

  /** field path → node id, so evidence/issues/classes can attach to real fields. */
  const fieldNodeByPath = new Map<string, string>();

  const ensureField = (
    path: string,
    opts: { label?: string; value?: unknown; status?: string; evidenceCount?: number; fromDraft: boolean },
  ): string | null => {
    const known = fieldNodeByPath.get(path);
    if (known) return known;
    const sectionTitle = sectionTitleFor(path);
    const sectionId = ensureSection(sectionTitle, opts.fromDraft);
    const id = nodeIds.field(path);
    const lines: ExperimentGraphDetailLine[] = [{ term: 'Official path', value: path }];
    const v = valueText(opts.value);
    if (v !== undefined) lines.push({ term: 'Value', value: v });
    if (opts.status) lines.push({ term: 'Status', value: opts.status });
    if (opts.evidenceCount !== undefined) {
      lines.push({ term: 'Evidence entries', value: String(opts.evidenceCount) });
    }
    if (!opts.fromDraft) {
      lines.push({
        term: 'Source',
        value: 'An official path carried by the evidence trail rather than by the draft field list.',
      });
    }
    const added = b.addNode({
      id,
      kind: 'field',
      label: opts.label ?? lastSegmentLabel(path),
      producer: opts.fromDraft
        ? NODE_PRODUCERS.field
        : 'official dotted path carried by the evidence trail',
      detail: lines,
      jump: { label: 'Open in the Record', to: ROUTES.record(detail.id) },
    });
    if (!added) return null;
    fieldNodeByPath.set(path, added);
    if (sectionId) {
      b.addEdge({
        source: sectionId,
        target: added,
        kind: 'contains',
        why: `Defined by schema field ${path}, grouped into "${sectionTitle}" by its top-level path segment.`,
        label: null,
      });
    }
    return added;
  };

  for (const group of groups) {
    ensureSection(group.title, true);
    for (const f of group.fields) {
      ensureField(f.path, {
        label: f.label,
        value: f.value,
        status: f.status,
        evidenceCount: f.evidence_count,
        fromDraft: true,
      });
    }
  }

  // ── 3. block objects ──────────────────────────────────────────────────────
  //
  // TWO named producers, joined only on EXACT natural-key equality:
  //
  //   (a) a namespaced evidence key — `series:averaged_spectrum`, `qc:status`,
  //       `assets:<asset_id>`, `descriptors:<name>` — which is the ONLY
  //       producer before export, and
  //   (b) the exported official record's own structure, enumerated at fixed
  //       official paths.
  //
  // A record-structure object joins an existing namespaced node only when its
  // OWN identity field produces a byte-identical key (`assets[i].asset_id`,
  // `measurement.series[i].series_id`, a descriptor's `name`). Anything else
  // gets its own node. There is no fuzzy matching, and there never should be.

  const blockNodeByKey = new Map<string, string>();

  const ensureBlock = (
    key: string,
    opts: {
      label: string;
      kindWord: string;
      producer: string;
      lines?: ExperimentGraphDetailLine[];
      parentId?: string | null;
      stale?: boolean;
    },
  ): string | null => {
    const known = blockNodeByKey.get(key);
    const id = nodeIds.block(key);
    const sectionTitle = sectionTitleFor(key);
    const parentId = opts.parentId ?? ensureSection(sectionTitle, false);
    const added = b.addNode({
      id,
      kind: 'block_object',
      label: opts.label,
      producer: opts.producer,
      detail: [
        { term: 'Block', value: opts.kindWord },
        { term: 'Key', value: key },
        ...(opts.lines ?? []),
      ],
      jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
      fromStaleArtifact: opts.stale,
    });
    if (!added) return null;
    blockNodeByKey.set(key, added);
    if (!known && parentId) {
      b.addEdge({
        source: parentId,
        target: added,
        kind: 'contains',
        why: `${opts.kindWord} "${opts.label}" is a structured block of this record, identified by ${key}.`,
        label: null,
      });
    }
    return added;
  };

  const implicitNodeByAbout = new Map<string, string>();

  const ensureImplicit = (about: string, value: unknown, status: string): string | null => {
    const known = implicitNodeByAbout.get(about);
    if (known) return known;
    const id = nodeIds.implicit(about);
    const lines: ExperimentGraphDetailLine[] = [{ term: 'About', value: about }];
    const v = valueText(value);
    if (v !== undefined) lines.push({ term: 'Value', value: v });
    lines.push({ term: 'Status', value: status });
    lines.push({
      term: 'Why it is not a field',
      value:
        'The official ISAAC schema has no native path for this value, so it is preserved in the evidence sidecar instead of being forced into the record.',
    });
    const added = b.addNode({
      id,
      kind: 'implicit',
      label: titleCase(about.replace(/_/g, ' ')),
      producer: NODE_PRODUCERS.implicit,
      detail: lines,
      jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
    });
    if (!added) return null;
    implicitNodeByAbout.set(about, added);
    b.addEdge({
      source: subjectId,
      target: added,
      kind: 'contains',
      why: 'An implicit value kept in the evidence sidecar — the official schema provides no path for it, so it is attached to the record itself rather than to a section.',
      label: null,
    });
    return added;
  };

  // ── 4. evidence, source files, rules, confirmations ───────────────────────
  const ruleNodeByText = new Map<string, string>();
  const confirmationNodeByKey = new Map<string, string>();
  const sourceFileNodeByName = new Map<string, string>();

  for (const entry of evidence) {
    const path = entry.path;
    const colon = path.indexOf(':');
    let ownerId: string | null;

    if (colon >= 0) {
      const ns = path.slice(0, colon);
      const name = path.slice(colon + 1);
      if (ns === 'implicit') {
        ownerId = ensureImplicit(name, entry.value, entry.status);
      } else {
        const v = valueText(entry.value);
        ownerId = ensureBlock(path, {
          label: titleCase(name.replace(/_/g, ' ')),
          kindWord: titleCase(ns.replace(/_/g, ' ')),
          producer: 'namespaced evidence key (GET /api/experiments/{id}/evidence)',
          lines: [
            ...(v !== undefined ? [{ term: 'Value', value: v }] : []),
            { term: 'Status', value: entry.status },
          ],
        });
      }
    } else {
      ownerId = ensureField(path, {
        value: entry.value,
        status: entry.status,
        evidenceCount: (entry.evidence ?? []).length,
        fromDraft: false,
      });
    }

    if (!ownerId) continue;

    (entry.evidence ?? []).forEach((ev, index) => {
      const evId = b.addNode({
        id: nodeIds.evidence(path, index),
        kind: 'evidence',
        label: evidenceLabel(ev),
        producer: NODE_PRODUCERS.evidence,
        detail: evidenceDetailLines(ev),
        jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
      });
      if (!evId) return;
      b.addEdge({
        source: ownerId,
        target: evId,
        kind: 'supported_by',
        why: supportWhy(ev),
        label: ev.source_type,
      });

      if (ev.source_file) {
        const fileId =
          sourceFileNodeByName.get(ev.source_file) ??
          b.addNode({
            id: nodeIds.sourceFile(ev.source_file),
            kind: 'source_file',
            label: ev.source_file,
            producer: NODE_PRODUCERS.source_file,
            detail: [{ term: 'File', value: ev.source_file }],
            jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
          });
        if (fileId) {
          sourceFileNodeByName.set(ev.source_file, fileId);
          b.addEdge({
            source: evId,
            target: fileId,
            kind: 'cites',
            why: ev.locator
              ? `This evidence cites ${ev.source_file} — ${ev.locator}.`
              : `This evidence cites ${ev.source_file}.`,
            label: null,
          });
        }
      }

      if (ev.rule) {
        const ruleId =
          ruleNodeByText.get(ev.rule) ??
          b.addNode({
            id: nodeIds.rule(ev.rule),
            kind: 'rule',
            label: shortLabel(ev.rule, 46),
            producer: NODE_PRODUCERS.rule,
            detail: [{ term: 'Rule', value: ev.rule }],
            jump: null,
          });
        if (ruleId) {
          ruleNodeByText.set(ev.rule, ruleId);
          b.addEdge({
            source: evId,
            target: ruleId,
            kind: 'derived_by_rule',
            why: `Derived by a documented rule: ${ev.rule}`,
            label: 'derivation',
          });
        }
      }

      if (ev.source_type === 'user_confirmation' || ev.question || ev.answer) {
        const question = ev.question ?? '(no question recorded)';
        const timestamp = ev.timestamp ?? '(no timestamp recorded)';
        const key = `${question}#${timestamp}`;
        const confId =
          confirmationNodeByKey.get(key) ??
          b.addNode({
            id: nodeIds.confirmation(question, timestamp),
            kind: 'confirmation',
            label: ev.timestamp ? `Confirmed ${ev.timestamp.slice(0, 10)}` : 'Your confirmation',
            producer: NODE_PRODUCERS.confirmation,
            detail: [
              { term: 'Question', value: question },
              ...(ev.answer ? [{ term: 'Your answer', value: ev.answer }] : []),
              { term: 'Timestamp', value: timestamp },
            ],
            jump: { label: 'Review & Answer', to: ROUTES.complete(detail.id) },
          });
        if (confId) {
          confirmationNodeByKey.set(key, confId);
          b.addEdge({
            source: evId,
            target: confId,
            kind: 'confirmed_by_user',
            why: ev.timestamp
              ? `Confirmed by you on ${ev.timestamp}.`
              : 'Confirmed by you (no timestamp was recorded).',
            label: null,
          });
        }
      }
    });
  }

  // ── 5. the exported official record's own structure ───────────────────────
  const record = artifacts.record;
  if (record) {
    enumerateRecordBlocks(record, ensureBlock, blockNodeByKey, artifactStale);
  }

  // ── 6. workflow ───────────────────────────────────────────────────────────
  const steps = detail.workflow?.ordered_steps ?? [];
  let previousStepId: string | null = null;
  for (const step of steps) {
    const id = b.addNode({
      id: nodeIds.step(step.id),
      kind: 'workflow_step',
      label: step.label,
      producer: NODE_PRODUCERS.workflow_step,
      detail: [
        { term: 'State', value: step.state },
        { term: 'Blocked', value: step.blocked ? 'yes' : 'no' },
        { term: 'Reopened', value: step.reopened ? 'yes' : 'no' },
        ...(step.reason ? [{ term: 'Reason', value: step.reason }] : []),
      ],
      jump: stepJump(step.id, detail.id),
    });
    if (!id) continue;
    if (previousStepId) {
      b.addEdge({
        source: previousStepId,
        target: id,
        kind: 'precedes',
        why: 'The canonical workflow order (workflow.CANONICAL_ORDER) — this step comes before the next one.',
        label: null,
      });
    }
    if (step.current) {
      b.addEdge({
        source: subjectId,
        target: id,
        kind: 'at_step',
        why: step.reason
          ? `This record's current workflow step is "${step.label}" — ${step.reason}`
          : `This record's current workflow step is "${step.label}".`,
        label: null,
      });
    }
    previousStepId = id;
  }

  // ── 7. validation issues ──────────────────────────────────────────────────
  if (validate.dry_run && validate.errors.length > 0) {
    b.note(
      'dry_run_validation',
      'Validation here is a DRY RUN against the official ISAAC schema — the record has not been exported, so these are the issues an export would hit.',
    );
  }
  validate.errors.forEach((err, index) => {
    const normalized = normalizeIssuePath(err.path);
    const id = b.addNode({
      id: nodeIds.issue(err.path, index),
      kind: 'issue',
      label: normalized || 'record',
      producer: NODE_PRODUCERS.issue,
      detail: [
        { term: 'Path', value: err.path },
        { term: 'Message', value: err.message },
        { term: 'Schema', value: validate.schema },
        { term: 'Dry run', value: validate.dry_run ? 'yes' : 'no' },
      ],
      jump: { label: 'Review Export Readiness', to: ROUTES.export(detail.id) },
    });
    if (!id) return;
    const owner =
      fieldNodeByPath.get(normalized) ??
      blockNodeByKey.get(normalized) ??
      subjectId;
    b.addEdge({
      source: owner,
      target: id,
      kind: 'fails',
      why: `Validation issue at ${err.path} — ${err.message}${
        validate.dry_run ? ' (dry run against the official ISAAC schema)' : ''
      }`,
      label: null,
    });
  });

  // ── 8. advisory warnings ──────────────────────────────────────────────────
  (warnings.warnings ?? []).forEach((w, index) => {
    const id = b.addNode({
      id: nodeIds.warning(w.code, index),
      kind: 'warning',
      label: w.code,
      producer: NODE_PRODUCERS.warning,
      detail: [
        { term: 'Code', value: w.code },
        { term: 'Where', value: w.where },
        { term: 'Message', value: w.message },
        { term: 'Gating', value: 'no — advisory only, it blocks nothing' },
      ],
      jump: null,
    });
    if (!id) return;
    b.addEdge({
      source: subjectId,
      target: id,
      kind: 'advises',
      why: `Advisory warning ${w.code} at ${w.where} — ${w.message}. This is advisory and non-gating: it decides nothing about validity or export.`,
      label: null,
    });
  });

  // ── 9. declared links (and the honest absence of them) ────────────────────
  const rawLinks = record && Array.isArray(record.links) ? (record.links as unknown[]) : null;
  let linkCount = 0;
  if (rawLinks) {
    for (const raw of rawLinks) {
      if (typeof raw !== 'object' || raw === null) continue;
      const link = raw as { rel?: unknown; target?: unknown; basis?: unknown; notes?: unknown };
      if (typeof link.target !== 'string' || link.target === '') continue;
      const rel = typeof link.rel === 'string' ? link.rel : 'unspecified';
      const basis = typeof link.basis === 'string' ? link.basis : 'unspecified';
      const id = b.addNode({
        id: nodeIds.linkedRecord(link.target),
        kind: 'linked_record',
        label: link.target,
        producer: NODE_PRODUCERS.linked_record,
        detail: [
          { term: 'Target record', value: link.target },
          { term: 'Relationship', value: rel },
          { term: 'Basis', value: basis },
          ...(typeof link.notes === 'string' && link.notes
            ? [{ term: 'Notes', value: link.notes }]
            : []),
        ],
        jump: null,
        fromStaleArtifact: artifactStale,
      });
      if (!id) continue;
      linkCount += 1;
      b.addEdge({
        source: subjectId,
        target: id,
        kind: 'links_to',
        why: `Declared link: ${rel} (basis: ${basis}). It is drawn because this record ASSERTS it in its own links[] — never because two records happened to look alike.`,
        label: `${rel} · ${basis}`,
      });
    }
  }
  if (linkCount === 0) {
    b.note(
      'no_declared_links',
      'This record declares no links. Nothing is inferred to fill the gap: a shared formula, sample id, beamline or proposal is not a relationship, and this graph will not draw one.',
    );
  }

  // ── 10. evidence-support classes ──────────────────────────────────────────
  for (const result of classification.field_results ?? []) {
    const field = result.field;
    let owner: string | null = null;
    const colon = field.indexOf(':');
    if (colon >= 0) {
      const ns = field.slice(0, colon);
      const name = field.slice(colon + 1);
      owner =
        ns === 'implicit'
          ? (implicitNodeByAbout.get(name) ?? null)
          : (blockNodeByKey.get(field) ?? null);
    } else {
      owner = ensureField(field, { fromDraft: false });
    }
    if (!owner) continue;
    const classId = b.addNode({
      id: nodeIds.evidenceClass(result.classification),
      kind: 'evidence_class',
      label: titleCase(result.classification.replace(/_/g, ' ')),
      producer: NODE_PRODUCERS.evidence_class,
      detail: [
        { term: 'Class', value: result.classification },
        {
          term: 'Axis',
          value:
            'Evidence support only. This is not validity, completion, exportability, or an advisory verdict.',
        },
      ],
      jump: { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(detail.id) },
    });
    if (!classId) continue;
    b.addEdge({
      source: owner,
      target: classId,
      kind: 'classified_as',
      why: `Evidence-support classification "${result.classification}" — ${result.explanation}`,
      label: result.value_state,
    });
  }

  if (b.truncated) {
    b.note(
      'node_cap',
      `This experiment produced more than ${MAX_EXPERIMENT_NODES} nodes, so the graph is incomplete. It is bounded rather than partial-and-silent.`,
    );
  }

  return { ok: true, graph: finalize(b, subjectId) };
}

// -------------------------------------------- official-record block enumeration

type EnsureBlock = (
  key: string,
  opts: {
    label: string;
    kindWord: string;
    producer: string;
    lines?: ExperimentGraphDetailLine[];
    parentId?: string | null;
    stale?: boolean;
  },
) => string | null;

const RECORD_PRODUCER = 'the exported official record structure (GET /api/experiments/{id}/artifacts)';

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

/**
 * Enumerate the structured blocks the OFFICIAL record actually contains, at
 * fixed official paths. This walks a known schema shape — it never searches for
 * "interesting" objects and never names one the schema does not.
 *
 * The natural-key join is exact and is limited to the three cases where the
 * object carries its OWN identity field: `assets[i].asset_id`,
 * `measurement.series[i].series_id`, and a descriptor's `name`. Everything else
 * gets its own node under its official path.
 */
function enumerateRecordBlocks(
  record: Record<string, unknown>,
  ensureBlock: EnsureBlock,
  blockNodeByKey: Map<string, string>,
  stale: boolean,
): void {
  const measurement = asObject(record.measurement);

  asArray(measurement?.series).forEach((rawSeries, i) => {
    const series = asObject(rawSeries);
    if (!series) return;
    const seriesId = str(series.series_id);
    const naturalKey = seriesId ? `series:${seriesId}` : null;
    const key =
      naturalKey && blockNodeByKey.has(naturalKey)
        ? naturalKey
        : `measurement.series[${i}]`;
    const parent = ensureBlock(key, {
      label: seriesId ?? `Series ${i + 1}`,
      kindWord: 'Series',
      producer: RECORD_PRODUCER,
      lines: [{ term: 'Official path', value: `measurement.series[${i}]` }],
      stale,
    });
    if (!parent) return;

    asArray(series.independent_variables).forEach((rawIv, j) => {
      const iv = asObject(rawIv);
      if (!iv) return;
      const name = str(iv.name) ?? `variable ${j + 1}`;
      ensureBlock(`measurement.series[${i}].independent_variables[${j}]`, {
        label: name,
        kindWord: 'Independent variable',
        producer: RECORD_PRODUCER,
        lines: [
          { term: 'Official path', value: `measurement.series[${i}].independent_variables[${j}]` },
          ...(str(iv.unit) ? [{ term: 'Unit', value: str(iv.unit) as string }] : []),
          { term: 'Points', value: String(asArray(iv.values).length) },
        ],
        parentId: parent,
        stale,
      });
    });

    asArray(series.channels).forEach((rawCh, j) => {
      const ch = asObject(rawCh);
      if (!ch) return;
      const name = str(ch.name) ?? `channel ${j + 1}`;
      ensureBlock(`measurement.series[${i}].channels[${j}]`, {
        label: name,
        kindWord: 'Channel',
        producer: RECORD_PRODUCER,
        lines: [
          { term: 'Official path', value: `measurement.series[${i}].channels[${j}]` },
          ...(str(ch.unit) ? [{ term: 'Unit', value: str(ch.unit) as string }] : []),
          ...(str(ch.role) ? [{ term: 'Role', value: str(ch.role) as string }] : []),
          { term: 'Points', value: String(asArray(ch.values).length) },
        ],
        parentId: parent,
        stale,
      });
    });
  });

  const qc = asObject(measurement?.qc);
  if (qc) {
    ensureBlock('measurement.qc', {
      label: 'QC',
      kindWord: 'QC block',
      producer: RECORD_PRODUCER,
      lines: [
        { term: 'Official path', value: 'measurement.qc' },
        ...(str(qc.status) ? [{ term: 'Status', value: str(qc.status) as string }] : []),
      ],
      stale,
    });
  }

  asArray(record.assets).forEach((rawAsset, i) => {
    const asset = asObject(rawAsset);
    if (!asset) return;
    const assetId = str(asset.asset_id);
    const naturalKey = assetId ? `assets:${assetId}` : null;
    const key = naturalKey && blockNodeByKey.has(naturalKey) ? naturalKey : `assets[${i}]`;
    ensureBlock(key, {
      label: assetId ?? `Asset ${i + 1}`,
      kindWord: 'Asset',
      producer: RECORD_PRODUCER,
      lines: [
        { term: 'Official path', value: `assets[${i}]` },
        ...(str(asset.content_role)
          ? [{ term: 'Role', value: str(asset.content_role) as string }]
          : []),
        ...(str(asset.media_type)
          ? [{ term: 'Media type', value: str(asset.media_type) as string }]
          : []),
      ],
      stale,
    });
  });

  const descriptors = asObject(record.descriptors);
  asArray(descriptors?.outputs).forEach((rawOut, i) => {
    const out = asObject(rawOut);
    if (!out) return;
    asArray(out.descriptors).forEach((rawD, j) => {
      const d = asObject(rawD);
      if (!d) return;
      const name = str(d.name);
      const naturalKey = name ? `descriptors:${name}` : null;
      const key =
        naturalKey && blockNodeByKey.has(naturalKey)
          ? naturalKey
          : `descriptors.outputs[${i}].descriptors[${j}]`;
      ensureBlock(key, {
        label: name ?? `Descriptor ${j + 1}`,
        kindWord: 'Descriptor',
        producer: RECORD_PRODUCER,
        lines: [
          { term: 'Official path', value: `descriptors.outputs[${i}].descriptors[${j}]` },
          ...(str(d.unit) ? [{ term: 'Unit', value: str(d.unit) as string }] : []),
          ...(str(d.source) ? [{ term: 'Source', value: str(d.source) as string }] : []),
        ],
        stale,
      });
    });
  });

  const attribution = asObject(record.attribution);
  asArray(attribution?.contributors).forEach((rawC, i) => {
    const c = asObject(rawC);
    if (!c) return;
    ensureBlock(`attribution.contributors[${i}]`, {
      label: str(c.name) ?? `Contributor ${i + 1}`,
      kindWord: 'Contributor',
      producer: RECORD_PRODUCER,
      lines: [
        { term: 'Official path', value: `attribution.contributors[${i}]` },
        ...(str(c.role) ? [{ term: 'Role', value: str(c.role) as string }] : []),
        ...(str(c.affiliation)
          ? [{ term: 'Affiliation', value: str(c.affiliation) as string }]
          : []),
        {
          term: 'Not an entity',
          value:
            'A contributor name is a free string. It is not resolved to a person, and no collaboration edge is drawn from it.',
        },
      ],
      stale,
    });
  });
}

// ------------------------------------------------------------------- finalize

function stepJump(stepId: string, experimentId: string): ExperimentGraphJump | null {
  switch (stepId) {
    case 'complete_metadata':
      return { label: 'Review & Answer', to: ROUTES.complete(experimentId) };
    case 'review_evidence':
      return { label: 'Open Evidence & Artifacts', to: ROUTES.evidence(experimentId) };
    case 'review_export_readiness':
    case 'export':
      return { label: 'Review Export Readiness', to: ROUTES.export(experimentId) };
    case 'load_record':
      return { label: 'Open This Record', to: ROUTES.record(experimentId) };
    default:
      return null;
  }
}

function finalize(b: Builder, anchorId: string): ExperimentGraph {
  const nodes = [...b.nodes.values()].sort((x, y) => byIdAsc(x.id, y.id));
  const byId = new Map(nodes.map((n) => [n.id, n] as const));
  const edges = [...b.edges].sort(
    (p, q) => byIdAsc(p.source, q.source) || byIdAsc(p.target, q.target) || byIdAsc(p.kind, q.kind),
  );

  const adjacency = new Map<string, ExperimentGraphAdjacent[]>();
  for (const n of nodes) adjacency.set(n.id, []);
  for (const e of edges) {
    adjacency.get(e.source)?.push({ id: e.target, edge: e, incoming: false });
    adjacency.get(e.target)?.push({ id: e.source, edge: e, incoming: true });
  }

  const counts = Object.fromEntries(
    EXPERIMENT_NODE_KINDS.map((k) => [k, 0]),
  ) as Record<ExperimentNodeKind, number>;
  for (const n of nodes) counts[n.kind] += 1;

  // The SAME deterministic layout the Project Memory canvas uses, over the whole
  // graph — so expanding a node reveals neighbours in place instead of
  // reshuffling everything the reader had just oriented themselves in.
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
    nodes,
    edges,
    byId,
    adjacency,
    layout,
    counts,
    notes: b.notes,
    truncated: b.truncated,
  };
}

// ------------------------------------------------------------------ view state

export interface ExperimentGraphViewState {
  /** Nodes whose neighbours are revealed. Always contains the anchor. */
  expanded: string[];
  selectedId: string | null;
  search: string;
  view: GraphViewport;
  /** Kinds the reader has hidden. Empty = everything the expansion reveals. */
  hiddenKinds: ExperimentNodeKind[];
}

export function initialExperimentGraphState(graph: ExperimentGraph): ExperimentGraphViewState {
  return {
    expanded: [graph.anchorId],
    selectedId: graph.anchorId,
    search: '',
    view: { cx: 0, cy: 0, scale: 1 },
    hiddenKinds: [],
  };
}

/**
 * Every state mutation this surface can perform. One union, one reducer — the
 * same discipline `GraphAction` established for the memory graph, so a pointer
 * click, a keyboard control and a search result cannot drift apart.
 */
export type ExperimentGraphAction =
  | { kind: 'select'; nodeId: string | null }
  | { kind: 'expand'; nodeId: string }
  | { kind: 'collapse'; nodeId: string }
  | { kind: 'reveal'; nodeId: string }
  | { kind: 'search'; query: string }
  | { kind: 'toggleKind'; nodeKind: ExperimentNodeKind }
  | { kind: 'pan'; dx: number; dy: number }
  | { kind: 'zoom'; factor: number }
  /** `box` is the measured canvas size; omitted, the default box is used. */
  | { kind: 'fit'; box?: ViewportBox }
  | { kind: 'reset'; box?: ViewportBox };

export function applyExperimentGraphAction(
  state: ExperimentGraphViewState,
  action: ExperimentGraphAction,
  graph: ExperimentGraph,
): ExperimentGraphViewState {
  switch (action.kind) {
    case 'select': {
      if (action.nodeId === null) return { ...state, selectedId: null };
      // Identity is never guessed: an id that is not in this graph selects
      // nothing rather than selecting something that looks similar.
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
      // The anchor is never collapsible: collapsing it would leave an empty
      // canvas with no way back except Reset.
      if (action.nodeId === graph.anchorId) return state;
      if (!state.expanded.includes(action.nodeId)) return state;
      const expanded = state.expanded.filter((id) => id !== action.nodeId);
      const visible = new Set(visibleNodeIds({ ...state, expanded }, graph));
      return {
        ...state,
        expanded,
        selectedId:
          state.selectedId && visible.has(state.selectedId) ? state.selectedId : graph.anchorId,
      };
    }

    case 'reveal': {
      if (!graph.byId.has(action.nodeId)) return state;
      const expanded = state.expanded.includes(action.nodeId)
        ? state.expanded
        : [...state.expanded, action.nodeId].sort(byIdAsc);
      return { ...state, expanded, selectedId: action.nodeId, search: '' };
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
        view: fitExperimentViewport(visibleNodeIds(state, graph), graph, action.box),
      };

    case 'reset': {
      const next = initialExperimentGraphState(graph);
      return {
        ...next,
        view: fitExperimentViewport(visibleNodeIds(next, graph), graph, action.box),
      };
    }

    default:
      return state;
  }
}

// --------------------------------------------------------------- derived views

/**
 * The nodes actually drawn: the expanded set plus every direct neighbour of it.
 *
 * This is what "progressive" means concretely — the first paint is the anchor
 * and its immediate neighbourhood, and the reader chooses what opens next.
 * Bounded by MAX_VISIBLE_NODES, and the bound is REPORTED (see
 * `visibleTruncated`) rather than silently applied.
 */
export function visibleNodeIds(
  state: ExperimentGraphViewState,
  graph: ExperimentGraph,
): string[] {
  const hidden = new Set(state.hiddenKinds);
  const out = new Set<string>();
  const allow = (id: string): boolean => {
    const node = graph.byId.get(id);
    if (!node) return false;
    // The anchor is never hidden by a kind filter: a reader must not be able to
    // filter away the thing the graph is about.
    if (id === graph.anchorId) return true;
    return !hidden.has(node.kind);
  };

  for (const id of state.expanded) {
    if (allow(id)) out.add(id);
    for (const adj of graph.adjacency.get(id) ?? []) {
      if (allow(adj.id)) out.add(adj.id);
    }
  }
  if (state.selectedId && allow(state.selectedId)) out.add(state.selectedId);
  if (allow(graph.anchorId)) out.add(graph.anchorId);

  return [...out].sort(byIdAsc).slice(0, MAX_VISIBLE_NODES);
}

export function visibleTruncated(
  state: ExperimentGraphViewState,
  graph: ExperimentGraph,
): boolean {
  const hidden = new Set(state.hiddenKinds);
  const set = new Set<string>();
  for (const id of state.expanded) {
    const node = graph.byId.get(id);
    if (node && (id === graph.anchorId || !hidden.has(node.kind))) set.add(id);
    for (const adj of graph.adjacency.get(id) ?? []) {
      const n = graph.byId.get(adj.id);
      if (n && (adj.id === graph.anchorId || !hidden.has(n.kind))) set.add(adj.id);
    }
  }
  return set.size > MAX_VISIBLE_NODES;
}

/** Edges whose BOTH endpoints are visible. An edge is never half-drawn. */
export function visibleEdges(
  visible: readonly string[],
  graph: ExperimentGraph,
): ExperimentGraphEdge[] {
  const set = new Set(visible);
  return graph.edges.filter((e) => set.has(e.source) && set.has(e.target));
}

/** Nodes that are drawn but still have undrawn neighbours — the expand targets. */
export function expandableNodeIds(
  state: ExperimentGraphViewState,
  graph: ExperimentGraph,
): Set<string> {
  const visible = new Set(visibleNodeIds(state, graph));
  const out = new Set<string>();
  for (const id of visible) {
    if (state.expanded.includes(id)) continue;
    const neighbours = graph.adjacency.get(id) ?? [];
    if (neighbours.some((adj) => !visible.has(adj.id))) out.add(id);
  }
  return out;
}

export interface ExperimentGraphSearchResult {
  id: string;
  label: string;
  kind: ExperimentNodeKind;
  /** The text that matched — never a guess about why it is relevant. */
  matchedOn: string;
}

/**
 * Search WITHIN this experiment. Case-insensitive substring over the node label,
 * its id and its already-server-derived detail values. Bounded, deterministic,
 * and it ranks nothing — a search that cannot explain its ordering should not
 * have one.
 */
export function searchExperimentGraph(
  query: string,
  graph: ExperimentGraph,
): ExperimentGraphSearchResult[] {
  const q = query.trim().toLowerCase();
  if (q === '') return [];
  const out: ExperimentGraphSearchResult[] = [];
  for (const node of graph.nodes) {
    if (out.length >= MAX_SEARCH_RESULTS) break;
    if (node.label.toLowerCase().includes(q)) {
      out.push({ id: node.id, label: node.label, kind: node.kind, matchedOn: node.label });
      continue;
    }
    const line = node.detail.find((l) => l.value.toLowerCase().includes(q));
    if (line) {
      out.push({
        id: node.id,
        label: node.label,
        kind: node.kind,
        matchedOn: `${line.term}: ${shortLabel(line.value, 60)}`,
      });
    }
  }
  return out;
}

/** Viewport that frames `ids` inside `box`. Falls back to identity when empty. */
export function fitExperimentViewport(
  ids: readonly string[],
  graph: ExperimentGraph,
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
    // BOTH dimensions, so a wide short box frames the content instead of
    // cropping it vertically or leaving it a dot in the middle.
    scale: clampScale(Math.min(box.width / w, box.height / h)),
  };
}

/** The edge between two nodes, if this graph has one (either direction). */
export function edgeBetween(
  a: string,
  b: string,
  graph: ExperimentGraph,
): ExperimentGraphEdge | null {
  return (
    graph.edges.find(
      (e) => (e.source === a && e.target === b) || (e.source === b && e.target === a),
    ) ?? null
  );
}
