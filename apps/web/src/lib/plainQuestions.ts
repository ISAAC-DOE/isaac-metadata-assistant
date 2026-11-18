/**
 * PLAIN WORDS FOR THE LOCAL IMPORTS QUESTIONS (2026-11-17, owner: "the questions page … read[s] like an engineer
 * wrote it").
 *
 * The backend's question text (`apps/api/isaac_api/local_import/questions.py`) is the command line's: the Claude
 * Code skill reads it, and it names field paths, decision names and flags. Those strings are NOT changed. This
 * module gives the site a plain layer on top of them, by question kind and field:
 *
 *   "What is the environment (context.environment)? No source in this import states it. Applies to 90 group(s) …"
 *   → "Was this done operando, in situ, ex situ or in silico? None of your files say."
 *
 * COPY ONLY, and never more than the server said. Each plain line restates what the kind of question already
 * means (a missing value: no file states it; a conflict: the files disagree), so it adds no claim. The server's
 * full wording and the field path stay on the card, behind its "Details" disclosure. A kind this module does not
 * know returns `null`, and the card shows the server's text as it is.
 *
 * WHAT CHANGES HOW TO ANSWER IS NEVER BEHIND DETAILS (2026-11-17 review, CRITICAL). The server's wording can carry
 * an instruction or a warning ("answer once ONLY if they are all the same sample", "ASKED AGAIN: …", "answers
 * already given … differ"). `questionWarnings` says each of them plainly beside the title, read from the question's
 * own structured fields (`partition`, `asked_again`, `answers_differ`, `targets_without_a_value`, …), never by
 * matching the server's sentences.
 */
import type { LocalEarlierAnswer, LocalQuestion, LocalScope } from './localImports';

/** How a field is ASKED when no file states it, in the words a scientist would use. Paths read from the schema. */
const FIELD_ASK: Readonly<Record<string, string>> = {
  'sample.sample_form': 'What form was the sample in?',
  'system.domain': 'Is this experimental or computational work?',
  'system.technique': 'Which technique was used?',
  'attribution.produced_by.group': 'Which research group produced this data?',
  'attribution.produced_by.organization': 'Which institution produced this data?',
  'sample.material.name': 'What is the sample material?',
  'sample.sample_id': 'What is the sample ID?',
  'context.electrochemistry.cell_type': 'What kind of cell was used?',
  'context.electrochemistry.reaction': 'Which reaction was studied?',
  'context.electrochemistry.potential_setpoint_V': 'What potential was applied?',
  'context.electrochemistry.electrolyte.name': 'What was the electrolyte?',
  'timestamps.acquired_start_utc': 'When did the measurement start?',
};

/** What a field IS, as a noun, for "is the … right?" and "your files disagree about the …". */
const FIELD_NOUN: Readonly<Record<string, string>> = {
  'context.environment': 'measurement environment',
  'sample.sample_form': 'sample form',
  'system.domain': 'domain',
  'system.technique': 'technique',
  'attribution.produced_by.group': 'research group',
  'attribution.produced_by.organization': 'institution',
  'sample.material.name': 'sample material',
  'sample.material.provenance': 'sample source',
  'sample.sample_id': 'sample ID',
  'context.electrochemistry.cell_type': 'cell type',
  'context.electrochemistry.reaction': 'reaction',
  'context.electrochemistry.potential_setpoint_V': 'applied potential',
  'context.electrochemistry.electrolyte.name': 'electrolyte',
  'timestamps.acquired_start_utc': 'start time',
  'measurement.series[].channels[].name': 'signal channel name',
  'measurement.series[].independent_variables[].values': 'energy values',
  'assets[].uri': 'data file location',
  'links[].rel': 'link type',
};

/** Last path segments that say nothing alone: their parent is named with them. */
const VAGUE = new Set(['name', 'group', 'organization', 'value', 'type', 'status', 'id']);

