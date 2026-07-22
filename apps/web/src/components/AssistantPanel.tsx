import './assistant.css';
import { useCallback, useEffect, useRef, useState } from 'react';
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
  GUIDED_ONLY_NOTE,
  MEMORY_UNAVAILABLE_CAVEAT,
  SOURCE_LABELS,
  SUBORDINATE_CAPTION,
  hasVerdictLanguage,
} from '../lib/assistant';
import { classifyAnswer, type MessageKind } from '../lib/assistantConversation';
import { appendMessage, loadSession, scrubForDisplay, type Msg } from '../lib/assistantSession';
import {
  DEGRADED_MESSAGE,
  INTENTS,
  confirmProposal,
  runIntent,
  type AgentContext,
  type AgentOpts,
  type ConfirmApi,
  type Proposal,
} from '../lib/assistantAgent';
import { api } from '../lib/api';
import type {
  AssistantMessage,
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
  /** Optional subordinate note, e.g. "truth questions route to the CLI…". */
  note?: string;
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

// The safe replacement rendered whenever a would-be verdict string reaches the
// panel — the assistant explains and routes; it never states PASS/FAIL.
const VERDICT_ROUTE_TEXT =
  'That is a truth question — open the Validate surface for the deterministic verdict.';

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
 * Conversation-style assistant (P29.2). Layout top→bottom: header → scrollable
 * message log (older → newest, newest at the BOTTOM) → guided prompt pills →
 * subordinate caption. The panel presents the P29.1 ephemeral session as a
 * conversation and preserves every honesty guard: `answered from:` on each
 * reply, the guided-only note, the memory-availability caveat, and the
 * verdict-language guard over ALL rendered assistant text. It explains and
 * points to sources — it never renders a verdict, never mutates a record, and
 * offers no free-text input (mutation/confirmation is P29.3).
 */
export function AssistantPanel({
  reply,
  prompts,
  experimentId = DEFAULT_SESSION_KEY,
  recordRev,
  availability,
  note,
  agentContext,
  degraded = false,
  agentPrompts,
  proposal: proposalProp,
  onRefresh,
  confirmApi = api,
}: AssistantPanelProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>(() => loadSession(experimentId).messages);
  const [showJump, setShowJump] = useState(false);

  // P29.4b — the live staged proposal, seeded from the prop and owned locally so
  // Cancel can clear it and a stale/412 confirm can mark it. The record is never
  // mutated by holding or displaying it.
  const [proposal, setProposal] = useState<Proposal | null>(proposalProp ?? null);
  const [confirming, setConfirming] = useState(false);

  const logRef = useRef<HTMLDivElement | null>(null);
  const replyRef = useRef<HTMLParagraphElement | null>(null);
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
  }, [messages.length, activeIndex]);

  // Move focus to the fresh reply after a submission (never during a poll).
  useEffect(() => {
    if (focusPendingRef.current) {
      focusPendingRef.current = false;
      replyRef.current?.focus();
    }
  }, [activeIndex, messages.length]);

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

  const agentActive = !!agentContext && !degraded && !agentContext.degraded;
  const shownAgentPrompts = agentContext
    ? (agentPrompts ?? []).filter((p) => INTENTS.includes(p.intent))
    : [];

  const active = activeIndex !== null ? (prompts[activeIndex]?.answer ?? reply) : reply;

  // Structural guard: the assistant must never render a verdict.
  const safeText = hasVerdictLanguage(active.text) ? VERDICT_ROUTE_TEXT : active.text;

  // Only a screen that actually fetched graph status may make a memory claim.
  // Dedupe guard: on the Project Memory unavailable mount the composed reply is
  // byte-identical to MEMORY_UNAVAILABLE_CAVEAT — render it once, never stacked.
  const caveat =
    availability === 'unavailable' && MEMORY_UNAVAILABLE_CAVEAT !== safeText
      ? MEMORY_UNAVAILABLE_CAVEAT
      : undefined;

  // Clicking a pill "asks" that question: the previously displayed turn is
  // committed to the ephemeral conversation log, the new answer becomes the live
  // reply, focus moves to it, and it is announced once (politely). No fetch, no
  // mutation — presentation + P29.1 session wiring only.
  function ask(index: number) {
    const prompt = prompts[index];
    if (!prompt?.answer) return; // disabled pill → never activatable
    if (index === activeIndex) return; // already showing

    const leaving = active; // the turn currently on screen, about to scroll into history
    const leavingQuestion = activeIndex !== null ? prompts[activeIndex]?.text : null;

    const cls = classifyAnswer(leaving.answeredFrom, availability);
    if (leavingQuestion) {
      appendMessage(experimentId, {
        role: 'user',
        text: leavingQuestion,
        recordRev,
        id: uid(),
        timestamp: Date.now(),
      });
    }
    appendMessage(experimentId, {
      role: 'assistant',
      text: leaving.text,
      answeredFrom: leaving.answeredFrom,
      recordRev,
      resultType: cls.resultType,
      authority: cls.authority,
      actionability: cls.actionability,
      id: uid(),
      timestamp: Date.now(),
    });
    setMessages(loadSession(experimentId).messages);

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
        {availability && (
          <span className="assistant-memory">
            <span className="dot dot-memory" aria-hidden="true" />
            memory: {availability}
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

      {/* role="log" gives the conversation its semantics but carries an IMPLICIT
          aria-live="polite"; we set aria-live="off" here to suppress it so that
          archiving prior turns into the log does NOT announce them. The single
          live region is the current reply below — announced once, politely. */}
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

        {/* The live current turn — the newest message, rendered below history.
            aria-live is the ONE live region (the log above is aria-live="off"),
            so a new reply is announced once — politely — while record polling that
            leaves the reply unchanged says nothing. */}
        <div className="assistant-reply-block">
          <p className="assistant-reply" ref={replyRef} tabIndex={-1} aria-live="polite">
            {safeText}
          </p>
          <div className="assistant-sources">
            <span className="answered-from">answered from: {SOURCE_LABELS[active.answeredFrom]}</span>
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
          context; the result is appended to the conversation above. Disabled while
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

      <p className="assistant-guided-note">{GUIDED_ONLY_NOTE}</p>

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
