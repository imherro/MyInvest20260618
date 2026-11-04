# 运行手册

## 1. 配置检查

```powershell
python -m shortterm_trader.cli doctor
```

检查结果只显示密钥是否存在，不显示密钥内容。

## 2. 拉取单个标的

```powershell
python -m shortterm_trader.cli fetch 000001.SZ --start 20260601 --end 20260615
```

缓存写入 `data/cache/`。

## 3. 扫描股票池

```powershell
python -m shortterm_trader.cli scan --universe config/universe.sample.csv --start 20260501 --end 20260615
```

报告写入 `reports/`。

## 4. 同步行情入库

```powershell
python -m shortterm_trader.cli sync-bars --universe config/universe.sample.csv --start 20260101 --end 20260615
```

行情写入 `data/shortterm.sqlite`，后续计划和面板可复用。

## 5. 明日计划

```powershell
python -m shortterm_trader.cli plan --universe config/universe.sample.csv --start 20260101 --end 20260615
```

报告写入 `reports/plan_*.csv` 和 `reports/plan_*.md`。输出是观察池和触发条件，不是下单指令。

## 6. 回测

```powershell
python -m shortterm_trader.cli backtest 000001.SZ --start 20250101 --end 20260615
```

输出指标包括总收益、最大回撤、暴露比例、交易次数、胜率和简化夏普。

## 7. 宏观序列

```powershell
python -m shortterm_trader.cli macro DGS10 --start 2025-01-01
```

需要 `.env` 中存在 `FRED_API_KEY`。

## 8. QMT 真实持仓只读导入

优先方式是在 QMT 独立交易端已经登录的情况下，直接从终端只读查询真实持仓：

```powershell
py -3.11 -m shortterm_trader.cli qmt-positions
```

也可以在 8009 面板的 `手动运行` 区域点 `导入持仓`。系统只调用查询资产和查询持仓接口，不调用报单、撤单接口。

`.env` 至少需要配置 `QMT_SDK_PATH`。如果系统无法自动识别目录或账号，可补充：

```text
QMT_USERDATA_PATH=C:\path\to\userdata_mini
QMT_ACCOUNT_ID=your_account_id
```

快照会写入：

- `data/qmt_positions_latest.json`
- `data/qmt_positions_latest.csv`

面板的 `真实持仓` 区域会展示最新导入结果，账号只显示掩码。

备用方式是读取从 QMT 导出的持仓 CSV/XLSX：

```powershell
python -m shortterm_trader.cli qmt-positions --file C:\path\to\qmt_positions.csv
```

也可以在 `.env` 中配置：

```text
QMT_POSITION_EXPORT=C:\path\to\qmt_positions.csv
```

终端查询失败且配置了 `QMT_POSITION_EXPORT` 时，面板按钮会自动用导出文件作为备用。

## 9. QMT 实时行情只读接入

先诊断当前环境：

```powershell
py -3.11 -m shortterm_trader.cli qmt-doctor --symbols 000001.SZ,510300.SH
```

上面的命令需要在项目目录 `C:\Users\kunpeng\Documents\MyShortTerm` 里运行。如果当前在别的目录，可直接用脚本：

```powershell
& C:\Users\kunpeng\Documents\MyShortTerm\scripts\qmt-doctor.ps1 -Symbols 000001.SZ,510300.SH
```

PowerShell 脚本的 `-Symbols` 支持逗号和空格写法；也可以写成 `-Symbols "000001.SZ,510300.SH"`。

如果 `xtquant` 可以导入且 QMT 客户端在线，启动只读刷新：

```powershell
py -3.11 -m shortterm_trader.cli qmt-watch --symbols 000001.SZ,510300.SH --interval 3
```

或从任意目录运行：

```powershell
& C:\Users\kunpeng\Documents\MyShortTerm\scripts\qmt-watch.ps1 -Symbols 000001.SZ,510300.SH -Interval 3
```

它会持续写入 `data/qmt_realtime.json`，供 `8009` 面板读取。此流程只调用行情接口，不接交易写入。

