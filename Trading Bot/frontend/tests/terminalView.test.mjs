import test from 'node:test';
import assert from 'node:assert/strict';
import {visibleZones, chartBias, syncSeries, tradeMarkers, volumeChangeMarkers, wheelPriceRange} from '../src/terminalView.ts';

test('price wheel zooms in both directions around the cursor and stays bounded', () => {
 const range = {from: 23000, to: 23400}, anchor = 23100;
 const zoomed = wheelPriceRange(range, anchor, -100);
 assert.ok(zoomed.from > range.from && zoomed.to < range.to);
 assert.ok(Math.abs((anchor-zoomed.from)/(zoomed.to-zoomed.from)-.25) < 1e-8);
 const out = wheelPriceRange(zoomed, anchor, 100);
 assert.ok(Math.abs(out.from-range.from) < 1e-8 && Math.abs(out.to-range.to) < 1e-8);
 assert.equal(wheelPriceRange({from: 1, to: 1}, 1, 100), null);
 assert.equal(wheelPriceRange(range, anchor, NaN), null);
 assert.ok(wheelPriceRange({from: .01, to: .02}, .01, 1000).from > 0);
});

test('volume markers identify contract changes without repeating every candle', () => {
 const bars = [{time: 1, contract_id: 'NSE:1', expiry: '2026-09-29'}, {time: 2, contract_id: 'NSE:1', expiry: '2026-09-29'},
  {time: 3, contract_id: 'NSE:2', expiry: '2026-10-27'}];
 assert.deepEqual(volumeChangeMarkers(bars).map(m => m.time), [1, 3]);
 assert.match(volumeChangeMarkers(bars)[1].text, /NSE:2.*2026-10-27/);
});

test('zone layers retain distinct timeframes and cap nearby levels', () => {
 const zones = Array.from({length: 6}, (_, i) => ({id: i, timeframe: '5m', relation: 'SUPPORT', lower: 90-i, upper: 91-i, price: 90.5-i, distance_points: i, available_at: '2026-09-25T10:00:00+05:30'}));
 zones.push({...zones[0], id: 7, timeframe: '4h'});
 assert.deepEqual(visibleZones(zones, ['5m', '4h']).map(z => z.id), [0,1,2,3,4,7]);
 assert.equal(visibleZones(zones, ['5m'], 10).length, 6);
 assert.equal(visibleZones(zones, ['5m', '4h'], Infinity).length, 7);
 assert.deepEqual(visibleZones(zones, []), []);
});
test('zone depth applies independently to both sides and removes exact duplicate bands only within a timeframe', () => {
 const zones = ['SUPPORT', 'RESISTANCE'].flatMap(relation => Array.from({length: 12}, (_, i) => ({id: `${relation}${i}`, timeframe: '5m', relation, lower: 90+i, upper: 91+i, price: 90.5+i, distance_points: i, available_at: '2026-09-25T10:00:00Z'})));
 zones.push({...zones[0], id: 'duplicate'}, {...zones[0], id: 'invalid', lower: NaN});
 const selected = visibleZones(zones, ['5m', '5m']);
 assert.equal(selected.length, 10);
 assert.ok(selected.some(z => z.label === '5m S5'));
 assert.ok(selected.some(z => z.label === '5m R5'));
 assert.equal(visibleZones(zones, ['5m'], 10).length, 20);
 assert.equal(visibleZones(zones, ['5m'], Infinity).length, 24);
});
test('developing candle cannot change completed-bar directional context', () => {
 const rows = Array.from({length: 25}, (_, i) => ({complete: true, close: 100+i}));
 assert.equal(chartBias(rows).label, 'Bullish alignment');
 assert.deepEqual(chartBias([...rows, {complete: false, close: 0}]), chartBias(rows));
 assert.equal(chartBias(rows.slice(0, 10)).label, 'Insufficient history');
});
test('live updates preserve history; corrections and resets replace it', () => {
 const calls = [], series = {setData: x => calls.push(['set', x]), update: x => calls.push(['update', x])};
 let previous = syncSeries(series, [], [{time: 1, close: 5}, {time: 2, close: 6}]);
 assert.equal(calls[0][0], 'set'); calls.length = 0;
 previous = syncSeries(series, previous, [{time: 1, close: 5}, {time: 2, close: 7}, {time: 3, close: 8}]);
 assert.deepEqual(calls.map(c => c[0]), ['update', 'update']); calls.length = 0;
 syncSeries(series, previous, [{time: 1, close: 4}, {time: 2, close: 7}, {time: 3, close: 8}]);
 assert.equal(calls[0][0], 'set');
});
test('paper markers deduplicate entries and never attach to a missing candle', () => {
 const time = Date.parse('2026-09-25T10:00:00+05:30')/1000;
 const trade = {contract_id: 'NSE:1', entry_ts: '2026-09-25T10:02:00+05:30', exit_ts: '2026-09-25T10:07:00+05:30', option_type: 'PUT'};
 const result = tradeMarkers([{time}], [trade, trade], '5m');
 assert.equal(result.length, 1);
 assert.equal(result[0].time, time);
 assert.equal(result[0].text, 'Paper buy PUT');
});
