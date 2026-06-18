# MyInvest20260618 Web Hub

一个本地 Web 总览页，用于汇聚四类主要信息：

- 市场：`https://market.okbbc.com/api/index`
- 主线：`https://theme.okbbc.com/api/index`
- 影子：`https://shadow.okbbc.com/api/index`
- 操作：`https://position.okbbc.com/api/index`

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

