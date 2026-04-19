<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Creer</NuxtLink></li>
        <li aria-current="page">Donnees</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Charger les donnees — {{ collection }}</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 3 sur 5 — Ajoutez vos documents a la collection</p>

    <WizardStepper :current-step="3" />

    <div v-if="!collection" class="fr-alert fr-alert--warning fr-mb-4w">
      <p>Aucune collection specifiee. <NuxtLink to="/admin/create">Retour a l'etape 1</NuxtLink></p>
    </div>

    <div v-else class="fr-col-8">
      <!-- Source selector -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <div class="fr-segmented fr-segmented--sm fr-mt-2w fr-mb-2w">
              <div class="fr-segmented__elements">
                <div class="fr-segmented__element">
                  <input type="radio" id="tab-file" name="upload-mode" value="file"
                         v-model="tab" :disabled="uploaded" />
                  <label class="fr-label" for="tab-file">📄 Fichier local</label>
                </div>
                <div class="fr-segmented__element">
                  <input type="radio" id="tab-url" name="upload-mode" value="url"
                         v-model="tab" :disabled="uploaded" />
                  <label class="fr-label" for="tab-url">🌐 URL distante</label>
                </div>
              </div>
            </div>

            <!-- Mode: Fichier local -->
            <div v-if="tab === 'file' && !uploaded">
              <div class="fr-upload-group fr-mt-2w">
                <label class="fr-label">
                  Deposer un fichier depuis votre ordinateur
                  <span class="fr-hint-text">Formats acceptes : PDF, MD, TXT, DOCX, PPTX, images, audio</span>
                </label>
                <input type="file" class="fr-upload" @change="onFile"
                       accept=".pdf,.txt,.md,.docx,.pptx,.doc,.eml,.png,.jpeg,.jpg" />
              </div>

              <div v-if="file" class="fr-mt-2w">
                <p class="fr-text--sm">
                  Fichier selectionne : <strong>{{ file.name }}</strong> ({{ formatSize(file.size) }})
                </p>
              </div>
            </div>

            <!-- Mode: URL distante -->
            <div v-if="tab === 'url' && !uploaded">
              <div class="fr-input-group fr-mt-2w">
                <label class="fr-label">
                  URL d'un fichier unique accessible en ligne
                  <span class="fr-hint-text">Lien direct vers un PDF, DOCX, TXT, MD, etc.</span>
                </label>
                <input class="fr-input" v-model="remoteUrl"
                       placeholder="https://example.gouv.fr/documents/rapport.pdf" />
              </div>

              <!-- Verification -->
              <div v-if="remoteUrl && (!remoteCheck || remoteCheck.status === 'error')" class="fr-mt-1w">
                <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="checkRemoteUrl">
                  Verifier l'accessibilite
                </button>
              </div>

              <div v-if="remoteCheck && remoteCheck.status === 'checking'" class="fr-mt-1w">
                <p class="fr-text--sm" style="color:#666;">Verification en cours...</p>
              </div>

              <div v-if="remoteCheck && remoteCheck.status === 'error'" class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w">
                <p>{{ remoteCheck.message }}</p>
              </div>

              <!-- Verification OK: info + preview -->
              <div v-if="remoteCheck && remoteCheck.status === 'ok'" class="fr-mt-2w">
                <div class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w">
                  <p>
                    Document accessible — <strong>{{ remoteCheck.contentType }}</strong>
                    <span v-if="remoteCheck.size"> — {{ formatSize(remoteCheck.size) }}</span>
                  </p>
                  <p v-if="remoteCheck.githubConverted" class="fr-text--sm fr-mt-1v">
                    L'URL GitHub a ete convertie automatiquement vers le fichier brut (raw).
                  </p>
                </div>

                <details class="fr-mb-1w" open>
                  <summary class="fr-text--sm" style="cursor:pointer;font-weight:bold;">
                    Apercu du document
                  </summary>
                  <div class="myrag-preview-frame fr-mt-1w">
                    <!-- Text preview fetched via backend -->
                    <div v-if="previewContent !== null" class="myrag-preview-content">
                      <pre>{{ previewContent }}</pre>
                      <p v-if="previewTruncated" class="fr-text--xs" style="color:#666;text-align:center;margin-top:0.5rem;">
                        ... affichage limite aux {{ previewMaxChars }} premiers caracteres
                      </p>
                    </div>
                    <div v-else-if="previewLoading" style="text-align:center;padding:2rem;color:#666;">
                      Chargement de l'apercu...
                    </div>
                    <div v-else class="myrag-preview-placeholder">
                      <p class="fr-text--sm" style="text-align:center;color:#666;padding:2rem;">
                        Apercu non disponible pour le format <strong>{{ remoteCheck.contentType }}</strong>.<br>
                        Le document sera telecharge et indexe directement.
                      </p>
                    </div>
                  </div>
                </details>
              </div>
            </div>

            <!-- Upload progress bar (shown during upload for both modes) -->
            <div v-if="uploading" class="fr-mt-2w">
              <progress style="width:100%;" :value="uploadProgress" max="100"></progress>
              <p class="fr-text--sm">Envoi en cours... {{ uploadProgress }}%</p>
            </div>

            <!-- Upload done confirmation -->
            <div v-if="uploaded" class="fr-alert fr-alert--success fr-alert--sm fr-mt-2w">
              <p>
                <strong>{{ uploadedName }}</strong> envoye avec succes.
                L'indexation s'effectue en tache de fond — vous pouvez passer a l'etape suivante.
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Indexation progress (background) -->
      <div v-if="job" class="fr-card fr-mb-4w" :class="job.status === 'done' ? 'fr-card--grey' : ''">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">
              {{ job.status === 'done' ? '✅' : job.status === 'done_with_errors' ? '⚠️' : '⏳' }}
              Indexation en tache de fond
            </h3>
            <progress :value="job.uploaded_chunks" :max="job.total_chunks" style="width:100%;"></progress>
            <p class="fr-text--sm fr-mt-1w">
              {{ job.uploaded_chunks }} / {{ job.total_chunks }} chunks indexes ({{ job.progress_pct }}%)
              <span v-if="job.status === 'uploading'"> — en cours</span>
              <span v-if="job.status === 'done'" style="color:#18753c;"> — termine</span>
              <span v-if="job.status === 'done_with_errors'" style="color:#b34000;"> — termine avec erreurs</span>
            </p>
            <p class="fr-hint-text fr-mt-1w">
              Vous n'avez pas besoin d'attendre la fin de l'indexation pour continuer.
            </p>
          </div>
        </div>
      </div>

      <!-- Upload error -->
      <div v-if="uploadError" class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w">
        <p>{{ uploadError }}</p>
      </div>

      <!-- Navigation -->
      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink :to="`/admin/create/step-2?source=${source}`" class="fr-btn fr-btn--secondary">
          ← Precedent
        </NuxtLink>

        <!-- Main action button: changes role depending on state -->
        <button v-if="uploaded" class="fr-btn" @click="next">
          Suivant →
        </button>
        <button v-else class="fr-btn" @click="handleMainAction"
                :disabled="!isReadyToUpload || uploading">
          {{ uploading ? 'Chargement en cours...' : 'Charger la donnee →' }}
        </button>
      </div>

      <p v-if="!uploaded && !uploading" class="fr-hint-text fr-mt-1w">
        <span v-if="tab === 'file' && !file">Selectionnez un fichier pour continuer.</span>
        <span v-else-if="tab === 'url' && (!remoteCheck || remoteCheck.status !== 'ok')">Saisissez une URL et verifiez son accessibilite.</span>
        <span v-else>Cliquez sur « Charger la donnee » pour lancer l'envoi et l'indexation.</span>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const collection = route.query.collection as string
