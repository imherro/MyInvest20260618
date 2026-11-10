# 龙头研究日更

先阅读本目录 README.md，遵守 claim/generate/finish 协议。任务键为 `leader`。
所有命令从总仓库运行，不使用旧仓库脚本，不开启 8014 服务。

1. `inspect leader` 验证路径与旧 writer；`claim leader` 成功后记录 token。
2. `generate leader --token <token>` 先做上游新鲜度门禁，再按原顺序运行龙头、个股深研、最终审计。
   第一阶段失败、缺口或旧基准日即停止，不强行生成下游或用历史报告冒充新报告。
3. 无论生成成功或失败，运行 `python scripts/test_subsystems.py --system leader --data-root ..`，
   明确这只是隔离健康测试，不代表上游新鲜。
4. 只读验证 `http://127.0.0.1:8888/api/leader/latest`、`/api/leader/index`、`/api/leader/stocks/deep/latest`。
   检查真实响应结构，比较基准日、报告 lineage，核对 A 可跟踪龙头和数据缺口。
5. 影子输出保持 read_only、ratio_only，不包含真实资金、股数或交易指令。
6. 成功且验证通过再 `finish leader --token <token> --outcome success`；验证失败则 outcome failed。
   generate 已失败时状态已经关闭，不再次 finish、不重试。
7. 中文汇报生成状态、基准日、主线、A 可跟踪龙头、数据缺口、测试和 API 验证。
   明确研究产物保留在原 `MyInvestLeader/research`，未自动提交/推送数据，不修改或输出 .env。
