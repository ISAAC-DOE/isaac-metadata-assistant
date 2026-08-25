/*
 * P29.3 — bounded DETERMINISTIC workflow agent (authority + proposal/confirmation).
 *
 * AUTHORITY BOUNDARY (truth-critical — this is the whole point of the module):
 * This agent is a bounded, typed-intent state machine over the P28 authoritative
 * context (workflow + evidence classification + pending list + record revision).
 * It is DETERMINISTIC: there is NO external LLM, no freeform natural-language
 * model, no generation — only a fixed registry of small pure functions that read
 * the context handed to them and render honest, verdict-free explanations.
 *
 * The agent EXPLAINS and STAGES. It MUST NEVER:
 *   - confirm a scientific value on its own (only `confirmProposal`, driven by an
 *     explicit user action, ever writes),
 *   - silently write a candidate, or invent a value / evidence / provenance,
 *   - strengthen or override an evidence classification (returned verbatim),
 *   - override validation / audit, or render a PASS/FAIL / validity verdict
 *     (every rendered text passes the `hasVerdictLanguage` guard),
 *   - resolve a conflict or pick a winner,
 *   - guess an Unknown,
 *   - mark a step complete or advance the workflow,
 *   - export without the user's confirm action,
 *   - use Project Memory as record evidence (read intents read ONLY `ctx.evidence`),
 *   - claim current state without version verification (a `degraded` context yields
 *     the honest "cannot verify" message),
 *   - silently retry after a 412, or auto-merge a stale write.
 *
 * Writes are gated twice: a proposal is bound to the record revision it was
 * computed against (`sourceRev`), and `confirmProposal` refuses to touch the api
 * if the record has advanced (stale) — revalidation is required. A 412 from the
 * backend marks the proposal stale with NO retry and NO merge.
 */

import { hasVerdictLanguage } from './assistant';
import { statusOf } from './mutationErrors';

/** One workflow step as reported by the authoritative P28 workflow context. */
export type WorkflowStep = {
  id: string;
  label: string;
  state: string;
  current: boolean;
  reopened: boolean;
  blocked: boolean;
  reason: string | null;
};

/** One field's evidence-support classification, reported verbatim from the record. */
export type EvidenceView = {
  field: string;
  classification: string;
  value_state: string;
  explanation: string;
  sources: { source_type: string }[];
};

/** One pending (not-yet-entered) field. */
/** `run_id` is present when a RUN owns the question — see `ConfirmApi`. Optional so an
 *  older caller or a fixture that omits it still typechecks, which is correct: a record
 *  with no runs has no run-owned questions. */
export type PendingItem = {
  id: string;
  label: string;
  run_id?: string | null;
  /** Unique across owners; `id` is not. See `Proposal.blockerKey`. */
  blocker_key?: string;
};

/**
 * The authoritative context the agent reasons over. It is passed in by the
 * caller (already fetched from the backend); the agent never fetches truth
 * itself and never consults Project Memory for any of these values.
 */
export type AgentContext = {
  experimentId: string;
  recordRev: number;
  version: string;
  workflow: {
    current_step: string | null;
    ordered_steps: WorkflowStep[];
  };
  evidence: EvidenceView[];
  pending: PendingItem[];
  /** True when the current record state could not be verified (e.g. version
   *  check failed). Any dataset-specific intent then refuses to answer. */
  degraded?: boolean;
};

/** Options a read intent may take. `field` selects an evidence entry; `step`
 *  selects a navigation target; `value` is only ever the user-supplied value. */
export type AgentOpts = { field?: string; step?: string; value?: unknown };

/** The result of a read intent. `navigateTo` marks a (non-mutating) navigation. */
export type IntentResult = {
  text: string;
  classification?: string;
  navigateTo?: string;
};

