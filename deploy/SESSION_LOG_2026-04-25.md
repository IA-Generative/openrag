# Session log — déploiement OpenRAG sur VM Mirai (`openrag-01-et`)

> Couvre la session 2026-04-25 → 2026-04-26 : install initial, intégration hub
> Mirai, multi-domaine, bascule canonical. Complément des docs de portée
> permanente (`PROPOSAL.md`, `keycloak/README.md`).

---

## 1. Cible atteinte

```
                                ┌─────────────────────────┐
                                │  Mirai LiteLLM           │  Authorization: Bearer sk-…
                                │  /v1/chat /v1/embeddings │  LLM, Embedder, Reranker
                                │  /v1/rerank              │
                                └────────────┬─────────────┘
                                             │ HTTPS
       Internet (TLS LE)                     │
       ┌──────────┐                          │
       │ Caddy 2  │──reverse_proxy──► OpenRAG API ──► PostgreSQL (local)
       │ 6 vhosts │                  (FastAPI/Ray)─► Milvus + etcd + minio (local)
       └────┬─────┘                          │  └► Marker (CPU PDF parsing)
            │                                │
            │                                ▼
            └──redir 301──► canonical    Scaleway Generative API
                                          /v1/chat (VLM image captioning)
                                          /v1/audio/transcriptions (Whisper)
```

- **Canonical** (proxy direct) : `*.openrag-mirai.numerique-interieur.com`
- **Non-canonical** (redirect 301 permanent) : `*.openrag-mirai.fake-domain.name`
- **Domaines exposés** :
  - `api.openrag-mirai.numerique-interieur.com` → API FastAPI + endpoints OIDC
  - `indexer.openrag-mirai.numerique-interieur.com` → Indexer Admin UI (Vite)
  - `chat.openrag-mirai.numerique-interieur.com` → 301 vers `/chainlit/` sur api.…

---

## 2. Timeline

