function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value == null || value === "" ? "--" : String(value);
}

function fmtPercent(value) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function fmtNumber(value, digits = 2) {
  if (typeof value !== "number") return "--";
  return value.toFixed(digits);
}

function toIsoDate(value) {
  const text = String(value || "");
  return text.length === 8 ? `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}` : text || "--";
}

async function getJson(url) {
  const requestUrl = new URL(url, window.location.origin);
  requestUrl.searchParams.set("_t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderChecks(payload) {
  const validation = payload.validation || {};
  const metadata = payload.metadata || {};
  const checks = [
    ["Walk-forward T+1", validation.walk_forward_t_plus_1],
    ["只是假设暴露验证", validation.uses_hypothetical_exposure_only],
    ["无交易执行", metadata.no_trade_execution],
    ["无下单", metadata.no_order_generation],
    ["无券商连接", metadata.no_broker_connection],
    ["快照错误数", validation.snapshot_error_count === 0],
  ];
  const target = document.getElementById("validationChecks");
  if (!target) return;
  target.innerHTML = checks
    .map(([label, ok]) => `<div class="v2-list-row"><span>${label}</span><strong>${ok ? "通过" : "检查"}</strong></div>`)
    .join("");
}

function renderChart(curve) {
  const chart = document.getElementById("v2ValidationChart");
  if (!chart || !window.Plotly) return;
  const dates = curve.map((row) => toIsoDate(row.date));
  const traces = [
    ["V2 配置意图", "v2_equity", "#2563eb"],
    ["510300", "benchmark_510300_equity", "#dc2626"],
    ["510500", "benchmark_510500_equity", "#ef4444"],
    ["旧 S1.1", "old_s1_equity", "#64748b"],
    ["M2.1", "m2_macro_style_equity", "#059669"],
  ].map(([name, key, color]) => ({
    type: "scatter",
    mode: "lines",
    name,
    x: dates,
    y: curve.map((row) => row[key]),
    line: { color, width: name === "V2 配置意图" ? 3 : 2 },
    hovertemplate: "%{x}<br>%{y:.3f}<extra>" + name + "</extra>",
  }));
  Plotly.newPlot(
    chart,
    traces,
    {
      margin: { l: 48, r: 20, t: 12, b: 40 },
      hovermode: "x unified",
      legend: { orientation: "h", x: 0, y: 1.12 },
      xaxis: { showgrid: false },
      yaxis: { tickformat: ".2f", gridcolor: "rgba(148, 163, 184, 0.18)" },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
    },
    { responsive: true, displayModeBar: true }
  );
}

function renderBenchmarkTable(comparison) {
  const target = document.getElementById("benchmarkRows");
  if (!target) return;
  const rows = Object.values(comparison || {});
  target.innerHTML = rows
    .map((item) => {
      const benchmark = item.benchmark || {};
      return `<tr>
        <td>${item.label || "--"}</td>
        <td>${fmtPercent(benchmark.total_return)}</td>
        <td>${fmtPercent(benchmark.annualized_return)}</td>
        <td>${fmtPercent(benchmark.max_drawdown)}</td>
        <td>${fmtPercent(item.excess_return)}</td>
        <td>${fmtPercent(item.hit_rate)}</td>
      </tr>`;
    })
    .join("");
}

function renderStateTable(attribution) {
  const target = document.getElementById("stateRows");
  if (!target) return;
  const rows = Object.entries(attribution?.allocation_structural_state || attribution?.structural_state || {});
  target.innerHTML = rows
    .map(([state, item]) => `<tr>
      <td>${state}</td>
      <td>${item.sessions ?? "--"}</td>
      <td>${fmtPercent(item.strategy_return)}</td>
      <td>${fmtPercent(item.benchmark_return)}</td>
      <td>${fmtPercent(item.alpha)}</td>
      <td>${fmtPercent(item.average_exposure)}</td>
    </tr>`)
    .join("");
}

function renderPolicySensitivity(payload) {
  const sensitivity = payload.sensitivity || {};
  const variants = sensitivity.variants || {};
  const target = document.getElementById("policyRows");
  if (target) {
    target.innerHTML = Object.values(variants)
      .map((item) => {
        const summary = item.summary || {};
        return `<tr>
          <td><strong>${item.label || item.variant_id}</strong><br><span>${item.description || ""}</span></td>
          <td>${fmtPercent(summary.v2_total_return)}</td>
          <td>${fmtPercent(summary.v2_annualized_return)}</td>
          <td>${fmtPercent(summary.v2_max_drawdown)}</td>
          <td>${fmtNumber(summary.v2_calmar)}</td>
          <td>${fmtPercent(summary.average_exposure)}</td>
          <td>${fmtPercent(summary.alpha_vs_510500)}</td>
        </tr>`;
      })
      .join("");
  }
  const best = sensitivity.best_by || {};
  setText(
    "policyBestNote",
    `年化最优：${best.annualized_return?.label || "--"}；回撤最稳：${best.max_drawdown?.label || "--"}；Calmar 最优：${best.calmar?.label || "--"}。`
  );
}

function renderCoverageAudit(payload) {
  const audit = payload.coverage_audit || {};
  const target = document.getElementById("coverageRows");
  if (target) {
    const rows = Object.entries(audit.series || {});
    target.innerHTML = rows
      .map(([name, item]) => `<div class="v2-list-row">
        <span>${name}</span>
        <strong>${item.start || "--"} - ${item.end || "--"}</strong>
      </div>`)
      .join("");
  }
  const common = audit.common_available_window || {};
  const desired = audit.desired_window || {};
  const blockers = audit.blockers || [];
  setText(
    "coverageNote",
    `目标长历史 ${toIsoDate(desired.start)} - ${toIsoDate(desired.end)}；当前共同可用 ${toIsoDate(common.start)} - ${toIsoDate(common.end)}。${blockers.length ? "存在覆盖缺口，页面不把短样本冒充完整长周期。" : "覆盖完整。"}`
  );
}

function renderFullCycleValidation(payload) {
  const meta = payload.metadata || {};
  const coverage = payload.coverage_audit || {};
  const desired = meta.desired_window || coverage.desired_window || {};
  const validation = meta.validation_window || {};
  const operational = coverage.operational_validation_window || {};
  const summaryTarget = document.getElementById("fullCycleSummary");
  if (summaryTarget) {
    const rows = [
      ["目标完整周期", `${toIsoDate(desired.start)} - ${toIsoDate(desired.end)}`],
      ["当前真实可验证窗口", `${toIsoDate(validation.start || operational.start)} - ${toIsoDate(validation.end || operational.end)}`],
      ["是否可声明完整周期", meta.full_cycle_claim ? "是" : "否"],
      ["覆盖阻塞项", `${coverage.blocker_count ?? (coverage.blockers || []).length} 项`],
    ];
    summaryTarget.innerHTML = rows
      .map(([label, value]) => `<div class="v2-list-row"><span>${label}</span><strong>${value}</strong></div>`)
      .join("");
  }

  const order = [
    "v2_refined_structural_policy",
    "v2_baseline",
    "benchmark_510300",
    "benchmark_510500",
    "buy_hold_equal_510300_510500",
    "old_s1",
    "m2_macro_style",
  ];
  const comparison = payload.comparison || {};
  const table = document.getElementById("fullCycleRows");
  if (table) {
    table.innerHTML = order
      .filter((key) => comparison[key])
      .map((key) => {
        const item = comparison[key] || {};
        return `<tr>
          <td>${item.label || key}</td>
          <td>${fmtPercent(item.total_return)}</td>
          <td>${fmtPercent(item.annualized_return)}</td>
          <td>${fmtPercent(item.max_drawdown)}</td>
          <td>${fmtNumber(item.sharpe)}</td>
          <td>${fmtNumber(item.calmar)}</td>
          <td>${fmtPercent(item.average_exposure)}</td>
        </tr>`;
      })
      .join("");
  }

  const blockers = coverage.blockers || [];
  const firstBlockers = blockers.slice(0, 3).join("；");
  setText(
    "fullCycleNote",
    meta.full_cycle_claim
      ? "本地数据已覆盖目标完整周期，结果可作为完整周期验证。"
      : `本地数据尚不能支撑 2015 起完整周期结论，当前只展示真实可验证窗口；主要缺口：${firstBlockers || "见 API 覆盖审计"}。`
  );
}

function renderHistoryExpansion(payload) {
  const before = payload.available_before || {};
  const after = payload.after || {};
  const target = document.getElementById("historyExpansionSummary");
  if (target) {
    const rows = [
      ["目标区间", payload.target || "--"],
      ["扩展前窗口", `${toIsoDate(before.start)} - ${toIsoDate(before.end)}`],
      ["扩展后窗口", `${toIsoDate(after.start)} - ${toIsoDate(after.end)}`],
      ["覆盖状态", payload.coverage_status || "--"],
      ["完整周期 ready", payload.full_cycle_ready ? "是" : "否"],
      ["硬缺口", `${after.blocker_count ?? (payload.known_gaps || []).length} 项`],
    ];
    target.innerHTML = rows
      .map(([label, value]) => `<div class="v2-list-row"><span>${label}</span><strong>${value}</strong></div>`)
      .join("");
  }
  const gaps = payload.known_gaps || [];
  setText(
    "historyExpansionNote",
    gaps.length
      ? `数据基础已扩展到 2015 首个交易日，但仍有显式缺口：${gaps.join("；")}。`
      : "历史数据基础已覆盖目标窗口。"
  );
}

function coverageLabel(item) {
  const coverage = item?.coverage || {};
  if (!coverage.sessions) return "--";
  const start = toIsoDate(coverage.start);
  const end = toIsoDate(coverage.end);
  const ratio = fmtPercent(coverage.coverage_ratio);
  return `${start} - ${end}<br><span>${coverage.sessions} 日 · ${ratio}</span>`;
}

function renderFullCycleBacktest(payload) {
  const meta = payload.metadata || {};
  const quality = payload.data_quality || {};
  const gap = quality.macro_gap_policy || {};
  const windowInfo = meta.validation_window || {};
  const summaryTarget = document.getElementById("fullCycleBacktestSummary");
  if (summaryTarget) {
    const rows = [
      ["验证窗口", `${toIsoDate(windowInfo.start)} - ${toIsoDate(windowInfo.end)} · ${windowInfo.sessions ?? "--"} 日`],
      ["覆盖状态", meta.coverage_status || "--"],
      ["严格完整周期声明", meta.strict_full_cycle_claim ? "是" : "否"],
      ["软缺口", (gap.missing_indicators || []).join(" / ") || "--"],
      ["置信度扣减", typeof gap.confidence_penalty === "number" ? `${(gap.confidence_penalty * 100).toFixed(0)}pct` : "--"],
    ];
    summaryTarget.innerHTML = rows
      .map(([label, value]) => `<div class="v2-list-row"><span>${label}</span><strong>${value}</strong></div>`)
      .join("");
  }

  const comparison = payload.comparison || {};
  const order = [
    "v2_current",
    "v2_structural_refined",
    "v2_baseline",
    "benchmark_510300",
    "benchmark_510500",
    "buy_hold_equal_510300_510500",
    "old_s1",
    "m2_macro_style",
  ];
  const table = document.getElementById("fullCycleBacktestRows");
  if (table) {
    table.innerHTML = order
      .filter((key) => comparison[key])
      .map((key) => {
        const item = comparison[key] || {};
        const note = item.note ? `<br><span>${item.note}</span>` : "";
        return `<tr>
          <td><strong>${item.label || key}</strong>${note}</td>
          <td>${coverageLabel(item)}</td>
          <td>${fmtPercent(item.total_return)}</td>
          <td>${fmtPercent(item.annualized_return)}</td>
          <td>${fmtPercent(item.max_drawdown)}</td>
          <td>${fmtNumber(item.sharpe)}</td>
          <td>${fmtNumber(item.calmar)}</td>
          <td>${fmtPercent(item.average_exposure)}</td>
          <td>${fmtNumber(item.cumulative_turnover, 2)}</td>
        </tr>`;
      })
      .join("");
  }

  const phases = payload.period_attribution || {};
  const phaseOrder = ["2015_bull_bear", "2018_bear", "2020_covid", "2021_core_asset", "2022_bear", "2024_2026_structural"];
  const phaseTable = document.getElementById("fullCyclePhaseRows");
  if (phaseTable) {
    phaseTable.innerHTML = phaseOrder
      .filter((key) => phases[key])
      .map((key) => {
        const phase = phases[key] || {};
        const strategies = phase.strategies || {};
        return `<tr>
          <td>${phase.label || key}</td>
          <td>${phase.sessions ?? "--"}</td>
          <td>${fmtPercent(strategies.v2_current?.total_return)}</td>
          <td>${fmtPercent(strategies.v2_baseline?.total_return)}</td>
          <td>${fmtPercent(strategies.benchmark_510300?.total_return)}</td>
          <td>${fmtPercent(strategies.benchmark_510500?.total_return)}</td>
          <td>${fmtPercent(strategies.buy_hold_equal_510300_510500?.total_return)}</td>
        </tr>`;
      })
      .join("");
  }

  const structural = payload.structural_bull_contribution?.STRUCTURAL_BULL_ROTATION || {};
  const structuralTarget = document.getElementById("structuralBullContribution");
  if (structuralTarget) {
    const rows = [
      ["结构性牛市样本", `${structural.sessions ?? "--"} 日`],
      ["平均暴露", fmtPercent(structural.average_exposure)],
      ["V2 区间复合收益", fmtPercent(structural.compound_return_within_sessions)],
      ["510500 区间收益", fmtPercent(structural.benchmark_510500_return)],
      ["Missed beta", fmtPercent(structural.missed_beta)],
    ];
    structuralTarget.innerHTML = rows
      .map(([label, value]) => `<div class="v2-list-row"><span>${label}</span><strong>${value}</strong></div>`)
      .join("");
  }

  const hard = quality.hard_blockers || [];
  const soft = quality.soft_blockers || [];
  setText(
    "fullCycleBacktestNote",
    `V2.6.3 使用 2015+ 真实历史数据重建 T+1 信号；硬缺口 ${hard.length} 项，软缺口 ${soft.length} 项。CN10Y/new_loans 只做置信度披露，不调规则、不补标签。`
  );
}

function renderBacktest(payload) {
  const summary = payload.summary || {};
  setText("validationHeadline", `V2 年化 ${fmtPercent(summary.v2_annualized_return)} · Alpha vs 510500 ${fmtPercent(summary.alpha_vs_510500)}`);
  setText("validationWindow", `${toIsoDate(summary.start_date)} - ${toIsoDate(summary.end_date)}`);
  setText("v2Annualized", fmtPercent(summary.v2_annualized_return));
  setText("v2Drawdown", fmtPercent(summary.v2_max_drawdown));
  setText("v2TotalReturn", fmtPercent(summary.v2_total_return));
  setText("v2Sharpe", fmtNumber(summary.v2_sharpe));
  setText("v2Calmar", fmtNumber(summary.v2_calmar));
  setText("v2AvgExposure", fmtPercent(summary.average_exposure));
  setText(
    "validationNote",
    `V2 跑赢旧 S1.1 ${fmtPercent(summary.alpha_vs_old_s1)}，跑赢 M2.1 ${fmtPercent(summary.alpha_vs_m2_macro_style)}；但落后 510300 ${fmtPercent(summary.alpha_vs_510300)}，落后 510500 ${fmtPercent(summary.alpha_vs_510500)}。这是验证结论，不是交易建议。`
  );
  renderChecks(payload);
  renderChart(payload.equity_curve || []);
  renderBenchmarkTable(payload.benchmark_comparison || {});
  renderStateTable(payload.state_attribution || {});
}

async function loadV2Validation() {
  try {
    setText("validationNote", "加载中...");
    const payload = await getJson("/api/v2/backtest");
    renderBacktest(payload);
    try {
      const sensitivity = await getJson("/api/v2/policy-sensitivity");
      renderPolicySensitivity(sensitivity);
      renderCoverageAudit(sensitivity);
    } catch (error) {
      setText("policyBestNote", `敏感性产物暂不可用：${error.message}`);
      setText("coverageNote", "覆盖审计暂不可用。");
    }
    try {
      const fullCycle = await getJson("/api/v2/full-cycle-validation");
      renderFullCycleValidation(fullCycle);
    } catch (error) {
      setText("fullCycleNote", `完整周期验证产物暂不可用：${error.message}`);
    }
    try {
      const historyExpansion = await getJson("/api/v2/history-expansion");
      renderHistoryExpansion(historyExpansion);
    } catch (error) {
      setText("historyExpansionNote", `历史数据扩展产物暂不可用：${error.message}`);
    }
    try {
      const fullCycleBacktest = await getJson("/api/v2/full-cycle-backtest");
      renderFullCycleBacktest(fullCycleBacktest);
    } catch (error) {
      setText("fullCycleBacktestNote", `完整周期回测产物暂不可用：${error.message}`);
    }
  } catch (error) {
    setText("validationNote", `加载失败：${error.message}`);
  }
}

document.getElementById("refreshButton")?.addEventListener("click", loadV2Validation);
loadV2Validation();
