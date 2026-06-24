const CHANNELS = [
  {
    id: "market",
    label: "市场",
    subtitle: "A股市场评分",
    home_url: "https://market.okbbc.com/",
    accent: "market",
  },
  {
    id: "theme",
    label: "主线",
    subtitle: "主题主线排名",
    home_url: "https://theme.okbbc.com/",
    accent: "theme",
  },
  {
    id: "shadow",
    label: "影子",
    subtitle: "影子观察",
    home_url: "https://shadow.okbbc.com/",
    accent: "shadow",
  },
  {
    id: "leader",
    label: "龙头",
    subtitle: "龙头研究",
    home_url: "https://leader.okbbc.com/",
    accent: "leader",
  },
  {
    id: "position",
    label: "操作",
    subtitle: "仓位与执行",
    home_url: "https://position.okbbc.com/",
    accent: "position",
  },
];
const SOURCE_ORDER = CHANNELS.map((source) => source.id);
const CHANNEL_BY_ID = new Map(CHANNELS.map((source) => [source.id, source]));
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
  theme: "主线",
  theme_name: "主线",
  theme_count: "主线数量",
  up_ratio: "上涨占比",
  report_id: "报告编号",
  signal_type: "类型",
  state: "状态",
  score: "分数",
  code: "代码",
  name: "名称",
  symbol: "标的",
  page: "页面",
  title: "标题",
  recommendation: "建议",
  action: "动作",
  position: "仓位",
  target: "目标",
  target_delta: "调整%",
  target_weight_ratio: "目标%",
  previous_weight_ratio: "前次%",
  drift_ratio: "变化%",
  sleeve: "分组",
  priority: "优先级",
  status: "状态",
  item_count: "数量",
  tracking_result: "评级",
  deep_rating: "深研评级",
  deep_label: "深研标签",
  deep_score: "深研分",
  candidate_leader_tier: "龙头层级",
  candidate_leader_claim: "龙头认定",
  candidate_evidence_score: "证据分",
  shadow_observation_eligible: "影子观察",
  pct_chg: "涨跌幅",
};

const TABLE_COLUMNS = {
  market: ["name", "label", "metric", "score", "value", "status"],
  theme: ["signal_type", "theme", "state", "score"],
  shadow: ["code", "name", "target_weight_ratio", "drift_ratio", "pct_chg"],
  position: ["symbol", "action", "target_delta", "priority", "confidence"],
  leader: ["name", "code", "theme", "tracking_result", "deep_score"],
};

const TABLE_COLUMN_LIMITS = {
  theme: 4,
  shadow: 5,
  position: 5,
  leader: 5,
};

const POLICY_MAINLINE_STATES = new Set(["accelerating", "sustained"]);
const MARKET_HEAT_STAGES = ["主线确认", "次主线"];
const POST_CLOSE_READY_HOUR = 20;

const LOCAL_CACHE_KEY = "myinvest20260618:sources:v1";
const LOCAL_CACHE_TTL_MS = 10 * 60 * 1000;

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

function fmtDateUTC(date) {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function chinaDateParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
    hour12: false,
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
    hour: Number(values.hour),
  };
}

function isWeekendUTC(date) {
  const day = date.getUTCDay();
  return day === 0 || day === 6;
}

function previousWeekdayUTC(date) {
  const result = new Date(date.getTime());
  do {
    result.setUTCDate(result.getUTCDate() - 1);
  } while (isWeekendUTC(result));
  return result;
}

