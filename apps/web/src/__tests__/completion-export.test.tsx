import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { MEMORY_UNAVAILABLE_CAVEAT, ROUTE_TO_CLI_NOTE } from '../lib/assistant';
import {
  answersAfterNotebook,
  answersStaleWrite,
  auditExported,
  auditNotExported,
  bundleRoutes,
  exportConflict,
  exportReadyRoutes,
  exportStaleWrite,
  exportSuccess,
  exportedReadyRoutes,
  pendingResponse,
  seriesDemoValue,
  stubFetchDown,
  stubFetchRoutes,
  validateDryRun,
} from '../test/apiFixtures';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const NOTEBOOK_URI = pendingResponse.pending[0].id; // asset blockers key on their uri
const SHA = 'c3b0c442…'; // the fixture's synthetic demo sha value

/** All POST bodies sent to the answers endpoint (parsed). */
function answerPosts(): { url: string; body: unknown }[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([url, init]) => init?.method === 'POST' && String(url).includes('/answers'))
    .map(([url, init]) => ({ url: String(url), body: JSON.parse(String(init?.body)) }));
}

/** The If-Match header sent on each POST /answers, in order (P27.5). */
function answerIfMatchHeaders(): (string | undefined)[] {
  const calls = (globalThis.fetch as Mock).mock.calls as [string, RequestInit?][];
  return calls
    .filter(([url, init]) => init?.method === 'POST' && String(url).includes('/answers'))
    .map(([, init]) => (init?.headers as Record<string, string> | undefined)?.['If-Match']);
}

