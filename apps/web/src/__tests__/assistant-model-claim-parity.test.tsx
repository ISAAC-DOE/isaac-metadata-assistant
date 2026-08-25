/*
 * ONE claim about a language model, two sites — and the decision that a third
 * site must not exist.
 *
 * WHY THIS FILE EXISTS. `docs/ai-integration-decision-packet.md` §3 (UPDATED
 * 2026-08-19) refuses to put the model-backed assistant seam on any product
 * screen:
 *
 *   "NO PRODUCT SCREEN CONSUMES IT, and that is a decision rather than an
 *    unfinished edge. §9's rule is 'build nothing that implies any of it exists',
 *    and a panel reporting an assistant seam — even one reporting it as
 *    unconfigured — would put a model-backed assistant in front of a scientist as
 *    a thing that is nearly here. The Assistant panel goes on saying 'There is no
 *    language model', which is true of the shipped deterministic Q&A and stays
 *    true."
 *
 * THE LAST SENTENCE WAS FALSE, AND IT IS THE MITIGATION THE DECISION RESTS ON.
 * The panel never said it. Measured on `main` at `b7008b8`:
 *
 *   git grep -in 'language model' b7008b8 -- apps/web/src/components/AssistantPanel.tsx
 *     → exit 1
 *   git grep -ln 'language model' b7008b8 -- apps/web/src/lib
 *     → apps/web/src/lib/assistantCapabilities.ts
 *       apps/web/src/lib/settingsContent.ts
 *
 * THE SECOND COMMAND'S OUTPUT IS CORRECTED IN PLACE, and the correction is the
 * reason it is written out rather than summarised. An earlier revision of this
 * comment recorded that grep as ~~`→ lib/settingsContent.ts`~~ — ONE file. It is
 * TWO, and always was: `assistantCapabilities.ts:43` also matches. Re-measure
 * with the command above rather than trusting this block.
 *
 * The conclusion survives, and the reason it survives is the thing to read. The
 * second hit is a CODE COMMENT — "* language model: the catalog is finite,
 * literal and offline." — so it is invisible to every reader who is not reading
 * the source, and it is not a claim the product makes to anyone. The USER-FACING
 * claim was at `settingsContent.ts:580` and `:587`, two places, both in
 * Settings → AI & Automation behind a tab. But a stated measurement is the whole
 * currency of this file, so a grep whose output is wrong by one file is exactly
 * the error this file exists to make impossible, and it is fixed rather than
 * excused.
 *
 * SO: the screen a scientist types into said nothing about whether a model is
 * involved or where a typed question goes. §3's argument — "a seam report would
 * only imply a model is nearly here, because the reader is already told there is
 * no model" — had a premise the product did not supply.
 *
 * ONE FURTHER SCOPE CORRECTION. It is tempting to write that the claim "lived
 * only in `lib/settingsContent.ts`", and that is false of the APPLICATION. The
 * backend authors the same claim three times in `apps/api/isaac_api/routes.py` —
 * the `TAG_ASSISTANT` tag description (`:216`, "There is no language model: an
 * unsupported question is refused rather than guessed"), and the descriptions of
 * `POST /api/experiments/{id}/assistant/query` (`:14848`) and
 * `POST /api/assistant/memory/query` (`:14988`) — and Settings → API Access
 * renders all three, with `ApiDocs.tsx:534` listing `'no language model'` in
 * `BOUNDARY_CAVEAT_MARKERS` precisely so the caveat cannot be collapsed behind a
 * disclosure. The defensible scope is therefore "in `apps/web/src`", which is
 * also the only tree this file reads.
 *
 * THE DECISION AND ITS MITIGATION ARE PINNED IN ONE FILE ON PURPOSE. Splitting
 * them would let either half drift alone, and each is only defensible while the
 * other holds: a panel that stops making the claim re-opens the gap §3 assumes
 * closed, and a panel that starts reporting the seam breaks the decision the
 * claim is standing in for. §1–§4 hold the claim; §5 holds the decision.
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the claim is on the panel a scientist types into, RENDERED, and is
 *     programmatically attached to the composer input — a disclosure a screen
 *     reader cannot reach is the `voiceSeamUnreported` defect again.
 *  §2 both sites make the SAME sub-claims. Parity is the property that was
 *     missing; a site stating half of it will drift the same way the four upload
 *     sites did (`upload-claim-parity.test.tsx`).
 *  §3 POLARITY. `upload-claim-parity`'s first version passed an inverted
 *     disclosure, so every claim here is checked for its negation as well as its
 *     presence.
 *  §4 neither site implies a provider exists, is connected, or is coming. This is
 *     §6.1's no-fake-`Connected`-state invariant applied to text, and it ratchets
 *     over ATTRIBUTES too — `connect-your-agent.test.tsx`'s precedent, because a
 *     `data-state="connected"` is a claim a reader's tooling can meet.
 *  §5 §3's decision, mechanically: no product surface calls the assistant seam,
 *     and the one capability-report consumer reads only the transcription seam.
 *  §6 negative controls. Every scan and every polarity check is proven on input
 *     that must fail it, so a pattern narrowed until it detects nothing fails
 *     here rather than going quiet.
 *
 * WHAT IT CANNOT CATCH, stated plainly.
 *
 *  · It is a parity-and-absence ratchet, not a detector for "is this paragraph
 *    true". A novel phrasing that implies a model is arriving — "the assistant is
 *    getting smarter", "grounded answers today, more soon" — satisfies every
 *    pattern here. A human reviewer remains the backstop for newly written model
 *    claims.
 *  · It reads `apps/web/src` only. Backend-served copy is invisible to it, and
 *    the population is THREE sites rather than the two §2 measures parity over —
 *    a distinction worth stating, because "both sites" reads as "all sites":
 *      – `apps/api/isaac_api/routes.py` — the refusal body
 *        `POST /api/assistant/ask` returns, plus the tag and operation
 *        descriptions the Endpoint Explorer renders (`:216`, `:14848`, `:14988`).
 *      – `apps/api/isaac_api/providers/assistant.py:177-181`, the THIRD site and
 *        the one most easily missed, because it is neither this bundle nor a
 *        route description. `UnconfiguredAssistantProvider.status_reason()`
 *        returns near-identical copy — "No language model is configured. Nothing
 *        typed here is sent to a model provider, because there is no model
 *        provider." — which is the panel's two clauses almost word for word. It
 *        is outside this guard's reach entirely: nothing here would notice it
 *        drifting, being inverted, or being deleted.
 *  · IT DELIBERATELY DOES NOT TREAT THE ENDPOINT EXPLORER AS A VIOLATION, and
 *    that is a judgement rather than an oversight. Settings → API Access lists
 *    every operation this application declares, `POST /api/assistant/ask`
 *    included, from `create_app().openapi()`. A scientist can therefore read that
 *    the operation exists — and read, in the same description, that it answers
 *    `501` in every deployment. §3's concern is a product AFFORDANCE that offers a
 *    model-backed answer; a complete API reference that documents the operation
 *    and its refusal is the opposite act. Narrowing the reference to hide one
 *    operation would make it lie about the surface it claims to enumerate. §5
 *    therefore scans `components/` and `screens/` for a CALL, not the fixture
 *    that transcribes the OpenAPI document.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import { AssistantPanel } from '../components/AssistantPanel';
import { ASSISTANT_COMPOSER_HELPER, ASSISTANT_NO_MODEL_CLAIM } from '../lib/assistant';
import { CAPABILITIES_BOUNDARY } from '../lib/assistantCapabilities';
import { settingsConcepts } from '../lib/settingsContent';
import type { AssistantMessage } from '../lib/types';

afterEach(cleanup);

/** The minimum a mount needs. `reply` is required by the props type; its content
 *  is irrelevant here — every assertion below is about the dock, not the answer. */
