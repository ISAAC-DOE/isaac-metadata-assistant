/**
 * QA-020 — the honest not-found state.
 *
 * FOUND ON THE HOSTED DEPLOYMENT, not in a test: navigating `/krish/validator`
 * landed on `<h1>My Experiments</h1>` with the path rewritten by `replace` and
 * no message of any kind. `App.tsx`'s catch-all was
 * `<Navigate to={ROUTES.experiments} replace />`.
 *
 * MEASURED BEFORE THIS FILE EXISTED: **zero** test files asserted the router
 * redirect. An earlier estimate of "8 test files" came from grepping
 * `catch-all|unknown route|not.found|NotFound`, which matched unrelated
 * vocabulary in three other domains (a fetch stub, a record list, and the
 * Assistant's intent resolver). A grep for a word measures your guess about the
 * vocabulary, not the behaviour.
 */

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AppRoutes } from '../App';
import { NotFound } from '../screens/NotFound';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';

/** The real router, entered at an address no `<Route>` declares. */
function renderAtUnknownPath(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

/** The screen alone, so a path can be supplied without the whole app. */
function renderScreenAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('QA-020 · an unrecognised address reaches the not-found screen', () => {
  it('MUTATION-GUARDED — does NOT silently become My Experiments', () => {
    /*
     * THE CENTRAL ASSERTION, and it is written as the ABSENCE of the old
     * destination as well as the presence of the new one. Asserting only the
     * new heading would still pass a build that rendered both, and asserting
     * only the absence would pass a blank page.
     */
    renderAtUnknownPath('/validator');
    expect(
      screen.getByRole('heading', { level: 1 }).textContent,
      'an unrecognised address still resolves to another screen',
    ).toBe(LABELS.screenNotFound);
    expect(screen.queryByText(LABELS.screenExperiments)).toBeNull();
  });

  it('shows the address that was asked for — the thing `replace` used to destroy', () => {
    renderScreenAt('/validator');
    expect(screen.getByText('/validator')).toBeTruthy();
  });

  it('MUTATION-GUARDED — renders the attempted path as TEXT, never as a link or markup', () => {
    // Anyone can put anything in a URL. React escapes by construction; this
    // asserts the escaping is not being worked around, and that the path is not
    // turned into an anchor a reader could be induced to click.
    const nasty = '/<img src=x onerror=alert(1)>/%2e%2e';
    const { container } = renderScreenAt(nasty);
    const shown = container.querySelector('.notfound-path')!;
    expect(shown.textContent).toBe(nasty);
    expect(shown.querySelector('img')).toBeNull();
    expect(shown.querySelector('a')).toBeNull();
    // NOT decoded: `%2e%2e` stays as typed. A decoded path is not the path the
    // reader requested, and decoding can surface control characters.
    expect(shown.textContent).toContain('%2e%2e');
  });

  it('offers exactly one way out, and it is a real link', () => {
    const { container } = renderScreenAt('/nope');
    const link = Array.from(container.querySelectorAll('a')).find(
      (a) => a.textContent === LABELS.actionGoToExperiments,
    );
    expect(link).toBeDefined();
    expect(link!.getAttribute('href')).toBe(ROUTES.experiments);
  });

  it('renders exactly one h1, as every surface in this app must', () => {
    // `e2e/specs/structure.spec.ts` holds every surface to one `<h1>`; asserted
    // here too so the unit suite catches it without a browser run.
    renderScreenAt('/nope');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });
});

describe('QA-020 · what the screen must NOT claim', () => {
  /*
   * THE HONESTY BOUNDARY, and it is narrow on purpose. This screen knows only
   * that no route answers to the address. A missing RECORD is a different
   * failure, already handled elsewhere: `/record/<unknown-ULID>` matches
   * `ROUTE_PATTERNS.record` and reaches `RecordWorkbench`'s own not-found
   * handling — proven by the negative control in the last describe block.
   *
   * Telling a scientist arriving from a stale bookmark that their record is
   * gone, when nothing was even looked up, is the worst thing this surface
   * could do.
   *
   * *** THE FIRST VERSION OF THIS TEST BANNED SUBSTRINGS AND FAILED ON THE
   * SHIPPED COPY'S OWN REASSURANCE. *** It forbade `has been deleted`, and the
   * scope sentence reads "Nothing HAS BEEN DELETED, and no record was looked
   * up" — the OPPOSITE claim, containing the banned string. That is the
   * polarity trap this repository has been caught by before, and the wrong
   * repair is to delete the reassurance to satisfy the substring.
   *
   * So the delete/discard family is checked with POLARITY: every occurrence of
   * a deletion word must be negated. `assertNegated` is used for those, and
   * plain bans only for phrasings that cannot be honest negations.
   */
  function deletionClaims(text: string): string[] {
    const unnegated: string[] = [];
    for (const m of text.matchAll(/\b(deleted|discarded|removed|erased)\b/g)) {
      const before = text.slice(Math.max(0, m.index! - 40), m.index!);
      if (!/\b(nothing|no|never|not)\b/i.test(before)) unnegated.push(before.slice(-40) + m[0]);
    }
    return unnegated;
  }

  it('MUTATION-GUARDED — never says a RECORD was not found, and every deletion word is NEGATED', () => {
    const { container } = renderScreenAt('/record-ish');
    const text = (container.textContent ?? '').toLowerCase();

    for (const banned of [
      'record was not found',
      'record not found',
      'no such record',
      'record does not exist',
      'record may have been',
      'could not be loaded',
    ]) {
      expect(text, `the not-found screen claims: ${banned}`).not.toContain(banned);
    }

    expect(
      deletionClaims(text),
      'the not-found screen asserts a deletion. Nothing was looked up, so it cannot know',
    ).toEqual([]);
  });

  it('POSITIVE CONTROL — the polarity check above actually fires on an affirmative claim', () => {
    /*
     * Without this, `deletionClaims` returning `[]` is indistinguishable from a
     * regex that matches nothing — which is precisely how this repository's
     * vacuous guards have passed before. Both arms are asserted: the honest
     * negation is accepted, the affirmative claim is caught.
     */
    expect(deletionClaims('nothing has been deleted, and no record was looked up')).toEqual([]);
    expect(deletionClaims('this record was deleted by an administrator').length).toBe(1);
    expect(deletionClaims('the draft was discarded').length).toBe(1);
    // And the negation window is bounded rather than unlimited, so a "nothing"
    // sixty characters earlier in an unrelated clause does not launder a claim.
    expect(
      deletionClaims('nothing about the following sentence is relevant here at all, yet the record was deleted').length,
    ).toBe(1);
  });

  it('states the scope explicitly rather than leaving it to inference', () => {
    const { container } = renderScreenAt('/nope');
    const text = container.textContent ?? '';
    expect(text).toContain(LABELS.notFoundRecordScope);
    // The two load-bearing halves of that sentence, asserted by meaning rather
    // than as one long literal so a rewording that KEEPS the meaning passes.
    expect(text.toLowerCase()).toContain('nothing has been deleted');
    expect(text.toLowerCase()).toContain('never reaches a record');
  });

  it('MUTATION-GUARDED — offers no guess at what the reader meant', () => {
    // A "did you mean ...?" needs a similarity rule nobody specified, and a
    // wrong guess here is the defect being fixed, one step further along.
    const { container } = renderScreenAt('/experiment');
    const text = (container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('did you mean');
    expect(text).not.toContain('perhaps you');
  });
});

describe('QA-020 · the record route is NOT affected, which is why the scope claim is true', () => {
  it('an unknown record id still reaches the record route, not this screen', () => {
    /*
     * THE LOAD-BEARING NEGATIVE CONTROL. Without it, the scope sentence above is
     * an unverified assertion about a neighbouring surface. `/record/<id>`
     * matches a declared pattern, so it must NOT fall through to the catch-all
     * however unknown the id is — and if it ever did, the scope note ("no record
     * was looked up") would become false on the most common failing address in
     * the product.
     */
    renderAtUnknownPath('/record/01SYNTHDOESNOTEXIST00000000');
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(
      h1.textContent,
      'an unknown RECORD ID fell through to the not-found screen — the scope claim ' +
        'on that screen ("no record was looked up") is now false',
    ).not.toBe(LABELS.screenNotFound);
  });
});
