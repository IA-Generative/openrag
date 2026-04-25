# Prompts d'implementation — Integration OpenRAG + Open WebUI + Keycloak + Scaleway

> Ce document contient les prompts et notes intermediaires pour le deploiement
> local d'OpenRAG integre a l'ecosysteme owuicore-main.

---

## Prompt 0 / Intermediaire — Etat des lieux et configuration

### 0.1 — Allocation des ports Docker (sans collision)

Ports du socle owuicore-main :

| Port  | Service socle      |
|-------|--------------------|
| 3000  | openwebui          |
| 5432  | postgres           |
| 8082  | keycloak           |
| 8083  | searxng            |
| 9098  | tika               |
| 9099  | pipelines          |

Ports OpenRAG choisis :

| Variable               | Port   | Service                |
|------------------------|--------|------------------------|
| `APP_PORT`             | 8180   | OpenRAG API (FastAPI)  |
| `CHAINLIT_PORT`        | 8190   | Chainlit Chat UI       |
| `RAY_DASHBOARD_PORT`   | 8265   | Ray Dashboard          |
| `INDEXERUI_PORT`       | 3042   | Indexer UI (SvelteKit) |

Services internes OpenRAG (pas de mapping host) :
rdb (5432), milvus (19530), etcd (2379), minio (9000/9001), reranker (7997).

### 0.2 — Remplacement VLLM par API Scaleway

Au lieu de deployer vllm-cpu/vllm-gpu localement, utiliser les APIs
Scaleway Generative (compatibles OpenAI).

```bash
# .env OpenRAG — section Embedder via Scaleway
EMBEDDER_BASE_URL=https://api.scaleway.ai/<SCW_PROJECT_ID>/v1
EMBEDDER_API_KEY=<SCW_SECRET_KEY>
EMBEDDER_MODEL_NAME=bge-multilingual-gemma2

# .env OpenRAG — section LLM via Scaleway
BASE_URL=https://api.scaleway.ai/<SCW_PROJECT_ID>/v1
API_KEY=<SCW_SECRET_KEY>
MODEL=mistral-small-3.2-24b-instruct-2506
# Alternatives : gpt-oss-120b, llama-3.3-70b-instruct, qwen3-235b-a22b-instruct-2507

# VLM (si besoin de captioning d'images)
VLM_BASE_URL=https://api.scaleway.ai/<SCW_PROJECT_ID>/v1
VLM_API_KEY=<SCW_SECRET_KEY>
VLM_MODEL=pixtral-12b-2409

# Desactiver le reranker (pas dispo sur Scaleway)
RERANKER_ENABLED=false
```

Note : Scaleway a des limites de rate sur les embeddings (erreur 429).
Si probleme, reduire `RETRIEVER_TOP_K` ou utiliser un embedder local.

Impact docker-compose : supprimer les `depends_on` vers `vllm-gpu`/`vllm-cpu`
et `reranker`/`reranker-cpu`. Ne plus builder ces services.

### 0.3 — Architecture OAuth2 Proxy (Option 1)

```
[Navigateur]
     |
     v
[oauth2-proxy :4180]  <-->  [Keycloak :8082/realms/openrag]
     |
     +---> [OpenRAG API :8180]     (AUTH_MODE=oidc)
     +---> [Indexer UI :3042]      (passe le JWT en Authorization)
```

Le backend OpenRAG possede deja un mode `AUTH_MODE=oidc` complet :
- Validation JWT via JWKS (`openrag/auth/oidc.py`)
- Auto-provisioning des utilisateurs (`OIDC_AUTO_PROVISION=true`)
- Sync groupes Keycloak -> PartitionMembership
- 2 modes de sync : `additive` et `authoritative`
- Tests unitaires : `openrag/auth/test_oidc.py`, `openrag/auth/test_group_sync.py`

Configuration backend :
```bash
AUTH_MODE=oidc
OIDC_ISSUER_URL=http://keycloak:8080/realms/openrag
OIDC_AUDIENCE=openrag
OIDC_AUTO_PROVISION=true
OIDC_GROUP_CLAIM=groups
OIDC_GROUP_PREFIX_VIEWER=rag-query/
OIDC_GROUP_PREFIX_EDITOR=rag-edit/
OIDC_GROUP_PREFIX_OWNER=rag-admin/
OIDC_GROUP_SYNC_MODE=additive
```

