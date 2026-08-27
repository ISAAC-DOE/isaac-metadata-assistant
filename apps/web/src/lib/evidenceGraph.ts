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
 * verbatim. That is enforced at RUNTIME, in both directions and symmetrically:
 * {@link Builder.addNode} refuses a node whose producer is not
 * `NODE_PRODUCERS[kind]`, and {@link Builder.addEdge} refuses an edge whose
 * producer is not one of `EDGE_PRODUCERS[kind]`. A test then asserts membership
 * over every emitted node and edge.
 *
 * Both halves are needed and neither is decoration. Until the node guard existed,
 * only the edges were checked and the node test asserted merely that the producer
 * string was non-empty — which `producer: 'inferred from the sample name'` would
 * have satisfied. Refusing at construction is what stops a future slice from
 * inventing a relationship, or a provenance, that merely looks plausible.
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
 * "EXACTLY TWO" MEANS TWO AS THE SERVER RECORDED THEM, not two as this module
 * managed to draw, and the difference is the whole guard rather than a nicety.
 * `attachEvidence` drops any item {@link readEvidenceItem} cannot narrow and any
 * item the node cap refuses; the backend filters neither way — `serialize`'s
 * readable-evidence projection keeps any object, and `evidence_classify` counts an
 * entry with no `source_type` when it decides `conflicting_evidence`. So three
 * stored entries of which one is unreadable here leave TWO drawn nodes, and a pair
 * chosen from them would be a pair chosen by ARRAY POSITION out of three — exactly
 * the invention the `> 2` rule exists to refuse, arrived at by a different road.
 * Step 6 therefore reads the count off the SERVER's `ApiEvidenceEntry` and refuses
 * the edge whenever anything at all was dropped.
 *
 * ── The four routes beyond the record bundle ────────────────────────────────
 *
 * This module read the bundle (detail, runs, evidence trail, classification, run
 * checks) and nothing else, and four routes the record screens ALREADY call went
 * unread — so the graph could not answer "which conflict was decided, and does the
 * decision still hold?", "what has been written down that has no place yet?",
 * "where did this value come from?" or "which asset is referenced, and does it
 * reach any exported record?". They are now inputs: `GET .../conflicts`,
 * `GET .../notes`, `GET .../provenance` and `GET .../assets`, plus
 * `GET .../revisions` for exactly one question. **No backend route was added.**
 *
 * Four things about them that are design rather than convenience:
 *
 *   · EACH IS OPTIONAL AND EACH IS A STATE, not data — see {@link EvidenceSubFetch}.
 *     "not read yet", "could not be read" and "this mount does not read it" are
 *     three different facts and only the middle one is a failure.
 *   · EACH IS BOUNDED BY ITS OWN CONSTANT and says what it withheld. The global
 *     node cap is shared, so leaning on it alone would let a record with 900 notes
 *     displace the runs a reader came for, under a note that named neither.
 *   · EACH IS COMPARED AGAINST THE RECORD'S VERSION using the token IT publishes —
 *     `subFetchFreshness`, the same version-token discipline as the key below, not
 *     a second mechanism.
 *   · PROVENANCE AND REVISIONS MINT NO NODES. The first describes addresses this
 *     view already draws, so it adds lines to the node that owns each one; the
 *     second is read for a sentence about whether the drawn content is on record,
 *     and NO historical revision is drawn at all. A superseded value drawn beside a
 *     current one, in a picture whose grammar is "these things are related", reads
 *     as something the record still holds.
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
  ApiAsset,
  ApiAssetsResponse,
  ApiConflict,
  ApiConflictCandidate,
  ApiConflictResolution,
  ApiConflictsResponse,
  ApiEvidenceClassification,
  ApiEvidenceEntry,
  ApiExperimentDetail,
  ApiMemoryGraphEdge,
  ApiNote,
  ApiNotesResponse,
  ApiResolutionWithoutConflict,
  ApiRevisionHistory,
  ApiRunCheckFinding,
  ApiRunCheckResponse,
  ApiRunView,
  FieldEvidence,
} from './types';
import type { ApiProvenanceResponse } from './api';
import {
  ORIGIN_LABEL,
  REVIEW_STATE_LABEL,
  type ProvenanceOrigin,
  type ProvenanceReviewState,
} from './provenance';
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
import {
  OFFICIAL_SOURCE_LABEL,
  officialCheckedDocument,
  officialDocumentDetailValue,
  officialFindingSource,
} from './officialAttribution';
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

/*
 * ── Per-source bounds, and why each source needs its OWN one ────────────────
 *
 * `MAX_EVIDENCE_GRAPH_NODES` bounds the graph. It does NOT bound a source, and
 * relying on it alone would be a silent truncation with a misleading name: an
 * experiment carrying 900 notes would fill the cap with notes, the `node_cap`
 * note would say "more than 1200 nodes", and the runs a reader came for would
 * simply be missing with no sentence saying which source displaced them.
 *
 * So each unbounded route gets a bound of its own, is truncated in a
 * DETERMINISTIC order (never "whatever arrived first"), and says what it withheld
 * through the `source_bounded` note. `GET /notes`, `GET /conflicts` and
 * `GET /assets` take no `limit` parameter, so the bound is applied here, on what
 * is DRAWN — the payload cost was already paid by the record screens that read
 * the same routes (`api.ts`: no backend route was added for this surface).
 */

/**
 * Bound on `conflict` nodes drawn. Ordered by address, so the cut is stable.
 *
 * ALSO the bound on `resolutions_without_conflict[]` — the second unbounded array
 * in the same response. See {@link addOrphanDecisions}: they come from one route,
 * they are the same family of thing, and each withholding is disclosed under its
 * own clause of the `source_bounded` note.
 */
export const MAX_GRAPH_CONFLICTS = 40;

/**
 * Bound on `conflict_candidate` nodes under ONE conflict.
 *
 * Deliberately small. A disagreement between more than a handful of answers is
 * not read one candidate at a time, and `distinct_value_count` is on the conflict
 * node either way — so the reader is never told there are six when there are
 * sixty.
 */
export const MAX_CONFLICT_CANDIDATES = 6;

/** Bound on `note` nodes drawn. Ordered by capture time, then id. */
export const MAX_GRAPH_NOTES = 50;

