<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Creer</NuxtLink></li>
        <li aria-current="page">Donnees</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Associer la donnee — {{ collection }}</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 2 sur 4 — Indexez au moins un document</p>

    <WizardStepper :current-step="2" />

    <div v-if="!collection" class="fr-alert fr-alert--warning fr-mb-4w">
      <p>Aucune collection specifiee. <NuxtLink to="/admin/create">Retour a l'etape 1</NuxtLink></p>
    </div>

    <div v-else class="fr-col-8">
      <!-- Upload -->
      <div class="fr-upload-group fr-mb-4w">
        <label class="fr-label">Deposer un fichier</label>
        <input type="file" class="fr-upload" @change="onFile"
               accept=".pdf,.txt,.md,.docx,.pptx,.doc,.eml,.png,.jpeg,.jpg" />
      </div>

      <button v-if="file" class="fr-btn fr-mb-4w" @click="upload" :disabled="uploading">
        {{ uploading ? 'Indexation...' : 'Indexer le document' }}
      </button>

      <!-- Job progress -->
      <div v-if="job" class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <p>{{ job.uploaded_chunks }}/{{ job.total_chunks }} chunks ({{ job.progress_pct }}%)</p>
            <progress :value="job.uploaded_chunks" :max="job.total_chunks" style="width:100%;"></progress>
            <p class="fr-text--sm">Status: {{ job.status }}</p>
          </div>
        </div>
      </div>

      <!-- Legifrance source -->
      <div class="fr-input-group fr-mt-4w">
        <label class="fr-label">Ou coller une URL Legifrance</label>
        <input class="fr-input" v-model="legiUrl" placeholder="https://www.legifrance.gouv.fr/codes/texte_lc/..." />
      </div>
      <button v-if="legiUrl" class="fr-btn fr-btn--secondary fr-btn--sm fr-mt-1w" @click="addLegiSource">
        Ajouter la source
      </button>

      <!-- Navigation -->
      <div class="fr-btns-group fr-btns-group--inline fr-mt-6w">
        <NuxtLink to="/admin/create" class="fr-btn fr-btn--secondary">← Precedent</NuxtLink>
        <button class="fr-btn" @click="next" :disabled="!hasDocuments">
          Suivant →
        </button>
      </div>

      <p v-if="!hasDocuments" class="fr-text--sm fr-mt-1w" style="color:#b34000;">
        ⚠ Au moins un document est requis pour continuer.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const collection = route.query.collection as string
const { uploadFile, post, get } = useApi()

const file = ref<File | null>(null)
const uploading = ref(false)
const job = ref<any>(null)
const legiUrl = ref('')
const hasDocuments = ref(false)

function onFile(e: Event) { file.value = (e.target as HTMLInputElement).files?.[0] || null }

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const result = await uploadFile(`/api/ingest/${collection}`, file.value, { strategy: 'auto', sensitivity: 'public' })
    job.value = result
    // Poll progress
    const interval = setInterval(async () => {
      const j = await get(`/api/ingest/jobs/${result.job_id}`)
      job.value = j
      if (j.status === 'done' || j.status === 'done_with_errors') {
        clearInterval(interval)
        hasDocuments.value = true
        uploading.value = false
      }
    }, 2000)
  } catch (e) { uploading.value = false }
}

async function addLegiSource() {
  await post('/api/sources/legifrance/parse-url', { url: legiUrl.value, collection })
}

function next() { router.push(`/admin/create/step-3?collection=${collection}`) }
</script>
