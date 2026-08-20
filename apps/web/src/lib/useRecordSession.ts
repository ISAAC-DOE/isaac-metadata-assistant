/*
 * P29.4 — ONE shared authoritative record-session state for a single record.
 *
 * WHY THIS EXISTS (and why it is NOT a new store): before P29.4 the assistant
 * (P29.1 session + P29.3 agent) and the manual workflow UI each read the record
 * independently — different fetches, different notions of "the current revision".
 * They could disagree on which version is live, and a staged assistant proposal
 * could survive a manual edit it no longer matched. This hook is the SMALLEST
 * sufficient owner that removes that gap: a per-record-route hook that COMPOSES
 * the pieces that already exist — the screen's existing bundle fetch (the single
 * source of `detail`, so there is NO second record cache), exactly ONE
 * `useRecordSync` poller (P27.6), the P29.1 ephemeral session, and the P29.3
 * AgentContext — behind one authoritative `version`/`recordRev`.
 *
 * It owns, for one record id:
 *   - the authoritative `version` (the ETag/If-Match token) and `recordRev`,
 *     taken verbatim from the screen's already-fetched `detail` (never re-fetched
 *     here — no duplicate record cache);
 *   - the derived P29.3 `AgentContext` (detail.workflow + evidence-classification
 *     + pending + version + rev), fetched from the two additive AgentContext
 *     inputs the screen bundle may not carry;
 *   - the P29.1 `session` snapshot (messages + the single staged proposal);
 *   - exactly ONE `useRecordSync` poller (screens no longer mount their own);
 *   - `refresh()`, a `conflict` flag (the record moved under the current view),
 *     an agent-context `degraded` flag, and the poller's own `syncDegraded`.
 *
 * On a poll change signal it (1) marks any staged proposal grounded in the OLD
 * revision STALE via `invalidateStaleProposals`, so a stale suggestion can never
 * be silently confirmed; (2) refreshes the session snapshot so the stale flag is
 * visible; (3) raises `conflict`; and (4) delegates to the screen's `onChange`
 * (which refetches its bundle or raises its own input-preserving banner). An
 * out-of-order/aborted extras fetch for a previous record can never clobber the
 * currently-selected one (the `currentRef` stale-guard pattern from useRecordSync).
 *
 * MANUAL-FIRST: if the AgentContext inputs fail to load, `degraded` is raised and
 * the AgentContext refuses dataset-specific intents — but this hook NEVER blocks
 * the manual workflow. The screen's own bundle drives fields/evidence/export.
 *
 * Truth-plane-free: this hook fetches only read endpoints and never validates,
 * exports, or writes; the only write path remains P29.3 `confirmProposal`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { useRecordSync } from './useRecordSync';
import {
  invalidateStaleProposals,
  loadSession,
  type Msg,
  type Proposal as SessionProposal,
} from './assistantSession';
import type {
  AgentContext,
  EvidenceView,
  PendingItem,
  WorkflowStep,
} from './assistantAgent';
import type {
  ApiEvidenceClassification,
  ApiExperimentDetail,
  ApiPendingItem,
} from './types';

/** The additive AgentContext inputs the hook fetches (not always in the screen's
 *  bundle): the pending blockers and the evidence-support classification. */
interface AgentExtras {
  pending: ApiPendingItem[];
  classification: ApiEvidenceClassification;
}

export interface UseRecordSessionOptions {
  /**
   * The authoritative record detail from the screen's EXISTING bundle fetch —
   * the single source of `version`/`rev`/`workflow`. Undefined while the bundle
   * is still loading (the hook is then inert: no poll, no extras). Passing it in
   * (rather than re-fetching) is what keeps this from becoming a second cache.
   */
  detail: ApiExperimentDetail | undefined;
  /**
   * The screen's poll-change handler. Called with the FRESH detail on a change
   * signal so the screen can silently refetch its bundle (read-only surfaces) or
   * raise an input-preserving "changed elsewhere" banner (the completion form).
   */
  onChange?: (detail: ApiExperimentDetail) => void;
  /** When false the hook is fully inert (no poll, no fetch). Default true. */
  enabled?: boolean;
}

