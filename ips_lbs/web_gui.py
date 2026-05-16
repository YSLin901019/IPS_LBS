import argparse
import errno
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from ips_lbs.factory import add_positioning_args, build_service


HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IPS/LBS Control Station</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, "Noto Sans TC", sans-serif;
      background: #f8fafc;
      color: #0f172a;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      grid-template-columns: 1fr 340px;
    }
    main {
      padding: 24px;
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 14px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }
    #map {
      width: 100%;
      min-height: 520px;
      border: 1px solid #cbd5e1;
      background: white;
    }
    aside {
      border-left: 1px solid #cbd5e1;
      background: #ffffff;
      padding: 20px;
      overflow: auto;
    }
    .metric {
      margin: 10px 0;
      font-size: 18px;
    }
    button {
      border: 1px solid #94a3b8;
      background: #0f172a;
      color: white;
      padding: 8px 12px;
      margin: 8px 4px 14px 0;
      border-radius: 6px;
      cursor: pointer;
    }
    button.secondary {
      background: white;
      color: #0f172a;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 14px;
    }
    th, td {
      border-bottom: 1px solid #e2e8f0;
      padding: 7px 4px;
      text-align: right;
    }
    th:first-child, td:first-child {
      text-align: left;
    }
    .section-title {
      margin-top: 18px;
      font-weight: 700;
    }
    @media (max-width: 820px) {
      body {
        grid-template-columns: 1fr;
      }
      aside {
        border-left: 0;
        border-top: 1px solid #cbd5e1;
      }
      #map {
        min-height: 360px;
      }
    }
  </style>
</head>
<body>
  <main>
    <h1>物聯網實驗室 Radio Map</h1>
    <svg id="map" viewBox="0 0 720 520" role="img"></svg>
  </main>
  <aside>
    <h2>Raspberry Pi 3 定位結果</h2>
    <div id="status">待機中</div>
    <div class="metric" id="position">座標: --</div>
    <div class="metric" id="area">區域: --</div>
    <div class="metric" id="confidence">信心值: --</div>
    <button id="start">開始</button>
    <button class="secondary" id="stop">停止</button>
    <button class="secondary" id="once">單次定位</button>
    <div class="section-title">最近 WKNN 參考點</div>
    <table>
      <thead><tr><th>點位</th><th>距離</th><th>權重</th></tr></thead>
      <tbody id="neighbors"></tbody>
    </table>
    <div class="section-title">目前 RSSI</div>
    <table>
      <thead><tr><th>節點</th><th>Raw</th><th>Median</th></tr></thead>
      <tbody id="rssi"></tbody>
    </table>
  </aside>
  <script>
    const map = document.getElementById("map");
    let radioPoints = [];
    let timer = null;

    const colors = {
      "入口區": "#2563eb",
      "工作桌區": "#16a34a",
      "設備櫃區": "#dc2626"
    };

    function bounds(points) {
      const xs = points.map(p => p.x);
      const ys = points.map(p => p.y);
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys)
      };
    }

    function toScreen(point, b) {
      const pad = 56;
      const spanX = Math.max(b.maxX - b.minX, 1);
      const spanY = Math.max(b.maxY - b.minY, 1);
      return {
        x: pad + (point.x - b.minX) / spanX * (720 - pad * 2),
        y: 520 - pad - (point.y - b.minY) / spanY * (520 - pad * 2)
      };
    }

    function draw(estimate) {
      const b = bounds(radioPoints);
      map.innerHTML = "";
      map.insertAdjacentHTML("beforeend", `<rect x="56" y="56" width="608" height="408" fill="#fff" stroke="#334155" stroke-width="2"/>`);
      for (const point of radioPoints) {
        const p = toScreen(point, b);
        const fill = colors[point.area] || "#64748b";
        map.insertAdjacentHTML("beforeend", `<circle cx="${p.x}" cy="${p.y}" r="8" fill="${fill}"/>`);
        map.insertAdjacentHTML("beforeend", `<text x="${p.x}" y="${p.y - 16}" text-anchor="middle" font-size="13" fill="#0f172a">${point.point_id}</text>`);
      }
      if (estimate) {
        const p = toScreen(estimate, b);
        map.insertAdjacentHTML("beforeend", `<circle cx="${p.x}" cy="${p.y}" r="15" fill="#facc15" stroke="#854d0e" stroke-width="2"/>`);
        map.insertAdjacentHTML("beforeend", `<text x="${p.x}" y="${p.y + 32}" text-anchor="middle" font-size="15" font-weight="700" fill="#713f12">Pi 3</text>`);
      }
    }

    function rows(items, render) {
      return items.map(render).join("");
    }

    async function locateOnce() {
      document.getElementById("status").textContent = "定位中";
      const response = await fetch("/api/locate");
      const estimate = await response.json();
      document.getElementById("status").textContent = estimate.message || "定位完成";
      document.getElementById("position").textContent = `座標: (${estimate.x.toFixed(2)}, ${estimate.y.toFixed(2)})`;
      document.getElementById("area").textContent = `區域: ${estimate.area}`;
      document.getElementById("confidence").textContent = `信心值: ${estimate.confidence.toFixed(3)}`;
      document.getElementById("neighbors").innerHTML = rows(estimate.neighbors, n =>
        `<tr><td>${n.point_id}</td><td>${n.distance.toFixed(2)}</td><td>${n.weight.toFixed(3)}</td></tr>`
      );
      const nodes = Array.from(new Set([...Object.keys(estimate.raw_rssi), ...Object.keys(estimate.filtered_rssi)])).sort();
      document.getElementById("rssi").innerHTML = rows(nodes, node =>
        `<tr><td>${node}</td><td>${fmt(estimate.raw_rssi[node])}</td><td>${fmt(estimate.filtered_rssi[node])}</td></tr>`
      );
      draw(estimate);
    }

    function fmt(value) {
      return value === undefined ? "--" : Number(value).toFixed(1);
    }

    async function init() {
      const response = await fetch("/api/radio-map");
      radioPoints = await response.json();
      draw(null);
    }

    document.getElementById("once").addEventListener("click", locateOnce);
    document.getElementById("start").addEventListener("click", () => {
      if (!timer) {
        locateOnce();
        timer = setInterval(locateOnce, window.intervalMs || 3000);
      }
    });
    document.getElementById("stop").addEventListener("click", () => {
      clearInterval(timer);
      timer = null;
      document.getElementById("status").textContent = "已停止";
    });
    init();
  </script>
