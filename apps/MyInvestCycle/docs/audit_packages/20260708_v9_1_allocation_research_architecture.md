# V9.1 配置研究架构基础审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.1 — Allocation Research Architecture Foundation`。

核心边界：

- 只定义未来配置研究层的架构、输入、证据要求和禁止输出。
- 只读取已经冻结的 V6 风险上下文、V7 机会研究状态、V8 研究解释语境。
- 不生成资产选择。
- 不生成 ETF 映射。
- 不生成组合权重。
- 不做回测优化。
- 不生成交易信号。
- 不连接券商或下单。

## 新增/修改文件

- `allocation_research/allocation_research_schema.py`
  - 定义 V9.1 schema。
  - 允许输入限定为 Frozen V6 / V7 / V8。
  - 未来证据要求包括配置假设、非优化候选、样本外验证、回撤与矛盾审计、研究边界。
  - 明确禁止 `portfolio_weight`、`asset_selection`、`etf_mapping`、`top_n`、`trade_signal`、`rebalance_instruction`、`broker_order`、`backtest_optimization`。
- `allocation_research/allocation_research_boundary.py`
  - 生成 V9.1 配置研究架构 JSON。
  - 校验所有 ready flag 均为 `false`。
  - 校验输出边界禁止资产、ETF、权重、回测优化和交易。
- `scripts/audit_allocation_research_architecture.py`
  - 生成 `data/allocation_research_architecture.json`。
  - 输出 ready、environment context 和 audit 状态。
- `scripts/test_allocation_research_architecture.py`
  - 本地轻量测试 V9.1 产物、schema、边界和写文件逻辑。
- `data/allocation_research_architecture.json`
  - V9.1 架构产物。
- `web/app.py`
  - 新增 `/api/allocation-research/architecture`。
  - 将 V9.1 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“配置研究架构基础”卡片。
- `web/static/dashboard.js`
  - 渲染 V9.1 允许输入、来源证据、禁止输出和未就绪状态。

## 关键结果

- engine：`V9.1 Allocation Research Architecture Foundation`
- 数据基准：`20260707`
- environment context：`risk_controlled_opportunity_watch`
- risk state：`risk_axis_visible_opportunity_axis_weak`
- opportunity state：`feature_attribution_not_ready_for_opportunity_score`
- research interpretation state：`contradiction_attribution_research_only_no_rule_change`
- scenario consistency：low 3 / medium 3
- conclusion：`allocation_research_architecture_defined_not_ready`
- `allocation_research_ready`：`false`
- `ready_for_asset_selection`：`false`
- `ready_for_etf_mapping`：`false`
- `ready_for_weight_generation`：`false`
- `ready_for_backtest`：`false`
- `ready_for_trade`：`false`

## 明确拒绝

- Portfolio Weight。
- Asset Selection。
- ETF Mapping。
- Top N。
- Trade Signal。
- Rebalance Instruction。
- Broker Order。
- Backtest Optimization。

## Web / API

- `/api/allocation-research/architecture`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行或需要审计复核运行：

```powershell
python scripts\audit_allocation_research_architecture.py
python scripts\test_allocation_research_architecture.py
python -m py_compile web\app.py allocation_research\allocation_research_schema.py allocation_research\allocation_research_boundary.py scripts\audit_allocation_research_architecture.py scripts\test_allocation_research_architecture.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API / 页面烟测目标：

- `/api/allocation-research/architecture` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `allocation_research_architecture`。
- `/api` 返回 200 且包含 `/api/allocation-research/architecture`。
- `/validation` 返回 200 且可见“配置研究架构基础”卡片。

## 待审计问题

1. V9.1 是否满足“架构基础而非配置策略”的边界？
2. 是否可以进入下一步 V9.2：定义配置研究候选假设，但仍不做权重、ETF 映射、回测优化或交易？
3. V9 后续是否需要继续强制保留 `allocation_research_ready=false`，直到样本外验证和矛盾审计完成？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.1，本次不应纳入 commit。
