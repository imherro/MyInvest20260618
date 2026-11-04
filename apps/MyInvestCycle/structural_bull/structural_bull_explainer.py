from __future__ import annotations

from typing import Mapping


STATE_LABELS = {
    "STRUCTURAL_BULL_ROTATION": "结构性牛市主线轮动",
    "BROAD_BULL": "全面扩散牛市",
    "WEAK_MARKET": "弱势市场",
    "BEAR_REBOUND": "熊市反弹中的结构机会",
    "BEAR_STRUCTURE": "熊市结构",
    "RANGE": "震荡观察",
}


def _section(payload: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = payload.get(name)
    return value if isinstance(value, Mapping) else {}


def explain_structural_bull(state: str, payload: Mapping[str, object]) -> list[str]:
    macro = _section(payload, "macro")
    structure = _section(payload, "market_structure")
    industry = _section(payload, "industry_opportunity")
    top_themes = industry.get("top_themes") or []
    top_names = "、".join(str(item.get("name")) for item in top_themes[:3]) if isinstance(top_themes, list) else ""
    lines = [
        f"structural_state={state}: {STATE_LABELS.get(state, state)}。",
        f"宏观层为 {macro.get('state')}，宏观分 {float(macro.get('score') or 0.0):.1f}。",
        f"市场结构为 {structure.get('state')}，结构分 {float(structure.get('score') or 0.0):.1f}，宽度 {float(structure.get('breadth') or 0.0):.1f}。",
        f"行业机会分 {float(industry.get('score') or 0.0):.1f}，行业强度 {float(industry.get('industry_strength') or 0.0):.1f}，主线持续性 {float(industry.get('theme_persistence') or 0.0):.1f}。",
    ]
    if top_names:
        lines.append(f"当前主线候选：{top_names}。")
    if state == "STRUCTURAL_BULL_ROTATION":
        lines.append("判断含义：宏观不处于熊市，宽基不是破位结构，同时存在持续行业主线；这不是仓位或买入信号。")
    elif state == "BROAD_BULL":
        lines.append("判断含义：指数、宽度和行业机会同时扩散，更接近全面牛市。")
    elif state in {"WEAK_MARKET", "BEAR_STRUCTURE"}:
        lines.append("判断含义：宏观或市场结构偏弱，行业机会不足以抵消系统性压力。")
    else:
        lines.append("判断含义：证据不足以确认结构牛或全面牛，保持观察状态。")
    lines.append("V2.3.3 只输出状态与证据链，不输出仓位、ETF 配置、交易信号或回测结论。")
    return lines
