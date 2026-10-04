import assert from 'node:assert/strict';
import { test } from 'node:test';
import { evidenceMetrics, evidenceStamp, evidenceTone, learningGroup, learningSummary, monitorCurrent } from '../src/learningView.ts';

test('a monitor heartbeat requires fresh, connected, healthy backend evidence', () => {
  const now = Date.parse('2026-09-26T13:00:00+05:30');
  const data = { worker_alive: true, stale: false, status: 'MONITORING', checked_at: new Date(now - 60000).toISOString(), training_now: true };
  assert.equal(monitorCurrent(data, true, now), true);
  assert.equal(monitorCurrent(data, false, now), false);
  for (const change of [{ worker_alive: false }, { stale: true }, { status: 'ERROR' }, { checked_at: null },
    { checked_at: new Date(now - 151000).toISOString() }, { checked_at: new Date(now + 60000).toISOString() }]) {
    assert.equal(monitorCurrent({ ...data, ...change }, true, now), false);
  }
  assert.equal(monitorCurrent(undefined, true, now), false);
});

test('failed validation and fixed risk controls cannot appear as successful learning', () => {
  assert.equal(evidenceTone({ status: 'CANDIDATES_REJECTED', fitted_candidates: 3 }), 'blocked');
  assert.equal(evidenceTone({ status: 'TRAINING_ATTEMPTED', validation: 'INSUFFICIENT_SESSIONS' }), 'blocked');
  assert.equal(evidenceTone({ status: 'ACTIVE_VALIDATION_MISSING' }), 'blocked');
  assert.equal(evidenceTone({ status: 'ACTIVE_FORWARD_UNPROVEN' }), 'active');
  assert.equal(evidenceTone({ status: 'NO_EVIDENCE' }), 'waiting');
  const risk = { kind: 'control', learnable: false, status: 'FIXED_NON_LEARNABLE', learning_attempts: 13 };
  assert.equal(evidenceTone(risk), 'fixed');
  assert.equal(learningGroup(risk), 'controls');
  assert.equal(learningGroup({ kind: 'control', learnable: true, id: 'Orchestrator' }), 'specialist');
});

test('counts distinguish model fits, runs and explicit proof without double counting agent activity', () => {
  const summary = learningSummary({ total_training_attempts: 68, agents: [
    { kind: 'entry_model', fitted_candidates: 3, training_attempts: 41, last_evidence_at: '2026-09-23' },
    { kind: 'entry_model', fitted_candidates: 0, training_attempts: 14 },
    { kind: 'intelligence', fitted_candidates: 99, learning_attempts: 13, decision_count: 230, self_improvement_proven: false },
    { kind: 'pipeline', status: 'POLICY_ACTIVE_FORWARD_UNPROVEN', last_evidence_at: '2026-09-20' },
  ] });
  assert.equal(summary.fitted, 3);
  assert.equal(summary.proven, 0);
  assert.equal(summary.withEvidence, 2);
  assert.equal(evidenceMetrics({ kind: 'rules_or_analysis' })[0].value, undefined);
  assert.equal(evidenceMetrics({ kind: 'entry_model', training_attempts: 0 })[0].value, 0);
});

test('poll heartbeats do not become new agent evidence, but actual counts and validation do', () => {
  const agent = { id: 'Momentum Agent', decision_count: 39, outcome_count: 0, status: 'LEARNING_ATTEMPTED', checked_at: 'before' };
  assert.equal(evidenceStamp(agent), evidenceStamp({ ...agent, checked_at: 'after', worker_alive: true }));
  assert.notEqual(evidenceStamp(agent), evidenceStamp({ ...agent, outcome_count: 1 }));
  assert.notEqual(evidenceStamp(agent), evidenceStamp({ ...agent, validation: 'BLOCKED' }));
});
