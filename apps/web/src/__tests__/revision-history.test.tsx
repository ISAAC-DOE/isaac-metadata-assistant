/**
 * SUBMISSION HISTORY — the read surface, and the honesty contract it exists under.
 *
 * THE TEST THAT MATTERS MOST IS THE FIRST ONE. The submission-history tables are
 * created by a migration an OPERATOR applies, separately from the image, and on
 * this deployment they have not been applied — so "this record has no submitted
 * revisions" and "this server could not find out" are both reachable, and they look
 * identical unless the surface is careful. The API answers `503` with NO `revisions`
 * key in the second case; this panel must render the server's own sentence and must
 * not render an empty history. The opposite direction is pinned too, because
 * without it the guard would be vacuous: a genuinely empty history renders as one.
 *
 * The rest of the contract:
 *   - an unattributable revision names NOBODY. No "System", no "Unknown user", no
 *     dash standing in for a name, no fallback to the deployment;
 *   - a name recorded on a test-fixture basis says what that basis is worth;
 *   - export is never called a submission, in any state;
 *   - "this deployment cannot accept a submission" never lowers "this record is
 *     ready" — two facts about two subjects, two blocks, two headings;
 *   - absence is never rendered as a value, and a value that cannot be shown on one
 *     line says so rather than being reported as absent;
 *   - no evaluative or causal vocabulary anywhere in the rendered text.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import { RevisionHistoryPanel } from '../components/RevisionHistoryPanel';
import {
  NO_ACTOR_TEXT,
  actorBasisNote,
  actorText,
  diffChangeWord,
  recordedChangeWord,
  sideSentence,
  sideText,
} from '../lib/revisionHistory';
import { stubFetchRoutes } from '../test/apiFixtures';
import type {
  ApiLifecycle,
  ApiRevisionActor,
  ApiRevisionDetail,
  ApiRevisionDiff,
  ApiRevisionHistory,
  ApiRevisionSummary,
} from '../lib/types';

const EXP = 'demo';
const LIST = `GET /api/experiments/${EXP}/revisions`;
const DETAIL = `GET /api/experiments/${EXP}/revisions/1`;
const DIFF = `GET /api/experiments/${EXP}/revisions/1/diff`;

const UNIT = '01UNITAAAAAAAAAAAAAAAAAAAA';

/** The message the server sends when the migration has not been applied. */
const TABLES_ABSENT_MESSAGE =
  "This deployment's database does not yet have the submission-history tables, so " +
  'the history could not be read. The migration that creates them has to be ' +
  'applied by an operator. This is not a statement that this record has never ' +
  'been submitted — it is a statement that this server could not find out.';

const READ_MESSAGE =
  "The submission history was read from this deployment's database. An empty list " +
  'here means this record has no submitted revisions.';

const ATTRIBUTED: ApiRevisionActor = {
  subject: 'ada.lovelace',
  trust_basis: 'test_fixture',
  attributed: true,
};

const UNATTRIBUTED: ApiRevisionActor = {
  subject: null,
  trust_basis: 'unattributed',
  attributed: false,
};

function lifecycle(overrides: Partial<ApiLifecycle> = {}): ApiLifecycle {
  return {
    state: 'ready_to_submit',
    label: 'Ready to Submit',
    reasons: [
      {
        code: 'no_scientific_blockers',
        message: 'Every question is answered and every unit passes the export gate.',
      },
    ],
    scientific_readiness: {
      blocked: false,
      pending_count: 0,
      failing_unit_count: 0,
      failing_units: [],
    },
    submission: {
      known: true,
      submitted_for_current_content: false,
      unknown_reason: null,
    },
    submission_blocked_by_deployment: {
      blocked: false,
      blockers: [],
      basis: 'configuration_only',
      requires_attributable_actor: true,
      actor_trust_basis: null,
      message: 'This deployment is configured to accept a submission.',
    },
    ...overrides,
  };
}

