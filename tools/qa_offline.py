#!/usr/bin/env python3
"""資料解析 QA：用 cache/ 內已抓取的康文署 HTML 重跑 parser，報告每池欄位覆蓋。

用法：
    python3 tools/qa_offline.py            # 用 cache/ 內的 HTML（跑過 fetch_pools.py 就有）
    python3 tools/qa_offline.py --fetch    # 冇 cache 就即場抓 18 區（約 30 秒）
    python3 tools/qa_offline.py --json     # 以 JSON 輸出（供 CI／其他工具用）

驗收標準：46 個泳池每個都要有 設施、時段、大清潔日；有任何缺漏會以非零 exit 結束。
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import fetch_pools as F  # noqa: E402


def ensure_cache(fetch_missing):
    have = all(os.path.exists(f"{F.CACHE}/{loc}.tc.html") for loc, _t, _e in F.DISTRICTS)
    if have or not fetch_missing:
        return have
    print("cache 不齊，開始抓取 18 區…", file=sys.stderr)
    for loc, d_tc, _e in F.DISTRICTS:
        for lang in ("tc", "en"):
            html = F.fetch(f"https://www.lcsd.gov.hk/clpss/{lang}/webApp/Swimming.do?dist={loc}")
            io.open(f"{F.CACHE}/{loc}.{lang}.html", "w", encoding="utf-8").write(html)
        print(f"  {d_tc} ok", file=sys.stderr)
    return True


def main():
    as_json = "--json" in sys.argv
    if not ensure_cache("--fetch" in sys.argv):
        print("缺 cache/*.tc.html：先跑 python3 fetch_pools.py（或加 --fetch）", file=sys.stderr)
        return 2

    rows, bad = [], []
    for loc, d_tc, _d_en in F.DISTRICTS:
        h_tc = io.open(f"{F.CACHE}/{loc}.tc.html", encoding="utf-8", errors="ignore").read()
        h_en = io.open(f"{F.CACHE}/{loc}.en.html", encoding="utf-8", errors="ignore").read() \
            if os.path.exists(f"{F.CACHE}/{loc}.en.html") else h_tc
        ptc = re.split(r'<div class="panel panel-primary">', h_tc)[1:]
        pen = re.split(r'<div class="panel panel-primary">', h_en)[1:]
        for i, panel in enumerate(ptc):
            d = F.parse_pool(panel, pen[i] if i < len(pen) else panel)
            row = {"district": d_tc, "name": d["name"], "facilities": len(d["facilities"]),
                   "sessions": len(d["sessions"]), "months": len(d["months"]),
                   "maintenance": len(d["maintenance"]), "cleaning": bool(d["cleaning"]),
                   "announcements": len(d["announcements"])}
            rows.append(row)
            if not d["facilities"] or not d["sessions"] or not d["cleaning"]:
                bad.append(row)

    if as_json:
        print(json.dumps({"total": len(rows), "problems": bad, "pools": rows}, ensure_ascii=False, indent=1))
    else:
        print(f"總數 {len(rows)} | 有問題 {len(bad)}")
        for r in bad:
            print(f"  ⚠️ {r['district']} {r['name']} 設施{r['facilities']} 時段{r['sessions']} 清潔{r['cleaning']}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
