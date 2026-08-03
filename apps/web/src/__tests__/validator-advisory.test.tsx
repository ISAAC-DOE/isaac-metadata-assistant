/**
 * R2 · the advisory tier is VISIBLE on the standalone validator, and is not mistaken
 * for a verdict.
 *
 * The defect this covers: `POST /api/validate/record` called schema validation and
 * nothing else, so a record with `measurement.series: []` reached the operator as an
 * unqualified PASS — schema-valid, zero errors, no indication anywhere that it held no
 * measured data. The per-record route had always run `portal_warnings`; this surface,
 * the one an operator actually points at a candidate file, was the only place they
 * never ran.
 *
 * The two properties asserted here are in tension and both matter:
 *
 *   1. the warnings must be SHOWN (otherwise the backend fix is invisible), and
 *   2. they must not read as a failure — `ok: true` must still present as a PASS.
 *
 * Getting (2) wrong would be a new honesty defect in the opposite direction: an
 * advisory note styled as an error teaches the reader that something blocked them
 * when nothing did.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, cleanup, screen } from '@testing-library/react';
import { RecordValidator } from '../components/RecordValidator';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const EMPTY_SERIES_RECORD = JSON.stringify({
  isaac_record_version: '1.05',
  measurement: { series: [] },
});

/** A PASS carrying advisory notes — the exact shape the empty-series QA file produces. */
const PASS_WITH_WARNINGS = {
  ok: true,
  summary: 'Official validation: PASS',
  errors: [],
  schema_version: '1.05',
  advisory: true,
  gating: false,
  warnings: [
    { code: 'NO_LINKS', where: 'links', message: 'record declares no relationships to other records.' },
    {
      code: 'NO_MEASUREMENT_SERIES',
      where: 'measurement.series',
      message: '`measurement.series` is empty, so the record contains no measured data.',
    },
  ],
};

function stubValidate(body: unknown, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (String(url).includes('/validate/record')) {
        return new Response(JSON.stringify(body), {
          status,
          headers: { 'content-type': 'application/json' },
        });
      }
      return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
    })
  );
}

async function validate(text: string) {
  render(<RecordValidator />);
  const box = screen.getByRole('textbox');
  fireEvent.change(box, { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: /Validate/i }));
}

describe('R2 · the validator shows advisory notes without calling them failures', () => {
  it('renders each advisory note with its path and message', async () => {
    stubValidate(PASS_WITH_WARNINGS);
    await validate(EMPTY_SERIES_RECORD);

    expect(await screen.findByText(/Advisory notes \(2\)/)).toBeInTheDocument();
    expect(screen.getByText('measurement.series')).toBeInTheDocument();
    expect(
      screen.getByText(/contains no measured data/),
      'the empty-series advisory is the whole point of this slice — an operator must see it'
    ).toBeInTheDocument();
    expect(screen.getByText('links')).toBeInTheDocument();
  });

  it('says out loud that the notes do not affect the verdict', async () => {
    stubValidate(PASS_WITH_WARNINGS);
    await validate(EMPTY_SERIES_RECORD);
    expect(await screen.findByText(/do not affect the verdict/i)).toBeInTheDocument();
  });

  it('still presents a PASS as a PASS when warnings are present', async () => {
    stubValidate(PASS_WITH_WARNINGS);
    await validate(EMPTY_SERIES_RECORD);

    // The verdict comes from `ok` alone. If a future change ORs the warning count into
    // the verdict, this fails — which is the intent: the advisory tier must never
    // become a second authority on validity beside the vendored schema.
    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(screen.queryByText('FAIL')).toBeNull();
  });

  it('renders nothing advisory when the response carries no warnings', async () => {
    stubValidate({ ...PASS_WITH_WARNINGS, warnings: [] });
    await validate(EMPTY_SERIES_RECORD);

    await screen.findByText('PASS');
    expect(
      screen.queryByText(/Advisory notes/),
      'an empty warning list must not render an empty box'
    ).toBeNull();
  });

  it('does not break on a response with no advisory fields at all', async () => {
    // Older/other shapes must not throw — the fields are optional in the type for
    // exactly this reason.
    // Summary deliberately NOT the bare string 'PASS': that would also match the
    // verdict chip's text and make findByText ambiguous. A test that fails on its own
    // fixture wording teaches nothing.
    stubValidate({ ok: true, summary: 'Official validation: ok', errors: [], schema_version: '1.05' });
    await validate(EMPTY_SERIES_RECORD);

    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(screen.queryByText(/Advisory notes/)).toBeNull();
  });

  it('shows advisory notes alongside a FAIL too, without merging the two', async () => {
    stubValidate({
      ...PASS_WITH_WARNINGS,
      ok: false,
      summary: 'Official validation: FAIL',
      errors: [{ path: 'record_type', message: "'record_type' is a required property" }],
    });
    await validate(EMPTY_SERIES_RECORD);

    expect(await screen.findByText('FAIL')).toBeInTheDocument();
    expect(screen.getByText(/Advisory notes \(2\)/)).toBeInTheDocument();
    // The schema error is what failed it — the advisory is separate and additional.
    expect(screen.getByText(/'record_type' is a required property/)).toBeInTheDocument();
  });
});