describe('S4 · Guided Completion (live)', () => {
  it('confirming an answer POSTs confirmed_by_user:true and shrinks pending from the response', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
    });
    const { findByText, getByText, getByLabelText, queryByText } = renderAt(
      '/record/demo/complete',
    );

    // question 1 of 5, live from /pending, verbatim
    expect(await findByText('Answer 5 Questions to Finish This Record')).toBeInTheDocument();
    expect(getByText('What is the sha256 of the processing notebook?')).toBeInTheDocument();
    expect(getByText('0 / 5')).toBeInTheDocument();

    // type the value and confirm
    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: SHA } });
    fireEvent.click(getByText('Confirm'));

    // pending shrank (4 remain, question 2 is current) + answered row with the chip
    expect(await findByText('1 / 5')).toBeInTheDocument();
    expect(getByText('What is the sha256 of the raw scan file?')).toBeInTheDocument();
    expect(getByText(`stored ${SHA}`)).toBeInTheDocument();
    expect(getByText('Confirmed by You')).toBeInTheDocument();
    expect(queryByText('What is the sha256 of the processing notebook?')).toBeNull();

    // the wire shape: keyed by the blocker id (asset uri) + explicit confirmation
    const posts = answerPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      answers: { [NOTEBOOK_URI]: SHA },
      confirmed_by_user: true,
    });
  });

  it('"I don\'t know / leave missing" advances WITHOUT sending anything and is not penalized', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { findByText, getByText, container } = renderAt('/record/demo/complete');

    await findByText('What is the sha256 of the processing notebook?');
    fireEvent.click(getByText("I don't know — leave honestly missing"));

    // advanced to the next question; the skipped one is listed, honestly missing
    expect(await findByText('What is the sha256 of the raw scan file?')).toBeInTheDocument();
    expect(getByText('Left Honestly Missing')).toBeInTheDocument();
    // NOTHING was sent — no POST to /answers at all
    expect(answerPosts()).toHaveLength(0);
    // non-penalized: no alert/error styling anywhere for the skipped question
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(getByText('5 of 5 fields still to confirm')).toBeInTheDocument();

    // the skipped question can be answered later
    fireEvent.click(getByText('Answer now'));
    expect(getByText('What is the sha256 of the processing notebook?')).toBeInTheDocument();
  });

  it('the demo answer is a labeled suggestion — never prefilled, never auto-submitted', async () => {
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { body: answersAfterNotebook },
    });
    const { findByText, getByText, getByLabelText } = renderAt('/record/demo/complete');

    // labeled as synthetic and explicitly not a value yet
    expect(await findByText('Demo answer (synthetic)')).toBeInTheDocument();
    expect(getByText('— not a value until you confirm')).toBeInTheDocument();

    // never prefilled as truth: the input starts empty, and nothing was submitted
    const input = getByLabelText('Asset Hash') as HTMLInputElement;
    expect(input.value).toBe('');
    expect(answerPosts()).toHaveLength(0);

    // taking the suggestion fills the input but STILL submits nothing
    fireEvent.click(getByText('Use This Suggestion'));
    expect(input.value).toBe(SHA);
    expect(answerPosts()).toHaveLength(0);

    // only the explicit Confirm sends it
    fireEvent.click(getByText('Confirm'));
    await findByText('1 / 5');
    expect(answerPosts()).toHaveLength(1);
  });

  it('a structured blocker (series) can only be confirmed from the labeled demo value', async () => {
    const seriesPending = {
      pending: [
        {
          id: 'series',
          kind: 'series',
          question: 'Which reduced spectrum should this record point to?',
          about: 'reduced_spectrum',
          demo_answer: { value: seriesDemoValue, label: 'Demo answer (synthetic)' },
        },
      ],
    };
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo/pending': { body: seriesPending },
      'POST /api/experiments/demo/answers': {
        body: { pending: [], status: 'ready_to_export' },
      },
    });
    const { findByText, getByText } = renderAt('/record/demo/complete');

    await findByText('Which reduced spectrum should this record point to?');
    // no free-text path for a structured scientific value; confirm is gated on
    // explicitly taking the labeled demo value first
    const confirm = getByText('Confirm').closest('button')!;
    expect(confirm).toBeDisabled();
    expect(answerPosts()).toHaveLength(0);

    fireEvent.click(getByText('Use This Value'));
    expect(confirm).not.toBeDisabled();
    expect(answerPosts()).toHaveLength(0); // staged, still not submitted

    fireEvent.click(confirm);
    // 0 remaining -> the finished state routes forward to S6
    expect(await findByText('This record is ready to export.')).toBeInTheDocument();
    expect(getByText('Go to Ready to Export →')).toBeInTheDocument();
    // non-zero total (1 question, now answered): the real counter still renders
    expect(getByText('1 / 1')).toBeInTheDocument();
    const posts = answerPosts();
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({
      answers: { series: seriesDemoValue },
      confirmed_by_user: true,
    });
  });

  it('zero blockers on arrival shows honest empty-state copy, never the meaningless "0 / 0"', async () => {
    stubFetchRoutes(exportReadyRoutes('demo')); // pending: [] from the very first load
    const { findByText, getByText, queryByText } = renderAt('/record/demo/complete');

    expect(await findByText('All Fields Resolved')).toBeInTheDocument();
    expect(getByText('No open questions.')).toBeInTheDocument();
    expect(queryByText('0 / 0')).toBeNull();
    expect(getByText('This record is ready to export.')).toBeInTheDocument();
    // the sidebar spine's "Complete" step must not repeat the same dishonest
    // zero-count in its meta line either
    expect(queryByText('0 of 0 answered')).toBeNull();
  });
});

