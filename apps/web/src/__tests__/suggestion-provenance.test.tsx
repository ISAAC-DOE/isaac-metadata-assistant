import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import { GuidedPrompt } from '../components/GuidedPrompt';
import { pendingItemToBlocker, sanitizeInferability, toExperimentSummary } from '../lib/adapt';
import type {
  ApiExperimentSummary,
  ApiAnswerablePendingItem,
  Inferability,
  PendingBlocker,
} from '../lib/types';

/**
 * The client half of the no-guessing suggestion contract.
 *
 * The backend enforces the invariant structurally; these tests assert the client
 * neither weakens it on the way in (`sanitizeInferability`) nor re-creates a
 * fabricated value of its own (`toExperimentSummary`), and that the completion
 * card can only ever submit a value the user acted on.
 */

const REFUSAL: Inferability = {
  field: 'measurement.series',
  state: 'needs_user_input',
  explanation:
    "The reduced spectrum's data points exist only in the reduction product, so the series must come from you.",
  value: null,
  provenance: null,
  detail: {},
};

/** A provenance that passes every check, so a test can vary exactly one clause. */
function prov(
  patch: Partial<NonNullable<Inferability['provenance']>>,
): NonNullable<Inferability['provenance']> {
  return {
    supporting_fields: ['sample.material.formula'],
    supporting_evidence: [{ source_type: 'spreadsheet' }],
    rule: 'absorbing element = the sole non-oxygen element (CuO2 -> Cu)',
    unique: true,
    alternatives_excluded: ['oxygen is excluded by the rule'],
    requires_user_confirmation: true,
    ...patch,
  };
}

function blocker(overrides: Partial<PendingBlocker> = {}): PendingBlocker {
  return {
    id: 'series',
    key: 'series',
    kind: 'series',
    question: 'Provide the reduced spectrum.',
    label: 'Reduced Spectrum',
    path: 'measurement.series',
    inputType: 'structured',
    inferability: REFUSAL,
    ...overrides,
  };
}

function renderPrompt(b: PendingBlocker, onConfirm = vi.fn(), onDontKnow = vi.fn()) {
  const view = render(
    <GuidedPrompt blocker={b} index={0} total={1} onConfirm={onConfirm} onDontKnow={onDontKnow} />,
  );
  return { view, onConfirm, onDontKnow };
}

// --- the invariant, re-checked on arrival ------------------------------------