/** A field path as a noun, for a path this module has no word for: "sample.sample_form" → "sample form". */
export function fieldNoun(path: string): string {
  if (FIELD_NOUN[path]) return FIELD_NOUN[path];
  // a unit the field's NAME carries (temperature_K, potential_setpoint_V) is said by the answer box, not the question
  const segs = path
    .split('.')
    .map((x) => x.replace(/\[\]$/, '').replace(/_(mA_cm2|eV|mm|K|V|M)$/, '').replace(/_/g, ' '));
  const last = segs[segs.length - 1] ?? path;
  return VAGUE.has(last) && segs.length > 1 ? `${segs[segs.length - 2]} ${last}` : last;
}

/**
 * Fields asked as a choice between their allowed values: the lead, then the values themselves. The values are
 * never written here: they are the question's own `allowed_values`, which the server reads from the vendored
 * schema's enum (the same list the backend question and `decide` use), so a value the schema adds is asked too.
 */
const CHOICE_ASK: Readonly<Record<string, string>> = {
  'context.environment': 'Was this done',
};

/** A vocabulary value in words: "in_situ" → "in situ". */
function valueWords(v: unknown): string {
  return String(v).replace(/_/g, ' ');
}

/** "a, b or c". */
function orList(items: string[]): string {
  return items.length <= 1 ? (items[0] ?? '') : `${items.slice(0, -1).join(', ')} or ${items[items.length - 1]}`;
}

/** The plain question for a field no file states; a choice field names its allowed values, as the server sends them. */
export function fieldAsk(path: string, allowed?: readonly unknown[] | null): string {
  const lead = CHOICE_ASK[path];
  const values = (allowed ?? []).filter((v) => typeof v === 'string' && v !== '');
  if (lead && values.length > 1) return `${lead} ${orList(values.map(valueWords))}?`;
  return FIELD_ASK[path] ?? `What is the ${fieldNoun(path)}?`;
}

/** The allowed values the server sent for a question's field, if any. */
function allowedOf(q: LocalQuestion): readonly unknown[] | null {
  return q.allowed_values ?? q.display.value_rule?.allowed ?? null;
}

/**
 * What a confirm question can be answered with, from the server's own flags: `no_value` (no target carries a value:
 * the question asks for one), `unfit` (every target's value is missing or one its field refuses: nothing to
 * confirm), else `value` (there is a value read from the files to confirm, for some targets at least).
 * `distinct_extracted_values` is NOT this: it is empty whenever any one target lacks a value.
 */
export function confirmShape(q: LocalQuestion): 'no_value' | 'unfit' | 'value' {
  if (q.no_value) return 'no_value';
  const total = q.targets.length;
  const without = withoutValue(q);
  const unfit = q.targets_with_an_unfit_value ?? 0;
  if (total > 0 && without >= total) return 'no_value';
  if (total > 0 && unfit > 0 && without + unfit >= total) return 'unfit';
  return 'value';
}

/** How many of a confirm question's targets carry no value: the question's own count, else the one the page's
 *  server counts for every confirm question (`display.targets_without_a_value`). */
function withoutValue(q: LocalQuestion): number {
  return q.targets_without_a_value ?? q.display.targets_without_a_value ?? 0;
}

/** A confirmed value asked again because the instrument clock's time zone changed after it was confirmed. */
const CLOCK_ZONE_CHANGED = 'clock_zone_changed_after_confirmation';

const ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'];

/** A filename position in words: 1 → "first", -1 → "last". */
export function positionWords(p: number): string {
  if (p === -1) return 'last';
  return ORDINALS[p - 1] ?? `${p}th`;
}

/** The counter question in plain words, from its positions. */
export function counterAsk(positions: number[]): string {
  if (positions.length === 1) return `Is the ${positionWords(positions[0])} number in these file names a repeat counter?`;
  return 'Are any of these numbers in the file names repeat counters?';
}

/**
 * One example file name for the counter question, read from the server's own wording ("e.g. the 1st token:
 * [03]_01_JK3_…"): the whole name, and the part asked about. `null` when the wording carries none.
 */
export function counterExample(text: string | null | undefined): { name: string; part: string } | null {
  if (!text) return null;
  const m = /([^\s(),]*)\[([^\]\s]+)\]([^\s(),]*)/.exec(text);
  if (!m) return null;
  return { name: `${m[1]}${m[2]}${m[3]}`, part: m[2] };
}

/**
 * The plain lead for a question card, or `null` to show the server's own text. Never states a value or a count:
 * those stay in the card's own controls and facts.
 */