describe('S6 · Ready to Export (live)', () => {
  it('export is locked while pending > 0 — no export button, no reserved verdict chip', async () => {
    stubFetchRoutes(bundleRoutes('demo')); // 5 pending, dry-run fails
    const { container, findByText, queryByText } = renderAt('/record/demo/export');

    expect(await findByText('5 fields still block export')).toBeInTheDocument();
    expect(queryByText('Export Official Record + Sidecar')).toBeNull();
    // the dry-run must NOT render the reserved verdict treatment
    expect(container.querySelector('.verdict')).toBeNull();
    expect(container.querySelector('.chip-pass')).toBeNull();
    expect(container.querySelector('.chip-fail')).toBeNull();
    // advisory still renders in its own non-gating component
    expect(container.querySelector('.advisory')).not.toBeNull();
    expect(container.querySelector('.advisory')!.textContent).toMatch(/non-gating/);
  });

  it('export stays gated when pending == 0 but the dry-run would not validate', async () => {
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/validate': { body: validateDryRun }, // ok:false
    });
    const { findByText, getByText, queryByText } = renderAt('/record/demo/export');

    expect(await findByText('Would Not Validate Yet')).toBeInTheDocument();
    expect(getByText(/assets is a required property/)).toBeInTheDocument();
    expect(queryByText('Export Official Record + Sidecar')).toBeNull();
    expect(getByText('Back to Complete →')).toBeInTheDocument();
  });

  it('ready → export writes both artifacts as SEPARATE cards; three distinct signal components', async () => {
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/audit': { body: auditExported },
      'POST /api/experiments/demo/export': { body: exportSuccess },
    });
    const { container, findByText, getByText } = renderAt('/record/demo/export');

    // pre-export: enabled gate, still no reserved verdict
    const exportBtn = (await findByText('Export Official Record + Sidecar')).closest('button')!;
    expect(exportBtn).not.toBeDisabled();
    expect(container.querySelector('.verdict')).toBeNull();

    fireEvent.click(exportBtn);

    // the real verdict appears only now, from the export's official report
    expect(await findByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();
    expect(getByText('PASS', { selector: '.verdict-word' })).toBeInTheDocument();

    // two separate artifact cards — record and sidecar never blended
    const cards = container.querySelectorAll('.artifact');
    expect(cards).toHaveLength(2);
    expect(getByText('Official Record')).toBeInTheDocument();
    expect(getByText('Evidence Trail')).toBeInTheDocument();
    expect(getByText('assistant convention — not official')).toBeInTheDocument();
    expect(getByText(/Review the sidecar before sharing/)).toBeInTheDocument();

    // three signals, three distinct root components, never merged
    await waitFor(() => expect(container.querySelector('.coverage')).not.toBeNull());
    expect(container.querySelector('.verdict')).not.toBeNull();
    expect(container.querySelector('.advisory')).not.toBeNull();
    const roots = [
      container.querySelector('.verdict')!.className,
      container.querySelector('.coverage')!.className,
      container.querySelector('.advisory')!.className,
    ];
    expect(new Set(roots).size).toBe(3);

    // local artifacts only — never CLAIMS a portal submission/acceptance
    // (denials like "no portal submission from here" / "not portal sign-off"
    // are allowed and expected)
    expect(container.textContent).not.toMatch(
      /(submit(ted)?|send|sent) to .{0,12}portal|portal[- ](validated|accepted|certified)/i,
    );
  });

  it('a fresh load of an exported record can View + Download via the artifacts endpoint', async () => {
    stubFetchRoutes(exportedReadyRoutes('demo'));
    const { container, findByText, getByText } = renderAt('/record/demo/export');

    // the real post-export verdict shows (no re-export needed)
    expect(await findByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();
    expect(container.querySelectorAll('.artifact')).toHaveLength(2);

    // View/Download are live from the fetched content, not disabled with a "session" hint
    const viewJson = getByText('View JSON').closest('button')!;
    expect(viewJson).not.toBeDisabled();
    expect(getByText(/Loaded from the immutable record \+ sidecar on disk/)).toBeInTheDocument();

    // View opens the real fetched record JSON
    fireEvent.click(viewJson);
    await waitFor(() => expect(container.querySelector('.artifact-modal')).not.toBeNull());
    expect(container.querySelector('.artifact-modal-body')!.textContent).toContain('asset_id');
  });

  it('exported + validation pass but audit not yet available: no fabricated coverage number renders', async () => {
    stubFetchRoutes({
      ...exportedReadyRoutes('demo'),
      'POST /api/experiments/demo/audit': { body: auditNotExported },
    });
    const { container, findByText, getByText } = renderAt('/record/demo/export');

    // the real verdict still renders (post-export, from the fetched validation)
    expect(await findByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();
    // the honest "coverage loading" state shows instead of a guessed number
    expect(getByText('Coverage loading…')).toBeInTheDocument();
    // the sidecar artifact card renders with NO invented path-count badge (it
    // used to fall back to a hardcoded 26 while audit data was unavailable)
    const sidecarCard = getByText('Evidence Trail').closest('.artifact')!;
    expect(sidecarCard.querySelector('.artifact-pathcount')).toBeNull();
    expect(container.querySelectorAll('.artifact-pathcount')).toHaveLength(0);
  });

  it('a 409 (already exported) shows a clear immutability message, never an overwrite', async () => {
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/export': { status: 409, body: exportConflict },
    });
    const { container, findByText } = renderAt('/record/demo/export');

    fireEvent.click(await findByText('Export Official Record + Sidecar'));

    expect(
      await findByText(/Official records are immutable — they are written once and never overwritten/),
    ).toBeInTheDocument();
    // nothing was written in this session: no in-session artifact cards
    expect(container.querySelectorAll('.artifact')).toHaveLength(0);
  });
});