describe('a concrete value may accompany supported_suggestion and nothing else', () => {
  const states: Inferability['state'][] = [
    'needs_user_input',
    'ambiguous',
    'contradictory_evidence',
    'not_inferable',
  ];

  it.each(states)('strips a value that arrives under state %s', (state) => {
    const rogue = { ...REFUSAL, state, value: 'Cu' } as Inferability;
    const cleaned = sanitizeInferability(rogue)!;
    expect(cleaned.value).toBeNull();
    expect(cleaned.provenance).toBeNull();
  });

  it('strips a supported_suggestion whose provenance is missing', () => {
    const rogue: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      value: 'Cu',
      provenance: null,
    };
    expect(sanitizeInferability(rogue)!.value).toBeNull();
  });

  it('strips a supported_suggestion whose inference is not unique', () => {
    const rogue: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      value: 'Cu',
      provenance: {
        supporting_fields: ['sample.material.formula'],
        supporting_evidence: [{ source_type: 'spreadsheet' }],
        rule: 'sole non-oxygen element',
        unique: false,
        alternatives_excluded: [],
        requires_user_confirmation: true,
      },
    };
    expect(sanitizeInferability(rogue)!.value).toBeNull();
  });

  it('strips a supported_suggestion justified by a value from ANOTHER record', () => {
    // REVIEW FINDING (client guard): the first version checked only `unique` and
    // `rule`, so a copied value with an otherwise well-formed provenance passed
    // the client untouched.
    const rogue: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      value: 'CuO2',
      provenance: {
        supporting_fields: ['sample.material.formula'],
        supporting_evidence: [{ source_type: 'other_record' }],
        rule: 'the neighbouring record in this campaign used this formula',
        unique: true,
        alternatives_excluded: [],
        requires_user_confirmation: true,
      },
    };
    expect(sanitizeInferability(rogue)!.value).toBeNull();
  });

  it.each(['tutorial_example', 'commonly_used', 'model_confidence', 'schema_enum'])(
    'strips a supported_suggestion justified by %s',
    (sourceType) => {
      const rogue: Inferability = {
        ...REFUSAL,
        state: 'supported_suggestion',
        value: 'Cu',
        provenance: {
          supporting_fields: ['sample.material.formula'],
          supporting_evidence: [{ source_type: sourceType }],
          rule: 'r',
          unique: true,
          alternatives_excluded: [],
          requires_user_confirmation: true,
        },
      };
      expect(sanitizeInferability(rogue)!.value).toBeNull();
    },
  );

  it('strips a supported_suggestion citing no supporting field or evidence', () => {
    const rogue: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      value: 'Cu',
      provenance: {
        supporting_fields: [],
        supporting_evidence: [],
        rule: 'r',
        unique: true,
        alternatives_excluded: [],
        requires_user_confirmation: true,
      },
    };
    expect(sanitizeInferability(rogue)!.value).toBeNull();
  });

  // The five shapes an independent review proved the DENYLIST version let through.
  // Each is a `supported_suggestion` carrying a value; each must now be stripped.
  const counterExamples: [string, Partial<Inferability>][] = [
    [
      "an unrecognised source type ('literature' — used by this repo's own fixtures)",
      { provenance: prov({ supporting_evidence: [{ source_type: 'literature' }] }) },
    ],
    [
      "an invented source type ('vibes')",
      { provenance: prov({ supporting_evidence: [{ source_type: 'vibes' }] }) },
    ],
    [
      'a NESTED confidence number (the corpus shape: uncertainty.confidence)',
      {
        provenance: prov({
          supporting_evidence: [
            { source_type: 'spreadsheet', uncertainty: { confidence: 0.86 } },
          ],
        }),
      },
    ],
    [
      'derivation evidence that states no rule',
      { provenance: prov({ supporting_evidence: [{ source_type: 'derivation' }] }) },
    ],
    ['an empty explanation', { explanation: '' }],
    // A second review found the TOP-LEVEL confidence key unpinned on this side:
    // every existing case nested it (`uncertainty.confidence`) or relied on the
    // source type alone, so a `confidence >= 0.9` bypass of BOTH the allowlist and
    // the confidence scan cost 0 frontend failures. These two are the pair that
    // kills it — the first keeps the source type legitimate so only the confidence
    // clause can refuse, the second keeps the confidence high so only the
    // allowlist can. A bypass that reads either clause alone still fails one.
    [
      'a TOP-LEVEL confidence number on otherwise legitimate evidence',
      {
        provenance: prov({
          supporting_evidence: [{ source_type: 'spreadsheet', confidence: 0.99 }],
        }),
      },
    ],
    [
      'a high confidence carried by a predictor source type',
      {
        provenance: prov({
          supporting_evidence: [{ source_type: 'model_confidence', confidence: 0.99 }],
        }),
      },
    ],
  ];

  it.each(counterExamples)('strips a supported_suggestion with %s', (_label, patch) => {
    const rogue: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      explanation: 'Uniquely determined by a documented rule.',
      value: 'Cu',
      provenance: prov({}),
      ...patch,
    } as Inferability;
    const cleaned = sanitizeInferability(rogue)!;
    expect(cleaned.value).toBeNull();
    expect(cleaned.provenance).toBeNull();
  });

  it('detaches a provenance left attached to a non-supported state', () => {
    // A justification for a value the state says does not exist.
    const rogue: Inferability = { ...REFUSAL, provenance: prov({}) };
    expect(sanitizeInferability(rogue)!.provenance).toBeNull();
  });

  it('accepts every source type the truth plane treats as record evidence', () => {
    // The positive allowlist must mirror `RECORD_EVIDENCE_SOURCE_TYPES`
    // (`OBSERVED_SOURCE_TYPES` + `derivation`) — not be narrower by accident.
    for (const sourceType of [
      'document',
      'spreadsheet',
      'screenshot',
      'web_form',
      'file_listing',
      'user_confirmation',
    ]) {
      const good: Inferability = {
        ...REFUSAL,
        state: 'supported_suggestion',
        explanation: 'Uniquely determined by a documented rule.',
        value: 'Cu',
        provenance: prov({ supporting_evidence: [{ source_type: sourceType }] }),
      };
      expect(sanitizeInferability(good)!.value).toBe('Cu');
    }
    const derivation: Inferability = {
      ...REFUSAL,
      state: 'supported_suggestion',
      explanation: 'Uniquely determined by a documented rule.',
      value: 'experimental',
      provenance: prov({
        supporting_evidence: [{ source_type: 'derivation', rule: 'facility => experimental' }],
      }),
    };
    expect(sanitizeInferability(derivation)!.value).toBe('experimental');
  });

  it('keeps a fully justified supported_suggestion intact', () => {
    const good: Inferability = {
      field: 'implicit:absorbing_element',
      state: 'supported_suggestion',
      explanation: 'Uniquely determined by a documented rule.',
      value: 'Cu',
      provenance: {
        supporting_fields: ['sample.material.formula'],
        supporting_evidence: [{ source_type: 'spreadsheet' }],
        rule: 'absorbing element = the sole non-oxygen element (CuO2 -> Cu)',
        unique: true,
        alternatives_excluded: ['oxygen is excluded by the rule'],
        requires_user_confirmation: true,
      },
      detail: {},
    };
    expect(sanitizeInferability(good)).toBe(good);
  });
});

