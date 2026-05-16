import argparse
import sys

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:
    print(
        "tkinter is not installed in this Python environment.\n\n"
        "Install it on Raspberry Pi OS / Debian / Ubuntu with:\n"
        "  sudo apt install python3-tk\n\n"
        "Or run the browser-based control station instead:\n"
        "  python3 -m ips_lbs.web_gui\n",
        file=sys.stderr,
    )
    raise SystemExit(1)

from ips_lbs.factory import add_positioning_args, build_service
from ips_lbs.radio_map import RadioMap


class ControlStation(tk.Tk):
    def __init__(
        self,
        radio_map: RadioMap,
        service: PositioningService,
        interval_ms: int = 3000,
    ) -> None:
        super().__init__()
        self.title("IPS/LBS Control Station")
        self.geometry("980x640")
        self.minsize(860, 560)
        self.radio_map = radio_map
        self.service = service
        self.interval_ms = interval_ms
        self.running = False
        self.last_estimate = None

        self._build_layout()
        self._draw_lab()

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, background="#f8fafc", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        side = ttk.Frame(self, padding=12)
        side.grid(row=0, column=1, sticky="ns")
        side.columnconfigure(0, weight=1)

        title = ttk.Label(side, text="Raspberry Pi 3 定位結果", font=("Arial", 15, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.status = tk.StringVar(value="待機中")
        ttk.Label(side, textvariable=self.status, font=("Arial", 11)).grid(
            row=1, column=0, sticky="w", pady=(0, 12)
        )

        self.position = tk.StringVar(value="座標: --")
        self.area = tk.StringVar(value="區域: --")
        self.confidence = tk.StringVar(value="信心值: --")
        for row, variable in enumerate(
            (self.position, self.area, self.confidence), start=2
        ):
            ttk.Label(side, textvariable=variable, font=("Arial", 12)).grid(
                row=row, column=0, sticky="w", pady=3
            )

        controls = ttk.Frame(side)
        controls.grid(row=5, column=0, sticky="ew", pady=12)
        ttk.Button(controls, text="開始", command=self.start).grid(row=0, column=0, padx=3)
        ttk.Button(controls, text="停止", command=self.stop).grid(row=0, column=1, padx=3)
        ttk.Button(controls, text="單次定位", command=self.locate_once).grid(
            row=0, column=2, padx=3
        )

        ttk.Label(side, text="最近 WKNN 參考點", font=("Arial", 11, "bold")).grid(
            row=6, column=0, sticky="w", pady=(12, 4)
        )
        self.neighbor_list = tk.Listbox(side, height=7, width=38)
        self.neighbor_list.grid(row=7, column=0, sticky="ew")

        ttk.Label(side, text="目前 RSSI", font=("Arial", 11, "bold")).grid(
            row=8, column=0, sticky="w", pady=(12, 4)
        )
        self.rssi_table = ttk.Treeview(
            side, columns=("node", "raw", "filtered"), show="headings", height=9
        )
        self.rssi_table.heading("node", text="節點")
        self.rssi_table.heading("raw", text="Raw")
        self.rssi_table.heading("filtered", text="Median")
        self.rssi_table.column("node", width=100)
        self.rssi_table.column("raw", width=70, anchor="e")
        self.rssi_table.column("filtered", width=80, anchor="e")
        self.rssi_table.grid(row=9, column=0, sticky="nsew")

        self.canvas.bind("<Configure>", lambda _event: self._draw_lab())

    def start(self) -> None:
        if not self.running:
            self.running = True
            self.status.set("定位中")
            self._tick()

    def stop(self) -> None:
        self.running = False
        self.status.set("已停止")

    def locate_once(self) -> None:
        try:
            self.last_estimate = self.service.locate_once()
        except Exception as exc:
            self.status.set(f"掃描失敗: {exc}")
            return
        self._render_estimate()

    def _tick(self) -> None:
        if not self.running:
            return
        self.locate_once()
        self.after(self.interval_ms, self._tick)

    def _render_estimate(self) -> None:
        estimate = self.last_estimate
        if estimate is None:
            return

        self.position.set(f"座標: ({estimate.x:.2f}, {estimate.y:.2f})")
        self.area.set(f"區域: {estimate.area}")
        self.confidence.set(f"信心值: {estimate.confidence:.3f}")
        if estimate.message:
            self.status.set(estimate.message)
        elif self.running:
            self.status.set("定位中")
        else:
            self.status.set("已完成單次定位")

        self.neighbor_list.delete(0, tk.END)
        for point, distance, weight in estimate.neighbors:
            self.neighbor_list.insert(
                tk.END,
                f"{point.point_id} {point.area} d={distance:.2f} w={weight:.3f}",
            )

        for item in self.rssi_table.get_children():
            self.rssi_table.delete(item)
        node_ids = sorted(set(estimate.raw_rssi) | set(estimate.filtered_rssi))
        for node_id in node_ids:
            raw = estimate.raw_rssi.get(node_id)
            filtered = estimate.filtered_rssi.get(node_id)
            self.rssi_table.insert(
                "",
                tk.END,
                values=(
                    node_id,
                    f"{raw:.1f}" if raw is not None else "--",
                    f"{filtered:.1f}" if filtered is not None else "--",
                ),
            )
        self._draw_lab()

    def _draw_lab(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 100)
        height = max(self.canvas.winfo_height(), 100)
        padding = 58

        xs = [point.x for point in self.radio_map.points]
        ys = [point.y for point in self.radio_map.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)

        def to_screen(x: float, y: float) -> tuple:
            sx = padding + (x - min_x) / span_x * (width - padding * 2)
            sy = height - padding - (y - min_y) / span_y * (height - padding * 2)
            return sx, sy

        self.canvas.create_rectangle(
            padding,
            padding,
            width - padding,
            height - padding,
            outline="#334155",
            width=2,
        )
        self.canvas.create_text(
            padding,
            24,
            text="物聯網實驗室 Radio Map",
            anchor="w",
            fill="#0f172a",
            font=("Arial", 15, "bold"),
        )

        area_colors = {
            "入口區": "#2563eb",
            "工作桌區": "#16a34a",
            "設備櫃區": "#dc2626",
        }
        for point in self.radio_map.points:
            sx, sy = to_screen(point.x, point.y)
            color = area_colors.get(point.area, "#64748b")
            self.canvas.create_oval(sx - 8, sy - 8, sx + 8, sy + 8, fill=color, outline="")
            self.canvas.create_text(
                sx,
                sy - 18,
                text=point.point_id,
                fill="#0f172a",
                font=("Arial", 9),
            )

        estimate = self.last_estimate
        if estimate is not None:
            sx, sy = to_screen(estimate.x, estimate.y)
            self.canvas.create_oval(
                sx - 14,
                sy - 14,
                sx + 14,
                sy + 14,
                fill="#facc15",
                outline="#854d0e",
                width=2,
            )
            self.canvas.create_text(
                sx,
                sy + 26,
                text="Pi 3",
                fill="#713f12",
                font=("Arial", 11, "bold"),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IPS/LBS Control Station")
    add_positioning_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    radio_map, service = build_service(args)
    app = ControlStation(radio_map, service, interval_ms=args.interval_ms)
    app.mainloop()


if __name__ == "__main__":
    main()
