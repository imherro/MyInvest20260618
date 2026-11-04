const strategyMetricTableSortState = {};
const strategyBenchmarkToggleState = {};
const strategyVirtualToggleState = {};
const strategyRangeState = {};

async function strategyGetJson(url) {
  const requestUrl = new URL(url, window.location.origin);
  requestUrl.searchParams.set("_t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function strategySetText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function strategyPercentText(value) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function strategySignedRatioText(value) {
  if (typeof value !== "number") return "--";
  const percent = value * 100;
  const sign = percent > 0 ? "+" : "";
  return `${sign}${percent.toFixed(2)}%`;
}

function strategyFixedText(value, digits = 2) {
  if (typeof value !== "number") return "--";
  return value.toFixed(digits);
}

function strategyIntegerText(value) {
  if (typeof value !== "number") return "--";
  return value.toLocaleString("zh-CN");
}

function strategyScoreText(value) {
  if (typeof value !== "number") return "--";
  return value.toFixed(3);
}

function strategyAnnualizedFromTotal(totalReturn, sessions) {
  if (typeof totalReturn !== "number" || typeof sessions !== "number" || sessions <= 0) return null;
  return (1 + totalReturn) ** (252 / sessions) - 1;
}

function strategySharpeFormulaText(performance) {
  if (typeof performance.sharpe !== "number") return "夏普 = (Rp - Rf) / σp；当前无足够样本。";
  const riskFreeRate = 0;
  const volatility = performance.annualized_volatility;
  const portfolioReturn =
    typeof volatility === "number" ? performance.sharpe * volatility + riskFreeRate : performance.annualized_return;
  return `夏普 = (Rp - Rf) / σp = (${strategySignedRatioText(portfolioReturn)} - ${strategyPercentText(riskFreeRate)}) / ${strategyPercentText(volatility)} = ${strategyFixedText(performance.sharpe, 2)}；Rp 为日收益均值年化，不是表格里的复利年化收益；σp 为日收益波动年化。`;
}

function strategyDrawdownReductionText(value) {
  if (typeof value !== "number") return "--";
  const percent = Math.abs(value * 100).toFixed(1);
  if (value > 0) return `策略少 ${percent}pct`;
  if (value < 0) return `策略多 ${percent}pct`;
  return "持平";
}

function strategyToIsoDate(value) {
  if (!value || String(value).length !== 8) return value || "--";
  const text = String(value);
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
}

function strategyEscapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function strategyStyleLabel(value) {
  const labels = {
    growth: "成长/科技",
    value: "价值/大盘",
    small_cap: "中小盘",
    dividend: "红利/低波",
    low_vol: "红利/低波",
    cash_proxy: "现金/债券代理",
  };
  return labels[value] || value || "--";
}

function strategyRegimeLabel(value) {
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

function strategyRotationSignalLabel(value) {
  if (!value) return "--";
  if (value === "hold_universe") return "保持观察池";
  if (value === "insufficient_data") return "样本不足";
  if (value.startsWith("rotate_to_")) return `转向${strategyStyleLabel(value.replace("rotate_to_", ""))}`;
  return value;
}

function strategyConfidenceLevelLabel(value) {
  const labels = {
    high: "高",
    medium: "中",
    medium_low: "中低",
    low: "低",
    insufficient: "样本不足",
  };
  return labels[value] || value || "--";
}

const STRATEGY_ETF_ORDER = [
  { code: "159915.SZ", style: "成长/科技", name: "创业板ETF" },
  { code: "510500.SH", style: "中小盘", name: "中证500ETF" },
  { code: "510300.SH", style: "价值/大盘", name: "沪深300ETF" },
  { code: "510880.SH", style: "红利/低波", name: "红利ETF" },
  { code: "511880.SH", style: "现金/债券代理", name: "银华日利ETF" },
];

function strategySetSummaryTiles(items) {
  const target = document.getElementById("summaryTiles");
  if (!target) return;
  target.innerHTML = items
    .map(
      (item) => `
        <div class="summary-tile">
          <span>${strategyEscapeHtml(item.label)}</span>
          <strong>${strategyEscapeHtml(item.value)}</strong>
        </div>
      `
    )
    .join("");
}

function strategyWeightsRowsHtml(weights) {
  const weightMap = weights || {};
  return STRATEGY_ETF_ORDER.map((asset) => {
    const weight = Number(weightMap[asset.code] || 0);
    return `
      <div class="rotation-weight-row">
        <span>${strategyEscapeHtml(asset.style)} · ${strategyEscapeHtml(asset.code)} ${strategyEscapeHtml(asset.name)}</span>
        <strong>${strategyPercentText(weight)}</strong>
        <i style="width:${Math.round(weight * 100)}%"></i>
      </div>
    `;
  }).join("");
}

function strategyTopCandidatesHtml(candidates) {
  return (candidates || [])
    .slice(0, 5)
    .map(
      (candidate) => `
        <div class="rotation-candidate-row">
          <span>${strategyEscapeHtml(candidate.name || "--")}</span>
          <strong>${strategyScoreText(candidate.signal_score)}</strong>
          <em>${strategyEscapeHtml(candidate.code || "--")} · ${strategyStyleLabel(candidate.primary_style)} · 相对强弱 ${strategyScoreText(candidate.relative_strength_score)}</em>
        </div>
      `
    )
    .join("");
}

function strategyBacktestComparisonTable(targetId, rows, options = {}) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const sessions = options.sessions;
  const strategyAnnualized =
    typeof options.strategyAnnualizedReturn === "number"
      ? options.strategyAnnualizedReturn
      : strategyAnnualizedFromTotal(rows.find((item) => item.isStrategy)?.total_return, sessions);
  target.innerHTML = `
    <div class="backtest-comparison-row backtest-comparison-head">
      <span>标的</span>
      <span>收益</span>
      <span>年化</span>
      <span>最大回撤</span>
      <span>收益差</span>
      <span>年化差</span>
      <span>回撤差</span>
    </div>
    ${rows
      .map((item) => {
        const annualizedReturn =
          typeof item.annualized_return === "number"
            ? item.annualized_return
            : strategyAnnualizedFromTotal(item.total_return, item.sessions || sessions);
        const annualizedAdvantage =
          typeof item.annualized_return_advantage === "number"
            ? item.annualized_return_advantage
            : typeof strategyAnnualized === "number" && typeof annualizedReturn === "number"
              ? strategyAnnualized - annualizedReturn
              : null;
        return `
          <div class="backtest-comparison-row${item.isStrategy ? " is-strategy" : ""}">
            <strong>${strategyEscapeHtml(item.label || item.code || "--")}</strong>
            <span>${strategySignedRatioText(item.total_return)}</span>
            <span>${strategySignedRatioText(annualizedReturn)}</span>
            <span>${strategyPercentText(item.max_drawdown)}</span>
            <span>${item.isStrategy ? "--" : strategySignedRatioText(item.return_advantage)}</span>
            <span>${item.isStrategy ? "--" : strategySignedRatioText(annualizedAdvantage)}</span>
            <span>${item.isStrategy ? "--" : strategyDrawdownReductionText(item.drawdown_reduction)}</span>
          </div>
        `;
      })
      .join("")}
  `;
}

function strategyBacktestMetricTable(targetId, rows) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const state = strategyMetricTableSortState[targetId] || {};
  const labels = {
    label: "标的",
    total_return: "总收益",
    annualized_return: "年化收益",
    max_drawdown: "最大回撤",
    sharpe: "夏普",
    calmar: "Calmar",
    start_date: "区间",
  };
  const headerButton = (key) => {
    const active = state.key === key;
    const arrow = active ? (state.direction === 1 ? "↑" : "↓") : "";
    return `<button class="comparison-sort-button${active ? " is-active" : ""}" type="button" data-metric-sort="${key}" title="点击按${strategyEscapeHtml(labels[key])}排序">${strategyEscapeHtml(labels[key])}<span>${arrow}</span></button>`;
  };
  const sortedRows = [...(rows || [])].sort((left, right) => {
    if (!state.key) return 0;
    const leftValue = strategyMetricSortValue(left, state.key);
    const rightValue = strategyMetricSortValue(right, state.key);
    const leftMissing = leftValue === null || leftValue === undefined || Number.isNaN(leftValue);
    const rightMissing = rightValue === null || rightValue === undefined || Number.isNaN(rightValue);
    if (leftMissing && rightMissing) return String(strategyMetricSortValue(left, "label")).localeCompare(String(strategyMetricSortValue(right, "label")), "zh-CN");
    if (leftMissing) return 1;
    if (rightMissing) return -1;
    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * state.direction;
    }
    return String(leftValue).localeCompare(String(rightValue), "zh-CN") * state.direction;
  });
  target.innerHTML = `
    <div class="backtest-comparison-row backtest-comparison-head metric-table-row">
      <span>${headerButton("label")}</span>
      <span>${headerButton("total_return")}</span>
      <span>${headerButton("annualized_return")}</span>
      <span>${headerButton("max_drawdown")}</span>
      <span>${headerButton("sharpe")}</span>
      <span>${headerButton("calmar")}</span>
      <span>${headerButton("start_date")}</span>
    </div>
    ${sortedRows
      .map(
        (item) => `
          <div class="backtest-comparison-row metric-table-row${item.isStrategy ? " is-strategy" : ""}">
            <strong>${strategyEscapeHtml(item.label || item.code || "--")}</strong>
            <span>${strategySignedRatioText(item.total_return)}</span>
            <span>${strategySignedRatioText(item.annualized_return)}</span>
            <span>${strategyPercentText(item.max_drawdown)}</span>
            <span>${strategyFixedText(item.sharpe, 2)}</span>
            <span>${strategyFixedText(item.calmar, 2)}</span>
            <span>${strategyToIsoDate(item.start_date)} - ${strategyToIsoDate(item.end_date)}</span>
          </div>
        `
      )
      .join("")}
  `;
  target.onclick = (event) => {
    const button = event.target.closest("[data-metric-sort]");
    if (!button) return;
    const key = button.dataset.metricSort;
    const current = strategyMetricTableSortState[targetId] || {};
    const defaultDirection = key === "label" || key === "start_date" ? 1 : -1;
    strategyMetricTableSortState[targetId] = {
      key,
      direction: current.key === key ? current.direction * -1 : defaultDirection,
    };
    strategyBacktestMetricTable(targetId, rows);
  };
}