| Date (UTC+2) | Étape | Commit / référence |
|---|---|---|
| 2026-04-25 | Inventaire VM, lecture `/root/hub-llm.txt`, tests modèles Mirai/Scaleway | (pas de commit) |
| 2026-04-25 | Sync `dev` + bump submodule `extern/indexer-ui` | `2590037d` |
| 2026-04-25 | `deploy/PROPOSAL.md` + `deploy/scripts/dns_setup.sh` | `42e08ab8` |
| 2026-04-25 | Sous-zone DNS `openrag-mirai.fake-domain.name` (4 records) | (Scaleway, pas de commit) |
| 2026-04-25 | Client Keycloak `openrag` (12 redirect URIs, mapper audience) | `a890a629`, `cd9dc7a0`, `b0f91146` |
| 2026-04-25 | `.env.example.vm` + `Caddyfile.example` initiaux | `7a389c62` |
| 2026-04-25 | `tests/deploy/run_all.sh` + tests pytest end-to-end | `b9545c4c`, `f28941f7` |
| 2026-04-25 | Sous-zones DNS `numerique-interieur.com` (4 records) | `68b63638` |
| 2026-04-25 | Multi-domaine actif : `fake-domain.name` canonical, `numerique-interieur.com` 301 | `06d3d2bf` |
| 2026-04-25 | Fix `chat.` → `/chainlit` (cookie OIDC consistency) | `e93e45a6` |
| 2026-04-25 | Capitalisation lessons : audio loader override, custom build vs pull | `5a9f5321` |
| 2026-04-25 | Fix `pypdfium2 PdfDocument context manager` (cherry-pick) | `1cab9c5e` |
| 2026-04-25 | Fix audio WAV inflation (Scaleway 100 MB cap) | `f3d700ce` |
| 2026-04-25 | OIDC auto-provisioning sur premier login (`OIDC_AUTO_PROVISION_LOGIN=true`) | `286294d1` |
| 2026-04-25 | Bump submodule indexer-ui (accept dynamique `/indexer/supported/types`) | `686d0406` |
| 2026-04-25 | Merge `dev → main` après validation end-to-end | PR [#2](https://github.com/IA-Generative/openrag/pull/2), `4ac743af` |
| 2026-04-26 | **Bascule canonical → `numerique-interieur.com`** | `acafb52d` ✱ |
| 2026-04-26 | Capture `docker-compose.override.yaml.example` + ce log | _ce commit_ |

✱ Bascule appliquée sur la VM en parallèle du commit (Caddy reload + restart container OpenRAG, ~30 s downtime API).

---

## 3. Décisions prises

| Décision | Rationale |
|---|---|
| Sous-zone DNS dédiée `openrag-mirai.…` | Isole de l'ancienne VM (`openrag.fake-domain.name`) |
| Wildcard `*` + records nommés | Ajout futur de vhosts (Grafana…) sans modif DNS, et liste explicite des 3 services en source de vérité |
| TTL DNS 60 s | Pivot d'IP rapide possible |
| Externalisation IA complète vers Mirai LiteLLM | Pas de GPU sur VM Scaleway dispo + key Mirai unifiée pour LLM/Embedder/Reranker |
| Scaleway Generative pour VLM + Whisper (initial) | Mirai LiteLLM n'expose pas de VLM ni `/v1/audio/transcriptions` ; Scaleway accessible avec une seule clé pour les 2 |
| Whisper Scaleway plutôt que Kevent Mirai | Le token Kevent fourni n'avait pas les droits audio à l'install (depuis débloqué — voir section 6) |
| `AUDIOLOADER=OpenAIAudioLoader` env | Le yaml par défaut force `LocalWhisperLoader` ; sans cet override, `TRANSCRIBER_BASE_URL` est ignoré |
| `USE_WHISPER_LANG_DETECTOR=false` | CPU-only : le pré-pass de détection de langue ajoute 5-10 s/fichier ; `whisper-large-v3` détecte la langue tout seul |
| Custom Docker image (`docker compose build`) plutôt que pull upstream | Bake `conf/config.yaml` dans l'image — sinon les modifs Hydra sont perdues car `conf/` n'est pas bind-mounté |
| `docker-compose.override.yaml` pour désactiver vllm/reranker | Conteneurs redondants avec hub Mirai externalisé ; profils `_disabled_` qui ne sont jamais activés |
| Multi-domaine via 301 (pas dual-proxy) | Cookie OIDC + `OIDC_REDIRECT_URI` sont liés à un domaine ; servir les 2 en proxy casserait la session après Keycloak |
| Bascule canonical → `numerique-interieur.com` | Domaine production officiel, `fake-domain.name` était un test |
| `OIDC_AUTO_PROVISION_LOGIN=true` | Mirai SSO = source de vérité, tout user qui se logue est créé non-admin avec son nom + email |
| Caddy `redir … permanent` plutôt que `tls { on_demand }` catch-all | Caddy 2.x rejette `on_demand` sans permission module ; `421 Misdirected Request` pour les Host headers non listés est acceptable |

---

## 4. Pièges rencontrés + résolutions (capitalisation)

| Symptôme | Cause | Fix |
|---|---|---|
| `Backchannel logout URL is not a valid URL` (Keycloak) | Client config initiale avait plusieurs URLs séparées par espaces | URL unique pointant sur le canonical (commit `ce74d11e`) |
| `on-demand TLS cannot be enabled without permission module` | Caddy 2.x | Remplacement des catch-all `*.…` par les vhosts explicites (commit `e93e45a6`) |
| `permission denied /var/log/caddy/api.log` au reload Caddy | Dossier non créé | `mkdir -p /var/log/caddy && chown caddy:caddy` (one-shot sur la VM) |
| `HTTP 405` sur `curl -I /auth/login` dans `smoke_test.sh` | `/auth/login` est GET-only, `curl -I` envoie HEAD | `curl -s -D - -o /dev/null` à la place |
| `User not registered` (403) sur premier login OIDC | Pas d'auto-provisioning par défaut côté upstream | PR [linagora/openrag#341](https://github.com/linagora/openrag/pull/341) + flag `OIDC_AUTO_PROVISION_LOGIN=true` |
| Sous-domaine `chat.` : `OIDC state cookie missing` | Cookie posé sur `chat.…`, callback sur `api.…` | `chat.…` redirige 301 vers `api.…/chainlit/` (commit `e93e45a6`) |
| MP3 refusé par le file picker du browser indexer | `accept=".pdf"` hardcodé dans Svelte | PR [linagora/openrag-admin-ui#26](https://github.com/linagora/openrag-admin-ui/pull/26) — accept dynamique depuis `/indexer/supported/types` |
| `Maximum file size exceeded (parameter=audio_filesize_mb, value=124.77)` sur Scaleway | `OpenAIAudioLoader` convertissait le mp3 en WAV non-compressé (×10 inflation) | DIRECT_UPLOAD_SUFFIXES whitelist (commit `f3d700ce`, PR [linagora/openrag#342](https://github.com/linagora/openrag/pull/342)) |
| Modifications `conf/config.yaml` ignorées après restart container | `conf/` n'est pas bind-mounté, l'image embarque sa propre copie | Rebuild de l'image (`docker compose build openrag-cpu`) — capitalisé dans `PROPOSAL.md` |
| `pypdfium2 PdfDocument context manager TypeError` | Bug pré-1.1.10 | Cherry-pick du fix existant (commit `1cab9c5e`) |
| `Sous-zone DNS créée dans le mauvais projet Scaleway` | `scw config` pointait sur un autre `default-project-id` | Suppression + recréation avec `project-id=…` explicite, et `dns_setup.sh` lit `default-project-id` (jamais hardcodé) |
| `gh pr` ne pousse pas la PR `dev → upstream` (#341) | Branch initialement basée sur `upstream/main` au lieu de `upstream/dev` | Cherry-pick sur une nouvelle branche depuis `upstream/dev` |
| Recreate container échoue : `dependency vllm-cpu failed to start` | `vllm-cpu` est en restart loop permanent (non utilisé) | `docker compose up -d --no-deps openrag-cpu` ou retry ; long-terme : `docker-compose.override.yaml` désactive ces services |

---

## 5. Tests effectués

### 5.1. Smoke tests `tests/deploy/run_all.sh`
| Test | Statut |
|---|---|
| `GET /health_check` (canonical) | ✅ HTTP 200 |
| `GET /version` | ✅ |
| `/auth/login` → 302 vers SSO Mirai | ✅ |
| `/indexer/` → 200 ou 302 | ✅ |
| `/chainlit/` → 200 | ✅ |
| Test redirect non-canonical → canonical (les 3 vhosts) | ✅ |

### 5.2. Pipeline complet — MP3 réunion 30 min (`task_id=64ac…02501000000`)
| Étape | Résultat |
|---|---|
| Upload via UI Indexer | ✅ |
| Sérialisation (`DocSerializer`) | ✅ |
| Transcription Scaleway `whisper-large-v3` | ✅ ~1 min pour 30 min audio |
| Chunking (`split_document`) | ✅ 42 chunks |
| Contextualisation LLM (Mirai `mistral-small-24b`) | ✅ 4 batches |
| Indexation Milvus | ✅ |
| Recherche RAG via Chainlit | ✅ MP3 retourné comme source citée |

### 5.3. Évaluation VLM comparative (5 modèles × 7 images = 35 appels)
Cf. `data-eval-vlm/vlm-eval-synthese.md` (hors repo, dossier perso). Verdict :
- Top 3 qualité : Claude (référence) > `mirai/mistral-medium-albert` > `mirai/chat-small (Gemma 4)`
- Latence : Scaleway 1.4-1.6 s vs MirAI 2.5-3.4 s en moyenne (~2× plus rapide côté Scaleway)
- `scaleway/pixtral-12b` à éviter (hallucinations factuelles)

### 5.4. Couverture modèles Mirai (admin a débloqué les droits le 2026-04-26)

| Service | LiteLLM Mirai | Gateway Kevent Mirai | Scaleway |
|---|---|---|---|
| LLM `mistral-small-24b` | ✅ | — | — |
| Embedder `bge-multilingual-gemma2` | ✅ | — | — |
| Reranker `/v1/rerank` | ✅ | — | — |
| VLM (multimodal) | ✅ `mistral-small-24b`, `mistral-medium-albert`, `chat-small` (Gemma 4) — testés | ❌ | ✅ (utilisé actuellement) |
| Whisper `faster-whisper-large-v3-turbo` | ❌ | ✅ (header `apikey: Bearer …`) | ✅ (utilisé actuellement) |
| Diarization `pyannote-diarization` | — | ✅ | — |

**Bascule complète vers Mirai possible** mais nécessite :
- Patch `OpenAIAudioLoader` pour utiliser `apikey:` au lieu de `Authorization: Bearer` (le client `AsyncOpenAI` n'envoie que ce dernier nativement)
- Ou conservation de Scaleway en l'état (statu quo, tests réussis)

---

## 6. PRs filées upstream

| PR | Repo | Sujet | Statut |
|---|---|---|---|
| [#341](https://github.com/linagora/openrag/pull/341) | linagora/openrag | feat(auth): OIDC auto-provisioning sur premier login | OPEN |
| [#342](https://github.com/linagora/openrag/pull/342) | linagora/openrag | fix(audio): skip WAV conversion (Scaleway 100 MB cap) | OPEN |
| [#26](https://github.com/linagora/openrag-admin-ui/pull/26) | linagora/openrag-admin-ui | feat(upload): accept dynamique depuis `/indexer/supported/types` | OPEN |
| [#313](https://github.com/linagora/openrag/pull/313) | linagora/openrag | fix(auth): detect HTTPS behind TLS proxy | OPEN |
| [#312](https://github.com/linagora/openrag/pull/312) | linagora/openrag | fix: pypdfium2 PdfDocument context manager | CLOSED (déjà mergé en interne) |

---

## 7. État final déployé

### 7.1. Repo `IA-Generative/openrag`
- `dev` : tip à jour avec la session
- `main` : promu après validation (PR [#2](https://github.com/IA-Generative/openrag/pull/2))
- Submodule `extern/indexer-ui` : `bbe57531` (incluant le fix accept dynamique)

### 7.2. VM `openrag-01-et` (51.159.184.192)
- Repo cloné dans `/opt/openrag/` sur branche `dev`
- Image Docker custom : `openrag-openrag-cpu:latest` (build local — embarque `conf/`)
- Services up : `openrag-openrag-cpu-1`, `openrag-indexer-ui-1`, `milvus`, `etcd`, `minio`, `rdb`
- Services désactivés via override : `vllm-cpu`, `vllm-gpu`, `reranker*`
- Caddy : 6 vhosts (`/etc/caddy/Caddyfile`, identique à `deploy/Caddyfile.example`)
- Backups conservés : `/etc/caddy/Caddyfile.bak.*`, `/opt/openrag/.env.bak.*`

### 7.3. DNS Scaleway
- Sous-zone `openrag-mirai.fake-domain.name` : 4 records (`*`, `api`, `indexer`, `chat`)
- Sous-zone `openrag-mirai.numerique-interieur.com` : 4 records identiques
- TTL 60 s, IP `51.159.184.192`

### 7.4. Keycloak Mirai (realm `mirai`)
- Client `openrag` : confidential, auth code + PKCE
- 12 redirect URIs (3 prefixes × 2 sous-zones × 2 domaines)
- Mapper audience `openrag` (token Open WebUI → OpenRAG accepté)
- Backchannel logout URL unique sur le canonical

### 7.5. Variables d'environnement clés (sur la VM, valeurs réelles dans `.env`)
```bash
BASE_URL=https://llm.api.ai.numerique-interieur.com/v1   # Mirai LiteLLM
API_KEY=sk-AD3by…                                         # token Mirai
MODEL=mistral-small-24b
EMBEDDER_BASE_URL=https://llm.api.ai.numerique-interieur.com/v1
EMBEDDER_API_KEY=sk-AD3by…
EMBEDDER_MODEL_NAME=bge-multilingual-gemma2
RERANKER_BASE_URL=https://llm.api.ai.numerique-interieur.com/v1
VLM_BASE_URL=https://api.scaleway.ai/<project>/v1         # Scaleway
TRANSCRIBER_BASE_URL=https://api.scaleway.ai/<project>/v1
TRANSCRIBER_MODEL=whisper-large-v3
AUDIOLOADER=OpenAIAudioLoader                             # override yaml
USE_WHISPER_LANG_DETECTOR=false
AUTH_MODE=oidc
OIDC_ENDPOINT=https://sso.mirai.interieur.gouv.fr/realms/mirai
OIDC_REDIRECT_URI=https://api.openrag-mirai.numerique-interieur.com/auth/callback
OIDC_AUTO_PROVISION_LOGIN=true
API_BASE_URL=https://api.openrag-mirai.numerique-interieur.com
INDEXERUI_URL=https://indexer.openrag-mirai.numerique-interieur.com
SUPER_ADMIN_MODE=false
DEFAULT_FILE_QUOTA=100
```

---

## 8. Runbook opérationnel

### 8.1. Mettre à jour OpenRAG sur la VM

```bash
ssh root@51.159.184.192
cd /opt/openrag
git pull origin dev
docker compose build openrag-cpu
docker compose up -d --no-deps openrag-cpu        # --no-deps évite l'attente de vllm-cpu
docker logs -f openrag-openrag-cpu-1               # vérifier au démarrage
```

### 8.2. Modifier la config Caddy

```bash
# Éditer /etc/caddy/Caddyfile sur la VM, puis :
caddy validate --config /etc/caddy/Caddyfile        # syntaxe
systemctl reload caddy                              # zéro downtime
systemctl status caddy
```

### 8.3. Modifier `.env`

```bash
# Backup avant édition (le restart d'OpenRAG est nécessaire pour appliquer)
cp /opt/openrag/.env /opt/openrag/.env.bak.$(date +%Y%m%d-%H%M%S)
vim /opt/openrag/.env
docker compose up -d --no-deps openrag-cpu          # recreate pour relire env
```

### 8.4. Bascule canonical (vers `fake-domain.name` ou retour)

1. Inverser les 6 vhosts dans `/etc/caddy/Caddyfile` (3 `reverse_proxy` ↔ 3 `redir … permanent`)
2. Mettre à jour 3 env vars dans `.env` : `API_BASE_URL`, `INDEXERUI_URL`, `OIDC_REDIRECT_URI`
3. `systemctl reload caddy && docker compose up -d --no-deps openrag-cpu`
4. Aucune modif Keycloak nécessaire (12 redirect URIs déjà whitelistées)

### 8.5. Diagnostic rapide

```bash
# Health check
curl -fsSL https://api.openrag-mirai.numerique-interieur.com/health_check

# Logs filtré sur les indexations en cours
ssh root@51.159.184.192 \
  "docker logs -f openrag-openrag-cpu-1 2>&1 | grep -E 'task_id|state=|chunks|Transcribing|FAILED'"

# Caddy logs
ssh root@51.159.184.192 "tail -f /var/log/caddy/api.log /var/log/caddy/indexer.log"

# DNS sanity
dig +short api.openrag-mirai.numerique-interieur.com @1.1.1.1   # → 51.159.184.192
scw dns record list dns-zone=openrag-mirai.numerique-interieur.com
```

### 8.6. Rollback du déploiement

```bash
# 1. Caddy
cp /etc/caddy/Caddyfile.bak.<timestamp> /etc/caddy/Caddyfile
systemctl reload caddy

# 2. .env
cp /opt/openrag/.env.bak.<timestamp> /opt/openrag/.env
docker compose up -d --no-deps openrag-cpu

# 3. App
cd /opt/openrag && git checkout <previous-commit>
docker compose build openrag-cpu
docker compose up -d --no-deps openrag-cpu

# 4. DNS (si rollback total)
scw dns record delete dns-zone=openrag-mirai.numerique-interieur.com <record-id>

# 5. Keycloak (jamais en runbook automatique — passer par l'admin SSO)
```

---

## 9. Pour l'agent suivant

Si tu reprends la VM, lis dans cet ordre :
1. `deploy/PROPOSAL.md` — décisions architecturales et leur justification
2. `deploy/keycloak/README.md` — flux OIDC, mapper audience, multi-domaine
3. `deploy/.env.example.vm` — toutes les variables avec placeholders + commentaires
4. `deploy/Caddyfile.example` — vhosts et logique de redirect
5. `deploy/docker-compose.override.yaml.example` — services désactivés
6. `tests/deploy/` — smoke tests + tests OIDC + tests indexing
7. **Ce fichier** (`SESSION_LOG_2026-04-25.md`) — historique chronologique + pièges

Pour l'indexation de documents par programme : voir le briefing dédié dans la
mémoire de l'agent (sinon générer via "comment indexer des documents sur la
VM ?").
