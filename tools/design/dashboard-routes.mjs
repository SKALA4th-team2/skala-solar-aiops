/** Allowlisted APIs found in the user-provided HAIC dashboard, without arbitrary URL forwarding. */
const reads = { info: '/system/info', dataset: '/system/dataset', metrics: '/metrics/summary', current: '/models/current', history: '/models/history?limit=100', alerts: '/system/alerts?limit=100' };
export async function handleDashboardRoute(req, res, base, url) {
  const key = url.pathname.slice('/preview-api/dashboard/'.length);
  if (!url.pathname.startsWith('/preview-api/dashboard/')) return false;
  const fail = (status, error) => res.writeHead(status).end(JSON.stringify({ error }));
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  const predict = key === 'predict';
  if (!predict && key !== 'timeseries' && !Object.hasOwn(reads, key)) { fail(404, 'unknown_route'); return true; }
  if (req.method !== (predict ? 'POST' : 'GET')) { fail(405, 'method_not_allowed'); return true; }
  if (predict && req.headers.origin !== `http://${req.headers.host}`) { fail(403, 'invalid_origin'); return true; }
  if (!base) { fail(503, 'not_configured'); return true; }
  try {
    let path = reads[key], body;
    if (key === 'timeseries') {
      const seconds = Number(url.searchParams.get('window_sec') || 300);
      if (![300, 3600, 21600, 86400].includes(seconds)) { fail(400, 'invalid_window'); return true; }
      path = `/system/timeseries?window_sec=${seconds}&buckets=12`;
    }
    if (predict) {
      const chunks = []; let size = 0;
      for await (const chunk of req) { size += chunk.length; if (size > 32768) { fail(413, 'too_large'); return true; } chunks.push(chunk); }
      let payload;
      try { payload = JSON.parse(Buffer.concat(chunks).toString()); } catch { fail(400, 'invalid_input'); return true; }
      if (!Array.isArray(payload?.sequence) || payload.sequence.length !== 20 || !payload.sequence.every(p => p && Number.isFinite(p.close) && p.close > 0 && Number.isInteger(p.volume) && p.volume >= 0)) { fail(400, 'invalid_input'); return true; }
      path = '/predict'; body = JSON.stringify({ sequence: payload.sequence.map(p => ({ close: p.close, volume: p.volume })) });
    }
    const upstream = await fetch(new URL(path, base), { method: predict ? 'POST' : 'GET', ...(predict ? { body, headers: { 'Content-Type': 'application/json' } } : {}), redirect: 'error', signal: AbortSignal.timeout(15000) });
    if (!upstream.ok) { fail(upstream.status === 404 ? 404 : 502, 'unavailable'); return true; }
    res.end(JSON.stringify(await upstream.json()));
  } catch { if (!res.writableEnded) fail(502, 'unavailable'); }
  return true;
}
