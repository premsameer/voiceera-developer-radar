from abc import ABC, abstractmethod
from datetime import datetime
from ..schemas import NormalizedSignal


class ConnectorAdapter(ABC):
    name: str
    @abstractmethod
    def collect(self, since: datetime, config: dict) -> list[NormalizedSignal]: ...

