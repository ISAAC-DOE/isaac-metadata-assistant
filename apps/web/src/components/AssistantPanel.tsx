import './assistant.css';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare,
  ChevronRight,
  ChevronDown,
  UserCheck,
  Shield,
  CornerDownRight,
  CircleAlert,
  CircleDashed,
  CircleHelp,
  TriangleAlert,
  Check,
  X,
  type LucideIcon,
} from './icons';
import { LABELS } from '../lib/labels';
import {
  ASSISTANT_COMPOSER_HELPER,
  ASSISTANT_UNAVAILABLE,
  MEMORY_UNAVAILABLE_CAVEAT,
  SOURCE_LABELS,
  SUBORDINATE_CAPTION,
  hasVerdictLanguage,
} from '../lib/assistant';
import { classifyAnswer, type MessageKind } from '../lib/assistantConversation';
import {
  appendMessage,
  clearSession,
  loadSession,
  scrubForDisplay,
  type Msg,
} from '../lib/assistantSession';
import {
  DEGRADED_MESSAGE,
  INTENTS,
  confirmProposal,
  proposeForField,
  runIntent,
  type AgentContext,
  type AgentOpts,
  type ConfirmApi,
  type Proposal,
} from '../lib/assistantAgent';
import { api } from '../lib/api';
// P36V.1 Unit B — the CLOSED local action catalog. A free-form answer's wire
// action is resolved through it, so an unknown kind is dropped and the visible
// label + client route stay frontend-owned.
import { resolveAssistantAction } from '../lib/assistantComposer';
import type {
  AssistantGraphCapability,
  GraphProposal,
  GraphProposalChoice,
} from '../lib/graphCommands';
import type {
  AssistantAction,
  AssistantActionKind,
  AssistantMessage,
  AssistantQuerySource,
  AssistantSource,
  MemoryAvailability,
  SuggestedPrompt,
} from '../lib/types';

interface AssistantPanelProps {
  reply: AssistantMessage;
  prompts: SuggestedPrompt[];
  /**
   * Per-experiment (or per-surface) session key. The conversation log is loaded
   * from and appended to the P29.1 ephemeral session under this key. Optional
   * with a stable default so memory-less mounts still work.
   */
  experimentId?: string;
  /**
   * Current record revision. An assistant message whose `recordRev` differs is
   * marked STALE ("based on an earlier version") — never silently trusted. When
   * omitted, no message is marked stale.
   */
  recordRev?: number;
  /**
   * The primary memory-plane axis (P24.10): available vs unavailable — passed
   * ONLY by screens that actually fetch GET /api/graph/status. When OMITTED
   * (P25.7), the screen makes no memory-availability claim: the panel renders
   * neither the header STATUS ROW nor the memory caveat.
   *
   * This prop is NOT presentational. Independently of whether the status row is
   * visible, it drives BOTH the memory caveat (`MEMORY_UNAVAILABLE_CAVEAT`) and
   * `classifyAnswer(answeredFrom, availability)` — a graph-sourced answer is
   * `degraded` when memory is unavailable and `advisory` when it is available.
   * A screen that knows the axis must therefore always pass it; suppressing the
   * VISIBLE row is a separate decision (see `showAvailabilityStatus`). Nothing
   * here is ever fabricated or defaulted.
   */
  availability?: MemoryAvailability;
  /**
   * P33 HQA #7, restored at P36V S-A review — whether THIS panel renders the
   * VISIBLE availability status row. Presentation only: it never changes how
   * `availability` is used for `classifyAnswer` or for the memory caveat.
   *
   * There are three meaningful states, and all three exist in the app:
   *
   *   (a) `availability` given, `showAvailabilityStatus` true (the DEFAULT) —
   *       the mount knows the axis and the panel is its SOLE visible owner.
   *       Record Workbench and Export Readiness: neither renders a
   *       `GraphStatusChip`, so the panel must state it or nobody does.
   *   (b) `availability` given, `showAvailabilityStatus={false}` — the mount
   *       knows the axis and still needs it for classification/caveat, but the
   *       PAGE already owns the visible label. Project Memory (where the chip is
   *       the page's subject) and Evidence Explorer (status-bar chip). Without
   *       this state the identical fact is stated twice, and — because the chip's
   *       accessible name is "Project memory available — memory plane, advisory
   *       only, never a validator" while this row's is its visible text — a
   *       screen reader hears ONE axis in TWO different wordings.
   *   (c) `availability` omitted — the mount cannot truthfully know the axis
   *       (Guided Completion loads only {detail, pending} and consults no graph),
   *       so nothing is rendered and no status is invented. This flag is then
   *       irrelevant: there is no state to show or suppress.
   */
  showAvailabilityStatus?: boolean;
  /** Optional subordinate note, e.g. "truth questions route to the CLI…". */
  note?: string;
  /**
   * P34.4 — which free-form query endpoint the composer submits to. `'record'`
   * (default) POSTs to the per-experiment resolver (`api.askAssistant`), used by
   * the four RECORD surfaces that each pass a real `experimentId`. `'memory'`
   * POSTs to the record-agnostic Project-Memory resolver (`api.askMemory`), used
   * by the Project Memory surface, which has NO record: a project-memory question
   * is answered from the memory reader; any record question is honestly refused
   * server-side. In memory scope the answer carries no numeric `record_rev`, so no
   * stale badge / Ask-again ever appears. Everything else — rendering, provenance
   * chips, follow-ups, session, empty state, Clear — is identical across scopes.
   */
  queryScope?: 'record' | 'memory';
  /**
   * P29.4 — the LIVE P29.3 AgentContext from the shared record-session owner
   * (`useRecordSession`), bound to the SAME authoritative version/revision the
   * manual workflow reads. Optional so memory-less / non-record mounts still
   * work. Threaded so the assistant reasons over the current record state (and a
   * confirm flow can be gated on it) rather than a stale snapshot.
   */
  agentContext?: AgentContext;
  /**
   * P29.4 — the AgentContext is degraded (its authoritative inputs failed to
   * load, or could not be verified). The assistant then shows an HONEST degraded
   * state and does not answer dataset-specific questions — but the manual
   * workflow on the screen stays fully functional (manual-first degradation).
   */
  degraded?: boolean;
  /**
   * P29.4b — the INTENT pills the screen surfaces. Each RUNS a real P29.3 intent
   * (`runIntent`) against the live `agentContext`; the result is appended to the
   * conversation. Only entries whose `intent` is in the frozen `INTENTS` registry
   * render — an unrecognised intent is never surfaced. Labels are repository-native
   * Title Case (never a raw intent id). Rendered only when `agentContext` exists.
   */
  agentPrompts?: AgentPrompt[];
  /**
   * P29.4b — a single STAGED proposal (a user-supplied value awaiting explicit
   * confirmation), rendered as a distinct UNCONFIRMED card. Nothing about
   * displaying it mutates the record; only an explicit Confirm writes, and only
   * ever through `confirmProposal`.
   */
  proposal?: Proposal;
  /**
   * P29.4b — the shared-session `refresh()` (from `useRecordSession`). Called
   * after a SUCCESSFUL confirm so the shared state (manual fields, workflow,
   * evidence, export readiness) recalculates, and offered as Re-Evaluate on a
   * stale proposal.
   */
  onRefresh?: () => void;
  /**
   * P29.4b — the mutation surface `confirmProposal` writes through (submitAnswer /
   * editField). Injectable for tests; defaults to the real `api` client. The panel
   * NEVER calls these directly — the ONLY write path is `confirmProposal`.
   */
  confirmApi?: ConfirmApi;
  /**
   * P29.6 — the CURRENT pending field the assistant may offer to STAGE an answer
   * for (the guided-completion S4 surface passes its active question here). When
   * present with a `suggestedValue` (and the live context is healthy, and no
   * proposal is already staged) a narrow "Stage Answer" affordance renders: the
   * user SELECTS the labeled synthetic suggestion (reusing GuidedPrompt's "Use
   * This Suggestion" value entry — NOT a freeform chat composer, so the assistant
   * stays guided-prompts + one narrow staging button, never a fake chatbot), and
   * it is routed through the GUARDED `proposeForField(..., source:'user')` to
   * create the SAME unconfirmed ProposalCard as every other staged value. The
   * assistant never INVENTS a value to stage: with no `suggestedValue` there is no
   * trigger (never a blanket write). It stages exactly ONE named field and confirms
   * through the existing `confirmProposal` path — it never infers another field.
   */
  stageField?: StageFieldOption;
  /**
   * P36R S5 — the OPT-IN graph capability. Passed by exactly ONE mount in this
   * phase (Project Memory, and only while its Graph tab is showing); the four
   * record surfaces pass nothing, so their behaviour is byte-identical to
   * before — there is no code path here that runs without this prop.
   *
   * When present, a submitted question is first offered to a bounded,
   * deterministic, OFFLINE classifier (`lib/graphCommands.ts`). No LLM, no
   * model provider, no embedding, no vector search, no network: it is literal
   * pattern matching over a frozen intent catalog. A recognised question is
   * answered from the already-fetched projection and produces a PROPOSAL — the
   * graph is not touched until the user presses "Apply to Graph". Anything the
   * catalog does not recognise returns null and falls through to the existing
   * read-only resolver, unchanged.
   */
  graphCapability?: AssistantGraphCapability;
}

/**
 * P29.6 — the current pending field + the labeled synthetic value the assistant
 * may offer to stage for it. `suggestedValue` is the SAME demo answer the manual
 * GuidedPrompt exposes via "Use This Suggestion" — the assistant never fabricates
 * one; absent ⇒ no staging trigger.
 */
export interface StageFieldOption {
  id: string;
  label: string;
  suggestedValue?: unknown;
  suggestedValueLabel?: string;
}

/**
 * One INTENT pill: a typed P29.3 intent + a repository-native Title Case label
 * (+ optional opts to target a field/step). The panel filters these to the
 * frozen `INTENTS` registry before rendering.
 */
