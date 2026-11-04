# V7.5 机会研究层冻结与架构审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V7.5 — Opportunity Research Layer Freeze & Audit Summary`。

核心边界：

- 冻结 V7.1-V7.4 机会研究链路。
- 不新增特征。
- 不新增 Opportunity Score。
- 不新增评分、排名、Top N、配置、ETF 权重或交易信号。
- 只新增架构冻结文档、边界一致性审计脚本和 Web/API 展示。

## 新增/修改文件

- `docs/opportunity_research_v7_architecture.md`
  - 记录 V7.1-V7.4 保留层。
  - 显式拒绝 Opportunity Score、Ranking、Top N、Allocation、ETF weight、Trading、New feature search。
  - 记录已验证和未验证内容。
- `scripts/audit_v7_architecture_consistency.py`
  - 审计 V7 架构文档和 V7.1-V7.4 数据产物是否一致。
  - 校验 ready flags 均为 false。
  - 校验 V7.3 固定 14 个特征、5/20/60 horizon、42 条结果。
  - 校验 V7.4 结论仍是 `feature_attribution_not_ready_for_opportunity_score`。
- `web/app.py`
  - 新增 `/api/opportunity/v7-architecture`。
  - 将 V7.5 纳入 `/api` 目录和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“机会研究层冻结”卡片。
- `web/static/dashboard.js`
  - 渲染 V7.5 保留层、拒绝项、冻结状态和输出边界。

## 关键结果

- V7 状态：已冻结。
- 保留层数：4。
- 拒绝输出项：7。
- 结论：`feature_attribution_not_ready_for_opportunity_score`。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 明确拒绝

- Opportunity Score。
- Ranking。
- Top N。
- Allocation。
- ETF weight。
- Trading。
- New feature search。

## Web / API

- `/api/opportunity/v7-architecture`
- `/api/opportunity/feature-attribution`
- `/api/opportunity/feature-validation`
- `/api/opportunity/context-features`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行：

```powershell
python scripts\audit_v7_architecture_consistency.py
python -m py_compile web\app.py scripts\audit_v7_architecture_consistency.py
node --check web\static\dashboard.js
python -m compileall asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/opportunity/v7-architecture` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `opportunity_v7_architecture`。
- `/api` 返回 200 且包含 `/api/opportunity/v7-architecture`。
- `/validation` 返回 200。

已运行内置浏览器页面检查：

- `/validation` 可见“机会研究层冻结”卡片。
- 卡片显示“已冻结”“7 项”“不可评分/排名/配置/交易”。

## 待审计问题

1. V7 是否应按该文档正式冻结？
2. V7.5 是否足够清楚地区分“研究底座已建立”和“机会评分/排名/配置未验证”？
3. 下一阶段是否应另起 V8，把 V6 风险上下文与 V7 机会研究基础做非交易研究整合，而不是继续扩展 V7？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V7.5，本次不应纳入 commit。
