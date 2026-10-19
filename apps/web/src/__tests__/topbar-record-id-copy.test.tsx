/*
 * THE RECORD TOP BAR'S ID CONTROL (2026-10-12 clutter audit; corrected in review
 * 2026-10-18). The bar used to print the full ULID — or a filename built around it —
 * in mono beside the record's name. It is now a compact control that shows the id
 * head…tail and copies the id.
 *
 * The review finding this file exists for: the first version copied the whole
 * DISPLAY string, so the clipboard held "draft · <ULID>" on Complete/Export and
 * "<ULID>.evidence.json" on an exported Evidence screen. Each case below is a real
 * `filename` a record surface passes.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TopBar, abbreviateId } from '../components/TopBar';

const ID = '01M5751MVDAWN5AHAME3D626VE';

function renderBar(filename: string) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="record" title="Zn K-edge — calibration foil (synthetic)" filename={filename} />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('record top bar · the id control copies the record id and nothing else', () => {
  it.each([
    ['a bare id (Review Record)', ID],
    ['a draft (Complete, Export)', `draft · ${ID}`],
    ['an exported record file', `${ID}.json`],
    ['an exported evidence sidecar', `${ID}.evidence.json`],
  ])('%s: copies exactly the ULID', async (_what, filename) => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    renderBar(filename);
    const button = screen.getByRole('button', { name: `Copy Record ID ${ID}` });
    // Visible text is the id head…tail, never the whole string.
    expect(button.textContent).toBe(abbreviateId(ID));
    await act(async () => {
      fireEvent.click(button);
    });
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(ID);
  });

  it('announces through a status region that exists BEFORE the press', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const { container } = renderBar(`draft · ${ID}`);
    const region = container.querySelector('.record-file [role="status"]');
    expect(region, 'the status region must be mounted with the control').not.toBeNull();
    expect(region!.textContent).toBe('');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: `Copy Record ID ${ID}` }));
    });
    // The SAME node now carries the outcome — a region inserted with its text is
    // not reliably announced.
    expect(container.querySelector('.record-file [role="status"]')).toBe(region);
    expect(region!.textContent).toMatch(/copied/i);
  });

  it('MUTATION-GUARDED — when copying fails, the full id is revealed as text, not left in a tooltip', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
    const { container } = renderBar(`${ID}.evidence.json`);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: `Copy Record ID ${ID}` }));
    });
    expect(container.querySelector('.record-file-full')?.textContent).toBe(ID);
    const status = container.querySelector('.record-file [role="status"]')!.textContent ?? '';
    expect(status).toMatch(/did not work/i);
    expect(status).not.toMatch(/tooltip/i);
  });

  it('renders a filename with no id in it as plain text, with no control', () => {
    const { container } = renderBar('synthetic_scan_0001.xdi');
    expect(screen.queryByRole('button', { name: /Copy Record ID/ })).toBeNull();
    expect(container.querySelector('.record-file')?.textContent).toBe('synthetic_scan_0001.xdi');
  });
});