describe('P27.5 · optimistic-concurrency conflict UX', () => {
  const NOTEBOOK_Q = 'What is the sha256 of the processing notebook?';

  it('answers: a successful confirm adopts the new version; the NEXT submit sends the updated If-Match', async () => {
    let post = 0;
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': {
        body: () => {
          post += 1;
          // 1st confirm → version 1.1; 2nd confirm → version 1.2.
          return post === 1
            ? answersAfterNotebook // version: '1.1'
            : {
                pending: pendingResponse.pending.slice(2),
                status: 'needs_attention',
                rev: 5,
                updated_utc: '2099-04-02T09:17:00Z',
                version: '1.2',
              };
        },
      },
    });
    const { findByText, getByText, getByLabelText } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    // confirm #1 (detail.version is "1.0" from the loaded fixture)
    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: 'aaaa' } });
    fireEvent.click(getByText('Confirm'));
    await findByText('1 / 5');

    // confirm #2 — question 2 (raw scan) is now current
    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: 'bbbb' } });
    fireEvent.click(getByText('Confirm'));
    await findByText('2 / 5');

    // first submit echoes the loaded token, second echoes the adopted one
    expect(answerIfMatchHeaders()).toEqual(['"1.0"', '"1.1"']);
  });

  it('answers: a 412 shows the conflict banner, preserves the typed input, and Refresh reloads', async () => {
    const calls = stubFetchRoutes({
      ...bundleRoutes('demo'),
      'POST /api/experiments/demo/answers': { status: 412, body: answersStaleWrite },
    });
    const { findByText, getByText, getByLabelText, queryByText } = renderAt('/record/demo/complete');
    await findByText(NOTEBOOK_Q);

    fireEvent.change(getByLabelText('Asset Hash'), { target: { value: 'staged-value' } });
    fireEvent.click(getByText('Confirm'));

    // the honest conflict banner — nothing applied, input kept
    expect(
      await findByText(/This record changed elsewhere\. Nothing was applied — your input is kept\./),
    ).toBeInTheDocument();
    // the typed input is preserved (GuidedPrompt was not unmounted)
    expect((getByLabelText('Asset Hash') as HTMLInputElement).value).toBe('staged-value');
    // NOT advanced: still 0/5, no answered "stored" row, question 1 still current
    expect(getByText('0 / 5')).toBeInTheDocument();
    expect(queryByText(/^stored /)).toBeNull();

    // Refresh re-fetches current state via the parent useFetch reload
    const before = calls.filter((c) => c === 'GET /api/experiments/demo').length;
    fireEvent.click(getByText('Refresh'));
    await findByText(NOTEBOOK_Q); // reloaded to a fresh LoadedCompletion
    const after = calls.filter((c) => c === 'GET /api/experiments/demo').length;
    expect(after).toBeGreaterThan(before);
  });

  it('export: a 412 shows the stale banner + Refresh and does NOT mark the record exported', async () => {
    const calls = stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/export': { status: 412, body: exportStaleWrite },
    });
    const { container, findByText, getByText } = renderAt('/record/demo/export');

    fireEvent.click(await findByText('Export Official Record + Sidecar'));

    // distinct stale copy (not the 409 immutability message) + a Refresh control
    expect(
      await findByText(/This record changed elsewhere\. Nothing was exported/),
    ).toBeInTheDocument();
    expect(getByText('Refresh')).toBeInTheDocument();
    // not exported: no artifact cards, and the export gate is still offered
    expect(container.querySelectorAll('.artifact')).toHaveLength(0);
    expect(getByText('Export Official Record + Sidecar')).toBeInTheDocument();

    // Refresh reloads current state (a fresh readiness fetch)
    const before = calls.filter((c) => c === 'GET /api/experiments/demo').length;
    fireEvent.click(getByText('Refresh'));
    await waitFor(() => {
      const after = calls.filter((c) => c === 'GET /api/experiments/demo').length;
      expect(after).toBeGreaterThan(before);
    });
  });
});

