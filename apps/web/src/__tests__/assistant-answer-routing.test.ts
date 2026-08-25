/*
 * THE OPEN/ANSWERED DECISION BELONGS TO THE SERVER, AND USED TO BELONG TO A CACHE.
 *
 * `confirmProposal` chose `submitAnswer` (fill an OPEN question) or `editField` (correct
 * an ALREADY-ANSWERED one) by asking whether the proposal's question appeared in
 * `ctx.pending` — a list fetched before the click, by a different component, for a
 * different purpose. That made a READ's completeness into a WRITE's correctness
 * condition, and it is why the read could not be bounded: with a 50-entry context, a
 * reader who paged to question 900 of a 1,000-run record and staged it took
 * `isPending: false` and the edit route, which answered `422 unrecognized_field` —
 * *"No editable field was recognized in the request."* A legitimate first answer refused,
 * with a reason naming the wrong cause.
 *
 * The list is now a HINT. The hinted route is attempted; if it was the wrong one, the
 * server says so in a vocabulary that cannot drift from its own behaviour — `422
 * already_answered` from `/answers` on a closed question, `422 not_yet_answered` from
 * `/edit` on an open one — and each names, in `answer_at`, the operation that can take
 * the request. Both guarantee that nothing was written.
 *
 * WHAT THESE TESTS ARE FOR. A redirect is a second write, so the cheap version of this
 * feature is a retry loop with a nice name. Every property that makes it not one is
 * pinned below and none of them is left to a comment:
 *
 *   - ONE hop, and never a second — including when the server contradicts itself.
 *   - ONLY the two named refusals. A 412, a `409 belongs_to_a_run`, a 403, a 500, an
 *     `invalid_field_value` are not followed, and the request is not repeated.
 *   - The If-Match token is the TARGET's, re-derived after the redirect. A run write
 *     takes the RUN's version; sending the record's is a 412 the reader would be told to
 *     fix by refreshing something that was never stale.
 *   - The run is taken from the REFUSAL's `run_id`, never from the guess that produced
 *     it — a redirect that reuses the run we happened to try is how a value lands on the
 *     wrong run.
 *   - An ABSENT `answer_at` is obeyed rather than worked around. It means no operation
 *     on this record can resolve the condition, and the server omits the key rather than
 *     naming one it would refuse.
 */

import { describe, expect, it, vi } from 'vitest';
import { answerRoutingRefusal, confirmProposal, stageAnswer } from '../lib/assistantAgent';
import type { AgentContext, Proposal } from '../lib/assistantAgent';
import { REAL_CONTRACT_DESCRIPTIONS } from '../test/apiFixtures';

const RUN_ONE = '01RUNAAAAAAAAAAAAAAAAAAAA0';
const RUN_TWO = '01RUNBBBBBBBBBBBBBBBBBBBB0';

const ANSWERS_RECORD = 'POST /api/experiments/{experiment_id}/answers';
const ANSWERS_RUN = 'POST /api/experiments/{experiment_id}/runs/{run_id}/answers';
const EDIT_RECORD = 'POST /api/experiments/{experiment_id}/edit';
const EDIT_RUN = 'POST /api/experiments/{experiment_id}/runs/{run_id}/edit';

/** A context whose `pending` is exactly what the caller passes — the HINT under test. */
function ctxWith(pending: AgentContext['pending']): AgentContext {
  return {
    experimentId: '01EXPERIMENTA0000000000000',
    recordRev: 5,
    version: 'genabc.5',
    workflow: { current_step: null, ordered_steps: [] },
    evidence: [],
    pending,
  };
}

/** A thrown `ApiError` as `lib/api.ts::mutationError` builds one: status + parsed body. */
function refusal(status: number, body: unknown) {
  return Object.assign(new Error('refused'), { status, body });
}

const ALREADY_ANSWERED_AT_RUN = refusal(422, {
  error: 'already_answered',
  experiment_id: '01EXPERIMENTA0000000000000',
  run_id: RUN_ONE,
  keys: ['series'],
  answer_at: EDIT_RUN,
  message:
    'Each of these is already answered, and the value submitted here differs from the ' +
    'confirmed one. Nothing was written and the stored value is unchanged.',
});

const NOT_YET_ANSWERED_AT_RUN = refusal(422, {
  error: 'not_yet_answered',
  experiment_id: '01EXPERIMENTA0000000000000',
  run_id: RUN_ONE,
  keys: ['series'],
  answer_at: ANSWERS_RUN,
  message:
    'Each of these is still an open question, so there is no confirmed value to ' +
    'correct. Nothing was written.',
});

