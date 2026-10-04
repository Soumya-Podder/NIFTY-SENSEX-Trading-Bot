import test from 'node:test';
import assert from 'node:assert/strict';
import {TerminalZones} from '../src/TerminalZones.ts';

test('reference zones span the viewport even when confirmation is near the latest candle', () => {
 const rectangles = [], marks = [];
 const context = {fillRect: (...args) => rectangles.push(args), strokeRect() {}, setLineDash() {},
  beginPath() {}, moveTo: (...args) => marks.push(args), lineTo() {}, stroke() {},
  measureText: () => ({width: 50}), fillText() {}};
 const zones = new TerminalZones();
 zones.attached({chart: {timeScale: () => ({timeToCoordinate: () => 590})},
  series: {priceToCoordinate: price => 300-price}, requestUpdate() {}});
 zones.update([{available_at: '2026-09-25T10:00:00Z', upper: 200, lower: 195,
  price: 197, relation: 'SUPPORT', label: '4H S1'}], [1790326800, 1790330400]);
 // Supply only the theme DOM needed by the canvas renderer.
 const originalDocument = globalThis.document;
 globalThis.document = {documentElement: {dataset: {theme: 'dark'}}};
 try { zones.paneViews()[0].renderer().draw({useMediaCoordinateSpace: fn => fn({context, mediaSize: {width: 600, height: 400}})}); }
 finally { globalThis.document = originalDocument; }
 assert.deepEqual(rectangles[0], [0, 100, 600, 5]);
 assert.deepEqual(marks[0], [590, 96]);
});

test('dense levels keep all bands but consolidate labels inside the visible pane in both themes', () => {
 const originalDocument = globalThis.document;
 try { for (const theme of ['dark', 'light']) {
  const bands = [], labels = [];
  const context = {fillRect: (...args) => { if (args[2] === 600) bands.push(args); }, strokeRect() {}, setLineDash() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, measureText: () => ({width: 100}), fillText: (...args) => labels.push(args)};
  const zones = new TerminalZones();
  zones.attached({chart: {timeScale: () => ({timeToCoordinate: () => 590})}, series: {priceToCoordinate: price => 300-price}, requestUpdate() {}});
  zones.update(Array.from({length: 80}, (_, i) => ({available_at: '2026-09-25T10:00:00Z', upper: 290-i*2, lower: 289-i*2, price: 289.5-i*2, relation: 'SUPPORT', label: `5m S${i+1}`})), [1790326800, 1790330400]);
  globalThis.document = {documentElement: {dataset: {theme}}};
  zones.paneViews()[0].renderer().draw({useMediaCoordinateSpace: fn => fn({context, mediaSize: {width: 600, height: 200}})});
  assert.equal(bands.length, 80);
  assert.ok(labels.length < 80);
  assert.ok(labels.some(([text]) => text.includes('+')));
  for (let i = 0; i < labels.length; i++) {
   assert.ok(labels[i][2] >= 14 && labels[i][2] <= 195);
   if (i) assert.ok(labels[i][2]-labels[i-1][2] >= 20);
  }
 } } finally { globalThis.document = originalDocument; }
});
