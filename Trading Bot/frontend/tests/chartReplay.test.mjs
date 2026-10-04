import test from 'node:test';
import assert from 'node:assert/strict';
import {replayFrame, replayCursor, replayDate, replayLoadCursor, replayTime} from '../src/chartReplay.ts';

const start = replayCursor('2026-10-01', '09:15:00');
const iso = offset => new Date((start + offset) * 1000).toISOString();
const minute = (offset, price = 100) => ({time: start + offset, end_time: start + offset + 60,
 open: price, high: price + 2, low: price - 1, close: price + 1, complete: true});
const session = () => ({date: '2026-10-01', period: '2m', start, end: start + 375 * 60,
 history_candles: [], minutes: [minute(0), minute(60, 110), minute(120, 900)],
 observations: [{time: start + 1, minute: start, open: 100, high: 101, low: 99, close: 101},
  {time: start + 2, minute: start, open: 102, high: 105, low: 102, close: 103}],
 zones: [{id: 'confirmed-later', lower: 105, upper: 107, available_at: iso(120)}],
 capture: {disconnects: []}, mode: 'observations', history_days: 365,
 trades: [{entry_ts: iso(2), exit_ts: iso(130), contract_id: 'NSE:1'}],
 volume: {bars: [{...minute(0), value: 500}], contract: {captured_at: iso(0)}}});

test('replay shows only received ticks, not future minute OHLC, zones, exits or volume', () => {
 const data = session();
 const before = replayFrame(data, start);
 assert.equal(before.candles.length, 0);
 assert.equal(before.trades.length, 0);
 const first = replayFrame(data, start + 1);
 assert.equal(first.candles[0].close, 101);
 assert.equal(first.candles[0].high, 101);
 assert.equal(first.structure.zones.length, 0);
 assert.equal(first.volume.bars.length, 0);
 const next = replayFrame(data, start + 2);
 assert.equal(next.candles[0].high, 105);
 assert.equal(next.trades[0].exit_ts, null);
 assert.equal(next.candles[0].complete, false);
 const closed = replayFrame(data, start + 120);
 assert.equal(closed.candles[0].complete, true);
 assert.equal(closed.candles[0].close, 111);
 assert.equal(closed.structure.zones.length, 1);
 assert.equal(closed.structure.zones[0].relation, 'SUPPORT');
 assert.equal(closed.volume.bars.length, 1);
 assert.equal(closed.trades[0].exit_ts, null);
 assert.ok(replayFrame(data, start + 130).trades[0].exit_ts);
 assert.deepEqual(replayFrame(data, start + 1), first, 'seeking backwards restores causal data');
});

test('one-second clock never invents prices during gaps or in candle-only mode', () => {
 const data = session();
 const gap = replayFrame(data, start + 20);
 assert.equal(gap.replay.gap, true);
 assert.equal(gap.candles[0].close, 103);
 data.observations = []; data.mode = 'candles';
 assert.equal(replayFrame(data, start + 59).candles.length, 0);
 assert.equal(replayFrame(data, start + 60).candles[0].close, 101);
 assert.equal(replayFrame(data, start + 61).candles[0].close, 101);
 data.minutes = [minute(0), minute(120)];
 assert.equal(replayFrame(data, start + 120).replay.gap, true);
 assert.equal(replayFrame(data, start + 180).candles[0].complete, false);
});

test('clock bounds, IST selection, disconnects and future volume bars are explicit', () => {
 const data = session();
 assert.equal(replayDate(start), '2026-10-01');
 assert.equal(replayTime(start), '09:15:00');
 assert.equal(replayCursor('2026-10-01', '09:15'), start);
 assert.equal(replayFrame(data, start - 10).replay.cursor, start);
 assert.equal(replayFrame(data, data.end + 10).replay.cursor, data.end);
 data.capture.disconnects = [start + 3];
 assert.equal(replayFrame(data, start + 3).replay.gap, true);
 data.volume.bars[0].contract_id = 'NSE:1'; data.volume.bars[0].expiry = '2026-10-27';
 assert.deepEqual(replayFrame(data, start + 59).volume.contracts, []);
 assert.deepEqual(replayFrame(data, start + 60).volume.contracts, [{contract_id: 'NSE:1', expiry: '2026-10-27'}]);
});

test('timeframe and index changes retain the clock while a different date starts at the open', () => {
 const data = session();
 const previous = {date: data.date, cursor: start + 10800};
 assert.equal(replayLoadCursor({...data, period: '4h', symbol: 'SENSEX'}, previous), previous.cursor);
 assert.equal(replayLoadCursor(data, {...previous, date: '2026-09-30'}), start);
 assert.equal(replayLoadCursor({...data, end: start + 60}, previous), start + 60);
});

test('next price update skips empty seconds without exposing future prices or volume', () => {
 const data = session();
 assert.equal(replayFrame(data, start).replay.next_update, start + 1);
 data.observations = []; data.mode = 'candles';
 assert.equal(replayFrame(data, start + 1).replay.next_update, start + 60);
 assert.equal(replayFrame(data, start + 1).candles.length, 0);
 assert.equal(replayFrame(data, start + 60).volume.bars.length, 1);
 data.minutes = [minute(0), minute(120)];
 assert.equal(replayFrame(data, start + 60).replay.next_update, start + 180);
 assert.equal(replayFrame(data, data.end).replay.next_update, null);
});