describe('S6 · Ready to Export — grounded assistant (P25.4)', () => {
  const VERDICT = /\b(PASS|FAIL)\b/;
  const INVALID_AGAINST = /\b(in)?valid against\b/i;

  it('pre-export: assistant is grounded live — empty-coverage fallback, blocking routing, ROUTE_TO_CLI_NOTE', async () => {
    stubFetchRoutes(exportReadyRoutes('demo')); // audit records:[], dry-run would pass, 1 advisory
    const { container, findByText } = renderAt('/record/demo/export');

    // reply defaults to the coverage chip (lead), grounded in the LIVE audit
    // bundle: pre-export there are no coverage figures yet.
    await findByText('No coverage figures yet — coverage appears after export.');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);
    expect(panel.getByText('answered from: Evidence Audit')).toBeInTheDocument();

    // the three approved export chips are the guided prompts
    expect(panel.getByText('Is coverage the same as valid?')).toBeInTheDocument();
    expect(panel.getByText("What's left before export?")).toBeInTheDocument();
    expect(panel.getByText('Explain the advisory warning')).toBeInTheDocument();

    // ROUTE_TO_CLI_NOTE is preserved on the panel
    expect(panel.getByText(ROUTE_TO_CLI_NOTE)).toBeInTheDocument();

    // clicking the blocker chip routes to the deterministic check — it never
    // states a verdict and never echoes validate.ok
    fireEvent.click(panel.getByText("What's left before export?").closest('button')!);
    expect(
      panel.getByText(
        'No blocking paths are listed in the current validation response. ' +
          'Open Validate to run the deterministic schema check.',
      ),
    ).toBeInTheDocument();
    expect(panel.getByText('answered from: Schema Rules')).toBeInTheDocument();

    // no verdict language anywhere in the assistant panel (the approved chip
    // label "…same as valid?" is a question, not a verdict, so the guard is the
    // reserved PASS/FAIL + "(in)valid against" language only)
    expect(assistant.textContent).not.toMatch(VERDICT);
    expect(assistant.textContent).not.toMatch(INVALID_AGAINST);
  });

  it('pre-export: the advisory chip echoes the LIVE warning, flagged advisory / non-gating', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/export');
    await findByText('No coverage figures yet — coverage appears after export.');
    const panel = within(container.querySelector('.assistant') as HTMLElement);

    fireEvent.click(panel.getByText('Explain the advisory warning').closest('button')!);
    expect(
      panel.getByText(
        'NO_LINKS — no relationships declared (advisory, non-gating; where: record.links).',
      ),
    ).toBeInTheDocument();
    expect(panel.getByText('answered from: Advisory Checks')).toBeInTheDocument();
  });

  it('post-export: coverage chip echoes evidence_present/expected live (33/33), never a verdict', async () => {
    stubFetchRoutes(exportedReadyRoutes('demo')); // audit 33/33, real (post-export) validation
    const { container, findByText } = renderAt('/record/demo/export');

    // wait for the loaded (post-export) screen
    await findByText('Valid against official ISAAC schema v1.05.');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    // the assistant reply is the LIVE coverage figure — a count, not a verdict
    expect(
      panel.getByText(
        'Coverage is 33/33 evidenced fields. It describes how many expected fields carry ' +
          'evidence; the schema check is separate.',
      ),
    ).toBeInTheDocument();
    expect(panel.getByText('answered from: Evidence Audit')).toBeInTheDocument();

    // even though the SCREEN shows a real PASS verdict card, the assistant panel
    // itself never states PASS/FAIL or an "(in)valid against" conclusion
    expect(assistant.textContent).not.toMatch(VERDICT);
    expect(assistant.textContent).not.toMatch(INVALID_AGAINST);
  });
});