/** A staged, user-supplied value awaiting the user's explicit confirmation. */
export type Proposal = {
  id: string;
  experimentId: string;
  field: string;
  /**
   * The IDENTITY of the question this proposal answers, when the caller knows it.
   *
   * `field` is the blocker KIND, which is what goes in the request body — and is NOT
   * unique. `confirmProposal` used to locate the owning run with
   * `ctx.pending.find((p) => p.id === proposal.field)`, which returns the FIRST entry
   * of that kind. An independent review measured the consequence with two runs each
   * owing a spectrum: run 2's spectrum was written onto RUN 1, with run 1's `If-Match`,
   * and reported as confirmed, while run 2's question stayed open. Before that routing
   * existed the same click 409'd — nothing written, honestly refused.
   */
  blockerKey?: string;
  /**
   * The run that owns the question, when one does — carried EXPLICITLY rather than
   * parsed back out of `blockerKey`.
   *
   * An earlier version recovered it from the key's prefix (`f"{run_id}:{id}"`, split at
   * the first colon, accepted if it matched a 26-char ULID shape). That works for the
   * questions every run owes, whose `id` is a kind — but an ASSET blocker's `id` is a
   * URI, and a record-level asset key is the bare URI. A URI whose text before the first
   * colon happened to be 26 characters of `[0-9A-Z]` would have been read as a run id
   * and routed a record-level answer at a run that does not exist. Remote, and entirely
   * avoidable: the owning run is known at STAGE time, so it is recorded rather than
   * reconstructed.
   */
  runId?: string;
  value: unknown;
  origin: string;
  classification?: string;
  explanation?: string;
  producingTool?: string;
  sourceRev: number;
  confirmationState: 'pending' | 'confirmed' | 'stale';
};

/** The minimal mutation surface `confirmProposal` needs — satisfied by `api`
 *  in lib/api.ts. Both methods add `If-Match: "<version>"` from the version arg.
 *
 *  `runId` ROUTES A RUN-OWNED ANSWER TO THE RUN, and it was missing. A spectrum, a QC
 *  verdict, a descriptor and an asset hash belong to the run that measured them, and
 *  the record-level route refuses them with `409 belongs_to_a_run` once a record has
 *  runs. So on any record with runs, Stage-Answer → Confirm for one of those fields hit
 *  the record route and threw a 409 into the panel's generic branch — whose copy says it
 *  CANNOT establish that nothing was written, while the server had just said "Nothing
 *  was written." An independent review measured it reachable in the shipped worked
 *  example. `getRun` is needed because a run write takes THE RUN's `If-Match`. */
export interface ConfirmApi {
  submitAnswer(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
    runId?: string,
  ): Promise<unknown>;
  editField(
    id: string,
    answersById: Record<string, unknown>,
    version?: string,
    runId?: string,
  ): Promise<unknown>;
  getRun?(experimentId: string, runId: string): Promise<{ run: { version: string } }>;
}

/** The exact honest message returned when the record state cannot be verified. */
export const DEGRADED_MESSAGE = 'I cannot verify the current record state right now.';

/**
 * Structural verdict guard. Every rendered text passes through here so a PASS/FAIL
 * or validity claim can never escape the agent — a defensive programming-error
 * check, not a runtime branch the tests are expected to trigger.
 */
function guard(result: IntentResult): IntentResult {
  if (hasVerdictLanguage(result.text)) {
    throw new Error('assistantAgent: verdict language is not permitted in agent output.');
  }
  return result;
}

/** The step object for the authoritative current step, if any. */
function currentStep(ctx: AgentContext): WorkflowStep | undefined {
  return ctx.workflow.ordered_steps.find((s) => s.id === ctx.workflow.current_step);
}

/**
 * The intent registry: a fixed map of typed intents to small PURE functions.
 * Each reads only the context (and opts) and returns a verdict-free explanation.
 * None mutates and none fetches — the ONLY write path is `confirmProposal`.
 */
