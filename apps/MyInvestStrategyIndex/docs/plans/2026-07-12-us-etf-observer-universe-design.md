# 美股 ETF 策略观察池调整

## 目标

- 从策略观察池移除 SPY、ITOT。
- 对用户给出的代码去重，保留已有 PFF、VNQ，新增 RSP、IWY、MOAT、SPMO、IEF、IAU、KMLM、PDBC。
- 不改变既有 ETF 的分类和动态等权计算方式。
- 默认只勾选 VOO 和动态等权组合，其余 28 只真实 ETF 默认不选。

## 分类

- 风险/风格增强器：RSP、IWY、MOAT、SPMO。
- 防御或避险组件：IEF、IAU、PDBC。
- 策略类：KMLM。

## 验证

- 数据层断言真实 ETF 共 29 只，SPY、ITOT 不存在，新增代码完整且不重复。
- 页面继续按当前勾选的真实 ETF 动态等权。
- 完整自动测试与本地浏览器检查均通过后提交。
