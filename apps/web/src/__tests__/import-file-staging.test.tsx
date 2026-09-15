import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import type { ComponentProps } from 'react';

import { ImportFileStaging, formatBytes } from '../components/ImportFileStaging';

/**
 * Choosing files for an import WITHOUT sending one.
 *
 * ── WHY THIS FILE IS SHAPED THE WAY IT IS ──────────────────────────────────
 *
 * The guard this component had to reconcile (`historical-import.test.tsx` §1)
 * asserted that the screen renders NO `input[type="file"]` at all. That guard
 * banned the AFFORDANCE. `DEC-33` authorises the affordance and supplies the
 * mitigation the original decline asked for, so the replacement guard has to
 * ban the HARM instead — which is a strictly stronger claim and is what this
 * file asserts:
 *
 *   1. no byte leaves the browser (behavioural AND structural),
 *   2. every staged row discloses that, visibly,
 *   3. nothing is ever described as verified.
 *
 * A test that only checked (2) would pass on a component that uploaded
 * everything and lied about it, which is why (1) is asserted twice by two
 * independent methods.
 */

const SOURCE = readFileSync(
  resolve(__dirname, '../components/ImportFileStaging.tsx'),
  'utf8',
);

function file(name: string, body = 'synthetic bytes', type = 'text/plain') {
  return new File([body], name, { type });
}

/** Drive the hidden input the way a file dialog does. */
function choose(files: File[]) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (input === null) throw new Error('no file input rendered');
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  fireEvent.change(input);
}

afterEach(() => vi.restoreAllMocks());

describe('the file staging panel sends nothing', () => {
  /*
   * (1a) BEHAVIOURAL. A spy on the two transports that could carry a byte. This
   * is the assertion that would fail on a component that actually uploaded,
   * which the structural one below cannot guarantee on its own — a fetch can be
   * spelled in ways a regex will not catch.
   */
  it('issues no network request when files are chosen', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch' as never).mockImplementation((() => {
      throw new Error('the staging panel must not perform a request');
    }) as never);
    const xhrSpy = vi.spyOn(XMLHttpRequest.prototype, 'open').mockImplementation(() => {
      throw new Error('the staging panel must not perform a request');
    });

    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan_0012.mac'), file('run_log.txt')]);

    expect(await screen.findByText('scan_0012.mac')).toBeInTheDocument();
    expect(screen.getByText('run_log.txt')).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(xhrSpy).not.toHaveBeenCalled();
  });

  /*
   * (1b) STRUCTURAL, and it is about what this module CAN do rather than what
   * it did on one path. The component takes `onRecord` as a prop precisely so
   * it cannot import the API client — that makes "this file cannot send a byte"
   * checkable rather than a promise in a comment.
   */
  it('declares no upload machinery and does not import the API client', () => {
    expect(SOURCE).not.toMatch(/FormData/);
    expect(SOURCE).not.toMatch(/multipart/i);
    expect(SOURCE).not.toMatch(/XMLHttpRequest/);
    expect(SOURCE).not.toMatch(/\bfetch\s*\(/);
    expect(SOURCE).not.toMatch(/from '\.\.\/lib\/api'/);
    // The negative control for this whole block: the thing it is scanning must
    // actually be the picker. Without this the five bans above pass on any file.
    expect(SOURCE).toMatch(/type="file"/);
  });

  /* (2) The disclosure is VISIBLE — not in a tooltip, not inside a <details>.
     A privacy state is one of the five things the copy rule says stays out in
     the open, so this asserts placement and not merely presence. */
  it('states that the file is not sent, in the open', () => {
    const { container } = render(<ImportFileStaging onRecord={async () => {}} />);
    const claim = screen.getByText(/The file itself\s+is not sent to ISAAC/);
    expect(claim).toBeInTheDocument();
    expect(claim.closest('details')).toBeNull();
    expect(claim.closest('[hidden]')).toBeNull();
    expect(container.querySelector('.ifs-claim')).not.toBeNull();
  });

  it('marks every freshly chosen row local-only', () => {
    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('a.mac'), file('b.mac')]);
    expect(screen.getAllByText('Local only — not sent to ISAAC')).toHaveLength(2);
  });
});

describe('the staged list', () => {
  it('shows name, size and type, and removes a row by an accessible name', async () => {
    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan_0012.mac', 'x'.repeat(2048))]);

    expect(screen.getByText('scan_0012.mac')).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KB · text\/plain/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove scan_0012.mac from this list' }));
    await waitFor(() => expect(screen.queryByText('scan_0012.mac')).toBeNull());
  });

  /* Selecting the same file twice must work — the input's value is cleared on
     change for exactly this reason, and a reader re-picking a corrected file is
     the ordinary case, not an edge one. */
  it('accepts the same filename twice as two rows', () => {
    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan.mac')]);
    choose([file('scan.mac')]);
    expect(screen.getAllByText('scan.mac')).toHaveLength(2);
  });
});