describe('S4 · Complete Missing Fields — grounded assistant (P25.6)', () => {
  const VERDICT = /\b(PASS|FAIL)\b/;
  const INVALID_AGAINST = /\b(in)?valid against\b/i;
  const P = pendingResponse.pending; // 5 pending; the notebook is item 0 (current)

  // Grounded live from {detail, pending} — no validate/audit/graph fetch (Q-D).
  const PENDING_SUMMARY =
    `5 fields need you: ${P[0].about}, ${P[1].about}, ${P[2].about}, …and 2 more. ` +
    'Confirm or skip each below.';
  const EXPLAIN_CURRENT =
    `${P[0].question} — about ${P[0].about}. Answer via propose → stage → confirm below.`;
  const MISSING_BEHAVIOR =
    'Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks export ' +
    'is a schema question — open Validate to run the deterministic schema check.';

  it('mounts the three approved complete chips; the default reply is the LIVE pending summary', async () => {
    stubFetchRoutes(bundleRoutes('demo')); // 5 pending, live from /pending
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    const panel = within(assistant);

    // exactly the three approved chip labels render as prompt buttons
    expect(panel.getByText('Which fields still need me?')).toBeInTheDocument();
    expect(panel.getByText('What does this question want?')).toBeInTheDocument();
    expect(panel.getByText('What if I leave one missing?')).toBeInTheDocument();
    expect(assistant.querySelectorAll('.assistant-prompt').length).toBe(3);

    // reply defaults to the pending-summary chip, grounded in the LIVE pending list
    expect(panel.getByText(PENDING_SUMMARY)).toBeInTheDocument();
    expect(panel.getByText('answered from: Workflow & Artifacts')).toBeInTheDocument();

    // honesty (P25.7): this memory-less screen never fetches graph status, so it
    // passes NO `availability` and the panel makes NO memory claim — neither the
    // `memory:` head line nor any caveat. The spec §6-flagged-FALSE wording
    // ("…answered from source files directly") stays absent, as does the memory
    // caveat entirely. (Previously the screen passed availability="available" to
    // dodge the false caveat; omitting it is the honest fix.)
    expect(assistant.textContent).not.toContain('answered from source files directly');
    expect(assistant.textContent).not.toContain(MEMORY_UNAVAILABLE_CAVEAT);
    expect(assistant.querySelector('.assistant-caveat')).toBeNull();
    expect(assistant.querySelector('.assistant-memory')).toBeNull();
    expect(assistant.textContent).not.toContain('memory:');
    // the only source claim is the accurate `answered from:` provenance line
    expect(assistant.textContent).toContain('answered from: Workflow & Artifacts');
  });

  it('the explain chip echoes the ACTIVE question live, answered from Workflow & Artifacts', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    fireEvent.click(panel.getByText('What does this question want?').closest('button')!);
    expect(panel.getByText(EXPLAIN_CURRENT)).toBeInTheDocument();
    expect(panel.getByText('answered from: Workflow & Artifacts')).toBeInTheDocument();
  });

  it('the missing-field chip routes to the deterministic schema check, answered from Schema Rules', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    fireEvent.click(panel.getByText('What if I leave one missing?').closest('button')!);
    expect(panel.getByText(MISSING_BEHAVIOR)).toBeInTheDocument();
    expect(panel.getByText('answered from: Schema Rules')).toBeInTheDocument();

    // the routed truth chip never states a verdict / validity conclusion
    expect(assistant.textContent).not.toMatch(VERDICT);
    expect(assistant.textContent).not.toMatch(INVALID_AGAINST);
  });

  it('is guided-prompts-only — the note is present and there is NO textbox/send button', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByText, queryByRole } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    expect(
      getByText('Guided prompts only — the assistant answers the suggested questions above.'),
    ).toBeInTheDocument();
    // no free-text affordance inside the assistant panel
    expect(container.querySelector('.assistant textarea')).toBeNull();
    expect(container.querySelector('.assistant input')).toBeNull();
    expect(queryByRole('button', { name: /send/i })).toBeNull();
  });

  it('clicking a chip issues NO new network request (pure, LLM-free)', async () => {
    const calls = stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    const panel = within(container.querySelector('.assistant') as HTMLElement);
    const before = calls.length;

    fireEvent.click(panel.getByText('What if I leave one missing?').closest('button')!);
    expect(panel.getByText(MISSING_BEHAVIOR)).toBeInTheDocument();
    expect(calls.length).toBe(before);
  });

  it('no verdict language anywhere in the assistant panel across every chip', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('Answer 5 Questions to Finish This Record');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    const panel = within(assistant);

    for (const label of [
      'Which fields still need me?',
      'What does this question want?',
      'What if I leave one missing?',
    ]) {
      fireEvent.click(panel.getByText(label).closest('button')!);
      expect(assistant.textContent).not.toMatch(VERDICT);
      expect(assistant.textContent).not.toMatch(INVALID_AGAINST);
      expect(assistant.textContent).not.toMatch(/\bthat is a truth question\b/i); // guard never triggered
    }
  });

  it('the assistant also mounts on the all-resolved branch (0 pending), honestly', async () => {
    stubFetchRoutes(exportReadyRoutes('demo')); // pending: [] from the first load
    const { container, findByText } = renderAt('/record/demo/complete');

    await findByText('All Fields Resolved');
    const assistant = container.querySelector('.assistant') as HTMLElement;
    expect(assistant).not.toBeNull();
    const panel = within(assistant);

    // pending is empty → the honest empty-state summary, still guided-only
    expect(panel.getByText('This draft currently has no pending fields listed.')).toBeInTheDocument();
    expect(assistant.querySelectorAll('.assistant-prompt').length).toBe(3);
  });

  it('does NOT render an assistant panel in the loading state', () => {
    // never-resolving fetch keeps the screen in its loading state
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    const { container, getByRole } = renderAt('/record/demo/complete');
    expect(getByRole('status')).toBeInTheDocument(); // LoadingPanel
    expect(container.querySelector('.assistant')).toBeNull();
  });

  it('does NOT render an assistant panel when the backend is down', async () => {
    stubFetchDown();
    const { container, findByText } = renderAt('/record/demo/complete');
    await findByText('Backend Not Running');
    expect(container.querySelector('.assistant')).toBeNull();
  });
});
