# V9.4 配置研究实验模板审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.4 — Allocation Research Experiment Template Framework`。

核心边界：

- 只定义未来如何做配置研究实验。
- 只读取 V9.3 配置研究验证计划。
- 不运行实验。
- 不生成实验结果。
- 不生成验证结果。
- 不生成回测结果。
- 不做参数搜索或优化。
- 不定义资产、ETF、权重、仓位百分比、买卖或调仓。

## 新增/修改文件

- `allocation_research/allocation_experiment_schema.py`
  - 定义 V9.4 experiment template schema。
  - 允许输入仅为 V9.3。
  - 模板字段包括假设引用、实验问题、预声明比较方法、评价标准、失败标准、防过拟合规则和执行状态。
- `allocation_research/allocation_experiment_audit.py`
  - 为 V9.3 的 4 个验证计划生成 4 个实验模板。
  - 校验所有模板均为 `template_only_not_executed`。
  - 校验只比较 research posture，不定义资产、ETF、权重或交易。
- `scripts/run_allocation_experiment_template.py`
  - 生成 `data/allocation_experiment_templates.json`。
- `scripts/test_allocation_experiment_template.py`
  - 测试 schema、模板状态、预声明比较、防过拟合、禁止输出、时间安全和写文件。
- `data/allocation_experiment_templates.json`
  - V9.4 架构产物。
- `web/app.py`
  - 新增 `/api/allocation-research/experiment-templates`。
  - 将 V9.4 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“配置研究实验模板”卡片。
- `web/static/dashboard.js`
  - 渲染模板数量、执行状态、评价标准、边界和模板列表。

## 关键结果

- engine：`V9.4 Allocation Research Experiment Template Framework`
- 数据基准：`20260707`
- source context：`risk_controlled_opportunity_watch`
- source conclusion：`allocation_validation_plan_defined_not_executed`
- validation_plan_count：4
- experiment_template_count：4
- executed_experiment_count：0
- conclusion：`allocation_experiment_templates_defined_not_executed`
- `experiment_template_ready`：`false`
- `experiment_executed`：`false`
- `ready_for_asset_selection`：`false`
- `ready_for_etf_mapping`：`false`
- `ready_for_weight_generation`：`false`
- `ready_for_backtest`：`false`
- `ready_for_validation_result`：`false`
- `ready_for_optimization`：`false`
- `ready_for_trade`：`false`

## 实验模板口径

每个模板只允许比较：

- baseline_research_posture
- alternative_research_posture

每个模板评价标准包括：

- out_of_sample_design
- drawdown_audit_design
- contradiction_audit_design
- regime_stability_design
- time_safety_design

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
- Validation Result。
- Experiment Result。
- Optimization。

## Web / API

- `/api/allocation-research/experiment-templates`
- `/api/allocation-research/validation-plan`
- `/api/allocation-research/hypotheses`
- `/api/allocation-research/architecture`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行或需要审计复核运行：

```powershell
python scripts\run_allocation_experiment_template.py
python scripts\test_allocation_experiment_template.py
python -m py_compile allocation_research\allocation_experiment_schema.py allocation_research\allocation_experiment_audit.py scripts\run_allocation_experiment_template.py scripts\test_allocation_experiment_template.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API / 页面烟测目标：

- `/api/allocation-research/experiment-templates` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `allocation_experiment_templates`。
- `/api` 返回 200 且包含 `/api/allocation-research/experiment-templates`。
- `/validation` 返回 200 且可见“配置研究实验模板”卡片。

## 待审计问题

1. V9.4 是否通过？
2. 是否可以进入 V9.5：冻结 V9.1-V9.4 为“配置研究设计层”，形成设计层总文档和一致性审计？
3. 或者下一步是否允许进入真正的实验执行阶段？如果允许，需要明确哪些边界仍禁止。

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.4，本次不应纳入 commit。