const REPLY: AssistantMessage = { text: 'A grounded answer.', answeredFrom: 'schema' };

function mountPanel(extra: Record<string, unknown> = {}) {
  return render(<AssistantPanel reply={REPLY} prompts={[]} {...extra} />);
}

// --- locating and reading the real sources -----------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a
 *  file one. Duplicated from `upload-claim-parity.test.tsx` rather than exported,
 *  so no file can silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

function rawSource(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8');
}

/** Every `.ts`/`.tsx` file under one of `SRC_DIR`'s subdirectories, recursively. */
function sourceFilesUnder(relDir: string): string[] {
  const out: string[] = [];
  const walk = (dir: string, rel: string) => {
    for (const entry of readdirSync(dir).sort()) {
      const abs = join(dir, entry);
      const next = rel === '' ? entry : `${rel}/${entry}`;
      if (statSync(abs).isDirectory()) {
        walk(abs, next);
      } else if (/\.tsx?$/.test(entry)) {
        out.push(next);
      }
    }
  };
  walk(join(SRC_DIR, relDir), '');
  return out;
}

/** Every `.ts`/`.tsx` file in the whole bundle, as a `SRC_DIR`-relative path. */
function allSourceFiles(): string[] {
  return sourceFilesUnder('.');
}

/*
 * THE CONCATENATION NORMALISER, AND EXACTLY WHAT IT CAN AND CANNOT SEE.
 *
 * A literal scan for `assistant/ask` is defeated by spelling the path in pieces —
 * `'/assistant' + '/' + 'ask'` — and that is not hypothetical: it was MEASURED
 * against the previous version of §5, sitting in a component, with all 29 tests
 * green. Joining adjacent string literals across `+` collapses it back into the
 * one token the pattern is looking for.
 *
 * WHAT IT CATCHES: any number of adjacent quoted fragments joined by `+`, in any
 * of the three quote styles, across line breaks (`\s*` spans newlines), which is
 * how a human actually writes a path they are splitting up.
 *
 * WHAT IT DOES NOT CATCH, stated rather than implied, because a guard that
 * overstates its reach is worse than a narrow one that is honest:
 *   · a template literal with an interpolation — `` `/assistant${sep}ask` ``;
 *   · a path assembled from an array — `['assistant', 'ask'].join('/')`;
 *   · fragments held in named identifiers — `const A = 'assistant'; A + '/ask'`;
 *   · anything computed — `String.fromCharCode(...)`, an encoded constant, a
 *     value arriving from the server.
 * None of those is reachable by TEXT MATCHING at all, so no amount of widening
 * this function reaches them. They are the reason §5's real strength is the
 * ABSENCE OF A CLIENT METHOD (enforcement by non-implementation, checked below)
 * rather than this scan, and the reason a human reviewer stays the backstop.
 *
 * It runs over the WHOLE bundle and produced ZERO false positives when this was
 * written: 309 `.ts`/`.tsx` files, and the only three matches — before or after
 * normalisation — are the three allowlisted below. A future false positive is a
 * cheap failure (a comment or a fixture) and a false negative is the expensive
 * one, so the collapse is deliberately eager.
 */