function strategyMetricSortValue(item, key) {
  if (key === "label") return item.label || item.code || "";
  if (key === "start_date") return item.start_date || "";
  return item[key];
}

function strategySetEtfComparison(summary) {
  const comparisonEtfs = (summary.comparison_etfs || []).map((item) => ({
    ...item,
    return_advantage: item.rotation_return_advantage,
    drawdown_reduction: item.rotation_drawdown_reduction,
  }));
  strategyBacktestComparisonTable(
    "backtestEtfComparison",
    [
      {
        label: "轮动策略",
        total_return: summary.rotation_total_return,
        max_drawdown: summary.max_drawdown,
        isStrategy: true,
      },
      ...comparisonEtfs,
    ],
    { sessions: summary.sessions }
  );
}

function strategySetMacroComparison(summary) {
  const strategyReturn = summary.hierarchical_total_return;
  const strategyDrawdown = summary.max_drawdown;
  const comparisonRows = [
    {
      label: "当前 A1 轮动",
      total_return: summary.current_a1_return,
      max_drawdown: summary.current_a1_max_drawdown,
    },
    {
      label: "价值/大盘 510300 沪深300ETF",
      total_return: summary.benchmark_510300_return,
      max_drawdown: summary.benchmark_510300_max_drawdown,
    },
    {
      label: "中小盘 510500 中证500ETF",
      total_return: summary.benchmark_510500_return,
      max_drawdown: summary.benchmark_510500_max_drawdown,
    },
    {
      label: "等权 ETF Basket",
      total_return: summary.equal_weight_basket_return,
      max_drawdown: summary.equal_weight_basket_max_drawdown,
    },
  ].map((item) => ({
    ...item,
    return_advantage:
      typeof strategyReturn === "number" && typeof item.total_return === "number"
        ? strategyReturn - item.total_return
        : null,
    drawdown_reduction:
      typeof strategyDrawdown === "number" && typeof item.max_drawdown === "number"
        ? Math.abs(item.max_drawdown) - Math.abs(strategyDrawdown)
        : null,
  }));
  strategyBacktestComparisonTable(
    "macroStyleComparison",
    [
      {
        label: "M2.1 分层组合",
        total_return: strategyReturn,
        max_drawdown: strategyDrawdown,
        isStrategy: true,
      },
      ...comparisonRows,
    ],
    { sessions: summary.sessions }
  );
}

function strategySetRotationSignal(signal) {
  const confidence = signal.confidence || {};
  const topCandidate = (signal.top_candidates || [])[0] || {};
  strategySetText("rotationSignal", strategyRotationSignalLabel(signal.rebalance_signal));
  strategySetText(
    "rotationConfidence",
    `${strategyPercentText(confidence.score)} · ${strategyConfidenceLevelLabel(confidence.level)}`
  );
  strategySetText(
    "rotationTopEtf",
    topCandidate.code ? `${topCandidate.name} · ${topCandidate.code}` : "--"
  );
  const weightsTarget = document.getElementById("rotationTargetWeights");
  if (weightsTarget) weightsTarget.innerHTML = strategyWeightsRowsHtml(signal.etf_target_weights || {});
  const candidatesTarget = document.getElementById("rotationCandidateList");
  if (candidatesTarget) candidatesTarget.innerHTML = strategyTopCandidatesHtml(signal.top_candidates || []);
  strategySetText(
    "rotationConclusion",
    signal.engine
      ? `A1.2 输出 ${strategyRotationSignalLabel(signal.rebalance_signal)}，${confidence.reason || "置信度待评估"} 该层只给 ETF 级模拟权重建议，不选股、不下单、不生成订单。`
      : "A1.2 ETF 轮动信号结果尚未生成。"
  );
}

function strategySetEtfBacktest(backtest) {
  const summary = backtest.summary || {};
  const validation = backtest.validation || {};
  strategySetText("backtestAlpha510500", strategySignedRatioText(summary.alpha_vs_510500));
  strategySetText("backtestAlphaEqual", strategySignedRatioText(summary.alpha_vs_equal_weight));
  strategySetText("backtestRotationReturn", strategySignedRatioText(summary.rotation_total_return));
  strategySetText("backtestBenchmark510500Return", strategySignedRatioText(summary.benchmark_510500_return));
  strategySetText("backtestEqualReturn", strategySignedRatioText(summary.equal_weight_basket_return));
  strategySetText("backtestSharpe", strategyFixedText(summary.sharpe, 2));
  strategySetText("backtestSessions", strategyIntegerText(summary.sessions));
  strategySetText("backtestRebalanceCount", strategyIntegerText(summary.rebalance_count));
  strategySetEtfComparison(summary);
  strategySetText(
    "backtestDrawdown",
    `轮动 ${strategyPercentText(summary.max_drawdown)} / 等权 ${strategyPercentText(summary.equal_weight_basket_max_drawdown)}`
  );
  strategySetText("backtestHitRate", strategyPercentText(summary.hit_rate_vs_510500));
  const alphaVerdict = validation.alpha_positive_vs_equal_weight
    ? "跑赢 510500、510300 和等权 ETF basket，存在初步 alpha 证据"
    : validation.alpha_positive_vs_510500
      ? "仅小幅跑赢 510500，但未跑赢等权 ETF basket，alpha 证据不足"
      : "未跑赢 510500，当前轮动信号未证明 alpha";
  strategySetText(
    "backtestConclusion",
    backtest.metadata
      ? `A1.3 覆盖 ${strategyIntegerText(summary.sessions)} 个交易日，${alphaVerdict}；收益口径优先采用 Tushare pct_chg/pre_close，避免 ETF 价格断点被误算为收益。`
      : "A1.3 ETF 轮动回测结果尚未生成。"
  );
}

function strategyTopWeightText(weights, labelFn, limit = 3) {
  return Object.entries(weights || {})
    .map(([key, value]) => [key, Number(value) || 0])
    .filter((entry) => entry[1] > 0)
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit)
    .map(([key, value]) => `${labelFn(key)} ${strategyPercentText(value)}`)
    .join(" / ") || "--";
}

function strategyCombinedStyleWeights(weights) {
  return {
    growth: Number((weights || {}).growth || 0),
    small_cap: Number((weights || {}).small_cap || 0),
    value: Number((weights || {}).value || 0),
    dividend_low_vol: Number((weights || {}).dividend || 0) + Number((weights || {}).low_vol || 0),
  };
}

