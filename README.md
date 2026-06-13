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

## 匯入雲端 UTM Fingerprint

如果雲端 UTM 系統輸出 JSON，格式包含 `map.rows`、`map.cols` 與每格的 `fingerprints[].ap_data[].rssi_avg`，本地端可以直接讀取。系統會將 `row/col` 轉成絕對座標：

- `row -> x`
- `col -> y`
- `row=0, col=0 -> x=0, y=0`
- 每增加一格為 0.6 m
- 目前場景長邊 23 格對應 X 軸，短邊 12 格對應 Y 軸

例如 2 × 2 map 會轉成：

```text
row=0 col=0 -> x=0.00 y=0.00
row=0 col=1 -> x=0.00 y=0.60
row=1 col=0 -> x=0.60 y=0.00
row=1 col=1 -> x=0.60 y=0.60
```

直接用 JSON 啟動 Web GUI：

```bash
python3 -m ips_lbs.web_gui --radio-map data/utm_fingerprint_sample.json
```

或先轉成 CSV 方便檢查：

```bash
python3 scripts/utm_json_to_radio_map.py \
  data/utm_fingerprint_sample.json \
  data/radio_map_from_utm.csv
```

JSON 匯入時會直接使用 0.6 m 格距計算絕對座標，`--room-length` 與 `--room-width` 不再影響 UTM JSON 的座標換算。

快速跑一次 WKNN 模擬定位：

```bash
python3 scripts/locate_once.py --radio-map data/utm_fingerprint_sample.json --k 3
```

使用雲端建立的 `indoor-map-5.json`，並用當前 Wi-Fi RSSI 推測所在 cell：

```bash
python3 scripts/locate_live.py \
  --radio-map data/indoor-map-5.json \
  --interface wlan1 \
  --samples 5 \
  --k 3
```

如果要先手動貼一組 RSSI 測 WKNN：

```bash
python3 scripts/locate_live.py \
  --radio-map data/indoor-map-5.json \
  --rssi infra_1=-38 infra_2=-28 infra_3=-45 infra_4=-42
```

## WKNN 參數訓練與優化

`data/indoor-map-11 (4).json` 是實測 fingerprint 資料，可以先轉成 CSV 方便檢查：

```bash
python3 scripts/utm_json_to_radio_map.py \
  "data/indoor-map-11 (4).json" \
  data/radio_map_indoor_map_11.csv
```

WKNN 本身不需要模型檔訓練；訓練資料就是 radio map。參數優化可以用 leave-one-out validation：

```bash
python3 scripts/tune_wknn.py \
  "data/indoor-map-11 (4).json" \
  --output data/wknn_tuning_indoor_map_11.csv
```

目前這份 312 格實測資料的擴大搜尋最佳結果：

```text
k=12
weight_power=2.0
missing_rssi=-110
region_filter=off
mean_error=2.426 m
median_error=2.032 m
p90_error=4.936 m
```

也可以把場地切成 3 × 3 九宮格區域，讓系統先選出最相近的幾個 zone，再只在候選 zone 中做 WKNN：

```bash
python3 scripts/utm_json_to_radio_map.py \
  "data/indoor-map-11 (4).json" \
  data/radio_map_indoor_map_11_zones.csv \
  --area-mode zone-grid \
  --area-prefix zone \
  --zone-rows 3 \
  --zone-cols 3
```

九宮格分區名稱從左上到右下依序是：

```text
zone_A | zone_B | zone_C
zone_D | zone_E | zone_F
zone_G | zone_H | zone_I
```

目前 3 × 3 zone + Top-3 zone WKNN 的最佳搜尋結果：

```text
k=12
region_k=15
region_count=3
weight_power=1.5
missing_rssi=-110
region_filter=on
mean_error=2.389 m
median_error=1.909 m
p90_error=4.821 m
```

套用最佳參數做一次手動 RSSI 定位：

```bash
python3 scripts/locate_live.py \
  --radio-map "data/indoor-map-11 (4).json" \
  --area-mode zone-grid \
  --area-prefix zone \
  --zone-rows 3 \
  --zone-cols 3 \
  --k 12 \
  --region-k 15 \
  --region-count 3 \
  --weight-power 1.5 \
  --missing-rssi -110 \
  --rssi infra_1=-38 infra_2=-28 infra_3=-45 infra_4=-42
```

如果實測結果有固定方向偏移，可以用已知點做 offset 校正。計算方式是：

```text
x_offset = 實際 x - 推論 x
y_offset = 實際 y - 推論 y
```

再把 offset 套到實測推論：

```bash
python3 scripts/locate_live.py \
  --radio-map "data/indoor-map-11 (4).json" \
  --area-mode zone-grid \
  --area-prefix zone \
  --zone-rows 3 \
  --zone-cols 3 \
  --interface wlan1 \
  --samples 8 \
  --window 8 \
  --k 12 \
  --region-k 15 \
  --region-count 3 \
  --weight-power 1.5 \
  --missing-rssi -110 \
  --x-offset 0.0 \
  --y-offset 0.0
```

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
