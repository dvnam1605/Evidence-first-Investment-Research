"""Source connector registry."""

from __future__ import annotations

from src.domain.enums import SourceType
from src.ingestion.base import SourceConnector
from src.ingestion.errors import SourceError


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[SourceType, SourceConnector] = {}

    def register(self, connector: SourceConnector) -> None:
        self._connectors[connector.source] = connector

    def get(self, source: SourceType | str) -> SourceConnector:
        key = SourceType(source)
        connector = self._connectors.get(key)
        if connector is None:
            raise SourceError(f"No connector registered for source {source!s}")
        return connector

    def sources(self) -> list[SourceType]:
        return list(self._connectors.keys())