export function plainQuestion(q: LocalQuestion): string | null {
  const path = q.target_field_path;
  switch (q.kind) {
    case 'missing_value':
      return path ? `${fieldAsk(path, allowedOf(q))} None of your files say.` : null;
    case 'confirm_value': {
      // nothing is asked of an informational one: the server's own words say so ("For information only: …")
      if (!path || q.informational) return null;
      const shape = confirmShape(q);
      if (q.reason === CLOCK_ZONE_CHANGED) {
        // the server: under the zone now recorded the local time is no single instant, "nothing to confirm"
        return shape === 'value'
          ? `Is the ${fieldNoun(path)} right under the time zone now recorded?`
          : `${fieldAsk(path)} Under the clock’s time zone now recorded, the time in your files is not a single ` +
              'moment, so there is nothing to confirm. Give it in UTC.';
      }
      if (shape === 'no_value') return `${fieldAsk(path, allowedOf(q))} Your files mention it, but not as a value a record can hold.`;
      if (shape === 'unfit') return `${fieldAsk(path, allowedOf(q))} The value read from your files does not fit this field.`;
      return `Is the ${fieldNoun(path)} read from your files right?`;
    }
    case 'resolve_conflict':
      return path ? `Your files disagree about the ${fieldNoun(path)}. Which is right?` : 'Your files disagree here. Which is right?';
    case 'naming_counter_positions':
      return counterAsk((q.positions ?? []).length > 0 ? (q.positions ?? []) : [1]);
    case 'clock_time_zone':
      return 'What time zone was the instrument clock set to?';
    case 'confirm_absorber':
      return 'Which element and absorption edge were measured?';
    case 'optional_values':
      return 'Some optional details are not in your files. Fill in any you know.';
    default:
      return null;
  }
}

/**
 * The sample a per-sample question is asked for, in the files' own spelling where the server's wording gives it
 * ("… with the same sample reading (sample name 'JK1', sample or electrode number '06', as the files write it)"),
 * else from its `partition` (`sample={"sample_name": "jk1", …}`). `null` for a question not asked per sample.
 */
export function sampleLabel(q: LocalQuestion): string | null {
  const partition = q.partition ?? '';
  if (!partition.startsWith('sample=')) return null;
  const raw = partition.slice('sample='.length);
  if (raw === 'unrecorded') return 'Groups whose files name no sample';
  const said = /sample reading \((.+?), as the files write it\)/.exec(q.display.text ?? q.text);
  let pairs: [string, string][] = [];
  if (said) {
    pairs = Array.from(said[1].matchAll(/([a-z][a-z ]*?) '([^']*)'/g), (m) => [m[1].trim().replace(/ /g, '_'), m[2]]);
  }
  if (pairs.length === 0) {
    try {
      const obj = JSON.parse(raw) as Record<string, unknown>;
      pairs = Object.entries(obj)
        .filter(([, v]) => v !== null && v !== undefined && v !== '')
        .map(([k, v]) => [k, String(v)]);
    } catch {
      return `Sample ${raw}`;
    }
  }
  const get = (k: string) => pairs.find(([key]) => key === k)?.[1];
  const name = get('sample_name');
  const number = get('sample_or_electrode_number');
  const rest = pairs.filter(([k]) => k !== 'sample_name' && k !== 'sample_or_electrode_number').map(([, v]) => v);
  const parts = [name, number ? `no. ${number}` : undefined, ...rest].filter((x): x is string => !!x);
  return parts.length > 0 ? `Sample ${parts.join(', ')}` : 'Sample (no name in the files)';
}

/** Kinds whose per-group copies are the same question asked of each group, so one card can ask it once. */
const REPEATED_PER_GROUP = new Set(['missing_value', 'confirm_value', 'resolve_conflict']);

/**
 * The key that puts the same question, asked once per sample or once per group, on one card; `null` for a question
 * asked once. "Once per sample": a beamtime question split by the sample its files name (`partition`). "Once per
 * group": the same field asked of one group at a time (a `group:` scope); a confirm question with a value to
 * confirm and one without are asked differently, so they are never on one card.
 */
