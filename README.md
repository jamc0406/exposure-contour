# exposure-contour：作業場所濃度分布圖 Skill

勞動部勞動及職業安全衛生研究所委託研究計畫成果。用對話完成作業場所有害物暴露濃度分布圖：由平面圖規劃測點、整理儀器紀錄成標準資料表、以普通克利金法製圖、以 RRMSE 與 MAPE 判斷圖面可信程度並提出補點建議、標示熱區與超過容許濃度範圍。計算方法與網頁版本工具 [ConcTour](https://jamc0406.github.io/ConcTour/) 相同。操作方式詳見《濃度分布圖製作技術手冊》。

## 下載

- **安裝檔：[exposure-contour.skill](dist/exposure-contour.skill)**（點進去後按右上角下載鍵），或到右側 [Releases](../../releases/latest) 下載最新版。

## 安裝（依使用的工具選一種）

### 1. Claude 網頁版、桌面版

1. 下載 `exposure-contour.skill`。
2. 「設定」→「功能」，打開「程式碼執行與檔案建立」。
3. 左側「自訂」→「技能」→「＋」→「上傳技能」，選擇剛下載的檔案。
4. 打開該技能的開關。

### 2. Claude Code

```
/plugin marketplace add jamc0406/exposure-contour
/plugin install exposure-contour@conctour
```

### 3. 其他 AI 工具通用（Claude Code、Codex、Cursor 等）

```
npx skills add jamc0406/exposure-contour
```

依畫面選擇要安裝到哪個工具；之後更新輸入 `npx skills update`。

## 使用

安裝後開新對話，上傳平面圖或量測資料，用一般講話的方式說明手上有什麼、要做什麼即可。提示詞範例見技術手冊附錄一。

## 版本紀錄

### 1.2（2026-11-13，對齊技術手冊 v5）

- 固定參考點漂移門檻改為兩段：10% 以下可接受；10%–30% 記錄於備註，判讀以相對高低為主；超過 30% 建議重新量測。
- 點位量測時間表中同一點在不同時間重複量測時，自動計算漂移並寫入該點備註與資料表 remark。
- 安裝檔統一命名為 `exposure-contour.skill`。

## 使用限制

濃度分布圖不得作為法定作業環境監測，或時量平均、短時間時量平均暴露評估的依據。一張圖只代表單一污染物、單一時段及單一高度。

## 資料夾

- `skills/exposure-contour/`：Skill 本體
- `dist/exposure-contour.skill`：給 Claude 網頁版、桌面版上傳用的安裝檔
- `.claude-plugin/`：Claude Code 安裝設定
