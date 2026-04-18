#!/usr/bin/env bash
# Setup Keycloak realm, client, groups and test user for OpenRAG
# Usage: KEYCLOAK_ADMIN_PASSWORD=xxx ./setup-keycloak.sh
set -euo pipefail

KC_URL="${KEYCLOAK_URL:-http://localhost:8082}"
KC_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KC_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?Set KEYCLOAK_ADMIN_PASSWORD}"
REALM="openrag"
CLIENT_ID="openrag"
REDIRECT_URI="${OPENRAG_REDIRECT_URI:-http://localhost:8180/auth/callback}"
POST_LOGOUT_URI="${OPENRAG_POST_LOGOUT_URI:-http://localhost:3042}"
SYNC_CLIENT_ID="openrag-sync"
TEST_USER="testuser"
TEST_PASSWORD="testpass123"

echo "=== Authenticating to Keycloak at $KC_URL ==="
KC_TOKEN=$(curl -sf -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" \
  -d "username=$KC_ADMIN" \
  -d "password=$KC_ADMIN_PASSWORD" \
  -d "grant_type=password" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

AUTH="Authorization: Bearer $KC_TOKEN"

# --- Create realm ---
echo "=== Creating realm: $REALM ==="
curl -sf -o /dev/null -w "%{http_code}" -X POST "$KC_URL/admin/realms" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"realm\": \"$REALM\", \"enabled\": true}" 2>/dev/null || true

# --- Create main client (confidential, auth code + PKCE) ---
echo "=== Creating client: $CLIENT_ID ==="
CLIENT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")
curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/clients" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"clientId\": \"$CLIENT_ID\",
    \"enabled\": true,
    \"protocol\": \"openid-connect\",
    \"publicClient\": false,
    \"secret\": \"$CLIENT_SECRET\",
    \"standardFlowEnabled\": true,
    \"directAccessGrantsEnabled\": false,
    \"serviceAccountsEnabled\": false,
    \"redirectUris\": [\"$REDIRECT_URI\"],
    \"postLogoutRedirectUris\": [\"$POST_LOGOUT_URI\"],
    \"webOrigins\": [\"http://localhost:8180\", \"http://localhost:3042\"],
    \"attributes\": {
      \"backchannel.logout.url\": \"http://openrag:8080/auth/backchannel-logout\",
      \"backchannel.logout.session.required\": \"true\",
      \"pkce.code.challenge.method\": \"S256\"
    }
  }" 2>/dev/null || echo "(client may already exist)"

# Get client internal ID
CLIENT_UUID=$(curl -sf "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" \
  -H "$AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")

# If client already existed, update the secret
curl -sf -o /dev/null -X PUT "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"secret\": \"$CLIENT_SECRET\"}" 2>/dev/null || true

# --- Add groups mapper to client scope ---
echo "=== Adding groups mapper ==="
# Get the client's dedicated scope
DEDICATED_SCOPE_ID=$(curl -sf "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/default-client-scopes" \
  -H "$AUTH" | python3 -c "
import sys, json
scopes = json.load(sys.stdin)
# Find dedicated scope or first one
for s in scopes:
    if 'dedicated' in s.get('name', '').lower() or s.get('name') == '$CLIENT_ID':
        print(s['id']); break
else:
    if scopes: print(scopes[0]['id'])
" 2>/dev/null || echo "")

# Add protocol mapper for groups directly on the client
curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"name\": \"groups\",
    \"protocol\": \"openid-connect\",
    \"protocolMapper\": \"oidc-group-membership-mapper\",
    \"config\": {
      \"full.path\": \"true\",
      \"id.token.claim\": \"true\",
      \"access.token.claim\": \"true\",
      \"claim.name\": \"groups\",
      \"userinfo.token.claim\": \"true\"
    }
  }" 2>/dev/null || echo "(mapper may already exist)"

# --- Create sync service account client ---
echo "=== Creating sync client: $SYNC_CLIENT_ID ==="
SYNC_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(24))")
curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/clients" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"clientId\": \"$SYNC_CLIENT_ID\",
    \"enabled\": true,
    \"protocol\": \"openid-connect\",
    \"publicClient\": false,
    \"secret\": \"$SYNC_SECRET\",
    \"standardFlowEnabled\": false,
    \"directAccessGrantsEnabled\": false,
    \"serviceAccountsEnabled\": true
  }" 2>/dev/null || echo "(sync client may already exist)"

# Grant realm-management view-users role to sync service account
SYNC_UUID=$(curl -sf "$KC_URL/admin/realms/$REALM/clients?clientId=$SYNC_CLIENT_ID" \
  -H "$AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])" 2>/dev/null || echo "")

