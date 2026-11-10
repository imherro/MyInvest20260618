# 市场研究日更

先阅读本目录 README.md，任务键 `market`。从总仓库 inspect/claim，仅在取得本次 token 后写入。

1. `python scripts/research_jobs.py generate market --token <token>` 运行原收盘更新，保留其幂等和完整性检查。
   最新完整 A 股交易日生成市场评分、市场观察、A-FEAR、四仓配置、模型验证、模型健康、稳健性历史。
2. skipped 如实说明是基准日未变、候选数据不完整或已有任务运行，不强制旧日报。
   updated 汇报基准日、run_id、机会分、风险扣分、仓位分、权益仓位区间、市场/趋势状态、A-FEAR、健康与稳健性。
3. 更新完成后进行一次独立市场问答，分析周期、仓位、未来 3 至 12 个月方向；不预测明天涨跌、不复述券商。
   至少核查估值、盈利、宏观流动性、市场结构、情绪风险；缺失项如实列出。
4. 回答完整包含：A 六选一周期阶段与置信度；B 0 至 100%建议总仓位及较昨日动作；
   C 按风险收益排序 3 至 5 个方向、ETF 优先；D 三个不追方向及原因；
   E 大幅加仓/减仓所缺信号；F 较昨日实质变化。信息不足明确“今天无需交易”，保持不动为默认。
5. 按 `apps/MyInvestMarket/data/chatgpt_qa_history.json` 现有结构追加，唯一 record_id，
   保留基准日、提问时间、模型、阶段、置信度、建议仓位、动作、方向、不追方向、拐点、昨日变化、风险、证据和完整正文。
   同基准日复问不能覆盖旧记录，应写 comparison_to_previous。该路径仍解析到原项目 data。
6. `python scripts/test_subsystems.py --system market --data-root ..`；只读验证统一入口
   `/api/market/dashboard`、`/api/market/index`、`/api/market/chatgpt-qa/latest`、`/api/market/chatgpt-qa/history`、
   `/market/chatgpt-qa.html`，origin 为 `http://127.0.0.1:8888`，确认基准日一致。
7. 完成生成、问答、测试和验证后 finish success；失败则 finish failed；generate 已失败不再次 finish。
   研究产物保留原目录，不自动提交/推送数据，汇报明确区分 updated/skipped/failed。

使用原 .env，不输出、修改、提交密钥；不提交临时/缓存/日志或无关改动。
不输出真实账户金额、股数、交易指令或下单动作；样本不足 deployable=false 如实汇报，不包装为有效统计结论。