// --- the adapter neither invents nor launders ---------------------------------

describe('the adapter does not manufacture values', () => {
  it('no longer fabricates a technique the API never sent', () => {
    const summary = {
      id: '01SYNTH',
      title: 'Synthetic XANES · New Draft',
      status: 'needs_attention',
      pending_count: 5,
      exported: false,
      record_id: null,
      created_utc: '2099-04-02T00:00:00Z',
    } as unknown as ApiExperimentSummary;
    const row = toExperimentSummary(summary);
    expect(row.technique).toBeUndefined();
    // And nothing else in the row carries the retired constant.
    expect(JSON.stringify(row)).not.toContain('Cu K-edge XANES');
  });

  it('passes the inferability decision through without re-deciding it', () => {
    const item: ApiAnswerablePendingItem = {
      id: 'series',
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      demo_answer: null,
      inferability: REFUSAL,
    };
    expect(pendingItemToBlocker(item).inferability).toEqual(REFUSAL);
  });

  it('does not tell the user to confirm an example that is not on screen', () => {
    // REVIEW FINDING 2. Scoping the example answer to the built-in walkthrough
    // records made the old unconditional copy FALSE everywhere it was withheld:
    // "Confirm the example value, or leave it honestly missing" pointed at
    // nothing. Reachable on a `managed_legacy` record.
    for (const kind of ['series', 'descriptor'] as const) {
      const withoutExample = pendingItemToBlocker({
        id: kind,
        kind,
        question: 'q',
        demo_answer: null,
      });
      expect(withoutExample.context).not.toMatch(/Confirm the example value/);
      expect(withoutExample.context).toMatch(/never generate/);

      const withExample = pendingItemToBlocker({
        id: kind,
        kind,
        question: 'q',
        demo_answer: { value: [{ series_id: 's' }], label: 'Example answer' },
      });
      expect(withExample.context).toMatch(/Confirm the example value/);
    }
  });

  it('offers exactly the control its copy says it offers', () => {
    // THIS TEST WAS INVERTED, BY ITS OWN INSTRUCTION. It read
    // "does not invite the user to supply a value this screen cannot take", and pinned
    // the copy "this screen has no way to enter one" TOGETHER WITH the absence of any
    // control — deliberately, saying: "If a future slice builds the structured input,
    // this test fails and the copy must be revisited in the same change."
    //
    // That slice is `StructuredValueEntry.tsx`, this test failed, and the copy was
    // revisited in the same change. The pairing is what is preserved: the claim and the
    // rendered screen are still asserted together, because a claim pinned apart from
    // the screen it describes is exactly how the two drifted the first time.
    for (const kind of ['series', 'descriptor'] as const) {
      const b = pendingItemToBlocker({ id: kind, kind, question: 'q', demo_answer: null });

      // The half that has NOT changed and must not: the app never generates either.
      expect(b.context).toMatch(/never generate/);
      // The dead-end claim is gone, because the dead end is gone.
      expect(b.context).not.toMatch(/no way to enter one/i);

      const { view } = renderPrompt(b);
      // The claim is on screen …
      expect(view.getByText(b.context!)).toBeInTheDocument();
      // … and so is the control it describes.
      expect(view.queryAllByRole('textbox').length).toBeGreaterThan(0);
      expect(view.getByRole('button', { name: /confirm|save/i })).toBeInTheDocument();
      // Nothing is filled in: a blank form is not a suggested value.
      for (const box of view.queryAllByRole('textbox')) {
        expect(box).toHaveValue('');
      }
      // Leaving it missing is still offered, and is still the honest alternative.
      expect(view.getByRole('button', { name: /don.t know/i })).toBeInTheDocument();
      view.unmount();
    }
  });

  it('leaves the asset copy alone — it never referenced an example', () => {
    const asset = pendingItemToBlocker({
      id: 'synthetic://x',
      kind: 'asset',
      question: 'q',
      demo_answer: null,
    });
    expect(asset.context).toMatch(/Paste the sha256/);
    expect(asset.context).not.toMatch(/example value/);
  });

  it('carries an example answer’s provenance rather than re-deriving it', () => {
    const item: ApiAnswerablePendingItem = {
      id: 'series',
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      demo_answer: {
        value: [{ series_id: 'averaged_spectrum' }],
        label: 'Example answer',
        provenance: {
          source: 'tutorial_example_fixture',
          is_evidence_for_this_record: false,
          auto_applied: false,
          requires_user_confirmation: true,
        },
      },
      inferability: REFUSAL,
    };
    const out = pendingItemToBlocker(item);
    expect(out.demo_answer?.provenance?.is_evidence_for_this_record).toBe(false);
    expect(out.demo_answer?.provenance?.auto_applied).toBe(false);
  });
});