function strategyCombinedStyleLabel(value) {
  const labels = {
    growth: "成长/科技",
    small_cap: "中小盘",
    value: "价值/大盘",
    dividend_low_vol: "红利/低波",
  };
  return labels[value] || strategyStyleLabel(value);
}

function strategySetMacroLatestSignal(signals) {
  const latest = (signals || [])[signals.length - 1] || {};
  const styleWeights = strategyCombinedStyleWeights(latest.style_allocation || {});
  strategySetText(
    "macroLatestRegime",
    latest.date ? `${strategyToIsoDate(latest.date)} · ${strategyRegimeLabel(latest.macro_regime)}` : "--"
  );
  strategySetText("macroLatestExposure", strategyPercentText(latest.target_exposure));
  strategySetText("macroLatestStyle", strategyTopWeightText(styleWeights, strategyCombinedStyleLabel, 3));
  strategySetText("macroLatestEtf", strategyTopWeightText(latest.etf_allocation || {}, (code) => code, 3));
  strategySetText("macroLatestTurnover", strategyPercentText(latest.turnover_to_target));
  strategySetText(
    "macroLatestReason",
    latest.date
      ? `最近一次信号按 ${strategyRegimeLabel(latest.macro_regime)} 宏观状态计算权益上限，再把权益部分分配到风格 ETF；现金/债券代理在 511880 中体现。`
      : "暂无分层信号。"
  );
}

function strategySetMacroBacktest(backtest) {
  const summary = backtest.summary || {};
  const validation = backtest.validation || {};
  strategySetText("macroStyleAlpha510500", strategySignedRatioText(summary.alpha_vs_510500));
  strategySetText("macroStyleAlphaEqual", strategySignedRatioText(summary.alpha_vs_equal_weight));
  strategySetText("macroStyleReturn", strategySignedRatioText(summary.hierarchical_total_return));
  strategySetText("macroStyle510500Return", strategySignedRatioText(summary.benchmark_510500_return));
  strategySetText("macroStyleEqualReturn", strategySignedRatioText(summary.equal_weight_basket_return));
  strategySetText("macroStyleSharpe", strategyFixedText(summary.sharpe, 2));
  strategySetText("macroStyleSessions", strategyIntegerText(summary.sessions));
  strategySetText("macroStyleRebalance", strategyIntegerText(summary.rebalance_count));
  strategySetMacroComparison(summary);
  strategySetText(
    "macroStyleDrawdown",
    `分层 ${strategyPercentText(summary.max_drawdown)} / A1 ${strategyPercentText(summary.current_a1_max_drawdown)}`
  );
  strategySetText("macroStyleHitRate", strategyPercentText(summary.hit_rate_vs_510500));
  const verdict = validation.alpha_positive_vs_equal_weight
    ? "分层组合跑赢等权 ETF basket，具备继续验证价值"
    : validation.alpha_positive_vs_current_a1
      ? "分层组合优于当前 A1，但仍未跑赢 510500 和等权 ETF basket"
      : "分层组合未优于当前 A1，暂未证明新增 alpha";
  strategySetText(
    "macroStyleConclusion",
    backtest.metadata
      ? `M2.1 覆盖 ${strategyIntegerText(summary.sessions)} 个交易日，平均权益仓位 ${strategyPercentText(summary.average_target_exposure)}；${verdict}。宏观层只管仓位，风格层只管权重，ETF 层只做映射。`
      : "M2.1 Macro-Style-ETF 分层回测结果尚未生成。"
  );
}

function strategyGenericWeightRows(weights, universe) {
  const assets = universe || [];
  const byCode = new Map(assets.map((asset) => [asset.code, asset]));
  const rows = Object.entries(weights || {})
    .map(([code, weight]) => ({
      code,
      weight: Number(weight) || 0,
      asset: byCode.get(code) || { code, name: code, group: "资产" },
    }))
    .sort((left, right) => right.weight - left.weight);
  if (!rows.length) return '<div class="generic-empty">暂无目标仓位</div>';
  return rows
    .map(
      (row) => `
        <div class="rotation-weight-row">
          <span>${strategyEscapeHtml(row.asset.group)} · ${strategyEscapeHtml(row.code)} ${strategyEscapeHtml(row.asset.name)}</span>
          <strong>${strategyPercentText(row.weight)}</strong>
          <i style="width:${Math.round(row.weight * 100)}%"></i>
        </div>
      `
    )
    .join("");
}

function strategyGenericWeightPills(weights, universe) {
  const byCode = new Map((universe || []).map((asset) => [asset.code, asset]));
  return `<div class="weight-pill-list">${Object.entries(weights || {})
    .sort((left, right) => Number(right[1] || 0) - Number(left[1] || 0))
    .map(([code, weight]) => {
      const asset = byCode.get(code) || { name: code, group: "资产" };
      return `<span>${strategyEscapeHtml(asset.group)} ${strategyEscapeHtml(code)} ${strategyPercentText(Number(weight) || 0)}</span>`;
    })
    .join("")}</div>`;
}

function strategyGenericWeightStack(weights, universe) {
  const byCode = new Map((universe || []).map((asset) => [asset.code, asset]));
  const colorByCode = {
    "480092.CNI": "#111827",
    "399606.SZ": "#7c3aed",
    "510300.SH": "#dc2626",
    "510880.SH": "#16a34a",
    "510500.SH": "#f59e0b",
    "159915.SZ": "#7c3aed",
    "511880.SH": "#64748b",
    CASH: "#94a3b8",
  };
  const universeOrder = new Map((universe || []).map((asset, index) => [asset.code, index]));
  const rows = Object.entries(weights || {})
    .map(([code, weight]) => ({
      code,
      weight: Number(weight) || 0,
      asset: byCode.get(code) || { code, name: code, group: code },
    }))
    .sort((left, right) => (universeOrder.get(left.code) ?? 999) - (universeOrder.get(right.code) ?? 999));
  if (!rows.length) return '<div class="generic-empty">暂无目标仓位</div>';
  const segments = rows
    .map((row) => {
      const width = Math.max(2, Math.round(row.weight * 100));
      return `<i style="width:${width}%;background:${colorByCode[row.code] || "#64748b"}" title="${strategyEscapeHtml(row.asset.group || row.code)} ${strategyPercentText(row.weight)}"></i>`;
    })
    .join("");
  const labels = rows
    .map(
      (row) => `
        <span>
          <b style="background:${colorByCode[row.code] || "#64748b"}"></b>
          ${strategyEscapeHtml(row.asset.group || row.code)} ${strategyPercentText(row.weight)}
        </span>
      `
    )
    .join("");
  return `<div class="generic-weight-stack"><div>${segments}</div><em>${labels}</em></div>`;
}

function strategyGenericCandidateText(candidates) {
  return (candidates || [])
    .slice(0, 4)
    .map((item) => `${item.code} ${strategyScoreText(item.score)}`)
    .join(" / ") || "--";
}

function strategySetGenericComparison(summary, performance) {
  if (summary.metric_comparison_assets) {
    strategyBacktestMetricTable("genericComparison", summary.metric_comparison_assets);
    return;
  }
  const annualizedReturn =
    typeof summary.annualized_return === "number" ? summary.annualized_return : performance?.annualized_return;
  strategyBacktestComparisonTable(
    "genericComparison",
    [
      {
        label: summary.short_name || "策略组合",
        total_return: summary.strategy_total_return,
        annualized_return: annualizedReturn,
        max_drawdown: summary.max_drawdown,
        isStrategy: true,
      },
      ...(summary.variant_assets || []),
      ...(summary.comparison_assets || []),
    ],
    { sessions: summary.sessions, strategyAnnualizedReturn: annualizedReturn }
  );
}