const source = (route.query.source as string) || ''
const { uploadFile, post, get } = useApi()

const tab = ref<'file' | 'url'>('file')
const file = ref<File | null>(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploaded = ref(false)
const uploadedName = ref('')
const job = ref<any>(null)
const remoteUrl = ref('')
const remoteCheck = ref<{ status: string; contentType?: string; size?: number; message?: string; githubConverted?: boolean } | null>(null)
const uploadError = ref('')
const previewContent = ref<string | null>(null)
const previewLoading = ref(false)
const previewTruncated = ref(false)
const previewMaxChars = 4000

const isReadyToUpload = computed(() => {
  if (tab.value === 'file') return !!file.value
  if (tab.value === 'url') return remoteCheck.value?.status === 'ok'
  return false
})

function onFile(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] || null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function isPreviewableText(contentType: string): boolean {
  return contentType.startsWith('text/') || ['application/json', 'application/xml', 'application/javascript'].includes(contentType)
}

/**
 * Detect GitHub URLs and normalize them.
 * - Repo root (github.com/user/repo) → error, not a file
 * - Blob URL (github.com/user/repo/blob/branch/file) → raw.githubusercontent.com/...
 * - Already raw → pass through
 */
function isGithubRepoUrl(url: string): boolean {
  return /^https?:\/\/github\.com\/[^/]+\/[^/]+\/?$/.test(url)
    || /^https?:\/\/github\.com\/[^/]+\/[^/]+\/tree\//.test(url)
}

function normalizeGithubUrl(url: string): string {
  const match = url.match(/^https?:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\/(.+)$/)
  if (match) {
    return `https://raw.githubusercontent.com/${match[1]}/${match[2]}/${match[3]}`
  }
  return url
}

async function handleMainAction() {
  if (tab.value === 'file') {
    await uploadLocalFile()
  } else {
    await uploadRemoteUrl()
  }
}

async function uploadLocalFile() {
  if (!file.value) return
  uploading.value = true
  uploadProgress.value = 0

  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) uploadProgress.value += 10
  }, 200)

  try {
    const result = await uploadFile(`/api/ingest/${collection}`, file.value, {
      strategy: 'auto', sensitivity: 'public',
    })
    clearInterval(progressInterval)
    uploadProgress.value = 100
    uploadedName.value = file.value.name
    uploading.value = false
    uploaded.value = true
    job.value = result

    pollJob(result.job_id)
  } catch (e) {
    clearInterval(progressInterval)
    uploading.value = false
    uploadError.value = 'Erreur lors du chargement du fichier. Verifiez que le serveur MyRAG est accessible.'
  }
}