/** The one refusal the contract emits with NO `answer_at`: a run-owned key raised on a
 *  record that HAS runs, where no operation on the record can answer it. */
const NOT_YET_ANSWERED_NOWHERE = refusal(422, {
  error: 'not_yet_answered',
  experiment_id: '01EXPERIMENTA0000000000000',
  keys: ['series'],
  message:
    'Each of these is still an open question, so there is no confirmed value to ' +
    'correct. No operation on this record can answer it: the record has runs, so a ' +
    'spectrum, a QC verdict, a descriptor and an asset hash belong to the run that ' +
    'measured them. No `answer_at` is given rather than one that would refuse the ' +
    'request. Nothing was written.',
});

/** A fresh double. Each method resolves unless a test overrides it. */
function apiDouble(over: Record<string, unknown> = {}) {
  return {
    submitAnswer: vi.fn().mockResolvedValue({ ok: 'answers' }),
    editField: vi.fn().mockResolvedValue({ ok: 'edit' }),
    getRun: vi.fn().mockResolvedValue({ run: { version: 'run-one.4' } }),
    ...over,
  };
}

/** A proposal for a RUN-owned question, staged with the run recorded (stage time). */
function runProposal(ctx: AgentContext, runId = RUN_ONE): Proposal {
  return stageAnswer(ctx, {
    field: 'series',
    blockerKey: `${runId}:series`,
    runId,
    value: [{ series_id: 's' }],
  });
}

describe('answerRoutingRefusal — what this client will act on', () => {
  it('recognises both codes and carries the body VERBATIM', () => {
    const a = answerRoutingRefusal(ALREADY_ANSWERED_AT_RUN)!;
    expect(a.error).toBe('already_answered');
    expect(a.answerAt).toBe(EDIT_RUN);
    expect(a.runId).toBe(RUN_ONE);
    expect(a.message).toContain('Nothing was written');

    const b = answerRoutingRefusal(NOT_YET_ANSWERED_AT_RUN)!;
    expect(b.error).toBe('not_yet_answered');
    expect(b.answerAt).toBe(ANSWERS_RUN);
  });

  it('an ABSENT answer_at is reported absent, never filled in', () => {
    const r = answerRoutingRefusal(NOT_YET_ANSWERED_NOWHERE)!;
    expect(r.answerAt).toBeNull();
    expect(r.runId).toBeNull();
  });

  it('reads the CODE, not the status — every other 422 on these routes is not this', () => {
    /* `422` from `/answers` and `/edit` has at least six other causes:
       `confirmation_required`, `no_derivation_to_confirm`, `unrecognized_field`,
       `invalid_field_value`, the framework's own body validation, and whatever a future
       validation adds. None of them says where the request should have gone, so widening
       this to "any 422" would turn an unrelated refusal into a blind second write. */
    for (const other of [
      refusal(422, { error: 'invalid_field_value', message: 'no' }),
      refusal(422, { error: 'unrecognized_field', message: 'no' }),
      refusal(422, { error: 'confirmation_required', message: 'no' }),
      refusal(422, { detail: [{ loc: ['body'], msg: 'not an object' }] }),
      refusal(409, { error: 'belongs_to_a_run', answer_at: ANSWERS_RUN, message: 'no' }),
      refusal(412, { current_version: 'genabc.6' }),
      refusal(500, { error: 'already_answered', answer_at: EDIT_RUN, message: 'no' }),
      new Error('network'),
      undefined,
      null,
      'already_answered',
    ]) {
      expect(answerRoutingRefusal(other)).toBeNull();
    }
  });
});

describe('the four templates this client will follow are the four the API publishes', () => {
  it('every allowlisted answer_at is a real published operation', () => {
    /* THE ALLOWLIST IS HAND-TRANSCRIBED FROM `routes.py`, so it needs something holding
       it to the server. `REAL_CONTRACT_DESCRIPTIONS` is transcribed from
       `create_app().openapi()` and a BACKEND test compares it byte-for-byte, so an
       operation renamed there cannot stay spelled this way here without that fixture
       being re-transcribed — at which point this goes red.

       WHAT IT DOES NOT PROVE, said plainly. It pins the OPERATION IDENTIFIER, not the
       `answer_at` VALUE: `routes.py` builds `_ANSWERS_OPERATION_RECORD` and its three
       siblings as their own constants, and they coincide with the route paths rather
       than being derived from them. All four were observed identical over HTTP against
       the running app when this was written — `already_answered` and `not_yet_answered`
       at both levels — but a future divergence in those four constants alone would slip
       past this. A backend test asserting the constants ARE the paths is the guard that
       would close it, and this file cannot add one. */
    const published = new Set(REAL_CONTRACT_DESCRIPTIONS.map((o) => o.op));
    for (const template of [ANSWERS_RUN, EDIT_RECORD, EDIT_RUN, ANSWERS_RECORD]) {
      expect(published, `${template} is not a published operation`).toContain(template);
    }
  });
});

