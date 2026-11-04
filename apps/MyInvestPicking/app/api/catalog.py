from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request

from config.settings import APP_NAME, APP_VERSION


router = APIRouter(tags=["api-catalog"])


DOCS = {
    "swagger": "/docs",
    "redoc": "/redoc",
    "openapi": "/openapi.json",
}

RECOMMENDED_ENTRYPOINTS = [
    {
        "path": "/api",
        "purpose": "查看统一接口目录和安全边界。",
    },
    {
        "path": "/api/picks?shadow_days=0",
        "purpose": "查看今日候选榜和满仓目标组合，不生成影子组合历史。",
    },
    {
        "path": "/api/shadow-portfolio?shadow_days=5",
        "purpose": "查看最近 5 个交易日的影子组合净值和调仓历史。",
    },
    {
        "path": "/docs",
        "purpose": "查看 FastAPI 自动生成的交互式接口文档。",
    },
]

SAFETY = {
    "catalog": "GET /api 只返回静态接口说明，不触发选股重算、回测、缓存刷新、快照写入、交易或同步。",
    "trading": "当前公开接口不连接券商账户，不下单，不撤单，不生成真实交易指令。",
    "positioning": "组合和仓位字段保持比例表达，不输出账户金额、股数或收益金额。",
    "runtime_writes": "分析接口可能刷新本地 Tushare 缓存或运行快照；/api 本身不会写入任何运行数据。",
    "secrets": "接口目录不暴露 .env、TUSHARE_TOKEN、缓存文件路径或本机绝对路径。",
}

