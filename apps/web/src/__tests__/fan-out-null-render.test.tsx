import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  FAN_OUT_REASON,
  FAN_OUT_RUN_IDS,
  evidenceBundleRoutes,
  exportReadyRoutes,
  fanOutExportSuccess,
  fanOutExportedRoutes,
  stubFetchRoutes,
} from '../test/apiFixtures';

/**
 * F-C — `exported: true` beside a NULL `record_id` reached two screens as the
 * literal string `null`.
 *
 * Measured on `74509c4`, for a fully-exported 2-run fan-out
 * (`exported: True | record_id: None | artifact_refs: {record_filename: None,
 * sidecar_filename: None}`):
 *
 *   RecordWorkbench.tsx:294  `Exported · ${detail.record_id}`   -> "Exported · null"
 *   ExportReadiness.tsx:353  `${detail.record_id}.json`         -> "null.json"
 *   ExportReadiness.tsx:357  `${detail.record_id}.evidence.json`-> "null.evidence.json"
 *
 * The last two then rendered into the TopBar filename AND into both artifact cards,
 * the record one beside a PASS verdict chip.
 *
 * NO FRONTEND SCREEN WAS SWEPT IN ANY REVIEW ROUND, and the backend AST guard that
 * enumerates every surface reading the singular pair cannot cross the language
 * boundary. Nor could any existing fixture produce the combination: every
 * `exported: true` fixture in `apiFixtures.ts` carried a non-null `record_id`, so a
 * green suite proved nothing about this state. `fanOutExportedRoutes` closes that,
 * and the assertions below are deliberately about the RENDERED TEXT rather than
 * about a prop, because the defect was a template literal and only the output shows
 * it.
 */

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

/** Every rendered string that would betray an interpolated null. */
const NULL_MARKERS = [
  'null',
  'undefined',
  'NaN',
  '[object Object]',
];

function assertNoNullText(root: HTMLElement) {
  const text = root.textContent ?? '';
  for (const marker of NULL_MARKERS) {
    expect(text.toLowerCase(), `rendered the literal "${marker}"`).not.toContain(
      marker.toLowerCase(),
    );
  }
}

/**
 * The Evidence screen's bundle in one of two states, differing ONLY in whether the
 * record was exported and whether it has an experiment-level sidecar.
 *
 * `fanOut: true` is `exported: true` with a null singular id, null artifact refs and
 * a null `/artifacts` pair — the state the screen derived `exported` from the WRONG
 * one of those.
 */
function evidenceRoutesFor(id: string, opts: { exported: boolean; fanOut: boolean }) {
  const base = `/api/experiments/${id}`;
  const routes = evidenceBundleRoutes(id);
  const detail = (routes[`GET ${base}`] as { body: Record<string, unknown> }).body;
  return {
    ...routes,
    [`GET ${base}`]: {
      body: {
        ...detail,
        exported: opts.exported,
        status: opts.exported ? 'done' : 'in_review',
        record_id: null,
        artifact_refs: {
          record_filename: null,
          sidecar_filename: null,
          ...(opts.fanOut ? { reason: FAN_OUT_REASON } : {}),
        },
      },
    },
    [`GET ${base}/artifacts`]: {
      body: {
        record: null,
        sidecar: null,
        record_filename: null,
        sidecar_filename: null,
        artifact: { state: opts.exported ? ('current' as const) : ('none' as const), reason: null },
        ...(opts.fanOut ? { reason: FAN_OUT_REASON } : {}),
      },
    },
  };
}

