/*
 * P29.1 — ephemeral assistant session context.
 *
 * EPHEMERAL and NON-AUTHORITATIVE. This module holds browser-session-scoped
 * state only: conversation PRESENTATION (what the assistant said/asked), a
 * single staged proposal (a suggested edit awaiting user action), and the
 * last-observed record revision. It is keyed per experiment id and backed by
 * `sessionStorage` (tab/session lifetime) plus an in-memory mirror for fast
 * reads and as a fallback when storage is unavailable (e.g. private browsing).
 *
 * It is NOT a record store. It never holds, and the sanitizer here actively
 * strips, confirmed-record/verdict data (draft, validate, audit, export,
 * evidence), secrets, bearer tokens, authorization headers, or private
 * filesystem paths. localStorage and IndexedDB are never used — clearing the
 * browser session (or calling `clearAllSessions`, the Reset Demo path) is
 * enough to erase everything this module has written.
 *
 * A record revision change invalidates (marks `stale`) any staged proposal
 * grounded in an older revision, so the assistant never lets a user silently
 * confirm a suggestion computed against stale data. Historical conversation
 * messages are never deleted by a revision change — only proposals carry an
 * actionability/staleness flag.
 */

export type Msg = {
  role: 'user' | 'assistant';
  text: string;
  recordRev?: number;
  resultType?: string;
  authority?: string;
  actionability?: string;
  // P29.2 — the source category (an AssistantSource enum value) used to render
  // the honest `answered from: <label>` line on an assistant message. It is a
  // safe machine enum ('schema' | 'audit' | …), never free text.
  answeredFrom?: string;
  stale?: boolean;
  id?: string;
  timestamp?: number;
  [key: string]: unknown;
};

export type Proposal = {
  field: string;
  value: unknown;
  sourceRev: number;
  stale?: boolean;
  [key: string]: unknown;
};

type SessionState = {
  messages: Msg[];
  proposal: Proposal | null;
};

const STORAGE_PREFIX = 'isaac.assistant.session.';

// Presentation-safe keys. Anything not in this allowlist is dropped by the
// sanitizer before a value is ever written to sessionStorage.
const SAFE_KEYS = new Set([
  'role',
  'text',
  'recordRev',
  'resultType',
  'authority',
  'actionability',
  'answeredFrom',
  'stale',
  'id',
  'field',
  'value',
  'sourceRev',
  'timestamp',
]);

// Key names that are never safe to persist, regardless of allowlist status.
const UNSAFE_KEY_PATTERN = /authorization|token|bearer|secret|password/i;

// Confirmed-record / verdict fields must never leak into ephemeral session
// presentation state, even if a caller mistakenly stashes them on a message.
const VERDICT_KEYS = new Set(['draft', 'validate', 'audit', 'export', 'exported', 'evidence']);

const HEX_TOKEN_PATTERN = /\b[0-9a-f]{32,}\b/i;

function isUnsafeString(value: string): boolean {
  if (value.includes('Bearer ')) return true;
  if (value.startsWith('/') || value.includes('/Users/') || value.includes('\\Users\\')) {
    return true;
  }
  if (HEX_TOKEN_PATTERN.test(value)) return true;
  return false;
}

/**
 * Recursively scrub a value at ANY depth, regardless of the key it was found
 * under. This is what protects `unknown`-typed payloads (notably
 * `proposal.value`, and anything nested inside an allowlisted object/array
 * field) — an allowlisted top-level key only earns its *container* a place
 * in the persisted blob; everything inside it still has to pass this.
 *
 * - strings: dropped (return `undefined`) if `isUnsafeString` flags them —
 *   applies to every string, including ones under "safe" keys like `text`.
 * - arrays: each element is recursed into; elements that scrub to nothing
 *   are removed.
 * - objects: each key is dropped outright if it matches the unsafe-key
 *   pattern or is a verdict/confirmed-record key; otherwise its value is
 *   recursed into, and the key is dropped if the recursed value is
 *   `undefined`.
 * - numbers/booleans/null: passed through unchanged.
 */
function deepSanitize(value: unknown): unknown {
  if (typeof value === 'string') {
    return isUnsafeString(value) ? undefined : value;
  }
  if (Array.isArray(value)) {
    return value.map((entry) => deepSanitize(entry)).filter((entry) => entry !== undefined);
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (UNSAFE_KEY_PATTERN.test(key)) continue;
      if (VERDICT_KEYS.has(key)) continue;
      const cleaned = deepSanitize(nested);
      if (cleaned === undefined) continue;
      out[key] = cleaned;
    }
    return out;
  }
  // number, boolean, null, undefined — safe to keep as-is.
  return value;
}

