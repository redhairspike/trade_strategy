# trade_strategy

Spike 的期貨交易策略系統 — 破底翻（False Breakdown Reversal）

## 策略概述

核心策略：**破底翻**（False Breakdown Reversal）
- 價格跌破支撐 → 引發止損獵殺 → 快速收回支撐之上 → 做多

交易商品：MNQ / MGC / MCL

多時間框架框架：
- 60K → 識別關鍵邊界與亞當底部
- 5m/15m → 找互換進場訊號

## 文件結構

```
trade_strategy/
├── CLAUDE.md              # Claude 閱讀上下文（策略完整摘要）
├── README.md              # 本文件
└── strategy/
    ├── trend_filter.md    # 趨勢濾網三關制
    ├── entry_rules.md     # 進場規則
    ├── instruments.md     # 各商品規則（MNQ/MGC/MCL）
    └── journal_lessons.md # 交易日誌學到的教訓
```

## 快速參考

### 三關濾網
1. **日線方向** → 偏空不打多
2. **60K 亞當底** → 無結構不進
3. **5m/15m 互換** → 在計畫支撐區才按

### 最重要的規則
- 被點後**等 15 分鐘**再看圖，避免情緒單
- 沒有 60K 亞當撐腰 = 這天不是你的菜
- 到壓力區才出場，不要太早跑

## 交易日誌

Notion：https://app.notion.com/p/3885599f72ba8039ba0bcc81fdeb8bd7
