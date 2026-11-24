import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { FIXTURES } from './helpers.js';
import { describeAnswer, pickRun, tally, isStale, standing, shortcutAllowed } from '../public/logic.js';

const cards = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'site-data.json'), 'utf8')).cards;
const byId = Object.fromEntries(cards.map((c) => [c.card_id, c]));

test('the next sitting is the needed questions first, in the site\'s order, and never one already answered', () => {
  assert.deepEqual(pickRun(cards, {}, 3), ['C-0000000001', 'C-0000000002', 'C-0000000003']);
  const answers = { 'C-0000000001': { action: 'accept', value: 'HERFD-XAS' }, 'C-0000000003': { action: 'dont_know' } };
  assert.deepEqual(pickRun(cards, answers, 3), ['C-0000000002', 'C-0000000004', 'C-0000000005']);
  const allNeeded = Object.fromEntries(cards.filter((c) => c.blocking).map((c) => [c.card_id, { action: 'dont_know' }]));
  assert.deepEqual(pickRun(cards, allNeeded, 10), ['C-0000000008', 'C-0000000009'], 'then the nice-to-have ones');
  assert.deepEqual(pickRun(cards, Object.fromEntries(cards.map((c) => [c.card_id, {}])), 10), []);
});

test('progress counts needed and nice-to-have questions apart', () => {
  const t = tally(cards, { 'C-0000000001': {}, 'C-0000000002': { action: 'dont_know' }, 'C-0000000008': {} });
  assert.deepEqual([t.needed, t.neededDone, t.neededUnsure, t.neededOpen, t.optional, t.optionalDone, t.open], [7, 2, 1, 5, 2, 1, 6]);
});

test('a saved answer is shown in the words it was chosen in', () => {
  assert.equal(describeAnswer(byId['C-0000000001'], { action: 'accept', value: 'HERFD-XAS' }), 'HERFD-XAS');
  assert.equal(describeAnswer(byId['C-0000000005'], { action: 'value', value: 'thin_film' }), 'thin film');
  assert.equal(describeAnswer(byId['C-0000000008'], { action: 'value', value: 1.25, typed: true }), '1.25 V');
  assert.equal(describeAnswer(byId['C-0000000008'], { action: 'accept', value: 1.2 }), '1.2 V');
  assert.equal(describeAnswer(byId['C-0000000009'], { action: 'value', value: false }), 'No');
  assert.equal(describeAnswer(byId['C-0000000002'], { action: 'dont_know', value: null }), 'Don’t know');
  assert.equal(describeAnswer(byId['C-0000000007'], { action: 'value', value: 'settling' }), 'Settling: drop the first scan, keep the later ones');
});

test('an accepted suggestion that has since changed is an open question again', () => {
  const c = byId['C-0000000001'];
  const old = { action: 'accept', value: 'XRD' };
  assert.equal(isStale(c, old), true);
  assert.equal(isStale(c, { action: 'accept', value: 'HERFD-XAS' }), false);
  assert.equal(isStale(c, { action: 'value', value: 'XRD' }), false, 'a value the person picked stands whatever the suggestion says');
  assert.equal(isStale(byId['C-0000000002'], { action: 'accept', value: 'x' }), true, 'the suggestion was removed');
  assert.equal(standing(c, { 'C-0000000001': old }), null);
  assert.equal(pickRun(cards, { 'C-0000000001': old }, 1)[0], 'C-0000000001', 'it is asked again');
  assert.equal(tally(cards, { 'C-0000000001': old }).neededDone, 0, 'and not counted as done');
});

test('a single key never acts on a card that is mid-typing, just redrawn, saving, or already answered', () => {
  const base = { key: 'y', enabled: true, busy: false, msSinceRender: 5000, typedText: '', noteText: '', hasAnswer: false };
  assert.equal(shortcutAllowed(base), true);
  assert.equal(shortcutAllowed({ ...base, enabled: false }), false, 'shortcuts can be turned off');
  assert.equal(shortcutAllowed({ ...base, busy: true }), false);
  assert.equal(shortcutAllowed({ ...base, msSinceRender: 100 }), false, 'a key meant for the last card');
  assert.equal(shortcutAllowed({ ...base, typedText: 'abc' }), false, 'something is typed');
  assert.equal(shortcutAllowed({ ...base, noteText: 'a note' }), false);
  assert.equal(shortcutAllowed({ ...base, hasAnswer: true }), false, 'yes never replaces a standing answer');
  assert.equal(shortcutAllowed({ ...base, key: 'd', hasAnswer: true }), false, "nor does don't know");
  assert.equal(shortcutAllowed({ ...base, key: 's', hasAnswer: true }), true, 'skipping changes nothing, so it is allowed');
});

