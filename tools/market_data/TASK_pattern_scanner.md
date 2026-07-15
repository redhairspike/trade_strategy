# Task: 整合 2B/頭肩底型態掃描器 進 market_data tool

## 目標
在 `trade_strategy/tools/market_data/` 裡新增型態掃描功能，掃描 2B法則（= 破底翻）和頭肩底型態。

## 現有架構
- `server.py`：本機 HTTP server，提供 /data API 和前端
- `web/index.html`：Lightweight Charts 前端，已有水平線/手繪功能
- `sources/`：yahoo.py / taifex.py 資料來源
- `data/`：下載好的 OHLCV CSV（欄位：Datetime, Open, High, Low, Close, Volume）
- `reversal_pattern_study.py`：已有破底翻統計腳本（可參考）

## 要新增的功能

### 1. 新增 pattern_scanner.py
輸入：OHLCV DataFrame（從現有 data/ CSV 讀取）
輸出：偵測到的型態清單，每筆包含：
  - pattern_type: "2B" or "HnS_bottom"
  - head_idx: 頭部K棒位置（第一低）
  - right_shoulder_idx: 右肩K棒位置（第二低）
  - entry_idx: 進場K棒位置（右肩反彈確認）
  - support_level: 支撐價位
  - head_volume: 頭部成交量
  - right_shoulder_volume: 右肩成交量
  - volume_ok: bool（右肩量 < 頭部量）

### 2B 型態偵測邏輯（依照破底翻演算法）
- 找局部低點（local minimum）作為「頭部」
- 頭部前需有下跌趨勢（N根K棒高點序列向下）
- 頭部K棒：破底放量（volume > 近期均量 * 1.2）
- 頭部後 1-4 根K棒反彈 ≥ 0.3%
- 再回測：第二低（右肩）不破頭部低點
- 右肩縮量：right_shoulder_volume < head_volume
- 右肩反彈後收紅K = 進場點

### 頭肩底偵測邏輯
- 找三個低點：左肩、頭（最低）、右肩（左右肩高度相近）
- 頸線 = 左肩高點和右肩高點連線
- 頭部量 > 左肩量（放量創低）
- 右肩量 < 頭部量（縮量 = 耗盡）
- 頸線突破 = 進場訊號

### 2. 整合進 server.py
新增 API endpoint：`GET /patterns?symbol=MNQ&interval=5m`
回傳 JSON：`{ "patterns": [...] }`

### 3. 整合進 web/index.html
在圖表上疊加型態標記：
- 頭部：紅色向下三角
- 右肩：橘色圓點
- 進場點：綠色向上三角
- 支撐線：虛線水平線（與現有水平線功能整合）
新增「型態掃描」按鈕，點擊後呼叫 /patterns API 並在圖表顯示結果

## 規格參考
- 完整演算法規則：`D:/AI/Claude_Cowork_Projects/破底翻/破底翻_演算法.md`
- 現有型態研究：`tools/reversal_pattern_study.py`

## 完成標準
- [ ] pattern_scanner.py 可獨立執行，輸出型態清單
- [ ] server.py 有 /patterns endpoint
- [ ] 網頁圖表可視化顯示掃描結果
- [ ] 至少用 MNQ 5m 資料測試驗證
