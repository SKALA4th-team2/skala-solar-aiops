/* Same-origin hourly dashboard. Source observations and retrospective predictions are explicit. */
"use strict";
const iconPaths = {
  solar: '<path d="m5 5-3 11h20L19 5ZM12 5v11M4 10h16M8 16v5m8-5v5M5 21h14"/>',
  activity: '<path d="M2 12h4l3-8 6 16 3-8h4"/>',
  history: '<path d="M3 4v5h5M3 9a9 9 0 1 1-1 7M12 7v6l4 2"/>',
  building: '<path d="M4 21V5l8-2v18m0-12h8v12M2 21h20M8 8v1m0 4v1m0 4v1m8-6v1m0 4v1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
  alert: '<path d="m12 3 10 18H2Z M12 9v5m0 3h.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 10-13h-7Z"/>',
  chart: '<path d="M3 3v18h18M6 15l4-5 4 3 6-8"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>'
};
document.querySelectorAll("[data-icon]").forEach((element) => {
  element.innerHTML = `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[element.dataset.icon]}</svg>`;
});

const $=s=>document.querySelector(s);
const $$=s=>Array.from(document.querySelectorAll(s));
const state={plant:'hadong-sewage',period:24,data:null,job:null,epoch:0,demo:false};
const fmt=n=>Number.isFinite(n)?n.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—';
const eventStamp=s=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',dateStyle:'short',timeStyle:'medium'}).format(new Date(s));
const stamp=s=>String(s).replace('T',' ').replace('+09:00',' KST');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function text(s,v){const e=$(s);if(e)e.textContent=v;}
function value(k,v){$$(`[data-value="${k}"]`).forEach(e=>e.textContent=v);}
async function api(url,options={}){
 const response=await fetch(url,{cache:'no-store',...options});const body=await response.json();
 if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));return body;
}
function path(url){return `${url}?plant_id=${encodeURIComponent(state.plant)}`;}
function post(url,body){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
function view(){
 const name=['energy','service','history'].includes(location.hash.slice(1))?location.hash.slice(1):'energy';
 $$('.view').forEach(e=>e.hidden=e.id!==`view-${name}`);
 $$('.nav-link').forEach(e=>{const selected=e.dataset.view===name;e.classList.toggle('selected',selected);if(selected)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');});
 const title={energy:'발전 현황',service:'서비스 운영',history:'이력 · 알림'}[name];text('#page-title',title);text('#breadcrumb-title',title);
 $('#simulation-button').hidden=name!=='service';
 if(name==='history')loadHistory();if(name==='service')operations();
}
function chart(){
 if(!state.data)return;const rows=state.data.records.slice(-state.period);const max=Math.max(1,...rows.flatMap(r=>[r.actual,r.predicted]))*1.1;
 const w=720,h=280,x=i=>48+i*650/Math.max(1,rows.length-1),y=v=>235-v/max*205;
 const points=k=>rows.map((r,i)=>`${x(i)},${y(r[k])}`).join(' ');
 const grid=[0,.25,.5,.75,1].map(n=>`<line x1="48" x2="698" y1="${y(max*n)}" y2="${y(max*n)}" stroke="#eee"/><text x="42" y="${y(max*n)+4}" text-anchor="end">${fmt(max*n)}</text>`).join('');
 const ticks=rows.map((r,i)=>i%Math.max(1,Math.floor(rows.length/4))===0?`<text x="${x(i)}" y="264" text-anchor="middle">${esc(r.timestamp.slice(5,16).replace('T',' '))}</text>`:'').join('');
 $('#overview-chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;min-height:180px" role="img" aria-label="시간별 실측과 LSTM 예측, 단위 kWh. 아래 시간별 기록에서 정확한 값을 확인할 수 있습니다."><text x="8" y="15">kWh</text>${grid}<polyline points="${points('predicted')}" fill="none" stroke="#bd7950" stroke-width="2" stroke-dasharray="5 4"/><polyline points="${points('actual')}" fill="none" stroke="#273e48" stroke-width="2"/>${ticks}</svg>`;
 text('[data-chart-range]',`${stamp(rows[0].timestamp)} – ${stamp(rows.at(-1).timestamp)}`);
 $('#generation-rows').innerHTML=rows.map(r=>`<tr><td>${esc(stamp(r.timestamp))}</td><td class="numeric">${fmt(r.actual)}</td><td class="numeric">${fmt(r.predicted)}</td><td class="numeric">${fmt(r.predicted-r.actual)}</td><td class="numeric">${fmt(r.irradiance)}</td></tr>`).join('');
 renderIncentives();value('record-count',`${rows.length}시간`);value('rmse',fmt(Math.sqrt(rows.reduce((a,r)=>a+(r.predicted-r.actual)**2,0)/rows.length)));value('rmse-period',`최근 ${rows.length}시간 · 자료 재생`);
 $$('[data-period]').forEach(e=>{const selected=Number(e.dataset.period)===state.period;e.classList.toggle('selected',selected);e.setAttribute('aria-pressed',selected);});
}
function renderIncentives(){
 const report=state.data?.incentives?.[String(state.period)];$('#incentive-rows').replaceChildren();
 if(!report){['inc-error','inc-le6','inc-le8','inc-eligible','inc-excluded','inc-won'].forEach(k=>value(k,'—'));text('#incentive-period','인센티브 지표를 불러오지 못했습니다.');return;}
 const factor=Number($('#incentive-coefficient').value);
 value('inc-error',fmt(report.mean_error_pct));value('inc-le6',fmt(report.le6_pct));value('inc-le8',fmt(report.le8_pct));value('inc-eligible',report.eligible_hours);value('inc-excluded',report.excluded_hours);value('inc-won',fmt(report.scenario_krw*factor));
 text('#incentive-period',`최근 ${report.total_hours}시간 · LSTM v${state.data.model_version} · 단일 예측 대용 · 과거 재생`);
 text('#incentive-exclusions',Object.entries(report.excluded_reasons).map(([reason,n])=>`${reason} ${n}시간`).join(' · ')||'제외 시간 없음');
 $('#incentive-rows').innerHTML=report.rows.map(r=>`<tr><td>${esc(stamp(r.timestamp))}</td><td class="numeric">${fmt(r.utilization_pct)}</td><td class="numeric">${fmt(r.error_pct)}</td><td>${esc(r.exclusion_reason||({le6:'6% 이하',le8:'6~8%',gt8:'8% 초과'}[r.band]))}</td><td class="numeric">${fmt(r.base_rate_krw_per_kwh*factor)}</td><td class="numeric">${fmt(r.scenario_krw*factor)}</td></tr>`).join('');
}
$('#incentive-coefficient').onchange=renderIncentives;
async function loadEnergy(){
 const epoch=++state.epoch;state.data=null;text('#overview-chart','시간별 자료 조회 중…');$('#generation-rows').replaceChildren();$('#forecast-hours').replaceChildren();$('#incentive-rows').replaceChildren();text('#incentive-period','조회 중…');text('#incentive-exclusions','');
 $$('[data-value]').forEach(e=>e.textContent='—');
 try{
  const d=await api(path('/ui/energy'));if(epoch!==state.epoch)return;state.data=d;
  const p=d.plant,rows=d.records,last=rows.at(-1);text('#page-description',state.demo?'격리된 기능 검증 환경 · 합성 드리프트 · 성능 평가 자료 아님':`${p.name} · ${fmt(p.capacity_kw)} kW · 시간별 LSTM`);
  text('.sidebar-site strong',p.name);text('.sidebar-site div span',`${fmt(p.capacity_kw)} kW`);text('#plant-scope',`${p.name} · 1시간 구간`);
  value('replay-date',last.timestamp.slice(0,10));value('actual',fmt(last.actual));value('actual-date',stamp(last.timestamp));value('today-prediction',fmt(last.predicted));
  value('week-mean',fmt(rows.slice(-24).reduce((a,r)=>a+r.actual,0)/24));value('week-range','최근 확정 24시간');
  value('forecast',fmt(d.forecast_total_kwh));value('tomorrow-label',d.forecast[0].timestamp.slice(0,10));value('forecast-delta','24개 시간 예측의 합계');
  value('tomorrow-irradiance',fmt(rows.slice(-24).reduce((a,r)=>a+r.irradiance,0)/24));
  text('.forecast-note',`LSTM v${d.model_version} · ${d.source==='uploaded'?'업로드':'보관'} 자료 대상일 재생. 오늘 기준 실시간 예보가 아닙니다.`);
  $('#forecast-hours').innerHTML=d.forecast.map(r=>`<tr><td>${esc(r.timestamp.slice(11,16))}–${String((Number(r.timestamp.slice(11,13))+1)%24).padStart(2,'0')}:00</td><td class="numeric">${fmt(r.predicted_kwh)}</td></tr>`).join('');chart();
 }catch(e){renderIncentives();text('#overview-chart',`조회 실패: ${e.message}`);text('.forecast-note','시간별 자료를 불러오지 못했습니다.');}
}
async function operations(){
 const pid=state.plant;
 try{
  const d=await api(path('/preview-api/operations'));if(pid!==state.plant)return;
  if(d.health.demo_mode)text('#page-description','격리된 기능 검증 환경 · 합성 드리프트 · 성능 평가 자료 아님');
  text('#ops-status',d.health.worker_alive?'API · AIOps 작업자 정상':'API 연결됨 · 작업자 확인 필요');text('#ops-updated',`조회 ${new Date().toLocaleTimeString('ko-KR')}`);
  text('[data-ops="health"]',d.health.status);text('[data-ops="model"]',`시간별 v${d.plant.current.version}`);text('[data-ops="latency"]',d.health.worker_alive?'동작 중':'확인 필요');text('[data-ops="rows"]',`${d.plant.upload.rows}시간`);text('[data-ops="range"]',d.plant.upload.end?stamp(d.plant.upload.end):'기본 보관 자료 사용');
  const m=d.plant.model;$('.current-model-panel .status-badge').textContent=`v${m.version} 운영 중`;
  $('.model-summary').innerHTML=`<div><span class="metric-label">현재 운영 모델</span><strong>Hourly LSTM v${esc(m.version)}</strong></div><dl><div><dt>2025 독립 검증 RMSE</dt><dd>${fmt(m.evaluation.rmse_kwh)} <small>kWh/시간</small></dd></div><div><dt>입력 → 출력</dt><dd>실적 24h + 예보 24h → 24h</dd></div><div><dt>배포 게이트</dt><dd>통과 · ${fmt(m.gate.limit_kwh)} kWh</dd></div></dl>`;
  if(d.plant.monitor)renderMonitor(d.plant.monitor,d.plant.jobs.find(j=>j.id===d.plant.monitor.job?.id));
 }catch(e){text('#ops-status',`연결 오류: ${e.message}`);}
}
const reasons={normal:'정상',daytime_near_zero_check_data_or_facility:'주간 저발전 연속 발생 · 데이터/설비 확인',need_7_complete_days_and_48_daylight_hours:'7일·주간 48시간 미충족',forecast_conditioned_drop_and_error:'예보 대비 실적 저하와 오차 증가'};
function renderMonitor(m,job=null){
 const status=job?.status||m.state;text('#pipeline-status',status);text('#pipeline-time',`${reasons[m.reason]||m.reason} · 예보 기반 검사`);if(m.job)state.job=m.job.id;
 const stages=['완료','완료',m.state==='normal'?'정상':m.state==='held'?'보류':m.state==='skipped'?'자료 부족':'감지','미요청','미실행','미등록','기존 유지'];
 if(m.job){stages[3]='등록';stages[4]=status==='queued'?'대기':status==='running'?'학습 중':status==='succeeded'?'통과':status==='rejected'?'게이트 미달':'실패';if(status==='succeeded'){stages[5]='등록 완료';stages[6]='반영 완료';}}
 $$('.step-state').forEach((e,i)=>e.textContent=stages[i]);
}
async function loadHistory(){
 const pid=state.plant;
 try{
  const [history,alerts,current]=await Promise.all([api(path('/preview-api/dashboard/history')),api(path('/preview-api/dashboard/alerts')),api(path('/preview-api/dashboard/current'))]);if(pid!==state.plant)return;
  $('.model-panel tbody').innerHTML=history.map(m=>`<tr><td>v${esc(m.version)}</td><td>${esc(eventStamp(m.created_at))}</td><td>${m.parent_version?'추가 학습':'최초 학습'}</td><td class="numeric">${fmt(m.gate.rmse_kwh)}</td><td>${m.version===current.version?'운영 중':'보관'}</td></tr>`).join('');
  $('.model-panel .status-badge').textContent=`v${current.version} 운영 중`;
  $('.event-list').innerHTML=alerts.map(e=>`<li><div><strong>${esc(e.kind)}</strong><p>${esc(eventStamp(e.created_at))} KST</p><details><summary>상세</summary><pre>${esc(e.payload)}</pre></details></div></li>`).join('')||'<li>아직 운영 알림이 없습니다.</li>';
  text('.events-panel .neutral-badge',`${alerts.length}건`);text('#history-status','실제 모델 등록·운영 이력');
 }catch(e){text('#history-status',e.message);$('.model-panel tbody').replaceChildren();$('.event-list').replaceChildren();}
}
async function generateSample(){try{const d=await api(path('/ui/sample'));$('#predict-input').value=JSON.stringify(d.prediction,null,2);text('#predict-status','실제 자료 예시 · 선택 발전소 · KST 24시간');}catch(e){text('#predict-status',e.message);}}
$('#generate-sample').onclick=generateSample;
$('#run-predict').onclick=async()=>{text('#predict-status','예측 중…');text('#predict-result','');try{const body=JSON.parse($('#predict-input').value);if(body.plant_id!==state.plant)throw Error('선택 발전소와 입력 plant_id가 다릅니다. 예시를 다시 생성하세요.');const d=await post('/predict',body);text('#predict-result',JSON.stringify(d,null,2));text('#predict-status',`24시간 예측 완료 · 합계 ${fmt(d.total_kwh)} kWh · v${d.model_version}`);}catch(e){text('#predict-status',`실패: ${e.message}`);}};
$('#simulation-button').onclick=()=>$('#simulation-dialog').showModal();$('#simulation-close').onclick=()=>$('#simulation-dialog').close();
$('#normal-batch').onclick=async()=>{const button=$('#normal-batch');button.disabled=true;text('#simulation-status','시간별 실제 자료 검사 중…');try{const d=await api(path('/ui/sample'));const r=await post('/predict/batch-test',d.batch);text('#simulation-result',JSON.stringify(r,null,2));text('#simulation-count',`${r.predictions.length}시간`);text('#simulation-rmse',`${fmt(r.monitor.rmse_kwh)} kWh/시간`);text('#simulation-status',`${r.monitor.state}: ${reasons[r.monitor.reason]||r.monitor.reason}`);renderMonitor(r.monitor);await operations();}catch(e){text('#simulation-status',e.message);}finally{button.disabled=false;}};
$('#drift-batch').onclick=async()=>{try{const jobs=await api(path('/jobs'));text('#simulation-result',JSON.stringify(jobs,null,2));text('#simulation-status',jobs[0]?`최근 작업: ${jobs[0].status}`:'현재 재학습 작업이 없습니다.');await operations();}catch(e){text('#simulation-status',e.message);}};
$('#upload-button').onclick=()=>$('#upload-dialog').showModal();$('#upload-close').onclick=()=>$('#upload-dialog').close();
$('#upload-form').onsubmit=async event=>{event.preventDefault();const b=$('#upload-submit');b.disabled=true;text('#upload-status','업로드·검증 중…');try{const f=$('#upload-file').files[0];if(!f||f.size>5*1024*1024)throw Error('5MB 이하 CSV를 선택하세요.');const form=new FormData();form.append('plant_id',state.plant);form.append('file',f);const r=await api('/data/upload',{method:'POST',body:form});text('#upload-status',`${r.rows}시간 등록 완료 · ${r.monitor.state}`);await loadEnergy();await operations();}catch(e){text('#upload-status',e.message);}finally{b.disabled=false;}};
$('#inspect-server').onclick=async()=>{try{const d=await api(path('/preview-api/dashboard/'+$('#server-resource').value));text('#inspector-result',JSON.stringify(d,null,2));text('#inspector-status','현재 서버 응답');}catch(e){text('#inspector-status',e.message);}};
$('#load-logs').onclick=async()=>{try{const files=await api('/logs');$('#log-files').innerHTML=files.map(f=>`<option>${esc(f)}</option>`).join('');text('#log-status','시간별 AIOps 로그');}catch(e){text('#log-status',e.message);}};
$('#read-log').onclick=async()=>{try{const d=await api('/logs/'+encodeURIComponent($('#log-files').value));text('#log-content',d.content);}catch(e){text('#log-status',e.message);}};
$('#refresh-history').onclick=loadHistory;$('#refresh-ops').onclick=operations;
$$('[data-period]').forEach(e=>e.onclick=()=>{state.period=Number(e.dataset.period);chart();});
$('#plant-filter').onchange=async e=>{state.plant=e.target.value;state.job=null;$('#predict-input').value='';text('#predict-result','');text('#simulation-result','');text('#pipeline-status','검사 전');text('#pipeline-time','새 발전소 조회');await loadEnergy();view();};
window.addEventListener('hashchange',view);
let timer;
function schedule(){clearTimeout(timer);const delay=Number($('#refresh-interval').value);if(delay)timer=setTimeout(async()=>{if(!document.hidden&&location.hash==='#service')await operations();schedule();},delay);}
$('#refresh-interval').onchange=schedule;
window.SolarLive={plant:()=>state.plant,reload:loadEnergy};
async function init(){
 $('.model-panel tbody').replaceChildren();$('.event-list').replaceChildren();$('.model-summary').textContent='모델 조회 전';$('.current-model-panel .status-badge').textContent='조회 전';
 try{const [plants,health]=await Promise.all([api('/plants'),api('/health')]);state.demo=health.demo_mode;if(!plants.some(p=>p.plant_id===state.plant))state.plant=plants[0].plant_id;
 $('#plant-filter').innerHTML=plants.map(p=>`<option value="${esc(p.plant_id)}">${esc(p.name)} · ${fmt(p.capacity_kw)} kW</option>`).join('');$('#plant-filter').value=state.plant;text('#plant-filter-note',`시간별 품질 검증 통과 ${plants.length}개소`);await loadEnergy();view();schedule();}
 catch(e){text('#page-description',`서버 연결 실패: ${e.message}`);}
}
init();