describe('recording a staged file as a source', () => {
  it('sends the browser metadata, a null digest when none was computed, and no path', async () => {
    // Typed from the component's own prop, so the assertions below read real
    // field names rather than casting an `unknown` and hoping.
    type RecordInput = Parameters<ComponentProps<typeof ImportFileStaging>['onRecord']>[0];
    const onRecord = vi.fn((_input: RecordInput): Promise<void> => Promise.resolve());
    render(<ImportFileStaging onRecord={onRecord} />);
    choose([file('run_log.txt', 'abc', 'text/plain')]);

    fireEvent.click(screen.getByRole('button', { name: 'Record as source' }));

    await waitFor(() => expect(onRecord).toHaveBeenCalledTimes(1));
    const sent = onRecord.mock.calls[0][0];
    expect(sent.filename).toBe('run_log.txt');
    expect(sent.mediaType).toBe('text/plain');
    expect(sent.sizeBytes).toBe(3);
    // NOT an empty string and NOT a fabricated digest: the route accepts an
    // entry without one, and inventing a checksum is the §5 violation this
    // whole component is careful about.
    expect(sent.sha256).toBeNull();
    /* The reference says ISAAC does not know where the file is. A browser does
       not disclose a local path, so any confident-looking pointer here would be
       one that points nowhere. */
    expect(sent.reference).toBe(
      'Chosen in the browser; its location was not disclosed to ISAAC',
    );
    expect(String(sent.reference)).not.toContain('run_log.txt');

    expect(await screen.findByText('Recorded as a source')).toBeInTheDocument();
  });

  /* NEGATIVE CONTROL. A refusal must be reported as a refusal — the row must
     not read "Recorded as a source" for something that was not recorded. */
  it('reports a refusal instead of claiming the source landed', async () => {
    const onRecord = vi.fn(async () => {
      throw new Error('too_many_sources');
    });
    render(<ImportFileStaging onRecord={onRecord} />);
    choose([file('x.mac')]);

    fireEvent.click(screen.getByRole('button', { name: 'Record as source' }));

    expect(await screen.findByText('Not recorded')).toBeInTheDocument();
    expect(screen.getByText('too_many_sources')).toBeInTheDocument();
    expect(screen.queryByText('Recorded as a source')).toBeNull();
  });
});

describe('the checksum', () => {
  /* It is OPT-IN because computing it is the only thing here that reads the
     file. Asserted so a later "helpful" change to compute on selection fails:
     that would make the panel's own default claim false for every row, and
     would pull a raw dataset into the tab nobody asked to read. */
  it('is not computed until it is asked for', () => {
    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan.mac')]);
    expect(screen.getByRole('button', { name: 'Compute checksum' })).toBeInTheDocument();
    expect(screen.queryByText(/sha256/)).toBeNull();
    expect(screen.queryByText(/checksum computed in your browser/)).toBeNull();
  });

  /*
   * MEASURED, NOT ASSUMED: this jsdom has `crypto.subtle` but NO
   * `File.prototype.arrayBuffer` (probed 2026-09-15 — `subtle` is an object,
   * `arrayBuffer` is `undefined`). So the graceful-degradation branch is the
   * one that runs here by default, and it is a REAL branch rather than a test
   * artifact: `crypto.subtle` is genuinely absent on an insecure non-localhost
   * origin. Both paths are therefore asserted, and the success path supplies
   * the missing method rather than stubbing the digest — stubbing the thing
   * under test would confirm any implementation, including an inert one.
   */
  it('says so honestly when the browser cannot compute one, and invents nothing', async () => {
    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan.mac', 'synthetic bytes')]);

    fireEvent.click(screen.getByRole('button', { name: 'Compute checksum' }));

    expect(
      await screen.findByText(/The checksum could not be computed in this browser/),
    ).toBeInTheDocument();
    // No digest is fabricated, and the file stays recordable without one.
    expect(screen.queryByText(/^sha256 /)).toBeNull();
    expect(screen.getByRole('button', { name: 'Record as source' })).toBeEnabled();
  });

  it('computes in the browser and never calls the result verified', async () => {
    // Supply the ONE method jsdom lacks. The digest itself is still computed by
    // the component, through the real `crypto.subtle`, over the real bytes.
    const bytes = new TextEncoder().encode('synthetic bytes');
    Object.defineProperty(File.prototype, 'arrayBuffer', {
      configurable: true,
      writable: true,
      value: async function arrayBuffer() {
        return bytes.buffer.slice(0);
      },
    });

    render(<ImportFileStaging onRecord={async () => {}} />);
    choose([file('scan.mac', 'synthetic bytes')]);

    fireEvent.click(screen.getByRole('button', { name: 'Compute checksum' }));

    const digest = await screen.findByText(/^sha256 [0-9a-f]{16}…$/);
    expect(digest).toBeInTheDocument();
    expect(screen.getByText(/checksum computed in your browser/)).toBeInTheDocument();

    // It is the REAL SHA-256 of those bytes, not a placeholder: compared
    // against an independently computed digest rather than against itself.
    const expected = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    )
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    expect(digest.getAttribute('title')).toBe(expected);

    Reflect.deleteProperty(File.prototype, 'arrayBuffer');

    /* THE CLAIM THAT MUST NEVER APPEAR. The route's own description says the
       digest is checked for SHAPE only and is never computed server-side, and
       that no surface may call it verified, checked or matched. A digest
       computed in this tab is still the caller's claim about bytes the server
       never saw. */
    const shown = document.body.textContent ?? '';
    for (const banned of [/\bverified\b/i, /\bchecked against\b/i, /\bmatches the file\b/i, /\bconfirmed\b/i]) {
      expect(shown).not.toMatch(banned);
    }
  });
});

describe('formatBytes', () => {
  it('reads bytes, KB and MB, and refuses to guess at a bad number', () => {
    expect(formatBytes(1)).toBe('1 byte');
    expect(formatBytes(812)).toBe('812 bytes');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
    expect(formatBytes(Number.NaN)).toBe('unknown size');
    expect(formatBytes(-1)).toBe('unknown size');
  });
});
