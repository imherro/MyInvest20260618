# MyShortTerm

这是一个短线交易研究系统的第一版：从多数据源拉取行情，生成短线候选信号，给出比例化风控参数，并提供回测验证。

## 数据源边界

- Tushare：A 股日线、基础行情和结构化主源。
- QMT：盘中价格和持仓只读导入，不接下单。
- BaoStock：A 股免费交叉验证和备用日线源。
- yfinance：海外市场和 ETF 补充源。
- FRED：宏观利率、流动性等序列源。
- 网络数据：只做补充证据，不覆盖结构化行情源。

## 快速使用

```powershell
python -m shortterm_trader.cli doctor
python -m shortterm_trader.cli fetch 000001.SZ --start 20260601 --end 20260615
python -m shortterm_trader.cli sync-bars --universe config/universe.sample.csv --start 20260101 --end 20260615
python -m shortterm_trader.cli scan --universe config/universe.sample.csv --start 20260501 --end 20260615
python -m shortterm_trader.cli plan --universe config/universe.sample.csv --start 20260101 --end 20260615
py -3.11 -m shortterm_trader.cli qmt-doctor --symbols 000001.SZ,510300.SH
py -3.11 -m shortterm_trader.cli qmt-watch --symbols 000001.SZ,510300.SH --interval 3
py -3.11 -m shortterm_trader.cli qmt-positions
& C:\Users\kunpeng\Documents\MyShortTerm\scripts\qmt-doctor.ps1 -Symbols 000001.SZ,510300.SH
python -m shortterm_trader.cli intraday-monitor
python -m shortterm_trader.cli intraday-monitor --no-alerts
python -m shortterm_trader.cli intraday-watch --interval 3
& C:\Users\kunpeng\Documents\MyShortTerm\scripts\intraday-watch.ps1 -Interval 3
python -m shortterm_trader.cli backtest 000001.SZ --start 20250101 --end 20260615
python -m shortterm_trader.webapp --port 8009
```

行情会写入本地 SQLite 数据库 `data/shortterm.sqlite`，缓存和报告会写入 `data/cache/` 和 `reports/`。`.env` 只在本机读取，不能提交。

本地面板地址默认为 `http://127.0.0.1:8009`。

研究频道包含宽基趋势图、主线指数趋势图、指数/ETF 对比、策略指数对比和 `资金迁移雷达`。策略指数对比位于 `/strategy-index-compare`，对比国信价值全收益、创成长R、红利低波全收益、自由现金流R，并提供策略等权组合和滚动60日风险平价组合，用上证指数作背景参考。资金迁移雷达使用指数/ETF 的相对收益、短期动量、回撤修复和成交活跃度生成价量承接代理，不等同于真实资金净流入。

QMT 实时行情建议用 Python 3.11 单独运行 `qmt-watch`，它会把只读 tick 快照写到 `data/qmt_realtime.json`，面板会自动读取。
QMT 真实持仓可以在独立交易端登录后点页面 `导入持仓`，或运行 `qmt-positions` 生成本机快照。

## 交易边界

系统只输出研究信号和风险比例，不输出股数、金额或自动交易指令。任何候选都需要人工复核流动性、公告、停复牌、财报、监管和市场状态。
