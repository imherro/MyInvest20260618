# V15.5 严格时点阶段审计与高位风险覆盖层设计

## 目的

V15.3/V15.4 使用了历史市场阶段序列。V15.5 不继续优化收益，而是先回答一个更基础的问题：这些阶段标签能否用每个决策日当时已经公开、已经生效且版本可追溯的数据重新生成。

本阶段只做证据审计和数据契约设计，不回测、不选参数、不输出仓位、不生成交易信号。

## 审计结论

当前结论为 `gap_report_ready`，不是 `rebuilt`：

- 阶段日期：140 个。
- 宏观发布日期与生效日期安全：140/140。
- 具备完整抓取时间、源版本、发布日期/生效日期和源文件哈希的阶段日期：0/140。
- 事后从当前本地缓存重建的风格上下文：140/140。
- 结构字段完整：79/140。
- PE/PB 百分位或 ERP 历史可用：0/140。
- 严格时点已验证日期：0/140。
- `publication_time_lineage_verified=false`。
- `promotion_ready=false`。

“没有使用未来收益”只说明分类器未用未来回报作为输入，并不等于“保存了当时真实可见的数据快照”。现有风格、宽度、拥挤和价格延伸字段是后来用当前本地缓存重算的；缺少每个历史决策日对应的不可变快照、抓取时间、源版本和文件哈希，因此不能标记为严格 point-in-time。

## 四类阻断缺口

1. 阶段行缺少完整发布时间链路：未同时保存 `captured_at`、源发布日期、源生效日期、源版本和源 SHA-256。
2. 风格上下文为历史重建：行业范围和价格缓存虽只截取当日以前数据，但无法证明今天的缓存内容和行业定义就是当时版本。
3. 结构上下文不完整：61 个阶段日期缺少趋势、宽度、流动性、波动或压力字段。
4. 历史估值缺失：140 个日期均没有 PE/PB 百分位和 ERP，无法审计高位风险。

## 严格时点行契约

未来可重建的每行至少保存：

- `decision_date`
- `captured_at`
- `source_observation_date`
- `source_release_date`
- `source_effective_date`
- `source_version`
- `source_sha256`
- `transformation_version`

当日收盘后观察到的数据只能影响下一交易日收益。历史缺失值必须保留为 `null`，不得用 0、当前值或未来最近值填补。

## 高位风险覆盖层

V15.5 只定义六项输入，不给阈值：

| 特征 | 含义 | 当前状态 |
| --- | --- | --- |
| `valuation_percentile` | 宽基 PE/PB 与 ERP 的扩展窗口历史百分位 | 缺失 |
| `crowding_score` | 行业宽度、持续性、延伸与集中度形成的拥挤度 | 部分存在，时点链路未证实 |
| `turnover_concentration` | 领先行业成交额占全市场成交额比例及其历史位置 | 缺失 |
| `breadth_divergence` | 宽基趋势创新高与行业/成分参与度背离 | 部分存在，早期不完整 |
| `late_cycle_heat` | 严格时点晚周期 + 高估值/拥挤的解释型复合状态 | 被上游缺口阻断 |
| `high_level_drawdown_risk` | 高估值/高拥挤状态下发生的回撤，而非牛市早中期回调 | 被上游缺口阻断 |

研究意图是：只有“晚周期 + 高估值或高拥挤/集中 + 回撤或宽度背离”同时出现时，才研究降低风险；牛市早中期、估值和拥挤不高的回调，不应被同一规则机械减仓。

## V15.6 前置门槛

以下条件未全部满足前，不启动覆盖层回测：

- 严格 point-in-time 阶段序列可复现。
- 每个输入具备发布日期、生效日期、抓取时间、版本和哈希。
- 历史估值数据可用。
- 覆盖率门槛和缺失值处理事先登记。
- 参数与样本外验证方案事先登记，不能根据最终收益倒推。

## 产物

- `data/v15_point_in_time_phase_rebuild_status.json`
- `data/v15_late_cycle_overlay_manifest.json`
- `strategy_rebase/point_in_time_phase_rebuilder.py`
- `strategy_rebase/late_cycle_overlay.py`
- `scripts/run_v15_point_in_time_phase_rebuild.py`
- `scripts/test_v15_point_in_time_phase_rebuild.py`