const REGISTRY: Record<string, (ctx: AgentContext, opts: AgentOpts) => IntentResult> = {
  explain_current_state(ctx) {
    const step = currentStep(ctx);
    if (!step) return { text: 'No current step is set on this record.' };
    return {
      text:
        `The workflow is on the step "${step.label}". This is where your attention is ` +
        `needed now; the assistant explains it and points to the source — it does not ` +
        `advance the step for you.`,
    };
  },

  identify_next_missing_field(ctx) {
    const next = ctx.pending[0];
    if (!next) {
      return {
        text:
          'There are no pending fields — none is currently blocking. The deterministic ' +
          'audit remains the authority on completeness.',
      };
    }
    return {
      text:
        `The next pending field is "${next.label}". It is not yet entered; the assistant ` +
        `can stage a value you supply for confirmation, but never fills it in on its own.`,
    };
  },

  explain_step_blocker(ctx) {
    const blocked = ctx.workflow.ordered_steps.find((s) => s.blocked);
    if (!blocked) return { text: 'No step is currently blocked.' };
    return {
      text:
        `The step "${blocked.label}" is blocked. Reason from the workflow: ` +
        `${blocked.reason ?? '(no reason provided)'}`,
    };
  },

  explain_reopened_step(ctx) {
    const reopened = ctx.workflow.ordered_steps.find((s) => s.reopened);
    if (!reopened) return { text: 'No step has been reopened.' };
    return {
      text:
        `The step "${reopened.label}" was reopened. Reason from the workflow: ` +
        `${reopened.reason ?? '(no reason provided)'}`,
    };
  },

  review_field_evidence(ctx, opts) {
    const field = opts.field;
    if (!field) return { text: 'Name a field to review its evidence.' };
    // Reads ONLY the authoritative record evidence — never Project Memory.
    const e = ctx.evidence.find((x) => x.field === field);
    if (!e) return { text: `No evidence classification is recorded for "${field}".` };
    return {
      // Classification is returned VERBATIM; the assistant never strengthens it.
      classification: e.classification,
      text:
        `Field "${e.field}" — classification: ${e.classification} (value state: ` +
        `${e.value_state}). ${e.explanation} This is reported verbatim from the record's ` +
        `evidence classification; the assistant does not upgrade or reinterpret it.`,
    };
  },

  show_inferred_candidates(ctx) {
    const cands = ctx.evidence.filter((e) => e.classification === 'inferred_candidate');
    if (!cands.length) {
      return { text: 'No inferred candidates are present — nothing awaits confirmation.' };
    }
    const list = cands.map((e) => `${e.field} (${e.explanation})`).join('; ');
    return {
      text:
        `These are inferred candidates — unconfirmed, not entered as fact: ${list}. ` +
        `Each needs your confirmation before it becomes a recorded value.`,
    };
  },

  review_evidence_conflicts(ctx) {
    const conflicts = ctx.evidence.filter((e) => e.classification === 'conflicting_evidence');
    if (!conflicts.length) return { text: 'No conflicting evidence is present.' };
    const list = conflicts
      .map((e) => `${e.field}: ${e.explanation} (${e.sources.length} sources)`)
      .join('; ');
    return {
      text:
        `Conflicting evidence needs a human to resolve — the assistant presents both ` +
        `sides and never picks a winner: ${list}.`,
    };
  },

  explain_unknown(ctx) {
    const unknowns = ctx.evidence.filter((e) => e.classification === 'unknown');
    if (!unknowns.length) return { text: 'No fields are classified Unknown.' };
    const list = unknowns.map((e) => `${e.field} (${e.explanation})`).join('; ');
    return {
      text:
        `These fields are Unknown — there is no defensible value, and the assistant ` +
        `does not guess one: ${list}.`,
    };
  },

  navigate_to_step(ctx, opts) {
    const target = opts.step ?? ctx.workflow.current_step ?? undefined;
    const step = ctx.workflow.ordered_steps.find((s) => s.id === target);
    if (!step) return { text: 'That step is not part of this workflow.' };
    return {
      navigateTo: step.id,
      text:
        `Navigating to "${step.label}". This only changes your view — it does not ` +
        `complete, unblock, or advance any step.`,
    };
  },

  stage_answer(_ctx, opts) {
    const field = opts.field;
    if (!field) return { text: 'Name a field to stage a value for.' };
    return {
      text:
        `The assistant can stage a value you supply for "${field}" as a pending proposal ` +
        `bound to the current record revision. It records your value verbatim and waits ` +
        `for your explicit confirmation — it never fills the value in itself.`,
    };
  },

  confirm_staged_answer() {
    return {
      text:
        'Confirming a staged value sends YOUR value to the record with the current ' +
        'version as If-Match, through the confirmation path. The assistant will not ' +
        'confirm on its own, retry a stale write, or auto-merge; a stale conflict is ' +
        'returned for your review.',
    };
  },

  review_export_readiness(ctx) {
    const step = ctx.workflow.ordered_steps.find((s) => s.id === 'review_export_readiness');
    const label = step?.label ?? 'Review Export Readiness';
    const note = step?.blocked ? ` This step is currently blocked: ${step.reason ?? ''}` : '';
    return {
      text:
        `Export readiness ("${label}") is decided by the deterministic gate — schema ` +
        `validation and the evidence audit — not by the assistant.${note} The assistant ` +
        `explains the inputs and points you to the gate; it never authorizes export.`,
    };
  },
};

