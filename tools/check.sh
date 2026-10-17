#!/bin/bash
# 離線靜態檢查（CI 同款）：Python 語法 + 前端 JS 語法；有 cache 就順便跑解析 QA。
set -e
cd "$(dirname "$0")/.."
echo "== python syntax =="
python3 -m py_compile fetch_pools.py tools/qa_offline.py
echo "  ok"
if command -v node >/dev/null 2>&1; then
  echo "== app.js syntax =="
  node --check app.js && echo "  ok"
else
  echo "== app.js syntax == skipped (no node)"
fi
if compgen -G "cache/loc*.tc.html" >/dev/null; then
  echo "== parser QA =="
  python3 tools/qa_offline.py || exit 1
else
  echo "== parser QA == skipped (no cache; run: python3 fetch_pools.py)"
fi