describe('a wrong routing HINT is corrected by the server, not by the client', () => {
  it('THE HEADLINE: a question OUTSIDE the bounded window still lands as a first ANSWER', async () => {
    /* The whole reason the AgentContext read could not be bounded. The window holds the
       record's first questions; the staged one is question 900, so the hint says "not
       open" and the edit route is tried. The server refuses without writing, names the
       run's `/answers`, and the answer lands there — where it always should have. */
    const ctx = ctxWith([
      { id: 'series', label: 'series', run_id: RUN_TWO, blocker_key: `${RUN_TWO}:series` },
    ]);
    const p = runProposal(ctx, RUN_ONE); // owned by a run the window does not carry
    const api = apiDouble({ editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_AT_RUN) });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('ok');
    expect(api.editField).toHaveBeenCalledTimes(1); // the hint, once
    expect(api.submitAnswer).toHaveBeenCalledTimes(1); // the correction, once
    expect(api.submitAnswer).toHaveBeenCalledWith(
      ctx.experimentId,
      { series: [{ series_id: 's' }] },
      'run-one.4', // THE RUN's token, for the run's operation
      RUN_ONE,
    );
  });

  it('the mirror: a stale hint that says OPEN is corrected onto /edit', async () => {
    const ctx = ctxWith([
      { id: 'series', label: 'series', run_id: RUN_ONE, blocker_key: `${RUN_ONE}:series` },
    ]);
    const p = runProposal(ctx, RUN_ONE);
    const api = apiDouble({
      submitAnswer: vi.fn().mockRejectedValue(ALREADY_ANSWERED_AT_RUN),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('ok');
    expect(api.submitAnswer).toHaveBeenCalledTimes(1);
    expect(api.editField).toHaveBeenCalledTimes(1);
    expect(api.editField).toHaveBeenCalledWith(
      ctx.experimentId,
      { series: [{ series_id: 's' }] },
      'run-one.4',
      RUN_ONE,
    );
  });

  it('a RECORD-level pair redirects with the RECORD token and no run', async () => {
    const ctx = ctxWith([{ id: 'series', label: 'series' }]); // no runs anywhere
    const p = stageAnswer(ctx, { field: 'series', value: 'x' });
    const api = apiDouble({
      submitAnswer: vi.fn().mockRejectedValue(
        refusal(422, {
          error: 'already_answered',
          experiment_id: ctx.experimentId,
          keys: ['series'],
          answer_at: EDIT_RECORD,
          message: 'Already answered. Nothing was written.',
        }),
      ),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('ok');
    expect(api.getRun).not.toHaveBeenCalled(); // no run is involved at either end
    expect(api.editField).toHaveBeenCalledWith(
      ctx.experimentId,
      { series: 'x' },
      'genabc.5', // the RECORD's version
      undefined, // …and no run id
    );
  });
});

describe('the CAS token follows the REDIRECT, not the guess', () => {
  it('a record-level guess redirected to a RUN re-fetches the RUN token', async () => {
    /* THE CASE THE TOKEN RULE EXISTS FOR. The first attempt is record-routed, so it
       carries `ctx.version`. The server sends it to a run, and a run write takes the
       RUN's version — reusing what the first attempt held would be a 412 the reader
       would be told to fix by refreshing something that was never stale. */
    const ctx = ctxWith([]);
    const p = stageAnswer(ctx, { field: 'series', value: 'x' }); // no runId recorded
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_AT_RUN),
      getRun: vi.fn().mockResolvedValue({ run: { version: 'run-one.11' } }),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('ok');
    // The FIRST attempt was record-routed and carried the record's token…
    expect(api.editField).toHaveBeenCalledWith(ctx.experimentId, { series: 'x' }, 'genabc.5', undefined);
    // …and the SECOND asked for the run's, for the run the REFUSAL named.
    expect(api.getRun).toHaveBeenCalledTimes(1);
    expect(api.getRun).toHaveBeenCalledWith(ctx.experimentId, RUN_ONE);
    expect(api.submitAnswer).toHaveBeenCalledWith(ctx.experimentId, { series: 'x' }, 'run-one.11', RUN_ONE);
  });

  it('the run comes from the REFUSAL, never from the run that was tried', async () => {
    /* A value landing on the wrong run is the defect `Proposal.blockerKey` was added
       for — measured once as run 2's spectrum written onto RUN 1 with run 1's If-Match
       and reported as confirmed. A redirect that reused the attempted run would be a
       second way in. */
    const ctx = ctxWith([]);
    const p = runProposal(ctx, RUN_TWO); // tried against run TWO
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_AT_RUN), // …refused, naming run ONE
      getRun: vi
        .fn()
        .mockResolvedValueOnce({ run: { version: 'run-two.2' } })
        .mockResolvedValueOnce({ run: { version: 'run-one.9' } }),
    });

    await confirmProposal(p, ctx, api as never);

    expect(api.getRun).toHaveBeenNthCalledWith(1, ctx.experimentId, RUN_TWO);
    expect(api.getRun).toHaveBeenNthCalledWith(2, ctx.experimentId, RUN_ONE);
    expect(api.submitAnswer).toHaveBeenCalledWith(
      ctx.experimentId,
      { series: [{ series_id: 's' }] },
      'run-one.9',
      RUN_ONE,
    );
  });
});

