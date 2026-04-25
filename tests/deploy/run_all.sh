#!/usr/bin/env bash
# Lance la suite de tests post-déploiement OpenRAG :
#   1. smoke (curl/dig/openssl) — toujours
#   2. test_llm_hub.py — si BASE_URL et API_KEY définis (à lancer EN SSH sur la VM)
#   3. test_oidc_flow.py — toujours
#   4. test_indexing.py — si AUTH_TOKEN défini
#
# Usage :
#   bash tests/deploy/run_all.sh                    # smoke + oidc seulement
#   AUTH_TOKEN=... bash tests/deploy/run_all.sh     # + indexing
#   ssh root@<vm> 'cd /opt/openrag && \
#     env $(grep -v ^# .env | xargs) python -m pytest tests/deploy/test_llm_hub.py'

set -euo pipefail
cd "$(dirname "$0")/../.."

BASE_HOST="${BASE_HOST:-openrag-mirai.fake-domain.name}"
export BASE_HOST

errors=0

run() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
    shift
    if "$@"; then
        echo "  → OK"
    else
        echo "  → ÉCHEC"
        errors=$((errors + 1))
    fi
}

run "1. Smoke tests (DNS / TLS / endpoints publics)" \
    bash tests/deploy/smoke_test.sh "$BASE_HOST"

run "2. OIDC flow surface tests" \
    python -m pytest tests/deploy/test_oidc_flow.py -v --tb=short

if [[ -n "${BASE_URL:-}" && -n "${API_KEY:-}" ]]; then
    run "3. LLM hub tests (BASE_URL/API_KEY détectés)" \
        python -m pytest tests/deploy/test_llm_hub.py -v --tb=short
else
    echo ""
    echo "⏭  3. LLM hub tests sautés (BASE_URL/API_KEY absents — à lancer sur la VM)"
fi

if [[ -n "${AUTH_TOKEN:-}" ]]; then
    run "4. Indexing end-to-end tests (AUTH_TOKEN détecté)" \
        python -m pytest tests/deploy/test_indexing.py -v --tb=short
else
    echo ""
    echo "⏭  4. Indexing tests sautés (AUTH_TOKEN absent)"
fi

echo ""
echo "============================================================"
if [[ "$errors" == "0" ]]; then
    echo "  ✓ Tous les tests exécutés sont passés"
    exit 0
else
    echo "  ✗ $errors étape(s) en échec"
    exit 1
fi