test('someone else’s answers come after the open cards, until they are kept', async () => {
  const { byOther, keptKey } = await import('../public/logic.js');
  const cards = [
    { card_id: 'C-1', blocking: true },
    { card_id: 'C-2', blocking: true },
    { card_id: 'C-3', blocking: false },
  ];
  const theirs = { card_id: 'C-1', action: 'value', value: 'x', by: 'Krish Verma', at: '2026-11-23T10:00:00.000Z' };
  const answers = { 'C-1': theirs };
  assert.deepEqual(pickRun(cards, answers, 10), ['C-2', 'C-3'], 'without a name, nothing changes');
  assert.deepEqual(pickRun(cards, answers, 10, 'Angel'), ['C-2', 'C-3', 'C-1'], 'open cards first, then theirs');
  assert.deepEqual(pickRun(cards, answers, 10, '  krish   verma '), ['C-2', 'C-3'], 'my own answers are not offered again');
  assert.deepEqual(pickRun(cards, answers, 10, 'Angel', new Set([keptKey(theirs)])), ['C-2', 'C-3'], 'kept');
  const newer = { ...theirs, at: '2026-11-24T10:00:00.000Z' };
  assert.deepEqual(pickRun(cards, { 'C-1': newer }, 10, 'Angel', new Set([keptKey(theirs)])), ['C-2', 'C-3', 'C-1'], 'a newer answer asks again');
  const dk = { ...theirs, action: 'dont_know', value: null };
  assert.deepEqual(pickRun(cards, { 'C-1': dk }, 10, 'Angel'), ['C-2', 'C-3', 'C-1'], 'their “don’t know” may be something I know');
  assert.equal(byOther(null, 'Angel'), false);
  assert.equal(byOther(theirs, ''), false);
});

test('replacing someone else’s answer keeps their note under their name', async () => {
  const { carryNote } = await import('../public/logic.js');
  const before = { by: 'Krish Verma', note: 'checked against logbook' };
  assert.equal(carryNote('', before, 'Angel'), 'Earlier note from Krish Verma: checked against logbook');
  assert.equal(carryNote('it was XAS', before, 'Angel'), 'it was XAS\n\nEarlier note from Krish Verma: checked against logbook');
  assert.equal(carryNote('mine', before, 'krish verma'), 'mine', 'my own earlier note is mine to change');
  assert.equal(carryNote('mine', { by: 'Krish', note: '' }, 'Angel'), 'mine');
  assert.equal(carryNote(carryNote('x', before, 'Angel'), before, 'Angel'), carryNote('x', before, 'Angel'), 'not added twice');
  assert.equal(carryNote(' x ', null, 'Angel'), 'x');
});

test('keeping someone else’s answer with a note says who gave the answer', async () => {
  const { carryNote } = await import('../public/logic.js');
  assert.equal(carryNote('agree', { by: 'Krish Verma', note: '' }, 'Angel', true), 'agree\n\nAnswer first given by Krish Verma.');
  assert.equal(carryNote('', { by: 'Krish Verma', note: 'ok' }, 'Angel', true), 'Answer first given by Krish Verma, with the note: ok');
});

test('a carried note is never dropped: the new words give way, and a note inside them is not mistaken for it', async () => {
  const { carryNote, NOTE_MAX } = await import('../public/logic.js');
  const before = { by: 'Krish Verma', note: 'ok' };
  assert.equal(carryNote('looks ok to me', before, 'Angel'), 'looks ok to me\n\nEarlier note from Krish Verma: ok');
  const { noteRoom } = await import('../public/logic.js');
  const room = noteRoom(before, 'Angel');
  assert.equal(room, NOTE_MAX - 'Earlier note from Krish Verma: ok'.length - 2);
  const full = carryNote('a'.repeat(room), before, 'Angel');
  assert.ok(full.length === NOTE_MAX && full.startsWith('a'.repeat(room)) && full.endsWith('Earlier note from Krish Verma: ok'),
    'at the limit both are kept whole (the page refuses a longer note of their own)');
  assert.equal(noteRoom(null, 'Angel'), NOTE_MAX);
  assert.equal(noteRoom({ by: 'Angel', note: 'x' }, 'Angel'), NOTE_MAX, 'my own note is not carried');
  assert.equal(noteRoom({ by: 'K', note: 'b'.repeat(1999) }, 'Angel'), 0);
});