也可以在 8009 面板的 `手动运行` 区域点 `刷新全量行情`。面板会自动把 `QMT_REALTIME_SYMBOLS`、真实持仓和最新计划里的 A 股观察标的合并后刷新，不需要手动输入代码。

如果 XtQuant SDK 不在 Python 路径里，可在 `.env` 配置：

```text
QMT_SDK_PATH=C:\path\to\xtquant_parent
QMT_REALTIME_SYMBOLS=000001.SZ,510300.SH
```

## 10. 本地面板

```powershell
python -m shortterm_trader.webapp --port 8009
```

打开 `http://127.0.0.1:8009` 查看数据源状态、明日计划、最新扫描、最新回测、本地行情库、真实持仓、今日处理清单和缓存行情。

研究频道里的 `资金迁移雷达` 位于 `http://127.0.0.1:8009/capital-migration`。它用代表性指数/ETF 的相对收益、短期动量、回撤修复和成交活跃度观察宽基、科技、红利现金流、周期稳增长、消费医药、防御现金之间的流出压力和承接强度；这只是价量承接代理，不是资金净流入数据，也不是交易指令。

研究频道里的 `策略指数对比` 位于 `http://127.0.0.1:8009/strategy-index-compare`。它对比 `h21052.CSI` 国信价值全收益、`CN2296.CNI` 创成长R、`h20269.CSI` 红利低波全收益、`480092.CNI` 自由现金流R，并提供当前勾选成分的策略等权组合和滚动60日风险平价组合；`000001.SH` 上证指数作灰色背景参考，不参与收益、回撤、回本时间和滚动收益排序。旧地址 `/value-compare` 仍保留兼容。

盘中优先点 `一键盘中刷新`。它会依次导入真实持仓、刷新全量行情、运行盘中监控，然后页面自动更新 `今日处理清单`。

`今日处理清单` 按 `必须检查`、`补研究`、`继续观察` 分组显示。先看 `必须检查`，再处理缺研究或缺行情的持仓。`补研究` 组会按仓位、浮亏、不在计划、无实时价自动排优先级。

面板里的 `QMT 实时行情` 和 `QMT 真实持仓` 是两件事。前者检查 XtQuant 实时行情 SDK，后者优先从独立交易端只读查询持仓，终端不可用时再读取持仓导出文件。

## 11. 盘中监控

盘中监控会读取最新 `reports/plan_*.csv` 和 `data/qmt_realtime.json`：

优先在 8009 面板的 `手动运行` 区域点 `Run 监控`。这等价于运行：

```powershell
python -m shortterm_trader.cli intraday-monitor
```

默认会把新的触发提醒写入 `data/intraday_alerts.jsonl`。同一份计划里，同一个标的、同一种提醒状态只写一次，避免重复刷屏。如果只想生成报告、不写提醒：

```powershell
python -m shortterm_trader.cli intraday-monitor --no-alerts
```

也可以在面板点 `Run 不写提醒`。

状态含义：

- `waiting`：未触发。
- `triggered`：实时价达到计划触发价。
- `invalidated`：实时价跌破失效价。
- `gap_skip`：开盘价超过 `max_open_price`，不追。
- `no_tick`：没有拿到对应 QMT tick。
- `not_monitoring`：计划里不是候选或观察项。

只有 `triggered`、`invalidated`、`gap_skip` 会写入提醒。该流程只生成提示、报告和本地提醒日志，不下单。

自动盘中监控：

```powershell
python -m shortterm_trader.cli intraday-watch --interval 3
```

或从任意目录运行：

```powershell
& C:\Users\kunpeng\Documents\MyShortTerm\scripts\intraday-watch.ps1 -Interval 3
```

`intraday-watch` 默认不生成 `reports/intraday_*.csv/md`，只更新 `data/intraday_status.json` 并写入新的提醒，避免盘中每几秒产生大量报告文件。需要每轮也写报告时再加 `--write-reports`。
