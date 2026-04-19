<template>
  <div>
    <h1 class="fr-h2">Mes collections</h1>

    <div v-if="loading" class="fr-callout">
      <p>Chargement des collections...</p>
    </div>

    <div v-else-if="error" class="fr-alert fr-alert--error fr-mb-4w">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="collections.length === 0" class="fr-callout">
      <h3 class="fr-callout__title">Aucune collection</h3>
      <p class="fr-callout__text">Creez une collection pour commencer a indexer des documents.</p>
      <NuxtLink to="/admin/create" class="fr-btn">Creer une collection</NuxtLink>
    </div>

    <div v-else class="myrag-card-grid">
      <div v-for="col in collections" :key="col.name" class="fr-card fr-enlarge-link">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">
              <NuxtLink :to="`/c/${col.name}`">{{ col.name }}</NuxtLink>
            </h3>
            <p class="fr-card__desc">{{ col.description || 'Pas de description' }}</p>
            <div class="fr-card__start">
              <p class="fr-card__detail">
                <span class="fr-badge fr-badge--sm fr-badge--info">{{ col.strategy }}</span>
                <span class="fr-badge fr-badge--sm" :class="sensitivityBadge(col.sensitivity)">
                  {{ col.sensitivity }}
                </span>
                <span v-if="col.graph_enabled" class="fr-badge fr-badge--sm fr-badge--new">graph</span>
                <span v-if="col.publication?.state === 'published'" class="fr-badge fr-badge--sm fr-badge--success">publie</span>
                <span v-else class="fr-badge fr-badge--sm">brouillon</span>
              </p>
            </div>
            <div v-if="col.contact_name" class="fr-card__end">
              <p class="fr-card__detail fr-text--sm">
                📧 {{ col.contact_name }}
                <a v-if="col.contact_email" :href="`mailto:${col.contact_email}`" class="fr-link fr-text--sm">
                  {{ col.contact_email }}
                </a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { get } = useApi()

const collections = ref<any[]>([])
const loading = ref(true)
const error = ref('')

function sensitivityBadge(s: string) {
  const map: Record<string, string> = {
    public: 'fr-badge--success',
    internal: 'fr-badge--info',
    restricted: 'fr-badge--warning',
    confidential: 'fr-badge--error',
  }
  return map[s] || ''
}

onMounted(async () => {
  try {
    const data = await get('/api/collections')
    collections.value = data.collections || []
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
