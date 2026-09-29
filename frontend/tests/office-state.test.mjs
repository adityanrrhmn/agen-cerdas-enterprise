import assert from 'node:assert/strict';
import test from 'node:test';
import { officeStates } from '../src/components/office-state.ts';
const summary = { campaign: { status: 'RUNNING' }, counts: { pass: 0, review: 0, block: 0 } };
const lead = { lead_id: 'L-1', stage: 'writing', task_status: 'RUNNING', email_status: '' };
const now = Date.parse('2026-09-29T12:00:00Z');
const event = { sender: 'security', lead_id: 'L-1', performative: 'PASS', ts: '2026-09-29T11:59:59Z' };
test('only running lead stages animate work; checkpoints and held work do not', () => {
  assert.equal(officeStates(summary, [lead], [], now).writer.mode, 'working');
  const held = officeStates(summary, [{ ...lead, task_status: 'HELD' }], [], now);
  assert.equal(held.writer.mode, 'idle');
  assert.equal(held.orchestrator.mode, 'review');
  assert.equal(officeStates(summary, [{ ...lead, stage: 'enriched' }], [], now).enrichment.mode, 'idle');
});
test('paused, unavailable and completed campaigns never display working agents', () => {
  for (const status of ['PAUSED', 'COMPLETED', 'DRAFT']) {
    const result = officeStates({ ...summary, campaign: { status } }, [lead], [event], now);
    assert.ok(Object.values(result).every(s => s.mode !== 'working' && s.mode !== 'recent'));
  }
  assert.equal(officeStates(summary, [lead], [], now, true).writer.mode, 'unknown');
  assert.equal(officeStates(summary, null, [], now).writer.mode, 'unknown');
});
test('security acknowledgement belongs to this campaign and expires', () => {
  assert.equal(officeStates(summary, [lead], [event], now).security.mode, 'recent');
  assert.equal(officeStates(summary, [lead], [{ ...event, lead_id: 'OTHER' }], now).security.mode, 'idle');
  assert.equal(officeStates(summary, [lead], [event], now + 4000).security.mode, 'idle');
});
test('human approval is shown as waiting, never as agent work', () => {
  const result = officeStates(summary, [{ ...lead, task_status: 'DONE', email_status: 'AWAITING_APPROVAL' }], [], now);
  assert.equal(result.security.mode, 'review');
  assert.equal(result.writer.mode, 'idle');
});
