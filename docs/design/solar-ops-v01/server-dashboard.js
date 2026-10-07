/** Saved HAIC dashboard parity: explicit live queries, editable prediction input, and history. */
(() => {
  const element = id => document.getElementById(id);
  const display = value => value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  async function query(path, payload) {
    const response = await fetch(`/preview-api/dashboard/${path}`, { ...(payload ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}), signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error('조회 불가 · API 연결/지원 여부 확인');
    return response.json();
  }
  function pairs(target, entries) {
    target.replaceChildren();
    entries.forEach(([label, value]) => {
      const group = document.createElement('div'), term = document.createElement('dt'), description = document.createElement('dd');
      term.textContent = label; description.textContent = display(value); group.append(term, description); target.append(group);
    });
  }
  const labels = { seq_len: '입력 길이', rmse_gate: 'RMSE 게이트', drift_window_size: '검사 윈도우', drift_rmse_threshold: '드리프트 임계값', base_epochs: '기본 학습 횟수', fine_tune_epochs: '재학습 횟수', fine_tune_lr: '학습률', model_source: '모델 소스', loading_mode: '로딩 방식', rows: '행 수', start_date: '시작일', end_date: '종료일', min_close: 'Close 최솟값', max_close: 'Close 최댓값', mean_volume: '평균 Volume', avg_latency_ms: '평균 응답시간(ms)', error_rate: '오류율', request_count: '요청 수', version: '모델 버전', source: '소스', name: '모델명', stage: '스테이지', mode: '학습 방식', rmse: 'RMSE', created_at: '등록 시각', exists: '데이터 존재' };
  let inspecting = false;
  async function inspect() {
    if (inspecting) return;
    inspecting = true; element('inspect-server').disabled = true;
    element('inspector-status').textContent = '조회 중…';
    element('inspector-summary').replaceChildren(); element('inspector-result').textContent = '';
    try {
      const resource = element('server-resource').value;
      const response = await query(resource === 'timeseries' ? `timeseries?window_sec=${element('server-window').value}` : resource);
      let entries;
      if (resource === 'timeseries') {
        if (!Array.isArray(response) || !response.every(row => row && Number.isInteger(row.request_count) && row.request_count >= 0 && Number.isFinite(row.avg_latency_ms) && row.avg_latency_ms >= 0 && Number.isFinite(row.error_rate) && row.error_rate >= 0 && row.error_rate <= 1)) throw new Error('응답 형식 오류');
        const count = response.reduce((sum, row) => sum + row.request_count, 0);
        const weighted = response.reduce((sum, row) => sum + row.avg_latency_ms * row.request_count, 0);
        const errors = response.reduce((sum, row) => sum + row.error_rate * row.request_count, 0);
        entries = [['요청 수', count], ['평균 응답시간', count ? `${(weighted / count).toFixed(1)} ms` : '—'], ['성공률', count ? `${((1 - errors / count) * 100).toFixed(1)}%` : '—']];
      } else {
        if (!response || Array.isArray(response) || typeof response !== 'object') throw new Error('응답 형식 오류');
        entries = Object.entries(response).filter(([key]) => labels[key]).map(([key, value]) => [labels[key], value]);
      }
      pairs(element('inspector-summary'), entries);
      element('inspector-result').textContent = JSON.stringify(response, null, 2);
      if (resource === 'current') {
        document.querySelector('.current-model-panel .status-badge').textContent = '서버 조회';
        const summary = document.querySelector('.current-model-panel .model-summary');
        summary.replaceChildren(); const list = document.createElement('dl'); list.className = 'inspector-summary'; pairs(list, entries); summary.append(list);
      }
      element('inspector-status').textContent = `서버 조회 · ${new Date().toLocaleTimeString('ko-KR')}`;
    } catch (error) { element('inspector-status').textContent = error.message; }
    finally { inspecting = false; element('inspect-server').disabled = false; }
  }
  element('inspect-server').addEventListener('click', inspect);
  element('server-window').addEventListener('change', inspect);
  element('server-resource').addEventListener('change', () => { element('server-window').hidden = element('server-resource').value !== 'timeseries'; inspect(); });
  function generate() {
    let level = Math.log(165);
    const sequence = Array.from({ length: 20 }, () => {
      level += Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random()) * .012;
      return { close: Number(Math.exp(level).toFixed(2)), volume: Math.round(1250000 + (Math.random() - .5) * 300000) };
    });
    element('predict-input').value = JSON.stringify({ sequence }, null, 2);
  }
  element('generate-sample').addEventListener('click', generate);
  element('run-predict').addEventListener('click', async event => {
    event.target.disabled = true; element('predict-status').textContent = '예측 중…'; element('predict-result').textContent = '';
    try {
      let payload;
      try { payload = JSON.parse(element('predict-input').value); } catch { throw new Error('JSON 형식 확인 필요'); }
      if (!Array.isArray(payload?.sequence) || payload.sequence.length !== 20 || !payload.sequence.every(row => row && Number.isFinite(row.close) && row.close > 0 && Number.isInteger(row.volume) && row.volume >= 0)) throw new Error('입력 20개 · close > 0 · volume은 0 이상 정수');
      const response = await query('predict', payload);
      if (!Number.isFinite(response.predicted_close)) throw new Error('예측 응답 형식 오류');
      element('predict-status').textContent = `예측값 ${response.predicted_close} · 모델 ${display(response.model_version)}`;
      element('predict-result').textContent = JSON.stringify(response, null, 2);
    } catch (error) { element('predict-status').textContent = error.message; }
    finally { event.target.disabled = false; }
  });
  const time = timestamp => typeof timestamp === 'number' && Number.isFinite(timestamp) ? new Date(timestamp * 1000).toLocaleString('ko-KR') : display(timestamp);
  let historyPending = false;
  async function refreshHistory() {
    if (historyPending) return;
    historyPending = true; element('refresh-history').disabled = true; element('history-status').textContent = '조회 중…';
    try {
      const results = await Promise.allSettled([query('history'), query('alerts')]);
      let allValid = true;
      results.forEach((result, index) => {
        const panel = document.querySelector(index ? '.events-panel' : '.model-panel');
        const target = panel.querySelector(index ? '.event-list' : 'tbody');
        target.replaceChildren();
        const valid = result.status === 'fulfilled' && Array.isArray(result.value) && result.value.every(row => row && typeof row === 'object' && !Array.isArray(row) && (index ? typeof row.message === 'string' : row.version !== undefined));
        allValid = allValid && valid;
        const rows = valid ? result.value : [];
        panel.querySelector('.panel-heading p').textContent = valid ? '서버 조회' : '조회 불가';
        panel.querySelector('.panel-heading > span').textContent = valid ? `${rows.length}건` : '미연결';
        if (!rows.length) {
          const empty = document.createElement(index ? 'li' : 'tr');
          if (index) empty.textContent = valid ? '운영 알림 없음' : '알림 조회 불가';
          else { const cell = document.createElement('td'); cell.colSpan = 5; cell.textContent = valid ? '등록된 모델 없음' : '모델 이력 조회 불가'; empty.append(cell); }
          target.append(empty);
        }
        rows.forEach(row => {
          const entry = document.createElement(index ? 'li' : 'tr');
          if (index) { const content = document.createElement('div'), title = document.createElement('strong'), stamp = document.createElement('p'); title.textContent = `${display(row.level)} · ${display(row.message)}`; stamp.textContent = time(row.ts); content.append(title, stamp); entry.append(content); }
          else [row.version, time(row.created_at), row.mode, row.rmse, row.stage].forEach(value => { const cell = document.createElement('td'); cell.textContent = display(value); entry.append(cell); });
          target.append(entry);
        });
      });
      document.querySelector('.events-foot').textContent = `조회 시각 ${new Date().toLocaleTimeString('ko-KR')}`;
      document.querySelector('.model-panel caption').textContent = '서버 모델 버전 이력';
      document.querySelector('.model-panel .table-scroll').setAttribute('aria-label', '모델 버전 이력, 상하좌우 스크롤');
      element('history-status').textContent = allValid ? '조회 완료' : '일부 API 조회 불가';
    } catch { element('history-status').textContent = '응답 처리 실패 · 다시 조회해 주세요'; }
    finally { historyPending = false; element('refresh-history').disabled = false; }
  }
  element('refresh-history').addEventListener('click', refreshHistory);
  // Honor the existing refresh interval only while the corresponding live view is visible.
  let timer;
  function schedule() {
    clearTimeout(timer);
    const interval = Number(element('refresh-interval').value);
    if (document.hidden || !interval) return;
    timer = setTimeout(async () => {
      if (location.hash === '#history') await refreshHistory();
      if (location.hash === '#service' && document.querySelector('.server-inspector').open) await inspect();
      schedule();
    }, interval);
  }
  element('refresh-interval').addEventListener('change', schedule);
  document.addEventListener('visibilitychange', schedule);
  window.addEventListener('pagehide', () => clearTimeout(timer));
  generate(); schedule();
})();
