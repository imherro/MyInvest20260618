# V8.4 研究决策架构冻结审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V8.4 — Research Decision Architecture Freeze & Summary`。

核心边界：

- 冻结 V8.1-V8.3 研究解释链路。
- 不新增分析。
- 不新增状态。
- 不新增评分。
- 不修改 V6/V7。
- 不输出资产选择、排名、Top N、配置、ETF 权重或交易。
- 只新增架构冻结文档、一致性审计脚本和 Web/API 展示。

## 新增/修改文件

- `docs/research_decision_v8_architecture.md`
  - 记录 V8.1、V8.2、V8.3 保留层。
  - 显式拒绝 Score、Ranking、Asset Selection、Top N、Allocation、ETF Weight、Trading、New State、V6/V7 Modification。
- `scripts/audit_v8_architecture_consistency.py`
  - 读取 V8.1-V8.3 三个产物和 V8 架构文档。
  - 校验 ready flags 均为 false。
  - 校验 V8.1 研究语境、V8.2 场景覆盖和 V8.3 归因结果未漂移。
- `web/app.py`
  - 新增 `/api/decision/v8-architecture`。
  - 将 V8.4 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“研究决策架构冻结”卡片。
- `web/static/dashboard.js`
  - 渲染 V8.4 保留层、拒绝项、证据摘要和输出边界。

## 关键结果

- V8 状态：已冻结。
- 保留层数：3。
- 拒绝输出项：9。
- V8.1：`risk_controlled_opportunity_watch` / `observe_without_selection`。
- V8.2：6 个场景，medium 3 / low 3。
- V8.3：5 个重点场景，5 条归因。
- 结论：`v8_research_interpretation_frozen_no_strategy`。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 明确拒绝

- Score。
- Ranking。
- Asset Selection。
- Top N。
- Allocation。
- ETF Weight。
- Trading。
- New State。
- V6/V7 Modification。

## Web / API

- `/api/decision/v8-architecture`
- `/api/decision/contradiction-attribution`
- `/api/decision/scenario-audit`
- `/api/decision/research-context`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行：

```powershell
python scripts\audit_v8_architecture_consistency.py
python -m py_compile web\app.py scripts\audit_v8_architecture_consistency.py
node --check web\static\dashboard.js
python -m compileall decision_research asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/decision/v8-architecture` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `research_decision_v8_architecture`。
- `/api` 返回 200 且包含 `/api/decision/v8-architecture`。
- `/validation` 返回 200。

已运行内置浏览器页面检查：

- `/validation` 可见“研究决策架构冻结”卡片。
- 卡片显示“已冻结”“3 层”“9 项”“不可策略化/配置/交易”。

## 待审计问题

1. V8.4 是否通过？
2. V8 是否可以正式冻结为研究解释架构？
3. 下一阶段是否必须另起 V9，且不能把 V8 直接当成策略或配置引擎？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V8.4，本次不应纳入 commit。
