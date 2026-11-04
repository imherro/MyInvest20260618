const state = {
  payload: null,
  loading: false,
};

const els = {
  sessionPill: document.querySelector("#session-pill"),
  clockPill: document.querySelector("#clock-pill"),
  updatedPill: document.querySelector("#updated-pill"),
  refreshButton: document.querySelector("#refresh-button"),
  fullscreenButton: document.querySelector("#fullscreen-button"),
  marketPrediction: document.querySelector("#market-prediction"),
  marketScore: document.querySelector("#market-score"),
  marketRegime: document.querySelector("#market-regime"),
  positionRange: document.querySelector("#position-range"),
  marketMetrics: document.querySelector("#market-metrics"),
  indexQuotes: document.querySelector("#index-quotes"),
  industryList: document.querySelector("#industry-list"),
  strategyList: document.querySelector("#strategy-list"),
  channelCount: document.querySelector("#channel-count"),
  focusList: document.querySelector("#focus-list"),
  alertCount: document.querySelector("#alert-count"),
  holdingList: document.querySelector("#holding-list"),
  sourceCount: document.querySelector("#source-count"),
  alertList: document.querySelector("#alert-list"),
  scoreCanvas: document.querySelector("#score-canvas"),
};

function fmtTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function fmtValue(value) {
  if (value === null || value === undefined || value === "") return "暂无";
  if (typeof value === "number") return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function fmtPct(value) {
  if (typeof value !== "number") return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function pctClass(value) {
  if (typeof value !== "number") return "pct-flat";
  if (value > 0) return "pct-up";
  if (value < 0) return "pct-down";
  return "pct-flat";
}

function metricValue(metrics, label) {
  return metrics?.find((metric) => metric.label === label)?.value;
}

function numericScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, number));
}

function colorForScore(score) {
  if (score >= 70) return "#147d52";
  if (score >= 45) return "#ad5f00";
  return "#b42318";
}

