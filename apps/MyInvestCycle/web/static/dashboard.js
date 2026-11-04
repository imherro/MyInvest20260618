const state = {
  current: null,
  cycle: null,
  scoreHistory: null,
  results: null,
};

function setRegimePanel(current) {
  const panel = document.getElementById("regimePanel");
  if (!panel) return;
  const color = REGIME_COLORS[current.regime] || REGIME_COLORS.range;
  panel.style.borderLeftColor = color;
  setText("regimeName", shortTermRegimeLabel(current.regime));
  const name = document.getElementById("regimeName");
  if (name) name.style.color = color;
  setText("asOf", `数据基准日 ${toIsoDate(current.as_of)}`);
  setText("dataAsOfValue", toIsoDate(current.as_of));
  setText("confidenceValue", scorePercent(current.confidence));
  setText("regimeScoreValue", scorePercent(current.regime_score));
}

function shortTermRegimeLabel(regime) {
  const labels = {
    bull: "短期强势",
    bear: "短期弱势",
    range: "短期震荡",
    transition: "短期分歧",
    recovery: "短期修复",
    contraction: "风险收缩",
  };
  return labels[regime] || regimeLabel(regime);
}

function setRegimeContextNote(current, cycle) {
  const currentLabel = shortTermRegimeLabel(current?.regime);
  const cycleState = cycle?.current_cycle?.state;
  const cycleLabel = cycleState ? `${regimeLabel(cycleState)}主周期` : "长期主周期";
  const drivers = [];
  if (typeof current?.trend_score === "number") drivers.push(`趋势 ${scorePercent(current.trend_score)}`);
  if (typeof current?.breadth_score === "number") drivers.push(`宽度 ${scorePercent(current.breadth_score)}`);
  const driverText = drivers.length ? `，当前主要证据是${drivers.join("、")}` : "";
  const asOfText = current?.as_of ? `数据基准日 ${toIsoDate(current.as_of)}。` : "";
  const note = `${asOfText}短期风控状态为“${currentLabel}”，只代表趋势、宽度、流动性、波动稳定性的短期温度${driverText}；长期判断仍按“${cycleLabel}”单独观察。`;
  setText("regimeContextNote", note);
  const help = document.getElementById("macroSummaryHelp");
  if (help) help.dataset.help = note;
}

function setScoreList(scores) {
  const target = document.getElementById("scoreList");
  if (!target) return;
  const labels = [
    ["trend", "趋势"],
    ["breadth", "宽度"],
    ["liquidity", "流动性"],
    ["volatility", "波动稳定"],
  ];
  target.innerHTML = labels
    .map(([key, label]) => `<div class="score-chip"><span>${label}</span><strong>${scorePercent(scores[key])}</strong></div>`)
    .join("");
}

function setScoreHistoryNote(history) {
  const items = history?.items || [];
  if (!items.length) {
    setText("scoreHistoryNote", "暂无可用历史评分。");
    return;
  }
  const historyEnd = history?.source?.history_end;
  const cacheText = historyEnd && historyEnd !== history.as_of ? `，历史缓存至 ${toIsoDate(historyEnd)}` : "";
  const latestText = history?.source?.appended_current ? `，最新点 ${toIsoDate(history.as_of)} 使用当前评分` : "";
  const filledCount = history?.source?.dynamic_tail_count || 0;
  const filledText = filledCount ? `，末尾 ${filledCount} 个交易日为现场补算` : "";
  setText(
    "scoreHistoryNote",
    `${toIsoDate(history.start_date)} 至 ${toIsoDate(history.as_of)} · ${items.length} 个绘图点 · 色块为5日平滑后的信号区间：绿色=趋势宽度共振弱，黄色=流动性修复，红色=短期风险解除；黑线为综合分，灰线为上证指数背景${cacheText}${latestText}${filledText}。`
  );
}

function mergeScoreHistoryCurrent(history, current) {
  if (!history || !current?.as_of) return history;
  const items = [...(history.items || [])];
  const hasCurrent = items.some((item) => item.as_of === current.as_of);
  if (!hasCurrent) {
    items.push({
      as_of: current.as_of,
      regime: current.regime,
      structural_regime: null,
      scores: {
        ...(current.sub_scores || {}),
        regime_score: current.regime_score,
        confidence: current.confidence,
      },
      index: {
        close: history.source?.latest_index?.as_of === current.as_of ? history.source.latest_index.close : null,
      },
    });
  }
  items.sort((left, right) => String(left.as_of).localeCompare(String(right.as_of)));
  return {
    ...history,
    as_of: current.as_of,
    items,
    source: {
      ...(history.source || {}),
      appended_current: !hasCurrent,
    },
  };
}

