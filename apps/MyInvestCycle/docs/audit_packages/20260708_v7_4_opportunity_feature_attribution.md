# V7.4 机会特征归因与稳定性审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V7.4 — Opportunity Feature Attribution & Stability Audit`。

核心边界：

- 固定读取 V7.3 验证结果。
- 不重新计算特征。
- 不重新计算 forward return。
- 只做保留研究 / 继续观察 / 暂不保留 / 样本不足归因。
- 不生成机会评分。
- 不生成特征权重。
- 不生成资产排名或 Top N。
- 不生成仓位、ETF 权重、组合权重或交易信号。

## 新增/修改文件

- `asset_opportunity/opportunity_feature_attribution.py`
  - 构建 V7.4 特征归因与稳定性审计。
  - 读取 `data/opportunity_feature_validation.json`。
  - 输出 proxy/ETF 对齐关系、regime consistency、retention 标签。
- `scripts/run_opportunity_feature_attribution.py`
  - 生成 `data/opportunity_feature_attribution.json`。
- `scripts/test_opportunity_feature_attribution.py`
  - 校验 42 条归因、边界约束、时间安全和禁止评分/权重/排名/配置/交易。
- `data/opportunity_feature_attribution.json`
  - V7.4 生成产物。
- `asset_opportunity/__init__.py`
  - 导出 `build_opportunity_feature_attribution`。
- `web/app.py`
  - 新增 `/api/opportunity/feature-attribution`。
  - 将 V7.4 纳入 `/api` 目录和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“机会特征归因与稳定性”卡片。
- `web/static/dashboard.js`
  - 渲染 V7.4 retention 计数、环境一致性计数和样本归因。

## 关键结果

- 来源结果条数：42。
- 归因条数：42。
- Retention 计数：
  - research_candidate：1。
  - watch：17。
  - reject_for_now：18。
  - insufficient：6。
- Regime consistency 计数：
  - consistent_context_signal：7。
  - single_context_signal：6。
  - mixed_or_conflicting_context_signal：23。
  - no_regime_signal：6。
- 结论：`feature_attribution_not_ready_for_opportunity_score`。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 解释口径

V7.4 的 retention 标签不是：

- 分数。
- 权重。
- 排名。
- Top N。
- 策略配置。
- 交易信号。

当前结论是：少量特征可继续研究，但整体仍不具备进入机会评分模型的条件。

## Web / API

- `/api/opportunity/feature-attribution`
- `/api/opportunity/feature-validation`
- `/api/opportunity/context-features`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

页面口径：

- 显示“归因条数”“保留结论”“环境一致性”“输出边界”。
- 显示 retention 计数和定义顺序样本。
- 不按 retention 或 IC 强弱排序，不展示资产优劣排名。

## 验证命令

已运行：

```powershell
python scripts\run_opportunity_feature_attribution.py
python scripts\test_opportunity_feature_attribution.py
node --check web\static\dashboard.js
python -m py_compile web\app.py asset_opportunity\opportunity_feature_attribution.py scripts\run_opportunity_feature_attribution.py scripts\test_opportunity_feature_attribution.py
```

已运行本地 API 烟测：

- `/api/opportunity/feature-attribution` 返回 200。
- `/api/opportunity/feature-validation` 返回 200。
- `/api/opportunity/context-features` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `opportunity_feature_attribution`。
- `/api` 返回 200 且包含 `/api/opportunity/feature-attribution`。
- `/validation` 返回 200。

## 待审计问题

1. V7.4 是否应判定通过，并冻结为特征归因层？
2. 由于 V7.4 结论仍是 not ready for score，下一步是否应该冻结 V7 机会研究层，而不是继续做模型？
3. 若继续，是否只能做架构冻结文档 / 结果解释页面，而不能进入 Opportunity Score？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V7.4，本次不应纳入 commit。
