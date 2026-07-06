# K 棒資料下載 + K 線檢視器

下載每日 K 棒 CSV（供回測用），並用 TradingView 官方開源的 Lightweight Charts 呈現。

## 支援商品

| 代碼 | 名稱 | 來源 | 備註 |
|------|------|------|------|
| MNQ | 微型納斯達克 | Yahoo（NQ=F 代理） | 美股 |
| MGC | 微型黃金 | Yahoo（GC=F 代理） | 美股 |
| MCL | 微型原油 | Yahoo（CL=F 代理） | 美股 |
| TX  | 大台（臺股期貨） | TAIFEX 官方 | 1998 上市，歷史最長，**回測首選** |
| MTX | 小台（小型臺指） | TAIFEX 官方 | 2001 上市，歷史長，**回測首選** |
| TMF | 微台（微型臺指） | TAIFEX 官方 | 2024 才上市，僅 ~1 年，供近期實盤對照 |

> 微台/小台/大台追蹤同一個加權指數，K 線走勢一致，差別只在合約規格。
> **建議用大台/小台的長歷史回測，訊號直接適用於實際交易的微台。**

## 安裝

```bash
pip install yfinance requests pandas
# 選配（官方來源抓不到時的備援）：
pip install tvDatafeed        # 需設環境變數 TV_USERNAME / TV_PASSWORD
```

## 用法

### 最簡單：全部在網頁上做（推薦）

```bash
python serve.py            # 啟動並自動開瀏覽器
```

網頁上就能：
- **下載 / 更新**：選商品 + 起始日 → 按「下載」，後端即時下載，完成後自動顯示該商品 K 線。
- **檢視**：上方「檢視」下拉切換已下載商品；十字游標顯示 開/高/低/收/量。

不用再開終端機跑下載指令。長歷史（如大台 20+ 年）下載時網頁會顯示進度，下載在背景執行不卡頁面。

### 或用 CLI 下載（等同網頁的下載鈕）

```bash
python download.py                     # 全部商品
python download.py MNQ 大台 小台          # 指定（可用中英別名）
python download.py MNQ --start 2015-01-01
python download.py --list              # 列出可用商品
```

輸出：`data/<KEY>_1d.csv`，欄位 `Date,Open,High,Low,Close,Volume`。

- 美股（Yahoo）：一次下載完整歷史。
- 台指（TAIFEX）：因官方單次查詢上限 1 個月，程式**自動逐月分段**下載，
  並以「每日成交量最大的合約月份」組成連續日K（近似連續合約，避免換月跳空）。
  抓大台/小台完整歷史（20+ 年）會需要幾分鐘。

### 2) 開啟 K 線 UI

```bash
python serve.py            # 啟動並自動開瀏覽器（預設 http://127.0.0.1:8765）
python serve.py --port 8800 --no-open
```

- 上方下拉選單切換商品；十字游標顯示 開/高/低/收/量。
- 資料直接讀 `data/` 內的 CSV，換商品即時載入。

## 檔案結構

```
market_data/
├── symbols.py          # 商品註冊表（新增商品在此加一筆）
├── download.py         # 下載 CLI
├── serve.py            # K 線 UI 本機伺服器 + 資料 API
├── sources/
│   ├── yahoo.py        # Yahoo Finance 來源
│   ├── taifex.py       # 台灣期交所官方來源
│   └── tradingview.py  # tvDatafeed 備援（選配）
├── web/index.html      # Lightweight Charts 前端
└── data/               # 下載的 CSV（不入 git）
```

## 給回測用

`data/<KEY>_1d.csv` 是標準 OHLCV，可直接餵給 `../reversal_pattern_study.py`
之類的回測腳本（例如改讀本地 CSV 而非 Yahoo，就能離線、可重現地回測台指）。
