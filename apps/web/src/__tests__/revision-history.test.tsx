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
  SUBMITTED_IMMUTABLE_NOTE,
  SUBMITTED_REVISION_HEADING,
  WORKING_CHANGES_HEADING,
  actorBasisNote,
  actorText,
  diffChangeWord,
  recordedChangeWord,
  renameTrapNote,
  sideSentence,
  sideText,
  submittedRevisionText,
  workingState,
  workingStateSentence,
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

/**
 * Render the panel and OPEN "Submission Details".
 *
 * Since owner QA V1 (2026-09-22) the panel is ONE visible status line and the
 * cards sit behind that disclosure. `getByRole` ignores a `hidden` subtree, so a
 * role query against a closed disclosure would make every "is NOT rendered"
 * assertion in this file vacuous — it would pass because nothing is exposed, not
 * because the panel declined to render it. Every data-state test opens first.
 */
async function renderOpen() {
  render(<RevisionHistoryPanel experimentId={EXP} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Submission Details' }));
}

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
    await renderOpen();

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
    await renderOpen();
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
    await renderOpen();
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
    await renderOpen();

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
    await renderOpen();
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
    await renderOpen();

    expect(await screen.findByText('Ready to Submit')).toBeTruthy();
    const text = (document.body.textContent ?? '').toLowerCase();
    // A record this fixture describes is export-ready. Nothing may present that
    // as a submission, in any phrasing.
    expect(text).not.toMatch(/export(ed|ing)?[^.]{0,40}\bsubmitted\b/);
    expect(text).not.toMatch(/\bsubmitted\b[^.]{0,40}\bexport(ed)?\b/);

    /*
     * QA-010 — POLARITY CONTROLS, which is what that row actually asked for: "Each
     * needs a constructed false version to polarity-test." The two windows above
     * are `not.toMatch`, so they pass whether they are load-bearing or unfireable,
     * and the ledger recorded them as "unproven either way". They are proven here.
     *
     * *** AND WIDENING THEM WAS TRIED FIRST AND WAS WRONG. *** `[^.]` cannot span a
     * sentence boundary, so a two-sentence conflation ("the record was exported. it
     * is submitted") escapes — which looked like a gap worth closing with
     * `[\s\S]{0,40}`. Measured against the real rendered text, that widening FAILED
     * immediately, on:
     *
     *     "export gate.last submitted"
     *
     * — two ADJACENT BUT UNRELATED labels. `document.body.textContent` concatenates
     * across element boundaries with NO SEPARATOR, so a widened window stitches
     * unrelated UI strings into a sentence that was never written. **On a
     * textContent haystack, `[^.]` is not merely a sentence proxy — it is also the
     * only thing preventing cross-element false positives.** The windows stay as
     * they are, and the residual two-sentence gap is named rather than closed with
     * a guard that cries wolf.
     */
    for (const [label, re, violation] of [
      ['export→submitted', /export(ed|ing)?[^.]{0,40}\bsubmitted\b/, 'exported and therefore submitted'],
      ['submitted→export', /\bsubmitted\b[^.]{0,40}\bexport(ed)?\b/, 'submitted, which is the same as exported'],
    ] as const) {
      expect(
        re.test(violation),
        `${label}: this guard cannot fire, so its passing above means nothing. ` +
          `Constructed violation: ${JSON.stringify(violation)}`,
      ).toBe(true);
      // ...and it is not a regex that matches everything, which would be the other
      // way to be useless.
      expect(re.test('this record is ready to submit and has not been exported'), label).toBe(false);
    }
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
    await renderOpen();

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
    await renderOpen();
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
    await renderOpen();

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
    await renderOpen();
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));
    expect(
      await screen.findByText(/holds exactly the content that was submitted/i),
    ).toBeTruthy();
  });

  it('says the comparison did not look everywhere when the signature differs but no field does', async () => {
    withRevision({ content_signature_matches: false, changes: [] });
    await renderOpen();
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
    await renderOpen();
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
    await renderOpen();
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
  await renderOpen();
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
    await renderOpen();
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
    await renderOpen();
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
    await renderOpen();
    fireEvent.click(await screen.findByRole('button', { name: /Revision 1/ }));

    expect(
      await screen.findByText(/In this revision and not recorded now: this record/),
    ).toBeTruthy();
  });
});

