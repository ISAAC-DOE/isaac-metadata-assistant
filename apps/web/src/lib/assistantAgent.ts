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
 *
 * ONE THING IS NOT A RETRY AND MUST NOT BE READ AS ONE. `confirmProposal` may issue a
 * SECOND write when — and only when — the first was refused `422 already_answered` or
 * `422 not_yet_answered`, two refusals that write nothing and name the operation that
 * can take the request. It follows that name ONCE, to the operation the server named,
 * with the If-Match token of the level the server named. It is a redirect, not a retry:
 * nothing is re-sent to an operation that has already refused it, and no other status
 * — not a 412, not a `409 belongs_to_a_run`, not a 403, not a 500 — is followed at all.
 * See `confirmProposal` for why the alternative (deciding the route from a pre-fetched
 * list) had to go.
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
  /**
   * The record's open questions, FROM THE HEAD, and NOT NECESSARILY ALL OF THEM.
   *
   * `useRecordSession` fills this from a bounded page rather than the complete list: a
   * record's question count is `3 x runs`, and at 1,000 runs the complete list is
   * 1,772,692 bytes fetched again after every accepted answer. It is a PREFIX from
   * offset 0, so "the first entry" and "empty means none are open" are both exactly as
   * true as they were; "this is every open question" never was a promise this field
   * made, and is now measurably false on a large record.
   *
   * NO CONSUMER MAY COUNT IT, TOTAL IT, OR TREAT AN ABSENT ENTRY AS "ANSWERED".
   * `confirmProposal` used to do the last of those and that is what kept the read
   * unbounded; it now treats membership as a hint and lets the server decide. The
   * property is pinned rather than asserted: `assistant-agent-pending-window.test.ts`
   * runs every registered intent against a full list and against a one-entry window of
   * it and requires byte-identical output.
   */
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
 * THE TWO SERVER REFUSALS THAT NAME WHERE THE ANSWER SHOULD HAVE GONE.
 *
 * `POST /answers` against a CLOSED question answers `422 already_answered`; `POST /edit`
 * against an OPEN one answers `422 not_yet_answered`. Both guarantee that NOTHING was
 * written, and both carry `answer_at` — the operation at the level that can actually take
 * the request. They are the reason this module no longer decides `submitAnswer` vs
 * `editField` from membership in a pre-fetched list; see `confirmProposal`.
 */
export type AnswerRoutingError = 'already_answered' | 'not_yet_answered';

/** The parsed form of one of those refusals. `answerAt`/`runId` are `null` when the
 *  body does not say — ABSENCE IS A STATEMENT here and is never filled in. */
export type RoutingRefusal = {
  error: AnswerRoutingError;
  /** The operation TEMPLATE the server named, verbatim, or `null` when it named none. */
  answerAt: string | null;
  /** The concrete run id the refusal was raised at, or `null` on the record path. */
  runId: string | null;
  /** The server's own sentence, or `null` when the body carries none. */
  message: string | null;
};

/**
 * Is this thrown error one of the two routing refusals? `null` for anything else.
 *
 * Duck-typed and fail-closed for the reasons every discriminator in `lib/mutationErrors`
 * is: a transport failure, a rejected `fetch` and a test double all arrive at a `catch`
 * as something that may or may not carry a `status` and a parsed `body`. Anything that
 * does not have the expected shape returns `null`, which routes the caller to "I cannot
 * tell you what happened" rather than to a redirect it cannot justify.
 *
 * THE `error` CODE IS READ, NOT THE STATUS ALONE. `422` from these two operations has
 * at least six other causes — `confirmation_required`, `no_derivation_to_confirm`,
 * `unrecognized_field`, `invalid_field_value`, the framework's own body validation, and
 * whatever a future validation adds — and none of them says where the request should
 * have gone. Widening this to "any 422" would turn an unrelated refusal into a blind
 * second write.
 */