function collapseConcatenatedStrings(text: string): string {
  return text.replace(/['"`]\s*\+\s*['"`]/g, '');
}

/** True if `source` names the assistant-seam operation, literally or in pieces. */
function namesTheSeam(source: string): boolean {
  return /assistant\/ask/.test(collapseConcatenatedStrings(source));
}

/*
 * Apostrophes are normalized before every comparison, and the reason is
 * concrete: this bundle's copy uses the typographic `’` (`transcriptCaptureContent.ts`
 * writes "this tab’s memory") while `settingsContent.ts`'s model claim sits in a
 * double-quoted string and uses the straight `'`. Two sites making the same claim
 * in the two idiomatic quote styles are still the same claim, and a parity guard
 * that failed on the punctuation would be pressure to change correct copy.
 */
function norm(text: string): string {
  return text.replace(/[‘’]/g, "'").replace(/\s+/g, ' ').trim().toLowerCase();
}

// --- the two sites, as the text a reader actually meets -----------------------

const SETTINGS_FACTS = {
  dataRegime: 'synthetic-only',
  persistence: 'ephemeral',
  recordSchemaVersion: '1.05',
};

/** Settings → AI & Automation → `no-external-model-calls`, summary + detail. */
function settingsModelClaim(): string {
  const found = settingsConcepts(SETTINGS_FACTS).find((c) => c.id === 'no-external-model-calls');
  if (!found) throw new Error('no such concept: no-external-model-calls');
  return `${found.heading} ${found.summary} ${found.detail}`;
}

/**
 * The Assistant panel's disclosure, RENDERED — never read off the constant.
 *
 * Reading `ASSISTANT_NO_MODEL_CLAIM` would pass for a string that is exported
 * and never mounted, which is exactly the failure mode `upload-claim-parity`
 * names ("copy that exists in the module and is not shown"). The panel is
 * rendered with the minimum props every mounting screen supplies.
 */
function panelDisclosureText(): string {
  mountPanel();
  const node = document.querySelector('.assistant-no-model');
  if (node === null) throw new Error('the panel renders no no-model disclosure');
  return node.textContent ?? '';
}

const SITES: [string, () => string][] = [
  ['the Assistant panel, beneath the composer', panelDisclosureText],
  ['Settings → AI & Automation → no-external-model-calls', settingsModelClaim],
];

/*
 * FOUR FACTS, TWO OWNERS — and parity is measured only over the two that BOTH
 * sites must make.
 *
 * The temptation is to require every site to recite all four, and that is the
 * inverse of `upload-claim-parity.test.tsx`'s actual lesson. The defect there was
 * three sites making a claim BROADER than each could defend ("no file is read,
 * parsed, or inspected", asserted one tab away from a validator that reads files).
 * Settings speaks for the whole application; the panel speaks for the panel.
 *
 *  · no model in this build        BOTH. Without it, "nothing is sent to a
 *                                 provider" reads as a routing detail rather
 *                                 than as an absence.
 *  · nothing typed reaches a       BOTH. The question a scientist actually has,
 *    model provider               and the one that becomes false the day
 *                                 capability B ships.
 *  · a bounded deterministic set   SETTINGS, and on the panel by its own
 *    over the deployment's data   controls — see PANEL_OWNED_ELSEWHERE.
 *  · refuses rather than guesses   likewise. §6.4's no-guessing rule.
 */
const SUB_CLAIMS: [string, RegExp][] = [
  ['there is no language model in this build', /there is no language model in this build/],
  ['nothing typed is sent to a model provider', /is sent to a model provider/],
];

/*
 * The other two facts, and the panel control that owns each.
 *
 * They are NOT absent from the panel — they are stated where they belong, and
 * this array is what stops "the panel does not repeat them" from quietly becoming
 * "the panel does not say them". `CAPABILITIES_BOUNDARY` sits inside the "What
 * Can I Ask?" popover, which is a control of this panel rather than another
 * screen; that placement is the panel's own and is checked by
 * `assistant-capabilities.test.tsx`, so what is asserted here is only that the
 * constants still carry the claims.
 */
const PANEL_OWNED_ELSEWHERE: [string, string, RegExp][] = [
  [
    'the grounded scopes, beneath the composer',
    ASSISTANT_COMPOSER_HELPER,
    /ask about this record, its evidence, workflow, export readiness/i,
  ],
  [
    'the bounded set, in "What Can I Ask?"',
    CAPABILITIES_BOUNDARY,
    /these families are the whole set/i,
  ],
  [
    'refused rather than guessed, in "What Can I Ask?"',
    CAPABILITIES_BOUNDARY,
    /refused, not guessed/i,
  ],
];

// --- §1 the claim is where the question arises, and it is announced ----------

describe('§1 · the disclosure is on the panel a scientist types into', () => {
  it('renders beneath the composer, in the dock, not behind a disclosure control', () => {
    mountPanel();
    const foot = document.querySelector('.assistant-foot');
    const claim = document.querySelector('.assistant-no-model');
    expect(claim).not.toBeNull();
    // In the sticky dock, so it is visible without scrolling the transcript.
    expect(foot?.contains(claim as Node)).toBe(true);
    // NOT inside a <details>. §3's own lesson (`voiceSeamUnreported`) is that a
    // disclosure conditional on being opened is not a disclosure.
    expect(claim?.closest('details')).toBeNull();
    expect(claim?.getAttribute('hidden')).toBeNull();
  });

  it('is the composer input’s accessible description, together with the scope helper', () => {
    mountPanel();
    const input = screen.getByLabelText('Ask the assistant a question');
    const described = (input.getAttribute('aria-describedby') ?? '').split(/\s+/).filter(Boolean);
    expect(described.length).toBe(2);
    // Neither id may dangle — a description pointing at nothing is silence.
    const texts = described.map((id) => {
      const el = document.getElementById(id);
      expect(el, `dangling aria-describedby: ${id}`).not.toBeNull();
      return el?.textContent ?? '';
    });
    // The disclosure is one of the two, and the scope helper is the other.
    expect(texts.some((t) => norm(t) === norm(ASSISTANT_NO_MODEL_CLAIM))).toBe(true);
    expect(texts.some((t) => /ask about this record/i.test(t))).toBe(true);
  });

  it('the exported constant and the rendered text are the same string', () => {
    // A drifting constant would make the other guards here read the module while
    // the reader reads something else.
    expect(norm(panelDisclosureText())).toBe(norm(ASSISTANT_NO_MODEL_CLAIM));
  });

  it('renders on every mount, with no availability, context or agent props', () => {
    // The panel takes ~15 optional props and mounts on five screens. A
    // disclosure that appeared only on the record surfaces would be absent from
    // Project Memory, which is where a reader is most likely to mistake the
    // assistant for a chatbot.
    mountPanel({ queryScope: 'memory' });
    expect(document.querySelectorAll('.assistant-no-model').length).toBe(1);
  });
});

// --- §2 parity ---------------------------------------------------------------

describe('§2 · both sites make the same sub-claims', () => {
  for (const [site, read] of SITES) {
    it.each(SUB_CLAIMS)(`${site} states: %s`, (_what, pattern) => {
      expect(norm(read())).toMatch(pattern);
    });
  }

  it.each(PANEL_OWNED_ELSEWHERE)(
    'the panel still carries, elsewhere: %s',
    (_where, text, pattern) => {
      // The two clauses the panel deliberately does NOT restate in the dock. If a
      // later slice deletes one of these, the panel stops saying it ANYWHERE and
      // the shortening above stops being justified — which is the failure this
      // array exists to convert into a red test rather than a stale comment.
      expect(norm(text)).toMatch(pattern);
    },
  );

  it('Settings, which speaks for the application, still states all four', () => {
    const text = norm(settingsModelClaim());
    for (const [, pattern] of SUB_CLAIMS) expect(text).toMatch(pattern);
    expect(text).toMatch(/bounded, deterministic catalog over the deployment's own data/);
    expect(text).toMatch(/refuses anything outside it rather than guessing/);
  });

  it('the panel does NOT restate the two Settings owns, so the dock stays short', () => {
    /*
     * Not a style rule — it is a length budget for a sticky dock at 11px inside a
     * content-sized rail.
     *
     * THE FIGURE IS MEASURED HERE RATHER THAN WRITTEN DOWN, and that is a
     * correction. An earlier revision of this comment stated the full paragraph
     * was ~~244 characters~~ and the kept pair 92. The 92 is exact. The 244 was
     * NOT reproducible from anything committed: Settings' real paragraph
     * (`settingsContent.ts:587`) is 272, and a panel-scoped reconstruction of the
     * four clauses comes to 238. 244 described a draft that no longer exists in
     * the tree, stated as fact in the one file whose subject is that a stated
     * measurement must be true.
     *
     * So both numbers are now computed from the committed strings on every run.
     * They cannot go stale, and a reader can reproduce them by reading this test.
     */
    const claim = norm(ASSISTANT_NO_MODEL_CLAIM);
    const settings = settingsModelClaim();
    expect(claim).not.toMatch(/bounded, deterministic catalog/);

    // The kept pair, exact — the raw constant, not the normalised copy.
    expect(ASSISTANT_NO_MODEL_CLAIM.length).toBe(92);
    // Settings' detail paragraph, which is what the panel declines to restate.
    const detail = settingsConcepts(SETTINGS_FACTS).find(
      (c) => c.id === 'no-external-model-calls',
    )!.detail;
    expect(detail.length).toBe(272);
    // The budget, as a relation rather than a magic number: the dock carries
    // comfortably under half of what Settings does.
    expect(ASSISTANT_NO_MODEL_CLAIM.length).toBeLessThan(detail.length / 2);
    expect(claim.length).toBeLessThan(140);
    expect(settings.length).toBeGreaterThan(claim.length);
  });
});

// --- §3 polarity ------------------------------------------------------------

/*
 * The shapes an inversion actually takes. Each is the same sentence with the
 * negation removed or reversed, and each would satisfy §2's substring patterns on
 * its own — `/is sent to a model provider/` matches "your question is sent to a
 * model provider" perfectly. §2 proves the words are there; §3 proves they still
 * mean the same thing, and §6 proves this array can see an inversion at all.
 *
 * Module scope rather than inside §3's `describe`, so §6's negative control tests
 * THIS array and not a second copy of it that could be narrowed independently.
 */
const INVERSIONS: RegExp[] = [
  /there is a language model in this build/,
  /(?:what|everything) you type (?:here )?is sent to a model provider/,
];

describe('§3 · polarity — an inverted disclosure must not pass', () => {
  for (const [site, read] of SITES) {
    it(`${site} is not inverted`, () => {
      const text = norm(read());
      for (const bad of INVERSIONS) expect(text).not.toMatch(bad);
      // The "nothing ... is sent" clause must carry its own negation WITHIN the
      // sentence that mentions the provider — not two sentences away, where a
      // later edit could delete one and leave the other reading as an assertion.
      const sentence = text
        .split(/(?<=\.)\s+/)
        .find((s) => /is sent to a model provider/.test(s));
      expect(sentence, 'no sentence mentions a model provider').toBeDefined();
      expect(sentence).toMatch(/\bnothing\b/);
    });
  }
});

// --- §4 no site implies a provider exists ------------------------------------

/*
 * The vocabulary of a provider that is there but momentarily out of reach.
 *
 * It is `providers/refusal.py`'s `_FORBIDDEN_MESSAGE_SUBSTRINGS`, extended with
 * the four forward-looking words a UI reaches for and a backend refusal never
 * would. The backend list is enforced at construction time on every
 * `ProviderRefusal`; nothing enforced it on the copy in this bundle, which is
 * where a "coming soon" would actually be written.
 */
const IMPLIES_A_PROVIDER: string[] = [
  'connected',
  'connecting',
  'reconnect',
  'temporarily',
  'try again',
  'retry',
  'timed out',
  'rate limit',
  'quota',
  'coming soon',
  'not yet available',
  // Added here, not in the backend list: a refusal body has no reason to promise.
  'coming to',
  'will be available',
  'once configured',
  'in a future',
];

describe('§4 · neither site implies a provider exists, is connected, or is coming', () => {
  it.each(SITES)('%s uses none of the provider-implying words', (_site, read) => {
    const text = norm(read());
    for (const word of IMPLIES_A_PROVIDER) {
      expect(text, `implies a provider: ${word}`).not.toContain(word);
    }
  });

  it('the rendered panel carries no connection state in TEXT or in any ATTRIBUTE', () => {
    /*
     * ATTRIBUTES TOO, and that is `connect-your-agent.test.tsx`'s precedent
     * rather than belt-and-braces: §6.1 forbids showing "a connection state the
     * application has not verified", and `data-state="connected"` or
     * `aria-label="Model connected"` is exactly such a state — invisible to a
     * text scan and fully visible to a reader's tooling.
     */
    const { container } = mountPanel();
    expect(norm(container.textContent ?? '')).not.toContain('connected');
    for (const el of Array.from(container.querySelectorAll('*'))) {
      for (const attr of Array.from(el.attributes)) {
        expect(
          attr.value.toLowerCase(),
          `${el.tagName.toLowerCase()}[${attr.name}] claims a connection`,
        ).not.toContain('connected');
      }
    }
  });
});

// --- §5 §3's decision, held mechanically ------------------------------------

/**
 * The product surfaces, kept as a named set because §6 proves the walker reaches
 * them and because the capability-report assertion below is genuinely about
 * screens rather than about the whole bundle.
 */
const PRODUCT_DIRS = ['components', 'screens'] as const;

/*
 * THE SCAN IS THE WHOLE BUNDLE, AGAINST AN ALLOWLIST — and it was two directories
 * until a review measured both ways out.
 *
 * The previous version read `components/` and `screens/` for the literal, plus
 * `lib/api.ts` BY NAME. Both escapes below were measured with all 29 tests green:
 *
 *   (a) `const P = '/api' + '/assistant' + '/' + 'ask';` in `components/RunCard.tsx`
 *       → 29 passed. Closed by `collapseConcatenatedStrings`.
 *   (b) a new `src/lib/assistantSeamClient.ts` holding
 *       `fetch('/api/assistant/ask', …)`, imported and called from
 *       `screens/RecordWorkbench.tsx`
 *       → 29 passed. `lib/` was exempt except for the ONE file named above, so
 *         the client method §5 forbids in `lib/api.ts` could simply be written in
 *         a sibling. Closed by scanning every file and naming the exceptions.
 *
 * (b) is the more instructive of the two: `lib/api.ts` was checked by name, which
 * reads as "the client layer is covered" and actually means "one file is". An
 * allowlist inverts that — a new file is a violation by default, and admitting it
 * is an edit to this array that a reviewer sees.
 *
 * THE ALLOWLIST IS EXACTLY TWO ENTRIES, and the first is the judgement the
 * docstring above defends at length: `test/apiFixtures.ts` TRANSCRIBES the
 * OpenAPI document, `POST /api/assistant/ask` included, because Settings → API
 * Access enumerates every operation this application declares and narrowing that
 * reference to hide one operation would make it lie about the surface it claims
 * to enumerate. Documenting an operation and its `501` is the opposite act from
 * offering a model-backed answer. `__tests__/**` is allowlisted because this very
 * file, and `settings-api.test.tsx`, must be able to write the string down.
 */
const SEAM_NAMING_ALLOWED: readonly RegExp[] = [
  /^test\/apiFixtures\.ts$/,
  /^__tests__\//,
];

function seamNamingAllowed(rel: string): boolean {
  return SEAM_NAMING_ALLOWED.some((p) => p.test(rel));
}

describe('§5 · no product surface consumes the assistant seam', () => {
  it('no file in the bundle names the assistant-seam operation, outside the allowlist', () => {
    const offenders = allSourceFiles().filter(
      (rel) => !seamNamingAllowed(rel) && namesTheSeam(rawSource(rel)),
    );
    expect(offenders, 'a file outside the allowlist reaches the assistant seam').toEqual([]);
  });

  it('the allowlist is exactly the two entries the docstring defends', () => {
    // A guard whose allowlist grows quietly is a guard that stops guarding. A
    // third entry has to be argued for HERE, next to the reasoning for the first
    // two, rather than appearing as one more regex in a list nobody re-reads.
    const named = allSourceFiles().filter((rel) => namesTheSeam(rawSource(rel)));
    expect(named.filter((rel) => !seamNamingAllowed(rel))).toEqual([]);
    expect(named).toContain('test/apiFixtures.ts');
    expect(SEAM_NAMING_ALLOWED.length).toBe(2);
  });

  it('the api client declares no method for it', () => {
    /*
     * ENFORCEMENT BY NON-IMPLEMENTATION, which is §6.2's own standard for the
     * submit boundary and the right standard here: there is no client method to
     * call, so no screen can call one by accident. A future slice adding
     * `askAssistantSeam()` fails this line and has to argue with §3 rather than
     * with a linter.
     *
     * KEPT AS ITS OWN ASSERTION even though the bundle-wide scan above now
     * subsumes it, because the two say different things. That one says "no file
     * names the operation"; this one says "the file where a client method BELONGS
     * does not have one", and it is the line whose failure message points a future
     * author at the decision instead of at a path list.
     */
    expect(namesTheSeam(rawSource('lib/api.ts'))).toBe(false);
  });

  it('the capability report has exactly one consumer, and it is the voice surface', () => {
    const consumers = ([] as string[]).concat(
      ...PRODUCT_DIRS.map((dir) =>
        sourceFilesUnder(dir)
          .filter((rel) => /getProviderCapabilities/.test(rawSource(join(dir, rel))))
          .map((rel) => `${dir}/${rel}`),
      ),
    );
    // `TranscriptCapturePanel` is authorized by the D6 supersession, whose
    // mitigation for shipping a recorder against an unconfigured seam is that
    // "the seam's status renders ABOVE the controls, before any recording starts".
    // That argument is about transcription and does not transfer to the assistant.
    expect(consumers).toEqual(['components/TranscriptCapturePanel.tsx']);
  });

  it('that consumer reads only the transcription seam, never the assistant one', () => {
    const src = rawSource('components/TranscriptCapturePanel.tsx');
    // It selects its seam by name...
    expect(src).toMatch(/seam\.seam === 'transcription'/);
    // ...and never the assistant's, nor the report's any-provider roll-up, which
    // would go true the moment ANY seam is configured and so cannot be rendered
    // as a statement about transcription.
    expect(src).not.toMatch(/seam\.seam === 'assistant'/);
    expect(src).not.toMatch(/any_provider_configured/);
  });
});

// --- §6 negative controls ---------------------------------------------------

describe('§6 · the guards are proven on input that must fail them', () => {
  it('the sub-claim patterns reject text that omits each claim', () => {
    // The panel's own sentence with one clause removed, one at a time. Each
    // mutant must fail exactly the pattern for the clause it dropped.
    const full = norm(ASSISTANT_NO_MODEL_CLAIM);
    const mutants: [RegExp, string][] = [
      [SUB_CLAIMS[0][1], full.replace(/there is no language model in this build\.\s*/, '')],
      [SUB_CLAIMS[1][1], full.replace(/nothing you type here is sent to a model provider\./, '')],
    ];
    for (const [pattern, mutant] of mutants) expect(mutant).not.toMatch(pattern);
  });

  it('the polarity check rejects the inverted sentence', () => {
    const inverted = norm(
      'There is a language model in this build. Everything you type here is sent to a model provider.',
    );
    expect(INVERSIONS.some((bad) => bad.test(inverted))).toBe(true);
  });

  it('the polarity check rejects a negation that drifts out of its own sentence', () => {
    // The shape a well-meaning edit produces: the negation survives, in a
    // different sentence, where deleting one leaves the other an assertion.
    const drifted = norm(
      'Nothing here is a promise. Your question is sent to a model provider.',
    );
    const sentence = drifted.split(/(?<=\.)\s+/).find((s) => /is sent to a model provider/.test(s));
    expect(sentence).toBeDefined();
    expect(sentence).not.toMatch(/\bnothing\b/);
  });

  it('the provider-implying ratchet fires on a planted "coming soon"', () => {
    const planted = norm('A model provider is coming soon to this deployment.');
    expect(IMPLIES_A_PROVIDER.some((w) => planted.includes(w))).toBe(true);
  });

  it('the source scan can see a planted seam call', () => {
    // Proven against a literal rather than a file, because the scan's subject is
    // the pattern: a scan narrowed until it matches nothing would pass §5 while
    // the offending call sat in the tree.
    const planted = "api.post('/assistant/ask', { question })";
    expect(namesTheSeam(planted)).toBe(true);
  });

  /*
   * THE TWO MEASURED ESCAPES, AS CONTROLS.
   *
   * Each of these was green against the previous §5 — verified by planting the
   * real thing in the real tree and running the real file, not by reasoning about
   * it. They are pinned here as literals so the detector's claim about them is
   * checkable on every run, and so a narrowing of `collapseConcatenatedStrings`
   * or of the allowlist turns a test red instead of turning this comment stale.
   */
  it.each([
    ["'/assistant' + '/' + 'ask'", "const P = '/assistant' + '/' + 'ask';"],
    ['a three-piece split with the prefix', "const P = '/api' + '/assistant' + '/' + 'ask';"],
    ['double quotes', 'const P = "/assistant" + "/" + "ask";'],
    ['template literals', 'const P = `/assistant` + `/` + `ask`;'],
    [
      'a split across line breaks',
      "const P =\n  '/api/assistant' +\n  '/ask';",
    ],
  ])('escape (a): the normaliser sees a dynamically spelled path — %s', (_what, planted) => {
    expect(/assistant\/ask/.test(planted), 'precondition: the literal scan MISSES it').toBe(
      false,
    );
    expect(namesTheSeam(planted), 'the normalised scan must catch it').toBe(true);
  });

  it('escape (a): the normaliser does not pretend to catch what it cannot', () => {
    // The honesty half of the control. These shapes are NOT caught, the docstring
    // says so, and this pins that the docstring is telling the truth — if a future
    // widening does catch one, this test fails and the comment gets updated in the
    // same change rather than drifting into an overclaim.
    const uncatchable = [
      'const P = `/assistant${sep}ask`;',
      "const P = ['assistant', 'ask'].join('/');",
      "const A = 'assistant'; const P = `/${A}/ask`;",
    ];
    for (const planted of uncatchable) {
      expect(namesTheSeam(planted), `unexpectedly caught: ${planted}`).toBe(false);
    }
  });

  it('escape (b): a seam client in lib/ is a violation, and the allowlist does not cover it', () => {
    // The file that was measured green against the previous §5: a real `fetch` to
    // the operation, in `lib/`, which was exempt except for `lib/api.ts` by name.
    const planted = [
      "export async function askAssistantSeam(question: string) {",
      "  const response = await fetch('/api/assistant/ask', { method: 'POST' });",
      '  return response.json();',
      '}',
    ].join('\n');
    expect(namesTheSeam(planted)).toBe(true);
    // And the allowlist must NOT admit it wherever a plausible author would put it.
    for (const rel of [
      'lib/assistantSeamClient.ts',
      'lib/assistantSeam.ts',
      'lib/api2.ts',
      'components/AssistantPanel.tsx',
      'screens/RecordWorkbench.tsx',
      'App.tsx',
      'main.tsx',
    ]) {
      expect(seamNamingAllowed(rel), `allowlist wrongly admits ${rel}`).toBe(false);
    }
    // While the two deliberate exceptions still are admitted.
    expect(seamNamingAllowed('test/apiFixtures.ts')).toBe(true);
    expect(seamNamingAllowed('__tests__/settings-api.test.tsx')).toBe(true);
  });

  it('the bundle-wide walker reaches lib/, test/ and the root, so the widening is not vacuous', () => {
    // The point of the widening is the directories the old scan never opened. A
    // walker that still returned only `components/` and `screens/` would make §5's
    // new assertion pass exactly as vacuously as the old one did for `lib/`.
    const all = allSourceFiles();
    expect(all.length, 'the bundle walked to nothing').toBeGreaterThan(100);
    for (const probe of [
      'lib/api.ts',
      'lib/apiDocsModel.ts',
      'test/apiFixtures.ts',
      'App.tsx',
      'main.tsx',
    ]) {
      expect(all, `the walker never reached ${probe}`).toContain(probe);
    }
    // Nested, too — `screens/settings/*` is where a model-provider tab would most
    // plausibly be added.
    expect(all.some((f) => f.startsWith('screens/settings/'))).toBe(true);
  });

  it('the source walker actually reaches files, so §5 is not vacuously empty', () => {
    // A walker returning [] makes every `.filter(...)` above return [] and every
    // §5 assertion pass without reading a line.
    for (const dir of PRODUCT_DIRS) {
      const files = sourceFilesUnder(dir);
      expect(files.length, `${dir}/ walked to nothing`).toBeGreaterThan(10);
      expect(files.some((f) => f.endsWith('.tsx'))).toBe(true);
    }
    // And it reaches NESTED directories — `screens/settings/*` is where a
    // model-provider tab would most plausibly be added.
    expect(sourceFilesUnder('screens').some((f) => f.includes('/'))).toBe(true);
  });
});

