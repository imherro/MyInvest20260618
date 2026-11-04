# MyInvestCycle V2.0 设计文档

状态：已与 ChatGPT 审计窗口达成共识  
系统名称：Macro-aware Adaptive Asset Allocation System  
中文定位：宏观感知的自适应资产配置系统

## 1. 项目定位与旧系统结论

V2 不再定义为牛熊预测系统、Alpha 预测系统或自动交易系统。V2 的目标是：在不同长期赔率、中期市场结构、短期风险状态下，动态调整资产风险暴露。

旧 S1.1 仓位风控回测已经证明：风控有效，但收益牺牲过大。其 Alpha 验证未通过，应降级为短期风险温度计和防守参考，不再作为主策略。

旧四维评分保留，但不再决定牛熊、不再决定大仓位、不再主导 ETF 分配。

## 2. V2 总体架构

V2 使用三层模型：

1. Macro Cycle Engine：长期赔率和宏观周期，决定基础风险预算与权益仓位上下限。
2. Market Structure Engine：中期市场结构，解释牛市回撤、顶部背离、熊市反弹等周期内部状态。
3. Tactical Risk Overlay：旧四维模型降级为短期调整层，只做有限仓位微调。

最终进入 Adaptive Allocation Engine，输出目标权益仓位和 ETF/风格配置。

## 3. 数据层设计

所有宏观数据必须区分三个时间：

- `observation_date`：数据对应日期。
- `release_date`：公开发布日期。
- `effective_date`：系统允许使用日期。

回测只能使用 `release_date <= decision_date` 的数据，禁止未来函数。

宏观数据分为五类：

1. 估值赔率：PE/PB 分位、股债收益差、ERP、股票市值/M2、股票市值/GDP。
2. 信用周期：M1、M2、M1-M2、社融增速、社融增量、新增贷款、利率、Shibor。
3. 情绪杠杆：成交额、换手率、两融余额、两融/流通市值、开户数据。
4. 宏观景气：PMI、CPI、PPI、CPI-PPI、GDP、商品价格。
5. 外部环境：美债、美元指数、人民币汇率、AH 溢价、恒生估值。

缺失数据必须显式报告，禁止静默伪造。示例：

```json
{
  "indicator": "M1_growth",
  "status": "missing",
  "impact": "macro_score_weight_reduced"
}
```

## 4. Macro Cycle Engine

目标输出：

```json
{
  "macro_state": "BULL",
  "macro_score": 78,
  "confidence": 0.72
}
```

输入维度：

- Valuation Score：长期赔率。
- Credit Score：信用扩张。
- Economy Score：景气确认。
- External Score：外部压力。

初始评分结构：

```text
macro_score =
0.30 * valuation
+ 0.30 * credit
+ 0.20 * economy
+ 0.20 * external
```

状态定义：

- `BEAR`：估值压力或信用收缩，趋势破坏。
- `BOTTOMING`：估值低，信用开始企稳。
- `RECOVERY`：流动性改善，趋势恢复。
- `BULL`：赔率合理，信用扩张，趋势健康。
- `OVERHEATED`：高估值、高拥挤、信用边际下降。
- `RANGE`：周期不明确。

## 5. Market Structure Engine

该层不判断长期牛熊，只判断周期内部结构。

输入：

- 趋势：MA60、MA120、MA250。
- 宽度：上涨比例、新高比例、行业扩散。
- 流动性：成交额、北向、两融。

状态定义：

- `BULL_BROADENING`：牛市扩散，指数强、宽度强。
- `BULL_DIVERGENCE`：牛市分化，指数强、宽度弱，不等于减仓。
- `BULL_PULLBACK`：牛市回撤，长期趋势未破，可能是加仓机会。
- `BEAR_RALLY`：熊市反弹。
- `BEAR_BREAKDOWN`：熊市恶化。
- `RANGE_ACCUMULATION`：震荡筑底。

## 6. Tactical Risk Overlay

保留旧四维：

- trend
- breadth
- liquidity
- volatility

但输出仅为有限调整：

```json
{
  "risk_adjustment": -0.1
}
```

调整范围：`-20%` 到 `+10%`。

同样的短期弱势，在不同宏观结构下含义不同：

- `Macro=BULL` 且 `Structure=BULL_PULLBACK`：短期弱势不应导致大幅降仓。
- `Macro=OVERHEATED` 且短期弱势：应降低风险。

## 7. 最终仓位公式

```text
target_exposure =
macro_base_exposure
+ structure_adjustment
+ tactical_adjustment
```

边界：`0 <= exposure <= 100%`。

示例：

- 牛市回撤：`80% + 10% - 5% = 85%`
- 过热转弱：`80% - 20% - 10% = 50%`

## 8. ETF / 风格分配逻辑

ETF 不是 Alpha 来源，而是实现工具。

分配链路：

```text
Macro -> 权益预算
Structure -> 风格权重
Style Score -> ETF选择
```

示例：

```text
Macro: BULL
Structure: BULL_DIVERGENCE
Style: 成长强

权益90%
成长ETF 40%
宽基30%
红利20%
现金10%
```

