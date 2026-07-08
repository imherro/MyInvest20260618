# MyInvest20260618 Web Hub

一个本地 Web 总览页，用于汇聚多个研究频道信息：

- 市场：`https://market.okbbc.com/api/index`
- 主线：`https://theme.okbbc.com/api/index`
- 影子：`https://shadow.okbbc.com/api/index`
- 龙头：`https://leader.okbbc.com/api/index`
- 个股：`https://stock.okbbc.com/api/index`
- 操作：`https://position.okbbc.com/api/index`

页面顶部的频道首页入口指向频道根地址，例如 `https://market.okbbc.com/`。后台数据刷新仍然使用对应的 `/api/index` 接口。

数据接口有 10 分钟本地缓存。页面刚打开时会立即显示四个频道入口；如果浏览器本地有上次数据，会先显示旧数据，再后台请求服务端缓存。点击全部刷新或单项刷新时会同时清除浏览器缓存和服务端缓存，再重新请求远程接口。

## 启动

```powershell
python server.py
```

默认监听：

```text
http://127.0.0.1:8888/
```

页面支持全部刷新和单项刷新。远程接口异常时，对应入口会显示错误状态，其他入口不受影响。

## 本地检查

```powershell
python -m unittest discover -s tests -q
```

## Web 服务巡检

本项目提供巡检脚本，会检查首页和子系统本地 Web 服务；如果端口没有响应，会按已知启动命令拉起服务。

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
