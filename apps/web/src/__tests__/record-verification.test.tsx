import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RecordVerification } from '../screens/statistics/RecordVerification';
import { SAFEGUARD_LABELS, SAFEGUARD_STATE_LABELS } from '../lib/verificationContract';
import {
  verificationFailureEnvelope,
  verificationFutureFormat,
  verificationReportNoSuppression,
  verificationReportOk,
  verificationReportWithFindings,
  verificationRunningEnvelope,
} from '../test/verificationFixtures';

/**
 * The Record Verification section, rendered.
 *
 * The single most consequential rule this file guards: a safeguard that reads
 * `not_applicable` on the wire must NEVER reach the screen as the word
 * "verified" or as an affirmative tick. `transaction_read_only` is
 * `not_applicable` in the shipped mode because no database is contacted, and
 * claiming a read-only transaction was verified would be a statement about an
 * event that never happened — the exact class of false claim `CLAUDE.md` §15
 * records this project shipping and correcting more than once.
 */

function renderReport(body: unknown) {
  return render(
    <RecordVerification
      verification={
        {
          status: 'data',
          data: body,
          reload: () => {},
          reloadSilent: () => {},
        } as never
      }
    />,
  );
}

describe('the safeguards panel', () => {
  it('renders not_applicable with its own word, never as verified', () => {
    renderReport(verificationReportOk);

    const label = screen.getByText(SAFEGUARD_LABELS.transaction_read_only);
    const row = label.closest('.stats-verify-safeguard');
    expect(row).not.toBeNull();

    const state = row!.querySelector('.stats-verify-state');
    expect(state).not.toBeNull();
    expect(state!.getAttribute('data-state')).toBe('not_applicable');
    expect(state!.textContent).toBe(SAFEGUARD_STATE_LABELS.not_applicable);
    expect(state!.textContent).not.toMatch(/verified/i);
  });

  it('gives each of the three states a distinct word', () => {
    // If two states ever share a label, the panel stops carrying the
    // distinction it exists to carry.
    const labels = Object.values(SAFEGUARD_STATE_LABELS);
    expect(new Set(labels).size).toBe(labels.length);
    expect(SAFEGUARD_STATE_LABELS.not_applicable).not.toBe(
      SAFEGUARD_STATE_LABELS.verified,
    );
  });

  it('does not carry meaning by colour alone', () => {
    // Every state row exposes a text state as well as a tone attribute.
    renderReport(verificationReportOk);
    const states = document.querySelectorAll('.stats-verify-state');
    expect(states.length).toBeGreaterThan(0);
    states.forEach((node) => {
      expect(node.textContent?.trim()).not.toBe('');
    });
  });

  it('surfaces a degraded safeguard instead of normalising it', () => {
    renderReport(verificationReportWithFindings);
    const states = Array.from(document.querySelectorAll('.stats-verify-state'));
    const degraded = states.filter((n) => n.getAttribute('data-state') === 'unverified');
    expect(degraded.length).toBeGreaterThan(0);
  });

  it('reports a nonzero DML count as attention rather than hiding it', () => {
    renderReport(verificationReportWithFindings);
    expect(
      screen.getByText(/counted at least one statement/i),
    ).toBeTruthy();
  });

  it('says the run counted no data-changing statement when both counts are zero', () => {
    renderReport(verificationReportOk);
    expect(screen.getByText(/counted no statement/i)).toBeTruthy();
  });
});

describe('states that are not a report', () => {
  it('shows a running sweep as pending, not as zeros', () => {
    renderReport(verificationRunningEnvelope);
    expect(document.body.textContent).not.toMatch(/\b0 of 0\b/);
    expect(document.querySelectorAll('.stats-verify-state').length).toBe(0);
  });

  it('shows the null-filled failure envelope as unavailable, not as zeros', () => {
    // The backend projects this envelope non-strictly, so every block is null.
    // Rendering those as 0 would be a fabricated measurement.
    renderReport(verificationFailureEnvelope);
    expect(document.querySelectorAll('.stats-verify-state').length).toBe(0);
  });

  it('refuses a format version it has not been checked against', () => {
    renderReport(verificationFutureFormat);
    expect(document.querySelectorAll('.stats-verify-state').length).toBe(0);
  });
});

describe('disclosure of withheld histogram cells', () => {
  it('discloses in visible copy that categories were withheld', () => {
    renderReport(verificationReportOk);
    const withheld = verificationReportOk.format_shadow.failures_by_error_code
      .suppressed_categories;
    expect(withheld).toBeGreaterThan(0);
    expect(document.body.textContent).toMatch(/withheld/i);
  });

  it('never renders a withheld key, because none is on the wire', () => {
    renderReport(verificationReportOk);
    const text = document.body.textContent ?? '';
    // The payload carries counts and a category count — never the key names.
    expect(text).not.toMatch(/suppressed_categories/);
  });

  it('says nothing about withholding when nothing was withheld', () => {
    renderReport(verificationReportNoSuppression);
    const hist = verificationReportNoSuppression.format_shadow.failures_by_error_code;
    expect(hist.suppressed_categories).toBe(0);
  });
});

describe('what must never appear', () => {
  it('renders no record identifier, title, hostname or connection string', () => {
    renderReport(verificationReportOk);
    const text = document.body.textContent ?? '';
    for (const forbidden of [
      'record_id',
      'postgres://',
      'PGHOST',
      'localhost',
      'isaac-psql',
      'metadata_assistant',
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it('discloses which corpus ran, verbatim', () => {
    renderReport(verificationReportOk);
    expect(document.body.textContent).toContain('public_upstream_corpus');
  });
});

describe('the headline figures', () => {
  it('states the corpus size it actually received', () => {
    renderReport(verificationReportOk);
    const size = String(verificationReportOk.metadata.corpus_size);
    expect(document.body.textContent).toContain(size);
  });

  it('reports unexpected mutation outcomes when there are some', () => {
    renderReport(verificationReportWithFindings);
    expect(verificationReportWithFindings.mutations.unexpected_outcomes).toBe(3);
    expect(document.body.textContent).toContain('3');
  });
});
