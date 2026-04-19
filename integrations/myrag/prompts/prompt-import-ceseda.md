# Prompt — Import direct de sources documentaires dans MyRAG

## Contexte du projet

Tu travailles sur **MyRAG (beta)**, un module independant qui s'intercale entre l'utilisateur et OpenRAG pour offrir un decoupage intelligent de documents, un graph de references et une integration dans Open WebUI.

### Architecture existante

```
[MyRAG (beta) — FastAPI port 8200]
     |
     ├── /api/ingest/{collection}        → decoupage + upload vers OpenRAG (async, job tracking)
     ├── /api/collections                → CRUD collections + system prompt + 7 templates
     ├── /api/collections/{n}/publish    → publication dans OWUI (alias, tool, #collection)
     ├── /api/collections/{n}/publication → cycle de vie (draft→published→disabled→archived)
     ├── /api/feedback                   → feedback OWUI (ingest, review, promote)
     ├── /api/sync                       → sync Keycloak ↔ OpenRAG
     ├── /api/sources/legifrance         → gestion sources Legifrance (parse URL, search, add)
     ├── /graph                          → viewer Cytoscape.js + graph API (GraphDataResponse)
     ├── /graph/{collection}/build       → construire le graph depuis les chunks
     ├── /graph/{collection}/summarize   → resume IA des articles longs
     ├── /articles/{collection}/{id}     → vue article HTML (DSFR, iframe-friendly)
     └── frontend (Nuxt 4 + vue-dsfr, port 8201)
         ├── Dashboard collections avec qualite + contacts
         ├── Wizard creation 5 etapes (source → identification → donnees → eval → publication)
         ├── Playground RAG avec debug panel
         ├── Editeur system prompt avec templates + test
         ├── Page publication (modes, visibilite, widget snippet)
         └── Auth Keycloak PKCE (oidc-client-ts)

[OpenRAG v1.1.8 — FastAPI port 8180]
     |
     ├── /v1/chat/completions  → RAG (OpenAI-compatible)
     ├── /v1/models            → liste partitions comme modeles (openrag-{collection})
     ├── /search               → recherche semantique (top_k, similarity_threshold)
     └── /indexer/partition/{p}/file/{id} → upload fichier (form-data)

[Keycloak port 8082] — realm openwebui, clients: openwebui (confidential), myrag-front (public PKCE)
[Open WebUI port 3000] — chat avec modeles openrag-*, tool MyRAG, pipe #collection
[Scaleway APIs] — LLM (mistral-small) + embeddings (bge-multilingual-gemma2)
```

### Stack technique

- **Backend MyRAG** : Python 3.12, FastAPI, NetworkX, httpx, Jinja2, pydantic-settings
- **Frontend** : Nuxt 4, @gouvfr/dsfr, @gouvminint/vue-dsfr, oidc-client-ts
- **Tests** : pytest, 135 tests unitaires, TDD (tests avant le code)
- **Docker** : Docker Compose + K8s Scaleway manifests (7 fichiers YAML)
- **OWUI integration** : tool (4 methodes), pipe filter #collection, feedback outlet
- **Repository** : `/Users/etiquet/Documents/GitHub/openrag/integrations/myrag/`

### Fichiers cles

