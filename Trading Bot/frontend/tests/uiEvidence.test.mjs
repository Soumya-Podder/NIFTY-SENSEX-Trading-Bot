import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { transformWithOxc } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
async function component(file) {
 const source = await readFile(new URL(`../src/${file}`, import.meta.url), 'utf8');
 const compiled = (await transformWithOxc(source, file, { jsx: { runtime: 'automatic' } })).code
  .replace(/from "(react(?:\/jsx-runtime)?)"/g, (_, name) => `from ${JSON.stringify(pathToFileURL(require.resolve(name)).href)}`);
 return import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
}
const { MarketEvidence } = await component('MarketEvidence.tsx');
const { default: AutonomyStatus } = await component('AutonomyStatus.tsx');
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));

test('missing outcome estimates do not create a second empty probability or zone panel', () => {
 assert.equal(render(MarketEvidence, {}), '');
 assert.equal(render(MarketEvidence, { estimate: { estimates: {}, samples: 0 } }), '');
});

test('unique historical outcome estimates remain available without duplicating chart levels', () => {
 const markup = render(MarketEvidence, { estimate: {
  estimates: { UP: { estimate: .6, low: .4, high: .8 }, DOWN: { estimate: .3, low: .1, high: .5 } },
  samples: 35, minimum_sessions: 30, source: 'LAST_HISTORICAL_SCOPE',
  as_of: '2026-10-01T10:00:00+05:30',
  scope: { strategy_version: 'observed-v1', option_type: 'PUT', regime: 'TREND', horizon_minutes: 15 },
 } });
 assert.match(markup, /60\.0%/);
 assert.match(markup, /30\.0%/);
 assert.match(markup, /95% interval/);
 assert.match(markup, /Historical example/);
 assert.match(markup, /not a calibrated forecast/);
 assert.doesNotMatch(markup, /support &amp; resistance|<svg|Target first|Actual net profit/);
});

test('agent status omits an empty position panel but preserves management decisions and learning errors', () => {
 const data = { strategies: [], learning: {}, monthly_net_objective: 18000, management: {} };
 assert.doesNotMatch(render(AutonomyStatus, { data }), /Position management|No open position/);
 const markup = render(AutonomyStatus, { data: { ...data, learning_error: 'worker stopped',
  management: { NIFTY: { action: 'EXIT', reason: 'Session liquidation requested' } } } });
 assert.match(markup, /Position management/);
 assert.match(markup, /Session liquidation requested/);
 assert.match(markup, /worker stopped/);
});
