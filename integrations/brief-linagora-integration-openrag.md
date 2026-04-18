# OpenRAG — Retour d'analyse et propositions pour l'integration Mirai

**De :** Eric Tiquet  
**A :** Equipe Linagora — OpenRAG  
**Date :** 18 avril 2026  
**Objet :** Integration d'OpenRAG avec Open WebUI, Keycloak et Scaleway — constats et evolutions souhaitees

---

## Contexte

Nous deployon OpenRAG comme backend RAG au sein de l'environnement **Mirai**, compose de :

- **Open WebUI** — interface de chat (port 3000)
- **Keycloak** — SSO et gestion des identites (port 8082)
- **Scaleway Generative APIs** — LLM et embeddings (pas de GPU local)
- **Pipelines Open WebUI** — orchestration (port 9099)

L'objectif est un deploiement local Docker ou OpenRAG s'integre nativement a cette stack, avec un SSO unique via Keycloak et une gestion des droits par partition basee sur les groupes Keycloak.

Nous avons realise un audit complet du code OpenRAG (backend, frontend Indexer-UI, Docker, tests) et teste les builds. Nous avons egalement examine les evolutions recentes sur la branche `dev`.

---

## 1. Ce qui fonctionne deja — felicitations

### 1.1 — OIDC natif sur la branche `dev` (v1.1.8+)

La branche `dev` embarque une implementation OIDC remarquable, bien plus complete que ce que nous attendions :

- **Auth code + PKCE server-side** — Le flow complet est gere cote serveur (`/auth/login` -> Keycloak -> `/auth/callback`) avec session cookie chiffree (Fernet). Pas besoin de oauth2-proxy.

- **Session management** — Sessions persistees en base, tokens chiffres au repos, support des refresh tokens avec renouvellement automatique.

- **Back-channel logout** — Support du RP-initiated logout (`/auth/logout`) et du back-channel logout Keycloak (`/auth/backchannel-logout`) pour la revocation de session.

- **Claim mapping configurable** — `OIDC_CLAIM_MAPPING=display_name:name,email:email` permet de synchroniser les champs utilisateur depuis le JWT ou le endpoint userinfo, avec whitelist de securite.

- **Endpoint `/auth/me`** — Debug/health endpoint qui retourne l'identite de l'utilisateur authentifie.

### 1.2 — Autres evolutions notables (main)

- **Config Hydra -> Pydantic** — Migration propre vers `conf/config.yaml` + modeles Pydantic. Plus maintenable et type-safe.

- **API Users refactorisee** — `POST /users/` et `PATCH /users/{id}` utilisent du JSON body (modeles Pydantic `UserCreate`/`UserUpdate`) au lieu de Form data. Champ `external_user_id` supporte nativement.

- **Reranker OpenAI** — Nouveau backend `RERANKER_PROVIDER=openai` qui permet d'utiliser un reranker via API compatible OpenAI (potentiellement via Scaleway).

- **Workspaces** — Sous-collections dans les partitions, avec CRUD complet et filtrage dans search/chat.

- **Prometheus monitoring** — Endpoint `/metrics` + stack Grafana preconfiguree.

### 1.3 — API d'administration

CRUD complet des utilisateurs (JSON body), quotas, tokens, memberships par partition. Tout est accessible via des endpoints REST documentes, ce qui nous permet de scripter la synchronisation.

---

## 2. Points de friction restants

### 2.1 — Profil Docker sans GPU / sans VLLM

**Constat :** Les services `openrag` et `openrag-cpu` declarent des `depends_on` vers `vllm-gpu`/`vllm-cpu` et `reranker`/`reranker-cpu`. Quand on utilise une API externe (Scaleway, OpenAI, etc.), ces dependances bloquent le demarrage.

**Contournement actuel :** Nous utilisons un fichier `docker-compose.override.yaml` qui ecrase les `depends_on`.

**Evolution souhaitee :** Un profil Docker officiel type `external-llm` ou `api-only` :

```yaml
openrag-api:
  <<: *openrag_template
  depends_on:
    rdb: { condition: service_started }
    milvus: { condition: service_healthy }
  profiles: ["external-llm"]
```

**Effort estime :** ~2h | **Impact :** debloque le deploiement sans GPU pour tous les integrateurs.

---

### 2.2 — Indexer-UI et le mode OIDC

**Constat :** L'Indexer-UI utilise un login par token statique. Le flow OIDC server-side de la branche `dev` (`/auth/login` -> cookie de session) resout le probleme cote API, mais l'Indexer-UI est un frontend SvelteKit separe qui ne beneficie pas de ce flow.

**Questions :**
- L'Indexer-UI est-elle prevue pour fonctionner derriere le meme flow cookie-based que le backend ? (redirect `/auth/login?next=http://localhost:3042/`)
- Ou faut-il un flow PKCE dedie cote client SvelteKit ?
- La branche `feat/indexerui-base-path` semble amorcer du travail sur ce sujet — est-ce lie ?