| Fichier | Description |
|---------|-------------|
| `app/services/chunker.py` | 4 strategies de decoupage (article, section, Q&R, longueur) + sensibilite |
| `app/services/graph_builder.py` | Construction graph NetworkX, format GraphDataResponse, subgraph, resume IA |
| `app/services/openrag_client.py` | Client API OpenRAG (create partition, upload chunks, search, upload_form) |
| `app/services/legifrance_client.py` | Client API PISTE (search, get_article, get_code_toc, parse URL) |
| `app/services/keycloak_client.py` | Client Admin Keycloak (groupes, membres, create_collection_groups) |
| `app/services/sync_service.py` | Sync groupes KC → memberships OpenRAG |
| `app/services/qr_cache.py` | Cache Q&R avec fuzzy matching + import/export JSON |
| `app/services/eval_service.py` | Evaluation RAG (dataset Q&R, scoring similarite + citations) |
| `app/services/feedback_service.py` | Feedback OWUI (ingest, review, promote → Q&R ou eval) |
| `app/services/job_tracker.py` | Suivi progression ingestion (IngestJob, uploaded/total, pct) |
| `app/models/collection.py` | CollectionConfig + PublicationConfig + SourceConfig + 7 templates prompt |
| `app/routers/ingest.py` | POST /api/ingest/{collection} — ingest async avec job_id |
| `app/routers/collections.py` | CRUD collections + templates (GET/POST/PUT/DELETE) |
| `app/routers/publication.py` | Publish/unpublish/archive + history |
| `app/routers/graph.py` | Graph API (data, related, build, summarize, viewer HTML) |
| `app/routers/articles.py` | Vue article HTML DSFR (Jinja2) |
| `app/routers/sources.py` | Gestion sources Legifrance |
| `app/routers/feedback.py` | Ingest/list/review/promote feedback |
| `app/routers/sync.py` | Sync Keycloak → OpenRAG |
| `owui/tool_myrag.py` | Tool OWUI 4 methodes (search, view, graph, browse) |
| `owui/pipe_myrag_filter.py` | Pipe filter #collection |
| `owui/feedback_outlet.py` | Outlet OWUI capture feedback |
| `build-graph.py` | Script CLI pour construire le graph |
| `frontend/pages/admin/create/` | Wizard 5 etapes |
| `frontend/components/WizardStepper.vue` | Composant stepper visuel |
| `tests/unit/` | 135 tests (chunker, graph, openrag, keycloak, sync, qr, eval, feedback, publication) |

### Wizard de creation — 5 etapes (source-first)

Le wizard commence par le choix de la **source des donnees** :

```
① Source  →  ② Identification  →  ③ Donnees  →  ④ Evaluation  →  ⑤ Publication
```

**Sources supportees :**

| Source | Connecteur | Refresh auto | Strategie suggeree |
|--------|-----------|:------------:|-------------------|
| Legifrance | API PISTE OAuth2 | ✅ quotidien | `article` |
| Fichier unique | Upload local | ❌ | `auto` |
| Repertoire local | Upload multiple / ZIP | ❌ | `auto` |
| Suite Numerique Drive | API REST `/api/v1.0/items/` | ✅ | `auto` |
| Nextcloud | API OCS `/ocs/v2.php/apps/files/` | ✅ | `auto` |
| Resana | API Resana | ✅ | `auto` |

**Architecture connecteurs (a implementer dans `app/services/connectors/`) :**

```python
class BaseConnector:
    async def list_documents(self) -> list[DocumentInfo]: ...
    async def fetch_document(self, doc_id: str) -> bytes: ...
    async def check_updates(self, since: str) -> list[DocumentInfo]: ...
```

### Ce qui existe deja pour le CESEDA

1. **Chunker par article** (`chunker.py:chunk_by_article`) : regex `^Article [LRD]\d+`, hierarchie Livre/Titre/Chapitre, references croisees, prefixe "Article L421-1 — Livre IV, Titre II"

2. **Metadata par chunk** :
```python
{
    "article": "L421-1",
    "page": 42,
    "livre": "IV", "titre": "II", "chapitre": "III",
    "parent_path": "Livre-IV/Titre-II/Chapitre-III",
    "references": ["L110-1", "L321-4"],
    "referenced_by": [],
    "graph_ready": False,
    "sensitivity": "public"
}
```

3. **Graph CESEDA construit** : 2399 noeuds, 9293 edges, viewer Cytoscape.js fonctionnel

4. **System prompt CESEDA** (template `ceseda`) : citations d'articles, filtre AGDREF, preference L > R/D

5. **Legifrance client** : parse URLs (`LEGITEXT`, `LEGIARTI`, `JORFTEXT`), OAuth2 PISTE, search, get_article, get_code_toc

