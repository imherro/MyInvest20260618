const REGIME_COLORS = {
  bull: "#c73d3d",
  bear: "#17885b",
  range: "#eab308",
  transition: "#8b95a5",
  recovery: "#eab308",
  contraction: "#8b95a5",
};

const REGIME_LABELS = {
  bull: "牛市",
  bear: "熊市",
  range: "震荡",
  transition: "过渡",
  recovery: "修复",
  contraction: "收缩",
};

const SHADE_COLORS = {
  bull: "rgba(199, 61, 61, 0.12)",
  bear: "rgba(23, 136, 91, 0.12)",
  range: "rgba(234, 179, 8, 0.13)",
  transition: "rgba(139, 149, 165, 0.13)",
  recovery: "rgba(234, 179, 8, 0.13)",
  contraction: "rgba(139, 149, 165, 0.13)",
};

const STATUS_BAND_COLORS = {
  bull: "#c73d3d",
  bear: "#17885b",
  range: "#eab308",
  transition: "#8b95a5",
};

const STATUS_BAND_VALUES = {
  bull: 0,
  bear: 1,
  range: 2,
  transition: 3,
  recovery: 2,
  contraction: 3,
};

function regimeLabel(regime) {
  return REGIME_LABELS[regime] || regime || "--";
}

function toIsoDate(value) {
  if (!value || value.length !== 8) return value;
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function scorePercent(value) {
  if (typeof value !== "number") return "--";
  return `${Math.round(value * 100)}%`;
}

function baseLayout(height) {
  return {
    height,
    margin: { l: 42, r: 18, t: 18, b: 42 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Segoe UI, Microsoft YaHei, Arial, sans-serif", color: "#1d2433" },
  };
}

function resetEtfRotationBacktestChart(elementId = "rotationBacktestChart") {
  const chart = document.getElementById(elementId);
  if (!chart) return;
  Plotly.relayout(chart, {
    "xaxis.autorange": true,
    "yaxis.autorange": true,
  });
}

if (typeof window !== "undefined") {
  window.resetEtfRotationBacktestChart = resetEtfRotationBacktestChart;
}

function renderRadar(elementId, scores) {
  const labels = ["趋势", "宽度", "流动性", "波动稳定"];
  const values = [scores.trend, scores.breadth, scores.liquidity, scores.volatility];
  Plotly.react(
    elementId,
    [
      {
        type: "scatterpolar",
        r: [...values, values[0]],
        theta: [...labels, labels[0]],
        fill: "toself",
        fillcolor: "rgba(38, 99, 235, 0.18)",
        line: { color: "#2663eb", width: 3 },
        marker: { size: 7, color: "#2663eb" },
        hovertemplate: "%{theta}: %{r:.2f}<extra></extra>",
      },
    ],
    {
      ...baseLayout(260),
      polar: {
        bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 1], tickvals: [0, 0.5, 1], gridcolor: "#dde3ec" },
        angularaxis: { gridcolor: "#dde3ec" },
      },
      showlegend: false,
    },
    { responsive: true, displayModeBar: false }
  );
}

const SCORE_SIGNAL_STATES = {
  weak: {
    label: "趋势宽度共振弱",
    shortLabel: "共振弱",
    color: "rgba(23, 136, 91, 0.16)",
    textColor: "#11754d",
    labelY: 1.08,
  },
  liquidity: {
    label: "流动性修复",
    shortLabel: "流动性修复",
    color: "rgba(245, 158, 11, 0.15)",
    textColor: "#b45309",
    labelY: 1.03,
  },
  relief: {
    label: "短期风险解除",
    shortLabel: "风险解除",
    color: "rgba(199, 61, 61, 0.15)",
    textColor: "#b12f2f",
    labelY: 0.98,
  },
};

