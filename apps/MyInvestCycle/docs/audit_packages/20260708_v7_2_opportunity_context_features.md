# V7.2 机会研究特征层代码审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V7.2 — Structural Opportunity Context Feature Audit`。

核心边界：

- 只输出机会研究特征字段。
- 不生成机会评分。
- 不生成资产排名。
- 不输出 Top N。
- 不生成仓位、ETF 权重、组合权重或交易信号。
- 不连接券商、不下单、不做自动选股。
- V6 风险/保护/双轴上下文只作为架构引用，不 join 到资产特征，不参与资产评分或排名。

## 新增/修改文件

- `asset_opportunity/opportunity_context_features.py`
  - 构建 V7.2 特征快照。
  - 读取 V7.1 资产基础、ETF/研究代理历史、沪深300/中证500基准、V6 上下文元数据、历史风格上下文。
  - 输出动量、相对强弱、趋势、风险、结构五类字段。
  - 每个字段包含 `value`、`source`、`source_kind`、`as_of`、`method`。
- `scripts/run_opportunity_context_features.py`
  - 生成 `data/opportunity_context_features.json`。
- `scripts/test_opportunity_context_features.py`
  - 校验 17 个资产、字段结构、来源类型、时间安全，以及禁止评分/排名/Top N/配置/交易边界。
- `data/opportunity_context_features.json`
  - V7.2 生成产物。
- `asset_opportunity/__init__.py`
  - 导出 `build_opportunity_context_features`。
- `web/app.py`
  - 新增 `/api/opportunity/context-features`。
  - 将 V7.2 纳入 `/api` 目录和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“机会研究特征层”卡片。
- `web/static/dashboard.js`
  - 渲染 V7.2 日期、来源分布、字段组覆盖率和资产样本。

## 关键结果

- 资产数：17 个。
- 对齐后的安全特征日期：2026-06-25。
- ETF 真实历史来源：7 个资产。
- 研究代理来源：10 个资产。
- 字段组：动量、相对强弱、趋势、风险、结构。
- 字段覆盖率：
  - 动量：51 / 51。
  - 相对强弱：34 / 34。
  - 趋势：102 / 102。
  - 风险：51 / 51。
  - 结构：51 / 51。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 日期口径

V7.2 按所有资产与基准的共同最新可比日期对齐计算，当前为 `20260625`。

原因：

- 部分直接 ETF 历史只到 2026-06-25 或 2026-06-26。
- 研究代理和部分宽基 ETF 已到 2026-07-08。
- 为避免跨资产日期不一致，V7.2 使用共同安全日期，而不是每个资产各自最新日期。

V6 上下文文件 as_of 可晚于资产特征日期，但仅作为元数据引用：

- `v6_context_metadata_only = true`
- `v6_context_values_not_joined_to_asset_features = true`
- `v6_context_reference_not_used_for_asset_ranking = true`

## Web / API

- `/api/opportunity/context-features`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

页面口径：

- 显示“特征日期”“资产/来源”“字段组”“输出边界”。
- 输出边界明确为“不可评分/排名/配置/交易”。
- 展示字段组覆盖率和资产样本，但不展示资产优劣顺序。

## 验证命令

已运行：

```powershell
python scripts\run_opportunity_context_features.py
python scripts\test_opportunity_context_features.py
python scripts\test_opportunity_research_foundation_v7.py
node --check web\static\dashboard.js
python -m py_compile web\app.py asset_opportunity\opportunity_context_features.py scripts\run_opportunity_context_features.py scripts\test_opportunity_context_features.py
```

已运行本地 API 烟测：

- `/api/opportunity/context-features` 返回 200。
- `/api/opportunity/research-foundation` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `opportunity_context_features`。
- `/api` 返回 200 且包含 `/api/opportunity/context-features`。
- `/validation` 返回 200。

## 待审计问题

1. V7.2 是否应判定通过并冻结为机会研究特征层？
2. 下一步是否进入 V7.3：先做“特征有效性审计”，而不是直接做机会评分？
3. V7.3 若做有效性审计，是否应按 V6 宏观上下文分层检验，而不是全样本统一检验？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V7.2，本次不应纳入 commit。
