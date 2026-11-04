# V15.6 审计包

## 仓库信息

- 仓库：`https://github.com/imherro/MyInvestCycle`
- 分支：`main`
- 上游提交：`127c77781ec77a9bdccaef5b47e31ec0d1f40592`
- 阶段：V15.6

## 核心结果

- `ledger_status=ledger_gap_report_ready`
- `decision_date_count=140`
- `snapshot_complete_count=0`
- `strict_point_in_time_eligible_count=0`
- `hash_verified_count=0`
- `valuation_snapshot_available_count=0`
- `backtest_allowed=false`
- `promotion_ready=false`

观测日期覆盖：宏观 140、宽基 140、风格 140、结构 79、估值 0。观测日期覆盖不代表不可变历史快照覆盖。

## 审计重点

1. 缺少 `captured_at`、发布日期、生效日期、源版本或历史快照 hash 任一字段时，能否错误通过。
2. `source_sha256_origin` 不是 `historical_snapshot_file` 时，能否错误通过。
3. 当前文件 hash 是否只出现在 `current_file_sha256`，未复制到历史 `source_sha256`。
4. 五类源是否逐日列出，且 140 个日期均未错误标为 eligible。
5. 估值缺失时是否强制 `backtest_allowed=false`。
6. gap 存在时是否可能返回 `ledger_rebuilt`。
7. API compact 输出与网页是否保留 0/140、hash=0、valuation=0 和禁止回测边界。

## 新增产物

- `strategy_rebase/point_in_time_snapshot_ledger.py`
- `scripts/run_v15_point_in_time_snapshot_ledger.py`
- `scripts/test_v15_point_in_time_snapshot_ledger.py`
- `data/v15_point_in_time_snapshot_ledger.json`
- `data/v15_point_in_time_snapshot_ledger_status.json`
- `docs/strategy_rebase/v15_6_point_in_time_snapshot_ledger.md`
- `docs/audit_packages/20260720_v15_6_point_in_time_snapshot_ledger.md`

修改 `strategy_rebase/__init__.py`、`web/app.py`、`web/templates/validation.html`、`web/static/dashboard.js`。

## 边界

- 不运行回测。
- 不优化参数。
- 不生成仓位、ETF 映射或交易信号。
- 不生成订单、不连接券商。
- 不用 0、当前值或未来值填补历史估值。
- 不修改或提交既有 dirty 文件 `data/structural_survival_dataset.json`。

## 验证命令

```text
python scripts/run_v15_point_in_time_snapshot_ledger.py
python scripts/test_v15_point_in_time_snapshot_ledger.py
python scripts/test_v15_point_in_time_phase_rebuild.py
python -m py_compile strategy_rebase/point_in_time_snapshot_ledger.py scripts/run_v15_point_in_time_snapshot_ledger.py scripts/test_v15_point_in_time_snapshot_ledger.py web/app.py
node --check web/static/dashboard.js
python -m compileall strategy_rebase scripts web
```

Web 目标：

- `/api/strategy-rebase/v15-point-in-time-snapshot-ledger`
- `/api/strategy-rebase/v15-point-in-time-snapshot-ledger-status`
- `/api/results/summary?compact=true`
- `/validation`
