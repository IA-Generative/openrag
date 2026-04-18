# Capitalisation — Session de premiere utilisation OpenRAG + Mirai

> Journal des decisions, problemes rencontres et solutions appliquees
> lors de l'integration d'OpenRAG dans l'ecosysteme Mirai (Open WebUI + Keycloak + Scaleway).
>
> Date de debut : 17 avril 2026

---

## 1. Architecture deployee

```
[Navigateur]
     |
     +---> http://localhost:3000  → Open WebUI (chat, SSO Keycloak)
     +---> http://localhost:3042  → Indexer UI (upload de documents)
     +---> http://localhost:8180  → OpenRAG API (RAG, OIDC)
     +---> http://localhost:8082  → Keycloak Admin
     +---> http://localhost:8265  → Ray Dashboard

[Open WebUI] ---> [OpenRAG :8080] ---> [Milvus] + [PostgreSQL] + [Scaleway APIs]
     |                  |
     +-- owui-net ------+---> [Keycloak :8080]
```

- **LLM / Embeddings** : Scaleway Generative APIs (pas de GPU local)
- **Auth** : Keycloak realm `openwebui`, client unique `openwebui` partage entre OWUI et OpenRAG
- **Branche OpenRAG** : `dev` (v1.1.8, inclut le mode OIDC natif auth code + PKCE)

---

## 2. Problemes rencontres et solutions

### 2.1 VLLM ne demarre pas sur Mac ARM64
- **Cause** : Pas de manifest Docker ARM64 pour `vllm-cpu` et `reranker-cpu`
- **Solution** : Utiliser Scaleway APIs. Compose overlay (`integrations/docker-compose.integration.yaml`) qui ecrase les `depends_on` pour supprimer vllm/reranker
- **Limitation** : Le compose overlay ne peut pas supprimer un `depends_on` du fichier principal, seulement le merger. Il faut `docker stop` le vllm-cpu puis `docker start` openrag-cpu manuellement
- **Recommandation a Linagora** : Ajouter un profil Docker `external-llm` officiel

### 2.2 Volume SHARED_ENV et chemin hote vs conteneur
- **Cause** : `/$SHARED_ENV:/ray_mount/.env` dans le compose utilise `SHARED_ENV` a la fois pour le chemin hote (volume source) et le chemin conteneur (entrypoint `uv run --env-file`)
- **Solution** : Dans l'overlay, injecter `SHARED_ENV=/ray_mount/.env` dans la section `environment` du conteneur pour overrider la variable hote
- **Dans le .env** : `SHARED_ENV=/Users/etiquet/Documents/GitHub/openrag/.env` (chemin absolu hote)

### 2.3 DNS dans les conteneurs Docker (Mac)
- **Cause** : Resolution DNS echouait pour pypi.org pendant `uv sync` dans le conteneur
- **Solution** : Ajouter `dns: [8.8.8.8, 8.8.4.4]` dans l'overlay du service openrag-cpu

### 2.4 No space left on device
- **Cause** : Docker Desktop avait 54 GB de cache/images inutilisees
- **Solution** : `docker system prune -a --volumes -f` (42 GB recuperes), puis rebuild

### 2.5 Issuer mismatch OIDC (Keycloak vs OpenRAG)
- **Cause** : `OIDC_ENDPOINT` doit matcher **exactement** l'issuer retourne par Keycloak dans le `.well-known`. Mais :
  - `localhost:8082` n'est pas resolvable depuis le conteneur (localhost = le conteneur lui-meme)
  - `keycloak:8080` fonctionne pour le fetch mais l'issuer retourne est `localhost:8082` → mismatch
  - `host.docker.internal:8082` fonctionne dans le conteneur (Docker Desktop) mais pas dans le navigateur
- **Solution en 2 etapes** :
  1. Configurer le `frontendUrl` du realm Keycloak a `http://host.docker.internal:8082` (via API admin)
  2. Ajouter `127.0.0.1 host.docker.internal` dans `/etc/hosts` du Mac
- **Commande** : `echo "127.0.0.1 host.docker.internal" | sudo tee -a /etc/hosts`

### 2.6 HTTPS required sur le realm Keycloak
- **Cause** : Le realm `openrag` nouvellement cree avait `sslRequired=EXTERNAL` par defaut
- **Solution** : Passer a `NONE` via l'API admin Keycloak :
  ```bash
  curl -X PUT ".../admin/realms/openrag" -d '{"sslRequired": "NONE"}'
  ```

