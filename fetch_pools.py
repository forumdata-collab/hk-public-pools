#!/usr/bin/env python3
"""全港公眾泳池資料 scraper → data/pools.js (+ pools.json) → 部署 CF Pages。

資料來源：康文署「公眾游泳池」各區頁（Swimming.do?dist=locN，中英文）
  每個泳池 panel 提供：地址／電話／設施／開放時間表（逐月）／每年維修工程／
  每周大清潔行動／暫停開放公告／相片／位置圖參考
座標：map.gov.hk locationSearch（HK1980 格網 → WGS84，EPSG:2326→4326）
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
CACHE = os.path.join(BASE, "cache")
os.makedirs(DATA, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; pools-hk-bot/1.0)"}
CF_PROXY = os.environ.get("LCSD_PROXY_URL", "https://lcsd-proxy.forumdata.workers.dev/?url=")

DISTRICTS = [
    ("loc1", "東區", "Eastern"),
    ("loc2", "灣仔", "Wan Chai"),
    ("loc3", "中西區", "Central & Western"),
    ("loc4", "南區", "Southern"),
    ("loc5", "油尖旺", "Yau Tsim Mong"),
    ("loc6", "深水埗", "Sham Shui Po"),
    ("loc7", "九龍城", "Kowloon City"),
    ("loc8", "黃大仙", "Wong Tai Sin"),
    ("loc9", "觀塘", "Kwun Tong"),
    ("loc10", "沙田", "Sha Tin"),
    ("loc11", "西貢", "Sai Kung"),
    ("loc12", "屯門", "Tuen Mun"),
    ("loc13", "葵青", "Kwai Tsing"),
    ("loc14", "元朗", "Yuen Long"),
    ("loc15", "北區", "North"),
    ("loc16", "大埔", "Tai Po"),
    ("loc17", "荃灣", "Tsuen Wan"),
    ("loc18", "離島", "Islands"),
]
MONTHS = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ───────────────────────── fetch ─────────────────────────
def _proxy_token():
    """CF Worker proxy token：優先環境變數，其次 ~/.config/lcsd_proxy_token（可用 CF_PROXY_TOKEN_FILE 覆寫）。"""
    tok = os.environ.get("CF_PROXY_TOKEN", "")
    if tok:
        return tok
    for p in [os.environ.get("CF_PROXY_TOKEN_FILE", ""), os.path.expanduser("~/.config/lcsd_proxy_token"),
              "/tmp/cf_proxy_token.txt"]:
        if p and os.path.exists(p):
            try:
                return io.open(p).read().strip()
            except OSError:
                pass
    return ""


def fetch(url, tries=3):
    tok = _proxy_token()
    last = None
    for i in range(tries):
        try:
            if tok:
                proxied = CF_PROXY + urllib.parse.quote(url, safe="")
                req = urllib.request.Request(proxied, headers={**UA, "x-proxy-token": tok})
            else:
                req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


# ───────────────────────── html helpers ─────────────────────────
def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def outer_table(html, start_idx):
    i = html.find("<table", start_idx)
    if i < 0:
        return None
    depth = 0
    for m in re.finditer(r"<table\b|</table>", html[i:]):
        depth += 1 if m.group(0).startswith("<table") else -1
        if depth == 0:
            return html[i:i + m.end()]
    return html[i:]


def rows_of(tbl):
    """rows at nesting depth 0 of the given outer <table>"""
    inner = tbl[tbl.find(">") + 1: tbl.rfind("</table>")]
    out, depth, cur = [], 0, None
    for m in re.finditer(r"<table\b|</table>|<tr\b[^>]*>|</tr>", inner):
        tok = m.group(0)
        if tok.startswith("<table"):
            depth += 1
        elif tok.startswith("</table"):
            depth -= 1
        elif tok.startswith("<tr"):
            if depth == 0:
                cur = m.end()
        elif depth == 0 and cur is not None:
            out.append(inner[cur:m.start()])
            cur = None
    return out


def cells_of(row):
    return [(re.search(r'colspan=["\']?(\d+)', a).group(1) if re.search(r'colspan=["\']?(\d+)', a) else "1", clean(i))
            for _t, a, i in re.findall(r"<(t[dh])([^>]*)>(.*?)</\1>", row, re.S)]


def raw_cell(panel, label):
    """原始 HTML 版本嘅 info cell（保留 <br/>，設施名靠佢分格）"""
    m = re.search(r'<td class="info"[^>]*>\s*<b>' + re.escape(label) + r'</b>\s*</td>\s*<td[^>]*>(.*?)</td>', panel, re.S)
    return m.group(1) if m else ""


def panel_fields(panel):
    """{label: value} for the top info rows of a pool panel"""
    out = {}
    for r in re.findall(r"<tr>(.*?)</tr>", panel, re.S):
        cs = re.findall(r'<td class="info"[^>]*>\s*<b>(.*?)</b>\s*</td>\s*<td[^>]*>(.*?)</td>', r, re.S)
        for lab, val in cs:
            out[clean(lab)] = val
    return out


# ───────────────────────── hours parsing ─────────────────────────
def parse_zh_time(txt):
    """上午6時30分 → 06:30 ; 中午12時 → 12:00 ; 下午1時 → 13:00 ; 晚上10時 → 22:00"""
    m = re.match(r"(上午|中午|下午|晚上|午|上午)?\s*(\d{1,2})\s*時\s*(?:(\d{1,2})\s*分)?", txt.strip())
    if not m:
        return None
    per, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
    if per in ("下午", "晚上", "午") and hh < 12:      # 「午1時」係 LCSD 打漏「下」字
        hh += 12
    elif per == "中午" and hh < 12:
        hh += 12
    return f"{hh:02d}:{mm:02d}"


RANGE_RE = (r"(上午|中午|下午|晚上)?\s*\d{1,2}\s*時(?:\s*\d{1,2}\s*分)?"
            r"\s*至\s*(上午|中午|下午|晚上)?\s*\d{1,2}\s*時(?:\s*\d{1,2}\s*分)?")


def parse_zh_range(txt):
    """「下午1時至5時」→ ('13:00','17:00')：後段無時段詞時沿用前段（LCSD 慣例）"""
    m = re.search(RANGE_RE, txt)
    if not m:
        return None, None
    a, b = m.group(0).split("至")
    per_a, per_b = m.group(1), m.group(2)
    if not per_b and per_a:
        b = per_a + b                                   # 「下午1時至5時」→ 下午5時
    if not per_a and per_b:
        a = per_b + a
    s, e = parse_zh_time(a), parse_zh_time(b)
    if s and e and to_min(e) <= to_min(s):              # 保險：結束早過開始 → 試由前段推
        e2 = parse_zh_time((per_a or "") + b)
        if e2 and to_min(e2) > to_min(s):
            e = e2
    return s, e


def to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def parse_sessions_zh(text):
    """第一節：上午6時30分至中午12時 …→ [{'label':'第一節','start':'06:30','end':'12:00'}]"""
    out = []
    for m in re.finditer(r"(第[一二三四]節)\s*[：:]\s*([^第（(]+?)(?=[第（(]|$)", text):
        lab, seg = m.group(1), m.group(2)
        s, e = parse_zh_range(seg)
        if s and e:
            out.append({"label": lab, "start": s, "end": e, "text": clean(seg)})
    for i in range(1, len(out)):                       # 修順序：第二節起若早於上一節完結，+12 小時
        if to_min(out[i]["start"]) < to_min(out[i - 1]["end"]):
            s2, e2 = to_min(out[i]["start"]) + 720, to_min(out[i]["end"]) + 720
            if e2 <= 1440:
                out[i]["start"] = f"{s2 // 60:02d}:{s2 % 60:02d}"
                out[i]["end"] = f"{e2 // 60:02d}:{e2 % 60:02d}"
    if not out:  # 連續開放（如灣仔游泳池「上午7時至晚上10時」）
        s, e = parse_zh_range(text)
        if s and e:
            out.append({"label": "開放時段", "start": s, "end": e, "text": clean(text)})
    return out


def parse_breaks_zh(text):
    m = re.search(r"[（(]\s*(?:暫停開放時間|session break)[^：:]*[：:]\s*([^）)]+)[）)]", text)
    if not m:
        return []
    out = []
    for part in re.split(r"及|、|,", m.group(1)):
        s, e = parse_zh_range(part)
        if s and e:
            out.append({"start": s, "end": e})
    return out


def parse_sessions_en(text):
    out = []
    for m in re.finditer(r"(\d(?:st|nd|rd|th))\s*Session\s*[：:]\s*([^0-9]*?)(\d{1,2}[:.．]\d{2}|\d{1,2})\s*(am|pm|nn)?\s*-\s*(\d{1,2}[:.．]\d{2}|\d{1,2})\s*(am|pm|nn)?\b", text):
        _ord, _pre, a, am, b, bm = m.groups()
        am = (am or bm or "").lower()
        bm = (bm or am).lower()
        out.append({"label": m.group(0)[:12].strip(), "start": _en_time(a, am), "end": _en_time(b, bm), "text": clean(m.group(0))})
    return out


def _en_time(t, mer):
    t = t.replace("．", ".").replace(".", ":")
    hh, mm = (t.split(":") + ["00"])[:2]
    hh, mm = int(hh), int(mm)
    mer = mer.replace(".", "")
    if mer == "pm" and hh < 12:
        hh += 12
    if mer == "nn" and hh == 12:
        pass
    if mer == "am" and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm:02d}"


DATE_SPAN = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\s*[-–—~至]\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})")
NOTE_KEY = re.compile(r"(維修|暫停開放|只開放|開放時間表)")


def note_months(txt):
    """維修日期範圍 → 受影響月份名單（如 11.9.2026 - 31.10.2026 → ['九月','十月']）"""
    m = DATE_SPAN.search(txt)
    if not m:
        return None
    sm, em = int(m.group(2)), int(m.group(5))
    if sm <= em:
        return MONTHS[sm - 1:em]
    return MONTHS[sm - 1:] + MONTHS[:em]                    # 跨年


def note_text(txt):
    """由時段文字中抽出「維修…／只開放…」那句做備註（唔好抽到「暫停開放時間：…」嘅小息句）"""
    m = re.search(r"[（(]([^（()]{0,120}?維修[^（()]{0,120}?)[）)]", txt)   # 含「維修」嘅括號段
    if m:
        inner = m.group(1).strip(" ）(（")
        pre = re.search(r"(只開放[^（(]{0,40}|除[^（(]{0,45}外[^（(]{0,35})", txt[max(0, m.start() - 45):m.start()])
        return ((pre.group(1).strip() + "　" if pre else "") + inner).strip()[:170]
    idx = txt.find("維修")
    if idx >= 0:
        return txt[idx:].strip(" ）(（")[:170]
    return ""


def parse_month_table(panel, sec_tc, sec_en):
    """逐月開放時間表 → {'十月': {'sessions':[...], 'breaks':[...], 'notes':[...]}}

    LCSD 表格嘅 colspan 對唔齊月份標題（標題每格 4 欄、資料每格 3 欄），所以唔用格數對位，
    改為語義化：所有月份共用同一組時段；「維修」備註按日期範圍決定屬於邊幾個月。
    """
    i = panel.find(sec_tc)
    if i < 0:
        return {}
    tbl = outer_table(panel, i)
    if not tbl:
        return {}
    rows = rows_of(tbl)
    if not rows:
        return {}
    months = []
    for m in re.finditer(r'colspan=["\']?\d+["\']?[^>]*>\s*<b>([^<]{1,6})</b>', rows[0]):
        name = m.group(1).strip()
        if name in MONTHS:
            months.append(name)
    if not months:
        return {}
    cells = []
    for r in rows[1:]:
        for _cs, txt in cells_of(r):
            if txt:
                cells.append(txt)
    sessions, breaks = [], []
    for txt in cells:
        if sessions:
            break
        if "節" in txt or re.search(r"\d{1,2}\s*時[^。]{0,20}至[^。]{0,20}\d{1,2}\s*時", txt):
            sessions = parse_sessions_zh(txt)
            breaks = parse_breaks_zh(txt)
    notes = []            # [(text, months|None)]
    for txt in cells:
        if "維修" in txt or DATE_SPAN.search(txt):
            t = note_text(txt)
            if t and all(t != x[0] for x in notes):
                notes.append((t, note_months(txt)))
    res = {}
    for mon in months:
        res[mon] = {"sessions": sessions, "breaks": breaks,
                    "notes": [t for t, ms in notes if ms is None or mon in ms]}
    return res


# ───────────────────────── sections ─────────────────────────
def parse_annual_maintenance(panel):
    """配合每年維修工程的暫停開放時間：'主池：5月4日至6月23日' / '11月1日至翌年3月31日'"""
    i = panel.find("配合每年維修工程")
    if i < 0:
        return []
    seg = panel[i:i + 4000]
    seg = seg[:seg.find("每周大清潔")] if "每周大清潔" in seg else seg
    text = clean(seg).replace("配合每年維修工程的暫停開放時間", "")
    out, seen = [], set()
    pat = re.compile(r"([\u4e00-\u9fff、，, ]+(?:池|場))\s*(?:\([^)]*\))?\s*[：:]\s*(\d{1,2})月(\d{1,2})日\s*至\s*(翌年)?\s*(\d{1,2})月(\d{1,2})日")
    for m in pat.finditer(text):
        for pool in re.split(r"[、，,]", m.group(1)):
            pool = re.sub(r"^[日\s]+", "", pool.strip())      # 剝走前綴殘字（"日 室內副池"）
            pool = {"全池": "全場"}.get(pool, pool)
            if not pool.endswith(("池", "場")) or len(pool) > 8:
                continue
            key = (pool, m.group(2), m.group(3), m.group(5), m.group(6))
            if key in seen:
                continue
            seen.add(key)
            out.append({"pool": pool, "startMonth": int(m.group(2)), "startDay": int(m.group(3)),
                        "endMonth": int(m.group(5)), "endDay": int(m.group(6)), "nextYear": bool(m.group(4))})
    if not out:
        m2 = re.search(r"(\d{1,2})月(\d{1,2})日\s*至\s*(翌年)?\s*(\d{1,2})月(\d{1,2})日", text)
        if m2:
            out.append({"pool": "全場", "startMonth": int(m2.group(1)), "startDay": int(m2.group(2)),
                        "endMonth": int(m2.group(4)), "endDay": int(m2.group(5)), "nextYear": bool(m2.group(3))})
    return out


def parse_cleaning(panel):
    """每周大清潔行動：逢星期X（星期Y ※）"""
    for m0 in re.finditer(r"每周大清潔行動", panel):
        seg = clean(panel[m0.start():m0.start() + 2000])
        m = re.search(r"逢\s*星期([一二三四五六日天])", seg)
        if m:
            fb = re.search(r"[（(]\s*星期([一二三四五六日天])\s*[※*]?\s*[）)]", seg)
            raw = re.search(r"逢\s*星期[一二三四五六日天](?:\s*[（(][^）)]{0,24}[）)])?", seg)
            return {"day": m.group(1), "fallback": fb.group(1) if fb else "",
                    "raw": raw.group(0).strip() if raw else ""}
    return None


DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*-\s*(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})")


def parse_announcements(panel, en=False):
    """暫停開放公告表（逐列 parse）：關閉時間 | 設施 | 原因 | 備註"""
    i = panel.find("暫停開放公告")
    if i < 0:
        i = panel.find("Temporary Closure")
    if i < 0:
        return []
    seg = panel[i:i + 30000]
    if "沒有相關的公告" in seg[:1500] or "No relevant notice" in seg[:1500]:
        return []
    cut = seg.find("相片")
    if cut > 0:
        seg = seg[:cut]
    tbl = outer_table(seg, 0)
    if not tbl:
        return []
    out = []
    for row in rows_of(tbl):
        cells = [clean(c[1]) for c in cells_of(row)]
        if len(cells) < 2 or not DATE_RE.search(cells[0]):
            continue
        m = DATE_RE.search(cells[0])
        fac = cells[1] if len(cells) > 1 else ""
        rea = cells[2] if len(cells) > 2 else ""
        rem = " ".join(cells[3:]) if len(cells) > 3 else ""
        if rea.strip() in ("其他", "Other", "Others", ""):
            mm = re.search(r"(?:由於|因|due to)\s*([^，。；;,]{2,30})", rem)
            if mm:
                rea = mm.group(1).strip()          # 原因欄「其他」→ 具體原因喺備註（救生員不足／維修…）
        out.append({
            "start": f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}",
            "end": f"{m.group(6)}-{m.group(7)}-{m.group(8)}T{m.group(9)}:{m.group(10)}",
            "facilities": [x.strip() for x in re.split(r",|，", fac) if x.strip()],
            "reason": rea, "remarks": rem[:600],
        })
    seen, uniq = set(), []
    for a in out:
        k = (a["start"], a["end"], tuple(a["facilities"]))
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    return uniq


LABELS = ("室內設施", "戶外設施", "無障礙設施", "公眾授泳區", "家庭更衣室", "其他設施")


def parse_facilities(raw, areas_out=None):
    """設施 cell（原始 HTML，用 <br/> 分格）→ ['訓練池', '嬉水池 1', '嬉水池 2&3', …]
    同時把「池名 → indoor/outdoor」寫入 areas_out（設施 cell 用「室內設施／戶外設施」分段）。"""
    if not raw:
        return []
    txt = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("^", "\n")]:
        txt = txt.replace(a, b)
    out, areas = [], {}
    cur = ""                                   # 現時區段：室內設施 / 戶外設施
    for ln in txt.split("\n"):
        s = re.sub(r"\s+", " ", ln).strip(" ^*·")
        if not s:
            continue
        if s.startswith("室內設施"):
            cur = "indoor"
        elif s.startswith("戶外設施"):
            cur = "outdoor"
        if re.match(r"^(無障礙|公眾授泳|其他設施|家庭更衣|觀眾看台|育嬰|殘疾)", s):
            continue
        for lab in LABELS:                     # 剝走分區標籤（室內設施 : / 無障礙設施：…）
            if s.startswith(lab):
                s = s[len(lab):].lstrip(" :：")
        if not s:
            continue
        m = re.match(r"^(.{1,26}?)\s*[（(]", s)   # 括號前嘅才是池名，括號內係尺寸／水深
        cand = re.sub(r"\s+", " ", (m.group(1) if m else s)).strip()
        if not cand or len(cand) > 16 or not re.search(r"[池場]", cand) or re.search(r"[、，,：:]", cand):
            continue
        if cand not in out:
            name = cand.lstrip("室內外戶")
            area = cur or ("indoor" if cand.startswith("室內") else ("outdoor" if cand.startswith(("室外", "戶外")) else ""))
            out.append(cand)
            if area:
                areas[cand] = area
    if areas_out is not None:
        areas_out.update(areas)
    return out


def parse_photo(panel):
    m = re.search(r'<img src="(https?://[^"]+/SP/[^"]+)"', panel)
    return m.group(1) if m else ""


def parse_pool(panel_tc, panel_en):
    f_tc, f_en = panel_fields(panel_tc), panel_fields(panel_en)
    fac_areas = {}
    name = clean(re.search(r"<h3[^>]*>(.*?)</h3>", panel_tc, re.S).group(1))
    name_en = clean(re.search(r"<h3[^>]*>(.*?)</h3>", panel_en, re.S).group(1)) if re.search(r"<h3[^>]*>(.*?)</h3>", panel_en, re.S) else name
    months = parse_month_table(panel_tc, "開放時間表", "Opening Schedule")
    # 代表時段 = 最多月份使用嘅一組
    from collections import Counter
    sig = Counter(json.dumps((m.get("sessions"), m.get("breaks"))) for m in months.values() if m.get("sessions"))
    sessions, breaks = [], []
    if sig:
        best = json.loads(sig.most_common(1)[0][0])
        sessions, breaks = best[0] or [], best[1] or []
    return {
        "name": name,
        "nameEn": name_en,
        "address": clean(f_tc.get("地址", "")),
        "addressEn": clean(f_en.get("Address", "")),
        "phone": clean(f_tc.get("電話號碼", "")),
        "facilities": parse_facilities(raw_cell(panel_tc, "設施"), fac_areas),
        "facAreas": fac_areas,
        "facilitiesRaw": clean(raw_cell(panel_tc, "設施"))[:500],
        "months": months,
        "sessions": sessions,
        "breaks": breaks,
        "maintenance": parse_annual_maintenance(panel_tc),
        "cleaning": parse_cleaning(panel_tc),
        "announcements": parse_announcements(panel_tc),
        "photo": parse_photo(panel_tc),
    }


# ───────────────────────── geocode ─────────────────────────
def direct_fetch(url, tries=2):
    """map.gov.hk 等非 LCSD 站：直連優先（CF proxy 只准 LCSD 域名，會 403）"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2)
    raise RuntimeError(f"direct fetch failed {url}: {last}")


