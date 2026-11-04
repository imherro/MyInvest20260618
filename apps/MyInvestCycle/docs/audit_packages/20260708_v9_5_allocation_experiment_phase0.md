# V9.5 配置研究实验 Phase 0 审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.5 — Allocation Research Experiment Execution Phase 0`。

核心边界：

- 执行 V9.4 预声明实验模板的 Phase 0 研究纪律检查。
- 只读取 V9.4 实验模板。
- 不读取市场数据寻找最佳规则。
- 不生成市场回测结果。
- 不做参数搜索或优化。
- 不自动选择最佳实验。
- 不提升为配置候选。
- 不定义资产、ETF、权重、仓位百分比、买卖或调仓。

## 新增/修改文件

- `allocation_research/allocation_experiment_result.py`
  - 定义 V9.5 Phase 0 result schema。
  - 允许结果字段包括 `validation_result`，但禁止资产、ETF、权重、回测结果、优化和交易输出。
- `allocation_research/allocation_experiment_runner.py`
  - 读取 V9.4 模板，执行 Phase 0 设计纪律检查。
  - 产出每个模板的 design-level validation result。
  - 明确 `market_data_loaded=false`、`performance_measured=false`、`candidate_promotion_allowed=false`。
- `scripts/run_allocation_experiment.py`
  - 生成 `data/allocation_experiment_results_phase0.json`。
- `scripts/test_allocation_experiment.py`
  - 测试 Phase 0 执行结果、禁止输出、时间安全和写文件。
- `data/allocation_experiment_results_phase0.json`
  - V9.5 Phase 0 产物。
- `web/app.py`
  - 新增 `/api/allocation-research/experiment-results`。
  - 将 V9.5 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“配置研究实验 Phase 0”卡片。
- `web/static/dashboard.js`
  - 渲染执行数量、design pass、市场验证数量、边界和结果列表。

## 关键结果

- engine：`V9.5 Allocation Research Experiment Execution Phase 0`
- 数据基准：`20260707`
- source context：`risk_controlled_opportunity_watch`
- source conclusion：`allocation_experiment_templates_defined_not_executed`
- experiment_template_count：4
- executed_experiment_count：4
- validation_result_count：4
- design_pass_count：4
- design_fail_count：0
- market_validation_result_count：0
- conclusion：`allocation_experiment_phase0_completed_research_only_not_investable`
- `ready_for_asset_selection`：`false`
- `ready_for_etf_mapping`：`false`
- `ready_for_weight_generation`：`false`
- `ready_for_backtest`：`false`
- `ready_for_optimization`：`false`
- `ready_for_trade`：`false`
- `promoted_to_candidate`：`false`
- `investable_output_generated`：`false`

## Phase 0 口径

本阶段每条结果的 `validation_result` 为：

- `design_pass_market_not_evaluated`

含义：

- 预声明模板设计完整。
- 尚未读取市场数据。
- 尚未测量市场表现。
- 尚未生成样本外市场结果。
- 不可用于资产选择、ETF 映射、权重、优化或交易。

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

## Web / API

- `/api/allocation-research/experiment-results`
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
python scripts\run_allocation_experiment.py
python scripts\test_allocation_experiment.py
python -m py_compile allocation_research\allocation_experiment_result.py allocation_research\allocation_experiment_runner.py scripts\run_allocation_experiment.py scripts\test_allocation_experiment.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API / 页面烟测目标：

- `/api/allocation-research/experiment-results` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `allocation_experiment_results`。
- `/api` 返回 200 且包含 `/api/allocation-research/experiment-results`。
- `/validation` 返回 200 且可见“配置研究实验 Phase 0”卡片。

## 待审计问题

1. V9.5 是否通过？
2. Phase 0 的 `design_pass_market_not_evaluated` 口径是否清晰，是否避免被误读为市场验证通过？
3. 下一步是否允许进入 Phase 1 市场验证？如果允许，需要指定可以读取哪些冻结数据，以及哪些输出仍然禁止。

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.5，本次不应纳入 commit。
