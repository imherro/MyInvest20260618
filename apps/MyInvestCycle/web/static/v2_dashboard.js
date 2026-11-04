function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value == null || value === "" ? "--" : String(value);
}

function fmtNumber(value, digits = 1) {
  if (typeof value !== "number") return "--";
  return value.toFixed(digits);
}

function fmtPercent(value) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
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

function renderList(id, items, renderer) {
  const target = document.getElementById(id);
  if (!target) return;
  if (!items || !items.length) {
    target.innerHTML = `<div class="v2-empty">暂无</div>`;
    return;
  }
  target.innerHTML = items.map(renderer).join("");
}

function renderOverview(payload) {
  const modules = payload.modules || {};
  const macro = modules.macro || {};
  const structure = modules.market_structure || {};
  const industry = modules.industry_opportunity || {};
  const structural = modules.structural_bull || {};
  const themeRisk = modules.theme_risk || {};
  const allocation = modules.allocation_intent || {};
  const traceSnapshot = modules.decision_trace || {};
  const trace = traceSnapshot.decision_trace || {};
  const intent = allocation.allocation_intent || {};
  const structureMetrics = structure.metrics || {};
  const industryMetrics = industry.metrics || {};

  setText("v2Headline", `${structural.structural_state || "--"} · ${themeRisk.theme_risk_level || "--"} risk · ${intent.risk_budget || "--"} budget`);
  setText("v2AsOf", toIsoDate(payload.as_of));
  setText("v2RiskBudget", intent.risk_budget);
  setText("v2ExposureRange", intent.equity_exposure_range);

  setText("macroState", macro.macro_state);
  setText("macroScore", fmtNumber(macro.macro_score));
  setText("structureState", structure.structure_state);
  setText("structureScore", fmtNumber(structure.structure_score));
  setText("structureBreadth", fmtNumber(structureMetrics.breadth));
  setText("structureLiquidity", fmtNumber(structureMetrics.liquidity));

  setText("structuralState", structural.structural_state);
  setText("structuralConfidence", fmtPercent(structural.confidence));
  setText("industryScore", fmtNumber(industry.industry_opportunity_score));
  setText("themePersistence", fmtNumber(industry.theme_persistence));
  renderList("topThemes", (industry.top_themes || []).slice(0, 5), (item) => (
    `<div class="v2-list-row"><span>${item.name || item.code}</span><strong>${fmtNumber(item.composite_score)}</strong></div>`
  ));

  setText("themeRiskLevel", themeRisk.theme_risk_level);
  setText("qualityScore", fmtNumber(themeRisk.quality_score));
  setText("crowdingScore", fmtNumber(themeRisk.crowding_score));
  setText("topThemeName", themeRisk.top_theme?.name);
  renderList("themeWarnings", themeRisk.warnings || [], (item) => `<div class="v2-warning">${item}</div>`);

  const adjustment = trace.adjustment_path || [];
  const themeStep = adjustment.find((item) => item.step === "theme_risk_adjustment") || {};
  setText("allocationStructuralState", allocation.allocation_structural_state || allocation.risk_adjustments?.allocation_structural_state);
  setText("baseBudget", adjustment[0]?.value);
  setText("budgetDelta", themeStep.delta == null ? "--" : String(themeStep.delta));
  setText("finalBudget", trace.final_intent?.risk_budget || intent.risk_budget);
  setText("auditPassed", traceSnapshot.audit?.passed ? "通过" : "待检查");
  renderList("stylePreference", intent.style_preference || [], (item) => `<div class="v2-tag">${item}</div>`);
  renderList("conflictList", trace.conflicts || [], (item) => `<div class="v2-warning">${item}</div>`);

  const traceItems = [
    ["Macro", trace.macro],
    ["Structure", trace.structure],
    ["Industry", trace.industry],
    ["Theme Risk", trace.theme_risk],
  ];
  const traceTarget = document.getElementById("decisionTrace");
  if (traceTarget) {
    traceTarget.innerHTML = traceItems
      .map(([label, item]) => `<div class="v2-trace-step"><span>${label}</span><strong>${item?.impact || "--"}</strong><p>${item?.reason || ""}</p></div>`)
      .join("");
  }
  setText("v2Error", `行业宽度 ${fmtPercent(industryMetrics.industry_breadth)} · 决策审计 ${traceSnapshot.audit?.passed ? "通过" : "待检查"} · 只读展示，不产生交易动作。`);
}

async function loadV2Overview() {
  try {
    setText("v2Error", "加载中...");
    const payload = await getJson("/api/v2/overview");
    renderOverview(payload);
  } catch (error) {
    setText("v2Error", `加载失败：${error.message}`);
  }
}

document.getElementById("refreshButton")?.addEventListener("click", loadV2Overview);
loadV2Overview();
