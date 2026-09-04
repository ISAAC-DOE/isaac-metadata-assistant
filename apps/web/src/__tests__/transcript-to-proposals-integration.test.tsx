/*
 * I4, independent review of PR-D: "Review N Proposals" moving focus to
 * `IngestionProposalsPanel`'s `tabIndex={-1}` heading was previously pinned only
 * against a stand-in `<h2 id="ingestion-proposals-heading">` built inside
 * `transcript-capture.test.tsx` — a shape any component could produce, including
 * one that never gave its own real heading the same id or the same `tabIndex`.
 * This file renders the REAL `IngestionProposalsPanel` beside the REAL
 * `TranscriptCapturePanel`, exactly as `RecordWorkbench` mounts them, and asserts
 * `document.activeElement` actually becomes that heading.
 *
 * WHY THIS IS A GENUINE MUTATION GUARD, NOT JUST A RENDER TEST. jsdom (like every
 * real browser) refuses to move focus onto an element with no `tabIndex` — calling
 * `.focus()` on a bare `<h2>` is a silent no-op. So if `IngestionProposalsPanel`'s
 * heading ever lost its `tabIndex={-1}`, `reviewProposals()`'s `heading.focus()`
 * would do nothing, and this test's `document.activeElement` assertion would fail
 * — with no need to hand-delete the attribute to prove it.
 *
 * Every fixture is synthetic and no test here reaches a backend.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { TranscriptCapturePanel } from '../components/TranscriptCapturePanel';
import { IngestionProposalsPanel } from '../components/IngestionProposalsPanel';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';
import { CAPTURE_GUIDANCE_KEY } from '../lib/transcriptCapturePreference';
import {
  runFixture,
  stubFetchRoutes,
  PROPOSAL_TARGET_PATHS,
  PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
} from '../test/apiFixtures';
import type { ApiProposal, ApiProposalsResponse } from '../lib/types';

const EXP = 'demo';
const RUNS = `GET /api/experiments/${EXP}/runs`;
const CAPS = 'GET /api/providers/capabilities';
const TRANSCRIPT = `POST /api/experiments/${EXP}/transcript`;
const LIST = `GET /api/experiments/${EXP}/proposals`;

const RUN = runFixture({ id: 'run-1', label: 'Run 1', version: 'r1.0', fields: {} });
const runsPage = { runs: [RUN], experiment_version: 'g1.4', total: 1, matched: 1, returned: 1, offset: 0 };

const capabilities = {
  any_provider_configured: false,
  decision_reference: 'docs/ai-integration-decision-packet.md',
  note: 'A note the server composes.',
  manual_transcript_available: true,
  seams: [
    {
      seam: 'transcription',
      implementation: 'unconfigured',
      configured: false,
      is_test_double: false,
      reason: 'No transcription provider is configured.',
      selected_by: 'ISAAC_TRANSCRIPTION_PROVIDER',
    },
  ],
};

function readingWithOneProposal() {
  return {
    capture: {
      finalized: true,
      run_id: 'run-1',
      segments: 1,
      retention: {
        state: 'retained_with_experiment',
        notes_captured: 1,
        deletable: false,
        description: 'The finalized transcript is stored with this record as notes.',
        not_implemented: [],
        raw_audio: { stored: false, reason: 'No audio reaches this server.' },
      },
    },
    applied: false,
    candidates: [
      {
        field_path: 'context.temperature_K',
        proposed_value: 300,
        quote: 'Temperature was 300 K.',
        start_char: 0,
        end_char: 22,
        origin: 'transcript',
        produced_by: 'transcript-reader',
        rule: 'temperature_kelvin',
        provenance: { reader_rule: 'temperature_kelvin' },
        status: 'needs_confirmation',
        verified: false,
        is_evidence: false,
        requires_user_confirmation: true,
      },
    ],
    clarifications: [],
    abstentions: [],
    review_required: [],
    notes: [
      {
        id: 'n1',
        experiment_id: EXP,
        run_id: 'run-1',
        source: 'transcript',
        text: 'Temperature was 300 K.',
        revised_text: null,
        captured_utc: '2099-04-02T09:12:00Z',
        state: 'unreviewed',
        candidate_field_path: null,
        candidate_rule: null,
        mapped_field_path: null,
        history: [],
        status: 'unmapped_note',
        verified: false,
        is_evidence: false,
        is_field_value: false,
        display_text: 'Temperature was 300 K.',
      },
    ],
    proposals: [
      {
        candidate_index: 0,
        client_request_key: 'transcript-capture:n1:0',
        deduplicated: false,
        proposal: {
          proposal_id: 'p0',
          experiment_id: EXP,
          note_id: 'n1',
          run_id: 'run-1',
          target_field_path: 'context.temperature_K',
          proposed_value: 300,
          rule: 'temperature_kelvin',
          state: 'open',
          applied: false,
          verified: false,
          is_evidence: false,
          is_field_value: false,
        },
      },
    ],
    unproposable: [],
    ambiguity_policy: [],
    accept_contract: {
      method: 'POST',
      path: '/api/experiments/{experiment_id}/proposals/{proposal_id}/review',
      requires: ['confirmed_by_user: true', 'action: accept'],
      message: 'This operation writes no field.',
    },
    experiment_version: 'g1.5',
  };
}

function proposalFixture(over: Partial<ApiProposal> = {}): ApiProposal {
  return {
    proposal_id: 'p0',
    experiment_id: EXP,
    note_id: 'n1',
    run_id: 'run-1',
    target_field_path: 'context.temperature_K',
    proposed_value: 300,
    rule: 'temperature_kelvin',
    source: 'transcript',
    proposed_utc: '2099-04-02T09:12:00Z',
    base_rev: 1,
    target_digest: 'digest-at-proposal-time',
    start_char: 0,
    end_char: 22,
    client_request_key: 'transcript-capture:n1:0',
    state: 'open',
    subject: null,
    trust_basis: 'unattributed',
    accepted_value: null,
    accepted_from: null,
    applied_via: null,
    applied_run_id: null,
    applied_rev: null,
    applied_target_digest: null,
    history: [],
    status: 'ingestion_proposal',
    verified: false,
    is_evidence: false,
    is_field_value: false,
    applied: false,
    current_target_digest: 'digest-at-proposal-time',
    target_stale: false,
    still_current: null,
    excerpt: 'Temperature was 300 K.',
    attributed: false,
    accepted_by: null,
    ...over,
  };
}

function proposalsPage(
  proposals: ApiProposal[],
  over: Partial<ApiProposalsResponse> = {},
): ApiProposalsResponse {
  return {
    proposals,
    total: proposals.length,
    returned: proposals.length,
    by_state: {
      open: proposals.length,
      accepted: 0,
      rejected: 0,
      superseded: 0,
      withdrawn: 0,
    },
    has_more: false,
    next_cursor: null,
    order: 'oldest_first' as const,
    window_default: 50,
    window_max: 200,
    max_per_record: 1000,
    unreadable_entries: 0,
    target_field_paths: PROPOSAL_TARGET_PATHS,
    record_scoped_target_field_paths: PROPOSAL_RECORD_SCOPED_TARGET_PATHS,
    states: ['open', 'accepted', 'rejected', 'superseded', 'withdrawn'],
    review_actions: ['accept', 'reject', 'supersede', 'withdraw'],
    accepted_from_values: ['candidate', 'edited'],
    experiment_version: 'g1.5',
    ...over,
  };
}

// jsdom implements no `scrollIntoView`.
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = function scrollIntoViewPolyfill() {
    /* no-op: jsdom has no layout, so there is nothing to scroll */
  };
}