export function repeatKey(q: LocalQuestion): string | null {
  const path = q.target_field_path;
  if (!path) return null;
  if (q.kind === 'missing_value' && (q.partition ?? '').startsWith('sample=') && q.scope === 'experiment') {
    return `sample|${q.kind}|${path}`;
  }
  if (REPEATED_PER_GROUP.has(q.kind) && q.scope.startsWith('group:')) {
    const valued = q.kind === 'confirm_value' ? `|${q.informational ? 'informational' : confirmShape(q)}` : '';
    return `group|${q.kind}|${path}${valued}`;
  }
  return null;
}

/** One card's worth of questions: a question alone, or the same question asked per sample or per group. */
export type QuestionCluster = { by: 'sample' | 'group'; questions: LocalQuestion[] };

/**
 * The questions in page order, with each repeated question gathered where its first one stood: a single question
 * stays alone, two or more sharing `repeatKey` become one cluster. Every question appears exactly once.
 */
export function clusterRepeats(questions: LocalQuestion[]): (LocalQuestion | QuestionCluster)[] {
  const counts = new Map<string, number>();
  for (const q of questions) {
    const k = repeatKey(q);
    if (k) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const out: (LocalQuestion | QuestionCluster)[] = [];
  const at = new Map<string, QuestionCluster>();
  for (const q of questions) {
    const k = repeatKey(q);
    if (k && (counts.get(k) ?? 0) > 1) {
      const cluster = at.get(k);
      if (cluster) cluster.questions.push(q);
      else {
        const fresh: QuestionCluster = { by: k.startsWith('sample|') ? 'sample' : 'group', questions: [q] };
        at.set(k, fresh);
        out.push(fresh);
      }
    } else {
      out.push(q);
    }
  }
  return out;
}

/** How many different groups (or samples) a cluster's questions are for: a group can hold several disagreements
 *  about one field, each its own question, so this is not the number of questions. */
export function clusterSize(cluster: QuestionCluster): number {
  const key = (q: LocalQuestion) => (cluster.by === 'sample' ? (q.partition ?? q.question_id) : q.scope);
  return new Set(cluster.questions.map(key)).size;
}

/**
 * What a disagreement is about, from its own conflict (`display.conflict`): its subject where that names something
 * other than the field asked about, else its readings ("10 or 20"). `null` for any other question.
 */
export function conflictSubject(q: LocalQuestion): string | null {
  const cf = q.display.conflict;
  if (q.kind !== 'resolve_conflict' || !cf) return null;
  if (cf.subject && cf.subject !== q.target_field_path) return cf.subject;
  if (cf.readings.length > 0) return orList(cf.readings.map((r) => `“${r}”`));
  return cf.subject ?? null;
}

/**
 * The row titles of a cluster, one per question in order, each telling its row apart: the group or sample, then —
 * where one group holds more than one of the questions — the disagreement's own subject. Two rows that would still
 * read alike are numbered.
 */
export function clusterRowLabels(cluster: QuestionCluster, base: (q: LocalQuestion) => string): string[] {
  const qs = cluster.questions;
  const bases = qs.map(base);
  const repeats = new Map<string, number>();
  for (const b of bases) repeats.set(b, (repeats.get(b) ?? 0) + 1);
  const labels = qs.map((q, i) => {
    const subject = (repeats.get(bases[i]) ?? 0) > 1 ? conflictSubject(q) : null;
    return subject ? `${bases[i]}: ${subject}` : bases[i];
  });
  const seen = new Map<string, number>();
  const total = new Map<string, number>();
  for (const l of labels) total.set(l, (total.get(l) ?? 0) + 1);
  return labels.map((l) => {
    if ((total.get(l) ?? 0) < 2) return l;
    const n = (seen.get(l) ?? 0) + 1;
    seen.set(l, n);
    return `${l} (${n} of ${total.get(l)})`;
  });
}

// --- what changes how to answer ------------------------------------------------------------------

/** An answer as the asked-again line quotes it. */
function answeredWords(v: unknown): string {
  if (typeof v === 'string') return `“${v}”`;
  try {
    return JSON.stringify(v) ?? String(v);
  } catch {
    return String(v);
  }
}

/**
 * Every instruction or warning in a question's server wording that changes HOW to answer it, in plain words and
 * with nothing dropped or softened. Read from the question's structured fields; shown beside the title, never
 * behind Details. Empty when there is none.
 */
export function questionWarnings(q: LocalQuestion): string[] {
  const out: string[] = [];
  const groups = Object.keys(q.per_scope_targets ?? {}).length;
  if (q.partition === 'sample=unrecorded' && q.scope === 'experiment' && groups > 1) {
    out.push(
      'The files of these groups name no sample, so they may be different samples. Give one answer for all of them ' +
        'only if they are all the same sample. Otherwise answer each group on its own.',
    );
  }
  if (q.answers_differ) {
    out.push(
      'Answers already given for this field in other groups differ. Answer each group on its own, unless they ' +
        'really are all the same.',
    );
  }
  const again = q.asked_again ?? [];
  if (again.length > 0) {
    const distinct = new Map<string, { answered: unknown; reason: string | null | undefined; field?: string; n: number }>();
    for (const a of again) {
      const k = JSON.stringify([a.answered ?? null, a.field ?? null, a.reason ?? null]);
      const cur = distinct.get(k);
      if (cur) cur.n += 1;
      else distinct.set(k, { answered: a.answered, reason: a.reason, field: a.field, n: 1 });
    }
    const parts = Array.from(distinct.values())
      .slice(0, 3)
      .map((x) => `${answeredWords(x.answered)}${x.field ? ` for the ${fieldNoun(x.field)}` : ''}${x.reason ? ` (${x.reason})` : ''}`);
    const more = distinct.size > 3 ? `, and ${distinct.size - 3} other answer${distinct.size - 3 === 1 ? '' : 's'}` : '';
    out.push(
      `Asked again: ${again.length === 1 ? '1 answer' : `${again.length} answers`} already given here cannot go into ` +
        `the record: ${parts.join('; ')}${more}. Answer again with a value the record can take.`,
    );
  }
  if (q.reason === CLOCK_ZONE_CHANGED) {
    out.push(
      'The instrument clock’s time zone was changed after this was confirmed, so that confirmation no longer counts.' +
        (confirmShape(q) === 'value' ? ' Confirm it again, or correct it.' : ''),
    );
  }
  if (q.kind === 'confirm_value' && !q.informational && confirmShape(q) === 'value') {
    const total = q.targets.length;
    const without = withoutValue(q);
    const unfit = q.targets_with_an_unfit_value ?? 0;
    if (without > 0) {
      out.push(
        `No value was read from your files for ${without} of the ${total} asked about here, so those cannot be ` +
          'confirmed. Give their value one group at a time.',
      );
    }
    if (unfit > 0) {
      out.push(
        `For ${unfit} of the ${total} asked about here, the value read from your files does not fit this field, so ` +
          'those cannot be confirmed. Give their value one group at a time.',
      );
    }
  }
  return out;
}

/** The title a question's card carries: its plain lead, else the server's own words. */
export function cardTitle(q: LocalQuestion): string {
  return plainQuestion(q) ?? q.display.text ?? q.text;
}

// --- groups --------------------------------------------------------------------------------------

/** `{group_id: name}` as the server sends it (`group_names`): each group's first member file. */
export type GroupNames = Readonly<Record<string, string>>;

/** A group in the words a scientist knows it by: its name, else its first file. Only a server that sends neither
 *  (an older one) leaves the id as the one thing that tells two groups apart. */
export function groupName(id: string | null | undefined, names: GroupNames, runNames?: string[]): string {
  if (id && names[id]) return names[id];
  if (runNames && runNames.length > 0) return runNames[0];
  return id ? `group ${id}` : 'a group';
}

/** A scope (a group, a run, or the whole beamtime) by name. */
export function scopeName(sc: Pick<LocalScope, 'kind' | 'group_id' | 'run_names' | 'label'> & { scope?: string }, names: GroupNames): string {
  if (sc.kind === 'experiment' || sc.scope === 'experiment') return 'The whole beamtime';
  const id = sc.group_id ?? (sc.scope?.startsWith('group:') ? sc.scope.slice('group:'.length) : undefined);
  if (sc.kind === 'group' || id) {
    if (id && names[id]) return names[id];
    if (sc.run_names.length > 0) return sc.run_names[0];
    return sc.label;
  }
  return sc.run_names[0] ?? sc.label;
}

/** A minimum's scope (`group:<id>`, `run:<id>`) by name, or null for the question as asked. */
export function onlyName(only: string | null, names: GroupNames): string | null {
  if (!only) return null;
  if (only.startsWith('group:')) return groupName(only.slice('group:'.length), names);
  if (only.startsWith('run:')) return `one run (${only.slice('run:'.length)})`;
  return only;
}

// --- counts --------------------------------------------------------------------------------------

function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;
}