/* ── REV-002 · the submitted snapshot versus the record now ───────────────── */

describe('REV-002 · Last Submitted Revision versus Current Working Changes', () => {
  /*
   * DEC-21, and the correction inside it. The owner rejected describing a
   * resubmission as "keep editing, then submit again" — mechanically true, and
   * an understatement of the modelling requirement. The UI must show the two as
   * TWO THINGS and must never describe a submitted revision as mutable.
   *
   * Measured 2026-09-13 before this block was written: neither phrase existed
   * anywhere in `apps/web/src`. So there is no failing assertion to invert here
   * and no prior coverage to preserve — there was none.
   *
   * WHAT EACH ASSERTION IS LOAD-BEARING FOR:
   *  · §1 the comparison is EXACT, over two signatures the server computed. The
   *    fixtures differ only in `content_signature`, so nothing else can be what
   *    moved the verdict.
   *  · §2 `unknown` is a first-class state. Collapsing it into "never
   *    submitted" would be a FALSE NEGATIVE on every deployment shipped today,
   *    where the history tables are unapplied and the server says so.
   *  · §3 an unsubmitted revision row is not a submission. Comparing against one
   *    answers a question nobody asked.
   *  · §4 the rename trap appears ONLY where it can bite.
   *  · §5 the scope is the SERVER's string, never a list written in the client.
   *  · §6 polarity — each of the four verdicts is shown to be reachable and
   *    distinct, so none of the above can be passing vacuously.
   */

  const SIG_SUBMITTED = 'c'.repeat(64);
  const SIG_NOW = 'd'.repeat(64);

  /** A submitted revision at `no`, carrying `sig`. */
  const submittedAt = (no: number, sig: string) => ({
    ...revision({ revision_no: no, content_signature: sig }),
  });

  it('§1 · says UNCHANGED when the record still matches the last submitted revision', () => {
    const state = workingState(
      history({
        current_content_signature: SIG_SUBMITTED,
        revisions: [submittedAt(4, SIG_SUBMITTED)],
        total: 1,
        returned: 1,
      }),
    );
    expect(state).toEqual({ kind: 'unchanged', revisionNo: 4 });
    expect(workingStateSentence(state)).toContain('revision 4');
    expect(workingStateSentence(state)).toMatch(/Nothing that a submission covers has changed/);
  });

  it('§1 · says CHANGED when only the signature differs', () => {
    const state = workingState(
      history({
        current_content_signature: SIG_NOW,
        revisions: [submittedAt(4, SIG_SUBMITTED)],
        total: 1,
        returned: 1,
      }),
    );
    expect(state).toEqual({ kind: 'changed', revisionNo: 4 });
    expect(workingStateSentence(state)).toMatch(
      /has changed since revision 4 was submitted/,
    );
    // It must not describe the submitted revision as having been edited.
    expect(workingStateSentence(state)).not.toMatch(/edit|revert|restore|updated the/i);
  });

  it('§1 · takes the NEWEST submitted revision, whatever order the server returned', () => {
    const ascending = workingState(
      history({
        current_content_signature: SIG_NOW,
        revisions: [submittedAt(1, SIG_NOW), submittedAt(7, SIG_SUBMITTED)],
      }),
    );
    const descending = workingState(
      history({
        current_content_signature: SIG_NOW,
        revisions: [submittedAt(7, SIG_SUBMITTED), submittedAt(1, SIG_NOW)],
      }),
    );
    // Revision 1 happens to MATCH the record now; revision 7 does not. If order
    // decided the answer, these two would disagree — and the one that read
    // revision 1 would report `unchanged`, the exact false reassurance this
    // assertion exists to refuse.
    expect(ascending).toEqual({ kind: 'changed', revisionNo: 7 });
    expect(descending).toEqual(ascending);
  });

  it('§2 · says UNKNOWN when the history could not be read — never "never submitted"', () => {
    for (const h of [
      /* `tables_absent` is the real reason on every deployment shipped today:
         the five submission-history tables are created by a migration an
         OPERATOR applies, separately from the image, and none has been applied
         anywhere. Taken from `RevisionHistoryReason` rather than invented — the
         first draft of this line used `migration_not_applied`, which is not a
         member, and `tsc -b` refused it. */
      history({ availability: { state: 'unavailable', reason: 'tables_absent', message: 'x' } }),
      history({ revisions: undefined }),
    ]) {
      const state = workingState(h);
      expect(state.kind).toBe('unknown');
      expect(state.revisionNo).toBeNull();
      const sentence = workingStateSentence(state);
      expect(sentence).toMatch(/unknown rather than no/);
      // The false negative this exists to refuse.
      expect(sentence).not.toMatch(/no submitted revision|has not been submitted/i);
    }
  });

  it('§3 · a revision with no submission is not compared against', () => {
    const state = workingState(
      history({
        current_content_signature: SIG_NOW,
        // A recorded revision that was never declared finished.
        revisions: [revision({ revision_no: 9, content_signature: SIG_NOW, submission: null })],
      }),
    );
    expect(state).toEqual({ kind: 'never_submitted', revisionNo: null });
    // Had it been compared, the matching signature would have said `unchanged` —
    // i.e. "already submitted" about a record that never was.
    expect(workingStateSentence(state)).toMatch(/no submitted revision yet/);
  });

  it('§4 · the rename trap is offered on UNCHANGED and on nothing else', () => {
    const unchanged = workingState(
      history({ current_content_signature: SIG_SUBMITTED, revisions: [submittedAt(4, SIG_SUBMITTED)] }),
    );
    expect(renameTrapNote(unchanged)).toMatch(/Renaming this record does not count as a change/);
    expect(renameTrapNote(unchanged)).toMatch(/already submitted/);

    for (const other of [
      workingState(history({ current_content_signature: SIG_NOW, revisions: [submittedAt(4, SIG_SUBMITTED)] })),
      workingState(history({ revisions: [] })),
      workingState(history({ revisions: undefined })),
    ]) {
      // A caution shown where it cannot apply is how a true sentence becomes
      // ignored. On `changed` the resubmission is accepted; on the other two
      // there is nothing to be refused against.
      expect(renameTrapNote(other)).toBeNull();
    }
  });

  it('§5 · renders both headings and the SERVER\'s scope string, not a local list', async () => {
    stubFetchRoutes({
      [`GET /api/experiments/${EXP}/revisions`]: {
        body: history({
          current_content_signature: SIG_SUBMITTED,
          revisions: [submittedAt(4, SIG_SUBMITTED)],
          total: 1,
          returned: 1,
        }),
      },
    } as never);
    await renderOpen();

    const card = await screen.findByRole('region', {
      name: `${SUBMITTED_REVISION_HEADING} and ${WORKING_CHANGES_HEADING}`,
    });
    expect(within(card).getByText(SUBMITTED_REVISION_HEADING)).toBeInTheDocument();
    expect(within(card).getByText(WORKING_CHANGES_HEADING)).toBeInTheDocument();
    expect(within(card).getByText(SUBMITTED_IMMUTABLE_NOTE)).toBeInTheDocument();
    // Verbatim, from the response. A client-authored list would go quietly false
    // the day the server's scope changes.
    expect(
      within(card).getByText('export_unit_ids_drafts_and_conflict_decisions'),
    ).toBeInTheDocument();
    expect(within(card).getByText(/Renaming this record does not count/)).toBeInTheDocument();
  });

  it('§6 · POLARITY — the four verdicts are reachable and pairwise distinct', () => {
    const seen = [
      workingState(history({ revisions: undefined })),
      workingState(history({ revisions: [] })),
      workingState(
        history({ current_content_signature: SIG_SUBMITTED, revisions: [submittedAt(4, SIG_SUBMITTED)] }),
      ),
      workingState(
        history({ current_content_signature: SIG_NOW, revisions: [submittedAt(4, SIG_SUBMITTED)] }),
      ),
    ];
    expect(seen.map((s) => s.kind)).toEqual([
      'unknown',
      'never_submitted',
      'unchanged',
      'changed',
    ]);
    // Four verdicts, four DIFFERENT sentences. A shared sentence would make the
    // assertions above pass while telling the reader nothing.
    const sentences = seen.map(workingStateSentence);
    expect(new Set(sentences).size).toBe(4);
  });
});

