# 统一研究任务

任务清单在根目录 `research_jobs.json`，业务说明在本目录。Codex 是调度器，仓库不是第二份调度器。
迁移只更新原自动化 ID，不创建新任务；时间按 Asia/Shanghai，保留现有启停状态：

| 任务 | 原 ID | 时间 | 状态 |
| --- | --- | --- | --- |
| 龙头 | myinvestleader | 工作日 19:05 | ACTIVE |
| 市场 | myinvestmarket | 工作日 21:00 | PAUSED |
| 主线 | a-2 | 工作日 22:00 | PAUSED |

影子原有进程内调度已由统一服务的 shadow worker 承载，不创建 Codex/Windows 副本。
时间仍以原 `MyInvestShadow/.env` 的 `SHADOW_SCHEDULE_TIMES` 为准，缺省 21:10、21:40、22:10；
原算法每天成功一次，失败后尝试后续时段，保持不变。
其他频道未发现已有 Codex 日更任务或 Windows MyInvest 计划任务，不凭空为它们增加频率。
Web 巡检任务不属于研究任务，本次不修改其暂停状态或时间。

## 数据与安全边界

- 代码从 `apps/<项目>` 执行，`data`、`research` 继续通过已验证的 junction 写入原同级项目。
- 读取原项目 `.env`，不复制密钥，不修改原源码。市场 `web/data` 和旧更新锁路径仍指向原项目。
- 服务验证使用 `http://127.0.0.1:8888/api/<频道>/...`，不重启独立端口、不绕公网调用自身。
- 产物仍在原目录。生产数据被总仓库忽略，任务不对原仓库或总仓库自动执行 git add/commit/push。
  源码、任务定义、测试和说明由总仓库审核后发布；不要为上传研究数据而使用 `git add -f`。
- 测试调用 `scripts/test_subsystems.py` 在一次性源码副本中执行，禁止在 production junction 上直接 pytest。
- 主线政策变化使用内容指纹，对比本次 claim 前与上次成功生成的指纹，不依赖被忽略的数据目录的 Git 状态。
- 原有研究口径、数据源优先级、只读比例化约束保持不变，不增加真实交易功能。

## 每次运行协议

先阅读对应频道说明，再执行（以龙头为例）：

```powershell
python scripts/research_jobs.py inspect leader
python scripts/research_jobs.py claim leader
python scripts/research_jobs.py generate leader --token <claim返回的token>
python scripts/test_subsystems.py --system leader --data-root ..
python scripts/research_jobs.py finish leader --token <同一token> --outcome success
```

只有 `claimed=true` 才能写政策、日报或问答。重复触发应直接结束，**不能使用已有 token 冒充原运行**。
`generate` 只允许一次；主线问答另用 `qa theme --token ... --input <绝对JSON路径>`。
完成生成后仍持有整个研究会话，直到问答、隔离测试和只读 API 检查完成才能 finish。
业务脚本返回 skipped 与执行失败必须区别汇报；skipped 仍可按频道要求完成一次问答。

互斥有两层：操作期间 OS 文件锁防并发，持久 session 状态覆盖跨命令的政策/问答阶段。
同日已成功或失败的任务不自动重试；未完成会话即使跨日也不靠超时抢占。
执行错误保留 failed 结果；中断后 running/claimed 会阻止后续任务，先核对现场，不能直接删除锁。
人工确认没有旧任务/写入进程仍在运行后，可使用原 token 执行 `finish ... --outcome failed` 关闭中断会话；
当天仍不重跑，下一天恢复正常。需要同日补跑时另行人工审核，不在日更任务中绕过幂等限制。
session token 只在本机 `runtime/research-jobs/<频道>/session.json` 保存，不提交 Git。
每次新运行保留上一日 session 历史，不只保留最终状态。

迁移前后检查在运行的旧 writer，发现则停止切换/执行，不能强杀。原任务 ID 原位更新后不会再调度旧目录；
此机制不阻止用户主动绕开入口、在旧目录手工执行脚本，这种操作必须先停调度并确认无任务运行。

## 龙头新鲜度门禁

保持 19:05，不因主线 22:00 而改时间。读取主线 canonical latest，要求其 nominal_today 为当天、
basis_date 不晚于当天且晚于已有龙头基准日、daily/daily_basic 完整且有主题排名。
接口失败、历史回退或不完整则在第一份报告前停止；第一阶段缺口也阻止深研和最终审计。
HTTP 200、旧报告可读、测试通过都不能作为当日日更成功的证明。

## 调度变更与回滚

自动化提示词只引用本仓库说明及入口；业务规则变化先改仓库再测试。
改时间/状态时同时审核清单与现有自动化，通过 Codex automation 工具更新同一 ID，禁止创建重复任务。
运行 `python scripts/audit_research_jobs.py` 可只读检查当前 ID、时间、状态、工作目录和执行入口是否与清单一致。
迁移前定义私有备份在 `runtime/research-jobs-migration/before/`，不进入 Git。
回滚也须工具原位更新原 ID，保留时间/状态；先确认无正在运行会话，再恢复原工作目录与提示词，
不要同时保留新旧两份调度。只恢复旧提示词并不恢复已停用独立端口，须按统一服务方案另行适配。
