# V9.2 配置研究假设框架审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.2 — Allocation Research Hypothesis Framework`。

核心边界：

- 只定义未来配置研究应该验证的假设。
- 只读取 V9.1 配置研究架构基础。
- 所有假设状态必须为 `unvalidated`。
- 不定义参数。
- 不定义资产。
- 不定义 ETF。
- 不定义权重。
- 不定义仓位百分比。
- 不生成买卖或调仓信号。
- 不生成回测结果。
- 不做优化。

## 新增/修改文件

- `allocation_research/allocation_hypothesis_schema.py`
  - 定义 V9.2 hypothesis schema。
  - 允许输入仅为 V9.1。
  - 要求每条假设必须包含研究问题、假设、来源语境、验证要求、失效条件、状态和禁止解释。
  - 禁止输出包括资产选择、ETF 映射、权重、仓位百分比、买卖信号、调仓、回测结果和优化。
- `allocation_research/allocation_hypothesis_audit.py`
  - 基于 V9.1 产物构建 4 条未验证研究假设。
  - 校验 ready flags 均为 `false`。
  - 校验所有假设均为 `unvalidated`。
  - 校验不生成资产、ETF、权重、回测、优化或交易输出。
- `scripts/run_allocation_hypothesis_audit.py`
  - 生成 `data/allocation_research_hypotheses.json`。
- `scripts/test_allocation_hypothesis_audit.py`
  - 测试 schema、假设状态、禁止输出、时间安全和写文件。
- `data/allocation_research_hypotheses.json`
  - V9.2 架构产物。
- `web/app.py`
  - 新增 `/api/allocation-research/hypotheses`。
  - 将 V9.2 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“配置研究假设框架”卡片。
- `web/static/dashboard.js`
  - 渲染假设数量、未验证状态、验证要求、边界和假设列表。

## 关键结果

- engine：`V9.2 Allocation Research Hypothesis Framework`
- 数据基准：`20260707`
- source context：`risk_controlled_opportunity_watch`
- source conclusion：`allocation_research_architecture_defined_not_ready`
- hypothesis_count：4
- unvalidated_count：4
- validated_count：0
- conclusion：`allocation_hypothesis_framework_defined_unvalidated`
- `hypothesis_framework_ready`：`false`
- `ready_for_asset_selection`：`false`
- `ready_for_etf_mapping`：`false`
- `ready_for_weight_generation`：`false`
- `ready_for_backtest`：`false`
- `ready_for_optimization`：`false`
- `ready_for_trade`：`false`

## 四条假设

- H1 `risk_relief_opportunity_readiness`
  - 风险缓和与机会证据改善是否能共同解释更积极的未来研究姿态。
- H2 `risk_dominant_protection_persistence`
  - 风险轴强于机会轴时，是否应优先验证保护质量。
- H3 `structural_opportunity_independent_confirmation`
  - 宽基混合时，结构性机会是否可以独立确认。
- H4 `contradiction_first_promotion_gate`
  - 历史矛盾类型是否应成为后续候选晋级前置门槛。

## 明确拒绝

- Portfolio Weight。
- Asset Selection。
- ETF Mapping。
- Top N。
- Exposure Percent。
- Buy Signal。
- Sell Signal。
- Rebalance Instruction。
- Broker Order。
- Backtest Result。
- Optimization。

## Web / API

- `/api/allocation-research/hypotheses`
- `/api/allocation-research/architecture`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行或需要审计复核运行：

```powershell
python scripts\run_allocation_hypothesis_audit.py
python scripts\test_allocation_hypothesis_audit.py
python -m py_compile allocation_research\allocation_hypothesis_schema.py allocation_research\allocation_hypothesis_audit.py scripts\run_allocation_hypothesis_audit.py scripts\test_allocation_hypothesis_audit.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

API / 页面烟测目标：

- `/api/allocation-research/hypotheses` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `allocation_research_hypotheses`。
- `/api` 返回 200 且包含 `/api/allocation-research/hypotheses`。
- `/validation` 返回 200 且可见“配置研究假设框架”卡片。

## 待审计问题

1. V9.2 是否通过？
2. 四条假设是否足够覆盖后续配置研究方向？
3. 下一步是否进入 V9.3：只设计样本外验证与矛盾审计计划，仍不做资产、ETF、权重、回测结果、优化或交易？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.2，本次不应纳入 commit。
