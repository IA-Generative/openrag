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

## 2. Hub LLM Mirai — services testés depuis la VM

Deux endpoints disponibles dans `/root/hub-llm.txt` :
- **LiteLLM** (proxy unifié OpenAI-compat) — `https://llm.api.ai.numerique-interieur.com`
- **Kevent gateway** (gateway custom Mirai pour audio) — `https://gateway.api.ai.numerique-interieur.com`

> L'admin du hub indique que l'ensemble migrera progressivement derrière Kevent, LiteLLM proposant de plus en plus de fonctionnalités payantes. Source : doc gateway https://github.com/IA-Generative/kevent-ai

### Modèles utiles à OpenRAG, **testés ✓ depuis la VM**

| Usage OpenRAG | Modèle | Endpoint | Test | Latence |
|---|---|---|---|---|
| LLM principal | `mistral-small-24b` | LiteLLM `/v1/chat/completions` | ✓ "pong" | **124 ms** |
| LLM qualité (Albert / État) | `mistral-medium-albert` | LiteLLM `/v1/chat/completions` | ✓ + carbon footprint | 307 ms |
| LLM rapide (alias) | `chat-small` | LiteLLM `/v1/chat/completions` | ✓ | 161 ms |
| Embedder principal | `bge-multilingual-gemma2` | LiteLLM `/v1/embeddings` | ✓ dim=3584 | **97 ms** |
| Reranker | `bge-multilingual-gemma2` | LiteLLM `/v1/rerank` (Cohere-compat) | ✓ scores | **65 ms** |
| Transcription | `faster-whisper-large-v3-turbo` | Kevent `/v1/audio/transcriptions` | **bloqué** : token `kserve` reconnu mais `consumer_group` ne couvre pas la route audio | — |

Modèles disponibles non retenus pour l'instant : `gptoss-120b`, `qwen3-coder-30b`, `code`, `tools`, `tools-fast`, `classifier`, `guardrail`, `chat-smart`, `pyannote-diarization`.

VLM : **aucun** (pas de `gpt-4-vision`, `mistral-medium-vision`, etc.). Image captioning sera désactivé au démarrage.

### Statut Whisper

L'endpoint `/v1/audio/transcriptions` existe et est accessible, mais le token disponible (`kserve` du `hub-llm.txt`) renvoie 401 *"please check the consumer_group_id for this request"*. Demande envoyée à l'admin du hub pour ajouter la route audio au consumer group du token, ou émettre un token dédié à OpenRAG. En attendant, transcription désactivée (`TRANSCRIBER_BASE_URL` vide). Aucune incidence sur la chaîne RAG documentaire.

## 3. SSO Keycloak Mirai

- Issuer : `https://sso.mirai.interieur.gouv.fr/realms/<realm-mirai>`
- `AUTH_MODE=oidc` (mode OpenID Connect autorisation code + PKCE)
- Client OIDC à créer (cf. `deploy/keycloak/openrag-client.json` à venir, étape 5 du plan)
- 1 seul client Keycloak partagé entre les VMs OpenRAG (plusieurs `redirect_uris`), sessions indépendantes par VM (table `oidc_sessions` PostgreSQL locale à chaque VM)

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

| Variable | Valeur | Service |
|---|---|---|
| `BASE_URL`, `API_KEY`, `MODEL` | `https://llm.api.ai.numerique-interieur.com/v1` + `sk-AD…` + `mistral-small-24b` | LLM principal |
| `EMBEDDER_BASE_URL`, `EMBEDDER_API_KEY`, `EMBEDDER_MODEL_NAME` | (idem) + `bge-multilingual-gemma2` | Embeddings |
| `RERANKER_PROVIDER=openai`, `RERANKER_BASE_URL`, `RERANKER_API_KEY`, `RERANKER_MODEL_NAME` | (idem) + `bge-multilingual-gemma2` | Rerank (Cohere-compat) |
| `TRANSCRIBER_BASE_URL`, `TRANSCRIBER_API_KEY` | **vide** au démarrage (en attente du token audio) | Whisper |
| `VLM_BASE_URL` | **vide** | (aucun VLM exposé par le hub) |

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

## 8. État d'avancement (référencé au plan d'exécution)

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