/** Bound on `asset_reference` nodes drawn. Ordered by asset id. */
export const MAX_GRAPH_ASSET_REFS = 60;

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
  /*
   * The five kinds added when this view stopped reading only the evidence trail.
   * Each names a thing a SCIENTIST recognises, and each has exactly one route
   * behind it — see `NODE_PRODUCERS`. None of them is a schema concept and none
   * of them is a repository concept.
   */
  'conflict',
  'conflict_candidate',
  'conflict_decision',
  'note',
  'asset_reference',
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
  /*
   * `conflicts_with` joins TWO EVIDENCE ENTRIES and says they disagree; it is
   * emitted under the two conditions step 6 states and nothing here relaxes them.
   * `has_conflict` is a different statement entirely — it joins an ADDRESS to the
   * server's own record OF the disagreement, which exists whether or not the pair
   * can be named. The two coexist deliberately: one is a pair, the other is a
   * subject, and collapsing them would let a `> 2`-entry conflict either vanish or
   * acquire an invented pair.
   */
  'has_conflict',
  'competing_value',
  'has_decision',
  'has_note',
  'mapped_to',
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
  /*
   * THE THIRD CHANNEL IS NAMED BY ITS POSITION IN THE RESPONSE, NOT BY A VALIDATOR.
   * ~~"blockers, draft errors, official-schema errors"~~ — STRUCK, because this line
   * made the exact attribution the `Reported by` line beside it had just been
   * corrected for, on the SAME details pane. `EvidenceGraphPanel.tsx:1228` renders
   * this string verbatim under the heading "Where this came from", so on a dry-run
   * exactness finding the pane read:
   *
   *     Reported by:          Candidate-record check — source not named
   *     Where this came from: … blockers, draft errors, official-schema errors
   *
   * — the correction and the defect one line apart. `check.official.errors` is not
   * known to be the official schema's: `_validate_unit`'s dry-run branch returns
   * `export_draft`'s result, which falls back to the NO-GUESSING report's errors —
   * including an anchored-pattern exactness refusal, which `export.py` folds into it
   * — whenever `validate_official` was never reached. `CLAUDE.md` §12: no surface may
   * report an exactness refusal as an official-schema error.
   *
   * The producer now names WHERE each list came from, which is what a producer is for
   * and is true on every branch: three keys of one response. Which validator spoke is
   * `findingOriginLabel`'s answer, made per finding from `dry_run` and `unavailable`,
   * and it is the only place in this module that may name the schema at all.
   */
  validation_finding:
    'one finding of the run check (POST /api/experiments/{id}/runs/{runId}/check) — its `blockers`, `draft.errors` and `official.errors` lists',
  conflict:
    'one element of conflicts[] (GET /api/experiments/{id}/conflicts) — an address whose stored evidence asserts incompatible values',
  /*
   * A CANDIDATE IS NOT A VALUE THE RECORD HOLDS. `conflicts[].candidates[]` groups
   * the competing answers BY VALUE, each with the citations asserting it; the
   * record stores all of them and accepts none. Nothing in this module marks one as
   * chosen — see `candidateDecidedLine`, which compares only the SERVER's two
   * canonical strings and never canonicalises anything itself.
   */
  conflict_candidate:
    'one element of conflicts[].candidates[] (GET /api/experiments/{id}/conflicts) — one competing answer, with the citations that assert it',
  /*
   * ONE PRODUCER FOR TWO FIELDS, because they are the same act recorded in two
   * places: `conflicts[].resolution` is a decision whose address still conflicts,
   * and `resolutions_without_conflict[]` is a decision whose address no longer
   * does. `Builder.addNode` tests a node producer for EQUALITY (a kind has one),
   * so naming both fields in the one string is what keeps the answer to "where did
   * this come from?" true on both arms rather than true on the commoner one.
   */
  conflict_decision:
    'a recorded decision — conflicts[].resolution or resolutions_without_conflict[] (GET /api/experiments/{id}/conflicts)',
  note: 'one element of notes[] (GET /api/experiments/{id}/notes) — captured text with no schema home yet',
  asset_reference:
    "one element of assets[] (GET /api/experiments/{id}/assets) — this record's asset library",
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
  references: [
    'an assets* address present on this owner',
    "this record's asset library (GET /api/experiments/{id}/assets)",
    'assets[].used_by_runs (GET /api/experiments/{id}/assets)',
  ],
  supported_by: ['a stored evidence entry recorded at an address in this group'],
  derived_from: [
    'the source recorded on this evidence entry (source_file / rule / user confirmation)',
    "the server's own inherited state for this run (run.inherited[address].state === 'inherited')",
  ],
  validated_by: ['a finding of the run check (POST .../runs/{runId}/check)'],
  conflicts_with: [
    "the server's evidence-support classification `conflicting_evidence` at an address carrying exactly two entries",
  ],
  has_conflict: [
    'one element of conflicts[] at this address (GET /api/experiments/{id}/conflicts)',
  ],
  competing_value: [
    'one element of conflicts[].candidates[] at this address (GET /api/experiments/{id}/conflicts)',
  ],
  has_decision: [
    'conflicts[].resolution — the recorded decision at this address (GET /api/experiments/{id}/conflicts)',
    'one element of resolutions_without_conflict[] (GET /api/experiments/{id}/conflicts)',
  ],
  has_note: [
    'notes[].run_id names this run (GET /api/experiments/{id}/notes)',
    'notes[] carrying no run_id (GET /api/experiments/{id}/notes)',
  ],
  /*
   * `mapped_field_path` ONLY, and `candidate_field_path` DELIBERATELY NOT. The
   * first is a path a PERSON named; the second is what something deterministic
   * PROPOSED, and `notes.py` keeps the two apart precisely so a suggestion is
   * never indistinguishable from a decision. Drawing a line for a proposal nobody
   * has accepted would undo that here, in the one representation where a line
   * reads as a fact. The proposal is shown on the note's own details instead,
   * labelled as a proposal.
   */
  mapped_to: [
    'notes[].mapped_field_path — the path a person named (GET /api/experiments/{id}/notes)',
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
  conflict: 'Conflict',
  // "Competing answer", not "candidate value": the second reads as a value the
  // record is holding, and the record holds all of them and accepts none.
  conflict_candidate: 'Competing Answer',
  conflict_decision: 'Conflict Decision',
  note: 'Unmapped Note',
  asset_reference: 'Asset Reference',
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
  has_conflict: 'has conflict',
  competing_value: 'competing answer',
  has_decision: 'decided by',
  has_note: 'has note',
  mapped_to: 'placed at',
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
  | 'visible_cap'
  /*
   * The four sub-fetch note kinds are COMPOSED — one note listing every source in
   * that condition — rather than one kind per source.
   *
   * `Builder.note` keeps the FIRST text per kind, so a `conflicts_stale` and a
   * `notes_stale` kind would have produced two notes whose survival order a reader
   * cannot see, and eleven kinds where four say the same thing. Each of these
   * gathers across sources and emits once, at the end, naming every source it
   * covers. That is the same shape `unmodelled_addresses` already uses.
   */
  | 'sub_fetch_unavailable'
  | 'sub_fetch_stale'
  | 'unreadable_entries'
  | 'source_bounded'
  /** Conflicts are read at RECORD scope only. `?run=` is a per-run request. */
  | 'conflicts_record_scope'
  /** `provenance.blocks_not_described` — what the route itself did not describe. */
  | 'provenance_undescribed'
  /** Whether the drawn content is on record as a revision. Never history drawn. */
  | 'revision_state';

export interface EvidenceGraphNote {
  kind: EvidenceGraphNoteKind;
  text: string;
}

/**
 * The `conflict_pair_unknown` disclosure, as a constant because BOTH refusals in
 * {@link buildEvidenceGraph} step 6 emit it and `Builder.note` keeps only the
 * FIRST text per kind — two near-identical sentences would mean the surviving one
 * is decided by iteration order over the classification.
 *
 * It therefore has to be true of both reasons: more than two recorded entries, and
 * a recorded set this build could not draw in full. The per-address detail line
 * says which one applies where; this says the rule.
 */
export const CONFLICT_PAIR_UNKNOWN_NOTE =
  'At least one address is classified as conflicting, and cannot be reduced to a single pair here — either the server records more than two entries there, or not every entry it records could be read and drawn. The stored state says that the entries disagree, not which pair does, so no conflict line is drawn there; it is stated in the details instead.';

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
  /**
   * Coordinates for EVERY node BUILT — including the ones no expansion has
   * revealed yet, so opening a node never has to invent a position for it.
   *
   * DETERMINISTIC IN THE INPUT, NOT STABLE ACROSS INPUTS, and the distinction is
   * worth stating because an earlier revision of this line claimed "expanding
   * never reshuffles" and that is FALSE. `computeLayout` seeds each node from its
   * INDEX in the id list, so the whole layout is a function of the node SET: the
   * same set always yields byte-identical coordinates, and a set that gains a
   * member re-seeds every member. Expanding a node does not change the set —
   * visibility is a view concern and the builder draws everything either way — but
   * OPENING A RUN FETCHES ITS CHECK, and a check that arrives adds
   * `validation_finding` nodes, which does. So the picture can settle differently
   * once a run's findings load. That is a rebuild, not a reshuffle of a stale
   * layout, and it is the price of holding no cache; nothing here is random and
   * nothing depends on a clock.
   */
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

/**
 * ONE SUB-FETCH, IN ONE OF ITS FOUR STATES — and the fourth is `undefined`.
 *
 * The three members below are the states a reader can be in once a mount has
 * decided to read a source. `undefined` — the field simply absent from
 * {@link EvidenceGraphInput} — is the FOURTH and is a different fact: this mount
 * does not read that source at all, so there is nothing to report about it and no
 * note is emitted. A mount that reads a source and fails says so; a mount that
 * never asked says nothing, because "could not be read" would be false.
 *
 * `loading` and `error` are kept apart for the reason the run-check states are:
 * "not read yet" and "could not be read" are different, and only one of them is
 * worth a reader's attention.
 */
export type EvidenceSubFetch<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'data'; data: T };

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

  // ── the four routes this view reads BESIDES the bundle ───────────────────
  //
  // Every one is optional, and the absence of one is not a failure — see
  // `EvidenceSubFetch`. Each response carries its own version token, and the
  // builder compares it with the record's rather than assuming they agree; see
  // `SUB_FETCH_SOURCES`.

  /** `GET /api/experiments/{id}/conflicts` — RECORD scope. See `conflicts_record_scope`. */
  conflicts?: EvidenceSubFetch<ApiConflictsResponse>;
  /** `GET /api/experiments/{id}/notes`. */
  notes?: EvidenceSubFetch<ApiNotesResponse>;
  /** `GET /api/experiments/{id}/provenance` — RECORD scope. */
  provenance?: EvidenceSubFetch<ApiProvenanceResponse>;
  /** `GET /api/experiments/{id}/assets` — the asset LIBRARY, not the addresses. */
  assets?: EvidenceSubFetch<ApiAssetsResponse>;
  /**
   * `GET /api/experiments/{id}/revisions`.
   *
   * Read for ONE question — is the content drawn here on record as a revision? —
   * and for nothing else. No historical revision is drawn as a node; see
   * `applyRevisions` for why.
   */
  revisions?: EvidenceSubFetch<ApiRevisionHistory>;
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
 * THE SAME MECHANISM, APPLIED TO A SUB-FETCH — a version TOKEN comparison, never
 * a timestamp, a counter or a boolean "loaded".
 *
 * {@link evidenceGraphFreshnessKey} answers "is anything CACHED here describing a
 * record that has moved?" for the one thing that is cached. This answers the
 * neighbouring question for the four things that are FETCHED SEPARATELY: each of
 * those routes reads the record at whatever version it happens to hold, and each
 * one publishes the token it read. So the comparison is against the token the
 * RESPONSE carries, not against when the request went out — a re-read that
 * arrives late but reads the current version is fresh, and a re-read that lands
 * instantly on an older replica is not.
 *
 * `null` is `unknown`, not `fresh`, and that asymmetry is the whole point: a
 * response that publishes no token cannot be said to agree with the record, and
 * `fresh` is the one answer that must be earned.
 */
export type SubFetchFreshness = 'fresh' | 'stale' | 'unknown';

/**
 * The `record_rev` token, as a STRING or as `null` — never as the string
 * `"undefined"`.
 *
 * Two of the five sub-fetches publish a NUMBER (`record_rev`) rather than the
 * `"<generation>.<rev>"` string, so the number has to be rendered before
 * {@link subFetchFreshness} can compare it. Rendering it with a bare `String()`
 * is what silently defeated the guarantee that function's own doc calls "the
 * whole point": `String(undefined)` is `"undefined"`, which is a non-empty
 * string, so a record and a response that BOTH publish no rev compared EQUAL and
 * the response was drawn as `fresh` — the one answer that must be earned. A
 * missing token now returns `null` and reaches the `unknown` arm, which discloses.
 */
function revToken(rev: unknown): string | null {
  return typeof rev === 'number' && Number.isFinite(rev) ? String(rev) : null;
}

