# V9.6 配置研究实验 Phase 1 审计包

## 审计要求

请同时选取/启用 GitHub 技能，对 GitHub 仓库、最新 commit、diff 和数据产物做代码级审计，不要只依据摘要判断。

## 任务边界

本任务实现 `TASK V9.6 — Allocation Research Experiment Phase 1 Validation`。

核心边界：

- 只执行预声明研究实验的 Phase 1 验证。
- 只读取冻结 V6/V7/V8 与 V9.5 产物。
- 记录所有输入文件 sha256，防止看结果后改实验。
- 只输出 supported / inconclusive / unsupported 研究状态。
- 不晋级配置候选。
- 不输出资产、ETF、权重、仓位百分比、买卖、调仓或交易。
- 不做参数搜索、最优策略寻找或权重优化。

## 新增/修改文件

- `allocation_research/allocation_experiment_phase1_schema.py`
  - 定义 V9.6 Phase 1 validation schema。
- `allocation_research/allocation_experiment_phase1_validation.py`
  - 读取冻结 V6/V7/V8/V9.5 产物。
  - 生成 H1-H4 研究验证状态。
  - 记录输入 sha256。
  - 保持 `promotion_allowed=false` 与 `investable_output=false`。
- `scripts/run_allocation_experiment_phase1.py`
  - 生成 `data/allocation_experiment_phase1_validation.json`。
- `scripts/test_allocation_experiment_phase1.py`
  - 测试结果计数、哈希、禁止输出、边界和写文件。
- `data/allocation_experiment_phase1_validation.json`
  - V9.6 研究验证产物。
- `web/app.py`
  - 新增 `/api/allocation-research/experiment-phase1-validation`。
- `web/templates/validation.html`
  - 新增“配置研究实验 Phase 1”卡片。
- `web/static/dashboard.js`
  - 渲染 supported / inconclusive、输入哈希数量、边界和结果列表。

## 关键结果

- engine：`V9.6 Allocation Research Experiment Phase 1 Validation`
- validation_result_count：4
- supported_count：2
- inconclusive_count：2
- unsupported_count：0
- promotion_allowed：false
- promoted_to_candidate：false
- investable_output_generated：false
- conclusion：`allocation_experiment_phase1_validated_research_only_no_promotion`

## 单项结果

- H1：inconclusive
  - 风险上下文可测，但机会证据仍未准备好进入机会分。
- H2：supported
  - V6 风险轴强于机会轴，支持风险主导保护持续性研究假设。
- H3：inconclusive
  - V8 仍显示结构机会捕捉不足，无法确认结构机会独立成立。
- H4：supported
  - V8 场景审计和矛盾归因支持矛盾优先晋级门槛。

## Web / API

- `/api/allocation-research/experiment-phase1-validation`
- `/api/allocation-research/experiment-results`
- `/api/results/summary?compact=true`
- `/api`
- `/validation`

## 验证命令

```powershell
python scripts\run_allocation_experiment_phase1.py
python scripts\test_allocation_experiment_phase1.py
python -m py_compile allocation_research\allocation_experiment_phase1_schema.py allocation_research\allocation_experiment_phase1_validation.py scripts\run_allocation_experiment_phase1.py scripts\test_allocation_experiment_phase1.py
node --check web\static\dashboard.js
python -m compileall allocation_research decision_research asset_opportunity scripts web
```

## 待审计问题

1. V9.6 是否通过？
2. 是否允许进入候选晋级审计阶段？如果允许，仍应禁止资产、ETF、权重和交易。
3. supported=2 / inconclusive=2 是否应先冻结为研究结论，而不是直接进入配置？

## 已知工作区状态

`data/structural_survival_dataset.json` 是本任务前已存在的本地未提交改动，不属于 V9.6，本次不应纳入 commit。
