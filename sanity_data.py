#!/usr/bin/env python3
"""pools.json 資料體檢：fetch_pools.py 部署前必跑，fail = 唔准上線。

覆蓋 2026-10-31 體檢捉到嘅三類 bug：
  1. 冬季時間表冇 parse（11–4 月 months 缺失 → 全港誤報休館）
  2. 按星期分組時間表被合併（假時段 20:30-24:00、重複 start）
  3. 時段／座標／設施等欄位靜默變空
用法：python3 sanity_data.py [path/to/pools.json]
"""
import json
import os
import re
import sys

MONTHS = ["一月", "二月", "三月", "四月", "五月", "六月",
          "七月", "八月", "九月", "十月", "十一月", "十二月"]
HK_BOX = (22.1, 22.6, 113.8, 114.5)


def check(data):
    bad = []
    pools = data.get("pools") or []
    if len(pools) != 46:
        bad.append(f"泳池數 {len(pools)}（應為 46）")
    names = [p.get("name") for p in pools]
    if len(set(names)) != len(names):
        bad.append("有重複泳池名")
    if len({p.get("district") for p in pools}) != 18:
        bad.append(f"區數 {len({p.get('district') for p in pools})}（應為 18）")

    for p in pools:
        n = p.get("name", "?")
        months = p.get("months") or {}
        missing = [m for m in MONTHS if m not in months]
        if missing:
            bad.append(f"{n}: 缺月份 {','.join(missing)}（冬季時間表未 parse？）")
        for mon, v in months.items():
            ss = v.get("sessions") or []
            if not ss:
                bad.append(f"{n}/{mon}: 冇時段")
                continue
            starts = [s.get("start") for s in ss]
            if starts != sorted(starts):
                bad.append(f"{n}/{mon}: 時段非按時間排序 {starts}")
            if len(set(starts)) != len(starts):
                bad.append(f"{n}/{mon}: 重複開始時間 {starts}（按星期分組被合併？）")
            for s in ss:
                st, en = s.get("start", ""), s.get("end", "")
                if not re.fullmatch(r"\d{2}:\d{2}", st) or not re.fullmatch(r"\d{2}:\d{2}", en):
                    bad.append(f"{n}/{mon}: 時間格式錯 {st}-{en}")
                elif not ("05:00" <= st < en <= "23:59"):
                    bad.append(f"{n}/{mon}: 不合理時段 {st}-{en}")
                if not s.get("text"):
                    bad.append(f"{n}/{mon}: 時段冇原文")
        if not p.get("facilities"):
            bad.append(f"{n}: 設施為空")
        geo = p.get("geo") or {}
        lat, lng = geo.get("lat"), geo.get("lng")
        if not (lat and lng and HK_BOX[0] < lat < HK_BOX[1] and HK_BOX[2] < lng < HK_BOX[3]):
            bad.append(f"{n}: 座標唔在香港範圍 {lat},{lng}")
        for k in ("phone", "address", "officialUrl"):
            if not p.get(k):
                bad.append(f"{n}: 缺 {k}")
        cl = p.get("cleaning") or {}
        if cl.get("day") not in list("一二三四五六日"):
            bad.append(f"{n}: 大清潔日異常 {cl.get('day')}")
        for m in p.get("maintenance") or []:
            try:
                sm, sd, em, ed = m["startMonth"], m["startDay"], m["endMonth"], m["endDay"]
            except KeyError:
                bad.append(f"{n}: 維修欄位缺 {m}")
                continue
            if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 31 and 1 <= ed <= 31):
                bad.append(f"{n}: 維修日期範圍異常 {m}")
            if not m.get("pool"):
                bad.append(f"{n}: 維修冇池名")
        for a in p.get("announcements") or []:
            if not a.get("facilities"):
                bad.append(f"{n}: 公告冇設施")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", str(a.get("start", ""))):
                bad.append(f"{n}: 公告開始時間格式錯 {a.get('start')}")
            if a.get("end") and a["end"] < a["start"]:
                bad.append(f"{n}: 公告結束早過開始 {a['start']} → {a['end']}")
    return bad


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "pools.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    problems = check(data)
    if problems:
        print(f"❌ sanity FAIL：{len(problems)} 項")
        for b in problems[:40]:
            print("  -", b)
        sys.exit(1)
    print(f"✅ sanity PASS：{len(data['pools'])} 池 / {len(data['districts'])} 區 / 12 個月齊")
