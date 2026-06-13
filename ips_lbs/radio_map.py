import csv
import json
from pathlib import Path
from typing import Iterable, List, Sequence

from ips_lbs.models import ReferencePoint


REQUIRED_COLUMNS = {"point_id", "area", "x", "y"}
NON_RSSI_COLUMNS = {
    "timestamp",
    "z",
    "room_length",
    "room_width",
    "room_height",
    "tof_top_m",
    "tof_bottom_m",
}
GRID_SPACING_M = 0.6


class RadioMap:
    def __init__(self, points: Sequence[ReferencePoint]) -> None:
        if not points:
            raise ValueError("radio map must contain at least one reference point")
        self.points = list(points)
        self.infrastructure_ids = sorted(
            {node_id for point in self.points for node_id in point.rssi}
        )

    @classmethod
    def from_csv(cls, path: str) -> "RadioMap":
        csv_path = Path(path)
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"{csv_path} has no header row")

            fieldnames = set(reader.fieldnames)
            missing = REQUIRED_COLUMNS - fieldnames
            if missing:
                raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")

            rssi_columns = [
                name for name in reader.fieldnames if name not in REQUIRED_COLUMNS
            ]
            points: List[ReferencePoint] = []
            for row in reader:
                rssi = {}
                for column in rssi_columns:
                    value = row.get(column, "").strip()
                    if value:
                        rssi[column] = float(value)

                points.append(
                    ReferencePoint(
                        point_id=row["point_id"].strip(),
                        area=row["area"].strip(),
                        x=float(row["x"]),
                        y=float(row["y"]),
                        rssi=rssi,
                    )
                )
        return cls(points)

    @classmethod
    def from_utm_json(
        cls,
        path: str,
        room_length: float = 15.0,
        room_width: float = 9.0,
        area_prefix: str = "cell",
        area_mode: str = "cell",
        zone_rows: int = 3,
        zone_cols: int = 3,
    ) -> "RadioMap":
        data = load_utm_json(path)
        return cls(
            points_from_utm_json(
                data,
                room_length,
                room_width,
                area_prefix,
                area_mode=area_mode,
                zone_rows=zone_rows,
                zone_cols=zone_cols,
            )
        )

    def to_csv(self, path: str) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["point_id", "area", "x", "y", *self.infrastructure_ids],
            )
            writer.writeheader()
            for point in self.points:
                row = {
                    "point_id": point.point_id,
                    "area": point.area,
                    "x": f"{point.x:.3f}",
                    "y": f"{point.y:.3f}",
                }
                for node_id in self.infrastructure_ids:
                    value = point.rssi.get(node_id)
                    row[node_id] = "" if value is None else f"{value:.2f}"
                writer.writerow(row)

    @classmethod
    def from_samples(
        cls, samples_path: str, output_path: str, group_columns: Iterable[str] = ()
    ) -> "RadioMap":
        """Build a median radio map from raw repeated measurements."""

        from collections import defaultdict
        from statistics import median

        csv_path = Path(samples_path)
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"{csv_path} has no header row")
            fieldnames = set(reader.fieldnames)
            missing = REQUIRED_COLUMNS - fieldnames
            if missing:
                raise ValueError(f"{csv_path} is missing columns: {sorted(missing)}")

            group_keys = tuple(group_columns) or ("point_id", "area", "x", "y")
            rssi_columns = [
                name
                for name in reader.fieldnames
                if name not in set(group_keys) and name not in NON_RSSI_COLUMNS
            ]
            buckets = defaultdict(lambda: defaultdict(list))
            metadata = {}
            for row in reader:
                key = tuple(row[column] for column in group_keys)
                metadata[key] = {column: row[column] for column in group_keys}
                for column in rssi_columns:
                    value = row.get(column, "").strip()
                    if value:
                        buckets[key][column].append(float(value))

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["point_id", "area", "x", "y", *rssi_columns]
            )
            writer.writeheader()
            for key in sorted(buckets):
                row = dict(metadata[key])
                for column in rssi_columns:
                    values = buckets[key].get(column, [])
                    row[column] = f"{median(values):.2f}" if values else ""
                writer.writerow(row)

        return cls.from_csv(str(output))


def load_utm_json(path: str) -> dict:
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def points_from_utm_json(
    data: dict,
    room_length: float = 15.0,
    room_width: float = 9.0,
    area_prefix: str = "cell",
    area_mode: str = "cell",
    zone_rows: int = 3,
    zone_cols: int = 3,
) -> List[ReferencePoint]:
    map_info = data.get("map", {})
    rows = int(map_info.get("rows", 0))
    cols = int(map_info.get("cols", 0))
    if rows <= 0 or cols <= 0:
        raise ValueError("UTM JSON map.rows and map.cols must be positive")
    if area_mode not in {"cell", "zone-grid"}:
        raise ValueError("area_mode must be 'cell' or 'zone-grid'")
    if zone_rows <= 0 or zone_cols <= 0:
        raise ValueError("zone_rows and zone_cols must be positive")

    points: List[ReferencePoint] = []
    for fingerprint in data.get("fingerprints", []):
        row = int(fingerprint["row"])
        col = int(fingerprint["col"])
        if not 0 <= row < rows:
            raise ValueError(f"fingerprint row out of range: {row}")
        if not 0 <= col < cols:
            raise ValueError(f"fingerprint col out of range: {col}")

        rssi = {}
        for ap in fingerprint.get("ap_data", []):
            ssid = str(ap.get("ssid", "")).strip()
            if ssid and ap.get("rssi_avg") is not None:
                rssi[ssid] = float(ap["rssi_avg"])

        points.append(
            ReferencePoint(
                point_id=f"R{row:02d}C{col:02d}",
                area=utm_area_label(
                    row,
                    col,
                    rows,
                    cols,
                    area_prefix,
                    area_mode,
                    zone_rows,
                    zone_cols,
                ),
                # Current map uses row along the long X axis and col along Y.
                x=row * GRID_SPACING_M,
                y=col * GRID_SPACING_M,
                rssi=rssi,
            )
        )

    return points


def utm_area_label(
    row: int,
    col: int,
    rows: int,
    cols: int,
    area_prefix: str,
    area_mode: str,
    zone_rows: int,
    zone_cols: int,
) -> str:
    if area_mode == "cell":
        return f"{area_prefix}_{row}_{col}"

    zone_row = min(row * zone_rows // rows, zone_rows - 1)
    zone_col = min(col * zone_cols // cols, zone_cols - 1)
    zone_index = zone_row * zone_cols + zone_col
    if zone_index < 26:
        return f"{area_prefix}_{chr(ord('A') + zone_index)}"
    return f"{area_prefix}_{zone_row}_{zone_col}"


def load_radio_map(
    path: str,
    room_length: float = 15.0,
    room_width: float = 9.0,
    area_prefix: str = "cell",
    area_mode: str = "cell",
    zone_rows: int = 3,
    zone_cols: int = 3,
) -> RadioMap:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return RadioMap.from_utm_json(
            path,
            room_length=room_length,
            room_width=room_width,
            area_prefix=area_prefix,
            area_mode=area_mode,
            zone_rows=zone_rows,
            zone_cols=zone_cols,
        )
    return RadioMap.from_csv(path)