## 9. 回测与验证设计

必须使用 walk-forward，禁止全历史一次拟合。

必须满足：

- 所有数据 `release_date <= decision_date`。
- 所有状态和仓位均只使用当时可见数据。
- 回看确认标签只能用于验证，不能进入交易信号。

必须比较：

- 510500
- 510300
- 等权 ETF
- 旧 S1.1
- M2.1
- V2 新模型

必须输出：

- CAGR
- Max Drawdown
- Sharpe
- Calmar
- Average Exposure
- Turnover
- 牛市贡献
- 熊市保护
- 回撤期表现

阶段归因至少覆盖：

- 2015 牛熊
- 2018 熊市
- 2020 疫情冲击
- 2021 抱团与分化
- 2022 熊市
- 2024-2026 当前周期

## 10. 页面与 API 设计

首页核心展示：

1. Macro Cycle：`state`、`score`、`confidence`
2. Market Structure：结构状态
3. Tactical Risk：短期风险温度
4. Portfolio：目标仓位与 ETF 配置

新增 API：

- `GET /api/macro/current`
- `GET /api/structure/current`
- `GET /api/tactical-risk/current`
- `GET /api/allocation/current`
- `GET /api/allocation/history`

## 11. 开发阶段任务拆分

- Phase V2.1：Macro Data Foundation
- Phase V2.2：Macro Cycle Engine
- Phase V2.3：Market Structure Engine
- Phase V2.4：Adaptive Allocation Engine
- Phase V2.5：ETF Mapping
- Phase V2.6：Walk-forward Backtest

## 12. Codex 第一个开发任务 V2.1

任务名：Macro Data Foundation

目标：建立宏观数据基础层。只做数据采集、标准化、时间安全和质量审计，不做状态判断、仓位、策略或回测。

新增目录建议：

```text
macro/
  data_schema.py
  macro_loader.py
  release_calendar.py
  data_quality.py

scripts/
  audit_macro_data.py
```

必须实现 `MacroIndicator` schema：

```json
{
  "indicator": "",
  "value": "",
  "observation_date": "",
  "release_date": "",
  "effective_date": "",
  "source": "",
  "quality_status": ""
}
```

必须实现加载接口：

```python
load_macro_indicator(indicator, start, end)
```

必须实现数据质量检查：

- 缺失
- 时间穿越
- 发布日期错误
- 数据源不可用

必须输出缺口报告：

```json
{
  "missing_indicators": ["M1", "PMI"],
  "available": [],
  "impact": "weights_adjustment_required"
}
```

验收标准：

- 支持 observation/release/effective 三时间。
- 禁止未来数据。
- 无评分逻辑。
- 无仓位逻辑。
- 可扩展。
- 输出数据质量报告。

V2.1 禁止事项：

- 不做 Macro score。
- 不做 Bull/Bear 判断。
- 不做 ETF 配置。
- 不做回测。
- 不做策略。

## 13. 未决问题

这些问题不影响 V2.1 开发，但需要在 V2.2 前讨论：

1. Macro 指标权重是固定，还是采用历史标准化动态权重。
2. Macro state 是否允许人工政策事件修正。
3. ETF 资产池是否扩展到行业 ETF。

## 14. 共识结论

V2.0 设计共识已经达成，可以进入 Codex 开发。第一个任务是 V2.1 Macro Data Foundation。

## 15. V2.0.1 结构性牛市补充

状态：已与 ChatGPT 审计窗口达成补充共识
扩展名称：Structural Bull Rotation Extension

### 15.1 问题背景

后续 A 股可能不是传统全面牛市，而是进入结构性牛市：

- 主线板块轮动上涨。
- 非主线持续下跌或弱势。
- 宽基指数长期原地震荡。
- 指数不一定大涨，但局部机会持续存在。

如果系统只看宽基趋势、全市场宽度和全市场成交，可能会把“宽基没有牛市”误判为“市场没有机会”，从而错过主线行情。

### 15.2 共识结论

结构性牛市应纳入 V2 设计，但不应作为 Macro State。

原因：结构性牛市不是宏观周期，而是市场内部结构状态。正确归属是 Market Structure Engine。

因此：

- 不新增 `macro_state = STRUCTURAL_BULL`。
- 新增 `structure_state = STRUCTURAL_BULL_ROTATION`。
- V2.3 应升级为 `Market Structure & Structural Bull Engine`。

### 15.3 新增市场结构状态

新增状态：

```text
STRUCTURAL_BULL_ROTATION
```

定义：宽基指数未显著上涨，但市场内部存在持续赚钱主线。

特征：

- 沪深300、中证500、上证指数允许横盘或震荡。
- 不要求宽基指数突破。
- 行业或主题层面存在持续相对强势。
- 主线行业或主题具有一定持续性，而不是单日脉冲。
- 风格动量显著，例如成长、小盘、科技或政策主题增强。

输出示例：

```json
{
  "structure_state": "STRUCTURAL_BULL_ROTATION",
  "confidence": 0.75
}
```

