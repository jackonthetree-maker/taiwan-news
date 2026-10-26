# taiwan-news

新聞中立分析平台的網頁版。手機優先，每天早上自動從 Notion 同步。

網站：https://jackonthetree-maker.github.io/taiwan-news/

## 運作方式

1. 新聞整理程式每天 06:21 開始，約 9 點前把當天資料寫進 Notion。
2. GitHub Actions 在台灣時間 09:07、10:07 各跑一次 `scripts/sync_notion.py`：
   - 讀 Notion 五個資料庫和主頁的編輯原則
   - 輸出網頁用的 JSON 到 `data/`
   - 抓每則事件第一個來源的分享封面圖，存到 `photos/日期/事件ID.webp`
   - 「每日總覽」頁面若有封面圖，當作當天插畫存到 `illustrations/日期.webp`
3. 有變動就自動存回專案，GitHub Pages 約一分鐘後更新。

網頁只讀 `data/` 裡的檔案，不直接接觸 Notion，金鑰不會出現在網頁上。

## 頁面

| 網址 | 內容 |
|---|---|
| `#today` | 首頁，只放最新一天：今日三件重點、追蹤更新、事件列表 |
| `#e-日期-ID` | 事件內頁：一句話看懂 → 已確認的事實 → 各方說法 → 各家報導的差異 → 查證說明 → 看完你可以怎麼想 → 前情 → 來源 |
| `#claims` | 查證追蹤：所有說法與狀態，可依狀態、發言者、政黨篩選 |
| `#archive`、`#d-日期` | 歷史歸檔，一天一頁 |
| `#principles` | 編輯原則 |

## 資料檔

| 檔案 | 內容 |
|---|---|
| `data/index.json` | 有哪些日期、最新是哪天 |
| `data/days/日期.json` | 當天總覽與全部事件（含內文） |
| `data/claims.json` | 爆料查證追蹤的全部說法 |
| `data/principles.json` | 主頁的「編輯原則、說法分類、不實說法處理、選題原則」 |

首頁只讀 `index.json` 和最新一天的檔案，歷史資料再多也不會變慢。

## Notion 對應

| Notion | 用在 |
|---|---|
| 🗞️ 每日事件 | 事件卡片與內頁。屬性：事件標題、一句話摘要、類別、內容性質、查證狀態、排序、比對媒體數、獨立來源數、立場缺口、來源連結、議題、爆料查證。內文用「## 標題」分段 |
| 📅 每日總覽 | 今日三件重點、追蹤更新（一行一則，最多 5 則）、涵蓋時段。「執行狀態」為已完成或部分完成才會上網頁 |
| 🔍 爆料查證追蹤 | 查證追蹤頁、事件內頁的相關查證 |
| 🧵 議題追蹤 | 前情：同一議題、日期較早的事件 |
| 📰 來源名單 | 來源的立場標示（依網址網域比對） |

資料庫 ID 寫在 `scripts/sync_notion.py` 最上面。

## 第一次接上 Notion

1. 到 https://www.notion.so/profile/integrations 建立一個 internal integration，權限只要「讀取內容」，複製它的金鑰。
2. 在 Notion 打開「新聞中立分析平台」主頁 → 右上角 ⋯ → 連線（Connections）→ 加入剛建立的 integration。底下的資料庫會一起授權。
3. 到 GitHub 專案 Settings → Secrets and variables → Actions → New repository secret，名稱 `NOTION_TOKEN`，貼上金鑰。
4. 到 Actions → 「每日同步 Notion」→ Run workflow，手動跑一次確認。

沒設定 `NOTION_TOKEN` 前，排程會直接跳過，網頁繼續顯示目前的預覽資料。