/* ── C-3 / C-4 · the two states the first version of REV-002 got wrong ────── */

describe('REV-002 · the third availability state, and the cell that read "None"', () => {
  /*
   * BOTH FOUND BY INDEPENDENT REVIEW, 2026-09-13, and both in the state that is
   * the ONLY one any shipped deployment reaches.
   *
   * C-3 · `RevisionHistoryState` has THREE members. `workingState` branched on
   *       `!== 'available'`, so `not_applicable` — which the server's own
   *       description calls "a fact rather than an inability: such records are
   *       never submitted", served with **200** — was reported as "This
   *       deployment could not read the submission history".
   *
   * C-4 · `revisionNo` is `null` for BOTH `unknown` and `never_submitted`, and the
   *       panel rendered `'None'` for either. On every deployment shipped today
   *       the tables are unapplied, so the state is `unknown` and a scientist read
   *       **"Last Submitted Revision · None"** about a history that had not been
   *       read — this module's own Rule 1 ("ABSENCE IS NOT A VALUE") broken by
   *       this module.
   *
   * The review also noted WHY neither was caught: the `unknown` render path, the
   * only one that ships, had no rendering coverage at all — the single test that
   * rendered the block rendered `unchanged`. That gap is closed here too.
   */

  const NOT_APPLICABLE = {
    state: 'not_applicable' as const,
    reason: 'worked_example_session' as const,
    message: 'A worked-example record is never submitted.',
  };

  it('C-3 · not_applicable is NEVER SUBMITTED, not "could not read"', () => {
    const state = workingState(history({ availability: NOT_APPLICABLE, revisions: [] }));
    expect(state).toEqual({ kind: 'never_submitted', revisionNo: null });

    const sentence = workingStateSentence(state);
    expect(sentence).toMatch(/no submitted revision yet/);
    // The exact inversion this closes: an inability claimed about a successful read.
    expect(sentence).not.toMatch(/could not read/i);
    expect(sentence).not.toMatch(/unknown rather than no/);
  });

  it('C-3 · not_applicable stays NEVER SUBMITTED even with revisions absent', () => {
    // The server sends no `revisions` key for a non-available state. The state must
    // decide, not the presence of the key — otherwise the `undefined` guard below
    // would drag it back into `unknown`.
    const state = workingState(
      history({ availability: NOT_APPLICABLE, revisions: undefined }),
    );
    expect(state.kind).toBe('never_submitted');
  });

  it('C-3 · unavailable is STILL unknown — the other direction is not broken', () => {
    const state = workingState(
      history({
        availability: { state: 'unavailable', reason: 'tables_absent', message: 'x' },
        revisions: undefined,
      }),
    );
    expect(state.kind).toBe('unknown');
    expect(workingStateSentence(state)).toMatch(/unknown rather than no/);
  });

  it('C-4 · the submitted-revision cell distinguishes "none" from "not read"', () => {
    // The two states `revisionNo === null` could not tell apart.
    expect(submittedRevisionText({ kind: 'unknown', revisionNo: null })).toBe(
      'Not read on this deployment',
    );
    expect(submittedRevisionText({ kind: 'never_submitted', revisionNo: null })).toBe(
      'None',
    );
    // ...and the two that carry a number still read as one.
    expect(submittedRevisionText({ kind: 'unchanged', revisionNo: 4 })).toBe('Revision 4');
    expect(submittedRevisionText({ kind: 'changed', revisionNo: 9 })).toBe('Revision 9');

    // POLARITY: the four are pairwise distinct, so a helper returning one constant
    // would fail rather than satisfy the assertions above.
    const all = [
      submittedRevisionText({ kind: 'unknown', revisionNo: null }),
      submittedRevisionText({ kind: 'never_submitted', revisionNo: null }),
      submittedRevisionText({ kind: 'unchanged', revisionNo: 4 }),
      submittedRevisionText({ kind: 'changed', revisionNo: 9 }),
    ];
    expect(new Set(all).size).toBe(4);
  });

  it('C-4 · RENDERS the unknown state without the word "None" — the path that ships', async () => {
    /*
     * THE MISSING COVERAGE. `PGHOST` is unset in every shipped deployment, so the
     * server answers 503 with `no_durable_storage` and this is the branch a
     * scientist actually sees. It had no rendering test.
     */
    stubFetchRoutes({
      [`GET /api/experiments/${EXP}/revisions`]: {
        status: 503,
        body: history({
          availability: {
            state: 'unavailable',
            reason: 'no_durable_storage',
            message: 'This deployment has no durable storage, so no submission history exists.',
          },
          revisions: undefined,
          total: undefined,
          returned: undefined,
        }),
      },
    } as never);
    await renderOpen();

    const card = await screen.findByRole('region', {
      name: `${SUBMITTED_REVISION_HEADING} and ${WORKING_CHANGES_HEADING}`,
    });
    const row = within(card).getByText(SUBMITTED_REVISION_HEADING).parentElement!;
    expect(row.textContent).toContain('Not read on this deployment');
    // The defect, asserted as absent rather than merely as "the new text is there".
    expect(row.textContent).not.toContain('None');
    // And the rename caution must NOT appear: it belongs to `unchanged` only, and
    // there is nothing here for a resubmission to be refused against.
    expect(within(card).queryByText(/Renaming this record does not count/)).toBeNull();
  });
});