### 2.7 User not registered (OIDC login)
- **Cause** : Le mode OIDC de la branche `dev` ne fait PAS d'auto-provisioning. L'utilisateur doit exister dans OpenRAG avec le bon `external_user_id` (= `sub` Keycloak) AVANT de se connecter
- **Solution** : Provisionner les comptes via l'API admin OpenRAG avec le `sub` Keycloak comme `external_user_id`
- **Script** : Batch provisioning de tous les utilisateurs du realm `openwebui` via l'API admin Keycloak + API REST OpenRAG

### 2.8 Token admin reinitialise au restart
- **Cause** : Le bootstrap `_ensure_admin_user` ecrase le token admin a chaque demarrage
- **Solution** : Re-injecter le hash du token admin en base apres chaque restart :
  ```bash
  HASH=$(python3 -c "import hashlib; print(hashlib.sha256('or-admin-openrag-2026'.encode()).hexdigest())")
  docker exec openrag-rdb-1 psql -U root -d partitions_for_collection_vdb_test \
    -c "UPDATE users SET token='$HASH' WHERE id=1;"
  ```
- **Recommandation** : Configurer `AUTH_TOKEN=or-admin-openrag-2026` dans le `.env` pour que le bootstrap utilise ce token

### 2.9 File quota limit (-1 non gere par l'UI)
- **Cause** : Double probleme :
  1. L'Indexer UI verifie `total_files >= file_quota`. Quand `file_quota = -1`, `0 >= -1` = true → bloque
  2. Le endpoint `/users/info` retourne **toujours** `-1` pour les admins (hard-code lignes 69-70 de `users.py`) et quand `DEFAULT_FILE_QUOTA < 0` (defaut Pydantic)
- **Bug dans** : `Header.svelte` (check front) + `users.py` (logique admin)
- **Contournement** :
  1. Ajouter `DEFAULT_FILE_QUOTA=999999` dans le `.env`
  2. Ajouter `AUTH_TOKEN=or-admin-openrag-2026` pour stabiliser le token admin au restart
  3. Utiliser un **compte non-admin** pour l'Indexer UI (Eric Test, token : `or-3f8048addbdc7d6be07c767b09805be7`)
- **Recommandation a Linagora** : Corriger le check `file_quota` dans l'UI pour traiter `-1` comme illimite

### 2.11 Endpoint partition/users attend du Form data (pas JSON)
- **Cause** : `POST /partition/{p}/users` attend Form data, contrairement a `POST /users/` qui attend du JSON (migration v1.1.8 incomplete)
- **Solution** : Utiliser `-d "user_id=9" -d "role=owner"` au lieu de JSON
- **Impact** : Le script `sync_keycloak_openrag.py` doit utiliser Form data pour cet endpoint

### 2.12 Indexer UI supporte bien l'OIDC (commit c967017)
- **Decouverte** : Le submodule `extern/indexer-ui` (openrag-admin-ui) inclut deja le support OIDC depuis le commit `c967017` (17 avril 2026)
- **Fonctionnement** : L'entrypoint genere `config.json` avec `AUTH_MODE` depuis l'env. En mode `oidc`, le front skip le formulaire de token et redirige vers `{API_BASE_URL}/auth/login`
- **Configuration** : Ajouter `AUTH_MODE=oidc` et `INCLUDE_CREDENTIALS=true` dans l'env du service `indexer-ui`
- **Prerequis** : Le submodule doit etre a jour (`git submodule update` sur la branche dev)
- **Docs Linagora** : `docs/sso-quickstart.md` et `docs/oidc.md` sur la branche `dev`

### 2.13 Conteneur garde l'ancien OIDC_ENDPOINT apres changement .env
- **Cause** : Les variables d'environnement du conteneur sont injectees au `docker compose up`. Un `docker restart` ne relit pas le compose — il faut un `--force-recreate`
- **Symptome** : OIDC_ENDPOINT pointait vers `realms/openrag` au lieu de `realms/openwebui` apres modification du `.env`
- **Solution** : Toujours utiliser `docker compose up -d --force-recreate openrag-cpu` apres modification du `.env`