beforeEach(() => {
  try {
    localStorage.setItem(
      CAPTURE_GUIDANCE_KEY,
      JSON.stringify({
        guidanceId: 'isaac-transcript-capture-guidance',
        version: 1,
        seen: true,
        seenAt: '2099-01-01T00:00:00Z',
      }),
    );
  } catch {
    /* the read path fails safe */
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Review N Proposals moves focus into the REAL Ingestion Proposals heading', () => {
  it('MUTATION-GUARDED: focus lands on the panel\'s own tabIndex={-1} heading, not merely a matching id in isolation', async () => {
    stubFetchRoutes({
      [RUNS]: { body: runsPage },
      [CAPS]: { body: capabilities },
      [TRANSCRIPT]: { body: readingWithOneProposal() },
      [LIST]: { body: proposalsPage([proposalFixture()]) },
    } as never);

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TranscriptCapturePanel experimentId={EXP} />
        <IngestionProposalsPanel experimentId={EXP} />
      </MemoryRouter>,
    );

    // Confirm the real panel's heading exists ahead of time, exactly as
    // `IngestionProposalsPanel.tsx` renders it — an `id` and a `tabIndex={-1}`.
    const heading = await screen.findByRole('heading', { name: /ingestion proposals/i });
    expect(heading.id).toBe('ingestion-proposals-heading');
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(document.activeElement).not.toBe(heading);

    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.entryOpen }));
    const box = await screen.findByLabelText('Transcript');
    fireEvent.change(box, { target: { value: 'Temperature was 300 K.' } });
    fireEvent.change(await screen.findByLabelText(CAPTURE_COPY.runLabel), {
      target: { value: 'run-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: CAPTURE_COPY.finalize }));

    const reviewButton = await screen.findByRole('button', {
      name: CAPTURE_COPY.reviewProposals(1),
    });
    fireEvent.click(reviewButton);

    await waitFor(() => expect(document.activeElement).toBe(heading));
  });
});
