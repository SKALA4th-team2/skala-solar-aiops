/**
 * 작성자: Git 이력 참조
 * 작성목적: 실제 자료 재생을 위한 단일 화면의 차트·기간·CSV 상호작용.
 * 작성일: 2026-10-07
 * 발전량·예보는 실제 자료, 예측은 7일 비율 기준선이다. 운영 상태는 읽기 전용 프록시로 조회하며 실제 학습은 수행하지 않는다.
 */
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
const numberFormat = new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const replayDateFormat = new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" });
const weekdayFormat = new Intl.DateTimeFormat("ko-KR", { weekday: "long", timeZone: "UTC" });

let chartSummary = {replayDate:"2025-01-01",tomorrow:{date:"2025-01-02"}};
let dailyRecords = [];
let plants = [];
const previewState = { period: 7, view: "energy", plant: "hadong-sewage" };
let operationsTimer;
let operationsController;
let operationsLastSuccess;
function selectedPlants() { return previewState.plant === "all" ? plants : plants.filter((plant) => plant.id === previewState.plant); }
function selectedRecords() { return SolarDashboard.selectRecords(plants, previewState.plant); }
function chartMaximum() {
  return Math.max(350, Math.ceil(Math.max(...selectedRecords().flatMap((row) => [row.measured, row.predicted])) / 350) * 350);
}
let chartObserver;


function visibleRecords() {
  return selectedRecords().slice(-previewState.period);
}

function renderChart() {
  const host = document.getElementById("overview-chart");
  const records = visibleRecords();
  const firstRender = !host.dataset.rendered;
  chartObserver?.disconnect();
  const labelInterval = Math.max(1, Math.round(records.length / 7));
  const grid = [0, 100, 200, 300].map((amount) => amount * chartMaximum() / 350).map((amount) => `<g data-grid="${amount}"><line class="grid-line${amount === 0 ? " zero-line" : ""}"/><text text-anchor="end">${amount}</text></g>`).join("");
  const ticks = records.map((record, index) => (records.length - 1 - index) % labelInterval === 0 ? `<text data-tick="${index}" text-anchor="middle">${record.date.slice(5).replace("-", ".")}</text>` : "").join("");
  host.innerHTML = `<div class="chart-stage">
    <svg class="generation-chart" role="group" aria-label="최근 ${records.length}일 일별 발전량 비교. 실측은 검정 실선, LSTM 예측은 코랄색 점선. 단위 kWh. 현재 모델의 자료 재생 결과입니다.">
      <text x="4" y="13">kWh</text>${grid}<polyline class="prediction-path"/><polyline class="actual-path"/>${ticks}
      ${records.map((record, index) => `<circle class="chart-point" r="3" tabindex="0" role="img" data-point="${index}" aria-label="${record.date} 실측 ${numberFormat.format(record.measured)} kWh, 예측 ${numberFormat.format(record.predicted)} kWh, 일사량 예보 ${numberFormat.format(record.forecastIrradiance)} MJ/m²"/>`).join("")}
    </svg>
    <div class="chart-plot">
      <div class="chart-hit-columns" aria-hidden="true">${records.map((_, index) => `<div class="chart-hit-cell" data-chart-index="${index}"></div>`).join("")}</div>
      <div class="chart-wipe" style="--wipe-delay:${firstRender ? ".3s" : "0s"}" aria-hidden="true"></div>
      <div class="chart-tracker" aria-hidden="true" hidden><div class="chart-crosshair"></div><i class="chart-marker actual-marker"></i><i class="chart-marker predicted-marker"></i></div>
      <div class="chart-tooltip" role="tooltip" hidden><time></time><div><span><i class="tooltip-swatch actual-swatch"></i>실제</span><strong data-tooltip-value="measured"></strong></div><div><span><i class="tooltip-swatch predicted-swatch"></i>예측</span><strong data-tooltip-value="predicted"></strong></div><div><span><i class="tooltip-swatch irradiance-swatch"></i>일사량 예보</span><strong data-tooltip-value="irradiance"></strong></div></div>
    </div>
  </div>`;
  const stage = host.querySelector(".chart-stage");
  const svg = host.querySelector(".generation-chart");
  const plot = host.querySelector(".chart-plot");
  const layoutChart = () => {
    // Match the viewBox to CSS pixels so axis labels stay 12px even on mobile.
    // Updating attributes preserves the focused SVG point when the viewport changes.
    const { width, height } = stage.getBoundingClientRect();
    if (!width || !height) return;
    const left = 40;
    const top = 28;
    const plotWidth = width - left - 18;
    const plotHeight = height - top - 36;
    const x = (index) => left + (index + .5) / records.length * plotWidth;
    const y = (amount) => top + plotHeight * (1 - amount / chartMaximum());
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.querySelector(".actual-path").setAttribute("points", records.map((record, index) => `${x(index)},${y(record.measured)}`).join(" "));
    svg.querySelector(".prediction-path").setAttribute("points", records.map((record, index) => `${x(index)},${y(record.predicted)}`).join(" "));
    svg.querySelectorAll("[data-grid]").forEach((group) => {
      const gridY = y(Number(group.dataset.grid));
      const line = group.querySelector("line");
      Object.entries({ x1: left, x2: left + plotWidth, y1: gridY, y2: gridY }).forEach(([attribute, amount]) => line.setAttribute(attribute, amount));
      const label = group.querySelector("text");
      label.setAttribute("x", left - 10);
      label.setAttribute("y", gridY + 4);
    });
    svg.querySelectorAll("[data-tick]").forEach((label) => {
      const tickIndex = Number(label.dataset.tick);
      const [, month, day] = records[tickIndex].date.split("-");
      label.textContent = plotWidth < 230 ? `${Number(month)}/${Number(day)}` : `${month}.${day}`;
      label.setAttribute("x", x(tickIndex));
      label.setAttribute("y", height - 10);
    });
    svg.querySelectorAll("[data-point]").forEach((point, index) => {
      point.setAttribute("cx", x(index));
      point.setAttribute("cy", y(records[index].measured));
    });
    Object.assign(plot.style, { left: `${left}px`, top: `${top}px`, width: `${plotWidth}px`, height: `${plotHeight}px` });
  };
  layoutChart();
  chartObserver = new ResizeObserver(layoutChart);
  chartObserver.observe(stage);
  bindChartInteraction(host, records);
  host.dataset.rendered = "true";
}

