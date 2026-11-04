# V9.3 配置研究验证计划审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.3 — Allocation Research Validation Plan Framework`。

核心边界：

- 只设计如何验证 V9.2 假设。
- 只读取 V9.2 配置研究假设框架。
- 不执行验证。
- 不生成验证结果。
- 不生成回测结果。
- 不做参数搜索。
- 不做阈值优化。
- 不定义资产、ETF、权重、仓位百分比、买卖或调仓。

## 新增/修改文件

- `allocation_research/allocation_validation_plan_schema.py`
  - 定义 V9.3 validation plan schema。
  - 允许输入仅为 V9.2。
  - 要求计划包含验证目标、证据要求、失败标准、防过拟合规则、执行状态和禁止解释。
- `allocation_research/allocation_validation_plan_audit.py`
  - 为 V9.2 的 4 条假设生成 4 个验证计划。
  - 校验所有计划均为 `planned_not_executed`。
  - 校验不执行验证、不生成结果、不做配置或交易。
- `scripts/run_allocation_validation_plan.py`
  - 生成 `data/allocation_validation_plan.json`。
- `scripts/test_allocation_validation_plan.py`
  - 测试 schema、计划状态、防过拟合规则、禁止输出、时间安全和写文件。
- `data/allocation_validation_plan.json`
  - V9.3 架构产物。
- `web/app.py`
  - 新增 `/api/allocation-research/validation-plan`。
  - 将 V9.3 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“配置研究验证计划”卡片。
- `web/static/dashboard.js`
  - 渲染计划数量、执行状态、证据要求、防过拟合规则、边界和计划列表。

## 关键结果

- engine：`V9.3 Allocation Research Validation Plan Framework`
- 数据基准：`20260707`
- source context：`risk_controlled_opportunity_watch`
- source conclusion：`allocation_hypothesis_framework_defined_unvalidated`
- hypothesis_count：4
- validation_plan_count：4
- executed_plan_count：0
- conclusion：`allocation_validation_plan_defined_not_executed`
- `validation_plan_ready`：`false`
- `validation_executed`：`false`
- `ready_for_asset_selection`：`false`
- `ready_for_etf_mapping`：`false`
- `ready_for_weight_generation`：`false`
- `ready_for_backtest`：`false`
- `ready_for_optimization`：`false`
- `ready_for_trade`：`false`

## 验证计划覆盖

每个假设都要求：

- out_of_sample_test_design
- walk_forward_design
- drawdown_audit_design
- contradiction_audit_design
- regime_stability_design
- time_safety_audit_design
- research_only_report_design

每个假设都要求防过拟合规则：

- no_parameter_search
- no_best_period_selection
- no_threshold_optimization
- no_result_based_candidate_promotion
- predeclare_failure_criteria

## 明确拒绝

- Asset Selection。
- ETF Mapping。
- Portfolio Weight。
- Top N。
- Exposure Percent。
- Buy Signal。
- Sell Signal。
- Rebalance Instruction。
- Broker Order。
- Backtest Result。
- Optimization。
- Validation Result。

## Web / API

- `/api/allocation-research/validation-plan`
- `/api/allocation-research/hypotheses`
- `/api/allocation-research/architecture`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行或需要审计复核运行：

```powershell
python scripts\run_allocation_validation_plan.py
python scripts\test_allocation_validation_plan.py
python -m py_compile allocation_research\allocation_validation_plan_schema.py allocation_research\allocation_validation_plan_audit.py scripts\run_allocation_validation_plan.py scripts\test_allocation_validation_plan.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API / 页面烟测目标：

- `/api/allocation-research/validation-plan` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `allocation_validation_plan`。
- `/api` 返回 200 且包含 `/api/allocation-research/validation-plan`。
- `/validation` 返回 200 且可见“配置研究验证计划”卡片。

## 待审计问题

1. V9.3 是否通过？
2. 是否可以进入 V9.4：定义非优化、预声明的配置研究实验模板，但仍不执行回测、不输出结果、不产生 ETF/权重/交易？
3. 还是需要先冻结 V9.1-V9.3 为“配置研究设计层”？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.3，本次不应纳入 commit。
