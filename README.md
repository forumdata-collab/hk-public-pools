# 全港公眾泳池開放狀態 (HK Public Swimming Pools Status)

> 康文署 46 個公眾游泳池的即時開放狀態 — 18 區分區瀏覽、逐節開放時間、每周大清潔、每年維修工程、暫停開放公告，附 Leaflet 地圖與天文台警告條。

**Live:** <https://pools.we1co.me> · **Data API:** <https://pools.we1co.me/data/pools.json>

[![Live](https://img.shields.io/badge/live-pools.we1co.me-0f5c8c)](https://pools.we1co.me)
[![Data API](https://img.shields.io/badge/API-pools.json-0f7a52)](https://pools.we1co.me/data/pools.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![No build step](https://img.shields.io/badge/build-none-lightgrey)](#-quick-start)

---

## ✨ Features

| 功能 | 實作細節 |
|------|----------|
| 即時狀態徽章 | 開放中／即將開始／部分設施暫停／部分設施維修／大清潔中／維修中（暫停開放）／休館／**天氣關閉**，依 **香港時間** 每分鐘於前端重算，非爬蟲寫死 |
| 逐節狀態 | 每個時段獨立標示「進行中（剩 X 小時 Y 分）／已完結／即將開始」，休息時段（如 12:00–13:00）由官網括號文字解析 |
| 大清潔日 | 官網「每周大清潔行動」的 `逢星期X（後備星期Y ※）`；主日撞正**公眾假期**時自動改到同一星期的後備日（假期表來自 1823 官方 iCal） |
| 每年維修工程 | 逐池 parse `主池：5月4日至6月23日` 式範圍，支援「翌年」跨年範圍；官網時間表內的 `維修: 11.9.2026 - 31.10.2026` 逐月備註亦按日期範圍歸月 |
| 暫停開放公告 | 官網公告表（關閉時間｜設施｜原因｜備註）逐列解析；原因欄為「其他」時由備註抽出實質原因（例：救生員人手不足） |
| 設施層級暫停 | 公告設施名與池設施名做正規化比對（含 `嬉水池 2&3` ↔ `嬉水池 (2), 嬉水池 (3)` 展開），命中的設施標紅 |
| 室內／戶外標記 | 由官網「室內設施／戶外設施」分段推出每項設施屬室內或戶外 |
| 18 區小地圖 | Leaflet + OpenStreetMap，46 個標記按狀態着色；點標記即跳去該泳池卡；18 區 chips 同步篩選地圖與列表 |
| 天文台警告條 | 讀 HKO `warnsum` + `rhrread`（每 5 分鐘、cache-buster）；八號或以上熱帶氣旋警告時**全部泳池覆寫為「天氣關閉」**，雷暴警告時按室內／戶外設施給出對應提示 |
| 公開 JSON API | `data/pools.json`：`application/json` + `Access-Control-Allow-Origin: *` + `Cache-Control: max-age=300`，附 `schemaVersion` / `generatedAt` / `sourceUrls` |

## 📍 覆蓋範圍

- **18 區 · 46 個公眾游泳池**（以官網 live 為準；康文署 2018 年大清潔時間表只有 44 個）
- 每池欄位：`name` / `nameEn` / `district`(+En,+Code) / `address`(+En) / `phone` / `facilities` / `facAreas` / `sessions` / `months` / `maintenance` / `cleaning` / `announcements` / `geo` / `officialUrl` / `photo`

## 🏗️ Architecture

```
康文署 18 區泳池頁 (Swimming.do?dist=loc1..18, tc+en)
        │  fetch_pools.py  ─ 逐 panel 解析
        ├─ 地址／電話／設施（含室內戶外）
        ├─ 逐月開放時間表（月份 → sessions / breaks / 維修備註）
        ├─ 每年維修工程（池 → 日期範圍，支援翌年）
        ├─ 每周大清潔行動（主日 + 假期後備日）
        └─ 暫停開放公告（時間範圍｜設施｜原因｜備註）
                 │
   map.gov.hk locationSearch（HK1980 → WGS84，pyproj EPSG:2326→4326）
   1823 官方 iCal（公眾假期）
                 │
        data/pools.json + data/pools.js   ← 公開資料檔（cron 每次覆寫）
                 │
        index.html + app.js + style.css   ← 靜態前端，狀態於瀏覽器即時計算
                 │
   HKO warnsum / rhrread（瀏覽器直接 fetch，CORS 開放）
                 │
        Cloudflare Pages（project: pools-we1co）→ https://pools.we1co.me
```

**資料流設計取捨**：爬蟲只負責「事實」（時間表、維修、清潔日、公告、座標），
「今日此刻是否開放」一律由瀏覽器用香港時間計算 —— 因此靜態資料每幾小時同步一次已足夠，
狀態仍然準到分鐘，亦令 API 消費者可自行用同一套規則渲染。

## 📡 Data API

```bash
curl -s https://pools.we1co.me/data/pools.json | jq '.pools[] | select(.district=="觀塘") | {name, sessions, cleaning}'
```

```jsonc
{
  "schemaVersion": 1,
  "generatedAt": "2026-10-17T08:42:37Z",
  "source": "康樂及文化事務署（LCSD）公眾游泳池網頁",
  "sourceUrls": { "pools": "…Swimming.do?dist=locN", "geocode": "…map.gov.hk/…", "holidays": "…1823…" },
  "districts": [{ "code": "loc9", "name": "觀塘", "nameEn": "Kwun Tong" }],
  "pools": [{
    "name": "佐敦谷游泳池", "nameEn": "Jordan Valley Swimming Pool",
    "district": "觀塘", "districtCode": "loc9", "address": "九龍牛頭角彩霞道6號",
    "phone": "2305 5919, 2305 5920",
    "facilities": ["訓練池", "嬉水池 1", "嬉水池 2&3", "嬉水池 4"],
    "facAreas": { "訓練池": "outdoor", "嬉水池 1": "outdoor" },
    "sessions":   [{ "label": "第一節", "start": "06:30", "end": "12:00", "text": "上午6時30分至中午12時" }],
    "breaks":     [{ "start": "12:00", "end": "13:00" }],
    "months":     { "十月": { "sessions": [], "breaks": [], "notes": ["只開放戶外泳池　室內泳池維修 : 11.9.2026 - 31.10.2026"] } },
    "maintenance": [{ "pool": "全場", "startMonth": 11, "startDay": 1, "endMonth": 3, "endDay": 31, "nextYear": true }],
    "cleaning":   { "day": "二", "fallback": "四", "raw": "逢星期二 (星期四 ※)" },
    "announcements": [{ "start": "2026-10-01T06:30", "end": "2026-10-31T12:00",
                        "facilities": ["嬉水池 (2)", "嬉水池 (3)"], "reason": "救生員人手不足", "remarks": "…" }],
    "geo": { "lat": 22.323901, "lng": 114.218738, "mapName": "佐敦谷游泳池", "mapDistrict": "觀塘區" },
    "officialUrl": "https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist=loc9",
    "photo": "https://www.lcsd.gov.hk/en/beach/common/graphics/SP/small/Jordon%20Valley%20SP.jpg"
  }]
}
```

## 🚀 Quick Start

```bash
git clone https://github.com/forumdata-collab/hk-public-pools.git
cd hk-public-pools
pip install -r requirements.txt          # 只一個依賴：pyproj（座標轉換）

python3 fetch_pools.py                   # 抓 18 區 → data/pools.json + data/pools.js（約 30 秒）
python3 -m http.server 8899              # 開 http://localhost:8899 睇站
```

### 環境變數（全部可選）

| 變數 | 用途 | 預設 |
|------|------|------|
| `CF_PROXY_TOKEN` / `CF_PROXY_TOKEN_FILE` | 康文署抓取用的 Cloudflare Worker proxy token（隱藏來源 IP、600s 快取） | 讀 `~/.config/lcsd_proxy_token`，冇就直連 |
| `LCSD_PROXY_URL` | Proxy 端點前綴 | `https://lcsd-proxy.forumdata.workers.dev/?url=` |
| `CF_PAGES_PROJECT` | 部署目標 Pages project | `pools-we1co` |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | `--deploy` 時 wrangler 用 | — |

### 部署

```bash
export CLOUDFLARE_API_TOKEN=…        # Pages 部署憑證（wrangler 只認呢個名）
export CLOUDFLARE_ACCOUNT_ID=…
python3 fetch_pools.py --deploy      # stage → bump ?v= → wrangler pages deploy dist/
bash run-sync.sh                     # 完整流程：抓取 + 部署 + live 收斂驗證（成功完全靜默）
```

`run-sync.sh` 會自動載入 `${HERMES_ENV:-$HOME/.hermes/.env}`（如你慣用集中式憑證檔，可用 `HERMES_ENV` 指向它）；
cron 使用時只需把 `run-sync.sh` 包一層 `~/.hermes/scripts/<name>.sh`（`exec bash <專案>/run-sync.sh`）。

`run-sync.sh` 設計成 cron watchdog：成功 **零輸出**；失敗或有欄位警告才印訊息並以非零 exit 結束。
Live 版本驗證會重試最多 6 次 × 15 秒（CF edge 需要時間收斂，一次唔中可以係快取未更新，唔應報錯）。

## 🧪 Testing

```bash
python3 tools/qa_offline.py            # 用 cache/ 的 HTML 重跑 parser：46/46 需有設施／時段／清潔日，0 警告
python3 tools/qa_offline.py --fetch    # 冇 cache 時可即場抓取（約 30 秒）
bash tools/check.sh                    # py_compile + node --check（CI 同款，離線可跑）
```

前端另備兩個測試鉤，可在瀏覽器 console 直接驗時間／天氣分支：

```js
__poolsStatus(POOLS_DATA.pools[0], new Date('2026-10-19T11:00:00'))  // 指定時間問狀態（假期改期／大清潔／維修／收館）
__poolsWx({ WTS: { name: '雷暴警告' } }, {})                          // 注入模擬警告，驗雷暴／八號／黑雨渲染
```

實測紀錄（2026-10）：46/46 池設施／時段／清潔日齊全；10/19 重陽節假期（星期一）維多利亞公園游泳池（清潔日星期一、後備五）→ 當日不設大清潔，改為 10/23（星期五）；八號風球情境下 46/46 池狀態覆寫為「天氣關閉」。

## 📜 Data sources & disclaimer

| 資料 | 來源 |
|------|------|
| 開放時間、設施、維修工程、每周大清潔、暫停開放公告 | 康文署公眾游泳池網頁（<https://www.lcsd.gov.hk/clpss/tc/webApp/Swimming.do?dist=locN>） |
| 惡劣天氣下的泳池安排 | 康文署《[雷暴警告下公眾游泳池及公眾泳灘的開放安排](https://www.lcsd.gov.hk/tc/beach/arrangements_under_thunderstorm_warning.html)》、《[康樂及體育設施使用條件](https://www.lcsd.gov.hk/tc/condition/index.html)》 |
| 座標 | 香港地圖服務（map.gov.hk）locationSearch，HK1980 格網 → WGS84 |
| 公眾假期 | 1823 官方 iCal |
| 天氣警告／即時天氣 | 香港天文台開放數據 API |

本項目為民間整理，**非康文署官方服務**；開放時間、通告及惡劣天氣安排一切以康文署現場公佈為準。
泳池名稱、地址、相片等資料版權屬康文署所有，本項目的資料檔僅為便於查閱的整理結果。

## 📄 License

程式碼以 [MIT](LICENSE) 授權（Copyright (c) 2026 forumdata-collab）。

---

[SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)