/** The open questions in one plain line: "110 answers block a record. 485 are optional." */
export function countLine(c: { blocking?: number; conflicts_affecting_a_record?: number; optional?: number }): string {
  const blocking = c.blocking ?? 0;
  const conflicts = c.conflicts_affecting_a_record ?? 0;
  const optional = c.optional ?? 0;
  return [
    `${plural(blocking, 'answer blocks', 'answers block')} a record.`,
    ...(conflicts > 0 ? [`${plural(conflicts, 'disagreement changes', 'disagreements change')} a record.`] : []),
    `${optional.toLocaleString('en-US')} ${optional === 1 ? 'is' : 'are'} optional.`,
  ].join(' ');
}

/** Why groups cannot become records, one plain sentence per reason (`cannot_export.by_reason`). */
export function cannotExportLines(byReason: Record<string, number>): string[] {
  return Object.entries(byReason).map(([reason, n]) => {
    const groups = plural(n, 'group', 'groups');
    if (reason === 'processing_not_applicable:no_xas_channel') {
      return `${groups} ${n === 1 ? 'has' : 'have'} no absorption signal ISAAC can read.`;
    }
    if (reason === 'no_scans') return `${groups} ${n === 1 ? 'has' : 'have'} no scans.`;
    if (reason === 'not_a_measurement_run') {
      return `${groups} ${n === 1 ? 'holds' : 'hold'} only reference, alignment or calibration scans.`;
    }
    if (reason.startsWith('processing_not_applicable:')) {
      return `${groups} ${n === 1 ? 'has' : 'have'} data ISAAC cannot process yet.`;
    }
    return `${groups} cannot become ${n === 1 ? 'a record' : 'records'} as ${n === 1 ? 'it stands' : 'they stand'}.`;
  });
}