</body>
</html>
"""


def estimate_to_dict(estimate) -> dict:
    return {
        "x": estimate.x,
        "y": estimate.y,
        "area": estimate.area,
        "confidence": estimate.confidence,
        "message": estimate.message,
        "raw_rssi": estimate.raw_rssi,
        "filtered_rssi": estimate.filtered_rssi,
        "neighbors": [
            {
                "point_id": point.point_id,
                "area": point.area,
                "x": point.x,
                "y": point.y,
                "distance": distance,
                "weight": weight,
            }
            for point, distance, weight in estimate.neighbors
        ],
    }


def make_handler(radio_map, service):
    class ControlStationHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._send_text(HTML)
            elif path == "/api/radio-map":
                payload = [
                    {
                        "point_id": point.point_id,
                        "area": point.area,
                        "x": point.x,
                        "y": point.y,
                    }
                    for point in radio_map.points
                ]
                self._send_json(payload)
            elif path == "/api/locate":
                estimate = service.locate_once()
                self._send_json(estimate_to_dict(estimate))
            else:
                self.send_error(404)

        def log_message(self, format, *args):
            return

        def _send_text(self, text: str) -> None:
            encoded = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ControlStationHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser-based IPS/LBS Control Station")
    add_positioning_args(parser)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-auto-port",
        action="store_true",
        help="Fail instead of trying the next port when the selected port is busy.",
    )
    return parser.parse_args()


def create_server(args: argparse.Namespace, handler) -> HTTPServer:
    port = args.port
    max_attempts = 1 if args.no_auto_port else 20
    for attempt in range(max_attempts):
        try:
            return HTTPServer((args.host, port + attempt), handler)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE or attempt == max_attempts - 1:
                raise
    raise RuntimeError("Unable to create HTTP server.")


def main() -> None:
    args = parse_args()
    radio_map, service = build_service(args)
    server = create_server(args, make_handler(radio_map, service))
    host, port = server.server_address
    if port != args.port:
        print(f"Port {args.port} is busy; using {port} instead.")
    print(f"IPS/LBS Web Control Station: http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
