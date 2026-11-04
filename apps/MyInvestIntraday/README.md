# MyInvestIntraday

`MyInvestIntraday` 是 `MyInvest20260618` 的盘中只读看盘子系统。第一版聚合现有 MyInvest 子系统接口，显示盘中状态、市场基准、主线/龙头/影子/操作/个股信号和本地数据源健康。

## 边界

- 默认端口：`8022`
- 页面形态：全屏工作台
- 接口模式：只读
- 交易能力：禁用
- 本地 key：只检查是否配置，不在 API 或页面输出明文
- QMT：第一版只做本地目录探测，后续接入盘中价格和真实持仓只读导入

## 启动

```powershell
python server.py
```

打开：

```text
http://127.0.0.1:8022/
```

指定端口：

```powershell
python server.py --port 8022
```

## API

```text
GET /api
GET /api/index
GET /api/index?refresh=1
GET /api/config
GET /api/sources/health
```

`/api/index` 会读取以下子系统的 `/api/index`：

- 市场：`https://market.okbbc.com/api/index`
- 主线：`https://theme.okbbc.com/api/index`
- 龙头：`https://leader.okbbc.com/api/index`
- 影子：`https://shadow.okbbc.com/api/index`
- 操作：`https://position.okbbc.com/api/index`
- 个股：`https://stock.okbbc.com/api/index`

## 本地数据源

本地 `.env` 可参考 `.env.example`：

```text
TUSHARE_TOKEN=
FRED_API_KEY=
```

`.env` 不进入版本控制。

## 检查

```powershell
python -m unittest discover -s tests -q
```
