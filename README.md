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

Footer 显示当前时间、上证指数实时点位、涨跌额、涨跌幅，以及首页、ETF、选股和各子频道链接。上证指数链接到 `https://xueqiu.com/S/SH000001` 并新窗口打开；首页、ETF、选股和子频道链接仍在当前页打开。

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

Header 显示 MyInvest 品牌，以及首页、市场、主线、影子、龙头、ETF、选股、个股、操作导航链接；所有导航链接在当前页打开。
