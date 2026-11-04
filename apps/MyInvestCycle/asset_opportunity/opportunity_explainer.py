from __future__ import annotations

from typing import Mapping


def _pct(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number * 100:.2f}%"


def explain_asset_opportunity(row: Mapping[str, object]) -> list[str]:
    components = row.get("components") if isinstance(row.get("components"), Mapping) else {}
    metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
    penalty = row.get("penalty") if isinstance(row.get("penalty"), Mapping) else {}
    score = row.get("score")
    return [
        f"机会分 {score}，由动量、相对强度、趋势质量、风险调整和持续性组合得到。",
        f"20日收益 {_pct(metrics.get('return_20d'))}，60日收益 {_pct(metrics.get('return_60d'))}，相对沪深300 {_pct(metrics.get('relative_60d'))}。",
        (
            "组件分："
            f"动量 {components.get('momentum')}，"
            f"相对强度 {components.get('relative_strength')}，"
            f"趋势 {components.get('trend_quality')}，"
            f"风险调整 {components.get('risk_adjusted')}，"
            f"持续性 {components.get('persistence')}。"
        ),
        (
            "惩罚项："
            f"涨幅/位置过热 {penalty.get('extension')}，"
            f"主题拥挤 {penalty.get('crowding')}；"
            "本层只排序，不输出仓位或交易。"
        ),
    ]