describe('it follows ONE redirect, and there is no loop to bound', () => {
  it('a server that refuses the redirect the SAME way stops at two writes', async () => {
    /* Impossible under the published contract — each refusal names the OTHER member of
       its pair — so this is the self-contradicting server. The second attempt's failure
       is never inspected for an `answer_at`, so there is no edge back into the redirect
       and nothing to iterate. */
    const ctx = ctxWith([]);
    const p = runProposal(ctx);
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_AT_RUN),
      submitAnswer: vi.fn().mockRejectedValue(ALREADY_ANSWERED_AT_RUN),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('refused');
    expect(res.error).toBe('already_answered');
    expect(res.message).toContain('Nothing was written');
    expect(api.editField).toHaveBeenCalledTimes(1);
    expect(api.submitAnswer).toHaveBeenCalledTimes(1);
  });

  it('an answer_at naming the operation just attempted is not followed', async () => {
    // Same structural guard from the other side: a redirect to where we already were
    // would repeat a call that just failed, which is the one shape of "follow it once"
    // that could look like a loop.
    const ctx = ctxWith([]);
    const p = runProposal(ctx);
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(
        refusal(422, {
          error: 'not_yet_answered',
          experiment_id: ctx.experimentId,
          run_id: RUN_ONE,
          keys: ['series'],
          answer_at: EDIT_RUN, // …which is exactly what was just called
          message: 'Still open. Nothing was written.',
        }),
      ),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('refused');
    expect(api.editField).toHaveBeenCalledTimes(1);
    expect(api.submitAnswer).not.toHaveBeenCalled();
  });

  it('an answer_at this client does not know is not interpolated, parsed, or guessed at', async () => {
    const ctx = ctxWith([]);
    const p = runProposal(ctx);
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(
        refusal(422, {
          error: 'not_yet_answered',
          experiment_id: ctx.experimentId,
          run_id: RUN_ONE,
          keys: ['series'],
          answer_at: 'PUT /api/experiments/{experiment_id}/runs/{run_id}/answers',
          message: 'Still open. Nothing was written.',
        }),
      ),
    });

    const res = await confirmProposal(p, ctx, api as never);
    expect(res.status).toBe('refused');
    expect(api.submitAnswer).not.toHaveBeenCalled();
  });

  it('a run-level answer_at with no run_id in the body is not followed', async () => {
    // The ids travel beside the template in the refusal's own body, by contract. Without
    // one there is nothing to substitute, and the run that was tried is not a substitute.
    const ctx = ctxWith([]);
    const p = runProposal(ctx);
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(
        refusal(422, {
          error: 'not_yet_answered',
          experiment_id: ctx.experimentId,
          keys: ['series'],
          answer_at: ANSWERS_RUN, // names a run operation…
          message: 'Still open. Nothing was written.', // …but names no run
        }),
      ),
    });

    const res = await confirmProposal(p, ctx, api as never);
    expect(res.status).toBe('refused');
    expect(api.submitAnswer).not.toHaveBeenCalled();
  });
});

