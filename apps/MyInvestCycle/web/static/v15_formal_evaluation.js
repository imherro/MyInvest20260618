const percent = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : "--";
const decimal = (value) => Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "--";
const isoDate = (value) => {
  const text = String(value || "");
  return /^\d{8}$/.test(text) ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}` : text || "--";
};
const setText = (id, value) => {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
};

function metricRow(label, metrics, alpha = null, emphasized = false) {
  return `<tr${emphasized ? ' class="is-primary"' : ""}>
    <th>${label}</th>
    <td>${percent(metrics.total_return)}</td>
    <td>${percent(metrics.CAGR)}</td>
    <td>${alpha === null ? "--" : percent(alpha)}</td>
    <td>${percent(metrics.max_drawdown)}</td>
    <td>${decimal(metrics.sharpe)}</td>
    <td>${decimal(metrics.calmar)}</td>
  </tr>`;
}

function renderChecks(checks) {
  const labels = {
    full_period_beats_total_return_benchmark: "全周期跑赢沪深300全收益",
    full_period_annual_alpha_positive: "全周期年化超额为正",
    full_period_max_drawdown_within_30pct: "全周期最大回撤不超过30%",
    out_of_sample_beats_total_return_benchmark: "样本外跑赢全收益基准",
    out_of_sample_beats_cash: "样本外年化跑赢2%现金",
    default_parameter_rank_in_top_three: "默认参数进入九组参数前三",
    strict_point_in_time_verified: "历史阶段通过严格时点验证",
  };
  document.getElementById("formalChecks").innerHTML = Object.entries(labels).map(([key, label]) => {
    const passed = checks[key] === true;
    return `<div class="v15-eval-check ${passed ? "is-pass" : "is-fail"}"><span>${passed ? "通过" : "未通过"}</span><strong>${label}</strong></div>`;
  }).join("");
}

function renderChart(curve) {
  const rows = Array.isArray(curve) ? curve : [];
  const dates = rows.map((row) => isoDate(row.date));
  const traces = [
    { name: "V15策略", y: rows.map((row) => row.strategy_equity), color: "#c23b32", width: 2.5 },
    { name: "沪深300全收益", y: rows.map((row) => row.csi_300_total_return_equity ?? row.csi_300_equity), color: "#2263eb", width: 2 },
    { name: "现金2%", y: rows.map((row) => row.cash_equity), color: "#737b8c", width: 1.5 },
  ].map((item) => ({ x: dates, y: item.y, type: "scatter", mode: "lines", name: item.name, line: { color: item.color, width: item.width }, hovertemplate: "%{x}<br>%{y:.3f}<extra>%{fullData.name}</extra>" }));
  Plotly.newPlot("formalEquityChart", traces, {
    margin: { l: 54, r: 18, t: 20, b: 48 },
    paper_bgcolor: "transparent", plot_bgcolor: "transparent",
    hovermode: "x unified", legend: { orientation: "h", y: 1.12 },
    xaxis: { gridcolor: "#e6e9ef", rangeslider: { visible: false } },
    yaxis: { title: "累计净值", gridcolor: "#e6e9ef" },
  }, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
}

async function loadEvaluation() {
  try {
    const [backtestResponse, robustnessResponse] = await Promise.all([
      fetch("/api/strategy-rebase/v15-macro-drawdown-backtest", { cache: "no-store" }),
      fetch("/api/strategy-rebase/v15-macro-drawdown-robustness", { cache: "no-store" }),
    ]);
    if (!backtestResponse.ok || !robustnessResponse.ok) throw new Error("正式评价数据暂不可用");
    const backtest = await backtestResponse.json();
    const robustness = await robustnessResponse.json();
    const strategy = backtest.strategy_results?.macro_drawdown_strategy || {};
    const benchmark = backtest.benchmarks?.csi_300_total_return_buy_hold || backtest.benchmarks?.csi_300_buy_hold || {};
    const cash = backtest.benchmarks?.cash_baseline || {};
    const formal = robustness.formal_evaluation || {};
    const oos = robustness.walk_forward?.combined_oos_metrics || {};
    const oosBenchmark = robustness.walk_forward?.combined_oos_csi_300_metrics || {};
    const noCost = robustness.default_cost_sensitivity?.["0"] || {};
    const formalCost = robustness.default_cost_sensitivity?.["15"] || strategy;

    const passed = formal.status === "passed";
    setText("formalVerdict", passed ? "通过" : "不通过");
    document.getElementById("formalVerdict").className = passed ? "is-pass" : "is-fail";
    setText("formalConclusion", passed ? "所有正式门槛均已满足。" : "全周期未跑赢沪深300全收益，样本外收益未跑赢现金，且历史阶段严格时点证据未通过，因此拒绝策略推进。");
    setText("evaluationPeriod", `${isoDate(backtest.summary?.start_date)} 至 ${isoDate(backtest.summary?.end_date)}`);
    document.getElementById("formalMetricsBody").innerHTML = [
      metricRow("V15宏观回撤策略", strategy, strategy.annual_alpha, true),
      metricRow("沪深300全收益", benchmark),
      metricRow("现金基准", cash),
    ].join("");
    setText("oosCagr", percent(oos.CAGR));
    setText("oosBenchmarkCagr", percent(oosBenchmark.CAGR));
    setText("oosAlpha", percent(oos.annual_alpha));
    setText("oosDrawdown", percent(oos.max_drawdown));
    setText("oosCalmar", decimal(oos.calmar));
    setText("oosCost", `${robustness.summary?.walk_forward_cost_bps ?? 15}bp`);
    setText("oosConclusion", `样本外策略虽跑赢同期全收益基准，但年化仅 ${percent(oos.CAGR)}，低于2%现金假设，不能据此推进。`);
    setText("noCostCagr", percent(noCost.CAGR));
    setText("costDrag", percent(Number(noCost.CAGR || 0) - Number(formalCost.CAGR || 0)));
    setText("averageExposure", percent(formalCost.average_exposure));
    setText("annualTurnover", `${Number(formalCost.annualized_turnover || 0).toFixed(2)}倍`);
    setText("drawdownImprovement", percent(Math.abs(Number(benchmark.max_drawdown || 0)) - Math.abs(Number(strategy.max_drawdown || 0))));
    renderChecks(formal.checks || {});
    renderChart(backtest.equity_curve || []);
  } catch (error) {
    setText("pageError", error instanceof Error ? error.message : "正式评价加载失败");
  }
}

loadEvaluation();
