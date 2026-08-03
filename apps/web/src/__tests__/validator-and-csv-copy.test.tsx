/*
 * R1b (minor) · three small copy/label defects on the two file-reading surfaces.
 *
 *  1. `components/RecordValidator.tsx`'s scope note opened "Synthetic-mode
 *     validator:". "Synthetic-mode" is the name of a runtime configuration flag,
 *     not something a scientist reading a validator needs — and it says nothing
 *     about what the validator does. The TRUE half of the sentence (checked in
 *     memory, discarded, never uploaded to a model / indexed / stored — verified
 *     against `routes.py::post_validate_record`, which never writes and logs
 *     outcome only) is what earns its place and stays.
 *
 *  2. `components/CsvReconcilePanel.tsx`'s warning banner said "Synthetic or
 *     public data only". Same problem, plus it made the reader responsible for a
 *     word the product never defines for them. The instruction — do not upload
 *     real or private data — is the part that matters and is kept.
 *
 *  3. `Open Record` in that panel navigated to `ROUTES.complete` — Complete
 *     Missing Fields, a different screen from the record. A label that names the
 *     wrong destination is a small lie that costs a reader a wrong click, and it
 *     was invisible because the callback's NAME (`onOpenRecord`) agreed with the
 *     label rather than with the call site.
 *
 * This file asserts the copy, and — for (3) — that the label and the destination
 * are pinned to each other at the one call site, so the two cannot drift apart
 * again the way they already did.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RecordValidator } from '../components/RecordValidator';
import { CsvReconcilePanel } from '../components/CsvReconcilePanel';
import { LABELS } from '../lib/labels';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/** Comments stripped: the note recording the old prop name is not the old prop
 *  name. Same trade as the sibling honesty guards. */
const source = (path: string) =>
  readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');

describe('R1b · the validator scope note drops the mode jargon and keeps the true claim', () => {
  it('no longer opens with a runtime-flag name', () => {
    const { container } = render(<RecordValidator />);
    const note = container.querySelector('.rec-val-scope-note');
    expect(note).not.toBeNull();
    expect(note!.textContent ?? '').not.toMatch(/synthetic/i);
  });

  it('keeps both verified guarantees', () => {
    const { container } = render(<RecordValidator />);
    const note = container.querySelector('.rec-val-scope-note')!;
    expect(note.textContent ?? '').toMatch(/checked in memory and discarded/i);
    expect(note.textContent ?? '').toMatch(
      /nothing here is uploaded to a model, indexed, or stored/i,
    );
  });
});

describe('R1b · the CSV panel warning states the instruction, not a mode name', () => {
  function renderPanel(onGoToComplete?: () => void) {
    return render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CsvReconcilePanel experimentId="demo" version="1" onGoToComplete={onGoToComplete} />
      </MemoryRouter>,
    );
  }

  it('drops the mode word from the warning banner', () => {
    const { container } = renderPanel();
    const warn = container.querySelector('.csv-recon-banner-warn');
    expect(warn).not.toBeNull();
    expect(warn!.textContent ?? '').not.toMatch(/synthetic/i);
  });

  it('still tells the reader the one thing they must not do', () => {
    const { container } = renderPanel();
    const warn = container.querySelector('.csv-recon-banner-warn')!;
    expect(warn.textContent ?? '').toMatch(/do not upload real or private/i);
  });
});

describe('R1b · the panel action names the screen it actually navigates to', () => {
  it('the label is the Complete Missing Fields screen name, not "Open Record"', () => {
    const panel = source('components/CsvReconcilePanel.tsx');
    expect(panel).not.toMatch(/>\s*Open Record\s*</);
    // Pinned to the label module rather than duplicated, so a rename of the
    // screen carries the button with it.
    expect(panel).toMatch(/LABELS\.screenComplete/);
    expect(LABELS.screenComplete).toBe('Complete Missing Fields');
  });

  it('the callback name agrees with the destination at the one call site', () => {
    // The old name (`onOpenRecord`) agreed with the WRONG label, which is how the
    // mismatch survived review. Renaming it is what keeps the two honest.
    const explorer = source('screens/EvidenceExplorer.tsx');
    expect(explorer).toMatch(/onGoToComplete=\{\(\) => navigate\(ROUTES\.complete\(id\)\)\}/);
    expect(source('components/CsvReconcilePanel.tsx')).not.toMatch(/onOpenRecord/);
  });
});