/**
 * Top-level sanitizer for a Msg/Proposal: keeps only presentation fields on
 * `SAFE_KEYS` (dropping everything else, including verdict/confirmed-record
 * keys and unsafe key names outright), then deep-sanitizes the VALUE of each
 * kept key so secrets/paths/verdicts nested arbitrarily deep inside it (e.g.
 * inside `proposal.value`, or inside an object/array under an allowlisted
 * key) are scrubbed too.
 */
function sanitize<T extends Record<string, unknown>>(obj: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (!SAFE_KEYS.has(key)) continue;
    if (UNSAFE_KEY_PATTERN.test(key)) continue;
    if (VERDICT_KEYS.has(key)) continue;
    const cleaned = deepSanitize(value);
    if (cleaned === undefined) continue;
    out[key] = cleaned;
  }
  return out as Partial<T>;
}

function emptyState(): SessionState {
  return { messages: [], proposal: null };
}

// In-memory mirror, keyed by experiment id. Always the source of truth for
// reads; sessionStorage is a best-effort persistence layer beneath it.
const memory = new Map<string, SessionState>();

function storageKey(experimentId: string): string {
  return `${STORAGE_PREFIX}${experimentId}`;
}

function readStorage(experimentId: string): SessionState | null {
  try {
    const raw = sessionStorage.getItem(storageKey(experimentId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SessionState>;
    const messages = Array.isArray(parsed.messages) ? (parsed.messages as Msg[]) : [];
    const proposal =
      parsed.proposal && typeof parsed.proposal === 'object' ? (parsed.proposal as Proposal) : null;
    return { messages, proposal };
  } catch {
    return null;
  }
}

function writeStorage(experimentId: string, state: SessionState): void {
  try {
    sessionStorage.setItem(storageKey(experimentId), JSON.stringify(state));
  } catch {
    // sessionStorage unavailable (e.g. private mode) — in-memory mirror
    // already holds the state, so the app keeps working without it.
  }
}

function getState(experimentId: string): SessionState {
  const cached = memory.get(experimentId);
  if (cached) return cached;
  const fromStorage = readStorage(experimentId) ?? emptyState();
  memory.set(experimentId, fromStorage);
  return fromStorage;
}

function saveState(experimentId: string, state: SessionState): void {
  memory.set(experimentId, state);
  writeStorage(experimentId, state);
}

/** Read the per-experiment session (empty if none exists yet). */
export function loadSession(experimentId: string): SessionState {
  const state = getState(experimentId);
  return { messages: [...state.messages], proposal: state.proposal ? { ...state.proposal } : null };
}

/** Append a conversation message, sanitized before it is persisted. */
export function appendMessage(experimentId: string, message: Msg): void {
  const state = getState(experimentId);
  const clean = sanitize(message) as Msg;
  const next: SessionState = { messages: [...state.messages, clean], proposal: state.proposal };
  saveState(experimentId, next);
}

/** Stage the single current proposal for an experiment, sanitized. */
export function stageProposal(experimentId: string, proposal: Proposal): void {
  const state = getState(experimentId);
  const clean = sanitize(proposal) as Proposal;
  if (clean.stale === undefined) clean.stale = false;
  const next: SessionState = { messages: state.messages, proposal: clean };
  saveState(experimentId, next);
}

/**
 * Mark the staged proposal stale when it was grounded in an older record
 * revision than `currentRev`. Leaves it unchanged when the revision matches.
 * Never deletes historical messages.
 */
export function invalidateStaleProposals(experimentId: string, currentRev: number): void {
  const state = getState(experimentId);
  if (!state.proposal) return;
  if (state.proposal.sourceRev === currentRev) return;
  const next: SessionState = {
    messages: state.messages,
    proposal: { ...state.proposal, stale: true },
  };
  saveState(experimentId, next);
}

/** Clear only this experiment's session (messages + staged proposal). */
export function clearSession(experimentId: string): void {
  memory.delete(experimentId);
  try {
    sessionStorage.removeItem(storageKey(experimentId));
  } catch {
    // ignore — in-memory mirror is already cleared.
  }
}

/** Clear ALL assistant session state (Reset Demo semantics). */
export function clearAllSessions(): void {
  memory.clear();
  try {
    const keys: string[] = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(STORAGE_PREFIX)) keys.push(key);
    }
    for (const key of keys) sessionStorage.removeItem(key);
  } catch {
    // sessionStorage unavailable — in-memory mirror is already cleared.
  }
}
