#!/usr/bin/env python3
"""
SkyNode UTM — Indoor Fingerprint Collector

Polls UTM for collect commands, scans infrastructure WiFi SSIDs,
submits averaged RSSI fingerprints.

Usage (real hardware):
    python scripts/indoor_fingerprint.py \\
        --api-key sk_xxxxxxxx \\
        --interface wlan1 \\
        --command iw

Usage (mock — no hardware needed):
    python scripts/indoor_fingerprint.py \\
        --api-key sk_xxxxxxxx \\
        --command mock

Requirements:
    pip install requests
    (same ips_lbs package already on your drone)
"""

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import requests
except ImportError:
    print("Missing dependency. Run:  pip install requests")
    raise SystemExit(1)

from ips_lbs.measurement import (
    DEFAULT_INFRA_SSIDS,
    WifiScanError,
    WifiSsidScanner,
)


# ---------------------------------------------------------------------------
# WiFi scanning
# ---------------------------------------------------------------------------

def collect_n_scans(
    scanner: WifiSsidScanner,
    n: int,
    delay: float = 0.5,
) -> list[dict]:
    """
    Run N scans, average RSSI per SSID.
    Returns [{ssid, rssi_avg}] sorted by rssi_avg descending.
    Only SSIDs seen in at least one scan are included.
    """
    accumulated: dict[str, list[float]] = defaultdict(list)

    for i in range(n):
        print(f"  Scan {i + 1}/{n}...", end=" ", flush=True)
        try:
            readings: dict[str, float] = scanner.scan()  # {ssid: rssi_dBm}
        except WifiScanError as e:
            print(f"WARN: {e}")
            if i < n - 1:
                time.sleep(delay)
            continue

        for ssid, rssi in readings.items():
            accumulated[ssid].append(rssi)
        visible = [s for s in readings if readings[s] is not None]
        print(f"found {len(visible)} infra SSIDs: {visible}")

        if i < n - 1:
            time.sleep(delay)

    return sorted(
        [
            {"ssid": ssid, "rssi_avg": round(sum(v) / len(v), 2)}
            for ssid, v in accumulated.items()
        ],
        key=lambda x: x["rssi_avg"],
        reverse=True,
    )


# ---------------------------------------------------------------------------
# UTM API calls (device Bearer token auth)
# ---------------------------------------------------------------------------

def poll_command(server: str, api_key: str) -> Optional[dict]:
    """GET /api/indoor/command/pending → {map_id, row, col, scans_needed} or None."""
    resp = requests.get(
        f"{server}/api/indoor/command/pending",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json().get("command")
    print(f"[POLL] Unexpected {resp.status_code}: {resp.text[:200]}")
    return None


def submit_fingerprint(
    server: str,
    api_key: str,
    map_id: int,
    row: int,
    col: int,
    ap_data: list[dict],
    scans_count: int,
) -> bool:
    """POST /api/indoor/fingerprint"""
    resp = requests.post(
        f"{server}/api/indoor/fingerprint",
        json={
            "map_id":      map_id,
            "row":         row,
            "col":         col,
            "ap_data":     ap_data,
            "scans_count": scans_count,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"[SUBMIT] OK — cell ({row},{col}), {len(ap_data)} SSIDs stored")
        return True
    print(f"[SUBMIT] Failed {resp.status_code}: {resp.text[:200]}")
    return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(
    server: str,
    api_key: str,
    interface: str,
    command: str,
    ssids: list[str],
    use_sudo: bool,
    poll_interval: int,
) -> None:
    scanner = WifiSsidScanner(
        interface,
        ssids,
        command=command,
        use_sudo=use_sudo,
    )

    print(f"\n[START] Indoor Fingerprint Collector")
    print(f"        Server    : {server}")
    print(f"        Interface : {interface}  command={command}  sudo={use_sudo}")
    print(f"        SSIDs     : {', '.join(ssids)}")
    print(f"        Poll      : every {poll_interval}s")
    print("        Ctrl+C to stop\n")

    while True:
        try:
            cmd = poll_command(server, api_key)

            if cmd is None:
                print(f"[POLL] No pending command. Waiting {poll_interval}s...")
                time.sleep(poll_interval)
                continue

            map_id = cmd["map_id"]
            row    = cmd["row"]
            col    = cmd["col"]
            n      = cmd.get("scans_needed", 5)

            print(f"\n[CMD] Collect cell ({row},{col}) of map {map_id}  ({n} scans)")
            ap_data = collect_n_scans(scanner, n)

            if not ap_data:
                print("[WARN] No SSIDs found in any scan. Check AP power and interface. Retrying...")
                time.sleep(poll_interval)
                continue

            submit_fingerprint(server, api_key, map_id, row, col, ap_data, n)

        except KeyboardInterrupt:
            print("\n[STOP] Interrupted by user.")
            break
        except requests.exceptions.ConnectionError as e:
            print(f"[ERROR] Connection: {e}. Retry in {poll_interval}s...")
            time.sleep(poll_interval)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkyNode UTM Indoor Fingerprint Collector"
    )
    parser.add_argument("--api-key",   default="sk_9d2af2ee656168fc32fc08ddadb3a1f4327e8d92c50d69f371bbf6758011109c",
                        help="Device API key (sk_...)")
    parser.add_argument("--server",    default="https://skynode-utm-api.h03895-64272.workers.dev",
                        help="UTM server base URL")
    parser.add_argument("--interface", default="wlan1",
                        help="WiFi interface (default: wlan1)")
    parser.add_argument("--command",   choices=("iw", "iwlist", "mock"), default="iw",
                        help="Scan backend (default: iw)")
    parser.add_argument("--no-sudo",   action="store_true",
                        help="Do not prefix scan with sudo")
    parser.add_argument("--ssid",      nargs="+", default=list(DEFAULT_INFRA_SSIDS),
                        help="Infrastructure SSIDs to scan (default: DEFAULT_INFRA_SSIDS)")
    parser.add_argument("--poll",      type=int, default=5,
                        help="Poll interval in seconds (default: 5)")
    args = parser.parse_args()

    run(
        server=args.server,
        api_key=args.api_key,
        interface=args.interface,
        command=args.command,
        ssids=args.ssid,
        use_sudo=not args.no_sudo,
        poll_interval=args.poll,
    )


if __name__ == "__main__":
    main()