describe('an ABSENT answer_at is obeyed, and the server gets the last word', () => {
  it('no route is guessed, and the refusal\'s own sentence is returned', async () => {
    /* The record has runs, so a spectrum belongs to the run that measured it and NO
       operation on the record can answer the question. The server omits `answer_at`
       rather than naming one it would refuse — inventing a route from the other three
       templates would walk straight into the second refusal it was avoiding. */
    const ctx = ctxWith([]);
    const p = stageAnswer(ctx, { field: 'series', value: 'x' });
    const api = apiDouble({ editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_NOWHERE) });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('refused');
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).toHaveBeenCalledTimes(1);
    // VERBATIM. A restatement here would be a second description of a refusal this
    // client did not observe, free to drift from the behaviour producing it.
    expect(res.message).toBe(
      (NOT_YET_ANSWERED_NOWHERE as unknown as { body: { message: string } }).body.message,
    );
  });

  it('a refusal carrying no sentence is rethrown rather than narrated', async () => {
    // Unreachable under the contract, and the fail-closed direction if it ever is not:
    // the caller's own handling claims LESS than a sentence this client composed.
    const ctx = ctxWith([]);
    const p = stageAnswer(ctx, { field: 'series', value: 'x' });
    const err = refusal(422, { error: 'not_yet_answered', keys: ['series'] });
    const api = apiDouble({ editField: vi.fn().mockRejectedValue(err) });

    await expect(confirmProposal(p, ctx, api as never)).rejects.toBe(err);
    expect(api.submitAnswer).not.toHaveBeenCalled();
  });
});

describe('NOTHING ELSE IS FOLLOWED, and nothing else is repeated', () => {
  const cases: [string, unknown][] = [
    ['412 stale write', refusal(412, { current_version: 'genabc.6' })],
    ['409 belongs_to_a_run', refusal(409, { error: 'belongs_to_a_run', answer_at: ANSWERS_RUN })],
    ['403', refusal(403, { error: 'forbidden' })],
    ['500', refusal(500, {})],
    ['422 invalid_field_value', refusal(422, { error: 'invalid_field_value', message: 'no' })],
    ['422 unrecognized_field', refusal(422, { error: 'unrecognized_field', message: 'no' })],
    ['a transport failure', Object.assign(new Error('offline'), { unreachable: true })],
  ];

  for (const [name, err] of cases) {
    it(`${name}: exactly one write, and no redirect`, async () => {
      const ctx = ctxWith([
        { id: 'series', label: 'series', run_id: RUN_ONE, blocker_key: `${RUN_ONE}:series` },
      ]);
      const p = runProposal(ctx);
      const api = apiDouble({ submitAnswer: vi.fn().mockRejectedValue(err) });

      // A 412 is the pre-existing conflict outcome; everything else propagates to the
      // caller, whose own copy claims less than this function could honestly claim.
      if ((err as { status?: number }).status === 412) {
        const res = await confirmProposal(p, ctx, api as never);
        expect(res.status).toBe('conflict');
        expect(res.proposal?.confirmationState).toBe('stale');
      } else {
        await expect(confirmProposal(p, ctx, api as never)).rejects.toBe(err);
      }
      expect(api.submitAnswer).toHaveBeenCalledTimes(1);
      expect(api.editField).not.toHaveBeenCalled();
    });
  }

  it('a 412 on the REDIRECT is a conflict too — still no retry, still no merge', async () => {
    const ctx = ctxWith([]);
    const p = runProposal(ctx);
    const api = apiDouble({
      editField: vi.fn().mockRejectedValue(NOT_YET_ANSWERED_AT_RUN),
      submitAnswer: vi.fn().mockRejectedValue(refusal(412, { current_version: 'genabc.6' })),
    });

    const res = await confirmProposal(p, ctx, api as never);

    expect(res.status).toBe('conflict');
    expect(res.proposal?.confirmationState).toBe('stale');
    expect(api.submitAnswer).toHaveBeenCalledTimes(1);
    expect(api.editField).toHaveBeenCalledTimes(1);
  });

  it('the staleness guards still refuse BEFORE any api touch, redirect or not', async () => {
    const ctx = ctxWith([]);
    const api = apiDouble();
    const advanced = { ...ctx, recordRev: 6, version: 'genabc.6' };
    expect((await confirmProposal(runProposal(ctx), advanced, api as never)).status).toBe('stale');
    expect(
      (await confirmProposal(runProposal(ctx), { ...ctx, degraded: true }, api as never)).status,
    ).toBe('stale');
    expect(api.submitAnswer).not.toHaveBeenCalled();
    expect(api.editField).not.toHaveBeenCalled();
    expect(api.getRun).not.toHaveBeenCalled();
  });
});
