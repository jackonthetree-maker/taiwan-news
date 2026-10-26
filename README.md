# taiwan-news

新聞中立分析平台的網頁版。手機優先，每天早上自動從 Notion 同步。

網站：https://jackonthetree-maker.github.io/taiwan-news/

## 每天的流程

| 時間（台灣） | 誰 | 做什麼 |
|---|---|---|
| 06:21 | Claude 排程「台灣新聞每日彙整」 | 照 Notion《📘 執行手冊》整理新聞，寫進 Notion，最後把每日總覽設成「已完成／部分完成」 |
| 08:31 | Claude 排程「台灣新聞補跑檢查」 | 早上沒跑完才接手補完 |
| 08:07～10:37 每半小時 | GitHub Actions「每日同步 Notion」 | 執行 `scripts/sync_notion.py`，有新資料才更新網站 |
| 每月 1 號 09:51 | Claude 排程「新聞網站每月檢查」 | 檢查網站大小、同步紀錄、照片是否齊全 |

分工：網頁、寫法規則、Notion 欄位由網頁這邊的 chat 維護（直接改執行手冊與主頁）；每日排程只照執行手冊執行。

## 網站頁面

| 網址 | 內容 |
|---|---|
| `#today` | 首頁：類別分頁，每類依「主要性質 → 查證狀態 → 排序」自動排列 |
| `#e-日期-ID` | 事件頁：總結 → 前情 → 事實 → 各方怎麼說（人物／媒體）→ 查證與來源（摺疊） |
| `#claims` | 查證結果：依新聞分組；追蹤中、久未舉證收在摺疊區 |
| `#principles` | 說明：性質、排序、媒體立場、標記、做法（網頁自己的精簡版） |
| `#d-日期`、`#archive` | 舊的日期頁，導覽裡不顯示，供前情等連結使用 |

## 資料檔

| 檔案 | 內容 |
|---|---|
| `data/index.json` | 有哪些日期、最新是哪天 |
| `data/days/日期.json` | 當天全部事件（含內文） |
| `data/claims.json` | 爆料查證追蹤的全部說法 |
| `photos/日期/事件ID.webp` | 每則新聞的照片（取「來源連結」第一個網址的分享圖） |
| `illustrations/日期.webp` | 每日插畫（每日總覽頁面的封面圖，選用） |

同步程式只採用「執行狀態」為已完成或部分完成的每日總覽；試跑、作廢的事件不會出現在網站或前情連結裡。

## 設定

- GitHub Secret `NOTION_TOKEN`：Notion integration 的金鑰（integration 需連到「新聞中立分析平台」主頁）。
- 資料庫 ID 寫在 `scripts/sync_notion.py` 最上面。
- 想馬上更新網站：Actions →「每日同步 Notion」→ Run workflow。
