"""
從 Notion 匯出今日新聞到 data/news.json，並把照片、插畫存一份到專案裡。
由 .github/workflows/daily.yml 每天早上執行。

需要的 GitHub Secrets：
  NOTION_TOKEN      Notion integration 的金鑰
  NOTION_NEWS_DB    「新聞」資料庫 ID
  NOTION_DAYS_DB    「每日」資料庫 ID
欄位名稱見 README.md。缺任何一個 Secret 時直接跳過，不改任何檔案。
"""
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "news.json"
PHOTOS = ROOT / "photos"
ILLOS = ROOT / "illustrations"
PHOTO_WIDTH = 1200      # 存檔寬度，夠手機高解析度顯示
UA = "Mozilla/5.0 (taiwan-news digest bot)"

TOKEN = os.environ.get("NOTION_TOKEN", "")
NEWS_DB = os.environ.get("NOTION_NEWS_DB", "")
DAYS_DB = os.environ.get("NOTION_DAYS_DB", "")


# ---------- Notion ----------
def notion(path, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def query_all(db_id):
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = notion(f"databases/{db_id}/query", body)
        pages += res["results"]
        if not res.get("has_more"):
            return pages
        cursor = res["next_cursor"]


def text(prop):
    if not prop:
        return ""
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in prop[t]).strip()
    if t == "select":
        return (prop["select"] or {}).get("name", "")
    if t == "url":
        return prop["url"] or ""
    if t == "number":
        return prop["number"]
    if t == "checkbox":
        return prop["checkbox"]
    if t == "date":
        return ((prop["date"] or {}).get("start") or "")[:10]
    if t == "relation":
        return [r["id"].replace("-", "") for r in prop["relation"]]
    if t == "files":
        out = []
        for f in prop["files"]:
            out.append((f.get("file") or f.get("external") or {}).get("url", ""))
        return out
    return ""


def lines(s):
    return [x.strip() for x in str(s).splitlines() if x.strip()]


def split_row(line, n):
    parts = [p.strip() for p in re.split(r"[｜|]", line)]
    return (parts + [""] * n)[:n]


# ---------- 圖片 ----------
class OgImage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and not self.url and a.get("property") in ("og:image", "og:image:url"):
            self.url = a.get("content", "")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "")


def save_image(src, dest):
    """src 可以是圖片網址或新聞文章網址（會抓文章的分享封面圖）。成功回傳相對路徑。"""
    if dest.exists():
        return dest.relative_to(ROOT).as_posix()
    if not src:
        return ""
    try:
        from PIL import Image
        raw, ctype = fetch(src)
        if "html" in ctype:
            p = OgImage()
            p.feed(raw.decode("utf-8", "ignore"))
            if not p.url:
                return ""
            raw, _ = fetch(urllib.parse.urljoin(src, p.url))
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > PHOTO_WIDTH:
            img = img.resize((PHOTO_WIDTH, round(img.height * PHOTO_WIDTH / img.width)))
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "WEBP", quality=78)
        return dest.relative_to(ROOT).as_posix()
    except Exception as e:  # 一張圖失敗不影響整體
        print(f"  照片下載失敗 {src}: {e}", file=sys.stderr)
        return ""


# ---------- 轉換 ----------
def to_news(page):
    P = page["properties"]
    nid = page["id"].replace("-", "")[:12]
    date = text(P.get("日期"))
    sides = [dict(zip(("label", "text", "source"), split_row(l, 3))) for l in lines(text(P.get("各方說法")))]
    sources = [dict(zip(("name", "url"), split_row(l, 2))) for l in lines(text(P.get("來源")))]
    photo_path = save_image(text(P.get("照片網址")), PHOTOS / date / f"{nid}.webp")
    return {
        "id": nid,
        "date": date,
        "category": text(P.get("分類")) or "社會",
        "title": text(P.get("標題")),
        "summary": text(P.get("摘要")),
        "keyPoints": lines(text(P.get("重點"))),
        "body": [b.strip() for b in re.split(r"\n\s*\n", text(P.get("經過"))) if b.strip()],
        "sides": sides,
        "check": {
            "status": "verified" if text(P.get("查證狀態")) == "已查證" else "partial",
            "note": text(P.get("查證說明")),
        },
        "sources": sources,
        "photo": {
            "url": photo_path,
            "caption": text(P.get("照片說明")),
            "credit": text(P.get("照片出處")),
        },
        "related": [r[:12] for r in (text(P.get("相關前情")) or [])],
        "readMin": text(P.get("閱讀分鐘")) or 3,
        "featured": bool(text(P.get("頭條"))),
    }


def to_day(page):
    P = page["properties"]
    date = text(P.get("日期"))
    files = text(P.get("插畫")) or []
    illo = save_image(files[0] if files else "", ILLOS / f"{date}.webp")
    return {
        "date": date,
        "updatedAt": text(P.get("更新時間")) or "08:30",
        "oneLiner": text(P.get("今日一句話")),
        "illustration": {"url": illo, "alt": "今日插畫"},
    }


def main():
    if not (TOKEN and NEWS_DB and DAYS_DB):
        print("尚未設定 NOTION_TOKEN / NOTION_NEWS_DB / NOTION_DAYS_DB，跳過。")
        return
    news = [to_news(p) for p in query_all(NEWS_DB)]
    news = [n for n in news if n["date"] and n["title"]]
    days = [to_day(p) for p in query_all(DAYS_DB)]
    days = [d for d in days if d["date"]]
    from datetime import datetime, timezone, timedelta
    out = {
        "generatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "sample": False,
        "days": sorted(days, key=lambda d: d["date"], reverse=True),
        "news": sorted(news, key=lambda n: n["date"], reverse=True),
    }
    DATA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"匯出 {len(days)} 天、{len(news)} 則新聞。")


if __name__ == "__main__":
    main()
