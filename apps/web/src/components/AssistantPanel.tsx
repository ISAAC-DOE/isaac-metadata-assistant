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
  ASSISTANT_EMPTY_STATE,
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
import type {
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
   * neither the `memory:` head line nor the memory caveat.
   */
  availability?: MemoryAvailability;
  /**
   * P33 HQA (#7) — whether to render the memory-availability label in the
   * assistant head. Defaults to `true`. A screen that ALREADY shows a
   * `GraphStatusChip` for the same availability axis passes `false` to suppress
   * the redundant duplicate label (single-state). This is purely presentational:
   * `availability` is still consumed — message classification (`classifyAnswer`)
   * and the unavailable caveat are unchanged regardless of this flag.
   */
  showAvailabilityHead?: boolean;
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

// The safe replacement rendered whenever a would-be verdict string reaches the
// panel — the assistant explains and routes; it never states PASS/FAIL.
const VERDICT_ROUTE_TEXT =
  'That is a truth question — open the Validate surface for the deterministic verdict.';

// P34.2 — the accessible in-flight label announced in the single live region
// while a read-only grounded query is resolving.
const WORKING_LABEL = 'Working…';

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
// client route (the record workbench or the memory plane). Anything else — an
// absolute server path, an external URL, a bare token — is rendered as a plain,
// non-navigating label chip. This is the render-time complement to the session
// sanitizer, which strips any '/'-prefixed string on persistence: nav targets
// are never persisted, only followed live for an explicitly-allowlisted route.
function isClientRoute(nav: string | null | undefined): nav is string {
  return typeof nav === 'string' && (nav.startsWith('/record') || nav.startsWith('/memory'));
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
 * Conversation-style assistant (P29.2, reordered P33 S2 · D4). Layout top→bottom:
 * header → honest visual-only composer (P33 S2 · D3/C3) → Suggested Questions
 * pills → Agent Actions → the scrollable message log (older → newest, newest at
 * the BOTTOM) → StageAnswer/ProposalCard → the single subordinate caption. The
 * panel presents the P29.1 ephemeral session as a conversation and preserves
 * every honesty guard: `answered from:` on each reply, the composer's persistent
 * guided-only helper, the memory-availability caveat, and the verdict-language
 * guard over ALL rendered assistant text. It explains and points to sources — it
 * never renders a verdict, never mutates a record from the composer, and the
 * composer performs no fetch/append/persist (mutation/confirmation is P29.3).
 */
export function AssistantPanel({
  prompts,
  experimentId = DEFAULT_SESSION_KEY,
  recordRev,
  availability,
  showAvailabilityHead = true,
  note,
  queryScope = 'record',
  agentContext,
  degraded = false,
  agentPrompts,
  proposal: proposalProp,
  onRefresh,
  confirmApi = api,
  stageField,
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
    const msgs = log.querySelectorAll('.assistant-msg');
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
  // accessible "Working…"; a resolved answer → its guarded text; otherwise the
  // resting empty state. The auto-reply fallback (compose().reply) was REMOVED at
  // P34.2 — the resting rail no longer announces a pending-summary card.
  const liveText = loading
    ? WORKING_LABEL
    : liveAnswer
      ? hasVerdictLanguage(liveAnswer.text)
        ? VERDICT_ROUTE_TEXT
        : liveAnswer.text
      : ASSISTANT_EMPTY_STATE;

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

  return (
    <section className="assistant" aria-label="Assistant (advisory)">
      <div className="assistant-head">
        <span className="assistant-icon" aria-hidden="true">
          <MessageSquare size={15} strokeWidth={2} />
        </span>
        <span className="assistant-label">{LABELS.assistant}</span>
        {availability && showAvailabilityHead && (
          <span className="assistant-memory">
            <span
              className={`dot dot-memory${availability === 'available' ? ' dot-memory-available' : ''}`}
              aria-hidden="true"
            />
            {MEMORY_HEAD_LABEL[availability]}
          </span>
        )}
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

      {/* P34.2 — the composer, WIRED to the READ-ONLY grounded resolver. A real
          text input + a SECONDARY-styled send control, with a persistent helper
          naming the grounded scopes it answers over (not a general chatbot).
          Submitting calls only POST /assistant/query — a non-mutating query that
          never writes the record. An empty submit is a no-op; overlapping submits
          are ignored while a query is in flight. */}
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

      {/* P29.4b — the INTENT pills. Each RUNS a real agent intent against the live
          context; the result is appended to the conversation below. Disabled while
          the context is degraded/absent (manual-first: composed prompts stay live). */}
      {shownAgentPrompts.length > 0 && (
        <>
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
        </>
      )}

      {/* P34.2 — the conversation toolbar. Clear Conversation appears only once
          the log has history; it wipes THIS experiment's ephemeral session and
          returns the rail to its resting empty state. Session-only — it never
          touches record/truth state. */}
      {messages.length > 0 && (
        <div className="assistant-log-toolbar">
          <button
            type="button"
            className="assistant-clear"
            aria-label="Clear conversation"
            onClick={clearConversation}
          >
            <X size={13} strokeWidth={2} aria-hidden="true" />
            Clear Conversation
          </button>
        </div>
      )}

      {/* P33 S2 (D4) — the conversation LOG moved BELOW the prompt controls
          (newest at the bottom). role="log" carries an IMPLICIT aria-live="polite";
          we set aria-live="off" here to suppress it so archiving prior turns into
          the log does NOT announce them. The single live region is the current
          reply below — announced once, politely. */}
      <div
        className="assistant-log"
        ref={logRef}
        role="log"
        aria-live="off"
        aria-label="Assistant conversation"
        onScroll={onScroll}
      >
        {messages.map((m, i) => (
          <ConversationMessage key={m.id ?? i} message={m} currentRev={recordRev} />
        ))}

        {/* The live current turn — the newest content, rendered below history.
            The single `.assistant-reply` <p> is the ONE live region (the log above
            is aria-live="off"): while a query resolves it announces "Working…"
            (aria-busy), then the resolved answer; at rest it shows the empty state.
            The `answered from:` line renders only once there is a real answer. */}
        <div className="assistant-reply-block">
          <p
            className="assistant-reply"
            ref={replyRef}
            tabIndex={-1}
            aria-live="polite"
            aria-busy={loading || undefined}
            aria-describedby={staleDescId}
          >
            {liveText}
          </p>
          {/* R2 — the `answered from:` line is suppressed for a free-form refusal
              turn (empty grounding). Precomposed pill answers and error turns leave
              `hasGrounding` undefined, so they still show it; only an explicit
              `hasGrounding === false` (a refusal) hides it. */}
          {!loading && liveAnswer && liveAnswer.hasGrounding !== false && (
            <div className="assistant-sources">
              <span className="answered-from">
                answered from: {SOURCE_LABELS[liveAnswer.answeredFrom as AssistantSource]}
              </span>
            </div>
          )}
          {/* P34.3 — the cited-source chips: the citation detail beneath the plane
              label. For a Project-Memory answer these are the leads to verify. */}
          {!loading && liveAnswer && liveSources.length > 0 && (
            <ProvenanceChips sources={liveSources} />
          )}
          {/* P34.3 — the COMPACT live-answer staleness indicator (same visual as an
              archived message's stale badge) + an explicit "Ask again". A record
              change never auto-refetches; only this re-queries, at the current rev.
              The indicator is associated with the answer via aria-describedby above
              — no second live region is created. */}
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
          {/* P34.3 — suggested next questions. Shown only for a CURRENT (not stale,
              not loading) answer; each re-queries through the SAME read-only
              submitQuestion path — never a mutation. Capped at two, visually
              distinct from the provenance chips and the Suggested Questions. */}
          {!loading && liveAnswer && !liveStale && liveFollowups.length > 0 && (
            <div className="assistant-followups" aria-label="Suggested next questions">
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

      {/* P29.6 — the narrow STAGING trigger. For the CURRENT pending field only,
          the user SELECTS the labeled synthetic suggestion; it is routed through
          the guarded `proposeForField` (source:'user') to create the same
          UNCONFIRMED ProposalCard below. Nothing here mutates — staging just fills
          the card. Hidden once a proposal is staged (one at a time), when degraded,
          or when the screen passes no current pending field / no suggested value. */}
      {canStage && stageField && (
        <StageAnswer field={stageField} onStage={onStageUserAnswer} />
      )}

      {/* P29.4b — the UNCONFIRMED staged proposal. It states plainly that it has
          NOT changed the official record; nothing here mutates. Only the explicit
          Confirm writes (through confirmProposal). A candidate/unknown/conflicting
          value is visually + textually distinct and never styled as fact. */}
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

      {/* P33 S2 (D4) — the SINGLE advisory footer. The standalone guided-only note
          was removed here as redundant with the composer helper above. */}
      <p className="assistant-caption">{SUBORDINATE_CAPTION}</p>
    </section>
  );
}

/**
 * One conversation bubble. User vs. assistant is signalled by role class + an
 * icon + a text label (never color alone). An assistant message grounded in an
 * older revision than the current record is marked stale, and its text is run
 * through the verdict-language guard like every rendered assistant string.
 */
function ConversationMessage({ message, currentRev }: { message: Msg; currentRev?: number }) {
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
          <span className="answered-from">
            answered from: {SOURCE_LABELS[source] ?? source}
          </span>
        </div>
      )}
    </div>
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
