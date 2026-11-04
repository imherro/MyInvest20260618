from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


VALID_PROXY_TYPES = {"index"}
VALID_MAPPING_METHODS = {"research_only", "direct_etf_history_only"}


@dataclass(frozen=True)
class ResearchProxy:
    code: str
    name: str
    type: str
    source: str

    def __post_init__(self) -> None:
        if self.type not in VALID_PROXY_TYPES:
            raise ValueError(f"invalid proxy type for {self.code}: {self.type}")
        if "." not in self.code:
            raise ValueError(f"proxy code must include exchange suffix: {self.code}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ResearchProxy":
        return cls(
            code=str(payload["code"]),
            name=str(payload["name"]),
            type=str(payload["type"]),
            source=str(payload["source"]),
        )


@dataclass(frozen=True)
class AssetProxyRecord:
    asset_code: str
    asset_name: str
    asset_type: str
    asset_category: str
    mapping_method: str
    research_proxy: ResearchProxy | None = None
    enabled: bool = True
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.mapping_method not in VALID_MAPPING_METHODS:
            raise ValueError(f"invalid mapping method for {self.asset_code}: {self.mapping_method}")
        if self.mapping_method == "research_only" and self.research_proxy is None:
            raise ValueError(f"research_only mapping requires research_proxy: {self.asset_code}")
        if self.mapping_method == "direct_etf_history_only" and self.research_proxy is not None:
            raise ValueError(f"direct_etf_history_only must not include research_proxy: {self.asset_code}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["research_proxy"] = None if self.research_proxy is None else self.research_proxy.to_dict()
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AssetProxyRecord":
        proxy_payload = payload.get("research_proxy")
        proxy = ResearchProxy.from_mapping(proxy_payload) if isinstance(proxy_payload, Mapping) else None
        return cls(
            asset_code=str(payload["asset_code"]),
            asset_name=str(payload["asset_name"]),
            asset_type=str(payload["asset_type"]),
            asset_category=str(payload["asset_category"]),
            mapping_method=str(payload["mapping_method"]),
            research_proxy=proxy,
            enabled=bool(payload.get("enabled", True)),
            notes=None if payload.get("notes") is None else str(payload.get("notes")),
        )