### 2.14 Token admin ecrase a chaque restart
- **Cause** : Le bootstrap `_ensure_admin_user` regenere le token si `AUTH_TOKEN` n'est pas dans l'env du conteneur. Le `.env` monte en `/ray_mount/.env` est lu par `uv run` mais pas par le bootstrap qui lit `os.getenv("AUTH_TOKEN")`
- **Solution** : Ajouter `AUTH_TOKEN=or-admin-openrag-2026` dans le `.env` ET s'assurer qu'il est dans la section `environment` du compose (via `env_file` ou directement)
- **Contournement** : Re-injecter le hash en base apres chaque restart :
  ```bash
  HASH=$(python3 -c "import hashlib; print(hashlib.sha256('or-admin-openrag-2026'.encode()).hexdigest())")
  docker exec openrag-rdb-1 psql -U root -d partitions_for_collection_vdb_test \
    -c "UPDATE users SET token='$HASH' WHERE id=1;"
  ```

### 2.15 MarkerPool crash au demarrage (PDF non indexables)
- **Cause** : L'actor Ray `MarkerPool` (traitement PDF avec OCR) crash apres le demarrage — probablement memoire ou timeout au telechargement du modele Marker depuis HuggingFace
- **Symptome** : Upload PDF → FAILED, erreur `Failed to look up actor with name 'MarkerPool'`
- **Solution** : `docker restart openrag-openrag-cpu-1` relance les actors. Attendre ~30s que MarkerPool soit pret avant d'uploader
- **Whisper** : Les actors WhisperActor echouent aussi (erreur 416 HuggingFace) — l'audio/video ne fonctionne pas en local. Non-bloquant pour PDF/TXT/DOCX
- **Recommandation** : Pour des tests fiables, uploader d'abord des fichiers TXT/MD, puis tester les PDF une fois MarkerPool stable
- **Root cause confirmee** : OOM Ray — les workers MarkerPool sont tues par le memory monitor de Ray quand la RAM est insuffisante. Log : `3 Workers killed due to memory pressure (OOM)`
- **Fix definitif** :
  1. Augmenter la memoire Docker Desktop (Settings > Resources > Memory) — 24 GB minimum recommande pour traiter des PDF volumineux (CESEDA = 1.9 MB)
  2. Ajouter `RAY_memory_monitor_refresh_ms=0` dans le `.env` pour desactiver le kill OOM de Ray (laisse le systeme swapper au lieu de tuer les workers)
- **Avant le fix** : OpenRAG avait 15.6 GB, consommait ~10 GB (Ray + Marker + actors), et les workers MarkerPool se faisaient tuer des qu'ils chargeaient le modele OCR
- **Apres le fix** : Docker a 24 GB, OOM killer desactive — l'OOM n'est plus le probleme

### 2.15b Bug pypdfium2 sur ARM64 — PDF toujours en echec apres fix OOM
- **Cause** : Apres resolution de l'OOM, un second bug apparait dans MarkerLoader :
  ```
  TypeError: 'PdfDocument' object does not support the context manager protocol
  ```
  La version de `pypdfium2` installee par `uv sync` n'est pas compatible avec le code de `marker.py` (ligne 194 : `with pypdfium2.PdfDocument(file_path) as pdf`)
