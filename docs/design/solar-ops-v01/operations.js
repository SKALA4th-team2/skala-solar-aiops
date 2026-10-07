/** User-initiated HAIC-compatible batch tests and server log reads. No automatic mutations. */
(() => {
  const dialog = document.getElementById('simulation-dialog');
  const status = document.getElementById('simulation-status');
  let pending = false;
  const message = (error) => error.name === 'TimeoutError' ? '응답 시간 초과 · 서버 로그 확인 후 재실행' : error.message;
  async function request(path, options = {}) {
    if (location.protocol === 'file:') throw new Error('API가 연결된 로컬 서버에서 열어 주세요.');
    const response = await fetch(`/preview-api/${path}`, { ...options, signal: AbortSignal.timeout(125000) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error === 'not_configured' ? '운영 API 미연결' : body.error === 'upstream_timeout' ? '응답 시간 초과 · 서버 로그 확인 후 재실행' : '요청 실패 · 서버 연결 및 구현 상태 확인');
    return body;
  }
  // Match the reference dashboard's log-normal walk (165, sigma .012 / .036).
  function batch(kind) {
    let level = Math.log(165);
    return Array.from({ length: 41 }, () => {
      const gaussian = Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
      level += gaussian * (kind === 'drift' ? .036 : .012);
      return Math.exp(level);
    });
  }
  document.getElementById('simulation-button').addEventListener('click', () => dialog.showModal());
  document.getElementById('simulation-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  async function simulate(kind) {
    if (pending) return;
    pending = true;
    const buttons = ['normal-batch', 'drift-batch', 'simulation-close'];
    buttons.forEach(id => { document.getElementById(id).disabled = true; });
    status.textContent = '전송 중 · 재학습 시 최대 2분 소요';
    document.getElementById('simulation-rmse').textContent = '—';
    document.getElementById('simulation-count').textContent = '—';
    document.getElementById('simulation-result').textContent = '';
    try {
      const prices = batch(kind);
      const response = await request('batch-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prices }) });
      if (!Array.isArray(response.predictions) || response.predictions.length !== 21 || !response.predictions.every(Number.isFinite) || typeof response.drift_check?.status !== 'string') throw new Error('서버 응답 형식 오류');
      const error = Math.sqrt(response.predictions.reduce((sum, prediction, index) => sum + (prediction - prices[index + 20]) ** 2, 0) / 21);
      document.getElementById('simulation-rmse').textContent = error.toFixed(2);
      document.getElementById('simulation-count').textContent = '21건';
      const check = response.drift_check;
      status.textContent = check.status === 'ok' ? '검사 완료 · 드리프트 없음' : check.status === 'retrain_triggered' ? (check.promoted === true ? '재학습 완료 · 모델 승격' : check.promoted === false ? '재학습 완료 · 기존 모델 유지' : '재학습 요청됨 · 로그 확인') : `서버 상태 · ${check.status}`;
      document.getElementById('simulation-result').textContent = JSON.stringify(response, null, 2);
      document.getElementById('pipeline-status').textContent = status.textContent;
      document.getElementById('pipeline-time').textContent = `최근 실행 ${new Date().toLocaleTimeString('ko-KR')}`;
      const states = check.status === 'ok' ? ['완료', '완료', '이상 없음', '미실행', '미실행', '미실행', '유지'] : check.status === 'retrain_triggered' ? ['완료', '완료', '감지', '요청됨', check.promoted !== undefined ? '완료' : '확인 필요', check.promoted === true ? '반영 확인' : '확인 필요', check.promoted === true ? '승격' : check.promoted === false ? '유지' : '확인 필요'] : Array(7).fill('확인 필요');
      document.querySelectorAll('.pipeline .step-state').forEach((element, index) => { element.textContent = states[index]; });
      await loadLogs();
    } catch (error) { status.textContent = message(error); }
    finally { pending = false; buttons.forEach(id => { document.getElementById(id).disabled = false; }); }
  }
  document.getElementById('normal-batch').addEventListener('click', () => simulate('normal'));
  document.getElementById('drift-batch').addEventListener('click', () => simulate('drift'));
  const logStatus = document.getElementById('log-status');
  const files = document.getElementById('log-files');
  async function loadLogs() {
    const button = document.getElementById('load-logs');
    button.disabled = true;
    logStatus.textContent = '목록 조회 중…';
    files.replaceChildren(new Option('파일 선택', ''));
    document.getElementById('log-content').textContent = '';
    try {
      const logs = await request('logs');
      if (!Array.isArray(logs)) throw new Error('로그 응답 형식 오류');
      logs.forEach(log => files.add(new Option(`${log.name} (${log.size}B)`, log.name)));
      logStatus.textContent = logs.length ? `${logs.length}개 파일` : '등록된 로그 없음';
    } catch (error) { logStatus.textContent = message(error); }
    finally { button.disabled = false; }
  }
  document.getElementById('load-logs').addEventListener('click', loadLogs);
  document.getElementById('read-log').addEventListener('click', async event => {
    if (!files.value) { logStatus.textContent = '파일 선택 필요'; return; }
    event.target.disabled = true;
    document.getElementById('log-content').textContent = '';
    logStatus.textContent = '내용 조회 중…';
    try {
      const log = await request(`logs/${encodeURIComponent(files.value)}`);
      document.getElementById('log-content').textContent = log.content || '(빈 로그)';
      logStatus.textContent = '조회 완료';
    } catch (error) { logStatus.textContent = message(error); }
    finally { event.target.disabled = false; }
  });
})();
