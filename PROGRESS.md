# 專案進度 (Cowork ⇄ Code 共用)

> 每次完成一個任務就在此更新，讓 Cowork 模式與 Code 模式都能接手時知道目前狀態。
> 格式：日期 ｜ 執行者(Cowork/Code) ｜ 任務 ｜ 狀態 ｜ 產出/備註

---

## 目前狀態
- **最新完成**：7/10 盤後檢討 + 日內虧損控制規則新增（2026-07-11，Cowork）
- **Code 最新**：K 線 UI 畫筆（自由手繪型態，黃色）已 Spike 實測確認 OK（2026-07-11）
- **進行中**：無
- **下一步候選**：
  1. 開盤前檢查清單 Word 文件 → 更新加入所有新規則（開盤價撐壓、W底試單、有子彈彈性、日內虧損控制）
  2. 5m 回測資料接入（reversal_pattern_study.py 已支援 5m，跑一次拿數字）
  3. 繼續每日交易日誌更新

---

## 進度日誌

### 2026-07-08 ｜ Code ｜ 畫筆（自由手繪型態）｜ ✅ 完成（7/11 Spike 實測確認）
- 圖上疊一層 canvas，畫筆自由手繪；每筆存 K 棒座標 [logical, price]，
  用 coordinateToLogical/logicalToCoordinate + coordinate/priceToCoordinate 換算，跟著縮放平移
- 按鈕：✏ 畫筆（與水平線互斥）、⟲ 復原、清除（清水平線＋手繪）；依商品存 localStorage
- 修：canvas 需 width/height:100%（replaced element，inset:0 不撐開）；chart 改 autoSize
- 已驗證：載入無 JS 錯誤、按鈕/函式齊全、canvas 正確填滿、pointerdown 進得去、資料 631 根
- 7/8 preview 分頁被隱藏(document.hidden)無法截圖視覺驗證；
  **7/11 Spike 實機測試確認：能畫黃色線、縮放平移跟著 K 棒，OK ✅**
- 7/11 畫筆顏色由藍改黃（#ffeb3b）

### 2026-07-07 ｜ Code ｜ 畫水平線功能 ｜ ✅ 完成
- web/index.html 用 Lightweight Charts createPriceLine 實作：按鈕切換畫線模式，
  點圖表新增水平線（虛線+價格標籤）、點既有線刪除、「清除」清空
- 線依商品存 localStorage，換時框/重整/重開都保留（loadData 時 renderStoredLines 還原）
- preview 實測：新增/持久化/點擊刪除 皆通過，無 console 錯誤
- 因 UI 改動，重新 build exe（web 打包在內）

### 2026-07-07 ｜ Code ｜ 打包成 exe ｜ ✅ 完成
- 新增 `build_exe.py`（PyInstaller，--onefile + 打包 web/ + collect yfinance/curl_cffi）
- server.py/download.py 加 frozen 判斷：web 讀 exe 內資源、data 放 exe 旁邊（可寫可保存）
- 產出 `dist/kbar-server.exe`（~85MB）；`.gitignore` 排除 build/ dist/ *.spec
- **實測**：exe 啟動、serve UI/API、透過 exe 下載 MCL 631 根成功（bundled yfinance/curl_cffi 正常）

### 2026-07-07 ｜ Code ｜ 檔名加日期 + 改名 server.py + 舊版偵測 ｜ ✅ 完成
- CSV 檔名改 `<商品>_<刻度>_<起>_<迄>.csv`（如 `MNQ_15m_2026-04-24_2026-07-06.csv`）；
  download.py 加 save_csv/find_csv/csv_glob，每商品每刻度只留一份（更新自動刪舊檔）
- server.py/reversal 改用 glob 找檔，相容舊命名（fallback）
- `serve.py` → 改名 `server.py`（含 README、launch.json、啟動提示）
- **UI 加舊版伺服器偵測**：載入時檢查 /api/intervals，若後端是舊版就顯示明確提示要重啟，
  不再給空白下拉+`Unexpected token '<'`（這次卡住的根因是殘留舊 serve.py 行程）
- 實測：CLI/UI 下載都產生日期檔名、舊檔自動清除、回測與圖表都正確讀到

