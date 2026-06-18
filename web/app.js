const SOURCE_ORDER = ["market", "theme", "shadow", "position"];
const LABELS = {
  market_regime: "市场状态",
  equity_position_range: "权益仓位区间",
  confidence: "置信度",
  basis_trade_date: "基准交易日",
  basis_date: "基准日期",
  generated_at: "生成时间",
  run_id: "运行编号",
  top_theme: "最强主线",
  top_stage: "阶段",
  top_score: "评分",
  theme_count: "主线数量",
  up_ratio: "上涨占比",
  report_id: "报告编号",
  page: "页面",
  title: "标题",
  recommendation: "建议",
  action: "动作",
  position: "仓位",
  target: "目标",
  status: "状态",
};

const TABLE_COLUMNS = {
  market: ["name", "label", "metric", "score", "value", "status"],
  theme: ["theme", "top_stage", "top_score", "sw_score", "ths_score", "etf_score", "limit_count"],
  shadow: ["name", "theme", "subject", "score", "status", "signal", "reason"],
  position: ["name", "asset", "code", "action", "target", "position", "reason"],
};

let state = new Map();

const entryGrid = document.querySelector("#entry-grid");
const workspace = document.querySelector("#workspace");
const globalStatus = document.querySelector("#global-status");
const refreshAllButton = document.querySelector("#refresh-all");

function fmtTime(value) {
  if (!value) return "暂无";
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
  if (typeof value === "number") {
    if (Math.abs(value) >= 1000) return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 3 });
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.slice(0, 4).map(fmtValue).join(" / ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function fieldLabel(key) {
  return LABELS[key] || key.replace(/_/g, " ");
}

function isPrimitive(value) {
  return ["string", "number", "boolean"].includes(typeof value) || value === null;
}

function compactPrimitiveEntries(object, preferredKeys = []) {
  if (!object || typeof object !== "object" || Array.isArray(object)) return [];
  const keys = [
    ...preferredKeys.filter((key) => Object.prototype.hasOwnProperty.call(object, key)),
    ...Object.keys(object).filter((key) => !preferredKeys.includes(key)),
  ];
  return keys
    .filter((key) => isPrimitive(object[key]) || (Array.isArray(object[key]) && object[key].every(isPrimitive)))
    .filter((key) => !String(key).toLowerCase().includes("url"))
    .slice(0, 6)
    .map((key) => ({ label: fieldLabel(key), value: object[key] }));
}

function findFirstArray(value) {
  if (!value || typeof value !== "object") return null;
  if (Array.isArray(value)) return value.length && typeof value[0] === "object" ? value : null;
  const priority = ["theme_ranking", "ranking", "items", "signals", "actions", "positions", "rows", "data"];
  for (const key of priority) {
    const found = findFirstArray(value[key]);
    if (found) return found;
  }
  for (const key of Object.keys(value)) {
    const found = findFirstArray(value[key]);
    if (found) return found;
  }
  return null;
}

function pickSummary(source) {
  const data = source.data || {};
  if (source.id === "market") {
    return compactPrimitiveEntries(data.summary, [
      "market_regime",
      "equity_position_range",
      "confidence",
      "basis_trade_date",
      "run_id",
    ]);
  }
  if (source.id === "theme") {
    return compactPrimitiveEntries(data.latest_report, [
      "top_theme",
      "top_stage",
      "top_score",
      "theme_count",
      "up_ratio",
      "basis_date",
    ]);
  }
  const candidate = data.latest_report || data.summary || data.page || data;
  return compactPrimitiveEntries(candidate, [
    "title",
    "status",
    "recommendation",
    "action",
    "position",
    "target",
    "generated_at",
  ]);
}

function pickRows(source) {
  const rows = findFirstArray(source.data);
  if (!rows) return [];
  return rows.filter((row) => row && typeof row === "object" && !Array.isArray(row)).slice(0, 8);
}

function pickColumns(sourceId, rows) {
  const preferred = TABLE_COLUMNS[sourceId] || [];
  const available = new Set(rows.flatMap((row) => Object.keys(row)));
  const columns = preferred.filter((column) => available.has(column));
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (columns.length >= 6) return columns;
      if (!columns.includes(key) && isPrimitive(row[key])) columns.push(key);
    }
  }
  return columns.slice(0, 6);
}

function setLoading(button, loading) {
  button.classList.toggle("is-loading", loading);
  button.disabled = loading;
}

function renderEntries() {
  entryGrid.replaceChildren();
  const template = document.querySelector("#entry-template");
  for (const sourceId of SOURCE_ORDER) {
    const source = state.get(sourceId);
    if (!source) continue;
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.add(`accent-${source.accent}`);
    node.href = `#${source.id}`;
    node.querySelector(".entry-label").textContent = source.label;
    node.querySelector(".entry-subtitle").textContent = source.subtitle;
    const meta = node.querySelector(".entry-meta");
    meta.textContent = source.ok ? fmtTime(source.fetched_at) : `错误 ${source.status || ""}`.trim();
    entryGrid.append(node);
  }
}

