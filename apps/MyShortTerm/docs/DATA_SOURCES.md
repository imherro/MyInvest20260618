# 数据源说明

本系统读取本地 `.env`，但不会在日志、报告或文档里输出密钥值。

## 默认路由

| 场景 | 主源 | 备用 / 补充 |
| --- | --- | --- |
| A 股日线和结构化行情 | Tushare | BaoStock |
| A 股盘中价格 | QMT 只读 | Tushare / BaoStock 日线 |
| 真实持仓 | QMT 独立交易端只读查询 | QMT 导出文件 / 手工 CSV |
| 海外市场和 ETF | yfinance | 网络材料 |
| 宏观数据 | FRED | 官方网页 / 网络材料 |
| 新闻和公告类证据 | 交易所、公司公告、主流财经网页 | 不替代行情数据 |

## 本机 `.env`

当前代码识别以下键名：

```text
TUSHARE_TOKEN=
FRED_API_KEY=
QMT_POSITION_EXPORT=
QMT_SDK_PATH=
QMT_USERDATA_PATH=
QMT_ACCOUNT_ID=
QMT_REALTIME_SYMBOLS=000001.SZ,510300.SH
```

`QMT_SDK_PATH` 用于读取 QMT 行情，也用于在独立交易端已经登录时只读查询真实持仓。
`QMT_USERDATA_PATH` 和 `QMT_ACCOUNT_ID` 是可选项；系统会尽量从 SDK 路径自动识别 `userdata_mini` 和单一账号目录。
`QMT_POSITION_EXPORT` 可指向从 QMT 导出的持仓 CSV/XLSX，作为终端查询失败时的备用。系统不写回 QMT，不下单。
在 8009 面板点击 `导入持仓` 后，最新快照保存在本机 `data/qmt_positions_latest.json/csv`，不上传到 GitHub。

QMT 分成两类状态：

- `QMT 实时行情`：检查当前 Python 进程能否导入 `xtquant` 并读取盘中行情。
- `QMT 真实持仓`：优先从独立交易端只读查询持仓；终端不可用时读取 `QMT_POSITION_EXPORT` 指向的导出文件。

如果面板显示 `QMT 实时行情` 未就绪，通常是当前运行 Python 环境没有加载 XtQuant SDK，或 QMT 客户端未打开登录；这不等于 Tushare/BaoStock 的盘后计划不可用。

QMT 实时行情也可以由独立进程提供：用 Python 3.11 运行 `qmt-watch`，持续写入 `data/qmt_realtime.json`，`8009` 面板会读取这个本地快照。

更省事的方式是在 8009 面板点击 `刷新全量行情`。系统会合并 `QMT_REALTIME_SYMBOLS`、真实持仓和最新计划里的 A 股观察标的，只读刷新到 `data/qmt_realtime.json`。

## 设计原则

- A 股结构化行情优先使用 Tushare。
- BaoStock 是交叉验证和免费备用源，不替代主源。
- QMT 是本地终端源，适合盘中价格和真实持仓只读导入。
- yfinance 与 FRED 用于海外和宏观环境判断。
- 网络网页只做补充证据，并且必须保留来源和时间。
