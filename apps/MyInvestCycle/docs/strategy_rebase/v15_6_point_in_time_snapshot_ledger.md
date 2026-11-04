# V15.6 不可变时点源快照账本

## 目标

V15.5 证明现有市场阶段序列不是严格 point-in-time。V15.6 将这一结论推进为逐日期账本：对 140 个历史决策日逐一列出宏观、宽基、风格上下文、结构上下文和估值五类源的时间与哈希证据。

本阶段仍不做回测、不优化参数、不生成仓位、不生成交易信号。

## 账本结论

- 决策日期：140。
- 完整历史快照：0。
- 严格 point-in-time 可用日期：0。
- 已验证历史快照 hash：0。
- 历史估值快照：0。
- `ledger_status=ledger_gap_report_ready`。
- `backtest_allowed=false`。
- `promotion_ready=false`。

可以定位到观测日期的源不等于存在不可变历史快照：

| 源组 | 可定位观测日期 | 完整历史快照 |
| --- | ---: | ---: |
| 宏观 | 140 | 0 |
| 沪深300宽基 | 140 | 0 |
| 风格上下文 | 140 | 0 |
| 结构上下文 | 79 | 0 |
| 历史估值 | 0 | 0 |

## 每日账本结构

每个决策日记录五类 `source_groups`。每组至少检查：

- `observation_date`
- `release_date`
- `effective_date`
- `captured_at`
- `source_version`
- `source_path`
- `source_sha256`
- `source_sha256_origin`
- `hash_verified`

只有所有字段真实存在、`snapshot_available=true`、`hash_verified=true`、`source_sha256_origin=historical_snapshot_file` 且明确确认当前文件就是该历史不可变快照时，该源组才算 lineage 完整。五类源全部完整，日期才可进入 strict point-in-time rebuild。

## Hash 语义

- `source_sha256`：历史决策日对应的不可变快照文件 hash。
- `current_file_sha256`：今天工作区现有文件的 hash，仅用于识别当前输入。
- 两者即使数值相同，也不能仅凭相等证明历史来源。
- 当前缓存 hash 不得复制到 `source_sha256` 冒充历史快照。

当前账本因此保留了当前文件 hash，但所有 `source_sha256` 均为 `null`，`hash_verified=false`。

## V15.6.1 防伪校验

验证器不信任账本中保存的完成标志和状态计数，而是逐日期、逐源组重新计算：

- `source_sha256` 非空时必须是 64 位十六进制 SHA-256。
- 每组 `lineage_complete` 和 `strict_point_in_time_eligible` 必须等于原始 lineage 字段的重算结果。
- 每行完成标志、快照标志和缺失源列表必须等于五组源的重算结果。
- status 的完整日期、严格可用日期、已验证 hash 和估值快照计数必须由账本嵌套字段重算。
- V15.6 是账本阶段，`backtest_allowed` 和 `promotion_ready` 始终必须为 `false`。

因此，单独修改 JSON 中的布尔值、计数或回测开关不能把缺失快照伪装成已验证数据。

## 缺失值与时点边界

- 缺失时间、版本、估值和 hash 均保持 `null`。
- 不使用 0、当前值或未来最近值填补。
- 当日收盘数据只能用于下一交易日的未来研究。
- 事后重建的风格上下文明确标记 `historically_reconstructed=true`。

## 后续条件

启动严格阶段重建前，必须实际获得或按日归档不可变源快照。最低需要：

1. 快照文件本体和固定路径。
2. 抓取时间与源版本。
3. 发布日期与生效日期。
4. 快照 SHA-256 和重新计算校验结果。
5. 历史估值序列。

在这些条件满足前，V15.3/V15.4 仍是研究回测，V15.5 覆盖层仍禁止回测。

## 产物

- `data/v15_point_in_time_snapshot_ledger.json`
- `data/v15_point_in_time_snapshot_ledger_status.json`
- `strategy_rebase/point_in_time_snapshot_ledger.py`
- `scripts/run_v15_point_in_time_snapshot_ledger.py`
- `scripts/test_v15_point_in_time_snapshot_ledger.py`
