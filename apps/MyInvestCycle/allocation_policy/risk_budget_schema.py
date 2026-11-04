from __future__ import annotations

from dataclasses import asdict, dataclass


BUDGET_LEVELS: tuple[str, ...] = ("blocked", "low", "medium", "medium_high", "high")


@dataclass(frozen=True)
class StyleBudgetRule:
    style_id: str
    label: str
    role: str
    default_budget: str
    description: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


STYLE_BUDGET_RULES: tuple[StyleBudgetRule, ...] = (
    StyleBudgetRule(
        "growth",
        "成长/科技 Beta",
        "offensive",
        "medium",
        "代表成长、科技和高弹性主线暴露，只能在宏观与结构同时支持时提升预算。",
    ),
    StyleBudgetRule(
        "small_cap",
        "中小盘 Beta",
        "offensive",
        "medium",
        "代表中小市值扩散暴露，必须受市场宽度和流动性约束。",
    ),
    StyleBudgetRule(
        "value",
        "价值/大盘 Beta",
        "core",
        "medium",
        "代表核心宽基与大盘价值暴露，通常作为进攻和防守之间的过渡预算。",
    ),
    StyleBudgetRule(
        "dividend",
        "红利/低波 Beta",
        "defensive",
        "medium",
        "代表防守、波动缓冲和现金替代前的低波风险预算。",
    ),
)


STYLE_ROLES: dict[str, str] = {item.style_id: item.role for item in STYLE_BUDGET_RULES}
STYLE_LABELS: dict[str, str] = {item.style_id: item.label for item in STYLE_BUDGET_RULES}


def style_budget_universe_payload() -> list[dict[str, object]]:
    return [item.to_dict() for item in STYLE_BUDGET_RULES]


def budget_level_index(level: str) -> int:
    try:
        return BUDGET_LEVELS.index(level)
    except ValueError:
        return BUDGET_LEVELS.index("medium")


def budget_level_at(index: int) -> str:
    index = max(0, min(len(BUDGET_LEVELS) - 1, int(index)))
    return BUDGET_LEVELS[index]


def shift_budget_level(level: str, amount: int) -> str:
    return budget_level_at(budget_level_index(level) + int(amount))