function strategySetGenericParameterScan(summary) {
  const panel = document.getElementById("genericParameterPanel");
  const table = document.getElementById("genericParameterTable");
  if (!panel || !table) return;
  const rows = summary.parameter_scan || [];
  if (!rows.length) {
    panel.hidden = true;
    table.innerHTML = "";
    return;
  }
  const defaultVariant = summary.default_parameter || {};
  const bestVariant = summary.best_parameter || {};
  const bestAnnualizedVariant = summary.best_annualized_parameter || {};
  const topRows = rows.slice(0, 12);
  panel.hidden = false;
  strategySetText("genericParameterCount", `前 ${topRows.length} / ${rows.length} 组参数`);
  const noteTarget = document.getElementById("genericParameterNote");
  if (noteTarget) {
    const sample = summary.sample_validation || {};
    const sampleText = sample.train_best_calmar_test
      ? ` 样本外：训练段 Calmar 最优 ${strategyEscapeHtml(sample.train_best_calmar?.label || "--")} 在测试段年化 ${strategySignedRatioText(sample.train_best_calmar_test.annualized_return)}，最大回撤 ${strategyPercentText(sample.train_best_calmar_test.max_drawdown)}。`
      : "";
    noteTarget.innerHTML = `默认参数：${strategyEscapeHtml(defaultVariant.label || "--")}；全样本 Calmar 最优：${strategyEscapeHtml(bestVariant.label || "--")}；年化收益最高：${strategyEscapeHtml(bestAnnualizedVariant.label || "--")}。<strong class="lookahead-inline">未来函数</strong>${strategyEscapeHtml(summary.parameter_scan_lookahead_note || "全样本筛参只用于研究参数敏感性。")}${sampleText}`;
  }
  table.innerHTML = `
    <div class="backtest-comparison-row backtest-comparison-head parameter-table-row">
      <span>参数</span>
      <span>年化</span>
      <span>总收益</span>
      <span>最大回撤</span>
      <span>Calmar</span>
      <span>夏普</span>
      <span>调仓</span>
      <span>平均仓位</span>
    </div>
    ${topRows
      .map((item) => {
        const isDefault = item.variant === defaultVariant.variant;
        const isBest = item.variant === bestVariant.variant;
        const isBestAnnualized = item.variant === bestAnnualizedVariant.variant;
        const badges = [
          isBest ? '<em class="parameter-badge is-best">Calmar最优</em>' : "",
          isBestAnnualized ? '<em class="parameter-badge is-return">年化最高</em>' : "",
          isDefault ? '<em class="parameter-badge">默认</em>' : "",
        ].join("");
        return `
          <div class="backtest-comparison-row parameter-table-row${isDefault ? " is-strategy" : ""}">
            <strong>${strategyEscapeHtml(item.label || item.variant || "--")}${badges}</strong>
            <span>${strategySignedRatioText(item.annualized_return)}</span>
            <span>${strategySignedRatioText(item.total_return)}</span>
            <span>${strategyPercentText(item.max_drawdown)}</span>
            <span>${strategyFixedText(item.calmar, 2)}</span>
            <span>${strategyFixedText(item.sharpe, 2)}</span>
            <span>${strategyIntegerText(item.rebalance_count)}</span>
            <span>${strategyPercentText(item.average_target_exposure)}</span>
          </div>
        `;
      })
      .join("")}
  `;
}

function strategyBenchmarkEquityKey(code) {
  return code === "equal_weight" ? "equal_weight_equity" : `benchmark_${String(code || "").split(".")[0]}_equity`;
}

function strategyIsoToRawDate(value) {
  return String(value || "").replace(/-/g, "");
}

function strategyNormalizeIsoDate(value) {
  const text = strategyToIsoDate(value);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : "";
}

function strategyFullDateRange(backtest) {
  const dates = (backtest.equity_curve || []).map((item) => strategyNormalizeIsoDate(item.date)).filter(Boolean);
  return dates.length ? { start: dates[0], end: dates[dates.length - 1] } : null;
}

function strategyHasSelectableBenchmarks(backtest) {
  return [
    "free_cash_flow_buy_hold",
    "free_cash_flow_chinext_dynamic",
    "free_cash_flow_chinext_reversion",
    "free_cash_flow_chinext_balanced_reversion",
  ].includes(backtest.metadata?.indicator);
}

function strategyShiftIsoYear(isoDate, years) {
  const [year, month, day] = String(isoDate).split("-").map((part) => Number(part));
  const shifted = new Date(Date.UTC(year - years, month - 1, day));
  return shifted.toISOString().slice(0, 10);
}

function strategySelectedDateRange(backtest) {
  const full = strategyFullDateRange(backtest);
  if (!full) return null;
  const strategyId = backtest.summary?.strategy_id || "generic";
  const state = strategyRangeState[strategyId] || {};
  let start = state.start || full.start;
  let end = state.end || full.end;
  if (start < full.start) start = full.start;
  if (end > full.end) end = full.end;
  if (start > end) [start, end] = [end, start];
  strategyRangeState[strategyId] = { start, end };
  return { start, end, fullStart: full.start, fullEnd: full.end };
}

function strategySetGenericRangeControls(sourceBacktest) {
  const target = document.getElementById("genericRangeControls");
  if (!target) return null;
  if (sourceBacktest.metadata?.indicator !== "free_cash_flow_buy_hold") {
    target.hidden = true;
    target.innerHTML = "";
    return null;
  }
  const range = strategySelectedDateRange(sourceBacktest);
  if (!range) {
    target.hidden = true;
    return null;
  }
  const quickButtons = Array.from({ length: 11 }, (_, index) => index + 1)
    .map((year) => {
      const quickStart = strategyShiftIsoYear(range.fullEnd, year);
      const active = range.end === range.fullEnd && range.start === (quickStart < range.fullStart ? range.fullStart : quickStart);
      return `<button class="range-chip${active ? " is-active" : ""}" type="button" data-range-years="${year}">${year}年</button>`;
    })
    .join("");
  const fullActive = range.start === range.fullStart && range.end === range.fullEnd;
  target.hidden = false;
  target.innerHTML = `
    <div class="range-inputs">
      <label>开始 <input type="date" id="genericRangeStartInput" value="${range.start}" min="${range.fullStart}" max="${range.fullEnd}" /></label>
      <label>结束 <input type="date" id="genericRangeEndInput" value="${range.end}" min="${range.fullStart}" max="${range.fullEnd}" /></label>
    </div>
    <div class="quick-range-buttons">
      <button class="range-chip${fullActive ? " is-active" : ""}" type="button" data-range-full="1">全区间</button>
      ${quickButtons}
    </div>
  `;
  target.onclick = (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const strategyId = sourceBacktest.summary?.strategy_id || "generic";
    if (button.dataset.rangeFull) {
      strategyRangeState[strategyId] = { start: range.fullStart, end: range.fullEnd };
    } else if (button.dataset.rangeYears) {
      const years = Number(button.dataset.rangeYears);
      const quickStart = strategyShiftIsoYear(range.fullEnd, years);
      strategyRangeState[strategyId] = {
        start: quickStart < range.fullStart ? range.fullStart : quickStart,
        end: range.fullEnd,
      };
    }
    strategySetGenericPage(sourceBacktest);
  };
  target.onchange = () => {
    const strategyId = sourceBacktest.summary?.strategy_id || "generic";
    const start = document.getElementById("genericRangeStartInput")?.value || range.fullStart;
    const end = document.getElementById("genericRangeEndInput")?.value || range.fullEnd;
    strategyRangeState[strategyId] = { start, end };
    strategySetGenericPage(sourceBacktest);
  };
  return range;
}

function strategyRebaseCurveRows(rows, keys) {
  const bases = {};
  keys.forEach((key) => {
    const first = rows.find((item) => typeof item[key] === "number");
    bases[key] = first ? first[key] : null;
  });
  return rows.map((item) => {
    const next = { ...item };
    keys.forEach((key) => {
      next[key] = typeof item[key] === "number" && bases[key] ? item[key] / bases[key] : null;
    });
    return next;
  });
}

