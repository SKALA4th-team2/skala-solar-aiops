/* Same-origin hourly dashboard. Source observations and retrospective predictions are explicit. */
"use strict";
const iconPaths = {
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  play: '<path d="m8 4 12 8-12 8Z"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 17l10 5 10-5"/>',
  file: '<path d="M14 2H5v20h14V7Zm0 0v6h5M8 12h8M8 16h6"/>',


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
// Display-only numbering, ordered by stable plant ID within each duplicate name.
const plantLabels=new Map();
function labelPlants(plants){
 plantLabels.clear();
 const groups=new Map();
 for(const plant of plants){const group=groups.get(plant.name)||[];group.push(plant);groups.set(plant.name,group);}
 for(const [name,group] of groups){
  group.sort((a,b)=>a.plant_id.localeCompare(b.plant_id,'en',{numeric:true}));
  group.forEach((plant,index)=>plantLabels.set(plant.plant_id,group.length>1?`${name} ${index+1}`:name));
 }
}
const plantLabel=p=>plantLabels.get(p.plant_id)||p.name;
let inspectionReport=null;
const fmt=n=>Number.isFinite(n)?n.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—';
const fixed=n=>Number.isFinite(n)?n.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
const eventStamp=s=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',dateStyle:'short',timeStyle:'medium'}).format(new Date(s));
const stamp=s=>String(s).replace('T',' ').replace('+09:00',' KST');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function text(s,v){const e=$(s);if(e)e.textContent=v;}
function value(k,v){$$(`[data-value="${k}"]`).forEach(e=>e.textContent=v);}
async function api(url,options={}){
 const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(120000),...options});
 if(!response.headers.get('content-type')?.includes('application/json'))throw Error('시간별 API에 연결되지 않았습니다. 서버 주소를 확인하세요.');
 const body=await response.json();
 if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body));return body;
}
function path(url){return `${url}?plant_id=${encodeURIComponent(state.plant)}`;}
function post(url,body){return api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
function view(){
 const name=['energy','service','history'].includes(location.hash.slice(1))?location.hash.slice(1):'energy';
 $$('.view').forEach(e=>e.hidden=e.id!==`view-${name}`);
 $$('.nav-link').forEach(e=>{const selected=e.dataset.view===name;e.classList.toggle('selected',selected);if(selected)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');});
 if(name!=='service')stopFlowPreview();
 const title={energy:'발전 현황',service:'서비스 운영',history:'이력 · 알림'}[name];text('#page-title',title);text('#breadcrumb-title',title);
 $('#simulation-button').hidden=name!=='service';$('#upload-button').hidden=name!=='service';
 if(name==='history')loadHistory();if(name==='service')operations();
}
function chart(){
 if(!state.data)return;
 const rows=state.data.records.slice(-state.period),values=state.data.records.flatMap(r=>[r.actual,r.predicted]).filter(Number.isFinite);
 // One scale across all periods; missing values never become zero.
 const upper=Math.max(1,...values),lower=Math.min(0,...values),rawStep=(upper-lower)/4;
 const magnitude=10**Math.floor(Math.log10(rawStep)),step=([1,2,2.5,5,10].find(n=>n*magnitude>=rawStep)||10)*magnitude;
 const min=Math.floor(lower/step)*step,max=Math.ceil(upper/step)*step;
 const ticksY=Array.from({length:Math.round((max-min)/step)+1},(_,i)=>min+i*step);
 const host=$('#overview-chart'),w=Math.max(200,Math.round(host.clientWidth)),h=280;
 const left=Math.max(48,...ticksY.map(n=>fmt(n).length*9+12)),right=w-16,top=24,bottom=232;
 const x=i=>left+i*(right-left)/Math.max(1,rows.length-1),y=n=>bottom-(n-min)/(max-min)*(bottom-top);
 const line=key=>{let connected=false;return rows.map((r,i)=>{if(!Number.isFinite(r[key])){connected=false;return '';}const point=`${connected?'L':'M'}${x(i)},${y(r[key])}`;connected=true;return point;}).join(' ');};
 const grid=ticksY.map(n=>`<line x1="${left}" x2="${right}" y1="${y(n)}" y2="${y(n)}" stroke="${n===0?'#c7d1d7':'#edf1f3'}"/><text class="chart-y-tick" x="${left-10}" y="${y(n)+5}" text-anchor="end">${fmt(n)}</text>`).join('');
 const tickCount=w<400?2:w<650?3:4;
 const ticks=Array.from({length:tickCount},(_,j)=>Math.round(j*(rows.length-1)/(tickCount-1))).map((i,j)=>`<text x="${x(i)}" y="264" text-anchor="${j===0?'start':j===tickCount-1?'end':'middle'}">${esc(rows[i].timestamp.slice(state.period===24?11:5,16).replace('T',' '))}</text>`).join('');
 host.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" tabindex="0" aria-label="실측과 예측 발전량 비교, kWh. 좌우 방향키로 시간별 값 확인." style="width:100%;height:280px"><text x="0" y="15">kWh</text>${grid}<path d="${line('predicted')}" fill="none" stroke="#bd7950" stroke-width="2.5" stroke-dasharray="6 5"/><path d="${line('actual')}" fill="none" stroke="#44545d" stroke-width="2.5"/>${ticks}<line id="chart-cursor" x1="0" x2="0" y1="${top}" y2="${bottom}" stroke="#aabac3" stroke-dasharray="3 4" hidden/></svg><div class="chart-readout" aria-live="polite"></div>`;
 const readout=host.querySelector('.chart-readout'),cursor=host.querySelector('#chart-cursor'),svg=host.querySelector('svg');
 let selected=rows.reduce((best,r,i)=>Number.isFinite(r.actual)&&r.actual> (rows[best]?.actual??-Infinity)?i:best,0);
 const show=i=>{selected=i;const r=rows[i];cursor.removeAttribute('hidden');cursor.setAttribute('x1',x(i));cursor.setAttribute('x2',x(i));readout.innerHTML=`<time>${esc(r.timestamp.slice(5,16).replace('T',' '))}</time><span>실측 <strong>${fixed(r.actual)}</strong></span><span class="prediction-value">예측 <strong>${fixed(r.predicted)}</strong></span><span>예측−실측 <strong>${Number.isFinite(r.actual)&&Number.isFinite(r.predicted)?fixed(r.predicted-r.actual):'—'}</strong> kWh</span>`;};
 show(selected);
 svg.addEventListener('pointermove',e=>{const bounds=svg.getBoundingClientRect();show(Math.max(0,Math.min(rows.length-1,Math.round(((e.clientX-bounds.left)*w/bounds.width-left)/(right-left)*(rows.length-1)))));});
 svg.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();show(e.key==='Home'?0:e.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,selected+(e.key==='ArrowRight'?1:-1))));});
 const missing=rows.filter(r=>!Number.isFinite(r.actual)||!Number.isFinite(r.predicted)).length;
 text('[data-chart-range]',`${rows[0].timestamp.slice(0,10)}${rows[0].timestamp.slice(0,10)===rows.at(-1).timestamp.slice(0,10)?'':` – ${rows.at(-1).timestamp.slice(0,10)}`} · KST${missing?` · 결측 ${missing}시간`:''}`);
 text('[data-shared-period]',`${state.period}시간`);renderIncentives();
 value('error-rate',fixed(state.data.incentives?.[String(state.period)]?.mean_error_pct));value('rmse-period',`최근 ${rows.length}시간`);
 $$('[data-period]').forEach(e=>{const selected=Number(e.dataset.period)===state.period;e.classList.toggle('selected',selected);e.setAttribute('aria-pressed',selected);});
}
let chartWidth=0;
new ResizeObserver(entries=>{const width=Math.round(entries[0].contentRect.width);if(width>0&&width!==chartWidth){chartWidth=width;chart();}}).observe($('#overview-chart'));
function renderIncentives(){
 const report=state.data?.incentives?.[String(state.period)];$('#incentive-rows').replaceChildren();
 if(!report){['inc-error','inc-le4','inc-le6','inc-eligible','inc-excluded','inc-won'].forEach(k=>value(k,'—'));text('#incentive-period','인센티브 지표를 불러오지 못했습니다.');return;}
 const factor=Number($('#incentive-coefficient').value);
 value('inc-error',fmt(report.mean_error_pct));value('inc-le4',fmt(report.le4_pct));value('inc-le6',fmt(report.le6_pct));value('inc-eligible',report.eligible_hours);value('inc-excluded',report.excluded_hours);value('inc-won',fmt(report.scenario_krw*factor));
 text('#incentive-period',`최근 ${report.total_hours}시간 · LSTM v${state.data.model_version}`);
 text('#incentive-exclusions',Object.entries(report.excluded_reasons).map(([reason,n])=>`${reason} ${n}시간`).join(' · ')||'제외 시간 없음');
 $('#incentive-rows').innerHTML=report.rows.map(r=>`<tr><td>${esc(stamp(r.timestamp))}</td><td class="numeric">${fixed(r.utilization_pct)}</td><td class="numeric">${fixed(r.error_pct)}</td><td>${esc(r.exclusion_reason||({le4:'4% 이하',le6:'4~6%',gt6:'6% 초과'}[r.band]))}</td><td class="numeric">${fixed(r.base_rate_krw_per_kwh*factor)}</td><td class="numeric">${fixed(r.scenario_krw*factor)}</td></tr>`).join('');
}
$('#incentive-coefficient').onchange=renderIncentives;
async function loadEnergy(){
 const epoch=++state.epoch;state.data=null;$('#forecast-status').hidden=true;text('#overview-chart','시간별 자료 조회 중…');$('#forecast-hours').replaceChildren();$('#incentive-rows').replaceChildren();text('#incentive-period','조회 중…');text('#incentive-exclusions','');
 $$('[data-value]').forEach(e=>e.textContent='—');
 try{
  const d=await api(path('/ui/energy'));if(epoch!==state.epoch)return;state.data=d;
  const p=d.plant,rows=d.records,last=rows.at(-1);text('#page-description',state.demo?'데모 환경 · 합성 데이터':`${plantLabel(p)} · ${fmt(p.capacity_kw)} kW · 시간별 LSTM`);
  text('.sidebar-site strong',plantLabel(p));text('.sidebar-site div span',`${fmt(p.capacity_kw)} kW`);text('#plant-scope',`${plantLabel(p)} · 1시간 구간`);
  value('replay-date',last.timestamp.slice(0,10));value('actual',fmt(last.actual));value('actual-date',stamp(last.timestamp));value('today-prediction',fmt(last.predicted));
  value('week-mean',fmt(rows.slice(-24).reduce((a,r)=>a+r.actual,0)/24));value('week-range','최근 확정 24시간');
  value('forecast',fmt(d.forecast_total_kwh));value('tomorrow-label',d.forecast[0].timestamp.slice(0,10));value('forecast-delta','24개 시간 예측의 합계');
  value('tomorrow-irradiance',fmt(rows.slice(-24).reduce((a,r)=>a+r.irradiance,0)/24));
  $('#forecast-hours').innerHTML=d.forecast.map(r=>`<tr><td>${esc(r.timestamp.slice(11,16))}–${String((Number(r.timestamp.slice(11,13))+1)%24).padStart(2,'0')}:00</td><td class="numeric">${fixed(r.predicted_kwh)}</td></tr>`).join('');chart();
 }catch(e){renderIncentives();text('#overview-chart',`조회 실패: ${e.message}`);$('#forecast-status').hidden=false;text('#forecast-status','시간별 자료를 불러오지 못했습니다.');}
}
async function operations(){
 const pid=state.plant;
 try{
  const d=await api(path('/preview-api/operations'));if(pid!==state.plant)return;
  if(d.health.demo_mode)text('#page-description','데모 환경 · 합성 데이터');
  text('#ops-status',d.health.worker_alive?'API · AIOps 작업자 정상':'API 연결됨 · 작업자 확인 필요');text('#ops-updated',`조회 ${new Date().toLocaleTimeString('ko-KR')}`);
  text('[data-ops="health"]',d.health.status==='ok'?'정상 응답':d.health.status);text('[data-ops="model"]',`시간별 v${d.plant.current.version}`);text('[data-ops="latency"]',d.health.worker_alive?'동작 중':'확인 필요');text('[data-ops="rows"]',`${d.plant.upload.rows}시간`);text('[data-ops="range"]',d.plant.upload.end?stamp(d.plant.upload.end):'기본 보관 자료 사용');
  const m=d.plant.model;$('.current-model-panel .status-badge').textContent=`v${m.version} 운영 중`;
  $('.model-summary').innerHTML=`<div><span class="metric-label">현재 운영 모델</span><strong>Hourly LSTM v${esc(m.version)}</strong></div><dl><div><dt>${m.parent_version?'재학습 검증 RMSE':'2025 독립 검증 RMSE'}</dt><dd>${fmt(m.parent_version?m.gate.rmse_kwh:m.evaluation.rmse_kwh)} <small>kWh/시간</small></dd></div><div><dt>입력 → 출력</dt><dd>실적 24h + 예보 24h → 24h</dd></div><div><dt>배포 게이트</dt><dd>통과 · ${fmt(m.gate.limit_kwh)} kWh</dd></div></dl>`;
  if(d.plant.monitor)renderMonitor(d.plant.monitor,d.plant.jobs.find(j=>j.id===d.plant.monitor.job?.id));
 }catch(e){text('#ops-status',`연결 오류: ${e.message}`);}
}
let flowPreview=null;
let flowPreviewTimer=null;
let latestMonitor=null;
function stopFlowPreview(){
 if(!flowPreview)return;
 clearTimeout(flowPreviewTimer);
 const saved=flowPreview;flowPreview=null;
 $('.pipeline').innerHTML=saved.steps;
 text('#pipeline-status',saved.status);text('#pipeline-time',saved.time);
 $('#flow-preview').textContent='흐름 확인 테스트';$('#flow-preview').setAttribute('aria-pressed','false');
 $('.pipeline').closest('.ops-panel').removeAttribute('data-preview');
 if(latestMonitor)renderMonitor(latestMonitor.m,latestMonitor.job);
}
$('#flow-preview').onclick=()=>{
 if(flowPreview){stopFlowPreview();return;}
 flowPreview={steps:$('.pipeline').innerHTML,status:$('#pipeline-status').textContent,time:$('#pipeline-time').textContent};
 $('#flow-preview').textContent='실제 상태로 돌아가기';$('#flow-preview').setAttribute('aria-pressed','true');
 $('.pipeline').closest('.ops-panel').dataset.preview='true';
 text('#pipeline-time','화면 테스트 · 서버 변경 없음');
 const labels=['자료 확인','예측 비교','이상 감지','재학습 요청','학습·검증','모델 등록','운영 반영'];
 let active=0;
 const advance=()=>{
  if(!flowPreview)return;
  const complete=active===labels.length;
  text('#pipeline-status',complete?'화면 테스트 · 반영 완료':`화면 테스트 · ${active+1}/7 ${labels[active]}`);
  $$('.pipeline li').forEach((step,i)=>{
   const kind=i<active?'complete':i===active?'pending':'idle';step.dataset.state=kind;
   if(kind==='pending')step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');
   step.querySelector('.step-state').textContent=kind==='complete'?'✓ 완료':kind==='pending'?'◷ 진행 중':'− 대기';
  });
  if(!complete){active++;flowPreviewTimer=setTimeout(advance,1400);}
 };
 advance();
};
const jobLabels={queued:'학습 대기',running:'학습 중',succeeded:'반영 완료',rejected:'반영 보류',failed:'작업 실패'};
function monitorOutcome(m,job=null){
 const status=job?.status||m.job?.status||m.state;
 const title=jobLabels[status]||({normal:'정상 유지',held:'재학습 보류',skipped:'자료 부족',drift:'이상 감지'}[status])||'상태 확인';
 return m.reason==='existing_job_terminal'&&!['queued','running'].includes(status)?`이전 작업 · ${title}`:title;
}
function renderMonitor(m,job=null){
 latestMonitor={m,job};if(flowPreview)return;
 const status=job?.status||m.job?.status||m.state,title=monitorOutcome(m,job);
 text('#pipeline-status',jobLabels[status]||({normal:'정상 유지',held:'확인 필요',skipped:'자료 부족',drift:'이상 감지'}[status])||'상태 확인');
 text('#pipeline-time',m.end_timestamp?`검사 자료 기준 · ${stamp(m.end_timestamp)}`:'검사 결과 수신');if(m.job)state.job=m.job.id;
 if(inspectionReport&&inspectionReport.plant===state.plant&&inspectionReport.end===m.end_timestamp)text('#simulation-status',title);
 const stages=['완료','완료',m.state==='normal'?'정상':m.state==='held'?'보류':m.state==='skipped'?'자료 부족':'감지','미요청','미실행','미등록','기존 유지'];
 if(m.job){stages[3]='등록';stages[4]=({queued:'대기',running:'학습 중',succeeded:'통과',rejected:'보류',failed:'실패'}[status]||'확인 필요');if(status==='succeeded'){stages[5]='등록 완료';stages[6]=m.reason==='existing_job_terminal'?'이전 반영':'반영 완료';}else if(status==='rejected'&&job?.result?.version){stages[5]='후보 보관';}else if(status==='failed'){stages[6]='확인 필요';}}
 $$('.pipeline .step-state').forEach((e,i)=>{
  const label=stages[i];
  const kind=['완료','정상','등록','통과','등록 완료','반영 완료','이전 반영'].includes(label)?'complete':['대기','학습 중'].includes(label)?'pending':['미요청','미실행','미등록','기존 유지','후보 보관'].includes(label)?'idle':'attention';
  const step=e.closest('li');step.dataset.state=kind;if(kind==='pending')step.setAttribute('aria-current','step');else step.removeAttribute('aria-current');e.textContent=`${{complete:'✓',pending:'◷',idle:'−',attention:'!'}[kind]} ${label}`;
 });
}
let modelSwitchPending=false;
let historyRequest=0;
$('.model-panel tbody').addEventListener('click',async event=>{
 const button=event.target.closest('button[data-version]');if(!button||modelSwitchPending)return;
 const version=Number(button.dataset.version),pid=state.plant;
 modelSwitchPending=true;historyRequest++;$$('.model-activate').forEach(e=>e.disabled=true);$('#plant-filter').disabled=true;updatePlantArrows();$('#refresh-history').disabled=true;
 text('#history-status',`v${version} 적용 중…`);
 try{
  await post(`/plants/${encodeURIComponent(pid)}/rollback`,{version});
  await loadEnergy();await operations();await loadHistory();
  text('#history-status',`v${version} 운영 적용 완료`);
 }catch(e){text('#history-status',`적용 실패 · ${e.message}`);}
 finally{modelSwitchPending=false;$$('.model-activate').forEach(e=>e.disabled=false);$('#plant-filter').disabled=false;updatePlantArrows();$('#refresh-history').disabled=false;}
});
async function loadHistory(){
 const request=++historyRequest,pid=state.plant;
 try{
  const [history,alerts,current]=await Promise.all([api(path('/preview-api/dashboard/history')),api(path('/preview-api/dashboard/alerts')),api(path('/preview-api/dashboard/current'))]);if(pid!==state.plant||request!==historyRequest)return;
  $('.model-panel tbody').innerHTML=history.map(m=>`<tr><td>v${esc(m.version)}</td><td>${esc(eventStamp(m.created_at))}</td><td>${m.parent_version?'추가 학습':'최초 학습'}</td><td class="numeric">${fixed(m.gate.rmse_kwh)}</td><td>${String(m.version)===String(current.version)?'운영 중':'보관'}</td><td>${String(m.version)===String(current.version)?'<span class="model-active">현재 버전</span>':m.gate?.passed?`<button type="button" class="model-activate" data-version="${esc(m.version)}" aria-label="v${esc(m.version)} 운영 적용" ${modelSwitchPending?'disabled':''}><svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${iconPaths.refresh}</svg><span>운영 적용</span></button>`:'<span class="model-unavailable">검증 미통과</span>'}</td></tr>`).join('');
  $('.model-panel .status-badge').textContent=`v${current.version} 운영 중`;
  $('.event-list').innerHTML=alerts.map(e=>`<li><div><strong>${esc(e.kind)}</strong><p>${esc(eventStamp(e.created_at))} KST</p><details><summary>상세</summary><pre>${esc(e.payload)}</pre></details></div></li>`).join('')||'<li>아직 운영 알림이 없습니다.</li>';
  text('.events-panel .neutral-badge',`${alerts.length}건`);text('#history-status','실제 모델 등록·운영 이력');
 }catch(e){if(pid!==state.plant||request!==historyRequest)return;text('#history-status',e.message);$('.model-panel tbody').replaceChildren();$('.event-list').replaceChildren();}
}
async function generateSample(){try{const d=await api(path('/ui/sample'));$('#predict-input').value=JSON.stringify(d.prediction,null,2);text('#predict-status','실제 자료 예시 · 선택 발전소 · KST 24시간');}catch(e){text('#predict-status',e.message);}}
$('#generate-sample').onclick=generateSample;
$('#run-predict').onclick=async()=>{text('#predict-status','예측 중…');text('#predict-result','');try{const body=JSON.parse($('#predict-input').value);if(body.plant_id!==state.plant)throw Error('선택 발전소와 입력 plant_id가 다릅니다. 예시를 다시 생성하세요.');const d=await post('/predict',body);text('#predict-result',JSON.stringify(d,null,2));text('#predict-status',`24시간 예측 완료 · 합계 ${fmt(d.total_kwh)} kWh · v${d.model_version}`);}catch(e){text('#predict-status',`실패: ${e.message}`);}};
$('#simulation-button').onclick=()=>{stopFlowPreview();$('#simulation-dialog').showModal();};$('#simulation-close').onclick=()=>$('#simulation-dialog').close();
let batchPending=false;
$('#simulation-dialog').addEventListener('cancel',e=>{if(batchPending)e.preventDefault();});
function inspectionStep(active,failed=false){
 const names=['sample','check','decision'];
 names.forEach((name,i)=>{const e=$(`[data-inspection="${name}"]`),kind=i<active?'complete':i===active?(failed?'attention':'pending'):'idle';e.dataset.state=kind;e.querySelector('small').textContent={complete:'완료',pending:'진행 중',attention:'확인 필요',idle:'대기'}[kind];});
}
$('#normal-batch').onclick=async()=>{
 if(batchPending)return;batchPending=true;inspectionReport=null;let step=0;
 const buttons=[$('#normal-batch'),$('#drift-batch'),$('#simulation-close'),$('#plant-filter'),$('#previous-plant'),$('#next-plant')];buttons.forEach(b=>b.disabled=true);
 $('#simulation-dialog').dataset.state='pending';$('#simulation-dialog').setAttribute('aria-busy','true');inspectionStep(step);
 text('#simulation-result','');text('#simulation-count','—');text('#simulation-rmse','—');text('#simulation-status','자료 준비 중');
 try{
  const d=await api(path('/ui/sample'));step=1;inspectionStep(step);text('#simulation-status','예측·이상 검사 중');
  const r=await post('/predict/batch-test',d.batch);inspectionReport={plant:state.plant,end:r.monitor.end_timestamp};inspectionStep(3);$('#simulation-dialog').dataset.state='complete';
  text('#simulation-result',JSON.stringify(r,null,2));text('#simulation-count',`${r.predictions.length}시간`);text('#simulation-rmse',`${fmt(r.monitor.rmse_kwh)} kWh/시간`);
  text('#simulation-status',monitorOutcome(r.monitor));renderMonitor(r.monitor);await operations();
 }catch(e){inspectionStep(step,true);$('#simulation-dialog').dataset.state='error';text('#simulation-status',`검사 결과 확인 필요 · ${e.message}`);}
 finally{batchPending=false;$('#simulation-dialog').removeAttribute('aria-busy');buttons.forEach(b=>b.disabled=false);updatePlantArrows();}
};
$('#drift-batch').onclick=async()=>{
 const button=$('#drift-batch');button.disabled=true;text('#simulation-status','작업 상태 조회 중…');
 try{const jobs=await api(path('/jobs'));text('#simulation-result',JSON.stringify(jobs,null,2));text('#simulation-status',jobs[0]?`최근 작업 · ${jobLabels[jobs[0].status]||jobs[0].status}`:'재학습 작업 없음 · 현재 모델 유지');await operations();}
 catch(e){text('#simulation-status',`조회 실패 · ${e.message}`);}finally{button.disabled=false;}
};
$('#upload-button').onclick=()=>{stopFlowPreview();$('#upload-dialog').showModal();};$('#upload-close').onclick=()=>$('#upload-dialog').close();
$('#upload-form').onsubmit=async event=>{event.preventDefault();const b=$('#upload-submit');b.disabled=true;text('#upload-status','업로드·검증 중…');try{const f=$('#upload-file').files[0];if(!f||f.size>5*1024*1024)throw Error('5MB 이하 CSV를 선택하세요.');const form=new FormData();form.append('plant_id',state.plant);form.append('file',f);const r=await api('/data/upload',{method:'POST',body:form});text('#upload-status',`${r.rows}시간 등록 완료 · ${r.monitor.state}`);await loadEnergy();await operations();}catch(e){text('#upload-status',e.message);}finally{b.disabled=false;}};
function inspectorEntries(resource,d){
 const shown=n=>Number.isFinite(n)?fmt(n):'—';
 if(resource==='metrics')return [['요청 수',`${shown(d.requests)}건`],['오류 수',`${shown(d.errors)}건`],['평균 응답시간',d.mean_latency_ms==null?'아직 요청 없음':`${shown(d.mean_latency_ms)} ms`]];
 if(resource==='dataset')return [['자료',d.source==='uploaded'?'업로드 자료':'보관 자료'],['데이터 수',`${shown(d.rows)}시간`],['시작',stamp(d.start)],['종료',stamp(d.end)]];
 if(resource==='info')return [['실적 입력',`${shown(d.history_hours)}시간`],['예측 출력',`${shown(d.forecast_hours)}시간`],['감시 구간',`${shown(d.monitor_window_hours)}시간`],['시간대',d.timezone],['재학습 자료',`${shown(d.retrain_rows)}시간`]];
 if(resource==='current')return [['모델 버전',`v${d.version}`],['검증 RMSE',`${shown(d.evaluation?.rmse_kwh)} kWh/시간`],['게이트 기준',`${shown(d.gate?.limit_kwh)} kWh`]];
 if(resource==='predictions')return [['저장된 예측',`${d.length}건`],['최근 기록',d.length?eventStamp(d[0].created_at):'기록 없음'],['최근 모델',d.length?`v${d[0].model_version}`:'—']];
 return [];
}
let inspectorRequest=0;
let inspectorController=null;
function resetInspector(){
 inspectorRequest++;inspectorController?.abort();
 $('#inspector-summary').replaceChildren();$('#inspector-summary').hidden=true;
 $('#inspector-details').hidden=true;text('#inspector-result','');
 $('#inspector-status').hidden=true;$('.server-inspector').removeAttribute('aria-busy');
}
async function inspectServer(){
 preserveToolHeight('.server-inspector');
 resetInspector();
 const request=inspectorRequest,summary=$('#inspector-summary'),resource=$('#server-resource').value,pid=state.plant;
 inspectorController=new AbortController();
 const controller=inspectorController;
 const timeout=setTimeout(()=>controller.abort(),120000);
 $('.server-inspector').setAttribute('aria-busy','true');$('#inspector-status').hidden=false;text('#inspector-status','불러오는 중…');
 try{
  const d=await api(path('/preview-api/dashboard/'+resource),{signal:controller.signal});if(request!==inspectorRequest||pid!==state.plant)return;
  for(const [label,content] of inspectorEntries(resource,d)){
   const row=document.createElement('div'),term=document.createElement('dt'),detail=document.createElement('dd');
   term.textContent=label;detail.textContent=content;row.append(term,detail);summary.append(row);
  }
  summary.hidden=false;text('#inspector-result',JSON.stringify(d,null,2));$('#inspector-details').hidden=false;$('#inspector-status').hidden=true;
 }catch(e){if(request!==inspectorRequest)return;text('#inspector-status',controller.signal.aborted?'조회 시간 초과':`조회 실패 · ${e.message}`);}
 finally{clearTimeout(timeout);if(request===inspectorRequest)$('.server-inspector').removeAttribute('aria-busy');}
}
$('#server-resource').onchange=inspectServer;
$('.server-inspector').addEventListener('toggle',()=>{if($('.server-inspector').open)inspectServer();else{resetInspector();$('.server-inspector').style.minHeight='';}});
let logRequest=0;
let logController=null;
function preserveToolHeight(selector){
 const panel=$(selector);if(panel.open)panel.style.minHeight=`${panel.getBoundingClientRect().height}px`;
}
async function loadLogs(refreshList=false){
 preserveToolHeight('.server-logs');
 const request=++logRequest;logController?.abort();
 const controller=new AbortController();logController=controller;
 const timeout=setTimeout(()=>controller.abort(),120000),select=$('#log-files');
 const selected=select.value;
 text('#log-content','');$('#log-status').hidden=false;text('#log-status','불러오는 중…');
 $('.server-logs').setAttribute('aria-busy','true');$('#refresh-logs').disabled=true;
 if(refreshList)select.disabled=true;
 try{
  if(refreshList){
   const files=await api('/logs',{signal:controller.signal});if(request!==logRequest)return;
   select.replaceChildren(...files.map(file=>new Option(file,file)));
   if(!files.length){select.add(new Option('로그 파일 없음',''));select.disabled=true;text('#log-status','로그 파일 없음');return;}
   if(files.includes(selected))select.value=selected;
   select.disabled=files.length===1;
  }
  const file=select.value;
  if(!file){text('#log-status','로그 파일 없음');return;}
  const log=await api('/logs/'+encodeURIComponent(file),{signal:controller.signal});if(request!==logRequest)return;
  text('#log-content',log.content);$('#log-content').scrollTop=$('#log-content').scrollHeight;
  $('#log-status').hidden=Boolean(log.content);if(!log.content)text('#log-status','기록 없음');
 }catch(e){if(request!==logRequest)return;select.disabled=select.options.length<=1;text('#log-status',controller.signal.aborted?'조회 시간 초과':`조회 실패 · ${e.message}`);}
 finally{clearTimeout(timeout);if(request===logRequest){$('.server-logs').removeAttribute('aria-busy');$('#refresh-logs').disabled=false;}}
}
$('#refresh-logs').onclick=()=>loadLogs(true);
$('#log-files').onchange=()=>loadLogs();
$('.server-logs').addEventListener('toggle',()=>{
 if($('.server-logs').open)loadLogs(true);
 else{$('.server-logs').style.minHeight='';logRequest++;logController?.abort();$('.server-logs').removeAttribute('aria-busy');$('#refresh-logs').disabled=false;}
});
$('#refresh-history').onclick=loadHistory;$('#refresh-ops').onclick=operations;
$$('[data-period]').forEach(e=>e.onclick=()=>{state.period=Number(e.dataset.period);chart();});
function updatePlantArrows(){
 const select=$('#plant-filter');
 for(const button of [$('#previous-plant'),$('#next-plant')])button.disabled=select.disabled||select.options.length<2;
}
function movePlant(direction){
 const select=$('#plant-filter');if(select.disabled||select.options.length<2)return;
 select.selectedIndex=(select.selectedIndex+direction+select.options.length)%select.options.length;
 select.dispatchEvent(new Event('change'));
}
$('#previous-plant').onclick=()=>movePlant(-1);
$('#next-plant').onclick=()=>movePlant(1);
$('#plant-filter').onchange=async e=>{stopFlowPreview();latestMonitor=null;state.plant=e.target.value;resetInspector();if($('.server-inspector').open)inspectServer();state.job=null;inspectionReport=null;$$('.pipeline li').forEach(e=>{e.dataset.state='idle';e.querySelector('.step-state').textContent='대기';});$('#predict-input').value='';text('#predict-result','');text('#simulation-result','');inspectionStep(-1);text('#simulation-count','—');text('#simulation-rmse','—');text('#simulation-status','검사 대기');text('#pipeline-status','검사 전');text('#pipeline-time','새 발전소 조회');await loadEnergy();view();};
window.addEventListener('hashchange',view);
let timer;
function schedule(){clearTimeout(timer);const delay=Number($('#refresh-interval').value);if(delay)timer=setTimeout(async()=>{if(!document.hidden&&location.hash==='#service')await operations();schedule();},delay);}
$('#refresh-interval').onchange=schedule;
window.SolarLive={plant:()=>state.plant,reload:loadEnergy};
async function init(){
 $('.model-panel tbody').replaceChildren();$('.event-list').replaceChildren();$('.model-summary').textContent='모델 조회 전';$('.current-model-panel .status-badge').textContent='조회 전';
 try{const [plants,health]=await Promise.all([api('/plants'),api('/health')]);state.demo=health.demo_mode;if(!plants.some(p=>p.plant_id===state.plant))state.plant=plants[0].plant_id;
 labelPlants(plants);
 plants.sort((a,b)=>plantLabel(a).localeCompare(plantLabel(b),'ko',{numeric:true}));
 $('#plant-filter').innerHTML=plants.map(p=>`<option value="${esc(p.plant_id)}">${esc(plantLabel(p))} · ${fmt(p.capacity_kw)} kW</option>`).join('');$('#plant-filter').value=state.plant;updatePlantArrows();text('#plant-filter-note',`시간별 품질 검증 통과 ${plants.length}개소`);await loadEnergy();view();schedule();}
 catch(e){text('#page-description',`서버 연결 실패: ${e.message}`);}
}
init();