function addIsoDays(isoDate, days) {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoDate;
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function rollingScore(items, index, key, windowSize = 5) {
  const values = items
    .slice(Math.max(0, index - windowSize + 1), index + 1)
    .map((item) => item.scores?.[key])
    .filter((value) => typeof value === "number");
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function classifyScoreSignal(items, index) {
  const trend = rollingScore(items, index, "trend");
  const breadth = rollingScore(items, index, "breadth");
  const liquidity = rollingScore(items, index, "liquidity");
  const volatility = rollingScore(items, index, "volatility");
  const composite = rollingScore(items, index, "regime_score");
  const previousLiquidity = rollingScore(items, Math.max(0, index - 20), "liquidity") ?? liquidity;
  const liquidityDelta = typeof liquidity === "number" && typeof previousLiquidity === "number" ? liquidity - previousLiquidity : 0;

  if (typeof trend === "number" && typeof breadth === "number" && trend <= 0.42 && breadth <= 0.38) {
    return "weak";
  }
  if (
    typeof composite === "number" &&
    typeof trend === "number" &&
    typeof breadth === "number" &&
    typeof liquidity === "number" &&
    typeof volatility === "number" &&
    composite >= 0.55 &&
    trend >= 0.45 &&
    breadth >= 0.45 &&
    liquidity >= 0.45 &&
    volatility >= 0.45
  ) {
    return "relief";
  }
  if (
    typeof liquidity === "number" &&
    typeof composite === "number" &&
    liquidity >= 0.48 &&
    liquidityDelta >= 0.06 &&
    composite >= 0.35
  ) {
    return "liquidity";
  }
  return null;
}

function buildScoreSignalIntervals(items) {
  const intervals = [];
  let activeKey = null;
  let startIndex = 0;

  const closeActive = (endIndex) => {
    if (!activeKey) return;
    const sessions = endIndex - startIndex + 1;
    const isLatest = endIndex === items.length - 1;
    if (sessions >= 3 || isLatest) {
      intervals.push({ key: activeKey, startIndex, endIndex, sessions, isLatest });
    }
  };

  items.forEach((item, index) => {
    const key = classifyScoreSignal(items, index);
    if (key !== activeKey) {
      closeActive(index - 1);
      activeKey = key;
      startIndex = index;
    }
  });
  closeActive(items.length - 1);
  return intervals;
}

function renderScoreHistoryChart(elementId, history) {
  const items = history?.items || [];
  if (!items.length) {
    Plotly.purge(elementId);
    return;
  }
  const x = items.map((item) => toIsoDate(item.as_of));
  const signalIntervals = buildScoreSignalIntervals(items);
  const signalShapes = signalIntervals.map((interval) => {
    const state = SCORE_SIGNAL_STATES[interval.key];
    const x0 = x[interval.startIndex];
    const endDate = x[interval.endIndex];
    const x1 = interval.endIndex < x.length - 1 ? x[interval.endIndex + 1] : addIsoDays(endDate, 4);
    return {
      type: "rect",
      xref: "x",
      yref: "paper",
      x0,
      x1,
      y0: 0,
      y1: 1,
      fillcolor: state.color,
      line: { width: 0 },
      layer: "below",
    };
  });
  const signalAnnotations = signalIntervals
    .filter((interval) => interval.sessions >= 4 || interval.isLatest)
    .map((interval) => {
      const state = SCORE_SIGNAL_STATES[interval.key];
      const start = x[interval.startIndex];
      const end = x[interval.endIndex];
      return {
        x: interval.isLatest ? addIsoDays(end, 2) : start,
        xref: "x",
        y: state.labelY,
        yref: "paper",
        text: interval.isLatest ? `当前：${state.shortLabel}` : state.shortLabel,
        showarrow: false,
        xanchor: interval.isLatest ? "right" : "left",
        font: { size: 11, color: state.textColor },
        bgcolor: "rgba(255,255,255,0.82)",
        bordercolor: state.textColor,
        borderwidth: 1,
        borderpad: 3,
      };
    });
  const scoreSeries = [
    { key: "regime_score", name: "综合分", color: "#111827", width: 3.4, rank: 1 },
    { key: "trend", name: "趋势", color: "#2563eb", width: 2.1, rank: 2 },
    { key: "breadth", name: "宽度", color: "#16a34a", width: 2.1, rank: 3 },
    { key: "liquidity", name: "流动性", color: "#f97316", width: 2.1, rank: 4 },
    { key: "volatility", name: "波动稳定", color: "#9333ea", width: 2.1, rank: 5 },
  ];
  const scoreTraces = scoreSeries.map(({ key, name, color, width, rank }) => ({
    type: "scatter",
    mode: "lines",
    name,
    x,
    y: items.map((item) => item.scores?.[key] ?? null),
    line: { color, width },
    legendrank: rank,
    hovertemplate: `%{x}<br>${name} %{y:.1%}<extra></extra>`,
  }));
  const indexTrace = {
    type: "scatter",
    mode: "lines",
    name: "上证指数",
    x,
    y: items.map((item) => item.index?.close ?? null),
    yaxis: "y2",
    line: { color: "rgba(100, 116, 139, 0.38)", width: 2 },
    legendrank: 10,
    hovertemplate: "%{x}<br>上证 %{y:.2f}<extra></extra>",
  };
  Plotly.react(
    elementId,
    [indexTrace, ...scoreTraces],
    {
      ...baseLayout(360),
      margin: { l: 44, r: 58, t: 48, b: 54 },
      hovermode: "x unified",
      xaxis: { tickformat: "%Y-%m", gridcolor: "#edf0f5" },
      yaxis: {
        title: "评分",
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: "#edf0f5",
        zeroline: false,
      },
      yaxis2: {
        title: "上证",
        overlaying: "y",
        side: "right",
        showgrid: false,
        zeroline: false,
      },
      shapes: signalShapes,
      annotations: signalAnnotations,
      legend: { orientation: "h", x: 0, y: -0.17, font: { size: 12 } },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderShadowEquityChart(elementId, shadowBacktest) {
  const shadowCurve = shadowBacktest?.shadow_equity_curve || [];
  const benchmarkCurve = shadowBacktest?.benchmark_equity_curve || [];
  const x = shadowCurve.map((item) => toIsoDate(item.date));
  const shadow = shadowCurve.map((item) => item.value);
  const benchmarkByDate = new Map(benchmarkCurve.map((item) => [item.date, item.value]));
  const benchmark = shadowCurve.map((item) => benchmarkByDate.get(item.date) ?? null);
  if (!shadowCurve.length) {
    Plotly.purge(elementId);
    return;
  }
  Plotly.react(
    elementId,
    [
      {
        type: "scatter",
        mode: "lines",
        name: "风控仓位策略",
        x,
        y: shadow,
        line: { color: "#2663eb", width: 2.3 },
        hovertemplate: "%{x}<br>风控仓位策略 %{y:.3f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "510500 基准",
        x,
        y: benchmark,
        line: { color: "#c73d3d", width: 2, dash: "dot" },
        hovertemplate: "%{x}<br>510500 %{y:.3f}<extra></extra>",
      },
    ],
    {
      ...baseLayout(360),
      margin: { l: 44, r: 14, t: 22, b: 40 },
      xaxis: { tickformat: "%Y", gridcolor: "#edf0f5" },
      yaxis: { gridcolor: "#edf0f5", zeroline: false },
      legend: { orientation: "h", x: 0, y: 1.12, font: { size: 12 } },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderEtfRotationBacktestChart(elementId, backtest) {
  const items = backtest?.equity_curve || [];
  const x = items.map((item) => toIsoDate(item.date));
  const rotation = items.map((item) => item.rotation_equity ?? null);
  const comparisonEtfs = backtest?.summary?.comparison_etfs || [
    { code: "510300.SH", label: "价值/大盘 510300 沪深300ETF" },
    { code: "510880.SH", label: "红利/低波 510880 红利ETF" },
    { code: "510500.SH", label: "中小盘 510500 中证500ETF" },
    { code: "159915.SZ", label: "成长/科技 159915 创业板ETF" },
  ];
  const benchmarkColors = ["#c69214", "#c73d3d", "#697386", "#7c3aed"];
  const benchmarkTraces = comparisonEtfs.map((benchmark, index) => {
    const key = String(benchmark.code || "").split(".")[0];
    const equityKey = `benchmark_${key}_equity`;
    const label = benchmark.label || benchmark.code || key;
    return {
      type: "scatter",
      mode: "lines",
      name: label,
      x,
      y: items.map((item) => item[equityKey] ?? null),
      line: { color: benchmarkColors[index % benchmarkColors.length], width: 1.8, dash: index === 0 ? "dot" : "solid" },
      hovertemplate: `%{x}<br>${label} %{y:.3f}<extra></extra>`,
    };
  });
  const statusBandTrace = {
    type: "heatmap",
    name: "市场状态色带",
    x,
    y: ["预测状态", "回看确认"],
    z: [
      items.map((item) => STATUS_BAND_VALUES[item.model_regime || item.regime] ?? STATUS_BAND_VALUES.transition),
      items.map((item) => STATUS_BAND_VALUES[item.hindsight_regime || item.model_regime || item.regime] ?? STATUS_BAND_VALUES.transition),
    ],
    customdata: [
      items.map((item) => regimeLabel(item.model_regime || item.regime)),
      items.map((item) => regimeLabel(item.hindsight_regime || item.model_regime || item.regime)),
    ],
    xaxis: "x",
    yaxis: "y2",
    zmin: 0,
    zmax: 3,
    colorscale: [
      [0, STATUS_BAND_COLORS.bull],
      [0.1666, STATUS_BAND_COLORS.bull],
      [0.1667, STATUS_BAND_COLORS.bear],
      [0.5, STATUS_BAND_COLORS.bear],
      [0.5001, STATUS_BAND_COLORS.range],
      [0.8333, STATUS_BAND_COLORS.range],
      [0.8334, STATUS_BAND_COLORS.transition],
      [1, STATUS_BAND_COLORS.transition],
    ],
    showscale: false,
    hovertemplate: "%{x}<br>%{y}: %{customdata}<extra></extra>",
  };
  const statusLegendTraces = [
    ["牛市", STATUS_BAND_COLORS.bull],
    ["熊市", STATUS_BAND_COLORS.bear],
    ["震荡", STATUS_BAND_COLORS.range],
    ["过渡", STATUS_BAND_COLORS.transition],
  ].map(([name, color]) => ({
    type: "scatter",
    mode: "markers",
    name,
    x: [null],
    y: [null],
    marker: { color, size: 9, symbol: "square" },
    hoverinfo: "skip",
  }));
  Plotly.react(
    elementId,
    [
      {
        type: "scatter",
        mode: "lines",
        name: "轮动组合",
        x,
        y: rotation,
        line: { color: "#2663eb", width: 2.4 },
        hovertemplate: "%{x}<br>轮动 %{y:.3f}<extra></extra>",
      },
      ...benchmarkTraces,
      statusBandTrace,
      ...statusLegendTraces,
    ],
    {
      ...baseLayout(470),
      dragmode: "zoom",
      hovermode: "closest",
      hoverdistance: 80,
      spikedistance: -1,
      margin: { l: 72, r: 18, t: 74, b: 46 },
      xaxis: {
        tickformat: "%Y",
        gridcolor: "#edf0f5",
        anchor: "y2",
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis: {
        domain: [0.2, 1],
        gridcolor: "#edf0f5",
        zeroline: false,
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis2: {
        domain: [0, 0.13],
        fixedrange: true,
        showgrid: false,
        zeroline: false,
        tickfont: { size: 11, color: "#697386" },
      },
      legend: { orientation: "h", x: 0, y: 1.26, font: { size: 11 } },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderMacroStyleEtfBacktestChart(elementId, backtest) {
  const items = backtest?.equity_curve || [];
  if (!items.length) {
    Plotly.purge(elementId);
    return;
  }
  const x = items.map((item) => toIsoDate(item.date));
  const statusBandTrace = {
    type: "heatmap",
    name: "状态对比色带",
    x,
    y: ["M2.1 宏观", "回看确认"],
    z: [
      items.map((item) => STATUS_BAND_VALUES[item.macro_regime] ?? STATUS_BAND_VALUES.transition),
      items.map((item) => STATUS_BAND_VALUES[item.hindsight_regime || item.model_regime || item.macro_regime] ?? STATUS_BAND_VALUES.transition),
    ],
    customdata: [
      items.map((item) => regimeLabel(item.macro_regime)),
      items.map((item) => regimeLabel(item.hindsight_regime || item.model_regime || item.macro_regime)),
    ],
    xaxis: "x",
    yaxis: "y2",
    zmin: 0,
    zmax: 3,
    colorscale: [
      [0, STATUS_BAND_COLORS.bull],
      [0.1666, STATUS_BAND_COLORS.bull],
      [0.1667, STATUS_BAND_COLORS.bear],
      [0.5, STATUS_BAND_COLORS.bear],
      [0.5001, STATUS_BAND_COLORS.range],
      [0.8333, STATUS_BAND_COLORS.range],
      [0.8334, STATUS_BAND_COLORS.transition],
      [1, STATUS_BAND_COLORS.transition],
    ],
    showscale: false,
    hovertemplate: "%{x}<br>%{y}: %{customdata}<extra></extra>",
  };
  const statusLegendTraces = [
    ["牛市", STATUS_BAND_COLORS.bull],
    ["熊市", STATUS_BAND_COLORS.bear],
    ["修复/震荡", STATUS_BAND_COLORS.range],
    ["收缩/过渡", STATUS_BAND_COLORS.transition],
  ].map(([name, color]) => ({
    type: "scatter",
    mode: "markers",
    name,
    x: [null],
    y: [null],
    marker: { color, size: 9, symbol: "square" },
    hoverinfo: "skip",
  }));
  Plotly.react(
    elementId,
    [
      {
        type: "scatter",
        mode: "lines",
        name: "M2.1 分层组合",
        x,
        y: items.map((item) => item.hierarchical_equity ?? null),
        line: { color: "#0f766e", width: 2.5 },
        hovertemplate: "%{x}<br>M2.1 %{y:.3f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "当前 A1 轮动",
        x,
        y: items.map((item) => item.current_a1_equity ?? null),
        line: { color: "#2663eb", width: 2, dash: "dot" },
        hovertemplate: "%{x}<br>A1 %{y:.3f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "510300",
        x,
        y: items.map((item) => item.benchmark_510300_equity ?? null),
        line: { color: "#c69214", width: 1.8, dash: "dot" },
        hovertemplate: "%{x}<br>510300 %{y:.3f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "510500",
        x,
        y: items.map((item) => item.benchmark_510500_equity ?? null),
        line: { color: "#c73d3d", width: 1.8 },
        hovertemplate: "%{x}<br>510500 %{y:.3f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "等权 ETF",
        x,
        y: items.map((item) => item.equal_weight_basket_equity ?? null),
        line: { color: "#64748b", width: 1.8 },
        hovertemplate: "%{x}<br>等权 ETF %{y:.3f}<extra></extra>",
      },
      statusBandTrace,
      ...statusLegendTraces,
    ],
    {
      ...baseLayout(470),
      dragmode: "zoom",
      hovermode: "closest",
      hoverdistance: 80,
      spikedistance: -1,
      margin: { l: 72, r: 18, t: 74, b: 46 },
      xaxis: {
        tickformat: "%Y",
        hoverformat: "%Y-%m-%d",
        gridcolor: "#edf0f5",
        anchor: "y2",
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis: {
        domain: [0.2, 1],
        gridcolor: "#edf0f5",
        zeroline: false,
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis2: {
        domain: [0, 0.13],
        fixedrange: true,
        showgrid: false,
        zeroline: false,
        tickfont: { size: 11, color: "#697386" },
      },
      legend: { orientation: "h", x: 0, y: 1.26, font: { size: 11 } },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderStrategyBacktestChart(elementId, backtest, options = {}) {
  const items = backtest?.equity_curve || [];
  if (!items.length) {
    Plotly.purge(elementId);
    return;
  }
  const isFreeCashFlowTrend = backtest?.metadata?.indicator === "free_cash_flow_trend_channel";
  const isFreeCashFlowRebound = backtest?.metadata?.indicator === "free_cash_flow_drawdown_rebound";
  const isFreeCashFlowBuyHold = backtest?.metadata?.indicator === "free_cash_flow_buy_hold";
  const isFreeCashFlowPairDynamic = backtest?.metadata?.indicator === "free_cash_flow_chinext_dynamic";
  const isFreeCashFlowPairReversion = backtest?.metadata?.indicator === "free_cash_flow_chinext_reversion";
  const isFreeCashFlowPairBalancedReversion =
    backtest?.metadata?.indicator === "free_cash_flow_chinext_balanced_reversion";
  const isFreeCashFlowMaDeviation = backtest?.metadata?.indicator === "free_cash_flow_ma_deviation";
  const isFreeCashFlowDualMa = backtest?.metadata?.indicator === "free_cash_flow_dual_ma_crossover";
  const dualMaDefaultParameter = backtest?.summary?.default_parameter || {};
  const dualMaFastLabel = dualMaDefaultParameter.fast_window ? `MA${dualMaDefaultParameter.fast_window}` : "快线";
  const dualMaSlowLabel = dualMaDefaultParameter.slow_window ? `MA${dualMaDefaultParameter.slow_window}` : "慢线";
  const hasCycleBackground =
    isFreeCashFlowBuyHold || isFreeCashFlowPairDynamic || isFreeCashFlowPairReversion || isFreeCashFlowPairBalancedReversion;
  const isFreeCashFlowIndexStrategy =
    isFreeCashFlowTrend ||
    isFreeCashFlowRebound ||
    isFreeCashFlowBuyHold ||
    isFreeCashFlowPairDynamic ||
    isFreeCashFlowPairReversion ||
    isFreeCashFlowPairBalancedReversion ||
    isFreeCashFlowMaDeviation ||
    isFreeCashFlowDualMa;
  const x = items.map((item) => toIsoDate(item.date));
  const visibleBenchmarkCodes = Array.isArray(options.visibleBenchmarkCodes)
    ? new Set(options.visibleBenchmarkCodes)
    : null;
  const comparisonAssets = (backtest?.summary?.comparison_assets || []).filter((asset) =>
    visibleBenchmarkCodes ? visibleBenchmarkCodes.has(asset.code) : true
  );
  const primaryStrategyCode = backtest?.metadata?.index_code || "480092.CNI";
  const traceStyleByCode = {
    "000905.SH": { color: "#f97316", dash: "dot", width: 2.0 },
    "h00300.CSI": { color: "#dc2626", dash: "dot", width: 1.9 },
    "h00905.CSI": { color: "#f97316", dash: "dot", width: 1.9 },
    "399606.SZ": { color: "#7c3aed", dash: "dot", width: 1.9 },
    "h20269.CSI": { color: "#16a34a", dash: "dot", width: 1.9 },
    "510300.SH": { color: "#dc2626", dash: "solid" },
    "510880.SH": { color: "#16a34a", dash: "solid" },
    "512890.SH": { color: "#059669", dash: "dash" },
    "510500.SH": { color: "#f59e0b", dash: "solid" },
    "159915.SZ": { color: "#7c3aed", dash: "solid" },
    "511880.SH": { color: "#64748b", dash: "dot" },
    "511260.SH": { color: "#0891b2", dash: "solid" },
    "511010.SH": { color: "#0d9488", dash: "dash" },
    "518880.SH": { color: "#ca8a04", dash: "solid" },
    "480092.CNI": { color: "#111827", dash: "dashdot", width: 2.1 },
    "free-cash-flow-chinext-dynamic": { color: "#2563eb", dash: "solid", width: 2.7 },
    "free-cash-flow-chinext-reversion": { color: "#0f766e", dash: "solid", width: 2.7 },
    "free-cash-flow-chinext-balanced-reversion": { color: "#be123c", dash: "solid", width: 2.7 },
    "free-cash-flow-ma-deviation": { color: "#0f766e", dash: "solid", width: 2.7 },
    fcf_ma_best_full_sample: { color: "#be123c", dash: "longdash", width: 2.2 },
    "free-cash-flow-dual-ma-crossover": { color: "#2563eb", dash: "solid", width: 2.7 },
    fcf_peak_drawdown10_clear_20_full: { color: "#ea580c", dash: "solid", width: 2.25 },
    fcf_dual_ma_best_full_sample: { color: "#be123c", dash: "longdash", width: 2.2 },
    fcf_chinext_fixed_equal: { color: "#9333ea", dash: "longdash", width: 2.1 },
    checked_equal_weight: { color: "#0f172a", dash: "longdash", width: 2.5 },
    checked_risk_parity: { color: "#0891b2", dash: "dashdot", width: 2.5 },
    commodity_basket: { color: "#be123c", dash: "dash" },
    equal_weight: { color: "#111827", dash: "dashdot", width: 2.2 },
  };
  const fallbackColors = ["#c73d3d", "#17885b", "#c69214", "#64748b", "#7c3aed", "#0f766e"];
  const indicatorItems = backtest?.indicator_curve || [];
  const indicatorByDate = new Map(indicatorItems.map((item) => [toIsoDate(item.date), item]));
  const signalItems = backtest?.signals || [];
  const signalGroups = isFreeCashFlowDualMa
    ? [
        {
          name: "金叉买入",
          color: "#16a34a",
          symbol: "triangle-up",
          items: signalItems.filter((item) => item.strategy_signal === "fcf_dual_ma_golden_cross_buy"),
        },
        {
          name: "死叉卖出",
          color: "#dc2626",
          symbol: "triangle-down",
          items: signalItems.filter((item) => item.strategy_signal === "fcf_dual_ma_death_cross_sell"),
        },
      ]
    : isFreeCashFlowMaDeviation
    ? [
        {
          name: "高位减仓",
          color: "#dc2626",
          symbol: "triangle-down",
          items: signalItems.filter((item) => item.strategy_signal === "fcf_ma_deviation_reduce"),
        },
        {
          name: "低位买回",
          color: "#16a34a",
          symbol: "triangle-up",
          items: signalItems.filter((item) => item.strategy_signal === "fcf_ma_deviation_buy"),
        },
      ]
    : [
        {
          name: "上轨卖出",
          color: "#dc2626",
          symbol: "triangle-down",
          items: signalItems.filter((item) =>
            ["fcf_channel_half_reduce", "fcf_channel_full_exit"].includes(item.strategy_signal)
          ),
        },
        {
          name: "下轨买入",
          color: "#16a34a",
          symbol: "triangle-up",
          items: signalItems.filter((item) => item.strategy_signal === "fcf_channel_full_buy"),
        },
      ];
  const signalTraces =
    isFreeCashFlowTrend || isFreeCashFlowMaDeviation || isFreeCashFlowDualMa
      ? signalGroups
          .filter((group) => group.items.length)
          .map((group) => ({
            type: "scatter",
            mode: "markers",
            name: group.name,
            x: group.items.map((item) => toIsoDate(item.date)),
            y: group.items.map((item) => indicatorByDate.get(toIsoDate(item.date))?.index_equity ?? null),
            customdata: group.items.map((item) => {
              const targetWeights = item.target_weights || {};
              const equityWeight = targetWeights[primaryStrategyCode];
              const cashWeight = targetWeights.CASH || 0;
              const reason = item.rebalance_reason?.detail || "";
              return [
                typeof equityWeight === "number" ? `${(equityWeight * 100).toFixed(0)}%` : "--",
                typeof cashWeight === "number" ? `${(cashWeight * 100).toFixed(0)}%` : "--",
                reason,
              ];
            }),
            marker: {
              color: group.color,
              size: 9,
              symbol: group.symbol,
              line: { color: "#ffffff", width: 1.2 },
            },
            hovertemplate:
              "%{x}<br>" +
              `${group.name}<br>` +
              "指数位置 %{y:.3f}<br>" +
              "目标权益 %{customdata[0]} / 现金 %{customdata[1]}<br>" +
              "%{customdata[2]}<extra></extra>",
          }))
      : [];
  const buildChannelBandTrace = (name, lowerKey, upperKey, color) => {
    const points = x
      .map((date) => {
        const item = indicatorByDate.get(date);
        return {
          date,
          lower: item?.[lowerKey],
          upper: item?.[upperKey],
        };
      })
      .filter((point) => Number.isFinite(point.lower) && Number.isFinite(point.upper));
    if (!points.length) return null;
    const reversePoints = [...points].reverse();
    return {
      type: "scatter",
      mode: "lines",
      name,
      x: [...points.map((point) => point.date), ...reversePoints.map((point) => point.date)],
      y: [...points.map((point) => point.lower), ...reversePoints.map((point) => point.upper)],
      fill: "toself",
      fillcolor: color,
      line: { color: "rgba(255,255,255,0)", width: 0 },
      hoverinfo: "skip",
    };
  };
  const channelBandTraces = isFreeCashFlowTrend
    ? [
        buildChannelBandTrace("上轨卖出区间", "upper_zone_equity", "upper_equity", "rgba(220, 38, 38, 0.12)"),
        buildChannelBandTrace("下轨买入区间", "lower_equity", "lower_zone_equity", "rgba(22, 163, 74, 0.12)"),
      ].filter(Boolean)
    : [];
  const maDeviationBandTraces = isFreeCashFlowMaDeviation
    ? [buildChannelBandTrace("MA120 ±5% 偏离带", "lower_band_equity", "upper_band_equity", "rgba(15, 118, 110, 0.08)")].filter(Boolean)
    : [];
  const comparisonTraces = comparisonAssets.slice(0, 6).map((asset, index) => {
    const key = asset.code === "equal_weight" ? "equal_weight" : `benchmark_${String(asset.code || "").split(".")[0]}`;
    const equityKey = asset.equity_key || `${key}_equity`;
    const label = asset.label || asset.code || key;
    const style = traceStyleByCode[asset.code] || { color: fallbackColors[index % fallbackColors.length], dash: "solid" };
    return {
      type: "scatter",
      mode: "lines",
      name: label,
      x,
      y: items.map((item) => item[equityKey] ?? null),
      line: { color: style.color, width: style.width || 1.8, dash: style.dash },
      hovertemplate: `%{x}<br>${label} %{y:.3f}<extra></extra>`,
    };
  });
  const reboundVariantColors = ["#2563eb", "#16a34a", "#f59e0b", "#7c3aed", "#dc2626"];
  const bestVariant = backtest?.summary?.best_variant?.variant;
  const reboundVariantTraces = isFreeCashFlowRebound
    ? (backtest?.summary?.variants || []).map((variant, index) => {
        const isBest = variant.variant === bestVariant;
        const label = variant.label || variant.variant || `n${index + 1}`;
        return {
          type: "scatter",
          mode: "lines",
          name: `${label}${isBest ? " 代表" : ""}`,
          x,
          y: items.map((item) => item[variant.equity_key] ?? null),
          line: {
            color: reboundVariantColors[index % reboundVariantColors.length],
            width: isBest ? 2.9 : 1.8,
            dash: isBest ? "solid" : "dot",
          },
          hovertemplate: `%{x}<br>${label} %{y:.3f}<extra></extra>`,
        };
      })
    : [];
  const cycleBlockShapes = hasCycleBackground
    ? buildCycleBlockShapes(backtest?.cycle_blocks || [], x[0], x[x.length - 1])
    : [];
  const backgroundTraces =
    hasCycleBackground && items.some((item) => typeof item.shanghai_equity === "number")
      ? [
          {
            type: "scatter",
            mode: "lines",
            name: "上证指数背景",
            x,
            y: items.map((item) => item.shanghai_equity ?? null),
            line: { color: "rgba(71, 85, 105, 0.42)", width: 1.6, dash: "dash" },
            hovertemplate: "%{x}<br>上证归一 %{y:.3f}<extra></extra>",
          },
        ]
      : [];
  const reversionIndicatorTraces = isFreeCashFlowPairReversion || isFreeCashFlowPairBalancedReversion
    ? [
        {
          type: "scatter",
          mode: "lines",
          name: "相对比值 Z-score",
          x,
          y: items.map((item) => item.relative_zscore ?? null),
          yaxis: "y2",
          line: { color: "#f97316", width: 1.8, dash: "dot" },
          hovertemplate: "%{x}<br>Z-score %{y:.2f}<extra></extra>",
        },
      ]
    : [];
  Plotly.react(
    elementId,
    [
      ...backgroundTraces,
      ...(isFreeCashFlowRebound
        ? reboundVariantTraces
        : [
            {
              type: "scatter",
              mode: "lines",
              name: backtest?.summary?.short_name || "策略组合",
              x,
              y: items.map((item) => item.strategy_equity ?? null),
              line: { color: "#2663eb", width: 2.6 },
              hovertemplate: "%{x}<br>策略 %{y:.3f}<extra></extra>",
            },
          ]),
      ...comparisonTraces,
      ...reversionIndicatorTraces,
      ...(backtest?.metadata?.indicator === "equal_weight_ma_reversion"
        ? [
            {
              type: "scatter",
              mode: "lines",
              name: "等权ETF MA250",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.ma_equity ?? null),
              line: { color: "#9ca3af", width: 1.8, dash: "dash" },
              hovertemplate: "%{x}<br>MA250 %{y:.3f}<extra></extra>",
            },
          ]
        : []),
      ...channelBandTraces,
      ...maDeviationBandTraces,
      ...(isFreeCashFlowTrend
        ? [
            {
              type: "scatter",
              mode: "lines",
              name: "上轨：2026前98.5%残差",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.upper_equity ?? null),
              line: { color: "#ef4444", width: 2.1 },
              hovertemplate: "%{x}<br>上轨 %{y:.3f}<extra></extra>",
            },
            {
              type: "scatter",
              mode: "lines",
              name: "中轨",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.mid_equity ?? null),
              line: { color: "#718096", width: 1.8, dash: "dash" },
              hovertemplate: "%{x}<br>中轨 %{y:.3f}<extra></extra>",
            },
            {
              type: "scatter",
              mode: "lines",
              name: "下轨：主要低点拟合",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.lower_equity ?? null),
              line: { color: "#16a34a", width: 2.1 },
              hovertemplate: "%{x}<br>下轨 %{y:.3f}<extra></extra>",
            },
          ]
        : []),
      ...(isFreeCashFlowMaDeviation
        ? [
            {
              type: "scatter",
              mode: "lines",
              name: "MA120",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.ma_equity ?? null),
              line: { color: "#64748b", width: 1.9, dash: "dash" },
              hovertemplate: "%{x}<br>MA120 %{y:.3f}<extra></extra>",
            },
            {
              type: "scatter",
              mode: "lines",
              name: "上偏离带 +5%",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.upper_band_equity ?? null),
              line: { color: "#dc2626", width: 1.8, dash: "dot" },
              hovertemplate: "%{x}<br>上偏离带 %{y:.3f}<extra></extra>",
            },
            {
              type: "scatter",
              mode: "lines",
              name: "下偏离带 -5%",
              x,
              y: x.map((date) => indicatorByDate.get(date)?.lower_band_equity ?? null),
              line: { color: "#16a34a", width: 1.8, dash: "dot" },
              hovertemplate: "%{x}<br>下偏离带 %{y:.3f}<extra></extra>",
            },
          ]
        : []),
      ...(isFreeCashFlowDualMa
        ? [
            {
              type: "scatter",
              mode: "lines",
              name: `快线 ${dualMaFastLabel}`,
              x,
              y: x.map((date) => indicatorByDate.get(date)?.fast_ma_equity ?? null),
              line: { color: "#f97316", width: 1.9, dash: "dash" },
              hovertemplate: "%{x}<br>快线 %{y:.3f}<extra></extra>",
            },
            {
              type: "scatter",
              mode: "lines",
              name: `慢线 ${dualMaSlowLabel}`,
              x,
              y: x.map((date) => indicatorByDate.get(date)?.slow_ma_equity ?? null),
              line: { color: "#64748b", width: 1.9, dash: "dot" },
              hovertemplate: "%{x}<br>慢线 %{y:.3f}<extra></extra>",
            },
          ]
        : []),
      ...signalTraces,
    ],
    {
      ...baseLayout(500),
      dragmode: "zoom",
      hovermode: "closest",
      hoverdistance: 80,
      spikedistance: -1,
      margin: { l: 62, r: 18, t: 68, b: 46 },
      shapes: cycleBlockShapes,
      xaxis: {
        range: hasCycleBackground ? [x[0], x[x.length - 1]] : undefined,
        tickformat: "%Y",
        hoverformat: "%Y-%m-%d",
        gridcolor: "#edf0f5",
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis: {
        type: isFreeCashFlowIndexStrategy ? "log" : undefined,
        gridcolor: "#edf0f5",
        zeroline: false,
        showspikes: true,
        spikecolor: "#4b5563",
        spikedash: "solid",
        spikemode: "across",
        spikesnap: "cursor",
        spikethickness: 1,
      },
      yaxis2: isFreeCashFlowPairReversion || isFreeCashFlowPairBalancedReversion
        ? {
            anchor: "x",
            title: "Z-score",
            overlaying: "y",
            side: "right",
            zeroline: true,
            zerolinecolor: "rgba(249, 115, 22, 0.45)",
            showgrid: false,
            tickfont: { size: 10, color: "#f97316" },
          }
        : { anchor: "x", overlaying: "y", side: "right", visible: false, showgrid: false },
      legend: { orientation: "h", x: 0, y: 1.22, font: { size: 11 } },
    },
    { responsive: true, displayModeBar: false }
  );
}

function buildCycleBlockShapes(blocks, fallbackStart, fallbackEnd) {
  const normalizeDate = (value, fallback) => {
    const text = toIsoDate(value);
    return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : fallback;
  };
  const startBound = normalizeDate(fallbackStart, fallbackStart);
  const endBound = normalizeDate(fallbackEnd, fallbackEnd);
  return (blocks || [])
    .filter((block) => ["bull", "bear"].includes(block.state))
    .map((block) => {
      const blockStart = normalizeDate(block.start_date, startBound);
      const blockEnd = normalizeDate(block.end_date, endBound);
      const x0 = blockStart < startBound ? startBound : blockStart;
      const x1 = blockEnd > endBound ? endBound : blockEnd;
      if (x1 < startBound || x0 > endBound || x1 < x0) return null;
      return {
        type: "rect",
        xref: "x",
        yref: "paper",
        x0,
        x1,
        y0: 0,
        y1: 1,
        fillcolor: block.state === "bull" ? "rgba(199, 61, 61, 0.085)" : "rgba(23, 136, 91, 0.085)",
        line: { width: 0 },
        layer: "below",
      };
    })
    .filter(Boolean);
}

function buildRegimeShapes(items, options = {}) {
  const y0 = options.y0 ?? 0;
  const y1 = options.y1 ?? 1;
  const xEnd = options.xEnd || null;
  const ranges = [];
  for (const item of items) {
    const last = ranges[ranges.length - 1];
    if (last && last.regime === item.regime) {
      last.end = item.as_of;
    } else {
      ranges.push({ regime: item.regime, start: item.as_of, end: item.as_of });
    }
  }
  return ranges.map((range, index) => {
    const nextRange = ranges[index + 1];
    return {
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: toIsoDate(range.start),
      x1: toIsoDate(nextRange?.start || xEnd || range.end),
      y0,
      y1,
      fillcolor: SHADE_COLORS[range.regime] || SHADE_COLORS.range,
      line: { width: 0 },
      layer: "below",
    };
  });
}

function forecastWindowShape(x0, x1) {
  return {
    type: "rect",
    xref: "x",
    yref: "paper",
    x0,
    x1,
    y0: 0,
    y1: 1,
    fillcolor: "rgba(38, 99, 235, 0.06)",
    line: { width: 0 },
    layer: "below",
  };
}

function markerLine(x, color, label, yPosition) {
  return {
    shape: {
      type: "line",
      xref: "x",
      yref: "paper",
      x0: x,
      x1: x,
      y0: 0,
      y1: 1,
      line: { color, width: 2, dash: "dash" },
      layer: "above",
    },
    annotation: {
      x,
      y: yPosition,
      xref: "x",
      yref: "paper",
      text: label,
      showarrow: false,
      bgcolor: "rgba(255,255,255,0.88)",
      bordercolor: color,
      borderwidth: 1,
      font: { color, size: 12 },
    },
  };
}

function renderCycleTrackChart(elementId, track) {
  const items = track.items || [];
  const forecast = track.forecast || {};
  const paths = forecast.paths || [];
  const x = items.map((item) => toIsoDate(item.as_of));
  const close = items.map((item) => item.index?.close ?? null);
  const ma120 = items.map((item) => item.index?.ma120 ?? null);
  const ma250 = items.map((item) => item.index?.ma250 ?? null);
  const latest = items[items.length - 1];
  const latestDate = toIsoDate(latest?.as_of);
  const latestClose = latest?.index?.close ?? null;
  const futureX = paths.map((path) => toIsoDate(path.as_of));
  const futureEnd = futureX[futureX.length - 1];
  const projectionX = latestDate ? [latestDate, ...futureX] : futureX;
  const projectionTrace = (name, key, color) => ({
    type: "scatter",
    mode: "lines+markers",
    name,
    x: projectionX,
    y: latestClose === null ? paths.map((path) => path[key]) : [latestClose, ...paths.map((path) => path[key])],
    line: { color, width: 2, dash: "dash" },
    marker: { size: 6, color },
    hovertemplate: `%{x}<br>${name} %{y:.2f}<extra></extra>`,
  });
  const markers = [];
  if (track.cycle?.start_date) {
    markers.push(markerLine(toIsoDate(track.cycle.start_date), "#17201b", "本轮开始", 1.03));
  }
  if (latestDate) {
    markers.push(markerLine(latestDate, "#2663eb", "当前", 0.93));
  }
  const shapes = [
    ...buildRegimeShapes(items, { y0: 0, y1: 0.12, xEnd: latestDate }),
    ...(latestDate && futureEnd ? [forecastWindowShape(latestDate, futureEnd)] : []),
    ...markers.map((marker) => marker.shape),
  ];
  Plotly.react(
    elementId,
    [
      {
        type: "scatter",
        mode: "lines",
        name: "上证收盘",
        x,
        y: close,
        line: { color: "#2663eb", width: 2.6 },
        hovertemplate: "%{x}<br>收盘 %{y:.2f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "MA120",
        x,
        y: ma120,
        line: { color: "#c69214", width: 1.8, dash: "dot" },
        hovertemplate: "%{x}<br>MA120 %{y:.2f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "MA250",
        x,
        y: ma250,
        line: { color: "#697386", width: 1.8, dash: "dash" },
        hovertemplate: "%{x}<br>MA250 %{y:.2f}<extra></extra>",
      },
      ...(paths.length
        ? [
            projectionTrace("谨慎", "cautious", "#17885b"),
            projectionTrace("中性", "neutral", "#697386"),
            projectionTrace("乐观", "optimistic", "#c73d3d"),
          ]
        : []),
    ],
    {
      ...baseLayout(440),
      margin: { l: 48, r: 18, t: 24, b: 44 },
      shapes,
      annotations: [
        ...markers.map((marker) => marker.annotation),
        {
          x: x[0],
          y: 0.06,
          xref: "x",
          yref: "paper",
          text: "状态带",
          showarrow: false,
          xanchor: "left",
          font: { color: "#667085", size: 12 },
        },
      ],
      xaxis: { tickformat: "%Y-%m", gridcolor: "#edf0f5", range: futureEnd ? [x[0], futureEnd] : undefined },
      yaxis: { gridcolor: "#edf0f5", zeroline: false },
      legend: { orientation: "h", x: 0, y: 1.12 },
    },
    { responsive: true, displayModeBar: false }
  );
}

function renderIndexChart(elementId, items, phase, blocks = []) {
  const x = items.map((item) => toIsoDate(item.as_of));
  const close = items.map((item) => item.index?.close ?? null);
  const ma120 = items.map((item) => item.index?.ma120 ?? null);
  const ma250 = items.map((item) => item.index?.ma250 ?? null);
  const bullBlocks = blocks.filter((block) => block.major && block.state === "bull");
  const markers = bullBlocks.map((block, index) =>
    markerLine(toIsoDate(block.start_date), REGIME_COLORS.bull, block.short_label || `${String(block.start_date).slice(0, 4)} 牛市`, index % 2 ? 0.95 : 1.05)
  );
  if (phase?.currentDate) {
    markers.push(markerLine(toIsoDate(phase.currentDate), "#2663eb", "当前", 0.93));
  }
  Plotly.react(
    elementId,
    [
      {
        type: "scatter",
        mode: "lines",
        name: "上证收盘",
        x,
        y: close,
        line: { color: "#2663eb", width: 2.5 },
        hovertemplate: "%{x}<br>close %{y:.2f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "MA120",
        x,
        y: ma120,
        line: { color: "#c69214", width: 2, dash: "dot" },
        hovertemplate: "%{x}<br>MA120 %{y:.2f}<extra></extra>",
      },
      {
        type: "scatter",
        mode: "lines",
        name: "MA250",
        x,
        y: ma250,
        line: { color: "#697386", width: 2, dash: "dash" },
        hovertemplate: "%{x}<br>MA250 %{y:.2f}<extra></extra>",
      },
    ],
    {
      ...baseLayout(390),
      margin: { l: 48, r: 18, t: 34, b: 44 },
      shapes: [...buildRegimeShapes(items), ...markers.map((marker) => marker.shape)],
      annotations: markers.map((marker) => marker.annotation),
      xaxis: { tickformat: "%Y", gridcolor: "#edf0f5" },
      yaxis: { gridcolor: "#edf0f5", zeroline: false },
      legend: { orientation: "h", x: 0, y: 1.12 },
    },
    { responsive: true, displayModeBar: false }
  );
}