describe('a fan-out record never renders the string "null"', () => {
  it('Export Readiness shows the server-authored reason, not null.json', async () => {
    stubFetchRoutes(fanOutExportedRoutes('demo'));
    const { container, findByText, queryByText } = renderAt('/record/demo/export');

    // The screen has reached its post-export state (the defect only appears there:
    // `exported` is true, so the artifact section renders).
    await findByText(FAN_OUT_REASON);

    expect(queryByText('null.json')).toBeNull();
    expect(queryByText('null.evidence.json')).toBeNull();
    assertNoNullText(container as HTMLElement);
  });

  it('the Record Workbench status reads "Exported", never "Exported · null"', async () => {
    stubFetchRoutes(fanOutExportedRoutes('demo'));
    const { container, findAllByText, queryByText } = renderAt('/record/demo');

    expect((await findAllByText('Exported')).length).toBeGreaterThan(0);
    expect(queryByText('Exported · null')).toBeNull();
    assertNoNullText(container as HTMLElement);
  });

  it('CONTROL — a zero-run exported record is unchanged and still names its id', async () => {
    // The whole point of the guard above is that it must not have been bought by
    // deleting the id from the ordinary case — a record with no runs, which is how
    // every record starts and how it stays until a run is added through
    // `POST /api/experiments/{experiment_id}/runs`. (Was "every record this API can
    // currently create"; false since #109 added that route.)
    const { bundleRoutes, exportedReadyRoutes } = await import('../test/apiFixtures');
    stubFetchRoutes({ ...bundleRoutes('demo'), ...exportedReadyRoutes('demo') });
    const { findByText } = renderAt('/record/demo');

    expect(await findByText('Exported · demo')).toBeInTheDocument();
  });
});

/**
 * B4/B5 — a fan-out never says something FALSE either.
 *
 * The sweep that produced the tests above classified sites by whether they printed
 * a null. That was the wrong axis, and this branch's own standard says so: a guard
 * that avoids the null and substitutes a claim that is false for an exported record
 * is not GUARDED, it is BROKEN. Two of them were quoted as guarded siblings.
 *
 * A RE-SWEEP with `rg --text` — plain `rg` DROPPED all 20 hits in
 * `apps/web/src/lib/experimentGraph.ts`, which is how the first sweep lost that file
 * entirely — finds
 * 67 consumers: 14 BROKEN, 15 GUARDED, 38 NOT-AFFECTED (previously reported as
 * 41 / 8 / 8 / 25). Part of the +26 is finer granularity; the part that is not is
 * `experimentGraph.ts`, the two `POST /export` response sites, and the whole
 * `EvidenceExplorer -> EvidenceTrailPanel / SourcePreview` derivation chain.
 *
 * The two fixed here are the two that ALARM. The rest are recorded in the commit
 * message and are passive.
 *
 * THAT FILE NO LONGER CONTAINS A NUL BYTE, AND THE SENTENCE ABOVE IS CORRECTED RATHER
 * THAN DELETED because the sweep numbers depend on it. ~~"plain `rg` reports … as
 * 'binary file matches' because it contains a NUL byte"~~ — since `7a66127` the
 * separator is written as the escape `\u0000`, the runtime string is unchanged, and
 * `experimentGraph.ts` holds ZERO NUL bytes. Re-measured on the pre-fix bytes rather
 * than repeated from memory (ripgrep 14.1.1): a DIRECTORY sweep — `rg TOKEN dir/`,
 * which is how the original sweep ran — omitted the file with NO notice and exited 0;
 * an explicitly NAMED file printed the visible `binary file matches` line instead; and
 * `rg -c`, `rg --text -c` and `/usr/bin/grep -c` all returned the CORRECT count. So
 * the silence was the traversal's, not ripgrep's in general, and `grep`'s own silent
 * variant needs `-I`. The 67/14/15/38 figures above stand: they were produced with
 * `--text`, which was correct then and is a no-op for this file now.
 */
