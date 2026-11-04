# V8.2 历史情景解释审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V8.2 — Research Decision Historical Scenario Audit`。

核心边界：

- 固定读取 V8.1 研究语境和 V6 历史上下文行。
- 固定六个历史场景。
- 只审计解释一致性、上下文切换、矛盾样本和覆盖缺口。
- 不使用收益指标。
- 不新增特征。
- 不输出资产、ETF、排名、Top N、仓位、ETF 权重或交易信号。
- 不回测。
- 不做参数优化。

## 新增/修改文件

- `decision_research/research_decision_scenario_audit.py`
  - 构建 V8.2 历史情景解释审计。
  - 固定场景：2015 牛熊转换、2018 熊市、2020 恢复、2021 核心资产分化、2022 熊市、2024-2026 结构行情。
  - 读取 `data/research_decision_context.json`、`data/two_axis_context_validation.json`、`data/context_information_attribution.json`。
- `scripts/run_research_decision_scenario_audit.py`
  - 生成 `data/research_decision_scenario_audit.json`。
- `scripts/test_research_decision_scenario_audit.py`
  - 校验场景数量、覆盖、边界和禁止输出。
- `data/research_decision_scenario_audit.json`
  - V8.2 生成产物。
- `decision_research/__init__.py`
  - 导出 V8.2 构建与写入函数。
- `web/app.py`
  - 新增 `/api/decision/scenario-audit`。
  - 将 V8.2 纳入 `/api` 和 `/api/results/summary?compact=true`。
- `web/templates/validation.html`
  - 在验证归因频道新增“历史情景解释审计”卡片。
- `web/static/dashboard.js`
  - 渲染场景覆盖、一致性、平均切换率、场景列表和输出边界。

## 关键结果

- 场景数：6。
- 覆盖场景：6。
- 一致性：medium 3 / low 3。
- 主导语境：WAIT 5 / PARTICIPATE 1。
- 平均上下文切换率：42.2896%。
- 矛盾样本：16。
- 缺失上下文样本：0。
- 结论：`scenario_explanation_audit_only_no_strategy`。
- `ready_for_scoring`、`ready_for_ranking`、`ready_for_allocation`、`ready_for_trade` 全部为 `false`。

## 解释口径

V8.2 说明：

- V8.1 研究语境在六个历史场景中并不稳定到足以升级为策略。
- 2015、2018 等场景暴露出低一致性或较高矛盾。
- 该层只指出解释框架的稳定性问题，不给资产选择、仓位或交易结论。

## Web / API

- `/api/decision/scenario-audit`
- `/api/decision/research-context`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

已运行：

```powershell
python scripts\run_research_decision_scenario_audit.py
python scripts\test_research_decision_scenario_audit.py
python -m py_compile web\app.py decision_research\research_decision_scenario_audit.py scripts\run_research_decision_scenario_audit.py scripts\test_research_decision_scenario_audit.py
node --check web\static\dashboard.js
python -m compileall decision_research asset_opportunity scripts web
```

已运行本地 API 烟测：

- `/api/decision/scenario-audit` 返回 200。
- `/api/results/summary?compact=true` 返回 200 且包含 `research_decision_scenario_audit`。
- `/api` 返回 200 且包含 `/api/decision/scenario-audit`。
- `/validation` 返回 200。

已运行内置浏览器页面检查：

- `/validation` 可见“历史情景解释审计”卡片。
- 卡片显示“6 / 6”“medium 3 / low 3”“42.3%”“不可评分/排名/配置/交易”。

## 待审计问题

1. V8.2 是否通过？
2. V8.2 的 medium 3 / low 3 是否意味着 V8 仍应停留在研究解释层？
3. 下一步是否应做 V8.3：矛盾场景归因，集中解释 2015 和 2018 为什么低一致性，而不是进入策略？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V8.2，本次不应纳入 commit。
