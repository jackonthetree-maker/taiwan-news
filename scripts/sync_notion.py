"""
Notion → 網頁資料同步。由 .github/workflows/daily.yml 每天執行。

輸出（全部在 data/）：
  index.json            有哪些日期、最新是哪天（首頁先讀這個）
  days/YYYY-MM-DD.json  某一天的總覽與全部事件（首頁、歸檔頁讀這個）
  claims.json           爆料查證追蹤的全部說法（查證追蹤頁）
照片存在 photos/日期/事件ID.webp；每日插畫（每日總覽頁面的封面圖）存在 illustrations/日期.webp。

只需要一個 GitHub Secret：NOTION_TOKEN。沒設定就跳過，不改任何檔案。
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

# ---------- 設定 ----------
DS = {
    "events": "c9f8ff49-5877-4dae-83ad-8a61690722df",   # 🗞️ 每日事件
    "days": "25c68d69-6996-40a2-a79d-f4fb8f743eb3",     # 📅 每日總覽
    "claims": "bf09159e-0d9e-4da6-b80a-a47ee251a824",   # 🔍 爆料查證追蹤
    "issues": "560a6a9b-3f53-44be-bc05-ca1199973a27",   # 🧵 議題追蹤
    "sources": "e9c53626-9ee4-4516-80d0-fb15983ff9ea",  # 📰 來源名單
}
MAIN_PAGE = "4057fddd-d2f4-80c1-a14f-f4301db58d27"      # 新聞中立分析平台
PRINCIPLE_SECTIONS = ["編輯原則", "說法分類", "不實說法處理", "選題原則"]
PUBLISH_STATUS = {"已完成", "部分完成"}                 # 每日總覽「執行狀態」是這些才上網頁
MAX_FOLLOWUPS = 5
MAX_PRIOR = 5
PHOTO_WIDTH = 1200
TZ = timezone(timedelta(hours=8))

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PHOTOS = ROOT / "photos"
ILLOS = ROOT / "illustrations"
UA = "Mozilla/5.0 (compatible; taiwan-news-sync)"

LEAN = {"一般認為偏綠": "green", "一般認為偏藍": "blue", "中立基準": "neutral"}


# ---------- Notion API ----------
class Notion:
    def __init__(self, token):
        self.token = token

    def _call(self, path, body=None):
        for attempt in range(5):
            req = urllib.request.Request(
                "https://api.notion.com/v1/" + path,
                data=json.dumps(body).encode() if body is not None else None,
                method="POST" if body is not None else "GET",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": "2025-09-03",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Notion {path}: {e.code} {e.read()[:300]!r}")

    def query(self, ds_id):
        rows, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            res = self._call(f"data_sources/{ds_id}/query", body)
            rows += res["results"]
            if not res.get("has_more"):
                return rows
            cursor = res["next_cursor"]

    def children(self, block_id):
        """回傳區塊清單；有子區塊的會放在 _children。"""
        out, cursor = [], None
        while True:
            q = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            res = self._call(f"blocks/{block_id}/children{q}")
            for b in res["results"]:
                if b.get("has_children") and b["type"] not in ("child_page", "child_database"):
                    b["_children"] = self.children(b["id"])
                out.append(b)
            if not res.get("has_more"):
                return out
            cursor = res["next_cursor"]


# ---------- 屬性讀取 ----------
def nid(page_id):
    return page_id.replace("-", "")


def prop(page, name):
    p = page["properties"].get(name)
    if not p:
        return None
    t = p["type"]
    v = p.get(t)
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in v).strip()
    if t == "select":
        return (v or {}).get("name")
    if t == "multi_select":
        return [o["name"] for o in v]
    if t in ("number", "url", "checkbox", "created_time", "last_edited_time"):
        return v
    if t == "date":
        return ((v or {}).get("start") or "")[:10] or None
    if t == "relation":
        return [nid(r["id"]) for r in v]
    return None


URL_RE = re.compile(r"https?://[^\s;，、)）\]]+")


def urls_in(text):
    return URL_RE.findall(text or "")


# 舊類別 → 新的 4 類（Notion 選項改完後舊資料也照新分類顯示）
CATEGORY_ALIAS = {"社會": "社會・生活", "經濟": "財經・科技", "科技產業": "財經・科技"}


def lines(text):
    return [l.strip() for l in (text or "").splitlines() if l.strip()]



# ---------- 內文區塊 → 網頁用格式 ----------
# 節點：{"t": 類型, "r": [文字片段], "c": [子節點]}
#   t: p 段落 / li 項目符號 / ol 編號 / quote 引言 / callout 提示框 / h3 小標 / hr 分隔線
# 文字片段：{"x": 文字, "b": 1 粗體, "i": 1 斜體, "a": 連結}
TYPE_MAP = {
    "paragraph": "p", "bulleted_list_item": "li", "numbered_list_item": "ol",
    "quote": "quote", "callout": "callout", "heading_3": "h3", "toggle": "p",
    "to_do": "li",
}


def runs(rich):
    out = []
    for x in rich or []:
        r = {"x": x.get("plain_text", "")}
        a = x.get("annotations") or {}
        if a.get("bold"):
            r["b"] = 1
        if a.get("italic"):
            r["i"] = 1
        if x.get("href"):
            r["a"] = x["href"]
        if r["x"]:
            out.append(r)
    return out


def convert(blocks):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "divider":
            out.append({"t": "hr"})
            continue
        kind = TYPE_MAP.get(t)
        if not kind:
            continue
        node = {"t": kind, "r": runs(b[t].get("rich_text"))}
        kids = convert(b.get("_children", []))
        if kids:
            node["c"] = kids
        if node["r"] or kids:
            out.append(node)
    return out


def sections(blocks):
    """依 heading_2 切段 → [{"title", "body": [節點]}]"""
    secs, cur = [], None
    for b in blocks:
        if b["type"] in ("heading_1", "heading_2"):
            cur = {"title": "".join(x.get("plain_text", "") for x in b[b["type"]]["rich_text"]).strip(), "blocks": []}
            secs.append(cur)
        elif cur is not None:
            cur["blocks"].append(b)
    return [{"title": s["title"], "body": convert(s["blocks"])} for s in secs]


def text_of(node):
    return "".join(r["x"] for r in node.get("r", []))


# ---------- 來源與立場 ----------
def host(url):
    h = urllib.parse.urlparse(url).hostname or ""
    return h[4:] if h.startswith("www.") else h


def source_index(rows):
    idx = []
    for r in rows:
        name, url = prop(r, "媒體名稱"), prop(r, "網址")
        if name:
            idx.append({"name": name, "host": host(url) if url else "", "lean": LEAN.get(prop(r, "立場傾向"), "other")})
    return idx


def match_source(idx, url="", label=""):
    h = host(url) if url else ""
    for s in idx:
        if s["host"] and h and (h == s["host"] or h.endswith("." + s["host"])):
            return s
    for s in idx:
        if label and (label.startswith(s["name"]) or s["name"].startswith(label)):
            return s
    return None


def extract_sources(secs, prop_urls, idx):
    out, seen = [], set()
    src = next((s for s in secs if s["title"].startswith("來源")), None)
    for node in (src["body"] if src else []):
        link = next((r["a"] for r in node.get("r", []) if r.get("a")), None)
        if not link or link in seen:
            continue
        label = text_of(node)
        mt = re.match(r"^(.+?)[：:]\s*(.*)$", label)
        name, title = mt.groups() if mt else (label, "")
        m = match_source(idx, link, name.strip())
        out.append({"name": (m or {}).get("name") or name.strip() or host(link), "title": title.strip(),
                    "url": link, "lean": (m or {}).get("lean", "other")})
        seen.add(link)
    for u in prop_urls:
        if u not in seen:
            m = match_source(idx, u)
            out.append({"name": (m or {}).get("name") or host(u), "title": "", "url": u, "lean": (m or {}).get("lean", "other")})
            seen.add(u)
    return out


# ---------- 圖片 ----------
class OgImage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and not self.url and (a.get("property") or a.get("name")) in ("og:image", "og:image:url", "twitter:image"):
            self.url = a.get("content", "")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), r.headers.get("Content-Type", "")


def save_image(src, dest):
    """src 可為圖片網址或新聞文章網址（抓文章的分享封面圖）。成功回傳網站相對路徑。"""
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
    except Exception as e:  # 一張失敗不影響整體
        print(f"  圖片失敗 {src}: {e}", file=sys.stderr)
        return ""


def cover_url(page):
    c = page.get("cover") or {}
    return (c.get(c.get("type"), {}) or {}).get("url", "")


# ---------- 組資料 ----------
def build(api, save_images=True):
    src_idx = source_index(api.query(DS["sources"]))
    ev_rows = api.query(DS["events"])
    day_rows = api.query(DS["days"])
    claim_rows = api.query(DS["claims"])
    issue_rows = api.query(DS["issues"])

    events = {nid(p["id"]): p for p in ev_rows}

    # 只認「有上網頁的那幾天」的事件：試跑、作廢的舊事件不會出現在前情或查證結果裡
    def day_ids(d):
        ids = [e for e in (prop(d, "當日事件") or []) if e in events]
        return ids or [k for k, p in events.items() if prop(p, "日期") == prop(d, "日期")]
    published_days = {}
    for d in day_rows:
        date = prop(d, "日期")
        if date and prop(d, "執行狀態") in PUBLISH_STATUS:
            # 同一天有兩筆會上網頁的總覽時，用最後編輯的那筆
            if date not in published_days or d.get("last_edited_time", "") > published_days[date].get("last_edited_time", ""):
                published_days[date] = d
    published = {k for d in published_days.values() for k in day_ids(d)}
    ev_brief = {k: {"id": k, "date": prop(events[k], "日期"), "title": prop(events[k], "事件標題")} for k in published}
    issues = {nid(p["id"]): {"id": nid(p["id"]), "name": prop(p, "議題名稱"), "background": prop(p, "背景說明"),
                             "events": prop(p, "事件") or []} for p in issue_rows}

    # 舊資料快取：內文沒改就不重抓
    cache = {}
    for f in (DATA / "days").glob("*.json") if (DATA / "days").exists() else []:
        for e in json.loads(f.read_text(encoding="utf-8")).get("events", []):
            cache[e["id"]] = e

    def event_json(k, p):
        date = prop(p, "日期")
        edited = p.get("last_edited_time")
        old = cache.get(k)
        if old and old.get("edited") == edited:
            secs = old["sections"]
        else:
            secs = sections(api.children(p["id"]))
        prop_urls = urls_in(prop(p, "來源連結"))
        srcs = extract_sources(secs, prop_urls, src_idx)
        first = (prop_urls or [s["url"] for s in srcs] or [""])[0]
        m = match_source(src_idx, first) if first else None
        photo = save_image(first, PHOTOS / date / f"{k}.webp") if save_images else ""
        prior, iss = [], []
        for i in prop(p, "議題") or []:
            if i in issues:
                iss.append({"id": i, "name": issues[i]["name"], "background": issues[i]["background"]})
                for e in issues[i]["events"]:
                    b = ev_brief.get(e)
                    if b and e != k and b["date"] and b["date"] < date and b not in prior:
                        prior.append(b)
        prior.sort(key=lambda b: b["date"], reverse=True)
        return {
            "id": k, "date": date, "edited": edited,
            "order": prop(p, "排序") if prop(p, "排序") is not None else 99,
            "title": prop(p, "事件標題"),
            "summary": prop(p, "一句話摘要"),
            "category": CATEGORY_ALIAS.get(prop(p, "類別"), prop(p, "類別")),
            "subcategories": prop(p, "子類別") or [],
            "primaryNature": prop(p, "主要性質"),
            "secondaryNature": prop(p, "次要性質"),
            "check": prop(p, "查證狀態"),
            "mediaCount": prop(p, "比對媒體數"),
            "independentCount": prop(p, "獨立來源數"),
            "gap": prop(p, "立場缺口"),
            "people": prop(p, "涉及對象") or [],
            "issues": iss,
            "prior": prior[:MAX_PRIOR],
            "claims": prop(p, "爆料查證") or [],
            "photo": {"url": photo, "credit": (m or {}).get("name") or (host(first) if first else ""), "source": first},
            "sections": [s for s in secs if not s["title"].startswith("來源")],
            "sources": srcs,
        }

    # 每天
    (DATA / "days").mkdir(parents=True, exist_ok=True)
    index_days = []
    for date, d in published_days.items():
        ids = day_ids(d)
        evs = sorted((event_json(k, events[k]) for k in ids), key=lambda e: (e["order"], e["title"] or ""))
        illo = cover_url(d)
        day = {
            "date": date,
            "title": prop(d, "日期標題"),
            "coverage": prop(d, "涵蓋時段"),
            "status": prop(d, "執行狀態"),
            "followUps": lines(prop(d, "追蹤更新"))[:MAX_FOLLOWUPS],
            "illustration": (save_image(illo, ILLOS / f"{date}.webp") if (illo and save_images) else ""),
            "events": evs,
        }
        write(DATA / "days" / f"{date}.json", day)
        index_days.append({"date": date, "title": day["title"], "count": len(evs), "lead": evs[0]["title"] if evs else ""})

    index_days.sort(key=lambda x: x["date"], reverse=True)

    # 查證追蹤
    claims = []
    for c in claim_rows:
        ev = [ev_brief[e] for e in (prop(c, "相關事件") or []) if e in ev_brief]
        claims.append({
            "id": nid(c["id"]),
            "claim": prop(c, "說法"),
            "speaker": prop(c, "發言者"),
            "party": prop(c, "所屬政黨/身分"),
            "quote": prop(c, "原話"),
            "status": prop(c, "狀態"),
            "result": prop(c, "查證結果說明"),
            "evidenceTypes": prop(c, "證據類型") or [],
            "evidence": urls_in(prop(c, "證據連結")),
            "spread": prop(c, "擴散程度"),
            "saidOn": prop(c, "發言日期"),
            "needs": prop(c, "需要什麼證據"),
            "burden": prop(c, "舉證責任"),
            "checkedOn": prop(c, "最後檢查日"),
            "events": ev,
        })
    claims.sort(key=lambda c: (c["saidOn"] or "", c["checkedOn"] or ""), reverse=True)
    write(DATA / "claims.json", {"claims": claims})

    write(DATA / "index.json", {
        "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "latest": index_days[0]["date"] if index_days else None,
        "days": index_days,
    })
    print(f"同步完成：{len(index_days)} 天、{len(events)} 個事件、{len(claims)} 條說法。")


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("尚未設定 NOTION_TOKEN，跳過。")
        return
    build(Notion(token))


if __name__ == "__main__":
    main()