- **Impact** : Tous les PDF echouent a l'indexation sur la branche `dev` en ARM64
- **Contournement** : Uploader des fichiers TXT, MD ou DOCX (qui utilisent d'autres loaders, pas MarkerPool)
- **Alternatives pour le CESEDA** :
  1. Convertir le PDF en TXT/MD en amont (ex: `pdftotext` ou extraction manuelle)
  2. Attendre un fix upstream de Linagora sur la compatibilite pypdfium2/ARM64
  3. Deployer sur x86_64 (Scaleway) ou le bug n'est probablement pas present
- **Recommandation a Linagora** : Epingler la version de pypdfium2 compatible avec le context manager protocol, ou adapter `_get_page_count` pour ne pas utiliser `with`

### 2.15c Indexer UI n'accepte que les PDF dans le selecteur de fichiers
- **Cause** : `UploadModal.svelte` ligne 398 contient `accept=".pdf"` en dur, alors que le backend supporte 19 formats (txt, md, docx, pptx, eml, images, audio, video)
- **Impact** : Impossible d'uploader des TXT/MD/DOCX via l'UI, meme si le backend les accepte. Bloquant quand les PDF echouent (bug pypdfium2 ARM64)
- **Fix applique** : Patch du `accept` pour inclure tous les formats supportes :
  ```
  accept=".pdf,.txt,.md,.docx,.pptx,.doc,.eml,.png,.jpeg,.jpg,.svg,.wav,.mp3,.flac,.ogg,.aac,.mp4"
  ```
- **Fichier** : `extern/indexer-ui/src/lib/components/indexer/UploadModal/UploadModal.svelte` ligne 398
- **Recommandation a Linagora** : Charger la liste des formats depuis l'endpoint `/indexer/supported/types` au lieu de la coder en dur. Ce endpoint existe deja et retourne les extensions et mimetypes acceptes

### 2.15d Pas de feedback utilisateur apres upload d'un fichier
- **Constat** : Apres avoir selectionne un fichier et clique Upload dans l'Indexer UI, aucun retour visuel ne confirme que le fichier a ete pris en compte (pas de toast, pas de barre de progression, pas de changement d'etat)
- **Impact UX** : L'utilisateur ne sait pas si l'upload a fonctionne, s'il est en cours de traitement, ou s'il a echoue. Il est tente de re-uploader le meme fichier
- **Ce qui se passe reellement** : Le fichier est envoye au backend, une tache d'indexation est creee (visible dans `/queue/tasks`), mais l'UI ne montre rien
- **Recommandation a Linagora** :
  1. Afficher une notification/toast de confirmation apres la reponse 201 du backend
  2. Montrer la tache dans la liste avec son etat (QUEUED → SERIALIZING → CHUNKING → INSERTING → COMPLETED ou FAILED)
  3. Idealement, poll l'endpoint `/indexer/task/{id}` pour mettre a jour la progression en temps reel

### 2.15e Dashboard clignote en boucle (flash infini)
- **Cause** : `$effect()` dans `dashboard/+layout.svelte` lit `page.route.id` et appelle `handleRouting()` qui modifie `dashboardData.actors` (un `$state`). Le changement de state retrigger le `$effect` → boucle infinie de re-renders
- **Impact** : Le dashboard clignote a ~60fps, inutilisable
- **Fix applique** : Remplacer `$effect(() => { handleRouting() })` par `onMount(() => { handleRouting() })` — le chargement initial ne se fait qu'une fois, le refresh periodique est gere par le composant Header
- **Fichier** : `extern/indexer-ui/src/routes/dashboard/+layout.svelte`
- **Recommandation a Linagora** : Auditer tous les `$effect` qui appellent des fonctions modifiant des `$state` — risque de boucles infinies avec Svelte 5

### 2.15f OIDC sur Indexer UI impossible en dev local (cross-origin cookies)
- **Cause** : L'Indexer UI (localhost:3042) et l'API OpenRAG (localhost:8180) sont sur des ports differents. Le cookie `openrag_session` pose par `/auth/callback` sur `:8180` n'est pas envoye par le navigateur lors des `fetch()` cross-origin depuis `:3042` (`SameSite=Lax` bloque les requetes cross-origin non-navigation)
- **Symptome** : Boucle de redirect infinie (~1 redirect/seconde) : dashboard → login → Keycloak (session active) → callback → dashboard → login → ...
- **Analyse HAR** : 50+ pages chargees en 20 secondes, toutes sur `/auth/login?next=...dashboard`
- **Pourquoi ca ne marche pas** :
  1. `SameSite=Lax` : cookie envoye sur navigation top-level mais pas sur `fetch()` cross-origin
  2. `SameSite=None` : necessite `Secure=true` qui necessite HTTPS — pas disponible en dev local
  3. Meme domaine (`localhost`) mais ports differents = origines differentes pour les cookies
- **Solution en production** : Deployer l'Indexer UI et l'API derriere le meme domaine/port via un reverse proxy (nginx, traefik). Ex: `rag.mycorp.com/` → API, `rag.mycorp.com/admin/` → Indexer UI
- **Solution en dev local** : Garder le mode token pour l'Indexer UI (`AUTH_MODE=token`), OIDC pour Open WebUI
- **Recommandation a Linagora** : Documenter cette limitation dans le SSO quickstart. Proposer un `docker-compose` avec un reverse proxy nginx qui sert les deux sur le meme port

