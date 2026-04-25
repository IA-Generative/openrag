#!/usr/bin/env bash
# Provisionne une sous-zone DNS Scaleway dédiée à un déploiement OpenRAG :
#   - un wildcard *  → A → IP de la VM           (catch-all, routage par reverse proxy)
#   - des records nommés par service             (auto-documentation via commentaire Scaleway)
#
# Le reverse proxy sur la VM (Caddy/Nginx/Traefik) route par Host header vers
# les services internes. Les records nommés ne servent qu'à laisser une trace
# lisible dans `scw dns record list` — on saura quels services tournent ici
# sans avoir à se rappeler par cœur.
#
# Usage :
#   DRY_RUN=1 ./dns_setup.sh                                # simulation (défaut)
#   DRY_RUN=0 ./dns_setup.sh                                # création réelle
#   ZONE=… TARGET_IP=… DRY_RUN=0 ./dns_setup.sh
#
# Variables :
#   ZONE         sous-zone à provisionner          (défaut: openrag-mirai.fake-domain.name)
#   TARGET_IP    IP cible des records              (défaut: 51.159.184.192)
#   TTL          TTL des records                   (défaut: 60)
#   CREATE_ZONE  1 = crée la sous-zone si absente  (défaut: 1)
#   DRY_RUN      1 = simulation                    (défaut: 1)
#
# Pour ajuster la liste des services nommés, éditer le tableau SERVICES ci-dessous.
#
# Pré-requis : scw, jq, dig

set -euo pipefail

ZONE="${ZONE:-openrag-mirai.fake-domain.name}"
TARGET_IP="${TARGET_IP:-51.159.184.192}"
TTL="${TTL:-60}"
DRY_RUN="${DRY_RUN:-1}"
CREATE_ZONE="${CREATE_ZONE:-1}"
# Project Scaleway dans lequel créer la sous-zone si absente.
# Vide = utilise default-project-id de scw config (DANGER : peut tomber dans
# un autre projet selon les profils ; mettre explicitement pour reproductibilité).
PROJECT_ID="${PROJECT_ID:-223ee57e-66ff-4f84-9b47-fc3c86a21ad2}"

# Services à exposer en records nommés (auto-doc via Scaleway comment).
# Format : "name|comment"
SERVICES=(
  "api|OpenRAG API (FastAPI/Ray)"
  "indexer|Indexer admin UI"
  "chat|Chainlit chat"
)

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*"; }
err()  { printf '\033[1;31mXX \033[0m %s\n' "$*" >&2; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '\033[2m[DRY-RUN]\033[0m %s\n' "$*"
  else
    printf '\033[1;32m[EXEC]\033[0m   %s\n' "$*"
    "$@"
  fi
}

for bin in scw jq dig; do
  command -v "$bin" >/dev/null || { err "binaire manquant : $bin"; exit 1; }
done

log "Sous-zone   : $ZONE"
log "IP cible    : $TARGET_IP"
log "TTL         : ${TTL}s"
log "Records     : * (wildcard) + ${#SERVICES[@]} services nommés"
[[ "$DRY_RUN" == "1" ]] && warn "DRY_RUN=1 — aucune écriture. Relancer avec DRY_RUN=0 pour appliquer."

# 1. Vérifier / créer la sous-zone
log "Vérification de la sous-zone…"
zone_domain="${ZONE#*.}"
zone_sub="${ZONE%.${zone_domain}}"
[[ "$zone_sub" == "$ZONE" ]] && zone_sub=""

zone_just_created=0
if scw dns zone list domain="$zone_domain" -o json \
     | jq -e --arg d "$zone_domain" --arg s "$zone_sub" \
         '.[] | select(.domain==$d and .subdomain==$s)' >/dev/null; then
  log "  zone $ZONE trouvée"
else
  if [[ "$CREATE_ZONE" == "1" && -n "$zone_sub" ]]; then
    warn "  zone $ZONE absente — création (subdomain=$zone_sub dans $zone_domain, project=${PROJECT_ID:-default})"
    if [[ -n "$PROJECT_ID" ]]; then
      run scw dns zone create domain="$zone_domain" subdomain="$zone_sub" project-id="$PROJECT_ID"
    else
      run scw dns zone create domain="$zone_domain" subdomain="$zone_sub"
    fi
    zone_just_created=1
    if [[ "$DRY_RUN" == "0" ]]; then
      sleep 2
      scw dns zone list domain="$zone_domain" -o json \
        | jq -e --arg d "$zone_domain" --arg s "$zone_sub" \
            '.[] | select(.domain==$d and .subdomain==$s)' >/dev/null \
        || { err "création de la sous-zone échouée"; exit 2; }
      log "  sous-zone créée"
    fi
  else
    err "zone $ZONE introuvable (CREATE_ZONE=0 ou zone racine demandée)"
    exit 2
  fi
fi

# Helper : ajoute un record A si absent, ou met à jour si l'IP diffère.
upsert_a_record() {
  local name="$1" comment="$2"
  local existing_ip=""

  if [[ "$zone_just_created" == "0" || "$DRY_RUN" == "0" ]]; then
    existing_ip=$(scw dns record list dns-zone="$ZONE" -o json \
      | jq -r --arg n "$name" '.[] | select(.name==$n and .type=="A") | .data' | head -1)
  fi

  if [[ -z "$existing_ip" ]]; then
    log "  + $name  →  $TARGET_IP   (${comment:-no comment})"
    if [[ -n "$comment" ]]; then
      run scw dns record add "$ZONE" name="$name" type=A data="$TARGET_IP" ttl="$TTL" comment="$comment"
    else
      run scw dns record add "$ZONE" name="$name" type=A data="$TARGET_IP" ttl="$TTL"
    fi
  elif [[ "$existing_ip" == "$TARGET_IP" ]]; then
    log "  = $name  →  $TARGET_IP   (déjà à jour)"
  else
    warn "  ~ $name  →  $existing_ip → $TARGET_IP   (bascule)"
    run scw dns record delete dns-zone="$ZONE" name="$name" type=A data="$existing_ip" ttl="$TTL"
    if [[ -n "$comment" ]]; then
      run scw dns record add "$ZONE" name="$name" type=A data="$TARGET_IP" ttl="$TTL" comment="$comment"
    else
      run scw dns record add "$ZONE" name="$name" type=A data="$TARGET_IP" ttl="$TTL"
    fi
  fi
}

# 2. Wildcard catch-all
log "Wildcard *…"
upsert_a_record "*" ""

# 3. Records nommés (auto-doc)
log "Services nommés…"
for entry in "${SERVICES[@]}"; do
  IFS='|' read -r svc_name svc_comment <<< "$entry"
  upsert_a_record "$svc_name" "$svc_comment"
done

# 4. Vérification finale
if [[ "$DRY_RUN" == "0" ]]; then
  log "État final de la sous-zone :"
  scw dns record list dns-zone="$ZONE"

  log "Résolution publique (peut prendre jusqu'à $TTL s)…"
  for entry in "${SERVICES[@]}"; do
    IFS='|' read -r svc_name _ <<< "$entry"
    fqdn="${svc_name}.${ZONE}"
    answer=$(dig +short "$fqdn" @1.1.1.1 || true)
    if [[ -n "$answer" ]]; then
      log "  $fqdn → $answer"
    else
      warn "  $fqdn → non résolu (propagation en cours)"
    fi
  done
fi

log "Terminé."
