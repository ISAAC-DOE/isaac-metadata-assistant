/*
 * assistantCapabilities — the REAL, per-surface catalog behind the Assistant's
 * "What Can I Ask?" control, plus every string that control renders.
 *
 * WHY THIS EXISTS. Three separate, independent mechanisms answer text typed into
 * the Assistant composer, and only ONE of them is available on every surface:
 *
 *   1. the free-form QUERY RESOLVER — `apps/api/isaac_api/assistant_query.py`,
 *      reached by `AssistantPanel.submitQuestion`. Its catalog is a finite,
 *      explicit set of trigger phrases (`_TRIGGERS`) matched by plain lowercase
 *      substring containment. No model, no scoring, no learning: an unmatched
 *      question resolves to `unsupported` and is refused, never guessed.
 *   2. the frontend SUGGESTED-QUESTION chips (`assistantComposer.ts`) — a
 *      SEPARATE precomposed catalog that resolves locally and never reaches the
 *      resolver above. Untouched by this module and deliberately not merged into
 *      it: they are different mechanisms with different guarantees.
 *   3. the bounded GRAPH-NAVIGATION intents (`graphCommands.ts`
 *      `classifyGraphQuestion`), intercepted BEFORE the resolver — but ONLY on a
 *      mount that supplies `graphCapability`, which today is Project Memory and
 *      only while its Graph tab is showing.
 *
 * WHY THE CATALOG IS PER-SURFACE, and why that is the whole point of the file.
 * Capability is SCOPE-DEPENDENT. The record surfaces submit to the per-experiment
 * resolver (`api.askAssistant` → `assistant_query.answer`), which composes all
 * eight intent families. Project Memory has NO record, so it submits to the
 * record-agnostic resolver (`api.askMemory` → `assistant_query.answer_memory_scope`),
 * which answers `memory_lead` and HONESTLY REFUSES every other family with
 * "This is the Project Memory view…". A flat, screen-independent list would
 * therefore advertise, on Project Memory, questions that are refused on Project
 * Memory — worse than showing nothing. So the groups are selected from the two
 * facts the panel already knows for certain: its `queryScope`, and whether it was
 * given a `graphCapability`. Nothing is inferred about the mounting screen.
 *
 * Every `text` below has been traced to a real trigger phrase / pattern in the
 * resolver that will receive it, and exercised against that resolver. An example
 * that does not route is a bug, and two tests hold the line:
 * `assistant-capabilities.test.tsx` re-reads `_TRIGGERS` out of the Python source
 * and re-runs the real graph classifier, and
 * `apps/api/tests/test_assistant_capabilities_catalog.py` re-reads THIS file and
 * runs the real `classify()` over every example.
 *
 * Nothing here is a claim of general-purpose intelligence, and nothing here is a
 * language model: the catalog is finite, literal and offline.
 */

/** Which read-only resolver the mounting surface submits to. Mirrors
 *  `AssistantPanelProps.queryScope` exactly — no third value exists. */
export type AssistantQueryScope = 'record' | 'memory';

/**
 * The query resolver's intent ids, spelled as `assistant_query.py` spells them.
 * Mirrored so a group can NAME the family it advertises and a test can check the
 * claim against the backend catalog; never used to select or influence routing.
 */
export type AssistantIntentId =
  | 'pending_fields'
  | 'export_blockers'
  | 'export_readiness'
  | 'workflow_step'
  | 'field_provenance'
  | 'evidence_summary'
  | 'record_summary'
  | 'memory_lead';

/** The graph intents advertised here — the subset of `GraphIntentName` whose
 *  patterns need no node/cluster token, so a listed example resolves on any
 *  projection instead of depending on a node that may not exist in it. */
export type GraphIntentId = 'graph_type' | 'graph_relation' | 'graph_clear_filters';

export interface CapabilityExample {
  /** The EXACT text inserted into the composer. Never submitted for the reader. */
  readonly text: string;
  /** The intent this text classifies to in the resolver named by its group. */
  readonly intent: AssistantIntentId | GraphIntentId;
}

export interface CapabilityGroup {
  /** Visible Title-Case heading. */
  readonly heading: string;
  /** Which deterministic resolver recognises this group's examples. */
  readonly resolvedBy: 'query-resolver' | 'graph-commands';
  readonly examples: readonly CapabilityExample[];
}

// --- copy ---------------------------------------------------------------------

/** The trigger's visible label — and, by `aria-label`, the panel's accessible
 *  name, so the two can never be announced as two different things. */
export const CAPABILITIES_TRIGGER_LABEL = 'What Can I Ask?';

/**
 * How the list behaves. Choosing an example only fills the composer.
 *
 * DIRECTION-FREE on purpose. An earlier draft said "the box below", which was
 * simply wrong: `.assistant-foot` stacks the composer FIRST, so the input sits
 * ABOVE this control — and the popover opens upward over the composer, so a
 * reader looking "below" finds the boundary sentence and the Close button. The
 * note names the target ("the composer") instead of pointing at it.
 */
export const CAPABILITIES_INSERT_NOTE =
  'Pick one to put it in the composer. Nothing is sent until you send it.';

/**
 * Shown INSTEAD of the insert note while the composer already holds a draft.
 *
 * Inserting used to overwrite a half-typed question without warning. It no
 * longer does — and because a control that silently declines to act is its own
 * kind of surprise, the panel says so BEFORE the click rather than explaining
 * itself afterwards.
 */