if [ -n "$SYNC_UUID" ]; then
  SA_USER_ID=$(curl -sf "$KC_URL/admin/realms/$REALM/clients/$SYNC_UUID/service-account-user" \
    -H "$AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

  if [ -n "$SA_USER_ID" ]; then
    RM_CLIENT_UUID=$(curl -sf "$KC_URL/admin/realms/$REALM/clients?clientId=realm-management" \
      -H "$AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])" 2>/dev/null || echo "")

    if [ -n "$RM_CLIENT_UUID" ]; then
      VIEW_USERS_ROLE=$(curl -sf "$KC_URL/admin/realms/$REALM/clients/$RM_CLIENT_UUID/roles/view-users" \
        -H "$AUTH" 2>/dev/null || echo "")
      if [ -n "$VIEW_USERS_ROLE" ]; then
        curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/users/$SA_USER_ID/role-mappings/clients/$RM_CLIENT_UUID" \
          -H "$AUTH" -H "Content-Type: application/json" \
          -d "[$VIEW_USERS_ROLE]" 2>/dev/null || true
      fi
    fi
  fi
fi

# --- Create groups ---
echo "=== Creating groups ==="
for group in "rag-admin" "rag-edit" "rag-query"; do
  # Create parent group
  curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/groups" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"name\": \"$group\"}" 2>/dev/null || true

  # Create a "default" sub-group for testing
  PARENT_ID=$(curl -sf "$KC_URL/admin/realms/$REALM/groups?search=$group&exact=true" \
    -H "$AUTH" | python3 -c "import sys,json; groups=json.load(sys.stdin); print(groups[0]['id'] if groups else '')" 2>/dev/null || echo "")

  if [ -n "$PARENT_ID" ]; then
    curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/groups/$PARENT_ID/children" \
      -H "$AUTH" -H "Content-Type: application/json" \
      -d "{\"name\": \"default\"}" 2>/dev/null || true
  fi
done

# --- Create test user ---
echo "=== Creating test user: $TEST_USER ==="
curl -sf -o /dev/null -X POST "$KC_URL/admin/realms/$REALM/users" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"username\": \"$TEST_USER\",
    \"email\": \"testuser@example.com\",
    \"firstName\": \"Test\",
    \"lastName\": \"User\",
    \"enabled\": true,
    \"emailVerified\": true,
    \"credentials\": [{\"type\": \"password\", \"value\": \"$TEST_PASSWORD\", \"temporary\": false}]
  }" 2>/dev/null || echo "(user may already exist)"

# Add test user to rag-admin/default group
TEST_USER_ID=$(curl -sf "$KC_URL/admin/realms/$REALM/users?username=$TEST_USER&exact=true" \
  -H "$AUTH" | python3 -c "import sys,json; users=json.load(sys.stdin); print(users[0]['id'] if users else '')" 2>/dev/null || echo "")

RAG_ADMIN_ID=$(curl -sf "$KC_URL/admin/realms/$REALM/groups?search=rag-admin&exact=true" \
  -H "$AUTH" | python3 -c "
import sys, json
groups = json.load(sys.stdin)
for g in groups:
  for child in g.get('subGroups', []):
    if child['name'] == 'default':
      print(child['id']); break
" 2>/dev/null || echo "")

if [ -n "$TEST_USER_ID" ] && [ -n "$RAG_ADMIN_ID" ]; then
  curl -sf -o /dev/null -X PUT "$KC_URL/admin/realms/$REALM/users/$TEST_USER_ID/groups/$RAG_ADMIN_ID" \
    -H "$AUTH" 2>/dev/null || true
  echo "  Added $TEST_USER to rag-admin/default"
fi

echo ""
echo "============================================"
echo "  Keycloak setup complete!"
echo "============================================"
echo ""
echo "  Realm:           $REALM"
echo "  Client ID:       $CLIENT_ID"
echo "  Client Secret:   $CLIENT_SECRET"
echo "  Sync Client ID:  $SYNC_CLIENT_ID"
echo "  Sync Secret:     $SYNC_SECRET"
echo "  Test User:       $TEST_USER / $TEST_PASSWORD"
echo "  Redirect URI:    $REDIRECT_URI"
echo ""
echo "  --> Put these in your .env:"
echo "  OIDC_CLIENT_SECRET=$CLIENT_SECRET"
echo "  KEYCLOAK_CLIENT_SECRET=$SYNC_SECRET"
echo ""
