# taiwan-news

每日台灣新聞彙整網頁。手機優先，每天早上自動從 Notion 更新。

## 運作方式

1. 新聞整理好後寫進 Notion 的兩個資料庫：「新聞」與「每日」。
2. GitHub Actions 每天台灣時間 07:17 執行 `scripts/export_notion.py`：
   - 讀 Notion，輸出 `data/news.json`
   - 下載每則新聞的照片，存到 `photos/日期/新聞ID.webp`
   - 下載當天插畫，存到 `illustrations/日期.webp`
3. 有變動就自動存回專案，GitHub Pages 會跟著更新網頁。

網頁 `index.html` 只讀 `data/news.json`，不直接接觸 Notion，金鑰不會出現在網頁上。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `index.html` | 網頁本身 |
| `data/news.json` | 所有新聞資料（目前是範例） |
| `photos/` | 新聞照片，依日期分資料夾 |
| `illustrations/` | 每日 AI 插畫 |
| `scripts/export_notion.py` | Notion → news.json 匯出程式 |
| `.github/workflows/daily.yml` | 每日排程 |

## Notion 資料庫欄位

### 「新聞」資料庫

| 欄位名稱 | 類型 | 說明 |
|---|---|---|
| 標題 | 標題 | |
| 日期 | 日期 | 屬於哪一天的彙整 |
| 分類 | 選項 | 政治／社會／科技／生活／國際 |
| 摘要 | 文字 | 約 50 字 |
| 重點 | 文字 | 一行一點 |
| 經過 | 文字 | 段落之間空一行 |
| 各方說法 | 文字 | 一行一方：`標籤｜立場摘要｜出處` |
| 查證狀態 | 選項 | 已查證／部分待查證 |
| 查證說明 | 文字 | |
| 來源 | 文字 | 一行一家：`媒體名稱｜文章網址` |
| 照片網址 | 網址 | 圖片網址或新聞文章網址（文章網址會自動抓分享封面圖） |
| 照片說明 | 文字 | |
| 照片出處 | 文字 | 媒體／攝影者 |
| 相關前情 | 關聯（連到「新聞」本身） | |
| 閱讀分鐘 | 數字 | |
| 頭條 | 核取方塊 | 每天勾一則 |

### 「每日」資料庫

| 欄位名稱 | 類型 | 說明 |
|---|---|---|
| 日期 | 日期 | |
| 今日一句話 | 文字 | |
| 插畫 | 檔案 | 當天的 AI 插畫 |
| 更新時間 | 文字 | 例如 `08:30` |

## 接上 Notion 時要做的事

1. 在 Notion 建立 integration，拿到金鑰，並把兩個資料庫分享給它。
2. 到 GitHub 專案 Settings → Secrets and variables → Actions，新增：
   - `NOTION_TOKEN`
   - `NOTION_NEWS_DB`（「新聞」資料庫 ID）
   - `NOTION_DAYS_DB`（「每日」資料庫 ID）
3. 到 Actions 頁面手動執行一次「每日更新新聞」確認。

沒設定這三個 Secret 前，排程會直接跳過，網頁繼續顯示範例資料。
