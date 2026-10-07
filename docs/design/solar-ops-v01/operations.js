/** User-initiated HAIC-compatible batch tests and server log reads. No automatic mutations. */
(() => {
  const dialog = document.getElementById('simulation-dialog');
  const status = document.getElementById('simulation-status');
  let pending = false;
  let trackedJob=null,jobTimer=null;
  async function pollJob(){
    clearTimeout(jobTimer);
    try{
      if(!trackedJob){const response=await request('jobs');trackedJob=response.find(j=>j.plant_id===window.SolarLive.plant())?.id;}
      if(!trackedJob){status.textContent='이 발전소의 재학습 작업이 없습니다.';return;}
      const job=await request(`jobs/${trackedJob}`);if(job.plant_id!==window.SolarLive.plant()){trackedJob=null;return;}
      const labels={queued:'재학습 대기',running:'학습·검증 중',succeeded:job.result?.promoted?'검증 통과 · 모델 반영':'검증 미통과 · 기존 모델 유지',failed:'학습 실패 · 기존 모델 유지',skipped:'조건 미충족 · 작업 보류'};
      status.textContent=labels[job.status]||job.status;
      document.getElementById('pipeline-status').textContent=status.textContent;
      document.getElementById('simulation-result').textContent=JSON.stringify(job,null,2);
      const done=['succeeded','failed','skipped'].includes(job.status);
      const states=['완료','완료','감지','접수',done?'완료':job.status==='running'?'실행 중':'대기',job.result?.promoted?'등록':'미반영',job.result?.promoted?'승격':'기존 유지'];
      document.querySelectorAll('.pipeline .step-state').forEach((e,i)=>e.textContent=states[i]);
      if(!done)jobTimer=setTimeout(pollJob,2000);else{window.dispatchEvent(new Event('plantchange'));window.SolarLive.reload();}
    }catch(error){status.textContent=error.message;}
  }
  window.addEventListener('plantchange',()=>{trackedJob=null;clearTimeout(jobTimer);});
  window.addEventListener('pagehide',()=>clearTimeout(jobTimer));

  const message = (error) => error.name === 'TimeoutError' ? '응답 시간 초과 · 서버 로그 확인 후 재실행' : error.message;
  async function request(path, options = {}) {
    if (location.protocol === 'file:') throw new Error('API가 연결된 로컬 서버에서 열어 주세요.');
    const response = await fetch(`/${path}`, { ...options, signal: AbortSignal.timeout(125000) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error === 'not_configured' ? '운영 API 미연결' : body.error === 'upstream_timeout' ? '응답 시간 초과 · 서버 로그 확인 후 재실행' : (typeof body.detail==='string'?body.detail:'요청 실패 · 입력과 서버 상태 확인'));
    return body;
  }
  document.getElementById('simulation-button').addEventListener('click', () => dialog.showModal());
  document.getElementById('simulation-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', event => { if (pending) event.preventDefault(); });
  async function simulate(kind) {
    if (pending) return;
    pending = true;
    const buttons = ['normal-batch', 'drift-batch', 'simulation-close'];
    buttons.forEach(id => { document.getElementById(id).disabled = true; });
    status.textContent = '실제 자료 검사 중 · 학습은 별도 작업으로 실행됩니다';
    document.getElementById('simulation-rmse').textContent = '—';
    document.getElementById('simulation-count').textContent = '—';
    document.getElementById('simulation-result').textContent = '';
    try {
      const sampleResponse=await fetch(`/ui/sample?plant_id=${encodeURIComponent(window.SolarLive.plant())}`);
      const sample=await sampleResponse.json();if(!sampleResponse.ok)throw new Error(sample.detail);
      const prices=sample.batch.prices;
      const response = await request('predict/batch-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sample.batch) });
      if (!Array.isArray(response.predictions) || response.predictions.length !== 21 || !response.predictions.every(Number.isFinite) || typeof response.drift_check?.status !== 'string') throw new Error('서버 응답 형식 오류');
      const error = Math.sqrt(response.predictions.reduce((sum, prediction, index) => sum + (prediction - prices[index + 20]) ** 2, 0) / 21);
      document.getElementById('simulation-rmse').textContent = error.toFixed(2);
      document.getElementById('simulation-count').textContent = '21건';
      const check = response.drift_check;
      status.textContent = check.status === 'ok' ? '검사 완료 · 드리프트 없음' : check.status === 'retrain_triggered' ? (check.promoted === true ? '재학습 완료 · 모델 승격' : check.promoted === false ? '재학습 완료 · 기존 모델 유지' : '재학습 요청됨 · 로그 확인') : `서버 상태 · ${check.status}`;
      const reasons={insufficient_valid_days:`기대 발전량(Expected) 유효일 부족 (${check.valid_days ?? 0}/15일)`,outage_or_hold_in_training_window:'설비 이상 의심 · 점검 후 재학습',stale_or_already_evaluated:'이미 판정한 날짜 · 기존 기록 유지',window_overlaps_model_training:'학습 기간과 겹쳐 재학습 보류',input_window_not_yet_below_limit:'앞 20일의 지속 저하 대기'};
      if(check.status==='skipped'||check.status==='facility_check'||check.status==='drift_alerted')status.textContent=`${check.status==='facility_check'?'설비 점검':'감시 보류'} · ${reasons[check.reason]||check.reason||check.status}`;
      status.textContent+=` · 자료 ${sample.batch.dates[0]} ~ ${sample.batch.dates.at(-1)}`;
      document.getElementById('simulation-result').textContent = JSON.stringify(response, null, 2);
      document.getElementById('pipeline-status').textContent = status.textContent;
      document.getElementById('pipeline-time').textContent = `최근 실행 ${new Date().toLocaleTimeString('ko-KR')}`;
      const states = check.status === 'ok' ? ['완료', '완료', '이상 없음', '미실행', '미실행', '미실행', '유지'] : check.status === 'retrain_triggered' ? ['완료', '완료', '감지', '요청됨', check.promoted !== undefined ? '완료' : '확인 필요', check.promoted === true ? '반영 확인' : '확인 필요', check.promoted === true ? '승격' : check.promoted === false ? '유지' : '확인 필요'] : Array(7).fill('확인 필요');
      document.querySelectorAll('.pipeline .step-state').forEach((element, index) => { element.textContent = states[index]; });
      if(check.job_id){trackedJob=check.job_id;pollJob();}
      await loadLogs();
    } catch (error) { status.textContent = message(error); }
    finally { pending = false; buttons.forEach(id => { document.getElementById(id).disabled = false; }); }
  }
  document.getElementById('normal-batch').addEventListener('click', () => simulate('normal'));
  document.getElementById('drift-batch').addEventListener('click', pollJob);
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