export interface RecordSession {
  /** The authoritative ETag/If-Match token (undefined until `detail` arrives). */
  version: string | undefined;
  /**
   * The authoritative record revision — DERIVED from the same `version` string
   * the context/If-Match uses, so the two can never disagree (undefined until
   * `detail` arrives).
   */
  recordRev: number | undefined;
  /**
   * The derived P29.3 AgentContext. Undefined until the record `detail` arrives
   * AND its AgentContext inputs have SETTLED (loaded or failed) — never a
   * half-built context, so a healthy slow-network mount never flashes degraded.
   */
  context: AgentContext | undefined;
  /**
   * The AgentContext inputs are still in-flight on a healthy mount (no failure
   * yet). Distinct from `degraded`: loading is NOT degraded.
   */
  loading: boolean;
  /** The P29.1 session snapshot (messages + the single staged proposal). */
  session: { messages: Msg[]; proposal: SessionProposal | null };
  /** The poller's own degraded state (drives the LiveSyncNote). */
  syncDegraded: boolean;
  /** The AGENT-CONTEXT degraded state: the AgentContext inputs failed to load. */
  degraded: boolean;
  /** True when the record moved under the current view and has not been adopted. */
  conflict: boolean;
  /** Re-fetch the AgentContext inputs and reload the session snapshot. */
  refresh: () => void;
  /** Pass-through to the poller's imperative immediate check. */
  checkNow: () => void;
}

function toWorkflowSteps(detail: ApiExperimentDetail): WorkflowStep[] {
  return detail.workflow.ordered_steps.map((s) => ({
    id: s.id,
    label: s.label,
    state: s.state,
    current: s.current,
    reopened: s.reopened,
    blocked: s.blocked,
    reason: s.reason,
  }));
}

function toEvidenceViews(classification: ApiEvidenceClassification | undefined): EvidenceView[] {
  if (!classification) return [];
  return classification.field_results.map((f) => ({
    field: f.field,
    classification: f.classification,
    value_state: f.value_state,
    explanation: f.explanation,
    // Only the safe source_type is carried into the agent context.
    sources: (f.sources ?? []).map((s) => ({ source_type: s.source_type })),
  }));
}

/**
 * Derive the record revision from the authoritative `version` string so the rev
 * and the version can NEVER disagree — the optimistic-concurrency token has the
 * form `"<generation>.<rev>"`, so the trailing segment is the rev. This is the
 * SAME source the `If-Match` header uses, which closes the rev/version desync
 * window: if a local edit advances the version before the bundle refetch updates
 * `detail.rev`, a proposal staged at the old rev is still correctly detected as
 * stale (its `sourceRev` no longer matches the version-derived rev). Falls back
 * to `detail.rev` only when the version is absent or unparseable.
 */
function deriveRev(
  version: string | undefined,
  detail: ApiExperimentDetail | undefined,
): number | undefined {
  if (version) {
    const parsed = Number(version.split('.').pop());
    if (Number.isFinite(parsed)) return parsed;
  }
  return detail?.rev;
}

function toPendingItems(pending: ApiPendingItem[] | undefined): PendingItem[] {
  if (!pending) return [];
  return pending.map((p) => ({
    id: p.id,
    // The agent renders a human label; prefer the same about → question → id
    // ladder the composer uses so the two never disagree on a field's name.
    label:
      (typeof p.about === 'string' && p.about.trim() !== '' && p.about) ||
      (typeof p.question === 'string' && p.question.trim() !== '' && p.question) ||
      p.id,
    // CARRIED, because `confirmProposal` routes a run-owned answer to the run and reads
    // ownership from here. Dropped, it sent every answer to the record route, which
    // refuses a run-owned key with `409 belongs_to_a_run` once a record has runs.
    run_id: p.run_id ?? null,
  }));
}

