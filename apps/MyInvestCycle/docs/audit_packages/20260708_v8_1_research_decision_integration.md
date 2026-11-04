# V8.1 研究决策整合架构审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V8.1 — Research Decision Integration Architecture`。

核心边界：

- 连接冻结的 V6 风险上下文和冻结的 V7 机会研究归因。
- 只输出研究语境和解释口径。
- 不输出资产。
- 不输出 ETF 代码。
- 不输出评分、排名、Top N、仓位、ETF 权重、组合权重或交易信号。
- 不新增特征。
- 不回测。
- 不做参数优化。

## 新增/修改文件

- `decision_research/__init__.py`
  - 新增 V8.1 研究决策整合包。
- `decision_research/research_decision_context.py`
  - 读取 V6.5、V6.4、V5.10、V6.6 和 V7.4 冻结产物。
  - 输出 `data/research_decision_context.json`。
  - 生成研究语境 `risk_controlled_opportunity_watch`。
- `decision_research/research_decision_audit.py`
  - 校验 ready flags 全部为 false。
  - 校验禁止输出资产、ETF、排名、权重、交易相关字段。
  - 校验只使用冻结 V6/V7 产物。
- `scripts/run_research_decision_context.py`
  - 生成 V8.1 研究决策整合产物。
- `scripts/test_research_decision_context.py`
  - 校验 V8.1 产物、边界和写入流程。
- `data/research_decision_context.json`
  - V8.1 生成产物。
- `web/app.py`
  - 新增 `/api/decision/research-context`。
  - 将 V8.1 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“研究决策整合架构”卡片。
- `web/static/dashboard.js`
  - 渲染研究语境、研究姿态、风险证据、机会特征组关注和输出边界。

## 关键结果

- 研究语境：`risk_controlled_opportunity_watch`。
- 研究姿态：`observe_without_selection`。
- 风险上下文状态：`risk_axis_visible_opportunity_axis_weak`。
- 机会上下文状态：`feature_attribution_not_ready_for_opportunity_score`。
- 保留风险上下文层：3。
- 机会研究候选：1。
- 机会观察项：17。
- 输出边界：不可评分 / 排名 / 配置 / 交易。

## 解释口径

V8.1 的含义是：

- V6 风险上下文可以用来框架化解释当前环境。
- V7 机会研究只能作为特征组层面的研究关注。
- 二者尚不能合成为策略、排名或配置。

## Web / API

- `/api/decision/research-context`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行：

```powershell
python scripts\run_research_decision_context.py
python scripts\test_research_decision_context.py
python -m py_compile web\app.py decision_research\research_decision_context.py decision_research\research_decision_audit.py scripts\run_research_decision_context.py scripts\test_research_decision_context.py
node --check web\static\dashboard.js
python -m compileall decision_research asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/decision/research-context` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `research_decision_context`。
- `/api` 返回 200 且包含 `/api/decision/research-context`。
- `/validation` 返回 200。

已运行内置浏览器页面检查：

- `/validation` 可见“研究决策整合架构”卡片。
- 卡片显示“风险约束下观察机会”“只观察不选择”“候选 1 / 观察 17”“不可评分/排名/配置/交易”。

## 待审计问题

1. V8.1 是否通过？
2. 是否同意 V8.1 只能作为研究语境整合层，不能进入评分、排名或配置？
3. 下一步是否应继续 V8.2 做“历史情景解释审计”，检验 V8.1 研究语境在历史样本中的解释一致性，而不是直接做策略？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V8.1，本次不应纳入 commit。