describe('a fan-out never states something false', () => {
  it('a SUCCESSFUL fan-out export is not reported as a refusal that wrote nothing', async () => {
    // `post_export` pops `record`/`sidecar` for a fan-out while `ok` stays true, and
    // `doExport` tested `resp.ok && resp.record && resp.sidecar`. Measured: the
    // screen rendered, in a `role="alert"`, "Export was refused by the gated
    // validation — nothing was written. 0 schema errors." — three falsehoods and a
    // nonsense count, over N immutable official ISAAC records that HAD been written.
    // `onRefresh()` was never called either, so the screen could not recover; the
    // user's retry then got a 409 "This record already exists on disk", flatly
    // contradicting "nothing was written" seconds earlier.
    const calls = stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/export': { body: fanOutExportSuccess },
    });
    const { findByText, queryByText, getByText } = renderAt('/record/demo/export');

    const exportBtn = (await findByText('Export Official Record + Sidecar')).closest('button')!;
    const before = calls.filter((c) => c === 'GET /api/experiments/demo').length;
    fireEvent.click(exportBtn);

    // What it must SAY: two records were written, named.
    expect(await findByText(/2 official records/i)).toBeInTheDocument();
    for (const runId of FAN_OUT_RUN_IDS) {
      expect(getByText(new RegExp(`${runId}\\.json`))).toBeInTheDocument();
    }
    // …and what it must not say.
    expect(queryByText(/refused by the gated validation/i)).toBeNull();
    expect(queryByText(/nothing was written/i)).toBeNull();
    expect(queryByText(/schema error/i)).toBeNull();

    // …and it must RECOVER: the export response is adopted and the bundle refetched.
    await waitFor(() => {
      expect(calls.filter((c) => c === 'GET /api/experiments/demo').length).toBeGreaterThan(before);
    });
  });

  it('CONTROL — a zero-run export still reaches the ordinary success path', async () => {
    // The branch above must not have been bought by weakening the common case: a
    // record with no runs, which is how every record starts and how it stays until
    // `POST /api/experiments/{id}/runs` adds one. (This comment used to say "which
    // is every record this API can currently create" — false since that route
    // shipped, and mirrored in the export operation's own description, which is
    // corrected in the same change as this line.)
    const { exportSuccess } = await import('../test/apiFixtures');
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/export': { body: exportSuccess },
    });
    const { findByText, queryByText } = renderAt('/record/demo/export');
    fireEvent.click((await findByText('Export Official Record + Sidecar')).closest('button')!);

    expect(await findByText('Official Record')).toBeInTheDocument();
    expect(queryByText(/refused by the gated validation/i)).toBeNull();
    expect(queryByText(/official records/i)).toBeNull();
  });

  it('the Evidence screen calls an exported fan-out exported, not a Draft', async () => {
    // `const exported = artifacts.sidecar !== null` (EvidenceExplorer.tsx) is a
    // DERIVED `exported` that never reads `detail.exported`. A fan-out has no
    // experiment-level sidecar, so the derivation says false for a record that has
    // been exported N times. Measured by rendering:
    //
    //   "Evidence & File PreviewDraftdraft · demo … generated_utc not exported yet"
    //
    // `:202` was quoted in `0337d19`'s message as a GUARDED sibling. It is not: the
    // guard prevents a printed null and produces a false claim instead.
    stubFetchRoutes(evidenceRoutesFor('demo', { exported: true, fanOut: true }));
    const { container, findByText, queryByText } = renderAt('/record/demo/evidence');

    await findByText('Evidence Support');
    const text = (container as HTMLElement).textContent ?? '';

    expect(queryByText('Draft')).toBeNull();
    expect(text).not.toContain('draft · demo');
    expect(text).not.toContain('not exported yet');
    // The positive half: the screen says what IS true of this record.
    expect(text).toContain('Exported');
  });

  it('CONTROL — an unexported record is still called a draft on the Evidence screen', async () => {
    stubFetchRoutes(evidenceRoutesFor('demo', { exported: false, fanOut: false }));
    const { container, findByText } = renderAt('/record/demo/evidence');

    await findByText('Evidence Support');
    const text = (container as HTMLElement).textContent ?? '';
    expect(text).toContain('draft · demo');
    expect(text).toContain('not exported yet');
  });
});