### 0.4 — Inventaire des tests

| Categorie        | Commande                                           | Fichiers |
|------------------|----------------------------------------------------|----------|
| Unit tests       | `uv run pytest openrag/`                           | 16       |
| Auth/OIDC        | `uv run pytest openrag/auth/`                      | 2        |
| API tests (mock) | `tests/api_tests/api_run/scripts/run_api_tests_local.sh` | 10 |
| Robot Framework  | `robot tests/api/`                                 | 10       |
| Smoke tests      | `tests/smoke_test_data/run_smoke_test.sh`          | scripts  |
| Linting          | `uv run ruff check openrag/ tests/`                | -        |

### 0.5 — User Management API (Backend existant)

| Methode | Path                                      | Auth    | Description                    |
|---------|-------------------------------------------|---------|--------------------------------|
| GET     | `/users/`                                 | Admin   | Lister tous les utilisateurs   |
| GET     | `/users/info`                             | Any     | Info utilisateur courant       |
| POST    | `/users/`                                 | Admin   | Creer un utilisateur           |
| DELETE  | `/users/{user_id}`                        | Admin   | Supprimer un utilisateur       |
| POST    | `/users/{user_id}/regenerate_token`       | Admin   | Regenerer le token API         |
| PATCH   | `/users/{user_id}/quota`                  | Admin   | Modifier le quota fichiers     |
| GET     | `/partition/{p}/users`                    | Owner   | Lister les membres             |
| POST    | `/partition/{p}/users`                    | Owner   | Ajouter un membre              |
| DELETE  | `/partition/{p}/users/{uid}`              | Owner   | Retirer un membre              |
| PATCH   | `/partition/{p}/users/{uid}`              | Owner   | Modifier le role               |

Token format : `or-{32 hex chars}` (SHA-256 en base).

### 0.6 — Matching comptes Keycloak <-> OpenRAG

| Champ Keycloak       | Champ OpenRAG                   |
|----------------------|---------------------------------|
| `sub` (JWT claim)    | `users.external_user_id`        |
| `preferred_username` | `users.display_name`            |
| Groupes JWT          | `partition_memberships` (source="oidc") |

Le mode `AUTH_MODE=oidc` avec `OIDC_AUTO_PROVISION=true` cree
automatiquement le compte OpenRAG a la premiere requete JWT valide.
Les groupes Keycloak au format `rag-admin/<partition>`, `rag-edit/<partition>`,
`rag-query/<partition>` sont automatiquement syncs vers les PartitionMembership.

---

## Prompt 1 / 5 — Authentification OIDC Keycloak

```markdown
# Contexte

Tu travailles sur OpenRAG, un framework RAG (FastAPI + Ray + Milvus) dont le code est dans ce repo.
L'auth actuelle utilise des tokens statiques SHA-256 stockes en base (voir `openrag/api.py` class `AuthMiddleware` et `openrag/components/indexer/vectordb/utils.py` class `PartitionFileManager`).

Je veux ajouter un mode d'authentification OIDC/JWT compatible Keycloak, **en parallele** du mode token existant.

# Objectif

Implementer 3 chantiers :
1. Un middleware OIDC dans OpenRAG
2. La synchronisation automatique des groupes Keycloak vers les PartitionMembership
3. La documentation de configuration Open WebUI pour forwarder les tokens

# STATUT : DEJA IMPLEMENTE

Ce prompt a ete realise. Les fichiers suivants existent :
- `openrag/auth/oidc.py` — validation JWT + parsing groupes + sync memberships
- `openrag/auth/test_oidc.py` — tests unitaires validation JWT
- `openrag/auth/test_group_sync.py` — tests sync additive/authoritative
- `openrag/api.py` — AuthMiddleware supporte AUTH_MODE=oidc
- `.env.example` — variables OIDC_* documentees
- Migration Alembic pour `external_user_id` et `source` sur PartitionMembership
```

