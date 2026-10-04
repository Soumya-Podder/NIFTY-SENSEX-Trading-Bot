import assert from 'node:assert/strict';
import { test } from 'node:test';
import { levelsForPeriod, STRUCTURE_PERIODS } from '../src/marketStructureView.ts';

const zone = (id, relation, distance, period='2m') => ({id, relation, distance_points:distance,
 timeframe:period, price:100+distance, lower:99+distance, upper:101+distance, available_at:'2026-09-25T10:00:00+05:30'});

test('dense support does not crowd out resistance; markers are nearest first per timeframe', () => {
 const input=[...Array.from({length:8}, (_,i)=>zone(`s${i}`, 'SUPPORT',i+1)),
  zone('r', 'RESISTANCE',30), zone('other', 'RESISTANCE',1,'4h')];
 const before=JSON.stringify(input);
 const levels=levelsForPeriod(input,'2m');
 assert.deepEqual(levels.map(z=>z.marker),['S1','S2','S3','R1']);
 assert.equal(levels[3].id,'r');
 assert.equal(JSON.stringify(input), before);
 assert.equal(levelsForPeriod(input,'4h')[0].id,'other');
});

test('unknown, duplicate and nonfinite levels do not produce invented marks', () => {
 const z=zone('a','SUPPORT',2);
 assert.equal(levelsForPeriod([z,{...z,id:'duplicate'}, {...z,id:'invalid',price:NaN}],'2m').length,1);
 assert.deepEqual(levelsForPeriod([], '4h'), []);
 assert.deepEqual(STRUCTURE_PERIODS,['2m','5m','15m','30m','1h','2h','4h','1d']);
});

test('Agentic five-level selection uses exactly the chart bands including inside zones', async () => {
 const { visibleZones } = await import('../src/terminalView.ts');
 const input = [...Array.from({length:8}, (_,i)=>zone(`s${i}`, 'SUPPORT',i+1)), zone('inside','AT_ZONE',0)];
 const chart = visibleZones(input,['2m'],5);
 const evidence = levelsForPeriod(input,'2m',5);
 assert.deepEqual(evidence.map(z=>z.id),chart.map(z=>z.id));
 assert.equal(evidence.at(-1).marker,'Z1');
 assert.equal(evidence.filter(z=>z.relation==='SUPPORT').length,5);
});