function strategyEquityMetricsFromCurve(template, curveRows, equityKey) {
  const points = curveRows
    .map((item) => ({ date: item.date, value: item[equityKey] }))
    .filter((item) => typeof item.value === "number" && Number.isFinite(item.value));
  const base = {
    ...template,
    start_date: points[0]?.date ? strategyIsoToRawDate(points[0].date) : null,
    end_date: points[points.length - 1]?.date ? strategyIsoToRawDate(points[points.length - 1].date) : null,
    sessions: points.length,
  };
  if (points.length < 2) {
    return {
      ...base,
      total_return: null,
      annualized_return: null,
      max_drawdown: null,
      sharpe: null,
      calmar: null,
      annualized_volatility: null,
    };
  }
  const values = points.map((item) => item.value);
  const totalReturn = values[values.length - 1] - 1;
  const annualizedReturn = (1 + totalReturn) ** (252 / points.length) - 1;
  let peak = values[0];
  let maxDrawdown = 0;
  values.forEach((value) => {
    if (value > peak) peak = value;
    const drawdown = peak > 0 ? value / peak - 1 : 0;
    if (drawdown < maxDrawdown) maxDrawdown = drawdown;
  });
  const returns = values.map((value, index) => (index === 0 ? 0 : value / values[index - 1] - 1));
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance =
    returns.length > 1
      ? returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1)
      : 0;
  const annualizedVolatility = Math.sqrt(variance) * Math.sqrt(252);
  const sharpe = annualizedVolatility > 0 ? (mean * 252) / annualizedVolatility : null;
  return {
    ...base,
    total_return: totalReturn,
    annualized_return: annualizedReturn,
    max_drawdown: maxDrawdown,
    sharpe,
    calmar: Math.abs(maxDrawdown) > 0 ? annualizedReturn / Math.abs(maxDrawdown) : null,
    annualized_volatility: annualizedVolatility,
  };
}

function strategyBuildRangeBacktest(sourceBacktest, range) {
  if (!range || sourceBacktest.metadata?.indicator !== "free_cash_flow_buy_hold") return sourceBacktest;
  const comparisonAssets = sourceBacktest.summary?.comparison_assets || [];
  const curveKeys = [
    "strategy_equity",
    "shanghai_equity",
    ...comparisonAssets.map((asset) => strategyBenchmarkEquityKey(asset.code)),
  ];
  const rawRows = (sourceBacktest.equity_curve || [])
    .map((item) => ({ ...item, date: strategyNormalizeIsoDate(item.date) }))
    .filter((item) => item.date && item.date >= range.start && item.date <= range.end);
  if (!rawRows.length) return sourceBacktest;
  const equityCurve = strategyRebaseCurveRows(rawRows, curveKeys);
  const sourceMetricRows = sourceBacktest.summary?.metric_comparison_assets || [];
  const metricRows = sourceMetricRows.map((item) =>
    strategyEquityMetricsFromCurve(
      item,
      equityCurve,
      item.isStrategy ? "strategy_equity" : strategyBenchmarkEquityKey(item.code)
    )
  );
  const strategyMetrics = metricRows.find((item) => item.isStrategy) || {};
  const rangedComparisons = metricRows
    .filter((item) => !item.isStrategy)
    .map((item) => ({
      ...item,
      return_advantage:
        typeof strategyMetrics.total_return === "number" && typeof item.total_return === "number"
          ? strategyMetrics.total_return - item.total_return
          : null,
      drawdown_reduction:
        typeof strategyMetrics.max_drawdown === "number" && typeof item.max_drawdown === "number"
          ? strategyMetrics.max_drawdown - item.max_drawdown
          : null,
    }));
  const metricComparisonAssets = metricRows.map((item) => {
    const comparison = rangedComparisons.find((asset) => asset.code === item.code);
    return comparison || item;
  });
  const primaryBenchmark = rangedComparisons[0] || {};
  const alphaVsPrimary =
    typeof strategyMetrics.total_return === "number" && typeof primaryBenchmark.total_return === "number"
      ? strategyMetrics.total_return - primaryBenchmark.total_return
      : null;
  return {
    ...sourceBacktest,
    summary: {
      ...sourceBacktest.summary,
      start_date: strategyIsoToRawDate(equityCurve[0].date),
      end_date: strategyIsoToRawDate(equityCurve[equityCurve.length - 1].date),
      sessions: equityCurve.length,
      strategy_total_return: strategyMetrics.total_return,
      annualized_return: strategyMetrics.annualized_return,
      max_drawdown: strategyMetrics.max_drawdown,
      sharpe: strategyMetrics.sharpe,
      calmar: strategyMetrics.calmar,
      equal_weight_return: primaryBenchmark.total_return,
      alpha_vs_equal_weight: alphaVsPrimary,
      comparison_assets: rangedComparisons,
      metric_comparison_assets: metricComparisonAssets,
    },
    performance_metrics: {
      ...sourceBacktest.performance_metrics,
      total_return: strategyMetrics.total_return,
      annualized_return: strategyMetrics.annualized_return,
      annualized_volatility: strategyMetrics.annualized_volatility,
      max_drawdown: strategyMetrics.max_drawdown,
      sharpe: strategyMetrics.sharpe,
    },
    equity_curve: equityCurve,
  };
}

function strategyGetVisibleBenchmarkCodes(backtest) {
  if (!strategyHasSelectableBenchmarks(backtest)) return null;
  const summary = backtest.summary || {};
  const strategyId = summary.strategy_id || "generic";
  const assets = (summary.comparison_assets || []).filter((asset) => !asset.always_visible && !asset.isVirtual);
  if (!assets.length) return null;
  if (!strategyBenchmarkToggleState[strategyId]) {
    strategyBenchmarkToggleState[strategyId] = new Set(assets.map((asset) => asset.code));
  }
  const selected = strategyBenchmarkToggleState[strategyId];
  const availableCodes = new Set(assets.map((asset) => asset.code));
  for (const code of [...selected]) {
    if (!availableCodes.has(code)) selected.delete(code);
  }
  return [...selected];
}

function strategyGetVisibleVirtualCodes(backtest) {
  if (backtest.metadata?.indicator !== "free_cash_flow_buy_hold") return null;
  const summary = backtest.summary || {};
  const strategyId = summary.strategy_id || "generic";
  const assets = (summary.comparison_assets || []).filter((asset) => asset.isVirtual || asset.always_visible);
  if (!assets.length) return null;
  if (!strategyVirtualToggleState[strategyId]) {
    strategyVirtualToggleState[strategyId] = new Set(assets.map((asset) => asset.code));
  }
  const selected = strategyVirtualToggleState[strategyId];
  const availableCodes = new Set(assets.map((asset) => asset.code));
  for (const code of [...selected]) {
    if (!availableCodes.has(code)) selected.delete(code);
  }
  return [...selected];
}

function strategyVisibleChartCodes(backtest) {
  return [
    ...(strategyGetVisibleVirtualCodes(backtest) || []),
    ...(strategyGetVisibleBenchmarkCodes(backtest) || []),
  ];
}

function strategyMean(values) {
  const clean = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : null;
}

function strategyStandardDeviation(values) {
  const clean = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (clean.length < 2) return null;
  const mean = clean.reduce((sum, value) => sum + value, 0) / clean.length;
  const variance = clean.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (clean.length - 1);
  return Math.sqrt(variance);
}

function strategyRiskParityWeights(returnRows, equityKeys, index, lookback = 60, minSamples = 20) {
  if (index < minSamples) return null;
  const start = Math.max(1, index - lookback);
  const inverseVols = equityKeys.map((key) => {
    const values = returnRows.slice(start, index).map((row) => row[key]);
    const volatility = strategyStandardDeviation(values);
    return volatility && volatility > 0 ? 1 / volatility : null;
  });
  if (inverseVols.some((value) => typeof value !== "number" || !Number.isFinite(value))) return null;
  const total = inverseVols.reduce((sum, value) => sum + value, 0);
  if (!total) return null;
  return inverseVols.map((value) => value / total);
}

function strategyWeightedMean(values, weights) {
  let total = 0;
  let weightTotal = 0;
  values.forEach((value, index) => {
    const weight = weights?.[index];
    if (typeof value === "number" && Number.isFinite(value) && typeof weight === "number" && Number.isFinite(weight)) {
      total += value * weight;
      weightTotal += weight;
    }
  });
  return weightTotal > 0 ? total / weightTotal : null;
}