/** The set of intents the agent recognises (stable, deterministic). */
export const INTENTS = Object.freeze(Object.keys(REGISTRY));

/**
 * Run one typed intent against the authoritative context. Pure: no mutation, no
 * fetch. A `degraded` context refuses every dataset-specific intent with the
 * exact honest message (never a fabricated answer).
 */
export function runIntent(
  intent: string,
  ctx: AgentContext,
  opts: AgentOpts = {},
): IntentResult {
  if (ctx.degraded === true) return { text: DEGRADED_MESSAGE };
  const handler = REGISTRY[intent];
  if (!handler) return guard({ text: `Unrecognised request: "${intent}".` });
  return guard(handler(ctx, opts));
}

/** Monotonic counter so proposal ids are unique within a session. */
let proposalSeq = 0;

/**
 * Stage a USER-supplied value as a pending proposal. The value is recorded
 * verbatim — never invented. The proposal is bound to the record revision it was
 * computed against (`sourceRev`) so a later confirm can detect staleness. It is
 * always `pending`; nothing is auto-confirmed. Any matching evidence
 * classification is copied VERBATIM for context (never strengthened).
 */
export function stageAnswer(
  ctx: AgentContext,
  {
    field,
    blockerKey,
    runId,
    value,
    origin,
  }: {
    field: string;
    blockerKey?: string;
    runId?: string;
    value: unknown;
    origin?: string;
  },
): Proposal {
  const evidence = ctx.evidence.find((e) => e.field === field);
  return {
    id: `proposal-${field}-${ctx.recordRev}-${++proposalSeq}`,
    experimentId: ctx.experimentId,
    field,
    ...(blockerKey ? { blockerKey } : {}),
    ...(runId ? { runId } : {}),
    value, // the user's value, verbatim — never invented
    origin: origin ?? PROPOSAL_ORIGIN.DEFAULT,
    ...(evidence
      ? { classification: evidence.classification, explanation: evidence.explanation }
      : {}),
    sourceRev: ctx.recordRev,
    confirmationState: 'pending',
  };
}

/**
 * P29.6 — the source a staging request comes FROM. This is the whole point of the
 * guard: only a focused USER answer or an evidence-grounded CANDIDATE may ever
 * create a proposal. Project Memory / graph is a MEMORY plane and can NEVER
 * propose a scientific value (§7 of the project instructions).
 */
export type ProposeSource = 'user' | 'candidate' | 'memory' | 'graph';

/**
 * EVERY `origin` A PROPOSAL IN THIS APPLICATION CAN CARRY. Exhaustive by
 * construction: the three producers are `stageAnswer`'s default and the two labels
 * `proposeForField` passes, and each of them reads its literal from this object
 * rather than spelling one, so a new origin cannot appear without appearing here.
 *
 * WHY IT IS A CONSTANT AND NOT A COMMENT. `lib/assistantSession.ts` rehydrates a
 * `Proposal` out of `sessionStorage`, which is input rather than state, and it needs
 * a closed set to check it against. An ALLOWLIST rather than a denylist, for the
 * reason `proposeForField`'s own source guard is one: a denylist has to predict the
 * next author's spelling, and the shape of the mistake this project has already
 * made once (`__tests__/assistant-propose.test.ts`) is a guard rewritten from the
 * first form to the second.
 *
 * `user` is here because `stageAnswer` defaults to it when a caller supplies no
 * origin. No production caller does — `proposeForField` always names one — but the
 * parameter is optional, so the default is producible and is therefore legitimate.
 */
export const PROPOSAL_ORIGIN = {
  /** `stageAnswer`'s default, for a caller that names no origin. */
  DEFAULT: 'user',
  /** A focused answer the scientist typed or selected. */
  USER: 'user-provided',
  /** A value taken verbatim from the field's own evidence classification. */
  CANDIDATE: 'candidate (evidence-grounded)',
} as const;

/** The allowlist, as a set, for the rehydration boundary to check against. */
export const PROPOSAL_ORIGINS: ReadonlySet<string> = new Set(
  Object.values(PROPOSAL_ORIGIN),
);

