# Proposition de déploiement OpenRAG sur VM `openrag-01-et` (51.159.184.192)

> Statut : draft, en cours d'application — 2026-04-25.
> Cible : VM Scaleway dédiée, IA externalisée vers le hub Mirai (LiteLLM + Kevent gateway), SSO via Keycloak Mirai, DNS sur sous-zone Scaleway dédiée.

## 1. Inventaire VM

| | |
|---|---|
| Hostname | `openrag-01-et` |
| IP publique | `51.159.184.192` |
| OS | Linux 6.8.0 x86_64 |
| CPU | 8 cores |
| RAM | 47 GB (dont ~46 GB libres au démarrage) |
| Disque | 112 GB SSD (4 GB utilisés) |
| GPU | **1× NVIDIA L4 (24 GB VRAM)** — utilisable pour Marker / VLM local si besoin |

Cette capacité GPU permet aussi un fallback local pour Whisper si l'on ne reçoit pas un token avec accès `audio` côté hub.

## 2. Services IA — sources et tests depuis la VM

**Trois endpoints** combinés pour couvrir l'ensemble des besoins OpenRAG :

| Source | URL | Auth | Usage |
|---|---|---|---|
| **LiteLLM Mirai** | `https://llm.api.ai.numerique-interieur.com` | `Authorization: Bearer sk-…` | LLM, embedder, reranker |
| **Kevent gateway Mirai** | `https://gateway.api.ai.numerique-interieur.com` | `apikey: Bearer <token>` | (whisper bloqué côté consumer_group) |
| **Scaleway Generative API** | `https://api.scaleway.ai/<project-EricTiquet>/v1` | `Authorization: Bearer <scw-secret>` | VLM, Whisper |

> L'admin du hub Mirai indique que l'ensemble migrera progressivement derrière Kevent, LiteLLM proposant de plus en plus de fonctionnalités payantes. Source : doc gateway https://github.com/IA-Generative/kevent-ai. Scaleway est un complément actuel, pas une alternative permanente.

### Modèles utilisés, **tous testés ✓ depuis la VM**

| Usage | Modèle | Source | Latence |
|---|---|---|---|
| LLM principal | `mistral-small-24b` | LiteLLM Mirai | **124 ms** |
| Embedder | `bge-multilingual-gemma2` (dim=3584) | LiteLLM Mirai | **97 ms** |
| Reranker | `bge-multilingual-gemma2` (Cohere-compat) | LiteLLM Mirai `/v1/rerank` | **65 ms** |
| **VLM** (image captioning) | `mistral-small-3.2-24b-instruct-2506` | **Scaleway** | **177 ms** |
| **Transcription** | `whisper-large-v3` | **Scaleway** `/v1/audio/transcriptions` | **260 ms** |

Alternatives Scaleway si besoin : `pixtral-12b-2409` (VLM 12B plus léger), `voxtral-small-24b-2507` (audio Mistral), `qwen3-embedding-8b` (embedder alternatif).

Modèles Mirai disponibles non utilisés : `gptoss-120b`, `qwen3-coder-30b`, `code`, `tools`, `tools-fast`, `classifier`, `guardrail`, `chat-smart`, `mistral-medium-albert` (Albert État, plus lent).

### Statut Whisper Mirai (Kevent)

Endpoint `gateway.api.ai.numerique-interieur.com/v1/audio/transcriptions` accessible mais le token Kevent fourni dans `/root/hub-llm.txt` renvoie 401 *"please check the consumer_group_id for this request"* — son consumer_group APISIX ne couvre pas la route audio. Demande envoyée à l'admin du hub pour étendre les droits, mais **non bloquant** : Whisper passe désormais par Scaleway.

## 3. SSO Keycloak Mirai

- Issuer : `https://sso.mirai.interieur.gouv.fr/realms/mirai` (discovery OIDC testée ✓)
- `AUTH_MODE=oidc` (mode OpenID Connect autorisation code + PKCE)
- **Un seul client Keycloak `openrag`** partagé entre les 2 VMs OpenRAG (cf. `deploy/keycloak/openrag-client.json`)
- Les 2 VMs vivent dans 2 sous-zones DNS distinctes du domaine `fake-domain.name` :
  - VM 1 (existante, `51.159.119.187`) → `openrag.fake-domain.name` (api/indexer/chat)
  - VM 2 (nouvelle, `51.159.184.192`) → `openrag-mirai.fake-domain.name` (api/indexer/chat)
