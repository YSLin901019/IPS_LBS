# IPS/LBS Control Station

這個專題骨架實作「RSSI Fingerprinting + 區域分類 + WKNN + median moving filter」，用來在 15m × 9m × 2.7m 的室內長方形場地中定位 DUT，並把結果顯示在 GUI 上。目前 DUT 設定為 Raspberry Pi 4 + ALFA AWUS036AXML WiFi 6E dongle，並可同步紀錄上下兩組 ToF。

## 目前功能

- 離線 radio map CSV：`位置座標 -> RSSI 向量`
- 線上定位：RSSI 掃描後先做 median 濾波，再做區域分類與局部 WKNN
- GUI：顯示實驗室平面、reference points、Pi 3 估計位置、最近鄰與 RSSI
- Scanner：內建模擬模式，也保留 Raspberry Pi OS `iw` / `iwlist` 掃描器
- 採集工具：可紀錄四角 infrastructure RSSI 與上下 ToF 原始量測值

## 快速執行

桌面版 Tk GUI：

```bash
python3 -m ips_lbs.gui
```

如果系統沒有 `tkinter`，請先安裝 OS 套件：

```bash
sudo apt install python3-tk
```

也可以改用瀏覽器版 GUI，不需要 `tkinter` 或任何 pip 套件：

```bash
python3 -m ips_lbs.web_gui
```

啟動後打開：

```text
http://127.0.0.1:8000
```

如果 `8000` 已被佔用，程式會自動改用下一個可用 port，請以終端機顯示的 URL 為準。也可以手動指定：

```bash
python3 -m ips_lbs.web_gui --port 8001
```

沒有實測資料時會使用 `data/radio_map_sample.csv` 模擬 RSSI，因此可以先展示 GUI 和演算法流程。

單次定位測試：

```bash
python3 scripts/locate_once.py
```

## 實驗資料格式

radio map CSV 欄位如下：

```csv
point_id,area,x,y,infra_1,infra_2,infra_3,infra_4
RP01,入口區,1.5,1.5,-42,-74,-80,-66
```

建議離線階段每個 reference point 量測 20 到 50 次。raw samples 可以保留同樣欄位，額外加上 `timestamp`、`z`、`tof_top_m`、`tof_bottom_m` 也可以，再用：

```bash
python3 scripts/build_radio_map.py data/raw_measurements.csv data/radio_map_lab.csv
```

產生每個 reference point 的 median radio map。ToF 欄位會保留在 raw data 中供分析，但不會被當成 Wi-Fi RSSI fingerprint 欄位。

## 實測資料採集

場地設定：

- 長度：15 m
- 寬度：9 m
- 高度：2.7 m
- 四角 infrastructure SSID：`infra_1`、`infra_2`、`infra_3`、`infra_4`
- DUT：Raspberry Pi 4 + ALFA AWUS036AXML WiFi 6E dongle + 上下兩組 ToF

先確認 Wi-Fi dongle 的 interface 名稱，常見可能是 `wlan1`：

```bash
iw dev
```

確認能掃到四台 infrastructure：

```bash
python3 scripts/check_devices.py --interface wlan1
```

如果出現 `exit code 237` 或掃描失敗，先確認介面名稱與狀態：

```bash
iw dev
ip link show wlan1
rfkill list
sudo ip link set wlan1 up
```

接著改用 `iwlist` 或不透過 `sudo` 測試：

```bash
python3 scripts/check_devices.py --interface wlan1 --command iwlist
python3 scripts/check_devices.py --interface wlan1 --no-sudo
```

若系統沒有 `iw` 或 `iwlist`，先安裝：

```bash
sudo apt install iw wireless-tools
```

如果 ToF 已經接上，也可以一起檢查：

```bash
python3 scripts/check_devices.py \
  --interface wlan1 \
  --tof-top serial \
  --tof-top-path /dev/ttyUSB0 \
  --tof-bottom serial \
  --tof-bottom-path /dev/ttyUSB1 \
  --tof-top-scale 0.001 \
  --tof-bottom-scale 0.001
```

還沒接上硬體時，可以先用 mock 模式確認 CSV 流程：

```bash
python3 scripts/record_measurements.py \
  --scan-command mock \
  --point-id RP01 \
  --area 入口區 \
  --x 1.5 \
  --y 1.5 \
  --samples 3 \
  --tof-top mock \
  --tof-top-value 1.2 \
  --tof-bottom mock \
  --tof-bottom-value 1.4
```

如果你的環境只能用 `iwlist`：

```bash
python3 scripts/check_devices.py --interface wlan1 --command iwlist
```

在 reference point 量測 30 筆資料：

```bash
python3 scripts/record_measurements.py \
  --interface wlan1 \
  --point-id RP01 \
  --area 入口區 \
  --x 1.5 \
  --y 1.5 \
  --samples 30 \
  --interval 1.0
```

如果 ToF 是透過序列埠輸出「每行一個距離數值」，可以這樣接。以下假設感測器輸出單位是 mm，所以用 `0.001` 轉成 m：

```bash
python3 scripts/record_measurements.py \
  --interface wlan1 \
  --point-id RP01 \
  --area 入口區 \
  --x 1.5 \
  --y 1.5 \
  --samples 30 \
  --tof-top serial \
  --tof-top-path /dev/ttyUSB0 \
  --tof-bottom serial \
  --tof-bottom-path /dev/ttyUSB1 \
  --tof-top-scale 0.001 \
  --tof-bottom-scale 0.001
```

如果 ToF 數值由其他程式寫到檔案，也可以使用 file reader：

```bash
python3 scripts/record_measurements.py \
  --interface wlan1 \
  --point-id RP01 \
  --area 入口區 \
  --x 1.5 \
  --y 1.5 \
  --tof-top file \
  --tof-top-path /tmp/tof_top.txt \
  --tof-bottom file \
  --tof-bottom-path /tmp/tof_bottom.txt
```

## 接 Raspberry Pi 3 Wi-Fi 掃描

先查出 AP BSSID，並把它們對應到 radio map 欄位名稱：

目前採集階段可直接依 SSID 掃描 `infra_1` 到 `infra_4`。定位 GUI 的 `iwlist` 模式仍支援 BSSID 對應；若要避免同名 SSID 或 roaming 造成混淆，建議後續把四台 infrastructure 的 BSSID 固定填入。

若使用 Beacon Receiver，建議讓 Receiver 輸出同樣的 `{節點ID: RSSI}` 格式，再新增一個 scanner 類別接到 `PositioningService`。

## 建議專題步驟

1. 先用範例資料確認 GUI 與 WKNN 管線可跑。
2. 在物聯網實驗室標出 reference points，記錄每點座標與區域。
3. 每點收 20 到 50 筆 RSSI，建立 `raw_samples.csv`。
4. 產生 `radio_map_lab.csv`，用 K=3、K=5 比較誤差。
5. 測試不同 filter window 與區域分類候選數。
6. Demo 當天先做 3 到 5 個點的快速校正，必要時更新 radio map。