export function useRecordSession(
  id: string,
  { detail, onChange, enabled = true }: UseRecordSessionOptions,
): RecordSession {
  const version = detail?.version;
  // Derived from `version`, NOT read from `detail.rev` independently, so the rev
  // the AgentContext/confirmProposal staleness guard uses always matches the
  // If-Match token (no rev/version desync window).
  const recordRev = deriveRev(version, detail);
  const active = enabled && !!id && !!version;

  // The additive AgentContext inputs + their honest degraded flag.
  const [extras, setExtras] = useState<AgentExtras | null>(null);
  const [contextDegraded, setContextDegraded] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  // The P29.1 session snapshot. Re-read imperatively after a change/refresh so a
  // proposal marked stale by a revision change is immediately visible.
  const [session, setSession] = useState(() => loadSession(id));

  // Stale-guard: the CURRENT record id, read at response-resolve time so an
  // out-of-order/aborted extras fetch for a previous record cannot clobber the
  // currently-selected one (the useRecordSync currentRef pattern).
  const currentRef = useRef(id);
  currentRef.current = id;

  // Latest onChange without re-subscribing the poller effect.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Reload the session snapshot whenever the record changes.
  useEffect(() => {
    setSession(loadSession(id));
    setConflict(false);
  }, [id]);

  // Fetch the AgentContext inputs (pending + evidence classification). Keyed on
  // the authoritative version so an adopted revision re-derives the context. A
  // failure raises the agent `degraded` flag ONLY — the manual workflow, driven
  // by the screen's own bundle, is never blocked here.
  useEffect(() => {
    if (!active) return;
    const startedFor = id;
    let alive = true;
    Promise.all([api.getPending(id), api.getEvidenceClassification(id)])
      .then(([pending, classification]) => {
        if (!alive || currentRef.current !== startedFor) return; // superseded → drop
        setExtras({ pending, classification });
        setContextDegraded(false);
      })
      .catch(() => {
        if (!alive || currentRef.current !== startedFor) return;
        setContextDegraded(true); // honest agent degrade; manual UI unaffected
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, version, active, refreshNonce]);

  // A change signal was adopted (version advanced) → no longer in conflict.
  useEffect(() => {
    setConflict(false);
  }, [version]);

  // The ONE poller for this record. On a change signal, invalidate any staged
  // proposal grounded in the OLD revision, surface the stale flag, raise
  // `conflict`, then delegate to the screen's handler (refetch or banner).
  const handleChanged = useCallback(
    (fresh: ApiExperimentDetail) => {
      // Use the version-derived rev of the FRESH detail so it matches the rev a
      // proposal was staged against (also version-derived) — the two staleness
      // signals stay on the same axis.
      const freshRev = deriveRev(fresh.version, fresh);
      if (freshRev !== undefined) invalidateStaleProposals(id, freshRev);
      setSession(loadSession(id));
      setConflict(true);
      onChangeRef.current?.(fresh);
    },
    [id],
  );

  const { degraded: syncDegraded, checkNow } = useRecordSync(id, version, {
    onChanged: handleChanged,
    enabled,
  });

  const refresh = useCallback(() => {
    setConflict(false);
    setSession(loadSession(id));
    setRefreshNonce((n) => n + 1);
  }, [id]);

  // The AgentContext inputs have SETTLED once they either loaded (`extras`) or
  // failed (`contextDegraded`). Until then we are LOADING, not degraded.
  const settled = !!extras || contextDegraded;
  const loading = active && !settled;

  const context = useMemo<AgentContext | undefined>(() => {
    // Only expose a context once the record detail is present AND its inputs have
    // settled — never a half-built context mid-load (which would flash degraded).
    if (!detail || !settled) return undefined;
    return {
      experimentId: id,
      // Version-derived (see deriveRev) so rev and version never disagree.
      recordRev: deriveRev(detail.version, detail) ?? detail.rev,
      version: detail.version,
      workflow: {
        current_step: detail.workflow.current_step,
        ordered_steps: toWorkflowSteps(detail),
      },
      evidence: toEvidenceViews(extras?.classification),
      pending: toPendingItems(extras?.pending),
      // Degraded ONLY when a fetch actually FAILED — loading is never degraded.
      degraded: contextDegraded,
    };
  }, [detail, id, extras, contextDegraded, settled]);

  return {
    version,
    recordRev,
    context,
    loading,
    session,
    syncDegraded,
    // True ONLY after an AgentContext-input fetch actually failed — a healthy
    // slow-network mount stays `loading`, never flashes the degraded banner.
    degraded: contextDegraded,
    conflict,
    refresh,
    checkNow,
  };
}