### 2026-07-07 ｜ Code ｜ 回測接分鐘 CSV ｜ ✅ 完成
- `reversal_pattern_study.py` 加 `--interval`（1d/60m/30m/15m/5m/1m），load_csv 支援 Datetime 欄位
- 各刻度用對應參數（LOCAL_PARAMS）；用法：`--local MNQ --interval 15m`
- **結果**：MNQ 15分 需二次測試 60.0%（✅支持）、60分 41.4%、日 ~22% → 時框梯度一致
- 與先前 live-Yahoo 數字吻合（15m ~59% / 1h ~41%），證明本地 CSV 回測可重現
- 印證 trend_filter.md 第三關「等W底第二低」規則在 Spike 實際時框（5m/15m）成立

### 2026-07-07 ｜ Code ｜ 多時間刻度 + 更新全部 ｜ ✅ 完成
- 新增 `intervals.py`：支援 日/60/30/15/5/1分
- Yahoo 來源擴充分鐘K（美股）；分鐘 CSV 首欄 Datetime（交易所當地時間）
- CSV 命名改 `<KEY>_<刻度>.csv`；download.py 加 `--interval` 與增量更新 `update_one`
- serve.py：/api/data 帶 interval、/api/intervals、/api/update_all；分鐘時間轉 epoch 供圖表顯示盤中時間
- UI：檢視加「時間刻度分段鈕」（依該商品已下載刻度）、下載列加刻度選單、加「↻ 更新全部」鈕
- 台指+分鐘會提示「需券商 API（Shioaji）」；架構已預留，之後接 Shioaji 只加一個 source
- **實測（preview）**：MNQ 15m/60m 下載並顯示（時間軸正確）、TAIFEX 分鐘正確擋下、更新全部 7/7 增量成功且大台 4044 根歷史零重複

### 2026-07-06 ｜ Code ｜ K 線 Web UI 整合線上下載 ｜ ✅ 完成
- `serve.py` 加下載端點：POST /api/download（背景執行緒）+ GET /api/download_status（輪詢進度）+ /api/instruments
- `web/index.html` 加「下載/更新」控制列：選商品+起始日→按鈕下載，完成後自動切到該商品顯示
- 免再開終端機跑 download.py；長下載走背景不卡頁面，網頁顯示進度
- preview 實測：從網頁下載 MGC（880 根）→ 狀態✓ → 圖表自動顯示黃金 K 線，全流程通過

### 2026-07-06 ｜ Code ｜ 回測接本地 CSV + 大台日線回測 ｜ ✅ 完成
- `reversal_pattern_study.py` 新增 `--local <代碼>` / `--csv <路徑>` 模式，直接吃 market_data 的 CSV
- 下載大台 TX / 小台 MTX 2010→2026（各 ~4044 根日K）
- **大台 16 年日線回測**：176 個重大反轉，W底+複雜底 22.2%、V型 77.8%，雙底假陽性率 0%
- **跨市場一致**：美股 NQ 日線 ~22% W、大台日線 ~22% W → 日線層級反轉多為 V 型，
  W 底主導只在分鐘級（5m/15m）出現。台指 W 底假說仍待分鐘資料才能驗證（TAIFEX 只有日K）
- 下一步候選：接分鐘資料源（券商 API）才能驗證台指 5m/15m 的「等W底第二低」

### 2026-07-06 ｜ Code ｜ K 棒資料下載器 + K 線 UI ｜ ✅ 完成
- 新增 `tools/market_data/`：下載每日 K 棒 CSV + Lightweight Charts K 線 UI
- 資料來源：免費官方為主 —— 美股期貨(MNQ/MGC/MCL)走 Yahoo；台指(大台TX/小台MTX/微台TMF)走 TAIFEX 官方；tvDatafeed 備援
- 重點發現：微台 TMF 2024-07-29 才上市（僅 ~1 年），大台/小台歷史 20+ 年 →
  **回測用大台/小台，下單看微台**（同追蹤加權指數，K 線一致）
- TAIFEX 官方單次查詢上限 1 個月 → 程式自動逐月分段 + 取每日最活躍合約組連續日K
- UI 已用 preview 驗證：MNQ(Yahoo) 與 MTX(TAIFEX) 均正確渲染 K 棒+成交量
- `.gitignore` 加 `tools/market_data/data/*.csv`（可重新下載，不入庫）

### 2026-07-03 ｜ Code ｜ 安全性：清掉 remote URL 內嵌 token ｜ ✅ 完成
- 舊 remote URL 內嵌了明文 PAT（外洩風險）→ `git remote set-url` 換成乾淨 URL
- 改用 Git Credential Manager（manager-core）管理憑證，`.git/config` 不再存 token
- 舊 token 已於 GitHub 撤銷、重發新 token（由 Spike 於網站操作）

