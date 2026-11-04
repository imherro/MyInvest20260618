# V7.1 机会研究基础层代码审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V7.1 — Opportunity / Asset Research Layer Foundation`。

核心边界：

- 只建立机会研究侧资产池、研究代理、覆盖率和时间安全边界。
- 不生成机会评分。
- 不生成资产排名。
- 不生成仓位、ETF 权重、组合权重或交易信号。
- 不连接券商、不下单、不做自动选股。
- 真实 ETF 可交易历史与长历史研究代理必须分离，不能把研究代理当成可交易资产。

## 新增/修改文件

- `asset_opportunity/opportunity_research_foundation.py`
  - 构建 V7.1 研究基础快照。
  - 读取 `asset_registry.json`、`asset_universe_audit.json`、`asset_proxy_registry.json`、`asset_proxy_coverage_audit.json`。
  - 输出 `summary`、`coverage`、`asset_rows`、`time_safety`、`data_quality`、`constraints`。
- `scripts/run_opportunity_research_foundation.py`
  - 生成 `data/opportunity_research_foundation.json`。
- `scripts/test_opportunity_research_foundation_v7.py`
  - 校验资产数量、代理覆盖、时间安全、禁止评分/排名/配置/交易等硬边界。
- `data/opportunity_research_foundation.json`
  - V7.1 生成产物。
- `asset_opportunity/__init__.py`
  - 导出 `build_opportunity_research_foundation`。
- `web/app.py`
  - 新增 `/api/opportunity/research-foundation`。
  - 将 V7.1 纳入 `/api` 目录和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“机会研究基础层”卡片。
- `web/static/dashboard.js`
  - 渲染 V7.1 资产池、研究代理、覆盖口径和输出边界。

## 关键结果

- ETF 资产池：17 个。
- 行业资产：10 个。
- 有长历史研究代理的资产：10 个。
- 研究代理数量：8 个。
- 直接 ETF 历史资产：7 个。
- 研究代理覆盖：2015-01-05 至 2026-07-08，完整覆盖目标研究窗口。
- 真实 ETF 可交易历史公共覆盖：2021-02-04 至 2026-06-25，不能覆盖完整目标窗口。
- Readiness：`research_ready_with_tradability_caveat`。

## Web / API

- `/api/opportunity/research-foundation`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

页面口径：

- 显示“ETF 资产池”“研究代理”“覆盖口径”“输出边界”。
- 输出边界明确为“不可评分/排名/配置/交易”。
- 行业代理和直接 ETF 历史分开展示。

## 验证命令

已运行：

```powershell
python scripts\run_opportunity_research_foundation.py
python scripts\test_opportunity_research_foundation_v7.py
python scripts\test_asset_opportunity_foundation.py
node --check web\static\dashboard.js
python -m py_compile web\app.py asset_opportunity\opportunity_research_foundation.py scripts\run_opportunity_research_foundation.py scripts\test_opportunity_research_foundation_v7.py
python -m compileall asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/opportunity/research-foundation` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `opportunity_research_foundation`。
- `/api` 返回 200 且包含 `/api/opportunity/research-foundation`。
- `/validation` 返回 200。

## 待审计问题

1. V7.1 是否应判定通过，并作为 V7 机会研究层基础冻结？
2. 下一步是否进入 V7.2：在不排序、不配置、不交易的前提下，设计“结构性牛市资产机会观察指标”的候选字段？
3. 对 7 个没有长历史代理的宽基/风格 ETF，是否继续只使用真实 ETF 历史，还是允许引入指数代理但必须继续标注不可交易口径？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V7.1，本次不应纳入 commit。