function bindChartInteraction(host, records) {
  const plot = host.querySelector(".chart-plot");
  const tracker = host.querySelector(".chart-tracker");
  const tooltip = host.querySelector(".chart-tooltip");
  const cells = [...host.querySelectorAll(".chart-hit-cell")];
  const setActive = (index) => {
    tracker.hidden = index === null;
    tooltip.hidden = index === null;
    cells.forEach((cell, cellIndex) => cell.classList.toggle("is-active", index === cellIndex));
    if (index === null) return;
    const record = records[index];
    const fraction = (index + .5) / records.length;
    plot.style.setProperty("--active-x", `${fraction * 100}%`);
    plot.style.setProperty("--actual-y", `${(1 - record.measured / chartMaximum()) * 100}%`);
    plot.style.setProperty("--predicted-y", `${(1 - record.predicted / chartMaximum()) * 100}%`);
    tooltip.classList.toggle("is-flipped", fraction > .6);
    tooltip.querySelector("time").textContent = record.date;
    tooltip.querySelector("time").dateTime = record.date;
    tooltip.querySelector('[data-tooltip-value="measured"]').textContent = `${numberFormat.format(record.measured)} kWh`;
    tooltip.querySelector('[data-tooltip-value="predicted"]').textContent = `${numberFormat.format(record.predicted)} kWh`;
    tooltip.querySelector('[data-tooltip-value="irradiance"]').textContent = `${numberFormat.format(record.forecastIrradiance)} MJ/m²`;
  };
  cells.forEach((cell, index) => {
    cell.addEventListener("pointerenter", () => setActive(index));
    cell.addEventListener("pointerleave", () => setActive(null));
    cell.addEventListener("click", () => setActive(index));
  });
  host.querySelectorAll(".chart-point").forEach((point, index) => {
    point.addEventListener("focus", () => setActive(index));
    point.addEventListener("blur", () => setActive(null));
    point.addEventListener("keydown", (event) => { if (event.key === "Escape") setActive(null); });
  });
}

