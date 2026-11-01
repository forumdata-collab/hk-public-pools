#!/usr/bin/env python3
"""每月全量審核：唔靠站自己嘅快取，重新抓 18 區官網 → 重新 parse → 同 live 資料對比。

同每日 cross_check 唔同：
  - cross_check = 兩個站互對（捉其中一邊 parse 錯）
  - 呢個 = 官網 ↔ live 站（捉 live 部署過期、或 LCSD 頁面結構改咗而 parser 靜默漏讀）

靜默設計：全部正常 = 無輸出（cron no_agent 唔會發訊息）；有問題才印報告。
用法：python3 monthly_audit.py
"""
import json
import re
import sys
import urllib.request

import fetch_pools as fp
import sanity_data

LIVE = "https://pools.we1co.me/data/pools.json"
UA = {"User-Agent": "Mozilla/5.0 (monthly-audit)"}
FIELDS = ("facilities", "maintenance", "cleaning", "months", "sessions")   # 公告屬易變欄位，另做軟檢查


def live_data():
    req = urllib.request.Request(LIVE, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fresh_pools(geo_map):
    out = []
    for loc, d_tc, _d_en in fp.DISTRICTS:
        h_tc = fp.fetch(f"https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist={loc}")
        panels = re.split(r'<div class="panel panel-primary">', h_tc)[1:]
        for p in panels:
            d = fp.parse_pool(p, p)          # 只比對中文欄位，英文 panel 唔需要
            d.pop("_tables", None)
            d["district"] = d_tc
            d["officialUrl"] = f"https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist={loc}"
            d["geo"] = geo_map.get(d["name"], {})      # 座標由 live 帶過來（地圖 API 另一支，唔在本審核範圍）
            out.append(d)
    return out


def main():
    problems = []
    live = live_data()
    live_pools = {p["name"]: p for p in live.get("pools", [])}
    if len(live_pools) != 46:
        problems.append(f"live 只有 {len(live_pools)} 個池（應 46）")

    geo_map = {n: (p.get("geo") or {}) for n, p in live_pools.items()}
    fresh = fresh_pools(geo_map)
    if len(fresh) != 46:
        problems.append(f"官網 parse 到 {len(fresh)} 個池（應 46）")

    for p in fresh:
        n = p["name"]
        old = live_pools.get(n)
        if not old:
            problems.append(f"{n}: live 站冇呢個池")
            continue
        for f in FIELDS:
            if json.dumps(p.get(f), ensure_ascii=False, sort_keys=True) != \
               json.dumps(old.get(f), ensure_ascii=False, sort_keys=True):
                problems.append(f"{n}: {f} 同 live 唔一致（live 過期或 parser 改咗？）")

    # 公告：內容日日改（學校水運會、池水污染），只做「有冇成批漏讀」軟檢查
    for p in fresh:
        n = p["name"]
        old = live_pools.get(n) or {}
        fresh_n, live_n = len(p.get("announcements") or []), len(old.get("announcements") or [])
        if fresh_n and not live_n:
            problems.append(f"{n}: 官網有 {fresh_n} 條公告但 live 0 條（parser 漏讀？）")

    # 結構不變量（官網每一池都應該有 2 張時間表）
    for p in fresh:
        seen = p.get("_tables", {}).get("seen")
        if seen is not None and seen != 2:
            problems.append(f"{p['name']}: 官網有 {seen} 張開放時間表（預期 2）")

    # 獨立重跑一次資料體檢
    for msg in sanity_data.check({"pools": fresh, "districts": live.get("districts", [])}):
        problems.append("sanity: " + msg)

    if problems:
        print(f"⚠️ 每月全量審核：{len(problems)} 項問題")
        for x in problems[:30]:
            print("  -", x)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
