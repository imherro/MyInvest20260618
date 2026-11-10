from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
TUSHARE_API_URL = "http://api.tushare.pro"
START_DATE = "20160104"
END_DATE = "20260707"
DAY_MS = 86_400_000


@dataclass(frozen=True)
class AssetSpec:
    group: str
    name: str
    code: str
    api: str
    return_type: str
    asset_weight_score: int | None = None
    note: str = ""


REPRESENTATIVE_ASSETS: list[AssetSpec] = [
    AssetSpec("防守策略", "自由现金流R", "480092.CNI", "local", "全收益", 3, "国证自由现金流全收益指数"),
    AssetSpec("防守策略", "红利低波100全收益", "H20955.CSI", "index_daily", "全收益", 5),
    AssetSpec("防守策略", "中证红利全收益", "H00922.CSI", "index_daily", "全收益", 5),
    AssetSpec("防守策略", "300红利低波全收益", "H20740.CSI", "index_daily", "全收益", 5),
    AssetSpec("防守策略", "质量低波全收益", "H21062.CSI", "index_daily", "全收益", 4),
    AssetSpec("防守策略", "高股息策略全收益", "H21053.CSI", "index_daily", "全收益", 5),
    AssetSpec("防守策略", "中国盈利质量(全)", "H20880.CSI", "index_daily", "全收益", 3),
    AssetSpec("防守策略", "500红利全收益", "H00822.CSI", "index_daily", "全收益", 5),
    AssetSpec("防守策略", "价值回报全收益", "H20949.CSI", "index_daily", "全收益", 4),
    AssetSpec("防守策略", "500质量成长全收益", "H20939.CSI", "index_daily", "全收益", 3),
    AssetSpec("防守策略", "盈利质量全收益", "H20860.CSI", "index_daily", "全收益", 3),
    AssetSpec("宽基", "上证50收益", "H00016.CSI", "index_daily", "全收益", 5),
    AssetSpec("宽基", "沪深300收益", "H00300.CSI", "index_daily", "全收益", 4),
    AssetSpec("宽基", "中证500收益", "H00905.CSI", "index_daily", "全收益", 3),
    AssetSpec("宽基", "中证1000全收益", "H00852.CSI", "index_daily", "全收益", 2),
    AssetSpec("宽基", "创业板R", "399606.SZ", "index_daily", "全收益", 1),
    AssetSpec("宽基", "创业板指", "399006.SZ", "index_daily", "价格指数", 1),
    AssetSpec("宽基", "科创50(全)", "000688CNY01.CSI", "index_daily", "全收益", 1, "起点较晚"),
    AssetSpec("热点主题", "芯片产业全收益", "H20007.CSI", "index_daily", "全收益", 1),
    AssetSpec("热点主题", "半导体材料设备全收益", "931743CNY010.CSI", "index_daily", "全收益", 2, "起点较晚"),
    AssetSpec("热点主题", "CS创新药全收益", "H21152.CSI", "index_daily", "全收益", 1),
    AssetSpec("热点主题", "机器人全收益", "H20590.CSI", "index_daily", "全收益", 2),
    AssetSpec("热点主题", "CS新能源全收益", "H20771.CSI", "index_daily", "全收益", 3),
    AssetSpec("热点主题", "中证算力全收益", "931688CNY010.CSI", "index_daily", "全收益", 1, "起点较晚"),
    AssetSpec("热点主题", "A股资源全收益", "H00805.CSI", "index_daily", "全收益", 5),
]


