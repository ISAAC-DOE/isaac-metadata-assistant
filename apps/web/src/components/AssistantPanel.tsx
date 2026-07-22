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
import { appendMessage, loadSession, type Msg } from '../lib/assistantSession';
import { DEGRADED_MESSAGE, type AgentContext } from '../lib/assistantAgent';
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
}

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
}: AssistantPanelProps) {
  // The AgentContext is the P29.3 authority the assistant reasons over. It is
  // threaded from the shared record-session owner so it always matches the manual
  // workflow's revision. Referenced defensively so the prop is part of the live
  // contract even where the panel's default UI still renders composed prompts.
  void agentContext;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>(() => loadSession(experimentId).messages);
  const [showJump, setShowJump] = useState(false);

  const logRef = useRef<HTMLDivElement | null>(null);
  const replyRef = useRef<HTMLParagraphElement | null>(null);
  const nearBottomRef = useRef(true);
  const mountedRef = useRef(false);
  const focusPendingRef = useRef(false);

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
    <div className={classes} data-role={message.role} data-kind={kind}>
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