**Ce qu'il faudrait a minima :** Que l'Indexer-UI detecte `AUTH_MODE=oidc` (via `/api/config`) et redirige vers `/auth/login` au lieu d'afficher le formulaire token.

---

### 2.3 — Recherche d'utilisateur par identifiant externe

**Constat :** La methode `get_user_by_external_id(sub)` existe dans le backend mais n'est pas exposee en endpoint REST. Notre script de sync doit lister tous les utilisateurs et filtrer cote client.

**Evolution souhaitee :**

```
GET /users/?external_user_id={sub}
```

**Effort estime :** ~1h | **Impact :** rend les scripts de sync idempotents et performants.

---

### 2.4 — Pre-provisioning des utilisateurs et sync groupes

**Constat :** Le mode OIDC de la branche `dev` ne semble pas inclure la synchronisation automatique des groupes Keycloak vers les `PartitionMembership` (contrairement au code que nous avions vu precedemment dans `openrag/auth/oidc.py`). Le flow actuel sur `dev` fait du matching `sub` -> `external_user_id` et du claim mapping, mais pas de group-based partition access.

**Questions :**
- La sync de groupes (rag-admin/, rag-edit/, rag-query/ -> PartitionMembership) est-elle prevue sur `dev` ?
- Sinon, est-ce que l'approche par script externe (notre `sync_keycloak_openrag.py`) est la solution recommandee ?

---

## 3. Ce que nous avons prepare

Pour ne pas bloquer notre deploiement, nous avons developpe trois composants d'integration qui fonctionnent **sans modification du code OpenRAG** :

### 3.1 — Docker Compose overlay

Fichier `docker-compose.integration.yaml` qui :
- Supprime les dependances vllm/reranker
- Configure le mode OIDC natif (variables `OIDC_ENDPOINT`, `OIDC_CLIENT_ID`, etc.)
- Connecte OpenRAG au reseau Docker owuicore-main

### 3.2 — Script de synchronisation Keycloak -> OpenRAG

Script Python (`sync_keycloak_openrag.py`) qui :
- S'authentifie aupres de Keycloak via un service account (`client_credentials`)
- Liste les utilisateurs et leurs groupes
- Parse les groupes `rag-admin/`, `rag-edit/`, `rag-query/`
- Pre-provisionne les comptes via `POST /users/` (JSON body, compatible v1.1.8+)
- Cree les partitions et assigne les memberships
- Mode `--dry-run` pour previsualiser
- Executable en cron

### 3.3 — Template d'environnement

Fichier `.env.integration.example` preconfigure pour :
- APIs Scaleway (embeddings `bge-multilingual-gemma2`, LLM `mistral-small-3.2-24b-instruct-2506`, VLM `pixtral-12b-2409`)
- Variables OIDC Keycloak (format branche `dev`)
- Ports sans collision avec le socle owuicore-main

---

## 4. Configuration Keycloak cible

| Element | Configuration | Usage |
|---------|---------------|-------|
| Realm | `openrag` | Isole les utilisateurs OpenRAG |
| Client `openrag` | Confidential, redirect URI vers `/auth/callback` | Flow OIDC natif |
| Client `openrag-sync` | Service account, role `view-users` | Script de synchronisation |
| Mapper de groupes | Claim `groups` dans le scope du client | Si sync groupes activee |
| Groupes | `rag-admin/<partition>`, `rag-edit/<partition>`, `rag-query/<partition>` | Mapping vers les roles de partition |

---

## 5. Synthese des evolutions souhaitees

| # | Evolution | Effort | Priorite | Justification |
|---|-----------|--------|----------|---------------|
| 1 | Profil Docker `external-llm` sans vllm/reranker | ~2h | P0 | Deploiement sans GPU |
| 2 | Endpoint filtre `GET /users/?external_user_id=` | ~1h | P0 | Sync Keycloak idempotente |
| 3 | Redirect OIDC dans l'Indexer-UI quand `AUTH_MODE=oidc` | ~1j | P1 | SSO pour l'admin UI |
| 4 | Sync groupes Keycloak -> PartitionMembership (si pas prevu) | ~2j | P1 | Droits par partition automatiques |

**Cout total estime : 2 a 4 jours de developpement.**

---

## 6. Questions ouvertes

1. Le mode OIDC de la branche `dev` est-il prevu pour merger dans `main` prochainement ? Pouvons-nous baser notre deploiement dessus ?
2. La sync de groupes Keycloak vers les partitions est-elle dans la roadmap, ou doit-on la gerer en externe (script de sync) ?
3. Comment l'Indexer-UI est-elle prevue pour fonctionner en mode OIDC ? Redirect vers `/auth/login` ou flow PKCE client-side ?
4. Un profil Docker sans inference locale est-il envisage officiellement ?
5. Seriez-vous ouverts a integrer nos composants (script de sync, compose overlay) dans le repository, par exemple dans un dossier `contrib/` ?

---

Nous restons disponibles pour echanger sur ces sujets et contribuer aux evolutions si necessaire. Les composants que nous avons developpes sont fonctionnels et compatibles avec la v1.1.8+.

Cordialement,  
Eric Tiquet
