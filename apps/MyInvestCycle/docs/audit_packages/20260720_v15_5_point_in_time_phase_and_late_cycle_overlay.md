# V15.5 审计包

## 审计对象

- 阶段：V15.5
- 目标：严格时点阶段重建或诚实缺口报告；高位风险覆盖层数据契约
- 基准提交：`b17c2f41d269abc4b0e73c16456709e92352e7b9`
- 仓库：`https://github.com/imherro/MyInvestCycle`
- 分支：`main`

## 结论摘要

- `strict_point_in_time_phase_status=gap_report_ready`
- `phase_row_count=140`
- `verified_date_count=0`
- `unverified_date_count=140`
- `macro_release_effective_safe_count=140`
- `strict_lineage_count=0`
- `reconstructed_style_date_count=140`
- `structural_context_complete_count=79`
- `valuation_available_count=0`
- `gap_count=4`
- `publication_time_lineage_verified=false`
- `promotion_ready=false`

这不是回测结果，也不是仓位模型。V15.3/V15.4 的收益结果仍只能作为研究证据，不能因为宏观字段通过时间检查就宣称全部阶段标签已严格时点化。

## 代码审计重点

1. 检查 `point_in_time_phase_rebuilder.py` 是否可能在缺少 lineage 时错误返回 `rebuilt`。
2. 检查 `unverified_dates` 是否完整包含 140 个阶段日期。
3. 检查当前文件 SHA-256 是否被明确区分于历史时点快照哈希。
4. 检查六项覆盖层特征是否仅为数据契约，没有隐含参数优化、仓位或交易动作。
5. 检查网页是否醒目展示 0/140 严格验证、4 类缺口和“不允许回测”。
6. 检查 API 与 compact dashboard 输出是否保留关键边界。

## 边界

- 不运行覆盖层回测。
- 不选择或优化阈值。
- 不生成百分比仓位。
- 不生成交易信号、订单或券商连接。
- 不将缺失估值静默替换为价格延伸代理。
- 不修改 `data/structural_survival_dataset.json` 的既有本地变更。

## 运行与验证

```text
python scripts/run_v15_point_in_time_phase_rebuild.py
python scripts/test_v15_point_in_time_phase_rebuild.py
python scripts/test_macro_context_history.py
python -m compileall strategy_rebase scripts web
node --check web/static/dashboard.js
```

Web 验证目标：

- `/api/strategy-rebase/v15-point-in-time-phase-rebuild`
- `/api/strategy-rebase/v15-late-cycle-overlay-manifest`
- `/api/results/summary?compact=true`
- `/validation`