export function answerRoutingRefusal(err: unknown): RoutingRefusal | null {
  if (typeof err !== 'object' || err === null) return null;
  if ((err as { status?: unknown }).status !== 422) return null;
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return null;
  const code = (body as { error?: unknown }).error;
  if (code !== 'already_answered' && code !== 'not_yet_answered') return null;
  const answerAt = (body as { answer_at?: unknown }).answer_at;
  const runId = (body as { run_id?: unknown }).run_id;
  const message = (body as { message?: unknown }).message;
  return {
    error: code,
    answerAt: typeof answerAt === 'string' && answerAt !== '' ? answerAt : null,
    runId: typeof runId === 'string' && runId !== '' ? runId : null,
    message: typeof message === 'string' && message !== '' ? message : null,
  };
}

/** Which of the two write methods an operation is, and whether it is run-level. */
type WriteTarget = { operation: 'answers' | 'edit'; runId?: string };

/**
 * EVERY `answer_at` THIS CLIENT WILL FOLLOW, matched as an EXACT literal.
 *
 * An ALLOWLIST rather than a parser, and that is the whole safety property. The four
 * strings are `routes.py`'s own `_ANSWERS_OPERATION_RECORD` / `_ANSWERS_OPERATION_RUN` /
 * `_EDIT_OPERATION_RECORD` / `_EDIT_OPERATION_RUN` constants — which exist there for the
 * same reason this exists here: *"two copies of a URL is how one of them ends up stale"*.
 * A template this map does not know is NOT interpolated, NOT pattern-matched and NOT
 * guessed at; it is treated as "no route I can follow", which lands on the same honest
 * branch an absent `answer_at` does.
 *
 * A URL is deliberately never built from the pieces. The client already owns typed
 * methods for all four operations (`submitAnswer`/`editField` × record/run), so the
 * template is used only to CHOOSE one of them; the ids come from the refusal's own
 * body, which is the convention the server documents ("the ids to substitute into it
 * are in this same body").
 */
const ANSWER_AT_OPERATIONS: Readonly<
  Record<string, { operation: 'answers' | 'edit'; run: boolean }>
> = Object.freeze({
  'POST /api/experiments/{experiment_id}/answers': { operation: 'answers', run: false },
  'POST /api/experiments/{experiment_id}/runs/{run_id}/answers': {
    operation: 'answers',
    run: true,
  },
  'POST /api/experiments/{experiment_id}/edit': { operation: 'edit', run: false },
  'POST /api/experiments/{experiment_id}/runs/{run_id}/edit': {
    operation: 'edit',
    run: true,
  },
});

/**
 * The ONE operation this client will follow a refusal to, or `null` to surface it.
 *
 * `null` — meaning "say what the server said and stop" — for every case in which a
 * redirect would be a guess rather than an instruction:
 *
 *  - **no `answer_at`.** The server omits the key rather than emitting one it would
 *    refuse: on a record with runs, a spectrum, a QC verdict, a descriptor and an asset
 *    hash belong to the run that measured them, so no operation on the RECORD can answer
 *    one. Absence is the honest output there and inventing a route from the other three
 *    templates would walk straight into the second refusal the server was avoiding.
 *  - **an `answer_at` this client does not know.** See `ANSWER_AT_OPERATIONS`.
 *  - **a run-level template with no `run_id` in the body.** The id is taken from the
 *    refusal, never from the guess that produced it — a redirect that reuses the run
 *    we happened to try is how a value lands on the wrong run, which is the defect
 *    `Proposal.blockerKey` was added for.
 *  - **the operation we just called.** Impossible under the published contract (each
 *    refusal names the OTHER member of its pair at the same level), so reaching it means
 *    the server contradicted itself — and repeating a call that just failed is the one
 *    shape of "follow it once" that could look like a loop. Refusing structurally is
 *    cheaper than reasoning about it.
 */