export function subFetchFreshness(
  expected: string | null | undefined,
  reported: string | null | undefined,
): SubFetchFreshness {
  if (typeof expected !== 'string' || expected === '') return 'unknown';
  if (typeof reported !== 'string' || reported === '') return 'unknown';
  return expected === reported ? 'fresh' : 'stale';
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
  /*
   * SCOPED BY RUN, not by address alone. `GET .../conflicts` answers about the
   * RECORD's own fields or about ONE run's, and the same address can conflict in
   * both — so an id built from the address alone would merge two different
   * disagreements into one node, silently, the first time anything passes
   * run-scoped conflicts in. This view asks at record scope today; the id does not
   * depend on that staying true.
   */
  conflict: (runId: string | null, address: string) => `conflict:${runId ?? ''}#${address}`,
  /*
   * Built FROM the conflict's own id, so the scoping above cannot be forgotten
   * here, and keyed on the SERVER's `canonical` — the exact string its conflict
   * rule compares, so two candidates are the same node precisely when the server
   * says they are the same answer. Keying on array position would make a node's
   * identity depend on how the response happened to be ordered.
   */
  conflictCandidate: (conflictNodeId: string, canonical: string) =>
    `${conflictNodeId}#answer#${canonical}`,
  decision: (resolutionId: string) => `decision:${resolutionId}`,
  note: (noteId: string) => `note:${noteId}`,
  assetReference: (assetId: string) => `asset-ref:${assetId}`,
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

// ------------------------------------------- the four routes beyond the bundle

/**
 * The product word for an origin the SERVER named, or the raw string.
 *
 * A LOOKUP, NEVER AN ENUMERATION, and the difference is a project rule rather
 * than a nicety. `provenance.py:86-94` records that `assistant` is a member of the
 * dimension that **nothing in this build produces**, and that no surface may list
 * it as an available capability. A lookup renders it if and only if a response
 * carries it; a static list of origins in a legend would advertise it. This module
 * therefore has no origin legend, no origin filter and no origin chip inventory —
 * an origin reaches the screen only attached to an address that reported it.
 */
function originLabel(origin: string): string {
  return ORIGIN_LABEL[origin as ProvenanceOrigin] ?? origin;
}

function reviewStateLabel(state: string): string {
  return REVIEW_STATE_LABEL[state as ProvenanceReviewState] ?? state;
}

/** Everything the extra sources need in order to hang nodes off the right owner. */
interface ExtraSourceContext {
  rootId: string;
  /** The group node for an address under one owner, or undefined. */
  groupNodeFor: (ownerId: string, address: string) => string | undefined;
  /** Loaded runs only. A run beyond the bounded page is absent, and is SAID to be. */
  runNodeByRunId: Map<string, string>;
  runLabelByRunId: Map<string, string>;
  /** Accumulators the four composed notes are built from, at the very end. */
  ledger: SubFetchLedger;
}

/**
 * What the composed sub-fetch notes are built out of.
 *
 * Gathered across every source and emitted ONCE each, for the reason
 * {@link EvidenceGraphNoteKind} states: one kind per source would give four kinds
 * saying the same thing and let `Builder.note`'s first-wins rule decide, by
 * iteration order, which source a reader is told about.
 */
interface SubFetchLedger {
  loading: string[];
  failed: { source: string; message: string }[];
  stale: { source: string; expected: string; reported: string }[];
  unknownFreshness: string[];
  unreadable: { source: string; count: number }[];
  bounded: string[];
}

function emptyLedger(): SubFetchLedger {
  return {
    loading: [],
    failed: [],
    stale: [],
    unknownFreshness: [],
    unreadable: [],
    bounded: [],
  };
}

/**
 * Read one sub-fetch, recording its state, and return its data or `null`.
 *
 * `undefined` returns `null` and records NOTHING — a mount that does not read a
 * source has nothing to report about it. Every other state is recorded before the
 * data is returned, so a source can be simultaneously usable and disclosed as
 * stale rather than being either trusted or dropped.
 */
function readSubFetch<T>(
  sourceLabel: string,
  fetched: EvidenceSubFetch<T> | undefined,
  ledger: SubFetchLedger,
  freshness: {
    /**
     * `null` when the RECORD publishes no token to compare against — which is a
     * different fact from a mismatch and must reach {@link subFetchFreshness} as
     * one. Typing this `string` and stringifying at the call site is how the
     * `null` is `unknown`, never `fresh` guarantee was defeated for the two
     * `record_rev` sources: `String(undefined)` is the non-empty `"undefined"`,
     * and two of them compare EQUAL, so a pair of missing tokens read as `fresh`.
     */
    expected: string | null;
    reported: (data: T) => string | null | undefined;
  },
): T | null {
  if (fetched === undefined) return null;
  if (fetched.state === 'loading') {
    ledger.loading.push(sourceLabel);
    return null;
  }
  if (fetched.state === 'error') {
    ledger.failed.push({ source: sourceLabel, message: fetched.message });
    return null;
  }
  const reported = freshness.reported(fetched.data);
  const verdict = subFetchFreshness(freshness.expected, reported);
  if (verdict === 'stale') {
    // `stale` is reachable only when BOTH are non-empty strings, so neither cast
    // below can print `null` or `undefined` at a reader.
    ledger.stale.push({
      source: sourceLabel,
      expected: String(freshness.expected),
      reported: String(reported),
    });
  } else if (verdict === 'unknown') {
    ledger.unknownFreshness.push(sourceLabel);
  }
  return fetched.data;
}

/** The decision's own words for what state it is in. Never a colour, never a verdict. */
function decisionStateSentence(state: string, outcome: string): string {
  if (outcome === 'deferred') {
    return 'Somebody looked at this disagreement and deliberately did not choose. The conflict stands.';
  }
  if (state === 'current') {
    return 'Somebody chose, and the answers they chose between are still the answers recorded here.';
  }
  if (state === 'stale') {
    return 'Somebody chose, and MORE competing evidence has been recorded since. The decision was made over a different set of answers, so it no longer covers this disagreement — it is kept and shown rather than deleted, and the address is conflicting again.';
  }
  return `The server reports this decision's state as \`${state}\`.`;
}

function decisionLabel(outcome: string, state: string): string {
  if (outcome === 'deferred') return 'Deferred — nobody chose';
  if (state === 'stale') return 'Decision — superseded';
  if (state === 'current') return 'Decision — current';
  return `Decision — ${state}`;
}

function decisionDetailLines(
  resolution: ApiConflictResolution,
): EvidenceGraphDetailLine[] {
  const lines: EvidenceGraphDetailLine[] = [
    { term: 'Address', value: resolution.address },
    { term: 'Outcome', value: resolution.outcome },
    { term: 'Decision state', value: resolution.state },
    { term: 'What that means', value: decisionStateSentence(resolution.state, resolution.outcome) },
  ];
  if (resolution.outcome === 'resolved') {
    const chosen = valueText(resolution.chosen_value);
    lines.push({
      term: 'Value stood behind',
      value: chosen ?? 'the stored decision records no readable value',
    });
    lines.push({
      term: 'Chosen from',
      value:
        resolution.chosen_from === 'edited'
          ? 'a value none of the recorded citations asserts — the person entered it'
          : resolution.chosen_from === 'candidate'
            ? 'one of the recorded competing answers'
            : 'the stored decision does not say',
    });
  }
  lines.push({
    term: 'Competing answers at the time',
    value: String(resolution.competing_values.length),
  });
  if (resolution.rationale) lines.push({ term: 'Reason given', value: resolution.rationale });
  lines.push({ term: 'Recorded', value: resolution.recorded_utc });
  /*
   * WHO, INCLUDING HONESTLY NOBODY. `subject` is null whenever no trusted
   * boundary established one, and `trust_basis` says what the attribution is
   * WORTH — a basis of `test_fixture` is a real shipped basis and is not proof
   * anybody authenticated. Substituting a placeholder name here is exactly the
   * invention the backend refuses by pairing the two fields.
   */
  lines.push({
    term: 'Who is on record',
    value: resolution.subject
      ? `${resolution.subject} (trust basis: ${resolution.trust_basis})`
      : `nobody — no trusted identity was established (trust basis: ${resolution.trust_basis})`,
  });
  lines.push({ term: 'Times revised', value: String(Math.max(0, resolution.history.length - 1)) });
  /*
   * THE ONE THING A READER MUST NOT INFER, stated rather than left to the shape.
   * The backend serialises `is_field_value` and `is_evidence` as the literal
   * `false` precisely so this guarantee survives the boundary; a graph node that
   * showed the chosen value without this line would read as the field's value.
   */
  lines.push({
    term: 'Not the value, not a citation',
    value:
      'Recording a decision changes no scientific content. This is not the field’s value and not an evidence entry — the competing citations are all still stored, exactly as they were.',
  });
  return lines;
}

/**
 * Was this competing answer among the ones the decision was made over?
 *
 * BOTH SIDES OF THIS COMPARISON ARE THE SERVER'S OWN CANONICAL STRINGS — the
 * candidate's `canonical` and the resolution's `competing_values`, produced by the
 * same function on the same side of the wire. Nothing here canonicalises anything,
 * which is the trap `api.resolveConflict` records: reproducing the server's
 * `json.dumps(..., sort_keys=True, default=str)` in TypeScript is a second
 * definition of "the same value", and JS and Python already disagree about
 * container separators and non-ASCII escaping.
 *
 * `chosen_value` is deliberately NOT compared, because it is the raw value and
 * matching it to a candidate WOULD need that canonicalisation. So no candidate is
 * ever marked "this is the one that was chosen"; the chosen value is stated on the
 * decision node, where it needs no matching.
 */
function candidateDecidedLine(
  candidate: ApiConflictCandidate,
  resolution: ApiConflictResolution | null,
): EvidenceGraphDetailLine | null {
  if (!resolution) return null;
  return resolution.competing_values.includes(candidate.canonical)
    ? {
        term: 'Present when the decision was made',
        value:
          'Yes — this answer was among the ones the recorded decision was made over.',
      }
    : {
        term: 'Present when the decision was made',
        value:
          'No — this answer was recorded AFTER the decision, which is why that decision no longer covers this disagreement.',
      };
}

/**
 * Conflicts, decisions and competing answers, from `GET .../conflicts`.
 *
 * The classification-derived `conflicts_with` edge of step 6 is untouched and
 * still governs when a PAIR may be named. This adds the SUBJECT of the
 * disagreement, which exists whether or not a pair can be named — and, for the
 * first time, the recorded human decision about it.
 */
function addConflicts(
  b: Builder,
  ctx: ExtraSourceContext,
  res: ApiConflictsResponse,
): void {
  if (res.unreadable_resolution_entries > 0) {
    ctx.ledger.unreadable.push({
      source: 'recorded conflict decisions',
      count: res.unreadable_resolution_entries,
    });
  }

  const ordered = [...(res.conflicts ?? [])].sort((x, y) => byIdAsc(x.address, y.address));
  const drawn = ordered.slice(0, MAX_GRAPH_CONFLICTS);
  if (ordered.length > drawn.length) {
    ctx.ledger.bounded.push(
      `${ordered.length - drawn.length} of ${ordered.length} conflicting address(es) — the first ${MAX_GRAPH_CONFLICTS} by address are drawn`,
    );
  }

  for (const conflict of drawn) {
    const ownerRunNode = conflict.run_id ? ctx.runNodeByRunId.get(conflict.run_id) : undefined;
    const ownerBase = ownerRunNode ?? ctx.rootId;
    const owner = ctx.groupNodeFor(ownerBase, conflict.address) ?? ownerBase;
    const conflictId = addConflictNode(b, ctx, conflict, owner, ownerRunNode ?? null);
    if (!conflictId) continue;

    b.addEdge({
      source: owner,
      target: conflictId,
      kind: 'has_conflict',
      producer: EDGE_PRODUCERS.has_conflict[0],
      why: `The server reports ${conflict.address} as conflicting: ${conflict.explanation}`,
      label: conflict.resolution_state,
      containment: true,
    });

    addCandidates(b, ctx, conflict, conflictId);

    if (conflict.resolution) {
      const decisionId = addDecisionNode(b, conflict.resolution, conflictId, ownerRunNode ?? null);
      if (decisionId) {
        b.addEdge({
          source: conflictId,
          target: decisionId,
          kind: 'has_decision',
          producer: EDGE_PRODUCERS.has_decision[0],
          why: `A decision about ${conflict.address} is on record, and the server derives its state as \`${conflict.resolution.state}\`. ${decisionStateSentence(conflict.resolution.state, conflict.resolution.outcome)}`,
          label: conflict.resolution.state,
          containment: true,
        });
      }
    }
  }

  addOrphanDecisions(b, ctx, res.resolutions_without_conflict ?? []);
}

function addConflictNode(
  b: Builder,
  ctx: ExtraSourceContext,
  conflict: ApiConflict,
  owner: string,
  runNodeId: string | null,
): string | null {
  const detail: EvidenceGraphDetailLine[] = [
    { term: 'Address', value: conflict.address },
    {
      term: 'Scope',
      value: conflict.run_id
        ? `this run's own fields (${ctx.runLabelByRunId.get(conflict.run_id) ?? conflict.run_id})`
        : "the record's own fields",
    },
    { term: 'Why this is here', value: conflict.explanation },
    { term: 'Distinct competing answers', value: String(conflict.distinct_value_count) },
    { term: 'Citations recorded here', value: String(conflict.evidence_count) },
    { term: 'Decision state', value: conflict.resolution_state },
  ];
  if (conflict.unavailable) {
    detail.push({
      term: 'Partly unreadable',
      value:
        'Some of the stored evidence at this address could not be read, so the competing answers below are not the whole picture. Nothing is invented in place of what could not be read.',
    });
  }
  if (!conflict.resolution) {
    detail.push({
      term: 'Decided?',
      value:
        'No decision is on record for this address. Nothing here picks a winner, and the record stores every competing citation.',
    });
  }
  /*
   * AN ALREADY-DECIDED ADDRESS IS STILL LISTED, and this line is why that is not
   * a contradiction: nothing in this API removes an evidence entry, so the
   * competing citations remain stored forever and the address goes on classifying
   * as conflicting. A reader branches on the decision state, never on the absence
   * of a conflict.
   */
  if (conflict.resolved) {
    detail.push({
      term: 'Still listed after a decision',
      value:
        'A decided address is still shown, because nothing removes an evidence entry: the competing citations remain stored and the address goes on classifying as conflicting. What changed is that a decision is now on record.',
    });
  }
  return b.addNode({
    id: nodeIds.conflict(conflict.run_id, conflict.address),
    kind: 'conflict',
    label: shortLabel(conflict.address, 40),
    producer: NODE_PRODUCERS.conflict,
    detail,
    runId: conflict.run_id ?? (runNodeId ? (b.nodes.get(runNodeId)?.runId ?? null) : null),
    parentId: owner,
  });
}

function addCandidates(
  b: Builder,
  ctx: ExtraSourceContext,
  conflict: ApiConflict,
  conflictId: string,
): void {
  /*
   * SERVER ORDER, CUT AT THE TAIL. The order is the evidence array's, which is
   * deterministic in the response, so the same response always drops the same
   * candidates; re-sorting would reorder a list whose order is the record's.
   */
  const candidates = conflict.candidates ?? [];
  const drawn = candidates.slice(0, MAX_CONFLICT_CANDIDATES);
  if (candidates.length > drawn.length) {
    ctx.ledger.bounded.push(
      `${candidates.length - drawn.length} of ${candidates.length} competing answer(s) at ${conflict.address} — the first ${MAX_CONFLICT_CANDIDATES} the server lists are drawn, and the full count is on the conflict itself`,
    );
  }
  for (const candidate of drawn) {
    const value = valueText(candidate.value);
    const detail: EvidenceGraphDetailLine[] = [
      { term: 'Address', value: conflict.address },
      { term: 'Competing answer', value: value ?? '(the stored value has no one-line rendering)' },
      /*
       * RULE, STATED ON EVERY ONE OF THEM. A competing answer is not a value the
       * record holds and not something anything here accepts; the panel also
       * marks the kind visually. Both, because a colour is not a claim a screen
       * reader can hear and a sentence is not something a reader sees at a glance.
       */
      {
        term: 'What this is',
        value:
          'One of the answers the stored citations assert. The record holds all of them and accepts none — this is not the field’s value, and nothing here has chosen it.',
      },
      { term: 'Citations asserting it', value: String(candidate.evidence_count) },
    ];
    if (candidate.uncited_evidence_count > 0) {
      detail.push({
        term: 'Citations that cannot be named',
        value: `${candidate.uncited_evidence_count} of them record no source type, so there is nothing safe to name. They are counted, not withheld.`,
      });
    }
    for (const source of candidate.sources) {
      detail.push({
        term: 'Cited by',
        value: source.locator ? `${source.source_type} — ${source.locator}` : source.source_type,
      });
    }
    const decided = candidateDecidedLine(candidate, conflict.resolution);
    if (decided) detail.push(decided);

    const id = b.addNode({
      id: nodeIds.conflictCandidate(conflictId, candidate.canonical),
      kind: 'conflict_candidate',
      label: shortLabel(value ?? candidate.canonical, 40),
      producer: NODE_PRODUCERS.conflict_candidate,
      detail,
      runId: conflict.run_id ?? null,
      parentId: conflictId,
    });
    if (!id) continue;
    b.addEdge({
      source: conflictId,
      target: id,
      kind: 'competing_value',
      producer: EDGE_PRODUCERS.competing_value[0],
      why: `${candidate.evidence_count} stored citation(s) at ${conflict.address} assert this answer. Nothing here accepts it; the record holds every competing answer at once.`,
      label: null,
      containment: true,
    });
  }
}

function addDecisionNode(
  b: Builder,
  resolution: ApiConflictResolution,
  parentId: string,
  runNodeId: string | null,
): string | null {
  return b.addNode({
    id: nodeIds.decision(resolution.resolution_id),
    kind: 'conflict_decision',
    label: decisionLabel(resolution.outcome, resolution.state),
    producer: NODE_PRODUCERS.conflict_decision,
    detail: decisionDetailLines(resolution),
    runId: resolution.run_id ?? (runNodeId ? (b.nodes.get(runNodeId)?.runId ?? null) : null),
    parentId,
  });
}

/**
 * A recorded decision whose address carries NO conflict on this subject.
 *
 * It is drawn rather than dropped for the reason the server reports it rather than
 * omitting it: a decision is a recorded human act, and a surface that showed only
 * decisions attached to live conflicts would make one silently disappear the
 * moment the disagreement it settled stopped being one — including when the run it
 * belonged to was removed.
 *
 * BOUNDED BY {@link MAX_GRAPH_CONFLICTS}, LIKE THE CONFLICTS BESIDE IT — and this
 * was the one list on this route that had no bound at all.
 *
 * `resolutions_without_conflict[]` is a second unbounded array in the SAME
 * response as `conflicts[]`, and it grows monotonically: a decision is never
 * deleted, so every address whose disagreement was settled, and every decision
 * belonging to a removed run, lands here forever. Leaning on the shared node cap
 * for it was exactly the silent truncation the per-source bounds exist to end —
 * measured at 2,000 orphans, the cap filled with decisions, the notes and asset
 * references read afterwards drew NOTHING, and the only disclosure was the generic
 * `node_cap` note, which names no source. The bound is `MAX_GRAPH_CONFLICTS`
 * rather than a sixth constant because these come from the same route and are the
 * same family of thing — a recorded disagreement — and a reader meets them under
 * one heading; the withholding is disclosed as its own clause so the two are never
 * confusable.
 */
function addOrphanDecisions(
  b: Builder,
  ctx: ExtraSourceContext,
  orphans: readonly ApiResolutionWithoutConflict[],
): void {
  // Sorted by resolution id, so the cut is stable rather than "whatever the
  // response happened to list first".
  const ordered = [...orphans].sort((x, y) => byIdAsc(x.resolution_id, y.resolution_id));
  const drawn = ordered.slice(0, MAX_GRAPH_CONFLICTS);
  if (ordered.length > drawn.length) {
    ctx.ledger.bounded.push(
      `${ordered.length - drawn.length} of ${ordered.length} recorded decision(s) whose address carries no conflict now — the first ${MAX_GRAPH_CONFLICTS} by decision id are drawn`,
    );
  }
  for (const orphan of drawn) {
    const id = b.addNode({
      id: nodeIds.decision(orphan.resolution_id),
      kind: 'conflict_decision',
      label: `${orphan.outcome === 'deferred' ? 'Deferred' : 'Decision'} — no conflict here now`,
      producer: NODE_PRODUCERS.conflict_decision,
      detail: [
        { term: 'Address', value: orphan.address },
        { term: 'Outcome', value: orphan.outcome },
        {
          term: 'Why this is here',
          value: orphan.orphaned_run
            ? 'This decision belongs to a run that has since been removed from the record. It is a recorded human act, so it is shown rather than dropped, and the run it was about no longer exists.'
            : 'A decision is on record at this address, and the address carries no conflict on this subject now. It is shown rather than dropped, because a decision is a recorded human act.',
        },
        {
          term: 'Run',
          value: orphan.run_id
            ? (ctx.runLabelByRunId.get(orphan.run_id) ??
              `${orphan.run_id} — this run is not on the page of runs loaded here`)
            : "the record's own fields",
        },
        {
          term: 'Not the value, not a citation',
          value:
            'Recording a decision changes no scientific content. This is not the field’s value and not an evidence entry.',
        },
      ],
      runId: null,
      parentId: ctx.rootId,
    });
    if (!id) continue;
    b.addEdge({
      source: ctx.rootId,
      target: id,
      kind: 'has_decision',
      producer: EDGE_PRODUCERS.has_decision[1],
      why: `The server lists a recorded decision at ${orphan.address} that this subject carries no conflict at${orphan.orphaned_run ? ', and the run it belongs to has been removed from the record' : ''}. It is reported rather than dropped.`,
      label: orphan.outcome,
      containment: true,
    });
  }
}

/**
 * Captured text with no schema home, from `GET .../notes`.
 *
 * A note is NOT evidence and NOT a field value — `ApiNote` carries all three of
 * `is_evidence`, `is_field_value` and `verified` as the literal `false`, and this
 * module states that on every note rather than relying on the kind's name.
 */
function addNotes(b: Builder, ctx: ExtraSourceContext, res: ApiNotesResponse): void {
  if (res.unreadable_entries > 0) {
    ctx.ledger.unreadable.push({ source: 'captured notes', count: res.unreadable_entries });
  }

  /*
   * SORTED HERE RATHER THAN TRUSTED. The server sorts, but the CUT below depends
   * on the order, so the order is stated rather than assumed: capture time, then
   * id for two notes captured in the same instant.
   */
  const ordered = [...(res.notes ?? [])].sort(
    (x, y) => byIdAsc(x.captured_utc, y.captured_utc) || byIdAsc(x.id, y.id),
  );
  const drawn = ordered.slice(0, MAX_GRAPH_NOTES);
  if (ordered.length > drawn.length) {
    ctx.ledger.bounded.push(
      `${ordered.length - drawn.length} of ${ordered.length} captured note(s) — the ${MAX_GRAPH_NOTES} captured earliest are drawn`,
    );
  }

  for (const note of drawn) {
    const runNodeId = note.run_id ? ctx.runNodeByRunId.get(note.run_id) : undefined;
    const parentId = runNodeId ?? ctx.rootId;
    const id = addNoteNode(b, ctx, note, parentId, runNodeId ? note.run_id : null);
    if (!id) continue;

    b.addEdge({
      source: parentId,
      target: id,
      kind: 'has_note',
      producer: runNodeId ? EDGE_PRODUCERS.has_note[0] : EDGE_PRODUCERS.has_note[1],
      why: runNodeId
        ? `This note was captured against this run (notes[].run_id === ${note.run_id}).`
        : note.run_id
          ? `This note names run ${note.run_id}, which is not on the page of runs loaded here, so it is shown under the experiment rather than attached to a run that is not drawn.`
          : 'This note was captured against the record as a whole — it names no run, and none is inferred for it.',
      label: note.state,
      containment: true,
    });

    // The path a PERSON named. See `EDGE_PRODUCERS.mapped_to` for why the
    // machine's proposal is deliberately not drawn as a relationship.
    if (note.mapped_field_path) {
      const target =
        ctx.groupNodeFor(parentId, note.mapped_field_path) ??
        ctx.groupNodeFor(ctx.rootId, note.mapped_field_path);
      if (target) {
        b.addEdge({
          source: id,
          target,
          kind: 'mapped_to',
          producer: EDGE_PRODUCERS.mapped_to[0],
          why: `Somebody said this note belongs at ${note.mapped_field_path}. Mapping records a target; it writes no value, mints no evidence and confirms nothing.`,
          label: 'mapped',
          containment: false,
        });
      }
    }
  }
}

function addNoteNode(
  b: Builder,
  ctx: ExtraSourceContext,
  note: ApiNote,
  parentId: string,
  runId: string | null,
): string | null {
  const detail: EvidenceGraphDetailLine[] = [
    { term: 'Captured text', value: note.display_text },
  ];
  /*
   * THE VERBATIM CAPTURE SURVIVES A CORRECTION. `revised_text` is stored BESIDE
   * `text`, never replacing it, so when the two differ both are shown — showing
   * only the corrected wording would quietly lose what was actually captured.
   */
  if (note.revised_text !== null && note.revised_text !== note.text) {
    detail.push({ term: 'As originally captured', value: note.text });
  }
  detail.push(
    { term: 'Source', value: note.source },
    { term: 'Captured', value: note.captured_utc },
    { term: 'Review state', value: note.state },
    {
      term: 'Run',
      value: runId
        ? (ctx.runLabelByRunId.get(runId) ?? runId)
        : note.run_id
          ? `${note.run_id} — this run is not on the page of runs loaded here`
          : 'no run — this note is about the record as a whole, and none is inferred',
    },
  );
  if (note.mapped_field_path) {
    detail.push({
      term: 'Placed by a person at',
      value: `${note.mapped_field_path} — somebody said it belongs there. That records a target; it writes no value and confirms nothing.`,
    });
  } else {
    detail.push({
      term: 'Placed at',
      value: 'nowhere yet — nothing has said where this belongs, and no home is guessed for it.',
    });
  }
  if (note.candidate_field_path) {
    /*
     * A PROPOSAL, AND SAID TO BE ONE. `notes.py` keeps `candidate_field_path` and
     * `mapped_field_path` apart precisely so a suggestion is never
     * indistinguishable from a decision, which is why this is a detail line and
     * NOT a `mapped_to` edge: on a graph, a line reads as a fact.
     */
    detail.push({
      term: 'Proposed home (nobody has accepted this)',
      value: note.candidate_rule
        ? `${note.candidate_field_path} — proposed by the rule "${note.candidate_rule}". A proposal, not a decision; no line is drawn for it.`
        : `${note.candidate_field_path} — proposed deterministically, with no rule text stored. A proposal, not a decision; no line is drawn for it.`,
    });
  }
  detail.push(
    { term: 'Times acted on', value: String(note.history.length) },
    {
      term: 'What this is not',
      value:
        'A note is not evidence, not a field value and not verified — the record stores all three as false. Turning prose into a value means deciding what the value is, and nothing here does that.',
    },
  );

  return b.addNode({
    id: nodeIds.note(note.id),
    kind: 'note',
    label: shortLabel(note.display_text, 44),
    producer: NODE_PRODUCERS.note,
    detail,
    runId,
    parentId,
  });
}

/**
 * The asset LIBRARY, from `GET .../assets` — which is a different set from the
 * `assets*` ADDRESSES the existing `asset` nodes are built from.
 *
 * The two are deliberately NOT joined. A library entry has an `asset_id`; an
 * address has an array index; and matching one to the other would be a guess about
 * ordering that nothing in the response supports. So a shared asset appears once,
 * under the experiment, with an explicit line to every run that uses it.
 */
function addAssetReferences(
  b: Builder,
  ctx: ExtraSourceContext,
  res: ApiAssetsResponse,
): void {
  if (res.unreadable_entries > 0) {
    ctx.ledger.unreadable.push({ source: 'asset references', count: res.unreadable_entries });
  }
  const ordered = [...(res.assets ?? [])].sort((x, y) => byIdAsc(x.asset_id, y.asset_id));
  const drawn = ordered.slice(0, MAX_GRAPH_ASSET_REFS);
  if (ordered.length > drawn.length) {
    ctx.ledger.bounded.push(
      `${ordered.length - drawn.length} of ${ordered.length} asset reference(s) — the first ${MAX_GRAPH_ASSET_REFS} by asset id are drawn`,
    );
  }

  for (const asset of drawn) {
    const id = b.addNode({
      id: nodeIds.assetReference(asset.asset_id),
      kind: 'asset_reference',
      label: shortLabel(asset.uri, 40),
      producer: NODE_PRODUCERS.asset_reference,
      detail: assetDetailLines(asset, ctx),
      // Library-level: it can be used by several runs, so it belongs to none.
      runId: null,
      parentId: ctx.rootId,
    });
    if (!id) continue;
    b.addEdge({
      source: ctx.rootId,
      target: id,
      kind: 'references',
      producer: EDGE_PRODUCERS.references[1],
      why: `This record's asset library holds a reference to ${asset.uri}.`,
      label: asset.content_role,
      containment: true,
    });
    for (const use of asset.used_by_runs) {
      const runNode = ctx.runNodeByRunId.get(use.run_id);
      if (!runNode) continue;
      b.addEdge({
        source: runNode,
        target: id,
        kind: 'references',
        producer: EDGE_PRODUCERS.references[2],
        why: `The server lists this run in used_by_runs for this asset reference, so this run's exported record carries it.`,
        label: null,
        containment: false,
      });
    }
  }
}

function assetDetailLines(
  asset: ApiAsset,
  ctx: ExtraSourceContext,
): EvidenceGraphDetailLine[] {
  const lines: EvidenceGraphDetailLine[] = [
    { term: 'Asset id', value: asset.asset_id },
    { term: 'URI', value: asset.uri },
    { term: 'Content role', value: asset.content_role },
  ];
  if (asset.media_type) lines.push({ term: 'Media type', value: asset.media_type });
  /*
   * A STATEMENT ABOUT THE STRING, NOT ABOUT THE FILE. `sha256_wellformed` is named
   * for exactly what it measures; nothing in this application has opened the file
   * at the URI, and no surface may let this read as a verification result.
   */
  lines.push({
    term: 'Digest as supplied',
    value: asset.sha256
      ? `${asset.sha256} — ${asset.sha256_wellformed ? 'this is 64 lowercase hexadecimal characters' : 'this is NOT 64 lowercase hexadecimal characters'}. Nothing here has opened the file, so this says nothing about what the file contains.`
      : 'no digest was supplied, and none is computed or repaired here',
  });
  lines.push({ term: 'Citations recorded on it', value: String(asset.evidence_count) });
  lines.push({
    term: 'Used by',
    value:
      asset.used_by_runs.length === 0
        ? 'no run'
        : asset.used_by_runs
            .map((u) => ctx.runLabelByRunId.get(u.run_id) ?? u.label ?? u.run_id)
            .join(', '),
  });
  /*
   * `none` IS THE VALUE THAT MUST NEVER BE HIDDEN. An experiment that has runs
   * exports one record per run, composed from that run's blocks, and `assets` is
   * run-level — so a library entry associated with no run reaches no exported
   * record at all. A scientist who recorded a file and saw it listed would
   * otherwise never find out.
   */
  lines.push({
    term: 'Reaches an exported record',
    value:
      asset.export_reach === 'none'
        ? 'NO — this reference is associated with no run, and assets are run-level, so no exported record carries it.'
        : asset.export_reach === 'runs'
          ? 'Yes — through the runs it is associated with.'
          : 'Yes — through the record itself.',
  });
  if (asset.notes) lines.push({ term: 'Notes recorded on it', value: asset.notes });
  return lines;
}

/**
 * The two provenance dimensions, applied to the nodes that ALREADY exist.
 *
 * NO NODE IS CREATED HERE, and that is the design rather than a shortcut. This
 * route answers a question ABOUT an address — where the value came from, and what
 * establishes it — and this view already draws a node per address GROUP. Minting a
 * node per address would multiply the graph by the size of the draft to say two
 * words about each one, and would put a second, differently-shaped representation
 * of the same addresses beside the first.
 *
 * Origins are rendered by LOOKUP only — see {@link originLabel}.
 */
function applyProvenance(
  b: Builder,
  ctx: ExtraSourceContext,
  res: ApiProvenanceResponse,
): void {
  let unplaced = 0;
  for (const entry of [...(res.entries ?? [])].sort((x, y) => byIdAsc(x.address, y.address))) {
    // A note entry (`note:<id>`) is a note, and notes are drawn from the notes
    // route — which lists every note, not only the unreviewed ones this route
    // describes. Describing them twice would give one note two representations.
    if (entry.address.startsWith('note:')) continue;
    const target = ctx.groupNodeFor(ctx.rootId, entry.address);
    if (!target) {
      unplaced += 1;
      continue;
    }
    const node = b.nodes.get(target);
    if (!node) {
      unplaced += 1;
      continue;
    }
    const others = entry.origins.filter((o) => o !== entry.primary_origin);
    pushUnique(node, {
      term: `Where this came from · ${entry.address}`,
      value:
        others.length === 0
          ? originLabel(entry.primary_origin)
          : `${originLabel(entry.primary_origin)} (also: ${others.map(originLabel).join(', ')})`,
    });
    pushUnique(node, {
      term: `Review state · ${entry.address}`,
      value: `${reviewStateLabel(entry.review_state)}. Where a value came from says nothing about whether it is backed — these are two separate answers, and neither is a validity or export verdict.`,
    });
    if (entry.unavailable) {
      pushUnique(node, {
        term: `Partly unreadable · ${entry.address}`,
        value:
          'Some of the stored payload at this address could not be read, so it is not presented as plain support.',
      });
    }
  }

  const root = b.nodes.get(ctx.rootId);
  if (root && res.notes_summary) {
    pushUnique(root, {
      term: 'Notes on this record',
      value: `${res.notes_summary.total} captured, of which ${res.notes_summary.listed_as_unmapped} are still unreviewed.`,
    });
  }

  const blocks = res.blocks_not_described ?? [];
  if (blocks.length > 0 || unplaced > 0) {
    const parts: string[] = [];
    if (blocks.length > 0) {
      parts.push(
        `The server itself did not describe ${blocks.length} part(s) of this record, because they carry no value envelope to describe: ${blocks.join(', ')}.`,
      );
    }
    if (unplaced > 0) {
      parts.push(
        `${unplaced} described address(es) belong to a part of the record this view does not draw, so their origin and review state are not shown here.`,
      );
    }
    b.note(
      'provenance_undescribed',
      `Where each value came from, and what establishes it, is shown on the node that owns the address. ${parts.join(' ')} They are counted rather than hidden.`,
    );
  }
}

/** Append a detail line unless the node already carries exactly it. */
function pushUnique(node: EvidenceGraphNode, line: EvidenceGraphDetailLine): void {
  if (node.detail.some((l) => l.term === line.term && l.value === line.value)) return;
  node.detail.push(line);
}

/**
 * WHAT IS HISTORICAL VERSUS CURRENT — answered as a STATEMENT, not as nodes.
 *
 * No historical revision is drawn, and the omission is the honest answer rather
 * than an unfinished one. This graph draws the record as it is NOW: every node
 * above comes from the current draft, and a superseded value drawn beside a
 * current one — in a picture whose whole grammar is "these things are related" —
 * would read as something the record still holds. A history is a second model with
 * a second time axis, not a layer over this one.
 *
 * So the route is read for exactly one question: is the content drawn here on
 * record as a revision, or has the draft moved since the last one? Three answers,
 * and the third is "not known from this page", because the revision list is
 * BOUNDED and a signature absent from the page read is not a signature that does
 * not exist.
 */
function applyRevisions(
  b: Builder,
  ctx: ExtraSourceContext,
  res: ApiRevisionHistory,
): void {
  const root = b.nodes.get(ctx.rootId);
  if (res.availability.state !== 'available') {
    // The server's own sentence, verbatim. It knows why; this module does not.
    b.note(
      'revision_state',
      `Whether the content drawn here is on record as a revision could not be established: ${res.availability.message} Nothing historical is drawn either way — this graph draws the record as it is now.`,
    );
    return;
  }

  const revisions = [...(res.revisions ?? [])].sort((x, y) => y.revision_no - x.revision_no);
  const total = res.total ?? revisions.length;
  const returned = res.returned ?? revisions.length;
  const match = revisions.find((r) => r.content_signature === res.current_content_signature);
  const latest = revisions[0];

  if (root) {
    pushUnique(root, { term: 'Recorded revisions', value: String(total) });
    pushUnique(root, { term: 'Lifecycle', value: res.lifecycle.label });
    if (latest) {
      const changes = Object.entries(latest.change_counts)
        .sort((x, y) => byIdAsc(x[0], y[0]))
        .map(([kind, n]) => `${n} ${kind}`)
        .join(', ');
      pushUnique(root, {
        term: `Revision ${latest.revision_no} recorded these changes`,
        value: changes === '' ? 'no address-level change was recorded' : changes,
      });
    }
  }

  if (match) {
    b.note(
      'revision_state',
      `Everything drawn here is the record's CURRENT content, and that content is on record as revision ${match.revision_no} of ${total}. No earlier revision is drawn: this graph draws the record as it is now, and a superseded value shown beside a current one would read as one the record still holds.`,
    );
    return;
  }
  /*
   * ZERO IS ITS OWN ANSWER, not the tail of the one below it. With no revisions at
   * all there is no "last one" for the draft to have changed since, and the
   * sentence below would have asserted a history this record does not have.
   */
  if (total === 0) {
    b.note(
      'revision_state',
      "Everything drawn here is the record's CURRENT content, and no revision of it has been recorded yet. Nothing historical exists to draw.",
    );
    return;
  }
  if (returned >= total) {
    b.note(
      'revision_state',
      `Everything drawn here is the record's CURRENT content, and it matches none of the ${total} recorded revision(s) — the draft has changed since the last one was recorded. No earlier revision is drawn.`,
    );
    return;
  }
  b.note(
    'revision_state',
    `Everything drawn here is the record's CURRENT content. ${total} revision(s) are recorded and ${returned} were read; none of those ${returned} matches this content. Whether an unread revision does is not known from this page, so it is not stated. No earlier revision is drawn.`,
  );
}

/** The four composed sub-fetch notes, emitted once each at the very end. */
function emitLedgerNotes(b: Builder, ledger: SubFetchLedger): void {
  if (ledger.failed.length > 0 || ledger.loading.length > 0) {
    const parts: string[] = [];
    for (const f of ledger.failed) {
      parts.push(`${f.source} could not be read (${f.message})`);
    }
    /*
     * PHRASED WITHOUT A VERB. `${list} has/have not been read` needs to agree with
     * a list of PROPER NAMES ("Notes", "Asset references"), and no choice of verb
     * is right for both — "Notes has not been read yet" is what the singular arm
     * produced, about a source whose name is plural.
     */
    if (ledger.loading.length > 0) {
      parts.push(`not read yet: ${ledger.loading.join(', ')}`);
    }
    b.note(
      'sub_fetch_unavailable',
      `${parts.join('; ')}. Nothing from those sources is drawn, and an empty space where they would be is NOT a statement that this record has none.`,
    );
  }

  if (ledger.stale.length > 0 || ledger.unknownFreshness.length > 0) {
    const parts: string[] = [];
    for (const s of ledger.stale) {
      parts.push(
        `${s.source} was read at version ${s.reported}, and this record is at ${s.expected}`,
      );
    }
    if (ledger.unknownFreshness.length > 0) {
      parts.push(
        `${ledger.unknownFreshness.join(', ')} reported no version, so ${ledger.unknownFreshness.length === 1 ? 'it cannot be' : 'they cannot be'} shown to describe this version of the record`,
      );
    }
    b.note(
      'sub_fetch_stale',
      `${parts.join('; ')}. What those sources contributed is drawn, and it describes a different read of this record — a re-read has not landed since.`,
    );
  }

  if (ledger.unreadable.length > 0) {
    b.note(
      'unreadable_entries',
      `${ledger.unreadable
        .map((u) => `${u.count} ${u.source}`)
        .join(', ')} could not be read from the stored record, so they are not drawn. They are preserved in the record and counted here, because saying what one contains would mean inventing it.`,
    );
  }

  if (ledger.bounded.length > 0) {
    b.note(
      'source_bounded',
      `This view is bounded, and these were withheld rather than silently dropped: ${ledger.bounded.join('; ')}. Open the record's own sections to see them all.`,
    );
  }
}

// ------------------------------------------------------------------ the builder

class Builder {
  readonly nodes = new Map<string, EvidenceGraphNode>();
  readonly edges: EvidenceGraphEdge[] = [];
  private readonly edgeSeen = new Set<string>();
  readonly notes: EvidenceGraphNote[] = [];
  truncated = false;

  /**
   * A node is kept ONLY when its producer is THE declared producer for its kind.
   *
   * Symmetric with {@link addEdge}, and added because the asymmetry was real: for
   * a long while only edges were checked, so a node could carry any string at all
   * and the test that was supposed to catch it asserted only that the string was
   * non-empty. `producer` is the answer a reader gets when they ask "where did
   * this come from?", and a wrong answer there is worse than no node.
   *
   * Unlike edges, a kind has exactly ONE node producer, so this is an equality
   * rather than a membership test — `NODE_PRODUCERS` is a `Record`, not a
   * `Record` of arrays, and that shape is the reason.
   */
  addNode(node: EvidenceGraphNode): string | null {
    if (node.producer !== NODE_PRODUCERS[node.kind]) return null;
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
  /**
   * address → WHAT THE SERVER RECORDED THERE, before this module narrowed
   * anything: how many items its `evidence` array carries, and whether it flagged
   * the entry `unavailable`.
   *
   * Kept separate from `experimentEntriesByAddress` on purpose. That map holds the
   * nodes actually BUILT, which is a smaller set whenever an item could not be
   * narrowed or the node cap bit. Step 6 needs both, and needs them not to be
   * confusable: the count it may quote is this one, and the SIZE MATCH between the
   * two is the condition for drawing a pair at all.
   */
  const experimentRecordedByAddress = new Map<string, { count: number; unavailable: boolean }>();

  for (const entry of [...evidence].sort((x, y) => byIdAsc(x.path, y.path))) {
    const groupId = ensureGroup(
      rootId,
      null,
      entry.path,
      'This experiment records evidence at addresses in this part of the record.',
    );
    // Recorded BEFORE the `unavailable` early-return and before any narrowing, so
    // it describes the server's entry rather than this build's success with it.
    experimentRecordedByAddress.set(entry.path, {
      count: (entry.evidence ?? []).length,
      unavailable: entry.unavailable === true,
    });
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
  /*
   * The runs actually LOADED, indexed. Every source below that names a run looks
   * it up HERE and never assumes the name resolves: the run page is bounded, so a
   * note or a decision can legitimately name a run this graph is not drawing, and
   * the honest answer is to say which run rather than to hang the node off
   * whichever run happens to be on screen.
   */
  const runNodeByRunId = new Map<string, string>();
  const runLabelByRunId = new Map<string, string>();
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
    runNodeByRunId.set(run.id, added);
    runLabelByRunId.set(run.id, run.label || `Run ${run.ordinal}`);
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
    /*
     * "load more to extend it" USED TO END THIS SENTENCE, AND THERE IS NOTHING TO
     * PRESS. This view fetches one fixed page and offers no page control of its
     * own; the Runs section's Load More pages the Runs section, not this graph.
     * An instruction a reader cannot act on is worse than the bound it apologises
     * for, so the sentence now states the bound and stops.
     */
    b.note(
      'runs_bounded',
      `${runsMeta.returned} of ${runsMeta.matched} matching run(s) are loaded (${runsMeta.total} exist in this record). The graph draws this one page and never fetches every run to draw it. It has no page control of its own, and the runs beyond this page are not drawn here — open the record's Runs section to browse them.`,
    );
  }
  b.note(
    'checks_on_demand',
    'Validation findings are read per run, when you open that run. A run you have not opened shows no findings because none have been read — not because it has none.',
  );

  // ── 6. conflicts, from the server's OWN classification ────────────────────
  //
  // The ONLY source for a `conflicts_with` edge, and TWO conditions must both
  // hold before one is drawn:
  //
  //   (a) the SERVER recorded exactly two entries at the classified address —
  //       because with three or more, the stored state says THAT they conflict
  //       and not WHICH PAIR does;
  //   (b) this build drew BOTH of them, i.e. nothing was dropped on the way.
  //
  // (b) is not redundant, and leaving it out was a real defect rather than a
  // theoretical one. `attachEvidence` drops an item `readEvidenceItem` cannot
  // narrow and an item the node cap refuses; the classifier that produced
  // `conflicting_evidence` did neither. Three stored entries with one unreadable
  // here therefore leave a surviving set of two, and joining those two would
  // pick a pair by ARRAY POSITION out of three and then state, in `why`, that
  // "exactly two entries are recorded there" — a count from the wrong set, in
  // the sentence a reader would use to check the claim.
  //
  // So the count is read off the server's own `ApiEvidenceEntry` (never off
  // `entries`, which is post-narrowing), and any mismatch takes the same honest
  // route the `> 2` case already took: say it in the details, note it, draw
  // nothing.
  for (const result of classification.field_results ?? []) {
    if (result.classification !== 'conflicting_evidence') continue;
    const entries = experimentEntriesByAddress.get(result.field) ?? [];
    const groupId = experimentGroupByAddress.get(result.field);
    const recorded = experimentRecordedByAddress.get(result.field);
    // The classification names an address the trail does not hold at all. There
    // is nothing to join and no count to state, so nothing is said beyond this.
    if (!recorded) continue;
    const node = groupId ? b.nodes.get(groupId) : undefined;

    const drewEveryRecordedEntry = !recorded.unavailable && entries.length === recorded.count;

    if (recorded.count === 2 && drewEveryRecordedEntry) {
      b.addEdge({
        source: entries[0],
        target: entries[1],
        kind: 'conflicts_with',
        producer: EDGE_PRODUCERS.conflicts_with[0],
        why: `The evidence-support classification for ${result.field} is \`conflicting_evidence\` — ${result.explanation} The server records exactly two entries there and both are drawn, so the disagreement is between these two. No winner is picked.`,
        label: 'conflicting_evidence',
        containment: false,
      });
    } else if (recorded.count > 2) {
      node?.detail.push({
        term: `Conflicting evidence · ${result.field}`,
        value: `The server records ${recorded.count} entries here and classifies them \`conflicting_evidence\`. Which pair disagrees is not recorded, so no pair is drawn.`,
      });
      b.note('conflict_pair_unknown', CONFLICT_PAIR_UNKNOWN_NOTE);
    } else if (!drewEveryRecordedEntry) {
      // recorded.count is 0, 1 or 2, and the surviving set does not match it.
      // The commonest shape is two recorded entries of which one could not be
      // read — where a naive pairwise join would have had exactly one endpoint.
      node?.detail.push({
        term: `Conflicting evidence · ${result.field}`,
        value: `The server records ${recorded.count} entr${recorded.count === 1 ? 'y' : 'ies'} here and classifies them \`conflicting_evidence\`, but ${
          recorded.unavailable
            ? 'it reported the stored evidence as unreadable'
            : `only ${entries.length} of them could be read here`
        }. A conflict line drawn from an incomplete set would name a pair the record does not, so none is drawn.`,
      });
      b.note('conflict_pair_unknown', CONFLICT_PAIR_UNKNOWN_NOTE);
    }
  }

  // ── 7. the four routes beyond the bundle ──────────────────────────────────
  //
  // Ordered AFTER the runs deliberately. Every one of these is bounded by its own
  // constant, but the global node cap is shared, and the spine of this graph —
  // the experiment, its runs and what they carry — must not be displaced by a
  // record that happens to hold a great many notes.
  const ledger = emptyLedger();
  const extras: ExtraSourceContext = {
    rootId,
    groupNodeFor: (ownerId, address) => {
      const group = groupForAddress(address);
      if (!group) return undefined;
      return ownerGroups.get(ownerId)?.byItem.get(`${group.kind}/${group.itemKey}`);
    },
    runNodeByRunId,
    runLabelByRunId,
    ledger,
  };

  /*
   * THE NAMES A READER SEES ARE PRODUCT WORDS, NOT WIRE SEGMENTS — the same words
   * `components/FetchStates.tsx`'s `SUB_RESOURCE_LABELS` uses for a failed read of
   * the very same routes, so a reader who meets both surfaces meets one vocabulary.
   * "Conflicts", "Notes" and "Provenance" are path segments; `CLAUDE.md` §11 records
   * backend-sourced jargon on product screens as an open defect class, and a note
   * that names a route is exactly that.
   */
  const conflictsRes = readSubFetch('The conflicting evidence', input.conflicts, ledger, {
    expected: detail.version,
    reported: (d) => d.experiment_version,
  });
  if (conflictsRes) {
    addConflicts(b, extras, conflictsRes);
    /*
     * SAID WHENEVER CONFLICTS WERE READ AT ALL, not only when the record has some.
     * `GET .../conflicts` takes an optional `?run=` and this view asks WITHOUT it,
     * so what is drawn is the record's own fields; a per-run answer would be one
     * request per run, which is exactly the unbounded read the bounded run page
     * exists to prevent. A reader who is not told this would read "no conflict on
     * Run 2" off a graph that never asked about Run 2.
     *
     * GUARDED ON THE RESPONSE'S OWN `run_id`, not on what this view asked for. The
     * sentence is true of what this view does — but a caller handing in a
     * run-scoped response would otherwise have the claim printed over it, which is
     * the same class of defect as printing a version a fetch did not read.
     */
    if (conflictsRes.run_id === null) {
      b.note(
        'conflicts_record_scope',
        "Conflicting evidence is read for the record's own fields, in one request. This view does not ask per run — that would be one request per run — so a run that stores its own value at an address is not described here. Open that run's own evidence to see it.",
      );
    }
  }

  const notesRes = readSubFetch('The unmapped notes', input.notes, ledger, {
    expected: detail.version,
    reported: (d) => d.experiment_version,
  });
  if (notesRes) addNotes(b, extras, notesRes);

  const assetsRes = readSubFetch('The asset references', input.assets, ledger, {
    expected: detail.version,
    reported: (d) => d.experiment_version,
  });
  if (assetsRes) addAssetReferences(b, extras, assetsRes);

  /*
   * `record_rev` RATHER THAN `experiment_version`, because that is the token this
   * route publishes. `detail.rev` is the same number from the same document, so
   * the comparison stays a version-token comparison rather than becoming a second
   * freshness mechanism — see `subFetchFreshness`.
   */
  const provenanceRes = readSubFetch('Where the values came from', input.provenance, ledger, {
    expected: revToken(detail.rev),
    reported: (d) => revToken(d.record_rev),
  });
  if (provenanceRes) applyProvenance(b, extras, provenanceRes);

  const revisionsRes = readSubFetch('The submission history', input.revisions, ledger, {
    expected: revToken(detail.rev),
    reported: (d) => revToken(d.record_rev),
  });
  if (revisionsRes) applyRevisions(b, extras, revisionsRes);

  emitLedgerNotes(b, ledger);

  if (b.truncated) {
    b.note(
      'node_cap',
      `This experiment produced more than ${MAX_EVIDENCE_GRAPH_NODES} nodes, so the graph is incomplete. It is bounded rather than partial-and-silent.`,
    );
  }

  // ── 8. focus ──────────────────────────────────────────────────────────────
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

/**
 * The three finding channels of `POST …/runs/{id}/check`, in render order.
 *
 * IT CARRIES NO LABEL FOR THE `official` CHANNEL, AND THAT IS THE FIX. It used to
 * be `{ key: 'official', label: 'Official schema check' }` — a CONSTANT, with no
 * `dry_run` branch anywhere — so every element of `check.official.errors` became a
 * graph node, a `Reported by` line and an edge label attributing it to the official
 * ISAAC schema. On a dry run that attribution is unsupported: `_validate_unit`
 * returns `export_draft`'s result, and `export.py` returns `official_report=None`
 * on two paths BEFORE `validate_official` is called — a failed no-guessing report
 * (`export.py:305`) and a failed anchored-pattern EXACTNESS gate, whose findings it
 * folds into `draft_report` (`export.py:339-343`) — after which `_validate_unit`
 * falls back to `draft_report.errors` and `post_run_check` stamps
 * `official["schema"] = "ISAAC v1.05"` over them. Measured over HTTP on a run whose
 * descriptor name carries a trailing newline, `official.errors[0].message` was the
 * exactness gate's own text, `draft.errors` was empty, and this module labelled the
 * node "Official schema check".
 *
 * `CLAUDE.md` §12: "the gate is ISAAC's, not upstream's — §1 makes the schema not
 * ours to speak for, so no surface may report an exactness refusal as an
 * official-schema error." A graph node is such a surface, and it was the ONE
 * consumer of this payload with no `dry_run` branch at all — `ValidateReview` and
 * (since this change) `RunCard` both had one.
 *
 * The list keeps its keys, its order and its two sound labels; the official label
 * is derived where the node is actually built, by `findingOriginLabel`.
 */
const FINDING_ORIGINS = [
  { key: 'blocker' },
  { key: 'draft' },
  { key: 'official' },
] as const;

/**
 * What a finding of one channel is CALLED. The `official` channel's answer is the
 * shared module's, not this file's.
 *
 * IT USED TO BE A CONSTANT — `{ key: 'official', label: 'Official schema check' }`,
 * with no branch anywhere — so every element of `check.official.errors` became a
 * graph node, a `Reported by` line and an edge label attributing it to the official
 * ISAAC schema. On a dry run that attribution is unsupported: `export.py` returns
 * `official_report=None` on two paths BEFORE `validate_official` is called, and
 * `post_run_check` stamps `official["schema"] = "ISAAC v1.05"` over the result.
 * Measured over HTTP on a run whose descriptor name carries a trailing newline,
 * `official.errors[0].message` was the exactness gate's own text, `draft.errors` was
 * empty, and this module labelled the node "Official schema check". `CLAUDE.md` §12:
 * no surface may report an exactness refusal as an official-schema error.
 *
 * THE FIRST FIX WAS ALSO WRONG, in the branch it added: it read `dry_run` before
 * `unavailable`, and `_validate_unit`'s materialised-unreadable return carries
 * `dry_run: false` WITH `unavailable: true` — so every node and edge read "Official
 * schema check on Run 1 …: Validation could not be completed.", the server's refusal
 * to give a verdict rendered as the official schema having given one.
 *
 * NEITHER OF THOSE IS DERIVABLE HERE ANY MORE. `officialFindingSource` answers it
 * from the server's own `official_validator_ran`, tests `unavailable` first, and owns
 * the wording — so a graph node, a card heading and a screen headline cannot disagree
 * about the same payload, which is what four separate ladders guaranteed they could.
 * The `blocker` and `draft` labels stay local: those two channels have one producer
 * each and never carried a claim about the schema.
 */
function findingOriginLabel(
  key: (typeof FINDING_ORIGINS)[number]['key'],
  official: ApiRunCheckResponse['official'] | undefined,
): string {
  if (key === 'blocker') return 'Blocker';
  if (key === 'draft') return 'Draft check';
  return OFFICIAL_SOURCE_LABEL[officialFindingSource(official)];
}

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
    // Derived per channel, from the SAME response the findings came from, so a
    // dry-run finding can never be attributed to the official schema — and a
    // NO-VERDICT unit can never be attributed to any validator. See
    // `findingOriginLabel`.
    const originLabel = findingOriginLabel(origin.key, check.official);
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
        { term: 'Reported by', value: originLabel },
        { term: 'Finding', value: text },
        { term: 'Run', value: run.label || `Run ${run.ordinal}` },
        { term: 'Run version checked', value: check.checked_run_version },
      ];
      if (path) detail.push({ term: 'Path', value: path });
      if (origin.key === 'official') {
        detail.push({
          /* WHICH DOCUMENT — a different question from WHO produced the findings, and
             `officialCheckedDocument` is the only thing that answers it. It returns
             `null` for a no-verdict unit, because `unavailable` carries `dry_run:
             false` and reading that as "the record already written was checked" states
             the one thing the server explicitly could not do: it set the flag BECAUSE
             the written record could not be read. Rendering the corrected label above
             while this line kept the old reading would put the contradiction back on
             the same pane, one row down. */
          term: 'Dry run',
          value: officialDocumentDetailValue(
            officialFindingSource(check.official),
            officialCheckedDocument(check.official),
          ),
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
        why: `${originLabel} on ${run.label || `Run ${run.ordinal}`} (run version ${check.checked_run_version}): ${text}${path ? ` — reported at ${path}` : ''}`,
        label: originLabel,
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

/**
 * The user-space rectangle a viewport actually SHOWS, in numbers.
 *
 * `viewBoxFor` already computes this and formats it as the SVG `viewBox`
 * attribute; a renderer that needs to know whether something falls off the
 * canvas needs the same four numbers un-stringified. The two are pinned to each
 * other by a test rather than kept in step by hand — `viewBoxFor(v, b)` must be
 * this rect's four fields, space-joined, for every viewport.
 *
 * It is NOT put next to `viewBoxFor` in `experimentGraph.ts` on purpose: the
 * Project Memory and record-detail canvases render from that module, and the
 * label bounding this feeds is an evidence-graph fix. A shared edit there would
 * move surfaces this slice has not measured.
 */
export interface ViewportRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The rectangle `viewBoxFor(view, box)` describes. */
export function viewRectFor(view: GraphViewport, box: ViewportBox): ViewportRect {
  const width = box.width / view.scale;
  const height = box.height / view.scale;
  return { x: view.cx - width / 2, y: view.cy - height / 2, width, height };
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