/**
 * Whether `value` is an origin this application can have produced.
 *
 * ABSENCE IS NOT ACCEPTED, and that is the load-bearing half. A check that let an
 * origin-less proposal through would be decoration: a forger who can invent an
 * origin can also omit the key. Every proposal this code constructs goes through
 * `stageAnswer`, which always sets one.
 */
export function isRecognisedProposalOrigin(value: unknown): boolean {
  return typeof value === 'string' && PROPOSAL_ORIGINS.has(value);
}

/** One staging request: a NAMED field, the source it comes from, and (for a
 *  user answer or an explicitly-selected conflict option) the value verbatim. */
export interface ProposeInput {
  field: string;
  /** The question's identity, unique across runs. See `Proposal.blockerKey`. */
  blockerKey?: string;
  /** The run that owns the question, when one does. See `Proposal.runId`. */
  runId?: string;
  value?: unknown;
  source: ProposeSource;
}

/**
 * P29.6 — the GUARDED staging entry. A PURE guard that decides WHETHER a source
 * may stage a proposal for a field, and with what honest origin/classification.
 * It never mutates `ctx`, never calls the api, and never fabricates a value.
 *
 * The rules (truth-critical):
 *   - `memory` / `graph` → ALWAYS null. Project Memory is not record evidence and
 *     can never propose a scientific value.
 *   - no field named → null (a focused answer is bound to ONE named field; never a
 *     blanket write).
 *   - `user`: a focused answer to a named field stages a PENDING proposal labeled
 *     `user-provided`. The raw user value is NEVER auto-classified as
 *     evidence-supported — any matching classification is copied for context, but
 *     a `supported` classification is stripped (a user typing a value does not make
 *     it evidence-backed). It is the only path that may answer a field the evidence
 *     calls Unknown or Conflicting — the user is providing the value, not the agent.
 *   - `candidate`: pulls the field's classification from `ctx.evidence`.
 *       · `unknown`             → null (never fabricate a value).
 *       · `conflicting_evidence`→ null (never auto-pick a winner) UNLESS an explicit
 *                                 `value` is supplied, in which case it stages for
 *                                 REVIEW (still pending, never auto-confirmed).
 *       · `inferred_candidate`  → a proposal carrying `inferred_candidate` verbatim
 *                                 (explicitly inferred/unconfirmed, never as fact).
 *       · `supported`           → a proposal.
 *       · anything else / no evidence → null (nothing defensible to stage).
 */
export function proposeForField(
  ctx: AgentContext,
  { field, blockerKey, runId, value, source }: ProposeInput,
): Proposal | null {
  // A focused answer is always bound to ONE named field.
  if (!field) return null;
  // Project Memory / graph can never propose a scientific value.
  if (source !== 'user' && source !== 'candidate') return null;

  if (source === 'user') {
    // A user answer is labeled user-provided and carries NO evidence
    // classification at all — a user-typed value is never described by the
    // field's evidence classification, so strip any copied classification
    // unconditionally (defensive hardening from the P29.6 independent review).
    const p = stageAnswer(ctx, {
      field,
      blockerKey,
      runId,
      value,
      origin: PROPOSAL_ORIGIN.USER,
    });
    delete p.classification;
    return p;
  }

  // source === 'candidate' — must be grounded in the field's real classification.
  const evidence = ctx.evidence.find((e) => e.field === field);
  if (!evidence) return null;
  switch (evidence.classification) {
    case 'unknown':
      return null; // never fabricate a value for an Unknown
    case 'conflicting_evidence':
      // Never auto-pick a winner; only an explicitly selected option may stage.
      if (value === undefined) return null;
      return stageAnswer(ctx, { field, value, origin: PROPOSAL_ORIGIN.CANDIDATE });
    case 'inferred_candidate':
    case 'supported':
      return stageAnswer(ctx, { field, value, origin: PROPOSAL_ORIGIN.CANDIDATE });
    default:
      return null; // insufficient/other → nothing defensible to stage
  }
}

// `statusOf` now lives in `lib/mutationErrors` (imported at the top of this file). It
// was private here until `AssistantPanel` needed the same reader to describe a non-412
// failure honestly; it is imported rather than copied, and its behaviour is unchanged —
// the 412 branch below reads exactly what it read before.