### 2026-07-03 ｜ Code ｜ 推上 GitHub ｜ ✅ 完成
- commit `25e4315` push 到 `origin/main`（含回測腳本、SOP 更新、PROGRESS.md）
- 新增 `.gitignore`：回測產出圖 `tools/*.png` 與 `__pycache__` 不入庫

### 2026-07-03 ｜ Code ｜ 破底翻假說回測 ｜ ✅ 完成
- 完善 `tools/reversal_pattern_study.py`，修正 BACKTEST_HANDOFF.md 列出的 5 個已知問題
  （破底翻偵測、W底嚴謹度、完整失敗序列、多時框對齊、統計指標）+ 2 個執行期 bug（UTF-8、tz）
- 加 `--selftest` 離線自檢；實跑 NQ=F（日K/1h/30m/15m）通過
- **結論**：假說要看時框——整體 V 型仍多數，但時框越細越需二次測試（日K 22% → 15m 59%）；
  Spike 打的 5m/15m 上約 6 成反轉需等第二低，假陽性率僅 8~14%
- **已回寫 SOP**：
  - `strategy/trend_filter.md` 第三關 → 新增「破底翻失敗就等 W 底第二低」進場規則
  - `strategy/journal_lessons.md` → 新增「回測驗證」章節 + 學習閉環連結
- 輸出圖：`tools/reversal_patterns_{daily,1h,30m,15m}.png`、`reversal_interval_hist.png`

### 2026-07-11 ｜ Cowork ｜ 7/10 盤後檢討 + 日內虧損控制規則 ｜ ✅ 完成
- 分析 7/10 Performance CSV + Notion（+$955.5，回測高檔盤整）
- 4 次進場：進場3急進 -$124，進場4 W底第二低 +$1,068（全日獲利來源）
- 確認夜盤口數放大的依據：虧損 < $650 的 50%（$325）= 允許放大
- **新增 SOP「日內虧損控制」規則**（`CLAUDE.md` + `trend_filter.md`）：
  - $325 = 警戒線（回到基本口數）
  - $650 = 強制收工臨界點（根據自觀察回測的心理失控門檻）
- 更新：`journal_lessons.md`（七月績效表補 7/7、7/10；7/10 教訓段落；學習閉環）

### 2026-07-09 ｜ Cowork ｜ 7/7 盤後檢討 + SOP 補充 ｜ ✅ 完成
- 分析 7/7 Performance CSV + Notion（-$779，多方必死盤仍打多，連虧後口數加大）
- 核心問題：連虧後口數從 2→6 口試圖翻本，7 個交易群組全虧
- 討論趨勢濾網補充：確認「日K 高低點序列」對 7/7 無效（7/3、7/5 均 HH+HL，日K 看多）
- 真正有效的攔截點是「60K 連續空方亞當第二次出現即停」（第二關執行問題，非缺少濾網）
- **新增 SOP「開盤價撐壓規則」**（`trend_filter.md` + `CLAUDE.md`）：
  - 回踩開盤價 = 支撐；反彈撞開盤價 = 壓力
  - ⭐ 前一日出現下尖尖 → 隔天開盤價升格為主要支撐，回踩**強制尋找多方進場**
  - 止損設在昨日下尖尖低點以下

### 2026-07-09 ｜ Cowork ｜ 7/8 盤後檢討 + SOP 更新 ｜ ✅ 完成
- 分析 7/8 Performance CSV + Notion 日誌，+$1,225 盤後拆解
- 發現晚盤三次試底 = W底結構（19:10/19:12 失敗，19:17 確認）
- **新增 SOP「有子彈彈性規則」**：加碼許可 + 試單提升至 3 次（縮口 1 口）
- 更新：`trend_filter.md`（新增🟢彈性規則區塊）、`CLAUDE.md`（停損規則段）、`journal_lessons.md`（7/8 段落 + 學習閉環）

### 2026-07-03 ｜ Cowork ｜ 接手確認 Code 成果 ｜ ✅ 完成
- 讀取 PROGRESS.md + trend_filter.md 確認 Code 回寫正確
- 更新「目前狀態」與下一步候選清單
- 結論已整合進第三關：「破底翻失敗 → 等 W 底第二低再進」

### 2026-07-03（前）｜ Cowork ｜ 建立策略系統與回測初版 ｜ ✅ 完成
- `CLAUDE.md`、`strategy/{trend_filter,adam_flip,journal_lessons,instruments}.md`
- `tools/adam_flip_calculator.py`、`tools/reversal_pattern_study.py`（初版）
- `tools/BACKTEST_HANDOFF.md`（交接給 Code）
