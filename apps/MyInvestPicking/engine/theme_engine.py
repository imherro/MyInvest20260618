from __future__ import annotations

from collections import defaultdict

import pandas as pd


CORE_GROWTH_THEME_SCORES = {
    "AI算力": 0.98,
    "芯片半导体": 0.96,
    "机器人": 0.94,
    "高端制造": 0.86,
    "新能源智能车": 0.82,
    "创新药医疗": 0.78,
}

THEME_KEYWORDS = {
    "AI算力": (
        "人工智能",
        "AI",
        "AIGC",
        "大模型",
        "算力",
        "服务器",
        "数据中心",
        "CPO",
        "光模块",
        "云计算",
        "边缘计算",
        "ChatGPT",
        "GPU",
        "PCB",
    ),
    "芯片半导体": (
        "半导体",
        "芯片",
        "集成电路",
        "先进封装",
        "封测",
        "光刻",
        "光刻机",
        "光刻胶",
        "存储",
        "EDA",
        "MCU",
        "第三代半导体",
        "元器件",
        "电子",
    ),
    "机器人": (
        "机器人",
        "人形机器人",
        "工业机器人",
        "机器视觉",
        "减速器",
        "伺服",
        "传感器",
        "自动化",
    ),
    "高端制造": (
        "高端制造",
        "专用机械",
        "通用机械",
        "工业母机",
        "数控",
        "半导体设备",
        "专用设备",
        "智能装备",
        "航空",
        "军工",
        "新材料",
    ),
    "新能源智能车": (
        "新能源",
        "电池",
        "锂电",
        "储能",
        "光伏",
        "智能车",
        "汽车电子",
        "无人驾驶",
        "自动驾驶",
    ),
    "创新药医疗": (
        "创新药",
        "生物制药",
        "医疗器械",
        "医疗保健",
        "CXO",
        "化学制药",
    ),
}

TUSHARE_THEME_MATCH_KEYWORDS = tuple(
    sorted({keyword for keywords in THEME_KEYWORDS.values() for keyword in keywords}, key=len, reverse=True)
)


def add_growth_theme_profiles(
    factors: pd.DataFrame,
    theme_membership: pd.DataFrame | None = None,
) -> pd.DataFrame:
    enriched = factors.copy()
    if enriched.empty:
        enriched["theme_tags"] = ""
        enriched["theme_source"] = "none"
        enriched["growth_theme_profile"] = 0.25
        return enriched

    external_theme_data = _external_theme_data(theme_membership, enriched)
    derived_tags = _derive_theme_tags(enriched)

    tags = []
    sources = []
    scores = []
    for idx in enriched.index:
        combined = []
        external_tags = external_theme_data.get(idx, {}).get("tags", [])
        external_source = str(external_theme_data.get(idx, {}).get("source") or "external")
        for tag in external_tags:
            if tag not in combined:
                combined.append(tag)
        for tag in derived_tags.get(idx, []):
            if tag not in combined:
                combined.append(tag)
        combined = _sort_theme_tags(combined)

        if external_tags and derived_tags.get(idx):
            source = f"{external_source}+derived"
        elif external_tags:
            source = external_source
        elif derived_tags.get(idx):
            source = "derived"
        else:
            source = "none"

        tags.append("|".join(combined))
        sources.append(source)
        scores.append(theme_score(combined, source))

    enriched["theme_tags"] = tags
    enriched["theme_source"] = sources
    enriched["growth_theme_profile"] = scores
    return enriched


def classify_theme_name(name: str | None) -> str | None:
    text = str(name or "")
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return theme
    return None


def theme_score(tags: list[str], source: str = "derived") -> float:
    if not tags:
        return 0.25
    score = max(CORE_GROWTH_THEME_SCORES.get(tag, 0.55) for tag in tags)
    if "tushare" in source:
        score += 0.02
    return min(round(score, 4), 1.0)


def _external_theme_data(
    theme_membership: pd.DataFrame | None,
    factors: pd.DataFrame,
) -> dict[object, dict[str, object]]:
    if theme_membership is None or theme_membership.empty:
        return {}
    if "ts_code" not in factors.columns:
        return {}
    if "ts_code" not in theme_membership.columns:
        return {}

    membership = theme_membership.copy()
    if "theme_group" not in membership.columns:
        name_column = "theme_name" if "theme_name" in membership.columns else "name"
        if name_column not in membership.columns:
            return {}
        membership["theme_group"] = membership[name_column].map(classify_theme_name)
    membership = membership.dropna(subset=["theme_group"])
    if membership.empty:
        return {}

    membership["theme_source"] = membership.get("theme_source", "external")
    result_by_code = {}
    for code, group in membership.groupby(membership["ts_code"].astype(str)):
        tags = _unique(group["theme_group"].astype(str).tolist())
        sources = _unique(group["theme_source"].astype(str).tolist())
        result_by_code[code] = {"tags": tags, "source": _source_label(sources)}

    result: dict[object, dict[str, object]] = {}
    for index_value, code in factors["ts_code"].astype(str).items():
        data_for_code = result_by_code.get(code)
        if data_for_code:
            result[index_value] = data_for_code
    return result


def _derive_theme_tags(factors: pd.DataFrame) -> dict[object, list[str]]:
    derived: dict[object, list[str]] = defaultdict(list)
    text_parts = []
    for _, row in factors.iterrows():
        text_parts.append(
            " ".join(
                str(row.get(column) or "")
                for column in ("name", "industry", "theme_tags")
                if column in factors.columns
            )
        )

    for idx, text in zip(factors.index, text_parts):
        for theme, keywords in THEME_KEYWORDS.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                derived[idx].append(theme)
    return {idx: _unique(tags) for idx, tags in derived.items()}


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _source_label(sources: list[str]) -> str:
    if any("tushare" in source for source in sources):
        return "tushare"
    if any(source == "mock" for source in sources):
        return "mock"
    return sources[0] if sources else "external"


def _sort_theme_tags(tags: list[str]) -> list[str]:
    return sorted(
        _unique(tags),
        key=lambda tag: (-CORE_GROWTH_THEME_SCORES.get(tag, 0.55), tag),
    )