---

## Prompt 2 / 5 — Profils d'indexation + Base Q&R (evaluation et surcharge)

```markdown
# Contexte

Tu travailles sur OpenRAG (FastAPI + Ray + Milvus). L'authentification OIDC Keycloak a ete implementee (prompt precedent). 

Actuellement, la configuration de chunking/retrieval est **globale** via Hydra YAML (`.hydra_config/`). La factory de chunker est dans `openrag/components/indexer/chunker/chunker.py` (`ChunkerFactory.create_chunker`), invoquee par `Indexer.chunk()` dans `openrag/components/indexer/indexer.py`.

Je veux :
1. Des **profils d'indexation** editables par l'admin, assignables par partition
2. Une **base de Q&R** pour evaluer le RAG et surcharger certaines reponses

# Specifications detaillees

## 2.1 — Profils d'indexation par partition

### Nouvelles tables (migration Alembic)

```sql
indexing_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    chunker_name VARCHAR(50) DEFAULT 'recursive_splitter',
    chunk_size INT DEFAULT 512,
    chunk_overlap_rate FLOAT DEFAULT 0.2,
    contextual_retrieval BOOLEAN DEFAULT true,
    contextualization_timeout INT DEFAULT 120,
    max_concurrent_contextualization INT DEFAULT 10,
    retriever_type VARCHAR(50) DEFAULT 'single',
    retriever_top_k INT DEFAULT 50,
    similarity_threshold FLOAT DEFAULT 0.6,
    extra_params JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
)

partition_indexing_config (
    partition_name VARCHAR PRIMARY KEY REFERENCES partitions(partition_name) ON DELETE CASCADE,
    indexing_profile_id INT NOT NULL REFERENCES indexing_profiles(id),
    overrides JSONB DEFAULT '{}'
)
```

### Modeles SQLAlchemy

Ajouter les modeles `IndexingProfile` et `PartitionIndexingConfig` dans `openrag/components/indexer/vectordb/utils.py` (a cote des modeles existants).

### Endpoints (nouveau router `openrag/routers/admin.py`)

| Endpoint | Methode | Auth | Description |
|----------|---------|------|-------------|
| `GET /admin/indexing-profiles` | GET | admin | Lister tous les profils |
| `POST /admin/indexing-profiles` | POST | admin | Creer un profil |
| `GET /admin/indexing-profiles/{id}` | GET | admin | Detail d'un profil |
| `PUT /admin/indexing-profiles/{id}` | PUT | admin | Modifier un profil |
| `DELETE /admin/indexing-profiles/{id}` | DELETE | admin | Supprimer (erreur si utilise par une partition) |
| `GET /admin/partitions/{name}/indexing` | GET | owner | Config indexation de la partition |
| `PUT /admin/partitions/{name}/indexing` | PUT | owner | Assigner profil + overrides |

### Impact sur le pipeline d'indexation

1. Modifier `ChunkerFactory.create_chunker(config, profile=None)` : si `profile` est fourni, il remplace les valeurs Hydra correspondantes
2. Modifier `Indexer.chunk()` : avant de chunker, charger le profil de la partition via `vectordb.get_partition_indexing_config.remote(partition_name)`. Si aucun profil assigne, utiliser la config Hydra globale (comportement actuel).
3. Ajouter une methode `get_partition_indexing_config(partition_name)` sur le Ray actor `Vectordb`/`MilvusDB`
4. Au **boot**, creer un profil `"default"` initialise depuis les valeurs Hydra actuelles (idempotent, ne pas ecraser s'il existe)

### Re-indexation

Ne PAS re-indexer automatiquement au changement de profil. Ajouter un endpoint :
`POST /admin/partitions/{name}/reindex` (auth: owner) — cree une tache async qui supprime les chunks existants et re-indexe tous les fichiers de la partition avec le nouveau profil.

## 2.2 — Base de Q&R

(voir contenu original prompt 2 — inchange)
```

---

## Prompt 3 / 5 — Connecteur Drive (Suite Numerique)

(inchange — voir version originale)

---

## Prompt 4 / 5 — Boucle de feedback (Open WebUI -> OpenRAG -> Q&R)

