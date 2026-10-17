#!/bin/bash
# 全港公眾泳池站同步：抓康文署 18 區 → 寫 data/pools.* → 部署 Cloudflare Pages → 驗 live 收斂
#
# 設計：成功 = 完全靜默（exit 0、無 stdout）；失敗或抓取有欄位警告 = 印報告（非零 exit 令 cron 報警）。
# cron 用法：`~/.hermes/scripts/pools-hk-sync.sh` → exec 本腳本（cron 係新 env，唔會繼承任何變數）。
#
# 環境變數（全部可選）：
#   PROJECT_DIR       專案目錄（預設 = 本腳本所在目錄）
#   HERMES_ENV        憑證檔（預設 $HOME/.hermes/.env，載入 CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID）
#   POOLS_SITE_URL    live 驗證的站址（預設 https://pools.we1co.me）
set -o pipefail
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$PROJECT_DIR" || exit 1
LOG="$PROJECT_DIR/cache/sync-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

# cron 係新 env：自己載入憑證同 node PATH
ENV_FILE="${HERMES_ENV:-$HOME/.hermes/.env}"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }
export CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-$CF_WORKERS_TOKEN}"
export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-$CF_ACCOUNT_ID}"
export WRANGLER_CONFIG="${WRANGLER_CONFIG:-/tmp/empty.toml}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$(dirname "$(command -v node 2>/dev/null || echo /usr/bin/node)")"

python3 fetch_pools.py --deploy >>"$LOG" 2>&1
rc=$?
if [ $rc -ne 0 ] || ! grep -q "deploy=OK" "$LOG"; then
  echo "❌ 泳池站：抓取／部署失敗（rc=$rc）"
  tail -8 "$LOG" | sed 's/^/    /'
  exit 1
fi

# live 驗證（CF edge 需時收斂 → 必須重試，唔可以一次唔中就當失敗）
V=$(grep -oE 'pools\.js\?v=[0-9]+' "$PROJECT_DIR/dist/index.html" | head -1)
SITE="${POOLS_SITE_URL:-https://pools.we1co.me}"
OK=0
for _ in 1 2 3 4 5 6; do
  sleep 15
  LIVE_V=$(curl -s -m 20 "$SITE/?cb=$RANDOM" | grep -oE 'pools\.js\?v=[0-9]+' | head -1)
  if [ "$LIVE_V" = "$V" ]; then
    BODY=$(curl -s -m 25 "$SITE/data/$V&cb=$RANDOM")
    N=$(printf '%s' "$BODY" | python3 -c "import sys,re;print(len(re.findall(r'\"district\":', sys.stdin.read())))" 2>/dev/null)
    TODAY=$(printf '%s' "$BODY" | grep -c "\"generatedAt\":\"$(date -u +%Y-%m-%d)" || true)
    if [ -n "$N" ] && [ "$N" -ge 46 ] && [ "$TODAY" -ge 1 ]; then OK=1; break; fi
  fi
done
if [ $OK -ne 1 ]; then
  echo "❌ 泳池站：live 未收斂（local ${V:-?} / live ${LIVE_V:-?} / 泳池數 ${N:-?}）"
  exit 1
fi

# QA 有異常（例如某泳池欄位 parse 失敗）→ 報一次，唔好靜靜當成功
if grep -q "⚠️ QA" "$LOG"; then
  echo "⚠️ 泳池站：live 正常，但抓取有欄位警告"
  sed -n '/⚠️ QA/,$p' "$LOG" | head -8 | sed 's/^/    /'
  exit 0
fi
exit 0