function redirectTargetFor(refusal: RoutingRefusal, attempted: WriteTarget): WriteTarget | null {
  if (refusal.answerAt === null) return null;
  const spec = ANSWER_AT_OPERATIONS[refusal.answerAt];
  if (spec === undefined) return null;
  // A run operation with no run named in the body has nothing to substitute, and the run
  // that was attempted is not a substitute for the run the server meant.
  if (spec.run && refusal.runId === null) return null;
  const target: WriteTarget = spec.run
    ? { operation: spec.operation, runId: refusal.runId as string }
    : { operation: spec.operation };
  if (target.operation === attempted.operation && target.runId === attempted.runId) {
    return null;
  }
  return target;
}

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
 * Otherwise mutate, sending the version as If-Match (the api client adds the header).
 *
 * Guard 2 (concurrency): a 412 (`err.status === 412`) marks the proposal stale
 * and is returned as a conflict — NO silent retry, NO auto-merge. Other errors
 * propagate unchanged.
 *
 * ── THE OPEN/ANSWERED DECISION IS THE SERVER'S, AND USED NOT TO BE ─────────────────
 *
 * `submitAnswer` fills an OPEN question; `editField` corrects an ALREADY-ANSWERED one,
 * and each refuses the other's job. This function used to choose between them by asking
 * whether the proposal's question appeared in `ctx.pending` — a list fetched before the
 * click, by a different component, for a different purpose.
 *
 * THAT MADE A READ'S COMPLETENESS INTO A WRITE'S CORRECTNESS CONDITION, which is why
 * the list could not be bounded. A record's question count is `3 x runs`; the completion
 * screen pages past 50; and with a 50-entry context a reader who paged to question 900
 * and staged it took `isPending: false` and the EDIT route. Measured over HTTP against
 * that route on an unanswered question: `422 unrecognized_field`, *"No editable field
 * was recognized in the request."* A legitimate first answer refused, with a reason
 * naming the wrong cause — the field was recognised perfectly well; only its STATE was
 * other than the client had assumed.
 *
 * SO THE LIST IS NOW A HINT AND THE SERVER IS THE AUTHORITY. The hinted route is
 * attempted; if it was the wrong one, the server says so in the one vocabulary that
 * cannot drift from its own behaviour:
 *
 *   `POST /answers` on a CLOSED question   -> 422 `already_answered`,  answer_at: …/edit
 *   `POST /edit`    on an OPEN   question  -> 422 `not_yet_answered`,  answer_at: …/answers
 *
 * Both refusals guarantee that nothing was written, and both were proved actionable
 * rather than plausibly so — `_refuse_answering_an_already_answered_key` refuses a key
 * only if `apply_corrections` would write it, so `/edit` is guaranteed to accept what it
 * redirects; a security review followed all six `answer_at` values over HTTP and every
 * target returned `200`.
 *
 * ── WHAT "FOLLOW IT ONCE" MEANS, EXACTLY ──────────────────────────────────────────
 *
 *  - **ONE redirect, structurally.** The second attempt's failure is never inspected for
 *    an `answer_at`; there is no loop to bound because there is no cycle to enter. A
 *    target equal to the one just attempted is refused by `redirectTargetFor` as well,
 *    so even a self-contradicting server cannot produce a repeated call.
 *  - **ONLY those two codes.** A 412, a `409 belongs_to_a_run`, a 403, a 500, an
 *    `invalid_field_value`, a transport failure: none is retried, and none ever was.
 *    The `error` code is read, not the status.
 *  - **The CAS token follows the REDIRECT, not the guess.** A run write takes the RUN's
 *    version and a record write takes the record's; sending the wrong one is a 412 the
 *    reader would be told to fix by refreshing something that was never stale. The token
 *    is therefore re-derived from the target (`tokenFor`), so a redirect that crosses
 *    levels re-fetches rather than reusing what the first attempt happened to hold.
 *  - **An ABSENT `answer_at` is obeyed as an answer.** It means nothing on this record
 *    can resolve the condition, so no route is guessed and the server's own sentence is
 *    returned for the caller to show (`status: 'refused'`).
 *
 * `proposal.runId` keeps its existing role throughout: it is recorded at STAGE time and
 * is what makes the first attempt run-routed at all. The redirect does not read it —
 * it reads the refusal's `run_id` — so a mis-recorded run cannot be carried into the
 * second write.
 */
