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
 *   rg -in 'language model' apps/web/src/components/AssistantPanel.tsx  → exit 1
 *   rg -ln 'language model' apps/web/src/lib                            → lib/settingsContent.ts
 *
 * So the claim existed at exactly two places, both in Settings → AI & Automation
 * behind a tab, and the screen a scientist types into said nothing about whether
 * a model is involved or where a typed question goes. §3's argument — "a seam
 * report would only imply a model is nearly here, because the reader is already
 * told there is no model" — had a premise the product did not supply.
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
 *  · It reads `apps/web/src` only. Backend-served copy is invisible to it: the
 *    refusal body `POST /api/assistant/ask` returns, and the OpenAPI description
 *    the Endpoint Explorer renders, are both authored in `routes.py`.
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
    // Not a style rule. The full four-clause paragraph is 244 characters at 11px
    // in a sticky dock inside a content-sized rail; the kept pair is 92. A future
    // slice that pastes the paragraph back in fails here and has to read
    // `ASSISTANT_NO_MODEL_CLAIM`'s comment before doing it anyway.
    const claim = norm(ASSISTANT_NO_MODEL_CLAIM);
    expect(claim).not.toMatch(/bounded, deterministic catalog/);
    expect(claim.length).toBeLessThan(140);
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
 * The product surfaces. `lib/` is excluded here and checked separately below: the
 * client method that WOULD call the seam belongs in `lib/api.ts`, and asserting
 * its absence there is a different assertion from "no screen calls it".
 */
const PRODUCT_DIRS = ['components', 'screens'] as const;

describe('§5 · no product surface consumes the assistant seam', () => {
  it.each(PRODUCT_DIRS)('no file under %s/ names the assistant-seam operation', (dir) => {
    const offenders = sourceFilesUnder(dir).filter((rel) =>
      /assistant\/ask/.test(rawSource(join(dir, rel))),
    );
    expect(offenders, `${dir}/ reaches the assistant seam`).toEqual([]);
  });

  it('the api client declares no method for it', () => {
    /*
     * ENFORCEMENT BY NON-IMPLEMENTATION, which is §6.2's own standard for the
     * submit boundary and the right standard here: there is no client method to
     * call, so no screen can call one by accident. A future slice adding
     * `askAssistantSeam()` fails this line and has to argue with §3 rather than
     * with a linter.
     */
    expect(rawSource('lib/api.ts')).not.toMatch(/assistant\/ask/);
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
    expect(/assistant\/ask/.test(planted)).toBe(true);
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

