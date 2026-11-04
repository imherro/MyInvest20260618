# MyInvest20260618 Web Hub

## 统一源码仓库

13 个子系统源码已汇集到 `apps/`，清单见 `subsystems.json`。
已升级为统一应用：一个 `8888` 入口，13 个模块通过 `/market/`、`/theme/` 等子路径访问，不再各自监听端口。
原数据和 `.env` 留在原目录，模块通过明确的数据绑定继续使用；旧仓库保留用于历史和回退。
启动、测试、巡检和回退见 [统一应用说明](docs/migration/unified-application.md)。
迁移范围、来源提交、运行与测试方式见 [迁移说明](docs/migration/README.md)。

```powershell
python scripts/subsystems.py list
python scripts/test_subsystems.py --data-root C:\Users\kunpeng\Documents --timeout 1200
```

测试在 `temp/monorepo-tests/` 中的独立副本运行。`--data-root` 仅用于复制已登记的历史报告测试输入，不会在旧库中运行测试或写入数据。
日常修改和提交从本仓库统一进行；旧库保留历史和运行数据，不自动接收新代码。不要直接在挂接生产数据的 `apps/` 目录运行测试。

一个本地 Web 总览页，用于汇聚多个研究频道信息：

- 市场：`/api/market/index`
- 主线：`/api/theme/index`
- 影子：`/api/shadow/index`
- 龙头：`/api/leader/index`
- 个股：`/api/stock/index`
- 操作：`/api/position/index`

页面顶部的频道首页入口指向统一站点子路径，例如 `https://invest.okbbc.com/market/`。后台数据刷新通过本地统一入口读取对应的 `/api/<模块>/index`，不再绕行子系统公网域名。

数据接口有 10 分钟本地缓存。页面刚打开时立即显示频道入口；如果浏览器本地有上次数据，会先显示旧数据，再后台请求服务端缓存。点击全部刷新或单项刷新时会同时清除浏览器缓存和服务端缓存，再重新请求对应模块接口。

## 启动

```powershell
python server.py
```

默认监听：

```text
http://127.0.0.1:8888/
```

页面支持全部刷新和单项刷新。模块接口异常时，对应入口会显示错误状态，其他入口不受影响。

## 本地检查

```powershell
python -m unittest discover -s tests -q
```

## HTTP transport

The origin supports HTTP/1.1 connection reuse, negotiated gzip compression,
and ETag/304 validation for public static files (60-second freshness).
JSON APIs remain `no-store`; this does not change the 10-minute data cache.
Browser data requests stop after 25 seconds; shared navigation requests stop
after 10 seconds and retain the existing fallback or cached links.

For tunnel diagnostics, measure complete response transfer, not only HTTP 200.
Compare `/healthz`, `/`, and `/header.js` locally and on the public hostname.
Cloudflared readiness at `http://127.0.0.1:20241/ready` confirms edge connections,
not origin availability or client-to-edge performance.

2026-11-04: local homepage completed in about 22 ms. Public requests exhibited
intermittent connection timeouts and incomplete body transfer. Chrome also
recorded long connection/body delays despite sub-second Cloudflare origin timing.
Transport improvements are deployed, but public-network stability is not yet
confirmed. Do not treat a successful single request as full recovery.

Unified deployment acceptance: 29/29 local checks and 29/29 public checks via a
diagnostic real-edge DNS override passed. Normal fake-IP/proxy routing still
showed timeouts. Cloudflare chunked request handling and stale navigation asset
versions were fixed. See [acceptance record](docs/migration/unified-validation.json)
for test counts, evidence and the distinction between application and network health.

## Web 服务巡检

巡检默认管理统一主服务及其 13 个 IPC 模块，不再拉起旧的 13 个端口；逆向、测试仍按原来的独立服务配置检查。仅操作本次整合范围可加 `-Only home`。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ensure_web_services.ps1
```

只检查、不启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ensure_web_services.ps1 -NoStart
```

巡检日志写入 `temp/web_service_monitor/`。当前覆盖：首页、市场、主线、龙头、ETF、个股、影子、看盘、操作、周期、策略、逆向、短线、选股、十倍。

## 系统 API 入口

全系统 API 说明：

```text
https://invest.okbbc.com/api
```

`/api` 返回本系统接口、统一 Header/Footer 嵌入脚本，以及所有子系统的 `/api` 总入口。已接入首页聚合的频道还会额外给出对应的 `/api/index` 数据入口。

## 统一 Footer

数据 API：

```text
https://invest.okbbc.com/api/footer
```

子系统直接嵌入：

```html
<script src="https://invest.okbbc.com/footer.js" defer></script>
```

指定挂载位置：

```html
<div data-myinvest-footer></div>
<script src="https://invest.okbbc.com/footer.js" defer></script>
```

Footer 显示当前时间、上证指数实时点位、涨跌额、涨跌幅，以及首页、市场、主线、龙头、ETF、个股、影子、看盘、操作、周期、策略、逆向、短线、选股、十倍、测试链接。上证指数链接到 `https://xueqiu.com/S/SH000001` 并新窗口打开；导航链接仍在当前页打开。

## 统一 Header

数据 API：

```text
https://invest.okbbc.com/api/header
```

子系统直接嵌入：

```html
<script src="https://invest.okbbc.com/header.js" defer></script>
```

指定挂载位置：

```html
<div data-myinvest-header></div>
<script src="https://invest.okbbc.com/header.js" defer></script>
```

Header 显示 MyInvest 品牌，以及首页、市场、主线、龙头、ETF、个股、影子、看盘、操作、周期、策略、逆向、短线、选股、十倍、测试导航链接；所有导航链接在当前页打开。