def geocode(name_tc, district_tc):
    cache_path = os.path.join(CACHE, "geo.json")
    cache = json.load(io.open(cache_path)) if os.path.exists(cache_path) else {}
    if cache.get(name_tc):
        return cache[name_tc]
    q = urllib.parse.quote(name_tc.replace(" (只供團體訓練之用)", ""))
    try:
        raw = direct_fetch(f"https://www.map.gov.hk/gs/api/v1.0.0/locationSearch?q={q}")
        arr = json.loads(raw)
    except Exception:
        arr = []
    best = None
    for it in arr:
        if it.get("nameZH", "").strip() == name_tc.strip() or (name_tc.replace(" (只供團體訓練之用)", "") in it.get("nameZH", "")):
            if it.get("districtZH", "").startswith(district_tc[:2]) or district_tc in it.get("districtZH", ""):
                best = it
                break
            best = best or it
    if not best and arr:
        best = arr[0]
    if not best:
        return None  # 唔快取失敗，下次再試
    else:
        from pyproj import Transformer
        lon, lat = Transformer.from_crs("EPSG:2326", "EPSG:4326", always_xy=True).transform(best["x"], best["y"])
        cache[name_tc] = {"lat": round(lat, 6), "lng": round(lon, 6),
                          "mapName": best.get("nameZH", ""), "mapDistrict": best.get("districtZH", "")}
    io.open(cache_path, "w", encoding="utf-8").write(json.dumps(cache, ensure_ascii=False, indent=1))
    time.sleep(0.4)
    return cache[name_tc]


