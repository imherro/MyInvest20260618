# 主线研究日更

先阅读本目录 README.md，任务键 `theme`。从总仓库运行 inspect/claim，只有取得本次 token 后才能写入。
代码目录为 `apps/MyInvestTheme`；data/research 保持原路径，以下相对业务路径均在该子目录。

1. 检查工作区，绝不修改、输出或提交 .env、token、缓存、日志、temp 或无关改动。
2. 必要时按 `docs/POLICY_SIGNALS.md` 检查近 90 天官方政策/监管源，并按 schema 更新 `data/policy_signals.json`。
   没变化不制造变化；保留候选记录、来源、时间和内容 hash，遵守 canonical 政策审计。
3. 在总仓库运行 `python scripts/research_jobs.py generate theme --token <token>`。
   使用原 daily_mainline_update，保留 canonical 审计、时代主线生成、测试失败回滚，测试改在隔离副本。
   不调用或启动外部 market 系统，不用 --force/--skip-tests 绕过门禁。
4. Tushare 为首选；同花顺仅对已实现的市场广度、宽基指数阶段，在 Tushare 为空或异常时只读兜底，
   记录来源与原因。不替换申万行业、大单/特大单、主题、ETF、涨停口径，不静默混合数据。
5. skipped 如实说明 reason，不强制旧日报。成功或 skipped 后都完成一次独立 ChatGPT 问答，
   使用最新可用主线、时代主线、市场及政策资料，明确实际基准日；生成失败不伪造报告。
6. 每次只问一次，读取 `config/chatgpt_qa_prompt.md`，独立判断，不简单复述共识。
   比较上一份 `research/chatgpt_qa/chatgpt_qa_YYYY-MM-DD.json`；无实质变化明确说明，不强行改观点。
7. 完整问题、回答及摘要写入 `apps/MyInvestTheme/temp/chatgpt_qa_answer.json`。
   至少有 basis_date、source_report_id、question、answer_markdown、summary_fields、ranking、daily_changes、data_basis。
   summary_fields 为字段/内容数组；ranking 包含 rank、theme、stage、certainty、valuation、future_space、score、strategy；
   daily_changes 包含强化、削弱、排名变化、仅价格变化、新候选。保留政策、产业、盈利、估值、反证判断。
8. 从总仓库执行 `python scripts/research_jobs.py qa theme --token <token> --input <上述JSON绝对路径>`，
   确认原 research/chatgpt_qa 下 JSON/Markdown 生成；不提交临时文件。
9. `python scripts/test_subsystems.py --system theme --data-root ..`；只读验证
   `/theme/chatgpt-qa`、`/api/theme/chatgpt-qa`、`/api/theme/chatgpt-qa/latest`、`/api/theme/latest`、`/api/theme/index`，
   origin 为 `http://127.0.0.1:8888`。不要直接在 app 目录 pytest。
10. 成功或合理 skipped、问答和验证完成后 finish success；其他情形 finish failed，generate 已失败不再 finish。
    汇报日报、时代主线、问答基准日、顶部政策主线/政策分/热度分、问答第一时代主线、数据质量、测试和验证。
    研究产物保留原目录，不自动提交数据。独立评论不修改 canonical 分数、时代主线模型或历史报告。
    只读研究，不输出真实交易指令。全过程简洁中文汇报。