6. **Test reel** : CESEDA indexe (2399 articles), RAG fonctionnel dans Open WebUI avec citations

### Problemes connus

- PDF sur Mac ARM64 : bug pypdfium2 (contournement : conversion MD via Tika)
- Articles tres longs (R931-5 = 344K chars) : preview 500 chars + option resume IA
- `RERANKER_ENABLED=false` (a activer avec HuggingFace ou Scaleway)
- Ingest async mais pas de WebSocket (polling `/api/ingest/jobs/{id}`)
- Le token admin OpenRAG est ecrase au restart (fix : `AUTH_TOKEN` dans .env)

## Objectif de la fonctionnalite

Implementer le **connecteur Legifrance** complet pour l'etape 1 du wizard (source) + l'etape 3 (donnees) :

1. **Etape 1 (Source)** : l'utilisateur choisit "Legifrance" parmi les sources
2. **Etape 3 (Donnees)** : interface specifique Legifrance :
   - Recherche par nom de code ("CESEDA", "Code civil", etc.) via API PISTE
   - Ou coller une URL Legifrance → auto-detection du type et ID
   - Preview de la table des matieres du code
   - Choix du scope : partie legislative, reglementaire, ou tout
   - Bouton "Importer" → telecharge tous les articles, decoupe par article, indexe dans OpenRAG, construit le graph
   - Progression en temps reel
3. **Refresh automatique** : cron configurable (quotidien/hebdomadaire) qui detecte les articles modifies via l'API PISTE et re-indexe uniquement le delta

### Points d'attention

- L'API PISTE retourne les articles **un par un** — il faut iterer sur la table des matieres
- Chaque article PISTE a : `LEGIARTI` ID, texte, date version, statut (en vigueur/abroge)
- Le `LEGITEXT000006070158` = CESEDA (~2399 articles total)
- Les references croisees sont dans le texte (meme regex que le chunker)
- L'import complet d'un code peut prendre plusieurs minutes — utiliser le job tracking existant
- Pour le refresh delta : comparer `dateVersion` de chaque article avec la derniere sync

### Conventions de code

- **TDD** : ecrire les tests avant le code (`tests/unit/test_*.py`)
- **Commits incrementaux** avec messages descriptifs `feat(myrag): ...`
- Les endpoints suivent le pattern existant (`app/routers/*.py`)
- Les services metier dans `app/services/*.py`, connecteurs dans `app/services/connectors/`
- Le chunker ajoute `sensitivity` + metadata Legifrance (`legifrance_id`, `legifrance_url`, `version_date`)
- Le graph builder utilise le format `GraphDataResponse` compatible grafragexp
- Les templates HTML utilisent Jinja2 + DSFR
- Le frontend utilise le composable `useApi()` pour les appels API

### Commandes utiles

```bash
# Tests
cd integrations/myrag && python3 -m pytest tests/unit/ -v

# Lancer MyRAG
docker build -t myrag:beta . && docker run -p 8200:8200 myrag:beta

# Frontend
cd frontend && npx nuxt dev --port 8201

# Build graph
python3 build-graph.py CESEDA.md ceseda-v3 --strategy article

# API Swagger
http://localhost:8200/docs

# Viewer graph
http://localhost:8200/graph?corpus_id=ceseda-v3
```

### Livrables attendus

1. `app/services/connectors/base.py` — interface BaseConnector
2. `app/services/connectors/legifrance.py` — LegifranceConnector (fetch code complet, delta refresh)
3. `app/routers/connectors.py` — endpoints pour piloter les connecteurs
4. `tests/unit/test_legifrance_connector.py` — tests TDD
5. `frontend/pages/admin/create/index.vue` — mise a jour step 1 (choix source)
6. `frontend/pages/admin/create/step-3.vue` — interface Legifrance (recherche, preview, import)
7. Mise a jour de `SourceConfig` dans `app/models/collection.py`