function strategyBuildCheckedEqualWeightBacktest(backtest, visibleBenchmarkCodes) {
  if (backtest.metadata?.indicator !== "free_cash_flow_buy_hold") return backtest;
  const selectedCodes = new Set(visibleBenchmarkCodes || []);
  const baseComparisonAssets = (backtest.summary?.comparison_assets || []).filter(
    (asset) => !asset.always_visible && !asset.isVirtual
  );
  const selectedAssets = baseComparisonAssets.filter((asset) => selectedCodes.has(asset.code));
  const equityKeys = ["strategy_equity", ...selectedAssets.map((asset) => strategyBenchmarkEquityKey(asset.code))];
  const sourceRows = backtest.equity_curve || [];
  if (!sourceRows.length) return backtest;

  const returnRows = sourceRows.map((row, index) => {
    const previous = sourceRows[index - 1];
    const returns = {};
    equityKeys.forEach((key) => {
      returns[key] =
        index > 0 && previous && typeof row[key] === "number" && typeof previous[key] === "number" && previous[key] > 0
          ? row[key] / previous[key] - 1
          : null;
    });
    return returns;
  });
  let equalWeightEquity = 1;
  let riskParityEquity = 1;
  const equityCurve = sourceRows.map((row, index) => {
    if (index > 0) {
      const returns = equityKeys.map((key) => returnRows[index][key]);
      equalWeightEquity *= 1 + (strategyMean(returns) || 0);
      const riskWeights = strategyRiskParityWeights(returnRows, equityKeys, index);
      riskParityEquity *= 1 + (strategyWeightedMean(returns, riskWeights) ?? strategyMean(returns) ?? 0);
    }
    return {
      ...row,
      checked_equal_weight_equity: equalWeightEquity,
      checked_risk_parity_equity: riskParityEquity,
    };
  });
  const label =
    selectedAssets.length > 0
      ? `勾选等权ETF（自由现金流R + ${selectedAssets.length}个基准）`
      : "勾选等权ETF（仅自由现金流R）";
  const riskParityLabel =
    selectedAssets.length > 0
      ? `勾选风险平价ETF（自由现金流R + ${selectedAssets.length}个基准）`
      : "勾选风险平价ETF（仅自由现金流R）";
  const equalWeightMetric = strategyEquityMetricsFromCurve(
    {
      code: "checked_equal_weight",
      name: "勾选等权ETF",
      group: "虚拟等权",
      label,
      isVirtual: true,
      always_visible: true,
      equity_key: "checked_equal_weight_equity",
      composition: ["480092.CNI", ...selectedAssets.map((asset) => asset.code)],
    },
    equityCurve,
    "checked_equal_weight_equity"
  );
  const riskParityMetric = strategyEquityMetricsFromCurve(
    {
      code: "checked_risk_parity",
      name: "勾选风险平价ETF",
      group: "虚拟风险平价",
      label: riskParityLabel,
      isVirtual: true,
      always_visible: true,
      equity_key: "checked_risk_parity_equity",
      composition: ["480092.CNI", ...selectedAssets.map((asset) => asset.code)],
      weighting: "60日滚动波动率倒数权重，样本不足时等权。",
    },
    equityCurve,
    "checked_risk_parity_equity"
  );
  const metricRows = backtest.summary?.metric_comparison_assets || [];
  const strategyRow = metricRows.find((item) => item.isStrategy);
  const otherRows = metricRows.filter(
    (item) => !item.isStrategy && !["checked_equal_weight", "checked_risk_parity"].includes(item.code)
  );
  const withStrategyGap = (metric) => ({
    ...metric,
    return_advantage:
      typeof backtest.summary?.strategy_total_return === "number" && typeof metric.total_return === "number"
        ? backtest.summary.strategy_total_return - metric.total_return
        : null,
    drawdown_reduction:
      typeof backtest.summary?.max_drawdown === "number" && typeof metric.max_drawdown === "number"
        ? backtest.summary.max_drawdown - metric.max_drawdown
        : null,
  });
  return {
    ...backtest,
    summary: {
      ...backtest.summary,
      comparison_assets: [
        withStrategyGap(equalWeightMetric),
        withStrategyGap(riskParityMetric),
        ...baseComparisonAssets,
      ],
      metric_comparison_assets: [
        ...(strategyRow ? [strategyRow] : []),
        equalWeightMetric,
        riskParityMetric,
        ...otherRows,
      ],
    },
    equity_curve: equityCurve,
  };
}

function strategySetGenericBenchmarkToggles(backtest, sourceBacktest = backtest) {
  const target = document.getElementById("genericBenchmarkToggles");
  if (!target) return null;
  const summary = backtest.summary || {};
  const strategyId = summary.strategy_id || "generic";
  const baseAssets = (summary.comparison_assets || []).filter((asset) => !asset.always_visible && !asset.isVirtual);
  const virtualAssets = (summary.comparison_assets || []).filter((asset) => asset.always_visible || asset.isVirtual);
  if (!strategyHasSelectableBenchmarks(backtest) || (!baseAssets.length && !virtualAssets.length)) {
    target.hidden = true;
    target.innerHTML = "";
    return null;
  }
  strategyGetVisibleBenchmarkCodes(backtest);
  strategyGetVisibleVirtualCodes(backtest);
  const selectedBase = strategyBenchmarkToggleState[strategyId] || new Set();
  const selectedVirtual = strategyVirtualToggleState[strategyId] || new Set();
  const checkboxHtml = (asset, kind, selected) => `
    <label class="${kind === "virtual" ? "is-virtual" : ""}">
      <input type="checkbox" value="${strategyEscapeHtml(asset.code)}" data-toggle-kind="${kind}" ${selected.has(asset.code) ? "checked" : ""} />
      <i></i>
      ${strategyEscapeHtml(asset.group || asset.label || asset.code)}
    </label>
  `;
  target.hidden = false;
  target.innerHTML = `
    <span>${backtest.metadata?.indicator === "free_cash_flow_buy_hold" ? "图上显示基准 · 虚拟ETF=自由现金流R+勾选项" : "图上显示对照曲线"}</span>
    ${virtualAssets.map((asset) => checkboxHtml(asset, "virtual", selectedVirtual)).join("")}
    ${baseAssets.map((asset) => checkboxHtml(asset, "base", selectedBase)).join("")}
  `;
  target.onchange = (event) => {
    const input = event.target.closest("input[type='checkbox']");
    if (!input) return;
    if (input.dataset.toggleKind === "virtual") {
      if (input.checked) selectedVirtual.add(input.value);
      else selectedVirtual.delete(input.value);
      renderStrategyBacktestChart("genericStrategyChart", backtest, {
        visibleBenchmarkCodes: strategyVisibleChartCodes(backtest),
      });
      return;
    }
    if (input.checked) selectedBase.add(input.value);
    else selectedBase.delete(input.value);
    strategySetGenericPage(sourceBacktest);
  };
  return strategyVisibleChartCodes(backtest);
}

function strategySignalLabel(value) {
  const labels = {
    defensive_cash: "防守现金",
    single_defensive_asset: "单防守资产+现金",
    dividend_low_vol_mix: "红利低波组合",
    cash_empty_position: "511880 空仓",
    industry_top3_momentum: "行业 Top3 动量",
    all_assets_cash: "四资产现金",
    single_asset_plus_cash: "单资产+现金",
    top2_four_asset: "四资产 Top2",
    drawdown_cash_wait: "回撤未到档",
    drawdown_ladder_buy: "回撤分批买入",
    all_weather_rebalance: "全天候再平衡",
    reversion_full_buy: "回归满仓",
    reversion_buy: "回归加仓",
    reversion_mild_buy: "轻度加仓",
    reversion_neutral: "中性仓位",
    reversion_reduce: "高位降仓",
    reversion_light: "极高位轻仓",
    reversion_guard_cap: "下行限仓",
    fcf_channel_half_reduce: "上轨卖出",
    fcf_channel_full_exit: "上轨空仓",
    fcf_channel_full_buy: "下轨买入",
    fcf_channel_hold: "通道内持有",
    fcf_rebound_buy: "回撤买入",
    fcf_rebound_sell: "反弹卖出",
    fcf_rebound_hold: "等待信号",
    fcf_buy_hold_full: "满仓持有",
    fcf_chinext_dynamic_init: "初始等权",
    fcf_chinext_dynamic_rebalance: "动态调仓",
    fcf_chinext_dynamic_hold: "继续持有",
    fcf_chinext_reversion_init: "初始等权",
    fcf_chinext_reversion_rebalance: "回归调仓",
    fcf_chinext_reversion_hold: "继续持有",
    fcf_chinext_balanced_reversion_init: "初始等权",
    fcf_chinext_balanced_reversion_rebalance: "平衡回归调仓",
    fcf_chinext_balanced_reversion_hold: "继续持有",
    fcf_ma_deviation_init: "初始满仓",
    fcf_ma_deviation_buy: "低位恢复满仓",
    fcf_ma_deviation_reduce: "高位降到半仓",
    fcf_dual_ma_init: "初始满仓",
    fcf_dual_ma_golden_cross_buy: "金叉满仓",
    fcf_dual_ma_death_cross_sell: "死叉空仓",
  };
  return labels[value] || value || "--";
}

