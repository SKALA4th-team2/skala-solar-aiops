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
    if (!response.ok) throw new Error(body.error === 'not_configured' ? '운영 API 미연결' : body.error === 'upstream_input_mismatch' ? '입력 규격 불일치 · 연결된 백엔드의 배치 입력 항목을 확인하세요.' : body.error === 'upstream_model_unavailable' ? '서버 모델 준비 안 됨 · 모델과 스케일러 상태를 확인하세요.' : body.error === 'upstream_timeout' ? '응답 시간 초과 · 서버 로그 확인 후 재실행' : '요청 실패 · 서버 연결 및 구현 상태 확인');
    return body;
  }
  // Only the batch response establishes these states; health polling cannot advance them.
  function renderPipeline(states, headline, detail) {
    document.getElementById('pipeline-status').textContent = headline;
    document.getElementById('pipeline-summary').textContent = detail;
    document.getElementById('pipeline-summary').hidden = false;
    document.querySelectorAll('.pipeline li').forEach((step, index) => {
      const [state, label] = states[index];
      step.dataset.state = state;
      const symbol = { complete: '✓', pending: '◷', attention: '!', idle: '−' }[state];
      step.querySelector('.step-state').textContent = `${symbol} ${label}`;
    });
  }
  function showBatchOutcome(check) {
    const completed = [['complete', '응답 완료'], ['complete', '예측 완료']];
    if (check.status === 'ok') {
      renderPipeline([...completed, ['complete', '이상 없음'], ['idle', '미실행'], ['idle', '미실행'], ['idle', '미실행'], ['idle', '기존 유지']],
        '검사 완료', '드리프트 없음 · 재학습 미실행 · 기존 모델 유지');
    } else if (check.status === 'retrain_triggered') {
      const promoted = check.promoted === true;
      const retained = check.promoted === false;
      renderPipeline([...completed, ['attention', '감지'], ['complete', '요청 확인'],
        promoted || retained ? ['complete', '완료'] : ['attention', '결과 미확인'],
        promoted ? ['complete', '등록 확인'] : ['attention', '등록 미확인'],
        promoted ? ['complete', '승격 확인'] : retained ? ['idle', '기존 유지'] : ['attention', '반영 미확인']],
        promoted ? '모델 승격' : retained ? '기존 모델 유지' : '결과 확인 필요',
        promoted ? '드리프트 감지 → 재학습 완료 → 승격 응답 확인' : retained ? '재학습 완료 · 승격되지 않음 · 등록 여부는 응답에 없음' : '재학습 요청 확인 · 이후 결과는 서버 로그에서 확인');
    } else {
      renderPipeline([...completed, ...Array.from({ length: 5 }, () => ['attention', '미확인'])],
        '결과 확인 필요', `알 수 없는 서버 상태: ${check.status} · 서버 로그 확인`);
    }
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
    dialog.dataset.state = 'pending';
    renderPipeline([['pending', '응답 대기'], ...Array.from({ length: 6 }, () => ['idle', '미확인'])], '서버 응답 대기', '요청 처리 중 · 단계별 진행 상황은 제공되지 않습니다.');
    document.getElementById('pipeline-time').textContent = `${kind === 'drift' ? '드리프트' : '정상'} 배치 · 시작 ${new Date().toLocaleTimeString('ko-KR')}`;
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
      dialog.dataset.state = 'complete';
      const check = response.drift_check;
      status.textContent = check.status === 'ok' ? '검사 완료 · 드리프트 없음' : check.status === 'retrain_triggered' ? (check.promoted === true ? '재학습 완료 · 모델 승격' : check.promoted === false ? '재학습 완료 · 기존 모델 유지' : '재학습 요청됨 · 로그 확인') : `서버 상태 · ${check.status}`;
      document.getElementById('simulation-result').textContent = JSON.stringify(response, null, 2);
      showBatchOutcome(check);
      document.getElementById('pipeline-time').textContent += ` · 응답 ${new Date().toLocaleTimeString('ko-KR')}`;
      await loadLogs();
    } catch (error) {
      dialog.dataset.state = 'error';
      status.textContent = message(error);
      renderPipeline(Array.from({ length: 7 }, () => ['attention', '결과 미확인']), '응답 확인 실패',
        `${message(error)} · 서버 작업의 중단·실패 여부는 확인되지 않았습니다. 로그 확인 후 재실행하세요.`);
    }
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