function drawGauge(score) {
  const canvas = els.scoreCanvas;
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const center = size / 2;
  const radius = size * 0.38;
  const start = Math.PI * 0.78;
  const end = Math.PI * 2.22;
  const progress = start + (end - start) * (score / 100);

  ctx.clearRect(0, 0, size, size);
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.arc(center, center, radius, start, end);
  ctx.lineWidth = 18;
  ctx.strokeStyle = "#dce7ef";
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(center, center, radius, start, progress);
  ctx.lineWidth = 18;
  ctx.strokeStyle = colorForScore(score);
  ctx.stroke();
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderClock(payload) {
  const clock = payload.market_clock;
  els.sessionPill.textContent = `${clock.label} · ${clock.detail}`;
  els.sessionPill.classList.toggle("warn", !clock.is_live);
  els.clockPill.textContent = fmtTime(clock.now);
  els.updatedPill.textContent = `刷新 ${fmtTime(payload.generated_at)}`;
}

function renderPredictionBlock(prediction) {
  els.marketPrediction.replaceChildren();
  if (!prediction) {
    els.marketPrediction.append(node("div", "empty-state", "暂无市场判断"));
    return;
  }
  const head = node("div", "prediction-title");
  head.append(node("strong", "", prediction.direction));
  head.append(node("span", "probability", `大概率 ${prediction.probability}%`));
  els.marketPrediction.append(head);
  els.marketPrediction.append(node("p", "", prediction.stance));
  const evidence = node("ul", "evidence-list");
  (prediction.evidence || []).forEach((item) => evidence.append(node("li", "", item)));
  els.marketPrediction.append(evidence);
}

function renderMarket(payload) {
  const market = payload.channels.find((channel) => channel.id === "market");
  const metrics = market?.metrics || [];
  const score = numericScore(metricValue(metrics, "市场分"));
  const regime = fmtValue(metricValue(metrics, "市场状态"));
  const range = fmtValue(metricValue(metrics, "权益区间"));

  renderPredictionBlock(payload.predictions?.market);
  els.marketScore.textContent = market?.ok ? score.toFixed(1) : "--";
  els.marketRegime.textContent = market?.ok ? regime : "接口异常";
  els.positionRange.textContent = market?.ok ? range : "参考模式";
  drawGauge(market?.ok ? score : 0);

  els.marketMetrics.replaceChildren();
  metrics.slice(0, 4).forEach((metric) => {
    const row = node("div", "metric");
    row.append(node("span", "", metric.label));
    row.append(node("strong", "", fmtValue(metric.value)));
    els.marketMetrics.append(row);
  });

  els.indexQuotes.replaceChildren();
  const indexQuotes = (payload.live_quotes?.quotes || []).filter((quote) => quote.group === "market");
  indexQuotes.forEach((quote) => els.indexQuotes.append(renderQuoteCell(quote)));
}

function renderQuoteCell(quote) {
  const cell = node("article", "quote-cell");
  const main = node("div", "quote-main");
  main.append(node("strong", "", quote.label || quote.name));
  main.append(node("span", pctClass(quote.pct_chg), fmtPct(quote.pct_chg)));
  cell.append(main);
  cell.append(node("span", "muted-line", `${fmtValue(quote.price)} · 主力 ${fmtMoney(quote.main_net_inflow)}`));
  return cell;
}

function renderPredictions(payload) {
  const industry = payload.predictions?.industries || {};
  const strategies = payload.predictions?.strategies || [];
  const leaders = industry.leaders || [];
  const concepts = industry.hot_concepts || [];
  els.channelCount.textContent = `${leaders.length}/${strategies.length}`;

  els.industryList.replaceChildren();
  [...leaders.slice(0, 6), ...concepts.slice(0, 4)].forEach((item) => {
    const row = node("article", "prediction-row");
    const head = node("div", "prediction-row-head");
    head.append(node("h4", "", item.name));
    head.append(node("span", "tag", `概率 ${item.probability}%`));
    row.append(head);
    row.append(node("p", "", `${item.outlook} · 涨跌 ${fmtPct(item.pct_chg)} · 主力 ${fmtMoney(item.main_net_inflow)}`));
    els.industryList.append(row);
  });
  if (!els.industryList.children.length) els.industryList.append(node("div", "empty-state", "暂无行业判断"));

  els.strategyList.replaceChildren();
  strategies.forEach((item) => {
    const row = node("article", "prediction-row");
    const head = node("div", "prediction-row-head");
    head.append(node("h4", "", item.name));
    head.append(node("span", "tag", `概率 ${item.probability}%`));
    row.append(head);
    const quotePct = item.quote ? fmtPct(item.quote.pct_chg) : "无日内报价";
    row.append(node("p", "", `${item.outlook} · 权重 ${fmtPct(item.weight)} · ${quotePct}`));
    els.strategyList.append(row);
  });
}

function renderFocus(payload) {
  const focus = payload.predictions?.focus_assets || [];
  els.focusList.replaceChildren();
  els.alertCount.textContent = String(focus.length);
  focus.forEach((item) => {
    const row = node("article", "focus-row");
    const head = node("div", "focus-row-head");
    head.append(node("h4", "", `${item.type} · ${item.name}`));
    head.append(node("span", "tag", `优先级 ${fmtValue(item.priority)}`));
    row.append(head);
    row.append(node("p", "", item.reason));
    els.focusList.append(row);
  });
  if (!focus.length) els.focusList.append(node("div", "empty-state", "暂无重点关注"));
}

function renderHoldings(payload) {
  const monitor = payload.position_monitor || {};
  const holdings = monitor.holdings || [];
  els.sourceCount.textContent = String(holdings.length);
  els.holdingList.replaceChildren();
  holdings.slice(0, 10).forEach((item) => {
    const row = node("article", "holding-row");
    const head = node("div", "holding-row-head");
    head.append(node("h4", "", item.name));
    const pct = item.quote?.pct_chg;
    head.append(node("span", pctClass(pct), fmtPct(pct)));
    row.append(head);
    row.append(node("p", "", `${item.symbol} · 持仓占比 ${fmtPct(item.weight_pct)} · ${item.status}`));
    els.holdingList.append(row);
  });

  els.alertList.replaceChildren();
  (payload.alerts || []).forEach((alert) => {
    const row = node("article", `alert-row ${alert.level || ""}`);
    row.append(node("h3", "", alert.title));
    row.append(node("p", "", alert.message));
    els.alertList.append(row);
  });
}

function fmtMoney(value) {
  if (typeof value !== "number") return "--";
  return `${(value / 100000000).toFixed(2)}亿`;
}

function render(payload) {
  state.payload = payload;
  renderClock(payload);
  renderMarket(payload);
  renderPredictions(payload);
  renderFocus(payload);
  renderHoldings(payload);
}

function renderLoadingState() {
  els.updatedPill.textContent = "正在判断市场";
  els.marketPrediction.replaceChildren(node("div", "empty-state", "正在读取实时行情和策略上下文"));
  els.industryList.replaceChildren(node("div", "empty-state", "正在读取行业强弱"));
  els.strategyList.replaceChildren(node("div", "empty-state", "正在读取策略锚点"));
  els.focusList.replaceChildren(node("div", "empty-state", "正在生成重点关注"));
}

async function loadDashboard(refresh = false) {
  if (state.loading) return;
  state.loading = true;
  els.refreshButton.disabled = true;
  els.refreshButton.textContent = "判断中";
  if (!state.payload) renderLoadingState();
  try {
    const response = await fetch(`/api/index${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    render(payload);
  } catch (error) {
    els.focusList.replaceChildren();
    const row = node("article", "focus-row");
    row.append(node("h4", "", "本地服务读取失败"));
    row.append(node("p", "", error.message || String(error)));
    els.focusList.append(row);
  } finally {
    state.loading = false;
    els.refreshButton.disabled = false;
    els.refreshButton.textContent = "刷新";
  }
}

async function enterFullscreen() {
  const root = document.documentElement;
  if (!document.fullscreenElement && root.requestFullscreen) {
    await root.requestFullscreen();
    return;
  }
  if (document.exitFullscreen) await document.exitFullscreen();
}

els.refreshButton.addEventListener("click", () => loadDashboard(true));
els.fullscreenButton.addEventListener("click", () => {
  enterFullscreen().catch(() => {});
});

loadDashboard();
setInterval(() => loadDashboard(false), 60 * 1000);