- 12 `redirectUris` whitelistés (3 préfixes × 2 sous-zones × 2 domaines `fake-domain.name` / `numerique-interieur.com`), back-channel logout configuré sur les 4 hosts API
- Sessions indépendantes par VM (table `oidc_sessions` PostgreSQL locale à chaque VM)
- **Audience cross-services** : `openrag` est inclus comme audience explicite dans les tokens Keycloak (mapper `oidc-audience-mapper` côté `openrag-client.json`), et OpenRAG active son validateur bearer JWT (`OIDC_ISSUER_URL` + `OIDC_AUDIENCE=openrag` côté `.env`). Cela prépare la propagation imminente du token utilisateur depuis **Open WebUI vers OpenRAG** : il restera juste à demander à l'admin Keycloak d'ajouter un mapper audience symétrique sur le client `open-webui`.

## 4. Topologie de déploiement

```
                    ┌──────────────────────────────┐
                    │  Hub LLM Mirai (externe)     │
                    │  ┌────────┐    ┌──────────┐  │
                    │  │LiteLLM │    │ Kevent   │  │
                    │  │/v1/*   │    │ gateway  │  │
                    │  └────────┘    └──────────┘  │
                    └──────────┬───────────────────┘
                               │ HTTPS + Bearer / apikey
                               │
   Internet ──► Caddy ──► OpenRAG API (FastAPI / Ray)
   (TLS LE)        │            │
   *.openrag-mirai │            ├─► PostgreSQL  (local Docker, persistant)
   .fake-domain    │            ├─► Milvus + etcd + minio  (local, vector store)
                   │            └─► Marker  (local PDF parsing, CPU-bound)
                   │
                   ├──► Indexer Admin UI  (Vite static, port 3042)
                   └──► Chainlit chat     (sub-path FastAPI port 8080)
```

## 5. Choix de déploiement et justifications

### Externalisation IA → maximale

Tous les services IA passent par le hub Mirai via env vars :

| Variable | Valeur | Source |
|---|---|---|
| `BASE_URL`, `API_KEY`, `MODEL` | `https://llm.api.ai.numerique-interieur.com/v1` + `sk-AD…` + `mistral-small-24b` | **Mirai** LiteLLM |
| `EMBEDDER_BASE_URL`, `EMBEDDER_API_KEY`, `EMBEDDER_MODEL_NAME` | (idem) + `bge-multilingual-gemma2` | **Mirai** LiteLLM |
| `RERANKER_PROVIDER=openai`, `RERANKER_BASE_URL`, `RERANKER_API_KEY`, `RERANKER_MODEL_NAME` | (idem) + `bge-multilingual-gemma2` | **Mirai** LiteLLM `/v1/rerank` |
| `VLM_BASE_URL`, `VLM_API_KEY`, `VLM_MODEL` | `https://api.scaleway.ai/a9158aac…/v1` + `<scw-secret>` + `mistral-small-3.2-24b-instruct-2506` | **Scaleway** GenAI |
| `TRANSCRIBER_BASE_URL`, `TRANSCRIBER_API_KEY`, `TRANSCRIBER_MODEL_NAME` | (même endpoint Scaleway) + `whisper-large-v3` | **Scaleway** GenAI |

Conséquence : **vLLM, Reranker Infinity, Whisper local — tous désactivés** dans `docker-compose`. La VM peut tourner sans GPU pour OpenRAG (le L4 reste disponible pour Marker accéléré ou un fallback whisper local plus tard).

### Services conservés en local

| Service | Image | Pourquoi local |
|---|---|---|
| `openrag` (FastAPI / Ray) | applicatif | cœur métier |
| `rdb` (PostgreSQL 15) | `postgres:15` | données utilisateur, sessions OIDC, jobs, files |
| Milvus stack (`milvus`, `etcd`, `minio`) | `milvusdb/milvus:*` | vector store hybride (dense + BM25) |
| Marker | inclus dans image openrag | parsing PDF — CPU-bound, 4–8 cores |
| `indexer-ui` (Vite static) | `linagora/openrag-admin-ui` | UI admin |
| Chainlit | sub-path FastAPI | UI chat |
| **Caddy** (reverse proxy) | `caddy:2` | TLS Let's Encrypt + routing par Host header |

### Profil Docker