function renderBadge(source) {
  const fragment = document.createDocumentFragment();
  const statusBadge = document.createElement("span");
  statusBadge.className = `badge ${source.ok ? "ok" : "bad"}`;
  statusBadge.textContent = source.ok ? "已连接" : "接口异常";
  fragment.append(statusBadge);

  const codeBadge = document.createElement("span");
  codeBadge.className = source.status && source.status >= 400 ? "badge bad" : "badge";
  codeBadge.textContent = source.status ? `HTTP ${source.status}` : "无状态码";
  fragment.append(codeBadge);

  const timeBadge = document.createElement("span");
  timeBadge.className = "badge";
  timeBadge.textContent = `刷新 ${fmtTime(source.fetched_at)}`;
  fragment.append(timeBadge);

  if (source.truncated) {
    const warn = document.createElement("span");
    warn.className = "badge warn";
    warn.textContent = "内容已截断";
    fragment.append(warn);
  }

  if (!source.ok && source.detail) {
    const detail = document.createElement("span");
    detail.className = "badge bad";
    detail.textContent = source.error || "详情见原始 JSON";
    fragment.append(detail);
  }
  return fragment;
}

function renderMetrics(container, source) {
  container.replaceChildren();
  const metrics = source.ok ? pickSummary(source) : [{ label: "错误", value: source.error || "接口请求失败" }];
  if (!metrics.length) {
    const item = document.createElement("div");
    item.className = "metric";
    item.innerHTML = '<p class="metric-label">状态</p><p class="metric-value">暂无可提取摘要</p>';
    container.append(item);
    return;
  }

  for (const metric of metrics) {
    const item = document.createElement("div");
    item.className = "metric";
    const label = document.createElement("p");
    label.className = "metric-label";
    label.textContent = metric.label;
    const value = document.createElement("p");
    value.className = "metric-value";
    value.textContent = fmtValue(metric.value);
    item.append(label, value);
    container.append(item);
  }
}

function renderTable(container, source) {
  container.replaceChildren();
  if (!source.ok) {
    const note = document.createElement("p");
    note.className = "empty-note";
    note.textContent = "远程接口当前不可用，恢复后刷新即可显示数据。";
    container.append(note);
    return;
  }

  const rows = pickRows(source);
  if (!rows.length) {
    const note = document.createElement("p");
    note.className = "empty-note";
    note.textContent = "当前数据没有可直接表格化的列表。";
    container.append(note);
    return;
  }

  const columns = pickColumns(source.id, rows);
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const column of columns) {
    const th = document.createElement("th");
    th.textContent = fieldLabel(column);
    headerRow.append(th);
  }
  thead.append(headerRow);
  table.append(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const td = document.createElement("td");
      td.textContent = fmtValue(row[column]);
      tr.append(td);
    }
    tbody.append(tr);
  }
  table.append(tbody);
  container.append(table);
}

function renderPanels() {
  workspace.replaceChildren();
  const template = document.querySelector("#panel-template");
  for (const sourceId of SOURCE_ORDER) {
    const source = state.get(sourceId);
    if (!source) continue;
    const panel = template.content.firstElementChild.cloneNode(true);
    panel.id = source.id;
    panel.classList.add(`accent-${source.accent}`);
    panel.querySelector(".panel-kicker").textContent = source.subtitle;
    panel.querySelector("h2").textContent = source.label;
    panel.querySelector(".source-link").href = source.url;
    panel.querySelector(".refresh-one").dataset.source = source.id;
    panel.querySelector(".panel-state").append(renderBadge(source));
    renderMetrics(panel.querySelector(".metric-grid"), source);
    renderTable(panel.querySelector(".table-wrap"), source);
    panel.querySelector("pre").textContent = JSON.stringify(source.data || source, null, 2);
    workspace.append(panel);
  }
}

function render() {
  renderEntries();
  renderPanels();
}

async function loadAll() {
  setLoading(refreshAllButton, true);
  globalStatus.textContent = "刷新中";
  try {
    const response = await fetch(`/api/sources?t=${Date.now()}`, { cache: "no-store" });
    const payload = await response.json();
    for (const source of payload.sources || []) state.set(source.id, source);
    render();
    globalStatus.textContent = `最近刷新 ${fmtTime(payload.generated_at)}`;
  } catch (error) {
    globalStatus.textContent = `刷新失败：${error.message}`;
  } finally {
    setLoading(refreshAllButton, false);
  }
}

async function loadOne(sourceId, button) {
  setLoading(button, true);
  try {
    const response = await fetch(`/api/sources/${sourceId}?t=${Date.now()}`, { cache: "no-store" });
    const payload = await response.json();
    if (payload.source) state.set(payload.source.id, payload.source);
    render();
    globalStatus.textContent = `已刷新 ${state.get(sourceId)?.label || sourceId}`;
  } catch (error) {
    globalStatus.textContent = `刷新失败：${error.message}`;
  } finally {
    setLoading(button, false);
  }
}

refreshAllButton.addEventListener("click", loadAll);
workspace.addEventListener("click", (event) => {
  const button = event.target.closest(".refresh-one");
  if (!button) return;
  loadOne(button.dataset.source, button);
});

loadAll();
