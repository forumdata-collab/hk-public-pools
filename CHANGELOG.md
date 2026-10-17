# Changelog

本檔案格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號依 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [Unreleased]

## [1.0.0] - 2026-10-17

首個公開發布。

### Added
- 康文署 18 區共 **46 個公眾游泳池**的即時開放狀態站（<https://pools.we1co.me>）。
- 逐月開放時間表、每年維修工程、每周大清潔日（含公眾假期改期）、暫停開放公告解析。
- 前端狀態引擎（開放中／即將開始／部分設施暫停／部分設施維修／大清潔中／維修中／休館／天氣關閉），依香港時間每分鐘重算。
- Leaflet 小地圖：46 個標記按狀態着色、18 區 chips 篩選、點標記跳卡。
- 天文台警告條：讀 HKO `warnsum` + `rhrread`（每 5 分鐘、cache-buster）；八號或以上熱帶氣旋警告時全部泳池覆寫為「天氣關閉」；雷暴警告時按設施室內／戶外給出對應提示。
- 設施室內／戶外標記（`facAreas`）。
- 公開資料 API：`data/pools.json`（`application/json`、CORS `*`、`Cache-Control: max-age=300`），附 `schemaVersion` / `generatedAt` / `sourceUrls`。
- `run-sync.sh` cron watchdog（成功靜默、失敗或欄位警告才通知）與 live 收斂重試驗證。
- `tools/qa_offline.py` 解析 QA、`tools/check.sh` + GitHub Actions CI。

[Unreleased]: https://github.com/forumdata-collab/hk-public-pools/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/forumdata-collab/hk-public-pools/releases/tag/v1.0.0
