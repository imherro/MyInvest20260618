async function getJson(url) {
  const requestUrl = new URL(url, window.location.origin);
  requestUrl.searchParams.set("_t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function percentText(value) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function signedRatioText(value) {
  if (typeof value !== "number") return "--";
  const percent = value * 100;
  const sign = percent > 0 ? "+" : "";
  return `${sign}${percent.toFixed(2)}%`;
}

function fixedText(value, digits = 2) {
  if (typeof value !== "number") return "--";
  return value.toFixed(digits);
}

function integerText(value) {
  if (typeof value !== "number") return "--";
  return value.toLocaleString("zh-CN");
}

function scoreText(value) {
  if (typeof value !== "number") return "--";
  return value.toFixed(3);
}

function signedPointText(value) {
  if (typeof value !== "number") return "--";
  const percent = value * 100;
  const sign = percent > 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}pct`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function styleLabel(value) {
  const labels = {
    growth: "成长/科技",
    value: "价值/大盘",
    low_vol: "红利/低波",
    dividend: "红利/低波",
    small_cap: "中小盘",
    cash_proxy: "现金/债券代理",
  };
  return labels[value] || value || "--";
}

function styleAllocationLabel(value) {
  const labels = {
    growth: "成长/科技",
    value: "价值/大盘",
    low_vol: "低波",
    dividend: "红利",
    small_cap: "中小盘",
  };
  return labels[value] || value || "--";
}

function regimeLabel(value) {
  const labels = {
    bull: "牛市",
    bear: "熊市",
    range: "震荡",
    transition: "过渡",
    recovery: "修复",
    contraction: "收缩",
  };
  return labels[value] || value || "--";
}

function rotationSignalLabel(value) {
  if (!value) return "--";
  if (value === "hold_universe") return "保持观察池";
  if (value === "insufficient_data") return "样本不足";
  if (value.startsWith("rotate_to_")) return `转向${styleLabel(value.replace("rotate_to_", ""))}`;
  return value;
}

const ETF_ASSET_ORDER = [
  { code: "159915.SZ", style: "成长/科技", name: "创业板ETF", color: "#ef4444" },
  { code: "510500.SH", style: "中小盘", name: "中证500ETF", color: "#f97316" },
  { code: "510300.SH", style: "价值/大盘", name: "沪深300ETF", color: "#eab308" },
  { code: "510880.SH", style: "红利/低波", name: "红利ETF", color: "#64748b" },
  { code: "511880.SH", style: "现金/债券代理", name: "银华日利ETF", color: "#cbd5e1" },
];

function setSummaryTiles(items) {
  const target = document.getElementById("summaryTiles");
  if (!target) return;
  target.innerHTML = items
    .map(
      (item) => `
        <div class="summary-tile">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </div>
      `
    )
    .join("");
}

function weightsHtml(weights, reason) {
  const weightMap = weights || {};
  const changeMap = new Map((reason?.weight_changes || []).map((item) => [item.code, item.change]));
  const visualFloor = 0.012;
  const visualWeights = ETF_ASSET_ORDER.map((asset) => {
    const weight = Math.max(0, Number(weightMap[asset.code] || 0));
    return { ...asset, weight, visualWeight: weight > 0 ? weight : visualFloor };
  });
  const visualTotal = visualWeights.reduce((sum, asset) => sum + asset.visualWeight, 0) || 1;
  return `
    <div class="allocation-cell">
      <div class="allocation-stack" aria-label="本次目标仓位横向分配图">
        ${visualWeights.map((asset) => {
          const emptyClass = asset.weight > 0 ? "" : " is-empty";
          return `
            <span
              class="allocation-segment${emptyClass}"
              title="${escapeHtml(asset.style)} ${escapeHtml(asset.code)} ${percentText(asset.weight)}${asset.weight > 0 ? "" : "（观察标记）"}"
              style="width:${(asset.visualWeight / visualTotal) * 100}%; background:${asset.color}"
            ></span>
          `;
        }).join("")}
      </div>
      <div class="allocation-asset-list">
        ${ETF_ASSET_ORDER.map((asset) => {
          const weight = Number(weightMap[asset.code] || 0);
          const change = changeMap.get(asset.code);
          const changeText = typeof change === "number" ? signedPointText(change) : "0.0pct";
          const changeClass = change > 0 ? "is-up" : change < 0 ? "is-down" : "is-flat";
          return `
            <div class="allocation-asset-row">
              <i style="background:${asset.color}"></i>
              <span>${escapeHtml(asset.style)} · ${escapeHtml(asset.code)} ${escapeHtml(asset.name)}</span>
              <strong>${percentText(weight)}</strong>
              <em class="${changeClass}">${escapeHtml(changeText)}</em>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function topCandidatesHtml(candidates) {
  return `<div class="candidate-score-list">${(candidates || [])
    .slice(0, 4)
    .map(
      (item) => `
        <div>
          <span>${escapeHtml(item.code || "--")}</span>
          <strong>${scoreText(item.signal_score)}</strong>
        </div>
      `
    )
    .join("")}</div>`;
}

function rebalanceReasonHtml(reason) {
  if (!reason) return "--";
  const drivers = Array.isArray(reason.drivers) ? reason.drivers.slice(0, 3) : [];
  return `
    <div class="reason-cell">
      <strong>${escapeHtml(reason.label || "--")}</strong>
      <span>${escapeHtml(reason.detail || "")}</span>
      ${drivers.map((item) => `<em>${escapeHtml(item)}</em>`).join("")}
    </div>
  `;
}

function topWeightEntries(weights, limit = 3) {
  return Object.entries(weights || {})
    .map(([key, value]) => [key, Number(value) || 0])
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit);
}

function topStyleText(weights) {
  return topWeightEntries(weights, 3)
    .map(([style, weight]) => `${styleAllocationLabel(style)} ${percentText(weight)}`)
    .join(" / ");
}

function topEtfText(weights) {
  return topWeightEntries(weights, 3)
    .map(([code, weight]) => `${code} ${percentText(weight)}`)
    .join(" / ");
}

function macroRebalanceReason(current, previous) {
  if (!previous) {
    return {
      label: "初始建仓",
      detail: "首次按宏观、风格、ETF 三层规则建立目标组合。",
      drivers: [
        `宏观状态 ${regimeLabel(current.macro_regime)}`,
        `目标权益 ${percentText(current.target_exposure)}`,
        `主风格 ${topStyleText(current.style_allocation)}`,
      ],
    };
  }
  const exposureChange = Number(current.target_exposure || 0) - Number(previous.target_exposure || 0);
  const currentTopStyle = topWeightEntries(current.style_allocation, 1)[0]?.[0];
  const previousTopStyle = topWeightEntries(previous.style_allocation, 1)[0]?.[0];
  const drivers = [
    `目标权益 ${percentText(previous.target_exposure)} -> ${percentText(current.target_exposure)}`,
    `主风格 ${styleAllocationLabel(previousTopStyle)} -> ${styleAllocationLabel(currentTopStyle)}`,
    `ETF 权重 ${topEtfText(current.etf_allocation)}`,
  ];
  if (current.macro_regime !== previous.macro_regime) {
    return {
      label: "宏观状态切换",
      detail: `${regimeLabel(previous.macro_regime)} -> ${regimeLabel(current.macro_regime)}，重新计算权益上限和风格分配。`,
      drivers,
    };
  }
  if (Math.abs(exposureChange) >= 0.08) {
    return {
      label: "目标权益显著变化",
      detail: `目标权益变化 ${signedPointText(exposureChange)}，风险覆盖或宏观得分变化推动仓位调整。`,
      drivers,
    };
  }
  if (currentTopStyle !== previousTopStyle) {
    return {
      label: "主风格切换",
      detail: `${styleAllocationLabel(previousTopStyle)} -> ${styleAllocationLabel(currentTopStyle)}，权益内部风格权重重新分配。`,
      drivers,
    };
  }
  return {
    label: "周期再平衡",
    detail: "达到 20 个交易日再平衡间隔，按最新分层信号微调 ETF 权重。",
    drivers,
  };
}

function targetWeightChanges(currentWeights, previousWeights) {
  const keys = new Set([...Object.keys(currentWeights || {}), ...Object.keys(previousWeights || {})]);
  return [...keys].map((code) => ({
    code,
    change: Number((currentWeights || {})[code] || 0) - Number((previousWeights || {})[code] || 0),
  }));
}

function macroPositionHtml(item) {
  return `
    <div class="macro-position-cell">
      <strong>${escapeHtml(regimeLabel(item.macro_regime))}</strong>
      <span>目标权益 ${percentText(item.target_exposure)}</span>
      <em>上限 ${percentText(item.exposure_ceiling)} / 风险 ${percentText(item.risk_overlay)} / 换手 ${percentText(item.turnover_to_target)}</em>
    </div>
  `;
}

function styleWeightsHtml(weights) {
  const styleColors = {
    growth: "#ef4444",
    small_cap: "#f97316",
    value: "#eab308",
    dividend_low_vol: "#64748b",
  };
  const combined = {
    growth: Number((weights || {}).growth || 0),
    small_cap: Number((weights || {}).small_cap || 0),
    value: Number((weights || {}).value || 0),
    dividend_low_vol: Number((weights || {}).dividend || 0) + Number((weights || {}).low_vol || 0),
  };
  const labels = {
    growth: "成长/科技",
    small_cap: "中小盘",
    value: "价值/大盘",
    dividend_low_vol: "红利/低波",
  };
  const order = ["growth", "small_cap", "value", "dividend_low_vol"];
  return `
    <div class="style-allocation-cell">
      ${order
        .map((style) => {
          const weight = combined[style] || 0;
          return `
            <div class="style-allocation-row">
              <span>${escapeHtml(labels[style])}</span>
              <strong>${percentText(weight)}</strong>
              <i style="width:${Math.round(weight * 100)}%; background:${styleColors[style]}"></i>
            </div>
          `;
        })
        .join("")}
      <p>权益内部，不含现金/债券</p>
    </div>
  `;
}

async function renderRotationHistoryPage() {
  const payload = await getJson("/api/style/rotation-backtest");
  const summary = payload.summary || {};
  const signals = payload.signals || [];
  setSummaryTiles([
    { label: "回测区间", value: `${toIsoDate(summary.start_date)} - ${toIsoDate(summary.end_date)}` },
    { label: "轮动收益", value: signedRatioText(summary.rotation_total_return) },
    { label: "510500收益", value: signedRatioText(summary.benchmark_510500_return) },
    { label: "等权收益", value: signedRatioText(summary.equal_weight_basket_return) },
    { label: "最大回撤", value: percentText(summary.max_drawdown) },
    { label: "调仓次数", value: integerText(summary.rebalance_count) },
  ]);
  const rows = [...signals].reverse();
  document.getElementById("historyTableBody").innerHTML = rows
    .map(
      (item) => `
        <tr>
          <td>${toIsoDate(item.date)}</td>
          <td>${regimeLabel(item.regime)}</td>
          <td>${rotationSignalLabel(item.rebalance_signal)}</td>
          <td>${percentText(item.turnover_to_target)}</td>
          <td>${rebalanceReasonHtml(item.rebalance_reason)}</td>
          <td>${weightsHtml(item.target_weights, item.rebalance_reason)}</td>
          <td>${topCandidatesHtml(item.top_candidates)}</td>
        </tr>
      `
    )
    .join("");
  setText("historyCount", `${integerText(signals.length)} 次再平衡记录`);
}

async function renderMacroStyleHistoryPage() {
  const payload = await getJson("/api/style/macro-style-etf-backtest");
  const summary = payload.summary || {};
  const signals = payload.signals || [];
  setSummaryTiles([
    { label: "回测区间", value: `${toIsoDate(summary.start_date)} - ${toIsoDate(summary.end_date)}` },
    { label: "分层收益", value: signedRatioText(summary.hierarchical_total_return) },
    { label: "510500收益", value: signedRatioText(summary.benchmark_510500_return) },
    { label: "平均权益仓位", value: percentText(summary.average_target_exposure) },
    { label: "最大回撤", value: percentText(summary.max_drawdown) },
    { label: "调仓次数", value: integerText(summary.rebalance_count) },
  ]);
  const enriched = signals.map((item, index) => ({
    ...item,
    rebalance_reason: macroRebalanceReason(item, signals[index - 1]),
    target_weight_changes: targetWeightChanges(item.etf_allocation, signals[index - 1]?.etf_allocation || {}),
  }));
  const rows = [...enriched].reverse();
  document.getElementById("historyTableBody").innerHTML = rows
    .map(
      (item) => `
        <tr>
          <td>${toIsoDate(item.date)}</td>
          <td>${macroPositionHtml(item)}</td>
          <td>${rebalanceReasonHtml(item.rebalance_reason)}</td>
          <td>${styleWeightsHtml(item.style_allocation)}</td>
          <td>${weightsHtml(item.etf_allocation, { weight_changes: item.target_weight_changes })}</td>
        </tr>
      `
    )
    .join("");
  setText("historyCount", `${integerText(signals.length)} 次分层再平衡记录`);
}

function setProbabilityRow(id, value) {
  setText(id, percentText(value));
}

function forecastCaveatText(confidence) {
  const dominant = confidence?.dominant_outcome || "最高概率情形";
  const dominantProbability = percentText(confidence?.dominant_probability);
  const gap = percentText(confidence?.probability_gap);
  const level = confidence?.level_label || "--";
  return `${dominant}只是当前样本中的最高概率，概率 ${dominantProbability}，领先第二情形 ${gap}；展望置信度为${level}，不应解读为确定方向。`;
}

async function renderCycleTrackPage() {
  const track = await getJson("/api/regime/cycle/track");
  const cycle = track.cycle || {};
  const forecast = track.forecast || {};
  const probabilities = forecast.probabilities || {};
  const confidence = forecast.confidence || {};
  setSummaryTiles([
    { label: "本轮开始", value: `${toIsoDate(cycle.start_date)} · 上证 ${cycle.start_close ?? "--"}` },
    { label: "当前位置", value: `第 ${cycle.elapsed_sessions ?? "--"} 个交易日` },
    { label: "累计涨跌", value: typeof cycle.return_pct === "number" ? `${cycle.return_pct}%` : "--" },
    { label: "展望样本", value: forecast.sample_size ? `${forecast.sample_size} 组` : "--" },
    { label: "展望置信度", value: percentText(confidence.score) },
    { label: "预测窗口", value: forecast.basis_horizon_sessions ? `${forecast.basis_horizon_sessions} 交易日` : "--" },
  ]);
  setProbabilityRow("probContinue", probabilities.continue);
  setProbabilityRow("probRange", probabilities.range);
  setProbabilityRow("probWeaken", probabilities.weaken);
  setText("forecastCaveat", forecastCaveatText(confidence));
  setText("forecastConfidenceReason", confidence.reason || "--");
  const explanation = forecast.explanation || {};
  setText("explanationSummary", explanation.summary || "--");
  document.getElementById("explanationFacts").innerHTML = (explanation.facts || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  document.getElementById("explanationMethod").innerHTML = (explanation.method || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  setText("explanationResult", explanation.result || "--");
  renderCycleTrackChart("cycleTrackChart", track);
}

function cycleBlockMeta(block) {
  const start = toIsoDate(block.start_date);
  const end = block.ongoing ? "至今" : toIsoDate(block.end_date);
  const duration = typeof block.elapsed_years === "number" ? `约 ${block.elapsed_years} 年` : "--";
  const returnText = typeof block.return_pct === "number" ? `${block.return_pct > 0 ? "+" : ""}${block.return_pct}%` : "--";
  return `${start} - ${end} · ${duration} · ${returnText}`;
}

function cycleBlockHtml(block) {
  const features = (block.features || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const themes = (block.themes || [])
    .map((theme) => `<span class="theme-chip">${escapeHtml(theme)}</span>`)
    .join("");
  return `
    <article class="cycle-block cycle-block-${block.state === "bull" ? "bull" : "bear"}">
      <div class="cycle-block-main">
        <span>${escapeHtml(regimeLabel(block.state))}</span>
        <strong>${escapeHtml(block.label)}</strong>
        <em>${escapeHtml(cycleBlockMeta(block))}</em>
      </div>
      <div class="cycle-block-detail">
        <h3>${escapeHtml(block.theme_title)}</h3>
        <div class="theme-chips">${themes}</div>
        <ul>${features}</ul>
      </div>
    </article>
  `;
}

async function renderCycleObservationPage() {
  const cycle = await getJson("/api/regime/cycle");
  const current = cycle.current_cycle || {};
  setSummaryTiles([
    { label: "观察区间", value: `${toIsoDate(cycle.start_date)} - ${toIsoDate(cycle.as_of)}` },
    { label: "当前周期", value: regimeLabel(current.state) },
    { label: "本轮开始", value: toIsoDate(current.start_date) },
    { label: "本轮涨跌", value: typeof current.return_pct === "number" ? `${current.return_pct}%` : "--" },
    { label: "周期年龄", value: current.elapsed_years ? `约 ${current.elapsed_years} 年` : "--" },
    { label: "主要切块", value: integerText((cycle.cycle_blocks || []).filter((item) => item.major).length) },
  ]);
  renderIndexChart("indexChart", cycle.series || [], { currentDate: cycle.as_of }, cycle.cycle_blocks || []);
  const majorBlocks = (cycle.cycle_blocks || []).filter((item) => item.major).reverse();
  document.getElementById("cycleBlocks").innerHTML = majorBlocks.map(cycleBlockHtml).join("");
}

async function renderApiDocsPage() {
  const catalog = await getJson("/api");
  const groups = catalog.groups || [];
  setSummaryTiles([
    { label: "接口版本", value: catalog.version || "--" },
    { label: "接口数量", value: integerText(catalog.total_endpoints) },
    { label: "系统状态", value: catalog.status || "--" },
    { label: "只读边界", value: catalog.safety?.read_only ? "只读" : "需检查" },
    { label: "真实订单", value: catalog.safety?.no_real_orders ? "无" : "需检查" },
    { label: "交互文档", value: catalog.docs?.interactive || "/docs" },
  ]);
  document.getElementById("apiTableBody").innerHTML = groups
    .flatMap((group) =>
      (group.endpoints || []).map(
        (endpoint) => `
          <tr>
            <td>${escapeHtml(group.name)}</td>
            <td>${escapeHtml(endpoint.method)}</td>
            <td>${escapeHtml(endpoint.path)}</td>
            <td>${escapeHtml(endpoint.description)}</td>
            <td>${escapeHtml(endpoint.returns)}</td>
            <td>${escapeHtml(endpoint.safety)}</td>
          </tr>
        `
      )
    )
    .join("");
}

async function bootDetailPage() {
  const page = document.body.dataset.page;
  if (page === "rotation-history") await renderRotationHistoryPage();
  if (page === "macro-style-history") await renderMacroStyleHistoryPage();
  if (page === "cycle-track") await renderCycleTrackPage();
  if (page === "cycle-observation") await renderCycleObservationPage();
  if (page === "api-docs") await renderApiDocsPage();
}

bootDetailPage().catch((error) => {
  console.error(error);
  setText("pageError", error.message || "页面加载失败");
});
