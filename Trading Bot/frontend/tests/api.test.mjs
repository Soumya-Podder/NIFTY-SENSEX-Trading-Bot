import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from '../src/api.ts';

function pendingRequest(t) {
 t.mock.method(globalThis, 'fetch', (_url, { signal }) => new Promise((_resolve, reject) => {
  if (signal.aborted) reject(signal.reason);
  else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
 }));
}

test('a report request retains its deadline when given a cancellation signal', async t => {
 pendingRequest(t);
 const nativeTimeout = AbortSignal.timeout.bind(AbortSignal);
 t.mock.method(AbortSignal, 'timeout', () => nativeTimeout(5));
 // The watchdog makes a missing deadline fail promptly instead of hanging the suite.
 let watchdog;
 try {
  await assert.rejects(Promise.race([
   api('/backtest/reports/example', undefined, new AbortController().signal),
   new Promise((_resolve, reject) => { watchdog = setTimeout(() => reject(new Error('Missing request deadline')), 100); }),
  ]), { name: 'TimeoutError' });
 } finally { clearTimeout(watchdog); }
});

test('switching reports cancels the previous request', async t => {
 pendingRequest(t);
 const controller = new AbortController();
 const request = api('/backtest/reports/old', undefined, controller.signal);
 controller.abort();
 await assert.rejects(request, { name: 'AbortError' });
});

test('an already cancelled request cannot complete', async t => {
 pendingRequest(t);
 await assert.rejects(api('/dashboard', undefined, AbortSignal.abort()), { name: 'AbortError' });
});

test('GET requests use the same-origin API and return the payload', async t => {
 t.mock.method(globalThis, 'fetch', async (url, options) => {
  assert.equal(url, '/api/dashboard');
  assert.equal(options.method, 'GET');
  assert.equal(options.body, undefined);
  return Response.json({ online: true });
 });
 assert.deepEqual(await api('/dashboard'), { online: true });
});

test('archive loading can use a longer deadline without losing cancellation', async t => {
 const deadlines = [];
 const nativeTimeout = AbortSignal.timeout.bind(AbortSignal);
 t.mock.method(AbortSignal, 'timeout', ms => { deadlines.push(ms); return nativeTimeout(ms); });
 pendingRequest(t);
 const controller = new AbortController();
 const request = api('/market/replay/NIFTY?day=2026-10-01&period=5m', undefined, controller.signal, 120000);
 assert.deepEqual(deadlines, [120000]);
 controller.abort();
 await assert.rejects(request, { name: 'AbortError' });
});

test('POST requests preserve JSON and are issued once', async t => {
 const fetch = t.mock.method(globalThis, 'fetch', async (url, options) => {
  assert.equal(url, '/api/backtest/run');
  assert.equal(options.method, 'POST');
  assert.equal(options.headers['Content-Type'], 'application/json');
  assert.equal(options.body, '{"source":"cache"}');
  return Response.json({ id: 'job' });
 });
 assert.deepEqual(await api('/backtest/run', { source: 'cache' }), { id: 'job' });
 assert.equal(fetch.mock.callCount(), 1);
});

test('backend validation messages stay readable', async t => {
 t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Invalid date range' }, { status: 422 }));
 await assert.rejects(api('/backtest/run', {}), /Invalid date range/);
});

test('a non-JSON server failure identifies the endpoint and status', async t => {
 t.mock.method(globalThis, 'fetch', async () => new Response('<html>Internal server error</html>', { status: 502 }));
 await assert.rejects(api('/dashboard'), /dashboard.*502/);
});