function revision(overrides: Partial<ApiRevisionSummary> = {}): ApiRevisionSummary {
  return {
    revision_no: 1,
    revision_id: '01REVISIONAAAAAAAAAAAAAAAA',
    reason: 'submission',
    created_utc: '2026-01-01T00:00:00+00:00',
    experiment_rev: 3,
    content_signature: 'a'.repeat(64),
    actor: ATTRIBUTED,
    change_counts: {},
    submission: {
      submission_id: '01SUBMISSIONAAAAAAAAAAAAAA',
      submitted_utc: '2026-01-01T00:00:00+00:00',
      unit_count: 1,
      idempotency_key_used: false,
      actor: ATTRIBUTED,
      conflict_summary: {},
    },
    ...overrides,
  };
}

function history(overrides: Partial<ApiRevisionHistory> = {}): ApiRevisionHistory {
  return {
    experiment_id: EXP,
    record_rev: 3,
    current_content_signature: 'b'.repeat(64),
    signature_scope: 'export_unit_ids_drafts_and_conflict_decisions',
    limit: 200,
    availability: { state: 'available', reason: null, message: READ_MESSAGE },
    lifecycle: lifecycle(),
    revisions: [],
    total: 0,
    returned: 0,
    current_submission: null,
    ...overrides,
  };
}

function detail(overrides: Partial<ApiRevisionDetail> = {}): ApiRevisionDetail {
  return {
    experiment_id: EXP,
    revision_no: 1,
    availability: { state: 'available', reason: null, message: READ_MESSAGE },
    revision: {
      ...revision(),
      run_revisions: [],
      changes: [],
      changes_scope: 'draft_field_values_only',
      submission_runs: [],
    },
    ...overrides,
  };
}