async function uploadRemoteUrl() {
  uploading.value = true
  uploadProgress.value = 0

  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) uploadProgress.value += 15
  }, 300)

  try {
    const result = await post(`/api/ingest/${collection}/from-url`, {
      url: remoteUrl.value,
      strategy: 'auto',
      sensitivity: 'public',
    })
    clearInterval(progressInterval)
    uploadProgress.value = 100
    uploadedName.value = remoteUrl.value.split('/').pop() || remoteUrl.value
    uploading.value = false
    uploaded.value = true

    if (result?.job_id) {
      job.value = result
      pollJob(result.job_id)
    }
  } catch (e) {
    clearInterval(progressInterval)
    uploading.value = false
    uploadError.value = 'Erreur lors du chargement. Verifiez que le serveur MyRAG est accessible.'
  }
}

function pollJob(jobId: string) {
  const pollInterval = setInterval(async () => {
    try {
      const j = await get(`/api/ingest/jobs/${jobId}`)
      job.value = j
      if (j.status === 'done' || j.status === 'done_with_errors') {
        clearInterval(pollInterval)
      }
    } catch (e) {}
  }, 2000)
}

watch(remoteUrl, () => {
  remoteCheck.value = null
  previewContent.value = null
  previewTruncated.value = false
})

async function loadPreview(url: string, contentType: string) {
  // Only preview text-based formats
  if (!isPreviewableText(contentType)) {
    previewContent.value = null
    return
  }
  previewLoading.value = true
  try {
    const resp = await get(`/api/sources/preview-url?url=${encodeURIComponent(url)}&max_chars=${previewMaxChars}`)
    if (resp?.content) {
      previewContent.value = resp.content
      previewTruncated.value = resp.truncated || false
    }
  } catch {
    previewContent.value = null
  } finally {
    previewLoading.value = false
  }
}

async function checkRemoteUrl() {
  if (!remoteUrl.value) return

  // Reject GitHub repo/tree URLs (not a file)
  if (isGithubRepoUrl(remoteUrl.value)) {
    remoteCheck.value = {
      status: 'error',
      message: 'Cette URL pointe vers un depot ou dossier GitHub, pas un fichier. Utilisez l\'URL d\'un fichier specifique (bouton "Raw" ou lien vers un fichier dans le depot).',
    }
    return
  }

  // Auto-convert GitHub blob URLs to raw
  const normalized = normalizeGithubUrl(remoteUrl.value)
  const wasConverted = normalized !== remoteUrl.value
  if (wasConverted) {
    remoteUrl.value = normalized
  }

  remoteCheck.value = { status: 'checking' }

  try {
    const resp = await get(`/api/sources/check-url?url=${encodeURIComponent(remoteUrl.value)}`)
    if (resp?.accessible) {
      remoteCheck.value = {
        status: 'ok',
        contentType: resp.content_type || 'inconnu',
        size: resp.content_length || undefined,
        githubConverted: wasConverted,
      }
      loadPreview(remoteUrl.value, resp.content_type || '')
    } else {
      const detail = resp?.error
        ? `Erreur : ${resp.error}`
        : resp?.status_code
          ? `Le serveur a repondu HTTP ${resp.status_code}.`
          : 'Le document n\'est pas accessible.'
      remoteCheck.value = { status: 'error', message: `${detail} Verifiez l'URL et que le fichier est public.` }
    }
  } catch {
    remoteCheck.value = { status: 'error', message: 'Impossible de joindre le serveur MyRAG pour verifier l\'URL.' }
  }
}

function next() {
  router.push(`/admin/create/step-4?collection=${collection}`)
}
</script>

<style scoped>
.myrag-preview-frame {
  max-height: 320px;
  overflow: hidden;
  border-radius: 4px;
}

.myrag-preview-content {
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f6f6f6;
  max-height: 300px;
  overflow-y: auto;
}

.myrag-preview-content pre {
  margin: 0;
  padding: 1rem;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.8rem;
  line-height: 1.5;
}

.myrag-preview-placeholder {
  border: 1px dashed #ccc;
  border-radius: 4px;
  background: #f9f9f9;
}
</style>
