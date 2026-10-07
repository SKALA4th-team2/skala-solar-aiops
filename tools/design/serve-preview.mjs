/**
 * 작성자: Git 이력 참조 | 작성일: 2026-10-07
 * 독립 디자인 미리보기와 고정 상태 조회 및 사용자 CSV 업로드. project/ 및 API 계약은 변경하지 않는다.
 * SOLAR_API_BASE_URL은 사용자가 지정한 서버 origin. URL 입력을 요청에서 받지 않는다.
 * 로컬 루프백만 바인딩하며 CSV는 고정 /data/upload 경로로만 전달한다. 사용자가 실행한 배치 검사는 서버의 재학습·승격을 유발할 수 있다.
 */
import http from 'node:http';
import { handleDashboardRoute } from './dashboard-routes.mjs';
import { handleOperationRoute } from './operation-routes.mjs';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const root = new URL('../../docs/design/solar-ops-v01/', import.meta.url);
const allowedFiles = new Set(['index.html', 'solar-ops-preview.html', 'styles.css', 'app.js', 'dashboard-core.js', 'operations.js', 'server-dashboard.js']);

export async function readOperations(base, fetcher = fetch) {
  const checkedAt = new Date().toISOString();
  async function get(path, validate) {
    const started = performance.now();
    try {
      const response = await fetcher(new URL(path, base), { signal: AbortSignal.timeout(5000), redirect: 'error', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('Upstream unavailable');
      const body = await response.json();
      if (!validate(body)) throw new Error('Invalid response');
      return { ok: true, body, latencyMs: Math.round(performance.now() - started) };
    } catch { return { ok: false }; }
  }
  const [health, upload] = await Promise.all([
    get('/health', (body) => body?.status === 'ok' && typeof body.model_loaded === 'boolean'),
    get('/data/status', (body) => typeof body?.exists === 'boolean' && (!body.exists ||
      (Number.isInteger(body.rows) && body.rows >= 0 && /^\d{4}-\d{2}-\d{2}$/.test(body.start_date) && /^\d{4}-\d{2}-\d{2}$/.test(body.end_date))))
  ]);
  // Only explicitly used fields cross the preview boundary (no filenames, logs or credentials).
  return { checkedAt, health: health.ok ? { ok: true, modelLoaded: health.body.model_loaded, latencyMs: health.latencyMs } : { ok: false },
    upload: upload.ok ? { ok: true, exists: upload.body.exists, rows: upload.body.rows, startDate: upload.body.start_date, endDate: upload.body.end_date } : { ok: false } };
}

export function createPreviewServer(apiBase) {
  const base = apiBase ? new URL(apiBase) : null;
  if (base && (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.pathname !== '/' || base.search || base.hash)) throw new Error('Provide a plain HTTP(S) API origin without credentials');
  return http.createServer(async (request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    const path = new URL(request.url, 'http://localhost').pathname;
    if (await handleDashboardRoute(request, response, base, new URL(request.url, 'http://localhost'))) return;
    if (await handleOperationRoute(request, response, base, path)) return;
    if (path === '/preview-api/upload' && request.method === 'POST') {
      response.setHeader('Content-Type', 'application/json; charset=utf-8');
      const fail = (status, error) => response.writeHead(status).end(JSON.stringify({ error }));
      if (request.headers.origin !== `http://${request.headers.host}`) { fail(403, 'invalid_origin'); return; }
      if (!base) { fail(503, 'not_configured'); return; }
      const contentType = request.headers['content-type'] || '';
      if (!contentType.startsWith('multipart/form-data;')) { fail(400, 'invalid_csv'); return; }
      try {
        const chunks = [];
        let size = 0;
        for await (const chunk of request) {
          size += chunk.length;
          if (size > 10 * 1024 * 1024 + 65536) { fail(413, 'too_large'); return; }
          chunks.push(chunk);
        }
        const upstream = await fetch(new URL('/data/upload', base), {
          method: 'POST', body: Buffer.concat(chunks), headers: { 'Content-Type': contentType },
          signal: AbortSignal.timeout(25000), redirect: 'error'
        });
        if (!upstream.ok) { fail(upstream.status === 400 || upstream.status === 422 ? 400 : 502, upstream.status === 400 || upstream.status === 422 ? 'invalid_csv' : 'upstream_unavailable'); return; }
        const uploaded = await upstream.json();
        if (!Number.isInteger(uploaded.rows) || uploaded.rows < 41) { fail(502, 'invalid_response'); return; }
        response.end(JSON.stringify({ rows: uploaded.rows }));
      } catch { if (!response.writableEnded) fail(502, 'upstream_unavailable'); }
      return;
    }
    if (request.method !== 'GET') { response.writeHead(405).end(); return; }
    if (path === '/preview-api/operations') {
      response.setHeader('Content-Type', 'application/json; charset=utf-8');
      if (!base) { response.writeHead(503).end(JSON.stringify({ error: 'not_configured' })); return; }
      response.end(JSON.stringify(await readOperations(base)));
      return;
    }
    const filename = path === '/' ? 'solar-ops-preview.html' : path.slice(1);
    if (!allowedFiles.has(filename)) { response.writeHead(404).end(); return; }
    try {
      const content = await readFile(new URL(filename, root));
      response.setHeader('Content-Type', filename.endsWith('.css') ? 'text/css' : filename.endsWith('.js') ? 'text/javascript' : 'text/html; charset=utf-8');
      response.end(content);
    } catch { response.writeHead(404).end(); }
  });
}
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const port = Number(process.env.SOLAR_PREVIEW_PORT || 8767);
  createPreviewServer(process.env.SOLAR_API_BASE_URL).listen(port, '127.0.0.1', () => console.log(`Preview: http://127.0.0.1:${port}/`));
}