function renderRecords() {
  const records = visibleRecords();
  document.getElementById("generation-rows").innerHTML = [...records].reverse().map((record) => {
    const error = record.predicted - record.measured;
    return `<tr><td>${record.date}</td><td class="numeric">${numberFormat.format(record.measured)}</td><td class="numeric">${numberFormat.format(record.predicted)}</td><td class="numeric">${error > 0 ? "+" : ""}${numberFormat.format(error)}</td><td class="numeric">${numberFormat.format(record.forecastIrradiance)}</td></tr>`;
  }).join("");
  document.querySelector("[data-chart-range]").textContent = `${records[0].date.slice(5).replace("-", ".")} – ${records.at(-1).date.slice(5).replace("-", ".")}`;
  document.querySelectorAll("[data-period]").forEach((button) => {
    const selected = Number(button.dataset.period) === previewState.period;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function renderSummary() {
  const records = selectedRecords();
  const latest = records.at(-1);
  const tomorrow = { ...chartSummary.tomorrow,
    predicted: selectedPlants().reduce((sum, plant) => sum + plant.tomorrow.predicted, 0),
    forecastIrradiance: selectedPlants().reduce((sum, plant) => sum + plant.tomorrow.forecastIrradiance, 0) / selectedPlants().length };
  document.getElementById("plant-scope").textContent = `${previewState.plant === "all" ? "전체 " + plants.length + "개소" : selectedPlants()[0].name} · ${selectedPlants().reduce((sum, plant) => sum + plant.capacityKw, 0)} kW`;
  document.getElementById("plant-filter").value = previewState.plant;
  const tomorrowDay = new Date(`${chartSummary.tomorrow.date}T00:00:00Z`);
  const delta = (tomorrow.predicted / latest.predicted - 1) * 100;
  const summaries = {
    forecast: numberFormat.format(tomorrow.predicted),
    actual: numberFormat.format(latest.measured),
    "week-mean": numberFormat.format(records.slice(-7).reduce((sum, row) => sum + row.measured, 0) / 7),
    "week-range": `${dailyRecords.at(-7).date.slice(5).replace("-", ".")} – ${latest.date.slice(5).replace("-", ".")}`,
    "today-prediction": numberFormat.format(latest.predicted),
    rmse: numberFormat.format(SolarDashboard.rmse(visibleRecords())),
    "rmse-period": `최근 ${visibleRecords().length}일`,
    "record-count": `${visibleRecords().length}일`,
    "forecast-delta": `${delta >= 0 ? "+" : "−"}${numberFormat.format(Math.abs(delta))}%`,
    "replay-date": replayDateFormat.format(new Date(`${chartSummary.replayDate}T00:00:00Z`)),
    "actual-date": `${chartSummary.replayDate.slice(5).replace("-", ".")} 확정`,
    "tomorrow-label": `${chartSummary.tomorrow.date.slice(5).replace("-", ".")} ${weekdayFormat.format(tomorrowDay)}`,
    "tomorrow-irradiance": numberFormat.format(tomorrow.forecastIrradiance)
  };
  Object.entries(summaries).forEach(([key, text]) => {
    document.querySelectorAll(`[data-value="${key}"]`).forEach((element) => { element.textContent = text; });
  });
}

function renderPeriod() {
  if (!plants.length) return;
  renderChart();
  renderRecords();
  renderSummary();
}

const viewMetadata = {
  energy: ["발전 현황", "하동하수처리장 태양광 · 55 kW"],
  service: ["서비스 운영", "서버 상태 · 데이터 등록 · AIOps 검사"],
  history: ["이력 · 알림", "모델 버전 · 운영 알림"]
};

function renderView() {
  const hashView = location.hash.slice(1).split("?")[0];
  const legacyViews = { overview: "energy", forecast: "energy", models: "service", data: "energy" };
  const requestedView = legacyViews[hashView] || hashView;
  previewState.view = Object.hasOwn(viewMetadata, requestedView) ? requestedView : "energy";
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${previewState.view}`; });
  document.querySelectorAll(".nav-link").forEach((link) => {
    const selected = link.dataset.view === previewState.view;
    link.classList.toggle("selected", selected);
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const [title, description] = viewMetadata[previewState.view];
  document.getElementById("page-title").textContent = title;
  document.getElementById("breadcrumb-title").textContent = title;
  document.getElementById("page-description").textContent = description;
  document.getElementById("upload-button").hidden = previewState.view !== "service";
  document.getElementById("simulation-button").hidden = previewState.view !== "service";
  document.querySelector(".snapshot-date").hidden = previewState.view !== "energy";
  document.querySelector(".page-footer").hidden = previewState.view !== "energy";
  document.querySelector(".workspace-content").scrollTop = 0;
  document.title = `${title} · SOLAR OPS`;
  scheduleOperations(true);
}

function readPeriod() {
  // Accept both current query links and previously shared #forecast?days=… links.
  const query = new URLSearchParams(location.search);
  const legacyQuery = new URLSearchParams(location.hash.split("?")[1] || "");
  previewState.plant = plants.some((plant) => plant.id === query.get("plant")) ? query.get("plant") : "hadong-sewage";
  const requested = Number(query.get("days") || legacyQuery.get("days"));
  previewState.period = [7, 30, 90].includes(requested) ? requested : 7;
  renderView();
  renderPeriod();
}

const uploadDialog = document.getElementById("upload-dialog");
const uploadFile = document.getElementById("upload-file");
const uploadStatus = document.getElementById("upload-status");
let uploadPending = false;
document.getElementById("upload-close").addEventListener("click", () => uploadDialog.close());
uploadDialog.addEventListener("cancel", (event) => { if (uploadPending) event.preventDefault(); });
document.getElementById("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (uploadPending) return;
  const file = uploadFile.files[0];
  if (!file || !/\.csv$/i.test(file.name) || !file.size || file.size > 5 * 1024 * 1024) {
    uploadStatus.textContent = "내용이 있는 CSV 파일을 선택해 주세요. 최대 크기는 5MB입니다.";
    return;
  }
  if (location.protocol === "file:") {
    uploadStatus.textContent = "업로드하려면 API가 연결된 로컬 미리보기 서버에서 열어 주세요.";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("plant_id", window.SolarLive.plant());
  uploadPending = true;
  ["upload-submit", "upload-close", "upload-file"].forEach((id) => { document.getElementById(id).disabled = true; });
  uploadStatus.textContent = "파일을 업로드하고 있습니다…";
  try {
    const response = await fetch("/data/upload", { method: "POST", body: form, signal: AbortSignal.timeout(30000) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error === "not_configured" ? "업로드 서버가 연결되지 않았습니다. SOLAR_API_BASE_URL 설정이 필요합니다." : body.error === "invalid_csv" ? "서버가 CSV를 거부했습니다. 인코딩, 필수 열, 행 수를 확인해 주세요." : "업로드하지 못했습니다. 서버 연결을 확인한 뒤 다시 시도해 주세요.");
    if (!Number.isInteger(body.rows) || body.rows < 41) throw new Error("서버 응답을 확인할 수 없습니다. 등록 상태를 확인해 주세요.");
    uploadStatus.textContent = `${body.rows.toLocaleString()}행을 업로드했습니다. 서비스 상태에서 등록 결과를 확인할 수 있습니다.`;
    uploadFile.value = "";
    await loadEnergy(window.SolarLive.plant());
    window.dispatchEvent(new Event("plantchange"));
  } catch (error) {
    uploadStatus.textContent = error.name === "TimeoutError" ? "응답 시간이 초과되었습니다. 중복 업로드 전에 서버의 등록 상태를 확인해 주세요." : error instanceof TypeError ? "서버에 연결할 수 없습니다. 연결 상태를 확인해 주세요." : error.message;
  } finally {
    uploadPending = false;
    ["upload-submit", "upload-close", "upload-file"].forEach((id) => { document.getElementById(id).disabled = false; });
  }
});

document.querySelectorAll("[data-period]").forEach((button) => {
  button.addEventListener("click", () => {
    previewState.period = Number(button.dataset.period);
    const url = new URL(location.href);
    url.searchParams.set("days", previewState.period);
    url.hash = previewState.view;
    history.pushState(null, "", url);
    renderPeriod();
  });
});
document.getElementById("upload-button").addEventListener("click", () => { uploadStatus.textContent = ""; uploadDialog.showModal(); });
document.querySelectorAll(".view").forEach((view) => {
  view.querySelectorAll(".kpi, .panel, .forecast-card").forEach((card, index) => card.style.setProperty("--enter-delay", `${index * 60}ms`));
});
document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", () => {
  if (location.hash === link.hash) renderView();
}));
window.addEventListener("hashchange", () => {
  renderView();
  document.getElementById("main").focus({ preventScroll: true });
});
document.querySelectorAll("[data-example-date]").forEach((element) => {
  const exampleDay = new Date(`${chartSummary.replayDate}T00:00:00Z`);
  exampleDay.setUTCDate(exampleDay.getUTCDate() - Number(element.dataset.exampleDate));
  element.textContent = `${exampleDay.toISOString().slice(5, 10).replace("-", ".")} ${element.dataset.exampleTime}`;
});
document.getElementById("plant-filter").addEventListener("change", async event => {
  previewState.plant=event.target.value;
  await loadEnergy(previewState.plant);
  window.dispatchEvent(new Event('plantchange'));
});

function scheduleOperations(immediate = false) {
  clearTimeout(operationsTimer);
  if (previewState.view !== "service" || document.hidden) {
    operationsController?.abort();
    return;
  }
  const interval = Number(document.getElementById("refresh-interval").value);
  if (immediate) refreshOperations();
  else if (interval) operationsTimer = setTimeout(refreshOperations, interval);
}
async function refreshOperations() {
  if (operationsController || previewState.view !== "service" || document.hidden) return;
  const status = document.getElementById("ops-status");
  const updated = document.getElementById("ops-updated");
  const button = document.getElementById("refresh-ops");
  const setMetric = (key, text) => { document.querySelector(`[data-ops="${key}"]`).textContent = text; };
  if (location.protocol === "file:") {
    status.textContent = "운영 서버 미연결";
    updated.textContent = "API 연결 필요";
    return;
  }
  operationsController = new AbortController();
  const timeout = setTimeout(() => operationsController?.abort(), 8000);
  button.disabled = true;
  document.getElementById("live-metrics").setAttribute("aria-busy", "true");
  status.textContent = "서버 상태 확인 중…";
  try {
    const response = await fetch(`/preview-api/operations?plant_id=${encodeURIComponent(window.SolarLive.plant())}`, { signal: operationsController.signal, cache: "no-store" });
    if (!response.ok) throw new Error("Not connected");
    const snapshot = await response.json();
    if (typeof snapshot.health?.ok !== "boolean" || typeof snapshot.upload?.ok !== "boolean" || !Number.isFinite(Date.parse(snapshot.checkedAt))) throw new Error("Invalid response");
    if (!snapshot.health.ok && !snapshot.upload.ok) throw new Error("Unavailable");
    operationsLastSuccess = new Date(snapshot.checkedAt).toLocaleTimeString("ko-KR", { hour12: false });
    setMetric("health", snapshot.health.ok ? "정상 응답" : "조회 실패");
    setMetric("model", snapshot.health.ok ? (snapshot.health.modelLoaded ? "로딩 완료" : "아직 로딩 전") : "—");
    setMetric("latency", snapshot.health.ok ? `${snapshot.health.latencyMs} ms` : "—");
    setMetric("rows", snapshot.upload.ok ? (snapshot.upload.exists ? `${snapshot.upload.rows.toLocaleString("ko-KR")}행` : "등록 전") : "조회 실패");
    setMetric("range", snapshot.upload.ok && snapshot.upload.exists ? `${snapshot.upload.startDate} ~ ${snapshot.upload.endDate}` : "업로드된 자료 기준");
    status.textContent = snapshot.health.ok && snapshot.upload.ok ? "연결됨 · 서버 조회 값" : "일부 조회 실패 · 정상 항목만 반영";
    updated.textContent = `마지막 조회 ${operationsLastSuccess} · 자동 갱신`;
  } catch {
    status.textContent = operationsLastSuccess ? "갱신 실패 · 이전 조회 값" : "운영 서버 미연결";
    updated.textContent = operationsLastSuccess ? `마지막 반영 ${operationsLastSuccess} · 재조회 필요` : "API 연결 필요";
  } finally {
    clearTimeout(timeout);
    operationsController = null;
    button.disabled = false;
    document.getElementById("live-metrics").setAttribute("aria-busy", "false");
    scheduleOperations();
  }
}
document.getElementById("refresh-ops").addEventListener("click", () => { clearTimeout(operationsTimer); refreshOperations(); });
document.getElementById("refresh-interval").addEventListener("change", () => scheduleOperations(true));
document.addEventListener("visibilitychange", () => scheduleOperations(true));
window.addEventListener("pagehide", () => { clearTimeout(operationsTimer); operationsController?.abort(); });
window.addEventListener("popstate", readPeriod);

window.SolarLive = {plant:()=>previewState.plant, reload:()=>loadEnergy(previewState.plant)};
let energyGeneration=0;
async function loadEnergy(pid) {
  const generation=++energyGeneration;
  document.getElementById('plant-filter-note').textContent='모델 예측 조회 중…';
  document.getElementById('overview-chart').style.opacity='.35';
  try {
    const response=await fetch(`/ui/energy?plant_id=${encodeURIComponent(pid)}`,{signal:AbortSignal.timeout(60000)});
    const data=await response.json();
    if(generation!==energyGeneration)return;
    if(!response.ok)throw new Error(data.detail || '발전 자료 조회 실패');
    dailyRecords=data.records;chartSummary=data;
    plants=[{id:pid,name:data.plant.name,capacityKw:data.plant.capacity_kw,records:data.records,tomorrow:data.tomorrow}];
    previewState.plant=pid;renderPeriod();
    document.getElementById('plant-filter-note').textContent=`${data.source==='uploaded'?'업로드 자료':'과거 실적 재생'} · LSTM v${data.model_version} · 현 모델 재계산, 독립 성능평가 아님`;
    document.querySelector('.sidebar-site strong').textContent=data.plant.name;
    document.querySelector('.sidebar-site div > span').textContent=`${data.plant.capacity_kw} kW`;
    viewMetadata.energy[1]=`${data.plant.name} · ${data.plant.capacity_kw} kW`;
    document.getElementById('page-description').textContent=viewMetadata[previewState.view][1];
    document.querySelector('.forecast-note').textContent=`실제 LSTM v${data.model_version} · 자료 기준일 다음 날 예측`;
  }catch(error){if(generation===energyGeneration){plants=[];document.getElementById('plant-filter-note').textContent=error.message;document.querySelectorAll('[data-value]').forEach(e=>e.textContent='—');document.getElementById('overview-chart').replaceChildren();}}
  finally{if(generation===energyGeneration)document.getElementById('overview-chart').style.opacity='1';}
}
async function initializeLive(){
  renderView();
  try{
    const response=await fetch('/plants');if(!response.ok)throw new Error('발전소 목록 조회 실패');
    const available=await response.json();const select=document.getElementById('plant-filter');
    select.replaceChildren(...available.filter(p=>p.ready).map(p=>new Option(`${p.name} · ${p.plant_id}`,p.plant_id)));
    const requested=new URLSearchParams(location.search).get('plant');
    if(available.some(p=>p.plant_id===requested&&p.ready))previewState.plant=requested;
    select.value=previewState.plant;await loadEnergy(previewState.plant);
  }catch(error){document.getElementById('plant-filter-note').textContent=error.message;}
}

initializeLive();
