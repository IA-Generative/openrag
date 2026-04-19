<template>
  <div>
    <div class="fr-mb-4w">
      <h1>Mes collections</h1>
      <p class="fr-text--lead">
        En tant que gestionnaire, administrez et maintenez en qualite vos collections
        de donnees documentaires. Suivez l'usage et mettez-les a disposition de tout
        le ministere, de votre communaute ou de votre service.
      </p>
    </div>

    <!-- Action tiles -->
    <h2 class="fr-h3">Que souhaitez-vous faire ?</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-6w">
      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin/create" class="fr-tile__link">
                  {{ collections.length === 0 ? 'Creer ma premiere collection' : 'Creer une collection' }}
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Assistant guide en 5 etapes : source, identification, donnees, evaluation, publication.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-add-circle-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>

      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin/catalog" class="fr-tile__link">
                  Explorer le catalogue
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Parcourez les collections existantes. Contactez les responsables pour y contribuer plutot que dupliquer.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-search-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>

      <div class="fr-col-12 fr-col-md-4">
        <div class="fr-tile fr-enlarge-link">
          <div class="fr-tile__body">
            <div class="fr-tile__content">
              <h3 class="fr-tile__title">
                <NuxtLink to="/admin" class="fr-tile__link">
                  Administration
                </NuxtLink>
              </h3>
              <p class="fr-tile__desc">
                Synchronisation Keycloak, jobs d'ingestion, templates de prompt, monitoring.
              </p>
            </div>
          </div>
          <div class="fr-tile__header">
            <div class="fr-tile__pictogram">
              <span class="fr-icon-settings-5-line fr-icon--lg" aria-hidden="true"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Collections list -->
    <section>
      <h2 class="fr-h3">Mes collections ({{ collections.length }})</h2>

      <div v-if="loading" class="fr-callout"><p>Chargement...</p></div>

      <div v-else-if="collections.length === 0" class="fr-notice fr-notice--info">
        <div class="fr-container">
          <div class="fr-notice__body">
            <p class="fr-notice__title">Vous n'avez pas encore de collection.</p>
            <p class="fr-notice__desc">
              Commencez par choisir une source de donnees (Legifrance, fichier, Drive, etc.)
              et suivez l'assistant de creation.
            </p>
          </div>
        </div>
      </div>

      <div v-else class="fr-grid-row fr-grid-row--gutters">
        <div v-for="col in collections" :key="col.name" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
          <div style="border:1px solid var(--border-default-grey);border-radius:8px;padding:1.25rem;display:flex;flex-direction:column;height:100%;min-height:280px;">
            <h3 class="fr-h6 fr-mb-1w" style="margin:0;line-height:1.3;min-height:2.6em;">
              {{ col.name }}
            </h3>
            <div style="display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.75rem;">
              <span class="fr-badge fr-badge--sm" :class="stateBadge(col.publication?.state)">
                {{ stateLabel(col.publication?.state) }}
              </span>
              <span class="fr-badge fr-badge--sm" :class="sensitivityBadge(col.sensitivity)">
                {{ col.sensitivity }}
              </span>
              <span class="fr-badge fr-badge--sm fr-badge--info">{{ col.strategy }}</span>
              <span v-if="col.graph_enabled" class="fr-badge fr-badge--sm fr-badge--new">graph</span>
            </div>

            <p class="fr-text--sm fr-mb-2w" style="color:var(--text-mention-grey);">
              {{ col.description || 'Pas de description' }}
            </p>

            <p v-if="col.contact_name" class="fr-text--xs fr-mb-2w" style="color:var(--text-mention-grey);">
              📧 {{ col.contact_name }}
              <a v-if="col.contact_email" :href="`mailto:${col.contact_email}`" class="fr-link fr-text--xs">
                {{ col.contact_email }}
              </a>
            </p>

            <div style="margin-top:auto;display:flex;flex-direction:column;gap:0.5rem;">
              <NuxtLink :to="`/c/${col.name}/playground`"
                        class="fr-btn fr-btn--icon-left fr-icon-chat-3-line"
                        style="width:100%;justify-content:center;">
                Tester le RAG
              </NuxtLink>
              <p class="fr-text--xs fr-mb-0" style="color:var(--text-mention-grey);text-align:center;">
                Playground avec debug et sources
              </p>

              <NuxtLink :to="`/c/${col.name}`"
                        class="fr-btn fr-btn--secondary fr-btn--sm fr-btn--icon-left fr-icon-eye-line"
                        style="width:100%;justify-content:center;">
                Voir la collection
              </NuxtLink>

              <div style="display:flex;justify-content:flex-end;margin-top:0.25rem;">
                <NuxtLink :to="`/c/${col.name}/config`"
                          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-btn--icon-left fr-icon-edit-line">
                  Configurer
                </NuxtLink>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
const { get } = useApi()
const collections = ref<any[]>([])
const loading = ref(true)

function stateBadge(state: string) {
  return { draft: 'fr-badge--grey', published: 'fr-badge--success', disabled: 'fr-badge--warning' }[state] || 'fr-badge--grey'
}
function stateLabel(state: string) {
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[state] || 'Brouillon'
}
function sensitivityBadge(s: string) {
  return { public: 'fr-badge--green-emeraude', internal: 'fr-badge--yellow-tournesol', restricted: 'fr-badge--orange-terre-battue', confidential: 'fr-badge--pink-macaron' }[s] || ''
}

onMounted(async () => {
  try {
    const data = await get('/api/collections')
    collections.value = data.collections || []
  } catch (e) {}
  loading.value = false
})
</script>
