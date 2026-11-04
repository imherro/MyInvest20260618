from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


VALID_ASSET_TYPES = {"etf", "index"}
VALID_CATEGORIES = {"broad", "style", "industry"}


@dataclass(frozen=True)
class AssetRecord:
    code: str
    name: str
    type: str
    category: str
    source: str
    benchmark: str
    enabled: bool = True
    theme: str | None = None
    notes: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.type not in VALID_ASSET_TYPES:
            raise ValueError(f"invalid asset type for {self.code}: {self.type}")
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"invalid asset category for {self.code}: {self.category}")
        if not self.code or "." not in self.code:
            raise ValueError(f"asset code must include exchange suffix: {self.code}")
        if not self.name:
            raise ValueError(f"asset name is required for {self.code}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AssetRecord":
        tags = payload.get("tags") or []
        return cls(
            code=str(payload["code"]),
            name=str(payload["name"]),
            type=str(payload["type"]),
            category=str(payload["category"]),
            source=str(payload["source"]),
            benchmark=str(payload["benchmark"]),
            enabled=bool(payload.get("enabled", True)),
            theme=None if payload.get("theme") is None else str(payload.get("theme")),
            notes=None if payload.get("notes") is None else str(payload.get("notes")),
            tags=tuple(str(item) for item in tags),
        )
