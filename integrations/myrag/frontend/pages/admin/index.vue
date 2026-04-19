<template>
  <div>
    <h1 class="fr-h2">Administration MyRAG (beta)</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-4">
        <div class="fr-card fr-enlarge-link">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-card__title"><NuxtLink to="/admin/create">Creer une collection</NuxtLink></h3>
              <p class="fr-card__desc">Nouvelle collection avec partition OpenRAG et groupes Keycloak</p>
            </div>
          </div>
        </div>
      </div>

      <div class="fr-col-4">
        <div class="fr-card">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-card__title">Synchronisation</h3>
              <p class="fr-card__desc">Sync Keycloak → OpenRAG</p>
              <button class="fr-btn fr-btn--sm fr-mt-2w" @click="syncAll" :disabled="syncing">
                {{ syncing ? 'Sync...' : 'Synchroniser' }}
              </button>
              <div v-if="syncResult" class="fr-alert fr-alert--success fr-mt-1w">
                <p class="fr-text--sm">{{ syncResult.total_members_synced }} membres syncs</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="fr-col-4">
        <div class="fr-card">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-card__title">Templates</h3>
              <p class="fr-card__desc">{{ templateCount }} modeles de prompt disponibles</p>
              <NuxtLink to="/admin/templates" class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-2w">
                Gerer
              </NuxtLink>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Collections list -->
    <h2 class="fr-h4 fr-mt-6w">Toutes les collections</h2>

    <div v-if="collections.length === 0" class="fr-callout">
      <p>Aucune collection configuree dans MyRAG.</p>
    </div>

    <div v-else class="fr-table">
      <table>
        <thead>
          <tr>
            <th>Collection</th>
            <th>Strategie</th>
            <th>Sensibilite</th>
            <th>Graph</th>
            <th>Resume IA</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="col in collections" :key="col.name">
            <td><NuxtLink :to="`/c/${col.name}`">{{ col.name }}</NuxtLink></td>
            <td>{{ col.strategy }}</td>
            <td><span class="fr-badge fr-badge--sm">{{ col.sensitivity }}</span></td>
            <td>{{ col.graph_enabled ? '✅' : '—' }}</td>
            <td>{{ col.ai_summary_enabled ? '✅' : '—' }}</td>
            <td>
              <NuxtLink :to="`/c/${col.name}/config`" class="fr-btn fr-btn--sm fr-btn--tertiary">
                Config
              </NuxtLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Ingestion jobs -->
    <h2 class="fr-h4 fr-mt-6w">Jobs d'ingestion</h2>
    <div v-if="jobs.length === 0" class="fr-text--sm">Aucun job.</div>
    <div v-else class="fr-table">
      <table>
        <thead>
          <tr><th>Job</th><th>Collection</th><th>Progression</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.job_id">
            <td class="fr-text--sm">{{ job.job_id }}</td>
            <td>{{ job.collection }}</td>
            <td>
              <progress :value="job.uploaded_chunks" :max="job.total_chunks" style="width:100px;"></progress>
              {{ job.uploaded_chunks }}/{{ job.total_chunks }}
            </td>
            <td><span class="fr-badge fr-badge--sm">{{ job.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { get, post } = useApi()

const collections = ref<any[]>([])
const jobs = ref<any[]>([])
const templateCount = ref(0)
const syncing = ref(false)
const syncResult = ref<any>(null)

async function syncAll() {
  syncing.value = true
  try {
    syncResult.value = await post('/api/sync')
  } catch (e) {}
  syncing.value = false
}

onMounted(async () => {
  try {
    const colData = await get('/api/collections')
    collections.value = colData.collections || []

    const jobData = await get('/api/ingest/jobs')
    jobs.value = jobData.jobs || []

    const tplData = await get('/api/collections/templates')
    templateCount.value = tplData.templates?.length || 0
  } catch (e) {}
})
</script>
