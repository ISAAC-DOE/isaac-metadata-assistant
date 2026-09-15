import { useEffect, useState } from 'react';

import { api } from '../lib/api';
import { RUN_FIELDS } from '../lib/runFields';
import type { ApiRunView } from '../lib/types';
import './run-schema-mirror.css';

/**
 * WHAT THE OFFICIAL RECORD LOOKS LIKE AS A RUN IS FILLED IN.
 *
 * ── WHY IT EXISTS ───────────────────────────────────────────────────────────
 *
 * The project owner, 2026-09-14: *"im assuming you would want to ingest the
 * isaac actual schema structure no? … the whole idea is that these populate into
 * the schema right so there should be an intuitive way users can both add runs
 * and then see the schema being filled at the same time, maybe like a split
 * screen type of thing"*, and then, explicitly: *"build a provisional one and
 * revise later, i want the view there so i can show angel and hao the vision"*.
 *
 * ── WHAT IS REAL HERE, AND WHAT IS PROVISIONAL ─────────────────────────────
 *
 * REAL: the structure. Every block and field name comes from `GET /api/schema`,
 * which serves the vendored `schema/isaac_record_v1.json` — the same document
 * `isaac validate --official` checks against. Nothing on this pane is a
 * hand-written field list, so a schema refresh moves it.
 *
 * REAL: the filled/empty state. A block reads as recorded only when the run
 * itself carries it (`run.fields`) or inherits it from the record
 * (`run.inherited`). Nothing is inferred and no value is invented — an unfilled
 * block says nothing rather than showing a plausible default, which is §5.
 *
 * PROVISIONAL, AND SAID ON THE PANE: which blocks belong to a RUN rather than to
 * the record. That is a scientific decision about what a run owns, and the
 * project owner is getting the template from Angel. The split below is a
 * reasonable reading of the schema — `measurement`, `timestamps` and
 * `descriptors` move per run; `sample`, `system` and `attribution` describe the
 * campaign — and it is labelled as a draft so nobody mistakes it for settled.
 * It is deliberately NOT used to gate anything: no export decision, no
 * completeness claim, no validation. It is a mirror.
 *
 * ── WHY IT CANNOT CLAIM COMPLETENESS ───────────────────────────────────────
 *
 * "Recorded" here means a key is present, not that the value is valid — official
 * validation is the only thing that decides that, and it runs at export. So the
 * pane says "recorded" and never "complete", "ready" or "valid".
 */

/** The run/record split. PROVISIONAL — see the header. */
const RUN_BLOCKS: readonly string[] = ['measurement', 'timestamps', 'descriptors', 'context'];
const RECORD_BLOCKS: readonly string[] = [
  'sample',
  'system',
  'attribution',
  'links',
  'assets',
  'tags',
];

interface SchemaNode {
  properties?: Record<string, SchemaNode>;
  required?: string[];
  description?: string;
}

function blockFields(node: SchemaNode | undefined): { name: string; required: boolean }[] {
  const props = node?.properties ?? {};
  const required = new Set(node?.required ?? []);
  return Object.keys(props).map((name) => ({ name, required: required.has(name) }));
}