### 2.15g Decision : Indexer UI reste en mode token
- **Decision** : Garder `AUTH_MODE=token` pour l'Indexer UI en dev local et pour le deploiement initial
- **Justification** : L'OIDC cross-origin ne fonctionne pas en local (cf. 2.15f). En production, le OIDC fonctionnera derriere un reverse proxy (meme domaine), mais ce n'est pas une priorite immediate
- **Token Indexer UI** : Utiliser un compte non-admin (Eric Test) pour eviter le bug quota -1 (cf. 2.9)
- **Auth recap** :
  | Service | Auth | Token/Credentials |
  |---------|------|-------------------|
  | Open WebUI (:3000) | OIDC Keycloak | SSO automatique |
  | OpenRAG API (:8180) | OIDC + Bearer token | Les deux en parallele |
  | Indexer UI (:3042) | Token statique | `or-bb48c5c78af06a5700aa20f19509cc81` (Eric Test) |
- **En production** : Passer l'Indexer UI en OIDC via reverse proxy (meme domaine que l'API)

### 2.15h OpenRAG non visible depuis Open WebUI (alias DNS manquant)
- **Cause** : L'alias `openrag` etait defini sur le reseau `openrag_default` mais pas sur `owui-net`. Open WebUI (sur `owui-net`) ne pouvait pas resoudre `http://openrag:8080`
- **Fix** : Ajouter `aliases: [openrag]` sous le reseau `owuicore` dans l'overlay compose
- **Verification** : `docker exec owuicore-openwebui-1 curl http://openrag:8080/v1/models` doit retourner les modeles
- **Config OWUI robuste au redemarrage** (`owuicore-main/.env`) :
  ```
  OPENAI_API_BASE_URLS=http://pipelines:9099/v1;https://api.scaleway.ai/.../v1;http://openrag:8080/v1
  OPENAI_API_KEYS=<pipelines_key>;<scaleway_key>;or-admin-openrag-2026
  ```

### 2.17 Ingestion MyRAG : endpoint synchrone trop lent pour gros documents
- **Constat** : L'endpoint `POST /api/ingest/{collection}` est synchrone — il decoupe le document puis uploade chaque chunk un par un vers OpenRAG. Pour le CESEDA (~1247 articles), cela prend plusieurs minutes et le navigateur timeout
- **Impact** : Le Swagger UI perd la connexion, l'utilisateur ne sait pas si ca fonctionne
- **Solution a implementer** :
  1. L'ingest retourne immediatement un `job_id` apres le decoupage
  2. L'upload des chunks se fait en tache de fond (asyncio / BackgroundTasks FastAPI)
  3. Endpoint `GET /api/ingest/{job_id}/status` pour suivre l'avancement (chunks uploaded / total)
  4. Le front MyRAG affiche une barre de progression
- **Donnees reelles** : CESEDA = 2399 taches OpenRAG, 543 completees en ~5 minutes, 0 echecs

### 2.18 RAG ne cite pas les articles (contenu des chunks sans entete)
- **Constat** : Apres indexation du CESEDA par article via MyRAG, le LLM repond correctement mais ne cite pas les numeros d'article
- **Cause** : Le contenu du chunk ne contenait que le texte de l'article, sans la ligne `Article Lxxx-x` ni la hierarchie (Livre/Titre/Chapitre)
- **Fix applique** : Le chunker prefixe chaque chunk avec `Article L110-1 — Livre I, Titre I` en debut de contenu
- **Metadata enrichies** : ajout de `page`, `parent_path` (ex: `Livre-I/Titre-II/Chapitre-Ier`), `referenced_by` (placeholder pour le graph), `graph_ready` (flag pour post-traitement)
- **Impact** : Il faut re-indexer le CESEDA avec le nouveau format pour que les citations fonctionnent

