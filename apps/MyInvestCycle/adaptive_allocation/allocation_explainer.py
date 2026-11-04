from __future__ import annotations

from typing import Mapping


def explain_allocation_intent(snapshot: Mapping[str, object]) -> list[str]:
    intent = snapshot.get("allocation_intent") if isinstance(snapshot.get("allocation_intent"), Mapping) else {}
    evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), Mapping) else {}
    macro = evidence.get("macro") if isinstance(evidence.get("macro"), Mapping) else {}
    structure = evidence.get("market_structure") if isinstance(evidence.get("market_structure"), Mapping) else {}
    industry = evidence.get("industry_opportunity") if isinstance(evidence.get("industry_opportunity"), Mapping) else {}
    theme_risk = evidence.get("theme_risk") if isinstance(evidence.get("theme_risk"), Mapping) else {}
    return [
        f"宏观层为 {macro.get('state')}，市场结构为 {structure.get('state')}，结构状态为 {snapshot.get('structural_state')}，配置细分为 {snapshot.get('allocation_structural_state') or snapshot.get('structural_state')}。",
        f"行业机会分 {float(industry.get('score') or 0.0):.1f}，主线持续性 {float(industry.get('theme_persistence') or 0.0):.1f}。",
        f"主题风险为 {theme_risk.get('risk_level')}，质量分 {float(theme_risk.get('quality_score') or 0.0):.1f}，拥挤分 {float(theme_risk.get('crowding_score') or 0.0):.1f}。",
        f"因此只生成配置意图：风险预算 {intent.get('risk_budget')}，权益暴露区间 {intent.get('equity_exposure_range')}。",
        "V2.4.1 不输出 ETF 代码、不输出具体执行仓位、不输出买卖或下单指令。",
    ]