function strategySetGenericPage(sourceBacktest) {
  const selectedRange = strategySetGenericRangeControls(sourceBacktest);
  const rangedBacktest = strategyBuildRangeBacktest(sourceBacktest, selectedRange);
  const visibleBenchmarkCodes = strategyGetVisibleBenchmarkCodes(rangedBacktest);
  const backtest = strategyBuildCheckedEqualWeightBacktest(rangedBacktest, visibleBenchmarkCodes);
  const metadata = backtest.metadata || {};
  const summary = backtest.summary || {};
  const performance = backtest.performance_metrics || {};
  const validation = backtest.validation || {};
  const universe = metadata.universe || [];
  const signals = backtest.signals || [];
  const latestSignal = signals[signals.length - 1] || {};
  const isChannelStrategy = metadata.indicator === "free_cash_flow_trend_channel";
  const isReboundStrategy = metadata.indicator === "free_cash_flow_drawdown_rebound";
  const isBuyHoldStrategy = metadata.indicator === "free_cash_flow_buy_hold";
  const isPairDynamicStrategy = metadata.indicator === "free_cash_flow_chinext_dynamic";
  const isPairReversionStrategy = metadata.indicator === "free_cash_flow_chinext_reversion";
  const isPairBalancedReversionStrategy = metadata.indicator === "free_cash_flow_chinext_balanced_reversion";
  const isMaDeviationStrategy = metadata.indicator === "free_cash_flow_ma_deviation";
  const isDualMaStrategy = metadata.indicator === "free_cash_flow_dual_ma_crossover";
  const comparisonLabel = summary.equal_weight_label || "等权";
  const annualizedReturn =
    typeof summary.annualized_return === "number" ? summary.annualized_return : performance.annualized_return;

  document.title = summary.strategy_name || "策略回测";
  strategySetText("genericEyebrow", summary.strategy_id || "Strategy");
  strategySetText("genericTitle", summary.strategy_name || "策略回测");
  strategySetText("genericDescription", metadata.description || "--");
  strategySetText("genericRange", `${strategyToIsoDate(summary.start_date)} - ${strategyToIsoDate(summary.end_date)}`);
  const genericTiles = [
    { label: "回测区间", value: `${strategyToIsoDate(summary.start_date)} - ${strategyToIsoDate(summary.end_date)}` },
    { label: "策略收益", value: strategySignedRatioText(summary.strategy_total_return) },
    { label: "年化收益", value: strategySignedRatioText(annualizedReturn) },
    { label: "最大回撤", value: strategyPercentText(summary.max_drawdown) },
    { label: `Alpha vs ${comparisonLabel}`, value: strategySignedRatioText(summary.alpha_vs_equal_weight) },
    ...(isChannelStrategy
      ? [{ label: "最新轨道位置", value: strategyFixedText(summary.latest_channel_position, 2) }]
      : []),
    { label: "夏普", value: strategyFixedText(summary.sharpe, 2) },
    ...(typeof summary.calmar === "number" ? [{ label: "Calmar", value: strategyFixedText(summary.calmar, 2) }] : []),
    ...(isPairReversionStrategy || isPairBalancedReversionStrategy
      ? [
          { label: "相对Z-score", value: strategyFixedText(summary.latest_relative_zscore, 2) },
          { label: "120日相关", value: strategyFixedText(summary.latest_rolling_correlation, 2) },
        ]
      : []),
    ...(isMaDeviationStrategy
      ? [
          { label: "最新MA偏离", value: strategySignedRatioText(summary.latest_ma_deviation) },
          { label: "Calmar最优参数", value: summary.best_parameter?.label || "--" },
          { label: "年化最高参数", value: summary.best_annualized_parameter?.label || "--" },
        ]
      : []),
    ...(isDualMaStrategy
      ? [
          { label: "最新快慢线差", value: strategySignedRatioText(summary.latest_ma_spread) },
          { label: "Calmar最优参数", value: summary.best_parameter?.label || "--" },
          { label: "年化最高参数", value: summary.best_annualized_parameter?.label || "--" },
          { label: "10/20规则年化", value: strategySignedRatioText(summary.drawdown20_ma_rule?.annualized_return) },
          { label: "10/20规则回撤", value: strategyPercentText(summary.drawdown20_ma_rule?.max_drawdown) },
        ]
      : []),
    { label: "调仓次数", value: strategyIntegerText(summary.rebalance_count) },
  ];
  strategySetSummaryTiles(genericTiles);
  const methodTarget = document.getElementById("genericMethodList");
  if (methodTarget) {
    methodTarget.innerHTML = (metadata.method || [])
      .map((item, index) => `<div><span>规则 ${index + 1}</span><strong>${strategyEscapeHtml(item)}</strong></div>`)
      .join("");
  }
  strategySetText("genericLatestDate", latestSignal.date ? strategyToIsoDate(latestSignal.date) : "--");
  strategySetText("genericLatestSignal", strategySignalLabel(summary.latest_signal));
  strategySetText("genericRebalanceCount", strategyIntegerText(summary.rebalance_count));
  const latestWeightsTarget = document.getElementById("genericLatestWeights");
  if (latestWeightsTarget) latestWeightsTarget.innerHTML = strategyGenericWeightRows(summary.latest_weights || {}, universe);
  const latestReason = latestSignal.rebalance_reason || {};
  strategySetText("genericLatestReason", latestReason.detail || metadata.description || "--");
  strategySetText("genericStrategyReturn", strategySignedRatioText(summary.strategy_total_return));
  strategySetText("genericAnnualizedReturn", strategySignedRatioText(annualizedReturn));
  strategySetText("genericMaxDrawdown", strategyPercentText(summary.max_drawdown));
  strategySetText("genericAlphaEqual", strategySignedRatioText(summary.alpha_vs_equal_weight));
  strategySetText("genericSharpe", strategyFixedText(summary.sharpe, 2));
  strategySetText("genericHitRate", strategyPercentText(summary.hit_rate_vs_primary_benchmark));
  strategySetText("genericSessions", strategyIntegerText(summary.sessions));
  strategySetText("genericTurnover", strategyPercentText(summary.average_turnover));
  strategySetText("genericSignalSummary", strategySignalLabel(summary.latest_signal));
  strategySetText("genericSharpeFormula", strategySharpeFormulaText(performance));
  strategySetGenericComparison(summary, performance);
  strategySetGenericParameterScan(summary);
  const verdict = isChannelStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "本策略跑赢自由现金流指数基准，说明趋势通道择时存在初步收益改善。"
      : "本策略未跑赢自由现金流指数基准，当前更像风险暴露调节工具，需要继续优化趋势线规则。"
    : isReboundStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "代表阈值跑赢国证自由现金流R基准，说明回撤买入/反弹卖出在当前样本有正超额。"
      : "代表阈值未跑赢国证自由现金流R基准，说明该规则目前更像参数研究，不宜直接当成稳赚模型。"
    : isBuyHoldStrategy
    ? "本策略是不择时的 480092.CNI 满仓基准，用于直接观察自由现金流R相对主要全收益指数的长期收益和风险。"
    : isPairDynamicStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "动态满仓策略跑赢 50/50 固定等权，说明风险平价和趋势倾斜在当前样本有增益。"
      : "动态满仓策略未跑赢 50/50 固定等权，说明当前规则复杂度可能没有补偿调仓成本。"
    : isPairReversionStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "相对回归策略跑赢 50/50 固定等权，说明两资产偏离后反向再平衡在当前样本有增益。"
      : "相对回归策略未跑赢 50/50 固定等权，说明当前参数下回归交易没有补偿调仓和错判成本。"
    : isPairBalancedReversionStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "平衡回归策略跑赢 50/50 固定等权，说明底仓+风险平价修正+两档回归倾斜在当前样本有增益。"
      : "平衡回归策略未跑赢 50/50 固定等权，说明当前两档倾斜规则仍不足以形成稳定超额。"
    : isMaDeviationStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "默认 MA120/±5% 偏离策略跑赢自由现金流R满仓基准，说明均线偏离调仓在当前样本有初步收益改善。"
      : "默认 MA120/±5% 偏离策略未跑赢自由现金流R满仓基准，说明均线偏离更可能是仓位平滑工具；全样本最优参数只能作为研究参考。"
    : isDualMaStrategy
    ? validation.alpha_positive_vs_equal_weight
      ? "默认 MA30/MA90 双均线策略跑赢自由现金流R满仓基准，说明趋势过滤在当前样本有初步收益改善。"
      : "默认 MA30/MA90 双均线策略未跑赢自由现金流R满仓基准，说明金叉死叉更可能是回撤控制工具；全样本最优参数只能作为研究参考。"
    : validation.mean_reversion_signal
    ? validation.alpha_positive_vs_equal_weight
      ? "本策略跑赢四 ETF 等权基准，说明当前均值回归规则有初步 alpha 证据。"
      : "本策略未跑赢四 ETF 等权基准，当前更像回撤控制工具，不是稳赚模型。"
    : validation.static_allocation
    ? "本策略是固定配置基准，重点观察收益、回撤和夏普之间的权衡，不以跑赢等权资产池作为唯一目标。"
    : validation.alpha_positive_vs_equal_weight
      ? "本策略跑赢等权资产池，具备继续优化和跟踪价值。"
      : "本策略未跑赢等权资产池，当前规则更适合保留为反例或继续优化。";
  strategySetText(
    "genericConclusion",
    `${summary.short_name || "策略"}覆盖 ${strategyIntegerText(summary.sessions)} 个交易日，${verdict} 收益口径使用${isChannelStrategy ? " Tushare index_daily 指数日收益；图中红/灰/绿线为 2016 低点以来的对数直线上轨、中轨、下轨。本版通道包含当前研究锚点，适合复盘观察，不等同于严格无未来函数实盘信号。" : isReboundStrategy ? " Tushare index_daily 指数日收益；图中五条曲线分别代表 n=10%/12%/15%/18%/20%，策略摘要采用年化收益最高的阈值作为代表结果。现金收益暂按 0 处理。" : isBuyHoldStrategy ? " Tushare index_daily 全收益指数日收益；红/绿背景来自长期牛熊主周期，上证指数灰线只作市场环境背景参考。" : isPairDynamicStrategy ? " Tushare index_daily 全收益指数日收益；组合始终满仓，信号按收盘后计算并从下一交易日生效，红/绿背景来自长期牛熊主周期。" : isPairReversionStrategy ? " Tushare index_daily 全收益指数日收益；组合始终满仓，按相对比值 Z-score 做反向再平衡，信号按收盘后计算并从下一交易日生效。" : isPairBalancedReversionStrategy ? " Tushare index_daily 全收益指数日收益；组合始终满仓，以 50/50 为底仓，相对极端时先做预备回归倾斜，反转确认后加大倾斜。" : isMaDeviationStrategy ? " Tushare index_daily 全收益指数日收益；默认 MA120/±5% 信号按收盘后计算并从下一交易日生效。参数扫描是全样本回看筛参，含未来函数，只能用于研究。" : isDualMaStrategy ? " Tushare index_daily 全收益指数日收益；默认 MA30/MA90 金叉/死叉信号按收盘后计算并从下一交易日生效；额外测试规则为历史最高点回撤 10% 清仓、继续回撤到 20% 满仓，深跌买入后需先收复到 10% 回撤以内才重新允许下一次 10% 清仓。默认参数来自全样本筛参观察，含未来函数，只能用于研究。" : " ETF fund_daily pct_chg/pre_close。"}`
  );
  const signalTarget = document.getElementById("genericSignalList");
  if (signalTarget) {
    const rows = [...signals]
      .reverse()
      .map((item) => {
        const reason = item.rebalance_reason || {};
        return `
          <div class="generic-signal-row">
            <div><span>日期</span><strong>${strategyToIsoDate(item.date)}</strong></div>
            <div><span>信号</span><strong>${strategySignalLabel(item.strategy_signal)}</strong></div>
            <div><span>换手</span><strong>${strategyPercentText(item.turnover_to_target)}</strong><em>${strategyEscapeHtml(strategyGenericCandidateText(item.top_candidates))}</em></div>
            <div><span>目标仓位</span>${strategyGenericWeightStack(item.target_weights || {}, universe)}</div>
            <p>${strategyEscapeHtml(reason.detail || "")}</p>
          </div>
        `;
      })
      .join("");
    signalTarget.innerHTML = `
      <div class="generic-signal-table">
        <div class="generic-signal-row generic-signal-head">
          <strong>日期</strong>
          <strong>信号</strong>
          <strong>换手 / 候选</strong>
          <strong>目标仓位</strong>
          <strong>调仓原因</strong>
        </div>
        ${rows}
      </div>
    `;
  }
  strategySetText("genericHistoryCount", `${strategyIntegerText(signals.length)} 次再平衡记录`);
  const currentVisibleBenchmarkCodes = strategySetGenericBenchmarkToggles(backtest, sourceBacktest);
  renderStrategyBacktestChart(
    "genericStrategyChart",
    backtest,
    currentVisibleBenchmarkCodes === null ? {} : { visibleBenchmarkCodes: currentVisibleBenchmarkCodes }
  );
}