# ───────────────────────── main ─────────────────────────
def scrape():
    pools, qa = [], []
    for loc, d_tc, d_en in DISTRICTS:
        for lang, key in (("tc", "tc"), ("en", "en")):
            pass
        h_tc = fetch(f"https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist={loc}")
        h_en = fetch(f"https://www.lcsd.gov.hk/clpss/en/webApp/Swimming.do?dist={loc}")
        io.open(os.path.join(CACHE, f"{loc}.tc.html"), "w", encoding="utf-8").write(h_tc)
        io.open(os.path.join(CACHE, f"{loc}.en.html"), "w", encoding="utf-8").write(h_en)
        ptc = re.split(r'<div class="panel panel-primary">', h_tc)[1:]
        pen = re.split(r'<div class="panel panel-primary">', h_en)[1:]
        if len(ptc) != len(pen):
            qa.append(f"{d_tc}: panel 數唔一致 tc={len(ptc)} en={len(pen)}")
        for idx, p in enumerate(ptc):
            d = parse_pool(p, pen[idx] if idx < len(pen) else p)
            d["district"] = d_tc
            d["districtEn"] = d_en
            d["districtCode"] = loc
            d["officialUrl"] = f"https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist={loc}"
            geo = geocode(d["name"], d_tc)
            d["geo"] = geo
            if not d["facilities"]:
                qa.append(f"{d_tc}/{d['name']}: 設施 parse 失敗")
            if not d["sessions"]:
                qa.append(f"{d_tc}/{d['name']}: 時段 parse 失敗（months={len(d['months'])}）")
            if not d["cleaning"]:
                qa.append(f"{d_tc}/{d['name']}: 大清潔日 parse 失敗")
            if not geo:
                qa.append(f"{d_tc}/{d['name']}: 座標抓唔到")
            pools.append(d)
        print(f"  {d_tc}: {len(ptc)} 個泳池", flush=True)
    return {"schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "source": "康樂及文化事務署（LCSD）公眾游泳池網頁",
            "sourceUrls": {"pools": "https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist=locN",
                           "geocode": "https://www.map.gov.hk/gs/api/v1.0.0/locationSearch",
                           "holidays": "https://www.1823.gov.hk/common/ical/tc.json"},
            "note": "狀態（開放中／大清潔中／維修／休館等）由前端依香港時間即時計算，並非爬蟲寫死；通告以康文署現場公佈為準。",
            "districts": [{"code": c, "name": n, "nameEn": e} for c, n, e in DISTRICTS],
            "pools": pools}, qa


