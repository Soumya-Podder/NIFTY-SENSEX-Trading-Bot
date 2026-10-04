import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { transformWithOxc } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { decisionId, decisionKind, recentDecision, registrySummary } from '../src/activityView.ts';

test('only awaiting-review candidates enter the human approval queue', () => {
  const rows = ['AWAITING_REVIEW', 'PROMOTED', 'REJECTED_BY_REVIEW', 'DATA_BLOCKED', 'UNKNOWN'].map(validation_status => ({ validation_status }));
  const summary = registrySummary(rows);
  assert.deepEqual(summary.pending, [rows[0]]);
  assert.deepEqual(summary.approved, [rows[1]]);
  assert.deepEqual(summary.rejected, [rows[2]]);
});

test('system lifecycle and waiting events are not passed trades', () => {
  assert.equal(decisionKind('STARTED'), 'system');
  assert.equal(decisionKind('STOPPED'), 'system');
  assert.equal(decisionKind('WAITING'), 'waiting');
  assert.equal(decisionKind('UNKNOWN'), 'waiting');
  assert.equal(decisionKind('REJECTED'), 'blocked');
  assert.equal(decisionKind('FILLED'), 'passed');
  assert.equal(decisionKind('PASS'), 'passed');
});

test('old, invalid and future event times cannot trigger live arrival animation', () => {
  const now = Date.parse('2026-09-26T14:00:00+05:30');
  assert.equal(recentDecision({ timestamp: new Date(now - 30000).toISOString() }, now), true);
  for (const timestamp of [undefined, 'invalid', new Date(now - 121000).toISOString(), new Date(now + 1000).toISOString()]) {
    assert.equal(recentDecision({ timestamp }, now), false);
  }
  assert.notEqual(decisionId({ timestamp: 't', symbol: 'NIFTY', agent: 'Scanner' }), decisionId({ timestamp: 't', symbol: 'SENSEX', agent: 'Scanner' }));
});

// Render real review controls without a browser or a request to the trading backend.
const require = createRequire(import.meta.url);
const componentSource = await readFile(new URL('../src/LearningRegistry.tsx', import.meta.url), 'utf8');
const compiled = (await transformWithOxc(componentSource, 'LearningRegistry.tsx', { jsx: { runtime: 'automatic' } })).code
  .replace(/from "(react(?:\/jsx-runtime)?|\.\/activityView)"/g, (_match, specifier) => 'from ' + JSON.stringify(specifier === './activityView'
    ? new URL('../src/activityView.ts', import.meta.url).href : pathToFileURL(require.resolve(specifier)).href));
const { default: LearningRegistry } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
const render = (rows, online = true) => renderToStaticMarkup(React.createElement(LearningRegistry, { rows, online, busy: false, onReview() { throw new Error('No review should be sent during rendering'); }, onDetail() {} }));

test('pending candidate actions require a reviewer, and historical approvals have no action buttons', () => {
  const candidate = { agent: 'Setup', version: 2, source_run_id: 'fixture', validation_status: 'AWAITING_REVIEW' };
  const pending = render([candidate]);
  assert.match(pending, /Reviewer name/);
  assert.match(pending, /disabled=""[^>]*>Approve next session/);
  assert.match(pending, /disabled=""[^>]*>Reject/);
  const approved = render([{ ...candidate, validation_status: 'PROMOTED' }]);
  assert.doesNotMatch(approved, /Approve next session/);
  assert.match(approved, /Approved record/);
  assert.match(render([], false), /Review queue is not current/);
});
