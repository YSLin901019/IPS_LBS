from collections import defaultdict, deque
from statistics import median
from typing import Deque, Dict, Iterable

from ips_lbs.models import RssiVector


class MedianMovingFilter:
    """Keeps a short RSSI history per infrastructure node and returns medians."""

    def __init__(self, window_size: int = 5) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self.window_size = window_size
        self._history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

    def update(self, sample: RssiVector) -> RssiVector:
        for node_id, value in sample.items():
            self._history[node_id].append(float(value))
        return self.current(sample.keys())

    def current(self, visible_nodes: Iterable[str]) -> RssiVector:
        filtered: RssiVector = {}
        for node_id in visible_nodes:
            values = self._history.get(node_id)
            if values:
                filtered[node_id] = float(median(values))
        return filtered

    def clear(self) -> None:
        self._history.clear()

