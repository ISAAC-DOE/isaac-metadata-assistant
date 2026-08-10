import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { FAN_OUT_REASON, fanOutExportedRoutes, stubFetchRoutes } from '../test/apiFixtures';

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
    // deleting the id from the ordinary case, which is every record this API can
    // currently create.
    const { bundleRoutes, exportedReadyRoutes } = await import('../test/apiFixtures');
    stubFetchRoutes({ ...bundleRoutes('demo'), ...exportedReadyRoutes('demo') });
    const { findByText } = renderAt('/record/demo');

    expect(await findByText('Exported · demo')).toBeInTheDocument();
  });
});