GROUPS = [
    {
        "name": "文档入口",
        "description": "用于发现接口和查看 OpenAPI 文档。",
        "endpoints": [
            {
                "method": "GET",
                "path": "/",
                "purpose": "Web 首页，展示候选榜、满仓目标组合、调仓规则、影子组合净值和接口说明摘要。",
                "parameters": [],
                "returns": ["HTML workbench page"],
                "read_only": True,
            },
            {
                "method": "GET",
                "path": "/api",
                "purpose": "统一接口目录，返回所有公开接口、推荐入口和安全边界。",
                "parameters": [],
                "returns": [
                    "system",
                    "base_url",
                    "docs",
                    "recommended_entrypoints",
                    "safety",
                    "groups",
                    "total_endpoints",
                ],
                "read_only": True,
            },
            {
                "method": "GET",
                "path": "/docs",
                "purpose": "Swagger UI 交互式接口文档。",
                "parameters": [],
                "returns": ["HTML documentation UI"],
                "read_only": True,
            },
            {
                "method": "GET",
                "path": "/redoc",
                "purpose": "ReDoc 接口文档页面。",
                "parameters": [],
                "returns": ["HTML documentation UI"],
                "read_only": True,
            },
            {
                "method": "GET",
                "path": "/openapi.json",
                "purpose": "OpenAPI JSON schema。",
                "parameters": [],
                "returns": ["OpenAPI schema"],
                "read_only": True,
            },
        ],
    },
    {
        "name": "当前数据",
        "description": "面向首页当前工作台的数据入口。",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/picks",
                "purpose": "生成并返回当前交易日或指定日期的候选榜、满仓目标组合、调仓规则和组合结构。",
                "parameters": [
                    {
                        "name": "date",
                        "type": "string",
                        "required": False,
                        "default": None,
                        "description": "交易日，支持 YYYY-MM-DD 或 YYYYMMDD；为空时取最近交易日。",
                    },
                    {
                        "name": "top_n",
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "range": "1..100",
                        "description": "返回候选/组合数量上限。",
                    },
                    {
                        "name": "shadow_days",
                        "type": "integer",
                        "required": False,
                        "default": 10,
                        "range": "0..30",
                        "description": "内嵌影子组合回看天数；0 表示不生成影子历史。",
                    },
                ],
                "returns": [
                    "trading_date",
                    "source",
                    "mock_mode",
                    "candidate_pools",
                    "data",
                    "portfolio",
                    "signals",
                    "gate_summary",
                    "risk",
                    "portfolio_mode",
                    "backtest",
                    "shadow_portfolio",
                ],
                "read_only": False,
                "safety_note": "不交易、不同步；可能读取 Tushare 并写入本地缓存/快照。",
            },
        ],
    },
    {
        "name": "历史数据",
        "description": "用于查看影子组合净值曲线和调仓历史。",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/shadow-portfolio",
                "purpose": "返回影子组合净值曲线、每日调仓历史和模拟指标。",
                "parameters": [
                    {
                        "name": "date",
                        "type": "string",
                        "required": False,
                        "default": None,
                        "description": "交易日，支持 YYYY-MM-DD 或 YYYYMMDD；为空时取最近交易日。",
                    },
                    {
                        "name": "top_n",
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "range": "1..100",
                        "description": "每日影子组合选取数量。",
                    },
                    {
                        "name": "shadow_days",
                        "type": "integer",
                        "required": False,
                        "default": 5,
                        "range": "1..30",
                        "description": "影子组合回看交易日数量。",
                    },
                ],
                "returns": [
                    "trading_date",
                    "source",
                    "mock_mode",
                    "shadow_portfolio.summary",
                    "shadow_portfolio.equity_curve",
                    "shadow_portfolio.rebalance_history",
                    "shadow_portfolio.metrics",
                ],
                "read_only": False,
                "safety_note": "不交易、不同步；可能读取 Tushare 并写入本地缓存。",
            },
        ],
    },
    {
        "name": "分析结果",
        "description": "用于读取模型打分、满仓目标组合、调仓规则和影子组合模拟结果。",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/picks",
                "purpose": "返回候选榜、满仓目标组合、调仓规则、回测指标、相关性风险和组合稳定性。",
                "parameters": [
                    {
                        "name": "date",
                        "type": "string",
                        "required": False,
                        "default": None,
                        "description": "交易日，支持 YYYY-MM-DD 或 YYYYMMDD；为空时取最近交易日。",
                    },
                    {
                        "name": "top_n",
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "range": "1..100",
                        "description": "返回候选/组合数量上限。",
                    },
                    {
                        "name": "shadow_days",
                        "type": "integer",
                        "required": False,
                        "default": 10,
                        "range": "0..30",
                        "description": "内嵌影子组合回看天数；0 表示不生成影子历史。",
                    },
                ],
                "returns": [
                    "candidate_pools",
                    "signals",
                    "signal_summary",
                    "gate_summary",
                    "correlation_risk",
                    "factor_health",
                    "portfolio_stability",
                    "backtest",
                ],
                "read_only": False,
                "safety_note": "不交易、不同步；可能读取 Tushare 并写入本地缓存/快照。",
            },
            {
                "method": "GET",
                "path": "/api/shadow-portfolio",
                "purpose": "返回影子组合净值曲线、回撤、换手和逐日调仓记录。",
                "parameters": [
                    {
                        "name": "date",
                        "type": "string",
                        "required": False,
                        "default": None,
                        "description": "交易日，支持 YYYY-MM-DD 或 YYYYMMDD；为空时取最近交易日。",
                    },
                    {
                        "name": "top_n",
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "range": "1..100",
                        "description": "每日影子组合选取数量。",
                    },
                    {
                        "name": "shadow_days",
                        "type": "integer",
                        "required": False,
                        "default": 5,
                        "range": "1..30",
                        "description": "影子组合回看交易日数量。",
                    },
                ],
                "returns": [
                    "shadow_portfolio.summary",
                    "shadow_portfolio.equity_curve",
                    "shadow_portfolio.rebalance_history",
                    "shadow_portfolio.metrics",
                ],
                "read_only": False,
                "safety_note": "不交易、不同步；可能读取 Tushare 并写入本地缓存。",
            },
        ],
    },
    {
        "name": "系统状态",
        "description": "当前没有单独健康检查路由；接口目录暴露系统版本和只读边界。",
        "endpoints": [
            {
                "method": "GET",
                "path": "/api",
                "purpose": "读取系统名称、版本、说明、推荐入口、接口总数和安全边界。",
                "parameters": [],
                "returns": ["system", "safety", "total_endpoints"],
                "read_only": True,
            }
        ],
    },
]


@router.get("/api")
def get_api_catalog(request: Request) -> dict[str, Any]:
    groups = deepcopy(GROUPS)
    unique_endpoints = {
        (endpoint["method"], endpoint["path"])
        for group in groups
        for endpoint in group["endpoints"]
    }
    return {
        "system": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "description": "A 股满仓股票影子组合工作台，提供候选榜、目标组合、调仓记录和净值查看接口。",
        },
        "base_url": str(request.base_url).rstrip("/"),
        "docs": DOCS,
        "recommended_entrypoints": RECOMMENDED_ENTRYPOINTS,
        "safety": SAFETY,
        "groups": groups,
        "total_endpoints": len(unique_endpoints),
    }
