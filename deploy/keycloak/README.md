# Client Keycloak OIDC pour OpenRAG

> Configuration livrée pour import dans le realm Mirai sur `https://sso.mirai.interieur.gouv.fr`. Un seul client est partagé entre toutes les VMs OpenRAG : ajouter de nouvelles `redirectUris` quand de nouvelles VMs s'ajoutent.

## Fichiers

| Fichier | Rôle |
|---|---|
| `openrag-client.json` | Manifest d'import au format Keycloak (clients export) |
| `README.md` | Ce document — guide d'import + variables `.env` à reporter |

## Import dans Keycloak

### Option A — Via la console admin (recommandée)

1. Se connecter à la console admin du realm Mirai (URL fournie séparément).
2. Sélectionner le realm `mirai` (issuer confirmé : `https://sso.mirai.interieur.gouv.fr/realms/mirai`, discovery testée ✓).
3. **Clients → Create client → Import client** : charger `openrag-client.json`.
4. Vérifier que `Client ID = openrag`, `Client authentication = ON`, `Standard flow = ON`, autres flows OFF.
5. **Save**.
6. Onglet **Credentials** → noter ou régénérer le `Client secret` — c'est lui qui ira dans `OIDC_CLIENT_SECRET` (jamais committer).

### Option B — Via `kcadm.sh` (si vous avez les credentials admin)

```bash
kcadm.sh config credentials --server https://sso.mirai.interieur.gouv.fr \
  --realm master --user <admin> --password <password>

kcadm.sh create clients -r mirai -f deploy/keycloak/openrag-client.json

# Récupérer le secret
CID=$(kcadm.sh get clients -r mirai -q clientId=openrag --fields id --format csv --noquotes | tail -1)
kcadm.sh get clients/$CID/client-secret -r mirai
```

## Variables `.env` à coller côté OpenRAG sur chaque VM

```bash
AUTH_MODE=oidc

OIDC_ENDPOINT=https://sso.mirai.interieur.gouv.fr/realms/mirai
OIDC_CLIENT_ID=openrag
OIDC_CLIENT_SECRET=<récupéré dans la console Keycloak — voir étape 6>
OIDC_REDIRECT_URI=https://api.openrag-mirai.fake-domain.name/auth/callback

# Fernet key — générer avec :
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
OIDC_TOKEN_ENCRYPTION_KEY=<générée localement par VM>

# Mapping de claims IdP -> users.* OpenRAG (whitelist : display_name, email)
OIDC_CLAIM_MAPPING=display_name:name,email:email

# Optionnel — par défaut : "openid email profile offline_access"
# OIDC_SCOPES=openid email profile offline_access

# Optionnel — URL de retour après logout (sinon Keycloak redirige sur sa page d'accueil)
# OIDC_POST_LOGOUT_REDIRECT_URI=<à définir si on veut une landing page custom>
```

## Provisionnement utilisateurs

OpenRAG **ne crée pas automatiquement** les utilisateurs depuis l'IdP. Sur la première connexion d'un utilisateur, OpenRAG cherche `users.external_user_id == <sub IdP>` et renvoie 403 si introuvable.

Pré-créer chaque utilisateur via l'API admin :

```bash
curl -X POST https://api.openrag-mirai.fake-domain.name/users/ \
  -H "Authorization: Bearer <AUTH_TOKEN admin>" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Alice",
    "external_user_id": "<sub Keycloak de Alice>",
    "is_admin": false
  }'
```

Le `sub` Keycloak est récupérable :
- Console Keycloak → Users → sélectionner l'utilisateur → champ `ID` (UUID).
- Ou via décodage d'un access token (`https://jwt.io`) → claim `sub`.

Si `OIDC_CLAIM_MAPPING` est positionné, le `display_name` et l'`email` sont synchronisés à chaque login depuis l'ID token (whitelist stricte : seuls `display_name` et `email` sont écrasables, jamais `is_admin`, `external_user_id`, `file_quota` ou `token`).

## Multi-VM (notes)

Le client `openrag` est **partagé entre les 2 VMs** OpenRAG, qui vivent chacune dans leur propre **sous-zone DNS Scaleway** sur `fake-domain.name` :

| VM | Sous-zone DNS | Hôtes publics | IP |
|---|---|---|---|
| **VM 1** (existante / legacy) | `openrag.fake-domain.name` | `api.openrag.…`, `indexer.openrag.…`, `chat.openrag.…` | `51.159.119.187` |
| **VM 2** (nouvelle, openrag-01-et) | `openrag-mirai.fake-domain.name` | `api.openrag-mirai.…`, `indexer.openrag-mirai.…`, `chat.openrag-mirai.…` | `51.159.184.192` |

Le manifest `openrag-client.json` déclare donc **6 `redirectUris`** (3 par zone) et **6 `webOrigins`**. Vérifier dans la console Keycloak après import qu'aucun n'a été tronqué.

- `chat.openrag.fake-domain.name` retourne actuellement 404 sur la VM 1 (Chainlit non servi côté legacy). Le redirect URI est néanmoins whitelisté de manière préventive — si Chainlit est activé plus tard, pas de modif Keycloak nécessaire.
- Chaque VM stocke ses sessions dans sa propre table PostgreSQL `oidc_sessions` — il n'y a pas d'affinité ni de session sharing à mettre en place.
- Le `client_secret` est **partagé** entre les 2 VMs (un seul client → un seul secret). Distribuer via votre canal sécurisé habituel (Vault, ou env injection au déploiement). Le rotation se fait dans la console Keycloak (onglet *Credentials*) puis re-déploiement des deux VMs simultanément.
- Le back-channel logout est configuré sur **deux URLs** (séparées par un espace dans `attributes.backchannel.logout.url`) — Keycloak les notifie toutes les deux, garantissant que la révocation côté IdP atteint les deux instances.

## Sécurité

- `clientAuthenticatorType: client-secret` (confidential client). Ne **jamais** committer le secret.
- `consentRequired: false` — les utilisateurs internes Mirai ne doivent pas voir la page de consentement Keycloak.
- `directAccessGrantsEnabled: false` — pas de password grant (force le flow OIDC standard).
- `implicitFlowEnabled: false` — pas de flow implicite (déprécié OAuth 2.1).
- `frontchannelLogout: false` — on utilise uniquement le back-channel logout.
- `access.token.lifespan: 1800` (30 min) — équilibre entre UX et sécurité ; OpenRAG re-fetch via refresh token quand l'AT expire (TTL de session aligné côté VM).