export const CAPABILITIES_DRAFT_KEPT_NOTE =
  'Your unsent question stays in the composer. Clear it first to insert an example.';

/**
 * The BOUNDARY. It must never imply open-ended understanding — but it must also
 * not overstate the rigidity: the resolver holds several trigger phrases per
 * family, so a family tolerates re-phrasing while the SET of families is closed.
 * Both halves are load-bearing, and the second sentence is the honest part: a
 * question outside the set is refused rather than answered from a guess.
 */
export const CAPABILITIES_BOUNDARY =
  'These families are the whole set. Wording is flexible within them; anything outside them is refused, not guessed.';

/** Shown only in `memory` scope, where the record families genuinely are not
 *  available — the same fact the resolver's own refusal states. */
export const CAPABILITIES_MEMORY_SCOPE_NOTE =
  'This view answers project-memory questions. Open a record to ask about its fields, evidence, workflow, or export readiness.';

export const CAPABILITIES_CLOSE_LABEL = 'Close';

// --- the catalog --------------------------------------------------------------

/**
 * The RECORD surfaces (Record Workbench, Guided Completion, Evidence Explorer,
 * Ready to Export). All four mount with the default `queryScope` and a real
 * `experimentId`, so their questions reach `assistant_query.answer`, which
 * composes every one of these families — `memory_lead` included, because the
 * record endpoint passes a real memory search into its context.
 */
export const RECORD_CAPABILITY_GROUPS: readonly CapabilityGroup[] = Object.freeze([
  Object.freeze({
    heading: 'Workflow and Current Step',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({ text: 'What is the current step?', intent: 'workflow_step' }),
      Object.freeze({ text: 'Explain the workflow.', intent: 'workflow_step' }),
    ]),
  }),
  Object.freeze({
    heading: 'Missing Fields and Confirmations',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({ text: 'What still needs me?', intent: 'pending_fields' }),
      Object.freeze({ text: "What's missing?", intent: 'pending_fields' }),
    ]),
  }),
  Object.freeze({
    heading: 'Export Blockers and Readiness',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({ text: "What's blocking export?", intent: 'export_blockers' }),
      Object.freeze({ text: 'Is this ready to export?', intent: 'export_readiness' }),
    ]),
  }),
  Object.freeze({
    heading: 'Evidence and Provenance',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      // Both are the resolver's OWN follow-up strings (`_FOLLOWUPS`). With no
      // field named they resolve to the honest "which field?" answer, which lists
      // the record's really traceable fields — never a guessed field.
      Object.freeze({ text: 'Where did this field come from?', intent: 'field_provenance' }),
      Object.freeze({ text: "What's the evidence for this field?", intent: 'evidence_summary' }),
    ]),
  }),
  Object.freeze({
    heading: 'Record Summary',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({ text: 'Summarize this record.', intent: 'record_summary' }),
    ]),
  }),
  Object.freeze({
    heading: 'Project Memory',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({ text: 'Where is the evidence sidecar defined?', intent: 'memory_lead' }),
    ]),
  }),
]);

/**
 * PROJECT MEMORY (`queryScope: 'memory'`). This surface has no record, so
 * `answer_memory_scope` answers `memory_lead` and refuses every record family
 * outright. Advertising a record family here would advertise that refusal, so
 * none is listed.
 */
export const MEMORY_CAPABILITY_GROUPS: readonly CapabilityGroup[] = Object.freeze([
  Object.freeze({
    heading: 'Project Memory',
    resolvedBy: 'query-resolver',
    examples: Object.freeze([
      Object.freeze({
        text: 'What does project memory know about the evidence sidecar?',
        intent: 'memory_lead',
      }),
      Object.freeze({ text: 'Where is the evidence sidecar defined?', intent: 'memory_lead' }),
    ]),
  }),
]);

/**
 * GRAPH NAVIGATION — offered ONLY while the panel actually holds a
 * `graphCapability`, because that prop IS the interception: without it
 * `submitQuestion` never consults `classifyGraphQuestion` and these lines fall
 * through to the query resolver, which does not recognise them.
 *
 * Every example is token-free by design. `neighbors` / `path` / `community <x>`
 * need a node or cluster that exists in the loaded projection; hardcoding one
 * would make a listed example depend on a specific graph. Applying any of these
 * still requires the explicit "Apply to Graph" control — recognition only
 * proposes.
 */
export const GRAPH_CAPABILITY_GROUP: CapabilityGroup = Object.freeze({
  heading: 'Graph Navigation',
  resolvedBy: 'graph-commands',
  examples: Object.freeze([
    Object.freeze({ text: 'Show only files', intent: 'graph_type' }),
    Object.freeze({ text: 'Show all relationships', intent: 'graph_relation' }),
    Object.freeze({ text: 'Clear the graph filters', intent: 'graph_clear_filters' }),
  ]),
});

/**
 * The groups genuinely supported on the CURRENT surface.
 *
 * `scope` decides which resolver receives a typed question; `graph` says whether
 * the graph interception is wired right now. Both come from props the panel
 * already has, so no screen had to be changed to make this correct — and a group
 * is never listed on a surface that would refuse it.
 */
export function capabilityGroupsFor(
  scope: AssistantQueryScope,
  opts: { graph?: boolean } = {},
): readonly CapabilityGroup[] {
  const base = scope === 'memory' ? MEMORY_CAPABILITY_GROUPS : RECORD_CAPABILITY_GROUPS;
  return opts.graph ? Object.freeze([...base, GRAPH_CAPABILITY_GROUP]) : base;
}
