# 專案進度 (Cowork ⇄ Code 共用)

> 每次完成一個任務就在此更新，讓 Cowork 模式與 Code 模式都能接手時知道目前狀態。
> 格式：日期 ｜ 執行者(Cowork/Code) ｜ 任務 ｜ 狀態 ｜ 產出/備註

---

## 目前狀態
- **最新完成**：進度與 SOP 更新已推上 GitHub main（2026-07-03，Code）
- **前一步**：Cowork 接手確認，回測結論已整合進 SOP（2026-07-03，Cowork）
- **進行中**：無
- **下一步候選**：
  1. 5m 資料接入（Yahoo 無 5m 歷史，需券商/付費資料或 Tradovate CSV 匯出）在真實時框直接驗證
  2. 根據 W底 結論更新開盤前檢查清單 Word 文件
  3. 繼續每日交易日誌更新（7/3 盤後）

---

## 進度日誌

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

### 2026-07-03 ｜ Cowork ｜ 接手確認 Code 成果 ｜ ✅ 完成
- 讀取 PROGRESS.md + trend_filter.md 確認 Code 回寫正確
- 更新「目前狀態」與下一步候選清單
- 結論已整合進第三關：「破底翻失敗 → 等 W 底第二低再進」

### 2026-07-03（前）｜ Cowork ｜ 建立策略系統與回測初版 ｜ ✅ 完成
- `CLAUDE.md`、`strategy/{trend_filter,adam_flip,journal_lessons,instruments}.md`
- `tools/adam_flip_calculator.py`、`tools/reversal_pattern_study.py`（初版）
- `tools/BACKTEST_HANDOFF.md`（交接給 Code）