def holidays():
    try:
        raw = direct_fetch("https://www.1823.gov.hk/common/ical/tc.json")   # 非 LCSD 域名，唔可以走 LCSD proxy
        d = json.loads(raw.lstrip("\ufeff"))
        days = []
        for vc in d.get("vcalendar", []):
            for ev in vc.get("vevent", []):
                ds = ev.get("dtstart", [None])[0]
                if ds and re.match(r"^\d{8}$", str(ds)):
                    days.append(f"{ds[:4]}-{ds[4:6]}-{ds[6:]}")
        return sorted(set(days))
    except Exception as e:  # noqa: BLE001
        print("holidays fail:", e, file=sys.stderr)
        return []


def write_output(data):
    data["holidays"] = holidays()
    js = "window.POOLS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    io.open(os.path.join(DATA, "pools.js"), "w", encoding="utf-8").write(js)
    io.open(os.path.join(DATA, "pools.json"), "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=1))
    return len(js)


def bump_version(html_path):
    s = io.open(html_path, encoding="utf-8").read()
    epoch = int(time.time())
    s2 = re.sub(r"(pools\.js|app\.js|style\.css)\?v=\d+", lambda m: f"{m.group(1)}?v={epoch}", s)
    io.open(html_path, "w", encoding="utf-8").write(s2)
    return epoch


def stage():
    """只放上線檔案去 dist/（唔好把 cache/ recon/ 一齊 deploy）"""
    import shutil
    st = os.path.join(BASE, "dist")
    shutil.rmtree(st, ignore_errors=True)
    os.makedirs(os.path.join(st, "data"))
    for f in ("index.html", "style.css", "app.js"):
        shutil.copy(os.path.join(BASE, f), st)
    shutil.copy(os.path.join(DATA, "pools.js"), os.path.join(st, "data"))
    shutil.copy(os.path.join(DATA, "pools.json"), os.path.join(st, "data"))
    io.open(os.path.join(st, "_headers"), "w", encoding="utf-8").write(
        "/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n"
        "/\n  X-Content-Type-Options: nosniff\n")
    epoch = bump_version(os.path.join(st, "index.html"))
    return st, epoch


def deploy():
    env = dict(os.environ)
    env.setdefault("WRANGLER_CONFIG", "/tmp/empty.toml")
    st, epoch = stage()
    proj = os.environ.get("CF_PAGES_PROJECT", "pools-we1co")
    r = subprocess.run(["npx", "wrangler", "pages", "deploy", ".", "--project-name=" + proj,
                        "--branch=main", "--commit-dirty=true"],
                       cwd=st, capture_output=True, text=True, env=env, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    ok = "Deployment complete" in out or "Deployed" in out
    print(out[-900:])
    print(f"?v={epoch} deploy={'OK' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    t0 = time.time()
    data, qa = scrape()
    n = write_output(data)
    print(f"\n{len(data['pools'])} 個泳池 | pools.js {n/1024:.0f}KB | {time.time()-t0:.0f}s")
    if qa:
        print("⚠️ QA:")
        for q in qa:
            print("  -", q)
    else:
        print("QA: 全部欄位齊")
    if "--deploy" in sys.argv:
        deploy()
