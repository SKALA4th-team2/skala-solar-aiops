/** Fixed preview routes for reference-dashboard batch tests and read-only logs. */
export async function handleOperationRoute(request, response, base, path) {
  const isBatch = path === '/preview-api/batch-test';
  const isLogs = path === '/preview-api/logs' || path.startsWith('/preview-api/logs/');
  if (!isBatch && !isLogs) return false;
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  const fail = (code, error) => response.writeHead(code).end(JSON.stringify({ error }));
  if (request.method !== (isBatch ? 'POST' : 'GET')) { fail(405, 'method_not_allowed'); return true; }
  if (isBatch && request.headers.origin !== `http://${request.headers.host}`) { fail(403, 'invalid_origin'); return true; }
  if (!base) { fail(503, 'not_configured'); return true; }
  try {
    let upstreamPath = '/predict/batch-test';
    let body;
    if (isBatch) {
      if (!(request.headers['content-type'] || '').startsWith('application/json')) { fail(415, 'invalid_content_type'); return true; }
      let size = 0;
      const chunks = [];
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 16384) { fail(413, 'too_large'); return true; }
        chunks.push(chunk);
      }
      let payload;
      try { payload = JSON.parse(Buffer.concat(chunks).toString()); } catch { fail(400, 'invalid_batch'); return true; }
      if (!Array.isArray(payload?.prices) || payload.prices.length !== 41 || !payload.prices.every(n => Number.isFinite(n) && n > 0)) { fail(400, 'invalid_batch'); return true; }
      body = JSON.stringify({ prices: payload.prices });
    } else {
      const name = decodeURIComponent(path.slice('/preview-api/logs/'.length));
      if (path !== '/preview-api/logs' && (!/^[a-zA-Z0-9_.-]+$/.test(name) || name === '.' || name === '..')) { fail(400, 'invalid_filename'); return true; }
      upstreamPath = path === '/preview-api/logs' ? '/logs' : `/logs/${encodeURIComponent(name)}`;
    }
    const upstream = await fetch(new URL(upstreamPath, base), { method: isBatch ? 'POST' : 'GET', ...(isBatch ? { body, headers: { 'Content-Type': 'application/json' } } : {}), redirect: 'error', signal: AbortSignal.timeout(isBatch ? 120000 : 5000) });
    if (!upstream.ok) { fail(502, 'upstream_unavailable'); return true; }
    const result = await upstream.json();
    if (isBatch) {
      if (!Array.isArray(result.predictions) || result.predictions.length !== 21 || !result.predictions.every(Number.isFinite) || typeof result.drift_check?.status !== 'string') throw new Error('Invalid batch response');
      const check = result.drift_check;
      response.end(JSON.stringify({ predictions: result.predictions, drift_check: { status: check.status, ...(typeof check.promoted === 'boolean' ? { promoted: check.promoted } : {}), ...(Number.isFinite(check.rmse) ? { rmse: check.rmse } : {}) } }));
    } else if (upstreamPath === '/logs') {
      if (!Array.isArray(result)) throw new Error('Invalid logs response');
      response.end(JSON.stringify(result.filter(log => log && typeof log.name === 'string' && /^[a-zA-Z0-9_.-]+$/.test(log.name) && Number.isFinite(log.size)).map(log => ({ name: log.name, size: log.size }))));
    } else {
      if (typeof result.content !== 'string') throw new Error('Invalid log response');
      response.end(JSON.stringify({ content: result.content }));
    }
  } catch (error) { if (!response.writableEnded) fail(502, error.name === 'TimeoutError' ? 'upstream_timeout' : 'upstream_unavailable'); }
  return true;
}
