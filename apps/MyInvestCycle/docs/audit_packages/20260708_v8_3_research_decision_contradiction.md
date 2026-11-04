# V8.3 研究语境矛盾归因审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V8.3 — Research Decision Contradiction Attribution`。

核心边界：

- 解释 V8.1 研究语境在重点历史阶段为什么失败。
- 固定读取 V8.2、V8.1、V6 和 V7 现有产物。
- 不修改 V6。
- 不修改 V7。
- 不新增状态。
- 不新增评分。
- 不输出配置、ETF、权重或交易。
- 不做参数优化。

## 新增/修改文件

- `decision_research/research_decision_contradiction.py`
  - 构建 V8.3 研究语境矛盾归因。
  - 聚焦 low consistency、contradiction count > 0 和 2024-2026 结构行情场景。
- `scripts/run_research_decision_contradiction.py`
  - 生成 `data/research_decision_contradiction.json`。
- `scripts/test_research_decision_contradiction.py`
  - 校验归因数量、重点场景、边界和禁止输出。
- `data/research_decision_contradiction.json`
  - V8.3 生成产物。
- `decision_research/__init__.py`
  - 导出 V8.3 构建与写入函数。
- `web/app.py`
  - 新增 `/api/decision/contradiction-attribution`。
  - 将 V8.3 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“研究语境矛盾归因”卡片。
- `web/static/dashboard.js`
  - 渲染重点场景、归因条数、矛盾类型、可能原因和输出边界。

## 关键结果

- 重点场景：5。
- 归因条数：5。
- 矛盾类型：
  - rapid_context_switching：1。
  - participation_context_during_bear：1。
  - persistent_wait_during_style_divergence：1。
  - structural_market_opportunity_not_captured：1。
  - monitor_only_no_primary_contradiction：1。
- 可能原因：
  - macro_context_transition_noise：1。
  - risk_axis_lag_or_structural_rotation_missed：1。
  - style_divergence_not_resolved_by_current_context：1。
  - opportunity_axis_weak_and_width_index_divergence：1。
  - scenario_not_primary_failure_case：1。
- 结论：`contradiction_attribution_research_only_no_rule_change`。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 解释口径

V8.3 说明：

- 2015 主要问题是上下文快速切换。
- 2018 主要问题是熊市中 PARTICIPATE 语境偏多。
- 2021 主要问题是风格分化没有被当前上下文充分解释。
- 2024-2026 主要问题是结构行情机会解释不足。
- 该层只归因失败来源，不修规则、不输出策略。

## Web / API

- `/api/decision/contradiction-attribution`
- `/api/decision/scenario-audit`
- `/api/decision/research-context`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行：

```powershell
python scripts\run_research_decision_contradiction.py
python scripts\test_research_decision_contradiction.py
python -m py_compile web\app.py decision_research\research_decision_contradiction.py scripts\run_research_decision_contradiction.py scripts\test_research_decision_contradiction.py
node --check web\static\dashboard.js
python -m compileall decision_research asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/decision/contradiction-attribution` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `research_decision_contradiction`。
- `/api` 返回 200 且包含 `/api/decision/contradiction-attribution`。
- `/validation` 返回 200。

已运行内置浏览器页面检查：

- `/validation` 可见“研究语境矛盾归因”卡片。
- 卡片显示“5”“5”“不改规则/不配置/不交易”。

## 待审计问题

1. V8.3 是否通过？
2. 是否同意 V8 到目前为止仍只能停留在研究解释层？
3. 下一步是否应做 V8.4：Research Decision Freeze & Summary，把 V8.1-V8.3 冻结为研究解释架构，而不是继续扩展？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V8.3，本次不应纳入 commit。
