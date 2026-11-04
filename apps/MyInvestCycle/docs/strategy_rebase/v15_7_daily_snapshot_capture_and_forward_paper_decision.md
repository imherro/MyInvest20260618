# V15.7 每日前向快照与纸面决策

## 目标

从 2026-07-20 开始，把每日运行时真实可见的五个本地源复制为不可变快照，并生成只用于未来观察的纸面决策记录。V15.7 不回填历史，不运行回测，不优化参数，也不生成仓位、标的或买卖指令。

## 最短业务闭环

1. 复制宏观、市场阶段、风格、结构和沪深300日线源文件。
2. 对每个复制文件计算并复核 SHA-256。
3. 生成规范化 payload 的 `manifest_sha256`。
4. 从快照中的市场阶段读取当日可见状态。
5. 输出 `forward_observation_only` 纸面记录，留待未来结果验证。

同一日期重复运行时只验证并复用已有 Manifest，不覆盖当日快照。源文件缺失时记录 `missing`，不创建空文件。

## 当前读数与边界

- 市场阶段：`LATE_CYCLE`。
- 宏观状态：`RECOVERY`。
- 结构状态：`STRUCTURAL_BULL_ROTATION`。
- 历史估值：不可用。
- 纸面决策状态：`insufficient_for_trade_decision`。
- 允许用途：`forward_observation_only`。
- 回测：禁止。
- 生产交易：禁止。

当前读数只是快照中的研究状态，不是实盘信号。

## 产物

- `data/point_in_time_snapshots/20260720/manifest.json`
- `data/point_in_time_snapshots/20260720/sources/*`
- `data/v15_daily_snapshot_capture_status.json`
- `data/v15_forward_paper_decision_latest.json`