### 15.4 与 BULL_DIVERGENCE 的区别

`BULL_DIVERGENCE`：

- 指数上涨。
- 宽度不足。
- 少数权重股推动指数。
- 含义偏风险，代表牛市可能失去广度。

`STRUCTURAL_BULL_ROTATION`：

- 宽基一般或震荡。
- 行业或主题轮动。
- 主线持续创造收益。
- 含义偏机会，代表市场内部仍有赚钱结构。

两者不能混用，方向相反。

### 15.5 新增指标体系

新增 `Structural Opportunity Engine`，用于识别结构性机会。

建议指标：

1. 行业强度矩阵
   - 5日收益
   - 20日收益
   - 60日收益
   - 行业相对宽基收益
   - 行业强度排名

2. 行业扩散度
   - 上涨行业比例
   - 创新高行业比例
   - 强势行业数量
   - Top 行业数量变化

3. 主线持续性
   - 主题或行业连续处于强势排名的天数。
   - 连续超额收益。
   - 20/40/60 日排名稳定性。

4. 行业动量分位
   - 当前行业动量在历史中的分位。
   - 与宽基指数的相对强弱分位。

5. 集中度
   - Top1 行业贡献。
   - Top5 行业贡献。
   - 区分健康轮动与单一抱团。

6. 非主线亏钱效应
   - 非主线行业下跌比例。
   - 个股或行业中位数收益。
   - 市场上涨但多数资产下跌时，应提示结构性风险。

### 15.6 仓位影响

结构性牛市不应因为宽基震荡而自动降仓。

原则：

```text
Macro 决定权益风险预算
Structure 决定资金方向
Style / Theme 决定 ETF 选择
```

示例：

```text
Macro: BULL
Structure: STRUCTURAL_BULL_ROTATION

权益仓位: 80%-95%
行业/主题ETF: 60%
成长/风格ETF: 20%
宽基ETF: 10%
现金: 10%
```

若：

```text
Macro: RANGE
Structure: STRUCTURAL_BULL_ROTATION
```

则权益仓位可以为 50%-70%，但不应直接满仓。

若：

```text
Macro: BEAR
Structure: STRUCTURAL_BULL_ROTATION
```

默认不允许直接判定结构性牛市，应防止把熊市反弹误判为主线行情。

### 15.7 ETF / 行业策略补充

新增策略方向：

```text
Structural Bull Rotation Strategy
```

定位：Market Structure Response Strategy，不是独立 Alpha 预测器。

输入：

```text
Macro Cycle
+ Market Structure
+ Industry / Theme Strength
```

输出：

```text
行业/主题ETF权重
风格ETF权重
宽基ETF权重
现金权重
```

新版分配链路：

```text
Macro Cycle -> 权益预算
Market Structure -> 风格/行业方向
Style / Theme Rotation -> ETF配置
```

### 15.8 回测设计

结构性牛市回测最容易出现未来函数，必须禁止事后指定主线。

禁止：

- 事后定义“某一年 AI 是主线”。
- 事后选择表现最好的行业。
- 用未来收益确认当前主线。

允许：

- 每天只用当时可见的行业过去 5/20/60 日收益。
- 每天只用当时可见的行业扩散、行业动量和相对强弱。
- 使用 walk-forward 方式验证参数。

必须比较：

- 宽基持有。
- 等权行业 ETF。
- 普通 ETF 轮动。
- Macro-Style。
- Structural Bull Rotation Strategy。

必须输出：

- CAGR
- Max Drawdown
- Calmar
- Turnover
- 主线命中率
- 主线切换频率
- 非主线亏钱效应
- 宽基横盘期收益贡献

### 15.9 页面与 API 补充

`GET /api/structure/current` 应增加结构性牛市字段。

示例：

```json
{
  "structure_state": "STRUCTURAL_BULL_ROTATION",
  "theme_strength": 0.78,
  "breadth": 0.42,
  "industry_dispersion": 0.65,
  "leading_themes": ["AI", "semiconductor"]
}
```

页面新增市场结构卡片：

```text
Macro: BULL
Structure: STRUCTURAL_BULL_ROTATION
Explanation: 指数震荡，但主线扩散增强
```

首页不应只展示宽基牛熊，还要展示“市场有没有赚钱结构”。

### 15.10 开发任务影响

原：

```text
V2.3 Market Structure Engine
```

升级为：

```text
V2.3 Market Structure & Structural Bull Engine
```

建议拆分：

- V2.3.1 Industry / Theme Opportunity Data Foundation
- V2.3.2 Structural Bull Detection
- V2.3.3 Theme Rotation Signal
- V2.3.4 ETF Allocation Integration

这不影响 V2.1 Macro Data Foundation。V2.1 仍应先建设宏观数据基础层。

### 15.11 补充共识

结构性牛市已纳入 V2 设计共识。

最终原则：

```text
全面牛市和结构性牛市都可以允许较高权益暴露，
区别在于资金方向不同。
```

V2 的核心升级不是预测“牛市还是熊市”，而是识别“市场有没有赚钱结构”。
