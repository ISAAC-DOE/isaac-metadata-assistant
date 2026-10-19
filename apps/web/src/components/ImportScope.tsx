import { createContext, useContext, useEffect, useId, type ReactNode } from 'react';
import { HelpTip } from './HelpTip';
import { IMPORT_COPY, IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import type { ProposalDestinations } from '../lib/importDestinations';

const COPY = IMPORT_STAGE_COPY;

type ActFn = (name: string, run: () => Promise<unknown>) => Promise<unknown>;

/**
 * WHERE A READING RULE IS KEPT — ONE PICKER FOR EVERY RULE FORM (2026-10-18, QA `C-13`).
 *
 * Every rule form on the import screen — resolving a conflict, resolving a whole sample
 * group, binding a convention, assigning a signal channel — offers the owner's three
 * scopes: "Apply only here", "Use as a rule for this Experiment", "Use as a rule for this
 * convention". The audit measured the second and third as effectively DISABLED until a
 * record existed (and records exist only once the last stage has sent something), with
 * "this Experiment" naming no experiment at all. A reader was offered two choices they
 * could not take and given no reason.
 *
 * So the scope fields are one component, fed by the import screen:
 *
 *   * the record this import last targeted is NAMED in the option, and preselected
 *     when a stored scope is chosen — never chosen for the reader before they pick one;
 *   * when no record exists, the stored scopes stay choosable and say, in one sentence,
 *     that a rule of that kind is kept on a record — with "New Record From This Import"
 *     beside it, the same creation every send form already offers;
 *   * what each scope MEANS is one press away, behind the `?`.
 *
 * Rendered without the provider (a component test, or a future surface), it behaves
 * exactly as the per-form fields it replaces did: a picker, and no creation control.
 */
export interface ImportScopeValue {
  /** The record this import was last read for (`rules.target_experiment_id`). */
  targetId: string | null;
  /** Creates a record titled from the import and returns its id. */
  createRecord: () => Promise<string>;
  onAct: ActFn;
  busy: string | null;
}

const ImportScopeContext = createContext<ImportScopeValue | null>(null);

export function ImportScopeProvider({ value, children }: { value: ImportScopeValue; children: ReactNode }) {
  return <ImportScopeContext.Provider value={value}>{children}</ImportScopeContext.Provider>;
}

export type RuleScope = 'import' | 'experiment' | 'profile';

/** The three scopes, the record a stored one is kept on, and how to make one. */
export function RuleScopeFields({
  scope,
  setScope,
  experimentId,
  setExperimentId,
  destinations,
}: {
  scope: RuleScope;
  setScope: (scope: RuleScope) => void;
  experimentId: string;
  setExperimentId: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  const name = useId();
  const ctx = useContext(ImportScopeContext);
  const titleOf = (id: string) => destinations.rows?.find((r) => r.id === id)?.title;
  /* THE RECORD THE OPTIONS NAME: the one chosen below, else the one this import was last
     read for. Naming it is a label, not a choice — nothing is selected until the reader
     picks a stored scope, and then only if they have not chosen another record. */
  const named = experimentId || ctx?.targetId || '';
  const namedTitle = named ? titleOf(named) : undefined;
  useEffect(() => {
    if (scope !== 'import' && !experimentId && ctx?.targetId && titleOf(ctx.targetId)) {
      setExperimentId(ctx.targetId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, ctx?.targetId, destinations.rows]);

  const label = (option: RuleScope) => {
    const base = COPY.scopeOptions[option];
    if (option === 'import' || !namedTitle) return base;
    return `${base} — ${namedTitle}`;
  };
  const noRecords = destinations.rows !== null && destinations.rows.length === 0;
  const createKey = 'create:scope';

  return (
    <>
      <fieldset className="hi-resolve-group">
        <legend className="hi-field-label">
          {COPY.resolve.scope}{' '}
          <HelpTip subject="where a rule applies" label="What Each Choice Means">
            {COPY.scopeHelp}
          </HelpTip>
        </legend>
        {(['import', 'experiment', 'profile'] as RuleScope[]).map((option) => (
          <label key={option} className="hi-choice">
            <input
              type="radio"
              name={`${name}-scope`}
              checked={scope === option}
              onChange={() => setScope(option)}
            />
            <span>{label(option)}</span>
          </label>
        ))}
      </fieldset>
      {scope !== 'import' &&
        (noRecords ? (
          <div className="hi-scope-needs">
            <p className="hi-note">{COPY.scopeNeedsRecord}</p>
            {ctx && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={ctx.busy !== null}
                onClick={() => {
                  void ctx.onAct(createKey, async () => {
                    const id = await ctx.createRecord();
                    setExperimentId(id);
                  });
                }}
              >
                {ctx.busy === createKey ? 'Creating…' : IMPORT_COPY.actionNewRecord}
              </button>
            )}
          </div>
        ) : (
          <ExperimentPicker value={experimentId} onChange={setExperimentId} destinations={destinations} />
        ))}
    </>
  );
}

/** A record picker for a rule stored on an experiment. The same list every picker uses. */
export function ExperimentPicker({
  value,
  onChange,
  destinations,
}: {
  value: string;
  onChange: (id: string) => void;
  destinations: ProposalDestinations;
}) {
  return (
    <label className="hi-field">
      <span className="hi-field-label">{COPY.whichExperiment}</span>
      {destinations.failed ? (
        <>
          <input
            className="hi-input"
            type="text"
            required
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="the record's id"
          />
          <span className="hi-note">
            The list of records could not be read, so this asks for the id instead.
          </span>
        </>
      ) : destinations.rows === null ? (
        <span className="hi-note">Reading your records…</span>
      ) : destinations.rows.length === 0 ? (
        <span className="hi-note">This workspace holds no records yet.</span>
      ) : (
        <select
          className="hi-input"
          required
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Choose a record…</option>
          {destinations.rows.map((row) => (
            <option key={row.id} value={row.id}>
              {row.title}
            </option>
          ))}
        </select>
      )}
    </label>
  );
}
