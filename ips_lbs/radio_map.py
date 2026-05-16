import csv
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