export interface AgentPrompt {
  intent: string;
  label: string;
  opts?: AgentOpts;
}

// Evidence-plane intents answer "from the record's evidence"; step/workflow
// intents answer "from the workflow". Both map to advisory presentation kinds.
const EVIDENCE_INTENTS = new Set([
  'review_field_evidence',
  'show_inferred_candidates',
  'review_evidence_conflicts',
  'explain_unknown',
]);

// Evidence-support classification → repository-native Title Case label + glyph.
// A candidate/unknown NEVER wears the confirmed check (color is never the only
// signal — icon + text carry the distinction).
const CLASS_META: Record<string, { label: string; Icon: LucideIcon }> = {
  supported: { label: LABELS.chipEvSupported, Icon: Check },
  inferred_candidate: { label: LABELS.chipEvCandidate, Icon: CornerDownRight },
  insufficient_evidence: { label: LABELS.chipEvInsufficient, Icon: CircleAlert },
  conflicting_evidence: { label: LABELS.chipEvConflicting, Icon: TriangleAlert },
  unknown: { label: LABELS.chipEvUnknown, Icon: CircleHelp },
};

const DEFAULT_SESSION_KEY = '__assistant__';

// P33 HQA (#6) — the memory-availability head label, rendered in Title Case
// (never the raw lowercase state). Keyed on the same `MemoryAvailability` axis
// passed to the panel, so the head text stays in lockstep with the classifier.
const MEMORY_HEAD_LABEL: Record<MemoryAvailability, string> = {
  available: 'Memory Available',
  unavailable: 'Memory Unavailable',
};

// P36V — id of the proposed-action eyebrow, used as that region's
// `aria-labelledby` so its accessible name is exactly its visible text.
const PROPOSED_EYEBROW_ID = 'assistant-proposed-eyebrow';

// P36V (review, M1) — the same pattern for the Related Questions group: the
// group is named BY its visible eyebrow rather than by a detached `aria-label`
// duplicating the same words, which a screen reader would announce twice.
const FOLLOWUPS_EYEBROW_ID = 'assistant-followups-eyebrow';

// The safe replacement rendered whenever a would-be verdict string reaches the
// panel — the assistant explains and routes; it never states PASS/FAIL.
const VERDICT_ROUTE_TEXT =
  'That is a truth question — open the Validate surface for the deterministic verdict.';

// P34.2 — the accessible in-flight label announced in the single live region
// while a read-only grounded query is resolving.
const WORKING_LABEL = 'Working…';

// P36R S2 — the resting-state guidance, shown ONLY in the empty state (there is
// no conversation yet). It is deliberately distinct copy from the composer's
// persistent helper (ASSISTANT_COMPOSER_HELPER) so the same sentence is never
// rendered twice, and it claims nothing the panel cannot do.
const EMPTY_STATE_GUIDANCE = 'Pick a suggestion below, or ask your own question in the box at the bottom.';

// P36R S2 — the disclosure label for the Suggested Questions + Agent Actions
// controls once a conversation exists. They collapse (never disappear); the
// composer stays visible at all times, so asking again is never hidden.
const MORE_DISCLOSURE_LABEL = 'Suggested Questions & Agent Actions';

// P36V S-A — the visible Title-Case label for an ANSWER's own follow-ups. It is
// deliberately different from the global "Suggested Questions" control group:
// these belong to one specific answer and are rendered inside its bubble.
const RELATED_QUESTIONS_LABEL = 'Related Questions';

// P36V.1 Unit B — the visible Title-Case label of the collapsed disclosure holding
// the EXACT validation locators. Everything technical the humanized answer no
// longer shows inline (including the deterministic validator's literal `$` root
// marker) lives behind this one control, so nothing is hidden from the reader who
// wants it and nothing raw is pushed at the reader who does not.
const TECHNICAL_DETAILS_LABEL = 'Technical Details';

// P34.5 — a defensive client-side ceiling so a hung read-only query can never
// leave the composer stuck in `loading` forever. On timeout the query REJECTS,
// which flows through the SAME catch as any network error → the composer
// re-enables and the honest "unavailable" turn renders. This adds no
// cancellation/streaming UI (Decision #7): it only bounds the wait.
const QUERY_TIMEOUT_MS = 20000;

// Reject `p` if it has not settled within `ms`. The timer is cleared on settle
// so a resolved query leaves no dangling timeout; a late resolution after the
// timeout is discarded (the race has already rejected).
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('assistant query timed out')), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

// Message-kind presentation (icon + label + palette class). Each kind is
// distinguishable by ICON + TEXT, never color alone (project a11y rule).
const KIND_META: Record<MessageKind, { label: string; Icon: LucideIcon; className: string }> = {
  'deterministic-result': {
    label: 'From Deterministic Checks',
    Icon: Shield,
    className: 'kind-badge-deterministic',
  },
  advisory: { label: 'Advisory', Icon: MessageSquare, className: 'kind-badge-advisory' },
  'inferred-candidate': {
    label: 'Inferred Candidate',
    Icon: CornerDownRight,
    className: 'kind-badge-inferred',
  },
  'confirmation-request': {
    label: 'Needs Your Confirmation',
    Icon: CircleAlert,
    className: 'kind-badge-confirm',
  },
  degraded: { label: 'Memory Unavailable', Icon: CircleDashed, className: 'kind-badge-degraded' },
};

// P34.3 — a source's `navigate_to` is followed ONLY when it is a known in-app
// client route (the record workbench, the memory plane, or — P36V S-B — the
// governance plane that hosts the deterministic Validator). Anything else — an
// absolute server path, an external URL, a bare token — is rendered as a plain,
// non-navigating label chip. This is the render-time complement to the session
// sanitizer, which strips any '/'-prefixed string on persistence: nav targets
// are never persisted, only followed live for an explicitly-allowlisted route.
//
// The allowlist is what makes the P36V S-B Open Validator action safe by the
// same rule as every cited source: an action whose `to` is not allowlisted is
// never rendered as a navigating control.
function isClientRoute(nav: string | null | undefined): nav is string {
  return (
    typeof nav === 'string' &&
    (nav.startsWith('/record') || nav.startsWith('/memory') || nav.startsWith('/governance'))
  );
}