/** One earlier beamtime's answer, in plain words, with the text "Use this" puts in the answer box. */
export interface EarlierAnswerLine {
  text: string;
  /** The value as the answer box holds it. */
  answer: string;
  entryId: string;
  field: string;
}

/**
 * THE EARLIER ANSWERS of a question (the opt-in answer memory): each said as the server says it ("Earlier answer:
 * pellet — Angel, 17 Nov 2026, beamtime … (same sample JK3)"), the field named first when the card asks several
 * fields, and one plain sentence when earlier beamtimes answered differently. A hint, never an answer: nothing here
 * is recorded, and no value is chosen for the person.
 */
export function earlierAnswerLines(q: LocalQuestion): { lines: EarlierAnswerLine[]; disagree: string | null } {
  const earlier: LocalEarlierAnswer[] = q.display.earlier_answers ?? [];
  const several = new Set(earlier.map((e) => e.field)).size > 1 || q.kind === 'optional_values';
  const lines = earlier.map((e) => ({
    text: several ? `${capitalised(fieldNoun(e.field))}: ${e.said}` : e.said,
    answer: typeof e.value === 'string' ? e.value : JSON.stringify(e.value),
    entryId: e.entry_id,
    field: e.field,
  }));
  const differ = [...new Set(earlier.filter((e) => e.disagrees).map((e) => e.field))];
  const disagree =
    differ.length === 0
      ? null
      : `Earlier beamtimes gave different answers for the ${differ.map((f) => fieldNoun(f)).join(' and the ')}. Choose the one that applies here, or give your own; none is picked for you.`;
  return { lines, disagree };
}

function capitalised(s: string): string {
  return s.length > 0 ? s[0].toUpperCase() + s.slice(1) : s;
}