async function getJson(url) {
  const requestUrl = new URL(url, window.location.origin);
  requestUrl.searchParams.set("_t", Date.now().toString());
  const response = await fetch(requestUrl.toString(), {
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function setCyclePanel(phase) {
  if (!phase) return;
  const title = document.getElementById("cycleTitle");
  if (!title) return;
  const color = REGIME_COLORS[phase.regime] || REGIME_COLORS.range;
  title.textContent = `${regimeLabel(phase.regime)}主周期`;
  title.style.color = color;
  setText("cycleStart", `${toIsoDate(phase.startDate)} · 上证 ${phase.startClose}`);
  setText("cycleEnd", phase.endDate ? toIsoDate(phase.endDate) : "进行中");
  setText(
    "cyclePosition",
    `第 ${phase.elapsedSessions} 个交易日 · 约 ${phase.elapsedYears} 年 · ${phase.returnPct}%`
  );
}

function phaseFromMajorCycle(cycle) {
  const current = cycle.current_cycle;
  return {
    regime: current.state,
    startDate: current.start_date,
    currentDate: cycle.as_of,
    endDate: current.end_date,
    elapsedSessions: current.elapsed_sessions,
    elapsedYears: current.elapsed_years,
    startClose: current.start_close,
    returnPct: current.return_pct,
  };
}

function percentText(value) {
  if (typeof value !== "number") return "--";
  return `${(value * 100).toFixed(1)}%`;
}

function priceText(value) {
  if (typeof value !== "number") return "--";
  return value.toFixed(2);
}

function signedPercentText(value) {
  if (typeof value !== "number") return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function signedRatioText(value) {
  if (typeof value !== "number") return "--";
  return signedPercentText(value * 100);
}

function annualizedFromTotal(totalReturn, sessions) {
  if (typeof totalReturn !== "number" || typeof sessions !== "number" || sessions <= 0 || totalReturn <= -1) return null;
  return (1 + totalReturn) ** (252 / sessions) - 1;
}

function fixedText(value, digits = 3) {
  if (typeof value !== "number") return "--";
  return value.toFixed(digits);
}

function signedFixedText(value, digits = 3) {
  if (typeof value !== "number") return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

function drawdownReductionText(value) {
  if (typeof value !== "number") return "--";
  const percent = Math.abs(value * 100).toFixed(1);
  if (value > 0) return `策略少 ${percent}pct`;
  if (value < 0) return `策略多 ${percent}pct`;
  return "持平";
}

function integerText(value) {
  if (typeof value !== "number") return "--";
  return value.toLocaleString("zh-CN");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setProbability(id, barId, value) {
  setText(id, percentText(value));
  const bar = document.getElementById(barId);
  if (bar) bar.style.width = typeof value === "number" ? `${Math.round(value * 100)}%` : "0";
}

function listHtml(items) {
  return (items || []).map((item) => `<li>${item}</li>`).join("");
}

function riskLevelLabel(value) {
  const labels = { low: "低风险", medium: "中风险", high: "高风险" };
  return labels[value] || value || "--";
}

function actionLabel(value) {
  const labels = { reduce: "降低", increase: "提高", hold: "维持" };
  return labels[value] || value || "--";
}

function executionActionLabel(value) {
  const labels = {
    reduce_exposure: "降低仓位",
    rebalance_strategy: "策略再平衡",
    open_new_position: "新开仓",
    increase_exposure: "提高仓位",
    increase_leverage: "增加杠杆",
    trim_overweight: "削减超配",
    hedge: "对冲",
  };
  return labels[value] || value || "--";
}

function executionModeLabel(value) {
  const labels = {
    expand_or_rebalance: "扩张/再平衡",
    rebalance_strategy: "策略再平衡",
    defensive_only: "仅防御",
    reduce_risk: "降低风险",
  };
  return labels[value] || value || "--";
}

function boundaryLabel(value) {
  const labels = {
    no_stock_selection: "不选股",
    no_trade_execution: "不执行交易",
    no_real_orders: "无真实订单",
    no_broker_connection: "无券商连接",
    simulation_only: "仅模拟",
  };
  return labels[value] || value || "--";
}

function metaEdgeLevelLabel(value) {
  const labels = {
    quiet: "平静",
    low: "轻微矛盾",
    medium: "矛盾升温",
    high: "高矛盾",
  };
  return labels[value] || value || "--";
}

function metaSignalLabel(value) {
  const labels = {
    regime_risk_divergence: "状态-风险分歧",
    hazard_mismatch: "结构风险加速",
    portfolio_gap: "组合-策略错位",
    regime_age: "周期年龄异常",
  };
  return labels[value] || value || "--";
}

function styleIncrementalStatusLabel(value) {
  const labels = {
    incremental_positive: "有稳定增量",
    weak_short_horizon_trace: "仅弱短期迹象",
    no_clear_incremental_edge: "无明确增量",
  };
  return labels[value] || value || "--";
}

function budgetLevelLabel(value) {
  const labels = {
    blocked: "不要求",
    low: "低",
    medium: "中",
    medium_high: "中高",
    high: "高",
  };
  return labels[value] || value || "--";
}

function allocationPolicyStateLabel(value) {
  const labels = {
    constraint_only_style_descriptor: "约束型风格描述",
    structural_bull_with_crowding_control: "结构牛拥挤控制",
    broad_bull_beta_policy: "宽基牛 Beta",
    defensive_beta_policy: "防守 Beta",
    macro_defensive_policy: "宏观防守",
  };
  return labels[value] || value || "--";
}

function riskPostureLabel(value) {
  const labels = {
    defensive: "防守",
    risk_off: "低风险",
    balanced: "平衡",
    offensive: "进攻",
    unknown: "未知",
  };
  return labels[value] || value || "--";
}

function policyValidationReviewLabel(value) {
  const labels = {
    bear_or_downturn_budget_not_defensive_enough: "下跌阶段防守不够",
    bull_or_structural_uptrend_budget_may_be_too_constrained: "上涨阶段进攻受限",
  };
  return labels[value] || value || "--";
}

function policyValidationInterpretationLabel(value) {
  const labels = {
    risk_reduction_aligned: "防守匹配",
    risk_reduction_insufficient_review: "防守需复核",
    bull_participation_aligned: "牛市参与匹配",
    bull_participation_may_be_constrained: "牛市参与受限",
    mixed_or_range_validation: "震荡/混合观察",
    no_replay_rows: "无样本",
  };
  return labels[value] || value || "--";
}

function opportunityStateLabel(value) {
  const labels = {
    EARLY_RECOVERY: "早期修复",
    BULL_EXPANSION: "宽基扩张",
    STRUCTURAL_ROTATION: "结构轮动",
    LATE_BULL: "牛市后段/高位",
    DEFENSIVE_REPAIR: "防守修复",
    UNKNOWN: "未知",
  };
  return labels[value] || value || "--";
}

function opportunityRiskStateLabel(value) {
  const labels = {
    LOW_RISK: "低风险",
    NORMAL: "正常",
    CROWDED: "拥挤",
    HIGH_RISK: "高风险",
    UNKNOWN: "未知",
  };
  return labels[value] || value || "--";
}

function opportunityRiskEvidenceLabel(value) {
  const labels = {
    macro_recovery: "宏观修复",
    broad_bull_structure: "宽基牛结构",
    structural_rotation: "结构轮动",
    weak_or_bear_structure: "弱市/熊市结构",
    bull_divergence: "牛市分化",
    trend_strong: "趋势强",
    breadth_expanding: "宽度扩张",
    liquidity_supportive: "流动性支持",
    theme_persistence_high: "主线持续",
    industry_breadth_narrow: "行业宽度窄",
    single_theme_concentration: "单主线集中",
    crowding_elevated: "拥挤升高",
    price_extension_high: "涨幅延伸高",
    theme_risk_low: "主题风险低",
    theme_risk_medium: "主题风险中",
    theme_risk_high: "主题风险高",
  };
  return labels[value] || value || "--";
}

function opportunityRiskPolicyModeLabel(value) {
  const labels = {
    rebuild_risk: "修复期重建观察",
    participate: "参与研究",
    participate_selectively: "选择性参与",
    participate_with_control: "参与但控制拥挤",
    late_cycle_control: "后段收益保护",
    protect_capital: "保护资本",
    defensive: "防守修复",
    watch_only: "仅观察",
  };
  return labels[value] || value || "--";
}

function opportunityRiskPolicyActionLabel(value) {
  const labels = {
    observe_environment: "观察环境",
    rebuild_risk_attention: "修复期关注",
    require_breadth_confirmation: "要求宽度确认",
    maintain_recovery_attention: "保持修复关注",
    require_crowding_control: "要求拥挤控制",
    allow_participation_study: "允许参与研究",
    monitor_breadth: "监控市场宽度",
    allow_selective_participation_study: "允许选择性参与研究",
    monitor_rotation_health: "监控轮动健康度",
    maintain_opportunity_attention: "保持机会关注",
    allow_structural_rotation_study: "允许结构轮动研究",
    require_theme_persistence: "要求主线持续",
    protect_existing_gains: "保护已有收益",
    raise_review_threshold: "提高复核门槛",
    prioritize_risk_repair: "优先风险修复",
    wait_for_recovery_confirmation: "等待修复确认",
    aggressive_expansion: "激进扩张",
    automatic_allocation: "自动配置",
    full_beta_assumption: "默认满 Beta",
    theme_chasing: "追逐主线",
    ignore_crowding: "忽略拥挤",
    single_theme_concentration: "单主线集中",
    unrestricted_expansion: "无限制扩张",
    broad_beta_assumption: "宽基 Beta 假设",
    new_high_beta_budget: "新增高 Beta 预算",
    new_unconfirmed_beta: "新增未确认 Beta",
    offensive_expansion: "进攻扩张",
  };
  return labels[value] || value || "--";
}

function opportunityRiskPolicyInterpretationLabel(value) {
  const labels = {
    defensive_or_protection_dominant: "防守/保护占优",
    participation_with_controls_dominant: "参与/控制占优",
    mixed_policy_modes: "政策模式混合",
    no_replay_rows: "无样本",
  };
  return labels[value] || value || "--";
}

function policyUsefulnessLabel(value) {
  const labels = {
    policy_mode_too_concentrated_review: "政策模式过度集中",
    policy_mode_adds_environment_separation: "政策层增加区分力",
    opportunity_risk_axes_add_separation_but_policy_mapping_compresses: "二维状态有效但政策压缩",
    no_clear_incremental_environment_value: "未证明增量区分力",
  };
  return labels[value] || value || "--";
}

function marketPhaseLabel(value) {
  const labels = {
    EARLY_CYCLE: "早期修复",
    EXPANSION: "扩张阶段",
    ROTATION: "结构轮动",
    LATE_CYCLE: "后期阶段",
    CONTRACTION: "收缩阶段",
    UNKNOWN: "未知",
  };
  return labels[value] || value || "--";
}

function marketPhaseEvidenceLabel(value) {
  const labels = {
    limited_structural_context: "结构字段有限",
    macro_recovery: "宏观修复",
    macro_or_structure_weak: "宏观/结构转弱",
    trend_strong: "趋势强",
    trend_weak: "趋势弱",
    breadth_expanding: "宽度扩张",
    breadth_narrow: "宽度窄",
    liquidity_supportive: "流动性支持",
    liquidity_weak: "流动性弱",
    theme_persistence_high: "主线持续",
    industry_breadth_narrow: "行业宽度窄",
    industry_breadth_broad: "行业扩散",
    single_theme_concentration: "单主线集中",
    crowding_high: "拥挤高",
    price_extension_high: "涨幅延伸高",
    risk_pressure_high: "风险压力高",
    late_opportunity_state: "后期机会状态",
    bull_expansion_state: "扩张状态",
    structural_rotation_state: "结构轮动状态",
    early_recovery_state: "早期修复状态",
  };
  return labels[value] || value || "--";
}

function marketPhaseValidationLabel(value) {
  const labels = {
    phase_adds_risk_environment_separation: "阶段优于旧结构",
    phase_not_yet_better_than_structural: "暂未优于旧结构",
  };
  return labels[value] || value || "--";
}

function phaseEffectivenessVerdictLabel(value) {
  const labels = {
    underperform: "暂未优于旧结构",
    outperform: "优于旧结构",
  };
  return labels[value] || value || "--";
}

function phaseReviewItemLabel(value) {
  const labels = {
    phase_not_better_than_structural: "Phase 未优于旧结构",
    expansion_sample_too_sparse: "扩张样本太少",
    late_cycle_not_risk_enriched: "后期风险未富集",
    bear_period_phase_miss_cases: "熊市阶段漏判",
  };
  return labels[value] || value || "--";
}

function qualitativeExposureLabel(value) {
  const labels = {
    DEFENSIVE: "防守",
    LOW: "低暴露",
    BALANCED: "均衡",
    HIGH: "高暴露",
    OFFENSIVE: "进攻",
  };
  return labels[value] || value || "--";
}

function exposureBandLabel(value) {
  const labels = {
    defensive_research_exposure: "防守研究暴露",
    low_research_exposure: "低研究暴露",
    balanced_research_exposure: "均衡研究暴露",
    balanced_with_controls: "均衡但保留控制",
    selective_balanced_research_exposure: "选择性均衡",
    high_research_exposure: "高研究暴露",
    risk_reduced_research_exposure: "风险压降",
    late_cycle_crowding_control: "后期拥挤控制",
  };
  return labels[value] || value || "--";
}

function exposureEffectivenessStatusLabel(value) {
  const labels = {
    balanced_bucket_too_dominant: "BALANCED 过度集中",
    missing_positive_or_defensive_buckets: "存在缺失等级",
    usable_distribution: "分布可用",
    ordering_review_needed: "有序性待复核",
    ordered: "有序性通过",
  };
  return labels[value] || value || "--";
}

function exposureEffectivenessInterpretationLabel(value) {
  const labels = {
    missing_bucket: "缺失样本",
    sample_too_sparse: "样本太少",
    too_wide_bucket: "桶过宽",
    risk_too_high_for_level: "风险偏高",
    possible_opportunity_miss_bucket: "可能错失机会",
    contradiction_review_needed: "矛盾需复核",
    acceptable_for_now: "暂可接受",
  };
  return labels[value] || value || "--";
}

function exposureEffectivenessReviewLabel(value) {
  const labels = {
    balanced_bucket_too_dominant: "BALANCED 过度集中",
    missing_exposure_level: "暴露等级缺失",
    balanced_risk_higher_than_low: "BALANCED 风险高于 LOW",
    exposure_ordering_not_proven: "有序性未证明",
  };
  return labels[value] || value || "--";
}

function balancedOutcomeLabel(value) {
  const labels = {
    BALANCED_FAILURE: "失败/风险",
    BALANCED_MISSED_OPPORTUNITY: "机会错失",
    BALANCED_NEUTRAL: "中性",
  };
  return labels[value] || value || "--";
}

function exposureContextRecommendationLabel(value) {
  const labels = {
    split_balanced_before_mapper_changes: "先拆 BALANCED",
    balanced_split_not_yet_supported: "暂不支持拆分",
  };
  return labels[value] || value || "--";
}

function balancedCandidateLabel(value) {
  const labels = {
    BALANCED_RISK: "风险候选",
    BALANCED_OPPORTUNITY: "机会候选",
    BALANCED_NEUTRAL: "中性候选",
  };
  return labels[value] || value || "--";
}

function balancedCandidateQualityLabel(value) {
  const labels = {
    candidate_not_ready_for_mapper_change: "不可进正式规则",
    candidate_quality_review_passed: "质量初步通过",
    low: "低",
    low_medium: "中低",
    medium: "中",
    high: "高",
  };
  return labels[value] || value || "--";
}

function macroEnhancedValueLabel(value) {
  const labels = {
    visible_but_not_rule_ready: "可见但不可进规则",
    limited: "解释有限",
  };
  return labels[value] || value || "--";
}

function macroEnhancedDriverLabel(value) {
  const labels = {
    macro_score_low: "宏观分低",
    macro_credit_weak: "信用/M1-M2弱",
    macro_weaker_than_balanced_avg: "宏观弱于均值",
    macro_recovery: "宏观修复",
    liquidity_weak: "流动性弱",
    liquidity_below_balanced_avg: "流动性弱于均值",
    liquidity_above_balanced_avg: "流动性强于均值",
    breadth_low: "宽度低",
    breadth_below_balanced_avg: "宽度弱于均值",
    trend_weak: "趋势弱",
    crowding_high: "拥挤高",
    price_extended: "价格延伸",
    structural_rotation: "结构轮动",
    risk_hypothesis_supported: "风险假设有证据",
    opportunity_hypothesis_supported: "机会假设有证据",
  };
  return labels[value] || value || "--";
}

function macroEnhancedDriverText(drivers) {
  const order = [
    "macro_credit_weak",
    "macro_score_low",
    "macro_weaker_than_balanced_avg",
    "macro_recovery",
    "structural_rotation",
    "liquidity_weak",
    "liquidity_below_balanced_avg",
    "liquidity_above_balanced_avg",
    "breadth_low",
    "breadth_below_balanced_avg",
    "trend_weak",
    "crowding_high",
    "price_extended",
  ];
  const active = order.filter((key) => drivers?.[key]).map(macroEnhancedDriverLabel);
  return active.slice(0, 5).join("、") || "暂无明确驱动";
}

function macroEnhancedEvidenceText(item) {
  const evidence = item?.driver_evidence || {};
  const macro = evidence.macro_score || {};
  const breadth = evidence.breadth_score || {};
  const liquidity = evidence.liquidity_score || {};
  const extension = evidence.price_extension_proxy || {};
  return `宏观 ${fixedText(macro.candidate_avg, 1)} / 宽度 ${fixedText(breadth.candidate_avg, 1)} / 流动性 ${fixedText(liquidity.candidate_avg, 1)} / 价格延伸 ${fixedText(extension.candidate_avg, 1)}`;
}

function contextStateLabel(value) {
  const labels = {
    BALANCED_RECOVERY: "修复型均衡",
    BALANCED_STRUCTURAL_OPPORTUNITY: "结构机会型均衡",
    BALANCED_RISK: "风险型均衡",
    BALANCED_NEUTRAL: "中性均衡",
  };
  return labels[value] || value || "--";
}

function contextStateQualityLabel(value) {
  const labels = {
    research_only_not_rule_ready: "研究候选，未达规则化",
    low: "低",
    low_medium: "中低",
    medium: "中",
    high: "高",
    weak: "弱",
    visible: "可见",
  };
  return labels[value] || value || "--";
}

function riskGradientBucketLabel(value) {
  const labels = {
    high_risk: "高风险梯度",
    medium_risk: "中风险梯度",
    low_risk: "低风险梯度",
    unknown: "未知",
  };
  return labels[value] || value || "--";
}

function opportunityGradientBucketLabel(value) {
  const labels = {
    high_opportunity: "高机会梯度",
    medium_opportunity: "中机会梯度",
    low_opportunity: "低机会梯度",
    unknown: "未知",
  };
  return labels[value] || value || "--";
}

function robustnessConsistencyLabel(value) {
  const labels = {
    high: "高",
    medium: "中",
    weak: "弱",
    insufficient_evidence: "证据不足",
  };
  return labels[value] || value || "--";
}

function robustnessPeriodStatusLabel(value) {
  const labels = {
    positive: "正向",
    negative: "负向",
    flat: "持平",
    insufficient_total_sample: "样本不足",
    insufficient_high_risk_sample: "高风险样本不足",
    insufficient_high_bucket_sample: "高分桶样本不足",
  };
  return labels[value] || value || "--";
}

function robustnessConclusionLabel(value) {
  const labels = {
    risk_gradient_edge_not_confirmed: "风险边际未确认",
    research_value_confirmed_but_still_not_mapper_ready: "研究价值确认，但仍不可进入规则",
    overall_edge_visible_but_not_robust: "总体边际可见，但稳健性未确认",
  };
  return labels[value] || value || "--";
}

function conditionEdgeLabel(value) {
  const labels = {
    positive: "正向",
    negative: "负向",
    flat: "持平",
    insufficient_total_sample: "样本不足",
    insufficient_high_risk_sample: "高风险样本不足",
  };
  return labels[value] || value || "--";
}

function contextValueLabel(value) {
  const labels = {
    EARLY_RECOVERY: "早期修复",
    STRUCTURAL_ROTATION: "结构轮动",
    BULL_EXPANSION: "牛市扩张",
    EARLY_CYCLE: "早周期",
    ROTATION: "轮动",
    LATE_CYCLE: "后周期",
    CONTRACTION: "收缩",
    EXPANSION: "扩张",
    CROWDED: "拥挤",
    NORMAL: "正常",
    LOW_RISK: "低风险",
    UNKNOWN: "未知",
  };
  return labels[value] || value || "--";
}

function conditionDisplayLabel(value) {
  return String(value || "--")
    .split("+")
    .map(contextValueLabel)
    .join(" + ");
}

function conditionConclusionLabel(value) {
  const labels = {
    conditional_edge_visible_but_not_rule_ready: "条件边际可见，但不可规则化",
  };
  return labels[value] || value || "--";
}

function candidateTierLabel(value) {
  const labels = {
    primary_research_candidate: "主研究候选",
    secondary_watch_candidate: "观察候选",
    low_priority_candidate: "低优先级",
  };
  return labels[value] || value || "--";
}

function candidateConclusionLabel(value) {
  const labels = {
    minimal_candidates_found_but_none_rule_ready: "已形成最小候选集，但没有可规则化候选",
  };
  return labels[value] || value || "--";
}

function policyValidationStatusLabel(value) {
  const labels = {
    diagnostic_not_ready_for_policy_change: "诊断未准备好改变策略",
    diagnostic_weak: "诊断较弱",
    diagnostic_promising: "诊断有潜力",
    baseline_no_extra_diagnostic: "基线无额外诊断",
  };
  return labels[value] || value || "--";
}

function policyModelLabel(value) {
  const labels = {
    model_a_baseline_v5_1: "A 基线 V5.1",
    model_b_v5_1_plus_risk_gradient_flag: "B + 风险梯度提示",
    model_c_v5_1_plus_primary_candidate_context: "C + 主候选提示",
  };
  return labels[value] || value || "--";
}

function protectionValidationModelLabel(value) {
  const labels = {
    model_a_risk_gradient_bucket: "A 原始风险梯度",
    model_b_protection_score_bucket: "B 保护分高桶",
    model_c_risk_gradient_plus_protection_score: "C 风险梯度+保护分双高",
  };
  return labels[value] || value || "--";
}

function twoAxisLabel(value) {
  const labels = {
    PARTICIPATE: "参与",
    PROTECT_BUT_PARTICIPATE: "保护参与",
    WAIT: "等待",
    AVOID: "回避",
    UNKNOWN: "未知",
  };
  return labels[value] || value || "--";
}

function contextLayerLabel(value) {
  const labels = {
    layer_0_v5_1_exposure_level: "V5.1 暴露等级",
    layer_1_risk_gradient: "风险梯度",
    layer_2_protection_score: "保护分",
    layer_3_two_axis_context: "双轴上下文",
  };
  return labels[value] || value || "--";
}

function contextLayerStatusLabel(value) {
  const labels = {
    no_clear_incremental_value: "无清晰增量",
    risk_value_only: "只有风险价值",
    research_value: "研究价值",
    weak_risk_value: "弱风险价值",
    weak_opportunity_value: "弱机会价值",
  };
  return labels[value] || value || "--";
}

function contextLayerRetentionLabel(value) {
  const labels = {
    baseline_only_do_not_use_as_validation_axis: "仅作基线",
    keep_as_primary_risk_axis: "保留为主风险轴",
    keep_as_risk_confirmation_layer: "保留为确认层",
    keep_as_research_context_map_not_policy: "保留为研究地图",
    review: "复核",
  };
  return labels[value] || value || "--";
}

function assetCategoryLabel(value) {
  const labels = {
    broad: "宽基",
    style: "风格",
    industry: "行业",
  };
  return labels[value] || value || "--";
}

function opportunityFoundationReadinessLabel(value) {
  const labels = {
    research_ready_with_tradability_caveat: "研究可用，交易历史有限",
    research_ready: "研究可用",
    not_ready: "暂不可用",
  };
  return labels[value] || value || "--";
}

function opportunityFeatureGroupLabel(value) {
  const labels = {
    momentum: "动量",
    relative_strength: "相对强弱",
    trend: "趋势",
    risk: "风险",
    structure: "结构",
  };
  return labels[value] || value || "--";
}

function opportunityValidationStatusLabel(value) {
  const labels = {
    visible: "可见",
    weak: "偏弱",
    flat: "平坦",
    insufficient: "不足",
  };
  return labels[value] || value || "--";
}

function opportunityRetentionLabel(value) {
  const labels = {
    research_candidate: "保留研究",
    watch: "继续观察",
    reject_for_now: "暂不保留",
    insufficient: "样本不足",
  };
  return labels[value] || value || "--";
}

function opportunityRegimeConsistencyLabel(value) {
  const labels = {
    consistent_context_signal: "环境一致",
    single_context_signal: "单环境",
    mixed_or_conflicting_context_signal: "混合/冲突",
    no_regime_signal: "无环境信号",
  };
  return labels[value] || value || "--";
}

function decisionModeLabel(value) {
  const labels = {
    FULL_PARTICIPATION: "全参与",
    SELECTIVE_PARTICIPATION: "选择性参与",
    PROTECTED_PARTICIPATION: "保护性参与",
    DEFENSIVE: "防守",
    WAIT: "等待",
  };
  return labels[value] || value || "--";
}

function alphaSourceLabel(value) {
  const labels = {
    bull_support: "牛市支持",
    bull_drag: "牛市拖累",
    range_support: "震荡支持",
    range_cost: "震荡成本",
    bear_protection: "熊市保护",
    bear_cost: "熊市成本",
    transition_support: "过渡支持",
    transition_cost: "过渡成本",
  };
  return labels[value] || value || "--";
}

function styleLabel(value) {
  const labels = {
    growth: "成长",
    value: "价值",
    low_vol: "低波",
    dividend: "红利",
    small_cap: "小盘",
    cash_proxy: "现金代理",
  };
  return labels[value] || value || "--";
}

function rotationSignalLabel(value) {
  if (!value) return "--";
  if (value === "hold_universe") return "保持观察池";
  if (value === "insufficient_data") return "样本不足";
  if (value.startsWith("rotate_to_")) {
    return `转向${styleLabel(value.replace("rotate_to_", ""))}`;
  }
  return value;
}

function confidenceLevelLabel(value) {
  const labels = {
    high: "高",
    medium: "中",
    low: "低",
    insufficient: "不足",
  };
  return labels[value] || value || "--";
}

function metaEdgeInterpretationText(metaEdge) {
  const level = metaEdge.meta_edge_level;
  const activeSignals = metaEdge.signals || [];
  if (level === "high") return "系统内部矛盾较高，多层输出正在相互冲突";
  if (level === "medium") return "系统内部矛盾正在升温，提高风险前应先复核触发信号";
  if (activeSignals.length) return "存在局部系统矛盾，但还不是主导信号";
  return "系统各层整体一致，当前没有显著 Meta Edge 信号";
}

function strategyLabel(value) {
  const labels = {
    trend: "趋势",
    breakout: "突破",
    defensive: "防御",
    trend_following: "趋势跟随",
    mean_reversion: "均值回归",
    defensive_cash: "防御现金",
    reduce_trading: "降低交易频率",
  };
  return labels[value] || value || "--";
}

function componentLabel(value) {
  const labels = {
    volatility_stress: "波动压力",
    breadth_weakness: "市场宽度偏弱",
    trend_weakness: "趋势偏弱",
    liquidity_weakness: "流动性偏弱",
  };
  return labels[value] || value;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function setHtml(id, value) {
  const node = document.getElementById(id);
  if (node) node.innerHTML = value;
}

function setClassName(id, value) {
  const node = document.getElementById(id);
  if (node) node.className = value;
}

function setBacktestComparisonTable(targetId, rows) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.innerHTML = `
    <div class="backtest-comparison-row backtest-comparison-head">
      <span>标的</span>
      <span>收益</span>
      <span>最大回撤</span>
      <span>收益差</span>
      <span>回撤差</span>
    </div>
    ${rows
      .map(
        (item) => `
          <div class="backtest-comparison-row${item.isStrategy ? " is-strategy" : ""}">
            <strong>${escapeHtml(item.label || item.code || "--")}</strong>
            <span>${signedRatioText(item.total_return)}</span>
            <span>${percentText(item.max_drawdown)}</span>
            <span>${item.isStrategy ? "--" : signedRatioText(item.return_advantage)}</span>
            <span>${item.isStrategy ? "--" : drawdownReductionText(item.drawdown_reduction)}</span>
          </div>
        `
      )
      .join("")}
  `;
}

function setEtfBacktestComparisonTable(summary) {
  const comparisonEtfs = (summary.comparison_etfs || []).map((item) => ({
    ...item,
    return_advantage: item.rotation_return_advantage,
    drawdown_reduction: item.rotation_drawdown_reduction,
  }));
  setBacktestComparisonTable("backtestEtfComparison", [
    {
      label: "轮动策略",
      total_return: summary.rotation_total_return,
      max_drawdown: summary.max_drawdown,
      isStrategy: true,
    },
    ...comparisonEtfs,
  ]);
}

function setMacroStyleComparisonTable(summary) {
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
  setBacktestComparisonTable("macroStyleComparison", [
    {
      label: "M2.1 分层组合",
      total_return: strategyReturn,
      max_drawdown: strategyDrawdown,
      isStrategy: true,
    },
    ...comparisonRows,
  ]);
}

const STRATEGY_DIRECTORY_CARDS = [
  {
    id: "etf-rotation",
    title: "ETF 轮动回测",
    badge: "A1.3",
    href: "/strategy/etf-rotation",
    rule: "每 20 个交易日依据市场状态、风格分数、ETF 相对强弱和排名稳定性，在宽基、红利、成长与现金代理之间轮动；信号收盘后生成，下一交易日生效。",
    source: "etf_rotation_backtest",
    returnKey: "rotation_total_return",
    equalReturnKey: "equal_weight_basket_return",
    equalDrawdownKey: "equal_weight_basket_max_drawdown",
  },
  {
    id: "macro-style",
    title: "Macro-Style-ETF 分层回测",
    badge: "M2.1",
    href: "/strategy/macro-style",
    rule: "把规则拆成宏观层、风格层和 ETF 层：宏观层决定权益暴露范围，风格层分配成长、价值、小盘、红利低波，ETF 层只做执行映射。",
    source: "macro_style_etf_backtest",
    returnKey: "hierarchical_total_return",
    equalReturnKey: "equal_weight_basket_return",
    equalDrawdownKey: "equal_weight_basket_max_drawdown",
  },
  {
    id: "defensive-dividend",
    title: "红利低波防守",
    badge: "Defensive",
    href: "/strategy/defensive-dividend",
    rule: "在红利 ETF、红利低波 ETF 与 511880 现金代理之间切换；红利趋势不足时转向现金代理，目标是降低波动和控制回撤。",
  },
  {
    id: "industry-momentum",
    title: "行业 ETF 动量",
    badge: "Momentum",
    href: "/strategy/industry-momentum",
    rule: "在主要行业 ETF 中按 20/60/120 日动量、波动和回撤评分，选择中期趋势最强的行业；行业趋势不足时转入现金代理。",
  },
  {
    id: "four-asset",
    title: "四资产轮动",
    badge: "Four Asset",
    href: "/strategy/four-asset",
    rule: "在股票、债券、黄金、现金四类 ETF 间按趋势和风险调整评分选择，利用低相关资产改善组合波动和回撤。",
  },
  {
    id: "max-drawdown-batch",
    title: "回撤分批买入",
    badge: "Drawdown",
    href: "/strategy/max-drawdown-batch",
    rule: "用核心 ETF 自身历史回撤分布定义左侧买入档位，回撤加深时分批投入，回撤修复后逐级降低风险。",
  },
  {
    id: "all-weather",
    title: "全天候组合",
    badge: "All Weather",
    href: "/strategy/all-weather",
    rule: "用 A 股 ETF 近似经典全天候组合，覆盖股票、长久期国债、中期国债、黄金和商品期货篮子，并定期再平衡。",
  },
  {
    id: "equal-weight-reversion-basic",
    title: "等权回归基础",
    badge: "Mean Reversion",
    href: "/strategy/equal-weight-reversion-basic",
    rule: "构造 510300、510880、510500、159915 四 ETF 等权净值，观察其相对 MA250 的标准化偏离，低位提高权益暴露，高位降低。",
  },
  {
    id: "equal-weight-reversion-guarded",
    title: "等权回归风控",
    badge: "Guarded",
    href: "/strategy/equal-weight-reversion-guarded",
    rule: "在等权均线回归基础上增加 MA250 下行过滤，避免长期下行阶段越跌越加，优先控制回撤风险。",
  },
  {
    id: "free-cash-flow-trend-half",
    title: "自由现金流通道半仓",
    badge: "FCF Trend",
    href: "/strategy/free-cash-flow-trend-half",
    rule: "统一使用 480092.CNI 国证自由现金流R指数构造 2016 低点以来的对数直线通道；靠近上轨按 5pct 阶梯定卖，最低降到 50%，靠近下轨按 5pct 阶梯定投/加回。",
  },
  {
    id: "free-cash-flow-trend-full",
    title: "自由现金流通道空仓",
    badge: "FCF Trend",
    href: "/strategy/free-cash-flow-trend-full",
    rule: "统一使用 480092.CNI 国证自由现金流R指数对数直线通道；进入上轨卖出区间一次性降到 0%，进入下轨买入区间一次性恢复 100%。",
  },
  {
    id: "free-cash-flow-drawdown-rebound",
    title: "自由现金流回撤反弹",
    badge: "FCF Rebound",
    href: "/strategy/free-cash-flow-drawdown-rebound",
    rule: "空仓跟踪 480092.CNI 阶段高点，回撤 n% 后满仓买入；满仓跟踪阶段低点，反弹 n% 后空仓卖出；同时测试 10%、12%、15%、18%、20% 五个阈值。",
  },
  {
    id: "free-cash-flow-buy-hold-480092",
    title: "自由现金流R满仓",
    badge: "FCF Hold",
    href: "/strategy/free-cash-flow-buy-hold-480092",
    rule: "从 480092.CNI 国证自由现金流R指数有数据开始满仓持有，不择时、不调仓；同图对比沪深300、中证500、创业板、红利低波全收益指数。",
  },
  {
    id: "free-cash-flow-chinext-dynamic",
    title: "FCF/创业板动态",
    badge: "FCF Growth",
    href: "/strategy/free-cash-flow-chinext-dynamic",
    rule: "在自由现金流R和创业板R两个全收益指数之间满仓动态分配：风险平价作基础权重，趋势强弱决定倾斜，单边权重限制在 20%-80%。",
  },
  {
    id: "free-cash-flow-chinext-reversion",
    title: "FCF/创业板回归",
    badge: "FCF Reversion",
    href: "/strategy/free-cash-flow-chinext-reversion",
    rule: "在自由现金流R和创业板R之间做相对回归：用两者净值比值 Z-score 判断谁相对偏热，反向增配另一边，始终保持满仓。",
  },
  {
    id: "free-cash-flow-chinext-balanced-reversion",
    title: "FCF/创业板平衡回归",
    badge: "Balanced",
    href: "/strategy/free-cash-flow-chinext-balanced-reversion",
    rule: "以 50/50 为底仓，风险平价做更大幅度修正；相对比值极端时先做预备回归倾斜，反转确认后加大倾斜。",
  },
  {
    id: "free-cash-flow-ma-deviation",
    title: "FCF均线偏离",
    badge: "FCF MA",
    href: "/strategy/free-cash-flow-ma-deviation",
    rule: "只交易 480092.CNI 自由现金流R指数；默认用 MA120 与 ±5% 偏离带调仓，低于下轨恢复满仓，高于上轨降到半仓；页面同时展示全样本参数扫描，筛参结果仅供研究。",
  },
  {
    id: "free-cash-flow-dual-ma-crossover",
    title: "FCF双均线",
    badge: "Dual MA",
    href: "/strategy/free-cash-flow-dual-ma-crossover",
    rule: "只交易 480092.CNI 自由现金流R指数；默认 MA30/MA90 金叉满仓、死叉空仓；页面同时展示快慢均线参数扫描和样本外验证，筛参结果仅供研究。",
  },
];

const strategyDirectorySort = {
  key: "annualized",
  direction: "desc",
};

function strategyDirectoryPayload(results, card) {
  if (card.source === "etf_rotation_backtest") return results.etf_rotation_backtest || {};
  if (card.source === "macro_style_etf_backtest") return results.macro_style_etf_backtest || {};
  return (results.strategy_suite_backtests || []).find((item) => item.strategy_id === card.id) || {};
}

function strategyDirectorySummary(card, payload) {
  const summary = payload.summary || {};
  const totalReturn = summary[card.returnKey || "strategy_total_return"];
  const sessions = summary.sessions;
  const annualized = typeof summary.annualized_return === "number"
    ? summary.annualized_return
    : annualizedFromTotal(totalReturn, sessions);
  return {
    totalReturn,
    equalReturn: summary[card.equalReturnKey || "equal_weight_return"],
    annualized,
    alpha: summary.alpha_vs_equal_weight,
    drawdown: summary.max_drawdown,
    equalDrawdown: summary[card.equalDrawdownKey || "equal_weight_max_drawdown"],
    sharpe: summary.sharpe,
    sessions: summary.sessions,
    endDate: summary.end_date,
  };
}

function strategyDirectoryLookaheadNote(payload) {
  const metadata = payload.metadata || {};
  if (metadata.no_lookahead_bias === false) {
    return metadata.lookahead_note || "该策略使用回看锚点或未来信息，只适合复盘研究，不应与无未来函数策略直接排序比较。";
  }
  if (metadata.lookahead_note) return metadata.lookahead_note;
  return "";
}

function strategyDirectoryRows(results) {
  return STRATEGY_DIRECTORY_CARDS.map((card) => {
    const payload = strategyDirectoryPayload(results, card);
    const data = strategyDirectorySummary(card, payload);
    const lookaheadNote = strategyDirectoryLookaheadNote(payload);
    return {
      ...card,
      payload,
      data,
      lookahead: Boolean(lookaheadNote),
      lookaheadNote,
      evaluation: strategyDirectoryEvaluation(card, payload),
    };
  });
}

function strategyDirectorySortValue(row, key) {
  const values = {
    strategy: row.title,
    annualized: row.data.annualized,
    totalReturn: row.data.totalReturn,
    drawdown: row.data.drawdown,
    sharpe: row.data.sharpe,
    alpha: row.data.alpha,
    endDate: row.data.endDate,
  };
  return values[key];
}

function sortStrategyDirectoryRows(rows) {
  const key = strategyDirectorySort.key;
  const direction = strategyDirectorySort.direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    if (left.lookahead !== right.lookahead) return left.lookahead ? 1 : -1;
    const leftValue = strategyDirectorySortValue(left, key);
    const rightValue = strategyDirectorySortValue(right, key);
    const leftMissing = leftValue === null || leftValue === undefined || Number.isNaN(leftValue);
    const rightMissing = rightValue === null || rightValue === undefined || Number.isNaN(rightValue);
    if (leftMissing && rightMissing) return left.title.localeCompare(right.title, "zh-CN");
    if (leftMissing) return 1;
    if (rightMissing) return -1;
    if (typeof leftValue === "number" && typeof rightValue === "number") {
      if (leftValue !== rightValue) return (leftValue - rightValue) * direction;
      const leftSharpe = typeof left.data.sharpe === "number" ? left.data.sharpe : -Infinity;
      const rightSharpe = typeof right.data.sharpe === "number" ? right.data.sharpe : -Infinity;
      if (leftSharpe !== rightSharpe) return (leftSharpe - rightSharpe) * -1;
      return left.title.localeCompare(right.title, "zh-CN");
    }
    return String(leftValue).localeCompare(String(rightValue), "zh-CN") * direction;
  });
}

function strategyDirectoryHeader(label, key) {
  const active = strategyDirectorySort.key === key;
  const arrow = active ? (strategyDirectorySort.direction === "asc" ? "↑" : "↓") : "";
  const title = active ? `当前按${label}${strategyDirectorySort.direction === "asc" ? "升序" : "降序"}排序` : `点击按${label}排序`;
  return `<button class="strategy-table-sort${active ? " is-active" : ""}" type="button" data-strategy-sort="${key}" title="${escapeHtml(title)}">${escapeHtml(label)}<span>${arrow}</span></button>`;
}

function strategyDirectoryVerdict(data, comparisonLabel = "等权对照") {
  if (typeof data.totalReturn !== "number") return "回测摘要尚未生成，暂不能评价。";
  const hasAlpha = typeof data.alpha === "number";
  const hasDrawdownGap = typeof data.drawdown === "number" && typeof data.equalDrawdown === "number";
  const drawdownReduction = hasDrawdownGap ? Math.abs(data.equalDrawdown) - Math.abs(data.drawdown) : null;
  if (hasAlpha && data.alpha >= 0 && drawdownReduction !== null && drawdownReduction >= 0) {
    return `收益和回撤均优于${comparisonLabel}，可作为重点候选继续观察。`;
  }
  if (hasAlpha && data.alpha >= 0) {
    return "收益有超额，但回撤代价需要单独评估，适合限定场景使用。";
  }
  if (drawdownReduction !== null && drawdownReduction > 0) {
    return "更像降波动或防守工具，当前不是收益 Alpha 主力。";
  }
  return `当前回测未显示相对${comparisonLabel}的综合优势，暂作研究备选。`;
}

function strategyDirectoryEvaluation(card, payload) {
  const data = strategyDirectorySummary(card, payload);
  const comparisonLabel = payload.summary?.equal_weight_label || "等权";
  if (typeof data.totalReturn !== "number") return "回测数据缺失，等待重新生成后再评价。";
  const parts = [
    `截至 ${toIsoDate(data.endDate)}，累计收益 ${signedRatioText(data.totalReturn)}`,
    `最大回撤 ${percentText(data.drawdown)}`,
  ];
  if (typeof data.alpha === "number") parts.push(`相对${comparisonLabel} Alpha ${signedRatioText(data.alpha)}`);
  if (typeof data.sharpe === "number") parts.push(`夏普 ${fixedText(data.sharpe, 2)}`);
  return `${parts.join("，")}。${strategyDirectoryVerdict(data, comparisonLabel)}`;
}

function setStrategyDirectory(results) {
  const target = document.getElementById("strategyDirectoryGrid");
  if (!target) return;
  const rows = sortStrategyDirectoryRows(strategyDirectoryRows(results));
  target.innerHTML = `
    <div class="chart-panel strategy-directory-table" role="table" aria-label="策略回测对比表">
      <div class="strategy-directory-row strategy-directory-head" role="row">
        <div role="columnheader">排序</div>
        <div role="columnheader">${strategyDirectoryHeader("策略", "strategy")}</div>
        <div role="columnheader">${strategyDirectoryHeader("年化", "annualized")}</div>
        <div role="columnheader">${strategyDirectoryHeader("累计", "totalReturn")}</div>
        <div role="columnheader">${strategyDirectoryHeader("回撤", "drawdown")}</div>
        <div role="columnheader">${strategyDirectoryHeader("夏普", "sharpe")}</div>
        <div role="columnheader">${strategyDirectoryHeader("Alpha", "alpha")}</div>
        <div role="columnheader">${strategyDirectoryHeader("截至", "endDate")}</div>
        <div role="columnheader">规则与评价</div>
      </div>
      ${rows
        .map((row, index) => `
          <div class="strategy-directory-row${row.lookahead ? " has-lookahead" : ""}" role="row">
            <div class="strategy-rank" role="cell">${index + 1}</div>
            <div class="strategy-name-cell" role="cell">
              <span>${escapeHtml(row.badge)}</span>
              <a href="${row.href}">${escapeHtml(row.title)}</a>
              ${row.lookahead ? `<strong class="lookahead-badge" title="${escapeHtml(row.lookaheadNote)}">含未来函数</strong>` : ""}
            </div>
            <div class="metric-strong" role="cell">${signedRatioText(row.data.annualized)}</div>
            <div role="cell">${signedRatioText(row.data.totalReturn)}</div>
            <div role="cell">${percentText(row.data.drawdown)}</div>
            <div role="cell">${fixedText(row.data.sharpe, 2)}</div>
            <div role="cell">${signedRatioText(row.data.alpha)}</div>
            <div role="cell">${toIsoDate(row.data.endDate)}</div>
            <div class="strategy-rule-cell" role="cell">
              ${
                row.lookahead
                  ? `<p class="lookahead-warning"><strong>未来函数</strong>该策略使用回看锚点或未来信息，只适合复盘研究，已固定置底。</p>`
                  : ""
              }
              <p><strong>规则</strong>${escapeHtml(row.rule)}</p>
              <p><strong>评价</strong>${escapeHtml(row.evaluation)}</p>
            </div>
          </div>
        `)
        .join("")}
    </div>
  `;
}

function conclusionItemsForPage(results) {
  const items = results.conclusions || [];
  if (document.body?.dataset.page !== "validation") return items;
  return items.filter((item) =>
    /^(S1\.|H1\.|H2\.|V4\.2|V4\.3|V5\.)/.test(item) || /结构化|默认结构化|波动单因子|风险观察/.test(item)
  );
}

function setApiCatalogPanel(catalog) {
  const docs = catalog.docs || {};
  const groups = catalog.groups || [];
  const recommended = catalog.recommended_entrypoints || [];
  const safety = catalog.safety || {};
  const safetyOk = Object.values(safety).every((value) => value === true);

  setText("apiEndpointCount", integerText(catalog.total_endpoints));
  setText("apiDocsStatus", docs.interactive ? `已开放 ${docs.interactive}` : "--");
  setHtml("apiRecommendedList", recommended.length
    ? recommended
        .map(
          (item) => `
            <div class="api-link-row">
              <span>${escapeHtml(item.path)}</span>
              <strong>${escapeHtml(item.description)}</strong>
            </div>
          `
        )
        .join("")
    : '<div class="api-empty-row">暂无推荐入口</div>');
  setHtml("apiGroupList", groups.length
    ? groups
        .map(
          (group) => `
            <div class="api-group-row">
              <span>${escapeHtml(group.name)}</span>
              <strong>${integerText((group.endpoints || []).length)} 个</strong>
              <em>${escapeHtml(group.description || "")}</em>
            </div>
          `
        )
        .join("")
    : '<div class="api-empty-row">暂无接口分组</div>');
  setText(
    "apiCatalogConclusion",
    safetyOk
      ? "GET /api 已统一输出接口目录；当前系统接口保持只读、模拟、无真实交易边界。"
      : "接口目录已开放，但系统边界需要复核。"
  );
}

function setResultsPanel(results) {
  setStrategyDirectory(results);

  const risk = results.risk || {};
  const decision = risk.decision || {};
  const portfolio = (results.portfolio || {}).allocation || {};
  const route = (results.strategy_route || {}).route || {};
  const execution = (results.execution || {}).simulation || {};
  const metaEdge = results.meta_edge || {};
  const styleRotation = results.style_rotation || {};
  const styleFactor = styleRotation.style_factor || {};
  const etfUniverse = styleRotation.etf_universe || {};
  const styleInterpretation = styleRotation.interpretation || {};
  const etfRotation = results.etf_rotation_signal || {};
  const rotationConfidence = etfRotation.confidence || {};
  const etfBacktest = results.etf_rotation_backtest || {};
  const backtestSummary = etfBacktest.summary || {};
  const backtestValidation = etfBacktest.validation || {};
  const macroStyleBacktest = results.macro_style_etf_backtest || {};
  const macroStyleSummary = macroStyleBacktest.summary || {};
  const macroStyleValidation = macroStyleBacktest.validation || {};
  const shadowBacktest = results.shadow_backtest || {};
  const shadowSummary = shadowBacktest.summary || {};
  const shadowMetadata = shadowBacktest.metadata || {};
  const regimeAttribution = results.regime_attribution || {};
  const attributionSummary = regimeAttribution.summary || {};
  const regimePerformance = regimeAttribution.regime_performance || {};
  const alphaDecomposition = regimeAttribution.alpha_decomposition || {};
  const styleIncremental = results.style_incremental_analysis || {};
  const styleIncrementalSummary = styleIncremental.summary || {};
  const styleIncrementalEdge = styleIncrementalSummary.edge_read || {};
  const allocationPolicy = results.allocation_policy_snapshot || {};
  const allocationPolicyPolicy = allocationPolicy.policy || {};
  const allocationEnvironment = allocationPolicyPolicy.allocation_environment || {};
  const allocationRiskConstraints = allocationPolicyPolicy.risk_constraints || {};
  const allocationPolicyValidation = results.allocation_policy_validation || {};
  const allocationPolicyValidationSummary = allocationPolicyValidation.summary || {};
  const allocationPolicyContradictionAudit = allocationPolicyValidation.policy_contradiction_audit || {};
  const opportunityRiskSnapshot = results.opportunity_risk_snapshot || {};
  const opportunityRiskCurrent = opportunityRiskSnapshot.current || {};
  const opportunityRiskHistory = opportunityRiskSnapshot.historical_summary || {};
  const opportunityRiskPolicy = results.opportunity_risk_policy || {};
  const opportunityRiskPolicyCurrent = opportunityRiskPolicy.current || {};
  const opportunityRiskPolicySummary = opportunityRiskPolicy.summary || {};
  const policyEffectiveness = results.policy_effectiveness || {};
  const policyEffectivenessSummary = policyEffectiveness.summary || {};
  const policyUsefulness = policyEffectivenessSummary.policy_usefulness || {};
  const policyContradictionAudit = policyEffectivenessSummary.contradiction_audit || {};
  const marketPhase = results.market_phase || {};
  const marketPhaseCurrent = marketPhase.current || {};
  const marketPhaseHistory = marketPhase.historical_summary || {};
  const marketPhaseValidation = marketPhaseHistory.future_validation || {};
  const phaseEffectiveness = results.phase_effectiveness || {};
  const phaseEffectivenessSummary = phaseEffectiveness.summary || {};
  const phaseModelComparison = phaseEffectivenessSummary.model_comparison || {};
  const exposureSimulation = results.exposure_simulation || {};
  const exposureSimulationCurrent = exposureSimulation.current || {};
  const exposureSimulationSummary = exposureSimulation.summary || {};
  const exposureSimulationAudit = exposureSimulationSummary.audit || {};
  const exposureEffectiveness = results.exposure_effectiveness || {};
  const exposureEffectivenessSummary = exposureEffectiveness.summary || {};
  const exposureEffectivenessDistribution = exposureEffectivenessSummary.distribution_review || {};
  const exposureEffectivenessOrdering = exposureEffectivenessSummary.ordering_review || {};
  const exposureEffectivenessAbsence = exposureEffectivenessSummary.high_offensive_absence || {};
  const exposureContext = results.exposure_context_analysis || {};
  const exposureContextSummary = exposureContext.summary || {};
  const exposureContextSplit = exposureContextSummary.split_candidates || {};
  const balancedContextAudit = results.balanced_context_audit || {};
  const balancedContextSummary = balancedContextAudit.summary || {};
  const balancedContextQuality = balancedContextSummary.candidate_quality || {};
  const balancedFailureAnalysis = results.balanced_candidate_failure_analysis || {};
  const balancedFailureSummary = balancedFailureAnalysis.summary || {};
  const balancedFailureAttribution = balancedFailureAnalysis.candidate_attribution || {};
  const exposureNumeric = results.exposure_numeric_context || {};
  const exposureNumericSummary = exposureNumeric.summary || {};
  const exposureNumericCoverage = exposureNumericSummary.field_coverage || {};
  const exposureNumericTimeSafety = exposureNumericSummary.time_safety || {};
  const macroContextHistory = results.macro_context_history || {};
  const macroContextSummary = macroContextHistory.summary || {};
  const macroContextCoverage = macroContextSummary.field_coverage || {};
  const macroContextTimeSafety = macroContextSummary.time_safety || {};
  const macroEnhanced = results.macro_enhanced_context_analysis || {};
  const macroEnhancedSummary = macroEnhanced.summary || {};
  const macroEnhancedTimeSafety = macroEnhancedSummary.time_safety || {};
  const macroEnhancedAttribution = macroEnhanced.candidate_re_attribution || {};
  const contextStateAudit = results.exposure_context_state_audit || {};
  const contextStateSummary = contextStateAudit.summary || {};
  const contextStateTimeSafety = contextStateSummary.time_safety || {};
  const contextStateQuality = contextStateAudit.context_state_quality || {};
  const contextStateSeparationReview = contextStateSummary.separation_review || {};
  const gradientAnalysis = results.exposure_gradient_analysis || {};
  const gradientSummary = gradientAnalysis.summary || {};
  const gradientSeparation = gradientSummary.separation_review || {};
  const riskGradientBuckets = gradientAnalysis.risk_bucket_analysis || {};
  const opportunityGradientBuckets = gradientAnalysis.opportunity_bucket_analysis || {};
  const riskRobustness = results.risk_gradient_robustness || {};
  const riskRobustnessSummary = riskRobustness.summary || {};
  const riskRobustnessStats = riskRobustness.robustness || {};
  const riskRobustnessPeriods = riskRobustness.period_analysis || [];
  const riskRobustnessBuckets = riskRobustness.overall_bucket_metrics || {};
  const riskCondition = results.risk_gradient_condition_analysis || {};
  const riskConditionSummary = riskCondition.summary || {};
  const riskCandidates = results.risk_gradient_candidate_rules || {};
  const riskCandidatesSummary = riskCandidates.summary || {};
  const riskCandidateRules = riskCandidates.candidate_rules || [];
  const policyValidation = results.exposure_policy_validation || {};
  const policyValidationSummary = policyValidation.summary || {};
  const policyValidationModels = policyValidation.model_comparison || {};
  const decisionAudit = results.exposure_decision_audit || {};
  const decisionSummary = decisionAudit.summary || {};
  const decisionSeparation = decisionAudit.separation_review || {};
  const decisionModes = decisionAudit.mode_stats || {};
  const contextScoreAudit = results.exposure_context_score_audit || {};
  const contextScoreSummary = contextScoreAudit.summary || {};
  const contextScoreSeparation = contextScoreAudit.separation_review || {};
  const protectionBuckets = contextScoreAudit.protection_bucket_analysis || {};
  const participationBuckets = contextScoreAudit.participation_bucket_analysis || {};
  const protectionValidation = results.protection_score_validation || {};
  const protectionValidationSummary = protectionValidation.summary || {};
  const protectionValidationModels = protectionValidation.model_comparison || {};
  const protectionValidationPhases = protectionValidation.phase_analysis || [];
  const twoAxisValidation = results.two_axis_context_validation || {};
  const twoAxisSummary = twoAxisValidation.summary || {};
  const twoAxisMetrics = twoAxisValidation.dimension_metrics?.two_axis || {};
  const twoAxisComparison = twoAxisValidation.dimension_comparison || {};
  const contextAttribution = results.context_information_attribution || {};
  const contextAttributionSummary = contextAttribution.summary || {};
  const contextAttributionLayers = contextAttribution.layer_attribution || [];
  const opportunityFoundation = results.opportunity_research_foundation || {};
  const opportunityFoundationSummary = opportunityFoundation.summary || {};
  const opportunityFoundationCoverage = opportunityFoundation.coverage || {};
  const opportunityFoundationRows = opportunityFoundation.asset_rows || [];
  const opportunityFeatures = results.opportunity_context_features || {};
  const opportunityFeaturesSummary = opportunityFeatures.summary || {};
  const opportunityFeaturesRows = opportunityFeatures.sample_assets || opportunityFeatures.assets || [];
  const opportunityFeaturesTimeSafety = opportunityFeatures.time_safety || {};
  const opportunityValidation = results.opportunity_feature_validation || {};
  const opportunityValidationSummary = opportunityValidation.summary || {};
  const opportunityValidationSamples = opportunityValidation.sample_results || opportunityValidation.feature_results || [];
  const opportunityValidationTimeSafety = opportunityValidation.time_safety || {};
  const opportunityFeatureAttribution = results.opportunity_feature_attribution || {};
  const opportunityFeatureAttributionSummary = opportunityFeatureAttribution.summary || {};
  const opportunityFeatureAttributionSamples = opportunityFeatureAttribution.sample_attribution || opportunityFeatureAttribution.feature_attribution || [];
  const opportunityArchitecture = results.opportunity_v7_architecture || {};
  const opportunityArchitectureSummary = opportunityArchitecture.summary || {};
  const opportunityArchitectureLayers = opportunityArchitecture.retained_layers || [];
  const opportunityArchitectureRejected = opportunityArchitecture.rejected_outputs || [];
  const opportunityArchitectureEvidence = opportunityArchitecture.evidence || {};
  const researchDecision = results.research_decision_context || {};
  const researchDecisionSummary = researchDecision.summary || {};
  const researchDecisionContext = researchDecision.research_context || {};
  const researchDecisionRiskEvidence = researchDecision.risk_context_evidence || {};
  const researchDecisionOpportunityEvidence = researchDecision.opportunity_context_evidence || {};
  const scenarioAudit = results.research_decision_scenario_audit || {};
  const scenarioAuditSummary = scenarioAudit.summary || {};
  const scenarioAuditRows = scenarioAudit.scenarios || [];
  const contradictionAudit = results.research_decision_contradiction || {};
  const contradictionSummary = contradictionAudit.summary || {};
  const contradictionRows = contradictionAudit.attributions || [];
  const v8Architecture = results.research_decision_v8_architecture || {};
  const v8ArchitectureSummary = v8Architecture.summary || {};
  const v8ArchitectureLayers = v8Architecture.retained_layers || [];
  const v8ArchitectureRejected = v8Architecture.rejected_outputs || [];
  const v8ArchitectureEvidence = v8Architecture.evidence || {};
  const allocationResearch = results.allocation_research_architecture || {};
  const allocationResearchSummary = allocationResearch.summary || {};
  const allocationResearchSchema = allocationResearch.schema || {};
  const allocationResearchEvidence = allocationResearch.source_layer_evidence || {};
  const allocationEvidenceFreeze = results.allocation_research_evidence_freeze || {};
  const allocationEvidenceSummary = allocationEvidenceFreeze.summary || {};
  const allocationEvidenceStatus = allocationEvidenceFreeze.hypothesis_status || {};
  const allocationEvidenceBoundarySummary = allocationEvidenceFreeze.decision_boundary_summary || {};
  const allocationExecution = results.allocation_research_execution || {};
  const allocationExecutionSummary = allocationExecution.summary || {};
  const allocationExecutionRows = Array.isArray(allocationExecution.execution_runs) ? allocationExecution.execution_runs : [];
  const allocationReview = results.allocation_research_result_review || {};
  const allocationReviewSummary = allocationReview.summary || {};
  const allocationReviewRows = allocationReview.hypothesis_review || {};
  const allocationFinal = results.allocation_research_final_boundary || {};
  const allocationFinalSummary = allocationFinal.summary || {};
  const allocationFinalDirections = allocationFinal.directions || {};
  const externalProtocol = results.external_validation_protocol || {};
  const externalProtocolSummary = externalProtocol.summary || {};
  const externalProtocolBody = externalProtocol.protocol || {};
  const externalProtocolExcluded = externalProtocol.excluded_directions || {};
  const h2External = results.h2_external_validation_execution || {};
  const h2ExternalSummary = h2External.summary || {};
  const h2ExternalRuns = Array.isArray(h2External.validation_runs) ? h2External.validation_runs : [];
  const h2Freeze = results.h2_external_validation_result_freeze || {};
  const h2FreezeSummary = h2Freeze.summary || {};
  const h2FreezeConclusion = h2Freeze.final_conclusion || {};
  const h2FreezeEvidence = h2Freeze.evidence || {};
  const phaseClosure = results.research_phase_closure || {};
  const phaseClosureSummary = phaseClosure.summary || {};
  const phaseClosureValidated = Array.isArray(phaseClosure.validated_for_observation_only) ? phaseClosure.validated_for_observation_only : [];
  const phaseClosureNotVerified = Array.isArray(phaseClosure.not_verified_for_investment_use) ? phaseClosure.not_verified_for_investment_use : [];
  const implementationBoundary = results.research_to_implementation_boundary || {};
  const implementationBoundarySummary = implementationBoundary.summary || {};
  const implementationBoundaryGate = implementationBoundary.implementation_entry_gate || {};
  const implementationBoundaryComponents = Array.isArray(implementationBoundary.component_boundaries) ? implementationBoundary.component_boundaries : [];
  const readinessSpec = results.implementation_readiness_evidence_specification || {};
  const readinessSpecSummary = readinessSpec.summary || {};
  const readinessSpecComponents = Array.isArray(readinessSpec.component_readiness_specifications) ? readinessSpec.component_readiness_specifications : [];
  const readinessSpecGates = Array.isArray(readinessSpec.global_readiness_gates) ? readinessSpec.global_readiness_gates : [];
  const readinessAudit = results.implementation_readiness_evidence_audit || {};
  const readinessAuditSummary = readinessAudit.summary || {};
  const readinessAuditComponents = Array.isArray(readinessAudit.component_audits) ? readinessAudit.component_audits : [];
  const submissionProtocol = results.research_component_evidence_submission_protocol || {};
  const submissionProtocolSummary = submissionProtocol.summary || {};
  const submissionProtocolState = submissionProtocol.current_submission_state || {};
  const submissionProtocolContracts = Array.isArray(submissionProtocol.component_submission_contracts) ? submissionProtocol.component_submission_contracts : [];
  const packageValidator = results.evidence_package_validation_engine || {};
  const packageValidatorSummary = packageValidator.summary || {};
  const packageValidatorEngine = packageValidator.validation_engine || {};
  const packageValidatorTemplates = Array.isArray(packageValidator.component_validation_templates) ? packageValidator.component_validation_templates : [];
  const invalidExample = results.invalid_evidence_package_rejection_example || {};
  const invalidExampleSummary = invalidExample.summary || {};
  const invalidExampleDetail = invalidExample.invalid_example_summary || {};
  const governanceFreeze = results.implementation_readiness_governance_freeze || {};
  const governanceFreezeSummary = governanceFreeze.summary || {};
  const governanceFreezeChain = Array.isArray(governanceFreeze.frozen_governance_chain) ? governanceFreeze.frozen_governance_chain : [];
  const riskEvidence = results.risk_diagnostic_evidence_package || {};
  const riskEvidenceSummary = riskEvidence.summary || {};
  const riskEvidenceItems = Array.isArray(riskEvidence.evidence_items) ? riskEvidence.evidence_items : [];
  const riskEvidenceBoundary = riskEvidence.boundary_violation_scan || {};
  const riskEvidenceValidatorResult = riskEvidence.v13_2_validator_result || {};
  const riskEvidenceAuditProjection = riskEvidence.v12_3_audit_projection || {};
  const riskShadow = results.risk_diagnostic_shadow_framework || {};
  const riskShadowSummary = riskShadow.summary || {};
  const riskShadowSchema = riskShadow.event_log_schema || {};
  const riskShadowGuardrails = riskShadow.no_trade_guardrails || {};
  const riskShadowPromotion = riskShadow.promotion_gate || {};
  const riskShadowLog = results.risk_diagnostic_shadow_observation_log || {};
  const riskShadowLogSummary = riskShadowLog.summary || {};
  const riskShadowLogControls = riskShadowLog.observation_controls || {};
  const riskShadowLogBody = riskShadowLog.shadow_observation_log || {};
  const riskShadowLogPromotion = riskShadowLog.promotion_gate || {};
  const riskShadowReview = results.risk_diagnostic_shadow_observation_review || {};
  const riskShadowReviewSummary = riskShadowReview.summary || {};
  const riskShadowReviewFramework = riskShadowReview.review_framework || {};
  const riskShadowReviewResult = riskShadowReview.review_result || {};
  const riskShadowReviewPromotion = riskShadowReview.promotion_gate || {};
  const riskShadowCapture = results.risk_diagnostic_shadow_manual_event_capture || {};
  const riskShadowCaptureSummary = riskShadowCapture.summary || {};
  const riskShadowCaptureControls = riskShadowCapture.manual_capture_controls || {};
  const riskShadowCaptureResult = riskShadowCapture.current_capture_result || {};
  const riskShadowCapturePromotion = riskShadowCapture.promotion_gate || {};
  const riskShadowQuality = results.risk_diagnostic_shadow_event_quality_audit || {};
  const riskShadowQualitySummary = riskShadowQuality.summary || {};
  const riskShadowQualityFramework = riskShadowQuality.quality_audit_framework || {};
  const riskShadowQualityResult = riskShadowQuality.quality_audit_result || {};
  const riskShadowQualityPromotion = riskShadowQuality.promotion_gate || {};
  const riskShadowWorkflow = results.risk_diagnostic_shadow_first_event_workflow || {};
  const riskShadowWorkflowSummary = riskShadowWorkflow.summary || {};
  const riskShadowWorkflowBody = riskShadowWorkflow.first_event_workflow || {};
  const riskShadowWorkflowRequirements = riskShadowWorkflow.first_event_input_requirements || {};
  const riskShadowWorkflowQueue = riskShadowWorkflow.quality_audit_queue || {};
  const riskShadowWorkflowPromotion = riskShadowWorkflow.promotion_gate || {};
  const riskShadowInput = results.risk_diagnostic_shadow_event_input_package || {};
  const riskShadowInputSummary = riskShadowInput.summary || {};
  const riskShadowInputTemplate = riskShadowInput.event_template || {};
  const riskShadowInputSchema = riskShadowInput.json_schema || {};
  const riskShadowInputCli = riskShadowInput.validation_cli || {};
  const riskShadowInputResult = riskShadowInput.current_submission_result || {};
  const riskShadowInputPromotion = riskShadowInput.promotion_gate || {};
  const riskShadowEvidence = results.risk_diagnostic_shadow_evidence_dashboard || {};
  const riskShadowEvidenceSummary = riskShadowEvidence.summary || {};
  const riskShadowEvidenceStats = riskShadowEvidence.event_statistics || {};
  const riskShadowEvidenceStatus = riskShadowEvidence.evidence_status || {};
  const riskShadowEvidenceGate = riskShadowEvidence.implementation_gate || {};
  const v15Rebase = results.v15_strategy_direction_rebase || {};
  const v15RebaseSummary = v15Rebase.summary || v15Rebase;
  const v15RebaseFrozenTracks = v15Rebase.frozen_tracks || {};
  const v15RebaseFrozen = v15RebaseFrozenTracks.v12_v14_governance_shadow || {
    status: v15Rebase.v12_v14_status,
    not_main_alpha_strategy: v15Rebase.not_main_alpha_strategy,
  };
  const v15RebaseRoadmap = v15Rebase.v15_roadmap || { v15_1: v15Rebase.next_task };
  const v15RebaseConstraints = v15Rebase.constraints || {};
  const v15Dataset = results.v15_backtest_dataset_manifest || {};
  const v15DatasetSummary = v15Dataset.summary || v15Dataset;
  const v15DatasetGroupsSource = v15Dataset.dataset_groups || [];
  const v15DatasetGroups = Array.isArray(v15DatasetGroupsSource)
    ? v15DatasetGroupsSource
    : Object.keys(v15DatasetGroupsSource);
  const v15DatasetTargetsSource = v15Dataset.future_backtest_targets || [];
  const v15DatasetTargets = Array.isArray(v15DatasetTargetsSource)
    ? v15DatasetTargetsSource
    : Object.keys(v15DatasetTargetsSource).filter((key) => v15DatasetTargetsSource[key] === true);
  const v15DatasetConstraints = v15Dataset.constraints || {};
  const v15Materialization = results.v15_backtest_dataset_materialization || {};
  const v15MaterializationSummary = v15Materialization.summary || v15Materialization;
  const v15MaterializationGroups = Array.isArray(v15Materialization.coverage_groups)
    ? v15Materialization.coverage_groups
    : Object.keys(v15Materialization.coverage || {});
  const v15MaterializationQuality = v15Materialization.data_quality || {
    source_hash_recorded: v15Materialization.source_hash_recorded,
  };
  const v15MaterializationConstraints = v15Materialization.constraints || {
    no_broker_connection: v15Materialization.no_broker_connection,
  };
  const v15MacroBacktest = results.v15_macro_drawdown_backtest || {};
  const v15MacroBacktestSummary = v15MacroBacktest.summary || v15MacroBacktest;
  const v15MacroBacktestStrategy =
    (v15MacroBacktest.strategy_results || {}).macro_drawdown_strategy ||
    v15MacroBacktest.macro_drawdown_strategy ||
    {};
  const v15MacroBacktestBenchmarks = v15MacroBacktest.benchmarks || {};
  const v15MacroBacktestComparison = v15MacroBacktest.comparison || {};
  const v15MacroBacktestConstraints = v15MacroBacktest.constraints || {};
  const v15MacroRobustness = results.v15_macro_drawdown_robustness || {};
  const v15MacroRobustnessSummary = v15MacroRobustness.summary || v15MacroRobustness;
  const v15MacroRobustnessWalkForward = v15MacroRobustness.walk_forward || {};
  const v15MacroRobustnessConstraints = v15MacroRobustness.constraints || {};
  const v15PointInTime = results.v15_point_in_time_phase_rebuild || {};
  const v15PointInTimeSummary = v15PointInTime.summary || v15PointInTime;
  const v15PointInTimeGaps = Array.isArray(v15PointInTime.gaps) ? v15PointInTime.gaps : [];
  const v15LateCycleOverlay = results.v15_late_cycle_overlay_manifest || {};
  const v15LateCycleSummary = v15LateCycleOverlay.summary || {};
  const v15LateCycleFeatureList = Array.isArray(v15LateCycleOverlay.features) ? v15LateCycleOverlay.features : [];
  const v15SnapshotLedger = results.v15_point_in_time_snapshot_ledger_status || {};
  const v15SnapshotLedgerSummary = v15SnapshotLedger.summary || v15SnapshotLedger;
  const v15DailySnapshot = results.v15_daily_snapshot_capture || {};
  const v15ForwardDecision = results.v15_forward_paper_decision || {};
  const v15ForwardReadouts = v15ForwardDecision.readouts || {};
  const v15ForwardDecisionBody = v15ForwardDecision.paper_decision || {};
  const v15ForwardJournal = results.v15_forward_observation_journal || {};
  const v15ForwardOutcomes = results.v15_forward_outcomes || {};
  const allocationHypotheses = results.allocation_research_hypotheses || {};
  const allocationHypothesesSummary = allocationHypotheses.summary || {};
  const allocationHypothesesSchema = allocationHypotheses.schema || {};
  const allocationHypothesisRows = Array.isArray(allocationHypotheses.hypotheses) ? allocationHypotheses.hypotheses : [];
  const allocationValidationPlan = results.allocation_validation_plan || {};
  const allocationValidationSummary = allocationValidationPlan.summary || {};
  const allocationValidationSchema = allocationValidationPlan.schema || {};
  const allocationValidationRows = Array.isArray(allocationValidationPlan.validation_plans) ? allocationValidationPlan.validation_plans : [];
  const allocationExperiments = results.allocation_experiment_templates || {};
  const allocationExperimentSummary = allocationExperiments.summary || {};
  const allocationExperimentSchema = allocationExperiments.schema || {};
  const allocationExperimentRows = Array.isArray(allocationExperiments.experiment_templates) ? allocationExperiments.experiment_templates : [];
  const allocationExperimentResults = results.allocation_experiment_results || {};
  const allocationExperimentResultSummary = allocationExperimentResults.summary || {};
  const allocationExperimentResultRows = Array.isArray(allocationExperimentResults.experiment_results) ? allocationExperimentResults.experiment_results : [];
  const allocationExperimentScope = allocationExperimentResults.execution_scope || {};
  const allocationPhase1 = results.allocation_experiment_phase1_validation || {};
  const allocationPhase1Summary = allocationPhase1.summary || {};
  const allocationPhase1Rows = Array.isArray(allocationPhase1.validation_results) ? allocationPhase1.validation_results : [];
  const allocationPhase1Hashes = allocationPhase1.freeze_hashes || {};
  const researchGate = results.research_candidate_promotion_gate || {};
  const researchGateSummary = researchGate.summary || {};
  const researchGateRows = Array.isArray(researchGate.gate_results) ? researchGate.gate_results : [];
  const researchDeep = results.research_candidate_deep_validation || {};
  const researchDeepSummary = researchDeep.summary || {};
  const researchDeepRows = Array.isArray(researchDeep.deep_validation_results) ? researchDeep.deep_validation_results : [];
  const system = results.system || {};
  const hazard = results.hazard || {};
  const survival = results.survival || {};
  const validation = results.model_validation || {};
  const defaultModel = validation.default || {};
  const model = defaultModel.model || {};
  const volatility = defaultModel.volatility_only || {};
  const sensitivity = validation.sensitivity || {};
  const structuralHazard = hazard.structural || {};
  const rawHazard = hazard.raw || {};
  const structuralSurvival = survival.structural || {};

  setText("resultsAsOf", `截至 ${toIsoDate(results.as_of)}`);
  setText("riskLevel", riskLevelLabel(decision.risk_level));
  setClassName("riskLevel", `risk-level-text risk-${decision.risk_level || "medium"}`);
  setText("recommendedExposure", percentText(decision.recommended_exposure));
  setText("riskAction", actionLabel(decision.action));
  setText("riskScore", fixedText(decision.risk_score, 3));
  setText("strategyMode", strategyLabel(decision.strategy_mode));
  setText("riskAlert", decision.alert || "--");
  setHtml("riskComponents", Object.entries(decision.risk_components || {})
    .map(
      ([key, value]) => `
        <div class="component-row">
          <span>${componentLabel(key)}</span>
          <strong>${percentText(value)}</strong>
          <i style="width:${typeof value === "number" ? Math.round(value * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));

  setText("portfolioExposure", percentText(portfolio.total_exposure));
  setText("portfolioCash", percentText(portfolio.cash_ratio));
  const constraints = portfolio.constraints || {};
  const constraintOk =
    constraints.cash_plus_exposure === 1 &&
    constraints.min_cash_satisfied === true &&
    constraints.max_exposure_satisfied === true &&
    constraints.strategy_allocation_sum === 1;
  setText("portfolioConstraint", constraintOk ? "通过" : "需检查");
  setHtml("strategyAllocation", Object.entries(portfolio.strategy_allocation || {})
    .map(
      ([strategy, weight]) => `
        <div class="allocation-row">
          <span>${strategyLabel(strategy)}</span>
          <strong>${percentText(weight)}</strong>
          <i style="width:${typeof weight === "number" ? Math.round(weight * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));
  setText(
    "portfolioConclusion",
    `R2.1 使用当前 ${regimeLabel(portfolio.regime)} 状态和风险评分 ${fixedText(portfolio.risk_score, 3)}，将风险资产仓位控制在 ${percentText(portfolio.total_exposure)}，其余保持现金。`
  );

  setText("allocationPolicyState", allocationPolicyStateLabel(allocationPolicyPolicy.policy_state));
  setText("allocationPolicyGrowth", budgetLevelLabel(allocationRiskConstraints.growth_budget_ceiling));
  setText("allocationPolicySmallCap", budgetLevelLabel(allocationRiskConstraints.small_cap_budget_ceiling));
  setText("allocationPolicyDefensive", budgetLevelLabel(allocationRiskConstraints.dividend_budget_floor));
  setText("allocationPolicySingleStyle", budgetLevelLabel(allocationRiskConstraints.max_single_style_budget));
  setText("allocationPolicyOffensive", budgetLevelLabel(allocationRiskConstraints.max_offensive_beta_budget));
  const allocationControls = [];
  if (allocationRiskConstraints.requires_breadth_confirmation_for_offensive_expansion) allocationControls.push("进攻扩张需宽度确认");
  if (allocationRiskConstraints.requires_crowding_control) allocationControls.push("需要拥挤控制");
  if (allocationRiskConstraints.style_score_may_not_expand_budget_by_itself) allocationControls.push("风格分不能单独放大预算");
  if (allocationEnvironment.single_theme_concentration_watch) allocationControls.push("单一主线集中度观察");
  setHtml("allocationPolicyControls", allocationControls.length
    ? allocationControls.map((item) => `<span>${escapeHtml(item)}</span>`).join("")
    : "<em>暂无额外约束</em>");
  setText(
    "allocationPolicyConclusion",
    allocationPolicy.metadata
      ? `V4.1 当前为${allocationPolicyStateLabel(allocationPolicyPolicy.policy_state)}：${allocationPolicyPolicy.policy_summary || "只输出定性风险预算约束"} 该层不输出 ETF 权重、仓位或交易信号。`
      : "V4.1 Beta 风险预算约束尚未生成。"
  );

  setText("opportunityRiskOpportunity", opportunityStateLabel(opportunityRiskCurrent.opportunity_state));
  setText("opportunityRiskRisk", opportunityRiskStateLabel(opportunityRiskCurrent.risk_state));
  setText(
    "opportunityRiskCombined",
    opportunityRiskCurrent.combined_state
      ? `${opportunityStateLabel(opportunityRiskCurrent.opportunity_state)} / ${opportunityRiskStateLabel(opportunityRiskCurrent.risk_state)}`
      : "--"
  );
  setText("opportunityRiskHistory", integerText(opportunityRiskHistory.replay_count));
  setHtml("opportunityRiskEvidence", (opportunityRiskCurrent.evidence || []).length
    ? opportunityRiskCurrent.evidence
        .slice(0, 8)
        .map((item) => `<span>${opportunityRiskEvidenceLabel(item)}</span>`)
        .join("")
    : "<em>暂无证据链</em>");
  setText(
    "opportunityRiskConclusion",
    opportunityRiskSnapshot.metadata
      ? `V4.3 当前为${opportunityStateLabel(opportunityRiskCurrent.opportunity_state)} + ${opportunityRiskStateLabel(opportunityRiskCurrent.risk_state)}：${opportunityRiskCurrent.interpretation || "该层只拆分机会和风险状态"} 历史重放 ${integerText(opportunityRiskHistory.replay_count)} 次，不输出仓位、ETF 或交易信号。`
      : "V4.3 机会-风险二维状态尚未生成。"
  );

  setText("opportunityRiskPolicyMode", opportunityRiskPolicyModeLabel(opportunityRiskPolicyCurrent.policy_mode));
  setText(
    "opportunityRiskPolicyAllowed",
    (opportunityRiskPolicyCurrent.actions_allowed || []).length
      ? opportunityRiskPolicyCurrent.actions_allowed
          .slice(0, 2)
          .map(opportunityRiskPolicyActionLabel)
          .join(" / ")
      : "--"
  );
  setText(
    "opportunityRiskPolicyBlocked",
    (opportunityRiskPolicyCurrent.actions_blocked || []).length
      ? opportunityRiskPolicyCurrent.actions_blocked
          .slice(0, 2)
          .map(opportunityRiskPolicyActionLabel)
          .join(" / ")
      : "--"
  );
  setText("opportunityRiskPolicyHistory", integerText(opportunityRiskPolicySummary.replay_count));
  const policyModeDistribution = opportunityRiskPolicySummary.policy_mode_distribution || {};
  setHtml("opportunityRiskPolicyDistribution", Object.entries(policyModeDistribution)
    .sort(([, a], [, b]) => (b.share || 0) - (a.share || 0))
    .slice(0, 5)
    .map(
      ([mode, item]) => `
        <div class="alpha-source-row">
          <span>${opportunityRiskPolicyModeLabel(mode)}</span>
          <strong>${percentText(item.share)}</strong>
        </div>
      `
    )
    .join(""));
  setHtml("opportunityRiskPolicyPeriods", (opportunityRiskPolicy.period_validation || [])
    .map(
      (period) => `
        <div class="duration-row">
          <span>${escapeHtml(period.label || period.period || "--")}</span>
          <strong>${opportunityRiskPolicyModeLabel(period.dominant_policy_mode)}</strong>
          <em>${opportunityRiskPolicyInterpretationLabel(period.interpretation)} · ${integerText(period.signal_count)} 次</em>
        </div>
      `
    )
    .join(""));
  setText(
    "opportunityRiskPolicyConclusion",
    opportunityRiskPolicy.metadata
      ? `V4.4 当前映射为${opportunityRiskPolicyModeLabel(opportunityRiskPolicyCurrent.policy_mode)}：${opportunityRiskPolicyCurrent.interpretation || "该层只给出定性政策模式"}。允许/禁止动作均为研究约束，不是仓位、ETF、权重或交易信号。`
      : "V4.4 机会-风险政策映射尚未生成。"
  );

  setText("marketPhaseCurrent", marketPhaseLabel(marketPhaseCurrent.phase));
  setText("marketPhaseReplay", integerText(marketPhaseHistory.replay_count));
  setText("marketPhaseRiskSpread", percentText(marketPhaseValidation.phase_high_risk_rate_spread));
  setText("marketPhaseValidationRead", marketPhaseValidationLabel(marketPhaseValidation.phase_vs_structural_read));
  setHtml("marketPhaseEvidence", (marketPhaseCurrent.evidence || []).length
    ? marketPhaseCurrent.evidence
        .slice(0, 8)
        .map((item) => `<span>${marketPhaseEvidenceLabel(item)}</span>`)
        .join("")
    : "<em>暂无证据链</em>");
  const marketPhaseDistribution = marketPhaseHistory.phase_distribution || {};
  setHtml("marketPhaseDistribution", Object.entries(marketPhaseDistribution)
    .sort(([, a], [, b]) => (b.share || 0) - (a.share || 0))
    .slice(0, 6)
    .map(
      ([phase, item]) => `
        <div class="alpha-source-row">
          <span>${marketPhaseLabel(phase)}</span>
          <strong>${percentText(item.share)}</strong>
        </div>
      `
    )
    .join(""));
  setText(
    "marketPhaseConclusion",
    marketPhase.metadata
      ? `V4.6 当前为${marketPhaseLabel(marketPhaseCurrent.phase)}：${marketPhaseCurrent.interpretation || "阶段解释尚缺"}。阶段风险区分 ${percentText(marketPhaseValidation.phase_high_risk_rate_spread)}，${marketPhaseValidationLabel(marketPhaseValidation.phase_vs_structural_read)}；该层不输出仓位、ETF、权重或交易。`
      : "V4.6 市场阶段第三维尚未生成。"
  );

  const enabledStrategies = route.enabled_strategies || [];
  const disabledStrategies = route.disabled_strategies || [];
  setText("routeEnabledCount", integerText(enabledStrategies.length));
  setText("routeDisabledCount", integerText(disabledStrategies.length));
  setHtml("routeEnabledList", enabledStrategies.length
    ? enabledStrategies.map((strategy) => `<span>${strategyLabel(strategy)}</span>`).join("")
    : "<em>无启用策略</em>");
  setHtml("routeBudgetList", Object.entries(route.strategy_budget || {})
    .map(
      ([strategy, weight]) => `
        <div class="allocation-row route-budget-row">
          <span>${strategyLabel(strategy)}</span>
          <strong>${percentText(weight)}</strong>
          <i style="width:${typeof weight === "number" ? Math.round(weight * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));
  setText("routeExecutionStatus", route.constraints?.no_trade_execution ? "仅约束，不执行" : "需检查");
  const disabledReason = route.disabled_reason || {};
  const disabledText = disabledStrategies.length
    ? disabledStrategies.map((strategy) => `${strategyLabel(strategy)}: ${disabledReason[strategy] || "policy"}`).join("；")
    : "无禁用策略";
  setText(
    "routeConclusion",
    `R2.2 将组合资金路由到 ${enabledStrategies.map(strategyLabel).join("、") || "无"}；禁用原因：${disabledText}。`
  );

  const intent = execution.execution_intent || {};
  const simulatedOrders = execution.simulated_orders || [];
  setText("executionMode", executionModeLabel(intent.execution_mode));
  setText("executionOrderCount", integerText(simulatedOrders.length));
  setText("allowedActions", (intent.allowed_actions || []).map(executionActionLabel).join("、") || "--");
  setText("forbiddenActions", (intent.forbidden_actions || []).map(executionActionLabel).join("、") || "--");
  setHtml("simulatedOrders", simulatedOrders
    .map((order) => {
      const size = typeof order.weight_change === "number"
        ? signedPercentText(order.weight_change * 100)
        : percentText(order.target_weight);
      const target = order.strategy ? ` · ${strategyLabel(order.strategy)}` : "";
      return `
        <div class="simulated-order-row">
          <span>${executionActionLabel(order.action)}${target}</span>
          <strong>${size}</strong>
          <em>${escapeHtml(order.reason || "")}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "executionConclusion",
    execution.constraints?.no_real_orders
      ? "R3.1 只生成执行意图和模拟指令，不连接券商，不产生真实订单。"
      : "执行约束需要检查。"
  );

  setText("systemStatus", system.status === "stable" ? "稳定" : "需复核");
  setText("systemLayers", integerText(system.layers));
  setText("systemExecutionMode", system.execution_mode === "simulation" ? "模拟层" : system.execution_mode || "--");
  setText("systemPolicyLocked", system.policy_locked ? "已锁定" : "未锁定");
  setHtml("systemBoundaryList", Object.entries(system.boundaries || {})
    .map(
      ([key, passed]) => `
        <div class="boundary-row">
          <span>${boundaryLabel(key)}</span>
          <strong>${passed ? "通过" : "需检查"}</strong>
        </div>
      `
    )
    .join(""));
  setText(
    "systemConclusion",
    system.status === "stable"
      ? "FINAL 已冻结为 5 层机构级决策模拟系统，所有边界保持只读与模拟。"
      : "系统冻结条件未完全满足，请运行完整性检查。"
  );

  const activeMetaSignals = metaEdge.signals || [];
  const metaSignalStrengths = metaEdge.signal_strengths || {};
  setText("metaEdgeScore", percentText(metaEdge.meta_edge_score));
  setText("metaEdgeLevel", metaEdgeLevelLabel(metaEdge.meta_edge_level));
  setClassName("metaEdgeLevel", `meta-edge-level meta-${metaEdge.meta_edge_level || "quiet"}`);
  setText("metaEdgeActiveCount", activeMetaSignals.length ? `${integerText(activeMetaSignals.length)} 个` : "无触发");
  setHtml("metaEdgeSignalList", activeMetaSignals.length
    ? activeMetaSignals.map((signal) => `<span>${metaSignalLabel(signal)}</span>`).join("")
    : "<em>当前无显著矛盾信号</em>");
  setHtml("metaEdgeStrengthList", Object.entries(metaSignalStrengths)
    .map(
      ([signal, strength]) => `
        <div class="meta-strength-row">
          <span>${metaSignalLabel(signal)}</span>
          <strong>${percentText(strength)}</strong>
          <i style="width:${typeof strength === "number" ? Math.round(strength * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));
  setText(
    "metaEdgeConclusion",
    metaEdge.meta_edge_level
      ? `${metaEdgeInterpretationText(metaEdge)}；该层只检测系统内部矛盾，不预测收益、不选股、不下单。`
      : "M1.1 只检测系统内部矛盾，不改变既有风控链路。"
  );

  const topStyles = styleFactor.top_styles || [];
  const topStyle = topStyles[0] || {};
  const topCandidate = styleInterpretation.primary_candidate || (etfUniverse.top_candidates || [])[0] || {};
  setText("styleRegime", regimeLabel(styleFactor.regime));
  setText(
    "styleTopStyle",
    topStyle.style ? `${styleLabel(topStyle.style)} ${percentText(topStyle.score)}` : "--"
  );
  setText(
    "styleTopCandidate",
    topCandidate.code ? `${topCandidate.name} · ${topCandidate.code}` : "--"
  );
  setHtml("styleScoreList", Object.entries(styleFactor.style_scores || {})
    .map(
      ([style, score]) => `
        <div class="style-score-row">
          <span>${styleLabel(style)}</span>
          <strong>${percentText(score)}</strong>
          <i style="width:${typeof score === "number" ? Math.round(score * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));
  setHtml("styleCandidateList", (etfUniverse.top_candidates || [])
    .slice(0, 4)
    .map(
      (candidate) => `
        <div class="style-candidate-row">
          <span>${escapeHtml(candidate.name || "--")}</span>
          <strong>${escapeHtml(candidate.code || "--")}</strong>
          <em>${styleLabel(candidate.primary_style)} · ${percentText(candidate.candidate_score)}</em>
        </div>
      `
    )
    .join(""));
  setText(
    "styleConclusion",
    styleFactor.engine
      ? `${styleInterpretation.summary || "A1.1 已把当前状态映射为风格评分与 ETF 候选池。"} 当前候选数 ${integerText(etfUniverse.candidate_count)}，仅生成 universe，不选股、不下单。`
      : "A1.1 风格轮动基础结果尚未生成。"
  );

  const rotationTopCandidate = (etfRotation.top_candidates || [])[0] || {};
  setText("rotationSignal", rotationSignalLabel(etfRotation.rebalance_signal));
  setText(
    "rotationConfidence",
    `${percentText(rotationConfidence.score)} · ${confidenceLevelLabel(rotationConfidence.level)}`
  );
  setText(
    "rotationTopEtf",
    rotationTopCandidate.code ? `${rotationTopCandidate.name} · ${rotationTopCandidate.code}` : "--"
  );
  const targetWeights = etfRotation.etf_target_weights || {};
  setHtml("rotationTargetWeights", Object.entries(targetWeights)
    .map(
      ([code, weight]) => `
        <div class="rotation-weight-row">
          <span>${escapeHtml(code)}</span>
          <strong>${percentText(weight)}</strong>
          <i style="width:${typeof weight === "number" ? Math.round(weight * 100) : 0}%"></i>
        </div>
      `
    )
    .join(""));
  setHtml("rotationCandidateList", (etfRotation.top_candidates || [])
    .slice(0, 4)
    .map(
      (candidate) => `
        <div class="rotation-candidate-row">
          <span>${escapeHtml(candidate.name || "--")}</span>
          <strong>${percentText(candidate.signal_score)}</strong>
          <em>${escapeHtml(candidate.code || "--")} · ${styleLabel(candidate.primary_style)} · 相对强弱 ${percentText(candidate.relative_strength_score)}</em>
        </div>
      `
    )
    .join(""));
  setText(
    "rotationConclusion",
    etfRotation.engine
      ? `A1.2 输出 ${rotationSignalLabel(etfRotation.rebalance_signal)}，${rotationConfidence.reason || "置信度待评估"} 该层只给 ETF 级模拟权重建议，不选股、不下单、不生成订单。`
      : "A1.2 ETF 轮动信号结果尚未生成。"
  );

  setText("backtestAlpha510500", signedRatioText(backtestSummary.alpha_vs_510500));
  setText("backtestAlphaEqual", signedRatioText(backtestSummary.alpha_vs_equal_weight));
  setText("backtestRotationReturn", signedRatioText(backtestSummary.rotation_total_return));
  setText("backtestBenchmark510500Return", signedRatioText(backtestSummary.benchmark_510500_return));
  setText("backtestEqualReturn", signedRatioText(backtestSummary.equal_weight_basket_return));
  setText("backtestSharpe", fixedText(backtestSummary.sharpe, 2));
  setText("backtestSessions", integerText(backtestSummary.sessions));
  setText("backtestRebalanceCount", integerText(backtestSummary.rebalance_count));
  setEtfBacktestComparisonTable(backtestSummary);
  setText(
    "backtestDrawdown",
    `轮动 ${percentText(backtestSummary.max_drawdown)} / 等权 ${percentText(backtestSummary.equal_weight_basket_max_drawdown)}`
  );
  setText("backtestHitRate", percentText(backtestSummary.hit_rate_vs_510500));
  const alphaVerdict = backtestValidation.alpha_positive_vs_equal_weight
    ? "跑赢 510500、510300 和等权 ETF basket，存在初步 alpha 证据"
    : backtestValidation.alpha_positive_vs_510500
      ? "仅小幅跑赢 510500，但未跑赢等权 ETF basket，alpha 证据不足"
      : "未跑赢 510500，当前轮动信号未证明 alpha";
  setText(
    "backtestConclusion",
    etfBacktest.metadata
      ? `A1.3 覆盖 ${integerText(backtestSummary.sessions)} 个交易日，${alphaVerdict}；收益口径优先采用 Tushare pct_chg/pre_close，避免 ETF 价格断点被误算为收益。`
      : "A1.3 ETF 轮动回测结果尚未生成。"
  );

  setText("macroStyleAlpha510500", signedRatioText(macroStyleSummary.alpha_vs_510500));
  setText("macroStyleAlphaEqual", signedRatioText(macroStyleSummary.alpha_vs_equal_weight));
  setText("macroStyleReturn", signedRatioText(macroStyleSummary.hierarchical_total_return));
  setText("macroStyle510500Return", signedRatioText(macroStyleSummary.benchmark_510500_return));
  setText("macroStyleEqualReturn", signedRatioText(macroStyleSummary.equal_weight_basket_return));
  setText("macroStyleSharpe", fixedText(macroStyleSummary.sharpe, 2));
  setText("macroStyleSessions", integerText(macroStyleSummary.sessions));
  setText("macroStyleRebalance", integerText(macroStyleSummary.rebalance_count));
  setMacroStyleComparisonTable(macroStyleSummary);
  setText(
    "macroStyleDrawdown",
    `分层 ${percentText(macroStyleSummary.max_drawdown)} / A1 ${percentText(macroStyleSummary.current_a1_max_drawdown)}`
  );
  setText("macroStyleHitRate", percentText(macroStyleSummary.hit_rate_vs_510500));
  const macroStyleVerdict = macroStyleValidation.alpha_positive_vs_equal_weight
    ? "分层组合跑赢等权 ETF basket，具备继续验证价值"
    : macroStyleValidation.alpha_positive_vs_current_a1
      ? "分层组合优于当前 A1，但仍未跑赢 510500 和等权 ETF basket"
      : "分层组合未优于当前 A1，暂未证明新增 alpha";
  setText(
    "macroStyleConclusion",
    macroStyleBacktest.metadata
      ? `M2.1 覆盖 ${integerText(macroStyleSummary.sessions)} 个交易日，平均权益仓位 ${percentText(macroStyleSummary.average_target_exposure)}；${macroStyleVerdict}。宏观层只管仓位，风格层只管权重，ETF 层只做映射。`
      : "M2.1 Macro-Style-ETF 分层回测结果尚未生成。"
  );

  setText("shadowFinalAlpha", signedRatioText(shadowSummary.final_alpha));
  setText("shadowAverageExposure", percentText(shadowSummary.average_applied_exposure));
  setText("shadowTotalReturn", signedRatioText(shadowSummary.shadow_total_return));
  setText("benchmarkTotalReturn", signedRatioText(shadowSummary.benchmark_total_return));
  setText("shadowFinalEquity", fixedText(shadowSummary.final_shadow_equity, 3));
  setText("benchmarkFinalEquity", fixedText(shadowSummary.final_benchmark_equity, 3));
  setText("shadowSessions", integerText(shadowSummary.sessions));
  setText("shadowBenchmarkCode", shadowSummary.benchmark_code || "--");
  setText(
    "shadowDrawdown",
    `${percentText(shadowSummary.max_drawdown_shadow)} / 基准 ${percentText(shadowSummary.max_drawdown_benchmark)}`
  );
  setText(
    "shadowConclusion",
    shadowSummary.sessions
      ? `S1.1 覆盖 ${integerText(shadowSummary.sessions)} 个交易日，使用 ${shadowSummary.benchmark_code || "510500.SH"} 作为基准，并按 ${integerText(shadowMetadata.execution_lag_sessions || 0)} 个交易日滞后应用 R2 仓位；这是仓位风控回测，不做选股，也不代表真实交易账户。收益口径同样优先采用 Tushare pct_chg/pre_close。`
      : "S1.1 仓位风控回测结果尚未生成。"
  );

  setText("regimeAttributionTotalAlpha", signedRatioText(attributionSummary.total_alpha));
  setText("regimeAttributionDrawdownReduction", percentText(attributionSummary.drawdown_reduction));
  setText("largestDragRegime", regimeLabel(attributionSummary.largest_drag_regime));
  setText("largestPositiveRegime", regimeLabel(attributionSummary.largest_positive_regime));
  const regimeOrder = ["bull", "range", "bear", "transition"];
  setHtml("regimeAttributionList", regimeOrder
    .filter((regime) => regimePerformance[regime])
    .map((regime) => {
      const item = regimePerformance[regime];
      return `
        <div class="attribution-regime-row">
          <span>${regimeLabel(regime)}</span>
          <strong>${signedRatioText(item.alpha)}</strong>
          <em>策略 ${signedRatioText(item.shadow_return)} / 基准 ${signedRatioText(item.benchmark_return)}</em>
        </div>
      `;
    })
    .join(""));
  setHtml("alphaSourceList", Object.entries(alphaDecomposition.sources || {})
    .map(
      ([source, value]) => `
        <div class="alpha-source-row">
          <span>${alphaSourceLabel(source)}</span>
          <strong>${signedRatioText(value)}</strong>
        </div>
      `
    )
    .join(""));
  setText(
    "regimeAttributionConclusion",
    attributionSummary.sessions
      ? `S1.2 显示主要拖累来自${regimeLabel(attributionSummary.largest_drag_regime)}，主要正贡献来自${regimeLabel(attributionSummary.largest_positive_regime)}；系统更像风险保护层，而不是原始收益 Alpha 生成器。`
      : "S1.2 regime 归因结果尚未生成。"
  );

  setText("styleIncrementalStatus", styleIncrementalStatusLabel(styleIncrementalEdge.style_incremental_edge_status));
  setText("styleIncremental20Return", signedRatioText(styleIncrementalEdge.tradable_20d_combined_minus_baseline_return));
  setText("styleIncremental60Return", signedRatioText(styleIncrementalEdge.tradable_60d_combined_minus_baseline_return));
  setText("styleIncremental20Ic", signedFixedText(styleIncrementalEdge.tradable_20d_combined_ic_minus_baseline, 3));
  setText("styleIncremental60Ic", signedFixedText(styleIncrementalEdge.tradable_60d_combined_ic_minus_baseline, 3));
  setText(
    "styleIncrementalHitRate",
    `${percentText(styleIncrementalEdge.tradable_20d_combined_hit_rate)} / ${percentText(styleIncrementalEdge.tradable_60d_combined_hit_rate)}`
  );
  const styleIncrementalVerdict =
    styleIncrementalEdge.style_incremental_edge_status === "incremental_positive"
      ? "V3.5.7 显示固定 Combined 同时改善收益、IC 和命中率，Style 可能具备独立增量，但仍未生成仓位。"
      : styleIncrementalEdge.style_incremental_edge_status === "weak_short_horizon_trace"
        ? "V3.5.7 只显示弱短期迹象：20日均值和 IC 有改善，但命中率偏低、60日收益转弱，不能支持配置化。"
        : "V3.5.7 未证明 Style Preference 在 Opportunity Score 之外有稳定独立增量，当前只能保留为研究解释层。";
  setText(
    "styleIncrementalConclusion",
    styleIncremental.metadata
      ? `${styleIncrementalVerdict} Combined 固定为 50% Opportunity + 50% Style，没有调参、没有交易信号。`
      : "V3.5.7 Style 增量信息检验尚未生成。"
  );

  const policyValidationCoverage = allocationPolicyValidationSummary.context_coverage || {};
  const policyValidationReviewItems = allocationPolicyContradictionAudit.review_items || [];
  setText("policyValidationReplay", integerText(allocationPolicyValidationSummary.replay_count));
  setText("policyValidationHardContradictions", integerText(allocationPolicyValidationSummary.contradiction_count));
  setText("policyValidationReviewItems", integerText(allocationPolicyValidationSummary.review_item_count));
  setText("policyValidationContextCoverage", percentText(policyValidationCoverage.complete_structural_context_share));
  const postureDistribution = allocationPolicyValidationSummary.risk_posture_distribution || {};
  setHtml("policyValidationPosture", Object.entries(postureDistribution)
    .map(
      ([posture, item]) => `
        <div class="alpha-source-row">
          <span>${riskPostureLabel(posture)}</span>
          <strong>${percentText(item.share)}</strong>
        </div>
      `
    )
    .join(""));
  setHtml("policyValidationPeriods", (allocationPolicyValidation.period_validation || [])
    .map(
      (period) => `
        <div class="duration-row">
          <span>${escapeHtml(period.label || period.period || "--")}</span>
          <strong>${policyValidationInterpretationLabel(period.interpretation)}</strong>
          <em>${signedRatioText(period.market_return)} · ${integerText(period.signal_count)} 次</em>
        </div>
      `
    )
    .join(""));
  const reviewText = policyValidationReviewItems.length
    ? policyValidationReviewItems
        .slice(0, 3)
        .map((item) => `${item.period}: ${policyValidationReviewLabel(item.type)}`)
        .join("；")
    : "暂无软复核项";
  setText(
    "policyValidationConclusion",
    allocationPolicyValidation.metadata
      ? `V4.2 重放固定 V4.1 规则 ${integerText(allocationPolicyValidationSummary.replay_count)} 次，硬矛盾 ${integerText(allocationPolicyValidationSummary.contradiction_count)} 个，软复核项 ${integerText(allocationPolicyValidationSummary.review_item_count)} 个。${reviewText}。该验证不调规则、不输出仓位、不生成交易。`
      : "V4.2 风险预算历史验证尚未生成。"
  );

  setText("policyEffectivenessRows", integerText(policyEffectivenessSummary.usable_rows));
  setText("policyEffectivenessContradictionRate", percentText(policyContradictionAudit.contradiction_rate));
  setText("policyEffectivenessRiskRate", percentText(policyEffectivenessSummary.high_risk_event_rate));
  setText("policyEffectivenessTopModeShare", percentText(policyUsefulness.top_policy_mode_share));
  const modelComparison = policyEffectiveness.model_comparison || {};
  setHtml("policyEffectivenessModels", [
    ["旧结构状态", modelComparison.structural_state_model],
    ["机会/风险二维", modelComparison.opportunity_risk_model],
    ["政策模式", modelComparison.policy_mode_model],
  ]
    .map(([label, model]) => {
      const separation = (model || {}).separation || {};
      return `
        <div class="alpha-source-row">
          <span>${label}</span>
          <strong>${percentText(separation.high_risk_rate_spread)}</strong>
        </div>
      `;
    })
    .join(""));
  setHtml("policyEffectivenessPeriods", (policyEffectiveness.period_validation || [])
    .map(
      (period) => `
        <div class="duration-row">
          <span>${escapeHtml(period.label || period.period || "--")}</span>
          <strong>${percentText(period.contradiction_rate)}</strong>
          <em>高风险 ${percentText(period.high_risk_event_rate)} · ${integerText(period.usable_rows)} 次</em>
        </div>
      `
    )
    .join(""));
  setText(
    "policyEffectivenessConclusion",
    policyEffectiveness.metadata
      ? `V4.5 固定 V4.4 规则做事后审计：${policyUsefulnessLabel(policyUsefulness.status)}，主模式 ${opportunityRiskPolicyModeLabel(policyUsefulness.top_policy_mode)} 占 ${percentText(policyUsefulness.top_policy_mode_share)}，矛盾率 ${percentText(policyContradictionAudit.contradiction_rate)}。该层只验证解释力，不调阈值、不输出仓位或交易。`
      : "V4.5 政策解释力审计尚未生成。"
  );

  setText("phaseEffectivenessRows", integerText(phaseEffectivenessSummary.usable_rows));
  setText("phaseEffectivenessSpread", percentText(phaseModelComparison.phase_high_risk_rate_spread));
  setText("phaseEffectivenessStructuralSpread", percentText(phaseModelComparison.structural_high_risk_rate_spread));
  setText("phaseEffectivenessReviewItems", integerText(phaseEffectivenessSummary.review_item_count));
  setHtml("phaseEffectivenessReviewList", (phaseEffectivenessSummary.review_items || [])
    .slice(0, 5)
    .map(
      (item) => `
        <div class="alpha-source-row">
          <span>${phaseReviewItemLabel(item.type)}</span>
          <strong>${item.severity || "--"}</strong>
        </div>
      `
    )
    .join(""));
  setHtml("phaseEffectivenessPeriodCases", (phaseEffectiveness.period_error_cases || [])
    .filter((period) => (period.error_case_count || 0) > 0)
    .slice(0, 5)
    .map(
      (period) => `
        <div class="duration-row">
          <span>${escapeHtml(period.label || period.period || "--")}</span>
          <strong>${integerText(period.error_case_count)}</strong>
          <em>${integerText(period.usable_rows)} 次样本</em>
        </div>
      `
    )
    .join(""));
  setText(
    "phaseEffectivenessConclusion",
    phaseEffectiveness.metadata
      ? `V4.7 固定 V4.6 阶段规则做审计：${phaseEffectivenessVerdictLabel(phaseModelComparison.phase_vs_structural)}，Phase 风险区分 ${percentText(phaseModelComparison.phase_high_risk_rate_spread)}，旧结构 ${percentText(phaseModelComparison.structural_high_risk_rate_spread)}，复核项 ${integerText(phaseEffectivenessSummary.review_item_count)} 个。该层不调阈值、不输出仓位或交易。`
      : "V4.7 阶段解释力复核尚未生成。"
  );

  setText("exposureSimulationCurrent", qualitativeExposureLabel(exposureSimulationCurrent.exposure_level));
  setText("exposureSimulationRows", integerText(exposureSimulationSummary.replay_count));
  setText("exposureSimulationContradictionRate", percentText(exposureSimulationAudit.contradiction_rate));
  setText("exposureSimulationOpportunityMissRate", percentText(exposureSimulationAudit.opportunity_miss_rate));
  const exposureDistribution = exposureSimulationSummary.exposure_level_distribution || {};
  setHtml("exposureSimulationDistribution", Object.entries(exposureDistribution)
    .sort(([, a], [, b]) => (b.share || 0) - (a.share || 0))
    .map(
      ([level, item]) => `
        <div class="alpha-source-row">
          <span>${qualitativeExposureLabel(level)}</span>
          <strong>${percentText(item.share)}</strong>
        </div>
      `
    )
    .join(""));
  setHtml("exposureSimulationPeriods", (exposureSimulation.period_validation || [])
    .map(
      (period) => {
        const distribution = period.exposure_level_distribution || {};
        const [dominantLevel, dominantItem] = Object.entries(distribution)
          .sort(([, a], [, b]) => (b.share || 0) - (a.share || 0))[0] || ["--", {}];
        return `
          <div class="duration-row">
            <span>${escapeHtml(period.label || period.period || "--")}</span>
            <strong>${qualitativeExposureLabel(dominantLevel)}</strong>
            <em>矛盾 ${percentText(period.contradiction_rate)} · ${integerText(period.usable_rows)} 次 · ${percentText(dominantItem.share)}</em>
          </div>
        `;
      }
    )
    .join(""));
  setText(
    "exposureSimulationConclusion",
    exposureSimulation.metadata
      ? `V5.1 当前定性等级为${qualitativeExposureLabel(exposureSimulationCurrent.exposure_level)}（${exposureBandLabel(exposureSimulationCurrent.exposure_band)}）：历史重放 ${integerText(exposureSimulationSummary.replay_count)} 次，矛盾率 ${percentText(exposureSimulationAudit.contradiction_rate)}，机会错失率 ${percentText(exposureSimulationAudit.opportunity_miss_rate)}。该层只做模拟验证，不输出仓位百分比、ETF、权重或交易信号。`
      : "V5.1 定性暴露等级模拟尚未生成。"
  );

  setText(
    "exposureEffectivenessDominant",
    exposureEffectivenessDistribution.dominant_level
      ? `${qualitativeExposureLabel(exposureEffectivenessDistribution.dominant_level)} ${percentText(exposureEffectivenessDistribution.dominant_share)}`
      : "--"
  );
  setText("exposureEffectivenessOrdering", exposureEffectivenessStatusLabel(exposureEffectivenessOrdering.status));
  setText(
    "exposureEffectivenessMissing",
    (exposureEffectivenessDistribution.missing_levels || []).length
      ? exposureEffectivenessDistribution.missing_levels.map(qualitativeExposureLabel).join(" / ")
      : "--"
  );
  setText("exposureEffectivenessReviewItems", integerText(exposureEffectivenessSummary.review_item_count));
  const levelEffectiveness = exposureEffectivenessSummary.level_effectiveness || {};
  setHtml("exposureEffectivenessLevels", Object.entries(levelEffectiveness)
    .map(
      ([level, item]) => `
        <div class="alpha-source-row">
          <span>${qualitativeExposureLabel(level)} · ${exposureEffectivenessInterpretationLabel(item.interpretation)}</span>
          <strong>风险 ${percentText(item.future_high_risk_rate)} / 机会 ${percentText(item.future_opportunity_rate)}</strong>
        </div>
      `
    )
    .join(""));
  setHtml("exposureEffectivenessReviewList", (exposureEffectivenessSummary.review_items || [])
    .slice(0, 6)
    .map(
      (item) => `
        <div class="duration-row">
          <span>${exposureEffectivenessReviewLabel(item.type)}</span>
          <strong>${item.severity || "--"}</strong>
          <em>${item.evidence?.level ? qualitativeExposureLabel(item.evidence.level) : `问题 ${integerText(item.evidence?.issue_count)}`}</em>
        </div>
      `
    )
    .join(""));
  setText(
    "exposureEffectivenessConclusion",
    exposureEffectiveness.metadata
      ? `V5.2 固定 V5.1 不改规则做审计：${exposureEffectivenessSummary.key_read || "暴露等级有效性待复核"} 缺失 ${((exposureEffectivenessAbsence.missing_positive_levels || []).map(qualitativeExposureLabel).join(" / ")) || "无"}；该层只做审计，不输出仓位、ETF、权重或交易。`
      : "V5.2 暴露等级有效性审计尚未生成。"
  );

  setText("exposureContextShare", percentText(exposureContextSummary.balanced_share_of_all));
  setText("exposureContextFailure", percentText(exposureContextSummary.balanced_failure_rate));
  setText("exposureContextMissed", percentText(exposureContextSummary.balanced_missed_opportunity_rate));
  setText("exposureContextRecommendation", exposureContextRecommendationLabel(exposureContextSplit.recommendation));
  const balancedSubgroups = exposureContext.balanced_subgroups || {};
  setHtml("exposureContextSubgroups", Object.entries(balancedSubgroups)
    .map(
      ([group, item]) => `
        <div class="alpha-source-row">
          <span>${balancedOutcomeLabel(group)}</span>
          <strong>${integerText(item.count)} 次 · ${percentText(item.share_of_balanced)}</strong>
        </div>
      `
    )
    .join(""));
  const riskContexts = exposureContextSplit.risk_contexts || [];
  const opportunityContexts = exposureContextSplit.opportunity_contexts || [];
  setHtml("exposureContextCandidates", [...riskContexts.slice(0, 3), ...opportunityContexts.slice(0, 3)]
    .map(
      (item) => `
        <div class="duration-row">
          <span>${escapeHtml(item.opportunity_state || "--")} / ${escapeHtml(item.risk_state || "--")}</span>
          <strong>${escapeHtml(item.market_phase || "--")}</strong>
          <em>失败 ${percentText(item.failure_rate)} · 机会 ${percentText(item.missed_opportunity_rate)} · ${integerText(item.usable_rows)} 次</em>
        </div>
      `
    )
    .join(""));
  setText(
    "exposureContextConclusion",
    exposureContext.metadata
      ? `V5.3 只拆解 BALANCED：${exposureContextSummary.key_read || "上下文拆解待生成"} 当前源数据缺少完整数值型宏观/结构字段，暂用 evidence flags 代理；该层不改规则、不新增等级、不输出交易。`
      : "V5.3 BALANCED 上下文拆解尚未生成。"
  );

  setText("balancedContextStatus", balancedCandidateQualityLabel(balancedContextQuality.status));
  setText("balancedContextReady", balancedContextQuality.ready_for_formal_rule === true ? "可进入" : "不可进入");
  setText("balancedContextCount", integerText(balancedContextSummary.candidate_count));
  setText("balancedContextReviewItems", integerText(balancedContextSummary.review_item_count));
  const candidateStates = balancedContextAudit.candidate_states || {};
  setHtml("balancedContextCandidates", Object.entries(candidateStates)
    .map(
      ([candidate, item]) => `
        <div class="alpha-source-row">
          <span>${balancedCandidateLabel(candidate)} · 置信 ${balancedCandidateQualityLabel(item.confidence)} · 稳定 ${balancedCandidateQualityLabel(item.stability)}</span>
          <strong>${integerText(item.sample_count)} 次 · ${percentText(item.share_of_balanced)}</strong>
        </div>
      `
    )
    .join(""));
  setText(
    "balancedContextConclusion",
    balancedContextAudit.metadata
      ? `V5.4 候选状态仍为研究标签：${balancedContextSummary.key_read || "候选质量审计待生成"} 不能作为正式 mapper 或仓位规则。`
      : "V5.4 BALANCED 候选状态审计尚未生成。"
  );

  const riskAttribution = balancedFailureAttribution.BALANCED_RISK || {};
  const opportunityAttribution = balancedFailureAttribution.BALANCED_OPPORTUNITY || {};
  setText("balancedFailureReady", balancedFailureSummary.ready_for_rule_change === true ? "可变更" : "不可变更");
  setText("balancedFailureRiskRows", integerText(riskAttribution.sample_count));
  setText("balancedFailureOpportunityRows", integerText(opportunityAttribution.sample_count));
  setText("balancedFailureReviewItems", integerText(balancedFailureSummary.review_item_count));
  setHtml("balancedFailurePatterns", [
    ["BALANCED_RISK", riskAttribution],
    ["BALANCED_OPPORTUNITY", opportunityAttribution],
    ["BALANCED_NEUTRAL", balancedFailureAttribution.BALANCED_NEUTRAL || {}],
  ]
    .map(
      ([candidate, item]) => `
        <div class="alpha-source-row">
          <span>${balancedCandidateLabel(candidate)} · ${escapeHtml(item.interpretation || "--")}</span>
          <strong>失败 ${percentText(item.future_failure_rate)} / 机会 ${percentText(item.future_opportunity_rate)}</strong>
        </div>
      `
    )
    .join(""));
  setText(
    "balancedFailureConclusion",
    balancedFailureAnalysis.metadata
      ? `V5.5 固定 V5.4 候选标签做归因：${balancedFailureSummary.key_read || "候选归因待生成"} 当前仍不能改 mapper 或进入仓位规则。`
      : "V5.5 BALANCED 候选归因尚未生成。"
  );

  const structureCoverageFields = ["trend_score", "breadth_score", "liquidity_score", "volatility_score"];
  const structureCoverageValues = structureCoverageFields
    .map((field) => exposureNumericCoverage[field]?.coverage_rate)
    .filter((value) => typeof value === "number");
  const structureCoverageAverage = structureCoverageValues.length
    ? structureCoverageValues.reduce((sum, value) => sum + value, 0) / structureCoverageValues.length
    : null;
  const macroCoverage = exposureNumericCoverage.macro_score || {};
  const numericFieldLabels = {
    macro_score: "宏观分",
    macro_confidence: "宏观置信",
    trend_score: "趋势",
    breadth_score: "宽度",
    liquidity_score: "流动性",
    volatility_score: "波动稳定",
    industry_breadth: "行业扩散",
    theme_persistence: "主题持续",
    crowding_score: "拥挤",
    price_extension_proxy: "价格延伸",
    pressure_score: "压力",
    risk_score: "风险分",
  };
  setText("exposureNumericRows", integerText(exposureNumericSummary.row_count));
  setText(
    "exposureNumericTimeSafe",
    exposureNumericTimeSafety.feature_date_lte_signal_date === true
      ? `通过 · ${integerText(exposureNumericTimeSafety.violation_count)} 违规`
      : "需检查"
  );
  setText("exposureNumericStructureCoverage", percentText(structureCoverageAverage));
  setText(
    "exposureNumericMacroCoverage",
    macroCoverage.available_count === 0 ? "无历史序列" : percentText(macroCoverage.coverage_rate)
  );
  setHtml("exposureNumericCoverage", Object.entries(exposureNumericCoverage)
    .filter(([field]) => field !== "macro_confidence")
    .map(
      ([field, item]) => `
        <div class="alpha-source-row">
          <span>${numericFieldLabels[field] || field}</span>
          <strong>${integerText(item.available_count)} / ${integerText(exposureNumericSummary.row_count)} · ${percentText(item.coverage_rate)}</strong>
        </div>
      `
    )
    .join(""));
  const exposureNumericSamples = exposureNumeric.sample_rows || (exposureNumeric.rows || []).slice(-5);
  setHtml("exposureNumericSamples", exposureNumericSamples
    .map((row) => {
      const ctx = row.exposure_context || {};
      const missing = row.data_quality?.missing_numeric_fields || [];
      return `
        <div class="duration-row">
          <span>${toIsoDate(row.date)} · ${qualitativeExposureLabel(ctx.exposure_level)}</span>
          <strong>趋势 ${fixedText(ctx.trend_score, 1)} / 宽度 ${fixedText(ctx.breadth_score, 1)} / 拥挤 ${fixedText(ctx.crowding_score, 1)}</strong>
          <em>缺失 ${missing.slice(0, 4).map((field) => numericFieldLabels[field] || field).join("、") || "无"}</em>
        </div>
      `;
    })
    .join(""));
  const exposureMacroRead = exposureNumericSummary.missing_macro_history
    ? "宏观历史数值暂无序列，保持 null，不用 0 替代"
    : `宏观分已从 V5.7 历史宏观上下文接入，覆盖 ${percentText(macroCoverage.coverage_rate)}`;
  setText(
    "exposureNumericConclusion",
    exposureNumeric.metadata
      ? `V5.6 已把暴露重放接上数值上下文：${exposureNumericSummary.key_read || "数值上下文已生成"} 时间安全违规 ${integerText(exposureNumericTimeSafety.violation_count)} 个；${exposureMacroRead}。该层只做解释审计，不改 mapper、不输出仓位或交易。`
      : "V5.6 暴露数值上下文尚未生成。"
  );

  const macroScoreCoverage = macroContextSummary.macro_score_coverage || {};
  const macroValuationCoverage = macroContextSummary.valuation_coverage || {};
  const valuationScoreCoverage = macroValuationCoverage.valuation_score || {};
  const macroContextFieldLabels = {
    macro_score: "宏观分",
    macro_confidence: "宏观置信",
    valuation_score: "估值",
    credit_score: "信用",
    economy_score: "景气",
    external_score: "外部压力",
    M1_growth: "M1",
    M2_growth: "M2",
    M1_M2_spread: "M1-M2",
    social_financing_growth: "社融",
    SHIBOR: "SHIBOR",
    CN10Y: "CN10Y",
    US10Y: "US10Y",
    USD_CNH_offshore: "USD/CNH",
    PMI: "PMI",
    CPI: "CPI",
    PPI: "PPI",
    PE_percentile: "PE百分位",
    PB_percentile: "PB百分位",
    ERP: "ERP",
  };
  setText("macroContextRows", integerText(macroContextSummary.row_count));
  setText("macroContextScoreCoverage", percentText(macroScoreCoverage.coverage_rate));
  setText(
    "macroContextTimeSafe",
    macroContextTimeSafety.release_and_effective_lte_signal_date === true
      ? `通过 · ${integerText(macroContextTimeSafety.violation_count)} 违规`
      : "需检查"
  );
  setText(
    "macroContextValuationCoverage",
    `${integerText(valuationScoreCoverage.available_count)} / ${integerText(macroContextSummary.row_count)}`
  );
  const macroCoverageFields = [
    "macro_score",
    "credit_score",
    "economy_score",
    "external_score",
    "M1_growth",
    "M2_growth",
    "social_financing_growth",
    "PMI",
    "CPI",
    "PPI",
    "US10Y",
    "USD_CNH_offshore",
    "PE_percentile",
    "PB_percentile",
    "ERP",
  ];
  setHtml("macroContextCoverage", macroCoverageFields
    .map((field) => {
      const item = macroContextCoverage[field] || {};
      return `
        <div class="alpha-source-row">
          <span>${macroContextFieldLabels[field] || field}</span>
          <strong>${integerText(item.available_count)} / ${integerText(macroContextSummary.row_count)} · ${percentText(item.coverage_rate)}</strong>
        </div>
      `;
    })
    .join(""));
  const macroSamples = macroContextHistory.sample_rows || (macroContextHistory.rows || []).slice(-5);
  setHtml("macroContextSamples", macroSamples
    .map((row) => {
      const ctx = row.macro_context || {};
      return `
        <div class="duration-row">
          <span>${toIsoDate(row.date)} · ${escapeHtml(ctx.macro_state || "--")}</span>
          <strong>宏观 ${fixedText(ctx.macro_score, 1)} / 信用 ${fixedText(ctx.credit_score, 1)} / 景气 ${fixedText(ctx.economy_score, 1)}</strong>
          <em>M2 ${fixedText(ctx.M2_growth, 2)} · PMI ${fixedText(ctx.PMI, 1)} · 估值 ${fixedText(ctx.valuation_score, 1)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "macroContextConclusion",
    macroContextHistory.metadata
      ? `V5.7 已按 release/effective 日期生成历史宏观上下文：${macroContextSummary.key_read || "宏观历史上下文已生成"} 宏观分覆盖 ${percentText(macroScoreCoverage.coverage_rate)}，时间安全违规 ${integerText(macroContextTimeSafety.violation_count)} 个；PE/PB/ERP 本地历史缺失保持 null。该层不改规则、不生成仓位或交易。`
      : "V5.7 宏观历史上下文尚未生成。"
  );

  setText("macroEnhancedRows", integerText(macroEnhancedSummary.balanced_usable_rows));
  setText("macroEnhancedValue", macroEnhancedValueLabel(macroEnhancedSummary.macro_added_explanatory_value));
  setText(
    "macroEnhancedTimeSafe",
    macroEnhancedTimeSafety.feature_release_or_source_lte_signal_date === true
      ? `通过 · ${integerText(macroEnhancedTimeSafety.violation_count)} 违规`
      : "需检查"
  );
  setText("macroEnhancedReady", macroEnhancedSummary.ready_for_rule_change === true ? "可变更" : "不可变更");
  setHtml("macroEnhancedCandidates", ["BALANCED_RISK", "BALANCED_OPPORTUNITY", "BALANCED_NEUTRAL"]
    .map((candidate) => {
      const item = macroEnhancedAttribution[candidate] || {};
      return `
        <div class="alpha-source-row">
          <span>${balancedCandidateLabel(candidate)} · 置信 ${balancedCandidateQualityLabel(item.confidence)}</span>
          <strong>${integerText(item.sample_count)} 次 · 失败 ${percentText(item.future_failure_rate)} / 机会 ${percentText(item.future_opportunity_rate)}</strong>
        </div>
      `;
    })
    .join(""));
  setHtml("macroEnhancedDrivers", ["BALANCED_RISK", "BALANCED_OPPORTUNITY", "BALANCED_NEUTRAL"]
    .map((candidate) => {
      const item = macroEnhancedAttribution[candidate] || {};
      return `
        <div class="duration-row">
          <span>${balancedCandidateLabel(candidate)}</span>
          <strong>${macroEnhancedDriverText(item.drivers || {})}</strong>
          <em>${macroEnhancedEvidenceText(item)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "macroEnhancedConclusion",
    macroEnhanced.metadata
      ? `V5.8 固定 V5.4 候选标签做宏观增强归因：${macroEnhancedSummary.key_read || "宏观增强归因已生成"} 时间安全违规 ${integerText(macroEnhancedTimeSafety.violation_count)} 个，复核项 ${integerText(macroEnhancedSummary.review_item_count)} 个；该层只做诊断，不改 mapper、不新增正式状态、不输出仓位或交易。`
      : "V5.8 宏观增强 BALANCED 归因尚未生成。"
  );

  setText("contextStateRows", integerText(contextStateSummary.balanced_usable_rows));
  setText("contextStateQuality", contextStateQualityLabel(contextStateSummary.candidate_quality_status));
  setText(
    "contextStateTimeSafe",
    contextStateTimeSafety.feature_release_or_source_lte_signal_date === true
      ? `通过 · ${integerText(contextStateTimeSafety.violation_count)} 违规`
      : "需检查"
  );
  setText("contextStateReady", contextStateSummary.ready_for_mapper_change === true ? "可变更" : "不可变更");
  setHtml("contextStateList", ["BALANCED_RECOVERY", "BALANCED_STRUCTURAL_OPPORTUNITY", "BALANCED_RISK", "BALANCED_NEUTRAL"]
    .map((stateName) => {
      const item = contextStateQuality[stateName] || {};
      return `
        <div class="alpha-source-row">
          <span>${contextStateLabel(stateName)} · 置信 ${contextStateQualityLabel(item.confidence)} · 稳定 ${contextStateQualityLabel(item.stability?.label)}</span>
          <strong>${integerText(item.sample_count)} 次 · 风险 ${percentText(item.future_risk_rate)} / 机会 ${percentText(item.future_opportunity_rate)}</strong>
        </div>
      `;
    })
    .join(""));
  setHtml("contextStateSeparation", [
    {
      label: "风险型均衡",
      status: contextStateSeparationReview.risk_state_separation,
      metric: contextStateSeparationReview.risk_state_future_risk_lift,
      base: contextStateSeparationReview.overall_future_risk_rate,
    },
    {
      label: "结构机会型均衡",
      status: contextStateSeparationReview.opportunity_state_separation,
      metric: contextStateSeparationReview.structural_opportunity_future_opportunity_lift,
      base: contextStateSeparationReview.overall_future_opportunity_rate,
    },
  ]
    .map((item) => `
      <div class="duration-row">
        <span>${item.label}</span>
        <strong>${contextStateQualityLabel(item.status)}</strong>
        <em>相对总体抬升 ${signedRatioText(item.metric)} · 总体 ${percentText(item.base)}</em>
      </div>
    `)
    .join(""));
  setText(
    "contextStateConclusion",
    contextStateAudit.metadata
      ? `V5.9 只设计研究候选状态：${contextStateSummary.key_read || "状态模型审计已生成"} 风险分离 ${contextStateQualityLabel(contextStateSeparationReview.risk_state_separation)}，机会分离 ${contextStateQualityLabel(contextStateSeparationReview.opportunity_state_separation)}，复核项 ${integerText(contextStateSummary.review_item_count)} 个；不新增正式状态、不改 mapper、不输出仓位或交易。`
      : "V5.9 BALANCED 状态模型设计审计尚未生成。"
  );

  setText("gradientRows", integerText(gradientSummary.balanced_usable_rows));
  setText("gradientRiskSeparation", contextStateQualityLabel(gradientSeparation.risk_gradient_separation));
  setText("gradientOpportunitySeparation", contextStateQualityLabel(gradientSeparation.opportunity_gradient_separation));
  setText("gradientReady", gradientSummary.ready_for_mapper_change === true ? "可变更" : "不可变更");
  setHtml("gradientRiskBuckets", ["high_risk", "medium_risk", "low_risk"]
    .map((bucket) => {
      const item = riskGradientBuckets[bucket] || {};
      return `
        <div class="alpha-source-row">
          <span>${riskGradientBucketLabel(bucket)} · 置信 ${contextStateQualityLabel(item.confidence)}</span>
          <strong>${integerText(item.sample_count)} 次 · 风险 ${percentText(item.future_failure_rate)} / 机会 ${percentText(item.future_opportunity_rate)}</strong>
        </div>
      `;
    })
    .join(""));
  setHtml("gradientOpportunityBuckets", ["high_opportunity", "medium_opportunity", "low_opportunity"]
    .map((bucket) => {
      const item = opportunityGradientBuckets[bucket] || {};
      return `
        <div class="duration-row">
          <span>${opportunityGradientBucketLabel(bucket)}</span>
          <strong>${integerText(item.sample_count)} 次 · 机会 ${percentText(item.future_opportunity_rate)}</strong>
          <em>风险 ${percentText(item.future_failure_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "gradientConclusion",
    gradientAnalysis.metadata
      ? `V5.10 连续梯度审计：风险梯度 ${contextStateQualityLabel(gradientSeparation.risk_gradient_separation)}，高风险桶失败率较总体抬升 ${signedRatioText(gradientSeparation.high_risk_bucket_failure_lift)}；机会梯度 ${contextStateQualityLabel(gradientSeparation.opportunity_gradient_separation)}，高机会桶机会率抬升 ${signedRatioText(gradientSeparation.high_opportunity_bucket_opportunity_lift)}。该层只做研究，不改 mapper、不输出仓位或交易。`
      : "V5.10 BALANCED 风险/机会梯度审计尚未生成。"
  );

  setText("robustnessOverallLift", signedRatioText(riskRobustnessSummary.overall_high_risk_lift));
  setText("robustnessConsistency", robustnessConsistencyLabel(riskRobustnessSummary.period_consistency));
  setText(
    "robustnessEvaluated",
    `${integerText(riskRobustnessStats.evaluated_period_count)} 个 · 正 ${integerText(riskRobustnessStats.positive_period_count)} / 负 ${integerText(riskRobustnessStats.negative_period_count)} / 不足 ${integerText(riskRobustnessStats.insufficient_period_count)}`
  );
  setText("robustnessReady", riskRobustnessSummary.ready_for_mapper_change === true ? "可变更" : "不可变更");
  setHtml("robustnessPeriods", (Array.isArray(riskRobustnessPeriods) ? riskRobustnessPeriods : [])
    .map((period) => `
      <div class="duration-row">
        <span>${escapeHtml(period.period || "--")} · ${robustnessPeriodStatusLabel(period.status)}</span>
        <strong>${integerText(period.sample_count)} 样本 · 高风险 ${integerText(period.high_risk_sample_count)} 个</strong>
        <em>抬升 ${signedRatioText(period.high_risk_lift)} · 总体风险 ${percentText(period.overall_failure_rate)}</em>
      </div>
    `)
    .join(""));
  setHtml("robustnessBuckets", ["high_risk", "medium_risk", "low_risk"]
    .map((bucket) => {
      const item = riskRobustnessBuckets[bucket] || {};
      return `
        <div class="alpha-source-row">
          <span>${riskGradientBucketLabel(bucket)}</span>
          <strong>${integerText(item.sample_count)} 次 · 失败率 ${percentText(item.failure_rate)}</strong>
        </div>
      `;
    })
    .join(""));
  setText(
    "robustnessConclusion",
    riskRobustness.metadata
      ? `V5.11 固定 V5.10 风险梯度复核：总体高风险桶风险抬升 ${signedRatioText(riskRobustnessSummary.overall_high_risk_lift)}，但阶段一致性为 ${robustnessConsistencyLabel(riskRobustnessSummary.period_consistency)}。结论：${robustnessConclusionLabel(riskRobustnessSummary.conclusion)}，仍只做研究，不进入 mapper 或仓位规则。`
      : "V5.11 风险梯度稳健性审计尚未生成。"
  );

  const topCondition = riskConditionSummary.strongest_positive_condition || {};
  const positiveConditions = riskConditionSummary.top_positive_conditions || [];
  const negativeConditions = riskConditionSummary.negative_conditions || [];
  setText("conditionPositive", integerText(riskConditionSummary.positive_condition_count));
  setText("conditionInsufficient", integerText(riskConditionSummary.insufficient_condition_count));
  setText(
    "conditionTop",
    topCondition.condition
      ? `${conditionDisplayLabel(topCondition.condition)} · ${signedRatioText(topCondition.high_risk_lift)}`
      : "--"
  );
  setText("conditionReady", riskConditionSummary.ready_for_mapper_change === true ? "可变更" : "不可变更");
  setHtml("conditionPositiveList", (Array.isArray(positiveConditions) ? positiveConditions : [])
    .map((item) => `
      <div class="alpha-source-row">
        <span>${conditionDisplayLabel(item.condition)} · ${conditionEdgeLabel(item.risk_gradient_edge)} · 置信 ${contextStateQualityLabel(item.confidence)}</span>
        <strong>${integerText(item.sample_count)} 样本 · 高风险 ${integerText(item.high_risk_sample_count)} 个 · 抬升 ${signedRatioText(item.high_risk_lift)}</strong>
      </div>
    `)
    .join(""));
  setHtml("conditionNegativeList", (Array.isArray(negativeConditions) ? negativeConditions : [])
    .map((item) => `
      <div class="duration-row">
        <span>${conditionDisplayLabel(item.condition)} · ${conditionEdgeLabel(item.risk_gradient_edge)}</span>
        <strong>${integerText(item.sample_count)} 样本 · 高风险 ${integerText(item.high_risk_sample_count)} 个</strong>
        <em>抬升 ${signedRatioText(item.high_risk_lift)}</em>
      </div>
    `)
    .join(""));
  setText(
    "conditionConclusion",
    riskCondition.metadata
      ? `V5.12 条件验证：发现 ${integerText(riskConditionSummary.positive_condition_count)} 个正向条件，最强为 ${conditionDisplayLabel(topCondition.condition)}；但 ${integerText(riskConditionSummary.insufficient_condition_count)} 个条件样本不足。结论：${conditionConclusionLabel(riskConditionSummary.conclusion)}，只能解释“何时更有效”，不能形成仓位规则。`
      : "V5.12 风险梯度条件有效性审计尚未生成。"
  );

  setText("candidateCount", integerText(riskCandidatesSummary.candidate_count));
  setText("candidatePrimary", integerText(riskCandidatesSummary.primary_research_candidate_count));
  setText("candidateReadyCount", integerText(riskCandidatesSummary.ready_for_rule_count));
  setText("candidateReady", riskCandidatesSummary.ready_for_mapper_change === true ? "可变更" : "不可变更");
  setHtml("candidateRuleList", (Array.isArray(riskCandidateRules) ? riskCandidateRules : [])
    .map((item) => `
      <div class="alpha-source-row">
        <span>${escapeHtml(item.rule_id || "--")} · ${conditionDisplayLabel(item.candidate)} · ${candidateTierLabel(item.research_tier)} · 稳定 ${robustnessConsistencyLabel(item.stability?.label)}</span>
        <strong>${integerText(item.sample_count)} 样本 · 触发 ${integerText(item.trigger_sample_count)} 个 · 抬升 ${signedRatioText(item.high_risk_lift)} · 可规则化 ${item.ready_for_rule === true ? "是" : "否"}</strong>
      </div>
    `)
    .join(""));
  setText(
    "candidateConclusion",
    riskCandidates.metadata
      ? `V5.13 最小候选审计：从 V5.12 正向条件压缩出 ${integerText(riskCandidatesSummary.candidate_count)} 个候选，其中 ${integerText(riskCandidatesSummary.primary_research_candidate_count)} 个可继续重点研究，但 ${integerText(riskCandidatesSummary.ready_for_rule_count)} 个可规则化。结论：${candidateConclusionLabel(riskCandidatesSummary.conclusion)}。`
      : "V5.13 最小风险候选审计尚未生成。"
  );

  const modelB = policyValidationModels.model_b_v5_1_plus_risk_gradient_flag || {};
  const modelC = policyValidationModels.model_c_v5_1_plus_primary_candidate_context || {};
  setText("policyValidationRows", integerText(policyValidationSummary.joined_sample_count));
  setText("policyValidationCapture", percentText(modelB.high_risk_event_capture_rate));
  setText("policyValidationFalseWarning", percentText(modelB.false_warning_rate));
  setText(
    "policyValidationReady",
    policyValidationSummary.ready_for_mapper_change === true || policyValidationSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("policyValidationModels", [
    "model_a_baseline_v5_1",
    "model_b_v5_1_plus_risk_gradient_flag",
    "model_c_v5_1_plus_primary_candidate_context",
  ]
    .map((modelId) => {
      const item = policyValidationModels[modelId] || {};
      return `
        <div class="duration-row">
          <span>${policyModelLabel(modelId)} · ${policyValidationStatusLabel(item.status)}</span>
          <strong>提示 ${integerText(item.diagnostic_flag_count)} 次 · 捕获 ${percentText(item.high_risk_event_capture_rate)}</strong>
          <em>误警 ${percentText(item.false_warning_rate)} · 冲突覆盖 ${percentText(item.contradiction_capture_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "policyValidationConclusion",
    policyValidation.metadata
      ? `V6.1 固定 V5.1 暴露模拟做诊断叠加：B/C 风险提示集合${policyValidationSummary.model_b_c_flag_sets_identical ? "相同" : "不同"}，捕获率 ${percentText(modelB.high_risk_event_capture_rate)}，误警率 ${percentText(modelB.false_warning_rate)}。结论：${policyValidationStatusLabel(policyValidationSummary.policy_validation_status)}，不改 mapper、不改 exposure。`
      : "V6.1 暴露策略诊断验证尚未生成。"
  );

  setText("decisionRows", integerText(decisionSummary.joined_sample_count));
  setText("decisionRiskSeparation", contextStateQualityLabel(decisionSummary.risk_separation));
  setText("decisionOpportunitySeparation", contextStateQualityLabel(decisionSummary.opportunity_separation));
  setText(
    "decisionReady",
    decisionSummary.ready_for_mapper_change === true || decisionSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("decisionModeList", [
    "FULL_PARTICIPATION",
    "SELECTIVE_PARTICIPATION",
    "PROTECTED_PARTICIPATION",
    "DEFENSIVE",
    "WAIT",
  ]
    .map((mode) => {
      const item = decisionModes[mode] || {};
      return `
        <div class="duration-row">
          <span>${decisionModeLabel(mode)}</span>
          <strong>${integerText(item.sample_count)} 样本 · 风险 ${percentText(item.future_high_risk_rate)}</strong>
          <em>机会 ${percentText(item.future_opportunity_rate)} · 冲突 ${percentText(item.contradiction_row_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "decisionConclusion",
    decisionAudit.metadata
      ? `V6.2 决策上下文审计：保护/防守/等待组相对参与组风险抬升 ${signedRatioText(decisionSeparation.caution_vs_participation_risk_lift)}，机会分离 ${signedRatioText(decisionSeparation.participation_vs_caution_opportunity_lift)}。结论：风险/机会分离均弱，不改 mapper、不改 exposure。`
      : "V6.2 暴露决策上下文审计尚未生成。"
  );

  setText("scoreRows", integerText(contextScoreSummary.joined_sample_count));
  setText("scoreProtectionSeparation", contextStateQualityLabel(contextScoreSummary.protection_separation));
  setText("scoreParticipationSeparation", contextStateQualityLabel(contextScoreSummary.participation_separation));
  setText(
    "scoreReady",
    contextScoreSummary.ready_for_mapper_change === true || contextScoreSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("scoreBucketList", ["high", "medium", "low"]
    .map((bucket) => {
      const protection = protectionBuckets[bucket] || {};
      const participation = participationBuckets[bucket] || {};
      return `
        <div class="duration-row">
          <span>${bucket === "high" ? "高分" : bucket === "medium" ? "中分" : "低分"}</span>
          <strong>保护: ${integerText(protection.sample_count)} 样本 · 风险 ${percentText(protection.future_high_risk_rate)}</strong>
          <em>参与: ${integerText(participation.sample_count)} 样本 · 机会 ${percentText(participation.future_opportunity_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "scoreConclusion",
    contextScoreAudit.metadata
      ? `V6.3 连续评分审计：高保护分风险抬升 ${signedRatioText(contextScoreSeparation.high_protection_risk_lift)}，高参与分机会抬升 ${signedRatioText(contextScoreSeparation.high_participation_opportunity_lift)}。结论：保护分有可见风险分离，参与分仍弱，暂不改 mapper、不改 exposure。`
      : "V6.3 连续暴露上下文评分尚未生成。"
  );

  setText("protectionValidationRows", integerText(protectionValidationSummary.joined_sample_count));
  setText("protectionValidationLift", signedRatioText(protectionValidationSummary.model_b_protection_high_risk_lift));
  setText("protectionValidationConsistency", robustnessConsistencyLabel(protectionValidationSummary.protection_phase_consistency));
  setText(
    "protectionValidationReady",
    protectionValidationSummary.ready_for_mapper_change === true || protectionValidationSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("protectionValidationModels", [
    "model_a_risk_gradient_bucket",
    "model_b_protection_score_bucket",
    "model_c_risk_gradient_plus_protection_score",
  ]
    .map((modelId) => {
      const item = protectionValidationModels[modelId] || {};
      return `
        <div class="duration-row">
          <span>${protectionValidationModelLabel(modelId)} · 高桶 ${integerText(item.high_group_sample_count)} 样本</span>
          <strong>风险 ${percentText(item.high_group_high_risk_rate)} · 抬升 ${signedRatioText(item.high_group_high_risk_lift)}</strong>
          <em>回撤 ${percentText(item.high_group_drawdown_event_rate)} · 误警 ${percentText(item.false_warning_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setHtml("protectionValidationPhases", protectionValidationPhases
    .map((phase) => {
      const item = phase.model_b_protection_score || {};
      return `
        <div class="alpha-source-row">
          <span>${marketPhaseLabel(phase.market_phase)} · ${robustnessPeriodStatusLabel(item.status)}</span>
          <strong>${integerText(phase.sample_count)} 样本 · 高保护 ${integerText(item.high_sample_count)} 个 · 风险抬升 ${signedRatioText(item.high_risk_lift)}</strong>
        </div>
      `;
    })
    .join(""));
  setText(
    "protectionValidationConclusion",
    protectionValidation.metadata
      ? `V6.4 保护分验证：保护分高桶风险抬升 ${signedRatioText(protectionValidationSummary.model_b_protection_high_risk_lift)}，阶段一致性 ${robustnessConsistencyLabel(protectionValidationSummary.protection_phase_consistency)}；原始风险梯度抬升 ${signedRatioText(protectionValidationSummary.model_a_high_risk_lift)}，双高组合抬升 ${signedRatioText(protectionValidationSummary.model_c_both_high_risk_lift)}。保护分可作为风险解释线索，但仍不可变更 mapper/exposure。`
      : "V6.4 保护分稳健性验证尚未生成。"
  );

  setText("twoAxisRows", integerText(twoAxisSummary.joined_sample_count));
  setText("twoAxisRiskSpread", signedRatioText(twoAxisSummary.two_axis_risk_spread));
  setText("twoAxisOpportunitySpread", signedRatioText(twoAxisSummary.two_axis_opportunity_spread));
  setText(
    "twoAxisReady",
    twoAxisSummary.ready_for_mapper_change === true || twoAxisSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("twoAxisQuadrants", [
    "PARTICIPATE",
    "PROTECT_BUT_PARTICIPATE",
    "WAIT",
    "AVOID",
  ]
    .map((label) => {
      const item = twoAxisMetrics[label] || {};
      return `
        <div class="duration-row">
          <span>${twoAxisLabel(label)} · ${integerText(item.sample_count)} 样本</span>
          <strong>风险 ${percentText(item.future_high_risk_rate)} · 机会 ${percentText(item.future_opportunity_rate)}</strong>
          <em>回撤 ${percentText(item.drawdown_event_rate)} · 矛盾 ${percentText(item.contradiction_rate)}</em>
        </div>
      `;
    })
    .join(""));
  setHtml("twoAxisComparison", [
    ["相对 V5.1 暴露等级风险区分", twoAxisComparison.two_axis_minus_exposure_risk_spread],
    ["相对 V6.2 decision mode 风险区分", twoAxisComparison.two_axis_minus_decision_risk_spread],
    ["相对 V5.1 暴露等级机会区分", twoAxisComparison.two_axis_minus_exposure_opportunity_spread],
    ["相对 V6.2 decision mode 机会区分", twoAxisComparison.two_axis_minus_decision_opportunity_spread],
  ]
    .map(([label, value]) => `
      <div class="alpha-source-row">
        <span>${label}</span>
        <strong>${signedRatioText(value)}</strong>
      </div>
    `)
    .join(""));
  setText(
    "twoAxisConclusion",
    twoAxisValidation.metadata
      ? `V6.5 双轴验证：风险区分 ${signedRatioText(twoAxisSummary.two_axis_risk_spread)}，机会区分 ${signedRatioText(twoAxisSummary.two_axis_opportunity_spread)}；参与象限机会抬升仅 ${signedRatioText(twoAxisSummary.participate_opportunity_lift)}，保护参与象限风险抬升 ${signedRatioText(twoAxisSummary.protect_but_participate_risk_lift)}。结论：风险轴可见，机会轴仍弱，不改 mapper、不改 exposure。`
      : "V6.5 风险-机会双轴验证尚未生成。"
  );

  setText("contextAttributionRows", integerText(contextAttributionSummary.joined_sample_count));
  setText("contextAttributionRiskLeader", contextLayerLabel(contextAttributionSummary.risk_leader));
  setText("contextAttributionRetained", integerText(contextAttributionSummary.retained_layer_count));
  setText(
    "contextAttributionReady",
    contextAttributionSummary.ready_for_mapper_change === true || contextAttributionSummary.ready_for_exposure_change === true
      ? "可变更"
      : "不可变更"
  );
  setHtml("contextAttributionLayers", contextAttributionLayers
    .map((layer) => `
      <div class="duration-row">
        <span>${contextLayerLabel(layer.layer_id)} · ${contextLayerStatusLabel(layer.status)}</span>
        <strong>风险 ${signedRatioText(layer.risk_spread?.spread)} · 机会 ${signedRatioText(layer.opportunity_spread?.spread)}</strong>
        <em>${contextLayerRetentionLabel(layer.retention_recommendation)} · ${escapeHtml(layer.top_group || "--")} 占比 ${percentText(layer.top_group_share)}</em>
      </div>
    `)
    .join(""));
  setText(
    "contextAttributionConclusion",
    contextAttribution.metadata
      ? `V6.6 信息层归因：风险领先层为${contextLayerLabel(contextAttributionSummary.risk_leader)}，区分 ${signedRatioText(contextAttributionSummary.risk_leader_spread)}；建议保留 ${integerText(contextAttributionSummary.retained_layer_count)} 层：风险梯度、保护分、双轴上下文。V5.1 暴露等级只作基线，不改 mapper、不改 exposure。`
      : "V6.6 上下文信息层归因尚未生成。"
  );

  const opportunityCategoryCounts = opportunityFoundationSummary.category_counts || {};
  const opportunityResearchCoverage = opportunityFoundationCoverage.research_proxy_history || {};
  const opportunityTradableCoverage = opportunityFoundationCoverage.tradable_history || {};
  const opportunityProxyRows = opportunityFoundationRows.filter((row) => row.research_proxy?.has_proxy);
  const opportunityDirectRows = opportunityFoundationRows.filter((row) => !row.research_proxy?.has_proxy);
  setText(
    "opportunityFoundationAssets",
    opportunityFoundationSummary.asset_count
      ? `${integerText(opportunityFoundationSummary.asset_count)} 个 ETF`
      : "--"
  );
  setText(
    "opportunityFoundationProxy",
    opportunityFoundationSummary.research_proxy_assets
      ? `${integerText(opportunityFoundationSummary.research_proxy_assets)} 个资产 / ${integerText(opportunityFoundationSummary.research_proxy_count)} 个代理`
      : "--"
  );
  setText(
    "opportunityFoundationCoverage",
    opportunityResearchCoverage.coverage_start
      ? `${toIsoDate(opportunityResearchCoverage.coverage_start)} 起`
      : "--"
  );
  setText(
    "opportunityFoundationBoundary",
    opportunityFoundationSummary.ready_for_scoring === false &&
      opportunityFoundationSummary.ready_for_ranking === false &&
      opportunityFoundationSummary.ready_for_allocation === false &&
      opportunityFoundationSummary.ready_for_trade === false
      ? "不可评分/排名/配置/交易"
      : "需复核"
  );
  setHtml("opportunityFoundationCategories", Object.entries(opportunityCategoryCounts)
    .map(([category, count]) => `
      <div class="duration-row">
        <span>${assetCategoryLabel(category)}</span>
        <strong>${integerText(count)} 个</strong>
        <em>${category === "industry" ? "主要承接结构性牛市主线观察" : "作为风格或宽基对照"}</em>
      </div>
    `)
    .join(""));
  setHtml("opportunityFoundationSamples", [
    ...opportunityProxyRows.slice(0, 5).map((row) => `
      <div>
        <strong>${escapeHtml(row.asset_code)} ${escapeHtml(row.asset_name)}</strong>
        <span>${assetCategoryLabel(row.category)} · 代理 ${escapeHtml(row.research_proxy?.code || "--")} ${escapeHtml(row.research_proxy?.name || "--")}</span>
      </div>
    `),
    opportunityDirectRows.length
      ? `<div><strong>直接 ETF 历史</strong><span>${integerText(opportunityDirectRows.length)} 个资产未配置长历史代理，只按真实 ETF 历史研究。</span></div>`
      : "",
  ].join(""));
  setText(
    "opportunityFoundationConclusion",
    opportunityFoundation.metadata
      ? `V7.1 机会研究基础层：${opportunityFoundationReadinessLabel(opportunityFoundationSummary.readiness)}。研究代理覆盖 ${toIsoDate(opportunityResearchCoverage.coverage_start)} 至 ${toIsoDate(opportunityResearchCoverage.coverage_end)}；真实 ETF 可交易历史公共覆盖 ${toIsoDate(opportunityTradableCoverage.coverage_start)} 至 ${toIsoDate(opportunityTradableCoverage.coverage_end)}，存在 ${integerText(opportunityTradableCoverage.target_blocker_count)} 个覆盖阻塞。该层只建立研究对象和数据口径，不输出机会分、排名、仓位或交易。`
      : "V7.1 机会研究基础层尚未生成。"
  );

  const opportunityFeatureSourceCounts = opportunityFeaturesSummary.source_counts || {};
  const opportunityFeatureGroups = opportunityFeaturesSummary.feature_groups || [];
  const opportunityFeatureCompleteness = opportunityFeaturesSummary.feature_completeness || {};
  setText("opportunityFeaturesAsOf", toIsoDate(opportunityFeaturesSummary.resolved_as_of));
  setText(
    "opportunityFeaturesSources",
    opportunityFeaturesSummary.asset_count
      ? `${integerText(opportunityFeaturesSummary.asset_count)} 个 · ETF ${integerText(opportunityFeatureSourceCounts.etf || 0)} / 代理 ${integerText(opportunityFeatureSourceCounts.research_proxy || 0)}`
      : "--"
  );
  setText(
    "opportunityFeaturesGroups",
    opportunityFeatureGroups.length ? `${integerText(opportunityFeatureGroups.length)} 组` : "--"
  );
  setText(
    "opportunityFeaturesBoundary",
    opportunityFeaturesSummary.ready_for_scoring === false &&
      opportunityFeaturesSummary.ready_for_ranking === false &&
      opportunityFeaturesSummary.ready_for_allocation === false &&
      opportunityFeaturesSummary.ready_for_trade === false
      ? "不可评分/排名/配置/交易"
      : "需复核"
  );
  setHtml("opportunityFeaturesCompleteness", opportunityFeatureGroups
    .map((group) => {
      const item = opportunityFeatureCompleteness[group] || {};
      return `
        <div class="duration-row">
          <span>${opportunityFeatureGroupLabel(group)}</span>
          <strong>${percentText(item.coverage)}</strong>
          <em>${integerText(item.available_fields)} / ${integerText(item.total_fields)} 个字段可用</em>
        </div>
      `;
    })
    .join(""));
  setHtml("opportunityFeaturesSamples", opportunityFeaturesRows
    .map((row) => {
      const source = row.source || {};
      const features = row.features || {};
      const return60 = features.momentum?.return_60d?.value;
      const relHs300 = features.relative_strength?.relative_return_60d_vs_hs300?.value;
      const drawdown = features.risk?.max_drawdown_120d?.value;
      return `
        <div>
          <strong>${escapeHtml(row.asset_code)} ${escapeHtml(row.asset_name)}</strong>
          <span>${assetCategoryLabel(row.asset_category)} · ${escapeHtml(source.source_kind || "--")} ${escapeHtml(source.source || "--")} · 60日 ${signedRatioText(return60)} · 相对沪深300 ${signedRatioText(relHs300)} · 120日回撤 ${signedRatioText(drawdown)}</span>
        </div>
      `;
    })
    .join(""));
  setText(
    "opportunityFeaturesConclusion",
    opportunityFeatures.metadata
      ? `V7.2 特征层在 ${toIsoDate(opportunityFeaturesSummary.resolved_as_of)} 统一日期生成 ${integerText(opportunityFeatureGroups.length)} 类字段：动量、相对强弱、趋势、风险、结构。V6 上下文只作为元数据引用，不 join 到资产特征，不参与评分或排名；时间安全：${opportunityFeaturesTimeSafety.future_labels_used === false ? "未使用未来标签" : "需复核"}。`
      : "V7.2 机会研究特征层尚未生成。"
  );

  const proxyStatusCounts = opportunityValidationSummary.research_proxy_status_counts || {};
  const etfStatusCounts = opportunityValidationSummary.tradable_etf_status_counts || {};
  const statusText = (counts) => ["visible", "weak", "flat", "insufficient"]
    .filter((key) => counts[key])
    .map((key) => `${opportunityValidationStatusLabel(key)} ${integerText(counts[key])}`)
    .join(" / ") || "--";
  setText(
    "opportunityValidationScope",
    opportunityValidationSummary.feature_count
      ? `${integerText(opportunityValidationSummary.feature_count)} 特征 × ${integerText((opportunityValidationSummary.horizons || []).length)} horizon`
      : "--"
  );
  setText("opportunityValidationDates", integerText(opportunityValidationSummary.context_observation_count));
  setText("opportunityValidationProxy", statusText(proxyStatusCounts));
  setText("opportunityValidationEtf", statusText(etfStatusCounts));
  setHtml("opportunityValidationStatus", [
    ["Proxy", proxyStatusCounts],
    ["真实 ETF", etfStatusCounts],
  ].map(([label, counts]) => `
    <div class="duration-row">
      <span>${label}</span>
      <strong>${statusText(counts)}</strong>
      <em>IC 有效性审计状态，不是资产排名</em>
    </div>
  `).join(""));
  setHtml("opportunityValidationSamples", opportunityValidationSamples
    .map((item) => `
      <div>
        <strong>${escapeHtml(item.feature_key)} · ${integerText(item.horizon_sessions)}日</strong>
        <span>Proxy IC ${signedFixedText(item.research_proxy?.mean_ic, 3)}（${opportunityValidationStatusLabel(item.research_proxy?.status)}） · ETF IC ${signedFixedText(item.tradable_etf?.mean_ic, 3)}（${opportunityValidationStatusLabel(item.tradable_etf?.status)}）</span>
      </div>
    `)
    .join(""));
  setText(
    "opportunityValidationConclusion",
    opportunityValidation.metadata
      ? `V7.3 固定 V7.2 字段做 IC 审计：共 ${integerText(opportunityValidationSummary.result_count)} 条 feature × horizon 结果。多数结果仍为平坦或偏弱，说明当前只能用于研究归因，还不能进入机会评分。时间安全：${opportunityValidationTimeSafety.forward_returns_used_only_as_validation_labels ? "未来收益只作验证标签" : "需复核"}。`
      : "V7.3 机会特征有效性审计尚未生成。"
  );

  const retentionCounts = opportunityFeatureAttributionSummary.retention_counts || {};
  const regimeConsistencyCounts = opportunityFeatureAttributionSummary.regime_consistency_counts || {};
  const retentionSummaryText = ["research_candidate", "watch", "reject_for_now", "insufficient"]
    .filter((key) => retentionCounts[key])
    .map((key) => `${opportunityRetentionLabel(key)} ${integerText(retentionCounts[key])}`)
    .join(" / ") || "--";
  const regimeSummaryText = ["consistent_context_signal", "single_context_signal", "mixed_or_conflicting_context_signal", "no_regime_signal"]
    .filter((key) => regimeConsistencyCounts[key])
    .map((key) => `${opportunityRegimeConsistencyLabel(key)} ${integerText(regimeConsistencyCounts[key])}`)
    .join(" / ") || "--";
  setText("opportunityAttributionRows", integerText(opportunityFeatureAttributionSummary.attribution_count));
  setText("opportunityAttributionRetention", retentionSummaryText);
  setText("opportunityAttributionRegime", regimeSummaryText);
  setText(
    "opportunityAttributionBoundary",
    opportunityFeatureAttributionSummary.ready_for_scoring === false &&
      opportunityFeatureAttributionSummary.ready_for_ranking === false &&
      opportunityFeatureAttributionSummary.ready_for_allocation === false &&
      opportunityFeatureAttributionSummary.ready_for_trade === false
      ? "不可评分/排名/配置/交易"
      : "需复核"
  );
  setHtml("opportunityAttributionCounts", [
    ["保留/观察", retentionSummaryText],
    ["环境一致性", regimeSummaryText],
  ].map(([label, value]) => `
    <div class="duration-row">
      <span>${label}</span>
      <strong>${value}</strong>
      <em>归因标签，不是权重或交易动作</em>
    </div>
  `).join(""));
  setHtml("opportunityAttributionSamples", opportunityFeatureAttributionSamples
    .map((item) => `
      <div>
        <strong>${escapeHtml(item.feature_key)} · ${integerText(item.horizon_sessions)}日</strong>
        <span>${opportunityRetentionLabel(item.retention)} · ${escapeHtml(item.proxy_etf_alignment || "--")} · ${opportunityRegimeConsistencyLabel(item.regime_consistency?.status)}</span>
      </div>
    `)
    .join(""));
  setText(
    "opportunityAttributionConclusion",
    opportunityFeatureAttribution.metadata
      ? `V7.4 固定 V7.3 结果做归因：${integerText(retentionCounts.research_candidate || 0)} 条暂列保留研究，${integerText(retentionCounts.watch || 0)} 条继续观察，但总体结论仍是 ${escapeHtml(opportunityFeatureAttributionSummary.conclusion || "不可进入机会评分")}。这些 retention 标签不是评分、权重、排名或交易信号。`
      : "V7.4 机会特征归因与稳定性审计尚未生成。"
  );

  const architectureReadyFlagsOff =
    opportunityArchitectureSummary.ready_for_scoring === false &&
    opportunityArchitectureSummary.ready_for_ranking === false &&
    opportunityArchitectureSummary.ready_for_allocation === false &&
    opportunityArchitectureSummary.ready_for_trade === false;
  setText(
    "opportunityArchitectureStatus",
    opportunityArchitectureSummary.freeze_status === "frozen" ? "已冻结" : "--"
  );
  setText(
    "opportunityArchitectureLayers",
    opportunityArchitectureSummary.retained_layer_count
      ? `${integerText(opportunityArchitectureSummary.retained_layer_count)} 层`
      : "--"
  );
  setText(
    "opportunityArchitectureRejected",
    opportunityArchitectureSummary.rejected_output_count
      ? `${integerText(opportunityArchitectureSummary.rejected_output_count)} 项`
      : "--"
  );
  setText("opportunityArchitectureBoundary", architectureReadyFlagsOff ? "不可评分/排名/配置/交易" : "需复核");
  setHtml("opportunityArchitectureLayerList", opportunityArchitectureLayers
    .map((layer) => `
      <div class="duration-row">
        <span>${escapeHtml(layer.version || "--")} · ${escapeHtml(layer.name || "--")}</span>
        <strong>${escapeHtml(layer.status || "--")}</strong>
        <em>${escapeHtml(layer.role || "")}</em>
      </div>
    `)
    .join(""));
  setHtml("opportunityArchitectureRejectedList", opportunityArchitectureRejected
    .map((item) => `
      <div>
        <strong>${escapeHtml(item.name || "--")} · ${escapeHtml(item.status || "--")}</strong>
        <span>${escapeHtml(item.reason || "")}</span>
      </div>
    `)
    .join(""));
  setText(
    "opportunityArchitectureConclusion",
    opportunityArchitecture.metadata
      ? `V7.5 冻结 V7 机会研究层：保留资产基础、特征、IC 验证和归因框架，但结论仍是 ${escapeHtml(opportunityArchitectureSummary.conclusion || "不可进入机会评分")}。当前证据：资产 ${integerText(opportunityArchitectureEvidence.asset_count)} 个，V7.3 验证 ${integerText(opportunityArchitectureEvidence.feature_validation_result_count)} 条，V7.4 归因 ${integerText(opportunityArchitectureEvidence.feature_attribution_count)} 条；不输出机会分、排名、Top N、配置或交易。`
      : "V7.5 机会研究层冻结摘要尚未生成。"
  );

  const researchDecisionReadyFlagsOff =
    researchDecisionSummary.ready_for_scoring === false &&
    researchDecisionSummary.ready_for_ranking === false &&
    researchDecisionSummary.ready_for_allocation === false &&
    researchDecisionSummary.ready_for_trade === false;
  const researchDecisionLabels = {
    risk_controlled_opportunity_watch: "风险约束下观察机会",
    research_context_needs_review: "研究语境需复核",
  };
  const researchPostureLabels = {
    observe_without_selection: "只观察不选择",
    review_inputs_before_use: "先复核输入",
  };
  const featureAttentionRows = researchDecisionOpportunityEvidence.feature_group_attention || [];
  setText(
    "researchDecisionContext",
    researchDecisionLabels[researchDecisionSummary.decision_context] || researchDecisionSummary.decision_context || "--"
  );
  setText(
    "researchDecisionPosture",
    researchPostureLabels[researchDecisionSummary.research_posture] || researchDecisionSummary.research_posture || "--"
  );
  setText(
    "researchDecisionOpportunity",
    researchDecisionSummary.opportunity_research_candidate_count != null
      ? `候选 ${integerText(researchDecisionSummary.opportunity_research_candidate_count)} / 观察 ${integerText(researchDecisionSummary.opportunity_watch_count)}`
      : "--"
  );
  setText("researchDecisionBoundary", researchDecisionReadyFlagsOff ? "不可评分/排名/配置/交易" : "需复核");
  setHtml("researchDecisionEvidence", [
    ["风险上下文", researchDecisionRiskEvidence.two_axis_conclusion, `风险区分 ${signedFixedText(researchDecisionRiskEvidence.two_axis_risk_spread, 3)} · 机会区分 ${signedFixedText(researchDecisionRiskEvidence.two_axis_opportunity_spread, 3)}`],
    ["风险领先层", researchDecisionRiskEvidence.risk_leader, `保护层未来高风险率 ${percentText(researchDecisionRiskEvidence.protection_overall_future_high_risk_rate)}`],
    ["机会上下文", researchDecisionOpportunityEvidence.conclusion, `特征组 ${integerText(featureAttentionRows.length)} 个，仅作为研究关注`],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "--")}</strong>
      <em>${escapeHtml(note || "")}</em>
    </div>
  `).join(""));
  setHtml("researchDecisionFeatureGroups", featureAttentionRows
    .map((row) => {
      const counts = row.retention_counts || {};
      const parts = ["research_candidate", "watch", "reject_for_now", "insufficient"]
        .filter((key) => counts[key])
        .map((key) => `${opportunityRetentionLabel(key)} ${integerText(counts[key])}`);
      return `
        <div>
          <strong>${opportunityFeatureGroupLabel(row.feature_group || "--")}</strong>
          <span>${parts.join(" / ") || "--"} · ${escapeHtml(row.interpretation || "feature group only")}</span>
        </div>
      `;
    })
    .join(""));
  setText(
    "researchDecisionConclusion",
    researchDecision.metadata
      ? `V8.1 只把冻结的 V6 风险上下文和 V7 机会归因连成研究解释：${researchDecisionLabels[researchDecisionContext.context] || researchDecisionContext.context || "--"}。风险轴可用于框架化观察，机会层仍不具备评分、排名、Top N、配置或交易条件。`
      : "V8.1 研究决策整合架构尚未生成。"
  );

  const scenarioConsistencyCounts = scenarioAuditSummary.consistency_counts || {};
  const scenarioDominantCounts = scenarioAuditSummary.dominant_context_counts || {};
  const scenarioAuditReadyFlagsOff =
    scenarioAuditSummary.ready_for_scoring === false &&
    scenarioAuditSummary.ready_for_ranking === false &&
    scenarioAuditSummary.ready_for_allocation === false &&
    scenarioAuditSummary.ready_for_trade === false;
  const consistencySummaryText = ["high", "medium", "low", "insufficient"]
    .filter((key) => scenarioConsistencyCounts[key])
    .map((key) => `${key} ${integerText(scenarioConsistencyCounts[key])}`)
    .join(" / ") || "--";
  setText(
    "scenarioAuditCoverage",
    scenarioAuditSummary.scenario_count
      ? `${integerText(scenarioAuditSummary.covered_scenario_count)} / ${integerText(scenarioAuditSummary.scenario_count)}`
      : "--"
  );
  setText("scenarioAuditConsistency", consistencySummaryText);
  setText(
    "scenarioAuditTransitions",
    scenarioAuditSummary.average_transition_rate != null ? percentText(scenarioAuditSummary.average_transition_rate) : "--"
  );
  setText("scenarioAuditBoundary", scenarioAuditReadyFlagsOff ? "不可评分/排名/配置/交易" : "需复核");
  setHtml("scenarioAuditRows", scenarioAuditRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.name || row.scenario || "--")}</span>
        <strong>${escapeHtml(row.consistency || "--")} · ${escapeHtml(row.dominant_context || "--")}</strong>
        <em>${integerText(row.observation_count)} 点 · 切换 ${percentText(row.transition_rate)} · 矛盾 ${integerText(row.contradiction_count)} · ${escapeHtml(row.interpretation || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "scenarioAuditConclusion",
    scenarioAudit.metadata
      ? `V8.2 固定 ${integerText(scenarioAuditSummary.scenario_count)} 个历史场景做解释审计：一致性 ${consistencySummaryText}，主导语境 ${Object.entries(scenarioDominantCounts).map(([key, value]) => `${key} ${integerText(value)}`).join(" / ") || "--"}。该层只暴露解释稳定性问题，不使用收益指标，也不生成策略、评分、排名或配置。`
      : "V8.2 历史情景解释审计尚未生成。"
  );

  const contradictionTypeCounts = contradictionSummary.contradiction_type_counts || {};
  const contradictionReasonCounts = contradictionSummary.possible_reason_counts || {};
  const contradictionReadyFlagsOff =
    contradictionSummary.ready_for_scoring === false &&
    contradictionSummary.ready_for_ranking === false &&
    contradictionSummary.ready_for_allocation === false &&
    contradictionSummary.ready_for_trade === false;
  const contradictionTypeText = Object.entries(contradictionTypeCounts)
    .map(([key, value]) => `${key} ${integerText(value)}`)
    .join(" / ") || "--";
  setText("contradictionFocusCount", integerText(contradictionSummary.focus_scenario_count));
  setText("contradictionAttributionCount", integerText(contradictionSummary.attribution_count));
  setText("contradictionTypeSummary", contradictionTypeText);
  setText("contradictionBoundary", contradictionReadyFlagsOff ? "不改规则/不配置/不交易" : "需复核");
  setHtml("contradictionRows", contradictionRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.name || row.scenario || "--")}</span>
        <strong>${escapeHtml(row.contradiction_type || "--")}</strong>
        <em>${escapeHtml(row.possible_reason || "--")} · 矛盾 ${integerText(row.contradiction_count)} · 切换 ${percentText(row.transition_rate)} · ${escapeHtml(row.confidence_level || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "contradictionConclusion",
    contradictionAudit.metadata
      ? `V8.3 对 ${integerText(contradictionSummary.focus_scenario_count)} 个重点场景做失败归因：${contradictionTypeText}。可能原因分布：${Object.entries(contradictionReasonCounts).map(([key, value]) => `${key} ${integerText(value)}`).join(" / ") || "--"}。该层只解释失败来源，不修改 V6/V7、不新增状态、不生成评分、配置或交易。`
      : "V8.3 研究语境矛盾归因尚未生成。"
  );

  const v8ArchitectureReadyFlagsOff =
    v8ArchitectureSummary.ready_for_scoring === false &&
    v8ArchitectureSummary.ready_for_ranking === false &&
    v8ArchitectureSummary.ready_for_allocation === false &&
    v8ArchitectureSummary.ready_for_trade === false;
  setText("v8ArchitectureStatus", v8ArchitectureSummary.freeze_status === "frozen" ? "已冻结" : "--");
  setText(
    "v8ArchitectureLayers",
    v8ArchitectureSummary.retained_layer_count ? `${integerText(v8ArchitectureSummary.retained_layer_count)} 层` : "--"
  );
  setText(
    "v8ArchitectureRejected",
    v8ArchitectureSummary.rejected_output_count ? `${integerText(v8ArchitectureSummary.rejected_output_count)} 项` : "--"
  );
  setText("v8ArchitectureBoundary", v8ArchitectureReadyFlagsOff ? "不可策略化/配置/交易" : "需复核");
  setHtml("v8ArchitectureLayerList", v8ArchitectureLayers
    .map((layer) => `
      <div class="duration-row">
        <span>${escapeHtml(layer.version || "--")} · ${escapeHtml(layer.name || "--")}</span>
        <strong>${escapeHtml(layer.status || "--")}</strong>
        <em>${escapeHtml(layer.role || "")}</em>
      </div>
    `)
    .join(""));
  setHtml("v8ArchitectureRejectedList", v8ArchitectureRejected
    .map((item) => `
      <div>
        <strong>${escapeHtml(item.name || "--")} · ${escapeHtml(item.status || "--")}</strong>
        <span>${escapeHtml(item.reason || "")}</span>
      </div>
    `)
    .join(""));
  setText(
    "v8ArchitectureConclusion",
    v8Architecture.metadata
      ? `V8.4 冻结 V8 研究解释架构：V8.1=${escapeHtml(v8ArchitectureEvidence.v8_1_decision_context || "--")}，V8.2 场景 ${integerText(v8ArchitectureEvidence.v8_2_scenario_count)} 个，一致性 ${Object.entries(v8ArchitectureEvidence.v8_2_consistency_counts || {}).map(([key, value]) => `${key} ${integerText(value)}`).join(" / ") || "--"}，V8.3 归因 ${integerText(v8ArchitectureEvidence.v8_3_attribution_count)} 条。该层不生成评分、排名、资产选择、配置、ETF 权重或交易。`
      : "V8.4 研究决策架构冻结摘要尚未生成。"
  );

  const allocationResearchReadyFlagsOff =
    allocationResearchSummary.allocation_research_ready === false &&
    allocationResearchSummary.ready_for_asset_selection === false &&
    allocationResearchSummary.ready_for_etf_mapping === false &&
    allocationResearchSummary.ready_for_weight_generation === false &&
    allocationResearchSummary.ready_for_backtest === false &&
    allocationResearchSummary.ready_for_trade === false;
  const allocationAllowedInputs = Array.isArray(allocationResearchSchema.allowed_inputs)
    ? allocationResearchSchema.allowed_inputs
    : [];
  const allocationFutureEvidence = Array.isArray(allocationResearchSchema.required_future_evidence)
    ? allocationResearchSchema.required_future_evidence
    : [];
  const allocationForbiddenOutputs = Array.isArray(allocationResearchSchema.forbidden_outputs)
    ? allocationResearchSchema.forbidden_outputs
    : [];
  const allocationV8Evidence = allocationResearchEvidence.v8_research_interpretation || {};
  setText("allocationResearchReady", allocationResearchSummary.allocation_research_ready === false ? "未就绪" : "--");
  setText("allocationResearchContext", allocationResearchSummary.environment_context || "--");
  setText("allocationResearchForbidden", allocationForbiddenOutputs.length ? `${integerText(allocationForbiddenOutputs.length)} 项` : "--");
  setText("allocationResearchBoundary", allocationResearchReadyFlagsOff ? "不选资产/不映射ETF/不生成权重/不交易" : "需复核");
  setHtml("allocationResearchInputs", allocationAllowedInputs
    .map((item) => `
      <div class="duration-row">
        <span>${escapeHtml(item.field || "--")}</span>
        <strong>${escapeHtml(item.source || "--")}</strong>
        <em>${escapeHtml(item.description || "")}</em>
      </div>
    `)
    .join(""));
  setHtml("allocationResearchEvidence", [
    ["V6 风险上下文", allocationResearchEvidence.v6_risk_context?.conclusion, `风险区分 ${signedFixedText(allocationResearchEvidence.v6_risk_context?.two_axis_risk_spread, 3)} · 机会区分 ${signedFixedText(allocationResearchEvidence.v6_risk_context?.two_axis_opportunity_spread, 3)}`],
    ["V7 机会研究", allocationResearchEvidence.v7_opportunity_research?.conclusion, Object.entries(allocationResearchEvidence.v7_opportunity_research?.retention_counts || {}).map(([key, value]) => `${key} ${integerText(value)}`).join(" / ")],
    ["V8 研究解释", allocationV8Evidence.decision_context, `一致性 ${Object.entries(allocationV8Evidence.scenario_consistency_counts || {}).map(([key, value]) => `${key} ${integerText(value)}`).join(" / ") || "--"}`],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "--")}</strong>
      <em>${escapeHtml(note || "")}</em>
    </div>
  `).join(""));
  setText(
    "allocationResearchConclusion",
    allocationResearch.metadata
      ? `V9.1 只定义未来配置研究的架构边界：允许使用冻结 V6/V7/V8 作为输入，但必须先补齐 ${allocationFutureEvidence.map((item) => escapeHtml(item)).join(" / ") || "未来证据"}，当前结论为 ${escapeHtml(allocationResearchSummary.conclusion || "--")}。禁止输出：${allocationForbiddenOutputs.map((item) => escapeHtml(item)).join(" / ") || "--"}。`
      : "V9.1 配置研究架构基础尚未生成。"
  );

  const allocationHypothesisReadyFlagsOff =
    allocationHypothesesSummary.hypothesis_framework_ready === false &&
    allocationHypothesesSummary.ready_for_asset_selection === false &&
    allocationHypothesesSummary.ready_for_etf_mapping === false &&
    allocationHypothesesSummary.ready_for_weight_generation === false &&
    allocationHypothesesSummary.ready_for_backtest === false &&
    allocationHypothesesSummary.ready_for_optimization === false &&
    allocationHypothesesSummary.ready_for_trade === false;
  const allocationHypothesisValidation = Array.isArray(allocationHypothesesSchema.required_validation)
    ? allocationHypothesesSchema.required_validation
    : [];
  const allocationHypothesisForbidden = Array.isArray(allocationHypothesesSchema.forbidden_outputs)
    ? allocationHypothesesSchema.forbidden_outputs
    : [];
  setText("allocationHypothesisStatus", allocationHypothesesSummary.hypothesis_framework_ready === false ? "未验证" : "--");
  setText(
    "allocationHypothesisCount",
    allocationHypothesesSummary.hypothesis_count != null
      ? `${integerText(allocationHypothesesSummary.hypothesis_count)} 条`
      : "--"
  );
  setText(
    "allocationHypothesisValidation",
    allocationHypothesisValidation.length ? `${integerText(allocationHypothesisValidation.length)} 项` : "--"
  );
  setText("allocationHypothesisBoundary", allocationHypothesisReadyFlagsOff ? "不选资产/不映射ETF/不生成权重/不回测/不交易" : "需复核");
  setHtml("allocationHypothesisRows", allocationHypothesisRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.id || "--")} · ${escapeHtml(row.name || "--")}</span>
        <strong>${escapeHtml(row.status || "--")}</strong>
        <em>${escapeHtml(row.research_question || "")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationHypothesisConclusion",
    allocationHypotheses.metadata
      ? `V9.2 只定义 ${integerText(allocationHypothesesSummary.hypothesis_count)} 条未来配置研究假设，全部保持 ${escapeHtml(allocationHypothesesSchema.required_status || "unvalidated")}；后续必须先完成 ${allocationHypothesisValidation.map((item) => escapeHtml(item)).join(" / ") || "验证"}。禁止输出：${allocationHypothesisForbidden.map((item) => escapeHtml(item)).join(" / ") || "--"}。`
      : "V9.2 配置研究假设框架尚未生成。"
  );

  const allocationValidationReadyFlagsOff =
    allocationValidationSummary.validation_plan_ready === false &&
    allocationValidationSummary.validation_executed === false &&
    allocationValidationSummary.ready_for_asset_selection === false &&
    allocationValidationSummary.ready_for_etf_mapping === false &&
    allocationValidationSummary.ready_for_weight_generation === false &&
    allocationValidationSummary.ready_for_backtest === false &&
    allocationValidationSummary.ready_for_optimization === false &&
    allocationValidationSummary.ready_for_trade === false;
  const allocationValidationEvidence = Array.isArray(allocationValidationSchema.required_evidence)
    ? allocationValidationSchema.required_evidence
    : [];
  const allocationValidationAntiOverfit = Array.isArray(allocationValidationSchema.required_anti_overfitting_rules)
    ? allocationValidationSchema.required_anti_overfitting_rules
    : [];
  const allocationValidationForbidden = Array.isArray(allocationValidationSchema.forbidden_outputs)
    ? allocationValidationSchema.forbidden_outputs
    : [];
  setText("allocationValidationStatus", allocationValidationSummary.validation_executed === false ? "计划未执行" : "--");
  setText(
    "allocationValidationCount",
    allocationValidationSummary.validation_plan_count != null
      ? `${integerText(allocationValidationSummary.validation_plan_count)} 个`
      : "--"
  );
  setText("allocationValidationEvidence", allocationValidationEvidence.length ? `${integerText(allocationValidationEvidence.length)} 项` : "--");
  setText("allocationValidationAntiOverfit", allocationValidationAntiOverfit.length ? `${integerText(allocationValidationAntiOverfit.length)} 条` : "--");
  setText("allocationValidationBoundary", allocationValidationReadyFlagsOff ? "只设计验证/不执行/不出结果/不优化/不交易" : "需复核");
  setHtml("allocationValidationRows", allocationValidationRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.hypothesis_id || "--")} · ${escapeHtml(row.hypothesis_name || "--")}</span>
        <strong>${escapeHtml(row.execution_status || "--")}</strong>
        <em>${escapeHtml(row.validation_objective || "")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationValidationConclusion",
    allocationValidationPlan.metadata
      ? `V9.3 只为 ${integerText(allocationValidationSummary.validation_plan_count)} 个假设设计验证计划，执行数 ${integerText(allocationValidationSummary.executed_plan_count)}；要求 ${allocationValidationEvidence.map((item) => escapeHtml(item)).join(" / ") || "验证设计"}，防过拟合规则 ${allocationValidationAntiOverfit.map((item) => escapeHtml(item)).join(" / ") || "--"}。禁止输出：${allocationValidationForbidden.map((item) => escapeHtml(item)).join(" / ") || "--"}。`
      : "V9.3 配置研究验证计划尚未生成。"
  );

  const allocationExperimentReadyFlagsOff =
    allocationExperimentSummary.experiment_template_ready === false &&
    allocationExperimentSummary.experiment_executed === false &&
    allocationExperimentSummary.ready_for_asset_selection === false &&
    allocationExperimentSummary.ready_for_etf_mapping === false &&
    allocationExperimentSummary.ready_for_weight_generation === false &&
    allocationExperimentSummary.ready_for_backtest === false &&
    allocationExperimentSummary.ready_for_validation_result === false &&
    allocationExperimentSummary.ready_for_optimization === false &&
    allocationExperimentSummary.ready_for_trade === false;
  const allocationExperimentCriteria = Array.isArray(allocationExperimentSchema.required_evaluation_criteria)
    ? allocationExperimentSchema.required_evaluation_criteria
    : [];
  const allocationExperimentForbidden = Array.isArray(allocationExperimentSchema.forbidden_outputs)
    ? allocationExperimentSchema.forbidden_outputs
    : [];
  setText("allocationExperimentStatus", allocationExperimentSummary.experiment_executed === false ? "模板未执行" : "--");
  setText(
    "allocationExperimentCount",
    allocationExperimentSummary.experiment_template_count != null
      ? `${integerText(allocationExperimentSummary.experiment_template_count)} 个`
      : "--"
  );
  setText("allocationExperimentEvaluation", allocationExperimentCriteria.length ? `${integerText(allocationExperimentCriteria.length)} 项` : "--");
  setText("allocationExperimentBoundary", allocationExperimentReadyFlagsOff ? "只定义模板/不运行/不出结果/不配置/不交易" : "需复核");
  setHtml("allocationExperimentRows", allocationExperimentRows
    .map((row) => {
      const comparison = row.predefined_comparison || {};
      return `
        <div class="duration-row">
          <span>${escapeHtml(row.hypothesis_id || "--")} · ${escapeHtml(row.hypothesis_name || "--")}</span>
          <strong>${escapeHtml(row.execution_status || "--")}</strong>
          <em>${escapeHtml(comparison.baseline || "--")} vs ${escapeHtml(comparison.alternative || "--")} · ${escapeHtml(row.experiment_question || "")}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "allocationExperimentConclusion",
    allocationExperiments.metadata
      ? `V9.4 只定义 ${integerText(allocationExperimentSummary.experiment_template_count)} 个预声明实验模板，执行数 ${integerText(allocationExperimentSummary.executed_experiment_count)}；评价标准 ${allocationExperimentCriteria.map((item) => escapeHtml(item)).join(" / ") || "--"}。禁止输出：${allocationExperimentForbidden.map((item) => escapeHtml(item)).join(" / ") || "--"}。`
      : "V9.4 配置研究实验模板尚未生成。"
  );

  const allocationExperimentResultReadyFlagsOff =
    allocationExperimentResultSummary.ready_for_asset_selection === false &&
    allocationExperimentResultSummary.ready_for_etf_mapping === false &&
    allocationExperimentResultSummary.ready_for_weight_generation === false &&
    allocationExperimentResultSummary.ready_for_backtest === false &&
    allocationExperimentResultSummary.ready_for_optimization === false &&
    allocationExperimentResultSummary.ready_for_trade === false &&
    allocationExperimentResultSummary.promoted_to_candidate === false &&
    allocationExperimentResultSummary.investable_output_generated === false;
  setText("allocationExperimentResultStatus", allocationExperimentResultSummary.conclusion ? "Phase 0 完成" : "--");
  setText(
    "allocationExperimentResultExecuted",
    allocationExperimentResultSummary.executed_experiment_count != null
      ? `${integerText(allocationExperimentResultSummary.executed_experiment_count)} 个`
      : "--"
  );
  setText(
    "allocationExperimentResultDesignPass",
    allocationExperimentResultSummary.design_pass_count != null
      ? `${integerText(allocationExperimentResultSummary.design_pass_count)} 个`
      : "--"
  );
  setText(
    "allocationExperimentResultMarket",
    allocationExperimentResultSummary.market_validation_result_count != null
      ? `${integerText(allocationExperimentResultSummary.market_validation_result_count)} 个`
      : "--"
  );
  setText("allocationExperimentResultBoundary", allocationExperimentResultReadyFlagsOff ? "不选资产/不映射ETF/不生成权重/不优化/不交易" : "需复核");
  setHtml("allocationExperimentResultRows", allocationExperimentResultRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.experiment_id || "--")} · ${escapeHtml(row.hypothesis_name || "--")}</span>
        <strong>${escapeHtml(row.validation_result || "--")}</strong>
        <em>${escapeHtml(row.out_of_sample_status || "--")} · ${escapeHtml(row.promotion_status || "--")} · ${escapeHtml(row.interpretation || "")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationExperimentResultConclusion",
    allocationExperimentResults.metadata
      ? `V9.5 Phase 0 只执行预声明模板的研究纪律检查：执行 ${integerText(allocationExperimentResultSummary.executed_experiment_count)} 个，design pass ${integerText(allocationExperimentResultSummary.design_pass_count)} 个，市场验证结果 ${integerText(allocationExperimentResultSummary.market_validation_result_count)} 个。执行范围：market_data_loaded=${allocationExperimentScope.market_data_loaded === false ? "false" : "--"}，performance_measured=${allocationExperimentScope.performance_measured === false ? "false" : "--"}；不可用于资产选择、ETF 映射、权重、优化或交易。`
      : "V9.5 配置研究实验 Phase 0 结果尚未生成。"
  );

  const allocationPhase1ReadyFlagsOff =
    allocationPhase1Summary.ready_for_asset_selection === false &&
    allocationPhase1Summary.ready_for_etf_mapping === false &&
    allocationPhase1Summary.ready_for_weight_generation === false &&
    allocationPhase1Summary.ready_for_optimization === false &&
    allocationPhase1Summary.ready_for_trade === false &&
    allocationPhase1Summary.promoted_to_candidate === false &&
    allocationPhase1Summary.investable_output_generated === false;
  setText("allocationPhase1Status", allocationPhase1Summary.conclusion ? "研究验证完成" : "--");
  setText("allocationPhase1Supported", integerText(allocationPhase1Summary.supported_count));
  setText("allocationPhase1Inconclusive", integerText(allocationPhase1Summary.inconclusive_count));
  setText("allocationPhase1Hashes", `${integerText(Object.keys(allocationPhase1Hashes).length)} 个`);
  setText("allocationPhase1Boundary", allocationPhase1ReadyFlagsOff ? "不晋级/不选资产/不映射ETF/不生成权重/不交易" : "需复核");
  setHtml("allocationPhase1Rows", allocationPhase1Rows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.experiment_id || "--")}</span>
        <strong>${escapeHtml(row.validation_status || "--")}</strong>
        <em>${escapeHtml(row.finding || "")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationPhase1Conclusion",
    allocationPhase1.metadata
      ? `V9.6 使用冻结输入做研究验证：supported ${integerText(allocationPhase1Summary.supported_count)}、inconclusive ${integerText(allocationPhase1Summary.inconclusive_count)}、unsupported ${integerText(allocationPhase1Summary.unsupported_count)}；输入哈希 ${integerText(Object.keys(allocationPhase1Hashes).length)} 个。promotion_allowed=false，不能用于资产、ETF、权重、优化或交易。`
      : "V9.6 配置研究实验 Phase 1 验证尚未生成。"
  );

  const researchGateReadyFlagsOff =
    researchGateSummary.promotion_allowed === false &&
    researchGateSummary.strategy_promotion === false &&
    researchGateSummary.allocation_promotion === false &&
    researchGateSummary.investable_output === false &&
    researchGateSummary.investable_output_generated === false &&
    researchGateSummary.ready_for_asset_selection === false &&
    researchGateSummary.ready_for_etf_mapping === false &&
    researchGateSummary.ready_for_weight_generation === false &&
    researchGateSummary.ready_for_trade === false;
  const researchGateStatusLabel = (status) => ({
    continue_research: "继续研究",
    freeze: "冻结",
    reject_for_now: "暂拒",
  }[status] || status || "--");
  setText("researchGateStatus", researchGateSummary.conclusion ? "门禁完成" : "--");
  setText("researchGateContinue", integerText(researchGateSummary.continue_research_count));
  setText("researchGateFreeze", integerText(researchGateSummary.freeze_count));
  setText("researchGateReject", integerText(researchGateSummary.reject_for_now_count));
  setText("researchGateBoundary", researchGateReadyFlagsOff ? "不策略化/不配置/不选资产/不映射ETF/不交易" : "需复核");
  setHtml("researchGateRows", researchGateRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.hypothesis_id || "--")} · ${escapeHtml(row.validation_status || "--")}</span>
        <strong>${escapeHtml(researchGateStatusLabel(row.research_status))}</strong>
        <em>${escapeHtml(Array.isArray(row.promotion_reason) ? row.promotion_reason.join(" / ") : row.next_research_step || "")}</em>
      </div>
    `)
    .join(""));
  setText(
    "researchGateConclusion",
    researchGate.metadata
      ? `V9.7 固定 V9.6/V9.3/V9.4 输入做研究阶段门禁：继续研究 ${integerText(researchGateSummary.continue_research_count)}、冻结 ${integerText(researchGateSummary.freeze_count)}、暂拒 ${integerText(researchGateSummary.reject_for_now_count)}。promotion_allowed=false，strategy_promotion=false，investable_output=false；不产生策略、配置、资产、ETF、权重或交易。`
      : "V9.7 研究阶段门禁审计尚未生成。"
  );

  const researchDeepReadyFlagsOff =
    researchDeepSummary.promotion_allowed === false &&
    researchDeepSummary.strategy_promotion === false &&
    researchDeepSummary.allocation_promotion === false &&
    researchDeepSummary.investable_output === false &&
    researchDeepSummary.investable_output_generated === false &&
    researchDeepSummary.ready_for_asset_selection === false &&
    researchDeepSummary.ready_for_etf_mapping === false &&
    researchDeepSummary.ready_for_weight_generation === false &&
    researchDeepSummary.ready_for_optimization === false &&
    researchDeepSummary.ready_for_trade === false;
  const researchDeepStatusLabel = (status) => ({
    supported: "支持",
    inconclusive: "不确定",
    unsupported: "不支持",
  }[status] || status || "--");
  setText("researchDeepStatus", researchDeepSummary.conclusion ? "深度验证完成" : "--");
  setText("researchDeepSupported", integerText(researchDeepSummary.supported_count));
  setText("researchDeepInconclusive", integerText(researchDeepSummary.inconclusive_count));
  setText("researchDeepUnsupported", integerText(researchDeepSummary.unsupported_count));
  setText("researchDeepBoundary", researchDeepReadyFlagsOff ? "不策略化/不配置/不优化/不交易" : "需复核");
  setHtml("researchDeepRows", researchDeepRows
    .map((row) => {
      const checks = row.deep_checks || {};
      const checkText = row.hypothesis_id === "H2"
        ? `低一致 ${fixedText(checks.low_consistency_share, 3)} · 风险滞后 ${integerText(checks.risk_axis_lag_or_structural_rotation_missed_count)}`
        : `归因覆盖 ${checks.attribution_coverage_pass ? "通过" : "未过"} · 门禁阻断 ${checks.promotion_blocked ? "通过" : "未过"}`;
      return `
        <div class="duration-row">
          <span>${escapeHtml(row.hypothesis_id || "--")} · ${escapeHtml(row.hypothesis_name || "--")}</span>
          <strong>${escapeHtml(researchDeepStatusLabel(row.status))}</strong>
          <em>${escapeHtml(checkText)} · ${escapeHtml(row.next_research_step || "")}</em>
        </div>
      `;
    })
    .join(""));
  setText(
    "researchDeepConclusion",
    researchDeep.metadata
      ? `V9.8 只深化 H2/H4：supported ${integerText(researchDeepSummary.supported_count)}、inconclusive ${integerText(researchDeepSummary.inconclusive_count)}、unsupported ${integerText(researchDeepSummary.unsupported_count)}。当前读法：H2 在更严格跨场景稳定性下仍不确定；H4 作为矛盾优先研究门禁得到支持。仍不产生策略、配置、资产、ETF、权重、优化或交易。`
      : "V9.8 研究候选深度验证尚未生成。"
  );

  const allocationEvidenceReadyFlagsOff =
    allocationEvidenceSummary.promotion_allowed === false &&
    allocationEvidenceSummary.strategy_promotion === false &&
    allocationEvidenceSummary.allocation_ready === false &&
    allocationEvidenceSummary.investable_output === false &&
    allocationEvidenceSummary.investable_output_generated === false &&
    allocationEvidenceSummary.ready_for_asset_selection === false &&
    allocationEvidenceSummary.ready_for_etf_mapping === false &&
    allocationEvidenceSummary.ready_for_weight_generation === false &&
    allocationEvidenceSummary.ready_for_optimization === false &&
    allocationEvidenceSummary.ready_for_trade === false;
  const allocationEvidenceStatusLabel = (status) => ({
    freeze: "暂停",
    inconclusive: "不确定",
    supported_research_only: "研究支持",
  }[status] || status || "--");
  const allocationEvidenceRows = Object.entries(allocationEvidenceStatus);
  const allocationEvidenceProhibited = Array.isArray(allocationEvidenceBoundarySummary.prohibited_next_actions)
    ? allocationEvidenceBoundarySummary.prohibited_next_actions
    : [];
  setText("allocationEvidenceState", allocationEvidenceSummary.research_state === "frozen" ? "已冻结" : "--");
  setText("allocationEvidenceRetained", integerText(allocationEvidenceSummary.retained_research_direction_count));
  setText("allocationEvidencePaused", integerText(allocationEvidenceSummary.paused_research_direction_count));
  setText("allocationEvidenceReady", allocationEvidenceSummary.allocation_ready === false ? "否" : "--");
  setText("allocationEvidenceBoundary", allocationEvidenceReadyFlagsOff ? "不新增层/不策略化/不配置/不交易" : "需复核");
  setHtml("allocationEvidenceRows", allocationEvidenceRows
    .map(([id, row]) => `
      <div class="duration-row">
        <span>${escapeHtml(id)} · ${escapeHtml(row.hypothesis_name || "--")}</span>
        <strong>${escapeHtml(allocationEvidenceStatusLabel(row.status))}</strong>
        <em>${escapeHtml(row.research_direction || "--")} · ${escapeHtml(row.allowed_next_step || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationEvidenceConclusion",
    allocationEvidenceFreeze.metadata
      ? `V9.9 冻结 V9.1-V9.8 证据：保留研究方向 ${integerText(allocationEvidenceSummary.retained_research_direction_count)} 个，暂停 ${integerText(allocationEvidenceSummary.paused_research_direction_count)} 个；H2 为不确定研究方向，H4 为研究支持但不可策略化。禁止继续增加状态、假设或解释层：${allocationEvidenceProhibited.slice(0, 3).map((item) => escapeHtml(item)).join(" / ") || "--"}。`
      : "V9.9 配置研究证据冻结尚未生成。"
  );

  const allocationExecutionReadyFlagsOff =
    allocationExecutionSummary.promotion_allowed === false &&
    allocationExecutionSummary.strategy_promotion === false &&
    allocationExecutionSummary.allocation_ready === false &&
    allocationExecutionSummary.investable_output === false &&
    allocationExecutionSummary.investable_output_generated === false &&
    allocationExecutionSummary.ready_for_asset_selection === false &&
    allocationExecutionSummary.ready_for_etf_mapping === false &&
    allocationExecutionSummary.ready_for_weight_generation === false &&
    allocationExecutionSummary.ready_for_optimization === false &&
    allocationExecutionSummary.ready_for_trade === false;
  const allocationExecutionResultLabel = (result) => ({
    supported: "支持",
    inconclusive: "不确定",
    unsupported: "不支持",
  }[result] || result || "--");
  setText("allocationExecutionStatus", allocationExecutionSummary.completed_run_count === allocationExecutionSummary.run_count ? "已完成" : "--");
  setText("allocationExecutionRuns", integerText(allocationExecutionSummary.run_count));
  setText("allocationExecutionSupported", integerText(allocationExecutionSummary.supported_count));
  setText("allocationExecutionInconclusive", integerText(allocationExecutionSummary.inconclusive_count));
  setText("allocationExecutionBoundary", allocationExecutionReadyFlagsOff ? "只记录实验/不配置/不优化/不交易" : "需复核");
  setHtml("allocationExecutionRows", allocationExecutionRows
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.experiment_id || "--")} · ${escapeHtml(row.run_id || "--")}</span>
        <strong>${escapeHtml(allocationExecutionResultLabel(row.result))}</strong>
        <em>${escapeHtml(row.execution_scope || "--")} · hash ${escapeHtml(String(row.input_hash || "").slice(0, 10))}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationExecutionConclusion",
    allocationExecution.metadata
      ? `V10.1 只执行冻结研究实验记录：运行 ${integerText(allocationExecutionSummary.run_count)} 条，完成 ${integerText(allocationExecutionSummary.completed_run_count)} 条；H2 仍不确定，H4 为研究支持。input_hash 已记录，仍不生成资产、ETF、权重、配置、优化或交易。`
      : "V10.1 配置研究执行框架尚未生成。"
  );

  const allocationReviewReadyFlagsOff =
    allocationReviewSummary.promotion_allowed === false &&
    allocationReviewSummary.strategy_promotion === false &&
    allocationReviewSummary.allocation_ready === false &&
    allocationReviewSummary.investable_output === false &&
    allocationReviewSummary.investable_output_generated === false &&
    allocationReviewSummary.ready_for_asset_selection === false &&
    allocationReviewSummary.ready_for_etf_mapping === false &&
    allocationReviewSummary.ready_for_weight_generation === false &&
    allocationReviewSummary.ready_for_optimization === false &&
    allocationReviewSummary.ready_for_trade === false;
  const allocationReviewStatusLabel = (status) => ({
    continue_research: "继续研究",
    retain_research_only: "保留研究",
    pause_research: "暂停研究",
    reject_for_now: "暂拒",
  }[status] || status || "--");
  const allocationReviewEntries = Object.entries(allocationReviewRows || {});
  setText("allocationReviewStatus", allocationReviewSummary.research_review_status === "completed" ? "已完成" : "--");
  setText("allocationReviewCount", integerText(allocationReviewSummary.reviewed_hypothesis_count));
  setText("allocationReviewContinue", integerText(allocationReviewSummary.continue_research_count));
  setText("allocationReviewRetain", integerText(allocationReviewSummary.retain_research_only_count));
  setText("allocationReviewBoundary", allocationReviewReadyFlagsOff ? "只审查/不配置/不优化/不交易" : "需复核");
  setHtml("allocationReviewRows", allocationReviewEntries
    .map(([id, row]) => `
      <div class="duration-row">
        <span>${escapeHtml(id)} · ${escapeHtml(row.execution_result || "--")}</span>
        <strong>${escapeHtml(allocationReviewStatusLabel(row.status))}</strong>
        <em>${escapeHtml(row.reason || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationReviewConclusion",
    allocationReview.metadata
      ? `V10.2 只审查 V10.1 研究执行结果：H2 继续研究但不升级，H4 保留为研究流程门禁。promotion_allowed=false、allocation_ready=false，仍不生成资产、ETF、权重、配置、优化或交易。`
      : "V10.2 配置研究结果审查尚未生成。"
  );

  const allocationFinalReadyFlagsOff =
    allocationFinalSummary.promotion_allowed === false &&
    allocationFinalSummary.strategy_promotion === false &&
    allocationFinalSummary.allocation_ready === false &&
    allocationFinalSummary.investable_output === false &&
    allocationFinalSummary.investable_output_generated === false &&
    allocationFinalSummary.ready_for_asset_selection === false &&
    allocationFinalSummary.ready_for_etf_mapping === false &&
    allocationFinalSummary.ready_for_weight_generation === false &&
    allocationFinalSummary.ready_for_optimization === false &&
    allocationFinalSummary.ready_for_trade === false;
  const allocationFinalStatusLabel = (status) => ({
    continue_external_validation: "外部验证",
    research_governance_only: "治理保留",
    frozen_no_external_validation: "冻结",
  }[status] || status || "--");
  const allocationFinalEntries = Object.entries(allocationFinalDirections || {});
  setText("allocationFinalStatus", allocationFinalSummary.research_phase_status === "completed" ? "已完成" : "--");
  setText("allocationFinalDirections", integerText(allocationFinalSummary.direction_count));
  setText("allocationFinalExternal", integerText(allocationFinalSummary.continue_external_validation_count));
  setText("allocationFinalGovernance", integerText(allocationFinalSummary.research_governance_only_count));
  setText("allocationFinalBoundary", allocationFinalReadyFlagsOff ? "只定边界/不配置/不优化/不交易" : "需复核");
  setHtml("allocationFinalRows", allocationFinalEntries
    .map(([id, row]) => `
      <div class="duration-row">
        <span>${escapeHtml(id)} · ${escapeHtml(allocationFinalStatusLabel(row.status))}</span>
        <strong>${escapeHtml(row.allowed_next_step || "--")}</strong>
        <em>${escapeHtml(row.decision_reason || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "allocationFinalConclusion",
    allocationFinal.metadata
      ? `V10.3 固定最终研究边界：H2 只能继续外部验证，H4 仅作为研究治理保留，H1/H3 冻结且不做外部验证。allocation_ready=false，仍不生成资产、ETF、权重、配置、优化或交易。`
      : "V10.3 配置研究最终边界尚未生成。"
  );

  const externalProtocolReadyFlagsOff =
    externalProtocolSummary.promotion_allowed === false &&
    externalProtocolSummary.strategy_promotion === false &&
    externalProtocolSummary.allocation_ready === false &&
    externalProtocolSummary.investable_output === false &&
    externalProtocolSummary.investable_output_generated === false &&
    externalProtocolSummary.ready_for_asset_selection === false &&
    externalProtocolSummary.ready_for_etf_mapping === false &&
    externalProtocolSummary.ready_for_weight_generation === false &&
    externalProtocolSummary.ready_for_optimization === false &&
    externalProtocolSummary.ready_for_trade === false;
  const externalWindows = Array.isArray(externalProtocolBody.validation_windows)
    ? externalProtocolBody.validation_windows
    : [];
  const externalMethods = Array.isArray(externalProtocolBody.pre_registered_methods)
    ? externalProtocolBody.pre_registered_methods
    : [];
  const externalStops = Array.isArray(externalProtocolBody.stop_conditions)
    ? externalProtocolBody.stop_conditions
    : [];
  setText("externalProtocolStatus", externalProtocolSummary.protocol_phase_status === "defined" ? "已定义" : "--");
  setText("externalProtocolTarget", externalProtocolSummary.target_hypothesis || "--");
  setText("externalProtocolWindows", integerText(externalWindows.length));
  setText("externalProtocolExcluded", integerText(Object.keys(externalProtocolExcluded).length));
  setText("externalProtocolBoundary", externalProtocolReadyFlagsOff ? "只定协议/不验证/不配置/不交易" : "需复核");
  setHtml("externalProtocolRows", [
    ...externalWindows.map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.window_id || "--")}</span>
        <strong>${escapeHtml(row.result_use || "--")}</strong>
        <em>${escapeHtml(row.role || "--")}</em>
      </div>
    `),
    ...externalMethods.map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.method_id || "--")}</span>
        <strong>${escapeHtml(row.allowed_result || "--")}</strong>
        <em>${escapeHtml(row.description || "--")}</em>
      </div>
    `),
  ].join(""));
  setHtml("externalProtocolStops", externalStops
    .map((item) => `
      <div class="duration-row">
        <span>停止条件</span>
        <strong>预注册约束</strong>
        <em>${escapeHtml(item)}</em>
      </div>
    `)
    .join(""));
  setText(
    "externalProtocolConclusion",
    externalProtocol.metadata
      ? `V11.1 只为 H2 定义外部验证协议：验证窗口必须预先声明，结果只能支持/失败研究方向；H4 继续作为治理门禁，H1/H3 保持冻结。该层不运行验证，不生成资产、ETF、权重、配置、优化或交易。`
      : "V11.1 外部验证协议尚未生成。"
  );

  const h2ExternalReadyFlagsOff =
    h2ExternalSummary.promotion_allowed === false &&
    h2ExternalSummary.strategy_promotion === false &&
    h2ExternalSummary.allocation_ready === false &&
    h2ExternalSummary.investable_output === false &&
    h2ExternalSummary.investable_output_generated === false &&
    h2ExternalSummary.ready_for_asset_selection === false &&
    h2ExternalSummary.ready_for_etf_mapping === false &&
    h2ExternalSummary.ready_for_weight_generation === false &&
    h2ExternalSummary.ready_for_optimization === false &&
    h2ExternalSummary.ready_for_trade === false;
  const h2ExternalStatusLabel = (status) => ({
    passed: "通过",
    failed: "失败",
    inconclusive: "不确定",
  }[status] || status || "--");
  setText("h2ExternalStatus", h2ExternalStatusLabel(h2ExternalSummary.overall_status));
  setText("h2ExternalPassed", integerText(h2ExternalSummary.passed_count));
  setText("h2ExternalInconclusive", integerText(h2ExternalSummary.inconclusive_count));
  setText("h2ExternalFailed", integerText(h2ExternalSummary.failed_count));
  setText("h2ExternalBoundary", h2ExternalReadyFlagsOff ? "只验证研究/不配置/不交易" : "需复核");
  setHtml("h2ExternalRows", h2ExternalRuns
    .map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.window_id || "--")}</span>
        <strong>${escapeHtml(h2ExternalStatusLabel(row.status))}</strong>
        <em>${escapeHtml(row.result_reason || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "h2ExternalConclusion",
    h2External.metadata
      ? `V11.2 按预注册窗口执行 H2 外部验证：通过 ${integerText(h2ExternalSummary.passed_count)}、不确定 ${integerText(h2ExternalSummary.inconclusive_count)}、失败 ${integerText(h2ExternalSummary.failed_count)}，整体为${h2ExternalStatusLabel(h2ExternalSummary.overall_status)}。结论仍是 research-only，不生成资产、ETF、权重、配置、优化或交易。`
      : "V11.2 H2 外部验证执行尚未生成。"
  );

  const h2FreezeReadyFlagsOff =
    h2FreezeSummary.promotion_allowed === false &&
    h2FreezeSummary.strategy_promotion === false &&
    h2FreezeSummary.allocation_ready === false &&
    h2FreezeSummary.investable_output === false &&
    h2FreezeSummary.investable_output_generated === false &&
    h2FreezeSummary.ready_for_asset_selection === false &&
    h2FreezeSummary.ready_for_etf_mapping === false &&
    h2FreezeSummary.ready_for_weight_generation === false &&
    h2FreezeSummary.ready_for_optimization === false &&
    h2FreezeSummary.ready_for_trade === false;
  const h2EvidenceStatusLabel = (status) => ({
    supported: "支持",
    not_confirmed: "未确认",
    insufficient: "不足",
    unresolved: "未解决",
  }[status] || status || "--");
  const h2DecisionLabel = (value) => ({
    continue_observation_only: "仅继续观察",
  }[value] || value || "--");
  setText("h2FreezeStatus", h2FreezeSummary.freeze_status === "frozen" ? "已冻结" : "--");
  setText("h2FreezeH2Status", h2ExternalStatusLabel(h2FreezeSummary.h2_status));
  setText("h2FreezeDecision", h2DecisionLabel(h2FreezeConclusion.research_decision));
  setText("h2FreezeSupported", integerText(h2FreezeSummary.evidence_supported_count));
  setText("h2FreezeBoundary", h2FreezeReadyFlagsOff ? "只冻结解释/不配置/不交易" : "需复核");
  setHtml("h2FreezeRows", Object.entries(h2FreezeEvidence)
    .map(([key, row]) => `
      <div class="duration-row">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(h2EvidenceStatusLabel(row.status))}</strong>
        <em>${escapeHtml(row.interpretation || "--")}</em>
      </div>
    `)
    .join(""));
  setText(
    "h2FreezeConclusion",
    h2Freeze.metadata
      ? `V11.3 冻结 H2 外部验证结论：风险证据可见，但跨周期稳定不足、近期样本不足、结构机会冲突未解决。研究决策为${h2DecisionLabel(h2FreezeConclusion.research_decision)}，不修改 H2，不调阈值，不加特征，不生成资产、ETF、权重、配置、优化或交易。`
      : "V11.3 H2 外部验证结果冻结尚未生成。"
  );

  const phaseStatusLabel = (value) => ({
    closed: "已关闭",
    validated_for_observation_only: "仅观察可用",
    research_value_supported_observation_only: "观察价值支持",
    validated_for_research_governance_only: "仅研究治理",
    not_ready: "未就绪",
    disabled: "已禁用",
    research_phase_closed_project_not_complete: "研究阶段收口/项目未完成",
    defined: "已定义",
    not_started: "未启动",
    blocked: "已阻断",
    defined: "已定义",
    observation_only: "仅观察",
    research_governance_only: "仅研究治理",
    isolated_not_ready: "隔离/未就绪",
    not_ready_evidence_required: "未就绪/需证据",
    not_evaluated: "未评价",
    not_submitted: "未提交",
    invalid_not_submitted: "无包/无效",
    generated: "已生成",
    invalid_missing_or_boundary_violation: "缺失/越界",
    blocked_pending_manual_review_and_future_audit: "已阻断",
    frozen: "已冻结",
    none_submitted: "未提交",
    governance_frozen_project_not_complete: "治理冻结/项目未完成",
    submitted: "已提交",
    submitted_blocked_phase_0: "已提交/Phase 0 阻断",
    format_valid_not_ready_for_implementation: "格式有效/未就绪",
    passed_no_investable_output: "通过/无投资输出",
    projected_blocked: "预计阻断",
    blocked_pending_shadow_and_manual_review: "等待影子观察/人工审核",
    submitted_inconclusive: "已提交/不确定",
    submitted_negative: "已提交/负面",
    submitted_missing_required_live_log: "缺 live shadow",
    planned: "已规划",
    active: "已启用",
    active_empty: "启用/空日志",
    no_events_available: "无事件可复核",
    ready_for_manual_input: "可人工录入",
    manual_event_file_only: "仅人工文件",
    no_event_submitted: "本次未提交",
    manual_event_appended_no_trade: "已人工追加/不交易",
    events_pending_manual_review: "待人工复核",
    events_quality_checked_pending_manual_review: "已检查/待人工复核",
    ready_for_first_manual_event: "等待首个事件",
    empty_waiting_for_first_manual_event: "空队列/等待事件",
    ready: "已就绪",
    no_event_file_supplied: "未提供事件文件",
    valid_not_submitted: "有效/未提交",
    invalid_event_file: "事件文件无效",
    waiting_for_manual_events: "等待人工事件",
    initialized_empty: "空日志",
    defined_not_instantiated: "已定义/未实例化",
    risk_diagnostic_shadow_framework_defined_observation_only_no_trade: "只观察/不交易",
  }[value] || value || "--");
  setText("phaseClosureStatus", phaseStatusLabel(phaseClosureSummary.research_phase));
  setText("phaseClosureRisk", phaseStatusLabel(phaseClosureSummary.risk_research_status));
  setText("phaseClosureOpportunity", phaseStatusLabel(phaseClosureSummary.opportunity_research_status));
  setText("phaseClosureAllocation", phaseStatusLabel(phaseClosureSummary.allocation_status));
  setText("phaseClosureTrading", phaseStatusLabel(phaseClosureSummary.trading_status));
  setHtml("phaseClosureRows", [
    ...phaseClosureValidated.map((row) => `
      <div class="duration-row">
        <span>${escapeHtml(row.layer || "--")}</span>
        <strong>${escapeHtml(phaseStatusLabel(row.status))}</strong>
        <em>${escapeHtml(row.basis || "--")}</em>
      </div>
    `),
    ...phaseClosureNotVerified.map((item) => `
      <div class="duration-row">
        <span>${escapeHtml(item)}</span>
        <strong>未验证</strong>
        <em>不能进入策略、配置或交易。</em>
      </div>
    `),
  ].join(""));
  setText(
    "phaseClosureConclusion",
    phaseClosure.metadata
      ? `V11.4 冻结 V6-V11 研究阶段：风险诊断仅限观察，保护研究和矛盾治理有研究价值；机会预测、配置 Alpha、资产选择、组合构建未验证，交易保持禁用。该结论关闭研究阶段，但不代表整个项目已完成。`
      : "V11.4 研究阶段最终冻结尚未生成。"
  );

  setText("implementationBoundaryStatus", phaseStatusLabel(implementationBoundarySummary.boundary_status));
  setText("implementationBoundaryPhase", phaseStatusLabel(implementationBoundarySummary.implementation_phase));
  setText("implementationBoundaryCandidates", `${integerText(implementationBoundarySummary.implementation_candidate_count)} 个`);
  setText("implementationBoundaryBlocked", `${integerText(implementationBoundarySummary.isolated_or_blocked_count)} 个`);
  setText("implementationBoundaryGate", phaseStatusLabel(implementationBoundaryGate.current_gate_result));
  setHtml("implementationBoundaryRows", implementationBoundaryComponents.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.component_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.boundary_status))}</strong>
      <em>${escapeHtml(row.isolation_reason || row.candidate_role || "--")}</em>
    </div>
  `).join(""));
  setText(
    "implementationBoundaryConclusion",
    implementationBoundary.metadata
      ? `V12.1 只定义研究到实现的隔离边界：${integerText(implementationBoundarySummary.implementation_candidate_count)} 个只读观察/治理候选，${integerText(implementationBoundarySummary.isolated_or_blocked_count)} 个组件继续隔离或禁用；全局实现门禁为${phaseStatusLabel(implementationBoundaryGate.current_gate_result)}，不输出策略、资产、ETF、权重、配置或交易。`
      : "V12.1 研究到实现隔离边界尚未生成。"
  );

  setText("readinessSpecStatus", phaseStatusLabel(readinessSpecSummary.readiness_specification_status));
  setText("readinessSpecReadiness", phaseStatusLabel(readinessSpecSummary.implementation_readiness_status));
  setText("readinessSpecComponents", `${integerText(readinessSpecSummary.component_spec_count)} 个`);
  setText("readinessSpecGates", `${integerText(readinessSpecSummary.global_gate_count)} 个`);
  setText("readinessSpecGateResult", phaseStatusLabel(readinessSpecSummary.implementation_gate_result));
  setHtml("readinessSpecRows", readinessSpecComponents.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.component_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.readiness_status))}</strong>
      <em>${escapeHtml(row.minimum_observation_rule || "--")}</em>
    </div>
  `).join(""));
  setText(
    "readinessSpecConclusion",
    readinessSpec.metadata
      ? `V12.2 只定义未来实现就绪证据标准：${integerText(readinessSpecSummary.component_spec_count)} 个组件标准、${integerText(readinessSpecSummary.global_gate_count)} 个全局门槛，所有证据当前均未评价，实现门禁仍为${phaseStatusLabel(readinessSpecSummary.implementation_gate_result)}。`
      : "V12.2 实现就绪证据标准尚未生成。"
  );

  setText("readinessAuditStatus", phaseStatusLabel(readinessAuditSummary.audit_framework_status));
  setText("readinessAuditPackage", phaseStatusLabel(readinessAuditSummary.evidence_package_status));
  setText("readinessAuditComponents", `${integerText(readinessAuditSummary.component_audit_count)} 个`);
  setText("readinessAuditReady", `${integerText(readinessAuditSummary.implementation_ready_component_count)} 个`);
  setText("readinessAuditGate", phaseStatusLabel(readinessAuditSummary.implementation_gate_result));
  setHtml("readinessAuditRows", readinessAuditComponents.map((row) => {
    const missing = Array.isArray(row.required_evidence_missing) ? row.required_evidence_missing.length : 0;
    return `
      <div class="duration-row">
        <span>${escapeHtml(row.component_id || "--")}</span>
        <strong>${escapeHtml(phaseStatusLabel(row.audit_status))}</strong>
        <em>缺失 ${integerText(missing)} 项证据；${escapeHtml(row.audit_decision || "--")}</em>
      </div>
    `;
  }).join(""));
  setText(
    "readinessAuditConclusion",
    readinessAudit.metadata
      ? `V12.3 只定义未来 evidence package 审计框架：当前证据包${phaseStatusLabel(readinessAuditSummary.evidence_package_status)}，${integerText(readinessAuditSummary.component_audit_count)} 个组件全部未提交证据，ready 组件 ${integerText(readinessAuditSummary.implementation_ready_component_count)} 个，实现门禁仍为${phaseStatusLabel(readinessAuditSummary.implementation_gate_result)}。`
      : "V12.3 实现证据审计框架尚未生成。"
  );

  setText("submissionProtocolStatus", phaseStatusLabel(submissionProtocolSummary.protocol_status));
  setText("submissionProtocolSubmission", phaseStatusLabel(submissionProtocolSummary.submission_status));
  setText("submissionProtocolContracts", `${integerText(submissionProtocolSummary.component_contract_count)} 个`);
  setText("submissionProtocolFields", `${integerText(submissionProtocolSummary.required_top_level_field_count)} 个`);
  setText("submissionProtocolPackage", submissionProtocolState.package_present === false ? "未提交" : "--");
  setHtml("submissionProtocolRows", submissionProtocolContracts.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.component_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.initial_submission_status))}</strong>
      <em>要求 ${integerText(Array.isArray(row.required_package_sections) ? row.required_package_sections.length : null)} 个包字段；当前提交 ${row.current_package_submitted ? "是" : "否"}。</em>
    </div>
  `).join(""));
  setText(
    "submissionProtocolConclusion",
    submissionProtocol.metadata
      ? `V13.1 只定义未来研究组件 evidence package 的提交协议：${integerText(submissionProtocolSummary.component_contract_count)} 个组件协议、${integerText(submissionProtocolSummary.required_top_level_field_count)} 个顶层字段；当前没有提交证据包，submitted=${integerText(submissionProtocolState.submitted_component_count)}，ready=${integerText(submissionProtocolState.implementation_ready_component_count)}。`
      : "V13.1 证据包提交协议尚未生成。"
  );

  setText("packageValidatorStatus", phaseStatusLabel(packageValidatorSummary.validation_engine_status));
  setText("packageValidatorPackage", phaseStatusLabel(packageValidatorSummary.current_package_status));
  setText("packageValidatorTemplates", `${integerText(packageValidatorSummary.component_template_count)} 个`);
  setText("packageValidatorReady", packageValidatorSummary.implementation_ready === false ? "否" : "--");
  setText("packageValidatorChecks", `${integerText(Array.isArray(packageValidatorEngine.supported_checks) ? packageValidatorEngine.supported_checks.length : null)} 项`);
  setHtml("packageValidatorRows", packageValidatorTemplates.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.component_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.package_status))}</strong>
      <em>${escapeHtml(row.validation_decision || "--")}</em>
    </div>
  `).join(""));
  setText(
    "packageValidatorConclusion",
    packageValidator.metadata
      ? `V13.2 只定义未来证据包自动校验引擎：当前证据包状态为${phaseStatusLabel(packageValidatorSummary.current_package_status)}，${integerText(packageValidatorSummary.component_template_count)} 个组件模板均未提交，支持 ${integerText(Array.isArray(packageValidatorEngine.supported_checks) ? packageValidatorEngine.supported_checks.length : null)} 类格式和边界检查。`
      : "V13.2 证据包校验引擎尚未生成。"
  );

  setText("invalidExampleStatus", phaseStatusLabel(invalidExampleSummary.example_status));
  setText("invalidExamplePackage", phaseStatusLabel(invalidExampleSummary.package_status));
  setText("invalidExampleDecision", phaseStatusLabel(invalidExampleSummary.validation_decision));
  setText("invalidExampleViolations", `${integerText(invalidExampleSummary.boundary_violation_count)} 个`);
  setText("invalidExampleReady", invalidExampleSummary.implementation_ready === false ? "否" : "--");
  setHtml("invalidExampleRows", [
    ["缺失字段", integerText(invalidExampleSummary.missing_item_count), "模拟包故意不完整。"],
    ["禁用输出", invalidExampleSummary.forbidden_output_detected ? "已检测" : "--", "校验器识别到越界字段。"],
    ["真实代码", invalidExampleDetail.contains_real_market_code === false ? "无" : "--", "样例不包含真实市场代码。"],
    ["真实权重", invalidExampleDetail.contains_real_weight === false ? "无" : "--", "样例不包含真实权重。"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "invalidExampleConclusion",
    invalidExample.metadata
      ? `V13.3 使用模拟不合格证据包验证 validator：包状态为${phaseStatusLabel(invalidExampleSummary.package_status)}，决策为${phaseStatusLabel(invalidExampleSummary.validation_decision)}，违例 ${integerText(invalidExampleSummary.boundary_violation_count)} 个，implementation_ready=false。`
      : "V13.3 不合格证据包拒绝测试尚未生成。"
  );

  setText("governanceFreezeStatus", phaseStatusLabel(governanceFreezeSummary.governance_freeze_status));
  setText("governanceFreezeStages", `${integerText(governanceFreezeSummary.frozen_stage_count)} 个`);
  setText("governanceFreezeCandidate", phaseStatusLabel(governanceFreezeSummary.implementation_candidate_status));
  setText("governanceFreezeReady", governanceFreezeSummary.implementation_ready === false ? "否" : "--");
  setText("governanceFreezeProject", phaseStatusLabel(governanceFreezeSummary.project_completion_status));
  setHtml("governanceFreezeRows", governanceFreezeChain.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.version || "--")} · ${escapeHtml(row.stage_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.status))}</strong>
      <em>source=${escapeHtml(row.source_status || "--")}；ready=${row.implementation_ready ? "是" : "否"}</em>
    </div>
  `).join(""));
  setText(
    "governanceFreezeConclusion",
    governanceFreeze.metadata
      ? `V13.4 冻结 V12-V13 实现准入治理链：${integerText(governanceFreezeSummary.frozen_stage_count)} 个阶段已冻结，未来可按协议提交单组件证据包，但当前没有真实候选，implementation_ready=false，项目仍未完成。`
      : "V13.4 实现准入治理冻结尚未生成。"
  );

  const riskEvidenceBlockerCount = riskEvidenceItems.filter((row) => (
    row.evidence_status === "submitted_negative" ||
    row.evidence_status === "submitted_inconclusive" ||
    row.evidence_status === "submitted_missing_required_live_log"
  )).length;
  setText("riskEvidenceStatus", phaseStatusLabel(riskEvidenceSummary.evidence_status));
  setText("riskEvidencePackage", phaseStatusLabel(riskEvidenceSummary.package_status));
  setText("riskEvidenceValidator", phaseStatusLabel(riskEvidenceValidatorResult.package_status || riskEvidenceBoundary.validator_package_status));
  setText("riskEvidenceReady", riskEvidenceSummary.implementation_ready === false ? "否" : "--");
  setText("riskEvidenceBlockers", `${integerText(riskEvidenceBlockerCount)} 项`);
  setHtml("riskEvidenceRows", riskEvidenceItems.map((row) => `
    <div class="duration-row">
      <span>${escapeHtml(row.evidence_id || "--")}</span>
      <strong>${escapeHtml(phaseStatusLabel(row.evidence_status))}</strong>
      <em>${escapeHtml(row.finding || "--")}</em>
    </div>
  `).join(""));
  setText(
    "riskEvidenceConclusion",
    riskEvidence.metadata
      ? `V14.1 已提交 risk_diagnostic_layer 证据包，V13.2 校验结果为${phaseStatusLabel(riskEvidenceValidatorResult.package_status)}，V12.3 投影审计为${phaseStatusLabel(riskEvidenceAuditProjection.audit_decision)}；由于误报、漏报、跨周期稳定性和 live shadow 缺口，implementation_ready=false。`
      : "V14.1 风险诊断层证据包尚未生成。"
  );

  const riskShadowFields = Array.isArray(riskShadowSchema.required_event_fields) ? riskShadowSchema.required_event_fields : [];
  const riskShadowBlockers = Array.isArray(riskShadowPromotion.blocking_reasons) ? riskShadowPromotion.blocking_reasons : [];
  setText("riskShadowStatus", phaseStatusLabel(riskShadowSummary.shadow_framework_status));
  setText("riskShadowPlan", phaseStatusLabel(riskShadowSummary.shadow_status));
  setText("riskShadowEvents", integerText(riskShadowSummary.live_event_count));
  setText("riskShadowTrade", riskShadowSummary.trade_enabled === false ? "否" : "--");
  setText("riskShadowReady", riskShadowSummary.implementation_ready === false ? "否" : "--");
  setHtml("riskShadowRows", [
    ["事件字段", `${integerText(riskShadowFields.length)} 项`, "未来 observation event 的必填记录字段。"],
    ["空日志", riskShadowSummary.live_event_count === 0 ? "0 条" : integerText(riskShadowSummary.live_event_count), "当前不生成 warning event。"],
    ["交易护栏", riskShadowGuardrails.trade_enabled === false && riskShadowGuardrails.position_adjustment_enabled === false ? "关闭" : "--", "交易、订单、券商连接和仓位调整均关闭。"],
    ["阻断项", `${integerText(riskShadowBlockers.length)} 项`, riskShadowBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowConclusion",
    riskShadow.metadata
      ? `V14.2 已定义 risk_diagnostic_layer 的无交易影子观察框架：shadow_status=${phaseStatusLabel(riskShadowSummary.shadow_status)}，live events=${integerText(riskShadowSummary.live_event_count)}，交易和仓位调整均关闭；implementation_ready=false。`
      : "V14.2 风险诊断影子观察框架尚未生成。"
  );

  const riskShadowLogBlockers = Array.isArray(riskShadowLogPromotion.blocking_reasons) ? riskShadowLogPromotion.blocking_reasons : [];
  setText("riskShadowLogStatus", phaseStatusLabel(riskShadowLogSummary.observation_status));
  setText("riskShadowLogMode", phaseStatusLabel(riskShadowLogSummary.log_status));
  setText("riskShadowLogEvents", integerText(riskShadowLogSummary.event_count));
  setText("riskShadowLogAuto", riskShadowLogSummary.auto_trigger_enabled === false ? "否" : "--");
  setText("riskShadowLogTrade", riskShadowLogSummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowLogRows", [
    ["追加模式", riskShadowLogControls.append_mode === "manual_only" ? "手动" : "--", "未来只能手动追加无交易 observation event。"],
    ["自动预警", riskShadowLogControls.auto_warning_detection_enabled === false ? "关闭" : "--", "当前不自动触发 warning。"],
    ["行情读取", riskShadowLogControls.market_data_reader_enabled === false ? "关闭" : "--", "初始化不读取行情、不重算特征。"],
    ["阻断项", `${integerText(riskShadowLogBlockers.length)} 项`, riskShadowLogBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowLogConclusion",
    riskShadowLog.metadata
      ? `V14.3 已初始化 active 空日志：event_count=${integerText(riskShadowLogSummary.event_count)}，manual_append_only=${riskShadowLogSummary.manual_append_only ? "true" : "false"}，auto_trigger=false，trade=false；implementation_ready=false。`
      : "V14.3 风险诊断影子观察日志尚未生成。"
  );

  const riskShadowReviewChecks = Array.isArray(riskShadowReviewFramework.review_checks) ? riskShadowReviewFramework.review_checks : [];
  const riskShadowReviewBlockers = Array.isArray(riskShadowReviewPromotion.blocking_reasons) ? riskShadowReviewPromotion.blocking_reasons : [];
  setText("riskShadowReviewFramework", phaseStatusLabel(riskShadowReviewSummary.review_framework_status));
  setText("riskShadowReviewStatus", phaseStatusLabel(riskShadowReviewSummary.review_status));
  setText("riskShadowReviewEvents", integerText(riskShadowReviewSummary.event_count));
  setText("riskShadowReviewCount", integerText(riskShadowReviewSummary.reviewed_event_count));
  setText("riskShadowReviewTrade", riskShadowReviewSummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowReviewRows", [
    ["复核检查", `${integerText(riskShadowReviewChecks.length)} 项`, riskShadowReviewChecks.join("；") || "--"],
    ["复核结果", phaseStatusLabel(riskShadowReviewResult.review_status), "当前没有 shadow event，因此不生成 event review。"],
    ["自动决策", riskShadowReviewFramework.auto_decision_allowed === false ? "关闭" : "--", "复核框架不允许自动风险判断。"],
    ["阻断项", `${integerText(riskShadowReviewBlockers.length)} 项`, riskShadowReviewBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowReviewConclusion",
    riskShadowReview.metadata
      ? `V14.4 已定义 shadow event 人工复核框架：review_status=${phaseStatusLabel(riskShadowReviewSummary.review_status)}，event_count=${integerText(riskShadowReviewSummary.event_count)}，reviewed=${integerText(riskShadowReviewSummary.reviewed_event_count)}，trade=false；implementation_ready=false。`
      : "V14.4 风险诊断影子事件复核尚未生成。"
  );

  const riskShadowCaptureFields = Array.isArray(riskShadowCaptureControls.manual_event_required_fields) ? riskShadowCaptureControls.manual_event_required_fields : [];
  const riskShadowCaptureDedupeFields = Array.isArray(riskShadowCaptureControls.dedupe_key_fields) ? riskShadowCaptureControls.dedupe_key_fields : [];
  const riskShadowCaptureBlockers = Array.isArray(riskShadowCapturePromotion.blocking_reasons) ? riskShadowCapturePromotion.blocking_reasons : [];
  setText("riskShadowCaptureStatus", phaseStatusLabel(riskShadowCaptureSummary.manual_capture_status));
  setText("riskShadowCaptureSourceEvents", integerText(riskShadowCaptureSummary.source_event_count));
  setText("riskShadowCaptureSubmitted", integerText(riskShadowCaptureSummary.submitted_event_count));
  setText("riskShadowCaptureDedupe", riskShadowCaptureControls.duplicate_detection_enabled === true ? "开启" : "--");
  setText("riskShadowCaptureTrade", riskShadowCaptureSummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowCaptureRows", [
    ["录入方式", phaseStatusLabel(riskShadowCaptureControls.append_mode), "必须提供人工事件文件；默认不生成事件。"],
    ["必填字段", `${integerText(riskShadowCaptureFields.length)} 项`, riskShadowCaptureFields.join("；") || "--"],
    ["去重字段", `${integerText(riskShadowCaptureDedupeFields.length)} 项`, riskShadowCaptureDedupeFields.join("；") || "--"],
    ["本次结果", phaseStatusLabel(riskShadowCaptureResult.append_result), riskShadowCaptureResult.result_note || "--"],
    ["阻断项", `${integerText(riskShadowCaptureBlockers.length)} 项`, riskShadowCaptureBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowCaptureConclusion",
    riskShadowCapture.metadata
      ? `V14.5 已建立人工 no-trade shadow event 录入能力：source_events=${integerText(riskShadowCaptureSummary.source_event_count)}，submitted=${integerText(riskShadowCaptureSummary.submitted_event_count)}，auto_trigger=false，trade=false；implementation_ready=false。`
      : "V14.5 风险诊断人工事件录入状态尚未生成。"
  );

  const riskShadowQualityIntegrity = Array.isArray(riskShadowQualityFramework.event_integrity_checks) ? riskShadowQualityFramework.event_integrity_checks : [];
  const riskShadowQualityResearch = Array.isArray(riskShadowQualityFramework.research_quality_checks) ? riskShadowQualityFramework.research_quality_checks : [];
  const riskShadowQualityBoundary = Array.isArray(riskShadowQualityFramework.boundary_checks) ? riskShadowQualityFramework.boundary_checks : [];
  const riskShadowQualityReviews = Array.isArray(riskShadowQualityResult.event_quality_reviews) ? riskShadowQualityResult.event_quality_reviews : [];
  const riskShadowQualityBlockers = Array.isArray(riskShadowQualityPromotion.blocking_reasons) ? riskShadowQualityPromotion.blocking_reasons : [];
  setText("riskShadowQualityStatus", phaseStatusLabel(riskShadowQualitySummary.quality_audit_status));
  setText("riskShadowQualityEvents", integerText(riskShadowQualitySummary.event_count));
  setText("riskShadowQualityChecked", integerText(riskShadowQualitySummary.quality_checked_events));
  setText("riskShadowQualityAuto", riskShadowQualitySummary.auto_decision_enabled === false ? "否" : "--");
  setText("riskShadowQualityTrade", riskShadowQualitySummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowQualityRows", [
    ["事件完整性", `${integerText(riskShadowQualityIntegrity.length)} 项`, riskShadowQualityIntegrity.join("；") || "--"],
    ["研究质量", `${integerText(riskShadowQualityResearch.length)} 项`, riskShadowQualityResearch.join("；") || "--"],
    ["边界检查", `${integerText(riskShadowQualityBoundary.length)} 项`, riskShadowQualityBoundary.join("；") || "--"],
    ["质量记录", `${integerText(riskShadowQualityReviews.length)} 条`, riskShadowQualityResult.result_note || "--"],
    ["阻断项", `${integerText(riskShadowQualityBlockers.length)} 项`, riskShadowQualityBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowQualityConclusion",
    riskShadowQuality.metadata
      ? `V14.6 已建立 shadow event 质量审计：status=${phaseStatusLabel(riskShadowQualitySummary.quality_audit_status)}，event_count=${integerText(riskShadowQualitySummary.event_count)}，checked=${integerText(riskShadowQualitySummary.quality_checked_events)}，auto_decision=false，trade=false；implementation_ready=false。`
      : "V14.6 风险诊断事件质量审计尚未生成。"
  );

  const riskShadowWorkflowSteps = Array.isArray(riskShadowWorkflowBody.workflow_steps) ? riskShadowWorkflowBody.workflow_steps : [];
  const riskShadowWorkflowRequiredFields = Array.isArray(riskShadowWorkflowRequirements.event_required_fields) ? riskShadowWorkflowRequirements.event_required_fields : [];
  const riskShadowWorkflowDedupe = Array.isArray(riskShadowWorkflowRequirements.dedupe_key_fields) ? riskShadowWorkflowRequirements.dedupe_key_fields : [];
  const riskShadowWorkflowBlockers = Array.isArray(riskShadowWorkflowPromotion.blocking_reasons) ? riskShadowWorkflowPromotion.blocking_reasons : [];
  setText("riskShadowWorkflowStatus", phaseStatusLabel(riskShadowWorkflowSummary.workflow_status));
  setText("riskShadowWorkflowEvents", integerText(riskShadowWorkflowSummary.event_count));
  setText("riskShadowWorkflowQueue", integerText(riskShadowWorkflowSummary.quality_queue_count));
  setText("riskShadowWorkflowAuto", riskShadowWorkflowSummary.auto_event_generation_enabled === false ? "否" : "--");
  setText("riskShadowWorkflowTrade", riskShadowWorkflowSummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowWorkflowRows", [
    ["流程步骤", `${integerText(riskShadowWorkflowSteps.length)} 步`, riskShadowWorkflowSteps.map((step) => step.step_id).join("；") || "--"],
    ["事件字段", `${integerText(riskShadowWorkflowRequiredFields.length)} 项`, riskShadowWorkflowRequiredFields.join("；") || "--"],
    ["去重字段", `${integerText(riskShadowWorkflowDedupe.length)} 项`, riskShadowWorkflowDedupe.join("；") || "--"],
    ["质量队列", phaseStatusLabel(riskShadowWorkflowQueue.queue_status), `queued=${integerText(riskShadowWorkflowQueue.queued_event_count)}`],
    ["阻断项", `${integerText(riskShadowWorkflowBlockers.length)} 项`, riskShadowWorkflowBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowWorkflowConclusion",
    riskShadowWorkflow.metadata
      ? `V14.7 已定义首个人工 shadow event 流程：workflow=${phaseStatusLabel(riskShadowWorkflowSummary.workflow_status)}，event_count=${integerText(riskShadowWorkflowSummary.event_count)}，queue=${integerText(riskShadowWorkflowSummary.quality_queue_count)}，auto_event=false，trade=false；implementation_ready=false。`
      : "V14.7 风险诊断首个事件流程尚未生成。"
  );

  const riskShadowInputRequired = Array.isArray(riskShadowInputSchema.required) ? riskShadowInputSchema.required : [];
  const riskShadowInputBlockers = Array.isArray(riskShadowInputPromotion.blocking_reasons) ? riskShadowInputPromotion.blocking_reasons : [];
  const riskShadowInputNoTrade = riskShadowInputTemplate.no_trade_observation || {};
  setText("riskShadowInputStatus", phaseStatusLabel(riskShadowInputSummary.template_status));
  setText("riskShadowInputSubmitted", riskShadowInputSummary.event_submitted === false ? "否" : "--");
  setText("riskShadowInputValidated", integerText(riskShadowInputSummary.validated_event_count));
  setText("riskShadowInputCli", riskShadowInputCli.validates_only === true ? "是" : "--");
  setText("riskShadowInputTrade", riskShadowInputSummary.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowInputRows", [
    ["必填字段", `${integerText(riskShadowInputRequired.length)} 项`, riskShadowInputRequired.join("；") || "--"],
    ["校验脚本", riskShadowInputCli.script || "--", riskShadowInputCli.usage || "--"],
    ["当前结果", phaseStatusLabel(riskShadowInputResult.validation_status), riskShadowInputResult.result_note || "--"],
    ["无交易模板", riskShadowInputNoTrade.trade_enabled === false ? "已关闭" : "--", "order/broker/position 均要求 false"],
    ["阻断项", `${integerText(riskShadowInputBlockers.length)} 项`, riskShadowInputBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowInputConclusion",
    riskShadowInput.metadata
      ? `V14.8 已建立首个人工 shadow event 输入包：template=${phaseStatusLabel(riskShadowInputSummary.template_status)}，event_submitted=${riskShadowInputSummary.event_submitted === false ? "false" : "--"}，validated=${integerText(riskShadowInputSummary.validated_event_count)}，auto_event=false，trade=false；implementation_ready=false。`
      : "V14.8 风险诊断事件输入包尚未生成。"
  );

  const riskShadowEvidenceBlockers = Array.isArray(riskShadowEvidenceGate.blocking_reasons) ? riskShadowEvidenceGate.blocking_reasons : [];
  setText("riskShadowEvidenceEvents", integerText(riskShadowEvidenceStats.event_count));
  setText("riskShadowEvidencePending", integerText(riskShadowEvidenceStats.pending_review_count));
  setText("riskShadowEvidenceReviewed", integerText(riskShadowEvidenceStats.reviewed_count));
  setText("riskShadowEvidenceQueue", integerText(riskShadowEvidenceStats.quality_queue_count));
  setText("riskShadowEvidenceTrade", riskShadowEvidenceGate.trade_enabled === false ? "否" : "--");
  setHtml("riskShadowEvidenceRows", [
    ["积累状态", phaseStatusLabel(riskShadowEvidenceStatus.evidence_accumulation_status), `shadow=${phaseStatusLabel(riskShadowEvidenceStatus.shadow_status)}`],
    ["误报/漏报", `${integerText(riskShadowEvidenceStats.false_warning_count)} / ${integerText(riskShadowEvidenceStats.missed_risk_count)}`, "等待真实事件和后验复核。"],
    ["已校验事件", integerText(riskShadowEvidenceStats.validated_event_count), "当前没有人工事件文件提交。"],
    ["实现状态", riskShadowEvidenceGate.implementation_ready === false ? "阻塞" : "--", riskShadowEvidenceGate.trade_enabled === false ? "交易关闭" : "--"],
    ["阻断项", `${integerText(riskShadowEvidenceBlockers.length)} 项`, riskShadowEvidenceBlockers.join("；") || "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "riskShadowEvidenceConclusion",
    riskShadowEvidence.metadata
      ? `V14.9 已建立 shadow evidence 积累看板：event_count=${integerText(riskShadowEvidenceStats.event_count)}，pending=${integerText(riskShadowEvidenceStats.pending_review_count)}，reviewed=${integerText(riskShadowEvidenceStats.reviewed_count)}，false_warning=${integerText(riskShadowEvidenceStats.false_warning_count)}，missed_risk=${integerText(riskShadowEvidenceStats.missed_risk_count)}，quality_queue=${integerText(riskShadowEvidenceStats.quality_queue_count)}；trade=false，implementation_ready=false。`
      : "V14.9 风险诊断影子证据积累看板尚未生成。"
  );

  setText("v15RebasePhase", v15RebaseSummary.phase || "--");
  setText("v15RebaseDirection", v15RebaseSummary.mainline_direction || "--");
  setText("v15RebasePrimary", v15RebaseSummary.primary_objective || "--");
  setText("v15RebaseSecondary", v15RebaseSummary.secondary_objective || "--");
  setText("v15RebaseTrade", v15RebaseSummary.production_trade_enabled === false ? "否" : "--");
  setHtml("v15RebaseRows", [
    ["方向状态", v15RebaseSummary.direction_status || "--", "V15.0 只声明方向，不运行回测。"],
    ["V12-V14 状态", v15RebaseFrozen.status || "--", v15RebaseFrozen.not_main_alpha_strategy === true ? "不是主 alpha 策略" : "--"],
    ["回测前置", v15RebaseSummary.must_backtest_before_strategy_claim === true ? "必须" : "--", "没有 V15+ 回测，不得声明策略有效。"],
    ["下一任务", v15RebaseRoadmap.v15_1 || "--", "开始构建收益导向回测数据集。"],
    ["交易边界", v15RebaseSummary.broker_connection_enabled === false ? "券商关闭" : "--", v15RebaseSummary.real_order_generation_enabled === false ? "真实订单关闭" : "--"],
    ["V15.0 禁止项", v15RebaseConstraints.does_not_run_backtest === true ? "不回测" : "--", v15RebaseConstraints.does_not_generate_trade_signal === true ? "不生成交易信号" : "--"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "v15RebaseConclusion",
    v15RebaseSummary.phase
      ? "V15.0 已把主开发方向切回收益第一、最大回撤第二；V12-V14 仅保留为治理、证据和影子观察基础设施，不再包装为已验证投资策略或组合引擎。"
      : "V15.0 主线收益策略重构产物尚未生成。"
  );

  const v15DatasetGroupLabels = {
    broad_indices: "宽基指数",
    sector_indices: "行业/主题指数",
    macro_cycle: "宏观周期",
    drawdown_context: "回撤背景",
    structural_bull: "结构性牛市",
  };
  const v15DatasetTargetLabels = {
    macro_drawdown_strategy: "宏观+回撤策略",
    structural_bull_rotation_strategy: "结构牛轮动策略",
    old_strategy_baseline: "旧策略基线",
  };
  const v15DatasetNoBacktest = v15DatasetConstraints.no_backtest_result === true || v15DatasetSummary.no_backtest_result === true;
  const v15DatasetTradeDisabled = v15DatasetSummary.production_trade_enabled === false;
  setText("v15DatasetStatus", v15DatasetSummary.dataset_status || "--");
  setText("v15DatasetGroups", integerText(v15DatasetSummary.dataset_group_count || v15DatasetGroups.length));
  setText("v15DatasetNoStrategy", v15DatasetSummary.does_not_run_strategy === true ? "是" : "--");
  setText("v15DatasetNoPosition", v15DatasetSummary.does_not_generate_position === true ? "是" : "--");
  setText("v15DatasetTrade", v15DatasetTradeDisabled ? "否" : "--");
  setHtml("v15DatasetRows", [
    ["数据组", v15DatasetGroups.map((key) => v15DatasetGroupLabels[key] || key).join(" / ") || "--", "只定义字段清单，不拉取全量数据。"],
    ["未来回测目标", v15DatasetTargets.map((key) => v15DatasetTargetLabels[key] || key).join(" / ") || "--", "后续任务才允许进入回测。"],
    ["无回测结果", v15DatasetNoBacktest ? "是" : "--", "V15.1 不产出收益、仓位、权重或信号。"],
    ["下一任务", v15DatasetSummary.next_task || "--", "由 ChatGPT 审核后再继续。"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "v15DatasetConclusion",
    v15DatasetSummary.phase
      ? "V15.1 已完成收益导向回测的数据集 manifest：宽基、行业、宏观、回撤和结构牛字段就绪；当前仍严格不回测、不生成仓位、不生成交易信号、不接券商。"
      : "V15.1 回测数据集 manifest 尚未生成。"
  );

  const v15MaterializationNoStrategy = v15MaterializationSummary.strategy_run === false;
  const v15MaterializationNoTradeSignal = v15MaterializationSummary.trade_signal_generated === false;
  const v15MaterializationNoBroker =
    v15MaterializationConstraints.no_broker_connection === true ||
    v15MaterializationSummary.production_trade_enabled === false;
  setText("v15MaterializationStatus", v15MaterializationSummary.materialization_status || "--");
  setText("v15MaterializationGroups", integerText(v15MaterializationSummary.dataset_groups_checked || v15MaterializationGroups.length));
  setText(
    "v15MaterializationAvailable",
    v15MaterializationSummary.available_source_count != null && v15MaterializationSummary.source_count != null
      ? `${integerText(v15MaterializationSummary.available_source_count)} / ${integerText(v15MaterializationSummary.source_count)}`
      : "--"
  );
  setText("v15MaterializationMissing", integerText(v15MaterializationSummary.missing_source_count));
  setText("v15MaterializationTrade", v15MaterializationSummary.production_trade_enabled === false ? "否" : "--");
  setHtml("v15MaterializationRows", [
    ["覆盖率", percentText(v15MaterializationSummary.coverage_ratio), v15MaterializationGroups.join(" / ") || "--"],
    ["完整数据抓取", v15MaterializationSummary.full_dataset_fetched === false ? "否" : "--", "V15.2 只读本地缓存和既有报告。"],
    ["策略/信号", v15MaterializationNoStrategy && v15MaterializationNoTradeSignal ? "未运行" : "需复核", "不生成回测收益、仓位或交易信号。"],
    ["Hash 记录", v15MaterializationQuality.source_hash_recorded === true ? "已记录" : "--", "记录 manifest hash 与本地 cache hash。"],
    ["券商连接", v15MaterializationNoBroker ? "关闭" : "--", "无订单、无 broker connection。"],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "v15MaterializationConclusion",
    v15MaterializationSummary.phase
      ? "V15.2 已生成本地回测数据覆盖率报告：它说明哪些源文件已可见、哪些字段还需语义映射；这不是策略回测，也不证明任何收益结论。"
      : "V15.2 回测数据落地状态尚未生成。"
  );

  const v15MacroTradeDisabled =
    v15MacroBacktestSummary.no_real_trade_order === true ||
    v15MacroBacktestConstraints.no_order_generation === true ||
    v15MacroBacktestConstraints.no_broker_connection === true;
  const v15MacroBench = (key, field) => {
    const row = v15MacroBacktestBenchmarks[key] || {};
    return row[field];
  };
  const v15MacroCoreSuccess =
    v15MacroBacktestComparison.beats_cash_baseline === true &&
    v15MacroBacktestComparison.beats_csi_300_buy_hold === true &&
    v15MacroBacktestComparison.improves_max_drawdown_vs_csi_300 === true;
  setText("v15MacroBacktestStatus", v15MacroBacktestSummary.backtest_status || "--");
  setText("v15MacroBacktestCagr", percentText(v15MacroBacktestStrategy.CAGR));
  setText("v15MacroBacktestAlpha", percentText(v15MacroBacktestStrategy.annual_alpha));
  setText("v15MacroBacktestDrawdown", percentText(v15MacroBacktestStrategy.max_drawdown));
  setText("v15MacroBacktestTrade", v15MacroTradeDisabled ? "否" : "--");
  setHtml("v15MacroBacktestRows", [
    [
      "回测区间",
      `${v15MacroBacktestSummary.start_date || "--"} ~ ${v15MacroBacktestSummary.end_date || "--"}`,
      `${integerText(v15MacroBacktestSummary.sessions)} 个交易日`,
    ],
    [
      "策略指标",
      `Calmar ${v15MacroBacktestStrategy.calmar ?? "--"} / Sharpe ${v15MacroBacktestStrategy.sharpe ?? "--"}`,
      `回撤恢复 ${integerText(v15MacroBacktestStrategy.drawdown_recovery_days)} 日`,
    ],
    [
      "基准年化",
      `现金 ${percentText(v15MacroBench("cash_baseline", "CAGR"))} / 沪深300全收益 ${percentText(v15MacroBench("csi_300_buy_hold", "CAGR"))}`,
      `上证 ${percentText(v15MacroBench("shanghai_composite_buy_hold", "CAGR"))} / 旧策略 ${percentText(v15MacroBench("old_strategy_baseline", "CAGR"))}`,
    ],
    [
      "核心对比",
      v15MacroBacktestComparison.beats_cash_baseline === true ? "跑赢现金" : "未跑赢现金",
      v15MacroBacktestComparison.beats_csi_300_buy_hold === true ? "跑赢沪深300全收益" : "未跑赢沪深300全收益",
    ],
    [
      "回撤改善",
      v15MacroBacktestComparison.improves_max_drawdown_vs_csi_300 === true ? "优于沪深300全收益" : "未优于沪深300全收益",
      v15MacroBacktestComparison.improves_calmar_vs_csi_300 === true ? "Calmar 改善" : "Calmar 未改善",
    ],
    [
      "交易边界",
      v15MacroBacktestSummary.research_backtest_only === true ? "研究回测" : "--",
      v15MacroTradeDisabled ? "不生成交易信号/不接券商/不下单" : "--",
    ],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "v15MacroBacktestConclusion",
    v15MacroBacktestSummary.phase
      ? (v15MacroCoreSuccess
          ? "V15.3 全收益与15bp正式口径通过核心门槛，但仍只是历史研究回测；不得直接转成实盘交易信号。"
          : "V15.3 全收益与15bp正式评价未通过：未跑赢全收益宽基时不能包装为成功策略，只能作为下一轮规则修正依据。")
      : "V15.3 宏观回撤基准回测尚未生成。"
  );

  const v15RobustnessTradeDisabled =
    v15MacroRobustnessSummary.no_real_trade_order === true ||
    v15MacroRobustnessConstraints.no_order_generation === true ||
    v15MacroRobustnessConstraints.no_broker_connection === true;
  setText("v15MacroRobustnessStatus", v15MacroRobustnessSummary.validation_status || "--");
  setText("v15MacroRobustnessRank", v15MacroRobustnessSummary.default_variant_rank ? `${v15MacroRobustnessSummary.default_variant_rank} / ${v15MacroRobustnessSummary.parameter_variants || 9}` : "--");
  setText("v15MacroRobustnessOosCagr", percentText(v15MacroRobustnessSummary.walk_forward_CAGR));
  setText("v15MacroRobustnessOosDrawdown", percentText(v15MacroRobustnessSummary.walk_forward_max_drawdown));
  setText("v15MacroRobustnessPromotion", v15MacroRobustnessSummary.promotion_ready === true ? "可推进" : "不可推进");
  setHtml("v15MacroRobustnessRows", [
    [
      "参数邻域",
      `${integerText(v15MacroRobustnessSummary.parameter_variants)} 组 / 年化差 ${percentText(v15MacroRobustnessSummary.CAGR_range)}`,
      v15MacroRobustnessSummary.parameter_neighborhood_stable === true ? "邻域结果接近" : "对参数较敏感",
    ],
    [
      "默认参数",
      `年化 ${percentText(v15MacroRobustnessSummary.default_CAGR)} / 排名 ${v15MacroRobustnessSummary.default_variant_rank || "--"}`,
      v15MacroRobustnessSummary.default_parameter_preferred === true ? "默认参数位于前列" : "默认参数不占优",
    ],
    [
      "滚动样本外",
      `年化 ${percentText(v15MacroRobustnessSummary.walk_forward_CAGR)} / Calmar ${v15MacroRobustnessSummary.walk_forward_calmar ?? "--"}`,
      `${integerText(v15MacroRobustnessSummary.walk_forward_cost_bps)}bp 成本 / ${integerText(v15MacroRobustnessSummary.walk_forward_years || (v15MacroRobustnessWalkForward.selections || []).length)} 个年度`,
    ],
    [
      "样本外对比",
      v15MacroRobustnessSummary.walk_forward_beats_csi_300 === true ? "跑赢同期沪深300" : "未跑赢同期沪深300",
      `最大回撤 ${percentText(v15MacroRobustnessSummary.walk_forward_max_drawdown)}`,
    ],
    [
      "时点边界",
      v15MacroRobustnessSummary.strict_point_in_time_status === "unverified" ? "尚未独立证实" : v15MacroRobustnessSummary.strict_point_in_time_status || "--",
      "历史 phase 可能为重构序列，发布时点链路仍需验证",
    ],
    [
      "交易边界",
      v15MacroRobustnessSummary.research_backtest_only === true ? "研究验证" : "--",
      v15RobustnessTradeDisabled ? "不生成交易信号/不接券商/不下单" : "--",
    ],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  setText(
    "v15MacroRobustnessConclusion",
    v15MacroRobustnessSummary.phase
      ? "V15.4 说明参数邻域结果接近，但 V15.3 默认参数排名靠后、样本外收益有限，且历史阶段严格时点性未证实，因此不能推进为可用策略。"
      : "V15.4 参数稳健性与滚动样本外验证尚未生成。"
  );

  const pointInTimeStatus = v15PointInTime.strict_point_in_time_phase_status || v15PointInTimeSummary.status;
  const pointInTimeStatusLabel = pointInTimeStatus === "rebuilt" ? "已严格重建" : pointInTimeStatus === "gap_report_ready" ? "缺口报告" : "--";
  setText("v15PointInTimeStatus", pointInTimeStatusLabel);
  setText("v15PointInTimeVerifiedDates", `${integerText(v15PointInTimeSummary.verified_date_count)} / ${integerText(v15PointInTimeSummary.phase_row_count)}`);
  setText("v15PointInTimeGaps", `${integerText(v15PointInTime.gap_count ?? v15PointInTimeSummary.gap_count)} 类`);
  setText("v15LateCycleFeatures", `${integerText(v15LateCycleSummary.feature_count)} 项`);
  setText("v15LateCycleBacktest", v15LateCycleSummary.backtest_allowed === true ? "允许" : "不允许");
  setHtml("v15PointInTimeRows", [
    [
      "宏观发布时间",
      `${integerText(v15PointInTimeSummary.macro_release_effective_safe_count)} / ${integerText(v15PointInTimeSummary.phase_row_count)} 个日期通过`,
      "仅证明宏观字段，不代表最终 phase 全链路通过",
    ],
    [
      "阶段来源链路",
      `${integerText(v15PointInTimeSummary.strict_lineage_count)} 个日期完整`,
      "缺少当时快照、版本与源文件哈希",
    ],
    [
      "风格上下文",
      `${integerText(v15PointInTimeSummary.reconstructed_style_date_count)} 个日期为事后重建`,
      `结构字段完整 ${integerText(v15PointInTimeSummary.structural_context_complete_count)} 个日期`,
    ],
    [
      "历史估值",
      `${integerText(v15PointInTimeSummary.valuation_available_count)} 个日期可用`,
      "PE/PB 百分位与 ERP 历史缺失",
    ],
  ].map(([label, value, note]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(note)}</em>
    </div>
  `).join(""));
  const lateCycleFeatureLabels = {
    valuation_percentile: "估值百分位",
    crowding_score: "拥挤度",
    turnover_concentration: "成交集中度",
    breadth_divergence: "宽度背离",
    late_cycle_heat: "晚周期热度",
    high_level_drawdown_risk: "高位回撤风险",
  };
  setHtml("v15LateCycleFeatureRows", v15LateCycleFeatureList.map((feature) => `
    <div class="alpha-source-row">
      <span>${escapeHtml(lateCycleFeatureLabels[feature.feature_id] || feature.feature_id || "--")}</span>
      <strong>${escapeHtml(feature.current_availability || "--")}</strong>
    </div>
  `).join(""));
  setText(
    "v15PointInTimeConclusion",
    v15PointInTimeSummary.phase
      ? "V15.5 确认现有阶段序列没有使用未来收益，但 140 个日期都缺少完整发布时间链路，仍是事后重建研究数据。高位风险覆盖层只完成六项数据契约，历史估值与不可变快照补齐前不得启动 V15.6 回测。"
      : "V15.5 严格时点阶段审计尚未生成。"
  );

  setText("v15LedgerDates", integerText(v15SnapshotLedgerSummary.decision_date_count));
  setText("v15LedgerComplete", `${integerText(v15SnapshotLedgerSummary.snapshot_complete_count)} / ${integerText(v15SnapshotLedgerSummary.decision_date_count)}`);
  setText("v15LedgerEligible", `${integerText(v15SnapshotLedgerSummary.strict_point_in_time_eligible_count)} / ${integerText(v15SnapshotLedgerSummary.decision_date_count)}`);
  setText("v15LedgerHashes", integerText(v15SnapshotLedgerSummary.hash_verified_count));
  setText("v15LedgerBacktest", v15SnapshotLedgerSummary.backtest_allowed === true ? "允许" : "不允许");
  const v15LedgerObservations = v15SnapshotLedgerSummary.observations_available_by_group || {};
  const v15LedgerGroupLabels = {
    macro: "宏观",
    broad_index: "宽基",
    style_context: "风格上下文",
    structural_context: "结构上下文",
    valuation: "历史估值",
  };
  setHtml("v15LedgerSourceRows", Object.entries(v15LedgerGroupLabels).map(([groupId, label]) => `
    <div class="duration-row">
      <span>${escapeHtml(label)}</span>
      <strong>可定位观测 ${integerText(v15LedgerObservations[groupId])} / ${integerText(v15SnapshotLedgerSummary.decision_date_count)}</strong>
      <em>完整历史快照 0 · 当前文件 hash 不作历史证明</em>
    </div>
  `).join(""));
  setText(
    "v15LedgerConclusion",
    v15SnapshotLedgerSummary.phase
      ? "V15.6 已把五类源逐日列账，但 140 个日期都没有完整的历史抓取时间、源版本和不可变历史快照 hash，因此严格可用仍为 0/140。账本只完成缺口盘点，覆盖层回测继续禁止。"
      : "V15.6 不可变时点源快照账本尚未生成。"
  );

  setText("v15DailySnapshotDate", toIsoDate(v15DailySnapshot.snapshot_date));
  setText("v15DailySnapshotSources", `${integerText(v15DailySnapshot.available_source_count)} / ${integerText((v15DailySnapshot.available_source_count || 0) + (v15DailySnapshot.missing_source_count || 0))}`);
  setText("v15DailySnapshotHash", v15DailySnapshot.manifest_sha256 ? `${String(v15DailySnapshot.manifest_sha256).slice(0, 12)}...` : "--");
  setText("v15ForwardMacro", v15ForwardReadouts.macro_cycle || "--");
  setText("v15ForwardPhase", v15ForwardReadouts.late_cycle_risk || "--");
  setText("v15ForwardDecisionStatus", v15ForwardDecisionBody.decision_status || "--");
  setText("v15ForwardJournalRecords", integerText(v15ForwardJournal.record_count));
  setText("v15ForwardJournalLatest", toIsoDate(v15ForwardJournal.latest_decision_date));
  setText("v15ForwardJournalPending", integerText(v15ForwardJournal.pending_outcome_count));
  setText("v15ForwardOutcomeRecords", integerText(v15ForwardOutcomes.outcome_record_count));
  setText("v15ForwardOutcomeCompleted", integerText(v15ForwardOutcomes.completed_outcome_count));
  setText("v15ForwardOutcomePending", integerText(v15ForwardOutcomes.pending_outcome_count));
  setText(
    "v15ForwardConclusion",
    v15DailySnapshot.phase
      ? `V15.7 已建立不可变快照，V15.8 日志累计 ${integerText(v15ForwardJournal.record_count)} 条。V15.9 当前完成 ${integerText(v15ForwardOutcomes.completed_outcome_count)} 个沪深300前向窗口、待完成 ${integerText(v15ForwardOutcomes.pending_outcome_count)} 个；这只是市场结果，不是策略收益或交易信号。`
      : "V15.7 每日前向快照尚未生成。"
  );

  setText("hazardRawRate", percentText(rawHazard.event_rate));
  setText("hazardStructuralRate", percentText(structuralHazard.event_rate));
  setText("hazardRows", integerText(structuralHazard.observations));
  setText(
    "hazardConclusion",
    `结构化切分把跳变事件从 ${integerText(rawHazard.events)} 次压缩到 ${integerText(structuralHazard.events)} 次，减少日内噪声后更适合观察主周期风险。`
  );

  setText("modelAuc", fixedText(model.roc_auc, 3));
  setText("modelLift", fixedText(model.lift_vs_random, 2));
  setText("volatilityAuc", fixedText(volatility.roc_auc, 3));
  setText("sensitivityRange", `${fixedText(sensitivity.auc_min, 3)} - ${fixedText(sensitivity.auc_max, 3)}`);
  const modelGap = typeof volatility.roc_auc === "number" && typeof model.roc_auc === "number"
    ? model.roc_auc - volatility.roc_auc
    : null;
  const modelDirection = typeof modelGap === "number" && modelGap < 0 ? "弱于" : "强于";
  setText(
    "modelConclusion",
    `默认模型相对随机基准有正向识别力，但敏感性并非全部通过；默认口径下多因子模型${modelDirection}波动单因子。`
  );

  setText("survivalEventRate", percentText(structuralSurvival.event_rate));
  setText("survivalEvents", integerText(structuralSurvival.events));
  setText("survivalRows", integerText(structuralSurvival.observations));
  const durationOrder = ["bull", "range", "bear", "transition"];
  const durations = structuralSurvival.durations || {};
  setHtml("durationList", durationOrder
    .filter((key) => durations[key])
    .map((key) => {
      const item = durations[key];
      return `
        <div class="duration-row">
          <span>${regimeLabel(key)}</span>
          <strong>最长 ${integerText(item.max_duration)} 日</strong>
          <em>平均 ${fixedText(item.avg_duration, 1)} 日</em>
        </div>
      `;
    })
    .join(""));

  setHtml("conclusionList", listHtml(conclusionItemsForPage(results)));
}

function setForecastPanel(track) {
  const forecast = track.forecast || {};
  const probabilities = forecast.probabilities || {};
  const confidence = forecast.confidence || {};
  const levels = forecast.key_levels || {};
  const explanation = forecast.explanation || {};
  document.getElementById("trackRange").textContent =
    `${toIsoDate(track.cycle.start_date)} 至 ${toIsoDate(track.as_of)}`;
  document.getElementById("forecastHorizon").textContent = forecast.basis_horizon_sessions || "--";
  document.getElementById("forecastSample").textContent = forecast.sample_size ? `样本 ${forecast.sample_size}` : "样本不足";
  setText("forecastConfidence", percentText(confidence.score));
  setText("forecastConfidenceLabel", confidence.level_label || "--");
  document.getElementById("forecastConfidenceLabel").className = `confidence-level confidence-${confidence.level || "insufficient"}`;
  setText("forecastConfidenceReason", confidence.reason || "样本不足，暂不输出展望置信度。");
  setProbability("probContinue", "barContinue", probabilities.continue);
  setProbability("probRange", "barRange", probabilities.range);
  setProbability("probWeaken", "barWeaken", probabilities.weaken);
  document.getElementById("projectionList").innerHTML = (forecast.paths || [])
    .map(
      (path) => `
        <div class="projection-row">
          <span>${path.horizon_sessions}日</span>
          <div>
            <strong>${priceText(path.neutral)}</strong>
            <small>谨慎 ${priceText(path.cautious)} / 乐观 ${priceText(path.optimistic)} · 中性 ${path.median_return_pct}%</small>
          </div>
        </div>
      `
    )
    .join("");
  document.getElementById("keyLevels").innerHTML = [
    ["当前收盘", priceText(levels.current_close)],
    ["MA120", priceText(levels.ma120)],
    ["MA250", priceText(levels.ma250)],
    ["60日回撤", typeof levels.drawdown_60_pct === "number" ? `${levels.drawdown_60_pct}%` : "--"],
  ]
    .map(([label, value]) => `<div class="level-row"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  document.getElementById("explanationSummary").textContent = explanation.summary || "--";
  document.getElementById("explanationFacts").innerHTML = listHtml(explanation.facts);
  document.getElementById("explanationMethod").innerHTML = listHtml(explanation.method);
  document.getElementById("explanationResult").textContent = explanation.result || "--";
}

function cycleBlockMeta(block) {
  const start = toIsoDate(block.start_date);
  const end = block.ongoing ? "至今" : toIsoDate(block.end_date);
  const duration = typeof block.elapsed_years === "number" ? `约 ${block.elapsed_years} 年` : "--";
  return `${start} - ${end} · ${duration} · ${signedPercentText(block.return_pct)}`;
}

function cycleBlockHtml(block) {
  const stateClass = block.state === "bull" ? "bull" : "bear";
  const features = (block.features || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const themes = (block.themes || [])
    .map((theme) => `<span class="theme-chip">${escapeHtml(theme)}</span>`)
    .join("");
  return `
    <article class="cycle-block cycle-block-${stateClass}">
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

function setCycleBlocks(blocks) {
  const target = document.getElementById("cycleBlocks");
  const majorBlocks = (blocks || []).filter((block) => block.major).reverse();
  if (!majorBlocks.length) {
    target.innerHTML = '<div class="cycle-blocks-empty">暂无足够长的周期切块。</div>';
    return;
  }
  const basis = majorBlocks.find((block) => block.theme_basis)?.theme_basis || "";
  target.innerHTML = `
    <div class="cycle-blocks-head">
      <div>
        <h2>主要周期切块</h2>
        <p>按市场主周期切分，重点看每轮牛市的主线主题、扩散方式和风险偏好特征。</p>
      </div>
    </div>
    <div class="cycle-block-list">${majorBlocks.map(cycleBlockHtml).join("")}</div>
    <p class="cycle-block-basis">${escapeHtml(basis)}</p>
  `;
}

function pageNeedsResults() {
  return Boolean(
    document.body?.dataset.resultsPage ||
      document.querySelector(
        "#riskLevel, #portfolioExposure, #styleRegime, #rotationSignal, #shadowFinalAlpha, #regimeAttributionTotalAlpha, #hazardRawRate"
      )
  );
}

function pageNeedsRegime() {
  return Boolean(document.querySelector("#regimePanel, #scoreList, #scoreHistoryChart"));
}

function pageNeedsCycle() {
  return Boolean(document.querySelector("#cycleTitle"));
}

function pageNeedsFullResults() {
  return Boolean(document.querySelector("#shadowEquityChart, #rotationBacktestChart, #macroStyleEtfChart"));
}

async function loadDashboard() {
  const button = document.getElementById("refreshButton");
  if (button) {
    button.disabled = true;
    button.textContent = "刷新中";
  }
  try {
    const needsRegime = pageNeedsRegime();
    const needsCycle = pageNeedsCycle();
    const needsResults = pageNeedsResults();
    const needsScoreHistory = Boolean(document.getElementById("scoreHistoryChart"));
    const resultUrl = pageNeedsFullResults() ? "/api/results/summary" : "/api/results/summary?compact=1";
    const [current, cycle, scoreHistory, results] = await Promise.all([
      needsRegime ? getJson("/api/regime/current") : Promise.resolve(null),
      needsCycle ? getJson("/api/regime/cycle") : Promise.resolve(null),
      needsScoreHistory ? getJson("/api/regime/score-history") : Promise.resolve(null),
      needsResults ? getJson(resultUrl) : Promise.resolve(null),
    ]);
    state.current = current || null;
    state.cycle = cycle || null;
    state.scoreHistory = scoreHistory || null;
    state.results = results || null;

    if (current) {
      setRegimePanel(current);
      setScoreList(current.sub_scores);
    }
    if (scoreHistory && document.getElementById("scoreHistoryChart")) {
      const chartHistory = mergeScoreHistoryCurrent(scoreHistory, current);
      renderScoreHistoryChart("scoreHistoryChart", chartHistory);
      setScoreHistoryNote(chartHistory);
    }
    if (cycle) setCyclePanel(phaseFromMajorCycle(cycle));
    if (current && cycle) setRegimeContextNote(current, cycle);
    if (results) setResultsPanel(results);
    if (results && document.getElementById("shadowEquityChart")) renderShadowEquityChart("shadowEquityChart", results.shadow_backtest || {});
    if (results && document.getElementById("rotationBacktestChart")) renderEtfRotationBacktestChart("rotationBacktestChart", results.etf_rotation_backtest || {});
    if (results && document.getElementById("macroStyleEtfChart")) renderMacroStyleEtfBacktestChart("macroStyleEtfChart", results.macro_style_etf_backtest || {});
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "刷新";
    }
  }
}

document.getElementById("refreshButton")?.addEventListener("click", loadDashboard);
document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  const button = target?.closest("[data-strategy-sort]");
  if (!button || !document.getElementById("strategyDirectoryGrid")) return;
  const key = button.dataset.strategySort;
  if (!key) return;
  if (strategyDirectorySort.key === key) {
    strategyDirectorySort.direction = strategyDirectorySort.direction === "asc" ? "desc" : "asc";
  } else {
    strategyDirectorySort.key = key;
    strategyDirectorySort.direction = key === "strategy" ? "asc" : "desc";
  }
  if (state.results) setStrategyDirectory(state.results);
});
document.getElementById("rotationBacktestReset")?.addEventListener("click", () => {
  resetEtfRotationBacktestChart("rotationBacktestChart");
});
document.getElementById("macroStyleReset")?.addEventListener("click", () => {
  resetEtfRotationBacktestChart("macroStyleEtfChart");
});
loadDashboard();
