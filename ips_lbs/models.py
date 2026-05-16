from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


RssiVector = Dict[str, float]


@dataclass(frozen=True)
class ReferencePoint:
    point_id: str
    area: str
    x: float
    y: float
    rssi: RssiVector


@dataclass(frozen=True)
class PositionEstimate:
    x: float
    y: float
    area: str
    confidence: float
    neighbors: List[Tuple[ReferencePoint, float, float]]
    raw_rssi: RssiVector
    filtered_rssi: RssiVector
    message: Optional[str] = None

