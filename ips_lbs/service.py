from ips_lbs.filters import MedianMovingFilter
from ips_lbs.models import PositionEstimate
from ips_lbs.scanner import Scanner
from ips_lbs.wknn import WKNNLocalizer


class PositioningService:
    def __init__(
        self,
        scanner: Scanner,
        localizer: WKNNLocalizer,
        rssi_filter: MedianMovingFilter,
    ) -> None:
        self.scanner = scanner
        self.localizer = localizer
        self.rssi_filter = rssi_filter

    def locate_once(self) -> PositionEstimate:
        raw = self.scanner.scan()
        filtered = self.rssi_filter.update(raw)
        estimate = self.localizer.estimate(filtered)
        return PositionEstimate(
            x=estimate.x,
            y=estimate.y,
            area=estimate.area,
            confidence=estimate.confidence,
            neighbors=estimate.neighbors,
            raw_rssi=raw,
            filtered_rssi=filtered,
            message=estimate.message,
        )