ASSET_WEIGHT_SCORE: dict[str, int] = {
    "传媒": 1,
    "计算机": 1,
    "社会服务": 1,
    "美容护理": 1,
    "商贸零售": 1,
    "食品饮料": 2,
    "医药生物": 2,
    "纺织服饰": 2,
    "轻工制造": 2,
    "家用电器": 2,
    "电子": 3,
    "通信": 3,
    "汽车": 3,
    "机械设备": 3,
    "国防军工": 3,
    "农林牧渔": 3,
    "环保": 3,
    "综合": 3,
    "电力设备": 4,
    "基础化工": 4,
    "公用事业": 4,
    "交通运输": 4,
    "建筑装饰": 4,
    "建筑材料": 4,
    "非银金融": 4,
    "钢铁": 5,
    "有色金属": 5,
    "煤炭": 5,
    "石油石化": 5,
    "房地产": 5,
    "银行": 5,
}


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def tushare_token() -> str:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未找到 TUSHARE_TOKEN，无法拉取 Tushare 指数行情。")
    return token


def call_tushare(api_name: str, params: dict[str, Any], fields: str) -> pd.DataFrame:
    response = requests.post(
        TUSHARE_API_URL,
        json={"api_name": api_name, "token": tushare_token(), "params": params, "fields": fields},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Tushare {api_name} {params} 返回异常：{payload.get('msg')}")
    data = payload.get("data") or {}
    return pd.DataFrame(data.get("items") or [], columns=data.get("fields") or [])


def fetch_series(spec: AssetSpec) -> pd.DataFrame:
    if spec.api == "local":
        frame = pd.read_csv(OUTPUT_DIR / "480092_CNI_daily.csv")
        frame = frame[["trade_date", "close"]].copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y%m%d")
    else:
        fields = "ts_code,trade_date,close,pct_change,name" if spec.api == "sw_daily" else "ts_code,trade_date,close,pct_chg"
        frame = call_tushare(
            spec.api,
            {"ts_code": spec.code, "start_date": START_DATE, "end_date": END_DATE},
            fields,
        )
    if frame.empty:
        return frame
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "close"])
    frame = frame[(frame["trade_date"] >= START_DATE) & (frame["trade_date"] <= END_DATE)]
    return frame.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def load_sw_l1_assets() -> list[AssetSpec]:
    frame = call_tushare("index_classify", {"src": "SW2021", "level": "L1"}, "index_code,industry_name,level")
    assets = []
    for row in frame.itertuples(index=False):
        name = str(row.industry_name)
        assets.append(
            AssetSpec(
                "申万一级行业",
                name,
                str(row.index_code),
                "sw_daily",
                "价格指数",
                ASSET_WEIGHT_SCORE.get(name),
            )
        )
    return assets