export async function confirmProposal(
  proposal: Proposal,
  ctx: AgentContext,
  api: ConfirmApi,
): Promise<{
  status: 'ok' | 'stale' | 'conflict' | 'refused';
  proposal?: Proposal;
  result?: unknown;
  /** Present only on `refused`: the SERVER's own sentence, verbatim. */
  message?: string;
  /** Present only on `refused`: which of the two refusals it was. */
  error?: AnswerRoutingError;
}> {
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
     no runs — there the two are equal.

     THIS IS A HINT, NOT THE DECISION. `ctx.pending` may be a bounded window of the
     record's questions (`useRecordSession` reads a page, not the set), so an absent entry
     means "not in the window", which is a weaker statement than "already answered". Being
     wrong here now costs ONE extra round trip and never a wrong outcome — the server
     refuses the wrong route without writing and names the right one. Keeping the hint at
     all is what keeps that round trip rare: it is correct for every question inside the
     window, which is every question on every record that exists today. */
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

  /* THE If-Match TOKEN FOR ONE TARGET, DERIVED FROM THAT TARGET. A run write takes the
     RUN's version; a record write takes the record's. This is a function of the target
     rather than a variable computed once, which is the whole reason the redirect below
     can cross levels safely: it asks again instead of reusing what the first attempt
     held. A caller with no `getRun` keeps the previous behaviour exactly — the record's
     token is used, which is what it has always sent. */
  const tokenFor = async (target: WriteTarget): Promise<string> => {
    if (target.runId && api.getRun) {
      return (await api.getRun(ctx.experimentId, target.runId)).run.version;
    }
    return ctx.version;
  };

  /* ONE write, at one named operation. `runId` is passed through as `undefined` for a
     record-level target, which is what routes `api.submitAnswer`/`api.editField` at the
     record — nothing is parsed out of a key to get there. */
  const write = async (target: WriteTarget): Promise<unknown> => {
    const token = await tokenFor(target);
    return target.operation === 'answers'
      ? api.submitAnswer(ctx.experimentId, answers, token, target.runId)
      : api.editField(ctx.experimentId, answers, token, target.runId);
  };

  const attempted: WriteTarget = {
    operation: isPending ? 'answers' : 'edit',
    ...(runId ? { runId } : {}),
  };

  try {
    return { status: 'ok', result: await write(attempted) };
  } catch (err) {
    if (statusOf(err) === 412) {
      // Stale write detected by the backend — mark stale, no retry, no merge.
      return { status: 'conflict', proposal: { ...proposal, confirmationState: 'stale' } };
    }
    const refusal = answerRoutingRefusal(err);
    // Not one of the two routing refusals -> this function has nothing to add. Rethrown
    // unchanged so the caller's own handling (which claims LESS about what happened than
    // a redirect would) is what the reader sees.
    if (refusal === null) throw err;
    const target = redirectTargetFor(refusal, attempted);
    if (target === null) {
      // Nothing to follow. The server established that nothing was written and said why;
      // that sentence is returned rather than a route invented to replace it.
      return refusalOutcome(refusal, err);
    }
    try {
      return { status: 'ok', result: await write(target) };
    } catch (again) {
      /* THE SECOND ATTEMPT IS THE LAST ONE, AND THAT IS ENFORCED BY STRUCTURE RATHER
         THAN BY A COUNTER: this block does not call `redirectTargetFor`, so there is no
         edge back into the redirect and no cycle to bound. A 412 here is the same
         conflict it would have been on the first attempt (still no retry, still no
         merge); a routing refusal here means the pair contradicted itself, and is
         surfaced rather than acted on; anything else propagates. */
      if (statusOf(again) === 412) {
        return { status: 'conflict', proposal: { ...proposal, confirmationState: 'stale' } };
      }
      const second = answerRoutingRefusal(again);
      if (second === null) throw again;
      return refusalOutcome(second, again);
    }
  }
}

/**
 * A routing refusal the client will not act on, rendered as an outcome the caller can
 * show. The server's sentence is carried VERBATIM — it is the only description of the
 * refusal that cannot drift from the behaviour producing it. A refusal that carries no
 * sentence is rethrown instead of being narrated, because the alternative is this client
 * composing prose about a condition it did not observe.
 */
function refusalOutcome(
  refusal: RoutingRefusal,
  err: unknown,
): { status: 'refused'; message: string; error: AnswerRoutingError } {
  if (refusal.message === null) throw err;
  return { status: 'refused', message: refusal.message, error: refusal.error };
}