(inchange — voir version originale)

---

## Prompt 5 / 5 — Annonces, sondages et canaux de notification

(inchange — voir version originale)

---

## Prompt 6 (nouveau) — Script de sync Keycloak -> OpenRAG (sans modification de code)

```markdown
# Contexte

OpenRAG dispose deja de :
- `AUTH_MODE=oidc` avec auto-provisioning (cree le user a la premiere requete JWT)
- API REST d'admin pour gerer les users et partitions

Le probleme : l'auto-provisioning ne se declenche qu'a la premiere requete
d'un utilisateur. On veut pouvoir pre-provisionner les comptes AVANT
que l'utilisateur ne se connecte, par exemple pour :
- Pre-creer des partitions et assigner des droits
- Synchroniser un batch d'utilisateurs Keycloak
- Avoir un annuaire a jour

# Solution : script externe de sync (zero modification de code)

## Fonctionnement

Script Python standalone qui :
1. Interroge l'API admin Keycloak pour lister les utilisateurs et groupes
2. Pour chaque utilisateur Keycloak, appelle l'API admin OpenRAG pour :
   a. Creer le compte si inexistant
   b. Creer les partitions necessaires
   c. Assigner les memberships selon les groupes Keycloak

## Pre-requis

- Un token admin OpenRAG (AUTH_TOKEN du .env ou un user admin)
- Un service account Keycloak avec le role `realm-management/view-users`
- Acces reseau aux deux APIs

## API Keycloak utilisees

- `GET /admin/realms/{realm}/users` — lister les utilisateurs
- `GET /admin/realms/{realm}/users/{id}/groups` — groupes d'un utilisateur
- `POST /realms/{realm}/protocol/openid-connect/token` — obtenir un token admin

## API OpenRAG utilisees

- `GET /users/` — lister les users existants
- `POST /users/` — creer un user
- `POST /partition/{name}` — creer une partition
- `POST /partition/{name}/users` — ajouter un membre avec role
- `PATCH /partition/{name}/users/{uid}` — modifier le role

## Logique de sync

1. Obtenir un token admin Keycloak (client_credentials)
2. Lister tous les utilisateurs Keycloak
3. Pour chaque utilisateur :
   a. Recuperer ses groupes
   b. Parser les groupes avec le meme format que le backend OIDC :
      - `rag-admin/<partition>` -> owner
      - `rag-edit/<partition>` -> editor
      - `rag-query/<partition>` -> viewer
   c. Verifier si l'utilisateur existe dans OpenRAG (par display_name
      ou external_user_id si accessible via l'API)
   d. Si non : creer via POST /users/
   e. Pour chaque partition :
      - Creer la partition si elle n'existe pas
      - Ajouter le membership avec le bon role

## Execution

- En one-shot : `python sync_keycloak_openrag.py`
- En cron : `*/30 * * * * python sync_keycloak_openrag.py`
- En docker : sidecar container avec un cron

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `KEYCLOAK_URL` | URL Keycloak (ex: http://localhost:8082) |
| `KEYCLOAK_REALM` | Nom du realm |
| `KEYCLOAK_CLIENT_ID` | Client ID du service account |
| `KEYCLOAK_CLIENT_SECRET` | Client secret |
| `OPENRAG_URL` | URL OpenRAG (ex: http://localhost:8180) |
| `OPENRAG_ADMIN_TOKEN` | Token admin OpenRAG |
| `DRY_RUN` | true/false — mode simulation |
```

---

## Notes d'utilisation

### Ordre d'execution

Les prompts doivent etre executes **dans l'ordre** (1->2->3->4->5->6).
Le prompt 1 est deja realise. Le prompt 6 est independant.

### Avant chaque prompt

> Lis d'abord le fichier `CLAUDE.md` a la racine du repo pour comprendre
> l'architecture, les conventions et les commandes. Puis lis les fichiers
> mentionnes dans la section "Fichiers a modifier" avant de commencer.

### Apres chaque prompt

```bash
uv run ruff check openrag/ tests/ integrations/
uv run ruff format openrag/ tests/ integrations/
uv run pytest
```
