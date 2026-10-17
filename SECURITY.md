# Security Policy

## Reporting a vulnerability

請**不要**開公開 issue 揭露安全問題。改用 GitHub Security Advisory 私下回報：

<https://github.com/forumdata-collab/hk-public-pools/security/advisories/new>

我們會在 48 小時內確認收到，並就修補時間表與你聯絡。

## Scope

本專案為靜態網站 + 資料抓取腳本，最相關的風險類別：

- 資料抓取腳本對上游回應的處理（HTML 解析、注入面）
- 前端對資料檔／天文台 API 回應的渲染（XSS 逃逸）
- 憑證處理：所有 token 只經環境變數注入，repo 內不存任何憑證
