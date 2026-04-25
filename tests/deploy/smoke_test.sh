#!/usr/bin/env bash
# Smoke tests — déploiement OpenRAG VM openrag-01-et
# Usage : bash tests/deploy/smoke_test.sh [base-host]
#   base-host : suffixe DNS racine (défaut : openrag-mirai.fake-domain.name)

set -euo pipefail

BASE="${1:-${BASE:-openrag-mirai.fake-domain.name}}"
API="https://api.${BASE}"
INDEXER="https://indexer.${BASE}"
CHAT="https://chat.${BASE}"

pass=0
fail=0

check() {
    local label="$1" cmd="$2" expected="$3"
    local actual
    actual=$(eval "$cmd" 2>/dev/null || echo "FAIL")
    if [[ "$actual" =~ ^${expected}$ ]]; then
        printf '\033[1;32m  ✓\033[0m %-55s -> %s\n' "$label" "$actual"
        pass=$((pass + 1))
    else
        printf '\033[1;31m  ✗\033[0m %-55s -> %s (attendu: %s)\n' "$label" "$actual" "$expected"
        fail=$((fail + 1))
    fi
}

NC_BASE="${NC_BASE:-openrag-mirai.numerique-interieur.com}"
NC_API="https://api.${NC_BASE}"
NC_INDEXER="https://indexer.${NC_BASE}"
NC_CHAT="https://chat.${NC_BASE}"

echo "============ Smoke tests OpenRAG ============"
echo "Base canonical     : $BASE"
echo "Base non-canonical : $NC_BASE  (doit redir 301 vers le canonical)"
echo ""

echo "--- DNS canonical ---"
check "api.${BASE}    résout"     "dig +short api.${BASE} @1.1.1.1 | head -1"     '51\.[0-9.]+'
check "indexer.${BASE} résout"   "dig +short indexer.${BASE} @1.1.1.1 | head -1" '51\.[0-9.]+'
check "chat.${BASE}   résout"     "dig +short chat.${BASE} @1.1.1.1 | head -1"    '51\.[0-9.]+'
echo ""

echo "--- DNS non-canonical (numerique-interieur.com) ---"
check "api.${NC_BASE}    résout"     "dig +short api.${NC_BASE} @1.1.1.1 | head -1"     '51\.[0-9.]+'
check "indexer.${NC_BASE} résout"   "dig +short indexer.${NC_BASE} @1.1.1.1 | head -1" '51\.[0-9.]+'
check "chat.${NC_BASE}   résout"     "dig +short chat.${NC_BASE} @1.1.1.1 | head -1"    '51\.[0-9.]+'
echo ""

echo "--- API health (canonical, direct) ---"
check "GET ${API}/health_check"               "curl -fsSL -o /dev/null -w '%{http_code}' --max-time 10 ${API}/health_check"           '200'
check "GET ${API}/version"                    "curl -fsSL -o /dev/null -w '%{http_code}' --max-time 10 ${API}/version"                '200'
echo ""

echo "--- Redirect non-canonical → canonical (3 hosts) ---"
for n in api indexer chat; do
    nc="https://${n}.${NC_BASE}/health_check"
    canon="https://${n}.${BASE}/health_check"
    check "${n}.${NC_BASE} -> 30x sur /health_check" \
          "curl -sI --max-time 10 ${nc} | awk 'NR==1{print \$2}' | tr -d '\\r'" \
          '30[1278]'
    check "${n}.${NC_BASE}  Location  -> ${n}.${BASE}" \
          "curl -sI --max-time 10 ${nc} | awk 'BEGIN{IGNORECASE=1} /^location/{print \$2}' | head -1 | tr -d '\\r'" \
          "${canon//\./\\.}.*"
    check "${n}.${NC_BASE} -L (redirect suivi) -> 200" \
          "curl -fsSL -o /dev/null -w '%{http_code}' --max-time 15 ${nc}" \
          '200'
done
echo ""

echo "--- OIDC redirect ---"
# /auth/login doit rediriger vers le SSO Mirai (Keycloak) en mode oidc.
check "GET ${API}/auth/login -> 302 vers SSO" \
      "curl -sI --max-time 10 ${API}/auth/login | awk 'BEGIN{IGNORECASE=1} /^location/{print \$2}' | head -1 | tr -d '\\r'" \
      'https://sso\.mirai\.interieur\.gouv\.fr/.*'
echo ""

echo "--- Indexer UI ---"
check "GET ${INDEXER}/ -> 200 ou 30x" \
      "curl -s -o /dev/null -w '%{http_code}' --max-time 10 ${INDEXER}/" \
      '(200|30[0-9])'
echo ""

echo "--- Chainlit (chat) ---"
check "GET ${CHAT}/ -> 200 ou 30x" \
      "curl -s -o /dev/null -w '%{http_code}' --max-time 10 ${CHAT}/" \
      '(200|30[0-9])'
echo ""

echo "--- TLS ---"
check "Cert. valide api.${BASE}" \
      "echo | openssl s_client -servername api.${BASE} -connect api.${BASE}:443 2>/dev/null | openssl x509 -noout -checkend 0 >/dev/null && echo OK || echo INVALID" \
      'OK'
echo ""

echo "============ Résultat ============"
echo "  ✓  $pass succès"
echo "  ✗  $fail échec(s)"
[[ "$fail" == "0" ]]
