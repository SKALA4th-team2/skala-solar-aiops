/** Selection/portfolio aggregation and read-only operational response contracts. Synthetic values are test-only. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readOperations, createPreviewServer } from './serve-preview.mjs';
const { selectRecords, rmse } = createRequire(import.meta.url)('../../docs/design/solar-ops-v01/dashboard-core.js');
const plants = [
  { id: 'a', records: [{ date: '2025-06-04', measured: 100, predicted: 120, forecastIrradiance: 20 }] },
  { id: 'b', records: [{ date: '2025-06-04', measured: 200, predicted: 170, forecastIrradiance: 30 }] }
];
test('individual selection does not include another plant', () => assert.deepEqual(selectRecords(plants, 'a'), plants[0].records));
test('portfolio sums energy, averages irradiance and computes error after aggregation', () => {
  const records = selectRecords(plants, 'all');
  assert.deepEqual(records, [{ date: '2025-06-04', measured: 300, predicted: 290, forecastIrradiance: 25 }]);
  assert.equal(rmse(records), 10);
});
test('unknown plant and mismatched dates cannot silently produce partial totals', () => {
  assert.throws(() => selectRecords(plants, 'missing'));
  assert.throws(() => selectRecords([plants[0], { id: 'b', records: [] }], 'all'));
});
test('status reader only calls fixed read-only routes and strips unused fields', async () => {
  const calls = [];
  const snapshot = await readOperations('http://localhost:8099', async (url, options) => {
    calls.push(url.pathname);
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal);
    return { ok: true, json: async () => url.pathname === '/health' ? { status: 'ok', model_loaded: false, secret: 'not forwarded' } : { exists: true, rows: 90, start_date: '2025-03-07', end_date: '2025-06-04', filename: 'not forwarded' } };
  });
  assert.deepEqual(calls, ['/health', '/data/status']);
  assert.equal(snapshot.health.modelLoaded, false);
  assert.equal(snapshot.upload.rows, 90);
  assert.ok(!JSON.stringify(snapshot).includes('forwarded'));
});
test('partial failure retains independent successful endpoint; malformed payload is rejected', async () => {
  const partial = await readOperations('http://localhost:8099', async (url) => ({ ok: url.pathname === '/health', json: async () => ({ status: 'ok', model_loaded: true }) }));
  assert.equal(partial.health.ok, true);
  assert.equal(partial.upload.ok, false);
  const malformed = await readOperations('http://localhost:8099', async () => ({ ok: true, json: async () => ({}) }));
  assert.equal(malformed.health.ok, false);
  assert.equal(malformed.upload.ok, false);
});
test('network errors do not leak diagnostics; credentials or arbitrary base paths are rejected', async () => {
  const snapshot = await readOperations('http://localhost:8099', async () => { throw new Error('internal secret'); });
  assert.equal(snapshot.health.ok, false);
  assert.ok(!JSON.stringify(snapshot).includes('secret'));
  assert.throws(() => createPreviewServer('http://user:pass@localhost'));
  assert.throws(() => createPreviewServer('file:///etc/passwd'));
  assert.throws(() => createPreviewServer('http://localhost/other'));
});
test('upload forwards multipart to fixed endpoint, handles rejection, and blocks foreign origins', async (t) => {
  const { default: http } = await import('node:http');
  let reject = false;
  const upstream = http.createServer(async (req, res) => {
    assert.equal(req.url, '/data/upload');
    assert.equal(req.method, 'POST');
    let body = '';
    for await (const chunk of req) body += chunk;
    assert.match(body, /name="file"/);
    assert.match(body, /Date,Close,Volume/);
    res.writeHead(reject ? 400 : 200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(reject ? { detail: 'private diagnostics' } : { rows: 41, filename: 'private.csv' }));
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const preview = createPreviewServer(`http://127.0.0.1:${upstream.address().port}`);
  await new Promise(resolve => preview.listen(0, '127.0.0.1', resolve));
  t.after(() => { upstream.close(); preview.close(); });
  const origin = `http://127.0.0.1:${preview.address().port}`;
  const form = new FormData();
  form.append('file', new Blob(['Date,Close,Volume\n' + '2025-01-01,1,2\n'.repeat(41)]), 'sample.csv');
  const send = (site = origin) => fetch(`${origin}/preview-api/upload`, { method: 'POST', headers: { Origin: site }, body: form });
  assert.deepEqual(await (await send()).json(), { rows: 41 });
  reject = true;
  const rejected = await send();
  assert.equal(rejected.status, 400);
  assert.deepEqual(await rejected.json(), { error: 'invalid_csv' });
  assert.equal((await send('https://foreign.example')).status, 403);
});
test('operation proxy validates batches, limits routes, and reads logs without HTML interpolation', async (t) => {
  const { default: http } = await import('node:http');
  const calls = [];
  const upstream = http.createServer(async (req, res) => {
    calls.push(req.url);
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/predict/batch-test') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      assert.equal(JSON.parse(raw).prices.length, 41);
      res.end(JSON.stringify({ predictions: Array(21).fill(165), drift_check: { status: 'retrain_triggered', promoted: false, rmse: 2, internal: 'omit' } }));
    } else if (req.url === '/logs') res.end(JSON.stringify([{ name: 'aiops.log', size: 10 }, { name: '../invalid', size: 10 }]));
    else if (req.url === '/logs/aiops.log') res.end(JSON.stringify({ content: '<script>not executable</script>' }));
    else res.writeHead(404).end();
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const preview = createPreviewServer(`http://127.0.0.1:${upstream.address().port}`);
  await new Promise(resolve => preview.listen(0, '127.0.0.1', resolve));
  t.after(() => { upstream.close(); preview.close(); });
  const origin = `http://127.0.0.1:${preview.address().port}`;
  const send = (prices, site = origin) => fetch(`${origin}/preview-api/batch-test`, { method: 'POST', headers: { Origin: site, 'Content-Type': 'application/json' }, body: JSON.stringify({ prices }) });
  assert.equal((await send([1])).status, 400);
  assert.equal((await send(Array(41).fill(165), 'https://other.example')).status, 403);
  assert.equal(calls.length, 0);
  const result = await (await send(Array(41).fill(165))).json();
  assert.equal(result.predictions.length, 21);
  assert.deepEqual(result.drift_check, { status: 'retrain_triggered', promoted: false, rmse: 2 });
  assert.deepEqual(await (await fetch(`${origin}/preview-api/logs`)).json(), [{ name: 'aiops.log', size: 10 }]);
  assert.equal((await (await fetch(`${origin}/preview-api/logs/aiops.log`)).json()).content, '<script>not executable</script>');
  assert.equal((await fetch(`${origin}/preview-api/logs/bad%2Fname`)).status, 400);
  assert.deepEqual(calls, ['/predict/batch-test', '/logs', '/logs/aiops.log']);
});
test('saved dashboard routes forward only supported reads and validated single predictions', async (t) => {
  const { default: http } = await import('node:http');
  const calls = [];
  const upstream = http.createServer(async (req, res) => {
    calls.push(req.url); res.setHeader('Content-Type', 'application/json');
    if (req.url === '/preview-api/dashboard/predict') {
      let raw = ''; for await (const chunk of req) raw += chunk;
      assert.equal(JSON.parse(raw).history.length, 24);
      assert.equal(JSON.parse(raw).forecast.length, 24);
      res.end(JSON.stringify({ total_kwh: 160, model_version: 'test' }));
    } else res.end(JSON.stringify({ verified: true }));
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const server = createPreviewServer(`http://127.0.0.1:${upstream.address().port}`);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { upstream.close(); server.close(); });
  const origin = `http://127.0.0.1:${server.address().port}`;
  const prefix = `${origin}/preview-api/dashboard/`;
  for (const key of ['info','dataset','metrics','current','history','alerts','timeseries?window_sec=3600']) assert.equal((await fetch(prefix + key)).status, 200);
  assert.equal((await fetch(prefix + 'timeseries?window_sec=17')).status, 400);
  assert.equal((await fetch(prefix + 'arbitrary')).status, 404);
  const predict = payload => fetch(prefix + 'predict', { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  assert.equal((await predict({history:[],forecast:[]})).status,400);
  assert.equal((await predict(null)).status,400);
  const payload={plant_id:'hadong-sewage',history:Array.from({length:24},(_,i)=>({timestamp:`2026-02-26T${String(i).padStart(2,'0')}:00:00+09:00`,generation_kwh:0})),forecast:Array.from({length:24},(_,i)=>({timestamp:`2026-02-27T${String(i).padStart(2,'0')}:00:00+09:00`,shortwave_radiation:0,temperature_2m:10,cloud_cover:20,wind_speed_10m:2}))};
  const invalid=structuredClone(payload);invalid.forecast[0].shortwave_radiation=-1;
  assert.equal((await predict(invalid)).status,400);
  assert.deepEqual(await (await predict(payload)).json(),{total_kwh:160,model_version:'test'});
  assert.deepEqual(calls, ['info','dataset','metrics','current','history','alerts','timeseries?window_sec=3600','predict'].map(key=>'/preview-api/dashboard/'+key));
});

test('batch proxy distinguishes input contract rejection from model readiness without exposing upstream details', async (t) => {
  const { default: http } = await import('node:http');
  let code = 422;
  const upstream = http.createServer((req, res) => { req.resume(); res.writeHead(code, { 'Content-Type': 'application/json' }).end('{"detail":"private upstream detail"}'); });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const preview = createPreviewServer(`http://127.0.0.1:${upstream.address().port}`);
  await new Promise(resolve => preview.listen(0, '127.0.0.1', resolve));
  t.after(() => { upstream.close(); preview.close(); });
  const origin = `http://127.0.0.1:${preview.address().port}`;
  const send = () => fetch(`${origin}/preview-api/batch-test`, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ prices: Array(41).fill(165) }) });
  assert.deepEqual(await (await send()).json(), { error: 'upstream_input_mismatch' });
  code = 503;
  assert.deepEqual(await (await send()).json(), { error: 'upstream_model_unavailable' });
});

test('model switch forwards only same-origin POST with a positive integer version', async (t) => {
  const { default: http } = await import('node:http');
  const calls = [];
  const upstream = http.createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    calls.push({ path: req.url, body: JSON.parse(body) });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ version: '1', previous_version: '2' }));
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const preview = createPreviewServer(`http://127.0.0.1:${upstream.address().port}`);
  await new Promise(resolve => preview.listen(0, '127.0.0.1', resolve));
  t.after(() => { upstream.close(); preview.close(); });
  const origin = `http://127.0.0.1:${preview.address().port}`;
  const url = `${origin}/plants/hadong-sewage/rollback`;
  const send = (body, site = origin) => fetch(url, { method: 'POST', headers: { Origin: site, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  assert.equal((await fetch(url)).status, 405);
  assert.equal((await send({ version: 1 }, 'https://foreign.example')).status, 403);
  for (const body of [{ version: 0 }, { version: 1.5 }, { version: '1' }, { version: 1, force: true }, null]) assert.equal((await send(body)).status, 400);
  assert.equal(calls.length, 0);
  assert.deepEqual(await (await send({ version: 1 })).json(), { version: '1', previous_version: '2' });
  assert.deepEqual(calls, [{ path: '/plants/hadong-sewage/rollback', body: { version: 1 } }]);
});
