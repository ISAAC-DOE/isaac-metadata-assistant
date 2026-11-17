/**
 * PLAIN WORDS FOR THE LOCAL IMPORTS QUESTIONS (2026-11-17, owner: "the questions page … read[s] like an engineer
 * wrote it").
 *
 * The backend's question text (`apps/api/isaac_api/local_import/questions.py`) is the command line's: the Claude
 * Code skill reads it, and it names field paths, decision names and flags. Those strings are NOT changed. This
 * module gives the site a plain layer on top of them, by question kind and field:
 *
 *   "What is the environment (context.environment)? No source in this import states it. Applies to 90 group(s) …"
 *   → "Was this measured in situ, operando or ex situ? None of your files say."
 *
 * COPY ONLY, and never more than the server said. Each plain line restates what the kind of question already
 * means (a missing value: no file states it; a conflict: the files disagree), so it adds no claim. The server's
 * full wording and the field path stay on the card, behind its "Details" disclosure. A kind this module does not
 * know returns `null`, and the card shows the server's text as it is.
 */
import type { LocalQuestion, LocalScope } from './localImports';

/** How a field is ASKED when no file states it, in the words a scientist would use. Paths read from the schema. */
const FIELD_ASK: Readonly<Record<string, string>> = {
  'context.environment': 'Was this measured in situ, operando or ex situ?',
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

/** The plain question for a field no file states. */
export function fieldAsk(path: string): string {
  return FIELD_ASK[path] ?? `What is the ${fieldNoun(path)}?`;
}

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
      return path ? `${fieldAsk(path)} None of your files say.` : null;
    case 'confirm_value':
      if (!path) return null;
      return q.display.distinct_extracted_values.length > 0
        ? `Is the ${fieldNoun(path)} read from your files right?`
        : `${fieldAsk(path)} Your files mention it, but not as a value a record can hold.`;
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
    const valued = q.kind === 'confirm_value' ? `|${q.display.distinct_extracted_values.length > 0}` : '';
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