/**
 * Confirm a staged proposal — the ONLY write path.
 *
 * Guard 1 (staleness): if the proposal was grounded in an older revision than the
 * current context, refuse without touching the api — revalidation is required.
 *
 * Otherwise mutate exactly once, sending the current `version` as If-Match (the
 * api client adds the header). A pending field routes to `submitAnswer` (fills a
 * blocker); an already-answered field routes to `editField` (overwrites).
 *
 * Guard 2 (concurrency): a 412 (`err.status === 412`) marks the proposal stale
 * and is returned as a conflict — NO silent retry, NO auto-merge. Other errors
 * propagate unchanged.
 */
export async function confirmProposal(
  proposal: Proposal,
  ctx: AgentContext,
  api: ConfirmApi,
): Promise<{ status: 'ok' | 'stale' | 'conflict'; proposal?: Proposal; result?: unknown }> {
  // Defense-in-depth (client-side, on top of the backend byte-exact If-Match):
  // only a PENDING proposal against a VERIFIED (non-degraded), CURRENT-rev context
  // may write. A stale/already-confirmed proposal, or an unverifiable (degraded)
  // context, is refused here before any api touch — never rely on the backend 412
  // alone to stop a stale/duplicate confirm.
  if (proposal.confirmationState !== 'pending') {
    return { status: 'stale', proposal };
  }
  if (ctx.degraded) {
    // Cannot verify the current record state → must not confirm a mutation.
    return { status: 'stale', proposal: { ...proposal, confirmationState: 'stale' } };
  }
  if (proposal.sourceRev !== ctx.recordRev) {
    // The record advanced under the proposal — do NOT write; require revalidation.
    return { status: 'stale', proposal: { ...proposal, confirmationState: 'stale' } };
  }

  const answers: Record<string, unknown> = { [proposal.field]: proposal.value };
  /* MATCHED ON THE IDENTITY KEY WHEN THE PROPOSAL CARRIES ONE. `field` is the kind and
     is not unique across runs; see `Proposal.blockerKey`. Falling back to `field` keeps a
     caller that has no key working exactly as before, which is correct for a record with
     no runs — there the two are equal. */
  const open = proposal.blockerKey
    ? ctx.pending.find((p) => (p.blocker_key ?? p.id) === proposal.blockerKey)
    : ctx.pending.find((p) => p.id === proposal.field);
  const isPending = open !== undefined;
  /* THREE COMMENT BLOCKS USED TO STAND HERE AND TWO OF THEM WERE FALSE. An independent
     review found them stacked on this one statement, each describing a mechanism a later
     commit had replaced, and both are deleted rather than left as archaeology — a comment
     asserting a mechanism the code does not have is worse than no comment, because it is
     read as documentation.
       * "taken from the pending entry RATHER THAN from the proposal" — false: the edit
         path takes it from the proposal, which is the whole point of the block below.
       * "the key's own prefix IS the run id" — described `runIdFromBlockerKey`, a parser
         that was DELETED (a record-level asset key is a bare URI full of colons, so a
         26-character `[0-9A-Z]` prefix was a hazard rather than a guarantee). `runId` is
         carried explicitly now.
     The one that was correct is kept, below, unchanged. */
  /* THE OWNING RUN, FOR BOTH PATHS. `open === undefined` is what SELECTS `editField`, so
     reading the run from `open` alone left the EDIT path always record-routed — and
     correcting an answered run-owned field then 409'd on every record with runs, into a
     branch whose copy says it cannot establish whether anything reached the record while
     the server had just said "Nothing was written."
     `proposal.runId` is recorded at STAGE time, when the pending entry still exists, so
     the edit path has it without reconstructing anything. The live entry is preferred
     when there is one, because a run could have been renamed or removed since. */
  const runId = open?.run_id ?? proposal.runId;
  let token = ctx.version;
  if (runId && api.getRun) {
    token = (await api.getRun(ctx.experimentId, runId)).run.version;
  }

  try {
    const result = isPending
      ? await api.submitAnswer(ctx.experimentId, answers, token, runId)
      : await api.editField(ctx.experimentId, answers, token, runId);
    return { status: 'ok', result };
  } catch (err) {
    if (statusOf(err) === 412) {
      // Stale write detected by the backend — mark stale, no retry, no merge.
      return { status: 'conflict', proposal: { ...proposal, confirmationState: 'stale' } };
    }
    throw err;
  }
}