// --- the completion card ------------------------------------------------------

describe('the completion card explains the refusal and fills nothing', () => {
  it('renders the server’s explanation verbatim, tagged with its state', () => {
    const { view } = renderPrompt(blocker());
    const note = view.container.querySelector('.guided-inferability')!;
    expect(note).toBeTruthy();
    expect(note.textContent).toBe(REFUSAL.explanation);
    expect(note.getAttribute('data-inferability-state')).toBe('needs_user_input');
  });

  it('offers no value and no suggestion block on an ordinary record', () => {
    const { view } = renderPrompt(blocker({ demo_answer: undefined }));
    expect(view.container.querySelector('.guided-suggestion')).toBeNull();
    expect(screen.queryByText(/Use This Value|Use This Suggestion/)).toBeNull();
    // The fabricated walkthrough descriptor must not appear anywhere.
    expect(view.container.textContent).not.toContain('9001.2');
  });

  it('never pre-fills a plausible value into the input placeholder', () => {
    const { view } = renderPrompt(
      blocker({ kind: 'asset', id: 'synthetic://x', path: 'synthetic://x', inputType: 'hash' }),
    );
    const input = view.container.querySelector('input')! as HTMLInputElement;
    expect(input.value).toBe('');
    // The placeholder instructs; it is not a plausible answer.
    expect(input.placeholder).toBe('paste 64-character sha256…');
    expect(input.placeholder).not.toMatch(/^[0-9a-f]{64}$/);
  });

  it('cannot confirm a structured field until the user acts (never silent)', () => {
    const b = blocker({
      demo_answer: { value: [{ series_id: 'averaged_spectrum' }], label: 'Example answer' },
    });
    const { view, onConfirm } = renderPrompt(b);
    const confirm = screen.getByRole('button', { name: /Confirm/i }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();

    // Two explicit acts are required: accept the example, then confirm it.
    fireEvent.click(screen.getByRole('button', { name: 'Use This Value' }));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(b.demo_answer!.value);
    void view;
  });

  it('a declined question submits nothing at all', () => {
    const { onConfirm, onDontKnow } = renderPrompt(
      blocker({
        demo_answer: { value: [{ series_id: 'averaged_spectrum' }], label: 'Example answer' },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /don.t know/i }));
    expect(onDontKnow).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('a declined-then-re-offered question does not come back pre-accepted', () => {
    const b = blocker({
      demo_answer: { value: [{ series_id: 'averaged_spectrum' }], label: 'Example answer' },
    });
    const { onConfirm } = renderPrompt(b);
    fireEvent.click(screen.getByRole('button', { name: /don.t know/i }));

    // Re-mounting the same question (the parent re-renders with key={blocker.id})
    // must start unstaged: a rejection leaves no residue that could be confirmed.
    const second = render(
      <GuidedPrompt blocker={b} index={0} total={1} onConfirm={onConfirm} onDontKnow={vi.fn()} />,
    );
    const confirms = second.container.querySelectorAll('button.btn-primary');
    expect((confirms[confirms.length - 1] as HTMLButtonElement).disabled).toBe(true);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
