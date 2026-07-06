# 專案進度 (Cowork ⇄ Code 共用)

> 每次完成一個任務就在此更新，讓 Cowork 模式與 Code 模式都能接手時知道目前狀態。
> 格式：日期 ｜ 執行者(Cowork/Code) ｜ 任務 ｜ 狀態 ｜ 產出/備註

---

## 目前狀態
- **最新完成**：Cowork 接手確認，回測結論已整合進 SOP（2026-07-03，Cowork）
- **進行中**：無
- **下一步候選**：
  1. 5m 資料接入（Yahoo 無 5m 歷史，需券商/付費資料或 Tradovate CSV 匯出）在真實時框直接驗證
  2. 根據 W底 結論更新開盤前檢查清單 Word 文件
  3. 繼續每日交易日誌更新（7/3 盤後）

---

## 進度日誌

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
