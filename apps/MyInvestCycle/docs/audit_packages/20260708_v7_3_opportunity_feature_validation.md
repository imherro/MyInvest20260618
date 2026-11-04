# V7.3 机会特征有效性审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V7.3 — Opportunity Feature Effectiveness Audit`。

核心边界：

- 固定 V7.2 特征定义，只做有效性审计。
- 输出 IC 与分环境统计，不生成机会评分。
- 不生成资产排名。
- 不输出 Top N。
- 不生成仓位、ETF 权重、组合权重或交易信号。
- 不连接券商、不下单、不做自动选股。
- 未来收益只作为验证标签，不进入特征值计算。

## 新增/修改文件

- `asset_opportunity/opportunity_feature_validation.py`
  - 构建 V7.3 特征有效性审计。
  - 使用固定 V7.2 特征定义。
  - 对 5/20/60 日 horizon 计算 research proxy 与真实 ETF 两套 IC。
  - 按 V6 two_axis context 日期做观察，并保留 regime breakdown。
- `scripts/run_opportunity_feature_validation.py`
  - 生成 `data/opportunity_feature_validation.json`。
- `scripts/test_opportunity_feature_validation.py`
  - 校验特征数、horizon、结果数、时间安全、proxy/ETF 分离和禁止评分/排名/Top N/配置/交易边界。
- `data/opportunity_feature_validation.json`
  - V7.3 生成产物。
- `asset_opportunity/__init__.py`
  - 导出 `build_opportunity_feature_validation`。
- `web/app.py`
  - 新增 `/api/opportunity/feature-validation`。
  - 将 V7.3 纳入 `/api` 目录和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“机会特征有效性审计”卡片。
- `web/static/dashboard.js`
  - 渲染 V7.3 特征/horizon 范围、上下文日期数、proxy/ETF 状态计数和样本结果。

## 关键结果

- 固定特征数：14。
- Horizon：5、20、60 个交易日。
- 上下文观察日期：115。
- 结果条数：42。
- Research proxy 状态计数：
  - flat：28。
  - weak：8。
  - insufficient：6。
- 真实 ETF 状态计数：
  - visible：1。
  - weak：14。
  - flat：21。
  - insufficient：6。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 解释口径

V7.3 当前结论不是“可以评分”，而是：

- 大多数特征仍然 flat 或 weak。
- 有少量特征在真实 ETF 迁移侧显示 weak/visible，但不足以直接进入机会评分。
- 下一步若继续，应先做更严格的分环境、分来源稳定性审计，而不是直接做模型。

## 时间安全

- 特征值只使用 signal date 及以前历史。
- 未来收益只作为 validation label。
- research proxy 与真实 ETF forward return 分开验证。
- 没有使用未来收益生成评分、排名、仓位或交易信号。

## Web / API

- `/api/opportunity/feature-validation`
- `/api/opportunity/context-features`
- `/api/opportunity/research-foundation`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

页面口径：

- 显示“特征 / Horizon”“上下文日期”“Proxy 结果”“ETF 结果”。
- 显示状态计数和定义顺序样本。
- 不按 IC 强弱排序，不展示资产优劣排名。

## 验证命令

已运行：

```powershell
python scripts\run_opportunity_feature_validation.py
python scripts\test_opportunity_feature_validation.py
node --check web\static\dashboard.js
python -m py_compile web\app.py asset_opportunity\opportunity_feature_validation.py scripts\run_opportunity_feature_validation.py scripts\test_opportunity_feature_validation.py
```

已运行本地 API 烟测：

- `/api/opportunity/feature-validation` 返回 200。
- `/api/opportunity/context-features` 返回 200。
- `/api/opportunity/research-foundation` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `opportunity_feature_validation`。
- `/api` 返回 200 且包含 `/api/opportunity/feature-validation`。
- `/validation` 返回 200。

## 待审计问题

1. V7.3 是否应判定通过，并冻结为特征有效性审计层？
2. 下一步是否进入 V7.4：做“稳定候选特征归因”，仅解释哪些特征可保留，仍不做评分？
3. 由于当前 flat/weak 居多，是否应明确禁止进入机会评分模型，直到 V7.4 再审？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V7.3，本次不应纳入 commit。