async function strategyRenderGenericPage() {
  const strategyId = window.location.pathname.split("/").filter(Boolean).pop();
  const backtest = await strategyGetJson(`/api/strategy-backtests/${strategyId}`);
  strategySetGenericPage(backtest);
}

async function strategyRenderEtfRotationPage() {
  const [signal, backtest] = await Promise.all([
    strategyGetJson("/api/style/rotation-signal"),
    strategyGetJson("/api/style/rotation-backtest"),
  ]);
  const summary = backtest.summary || {};
  strategySetSummaryTiles([
    { label: "回测区间", value: `${strategyToIsoDate(summary.start_date)} - ${strategyToIsoDate(summary.end_date)}` },
    { label: "轮动收益", value: strategySignedRatioText(summary.rotation_total_return) },
    { label: "年化收益", value: strategySignedRatioText(backtest.performance_metrics?.annualized_return) },
    { label: "最大回撤", value: strategyPercentText(summary.max_drawdown) },
    { label: "命中率", value: strategyPercentText(summary.hit_rate_vs_510500) },
    { label: "当前方向", value: strategyRotationSignalLabel(signal.rebalance_signal) },
    { label: "调仓次数", value: strategyIntegerText(summary.rebalance_count) },
  ]);
  strategySetRotationSignal(signal);
  strategySetEtfBacktest(backtest);
  renderEtfRotationBacktestChart("rotationBacktestChart", backtest);
}

async function strategyRenderMacroStylePage() {
  const backtest = await strategyGetJson("/api/style/macro-style-etf-backtest");
  const summary = backtest.summary || {};
  strategySetSummaryTiles([
    { label: "回测区间", value: `${strategyToIsoDate(summary.start_date)} - ${strategyToIsoDate(summary.end_date)}` },
    { label: "分层收益", value: strategySignedRatioText(summary.hierarchical_total_return) },
    { label: "年化收益", value: strategySignedRatioText(backtest.performance_metrics?.annualized_return) },
    { label: "最大回撤", value: strategyPercentText(summary.max_drawdown) },
    { label: "平均权益仓位", value: strategyPercentText(summary.average_target_exposure) },
    { label: "Alpha vs A1", value: strategySignedRatioText(summary.alpha_vs_current_a1) },
    { label: "调仓次数", value: strategyIntegerText(summary.rebalance_count) },
  ]);
  strategySetMacroLatestSignal(backtest.signals || []);
  strategySetMacroBacktest(backtest);
  renderMacroStyleEtfBacktestChart("macroStyleEtfChart", backtest);
}

async function strategyBootPage() {
  const page = document.body.dataset.page;
  if (page === "strategy-etf-rotation") await strategyRenderEtfRotationPage();
  if (page === "strategy-macro-style") await strategyRenderMacroStylePage();
  if (page === "strategy-generic") await strategyRenderGenericPage();
}

document.getElementById("rotationBacktestReset")?.addEventListener("click", () => {
  resetEtfRotationBacktestChart("rotationBacktestChart");
});
document.getElementById("macroStyleReset")?.addEventListener("click", () => {
  resetEtfRotationBacktestChart("macroStyleEtfChart");
});
document.getElementById("genericStrategyReset")?.addEventListener("click", () => {
  resetEtfRotationBacktestChart("genericStrategyChart");
});

strategyBootPage().catch((error) => {
  console.error(error);
  strategySetText("pageError", error.message || "页面加载失败");
});