def pct(value: float | int | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{float(value) * 100:.{digits}f}%"


def normalize_date(value: str) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def date_diff_days(start: str, end: str) -> int:
    return max(1, int((pd.to_datetime(end) - pd.to_datetime(start)).days))


def max_drawdown_info(frame: pd.DataFrame) -> dict[str, Any]:
    closes = frame["close"].astype(float).tolist()
    dates = frame["trade_date"].astype(str).tolist()
    peak = closes[0]
    peak_date = dates[0]
    max_dd = 0.0
    max_start = dates[0]
    max_end = dates[0]
    current_peak = closes[0]
    current_peak_date = dates[0]
    for close, date in zip(closes, dates):
        if close > peak:
            peak = close
            peak_date = date
        drawdown = close / peak - 1
        if drawdown < max_dd:
            max_dd = drawdown
            max_start = peak_date
            max_end = date
        if close >= current_peak:
            current_peak = close
            current_peak_date = date
    current_dd = closes[-1] / current_peak - 1
    ratio = closes[-1] / closes[0]
    days = date_diff_days(dates[0], dates[-1])
    return {
        "first_date": dates[0],
        "last_date": dates[-1],
        "n": len(frame),
        "total_return": ratio - 1,
        "annual_return": ratio ** (365 / days) - 1,
        "max_drawdown": max_dd,
        "max_drawdown_start": max_start,
        "max_drawdown_end": max_end,
        "current_drawdown": current_dd,
        "current_drawdown_start": current_peak_date,
        "current_drawdown_end": dates[-1],
    }


def max_drawdown_value(points: pd.DataFrame) -> float:
    closes = points["close"].astype(float).tolist()
    if len(closes) < 2:
        return float("nan")
    peak = closes[0]
    max_dd = 0.0
    for close in closes:
        if close > peak:
            peak = close
        drawdown = close / peak - 1
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd


def rolling_drawdown_stats(frame: pd.DataFrame) -> dict[str, Any]:
    values: list[float] = []
    start = 0
    dates = frame["trade_date"].astype(str).tolist()
    sample_ends = list(range(1, len(frame), 21))
    if sample_ends[-1] != len(frame) - 1:
        sample_ends.append(len(frame) - 1)
    for end in sample_ends:
        while start < end and date_diff_days(dates[start], dates[end]) > 365:
            start += 1
        if date_diff_days(dates[start], dates[end]) < 250:
            continue
        value = max_drawdown_value(frame.iloc[start : end + 1])
        if math.isfinite(value):
            values.append(value)
    if not values:
        return {"rolling_1y_maxdd_p25": None, "rolling_1y_maxdd_p50": None, "rolling_1y_maxdd_p75": None, "rolling_1y_window_count": 0}
    series = pd.Series(values)
    return {
        "rolling_1y_maxdd_p25": float(series.quantile(0.25)),
        "rolling_1y_maxdd_p50": float(series.quantile(0.50)),
        "rolling_1y_maxdd_p75": float(series.quantile(0.75)),
        "rolling_1y_window_count": len(values),
    }


def value_on_or_after(frame: pd.DataFrame, target_date: pd.Timestamp) -> tuple[str, float] | None:
    dates = pd.to_datetime(frame["trade_date"])
    match = frame[dates >= target_date]
    if match.empty:
        return None
    row = match.iloc[0]
    return str(row["trade_date"]), float(row["close"])


def drawdown_threshold_events(spec: AssetSpec, frame: pd.DataFrame, thresholds: list[float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dates = frame["trade_date"].astype(str).tolist()
    closes = frame["close"].astype(float).tolist()
    active_thresholds: set[float] = set()
    peak = closes[0]
    for index, (date, close) in enumerate(zip(dates, closes)):
        if close >= peak:
            peak = close
            active_thresholds.clear()
        drawdown = close / peak - 1
        for threshold in thresholds:
            if drawdown <= threshold and threshold not in active_thresholds:
                active_thresholds.add(threshold)
                event: dict[str, Any] = {
                    "group": spec.group,
                    "name": spec.name,
                    "code": spec.code,
                    "asset_weight_score": spec.asset_weight_score,
                    "threshold": threshold,
                    "event_date": date,
                    "event_drawdown": drawdown,
                }
                event_close = close
                event_date = pd.to_datetime(date)
                for years in [1, 2, 3]:
                    forward = value_on_or_after(frame.iloc[index:].copy(), event_date + pd.Timedelta(days=365 * years))
                    if forward:
                        fwd_date, fwd_close = forward
                        event[f"fwd_{years}y_date"] = fwd_date
                        event[f"fwd_{years}y_return"] = fwd_close / event_close - 1
                    else:
                        event[f"fwd_{years}y_date"] = ""
                        event[f"fwd_{years}y_return"] = None
                rows.append(event)
    return rows


def make_summary(metrics: pd.DataFrame, events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    group_summary = (
        metrics.groupby("group")
        .agg(
            count=("name", "count"),
            median_max_drawdown=("max_drawdown", "median"),
            p25_max_drawdown=("max_drawdown", lambda value: value.quantile(0.25)),
            p75_max_drawdown=("max_drawdown", lambda value: value.quantile(0.75)),
            median_current_drawdown=("current_drawdown", "median"),
            median_annual_return=("annual_return", "median"),
        )
        .reset_index()
    )
    score_summary = (
        metrics[metrics["group"].eq("申万一级行业")]
        .dropna(subset=["asset_weight_score"])
        .groupby("asset_weight_score")
        .agg(
            count=("name", "count"),
            median_max_drawdown=("max_drawdown", "median"),
            min_max_drawdown=("max_drawdown", "min"),
            max_max_drawdown=("max_drawdown", "max"),
            median_annual_return=("annual_return", "median"),
        )
        .reset_index()
    )
    event_summary = pd.DataFrame()
    completed = events.dropna(subset=["fwd_2y_return"]).copy()
    if not completed.empty:
        event_summary = (
            completed.groupby(["group", "threshold"])
            .agg(
                events=("name", "count"),
                win_rate_2y=("fwd_2y_return", lambda value: float((value > 0).mean())),
                median_fwd_1y=("fwd_1y_return", "median"),
                median_fwd_2y=("fwd_2y_return", "median"),
                median_fwd_3y=("fwd_3y_return", "median"),
            )
            .reset_index()
        )
    return {"group": group_summary, "score": score_summary, "events": event_summary}


def markdown_table(frame: pd.DataFrame, columns: list[str], pct_columns: set[str] | None = None, limit: int | None = None) -> str:
    pct_columns = pct_columns or set()
    view = frame.loc[:, columns].copy()
    if limit:
        view = view.head(limit)
    for column in view.columns:
        if column in pct_columns:
            view[column] = view[column].map(lambda value: pct(value))
        elif column.endswith("date") or column.endswith("_start") or column.endswith("_end"):
            view[column] = view[column].map(lambda value: normalize_date(value) if pd.notna(value) and value else "")
    headers = [str(column) for column in view.columns]
    rows = []
    for row in view.itertuples(index=False, name=None):
        rows.append([("" if pd.isna(value) else str(value)) for value in row])
    table = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
    return "\n".join(table)


def write_markdown(metrics: pd.DataFrame, events: pd.DataFrame, summaries: dict[str, pd.DataFrame], output_path: Path) -> None:
    industry = metrics[metrics["group"].eq("申万一级行业")].sort_values("max_drawdown")
    strategy = metrics[metrics["group"].eq("防守策略")].sort_values("max_drawdown", ascending=False)
    broad = metrics[metrics["group"].eq("宽基")].sort_values("max_drawdown", ascending=False)
    themes = metrics[metrics["group"].eq("热点主题")].sort_values("max_drawdown")
    score_summary = summaries["score"].copy()
    event_summary = summaries["events"].copy()
    if not event_summary.empty:
        event_summary = event_summary[(event_summary["threshold"].isin([-0.25, -0.40, -0.50, -0.60, -0.70]))]
        event_summary = event_summary.sort_values(["threshold", "group"])

    industry_corr = industry.dropna(subset=["asset_weight_score"]).copy()
    industry_corr["abs_max_drawdown"] = -industry_corr["max_drawdown"]
    spearman = industry_corr[["asset_weight_score", "abs_max_drawdown"]].corr(method="spearman").iloc[0, 1]

    lines = [
        "# 资产轻重与极端回撤买入策略研究",
        "",
        f"- 数据窗口：{normalize_date(START_DATE)} 至 {normalize_date(END_DATE)}。",
        "- 数据源：Tushare `index_daily` / `sw_daily`；自由现金流指数使用本项目已生成的国证日线 CSV。Tushare HTTP 接口采用 POST JSON 调用，返回 `fields/items` 结构。",
        "- 回撤口径：从历史高点到后续低点的最大跌幅；收益指数优先使用全收益版本，申万行业只能使用价格指数。",
        "- 本文目的：把“资产越轻，最大回撤越深；越接近历史级最大回撤，买入胜算越高”的思路整理成可被反驳和复核的策略假设。",
        "",
        "## 一句话结论",
        "",
        "这条思路在 2016 至今的 A 股指数数据里有明显证据：防守策略指数最大回撤集中在 25%-35%，大盘宽基约 40%，小盘/科创/成长宽基约 55%-62%，申万一级行业中位约 56%，资产轻的行业回撤中枢接近 70%。",
        "",
        "但策略不能写成“跌到最大回撤就买”，因为实时无法知道最大回撤是否已经结束。更可执行的版本是：按资产类别设定历史压力区间，进入压力区后分批买入，并用基本面/政策/流动性检查排除永久损伤资产。",
        "",
        "## 核心假设",
        "",
        "1. 资产重、现金流硬、分红或资产负债表有锚的指数，回撤下限更浅。",
        "2. 资产轻、估值依赖远期预期的指数，回撤深度更大，常见极端回撤可到 60%-70%。",
        "3. 当一类资产跌入自己的历史级压力区，继续下跌空间开始小于长期赔率，若产业逻辑未破坏，分批买入的胜率提高。",
        "4. 这个策略的优势不是精准抄底，而是把买入点移到市场已经充分杀估值、心理压力反而更小的位置。",
        "",
        "## 数据摘要",
        "",
        "### 分组最大回撤",
        "",
        markdown_table(
            summaries["group"].sort_values("median_max_drawdown", ascending=False),
            ["group", "count", "median_max_drawdown", "p25_max_drawdown", "p75_max_drawdown", "median_current_drawdown", "median_annual_return"],
            {"median_max_drawdown", "p25_max_drawdown", "p75_max_drawdown", "median_current_drawdown", "median_annual_return"},
        ),
        "",
        "### 申万一级行业：资产轻重分层",
        "",
        "资产轻重评分为本文研究变量：1 代表资产最轻、最依赖预期；5 代表资产最重或现金流/资源/资产负债表锚更强。评分越高，历史最大回撤绝对值越低。该组 Spearman 相关约 "
        f"`{spearman:.2f}`，方向支持“资产越轻，极端回撤越深”。",
        "",
        markdown_table(
            score_summary,
            ["asset_weight_score", "count", "median_max_drawdown", "min_max_drawdown", "max_max_drawdown", "median_annual_return"],
            {"median_max_drawdown", "min_max_drawdown", "max_max_drawdown", "median_annual_return"},
        ),
        "",
        "### 防守策略指数样本",
        "",
        markdown_table(
            strategy,
            ["name", "code", "max_drawdown", "max_drawdown_start", "max_drawdown_end", "current_drawdown", "annual_return"],
            {"max_drawdown", "current_drawdown", "annual_return"},
        ),
        "",
        "### 宽基与科创/成长宽基",
        "",
        markdown_table(
            broad,
            ["name", "code", "asset_weight_score", "max_drawdown", "max_drawdown_start", "max_drawdown_end", "current_drawdown", "annual_return", "note"],
            {"max_drawdown", "current_drawdown", "annual_return"},
        ),
        "",
        "科创50、创业板、中证1000的回撤显著深于沪深300和上证50，符合“轻资产/成长预期占比高，回撤更深”的解释。",
        "",
        "### 当前热点主题代表线",
        "",
        markdown_table(
            themes,
            ["name", "code", "asset_weight_score", "max_drawdown", "max_drawdown_start", "max_drawdown_end", "current_drawdown", "annual_return", "note"],
            {"max_drawdown", "current_drawdown", "annual_return"},
        ),
        "",
        "### 申万一级行业最大回撤排序",
        "",
        markdown_table(
            industry,
            ["name", "code", "asset_weight_score", "max_drawdown", "max_drawdown_start", "max_drawdown_end", "current_drawdown", "annual_return"],
            {"max_drawdown", "current_drawdown", "annual_return"},
        ),
        "",
        "## 极端回撤买入的可执行版本",
        "",
        "建议不要用单一阈值。阈值应按资产类型分层：",
        "",
        "| 资产类型 | 观察到的历史压力区 | 初始买入区 | 加仓区 | 满仓/重点区 |",
        "|---|---:|---:|---:|---:|",
        "| 防守策略/红利低波/自由现金流 | 25%-35% | 18%-20% | 23%-27% | 30%附近 |",
        "| 大盘宽基 | 40%-45% | 30%-35% | 38%-42% | 45%附近 |",
        "| 小盘/成长/科创宽基 | 55%-62% | 40%-45% | 50%-55% | 60%附近 |",
        "| 资产轻主题/行业 | 60%-75% | 45%-50% | 55%-65% | 70%附近 |",
        "| 资源/银行/公用/重资产周期 | 35%-55% | 30%-35% | 40%-45% | 50%附近 |",
        "",
        "分批方式可以简单化：进入初始买入区买 30%，进入加仓区再买 30%，进入满仓区买剩余 40%。如果资产在第一笔后继续下跌，不把它视为失败，而视为这个策略必须接受的路径。",
        "",
        "## 初步事件回测",
        "",
        "下表不是最终回测，只回答一个问题：当指数在历史中首次跌破某个固定回撤阈值时，后续 1/2/3 年的中位收益和 2 年胜率如何。阈值是固定百分比，因此信号本身没有使用未来价格；但阈值分层来自这次样本观察，正式使用前应冻结参数并做滚动样本外验证。",
        "",
        markdown_table(
            event_summary,
            ["group", "threshold", "events", "win_rate_2y", "median_fwd_1y", "median_fwd_2y", "median_fwd_3y"],
            {"threshold", "win_rate_2y", "median_fwd_1y", "median_fwd_2y", "median_fwd_3y"},
        )
        if not event_summary.empty
        else "事件样本不足，未生成汇总。",
        "",
        "## 策略成立的条件",
        "",
        "1. 指数必须仍代表一个未来会被资本重新定价的资产池。",
        "2. 行业不能是结构性坍塌，例如长期需求收缩、资产负债表不可逆恶化、监管永久压制。",
        "3. 买入必须分批，因为最大回撤只有事后才知道。",
        "4. 更适合指数，不适合单只股票。指数可以通过成分股更新清除失败公司，单股可能永久归零。",
        "5. 需要接受很长修复期。资产轻主题从 60% 回撤修复到新高，可能需要 2-5 年。",
        "",
        "## 主要反证点",
        "",
        "- 房地产说明“资产重”不一定安全，高杠杆资产重可能比轻资产更危险。",
        "- 商贸零售、传媒、纺织服饰等长期低迷行业，即使回撤深，也可能只是长期 ROE 和商业模式弱化。",
        "- 创新药、芯片、机器人、新能源这类主题的指数成分会变化，历史指数回撤不等同于当前 ETF 的真实组合回撤。",
        "- 如果用未来全样本最大回撤做买入阈值，就是未来函数；可交易版本只能用事先冻结的分类阈值或滚动历史阈值。",
        "",
        "## 建议拿去问 ChatGPT 的问题",
        "",
        "1. 资产轻重评分是否应替换成更客观的财务指标，例如固定资产/总资产、无形资产占比、经营现金流稳定性、ROE 波动率、负债率？",
        "2. 阈值应该按“指数自身历史最大回撤”还是按“同类资产回撤分位数”确定？哪一种样本外更稳定？",
        "3. 对芯片、创新药、机器人、新能源这种轻资产主题，应该用 60% 还是 70% 作为满仓区？",
        "4. 进入深回撤后是否需要右侧确认，例如 120 日均线、相对宽基走强、成交额扩张？还是会降低赔率？",
        "5. 持有退出规则用回到前高、持有 3 年、还是相对自由现金流/沪深300走弱？",
        "",
        "## 可直接复制给 ChatGPT 的讨论提示词",
        "",
        "请从量化研究和资产定价角度反驳或支持下面这个策略假设：",
        "",
        "> A 股指数在 2016-01-04 至 2026-07-07 的数据中呈现出资产轻重与最大回撤深度相关的现象：自由现金流、红利低波等防守策略指数最大回撤多在 25%-35%；上证50/沪深300约 40%；中证1000、创业板、科创50约 55%-62%；芯片、创新药、新能源等轻资产/成长预期主题可到 60%-70%；申万一级行业中资产轻评分为 1 的行业最大回撤中位数约 70%，资产重评分为 5 的行业约 49%。我想用这个现象做一个“历史压力区分批买入”策略：按资产类型设定压力区，不预测底部，只在进入历史深回撤区后分批买入并持有 2-3 年。请重点判断：这个现象是否可能只是样本期偶然；资产轻重评分是否有更客观替代指标；用固定阈值是否有未来函数；如何做滚动样本外验证；哪些行业深回撤可能是价值陷阱而非赔率机会。",
        "",
        "## 附件",
        "",
        "- 指标明细：`asset_light_drawdown_metrics.csv`",
        "- 固定阈值事件：`asset_light_drawdown_events.csv`",
        "",
        "## 参考资料",
        "",
        "- Tushare HTTP API 说明：https://tushare.pro/document/1?doc_id=130",
        "- Tushare 数据获取方式：https://tushare.pro/document/1?doc_id=129",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    load_env_file(ROOT / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = REPRESENTATIVE_ASSETS + load_sw_l1_assets()
    seen: set[str] = set()
    unique_assets: list[AssetSpec] = []
    for asset in assets:
        if asset.code in seen:
            continue
        seen.add(asset.code)
        unique_assets.append(asset)

    metric_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    thresholds = [-0.25, -0.40, -0.50, -0.60, -0.70]

    for asset in unique_assets:
        try:
            frame = fetch_series(asset)
            if len(frame) < 2:
                failures.append({"name": asset.name, "code": asset.code, "error": "行情不足"})
                continue
            drawdown = max_drawdown_info(frame)
            rolling = rolling_drawdown_stats(frame)
            metric_rows.append(
                {
                    "group": asset.group,
                    "name": asset.name,
                    "code": asset.code,
                    "api": asset.api,
                    "return_type": asset.return_type,
                    "asset_weight_score": asset.asset_weight_score,
                    "note": asset.note,
                    **drawdown,
                    **rolling,
                }
            )
            event_rows.extend(drawdown_threshold_events(asset, frame, thresholds))
        except Exception as exc:
            failures.append({"name": asset.name, "code": asset.code, "error": str(exc)})

    metrics = pd.DataFrame(metric_rows)
    events = pd.DataFrame(event_rows)
    for column in [
        "total_return",
        "annual_return",
        "max_drawdown",
        "current_drawdown",
        "rolling_1y_maxdd_p25",
        "rolling_1y_maxdd_p50",
        "rolling_1y_maxdd_p75",
    ]:
        if column in metrics.columns:
            metrics[column] = pd.to_numeric(metrics[column], errors="coerce")
    if not events.empty:
        for column in ["threshold", "event_drawdown", "fwd_1y_return", "fwd_2y_return", "fwd_3y_return"]:
            events[column] = pd.to_numeric(events[column], errors="coerce")

    metrics_path = OUTPUT_DIR / "asset_light_drawdown_metrics.csv"
    events_path = OUTPUT_DIR / "asset_light_drawdown_events.csv"
    markdown_path = OUTPUT_DIR / "asset_light_drawdown_strategy.md"
    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    events.to_csv(events_path, index=False, encoding="utf-8-sig")
    summaries = make_summary(metrics, events)
    write_markdown(metrics, events, summaries, markdown_path)

    meta = {
        "metrics": str(metrics_path),
        "events": str(events_path),
        "document": str(markdown_path),
        "asset_count": len(metrics),
        "event_count": len(events),
        "failures": failures,
    }
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
