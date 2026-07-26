/**
 * P36.3 — the standalone Governance & Safety Validator (RecordValidator).
 *
 * Paste or upload a candidate JSON record; it is checked server-side against
 * the official ISAAC schema via `POST /api/validate/record`, which reuses the
 * SAME authoritative `validate_official` as `isaac validate --official`. This
 * component computes NO verdict itself — it only renders what the endpoint
 * returns, via the shared VerdictCard.
 *
 * These tests pin:
 *   - a valid record renders PASS; an invalid one renders structured errors;
 *   - malformed JSON / oversized input are rejected CLIENT-SIDE, never reaching
 *     the server (no fetch call);
 *   - the verdict is announced (an accessible live region via VerdictCard's
 *     `role="status"`);
 *   - the file input reads its contents into the textarea.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { RecordValidator } from '../components/RecordValidator';
import { stubFetchRoutes, stubFetchDown } from '../test/apiFixtures';
import {
  validateRecordPass,
  validateRecordFail,
  syntheticCandidateRecord,
} from '../test/apiFixtures';

const URL = 'POST /api/validate/record';

function fileInput(): HTMLInputElement {
  const input = screen.getByLabelText(/upload a candidate isaac record/i);
  return input as HTMLInputElement;
}

function textarea(): HTMLTextAreaElement {
  return screen.getByLabelText(/candidate record \(json\)/i) as HTMLTextAreaElement;
}

function paste(text: string) {
  fireEvent.change(textarea(), { target: { value: text } });
}

function clickValidate() {
  fireEvent.click(screen.getByRole('button', { name: /^validate$/i }));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// --- P36R S8: the clarifying purpose copy ---------------------------------------

describe('RecordValidator — stated purpose (P36R S8 copy)', () => {
  it('leads with the distinct purpose: validate WITHOUT adding to My Experiments', () => {
    render(<RecordValidator />);
    expect(
      screen.getByText(/Validate a record without adding it to My Experiments\./i),
    ).toBeInTheDocument();
  });

  it('lists the four things it is for, as a secondary disclosure', () => {
    render(<RecordValidator />);
    fireEvent.click(screen.getByText(/when to use this/i));
    expect(screen.getByText(/Inspect an external JSON object/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirm API and CLI validation parity/i)).toBeInTheDocument();
    expect(screen.getByText(/Diagnose structured schema errors by path/i)).toBeInTheDocument();
    expect(screen.getByText(/Independently verify an artifact you already exported/i)).toBeInTheDocument();
    expect(screen.getByText(/Nothing checked here is created, saved, or changed\./i)).toBeInTheDocument();
  });

  it('names the authoritative gate it reuses, not a second implementation', () => {
    render(<RecordValidator />);
    expect(screen.getAllByText('isaac validate --official').length).toBeGreaterThan(0);
    expect(screen.getByText('validate_official')).toBeInTheDocument();
  });

  it('states the 512 KB bound in the interface, not only in an error', () => {
    render(<RecordValidator />);
    expect(screen.getByText(/Accepts JSON up to 512 KB\./i)).toBeInTheDocument();
  });

  it('offers no propose/approve/edit/save affordance — only Upload and Validate', () => {
    render(<RecordValidator />);
    expect(screen.queryByRole('button', { name: /propose|approve|edit|delete|save|add to/i })).toBeNull();
    expect(screen.getAllByRole('button').map((b) => b.textContent?.trim())).toEqual([
      'Upload JSON File',
      'Validate',
    ]);
  });
});

// --- honest scope + empty state -------------------------------------------------

describe('RecordValidator — pre-validation', () => {
  it('states the synthetic/local scope: nothing is uploaded to a model or stored', () => {
    render(<RecordValidator />);
    expect(screen.getByText(/nothing here is uploaded to a model/i)).toBeInTheDocument();
  });

  it('shows an empty state before any record is checked', () => {
    render(<RecordValidator />);
    expect(screen.getByText(/no record checked yet/i)).toBeInTheDocument();
  });

  it('exposes a keyboard-reachable textarea, file input, and Validate button', () => {
    render(<RecordValidator />);
    expect(textarea()).toBeInTheDocument();
    expect(fileInput()).toHaveAttribute('accept', expect.stringContaining('.json'));
    expect(screen.getByRole('button', { name: /^validate$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upload json file/i })).toBeInTheDocument();
  });

  it('keeps the hidden file input out of the tab order (triggered by the visible button)', () => {
    render(<RecordValidator />);
    expect(fileInput().tabIndex).toBe(-1);
    expect(screen.getByRole('button', { name: /upload json file/i }).tabIndex).toBe(0);
  });
});

// --- valid / invalid records -----------------------------------------------------

describe('RecordValidator — validating a pasted record', () => {
  it('renders PASS for a valid record, plus its summary and schema version', async () => {
    const hits = stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    paste(JSON.stringify(syntheticCandidateRecord));
    clickValidate();
    expect(await screen.findByText('PASS')).toBeInTheDocument();
    expect(document.querySelector('.rec-val-schema-line')).toHaveTextContent('v1.05');
    expect(hits).toEqual([URL]);
  });

  it('sends the parsed JSON object as the POST body', async () => {
    stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    paste(JSON.stringify(syntheticCandidateRecord));
    clickValidate();
    await screen.findByText('PASS');
    const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    const [, init] = calls.find(([u]) => String(u).includes('/validate/record'))!;
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent).toEqual(syntheticCandidateRecord);
  });

  it('renders structured {path, message} errors for a schema-invalid record', async () => {
    stubFetchRoutes({ [URL]: { body: validateRecordFail } });
    render(<RecordValidator />);
    paste(JSON.stringify({ ...syntheticCandidateRecord, system: { technique: 'telepathy' } }));
    clickValidate();
    expect(await screen.findByText('FAIL')).toBeInTheDocument();
    const path = screen.getByText('system.technique');
    expect(path).toBeInTheDocument();
    expect(path.closest('.schema-error-row')).toHaveTextContent(/not one of/i);
  });

  it('shows the full validator summary in a disclosure', async () => {
    stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    paste(JSON.stringify(syntheticCandidateRecord));
    clickValidate();
    await screen.findByText('PASS');
    fireEvent.click(screen.getByText(/full validator summary/i));
    expect(screen.getByText(validateRecordPass.summary)).toBeInTheDocument();
  });
});

// --- client-side rejection: never reaches the server -----------------------------

describe('RecordValidator — client-side rejection (no server call)', () => {
  it('rejects non-JSON text without hitting the server', async () => {
    const hits = stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    paste('this is not { json');
    clickValidate();
    expect(await screen.findByText(/valid json/i)).toBeInTheDocument();
    expect(hits).toHaveLength(0);
  });

  it('rejects oversized pasted input without hitting the server', async () => {
    const hits = stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    const huge = JSON.stringify({ padding: 'x'.repeat(600 * 1024) });
    paste(huge);
    clickValidate();
    expect(await screen.findByText(/too large/i)).toBeInTheDocument();
    expect(hits).toHaveLength(0);
  });

  it('rejects an empty textarea without hitting the server', async () => {
    const hits = stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    clickValidate();
    expect(await screen.findByText(/paste or upload a json record first/i)).toBeInTheDocument();
    expect(hits).toHaveLength(0);
  });
});

// --- file upload reads into the textarea -----------------------------------------

describe('RecordValidator — file upload', () => {
  it('reads an uploaded JSON file into the textarea', async () => {
    render(<RecordValidator />);
    const content = JSON.stringify(syntheticCandidateRecord, null, 2);
    const file = new File([content], 'record.json', { type: 'application/json' });
    fireEvent.change(fileInput(), { target: { files: [file] } });
    await waitFor(() => expect(textarea().value).toBe(content));
  });

  it('rejects an oversized file client-side without reading it into the textarea', async () => {
    render(<RecordValidator />);
    const big = 'x'.repeat(600 * 1024);
    const file = new File([big], 'huge.json', { type: 'application/json' });
    Object.defineProperty(file, 'size', { value: 600 * 1024 });
    fireEvent.change(fileInput(), { target: { files: [file] } });
    expect(await screen.findByText(/too large/i)).toBeInTheDocument();
    expect(textarea().value).toBe('');
  });
});

// --- verdict accessibility + backend-down -----------------------------------------

describe('RecordValidator — accessibility + degraded backend', () => {
  it('announces the verdict via an accessible live region', async () => {
    stubFetchRoutes({ [URL]: { body: validateRecordPass } });
    render(<RecordValidator />);
    paste(JSON.stringify(syntheticCandidateRecord));
    clickValidate();
    // VerdictCard's outer <section> carries role="status" (implicit aria-live)
    // and an accessible name identifying the verdict — wait for THAT specific
    // named status region, not the earlier (also role="status") loading panel.
    const status = await screen.findByRole('status', { name: /validation pass/i });
    expect(status).toHaveTextContent('PASS');
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    render(<RecordValidator />);
    paste(JSON.stringify(syntheticCandidateRecord));
    clickValidate();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/not running|unreachable/i);
  });
});