function expectedBasisDate(now = new Date()) {
  const parts = chinaDateParts(now);
  let date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  if (isWeekendUTC(date) || parts.hour < POST_CLOSE_READY_HOUR) {
    date = previousWeekdayUTC(date);
  }
  return fmtDateUTC(date);
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

function normalizeBasisDate(value) {
  if (!value) return null;
  const match = String(value).match(/\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : null;
}

function sourceBasisDate(source) {
  const data = source?.data || {};
  const sourceMap = {
    market: data.summary?.basis_trade_date,
    theme: data.latest_report?.basis_date,
    shadow: data.run?.basis_date || data.metrics?.basis_date,
    leader: data.report?.basis_date,
    position: data.page?.basis_date,
  };
  return normalizeBasisDate(sourceMap[source?.id]);
}

function referenceBasisDate() {
  return sourceBasisDate(state.get("market")) || expectedBasisDate();
}

function basisFreshness(source) {
  if (!source || source.pending || !source.ok) return null;
  const basis = sourceBasisDate(source);
  const expected = source.id === "market" ? expectedBasisDate() : referenceBasisDate();
  if (!basis) {
    return {
      status: "missing",
      basis,
      expected,
      message: expected ? `未找到基准日，应为 ${expected}` : "未找到基准日",
    };
  }
  if (expected && basis < expected) {
    return {
      status: "stale",
      basis,
      expected,
      message: `基准日 ${basis}，应为 ${expected}`,
    };
  }
  return {
    status: "ok",
    basis,
    expected,
    message: `基准日 ${basis}`,
  };
}

function withBasisMetrics(metrics, source) {
  const freshness = basisFreshness(source);
  if (!freshness) return metrics;
  const next = [...metrics];
  const hasBasis = next.some((metric) => ["基准日期", "基准交易日", "数据基准日"].includes(metric.label));
  if (!hasBasis && freshness.basis) next.unshift({ label: "数据基准日", value: freshness.basis });
  if (freshness.status !== "ok") next.unshift({ label: "更新提示", value: freshness.message });
  return next;
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

function leaderKeyResultItems(data) {
  const items = data?.key_results?.primary_output?.items;
  return Array.isArray(items) ? items : [];
}

function leaderKeyResultTitle(data) {
  const sections = data?.page?.sections;
  if (!Array.isArray(sections)) return "A可跟踪龙头";
  const keyResultSection = sections.find((section) => section?.id === "key-results");
  return keyResultSection?.title || "A可跟踪龙头";
}

function shadowAllocationItems(data) {
  const allocations = data?.allocations;
  return Array.isArray(allocations) ? allocations : [];
}

function themePolicyMainlineItems(data) {
  const items = data?.mainline_ranking;
  return Array.isArray(items) ? items : [];
}

function themeMarketHeatItems(data) {
  const items = data?.theme_ranking;
  return Array.isArray(items) ? items : [];
}

function averageNumbers(values) {
  const numbers = values.filter((value) => typeof value === "number");
  if (!numbers.length) return null;
  return numbers.reduce((total, value) => total + value, 0) / numbers.length;
}

function themeSignalRows(data) {
  const policyRows = themePolicyMainlineItems(data)
    .filter((item) => POLICY_MAINLINE_STATES.has(item.lifecycle_state))
    .map((item) => ({
      signal_type: "政策主线",
      theme: item.theme_name,
      state: item.lifecycle_state,
      score: item.mainline_score_v6,
    }));
  const heatRows = themeMarketHeatItems(data)
    .filter((item) => MARKET_HEAT_STAGES.some((stage) => String(item.stage || "").includes(stage)))
    .map((item) => ({
      signal_type: "市场热度",
      theme: item.theme,
      state: item.stage,
      score: averageNumbers([item.sw_score, item.ths_score, item.etf_score]),
    }));
  return [...policyRows, ...heatRows].slice(0, 8);
}

function leaderTrackingResult(item) {
  return [item.deep_rating, item.deep_label].filter(Boolean).join(" ");
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
  if (source.id === "leader") {
    return compactPrimitiveEntries(
      {
        title: leaderKeyResultTitle(data),
        item_count: leaderKeyResultItems(data).length,
        report_id: data.report?.report_id,
        generated_at: data.report?.generated_at,
      },
      ["title", "item_count", "report_id", "generated_at"],
    );
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
  if (source.id === "theme") {
    return themeSignalRows(source.data);
  }
  if (source.id === "shadow") {
    return shadowAllocationItems(source.data)
      .map((item) => ({
        code: item.display_code || item.code,
        name: item.name,
        target_weight_ratio: item.target_weight_ratio,
        drift_ratio: item.drift_ratio,
        pct_chg: item.pct_chg,
      }))
      .slice(0, 8);
  }
  if (source.id === "leader") {
    return leaderKeyResultItems(source.data)
      .map((item) => ({
        name: item.name,
        code: item.code,
        theme: item.theme,
        tracking_result: leaderTrackingResult(item),
        deep_score: item.deep_score,
      }))
      .slice(0, 8);
  }
  const rows = findFirstArray(source.data);
  if (!rows) return [];
  return rows.filter((row) => row && typeof row === "object" && !Array.isArray(row)).slice(0, 8);
}

function pickColumns(sourceId, rows) {
  const preferred = TABLE_COLUMNS[sourceId] || [];
  const available = new Set(rows.flatMap((row) => Object.keys(row)));
  const maxColumns = TABLE_COLUMN_LIMITS[sourceId] || 6;
  const columns = preferred.filter((column) => available.has(column)).slice(0, maxColumns);
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (columns.length >= maxColumns) return columns;
      if (!columns.includes(key) && isPrimitive(row[key])) columns.push(key);
    }
  }
  return columns.slice(0, maxColumns);
}

function setLoading(button, loading) {
  button.classList.toggle("is-loading", loading);
  button.disabled = loading;
}

function baseSource(sourceId) {
  return {
    ...CHANNEL_BY_ID.get(sourceId),
    id: sourceId,
    ok: null,
    pending: true,
    data: null,
  };
}

function initializeShell() {
  for (const sourceId of SOURCE_ORDER) {
    if (!state.has(sourceId)) state.set(sourceId, baseSource(sourceId));
  }
  render();
  globalStatus.textContent = "入口已就绪，数据后台更新中";
}

function renderEntries() {
  entryGrid.replaceChildren();
  const template = document.querySelector("#entry-template");
  for (const sourceId of SOURCE_ORDER) {
    const source = state.get(sourceId);
    if (!source) continue;
    const node = template.content.firstElementChild.cloneNode(true);
    node.classList.add(`accent-${source.accent}`);
    node.href = source.home_url;
    node.querySelector(".entry-label").textContent = source.label;
    node.querySelector(".entry-subtitle").textContent = source.subtitle;
    const meta = node.querySelector(".entry-meta");
    if (source.pending) {
      meta.textContent = "入口";
    } else {
      const freshness = basisFreshness(source);
      if (freshness?.status === "stale") {
        meta.textContent = `滞后 ${freshness.basis}`;
      } else if (freshness?.status === "missing") {
        meta.textContent = "缺基准日";
      } else if (freshness?.basis) {
        meta.textContent = `基准 ${freshness.basis}`;
      } else {
        meta.textContent = source.ok ? fmtTime(source.fetched_at) : `错误 ${source.status || ""}`.trim();
      }
    }
    entryGrid.append(node);
  }
}

function renderBadge(source) {
  const fragment = document.createDocumentFragment();
  if (source.pending) {
    const readyBadge = document.createElement("span");
    readyBadge.className = "badge ok";
    readyBadge.textContent = "入口可用";
    fragment.append(readyBadge);

    const updateBadge = document.createElement("span");
    updateBadge.className = "badge";
    updateBadge.textContent = "后台更新中";
    fragment.append(updateBadge);
    return fragment;
  }

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

  const freshness = basisFreshness(source);
  if (freshness) {
    const basisBadge = document.createElement("span");
    basisBadge.className = freshness.status === "ok" ? "badge ok" : "badge warn";
    basisBadge.textContent = freshness.basis ? `基准 ${freshness.basis}` : "缺基准日";
    fragment.append(basisBadge);

    if (freshness.status !== "ok" && freshness.expected) {
      const expectedBadge = document.createElement("span");
      expectedBadge.className = "badge warn";
      expectedBadge.textContent = `应为 ${freshness.expected}`;
      fragment.append(expectedBadge);
    }
  }

  if (source.cache) {
    const cacheBadge = document.createElement("span");
    cacheBadge.className = source.cache.hit ? "badge" : "badge ok";
    if (source.cache.hit) {
      const minutes = Math.max(1, Math.ceil(source.cache.ttl_remaining_seconds / 60));
      cacheBadge.textContent = `缓存 ${minutes} 分`;
    } else {
      cacheBadge.textContent = "已更新缓存";
    }
    fragment.append(cacheBadge);
  }

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
  let metrics;
  if (source.pending) {
    metrics = [
      { label: "频道入口", value: "可直接打开" },
      { label: "数据状态", value: "后台更新中" },
    ];
  } else {
    metrics = source.ok ? pickSummary(source) : [{ label: "错误", value: source.error || "接口请求失败" }];
    metrics = source.ok ? withBasisMetrics(metrics, source) : metrics;
  }
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
  if (source.pending) {
    const note = document.createElement("p");
    note.className = "empty-note";
    note.textContent = "频道入口已显示，数据正在后台读取。";
    container.append(note);
    return;
  }

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
    panel.querySelector(".source-link").href = source.home_url;
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

function sourceSnapshot(generatedAt = new Date().toISOString()) {
  return {
    generated_at: generatedAt,
    stored_at: Date.now(),
    sources: SOURCE_ORDER.map((sourceId) => state.get(sourceId))
      .filter((source) => source && !source.pending),
  };
}

function readLocalSnapshot() {
  try {
    const raw = localStorage.getItem(LOCAL_CACHE_KEY);
    if (!raw) return null;
    const snapshot = JSON.parse(raw);
    if (!Array.isArray(snapshot.sources) || !snapshot.stored_at) return null;
    const ageMs = Date.now() - snapshot.stored_at;
    if (ageMs > LOCAL_CACHE_TTL_MS) {
      localStorage.removeItem(LOCAL_CACHE_KEY);
      return null;
    }
    const remainingSeconds = Math.max(1, Math.ceil((LOCAL_CACHE_TTL_MS - ageMs) / 1000));
    snapshot.sources = snapshot.sources.map((source) => ({
      ...source,
      cache: {
        ...(source.cache || {}),
        hit: true,
        ttl_seconds: LOCAL_CACHE_TTL_MS / 1000,
        ttl_remaining_seconds: remainingSeconds,
      },
    }));
    return snapshot;
  } catch {
    return null;
  }
}

function writeLocalSnapshot(payload) {
  try {
    const sources = (payload?.sources || []).filter((source) => !source.pending);
    if (!sources.length) return;
    localStorage.setItem(
      LOCAL_CACHE_KEY,
      JSON.stringify({
        generated_at: payload.generated_at,
        stored_at: Date.now(),
        sources,
      }),
    );
  } catch {
    // Local storage is best-effort; service-side cache still works.
  }
}

function clearLocalSnapshot() {
  try {
    localStorage.removeItem(LOCAL_CACHE_KEY);
  } catch {
    // Ignore storage restrictions.
  }
}

function applySources(payload) {
  for (const source of payload.sources || []) state.set(source.id, source);
  render();
}

function hydrateFromLocalSnapshot() {
  const snapshot = readLocalSnapshot();
  if (!snapshot) return false;
  applySources(snapshot);
  globalStatus.textContent = `本地缓存 ${fmtTime(snapshot.generated_at)}`;
  return true;
}

function sourceRequestUrl(path, forceRefresh) {
  const params = new URLSearchParams({ t: Date.now().toString() });
  if (forceRefresh) params.set("refresh", "1");
  return `${path}?${params.toString()}`;
}

async function loadAll({ forceRefresh = false, quiet = false } = {}) {
  if (forceRefresh) clearLocalSnapshot();
  if (!quiet) {
    setLoading(refreshAllButton, true);
    globalStatus.textContent = forceRefresh ? "清缓存刷新中" : "加载中";
  }
  try {
    const response = await fetch(sourceRequestUrl("/api/sources", forceRefresh), { cache: "no-store" });
    const payload = await response.json();
    applySources(payload);
    writeLocalSnapshot(payload);
    globalStatus.textContent = `最近刷新 ${fmtTime(payload.generated_at)}`;
  } catch (error) {
    if (!quiet || !state.size) globalStatus.textContent = `刷新失败：${error.message}`;
  } finally {
    if (!quiet) setLoading(refreshAllButton, false);
  }
}

async function loadOne(sourceId, button, { forceRefresh = true } = {}) {
  if (forceRefresh) clearLocalSnapshot();
  setLoading(button, true);
  try {
    const response = await fetch(sourceRequestUrl(`/api/sources/${sourceId}`, forceRefresh), { cache: "no-store" });
    const payload = await response.json();
    if (payload.source) state.set(payload.source.id, payload.source);
    render();
    writeLocalSnapshot(sourceSnapshot(payload.generated_at));
    globalStatus.textContent = `已刷新 ${state.get(sourceId)?.label || sourceId}`;
  } catch (error) {
    globalStatus.textContent = `刷新失败：${error.message}`;
  } finally {
    setLoading(button, false);
  }
}

refreshAllButton.addEventListener("click", () => loadAll({ forceRefresh: true }));
workspace.addEventListener("click", (event) => {
  const button = event.target.closest(".refresh-one");
  if (!button) return;
  loadOne(button.dataset.source, button, { forceRefresh: true });
});

initializeShell();
hydrateFromLocalSnapshot();
loadAll({ quiet: true });