/* ── 9. ONE status line, the cards one click away (owner QA V1, 2026-09-22) ───
 *
 * The panel used to render four prose cards in full below the export verdict. It
 * is now one visible line — the lifecycle label and what the server said about the
 * history and this deployment — over a `Submission Details` disclosure. Each
 * clause of the line is a server field or a heading the cards below already use,
 * and the two facts DEC-35 forbids hiding (history unreadable; deployment cannot
 * submit) are on the line, never only behind the disclosure.
 */
describe('the collapsed submission history', () => {
  const statusLine = () => document.querySelector('.revhist-status') as HTMLElement;

  it('shows one status line and keeps the cards closed until asked', async () => {
    stubFetchRoutes({ [LIST]: { body: history() } });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    const trigger = await screen.findByRole('button', { name: 'Submission Details' });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(statusLine().textContent).toContain('Ready to Submit');
    expect(statusLine().textContent).toContain('No submitted revisions');
    // The cards are not exposed while closed…
    expect(
      screen.queryByRole('region', {
        name: `${SUBMITTED_REVISION_HEADING} and ${WORKING_CHANGES_HEADING}`,
      }),
    ).toBeNull();
    // …and are once opened.
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(
      screen.getByRole('region', {
        name: `${SUBMITTED_REVISION_HEADING} and ${WORKING_CHANGES_HEADING}`,
      }),
    ).toBeTruthy();
  });

  it('says the lifecycle label ONCE, not once on the line and again in the card', async () => {
    stubFetchRoutes({ [LIST]: { body: history() } });
    await renderOpen();
    expect(screen.getAllByText('Ready to Submit')).toHaveLength(1);
  });

  it('an UNREADABLE history says so on the line, and never reads as "no revisions"', async () => {
    stubFetchRoutes({
      [LIST]: {
        status: 503,
        body: history({
          availability: {
            state: 'unavailable',
            reason: 'tables_absent',
            message: TABLES_ABSENT_MESSAGE,
          },
          revisions: undefined,
          total: undefined,
          returned: undefined,
        }),
      },
    } as never);
    render(<RevisionHistoryPanel experimentId={EXP} />);
    await screen.findByRole('button', { name: 'Submission Details' });
    expect(statusLine().textContent).toContain('Submission history could not be read');
    expect(statusLine().textContent).not.toMatch(/no submitted revisions/i);
  });

  it('a readable history gives its count', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: history({
          revisions: [revision({ revision_no: 2 }), revision()],
          total: 2,
          returned: 2,
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    await screen.findByRole('button', { name: 'Submission Details' });
    expect(statusLine().textContent).toContain('2 submitted revisions');
  });

  it('a deployment that cannot submit is stated on the line, beside — not instead of — the label', async () => {
    stubFetchRoutes({
      [LIST]: {
        body: history({
          lifecycle: lifecycle({
            submission_blocked_by_deployment: {
              blocked: true,
              blockers: ['no_attributable_actor'],
              basis: 'configuration_only',
              requires_attributable_actor: true,
              actor_trust_basis: null,
              message: 'This deployment cannot currently accept a submission of any record.',
            },
          }),
        }),
      },
    });
    render(<RevisionHistoryPanel experimentId={EXP} />);
    await screen.findByRole('button', { name: 'Submission Details' });
    expect(statusLine().textContent).toContain('Ready to Submit');
    expect(statusLine().textContent).toContain('Submitting is unavailable in this deployment');
  });
});
