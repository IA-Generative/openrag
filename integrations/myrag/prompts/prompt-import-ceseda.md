# Prompt — Import direct du CESEDA par articles dans MyRAG

## Contexte du projet

Tu travailles sur **MyRAG (beta)**, un module independant qui s'intercale entre l'utilisateur et OpenRAG pour offrir un decoupage intelligent de documents, un graph de references et une integration dans Open WebUI.

### Architecture existante

```
[MyRAG (beta) — FastAPI port 8200]
     |
     ├── /api/ingest/{collection}    → decoupage + upload vers OpenRAG
     ├── /api/collections            → CRUD collections + system prompt
     ├── /graph                      → viewer Cytoscape.js + graph API
     ├── /articles/{collection}/{id} → vue article HTML (DSFR)
     ├── /api/sync                   → sync Keycloak ↔ OpenRAG
     ├── /api/feedback               → feedback OWUI
     └── frontend (Nuxt 4 + vue-dsfr, port 8201)
         └── Wizard creation en 4 etapes

[OpenRAG v1.1.8 — FastAPI port 8180]
     |
     ├── /v1/chat/completions  → RAG (OpenAI-compatible)
     ├── /v1/models            → liste partitions comme modeles
     ├── /search               → recherche semantique
     └── /indexer/partition/{p}/file/{id} → upload fichier

[Keycloak port 8082] — realm openwebui, client myrag-front (PKCE)
[Open WebUI port 3000] — chat avec modeles openrag-*
[Scaleway APIs] — LLM (mistral-small) + embeddings (bge-multilingual-gemma2)
```

### Stack technique

- **Backend MyRAG** : Python 3.12, FastAPI, NetworkX, httpx, Jinja2
- **Frontend** : Nuxt 4, @gouvfr/dsfr, @gouvminint/vue-dsfr, oidc-client-ts
- **Tests** : pytest, 135 tests unitaires, TDD (tests avant le code)
- **Docker** : Docker Compose + K8s Scaleway manifests
- **Repository** : `/Users/etiquet/Documents/GitHub/openrag/integrations/myrag/`

### Fichiers cles a connaitre

| Fichier | Description |
|---------|-------------|
| `app/services/chunker.py` | 4 strategies de decoupage (article, section, Q&R, longueur) + sensibilite |
| `app/services/graph_builder.py` | Construction graph NetworkX depuis les chunks |
| `app/services/openrag_client.py` | Client API OpenRAG (create partition, upload chunks, search) |
| `app/services/legifrance_client.py` | Client API PISTE Legifrance (search, get_article, parse URL) |
| `app/routers/ingest.py` | Endpoint POST /api/ingest/{collection} — ingest async avec job tracking |
| `app/routers/graph.py` | Graph API (build, data, related, viewer) |
| `app/routers/sources.py` | Gestion sources Legifrance (parse URL, search, add) |
| `app/models/collection.py` | CollectionConfig + PublicationConfig + 7 templates prompt |
| `app/services/job_tracker.py` | Suivi progression ingestion (IngestJob) |
| `build-graph.py` | Script CLI pour construire le graph depuis un fichier local |
| `tests/unit/test_chunker.py` | 30 tests du chunker (article, section, Q&R, longueur) |
| `tests/unit/test_graph_builder.py` | 16 tests du graph builder |
| `frontend/pages/admin/create/` | Wizard 4 etapes (identification, donnees, evaluation, publication) |

### Ce qui existe deja pour le CESEDA

1. **Chunker par article** (`chunker.py:chunk_by_article`) : decoupe par regex `^Article [LRD]\d+`, extrait la hierarchie (Livre/Titre/Chapitre), les references croisees, et prefixe chaque chunk avec `Article L421-1 — Livre IV, Titre II, Chapitre III`

2. **Metadata par chunk** :
```python
{
    "article": "L421-1",
    "page": 42,
    "livre": "IV",
    "titre": "II",
    "chapitre": "III",
    "parent_path": "Livre-IV/Titre-II/Chapitre-III",
    "references": ["L110-1", "L321-4"],
    "referenced_by": [],
    "graph_ready": False,
    "sensitivity": "public"
}
```

3. **Graph CESEDA** : 2399 noeuds, 9293 edges, viewer Cytoscape.js

4. **System prompt CESEDA** (template `ceseda` dans `collection.py`) : force les citations d'articles, filtre AGDREF, prefere les articles legislatifs (L) aux reglementaires (R, D)

5. **Legifrance client** : parse les URLs Legifrance (`LEGITEXT`, `LEGIARTI`, `JORFTEXT`), OAuth2 PISTE

### Problemes connus

- Le CESEDA en PDF ne peut pas etre indexe sur Mac ARM64 (bug pypdfium2)
- Le CESEDA en MD (extrait via Tika) fait 2.3 MB, 63K lignes, ~2399 articles
- L'ingest est async (job tracking) mais pas de feedback UI en temps reel
- Les articles tres longs (R931-5 = 344K chars) sont tronques dans le graph viewer (preview 500 chars, option resume IA)

## Objectif de la fonctionnalite

Ajouter un **import direct du CESEDA** (ou de tout code juridique Legifrance) qui :

1. **Telecharge le code depuis Legifrance** via l'API PISTE (par `LEGITEXT` ID ou URL)
2. **Decoupe automatiquement par article** avec la hierarchie complete
3. **Construit le graph de references** automatiquement
4. **Indexe dans OpenRAG** avec les metadata enrichies
5. **Tout en une seule action** depuis le wizard de creation (etape 2) ou depuis la page collection

### Points d'attention

- Le client Legifrance (`legifrance_client.py`) est deja implemente mais ne fait que des recherches. Il faut ajouter le telechargement complet d'un code (tous les articles d'un `LEGITEXT`)
- L'API PISTE retourne le texte de chaque article individuellement — il faut les rassembler et les decouper
- Le `LEGITEXT000006070158` = CESEDA complet (~1247 articles legislatifs + ~1152 articles reglementaires)
- Chaque article PISTE a un `LEGIARTI` ID unique, une date de version, et un statut (en vigueur ou abroge)
- Les references croisees sont dans le texte des articles (meme regex que le chunker actuel)

### Conventions de code

- TDD : ecrire les tests avant le code (`tests/unit/test_*.py`)
- Commits incrementaux avec messages descriptifs
- Les endpoints FastAPI suivent le pattern existant (`app/routers/*.py`)
- Les services metier sont dans `app/services/*.py`
- Le chunker ajoute `sensitivity` a chaque chunk (parametre d'ingestion)
- Le graph builder utilise le format `GraphDataResponse` compatible grafragexp
- Les templates HTML utilisent Jinja2 + DSFR

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
```
