# K 棒資料下載 + K 線檢視器

下載每日 K 棒 CSV（供回測用），並用 TradingView 官方開源的 Lightweight Charts 呈現。

## 支援商品

| 代碼 | 名稱 | 來源 | 備註 |
|------|------|------|------|
| MNQ | 微型納斯達克 | Yahoo（NQ=F 代理） | 美股 |
| MGC | 微型黃金 | Yahoo（GC=F 代理） | 美股 |
| MCL | 微型原油 | Yahoo（CL=F 代理） | 美股 |
| TX  | 大台（臺股期貨） | TAIFEX 官方 | 1998 上市，歷史最長，**回測首選**（僅日盤）|
| MTX | 小台（小型臺指） | TAIFEX 官方 | 2001 上市，歷史長，**回測首選**（僅日盤）|
| TMF | 微台（微型臺指） | TAIFEX 官方 | 2024 才上市，僅 ~1 年，供近期實盤對照（僅日盤）|
| TXN  | 大台夜盤 | FinLab | 補 TAIFEX 沒有的盤後時段。⚠️ 免費帳號資料僅到 2018-12-28 |
| MTXN | 小台夜盤 | FinLab | 同上 |
| TMFN | 微台夜盤 | FinLab | 同上 |

> 微台/小台/大台追蹤同一個加權指數，K 線走勢一致，差別只在合約規格。
> **建議用大台/小台的長歷史回測，訊號直接適用於實際交易的微台。**
> TAIFEX 官方來源只抓日盤（排除夜盤避免同日重複）；夜盤要另外用 TXN/MTXN/TMFN（FinLab 來源）。

## 安裝

```bash
pip install yfinance requests pandas
# 選配（官方來源抓不到時的備援）：
pip install tvDatafeed        # 需設環境變數 TV_USERNAME / TV_PASSWORD
# 選配（抓 TXN/MTXN/TMFN 夜盤用）：
pip install finlab
python -c "import finlab; finlab.login()"   # 第一次登入，開瀏覽器走 Google OAuth，token 存 ~/.finlab
```

> **FinLab 免費帳號限制**：`futures_price` 資料集（大/小/微台夜盤的來源）免費方案只到
> 2018-12-28，之後的資料需要付費方案才能取得。抓 TXN/MTXN/TMFN 目前只能拿到 2018 年底以前的歷史。

## 用法

### 最簡單：全部在網頁上做（推薦）

```bash
python server.py            # 啟動並自動開瀏覽器
```

網頁上就能：
- **下載**：選商品 + **時間刻度（日/60/30/15/5/1分）** + 起始日 → 按「下載」，完成後自動顯示。
- **更新全部**：一鍵把所有已下載的 (商品×刻度) 增量更新到最新（只抓最近、與現有合併，不重抓整段歷史）。
- **檢視**：上方切換商品；商品旁的分段鈕切換該商品「已下載的時間刻度」；十字游標顯示 開/高/低/收/量。
- **水平線**：按「▬ 水平線」進入畫線模式 → 點圖表新增支撐/壓力線、點在既有線上刪除。
- **畫筆**：按「✏ 畫筆」自由手繪，塗出 W 底/破底翻/頭肩頂等型態；「⟲ 復原」退上一筆。
  手繪**跟著 K 棒縮放平移**（存的是 K 棒座標，不是像素）。
- 「清除」清掉該商品所有畫線（水平線＋手繪）。畫的東西**依商品存在瀏覽器**，換時框、重整、重開都還在。

不用再開終端機。長下載走背景不卡頁面，網頁顯示進度。

### 時間刻度與歷史限制

| 刻度 | 美股(Yahoo) 可回溯 | 台指(TAIFEX) |
|------|-------------------|-------------|
| 日 (1d)   | 完整 | 完整（大台 1998、小台 2001 起）|
| 60分 (60m)| ~730 天 | ❌ 需券商 API |
| 30/15/5分 | ~60 天  | ❌ 需券商 API |
| 1分 (1m)  | ~7 天   | ❌ 需券商 API |

> 台指期分鐘資料免費來源沒有；選台指+分鐘時 UI 會提示「需券商 API（Shioaji）」。
> 之後若接上 Shioaji，只要在 `sources/` 加一個來源即可，UI/下載流程不用改。

### 打包成執行檔（免裝 Python）

想在沒有 Python 的機器上用、或雙擊就跑，可打包成單一 exe：

```bash
pip install pyinstaller
python build_exe.py
```

產出 `dist/kbar-server.exe`（~85MB）：
- 雙擊即啟動、自動開瀏覽器；下載的 CSV 存到 **exe 旁邊的 `data/`**（可保存、可帶著走）。
- 單檔版首次啟動需解壓數秒；exe 內含 pandas/yfinance。
- 未簽章，Windows SmartScreen 可能跳「不明發行者」→ 點「其他資訊 → 仍要執行」。

### 或用 CLI 下載（等同網頁的下載鈕）

```bash
python download.py                            # 全部商品，日K
python download.py MNQ 大台 小台                 # 指定（可用中英別名）
python download.py MNQ --interval 15m         # 指定時間刻度（1d/60m/30m/15m/5m/1m）
python download.py MNQ --start 2015-01-01     # 日K 起始日
python download.py --list                     # 列出可用商品與刻度
```

輸出：`data/<KEY>_<刻度>_<起>_<迄>.csv`（起訖為資料第一/最後一天），
例如 `MNQ_15m_2026-04-24_2026-07-06.csv`、`TX_1d_2010-01-04_2026-07-06.csv`。
每個商品每種刻度只保留一份（更新時舊檔自動移除）。
日K 欄位 `Date,Open,High,Low,Close,Volume`；分鐘K 首欄為 `Datetime`（交易所當地時間）。

- 美股（Yahoo）：一次下載完整歷史。
- 台指（TAIFEX）：因官方單次查詢上限 1 個月，程式**自動逐月分段**下載，
  並以「每日成交量最大的合約月份」組成連續日K（近似連續合約，避免換月跳空）。
  抓大台/小台完整歷史（20+ 年）會需要幾分鐘。

### 2) 開啟 K 線 UI

```bash
python server.py            # 啟動並自動開瀏覽器（預設 http://127.0.0.1:8765）
python server.py --port 8800 --no-open
```

- 上方下拉選單切換商品；十字游標顯示 開/高/低/收/量。
- 資料直接讀 `data/` 內的 CSV，換商品即時載入。

## 檔案結構

```
market_data/
├── symbols.py          # 商品註冊表（新增商品在此加一筆）
├── intervals.py        # 時間刻度註冊表（日/60/30/15/5/1分）
├── download.py         # 下載 CLI（含增量更新 update_one）
├── server.py           # K 線 UI 本機伺服器 + 資料 API
├── build_exe.py        # 打包成單一 exe（PyInstaller）
├── sources/
│   ├── yahoo.py         # Yahoo Finance 來源
│   ├── taifex.py        # 台灣期交所官方來源（日盤）
│   ├── finlab_source.py # FinLab 來源（台指夜盤，選配，見上方限制）
│   └── tradingview.py   # tvDatafeed 備援（選配）
├── web/index.html      # Lightweight Charts 前端
└── data/               # 下載的 CSV（不入 git）
```

## 給回測用

`data/` 內的 CSV 是標準 OHLCV，回測腳本可直接讀：

```bash
cd ..
python reversal_pattern_study.py --local MNQ --interval 15m
python reversal_pattern_study.py --local TX  --interval 1d
```

（腳本會依 `<商品>_<刻度>_*.csv` 自動找檔，離線、可重現地回測。）