function diff(overrides: Partial<ApiRevisionDiff> = {}): ApiRevisionDiff {
  return {
    experiment_id: EXP,
    revision_no: 1,
    record_rev: 3,
    current_content_signature: 'b'.repeat(64),
    changes_scope: 'draft_field_values_only',
    availability: { state: 'available', reason: null, message: READ_MESSAGE },
    comparable: true,
    content_signature_matches: true,
    revision: { ...revision(), run_labels: {} },
    changes: [],
    change_counts: { added: 0, removed: 0, modified: 0 },
    units: { comparable: true, added: [], removed: [], unchanged: [UNIT] },
    current_run_labels: {},
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

/* ── 1. cannot-know is never rendered as nothing ───────────────────────────── */

describe('an unreadable history', () => {
  it('renders the server sentence and NOT an empty history', async () => {
    stubFetchRoutes({
      [LIST]: {
        status: 503,
        body: {
          error: 'revision_history_unavailable',
          experiment_id: EXP,
          record_rev: 3,
          current_content_signature: 'b'.repeat(64),
          signature_scope: 'export_unit_ids_drafts_and_conflict_decisions',
          limit: 200,
          availability: {
            state: 'unavailable',
            reason: 'tables_absent',
            message: TABLES_ABSENT_MESSAGE,
          },
          lifecycle: lifecycle({
            submission: {
              known: false,
              submitted_for_current_content: null,
              unknown_reason: 'tables_absent',
            },
          }),
        },
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);

    expect(
      await screen.findByRole('heading', { name: /Submission history could not be read/i }),
    ).toBeTruthy();
    expect(screen.getByText(TABLES_ABSENT_MESSAGE)).toBeTruthy();
    // THE POINT: no claim that the record has no revisions.
    expect(screen.queryByText(/has no submitted revisions/i)).toBeNull();
    expect(screen.queryByRole('list', { name: /revision/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Revision 1/ })).toBeNull();
    // And the lifecycle says the submitted-ness is unknown, never "no".
    expect(screen.getByText(/unknown here, not no/i)).toBeTruthy();
  });

  it('renders a genuinely empty history AS empty — the guard is not vacuous', async () => {
    stubFetchRoutes({ [LIST]: { body: history() } });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    expect(await screen.findByText(/This record has no submitted revisions/)).toBeTruthy();
    expect(
      screen.queryByRole('heading', { name: /could not be read/i }),
    ).toBeNull();
  });

  it('renders a worked-example record as having no history rather than as a failure', async () => {
    const message =
      'Records in a worked-example session are temporary and are discarded with the ' +
      'session, so they are never submitted and have no submission history.';
    stubFetchRoutes({
      [LIST]: {
        body: history({
          availability: {
            state: 'not_applicable',
            reason: 'worked_example_session',
            message,
          },
          revisions: undefined,
          total: undefined,
          returned: undefined,
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    expect(await screen.findByText(message)).toBeTruthy();
    expect(
      screen.queryByRole('heading', { name: /could not be read/i }),
    ).toBeNull();
  });
});

/* ── 2. the actor is never invented ────────────────────────────────────────── */

describe('attribution', () => {
  it('says nobody was recorded rather than naming a placeholder', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: history({
          revisions: [revision({ actor: UNATTRIBUTED, submission: null })],
          total: 1,
          returned: 1,
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);

    expect(await screen.findByText(NO_ACTOR_TEXT)).toBeTruthy();
    const text = document.body.textContent ?? '';
    for (const invented of [
      'System',
      'Unknown user',
      'Anonymous',
      'ISAAC user',
      'N/A',
      'someone',
    ]) {
      expect(text.toLowerCase()).not.toContain(invented.toLowerCase());
    }
  });

  it('says what a test-fixture attribution is worth', async () => {
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    expect(await screen.findByText(/ada\.lovelace/)).toBeTruthy();
    expect(screen.getByText(/not proof anyone authenticated/i)).toBeTruthy();
  });
});

/* ── 3. export is never a submission, and infrastructure never lowers the state ─ */

describe('the lifecycle', () => {
  it('renders the server label and never calls an export a submission', async () => {
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [], total: 0, returned: 0 }) },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);

    expect(await screen.findByText('Ready to Submit')).toBeTruthy();
    const text = (document.body.textContent ?? '').toLowerCase();
    // A record this fixture describes is export-ready. Nothing may present that
    // as a submission, in any phrasing.
    expect(text).not.toMatch(/export(ed|ing)?[^.]{0,40}\bsubmitted\b/);
    expect(text).not.toMatch(/\bsubmitted\b[^.]{0,40}\bexport(ed)?\b/);
    expect(screen.queryByText(/^Submitted$/)).toBeNull();
  });

  it('reports a deployment that cannot submit WITHOUT lowering the record state', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: history({
          lifecycle: lifecycle({
            submission_blocked_by_deployment: {
              blocked: true,
              blockers: ['no_attributable_actor', 'no_durable_storage'],
              basis: 'configuration_only',
              requires_attributable_actor: true,
              actor_trust_basis: null,
              message:
                'This deployment cannot currently accept a submission of any record. ' +
                'This says nothing about whether this record is ready — it is a fact ' +
                'about how this server is configured, and it is resolved by an ' +
                'operator, not by editing the record.',
            },
          }),
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);

    // The record's own state is UNCHANGED...
    expect(await screen.findByText('Ready to Submit')).toBeTruthy();
    // ...and the deployment fact is its own block with its own heading.
    const block = screen.getByRole('note', {
      name: /Submitting is unavailable in this deployment/i,
    });
    expect(within(block).getByText(/says nothing about whether this record is ready/i)).toBeTruthy();
    expect(within(block).getByText(/No attributable person can be established/i)).toBeTruthy();
  });

  it('renders an unrecognised deployment blocker verbatim rather than hiding it', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: history({
          lifecycle: lifecycle({
            submission_blocked_by_deployment: {
              blocked: true,
              blockers: ['some_future_blocker'],
              basis: 'configuration_only',
              requires_attributable_actor: true,
              actor_trust_basis: null,
              message: 'This deployment cannot currently accept a submission.',
            },
          }),
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    expect(await screen.findByText('some_future_blocker')).toBeTruthy();
  });
});

/* ── 4. the diff ───────────────────────────────────────────────────────────── */

describe('comparing the record with a revision', () => {
  function withRevision(extra: Record<string, unknown> = {}) {
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: { body: diff(extra) },
    });
  }

  it('shows the field, both values and the difference, and renders absence as absence', async () => {
    withRevision({
      content_signature_matches: false,
      changes: [
        {
          unit_id: UNIT,
          address: 'sample.material.name',
          change_kind: 'modified',
          previous_value: 'Copper oxide',
          current_value: 'Cuprite',
        },
        {
          unit_id: UNIT,
          address: 'context.environment',
          change_kind: 'removed',
          previous_value: 'ambient',
          current_value: null,
        },
        {
          unit_id: UNIT,
          address: 'sample.geometry.pellet_diameter_mm',
          change_kind: 'added',
          previous_value: null,
          current_value: 13,
        },
        {
          unit_id: UNIT,
          address: 'descriptors.block',
          change_kind: 'modified',
          previous_value: { a: 1 },
          current_value: { a: 2 },
        },
      ],
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);

    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    const table = await screen.findByRole('table');
    const rows = within(table).getAllByRole('row');

    const modified = rows.find((r) => r.textContent?.includes('sample.material.name'))!;
    expect(modified.textContent).toContain('Copper oxide');
    expect(modified.textContent).toContain('Cuprite');
    expect(modified.textContent).toContain('Different values');

    // ABSENCE IS NOT A VALUE: it gets its own sentence, never a blank cell.
    const removed = rows.find((r) => r.textContent?.includes('context.environment'))!;
    expect(removed.textContent).toContain('No value recorded');
    expect(removed.textContent).toContain('In this revision, not recorded now');

    const added = rows.find((r) =>
      r.textContent?.includes('sample.geometry.pellet_diameter_mm'),
    )!;
    expect(added.textContent).toContain('Recorded now, not in this revision');

    // A value that cannot be shown on one line SAYS SO, and is never reported as
    // absent and never truncated.
    const block = rows.find((r) => r.textContent?.includes('descriptors.block'))!;
    expect(block.textContent).toContain('cannot be shown on one line');
    expect(block.textContent).not.toContain('No value recorded');
  });

  it('states that nothing differs beside a matching signature', async () => {
    withRevision({ content_signature_matches: true, changes: [] });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    expect(
      await screen.findByText(/holds exactly the content that was submitted/i),
    ).toBeTruthy();
  });

  it('says the comparison did not look everywhere when the signature differs but no field does', async () => {
    withRevision({ content_signature_matches: false, changes: [] });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    expect(
      await screen.findByText(/Something outside draft field values differs/i),
    ).toBeTruthy();
  });

  it('renders an unreadable snapshot as a stated absence of comparison, not an empty table', async () => {
    const note =
      'The snapshot stored for this revision could not be read back into a ' +
      'comparable record, so no field comparison was made.';
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: {
        body: {
          ...diff(),
          comparable: false,
          comparable_note: note,
          changes: undefined,
          change_counts: undefined,
          units: { comparable: false, added: [], removed: [], unchanged: [] },
        },
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    expect(await screen.findByText(note)).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('reports an added run once, at the altitude a reader arrives with', async () => {
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: {
        body: diff({
          content_signature_matches: false,
          units: { comparable: true, added: [UNIT], removed: [], unchanged: [] },
          current_run_labels: { [UNIT]: 'Run B' },
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    expect(
      await screen.findByText(/Recorded now and not in this revision: Run B/),
    ).toBeTruthy();
  });
});

/* ── 5. the rendered vocabulary ────────────────────────────────────────────── */

it('renders no evaluative or causal vocabulary anywhere it can reach', async () => {
  stubFetchRoutes({
    [LIST]: { body: history({ revisions: [revision({ actor: UNATTRIBUTED })], total: 1, returned: 1 }) },
    [DETAIL]: {
      body: detail({
        revision: {
          ...revision(),
          run_revisions: [
            {
              run_revision_id: '01RUNREVAAAAAAAAAAAAAAAAAA',
              run_id: UNIT,
              ordinal: 0,
              rev: 1,
              generation: 'gen000001',
              created_utc: '2026-01-01T00:00:00+00:00',
              label: 'Run A',
            },
          ],
          changes: [{ unit_id: UNIT, address: 'sample.material.name', change_kind: 'modified' }],
          changes_scope: 'draft_field_values_only',
          submission_runs: [],
        },
      }),
    },
    [DIFF]: {
      body: diff({
        content_signature_matches: false,
        changes: [
          {
            unit_id: UNIT,
            address: 'sample.material.name',
            change_kind: 'modified',
            previous_value: 'Copper oxide',
            current_value: 'Cuprite',
          },
        ],
      }),
    },
  });
  render(<RevisionHistoryPanel experimentId={EXP} />);
  fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
  await screen.findByRole('table');

  const text = (document.body.textContent ?? '').toLowerCase();
  for (const banned of [
    'mismatch',
    'problem',
    'wrong',
    'better',
    'worse',
    'regression',
    'improved',
    'suspicious',
    'because of',
  ]) {
    expect(text).not.toContain(banned);
  }
});

/* ── 6. the pure helpers ───────────────────────────────────────────────────── */

describe('the words', () => {
  it('never returns a name for an unattributed actor', () => {
    expect(actorText(UNATTRIBUTED)).toBe(NO_ACTOR_TEXT);
    expect(actorText(null)).toBe(NO_ACTOR_TEXT);
    expect(actorText(undefined)).toBe(NO_ACTOR_TEXT);
    expect(actorText({ subject: 'x', trust_basis: 'unattributed', attributed: false })).toBe(
      NO_ACTOR_TEXT,
    );
    expect(actorText(ATTRIBUTED)).toBe('ada.lovelace');
  });

  it('qualifies a fixture basis and stays silent about a verified one', () => {
    expect(actorBasisNote(ATTRIBUTED)).toMatch(/not proof anyone authenticated/);
    expect(
      actorBasisNote({
        subject: 'a',
        trust_basis: 'verified_edge_assertion',
        attributed: true,
      }),
    ).toBeNull();
    expect(actorBasisNote(UNATTRIBUTED)).toBeNull();
  });

  it('names which moment holds the value, and reuses the one word that fits', () => {
    expect(diffChangeWord('added')).toBe('Recorded now, not in this revision');
    expect(diffChangeWord('removed')).toBe('In this revision, not recorded now');
    // Reused verbatim from `runCompare.categoryWord('value')` — the one case where
    // the two comparisons genuinely coincide.
    expect(diffChangeWord('modified')).toBe('Different values');
    expect(recordedChangeWord('added')).toBe('Added');
  });

  it('tells absence and unrenderability apart', () => {
    expect(sideSentence(sideText(null))).toBe('No value recorded');
    expect(sideSentence(sideText(undefined))).toBe('No value recorded');
    expect(sideSentence(sideText({ a: 1 }))).toMatch(/cannot be shown on one line/);
    expect(sideSentence(sideText([1, 2]))).toMatch(/cannot be shown on one line/);
    expect(sideSentence(sideText(0))).toBe('0');
    expect(sideSentence(sideText(false))).toBe('false');
    // An empty string is a RECORDED value that renders as nothing. It gets its
    // own sentence rather than being reported as absent or shown as a blank cell.
    expect(sideSentence(sideText(''))).toBe('An empty value is recorded here');
  });
});

/* ── 7. a failure this panel cannot describe is still a failure ────────────── */

it('renders the backend-down state for a response that is not a history envelope', async () => {
  stubFetchRoutes({
    [LIST]: { status: 503, body: { error: 'experiment_storage_unavailable' } },
  });
  render(<RevisionHistoryPanel experimentId={EXP} />);
  await waitFor(() =>
    expect(screen.queryByText(/Loading submission history/i)).toBeNull(),
  );
  // No availability sentence is invented for a body that carried none.
  expect(screen.queryByText(TABLES_ABSENT_MESSAGE)).toBeNull();
  expect(screen.queryByText(/has no submitted revisions/i)).toBeNull();
});

/* ── 8. every changed row says which unit it belongs to ─────────────────────
 *
 * REGRESSION FROM INDEPENDENT REVIEW. No test anywhere exercised a REMOVED unit
 * — `units.removed` was `[]` in every route test and every component fixture —
 * and that is exactly the case the diff table could not describe.
 */

describe('unit attribution in the diff table', () => {
  const REMOVED = '01UNITBBBBBBBBBBBBBBBBBBBB';

  it('attributes a row whose run was REMOVED since the revision', async () => {
    // `current_run_labels` is built from CURRENT units only, so a removed run is
    // absent from it by construction. Reading it alone left these rows with no
    // annotation at all — indistinguishable from a record-level field, and in a
    // record where one run was deleted and another edited, two rows with the
    // same address and no way to tell them apart.
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: {
        body: diff({
          content_signature_matches: false,
          changes: [
            {
              unit_id: UNIT,
              address: 'sample.composition',
              change_kind: 'modified',
              previous_value: 'CuO',
              current_value: 'Cu2O',
            },
            {
              unit_id: REMOVED,
              address: 'sample.composition',
              change_kind: 'removed',
              previous_value: 'CuO',
              current_value: null,
            },
          ],
          change_counts: { added: 0, removed: 1, modified: 1 },
          units: { comparable: true, added: [], removed: [REMOVED], unchanged: [UNIT] },
          current_run_labels: { [UNIT]: 'Run C' },
          revision: { ...revision(), run_labels: { [REMOVED]: 'Run B' } },
        } as Partial<ApiRevisionDiff>),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));

    // BOTH rows are attributed, and to DIFFERENT units. Before the fix the
    // second carried no annotation at all.
    expect(await screen.findByText(/· Run C/)).toBeTruthy();
    expect(await screen.findByText(/· Run B/)).toBeTruthy();
  });

  it('never prints a bare identifier when neither side recorded a label', async () => {
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: {
        body: diff({
          content_signature_matches: false,
          units: { comparable: true, added: [], removed: [REMOVED], unchanged: [] },
          current_run_labels: {},
          revision: { ...revision(), run_labels: {} },
        } as Partial<ApiRevisionDiff>),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));

    // The id is shown AS an id, the treatment `RevisionSnapshot` already uses —
    // never a naked ULID a reader would mistake for a name.
    expect(
      await screen.findByText(new RegExp(`a run with no recorded label · ${REMOVED}`)),
    ).toBeTruthy();
  });

  it('calls the record the record, when the unit IS the record', async () => {
    // `export_units` returns the RECORD ITSELF as the single unit of a record
    // with no runs. A record that had zero runs at revision time and has one now
    // produced `removed: [<experiment id>]`, rendered as "In this revision and
    // not recorded now: 01J…" — asserting a deletion where the record had simply
    // gained its first run.
    stubFetchRoutes({
      [LIST]: { body: history({ revisions: [revision()], total: 1, returned: 1 }) },
      [DETAIL]: { body: detail() },
      [DIFF]: {
        body: diff({
          content_signature_matches: false,
          units: { comparable: true, added: [UNIT], removed: [EXP], unchanged: [] },
          current_run_labels: { [UNIT]: 'Run A' },
          revision: { ...revision(), run_labels: {} },
        } as Partial<ApiRevisionDiff>),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));

    expect(
      await screen.findByText(/In this revision and not recorded now: this record/),
    ).toBeTruthy();
  });
});
