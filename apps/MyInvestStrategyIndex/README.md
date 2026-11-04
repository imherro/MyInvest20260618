# MyInvestStrategyIndex

独立的策略入口页和策略指数对比页，迁移自 `C:\Users\kunpeng\Documents\MyShortTerm` 的 `/value-compare`。

## 页面

- `http://127.0.0.1:8023/`
- `http://127.0.0.1:8023/value-compare`
- `http://127.0.0.1:8023/strategy-index-compare`
- `http://127.0.0.1:8023/chinext-compare`
- `http://127.0.0.1:8023/four-asset-compare`
- `http://127.0.0.1:8023/three-asset-compare`
- `http://127.0.0.1:8023/cashflow-growth-compare`
- `http://127.0.0.1:8023/strategy-backtests`
- `http://127.0.0.1:8023/us-etf-compare`
- `http://127.0.0.1:8023/us-inflation-portfolio`
- `http://127.0.0.1:8023/us-etf-strategy-observer`

首页是策略卡片入口，分为“策略研究”和“策略回测”两类。`/value-compare`、`/chinext-compare`、`/four-asset-compare`、`/three-asset-compare` 和 `/cashflow-growth-compare` 属于策略研究卡片；`/strategy-backtests` 属于策略回测卡片。`/value-compare` 和 `/strategy-index-compare` 打开同一页：页面对比国信价值全收益、创成长R、红利低波全收益、自由现金流R、518880 华安黄金ETF、511260 十年国债ETF，并提供策略等权组合、滚动60日风险平价组合和分层权重模型；分层模型使用 Calmar 全样本最优权重：国信价值0%、创成长R11.13%、红利低波0%、自由现金流R25.22%、黄金ETF23.64%、十年国债ETF40.00%，但 70/30 样本外验证弱于等权组合，仅作参考；默认所有有数据项目全部勾选；上证指数作为灰色背景线，不参与指标排序。

`/chinext-compare` 对比创业板三个指数的全收益版本：399006 创业板指使用 399606.SZ 创业板R，399673 创业板50使用 CN2673.CNI 创业板50R，399296 创成长使用 CN2296.CNI 创成长R。

`/four-asset-compare` 对比创业板R、自由现金流R、518880 华安黄金ETF、511260 十年国债ETF，并提供四资产等权组合和 Calmar 全样本最优分层权重模型。分层权重为创业板R15.80%、自由现金流R18.45%、黄金ETF25.74%、十年国债ETF40.00%；2017-08-24 至 2026-07-02 全样本区间年化收益10.43%、最大回撤8.05%、Calmar 1.296。

`/three-asset-compare` 对比创业板R、自由现金流R、518880 华安黄金ETF，并提供三资产等权组合和 Calmar 全样本最优分层权重模型。页面默认从 2017-08-24 开始；分层权重为创业板R21.68%、自由现金流R38.32%、黄金ETF40.00%；2017-08-24 至 2026-07-02 区间年化收益14.75%、最大回撤15.84%、Calmar 0.931。

`/cashflow-growth-compare` 参照 `/value-compare` 的完整交互，只保留 480092.CNI 自由现金流R收益指数和 CN2296.CNI 创成长R收益指数两个真实指数，同时保留基于当前勾选成分动态计算的双指数等权组合、滚动60日风险平价组合、最新风险平价比例、过去10年逆最大回撤风险平价组合及其权重，并新增最大回撤风险平价再平衡测试：在不再平衡、日/月/季/半年/年和偏离5/10/15%规则中按 Calmar 选出最优规则，展示最优再平衡组合曲线和候选规则表；页面仍包含上证指数灰色背景线、曲线/回撤/散点/指标排序和更新数据功能。

`/us-etf-compare` 对比 RSP、IWY、MOAT、SPMO、PFF、VNQ 六只美股 ETF，并提供每只目标权重 16.67% 的六 ETF 等权组合。历史数据来自 Yahoo Finance 复权收盘价，包含分红和拆股调整。

`/us-inflation-portfolio` 使用 SPMO 30%、MOAT 20%、IEF 20%、IAU 15%、KMLM 10%、PDBC 5% 构建美股抗通胀组合。回测采用月末复权总回报、季度检查、3个百分点或25%相对偏离阈值、10bp单边成本、只做多且无未来数据，并输出收益、风险、滚动收益、相关系数、风险贡献和年度换手率。

`/us-etf-strategy-observer` 按核心 Beta、风险/风格增强器、防御或避险组件和策略类，观察 VOO、SPY、VTI、ITOT、QQQ、IJH、IWM、VUG、VTV、SPLV、SCHD、MTUM、COWZ、VYM、XLP、XLU、GLD、SGOV、VNQ、PFF、USMV、DIVO、JEPI。页面以 Calmar、年化收益、最大回撤和波动率为核心，并根据当前勾选标的实时重算日线动态等权组合。

`/strategy-backtests` 读取同级 `C:\Users\kunpeng\Documents\MyInvestCycle\data\strategy_backtests\*.json` 的已生成策略回测结果，按资产配置、ETF轮动、自由现金流、回归/回撤等类别汇总。每个策略有详情页，展示回测摘要、净值曲线、最新权重、对比资产、最近信号和验证信息。当前阶段只复制 Cycle 子系统的回测结果查看功能，不迁移或混合两个系统的回测引擎；如果目录位置不同，可以用环境变量 `MYINVEST_CYCLE_BACKTEST_DIR` 指向 JSON 结果目录。

## 运行

先在 `.env` 配置：

```text
TUSHARE_TOKEN=...
```

启动：

```powershell
python -m myinvest_strategy_index.webapp --port 8023
```

默认端口是 `8023`，默认绑定 `0.0.0.0`，局域网可通过本机 IP 访问。

## Calmar 优化

使用本地 `data/cache/value_compare_*.csv` 历史价格缓存，生成 6 资产 Calmar Ratio 优化报告：

```powershell
python -m myinvest_strategy_index.calmar_optimizer --seed 20260703
```

输出会写入 `reports/calmar_optimizer/`，包含 Markdown 报告、权重 CSV、净值曲线 CSV 和净值曲线 PNG。