export function RunSchemaMirror({ run }: { run: ApiRunView | null }) {
  const [schema, setSchema] = useState<SchemaNode | null>(null);
  const [failed, setFailed] = useState(false);

  /*
   * THE SCHEMA IS THE ONLY THING THIS PANE FETCHES, and the run arrives as a
   * prop.
   *
   * It used to read `GET /runs?limit=1` itself, which made the Runs workspace
   * read the runs list TWICE on first paint —
   * `runs-live-refresh-integration.test.tsx` pins that at once and failed with
   * "expected [ …(2) ] to have a length of 1 but got 2". `RunsSection` already
   * holds the page, so it reports its first run upward instead: one read, two
   * consumers, and the mirror cannot disagree with the run card about the same
   * run.
   */
  useEffect(() => {
    let cancelled = false;
    void api
      .getSchema()
      .then((body) => {
        if (!cancelled) setSchema((body.schema ?? null) as SchemaNode | null);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <aside className="rsm" aria-labelledby="rsm-heading">
        <h3 className="rsm-heading" id="rsm-heading">
          Official Record Structure
        </h3>
        <p className="rsm-note">
          The schema could not be read, so nothing is shown rather than a structure
          from memory.
        </p>
      </aside>
    );
  }

  if (schema === null) {
    return (
      <aside className="rsm" aria-labelledby="rsm-heading">
        <h3 className="rsm-heading" id="rsm-heading">
          Official Record Structure
        </h3>
        <p className="rsm-note">Reading the official schema…</p>
      </aside>
    );
  }

  /*
   * ── WHAT THIS PANE CAN HONESTLY SAY ABOUT A BLOCK ────────────────────────
   *
   * `run.fields` is keyed by dotted official path and holds THE FIVE RUN
   * CONDITION FIELDS (`RUN_FIELDS`) — nothing else. Measured over HTTP: after
   * answering `qc` on a run, `run.fields` was still `{}` and `inherited`
   * carried only `block:attribution`. The qc, series and descriptor answers live
   * in the run's DRAFT, which the run-list payload does not serve.
   *
   * SO A BLOCK WITH NO OBSERVABLE PATH GETS "not shown here", NOT "nothing yet".
   * Saying "nothing yet" about `measurement` on a run whose spectrum and QC
   * verdict are recorded would be this product's signature defect — a surface
   * stating something it never checked. `runFilledCount` is the same authority
   * the run card's "N of 5 run fields" uses, so the two cannot disagree.
   */
  const own = (run?.fields ?? {}) as Record<string, unknown>;
  const inherited = (run?.inherited ?? {}) as Record<string, unknown>;
  /** Top-level blocks any `RUN_FIELDS` path reaches — the observable set. */
  const observable = new Set(RUN_FIELDS.map((spec) => spec.path.split('.')[0]));
  const stateOf = (block: string): 'own' | 'inherited' | 'empty' | 'unknown' => {
    const hit = (bag: Record<string, unknown>) =>
      Object.keys(bag).some(
        (key) => key === block || key.startsWith(`${block}.`) || key === `block:${block}`,
      );
    if (hit(own)) return 'own';
    if (hit(inherited)) return 'inherited';
    return observable.has(block) ? 'empty' : 'unknown';
  };

  const section = (title: string, blocks: readonly string[], scopeNote: string) => (
    <div className="rsm-group">
      <p className="rsm-group-title eyebrow">{title}</p>
      <p className="rsm-note">{scopeNote}</p>
      <ul className="rsm-blocks">
        {blocks
          .filter((block) => schema.properties?.[block] !== undefined)
          .map((block) => {
            const state = stateOf(block);
            const fields = blockFields(schema.properties?.[block]);
            return (
              <li className={`rsm-block rsm-${state}`} key={block}>
                <div className="rsm-block-head">
                  <code className="mono rsm-path">{block}</code>
                  <span className="rsm-state">
                    {state === 'own'
                      ? 'recorded on this run'
                      : state === 'inherited'
                        ? 'from the record'
                        : state === 'empty'
                          ? 'nothing yet'
                          : 'not shown here'}
                  </span>
                </div>
                {fields.length > 0 && (
                  <p className="rsm-fields">
                    {fields.map((f) => (f.required ? `${f.name}*` : f.name)).join(' · ')}
                  </p>
                )}
              </li>
            );
          })}
      </ul>
    </div>
  );

  return (
    <aside className="rsm" aria-labelledby="rsm-heading">
      <h3 className="rsm-heading" id="rsm-heading">
        Official Record Structure
      </h3>
      <p className="rsm-note">
        Read live from the vendored ISAAC v1.05 schema — the same document{' '}
        <code className="mono">isaac validate --official</code> checks against. A field
        marked <code className="mono">*</code> is required by the schema.
      </p>
      {section(
        'Filled per run',
        RUN_BLOCKS,
        'These change between runs of the same experiment.',
      )}
      {section(
        'Shared by the record',
        RECORD_BLOCKS,
        'Entered once and inherited by every run.',
      )}
      <p className="rsm-draft">
        <strong>Draft grouping.</strong> &ldquo;Not shown here&rdquo; means this pane
        cannot see that block from the run list it reads — the spectrum, QC verdict and
        descriptors are answered through Complete Metadata, and this view does not
        claim a state it did not check. The schema structure above is exact. Which
        blocks belong to a run rather than to the whole experiment is a scientific
        decision still to be confirmed, so this split is a starting point for that
        conversation — not a rule the product enforces. Nothing here gates export or
        claims a record is complete; official validation decides that.
      </p>
    </aside>
  );
}
