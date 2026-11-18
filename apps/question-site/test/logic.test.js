import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { FIXTURES } from './helpers.js';
import { describeAnswer, pickRun, tally } from '../public/logic.js';

const cards = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'site-data.json'), 'utf8')).cards;
const byId = Object.fromEntries(cards.map((c) => [c.card_id, c]));

test('the next sitting is the needed questions first, in the site\'s order, and never one already answered', () => {
  assert.deepEqual(pickRun(cards, {}, 3), ['C-0000000001', 'C-0000000002', 'C-0000000003']);
  const answers = { 'C-0000000001': { action: 'accept' }, 'C-0000000003': { action: 'dont_know' } };
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
