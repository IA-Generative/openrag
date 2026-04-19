<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Upload</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Uploader des documents — {{ id }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-8">
        <!-- File upload -->
        <div class="fr-upload-group">
          <label class="fr-label" for="file">Fichier a indexer</label>
          <input id="file" type="file" class="fr-upload" @change="onFileChange"
                 accept=".pdf,.txt,.md,.docx,.pptx,.doc,.eml,.png,.jpeg,.jpg" />
        </div>

        <!-- Strategy -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="strategy">Strategie de decoupage</label>
          <select id="strategy" class="fr-select" v-model="strategy">
            <option value="auto">Automatique (detection du type)</option>
            <option value="article">Par article (code juridique)</option>
            <option value="section">Par section (rapport)</option>
            <option value="qr">Par Q&R (FAQ)</option>
            <option value="length">Par longueur fixe</option>
          </select>
        </div>

        <!-- Sensitivity -->
        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label" for="sensitivity">Sensibilite</label>
          <select id="sensitivity" class="fr-select" v-model="sensitivity">
            <option value="public">Public</option>
            <option value="internal">Interne</option>
            <option value="restricted">Restreint</option>
            <option value="confidential">Confidentiel</option>
          </select>
        </div>

        <!-- Submit -->
        <button class="fr-btn fr-mt-4w" @click="upload" :disabled="!file || uploading">
          {{ uploading ? 'Envoi en cours...' : 'Indexer le document' }}
        </button>

        <!-- Result -->
        <div v-if="result" class="fr-alert fr-alert--success fr-mt-4w">
          <p>{{ result.total_chunks }} chunks crees (job {{ result.job_id }})</p>
          <p class="fr-text--sm">Suivi : <a :href="`${baseUrl}/api/ingest/jobs/${result.job_id}`" target="_blank">{{ result.job_id }}</a></p>
        </div>

        <div v-if="error" class="fr-alert fr-alert--error fr-mt-4w">
          <p>{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { uploadFile, baseUrl } = useApi()

const file = ref<File | null>(null)
const strategy = ref('auto')
const sensitivity = ref('public')
const uploading = ref(false)
const result = ref<any>(null)
const error = ref('')

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] || null
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  result.value = null
  error.value = ''

  try {
    result.value = await uploadFile(`/api/ingest/${id}`, file.value, {
      strategy: strategy.value,
      sensitivity: sensitivity.value,
    })
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}
</script>