`docker compose up -d` (profil GPU activable si on choisit d'utiliser le L4 pour Marker), sans `vllm-gpu` ni `reranker` (ces services sont externalisés). L'option `--profile cpu` reste disponible si on veut neutraliser totalement la dépendance NVIDIA.

## 6. Mapping ports / hosts

DNS sur sous-zone dédiée **`openrag-mirai.fake-domain.name`** (créée dans le projet Scaleway de l'utilisateur, projet `default` de `scw config`).

| Hôte public | Records DNS | Reverse proxy → conteneur:port |
|---|---|---|
| `api.openrag-mirai.fake-domain.name` | A → 51.159.184.192 | `openrag:8080` (FastAPI) |
| `indexer.openrag-mirai.fake-domain.name` | A → 51.159.184.192 | `indexer-ui:3042` |
| `chat.openrag-mirai.fake-domain.name` | A → 51.159.184.192 | `openrag:8080` (sub-path Chainlit) |
| `*.openrag-mirai.fake-domain.name` | A → 51.159.184.192 | wildcard catch-all (extensibilité future, ex. `metrics.…`) |

Tous les records ont **TTL 60s** (pivot rapide possible). La sous-zone est totalement séparée de l'ancienne (`openrag.fake-domain.name` → 51.159.119.187), donc bascule de prod sans interférence.

## 7. Sécurité

- TLS Let's Encrypt automatique via Caddy
- `AUTH_MODE=oidc` + bearer `users.token` toujours dispo pour appels API programmatiques
- `SUPER_ADMIN_MODE=false`
- `DEFAULT_FILE_QUOTA=100` (configurable)
- `OIDC_TOKEN_ENCRYPTION_KEY` généré localement (Fernet 32B)
- Aucun secret committé : `.env` réel reste sur la VM, seul `.env.example.vm` est versionné
- Project-id Scaleway **jamais hardcodé** dans le repo (le script `deploy/scripts/dns_setup.sh` lit `default-project-id` de `scw config`)

## 8. Tests pré-déploiement validés ✓ (2026-04-25)

Avant tout déploiement effectif, les composants externes ont été validés depuis la VM :

| Composant | Test | Résultat |
|---|---|---|
| DNS `*.openrag-mirai.fake-domain.name` | `dig +short` via 1.1.1.1 | ✓ → `51.159.184.192` |
| SSO Mirai discovery | `GET /realms/mirai/.well-known/openid-configuration` | ✓ HTTP 200, `backchannel_logout_supported: true` |
| Hub LiteLLM Mirai | `GET /v1/models` (token `litellm`) | ✓ 14 modèles |
| Scaleway Generative API | `GET /v1/models` (token IAM `openrag-mirai`) | ✓ 14 modèles |
| Client OIDC `openrag` créé | onglet Credentials Keycloak | ✓ `clientSecret` 32 caractères |
| **Validation `client_secret`** | `POST /protocol/openid-connect/token` (grant `client_credentials`) | ✓ Keycloak retourne `unauthorized_client` (attendu : `serviceAccountsEnabled=false`), prouvant que **le secret est correct** (sinon `invalid_client`) |

L'environnement est prêt pour un `docker compose up -d`.

## 9. État d'avancement (référencé au plan d'exécution)

| Étape | Description | Statut |
|---|---|---|
| 0 | Pré-vérifs locales (scw, gh, ssh, repo) | ✅ |
| 1 | SSH inventaire VM + hub-llm.txt + tests modèles | ✅ |
| 2 | Sync repo + bump submodule indexer-ui (commit `2590037d`) + verif PRs | ✅ |
| 3 | **Ce document** + script DNS livré (`deploy/scripts/dns_setup.sh`) | ✅ (cette PR) |
| 4 | Sous-zone DNS `openrag-mirai.fake-domain.name` créée + 4 records | ✅ |
| 5 | Client OIDC Keycloak (JSON + README) | ⏳ |
| 6 | Config VM (`.env`, Caddyfile, docker compose up) | ⏳ |
| 7 | Tests post-déploiement | ⏳ |
| 8 | Rapport final | ⏳ |

## 9. Risques et points ouverts

- **Whisper indisponible** tant que le consumer_group du token kserve n'est pas étendu (demande envoyée à l'admin)
- **2e VM** : non précisée — placeholder dans les redirect URIs Keycloak
- **Migration LiteLLM → Kevent** : prévue côté hub Mirai. Notre config doit pouvoir basculer le `BASE_URL` vers Kevent quand l'admin nous le signale (changement d'env var seulement).
- **Modifs locales du submodule** (`UploadModal` accept étendu, `+layout` onMount) : à promouvoir upstream via PR sur `linagora/openrag-admin-ui` à terme, sinon elles dérivent à chaque bump.
- **Branche dev** : 63 commits ahead, 1 commit upstream (`437076c3`) qui est un squash de notre travail myrag — ne pas rebaser sans précaution.