### 2.19 MyRAG (beta) — pas de front pour l'instant
- **Constat** : MyRAG n'a que l'API (Swagger sur http://localhost:8200/docs), pas de front
- **Le front DSFR (Nuxt 4 + vue-dsfr) est prevu en Phase 3** du plan (~4 semaines)
- **En attendant** : tester via Swagger (upload), Open WebUI (chat RAG), ou curl

### 2.16 Password manager ne capture pas les identifiants Keycloak
- **Cause** : Keycloak est accessible via `host.docker.internal:8082` (pas `localhost`), et les password managers ne reconnaissent pas ce domaine
- **Mots de passe des comptes de test** : pattern `{username}pwd` (ex: `eric` → `ericpwd`, `alexandre` → `alexandrepwd`)
- **Source** : `owuicore-main/keycloak/realm-openwebui.json`
- **Comptes generiques** : `user1` → `user1password`, `user2` → `user2password`, etc.

### 2.10 Client Keycloak unifie
- **Decision** : Utiliser un seul client `openwebui` dans le realm `openwebui` pour OWUI et OpenRAG
- **Configuration** : Ajouter les redirect URIs d'OpenRAG (`http://localhost:8180/auth/callback`) au client existant
- **Avantage** : Un seul secret a gerer, SSO seamless entre les deux services
- **Attention** : Apres changement de realm dans le `.env`, il faut `--force-recreate` le conteneur (cf. 2.13)

---

## 3. MyRAG (beta) — Bilan Phase 1

### Implementation realisee (11 commits, 68 tests)

| Module | Status | Tests |
|--------|--------|-------|
| FastAPI skeleton + Docker | ✅ | 6 |
| Chunker 4 strategies (article, section, Q&R, longueur) | ✅ | 30 |
| OpenRAG client (create partition, upload chunks, search) | ✅ | 6 |
| Ingest async avec job tracking + progression | ✅ | - |
| Metadata enrichies (sensibilite, hierarchie, references, graph_ready) | ✅ | - |
| Collections config + system prompt par collection | ✅ | 9 |
| 7 templates de prompt builtin + custom admin | ✅ | - |
| Keycloak client (groupes, membres, CRUD) | ✅ | 7 |
| Sync service KC → OpenRAG (auto-provision users + memberships) | ✅ | 6 |
| Fix regex hierarchie (Livre/Titre/Chapitre) | ✅ | - |
| Fix system prompt (citations articles, filtre AGDREF) | ✅ | - |

### Endpoints API disponibles

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /docs` | Swagger UI |
| `POST /api/ingest/{collection}` | Upload + decoupage + indexation async |
| `GET /api/ingest/jobs/{job_id}` | Suivi progression |
| `GET /api/ingest/jobs` | Liste tous les jobs |
| `POST /api/collections` | Creer une collection |
| `GET /api/collections` | Lister les collections |
| `GET /api/collections/{name}` | Detail collection |
| `PATCH /api/collections/{name}/system-prompt` | Modifier le system prompt |
| `GET /api/collections/{name}/system-prompt` | Voir le system prompt |
| `GET /api/collections/_templates` | Lister les templates de prompt |
| `POST /api/collections/_templates` | Creer un template custom |
| `POST /api/sync` | Sync tous les groupes KC → OpenRAG |
| `POST /api/sync/{collection}` | Sync un groupe KC |

### Templates de prompt builtin

| Template | Icon | Usage |
|----------|------|-------|
| `generic` | 📄 | Defaut, recherche documentaire |
| `juridique` | ⚖️ | Codes, lois, reglements |
| `ceseda` | 🛂 | CESEDA specialise |
| `multi_thematique` | 📚 | Gros corpus multi-domaines |
| `faq` | ❓ | Bases de connaissances Q&R |
| `multimedia` | 🎬 | Images, video, transcriptions |
| `technique` | 🔧 | Documentation technique |

### Test reel effectue

- CESEDA (2.3 MB, 63k lignes) decoupe en ~2399 articles
- Indexation async avec suivi de progression
- RAG fonctionnel dans Open WebUI (modele `openrag-ceseda-v3`)
- Citations d'articles dans les reponses (L423-1, L423-14, etc.)
- Filtrage AGDREF reussi via system prompt ameliore

---

## 4. Fichiers crees

| Fichier | Emplacement | Description |
|---------|-------------|-------------|
| `.env` | `openrag/` | Configuration locale (Scaleway + OIDC + ports) |
| `docker-compose.integration.yaml` | `openrag/integrations/` | Overlay Docker (sans vllm, avec OIDC, reseau owui-net) |
| `.env.integration.example` | `openrag/integrations/` | Template .env documente |
| `sync_keycloak_openrag.py` | `openrag/integrations/` | Script de sync Keycloak → OpenRAG |
| `setup-keycloak.sh` | `openrag/integrations/` | Script de setup realm/client Keycloak |
| `brief-linagora-integration-openrag.md` | `openrag/integrations/` | Brief a envoyer a Linagora |
| `guide-test-openrag.md` | `openrag/integrations/` | Guide de test des operations |
| `capitalisation-session.md` | `openrag/integrations/` | Ce fichier |

---

## 4. Configuration Keycloak

| Element | Valeur |
|---------|--------|
| Realm | `openwebui` |
| Client ID | `openwebui` (partage OWUI + OpenRAG) |
| Client Secret | `e05ce3f403fcf4aac67211d82bced83311eb7d46473445db` |
| Redirect URIs | `http://localhost:3000/*`, `http://localhost:8180/*` |
| PKCE | S256 |
| Backchannel logout | `http://openrag:8080/auth/backchannel-logout` |
| frontendUrl | `http://host.docker.internal:8082` |
| sslRequired | NONE (dev local) |
| Groupes crees | `rag-admin/default`, `rag-edit/default`, `rag-query/default` |

---

## 5. Ports utilises (sans collision)

| Port | Service | Stack |
|------|---------|-------|
| 3000 | Open WebUI | owuicore |
| 3042 | Indexer UI | openrag |
| 5432 | PostgreSQL (owuicore) | owuicore |
| 8082 | Keycloak | owuicore |
| 8180 | OpenRAG API | openrag |
| 8190 | Chainlit | openrag |
| 8265 | Ray Dashboard | openrag |
| 9099 | Pipelines | owuicore |

---

## 6. Commandes utiles

### Demarrer le stack complet
```bash
# 1. Socle (Keycloak + Postgres)
cd ~/Documents/GitHub/owuicore-main
docker compose up -d postgres keycloak

# 2. OpenRAG
cd ~/Documents/GitHub/openrag
SHARED_ENV=$(pwd)/.env docker compose -f docker-compose.yaml \
  -f integrations/docker-compose.integration.yaml \
  --profile cpu up -d etcd minio milvus rdb indexer-ui openrag-cpu

# 3. Contourner la dependance vllm
docker stop openrag-vllm-cpu-1 && docker start openrag-openrag-cpu-1

# 4. Re-injecter le token admin
HASH=$(python3 -c "import hashlib; print(hashlib.sha256('or-admin-openrag-2026'.encode()).hexdigest())")
docker exec openrag-rdb-1 psql -U root -d partitions_for_collection_vdb_test \
  -c "UPDATE users SET token='$HASH' WHERE id=1;"

# 5. Open WebUI
cd ~/Documents/GitHub/owuicore-main
docker compose up -d openwebui pipelines tika
```

### Arreter tout
```bash
cd ~/Documents/GitHub/openrag
SHARED_ENV=$(pwd)/.env docker compose -f docker-compose.yaml \
  -f integrations/docker-compose.integration.yaml \
  --profile cpu down

cd ~/Documents/GitHub/owuicore-main
docker compose down
```

---

## 7. Decisions d'architecture

| Decision | Justification |
|----------|---------------|
| Branche `dev` plutot que `main` | Seule branche avec le mode OIDC natif (auth code + PKCE + sessions) |
| Scaleway pour LLM/embeddings | Pas de GPU local, API OpenAI-compatible, memes cles que le socle |
| Client Keycloak unique `openwebui` | SSO unifie, un seul secret, memes redirect URIs |
| Provisioning via API REST | Zero modification du code OpenRAG, reproductible par script |
| Quota a 999999 vs -1 | Contournement du bug UI sur `file_quota = -1` |
| Approche A (modeles) pour OWUI | OpenRAG expose `/v1/models` nativement, zero code, integration immediate |

---

## 8. Prochaines etapes

- [ ] Tester l'upload de documents et le RAG via Open WebUI
- [ ] Ecrire le pipe filter pour l'approche B (`#` collections)
- [ ] Deploiement Scaleway (K8s ou Docker Compose sur VM)
- [ ] Remplacer MinIO par Scaleway Object Storage (pour prod)
- [ ] Automatiser le provisioning utilisateurs (cron sync_keycloak_openrag.py)
- [ ] Remonter les bugs a Linagora (quota -1, profil external-llm)


## ajout Eric

premier constat lors de la première utilisation (via l'ihm) lors de l'ajout d'un document s'il n'y a pas de collection est est diffile de comprendre ce qu'il faut faire
lorsque l'on va dans indexeur on n'a pas la liste des collections disponibles qui apparait. ( il manquerait un filtre ou sélection des collections ou ajout de collection )

l'ecran indexeur UI n'affiche que upload files:
qui affiche les options suivantes 

Upload files"

Create a partition
+ Add a new partition
Select one or multiple files

par defaut cela affiche :  You have reached your file quota limit et il n'est pas possible de créer une partition