let msgSeq = 0;
function uid(): string {
  msgSeq += 1;
  return `m${Date.now().toString(36)}-${msgSeq}`;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

const NEAR_BOTTOM_PX = 64;

/**
 * Conversation-style assistant (P29.2; re-laid-out P36R S2; presentation
 * contract re-specified P36V S-A; header + scroll contract P36V.1). Layout
 * top→bottom:
 *
 *   HEADER        ONE balanced row — LEFT: the chat icon + the "Assistant"
 *                 title; RIGHT: the availability status (dot + Title-Case
 *                 label), pushed to the header's right edge. Beneath that row,
 *                 and only once there IS a conversation to clear, a compact
 *                 right-aligned ACTION row holding "Clear Conversation" — never
 *                 between the title and the status. With no conversation the
 *                 action row is `:empty` and collapses, reserving no space.
 *   DEGRADED      the honest, manual-first degraded notice
 *   BODY          flex:1 / min-height:0 / overflow-y:auto — the region that
 *                 absorbs the rail height AND the panel's scrollport: its
 *                 content is clipped and scrolled here, so it can never spill
 *                 under the opaque sticky dock below
 *                   · EMPTY STATE (no conversation): one guidance sentence +
 *                     Suggested Questions + a subtle divider
 *                   · CONVERSATION (a conversation exists): the bounded,
 *                     scrollable conversation region (older → newest, newest at
 *                     the BOTTOM, live turn last)
 *   PROPOSED      StageAnswer / ProposalCard — a distinct proposed-ACTION region,
 *                 never a chat message, directly above the composer
 *   FOOT          the sticky dock, in order:
 *                   COMPOSER    directly beneath the transcript, always reachable
 *                   CONTROLS    empty state → Agent Actions; conversation →
 *                               Suggested Questions + Agent Actions collapsed
 *                               into ONE compact disclosure (never between the
 *                               transcript and the composer)
 *                   FOOTER      the single italicised advisory caption
 *
 * The panel presents the P29.1 ephemeral session as a conversation and preserves
 * every honesty guard: `Source:` beneath the response it supports, the
 * composer's persistent grounded-scope helper, the memory-availability caveat,
 * and the verdict-language guard over ALL rendered assistant text. It explains
 * and points to sources — it never renders a verdict, never mutates a record
 * from the composer, and `confirmProposal` remains the ONLY write path.
 */
export function AssistantPanel({
  prompts,
  experimentId = DEFAULT_SESSION_KEY,
  recordRev,
  availability,
  showAvailabilityStatus = true,
  note,
  queryScope = 'record',
  agentContext,
  degraded = false,
  agentPrompts,
  proposal: proposalProp,
  onRefresh,
  confirmApi = api,
  stageField,
  graphCapability,
}: AssistantPanelProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>(() => loadSession(experimentId).messages);
  const [showJump, setShowJump] = useState(false);

  // P34.2 — the unified "current live turn". `liveAnswer` is the single answer
  // shown in the live region below the log; `liveQuestion` is the question that
  // produced it (archived alongside it when the turn scrolls into history).
  // `loading` is true while the read-only grounded query is in flight. When
  // `liveAnswer` is null and not loading, the region shows the resting empty
  // state (never an auto-announced pending-summary card).
  const [liveAnswer, setLiveAnswer] = useState<Msg | null>(null);
  const [liveQuestion, setLiveQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // P34.2 — the composer input's LOCAL transient text (never persisted itself).
  // On submit it is sent to the READ-ONLY grounded resolver (POST /assistant/query)
  // and cleared; it is never written to the session/storage as raw input.
  const [composerText, setComposerText] = useState('');

  // P29.4b — the live staged proposal, seeded from the prop and owned locally so
  // Cancel can clear it and a stale/412 confirm can mark it. The record is never
  // mutated by holding or displaying it.
  const [proposal, setProposal] = useState<Proposal | null>(proposalProp ?? null);
  const [confirming, setConfirming] = useState(false);

  // P36R S5 — the current UNAPPLIED graph-navigation proposal. Holding it (or
  // rendering it) changes nothing: only the explicit "Apply to Graph" control
  // calls `graphCapability.apply`.
  const [graphProposal, setGraphProposal] = useState<GraphProposal | null>(null);

  // An unapplied proposal belongs to the surface it was resolved against. When
  // the capability is withdrawn — the Graph tab stopped showing, so the mounted
  // graph and its index are gone — the proposal goes with it. Without this it
  // survived the tab excursion and was re-offered on return against a DIFFERENT
  // GraphSurfaceContext, with counts derived from a state that no longer exists.
  // Dropping it applies nothing; the graph was never touched.
  useEffect(() => {
    if (!graphCapability) setGraphProposal(null);
  }, [graphCapability]);

  const logRef = useRef<HTMLDivElement | null>(null);
  const replyRef = useRef<HTMLParagraphElement | null>(null);
  // P34.5 — the composer input, so focus can return to it after Clear (the Clear
  // button unmounts when the log empties; focus must land somewhere sensible, not
  // be lost to <body>).
  const composerInputRef = useRef<HTMLInputElement | null>(null);
  const nearBottomRef = useRef(true);
  const mountedRef = useRef(false);
  const focusPendingRef = useRef(false);
  // Focus the NEWEST log message after an agent run / confirm summary.
  const focusNewestRef = useRef(false);
  // Synchronous re-entrancy guard: a second Confirm click in the same tick sees
  // this before React has re-rendered the disabled button (no double-submit).
  const confirmingRef = useRef(false);

  // Seed the local proposal from the prop, and reset it when the surface changes.
  // A proposal is always re-derived from the prop for the CURRENT experiment, so
  // a proposal from a previous experiment never lingers.
  useEffect(() => {
    setProposal(proposalProp ?? null);
  }, [proposalProp, experimentId]);

  // Reload the conversation when the surface (experiment) changes; the active
  // pill + follow-scroll baseline reset with it.
  useEffect(() => {
    setMessages(loadSession(experimentId).messages);
    setActiveIndex(null);
    setLiveAnswer(null);
    setLiveQuestion(null);
    setLoading(false);
    mountedRef.current = false;
    nearBottomRef.current = true;
  }, [experimentId]);

  const scrollToBottom = useCallback(() => {
    const el = logRef.current;
    if (!el) return;
    const behavior: ScrollBehavior = prefersReducedMotion() ? 'auto' : 'smooth';
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ top: el.scrollHeight, behavior });
    } else {
      el.scrollTop = el.scrollHeight;
    }
    nearBottomRef.current = true;
    setShowJump(false);
  }, []);

  const onScroll = useCallback(() => {
    const el = logRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
    nearBottomRef.current = near;
    if (near) setShowJump(false);
  }, []);

  // Respectful auto-scroll: jump to newest on open; afterwards follow only when
  // the reader is already near the bottom, otherwise surface "Jump to Latest".
  useEffect(() => {
    if (!logRef.current) return;
    if (!mountedRef.current) {
      mountedRef.current = true;
      scrollToBottom();
      return;
    }
    if (nearBottomRef.current) scrollToBottom();
    else setShowJump(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length, activeIndex, liveAnswer]);

  // Move focus to the fresh reply after a submission (never during a poll). Fires
  // when a pill swaps the live answer, when a free-form query resolves (liveAnswer
  // changes / loading clears), or when the archived history advances.
  useEffect(() => {
    if (focusPendingRef.current && !loading) {
      focusPendingRef.current = false;
      replyRef.current?.focus();
    }
  }, [activeIndex, messages.length, liveAnswer, loading]);

  // After an agent intent run / confirmed summary, move focus into the log to the
  // newest message so keyboard + screen-reader users land on the fresh result.
  useEffect(() => {
    if (!focusNewestRef.current) return;
    focusNewestRef.current = false;
    const log = logRef.current;
    if (!log) return;
    // The CURRENT turn's question bubble (`.assistant-msg-live`) is excluded: the
    // fresh result to land on is the newest ARCHIVED message, not the echo of the
    // question the reader already asked.
    const msgs = log.querySelectorAll('.assistant-msg:not(.assistant-msg-live)');
    (msgs[msgs.length - 1] as HTMLElement | undefined)?.focus();
  }, [messages.length]);

  // Append a deterministic assistant message to the ephemeral session and reflect
  // it. Every write goes through `appendMessage`, whose P29.1 sanitizer scrubs
  // secrets/paths/verdict fields BEFORE persistence — so nothing unsafe is stored,
  // and the log is re-read from the sanitized session (nothing unsafe is rendered).
  const appendAgentMessage = useCallback(
    (text: string, source: AssistantSource, rev: number | undefined) => {
      const cls = classifyAnswer(source, availability);
      appendMessage(experimentId, {
        role: 'assistant',
        text,
        answeredFrom: source,
        recordRev: rev,
        resultType: cls.resultType,
        authority: cls.authority,
        actionability: cls.actionability,
        id: uid(),
        timestamp: Date.now(),
      });
      setMessages(loadSession(experimentId).messages);
      focusNewestRef.current = true;
    },
    [experimentId, availability],
  );

  // Run ONE typed intent against the live context. Pure (no fetch, no mutation) —
  // the result is appended chronologically, version-bound to the rev it ran
  // against so it is later marked stale if the record advances. Refuses when the
  // context is absent, unsupported, or degraded (manual-first: the composed UI
  // below still renders; only dataset-specific answering is withheld).
  function runAgentIntent(prompt: AgentPrompt) {
    if (!agentContext || degraded || agentContext.degraded) return;
    if (!INTENTS.includes(prompt.intent)) return;
    const result = runIntent(prompt.intent, agentContext, prompt.opts ?? {});
    const source: AssistantSource = EVIDENCE_INTENTS.has(prompt.intent) ? 'files' : 'workflow';
    appendAgentMessage(result.text, source, agentContext.recordRev);
  }

  // --- proposal staleness (a proposal is actionable ONLY when it is grounded in
  // the CURRENT, verified revision of the SAME experiment) --------------------
  const proposalStale =
    !!proposal &&
    (proposal.confirmationState === 'stale' ||
      !agentContext ||
      degraded ||
      agentContext.degraded === true ||
      proposal.experimentId !== agentContext.experimentId ||
      proposal.sourceRev !== agentContext.recordRev);

  // Confirm — the ONLY write path, routed through `confirmProposal`. Re-entrancy
  // guarded (one submit), refuses a stale proposal, sends the current version as
  // If-Match. On ok → refresh the shared state + append a confirmed summary. On
  // stale/conflict (incl. a backend 412) → mark stale, explain, NO retry / merge.
  async function onConfirm() {
    if (!proposal || !agentContext) return;
    if (confirmingRef.current) return; // no double-submit
    if (proposalStale) return; // a stale proposal cannot be confirmed
    confirmingRef.current = true;
    setConfirming(true);
    try {
      const res = await confirmProposal(proposal, agentContext, confirmApi);
      if (res.status === 'ok') {
        setProposal(null);
        appendAgentMessage(
          `Confirmed "${proposal.field}". Your value was sent to the record with the current ` +
            `version as If-Match, through the confirmation path. The deterministic audit and ` +
            `export gate recalculate from the updated record.`,
          'workflow',
          agentContext.recordRev,
        );
        onRefresh?.();
      } else {
        // stale (refused before any api touch) OR conflict (a backend 412).
        setProposal(res.proposal ?? { ...proposal, confirmationState: 'stale' });
        appendAgentMessage(
          `That value could not be confirmed — the record changed since it was proposed. ` +
            `Nothing was written and nothing was merged. Re-evaluate against the current record ` +
            `before confirming again.`,
          'workflow',
          agentContext.recordRev,
        );
      }
    } finally {
      confirmingRef.current = false;
      setConfirming(false);
    }
  }

  // P36R S5 — the ONE place a graph proposal is applied, behind an explicit
  // click. It runs the SAME `GraphAction`s the equivalent typed command
  // produces, through the graph surface's own reducer. It writes nothing to any
  // record: `confirmProposal` remains the only write path in this panel.
  function onApplyGraphProposal() {
    if (!graphCapability || !graphProposal) return;
    if (graphProposal.status !== 'ready' || graphProposal.actions.length === 0) return;
    const applied = graphProposal;
    graphCapability.apply(applied);
    setGraphProposal(null);
    appendAgentMessage(
      `Applied to the graph: ${applied.command ?? applied.title}. This changed the view only — ` +
        `no record, evidence entry, or export decision was touched.`,
      'graph',
      undefined,
    );
  }

  // Picking one bounded candidate REPLACES the proposal with the same
  // navigation resolved to that node/cluster. Still unapplied.
  function onPickGraphChoice(choice: GraphProposalChoice) {
    setGraphProposal(choice.proposal);
    setLiveAnswer((prev) =>
      prev
        ? { ...prev, text: choice.proposal.explanation, id: uid(), timestamp: Date.now() }
        : prev,
    );
    focusPendingRef.current = true;
  }

  // Cancel — no mutation. Clears the proposal and restores focus to the reply.
  function onCancelProposal() {
    setProposal(null);
    replyRef.current?.focus();
  }

  // Archive the current live turn (its question, if any, then its answer) into the
  // ephemeral session log — exactly as a pill swap does — so the previous answer
  // scrolls into history when a new turn begins. A null live answer (the resting
  // empty state) archives nothing.
  function archiveLive() {
    if (!liveAnswer) return;
    if (liveQuestion) {
      appendMessage(experimentId, {
        role: 'user',
        text: liveQuestion,
        recordRev,
        id: uid(),
        timestamp: Date.now(),
      });
    }
    appendMessage(experimentId, {
      role: 'assistant',
      text: liveAnswer.text,
      // R2 — a refusal turn (empty grounding) is archived WITHOUT an
      // `answeredFrom`, so the archived message likewise hides the misleading
      // `answered from:` line; every other turn keeps its real source.
      answeredFrom: liveAnswer.hasGrounding === false ? undefined : liveAnswer.answeredFrom,
      recordRev: typeof liveAnswer.recordRev === 'number' ? liveAnswer.recordRev : recordRev,
      resultType: liveAnswer.resultType,
      authority: liveAnswer.authority,
      actionability: liveAnswer.actionability,
      id: uid(),
      timestamp: Date.now(),
    });
    setMessages(loadSession(experimentId).messages);
  }

  // Submit a FREE-FORM question to the READ-ONLY grounded resolver. This is the
  // ONLY network path the composer touches — a non-mutating POST /assistant/query
  // that never writes the record and never calls submitAnswer / editField /
  // confirmProposal / export / reset. The prior live turn is archived first; on
  // success the answer becomes the new live turn, on an ApiError an honest
  // "unavailable" turn does (the rest of the workspace stays fully usable).
  async function submitQuestion(text: string) {
    const question = text.trim();
    if (question === '' || loading) return; // empty is a no-op; guard overlapping submits

    // P36R S5 — bounded graph-intent interception, BEFORE any network call and
    // only when this mount opted in. `classify` is pure, offline and literal
    // pattern matching over a frozen catalog; it returns null for anything it
    // does not confidently recognise, and the unchanged resolver path below
    // then runs. A miss is deliberately preferred to hijacking a memory
    // question. Recognition produces a PROPOSAL — the graph is untouched.
    const graphIntent = graphCapability?.classify(question) ?? null;
    if (graphIntent) {
      archiveLive();
      setLiveQuestion(question);
      setActiveIndex(null);
      setComposerText('');
      setGraphProposal(graphIntent);
      const cls = classifyAnswer('graph', availability);
      setLiveAnswer({
        role: 'assistant',
        text: graphIntent.explanation,
        answeredFrom: 'graph',
        hasGrounding: true,
        resultType: cls.resultType,
        authority: cls.authority,
        actionability: cls.actionability,
        id: uid(),
        timestamp: Date.now(),
      });
      focusPendingRef.current = true;
      return;
    }
    setGraphProposal(null);
    archiveLive();
    setLiveQuestion(question);
    setActiveIndex(null);
    setComposerText('');
    setLoading(true);
    try {
      // P34.4 — the ONE composer, TWO read-only scopes: the record surfaces query
      // the per-experiment resolver; the record-less Project Memory surface queries
      // the record-agnostic memory resolver. Both are non-mutating and return the
      // SAME response shape (the memory answer simply carries a null record_rev).
      const resp = await withTimeout(
        queryScope === 'memory'
          ? api.askMemory({ question })
          : api.askAssistant(experimentId, { question }),
        QUERY_TIMEOUT_MS,
      );
      const source = (resp.grounding[0] ?? 'workflow') as AssistantSource;
      const cls = classifyAnswer(source, availability);
      setLiveAnswer({
        role: 'assistant',
        text: resp.answer,
        answeredFrom: source,
        // R2 — an honest refusal returns EMPTY grounding; track it so the
        // misleading `answered from:` line is not rendered (there is no real
        // source to attribute). A normally-grounded free-form answer sets `true`.
        hasGrounding: resp.grounding.length > 0,
        // A null rev (memory scope) becomes undefined so the stale guard
        // (`typeof recordRev === 'number'`) is never satisfied — no stale badge.
        recordRev: resp.record_rev ?? undefined,
        resultType: cls.resultType,
        authority: cls.authority,
        actionability: cls.actionability,
        // Richer presentation-safe fields stashed for P34.3 to render later. If
        // this turn is ever archived, the session sanitizer drops anything unsafe.
        sources: resp.sources,
        result: resp.result,
        followups: resp.followups,
        version: resp.version,
        // P36V.1 Unit B — the free-form answer's OPTIONAL bounded navigation
        // action, resolved through this build's CLOSED catalog: the wire supplies
        // the `kind`, the frontend supplies the label and the client route the
        // router resolves under its `basename`. An unknown/absent kind yields
        // undefined and no control is offered. Before this slice the response had
        // no action field at all, so a free-form answer could not render the
        // working Open Validator control — the backend instead cited a chip
        // labelled "Open Validate" pointing at the record already on screen.
        action: resolveAssistantAction(resp.action),
        // P36V.1 Unit B — the EXACT validation locators for the collapsed
        // Technical Details disclosure. This is the ONLY place the truth core's
        // raw `$` root marker surfaces; the answer text carries the humanized
        // location phrases instead.
        technicalPaths: resp.technical_paths ?? undefined,
        id: uid(),
        timestamp: Date.now(),
      });
    } catch {
      setLiveAnswer({
        role: 'assistant',
        text: ASSISTANT_UNAVAILABLE,
        answeredFrom: 'workflow',
        id: uid(),
        timestamp: Date.now(),
      });
    } finally {
      setLoading(false);
      focusPendingRef.current = true;
    }
  }

  function onComposerSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void submitQuestion(composerText);
  }

  // Clear the whole ephemeral conversation for this experiment and return to the
  // resting empty state. Session-only — it touches no record/truth state.
  function clearConversation() {
    clearSession(experimentId);
    setMessages([]);
    setLiveAnswer(null);
    setLiveQuestion(null);
    setActiveIndex(null);
    // An unapplied graph proposal goes with the conversation that produced it.
    // Dropping it applies nothing — the graph was never touched.
    setGraphProposal(null);
    // P36V S-A (bug fix) — the STAGED, unconfirmed proposal is ephemeral
    // conversation state too, and it used to SURVIVE a Clear: the panel returned
    // to its resting empty state while an unconfirmed ProposalCard still sat
    // above the composer, offering a Confirm bound to a conversation the reader
    // had just discarded. Dropping it writes nothing — exactly the same no-op as
    // Cancel (`onCancelProposal`); `confirmProposal` remains the only write path,
    // and the record / workflow / Project Memory state is untouched.
    setProposal(null);
    // P34.5 — the Clear button unmounts with the now-empty log, so move focus to
    // the always-present composer input rather than letting it fall to <body>.
    composerInputRef.current?.focus();
  }

  const agentActive = !!agentContext && !degraded && !agentContext.degraded;

  // The narrow staging affordance shows only for the CURRENT pending field, only
  // when the live context is healthy, only when a synthetic suggested value exists
  // to stage (the assistant never invents one), and only when no proposal is
  // already staged (one staged value at a time). Omitting `stageField` — or a field
  // with no `suggestedValue` — disables it entirely (never a blanket write).
  const canStage =
    agentActive && !!stageField && stageField.suggestedValue !== undefined && !proposal;

  // P29.6 — STAGE the current field's synthetic suggested value as a focused USER
  // answer. It is routed through the GUARDED `proposeForField` (source:'user'),
  // which labels it user-provided, never auto-classifies it as evidence-supported,
  // binds it to the current revision, and returns a PENDING proposal — never a
  // write. Displaying the resulting card mutates nothing; only an explicit Confirm
  // writes, through the SAME `confirmProposal` path.
  function onStageUserAnswer() {
    if (!agentContext || !canStage || !stageField) return;
    const staged = proposeForField(agentContext, {
      field: stageField.id,
      value: stageField.suggestedValue,
      source: 'user',
    });
    if (staged) setProposal(staged);
  }
  const shownAgentPrompts = agentContext
    ? (agentPrompts ?? []).filter((p) => INTENTS.includes(p.intent))
    : [];

  // The live current turn's text, verdict-guarded. A query in flight → an
  // accessible "Working…"; a resolved answer → its guarded text; otherwise
  // EMPTY (P36.1) — no resting placeholder text. The surrounding composer,
  // suggested prompts, and agent actions already make the panel's purpose
  // obvious, so the rail shows nothing until there is something to say. The
  // auto-reply fallback (compose().reply) was REMOVED at P34.2 — the resting
  // rail never announces a pending-summary card.
  const liveText = loading
    ? WORKING_LABEL
    : liveAnswer
      ? hasVerdictLanguage(liveAnswer.text)
        ? VERDICT_ROUTE_TEXT
        : liveAnswer.text
      : '';

  // P36.1 — true only at rest (not loading, no live answer yet). Drives the
  // `assistant-reply--empty` modifier that strips the visible card chrome
  // (padding/border/background) so an empty live region reads as nothing —
  // no bordered box, no awkward gap — while staying MOUNTED with
  // aria-live="polite" so it still announces the next "Working…"/answer.
  const liveReplyEmpty = !loading && !liveAnswer;

  // Only a screen that actually fetched graph status may make a memory claim. The
  // caveat is driven by `availability` INDEPENDENTLY of the empty/answer state;
  // it is de-duped when it would be byte-identical to the live text.
  const caveat =
    availability === 'unavailable' && MEMORY_UNAVAILABLE_CAVEAT !== liveText
      ? MEMORY_UNAVAILABLE_CAVEAT
      : undefined;

  // P34.3 — the live answer is STALE when it was grounded in an older record
  // revision than the current one (mirrors ConversationMessage's rule exactly). A
  // record change NEVER auto-refetches — the answer is simply marked stale and an
  // explicit "Ask again" re-queries at the current rev. Present only for a real
  // resolved answer that carries a numeric rev (the unavailable turn carries none).
  const liveStale =
    !!liveAnswer &&
    typeof liveAnswer.recordRev === 'number' &&
    typeof recordRev === 'number' &&
    liveAnswer.recordRev !== recordRev;

  // The cited sources + suggested follow-ups stashed on the live turn (P34.2).
  // Both are presentation-only and route through the SAME read-only paths.
  const liveSources = (liveAnswer?.sources as AssistantQuerySource[] | undefined) ?? [];
  const liveFollowups = (liveAnswer?.followups as string[] | undefined) ?? [];
  const staleDescId = liveStale ? 'assistant-live-stale' : undefined;

  // P36V.1 Unit B — the EXACT validation locators behind a humanized blocker
  // answer. The primary answer text never shows the truth core's literal root
  // marker `$` (it says "the record itself"); the unmodified locator is preserved
  // here and rendered ONLY inside the collapsed Technical Details disclosure, so
  // the technical reader loses nothing. Filtered to usable strings so an empty or
  // non-string entry can never render a blank row. Live-turn only: the P29.1
  // session sanitizer's SAFE_KEYS allowlist drops `technicalPaths` on archive.
  const liveTechnicalPaths = ((liveAnswer?.technicalPaths as string[] | undefined) ?? []).filter(
    (p) => typeof p === 'string' && p.trim() !== '',
  );

  // P36V S-B — the OPTIONAL bounded NAVIGATION action the live answer offers.
  // Today the catalog holds exactly one: Open Validator. It is surfaced only
  //   · for a RESOLVED answer (never while loading — a control must never hang
  //     off "Working…");
  //   · when the answer actually CARRIES one. The composer attaches it to exactly
  //     the routed truth answers that used to append the retired prose sentence
  //     "Open Validate to run the deterministic schema check." — so no new
  //     condition surfaces it and no intent resolution changed;
  //   · when its target passes the SAME client-route allowlist every cited source
  //     must pass.
  // Deriving or rendering it mutates NOTHING: no record write, no validation run,
  // no validation result change. It is live-turn-only — the P29.1 session
  // sanitizer's SAFE_KEYS allowlist drops `action` on archive, so an answer that
  // scrolls into history never leaves a stale control above the composer.
  const rawLiveAction = liveAnswer?.action as AssistantAction | undefined;
  const liveAction =
    !loading && rawLiveAction && isClientRoute(rawLiveAction.to) ? rawLiveAction : undefined;

  // Clicking a pill "asks" that PRECOMPOSED question: the previous live turn is
  // archived into the log, the pill's static answer becomes the new live turn, and
  // focus moves to it. No fetch, no mutation — presentation + P29.1 session wiring
  // only. (Unifying pills onto the endpoint is deferred to P34.3.)
  function ask(index: number) {
    const prompt = prompts[index];
    if (!prompt?.answer) return; // disabled pill → never activatable
    if (index === activeIndex) return; // already showing
    archiveLive();
    const ans = prompt.answer;
    const cls = classifyAnswer(ans.answeredFrom, availability);
    setLiveQuestion(prompt.text);
    setLiveAnswer({
      role: 'assistant',
      text: ans.text,
      answeredFrom: ans.answeredFrom,
      // P36V S-B — carry the answer's OPTIONAL bounded navigation action onto the
      // live turn so the proposed-action region can offer it. Most answers carry
      // none; carrying it copies the REFERENCE to the shared descriptor, which is
      // frozen at its definition (`OPEN_VALIDATOR_ACTION`), so nothing here — and
      // nothing downstream — can mutate the navigation target.
      action: ans.action,
      // P36V.1 Unit B — the precomposed answer's exact validation locators, shown
      // only inside the collapsed Technical Details disclosure.
      technicalPaths: ans.technicalPaths,
      recordRev,
      resultType: cls.resultType,
      authority: cls.authority,
      actionability: cls.actionability,
      id: uid(),
      timestamp: Date.now(),
    });
    setActiveIndex(index);
    focusPendingRef.current = true;
  }

  // P36R S2 — a conversation EXISTS once there is archived history, a resolved
  // live turn, or a query in flight. It drives the BODY: at rest the panel shows
  // its empty state (guidance + Suggested Questions + Agent Actions); once a
  // conversation exists those controls collapse into a disclosure and the bounded
  // conversation region takes the available height. `loading` is included so the
  // layout does not flip back for the duration of an in-flight first question.
  const hasConversation = messages.length > 0 || !!liveAnswer || loading;

  // Clear is offered only when there IS something to clear. It clears the
  // ephemeral chat only — never any record/truth state — so it needs no
  // confirmation, and it lives in the header (keyboard-reachable, never between
  // the controls and the transcript).
  const canClear = messages.length > 0 || !!liveAnswer;

  // P36V S-A — the two control groups are now SEPARATE, because the empty state
  // and the conversation state place them differently: empty → Suggested
  // Questions ABOVE the composer, Agent Actions below it; conversation → both
  // collapsed into ONE compact disclosure below the composer (so nothing sits
  // between the transcript and the composer). Neither group is ever removed.
  const suggestedQuestionControls = (
    <>
      <div className="assistant-suggested-eyebrow eyebrow">{LABELS.suggestedQuestions}</div>
      <div className="assistant-prompts">
        {prompts.map((p, i) => (
          <button
            type="button"
            className={`assistant-prompt${activeIndex === i ? ' active' : ''}`}
            key={p.text}
            aria-pressed={activeIndex === i}
            disabled={!p.answer}
            onClick={() => ask(i)}
          >
            <span>{p.text}</span>
            <ChevronRight className="chev" size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        ))}
      </div>
    </>
  );

  // P29.4b — the INTENT pills. Each RUNS a real agent intent against the live
  // context; the result is appended to the conversation. Disabled while the
  // context is degraded/absent (manual-first: composed prompts stay live).
  const agentActionControls =
    shownAgentPrompts.length > 0 ? (
      <div className="assistant-agent-actions">
        <div className="assistant-suggested-eyebrow eyebrow">Agent Actions</div>
        <div className="assistant-agent-prompts">
          {shownAgentPrompts.map((p) => (
            <button
              type="button"
              className="assistant-agent-prompt"
              key={p.intent}
              data-intent={p.intent}
              disabled={!agentActive}
              onClick={() => runAgentIntent(p)}
            >
              <span>{p.label}</span>
              <ChevronRight className="chev" size={15} strokeWidth={2} aria-hidden="true" />
            </button>
          ))}
        </div>
      </div>
    ) : null;

  return (
    <section className="assistant" aria-label="Assistant (advisory)">
      <div className="assistant-head">
        <span className="assistant-icon" aria-hidden="true">
          <MessageSquare size={15} strokeWidth={2} />
        </span>
        {/* P36V.1 S2 — the header ROW. The title is the LEFT group (with the
            icon immediately before it); the availability status is the RIGHT
            group, pushed to the header's right edge by CSS. The reading order —
            "Assistant", then the status, then (below) Clear Conversation — is
            the DOM order, so a screen reader hears the same row a sighted reader
            sees. The status is no longer stacked under the title, and Clear
            Conversation no longer competes with it for the same corner: it drops
            to its own subordinate action row beneath (`.assistant-head-right`,
            `flex-basis: 100%`). */}
        <div className="assistant-head-titles">
          <span className="assistant-label">{LABELS.assistant}</span>
          {/* The status row renders only where BOTH are true: the mounting screen
              actually fetched GET /api/graph/status and passed `availability`
              (a mount that cannot truthfully know it — Guided Completion loads
              only {detail, pending} and consults no graph — renders NOTHING
              here; a status is never fabricated, defaulted, or assumed), AND the
              panel is the visible OWNER of that axis on the screen.

              Project Memory and Evidence Explorer each already render a
              page-level `GraphStatusChip` for this SAME axis, so they pass
              `showAvailabilityStatus={false}`: one fact, stated once, in one
              wording. They still pass `availability`, so `classifyAnswer` and
              the memory caveat are completely unaffected — see the prop docs for
              the three states. */}
          {availability && showAvailabilityStatus && (
            <span className="assistant-memory assistant-status-row">
              <span
                className={`dot dot-memory${availability === 'available' ? ' dot-memory-available' : ''}`}
                aria-hidden="true"
              />
              {MEMORY_HEAD_LABEL[availability]}
            </span>
          )}
        </div>
        <div className="assistant-head-right">
          {/* P36R S2 — Clear Conversation lives in the HEADER (never between the
              controls and the transcript). It wipes THIS experiment's ephemeral
              session and returns the rail to its resting empty state; it touches
              no record/truth state, so it needs no confirmation.
              P36V.1 S2 — it now sits on its OWN compact right-aligned row BENEATH
              the title + status row, so it can never be read as sitting between
              the title and the status. When there is nothing to clear this
              wrapper is empty and CSS `:empty` collapses it — no reserved space.
              P36V S-A — the VISIBLE label is the full "Clear Conversation"; the
              accessible name now comes from that same visible text (the previous
              aria-label="Clear conversation" both contradicted the visible
              "Clear" and differed in casing). */}
          {canClear && (
            <button type="button" className="assistant-clear" onClick={clearConversation}>
              <X size={13} strokeWidth={2} aria-hidden="true" />
              Clear Conversation
            </button>
          )}
        </div>
      </div>

      {/* P29.4 — honest, manual-first degraded state: when the live AgentContext
          cannot be verified the assistant says so plainly and answers no
          dataset-specific question. It NEVER disables the surrounding manual
          workflow — that is driven by the screen's own bundle, not this panel. */}
      {degraded && (
        <p className="assistant-degraded" role="status">
          {DEGRADED_MESSAGE}
        </p>
      )}

      {/* P36R S2 — the BODY absorbs the rail height (flex:1 / min-height:0) so the
          conversation region can flex instead of being clipped by a fixed height. */}
      <div className="assistant-body">
        {/* EMPTY STATE (P36V S-A order) — one concise guidance sentence, then
            Suggested Questions at full prominence, then a subtle divider marking
            the break before the composer below. Agent Actions move BELOW the
            composer (rendered in the foot). No filler card is added. */}
        {!hasConversation && (
          <div className="assistant-empty">
            <p className="assistant-empty-note">{EMPTY_STATE_GUIDANCE}</p>
            {suggestedQuestionControls}
            <div className="assistant-empty-divider" aria-hidden="true" />
          </div>
        )}

        {/* The conversation region (older → newest, newest at the BOTTOM, the live
            turn last). role="log" carries an IMPLICIT aria-live="polite"; we set
            aria-live="off" here to suppress it so archiving prior turns into the
            log does NOT announce them. The single live region is the current reply
            inside it — announced once, politely. It is the SAME element in both
            states (so the live region is never unmounted); only the
            `assistant-conversation` chrome — one restrained full border, an
            elevated white surface, and the bounded scroll — is added once there is
            a conversation to hold. */}
        <div
          className={`assistant-log${hasConversation ? ' assistant-conversation' : ' assistant-log--resting'}`}
          ref={logRef}
          role="log"
          aria-live="off"
          aria-label="Assistant conversation"
          onScroll={onScroll}
        >
          {messages.map((m, i) => (
            <ConversationMessage key={m.id ?? i} message={m} currentRev={recordRev} />
          ))}

          {/* P36R S2 — the CURRENT turn's question, shown as a user bubble above
              the answer it produced. Before this the live question was rendered
              nowhere until it archived, so the newest (and usually only visible)
              turn showed an answer with no visible question. It is display-only:
              the persisted copy still goes through `appendMessage`'s sanitizer on
              archive, and nothing here re-sends or re-stores the text. */}
          {liveQuestion && (loading || liveAnswer) && (
            <ConversationMessage
              live
              message={{ role: 'user', text: liveQuestion, id: 'assistant-live-question' }}
            />
          )}

          {/* The live current turn — the newest content, rendered below history.
              The single `.assistant-reply` <p> is the ONE live region (the log
              above is aria-live="off"): while a query resolves it announces
              "Working…" (aria-busy), then the resolved answer; at rest (P36.1) it
              renders EMPTY — no placeholder text, no card chrome — but stays
              MOUNTED so it keeps announcing future turns. Its provenance,
              staleness, and follow-ups all attach BENEATH it, inside this block —
              each attached to the response it supports. */}
          <div className="assistant-reply-block">
            {/* P36V S-A — the LIVE answer is now an unmistakable ASSISTANT BUBBLE,
                the same one an archived turn wears: left-aligned, subtle border,
                very light lavender surface (it sits inside the WHITE conversation
                region — R2 — so a white-on-white bubble would be invisible), with
                the assistant icon + the visible "Assistant" label. Before this it
                was a bare, border-less, label-less <p>, so the newest and most
                visible answer in the panel was the ONLY one with no attribution.
                No coloured left/right accent edge is used (P36R R3 /
                no-vertical-rail): the distinction is a full four-sided border +
                the icon + the text label.

                At rest the bubble collapses to nothing (`--empty`): no chrome and
                no "Assistant" label with no answer behind it. The `.assistant-reply`
                <p> inside is UNCHANGED as the single aria-live region — it stays
                mounted in both states so it keeps announcing the next turn. */}
            <div
              className={`assistant-answer${liveReplyEmpty ? ' assistant-answer--empty' : ''}`}
              data-role="assistant"
            >
              {!liveReplyEmpty && (
                <div className="assistant-msg-meta">
                  <span className="assistant-msg-role">
                    <MessageSquare size={13} strokeWidth={2} aria-hidden="true" />
                    {LABELS.assistant}
                  </span>
                </div>
              )}
              <p
                className={`assistant-reply${liveReplyEmpty ? ' assistant-reply--empty' : ''}`}
                ref={replyRef}
                tabIndex={-1}
                aria-live="polite"
                aria-busy={loading || undefined}
                aria-describedby={staleDescId}
              >
                {liveText}
              </p>
              {/* R2 — the `Source:` line is suppressed for a free-form refusal
                  turn (empty grounding). Precomposed pill answers and error turns
                  leave `hasGrounding` undefined, so they still show it; only an
                  explicit `hasGrounding === false` (a refusal) hides it. A refusal
                  still renders as a fully labelled Assistant bubble — only the
                  provenance line it cannot honestly attribute is withheld. */}
              {!loading && liveAnswer && liveAnswer.hasGrounding !== false && (
                <div className="assistant-sources">
                  <span className="answered-from">
                    Source: {SOURCE_LABELS[liveAnswer.answeredFrom as AssistantSource]}
                  </span>
                </div>
              )}
              {/* P34.3 — the cited-source chips: the citation detail beneath the plane
                  label. For a Project-Memory answer these are the leads to verify. */}
              {!loading && liveAnswer && liveSources.length > 0 && (
                <ProvenanceChips sources={liveSources} />
              )}
              {/* P36V.1 Unit B — TECHNICAL DETAILS. The answer above names the
                  blocking locations in human terms ("the record itself", "sample →
                  material → formula"); the EXACT locator the deterministic
                  validator reported — including its literal `$` root marker — is
                  preserved verbatim here and nowhere else in the rendered answer,
                  behind a collapsed native <details> (the repo idiom, and the same
                  `.assistant-more*` chrome the prompt disclosure uses, so it needs
                  no stylesheet rule of its own). Opening it reveals data the
                  screen already holds: it fetches nothing, runs no validation and
                  mutates nothing. */}
              {!loading && liveAnswer && liveTechnicalPaths.length > 0 && (
                <details className="assistant-more" data-details="technical">
                  <summary className="assistant-more-summary">
                    <ChevronRight className="chev" size={13} strokeWidth={2} aria-hidden="true" />
                    <span>{TECHNICAL_DETAILS_LABEL}</span>
                  </summary>
                  <div className="assistant-more-body">
                    {/* The list's accessible name is DISTINCT from the
                        disclosure's visible label above it — repeating the same
                        words would make a screen reader announce "Technical
                        Details" twice (the exact defect P36V review M1 caught on
                        the follow-ups group). */}
                    <ul className="assistant-provenance" aria-label="Reported validation locators">
                      {liveTechnicalPaths.map((p, i) => (
                        <li key={`${p}-${i}`} className="assistant-provenance-item">
                          <span className="assistant-source-chip">
                            <code>{p}</code>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </details>
              )}
              {/* P34.3 — the COMPACT live-answer staleness indicator (same visual as
                  an archived message's stale badge) + an explicit "Ask again". A
                  record change never auto-refetches; only this re-queries, at the
                  current rev. The indicator is associated with the answer via
                  aria-describedby above — no second live region is created. */}
              {!loading && liveStale && (
                <div className="assistant-live-stale-row">
                  <span id={staleDescId} className="assistant-msg-stale">
                    <CircleDashed size={12} strokeWidth={2} aria-hidden="true" />
                    Based on an earlier version
                  </span>
                  {liveQuestion && (
                    <button
                      type="button"
                      className="assistant-ask-again"
                      aria-label="Ask again with the current record"
                      disabled={loading}
                      onClick={() => {
                        if (liveQuestion) void submitQuestion(liveQuestion);
                      }}
                    >
                      <CornerDownRight size={13} strokeWidth={2} aria-hidden="true" />
                      Ask again
                    </button>
                  )}
                </div>
              )}
              {/* P34.3 — the answer-specific follow-ups. Shown only for a CURRENT
                  (not stale, not loading) answer; each re-queries through the SAME
                  read-only submitQuestion path — never a mutation. Capped at two.
                  P36V S-A — they now carry the VISIBLE Title-Case label "Related
                  Questions", deliberately distinct from the global empty-state
                  "Suggested Questions", and they live INSIDE the bubble of the
                  answer they belong to. The group's accessible name is that same
                  visible label (it used to be an invisible-only aria-label
                  "Suggested next questions", which both hid the grouping from
                  sighted readers and named it differently from anything on
                  screen).
                  P36V review (M1) — the name comes from the visible eyebrow via
                  `aria-labelledby`, matching `.assistant-proposed`. A detached
                  `aria-label` carrying the same words made a screen reader
                  announce "Related Questions" twice: once as the group's name and
                  again as the eyebrow's own text. */}
              {!loading && liveAnswer && !liveStale && liveFollowups.length > 0 && (
                <div
                  className="assistant-followups"
                  role="group"
                  aria-labelledby={FOLLOWUPS_EYEBROW_ID}
                >
                  <div id={FOLLOWUPS_EYEBROW_ID} className="assistant-followups-eyebrow eyebrow">
                    {RELATED_QUESTIONS_LABEL}
                  </div>
                  {liveFollowups.slice(0, 2).map((f) => (
                    <button
                      type="button"
                      className="assistant-followup"
                      key={f}
                      disabled={loading}
                      onClick={() => void submitQuestion(f)}
                    >
                      <span>{f}</span>
                      <ChevronRight className="chev" size={13} strokeWidth={2} aria-hidden="true" />
                    </button>
                  ))}
                </div>
              )}
            </div>
            {caveat && <p className="assistant-caveat">{caveat}</p>}
            {note && <p className="assistant-note">{note}</p>}
          </div>
        </div>

        {showJump && (
          <button type="button" className="assistant-jump" onClick={scrollToBottom}>
            <ChevronDown size={14} strokeWidth={2} aria-hidden="true" />
            Jump to Latest
          </button>
        )}
      </div>

      {/* P36R S2 — the PROPOSED-ACTION region. A staged answer and an unconfirmed
          proposal are NOT chat messages: they are held in their own labelled
          region directly above the composer, where they cannot scroll away and
          cannot be mistaken for something that already happened. Nothing here
          mutates on render; `confirmProposal` (behind an explicit Confirm) remains
          the ONLY write path, and Cancel writes nothing.

          P36V — the region's accessible name IS the visible eyebrow
          (`aria-labelledby`, not a detached `aria-label`), so the two can never
          drift. The retired label read "needs your confirmation", which was untrue
          of the navigation action this region now also holds: Open Validator
          navigates and writes nothing, so there is nothing to confirm. "Not
          Applied" is accurate for BOTH a staged write and a navigation lead. */}
      {(canStage && stageField) || proposal || liveAction ? (
        <section className="assistant-proposed" aria-labelledby={PROPOSED_EYEBROW_ID}>
          <div id={PROPOSED_EYEBROW_ID} className="assistant-proposed-eyebrow eyebrow">
            Proposed Action — Not Applied
          </div>
          {/* P29.6 — the narrow STAGING trigger. For the CURRENT pending field
              only, the user SELECTS the labeled synthetic suggestion; it is routed
              through the guarded `proposeForField` (source:'user') to create the
              same UNCONFIRMED ProposalCard below. Nothing here mutates — staging
              just fills the card. Hidden once a proposal is staged (one at a
              time), when degraded, or when the screen passes no current pending
              field / no suggested value. */}
          {canStage && stageField && <StageAnswer field={stageField} onStage={onStageUserAnswer} />}

          {/* P29.4b — the UNCONFIRMED staged proposal. It states plainly that it
              has NOT changed the official record. Only the explicit Confirm writes
              (through confirmProposal). A candidate/unknown/conflicting value is
              visually + textually distinct and never styled as fact. */}
          {proposal && (
            <ProposalCard
              proposal={proposal}
              stale={proposalStale}
              confirming={confirming}
              onConfirm={onConfirm}
              onCancel={onCancelProposal}
              onReevaluate={onRefresh}
            />
          )}

          {/* P36V S-B — the answer's bounded NAVIGATION action (today: Open
              Validator). It is a real, explicit user activation — a focusable
              button, not a chat message and not a claim that anything already
              happened. Activating it navigates client-side; it writes no field,
              runs no validation, and changes no validation result. It is placed
              LAST so a confirmation-critical staged value always reads first. */}
          {liveAction && <AssistantNavAction action={liveAction} />}
        </section>
      ) : null}

      {/* P36R S5 — the graph-navigation proposal. Its own region, above the
          composer, never a chat message: it states plainly that it has NOT been
          applied, and the graph is genuinely unchanged until the explicit
          control below is pressed. Rendered only on a mount that opted in. */}
      {graphCapability && graphProposal && (
        <GraphProposalCard
          proposal={graphProposal}
          provenance={graphCapability.provenance}
          onApply={onApplyGraphProposal}
          onPick={onPickGraphChoice}
          onDismiss={() => setGraphProposal(null)}
        />
      )}

      {/* P36R S2 — the composer DOCK: sticky at the bottom of the panel so asking
          another question never requires scrolling. P34.2 — the composer is WIRED
          to the READ-ONLY grounded resolver: a real text input + a SECONDARY-styled
          send control, with a persistent helper naming the grounded scopes it
          answers over (not a general chatbot). Submitting calls only
          POST /assistant/query — a non-mutating query that never writes the
          record. An empty submit is a no-op; overlapping submits are ignored while
          a query is in flight.

          P36V S-A — the composer is the FIRST thing in the dock, so it sits
          DIRECTLY beneath the transcript. The prompt controls (which used to sit
          between the transcript and the composer as a `<details>` accordion) now
          come AFTER it, and the advisory caption is last in both states. */}
      <div className="assistant-foot">
        <form className="assistant-composer" onSubmit={onComposerSubmit}>
          <input
            ref={composerInputRef}
            type="text"
            className="assistant-composer-input"
            aria-label="Ask the assistant a question"
            placeholder="Ask a question"
            value={composerText}
            onChange={(e) => setComposerText(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-secondary assistant-composer-send"
            aria-label="Send question"
            disabled={loading}
          >
            <CornerDownRight size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </form>
        <p className="assistant-composer-helper">{ASSISTANT_COMPOSER_HELPER}</p>

        {/* EMPTY STATE — Agent Actions sit below the composer (Suggested Questions
            are above it, in the body). Rendered only where the screen actually
            supplies live agent intents. */}
        {!hasConversation && agentActionControls}

        {/* CONVERSATION — both control groups collapse into ONE compact native
            disclosure, still below the composer. They are never REMOVED (and the
            composer above is always visible), so asking again is never hidden. */}
        {hasConversation && (
          <details className="assistant-more">
            <summary className="assistant-more-summary">
              <ChevronRight className="chev" size={14} strokeWidth={2} aria-hidden="true" />
              <span>{MORE_DISCLOSURE_LABEL}</span>
            </summary>
            <div className="assistant-more-body">
              {suggestedQuestionControls}
              {agentActionControls}
            </div>
          </details>
        )}

        <p className="assistant-caption">{SUBORDINATE_CAPTION}</p>
      </div>
    </section>
  );
}

/**
 * One conversation bubble. User vs. assistant is signalled by `data-role` + a
 * role class + an icon + a text label (never color alone). An assistant message
 * grounded in an older revision than the current record is marked stale, and its
 * text is run through the verdict-language guard like every rendered assistant
 * string. `live` marks the CURRENT turn's question echo — presentation only, and
 * excluded from the "focus the newest result" query.
 */
function ConversationMessage({
  message,
  currentRev,
  live = false,
}: {
  message: Msg;
  currentRev?: number;
  live?: boolean;
}) {
  const isAssistant = message.role === 'assistant';
  const text = isAssistant && hasVerdictLanguage(message.text) ? VERDICT_ROUTE_TEXT : message.text;
  const stale =
    isAssistant &&
    typeof message.recordRev === 'number' &&
    typeof currentRev === 'number' &&
    message.recordRev !== currentRev;
  const kind = message.resultType as MessageKind | undefined;
  const kindMeta = isAssistant && kind ? KIND_META[kind] : undefined;

  const classes = [
    'assistant-msg',
    isAssistant ? 'assistant-msg-assistant' : 'assistant-msg-user',
    kind ? `kind-${kind}` : '',
    stale ? 'is-stale' : '',
    live ? 'assistant-msg-live' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const source = message.answeredFrom as AssistantSource | undefined;

  return (
    <div className={classes} data-role={message.role} data-kind={kind} tabIndex={-1}>
      <div className="assistant-msg-meta">
        <span className="assistant-msg-role">
          {isAssistant ? (
            <MessageSquare size={13} strokeWidth={2} aria-hidden="true" />
          ) : (
            <UserCheck size={13} strokeWidth={2} aria-hidden="true" />
          )}
          {isAssistant ? 'Assistant' : 'You'}
        </span>
        {kindMeta && (
          <span className={`assistant-msg-kind ${kindMeta.className}`}>
            <kindMeta.Icon size={12} strokeWidth={2} aria-hidden="true" />
            {kindMeta.label}
          </span>
        )}
        {stale && (
          <span className="assistant-msg-stale">
            <CircleDashed size={12} strokeWidth={2} aria-hidden="true" />
            Based on an earlier version
          </span>
        )}
      </div>
      <p className="assistant-msg-text">{text}</p>
      {isAssistant && source && (
        <div className="assistant-sources">
          {/* P36V S-A — Title-Case label ("Source:"), replacing the lowercase
              sentence fragment "answered from:". The LABEL VALUES themselves
              (SOURCE_LABELS) are unchanged. */}
          <span className="answered-from">Source: {SOURCE_LABELS[source] ?? source}</span>
        </div>
      )}
    </div>
  );
}

/**
 * P36R S5 — an UNAPPLIED graph-navigation proposal.
 *
 * It shows what was resolved, the equivalent command-bar command (so the two
 * front-ends are visibly one thing), the projection's provenance, and — only
 * when something is actually resolvable — an explicit "Apply to Graph". An
 * ambiguous token renders its BOUNDED candidates instead and applies nothing;
 * an unresolvable one renders no apply control at all and says so.
 *
 * Nothing here mutates on render, and nothing here touches a record: applying
 * changes a read-only view of an already-fetched projection.
 */
function GraphProposalCard({
  proposal,
  provenance,
  onApply,
  onPick,
  onDismiss,
}: {
  proposal: GraphProposal;
  provenance: string;
  onApply: () => void;
  onPick: (choice: GraphProposalChoice) => void;
  onDismiss: () => void;
}) {
  const ready = proposal.status === 'ready' && proposal.actions.length > 0;
  // The verdict guard covers EVERY assistant-rendered string, this one included.
  const title = hasVerdictLanguage(proposal.title) ? VERDICT_ROUTE_TEXT : proposal.title;
  return (
    <section className="assistant-graph" aria-label="Graph navigation — not applied">
      <div className="assistant-graph-eyebrow eyebrow">Graph Navigation — Not Applied</div>
      <p className="assistant-graph-title">{title}</p>
      {proposal.command && (
        <p className="assistant-graph-command mono">
          same as the command <span>{proposal.command}</span>
        </p>
      )}

      {proposal.choices.length > 0 && (
        <div className="assistant-graph-choices" role="group" aria-label="Candidates — pick one">
          {proposal.choices.map((choice) => (
            <button
              type="button"
              className="assistant-graph-choice mono"
              key={choice.label}
              onClick={() => onPick(choice)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      <p className="assistant-graph-prov mono">{provenance}</p>

      <div className="assistant-graph-actions">
        {ready ? (
          <button type="button" className="btn btn-secondary assistant-graph-apply" onClick={onApply}>
            <CornerDownRight size={14} strokeWidth={2} aria-hidden="true" />
            Apply to Graph
          </button>
        ) : (
          <span className="assistant-graph-note">
            Nothing to apply — the graph is unchanged.
          </span>
        )}
        <button type="button" className="assistant-graph-dismiss" onClick={onDismiss}>
          <X size={13} strokeWidth={2} aria-hidden="true" />
          Dismiss
        </button>
      </div>

      <p className="assistant-graph-note">
        Applying changes the Project Memory view only. It validates nothing, completes no field, and
        authorises no export.
      </p>
    </section>
  );
}

/**
 * P34.3 — one cited-source chip that NAVIGATES to an in-app client route via the
 * app's react-router navigation (the SAME mechanism SearchDialog / cross-record
 * triage use). Rendered only for a source whose `navigate_to` passed
 * `isClientRoute`, so the route followed here is always an allowlisted workspace
 * (`/record…`) or memory (`/memory…`) route — never an arbitrary/external target.
 * Its accessible name is the source label; navigation is read-only (a view
 * change), it mutates nothing.
 */
function NavSourceChip({ label, to }: { label: string; to: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="assistant-source-chip assistant-source-chip-nav"
      onClick={() => navigate(to)}
    >
      <span>{label}</span>
      <ChevronRight className="chev" size={13} strokeWidth={2} aria-hidden="true" />
    </button>
  );
}

/**
 * P36V S-B — per-kind copy for a bounded navigation action. Keyed on the closed
 * `AssistantActionKind` enum so a future kind must supply its OWN honest copy
 * rather than silently inheriting a sentence written for the Validator.
 */
const NAV_ACTION_COPY: Record<AssistantActionKind, { head: string; note: string }> = {
  'open-validator': {
    head: 'Deterministic Schema Check',
    note:
      'The deterministic schema check runs on its own surface — Governance & Safety → Validator. ' +
      'Opening it takes you there and does nothing else: no field is written, no check is run, and ' +
      'no validation result changes.',
  },
};

/**
 * P36V S-B — the answer's bounded NAVIGATION action, rendered inside the
 * proposed-action region as a real focusable button.
 *
 * It replaces the retired prose sentence "Open Validate to run the deterministic
 * schema check." — copy that named a control the app never rendered, which is
 * precisely why the action read as nonfunctional. Navigation goes through
 * react-router `useNavigate`, so:
 *   · the router's `basename` (the deployed `/krish` base path) is applied for us;
 *   · it is a client-side transition — never a full-page reload;
 *   · it is a history PUSH, so Back returns the reader to this screen.
 * The hook lives in this CHILD (not in `AssistantPanel`) deliberately: the child
 * mounts only when an action exists, so a panel rendered outside a Router — as
 * several unit tests do — is unaffected.
 *
 * Visual chrome REUSES the proposed-action card classes (`.agent-stage*`) verbatim
 * so the control looks native to the region — it needs no rule of its own, which
 * is why no `.assistant-nav-action*` selectors exist. (An earlier comment claimed
 * the reuse was to avoid touching `assistant.css` "out of scope for this slice";
 * that was untrue — this slice edits that stylesheet extensively — and the two
 * dead class hooks it named, styled by nothing, were removed. `data-action`
 * remains as the per-kind hook.)
 */
function AssistantNavAction({ action }: { action: AssistantAction }) {
  const navigate = useNavigate();
  const copy = NAV_ACTION_COPY[action.kind];
  const noteId = `assistant-nav-action-note-${action.kind}`;
  return (
    <div className="agent-stage" data-action={action.kind}>
      <div className="agent-stage-head">
        <Shield size={14} strokeWidth={2} aria-hidden="true" />
        {copy.head}
      </div>
      <p className="agent-stage-note" id={noteId}>
        {copy.note}
      </p>
      <div className="agent-stage-row">
        <button
          type="button"
          className="btn btn-secondary agent-stage-submit"
          aria-describedby={noteId}
          onClick={() => navigate(action.to)}
        >
          <span>{action.label}</span>
          <ChevronRight className="chev" size={14} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/**
 * P34.3 — the live answer's citation detail: the cited sources rendered as a
 * compact, accessible list beneath the `answered from:` plane label. A source
 * with a safe client route is an interactive nav chip (verify the lead in-app);
 * a source without one — or with a non-client target — is a plain label chip.
 * For a Project-Memory answer these ARE the leads the user can go verify; the
 * answer text already carries the "leads to verify" advisory framing.
 */
function ProvenanceChips({ sources }: { sources: AssistantQuerySource[] }) {
  // Defense-in-depth (D1): even though the backend already drops a source label
  // that carries reserved verdict language, filter any that reach the client so a
  // citation chip can never render a PASS/FAIL or "(in)valid against" phrase.
  const safe = sources.filter((s) => !hasVerdictLanguage(s.label));
  if (safe.length === 0) return null;
  return (
    <ul className="assistant-provenance" aria-label="Cited sources">
      {safe.map((s, i) => (
        <li key={`${s.label}-${i}`} className="assistant-provenance-item">
          {isClientRoute(s.navigate_to) ? (
            <NavSourceChip label={s.label} to={s.navigate_to} />
          ) : (
            <span className="assistant-source-chip">{s.label}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * P29.6 — the narrow "Stage Answer" affordance for the CURRENT pending field. It
 * reuses GuidedPrompt's "Use This Suggestion" value entry: the user SELECTS the
 * labeled synthetic suggestion (one field, one value) — it is NOT a freeform chat
 * composer (no textbox / textarea / send) and NOT a record writer. Clicking hands
 * the suggested value to the guarded `proposeForField` (source:'user'); nothing
 * mutates until the user confirms the resulting card. The suggestion is scrubbed
 * through the leak-safe display path so a secret-shaped value never renders here.
 * A single real, keyboard-focusable button.
 */
function StageAnswer({
  field,
  onStage,
}: {
  field: StageFieldOption;
  onStage: () => void;
}) {
  const preview = displayValue(field.suggestedValue);
  return (
    <div className="agent-stage" role="group" aria-label="Stage an answer for the current field">
      <div className="agent-stage-head">
        <CornerDownRight size={14} strokeWidth={2} aria-hidden="true" />
        {LABELS.actionStageAnswer} · <span className="mono">{field.label}</span>
      </div>
      <p className="agent-stage-note">
        {field.suggestedValueLabel ?? 'Suggested value'} — not a value until you confirm. Staging
        records it as your answer (user-provided) and shows it UNCONFIRMED below; the assistant never
        fills it in or classifies it as evidence, and nothing is written until you confirm.
      </p>
      {preview && <p className="agent-stage-value mono">{preview}</p>}
      <div className="agent-stage-row">
        <button
          type="button"
          className="btn btn-secondary agent-stage-submit"
          onClick={onStage}
        >
          {LABELS.actionStageAnswer}
        </button>
      </div>
    </div>
  );
}

/** Render a proposal's value on the DISPLAY path, scrubbed through the P29.1
 *  leak-safe sanitizer so a nested secret/token/path is never rendered. */
function displayValue(value: unknown): string {
  const scrubbed = scrubForDisplay(value);
  if (scrubbed === undefined || scrubbed === null) return '';
  return typeof scrubbed === 'string' ? scrubbed : JSON.stringify(scrubbed);
}

/**
 * The single UNCONFIRMED staged-proposal card (P29.4b). It shows the field, the
 * user's proposed value (scrubbed, and NEVER for an Unknown/conflicting field),
 * the origin, the evidence classification VERBATIM, an explanation, and an
 * explicit "it has not changed the official record" note. A candidate/unknown is
 * visually + textually distinct (icon + label + class + copy) and never styled as
 * fact; a conflicting field shows no winner. Confirm is the ONLY write; it is
 * disabled when the proposal is stale. Nothing here mutates on render.
 */
function ProposalCard({
  proposal,
  stale,
  confirming,
  onConfirm,
  onCancel,
  onReevaluate,
}: {
  proposal: Proposal;
  stale: boolean;
  confirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onReevaluate?: () => void;
}) {
  const classification = proposal.classification;
  const classMeta = classification ? CLASS_META[classification] : undefined;
  const isUnknown = classification === 'unknown';
  const isConflicting = classification === 'conflicting_evidence';
  const isInferred = classification === 'inferred_candidate';
  // A value is shown only when there IS a defensible single value to propose —
  // never for an Unknown (nothing is proposed) or a conflict (no winner).
  const showValue = !isUnknown && !isConflicting;

  const classes = [
    'agent-proposal',
    stale ? 'is-stale' : '',
    isInferred ? 'agent-proposal-inferred' : '',
    isUnknown ? 'agent-proposal-unknown' : '',
    isConflicting ? 'agent-proposal-conflicting' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} role="group" aria-label="Unconfirmed proposed value" data-classification={classification}>
      <div className="agent-proposal-head">
        <CircleAlert size={14} strokeWidth={2} aria-hidden="true" />
        Needs Your Confirmation — Unconfirmed
      </div>

      <dl className="agent-proposal-fields">
        <dt>field</dt>
        <dd className="mono">{proposal.field}</dd>

        {showValue && (
          <>
            <dt>proposed value</dt>
            <dd className="agent-proposal-value">{displayValue(proposal.value)}</dd>
          </>
        )}

        <dt>origin</dt>
        <dd>{proposal.origin}</dd>

        {classMeta && (
          <>
            <dt>evidence classification</dt>
            <dd className="agent-proposal-class">
              <classMeta.Icon size={12} strokeWidth={2} aria-hidden="true" />
              {classMeta.label}
            </dd>
          </>
        )}

        {proposal.explanation && (
          <>
            <dt>explanation</dt>
            <dd>{proposal.explanation}</dd>
          </>
        )}
      </dl>

      {isInferred && (
        <p className="agent-proposal-honesty">
          This is an inferred candidate — unconfirmed, not a recorded value. It becomes a value only
          after you confirm it.
        </p>
      )}
      {isUnknown && (
        <p className="agent-proposal-honesty">
          This field is Unknown — there is no defensible value, so none is proposed and none is
          guessed.
        </p>
      )}
      {isConflicting && (
        <p className="agent-proposal-honesty">
          The evidence conflicts here — both sides stand and no winner is chosen. A person must
          resolve it; the assistant does not pick one.
        </p>
      )}

      <p className="agent-proposal-note">It has not changed the official record.</p>

      {stale && (
        <p className="agent-proposal-stale" role="status">
          <CircleDashed size={12} strokeWidth={2} aria-hidden="true" />
          The record changed since this was proposed — it must be re-evaluated before it can be
          confirmed.
          {onReevaluate && (
            <button type="button" className="agent-proposal-reeval" onClick={onReevaluate}>
              Re-Evaluate
            </button>
          )}
        </p>
      )}

      <div className="agent-proposal-actions">
        <button
          type="button"
          className="btn btn-primary agent-proposal-confirm"
          onClick={onConfirm}
          disabled={stale || confirming}
        >
          <Check size={14} strokeWidth={2} aria-hidden="true" />
          {LABELS.actionConfirm}
        </button>
        <button
          type="button"
          className="btn btn-secondary agent-proposal-cancel"
          onClick={onCancel}
          disabled={confirming}
        >
          <X size={14} strokeWidth={2} aria-hidden="true" />
          {LABELS.actionCancel}
        </button>
      </div>
    </div>
  );
}
